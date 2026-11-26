"""Compare a transfer request, an acceptance-only notice and a payee-arrival note on watermarked originals."""

import argparse
import hashlib

from reportlab.pdfgen import canvas

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, draw_pdf_page, embedded_font, pdf
from quality_reinspection import reconcile_training_pages
from receipt_before_payment import FIELDS
from run import BASE, get, submit


CASES = {"notice": "交易状态与回单页脚冲突", "request": "验收款仅有付款申请单", "arrival": "回单区分付款与收款到账",
         "mixed": "验收款受理回单与质保金付款申请"}
NOTES = {"notice": "本单仅为付款申请受理凭证，不代表实际扣款", "arrival": "本回单不代表收款方已到账"}


def materials(seed, mode):
    code = hashlib.sha256((seed + "-" + mode).encode()).hexdigest()[:8].upper()
    folder = ROOT / "受理回执与扣款" / code
    folder.mkdir(parents=True, exist_ok=True)
    font = embedded_font("PaymentExecutionSampleCJK")
    records = documents(code, "complete")
    if mode in ("request", "mixed"):
        bank = dict(records["银行付款回单"])
        records["付款申请单"] = [(k, bank[k]) for k in ("合同编号", "付款户名", "收款户名")]
        records["付款申请单"] += [("款项用途", "第三期" if mode == "mixed" else "第二期"),
                             ("申请金额", "10,000.00" if mode == "mixed" else "60,000.00"), ("申请状态", "审批通过"),
                             ("申请时间", "2026年11月21日 14:00" if mode == "mixed" else "2026年9月21日 14:00")]
    if mode == "request":
        del records["银行付款回单"]
    else:
        records["银行付款回单"].append(("回单提示", NOTES["notice" if mode == "mixed" else mode]))
    for title, rows in records.items():
        path = folder / (title + ".pdf")
        if title == "银行付款回单":
            sheet = canvas.Canvas(str(path), pagesize=(595, 842), invariant=1)
            sheet.setTitle(title)
            draw_pdf_page(sheet, title, rows[:-1], font=font)
            sheet.setFont(font, 13)
            sheet.drawString(48, 92, "回单提示：" + rows[-1][1])
            sheet.save()
        else:
            pdf(path, title, rows, font=font)
    return folder, records


def verify_case(report, mode):
    findings = report["findings"]
    payments = [f for f in findings if f["rule"] == "H05"]
    assert {"H01","H02","H03","H04"} <= {f["rule"] for f in findings}
    if mode == "mixed":
        assert sorted((f["status"],f["execution_basis"]["state"]) for f in payments) == [("missing","application"),("risk","conflict")]
        assert len({f["execution_basis"]["unit"] for f in payments}) == 2
        assert report["result"]["verdict"] == "review"
        return
    payment, = payments
    if mode == "arrival":
        assert "execution_basis" not in payment
        assert not report["graph"]["payment_execution_sources"]["units"]
    else:
        expected = {"notice": ("risk", "conflict"), "request": ("missing", "application")}
        assert (payment["status"], payment["execution_basis"]["state"]) == expected[mode], payment["detail"]
        assert report["result"]["verdict"] == "review"
        assert "signer_timing" not in payment


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-id", default="bank-execution-notices-v1")
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    args = parser.parse_args()
    queue = []
    for mode in args.cases:
        folder, records = materials(args.run_id, mode)
        if args.run:
            cid = submit("合成演练 · " + CASES[mode], sorted(folder.glob("*.pdf")), args.run_id+"-"+mode, PROFILE)
            print(mode, BASE + "/workpaper/" + cid, flush=True)
            queue.append((cid, mode, folder, records))
        else:
            print(folder)
    for cid, mode, folder, records in queue:
        reconcile_training_pages(cid, folder, records, case_titles=CASES.values(), field_labels=FIELDS,
                                 document_types={"付款申请单": "other"})
        report = confirm_printed_records(cid, folder, records)
        verify_case(report, mode)
        print(mode, "R" + str(get("/api/cases/" + cid)["rev"]), report["result"]["verdict"], flush=True)
