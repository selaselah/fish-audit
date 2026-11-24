"""Exercise independent acceptance signatures, including a missing signature on reinspection."""

import argparse
import hashlib
from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, embedded_font, pdf
from quality_addenda import FIELDS, pdf_with_note
from quality_reinspection import reconcile_training_pages, reinspection_records
from run import BASE, get, submit


CASES = {"joint":"合同约定两人共同终验且均签字","missing":"共同验收缺少第二人签字",
         "different":"验收签字人与合同指定人员不同","retest":"整改复验缺少约定共同签字",
         "image":"两人验收签字另有影像代签说明"}
NOTE = "签认附注：林岚一栏为代签，须核对授权"


def generate(seed,mode):
    code=hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    folder=ROOT/"28-验收签认权限"/code
    folder.mkdir(parents=True,exist_ok=True)
    records=reinspection_records(code,"closed") if mode=="retest" else documents(code,"complete")
    clause="终验及整改复验均须由周宁、林岚共同签字确认" if mode=="retest" else "终验须由周宁、林岚共同签字确认"
    records["采购合同"].append(("验收签认约定",clause))
    for title,label in (("验收报告","验收签认"),("复验报告","复验签认")):
        if title not in records:
            continue
        names=["周宁","林岚"]
        if mode=="missing" or title=="复验报告":
            names=["周宁"]
        elif mode=="different":
            names=["周宁","何平"]
        records[title]=[(k,v) for k,v in records[title] if k!=label]+[(label,n+"（已签字）") for n in names]
    font=embedded_font("AcceptanceSignersCJK")
    for title,rows in records.items():
        path=folder/(title+".pdf")
        if title=="验收报告" and mode=="image":
            pdf_with_note(path,title,rows,font,NOTE)
        else:
            pdf(path,title,rows,font=font)
    return folder,records


def check(paper,mode):
    findings=paper["findings"]
    h=next(f for f in findings if f["rule"]=="H02")
    a=h["acceptance_authority"]
    expected={"joint":("ok","ok","ok","pass"),"missing":("missing","missing","missing","review"),
              "different":("risk","risk","risk","review"),"retest":("missing","issue","risk","reject"),
              "image":("missing","missing","missing","review")}
    status,quality,stage,verdict=expected[mode]
    assert (a["status"],h["status"],paper["result"]["verdict"])==(status,quality,verdict),[(f["rule"],f["status"],f["detail"]) for f in findings]
    assert all(f["status"]=="ok" for f in findings if f["rule"] in ("H01","H03"))
    assert [f["status"] for f in findings if f["rule"]=="H04"]==["ok",stage,stage]
    assert next(f for f in findings if f["rule"]=="H05")["status"]==("ok" if mode=="joint" else "missing")
    assert a["required"]==["周宁","林岚"] and a["mode"]=="joint"
    links=[e for e in paper["graph"]["edges"] if e["type"]=="named_acceptance_signature"]
    assert len(links)==(2 if mode in ("joint","retest") else 0)
    if mode in ("missing","retest"):
        assert a["records"][-1]["missing_names"]==["林岚"]
    if mode=="different":
        assert a["records"][0]["other_names"]==["何平"]
    if mode=="retest":
        assert h["reinspection"]["state"]=="open"
        assert [r["status"] for r in a["records"]]==["ok","missing"]
    if mode=="image":
        pages=paper["graph"]["acceptance_authority_sources"]["pages"]
        assert any(p["native"] and not p["text_only"] for p in pages)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-acceptance-signers-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    queue=[]
    for mode in args.cases:
        folder,records=generate(args.run_id,mode)
        if not args.run:
            print(folder)
            continue
        cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
        print(mode,BASE+"/workpaper/"+cid,flush=True)
        queue.append((cid,mode,folder,records))
    for cid,mode,folder,records in queue:
        reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels={**FIELDS,"验收签认约定":"acceptance_signing_clause"})
        paper=confirm_printed_records(cid,folder,records)
        check(paper,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),paper["result"]["verdict"],flush=True)
