"""Watermarked attachments for a signed acceptance that refers to a numbered inspection report."""

import argparse
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp

from contract_milestones import PROFILE, documents
from generate import ROOT, WATERMARK, embedded_font, pdf
from pdf_signing import signed_copy
from run import submit, wait
from supplier_annotations import REASON


NUMBER = "JC-2026-018"
REQUIRED = f"终验质量结论以正式检测报告（编号：{NUMBER}）为准。"
SCENARIOS = {"different":"验收签名所引检测报告与附件编号不同", "matched":"验收签名所引检测报告已定位"}
SCOPE_CASES = {"one":"四台逐台测温合同随附一台样机报告", "four":"四台逐台测温合同随附四台汇总报告"}


def generate(seed, *, scope=False):
    code = sha256(seed.encode()).hexdigest()[:8].upper()
    parent = ROOT / "签名所引检测报告"
    parent.mkdir(parents=True, exist_ok=True)
    folder = Path(mkdtemp(prefix=code+"-", dir=parent))
    font = embedded_font("InspectionReferenceCJK")
    records = documents(code, "complete")
    if scope:
        records["采购合同"].insert(12, ("性能检测要求","全部交付设备逐台测温"))
    shared = []
    for title, fields in records.items():
        path = folder / (title+".pdf")
        pdf(path, title, fields, font=font)
        if title == "验收报告":
            quantity = signed_copy(path.read_bytes(), "DeliveryCount", reason=REASON)
            path.write_bytes(signed_copy(quantity, "InspectionReview", reason=REQUIRED))
        shared.append(path)
    sets = {}
    for mode in SCOPE_CASES if scope else SCENARIOS:
        target = folder / mode
        target.mkdir()
        path = target / "随附资料.pdf"
        fields = [("报告编号", NUMBER if mode=="matched" else "JC-2026-081"),
                  records["验收报告"][0], ("检测项目","四门冷藏柜柜温"), ("检测结论","送检样机柜温符合约定值")]
        if scope:
            fields[0] = ("报告编号", NUMBER)
            fields[3:] = [("检测范围","送检样机" if mode=="one" else "本合同全部交付设备"),
                          ("实际测温台数","1台" if mode=="one" else "4台"),
                          ("检测结论","送检样机柜温符合约定值" if mode=="one" else "所检设备柜温符合约定值")]
        pdf(path, "检测报告", fields, font=font)
        sets[mode] = [*shared, path]
    return sets


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default="synthetic-inspection-reference-v1")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--scope", action="store_true", help="生成逐台测温合同与不同检测台数的报告")
    args = parser.parse_args()
    cases = []
    for mode, paths in generate(args.seed, scope=args.scope).items():
        print(mode, paths[-1], flush=True)
        if args.run:
            key = sha256(b"".join(sha256(p.read_bytes()).digest() for p in paths)).hexdigest()
            cid = submit("合成演练 · "+(SCOPE_CASES if args.scope else SCENARIOS)[mode], paths, key, PROFILE)
            cases.append((cid, mode, paths))
            print(mode, cid, flush=True)
    for cid, mode, paths in cases:
        report = wait(cid)
        if args.scope:
            from printed_dates import read_back
            from reinspection_register import prepare

            originals = {}
            for path in paths:
                page, = prepare(path, 1, save_images=False)
                assert page["text"].splitlines()[0] == WATERMARK
                originals[path.name] = (sha256(path.read_bytes()).hexdigest(), page)
            report = read_back(cid, "合成演练 · "+SCOPE_CASES[mode], originals, report,
                               only={p.name for p in paths[:-1]})
        rows = report["graph"]["signature_purposes"]["rows"]
        receipt, = [r["report_reference"] for r in rows if "report_reference" in r]
        assert receipt["state"] == ("matched" if args.scope else mode) and receipt["number"] == NUMBER
        if args.scope:
            assert receipt["coverage"]["state"] == ("short" if mode=="one" else "count_only")
        assert report["result"]["human_required"]
