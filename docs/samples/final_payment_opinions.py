"""Watermarked final acceptance records containing separate payment instructions."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, embedded_font, pdf
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit
from warranty_release import FIELDS


CASES = {"all":"终验合格但载明全部付款暂缓", "phase":"终验合格但第二期暂缓",
         "conflict":"同一验收款有两项相反付款意见", "quality":"验收单同意付款但实测超限"}


def materials(seed, mode):
    code=hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    records=documents(code,"complete")
    receipt=records["验收报告"]
    if mode=="quality":
        receipt[:]=[(label,"柜温8℃" if label=="实测结果" else value) for label,value in receipt]
    opinion={"all":"本合同项下全部付款暂缓","phase":"第二期验收款暂缓支付",
             "conflict":"第二期验收款暂缓支付","quality":"第二期验收款同意支付"}[mode]
    receipt.append(("付款意见",opinion))
    if mode=="conflict":
        receipt.append(("付款备注","同意支付第二期验收款"))
    folder=ROOT/"终验付款意见"/code
    folder.mkdir(parents=True,exist_ok=True)
    font=embedded_font("FinalPaymentOpinionsCJK")
    for title,rows in records.items():
        pdf(folder/(title+".pdf"),title,rows,font=font)
    return folder,records


def review_fixture(cid,folder,records):
    reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=FIELDS)
    return confirm_printed_records(cid,folder,records)


def check(report,mode):
    fs=report["findings"]
    first=[f["status"] for f in fs if f["rule"] in ("H01","H02","H03")]
    assert first==["ok","issue" if mode=="quality" else "ok","ok"],first
    phases=[f for f in fs if f["rule"]=="H04"]
    bank,=[f for f in fs if f["rule"]=="H05"]
    statuses={"all":["missing"]*3,"phase":["ok","missing","ok"],"conflict":["ok","risk","ok"],"quality":["ok","risk","risk"]}
    assert [f["status"] for f in phases]==statuses[mode] and bank["status"]=="missing"
    state={"all":"hold","phase":"hold","conflict":"conflict","quality":"assent"}[mode]
    for f in [phases[1],bank]:
        decision=f["payment_opinion"]
        assert decision["state"]==state and all(row["line"] and row["scope"]!="unresolved" for row in decision["notes"])
    if mode!="all":
        assert all("payment_opinion" not in phases[i] for i in (0,2))
    if mode=="quality":
        assert report["result"]["verdict"]=="reject"


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="final-payment-opinions-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    queue=[]
    for mode in args.cases:
        folder,records=materials(args.run_id,mode)
        if args.run:
            cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
            queue.append((cid,mode,folder,records))
            print(mode,BASE+"/workpaper/"+cid,flush=True)
        else:
            print(folder)
    for cid,mode,folder,records in queue:
        report=review_fixture(cid,folder,records)
        check(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
