"""Watermarked contracts that distinguish a signature plus a seal from alternatives and other forms."""

import argparse
from hashlib import sha256
from pathlib import Path

from contract_dates import DATE_FIELDS
from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import embedded_font, pdf
from quality_reinspection import reconcile_training_pages
from run import submit


CASES = {
    "representatives": ("合同另须双方法定代表人签字并盖章", "合同签署要求", "本合同须经双方法定代表人签字并加盖公章"),
    "board": ("董事会已列批准，合同仍另须代表签字", "签署方式", "本合同须加盖双方公章，并由双方法定代表人签字"),
    "either": ("合同签署栏约定签字或盖章", "合同签署要求", "本合同由双方签字或盖章"),
    "acceptance": ("另行签字盖章的对象为验收单", "验收单签署要求", "验收单须经双方代表签字并加盖公章"),
}
SHARED_CASES = {
    "shared_advance": ("合同与验收报告均须签字并盖章，已付首期", "签署要求", "本合同与验收报告均须由双方代表签字并盖章"),
    "shared_final": ("验收报告与合同均须用印和签字，已付第二期", "签署方式", "验收报告及本合同均须加盖双方公章，并由双方代表签字"),
    "under_contract": ("仅合同项下的验收报告另须签字盖章", "签署要求", "本合同项下的验收报告须由双方代表签字并盖章"),
    "shared_either": ("合同与验收报告均可签字或盖章", "签署方式", "本合同与验收报告均由双方签字或盖章"),
}
ALL_CASES = {**CASES, **SHARED_CASES}


def generate(folder, case):
    _, label, requirement = ALL_CASES[case]
    records = documents("SIGN-SCOPE" if case in SHARED_CASES else "SIGN-FORM", "approved" if case == "board" else "complete")
    records["采购合同"].append((label, requirement))
    first_payment = {"款项用途": "第一期", "付款金额": "30,000.00", "付款日期": "2026年9月2日"}
    if case != "shared_final":
        records["银行付款回单"] = [(key, first_payment.get(key, value)) for key, value in records["银行付款回单"]]
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for title, rows in records.items():
        path = folder / (title + ".pdf")
        pdf(path, title, rows, font=embedded_font("ContractSignForm"), spacing=28)
        paths.append(path)
    return records, sorted(paths)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--case", choices=ALL_CASES, action="append")
    parser.add_argument("--shared", action="store_true", help="生成对照主合同与验收报告签署范围的四组材料")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--check-fields", action="store_true")
    args = parser.parse_args()
    if args.check_fields and not args.run:
        parser.error("--check-fields 需要 --run 提交水印演练")
    queued = []
    for case in args.case or (SHARED_CASES if args.shared else CASES):
        folder = args.folder / case
        records, paths = generate(folder, case)
        if args.run:
            key = sha256("".join(sha256(p.read_bytes()).hexdigest() for p in paths).encode()).hexdigest()
            cid = submit("合成演练 · " + ALL_CASES[case][0], paths, "contract-signing-" + key, PROFILE)
            queued.append((cid, folder, records))
            print(case, cid, flush=True)
        else:
            print(case, folder)
    if args.check_fields:
        for cid, folder, records in queued:
            reconcile_training_pages(cid, folder, records, case_titles=[v[0] for v in ALL_CASES.values()],
                                     field_labels=DATE_FIELDS, document_types={"合同审批单":"contract_approval"}, row_spacing=28)
            confirm_printed_records(cid, folder, records)
