"""Exercise supplier identification, acceptance and payment terms on synthetic originals."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, embedded_font, pdf
from quality_addenda import pdf_with_note
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit
from warranty_release import FIELDS, check_training_watermark


CASES = {
    "match": "供应方与终验记录逐字相符",
    "absent": "终验单缺少供货主体",
    "different": "终验供应方与签约方不同",
    "delegate": "终验另列受托供货单位",
    "image": "实际供货说明位于签认页影像",
    "once": "终验合格后一次付清",
    "unspecified": "全额回单缺少合同付款约定",
}
THIRD = "山岚演练交付中心"
FIELD_LABELS = {**FIELDS, "实际供货单位": "other", "验收款": "payment_stage"}


def generate(seed, mode):
    code = hashlib.sha256((seed + "-" + mode).encode()).hexdigest()[:8].upper()
    records = documents(code, "complete")
    receipt = records["验收报告"]
    if mode == "absent":
        records["验收报告"] = [(label, value) for label, value in receipt if label != "供应方"]
    elif mode == "different":
        records["验收报告"] = [(label, THIRD if label == "供应方" else value) for label, value in receipt]
    elif mode == "delegate":
        receipt.append(("实际供货单位", THIRD))
    if mode in ("once", "unspecified"):
        terms = {"付款条款", "第一期", "第二期", "第三期"}
        contract = [(label, value) for label, value in records["采购合同"] if label not in terms]
        if mode == "once":
            contract.append(("验收款", "最终验收合格后一次性支付全款"))
        records["采购合同"] = contract
        payment = {"款项用途": "验收款", "付款金额": "100,000.00"}
        records["银行付款回单"] = [(label, payment.get(label, value)) for label, value in records["银行付款回单"]]
        del records["质保期满确认单"]

    folder = ROOT / "36-终验供应方与委托交付" / code
    folder.mkdir(parents=True, exist_ok=True)
    font = embedded_font("AcceptanceSupplierCJK")
    for title, rows in records.items():
        path = folder / (title + ".pdf")
        if mode == "image" and title == "验收报告":
            pdf_with_note(path, title, rows, font, "实际供货单位：" + THIRD, spacing=28)
        else:
            pdf(path, title, rows, font=font, spacing=28)
    return folder, records


def validate(report, mode):
    findings = report["findings"]
    by_rule = {finding["rule"]: finding for finding in findings}
    inspection = by_rule["H02"]
    supplier = inspection["acceptance_reservations"]["supplier"]
    expected = {"different": "risk", "absent": "missing", "delegate": "missing", "image": "missing"}
    assert supplier["status"] == expected.get(mode, "ok"), (mode, supplier)
    assert by_rule["H01"]["status"] == "ok"
    stages = [f for f in findings if f["rule"] == "H04"]
    shares = [f["stage"]["share"] for f in stages if f.get("stage")]
    if mode == "unspecified":
        assert shares == [] and by_rule["H03"]["status"] == "missing"
        assert inspection["status"] == "ok" and by_rule["H05"]["status"] == "missing"
        assert stages and all(f["status"] == "missing" for f in stages)
        return
    assert shares == (["100"] if mode == "once" else ["30", "60", "10"])
    assert by_rule["H03"]["status"] == stages[0]["status"] == "ok"
    if mode in ("match", "once"):
        assert all(f["status"] == "ok" for f in findings if f["rule"].startswith("H"))
    else:
        assert all(f["status"] != "ok" for f in (inspection, *stages[1:], by_rule["H05"]))
    if mode == "image":
        assert any(not page["text_only"] for page in supplier["pages"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-id", default="synthetic-acceptance-suppliers-v1")
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    args = parser.parse_args()
    queued = []
    for mode in args.cases:
        folder, records = generate(args.run_id, mode)
        if not args.run:
            print(folder)
            continue
        cid = submit("合成演练 · " + CASES[mode], sorted(folder.glob("*.pdf")), args.run_id + "-" + mode, PROFILE)
        queued.append((mode, cid, folder, records))
        print(mode, BASE + "/workpaper/" + cid, flush=True)
    for mode, cid, folder, records in queued:
        reconcile_training_pages(cid, folder, records, case_titles=CASES.values(),
                                 row_spacing=28, field_labels=FIELD_LABELS)
        report = confirm_printed_records(cid, folder, records)
        report = check_training_watermark(cid, folder, records, report)
        validate(report, mode)
        print(mode, "R" + str(get("/api/cases/" + cid)["rev"]), report["result"]["verdict"], flush=True)
