"""Compare four identical-price purchases against the dates on the contract and its performance records."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, embedded_font, pdf
from quality_addenda import FIELDS
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit


CASES = {
    "early":"终验早于约定董事会批准生效日",
    "reversed":"合同列明的生效日晚于截止日",
    "same_day":"终验与第二期付款同日仅有日期",
    "warranty":"合同期内终验且期后确认质保届满",
}
DATE_FIELDS = {**FIELDS, "合同有效期至":"valid_until", "审批日期":"approved_on", "审批机构":"approval_authority",
               "审批决定":"approval_result", "审批签认":"approval_signer"}


def generate(seed,mode):
    code=hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    folder=ROOT/"29-合同期间与实际履行日期"/code
    folder.mkdir(parents=True,exist_ok=True)
    board=mode in ("early","reversed")
    records=documents(code,"approved" if board else "complete")
    if board:
        for doc,field in (("采购合同","实际生效日期"),("合同审批单","审批日期")):
            records[doc]=[(k,"2026年9月15日" if k==field else v) for k,v in records[doc]]
    if mode=="early":
        records["验收报告"]=[(k,"2026年9月10日" if k=="验收日期" else v) for k,v in records["验收报告"]]
    if mode in ("reversed","warranty"):
        end="2026年9月12日" if mode=="reversed" else "2026年9月30日"
        records["采购合同"].append(("合同有效期至",end))
    if mode=="same_day":
        records["银行付款回单"]=[(k,"2026年9月20日" if k=="付款日期" else v) for k,v in records["银行付款回单"]]
    font=embedded_font("ContractDateCJK")
    for title,rows in records.items():
        pdf(folder/(title+".pdf"),title,rows,font=font)
    return folder,records


def validate(report,mode):
    fs=report["findings"]
    observed=tuple(next(f["status"] for f in fs if f["rule"]==k) for k in ("H01","H02","H05"))
    expected={"early":("ok","risk","missing"),"reversed":("risk","risk","missing"),
              "same_day":("ok","ok","missing"),"warranty":("ok","ok","ok")}
    assert observed==expected[mode],[(f["rule"],f["status"],f["detail"]) for f in fs]
    stages=[f for f in fs if f["rule"]=="H04"]
    assert [f["stage"]["share"] for f in stages]==["30","60","10"]
    assert [f["status"] for f in stages]=={"early":["ok","risk","risk"],"reversed":["missing"]*3}.get(mode,["ok"]*3)
    findings=[f for f in fs if f.get("date_checks")]
    assert {f["rule"] for f in findings}=={"early":{"H02"},"reversed":{"H01"},"same_day":{"H05"},"warranty":set()}[mode]
    assert all(set(c["evidence"])<=set(f["evidence"]) for f in findings for c in f["date_checks"])
    assert report["result"]["verdict"]==("pass" if mode=="warranty" else "review")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-contract-dates-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    queued=[]
    for mode in args.cases:
        folder,records=generate(args.run_id,mode)
        if not args.run:
            print(folder)
            continue
        cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
        print(mode,BASE+"/workpaper/"+cid,flush=True)
        queued.append((mode,cid,folder,records))
    for mode,cid,folder,records in queued:
        reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=DATE_FIELDS,
                                 document_types={"合同审批单":"contract_approval"})
        paper=confirm_printed_records(cid,folder,records)
        validate(paper,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),paper["result"]["verdict"],flush=True)
