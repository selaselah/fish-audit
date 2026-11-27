"""Submit watermarked pairs of approval slips and reconcile their physical rows."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, embedded_font, pdf
from payment_releases import AUTHORITY, DECISION
from quality_reinspection import reconcile_training_pages
from run import get, submit
from warranty_release import FIELDS


HOLD = "维持第二期验收款暂缓，继续暂停支付"
TITLE = "付款放行单"
CASES = {"opposed": "同一验收款的放行与暂缓意见", "other": "另一验收单上的暂缓意见",
         "repeat": "两张放行单列示不同签字日"}


def materials(seed, key):
    code = hashlib.sha256((seed + "-" + key).encode()).hexdigest()[:8].upper()
    folder = ROOT / "多份付款放行单" / code
    folder.mkdir(exist_ok=True, parents=True)
    records = documents(code, "complete")
    receipt = "YS-" + code + "-001"
    contract = records["采购合同"]
    contract.append(("放行约定", AUTHORITY))
    records["验收报告"].extend([("验收单编号", receipt), ("付款意见", "第二期验收款暂缓支付")])
    records["银行付款回单"] = [(k, "2026年9月24日" if k == "付款日期" else v) for k, v in records["银行付款回单"]]
    for name, number, decision, day in (
            ("审批记录甲", receipt, DECISION, 23),
            ("审批记录乙", receipt[:-1]+"2" if key == "other" else receipt, DECISION if key == "repeat" else HOLD, 25)):
        records[name] = [*contract[:4], ("原验收单编号", number), ("放行决定", decision),
                         ("放行签字日期", f"2026年9月{day}日"), ("审批签认", "演练林岚（已签字）")]
    font = embedded_font("CompetingReleasesCJK")
    for name, rows in records.items():
        pdf(folder / (name+".pdf"), TITLE if name.startswith("审批记录") else name, rows, font=font, spacing=31)
    return folder, records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="release-pair-v1")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--review", action="store_true", help="按演练原件核对提取字段及签认栏文字")
    args = parser.parse_args()
    if args.review and not args.run:
        parser.error("--review 需要 --run 提交本机水印案件")
    queue = []
    for key, title in CASES.items():
        folder, records = materials(args.run_id, key)
        if args.run:
            case = submit("合成演练 · "+title, [folder/(name+".pdf") for name in records], args.run_id+"-"+key, PROFILE)
            queue.append((case, key, folder, records))
            print(key, case, flush=True)
        else:
            print(folder)
    if args.review:
        for case, key, folder, records in queue:
            reconcile_training_pages(case, folder, records, case_titles=CASES.values(),
                field_labels={**FIELDS, "验收单编号":"acceptance_number", "原验收单编号":"original_acceptance",
                              "审批签认":"approval_signer", "放行签字日期":"release_signed_on"},
                document_types={TITLE:"payment_release"}, printed_titles={"审批记录甲":TITLE, "审批记录乙":TITLE},
                row_spacing=31, exact_fields=("approval_signer","buyer_signature","seller_signature","acceptance_signer"))
            report = confirm_printed_records(case, folder, records)
            print(key, get("/api/cases/"+case)["rev"], report["policy"]["version"],
                  [(f["id"], f["status"], f.get("payment_opinion",{}).get("release",{}).get("state"))
                   for f in report["findings"] if f["rule"] in ("H04","H05")], flush=True)
