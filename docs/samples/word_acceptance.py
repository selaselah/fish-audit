"""Paired watermarked Word acceptance reports with a reviewer's comment on the result."""

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

LIMIT = "本次仅核对到货数量，制冷性能须由技术部另行终验。"
AUTHOR = "演练仓储复核员"
CASES = {"clean": "Word 终验正文无审阅批注", "limited": "Word 验收合格栏旁的数量签收批注",
         "hot": "Word 验收温度超限且附数量签收批注"}


def materials(seed, mode):
    code = sha256(seed.encode()).hexdigest()[:8].upper()
    folder = ROOT / "Word验收批注" / code / mode
    folder.mkdir(exist_ok=True, parents=True)
    records = documents(code, "complete")
    rows = records["验收报告"]
    if mode == "hot":
        rows = [(k, "柜温8℃" if k == "实测结果" else v) for k, v in rows]
    target = folder / "验收报告.docx"
    word_file(target, rows, "验收报告")
    doc = Document(target)
    paragraph, = [p for p in doc.paragraphs if p.text == "验收结论：合格"]
    paragraph.runs[0].text = "验收结论："
    result = paragraph.add_run("合格")
    if mode != "clean":
        note = doc.add_comment(result, text=LIMIT, author=AUTHOR, initials="YL")
        note._element.set(qn("w:date"), "2026-09-20T03:00:00Z")
    save_document(doc, target)
    paths = []
    font = embedded_font("AcceptanceCommentFixture")
    for title, fields in records.items():
        if title == "验收报告":
            paths.append(target)
        else:
            path = folder / (title + ".pdf")
            pdf(path, title, fields, font=font)
            paths.append(path)
    return paths


def check_scope(cid,title,originals,report):
    case=get("/api/cases/"+cid)
    assert case["title"]==title and case["status"]=="ready" and not case["decisions"]
    assert {d["name"]:d["sha256"] for d in case["documents"]}=={name:raw for name,(raw,_) in originals.items()}
    digest,page=originals["验收报告.docx"]
    quote="验收范围：全部交付终验"
    match,=[f for f in report["graph"]["facts"] if f["name"]=="验收报告.docx" and f["field"]=="acceptance_scope" and f["quote"]==quote]
    assert match["value"]=="全部交付终验" and match["source_sha256"]==digest and match["page_sha256"]==page["sha256"]
    line=page["text"].splitlines().index(quote)+1
    assert match["source_line"]=={"number":line,"text":quote,"rects":page["layer"]["lines"][str(line)]}
    if match["status"]=="visual":
        post("/api/cases/"+cid+"/attest",{"rev":case["rev"],"facts":[match["id"]],"decision":"confirm",
            "reviewer":"水印演练核图","note":"已按此水印原件的第八行核对所印验收范围。"})
        return wait(cid)
    return report


def verify_result(mode, report):
    graph = report["graph"]
    finding, = [f for f in report["findings"] if f["rule"] == "H02"]
    doc, = graph["acceptance_word_reviews"]["documents"]
    assert doc["coverage"] == "complete" and doc["count"] == (0 if mode == "clean" else 1)
    assert finding["status"] == {"clean": "ok", "limited": "risk", "hot": "issue"}[mode]
    assert finding["acceptance_comments"]["status"] == ("ok" if mode == "clean" else "risk")
    if doc["notes"]:
        note, = doc["notes"]
        assert note["text"] == LIMIT and note["author"] == AUTHOR
        assert note["anchor"]["selected"] == "合格" and note["anchor"]["quote"] == "验收结论：合格"
        assert note["location"]["page"] == 1 and note["location"]["line"] == 9 and note["location"]["facts"]
        citations = [f for f in report["findings"] if note["id"] in f["evidence"] and f["rule"] in ("H01", "H02", "H03", "H04", "H05")]
        assert [(f["rule"], f.get("stage", {}).get("name")) for f in citations] == [
            ("H02", None), ("H04", "第二期"), ("H04", "第三期"), ("H05", "第二期")]
        edges = {(e["from"], e["to"]) for e in graph["edges"] if e["type"] == "supports_result"}
        assert all((note["id"], "finding/" + f["id"]) in edges for f in citations)
    return finding


def run(seed, modes, upload):
    pending = []
    for mode in modes:
        files = materials(seed, mode)
        print(mode, files[1].parent, flush=True)
        if not upload:
            continue
        originals = {}
        for path in files:
            page, = prepare(path, 1, False)
            assert normalize(page["text"].splitlines()[0]) == normalize(WATERMARK)
            if path.suffix == ".docx":
                assert "验收结论：合格" in page["text"].splitlines() and LIMIT not in page["text"]
                assert [note.text for note in Document(path).comments] == ([] if mode == "clean" else [LIMIT])
            originals[path.name] = (sha256(path.read_bytes()).hexdigest(), page)
        title = "合成演练 · " + CASES[mode]
        fingerprint = sha256("".join(digest for digest, _ in originals.values()).encode()).hexdigest()[:12]
        cid = submit(title, files, seed + "-" + mode + "-" + fingerprint, PROFILE)
        pending.append((mode, title, cid, originals))
        print(mode, cid, originals["验收报告.docx"][1]["sha256"], flush=True)
    for mode, title, cid, originals in pending:
        report = check_scope(cid,title,originals,read_back(cid, title, originals, wait(cid)))
        h02 = verify_result(mode, report)
        print(mode, cid, "R"+str(get("/api/cases/"+cid)["rev"]), report["policy"]["version"], h02["status"], h02["detail"], flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--case", nargs="+", choices=CASES, default=list(CASES))
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()
    run(args.seed, args.case, args.run)
