"""Watermarked payment approvals attached to a reinspection requiring a separate decision."""
import argparse
from pathlib import Path

from generate import embedded_font, pdf
from publish_batch_version import digest
from release_originals_demo import check_fields
from retest_use_notes import materials as inspection_materials
from run import submit


CASES = {
    "earlier": ("本期审批单列付款前一日", "第二期验收款", "FY-92B34462", "同意支付", 20),
    "later": ("本期审批单列付款后一日", "第二期验收款", "FY-92B34462", "同意支付", 22),
    "other_stage": ("所附审批单仅列第三期质保金", "第三期质保金", "FY-92B34462", "同意支付", 20),
    "refused": ("第二期审批决定列不同意支付", "第二期验收款", "FY-92B34462", "不同意支付", 20),
    "same_day": ("本期审批与付款同日", "第二期验收款", "FY-92B34462", "同意支付", 21),
    "other_receipt": ("所附审批单另指初验报告", "第二期验收款", "YS-92B34462", "同意支付", 20),
}
MASTER = "63d43ad3faf766111aef557d6f619aaefbc163fb1153c743fb1fe7f69ee87593"


def check_originals(archive, key, case, folder):
    fields=("repaired_on","defect_number","repair_number")
    check_fields(archive,key,case,folder,case_title=CASES[key][0],master_hash=MASTER,kind="bank_receipt",
                 reviewer="付款审批水印核字",visual_fields=fields,missing_fields=fields)


def materials(folder, key):
    _, files, profile = inspection_materials(folder, "approval")
    title, stage, number, decision, day = CASES[key]
    sheet = folder / "付款审批单.pdf"
    rows = [("合同编号", "YL-LY-92B34462"), ("付款户名", "青禾演练采购中心"), ("收款户名", "云桥演练设备中心"),
            ("审批期次", stage), ("所据验收单号", number), ("审批岗位", "财务负责人"),
            ("审批决定", decision), ("审批日期", f"2026年9月{day}日")]
    pdf(sheet, sheet.stem, rows, font=embedded_font("InstallmentApproval"))
    return title, [*files, sheet], profile


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--case", choices=CASES, action="append")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--check-against", type=Path, help="按原有 R11 水印母本逐行核字")
    args = parser.parse_args()
    if args.check_against and not args.run:
        parser.error("--check-against 需同时指定 --run")
    cases={}
    for key in args.case or CASES:
        title, files, profile = materials(args.folder / key, key)
        fingerprint = digest("".join(digest(f.read_bytes()) for f in files).encode())
        result = submit("合成演练 · " + title, files, "installment-approval-" + fingerprint, profile) if args.run else files[-1]
        print(key, result, flush=True)
        if args.run:
            cases[key]=result
    if args.check_against:
        for key,case in cases.items():
            check_originals(args.check_against,key,case,args.folder/key)
