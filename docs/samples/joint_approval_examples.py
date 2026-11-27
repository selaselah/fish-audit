"""Generate a watermarked installment approval naming one of two stipulated co-signers."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from approval_change_examples import write_agreement
from approval_times import append_printed_rows
from incomplete_payment_schedule import printed_rows
from named_approval_examples import MASTER
from publish_batch_version import digest, require
from release_originals_demo import check_fields
from run import submit


JOINT = "第二期验收款须由顾明远与周茵共同签批。"
CASES = {"contract": ("第二期合同会签名单只对上一人", None),
         "amended": ("第二期补充协议会签名单只对上一人", 20),
         "same_day": ("第二期会签名单在签批当日变更", 21)}


def additions(key):
    term = JOINT if key == "contract" else "第二期验收款须由林知行签批。"
    return {"采购合同.pdf": ("付款签批约定", term), "付款审批单.pdf": ("签批人姓名", "顾明远、林知行")}


def materials(archive, folder, key):
    folder.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=folder) as tmp:
        files, profile = append_printed_rows(archive, Path(tmp), additions(key), MASTER, "ApprovalNamesCJK")
        day = CASES[key][1]
        if day:
            contract = dict(printed_rows(Path(tmp) / "采购合同.pdf"))
            files.append(write_agreement(Path(tmp), contract, JOINT, day))
        paths = [folder / p.name for p in files]
        for dest, source in zip(paths, files):
            try:
                dest.hardlink_to(source)
            except FileExistsError:
                require(dest.read_bytes() == source.read_bytes(), dest.name + " 已有另一份原件")
    return paths, profile


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="先签批后扣款的水印 R7 证据包")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--check-fields", action="store_true")
    args = parser.parse_args()
    if args.check_fields and not args.run:
        parser.error("--check-fields 需要 --run")
    cases = {}
    for key, (title, _) in CASES.items():
        paths, profile = materials(args.archive, args.folder / key, key)
        if args.run:
            token = digest("".join(digest(p.read_bytes()) for p in paths).encode())
            cases[key] = submit("合成演练 · " + title, paths, "joint-approval-" + token, profile)
        print(key, cases.get(key) or args.folder / key, flush=True)
    if args.check_fields:
        fields = ("seller", "repaired_on", "defect_number", "repair_number", "acceptance_scope", "defect_closure")
        for key, cid in cases.items():
            extra = [(name, None, label, value, None) for name, (label, value) in additions(key).items()]
            check_fields(args.archive, key, cid, args.folder / key, case_title=CASES[key][0], master_hash=MASTER,
                         reviewer="会签水印演练核字", kind="bank_receipt", additions=extra, visual_fields=fields, missing_fields=fields)
