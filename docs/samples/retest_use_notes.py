"""Watermarked reinspection records with different limits on their use for payment."""
import argparse
from pathlib import Path

from generate import embedded_font, pdf
from publish_batch_version import digest
from quality_reinspection import reinspection_records
from release_originals_demo import check_fields
from retest_receipts import materials as receipt_materials
from run import submit


MASTER = "aba96f7da21c84a4e5b74639ea46d048668ffad7240316a8af2b18223a546659"
CASES = {
    "ban": ("所引复验单明示不得作为第二期付款依据", "复验报告", "用途说明", "本复验单不得作为第二期验收款的付款依据。"),
    "approval": ("所引复验单要求第二期另经财务审批", "复验报告", "审批说明", "本复验单仅确认质量，第二期验收款须另经财务负责人审批。"),
    "conditional": ("所引复验单对第二期付款附有签字条件", "复验报告", "用途说明", "未经财务负责人签字，本复验单不得作为第二期验收款的付款依据。"),
    "other_document": ("初验单限制付款但回单明确引用复验单", "验收报告", "用途说明", "本验收单不得作为第二期验收款的付款依据。"),
    "other_stage": ("所引复验单限制第三期但回单支付第二期", "复验报告", "用途说明", "本复验单不得作为第三期质保金的付款依据。"),
}


def materials(folder, key):
    _, paths, profile = receipt_materials(None, folder, "final")
    title, source, label, value = CASES[key]
    rows = reinspection_records("92B34462", "closed")[source]
    pdf(folder / (source + ".pdf"), source, [*rows, (label, value)], font=embedded_font("QualityReinspectionCJK"))
    return title, paths, profile


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--check-against", type=Path, help="用指定 R8 水印证据包核字")
    args = parser.parse_args()
    if args.check_against and not args.run:
        parser.error("--check-against 需同时指定 --run")
    cases = {}
    for key in CASES:
        title, paths, profile = materials(args.folder / key, key)
        if args.run:
            fingerprint = digest("".join(digest(p.read_bytes()) for p in paths).encode())
            cases[key] = submit("合成演练 · " + title, paths, "inspection-use-" + fingerprint, profile)
        print(key, cases.get(key) or args.folder / key, flush=True)
    if args.check_against:
        for key, cid in cases.items():
            title, source, label, value = CASES[key]
            check_fields(args.check_against, key, cid, args.folder / key, case_title=title, master_hash=MASTER,
                         reviewer="用途附注水印核字", kind="bank_receipt", visual_fields=("repaired_on",),
                         addition=(source+".pdf", None, label, value, None))
            print(key, "水印原行已核", flush=True)
