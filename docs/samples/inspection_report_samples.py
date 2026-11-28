"""Watermarked attachments for a signed acceptance that refers to a numbered inspection report."""

import argparse
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp

from contract_milestones import PROFILE, documents
from generate import ROOT, embedded_font, pdf
from pdf_signing import signed_copy
from run import submit, wait
from supplier_annotations import REASON


NUMBER = "JC-2026-018"
REQUIRED = f"终验质量结论以正式检测报告（编号：{NUMBER}）为准。"
SCENARIOS = {"different":"验收签名所引检测报告与附件编号不同", "matched":"验收签名所引检测报告已定位"}


def generate(seed):
    code = sha256(seed.encode()).hexdigest()[:8].upper()
    parent = ROOT / "签名所引检测报告"
    parent.mkdir(parents=True, exist_ok=True)
    folder = Path(mkdtemp(prefix=code+"-", dir=parent))
    font = embedded_font("InspectionReferenceCJK")
    records = documents(code, "complete")
    shared = []
    for title, fields in records.items():
        path = folder / (title+".pdf")
        pdf(path, title, fields, font=font)
        if title == "验收报告":
            quantity = signed_copy(path.read_bytes(), "DeliveryCount", reason=REASON)
            path.write_bytes(signed_copy(quantity, "InspectionReview", reason=REQUIRED))
        shared.append(path)
    sets = {}
    for mode in SCENARIOS:
        target = folder / mode
        target.mkdir()
        path = target / "随附资料.pdf"
        fields = [("报告编号", NUMBER if mode=="matched" else "JC-2026-081"),
                  records["验收报告"][0], ("检测项目","四门冷藏柜柜温"), ("检测结论","送检样机柜温符合约定值")]
        pdf(path, "检测报告", fields, font=font)
        sets[mode] = [*shared, path]
    return sets


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default="synthetic-inspection-reference-v1")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    cases = []
    for mode, paths in generate(args.seed).items():
        print(mode, paths[-1], flush=True)
        if args.run:
            key = sha256(b"".join(sha256(p.read_bytes()).digest() for p in paths)).hexdigest()
            cid = submit("合成演练 · "+SCENARIOS[mode], paths, key, PROFILE)
            cases.append((cid, mode))
            print(mode, cid, flush=True)
    for cid, mode in cases:
        report = wait(cid)
        rows = report["graph"]["signature_purposes"]["rows"]
        receipt, = [r["report_reference"] for r in rows if "report_reference" in r]
        assert receipt["state"] == mode and receipt["number"] == NUMBER
        assert report["result"]["human_required"]
