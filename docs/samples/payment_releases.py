"""Watermarked purchase files with a hold, a named release mandate and a bank transfer."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, embedded_font, pdf
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit
from warranty_release import FIELDS


CASES={"prior":"验收款放行后次日实付","late":"验收款实付后次日放行","same":"验收款放行与实付同日",
       "signer":"验收款放行单与合同指定人不同","reference":"放行单指向另一张验收单","approval_only":"放行单仅列审批日期"}
AUTHORITY="第二期暂缓自验收日起执行，须经甲方演练林岚签字放行"
DECISION="解除第二期验收款暂缓，自签字日起恢复支付"


def materials(seed,mode):
    code=hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    records=documents(code,"complete")
    receipt_no="YS-"+code+"-001"
    contract=records["采购合同"]
    contract.append(("放行约定",AUTHORITY))
    records["验收报告"].extend([("验收单编号",receipt_no),("付款意见","第二期验收款暂缓支付")])
    records["银行付款回单"]=[(k,"2026年9月24日" if k=="付款日期" else v) for k,v in records["银行付款回单"]]
    day={"late":"25","same":"24"}.get(mode,"23")
    signer="演练何平" if mode=="signer" else "演练林岚"
    records["付款放行单"]=[*contract[:4],("原验收单编号",receipt_no[:-1]+"2" if mode=="reference" else receipt_no),
                       ("放行决定",DECISION),("审批日期" if mode=="approval_only" else "放行签字日期","2026年9月"+day+"日"),
                       ("审批签认",signer+"（已签字）")]
    folder=ROOT/"验收款放行"/code
    folder.mkdir(parents=True,exist_ok=True)
    font=embedded_font("PaymentReleaseCJK")
    for title,rows in records.items():
        pdf(folder/(title+".pdf"),title,rows,font=font,spacing=31)
    return folder,records


def review(cid,folder,records,*,old=False):
    fields={**FIELDS,"验收单编号":"acceptance_number","原验收单编号":"original_acceptance","放行签字日期":"release_signed_on","审批日期":"approved_on","审批签认":"approval_signer"}
    if old:
        fields.pop("放行签字日期")
    reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=fields,
                             document_types={"付款放行单":"other" if old else "payment_release"},row_spacing=31)
    return confirm_printed_records(cid,folder,records)


def check(report,mode):
    findings=report["findings"]
    assert [f["status"] for f in findings if f["rule"] in ("H01","H02","H03")]==["ok"]*3
    stages=[f for f in findings if f["rule"]=="H04"]
    paid,=[f for f in findings if f["rule"]=="H05"]
    phase_status="missing" if mode in ("reference","signer","approval_only") else "ok"
    assert [f["status"] for f in stages]==["ok",phase_status,"ok"]
    assert paid["status"]=={"prior":"ok","late":"risk"}.get(mode,"missing")
    check=stages[1]["payment_opinion"]["release"]
    assert check["state"]=={"reference":"reference_mismatch","signer":"signer_mismatch","approval_only":"pending"}.get(mode,"matched"),check


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="payment-release-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    queue=[]
    for mode in args.cases:
        folder,records=materials(args.run_id,mode)
        if args.run:
            cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
            queue.append((cid,mode,folder,records)); print(mode,BASE+"/workpaper/"+cid,flush=True)
        else:
            print(folder)
    for cid,mode,folder,records in queue:
        report=review(cid,folder,records)
        check(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
