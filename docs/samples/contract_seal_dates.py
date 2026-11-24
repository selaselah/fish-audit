"""Compare the dates on each side of a watermarked contract with the first installment."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, embedded_font, pdf
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit
from warranty_release import FIELDS, check_training_watermark


CASES={"complete":"分日盖章后支付预付款","early":"预付款早于乙方实际盖章","partial":"合同只见甲方盖章日"}

def generate(seed,mode):
    code=hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    records=documents(code,"complete")
    contract=records["采购合同"]
    if mode=="complete":
        contract[:]=[(k,"2026年9月12日" if k=="实际生效日期" else v) for k,v in contract]
    contract.append(("甲方盖章日期","2026年9月1日"))
    if mode!="partial":
        contract.append(("乙方盖章日期","2026年9月12日"))
    payment={"付款日期":"2026年9月14日" if mode=="complete" else "2026年9月5日","款项用途":"第一期","付款金额":"30,000.00"}
    records["银行付款回单"]=[(k,payment.get(k,v)) for k,v in records["银行付款回单"]]
    folder=ROOT/"35-双方盖章与预付款"/code
    folder.mkdir(parents=True,exist_ok=True)
    font=embedded_font("SealDatesCJK")
    for name,rows in records.items():
        pdf(folder/(name+".pdf"),name,rows,font=font,spacing=28)
    return folder,records


def validate(report,mode):
    items=[f for f in report["findings"] if f["rule"].startswith("H")]
    expected={"complete":["ok"]*7,"early":["risk","ok","ok","missing","missing","missing","risk"],
              "partial":["missing","ok","ok","missing","missing","missing","missing"]}[mode]
    assert [f["status"] for f in items]==expected,[(f["rule"],f["detail"]) for f in items]
    assert items[0]["effect_review"]["seals"]["completed_on"]==(None if mode=="partial" else "2026-09-12")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-contract-seals-v1")
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
        reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),row_spacing=28,
                                 field_labels={**FIELDS,"甲方盖章日期":"buyer_sealed_on","乙方盖章日期":"seller_sealed_on"})
        report=confirm_printed_records(cid,folder,records)
        report=check_training_watermark(cid,folder,records,report)
        validate(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
