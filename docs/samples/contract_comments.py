"""Compare three watermarked contracts with the same printed payment schedule."""

import argparse
from hashlib import sha256

from docx import Document
from docx.oxml.ns import qn

from contract_milestones import PROFILE, documents, normalize
from generate import ROOT, WATERMARK, embedded_font, pdf
from printed_dates import read_back
from reinspection_register import prepare
from run import get, post, submit, wait
from word_percentage import save_document, word_file

CASES = {"clean": None, "second": "第二期", "third": "第三期"}
NOTES = {"第二期": "建议本期付款前取得双方签认的技术终验单，待双方签订补充协议。",
         "第三期": "建议本期付款前取得双方签认的质保复核单，待双方签订补充协议。"}


def materials(seed, mode):
    code = sha256(seed.encode()).hexdigest()[:8].upper()
    folder = ROOT / "合同分期批注" / code / mode
    folder.mkdir(parents=True, exist_ok=True)
    records = documents(code, "complete")
    title = "采购合同"
    contract = folder / (title + ".docx")
    word_file(contract, records.pop(title))
    doc = Document(contract)
    for paragraph in doc.paragraphs:
        label, _, clause = paragraph.text.partition("：")
        if label not in NOTES:
            continue
        condition, separator, amount = clause.partition("支付")
        assert separator and amount.endswith("%")
        paragraph.runs[0].text = label + "："
        selection = paragraph.add_run(condition)
        paragraph.add_run(separator + amount)
        if CASES[mode] == label:
            comment = doc.add_comment(selection, text=NOTES[label], author="演练合同复核员", initials="YL")
            comment._element.set(qn("w:date"), "2026-09-02T02:00:00Z")
    save_document(doc, contract)
    paths = [contract]
    font = embedded_font("ContractReviewFixture")
    for title, rows in records.items():
        path = folder / (title + ".pdf")
        pdf(path, title, rows, font=font)
        paths.append(path)
    return paths


def reconcile_rows(cid, title, originals, report):
    endpoint = "/api/cases/" + cid
    fields = {"付款条款": "payment_term", "第一期": "payment_stage", "第二期": "payment_stage",
              "第三期": "payment_stage", "验收范围": "acceptance_scope"}
    for name, (digest, page) in originals.items():
        if name not in {"采购合同.docx", "验收报告.pdf"}:
            continue
        for number, line in enumerate(page["text"].splitlines(), 1):
            key, _, value = line.partition("：")
            if key not in fields:
                continue
            field = fields[key]
            case = get(endpoint)
            assert case["title"] == title and case["status"] == "ready" and not case["decisions"]
            assert {d["name"]: d["sha256"] for d in case["documents"]} == {k: v[0] for k, v in originals.items()}
            assert page["text"].splitlines().count(line) == 1 and page["layer"]["lines"][str(number)]
            doc, = [d["id"] for d in case["documents"] if d["name"] == name]
            facts = [f for f in report["graph"]["facts"] if f["doc"] == doc and f["page"] == 1]
            matches = [f for f in facts if (f.get("source_line") or {}).get("number") == number]
            if not matches:
                matches = [f for f in facts if f["field"] == field and
                           normalize(f["quote"]).startswith(normalize(key + "：" + value))]
            assert len(matches) <= 1 and all(f["source_sha256"] == digest and f["page_sha256"] == page["sha256"] for f in matches)
            previous = matches[0] if matches else None
            if previous and previous["field"] == field and previous["quote"] == line and previous["value"] == value and previous["status"] in {"confirmed", "anchored"}:
                continue
            note = {"rev": case["rev"], "reviewer": "水印演练核图", "note": f"按本次水印原件第 {number} 行逐字回读该栏，保留原提取记录。"}
            post(endpoint + "/amend", {**note, "doc": doc, "page": 1, "target": previous["id"] if previous else None,
                 "field": field, "value": value, "quote": line, "region": previous["region"] if previous else "middle"})
            report = wait(cid)
    return report


def run(seed, modes, upload):
    pending = []
    for mode in modes:
        paths = materials(seed, mode)
        if not upload:
            print(mode, paths[0])
            continue
        originals = {}
        for path in paths:
            page, = prepare(path, 1, False)
            assert normalize(page["text"].splitlines()[0]) == normalize(WATERMARK)
            if path.suffix == ".docx":
                assert normalize("第二期：最终验收合格后支付60%") in [normalize(s) for s in page["text"].splitlines()]
                assert not any(note in page["text"] for note in NOTES.values())
            originals[path.name] = (sha256(path.read_bytes()).hexdigest(), page)
        title = "合成演练 · " + (CASES[mode] + "付款前提待签补充协议" if CASES[mode] else "分期合同无标准批注")
        key = sha256("".join(d for d, page in originals.values()).encode()).hexdigest()[:14]
        cid = submit(title, paths, seed + "-" + key, PROFILE)
        print(mode, cid, flush=True)
        pending.append((mode, title, cid, originals))
    for mode, title, cid, originals in pending:
        paper = reconcile_rows(cid, title, originals, read_back(cid, title, originals, wait(cid)))
        plan, = [f for f in paper["findings"] if f["rule"] == "H03"]
        record, = paper["graph"]["contract_word_reviews"]["documents"]
        assert record["coverage"] == "complete" and record["count"] == int(mode != "clean")
        assert plan["status"] == ("ok" if mode == "clean" else "missing"), plan["detail"]
        if mode != "clean":
            note, = record["notes"]
            stage = CASES[mode]
            assert note["text"] == NOTES[stage] and note["location"]["page"] == 1
            assert note["anchor"]["quote"].startswith(stage + "：") and note["location"]["facts"]
            linked = [f for f in paper["findings"] if note["id"] in f["evidence"]]
            assert [(f["rule"], f.get("stage", {}).get("name")) for f in linked] == (
                [("H03", None), ("H04", stage)] + ([("H05", stage)] if mode == "second" else []))
            assert all(f["status"] != "ok" for f in linked)
        print(mode, cid, "R" + str(get("/api/cases/" + cid)["rev"]), plan["status"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--case", nargs="+", choices=CASES, default=list(CASES))
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    run(args.seed, args.case, args.run)
