"""Upload watermarked contracts with a mixed date notation or conflicting effective dates."""

import argparse
import hashlib

from contract_milestones import PROFILE, documents
from generate import ROOT, WATERMARK, embedded_font, pdf
from reinspection_register import prepare
from run import get, post, submit, wait


SCENARIOS = {"mixed": ("生效日混用分隔符", "2026/9月1日"), "conflict": ("同份合同列明两个生效日", "2026年9月1日")}


def read_back(cid, title, originals, report, *, only=None):
    """Simulate the auditor only for known columns in these generated materials."""
    columns = {"合同编号":"contract_id", "甲方签章":"buyer_signature", "乙方签章":"seller_signature", "验收签认":"acceptance_signer",
               "遗留事项":"acceptance_exception", "款项用途":"payment_designation", "生效确认日期":"effect_on"}
    endpoint = "/api/cases/" + cid
    for name, (digest, page) in originals.items():
        if only is not None and name not in only:
            continue
        for line in page["text"].splitlines():
            label, sep, value = line.partition("：")
            if not sep or label not in columns:
                continue
            field = columns[label]
            case = get(endpoint)
            assert case["title"] == title and not case["decisions"] and case["status"] == "ready"
            assert {d["name"]:d["sha256"] for d in case["documents"]} == {n:d for n,(d,_) in originals.items()}
            doc = next(d["id"] for d in case["documents"] if d["name"] == name)
            facts = [f for f in report["graph"]["facts"] if f["doc"] == doc and f["page"] == 1]
            matches = [f for f in facts if (f.get("source_line") or {}).get("text") == line]
            if not matches and label == "款项用途":
                matches = [f for f in facts if f["field"] == field and not f.get("source_line") and f["value"] == value]
            assert len(matches) <= 1 and all(f["source_sha256"] == digest and f["page_sha256"] == page["sha256"] for f in matches)
            observed = matches[0] if matches else None
            note = {"rev":case["rev"],"reviewer":"水印演练核图","note":"按本次虚构材料的编号、页图和原行模拟核对。"}
            if observed and (observed["field"], observed["quote"], observed["value"]) == (field, line, value):
                if observed["status"] == "confirmed" or observed["status"] == "anchored" and "签" not in label:
                    continue
                post(endpoint + "/attest", {**note, "decision":"confirm", "facts":[observed["id"]]})
            else:
                payload = {**note,"doc":doc,"page":1,"field":field,"value":value,"quote":line,
                           "region":observed["region"] if observed else "middle"}
                if observed:
                    payload["target"] = observed["id"]
                post(endpoint + "/amend", payload)
            report = wait(cid)
    return report


def run(seed, mode, check_fields=False):
    label, value = SCENARIOS[mode]
    code = hashlib.sha256((seed + mode).encode()).hexdigest()[:8].upper()
    folder = ROOT / "合同日期原行" / code
    folder.mkdir(exist_ok=True, parents=True)
    records = documents(code, "complete")
    contract = records["采购合同"]
    position = next(i for i, row in enumerate(contract) if row[0] == "实际生效日期")
    contract[position] = ("实际生效日期", value)
    if mode == "conflict":
        contract.insert(position + 1, ("生效确认日期", "2026年9月23日"))
    paths, originals = [], {}
    font = embedded_font("PrintedCalendarCJK")
    for title, rows in records.items():
        path = folder / (title + ".pdf")
        pdf(path, title, rows, font=font)
        page, = prepare(path, 1, save_images=False)
        lines = page["text"].splitlines()
        assert lines[0] == WATERMARK and all(k + "：" + v in lines for k, v in rows)
        paths.append(path)
        originals[path.name] = (hashlib.sha256(path.read_bytes()).hexdigest(), page)
    title = "合成演练 · " + label
    cid = submit(title, paths, seed + "-" + mode, PROFILE)
    print(cid, flush=True)
    case = get("/api/cases/" + cid)
    assert {d["name"]: d["sha256"] for d in case["documents"]} == {n:d for n,(d,_) in originals.items()}
    report = wait(cid)
    if check_fields:
        report = read_back(cid, title, originals, report)
    finding = next(f for f in report["findings"] if f["rule"] == "H01")
    check = next(r for r in finding["effect_review"]["calendar"] if r["field"] == "effect_on")
    assert check["state"] == ("notation" if mode == "mixed" else "conflict") and check["date"] is None
    assert all(r["status"] != "ok" for r in report["findings"] if r["rule"] in ("H01", "H04", "H05"))
    print(label, check, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=SCENARIOS)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--check-fields", action="store_true")
    args = parser.parse_args()
    run(args.seed, args.mode, args.check_fields)
