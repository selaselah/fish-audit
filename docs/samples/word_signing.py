"""Check a typeset Word contract with the same amounts and delivery as a fulfilled purchase."""

import argparse
import hashlib

from contract_milestones import PROFILE, documents
from generate import WATERMARK
from reinspection_register import prepare
from run import get, post, submit, wait
from word_percentage import materials


TITLE = "合成演练 · 文字签章与三期付款"
FIELDS = {"甲方签章":"buyer_signature", "乙方签章":"seller_signature", "验收签认":"acceptance_signer",
          "遗留事项":"acceptance_exception"}


def run(seed):
    paths = materials(seed, split=False)
    source = documents(paths[0].parent.name, "complete")
    originals = {}
    for path in paths:
        page, = prepare(path, 1, save_images=False)
        assert "".join(WATERMARK.split()) == "".join(page["text"].splitlines()[0].split())
        if path.suffix == ".docx":
            assert page["layer"]["clause_text_only"]
        originals[path.name] = (hashlib.sha256(path.read_bytes()).hexdigest(), page)
    cid = submit(TITLE, paths, seed, PROFILE)
    print(cid, flush=True)
    base = "/api/cases/" + cid
    report = wait(cid)
    for path in paths:
        title = "采购合同" if path.suffix == ".docx" else path.stem
        for label, value in source[title]:
            if label not in FIELDS:
                continue
            case = get(base)
            assert case["title"] == TITLE and not case["decisions"] and {
                d["name"]:d["sha256"] for d in case["documents"]} == {k:v[0] for k,v in originals.items()}
            digest, page = originals[path.name]
            lines = [s for s in page["text"].splitlines() if s.split("：",1)[0] == label]
            assert len(lines) == 1 and lines[0].split("：",1)[1].strip() == value
            facts = [f for f in report["graph"]["facts"] if f["name"] == path.name and f["page"] == 1
                     and (f.get("source_line") or {}).get("text") == lines[0]]
            assert len(facts) <= 1 and all(f["source_sha256"] == digest and f["page_sha256"] == page["sha256"]
                                            and f["source_line"]["rects"] for f in facts)
            if not facts:
                assert not any(f["name"] == path.name and f["field"] == FIELDS[label] for f in report["graph"]["facts"])
            fact = facts[0] if facts else None
            note = {"rev":case["rev"],"reviewer":"合成演练核图","note":"依据本次水印原页模拟字段核对，仅确认该栏所印文字。"}
            if fact and fact["field"] == FIELDS[label] and fact["quote"] == lines[0] and fact["value"] == value:
                if fact["status"] == "confirmed" or label == "遗留事项" and fact["status"] == "anchored":
                    continue
                post(base + "/attest", {**note,"decision":"confirm","facts":[fact["id"]]})
            else:
                doc = next(d["id"] for d in case["documents"] if d["name"] == path.name)
                post(base + "/amend", {**note,"target":fact["id"] if fact else None,"doc":doc,"page":1,
                     "quote":lines[0],"value":value,"field":FIELDS[label],"region":fact["region"] if fact else "middle"})
            report = wait(cid)
    core = {k:[f["status"] for f in report["findings"] if f["rule"] == k] for k in ("H01","H02","H03","H04","H05")}
    check = next(f["effect_review"]["word_signatures"] for f in report["findings"] if f["rule"] == "H01")
    assert [r["state"] for r in check["rows"]] == ["checked"] * 2
    assert core == {"H01":["missing"],"H02":["ok"],"H03":["ok"],"H04":["missing"] * 3,"H05":["missing"]}, core
    print("R", get(base)["rev"], core, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="word-signing-20261126")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.run:
        run(args.run_id)
    else:
        print(materials(args.run_id, split=False)[0])
