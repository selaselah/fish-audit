"""Synthetic procurement milestones with an explicit invoice-receipt condition."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import BUYER, ROOT, embedded_font, pdf
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit


CASES = {"invoice_only": "验收款仅附发票，尚无收票签认", "paid_early": "验收款先付款后收票",
         "before_payment": "验收款付款前已签收对应发票", "different": "收票登记与发票原件号码不同"}
FIELDS = {"第一期":"payment_stage","第二期":"payment_stage","第三期":"payment_stage","付款条款":"payment_term",
          "生效条款":"effect_clause","签约日期":"signed_on","实际生效日期":"effect_on",
          "约定交付数量":"quantity_agreed","约定验收标准":"acceptance_criteria",
          "付款户名":"payer","收款户名":"payee","交易状态":"transfer_status","付款日期":"paid_on",
          "发票号码":"invoice_id","开票日期":"issued_on","签收发票号码":"received_invoice_id",
          "收票日期":"invoice_received_on","收票方签章":"invoice_received_seal","验收款支付前提":"invoice_receipt_clause"}


def materials(seed, mode):
    digest = hashlib.sha256((seed + mode).encode()).hexdigest()
    code = digest[:8].upper()
    number = "99" + str(int(digest[8:24], 16)).zfill(20)[-18:]
    records = documents(code, "complete")
    if mode == "before_payment":
        records["采购合同"] = [(k, "最终验收合格且采购方收到本合同对应的发票后支付60%" if k == "第二期" else v)
                            for k, v in records["采购合同"]]
    else:
        records["采购合同"].append(("验收款支付前提", "买方收到供应方就本合同开具的发票"))
    records["采购发票"] = [*records["采购合同"][:4], ("发票号码", number), ("开票日期", "2026年9月18日")]
    if mode != "invoice_only":
        received = number[:-1] + str((int(number[-1]) + 1) % 10) if mode == "different" else number
        records["验收报告"].extend([("签收发票号码", received), ("收票日期", "2026年9月22日" if mode == "paid_early" else "2026年9月20日"),
                                  ("收票方签章", BUYER + "（已盖章）")])
    folder = ROOT / "收票与分期付款" / code
    folder.mkdir(parents=True, exist_ok=True)
    font = embedded_font("ReceiptBeforePaymentCJK")
    for title, rows in records.items():
        pdf(folder / (title + ".pdf"), title, rows, font=font)
    return folder, records


def verify_case(report, mode):
    phases = [f for f in report["findings"] if f["rule"] == "H04"]
    payment, = [f for f in report["findings"] if f["rule"] == "H05"]
    expected = {"invoice_only":("missing","missing"), "paid_early":("ok","risk"),
                "before_payment":("ok","ok"), "different":("missing","missing")}[mode]
    assert [f["status"] for f in phases] == ["ok", expected[0], "ok"], [(f["status"],f["detail"]) for f in phases]
    assert payment["status"] == expected[1], payment["detail"]
    assert phases[1]["invoice_receipt"]["invoice"]["status"] == "ok"
    assert phases[1]["invoice_receipt"]["receipt"]["status"] == expected[0]
    assert all("invoice_receipt" not in f for f in (phases[0], phases[2]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-id", default="receipt-before-payment-v1")
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    args = parser.parse_args()
    queue = []
    for mode in args.cases:
        folder, records = materials(args.run_id, mode)
        if args.run:
            cid = submit("合成演练 · " + CASES[mode], sorted(folder.glob("*.pdf")), args.run_id + "-" + mode, PROFILE)
            print(mode, BASE + "/workpaper/" + cid, flush=True)
            queue.append((cid, mode, folder, records))
        else:
            print(folder)
    for cid, mode, folder, records in queue:
        reconcile_training_pages(cid, folder, records, case_titles=CASES.values(), field_labels=FIELDS,
                                 document_types={"采购发票":"invoice"})
        report = confirm_printed_records(cid, folder, records)
        verify_case(report, mode)
        print(mode, "R" + str(get("/api/cases/" + cid)["rev"]), report["result"]["verdict"], flush=True)
