"""Audit watermarked purchases whose signed receipt and inspection remarks need to be read together."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, embedded_font, pdf
from quality_addenda import pdf_with_note
from quality_reinspection import reconcile_training_pages, reinspection_records
from run import BASE, get, submit
from warranty_release import FIELDS, check_training_watermark


CASES = {"clear":"终验签认且无保留意见", "reserved":"合格栏与到货暂收附注冲突",
         "image":"签收栏旁的影像要求另行终验", "limit":"实测超限且验收有保留",
         "approval":"终验合格但合同约定的批准文件缺失", "retest":"整改复验另列未检项目"}
NOTE = "仅作到货签收，整机性能尚未检验，最终验收另行办理"
IMAGE_NOTE = "附注：仅核对数量，最终验收另行办理"


def generate(seed, mode):
    code = hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    records = reinspection_records(code,"closed") if mode=="retest" else documents(code,"approved" if mode=="approval" else "complete")
    if mode=="approval":
        del records["合同审批单"]
    if mode in ("clear","reserved","limit"):
        records["验收报告"].append(("验收备注","无保留意见" if mode=="clear" else NOTE))
    if mode=="limit":
        records["验收报告"]=[(k,"柜温8℃" if k=="实测结果" else v) for k,v in records["验收报告"]]
    if mode=="retest":
        records["复验报告"].append(("复验备注","整机性能待测，最终验收另行办理"))
    folder=ROOT/"34-终验结论与签收附注"/code
    folder.mkdir(parents=True,exist_ok=True)
    font=embedded_font("AcceptanceRemarksCJK")
    for title,rows in records.items():
        target=folder/(title+".pdf")
        if mode=="image" and title=="验收报告":
            pdf_with_note(target,title,rows,font,IMAGE_NOTE,spacing=28)
        else:
            pdf(target,title,rows,font=font,spacing=28)
    return folder,records


def validate(report,mode):
    fs=report["findings"]
    signed,accepted,plan=[f for f in fs if f["rule"] in ("H01","H02","H03")]
    phases=[f["status"] for f in fs if f["rule"]=="H04"]
    bank,=[f for f in fs if f["rule"]=="H05"]
    assert signed["status"]==("missing" if mode=="approval" else "ok"),signed["detail"]
    assert plan["status"]=="ok"
    expected={"reserved":"risk","image":"missing","limit":"issue","retest":"issue"}.get(mode,"ok")
    assert accepted["status"]==expected,accepted["detail"]
    evidence=accepted["acceptance_reservations"]
    if mode=="image":
        assert evidence["mixed_pages"] and all(not p["text_only"] for p in evidence["mixed_pages"])
    elif mode in ("reserved","limit","retest"):
        assert any(s["line"] and s["kind"]=="limited" for s in evidence["lines"])
    else:
        assert not evidence["mixed_pages"] and not evidence["lines"]
    if mode=="retest":
        assert accepted["reinspection"]["state"]=="open"
    if mode=="approval":
        assert phases==["missing"]*3
    elif mode=="clear":
        assert phases==["ok"]*3
    else:
        assert phases[0]=="ok" and all(p!="ok" for p in phases[1:]),phases
    assert bank["status"]==("ok" if mode=="clear" else "missing"),bank["detail"]
    if expected=="issue":
        assert report["result"]["verdict"]=="reject"
    elif mode!="clear":
        assert report["result"]["verdict"]=="review"


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-acceptance-remarks-v1")
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
                                 field_labels={**FIELDS,"验收备注":"other","复验备注":"other"})
        report=confirm_printed_records(cid,folder,records)
        report=check_training_watermark(cid,folder,records,report)
        validate(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
