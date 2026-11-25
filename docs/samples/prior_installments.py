"""Watermarked cases where the acceptance installment also requires bank evidence of a fully paid first installment."""

import argparse
import hashlib
import sys
from pathlib import Path

from contract_milestones import PROFILE, confirm_printed_records, documents, normalize
from generate import ROOT, WATERMARK, embedded_font, pdf
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit, wait
from stage_transfers import LABELS
from warranty_release import check_training_watermark

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from documents import prepare


CASES = {
    "absent": "终验合格但验收款所需的首款回单缺件",
    "ready": "首款足额成功支付后才付验收款",
    "later": "两笔首款合计足额但第二笔晚于验收款",
    "same": "首款足额与验收款实付只记同一日",
    "partial": "首款回单只覆盖约定预付款的一部分",
    "allocation": "疑似首款的回单未写明所付期次",
    "credit": "合同要求首款实际到账而只有付款回单",
    "quality": "首款回单齐备但终验实测柜温超限",
}
LABEL = "验收款放款条件"
TERM = "首款须已付足，以付款银行成功回单为据"


def generate(seed, mode):
    code = hashlib.sha256((seed + "-" + mode).encode()).hexdigest()[:8].upper()
    records = documents(code, "complete")
    bank = records.pop("银行付款回单")
    term = "须由供应方确认首款已足额到账" if mode == "credit" else TERM
    records["采购合同"].extend([("币种", "人民币"), ("金额单位", "元"), (LABEL, term)])
    if mode == "quality":
        records["验收报告"] = [(k, "柜温8℃" if k=="实测结果" else v) for k,v in records["验收报告"]]
    receipts = [("验收款回单", "第二期", "60,000.00", "2026年9月21日")]
    if mode != "absent":
        receipts.append(("首款回单", "采购货款" if mode=="allocation" else "第一期",
                         "10,000.00" if mode in ("later","partial") else "30,000.00",
                         "2026年9月21日" if mode=="same" else "2026年9月10日"))
    if mode == "later":
        receipts.append(("首款续付回单", "第一期", "20,000.00", "2026年9月24日"))
    for i,(name,stage,amount,paid) in enumerate(receipts,1):
        values = {"款项用途":stage, "付款金额":amount, "付款日期":paid}
        records[name] = [(k,values.get(k,v)) for k,v in bank] + [
            ("交易流水号", "YL-"+code+"-"+str(i)), ("币种","人民币"), ("金额单位","元")]
    folder = ROOT / "首款凭证与验收款" / code
    folder.mkdir(parents=True, exist_ok=True)
    font = embedded_font("PriorInstallmentCJK")
    for name,rows in records.items():
        pdf(folder/(name+".pdf"), "银行付款回单" if name.endswith("回单") else name, rows,font=font,spacing=25)
    return folder,records


def review(cid, mode, folder, records):
    api="/api/cases/"+cid
    case=get(api)
    assert case["title"]=="合成演练 · "+CASES[mode] and not case["decisions"]
    report=wait(cid)
    nodes={n["id"]:n for n in report["graph"]["nodes"] if n["type"]=="page"}
    for doc in case["documents"]:
        path=folder/doc["name"]
        assert doc["sha256"]==hashlib.sha256(path.read_bytes()).hexdigest()
        page,=prepare(path,1,save_images=False)
        assert nodes[doc["id"]+"/p1"]["sha256"]==page["sha256"] and normalize(WATERMARK) in normalize(page["text"])
    titles={title:"银行付款回单" for title in records if title.endswith("回单")}
    field="prior_installment_clause" if report["policy"].get("prior_installment") else "other"
    reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),printed_titles=titles,
                             field_labels={**LABELS,LABEL:field},row_spacing=25,
                             exact_fields=("total","currency","unit","contract_id","buyer","seller","payer","payee","transfer_status",
                                           "paid_on","transfer_amount","transfer_ref","payment_stage","payment_designation",field))
    return check_training_watermark(cid,folder,records,confirm_printed_records(cid,folder,records))


def validate(report, mode):
    calls = report["calls"]
    assert all(c["request_id"] and c["response_id"] for c in [*calls["pages"], calls["expert"]])
    if not report["policy"].get("prior_installment"):
        return
    expected = {
        "ready": ("met", "met"), "absent": ("absent", "absent"), "later": ("met", "early"),
        "same": ("met", "same_day"), "partial": ("partial", "partial"),
        "allocation": ("allocation", "allocation"), "credit": ("credit", "credit"), "quality": ("met", "met"),
    }
    findings = report["findings"]
    prior = [f for f in findings if f.get("prior_installment")]
    assert {f["stage"]["name"] for f in prior} == {"第二期"}
    phase, payment = (next(f for f in prior if f["rule"] == rule) for rule in ("H04", "H05"))
    assert (phase["prior_installment"]["state"], payment["prior_installment"]["state"]) == expected[mode], (mode, prior)
    acceptance = next(f for f in findings if f["rule"] == "H02")
    assert acceptance["status"] == ("issue" if mode == "quality" else "ok"), (mode, acceptance["status"])
    if mode == "quality":
        assert phase["status"] != "ok" and payment["status"] != "ok"
    if mode == "later":
        proof = payment["prior_installment"]
        assert (payment["status"], proof["before"], proof["covered_on"]) == ("risk", "10000.00", "2026-09-24")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-prior-installment-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    pending=[]
    for mode in args.cases:
        folder,records=generate(args.run_id,mode)
        if args.run:
            cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
            pending.append((cid,mode,folder,records))
            print(mode,cid,flush=True)
        else:
            print(folder)
    for cid,mode,folder,records in pending:
        r=review(cid,mode,folder,records)
        validate(r,mode)
        print(mode,BASE+"/workpaper/"+cid+"?rev="+str(get("/api/cases/"+cid)["rev"]),
              [(f["rule"],f.get("stage",{}).get("name"),f["status"],f.get("prior_installment",{}).get("state"))
               for f in r["findings"] if f["rule"].startswith("H")],flush=True)
