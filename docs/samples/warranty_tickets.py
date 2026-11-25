"""Exercise source-linked warranty work orders with marked, fictional procurement PDFs."""

import argparse
import hashlib
from datetime import datetime, timedelta, timezone

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, embedded_font, pdf
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit
from warranty_release import CONDITION, FIELDS as WARRANTY_FIELDS, check_training_watermark


CASES={"open":"期满确认无遗留但另有待维修工单","closed":"期满前有采购方具名关闭工单",
       "late":"质保金付款后才由采购方关闭工单","same_day":"工单关闭与期满确认同日",
       "other":"维修工单所列标的与本合同不同","two":"两张质保工单中仍有一张待维修"}
FIELDS={**WARRANTY_FIELDS,"质保工单编号":"warranty_ticket_id","报修日期":"warranty_reported_on",
        "报修事项":"warranty_fault","工单状态":"warranty_ticket_state","关闭日期":"warranty_closed_on",
        "采购方关闭签认":"warranty_closed_by"}


def generate(seed,mode,as_of):
    key=f"{seed}-{mode}-{as_of}"
    code=hashlib.sha256(key.encode()).hexdigest()[:8].upper()
    folder=ROOT/"质保维修工单"/code
    folder.mkdir(parents=True,exist_ok=True)
    def day(offset):
        d=as_of+timedelta(days=offset)
        return f"{d.year}年{d.month}月{d.day}日"
    records=documents(code,"complete")
    records["采购合同"].extend([("质保期限","自终验合格之日起60个自然日，届满日不顺延"),("质保金返还条件",CONDITION)])
    records["质保期满确认单"].append(("质保遗留事项","无未关闭缺陷"))
    changes={"签约日期":day(-70),"实际生效日期":day(-70),"验收日期":day(-64),"付款日期":day(-1),
             "质保期满确认":day(-3)+"双方确认质保期已满","付款金额":"10,000.00","款项用途":"第三期"}
    for fields in records.values():
        fields[:]=[(k,changes.get(k,v)) for k,v in fields]
    def ticket(number,opened):
        rows=[*records["采购合同"][:4],("质保工单编号","WX-"+code+"-"+str(number)),
              ("报修日期",day(-20)),("报修事项","温控探头故障" if number==1 else "柜体风扇故障"),
              ("工单状态","待维修" if opened else "已关闭")]
        if mode=="other":
            rows=[(k,"保温展示柜" if k=="采购标的" else v) for k,v in rows]
        if not opened:
            rows.extend([("关闭日期",day({"late":0,"same_day":-3}.get(mode,-5))),("采购方关闭签认","演练许澄（已签字）")])
        return rows
    records["质保维修工单"]=ticket(1,mode=="open")
    headings={"质保维修工单":"质保维修工单"}
    if mode=="two":
        records["质保报修工单"]=ticket(2,True)
        headings["质保报修工单"]="质保报修工单"
    font=embedded_font("WarrantyTicketsCJK")
    for title,rows in records.items():
        pdf(folder/(title+".pdf"),title,rows,font=font,spacing=28)
    return folder,records,headings


def validate(report,mode):
    checks=report["findings"]
    states=[f["status"] for f in checks if f["rule"] in ("H01","H02","H03","H04","H05")]
    expected={"open":"risk","closed":"ok","late":"risk","same_day":"missing","other":"missing","two":"risk"}[mode]
    assert states==["ok"]*5+[expected,expected],[(f["id"],f["status"],f["detail"]) for f in checks]
    phase=next(f for f in checks if f.get("warranty_check"))
    orders=phase["warranty_check"]["tickets"]
    expected_states={"open":["open"],"closed":["closed"],"late":["late"],"same_day":["same_day"],
                     "other":["identity"],"two":["closed","open"]}[mode]
    assert sorted(o["state"] for o in orders)==sorted(expected_states),orders
    assert all(set(o["evidence"])<=set(phase["evidence"]) for o in orders)
    assert len([e for e in report["graph"]["edges"] if e["type"]=="warranty_release_basis"])==int(mode=="closed")
    if mode!="closed":
        assert report["result"]["verdict"]=="review"


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-warranty-tickets-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    as_of=datetime.now(timezone(timedelta(hours=8))).date()
    pending=[]
    for mode in args.cases:
        folder,records,heads=generate(args.run_id,mode,as_of)
        if not args.run:
            print(folder)
            continue
        cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),f"{args.run_id}-{mode}-{as_of}",PROFILE)
        pending.append((mode,cid,folder,records,heads))
        print(mode,BASE+"/workpaper/"+cid,flush=True)
    for mode,cid,folder,records,heads in pending:
        reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=FIELDS,
                                 document_types={t:"warranty_ticket" for t in heads},row_spacing=28)
        report=confirm_printed_records(cid,folder,records)
        report=check_training_watermark(cid,folder,records,report)
        validate(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
