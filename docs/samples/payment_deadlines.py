"""Exercise phase-specific payment windows on watermarked contracts, receipts and transfers."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, embedded_font, pdf
from quality_addenda import pdf_with_note
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit
from warranty_release import FIELDS as WARRANTY_FIELDS, check_training_watermark


CASES={
    "within":"终验款在约定五个自然日内支付","late":"验收款晚于明列的最后付款日十四天",
    "early":"付款早于终验且合同明列期限","national":"国庆调休后第三个工作日届满",
    "boundary":"在调休上班的付款末日支付","custom":"合同写工作日但未明确采用哪套日历",
    "image":"验收页影像另约验收款付款时限","receipt":"验收原件另列到账时点要求",
    "prepay":"首期预付款在生效后五日内支付"}
FIELDS={**WARRANTY_FIELDS,"验收款付款期限":"payment_deadline","验收款最迟付款日":"payment_deadline",
        "预付款付款期限":"payment_deadline"}
NATIONAL="最终验收合格后3个工作日内支付60%（按国家调休日历）"
NATURAL="终验合格后5个自然日内支付，届满日不顺延"


def generate(seed,mode):
    code=hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    records=documents(code,"complete")
    contract=records["采购合同"]
    inline={"early":"最终验收合格后5个自然日内支付60%（届满日不顺延）","national":NATIONAL,
            "boundary":NATIONAL,"custom":"最终验收合格后3个工作日内支付60%"}
    if mode in inline:
        contract[:]=[(k,inline[mode] if k=="第二期" else v) for k,v in contract]
    elif mode=="late":
        contract.append(("验收款最迟付款日","2026年9月25日，届满日不顺延"))
    elif mode=="prepay":
        contract.append(("预付款付款期限","合同生效后5个自然日内支付，届满日不顺延"))
    else:
        contract.append(("验收款付款期限",NATURAL))
    receipt=records["验收报告"]
    if mode in ("national","boundary","custom"):
        receipt[:]=[(k,"2026年9月30日" if k=="验收日期" else v) for k,v in receipt]
    if mode=="receipt":
        receipt.append(("备注","验收款以收款方实际到账日为准"))
    paid={"early":"2026年9月18日","late":"2026年10月9日","national":"2026年10月12日",
          "boundary":"2026年10月10日","custom":"2026年10月12日","prepay":"2026年9月3日"}.get(mode,"2026年9月23日")
    bank={"付款日期":paid}
    if mode=="prepay":
        bank.update(款项用途="第一期",付款金额="30,000.00")
    records["银行付款回单"]=[(k,bank.get(k,v)) for k,v in records["银行付款回单"]]
    folder=ROOT/"33-分期付款期限及调休日历"/code
    folder.mkdir(parents=True,exist_ok=True)
    font=embedded_font("PaymentWindowCJK")
    for title,rows in records.items():
        path=folder/(title+".pdf")
        if mode=="image" and title=="验收报告":
            pdf_with_note(path,title,rows,font,"附注：验收款付款期限另行商定",spacing=28)
        else:
            pdf(path,title,rows,font=font,spacing=28)
    return folder,records


def validate(report,mode):
    checks=report["findings"]
    mixed_acceptance=mode=="image" and report["policy"].get("acceptance_reservations")
    assert [f["status"] for f in checks if f["rule"] in ("H01","H02","H03")]==["ok","missing" if mixed_acceptance else "ok","ok"],[(f["id"],f["detail"]) for f in checks if f["status"]!="ok"]
    phases=[f for f in checks if f["rule"]=="H04"]
    bank,=[f for f in checks if f["rule"]=="H05"]
    index=0 if mode=="prepay" else 1
    expected={"late":"late","early":"early","national":"late","boundary":"same_day",
              "custom":"unresolved","image":"unresolved","receipt":"unresolved"}.get(mode,"within")
    status={"late":"risk","early":"risk","within":"ok"}.get(expected,"missing")
    assert phases[0]["status"]=="ok" and phases[index]["status"]==("missing" if expected=="unresolved" else "ok"),[(f["status"],f["detail"]) for f in phases]
    if mode!="image":
        assert phases[2]["status"]=="ok"
    window=bank.get("payment_window") or {}
    assert (bank["status"],window.get("outcome"))==(status,expected),(bank["detail"],window)
    assert window["calendar_end"]=={"national":"2026-10-10","boundary":"2026-10-10","prepay":"2026-09-06"}.get(mode,None if expected=="unresolved" else "2026-09-25")
    if mode in ("national","boundary"):
        assert [day["date"] for day in window["days"] if day["counted"]]==["2026-10-08","2026-10-09","2026-10-10"]
    if expected=="late":
        assert window["days_late"]==(14 if mode=="late" else 2)
    links=[e for e in report["graph"]["edges"] if e["type"]=="payment_window_comparison"]
    assert len(links)==int(expected!="unresolved")
    if links:
        assert (links[0]["from"],links[0]["to"])==(window["term_ref"],window["paid_ref"])
    if status!="ok":
        assert report["result"]["verdict"]=="review"


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-payment-deadlines-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    queued=[]
    for mode in args.cases:
        folder,records=generate(args.run_id,mode)
        if not args.run:
            print(folder)
            continue
        cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
        queued.append((mode,cid,folder,records))
        print(mode,BASE+"/workpaper/"+cid,flush=True)
    for mode,cid,folder,records in queued:
        reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=FIELDS,row_spacing=28)
        report=confirm_printed_records(cid,folder,records)
        report=check_training_watermark(cid,folder,records,report)
        validate(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
