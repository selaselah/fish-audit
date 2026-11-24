"""Run watermarked purchases with distinct batch and final acceptance signatories."""

import argparse
import hashlib

from batch_final import FINAL, LABELS, TITLES, final_documents
from contract_milestones import PROFILE, confirm_printed_records, normalize
from generate import ROOT, WATERMARK, embedded_font, pdf
from quality_addenda import pdf_with_note
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit
from warranty_release import check_training_watermark


CASES={
    "joint":"分批验收人与终验共同签字人均相符", "borrowed":"陈琪只在第二批签字而未签终验",
    "substitute":"分批验收人在终验单替代合同指定人", "only_final":"合同只为另行终验指定一名验收人",
    "no_final":"只有指定终验人的条款和两份分批原件", "quality":"指定终验人均已签认而总单实测超限",
    "image":"终验签字页另有代签影像说明", "rider":"合同另约意见不一致时暂停各期付款",
}
SPACING=23


def set_signatures(rows,names):
    rows[:]=[(k,v) for k,v in rows if k!="验收签认"]+[("验收签认",name+"（已签字）") for name in names]


def generate(seed,mode):
    code=hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    folder=ROOT/"38-分批与另行终验的指定签认人"/code
    folder.mkdir(parents=True,exist_ok=True)
    records=final_documents(code,"quality" if mode=="quality" else "complete")
    clauses=records["采购合同"]
    if mode!="only_final":
        second=["林岚","陈琪" if mode=="borrowed" else "何平"]
        clauses.extend([("验收签认约定","第一批验收须由周宁签字确认"),
                        ("验收签认约定","第二批验收须由"+"、".join(second)+"共同签字确认")])
        set_signatures(records["第一批验收报告"],["周宁"])
        set_signatures(records["第二批验收报告"],second)
    clauses.append(("终验签认约定","终验须由郑敏签字确认" if mode=="only_final" else "终验须由郑敏、陈琪共同签字确认"))
    names=["郑敏"] if mode in ("only_final","borrowed") else ["郑敏","林岚" if mode=="substitute" else "陈琪"]
    set_signatures(records[FINAL],names)
    if mode=="rider":
        clauses.append(("其他约定","分批与终验意见不一致时暂停各期付款，另须监理会签"))
    if mode=="no_final":
        del records[FINAL]
        paid={"款项用途":"第二期","付款日期":"2026年9月15日","付款金额":"35,000.00"}
        records["银行付款回单"]=[(k,paid.get(k,v)) for k,v in records["银行付款回单"]]
    font=embedded_font("FinalSignatoriesCJK")
    for name,rows in records.items():
        path=folder/(name+".pdf")
        title=TITLES.get(name,name)
        if name==FINAL and mode=="image":
            pdf_with_note(path,title,rows,font,"签认附注：陈琪一栏为代签，授权未附",spacing=SPACING,note_y=115)
        else:
            pdf(path,title,rows,font=font,spacing=SPACING)
    return folder,records


def settle(cid,folder,records):
    labels={**LABELS,"终验签认约定":"acceptance_signing_clause"}
    reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=labels,printed_titles=TITLES,
                row_spacing=SPACING,exact_fields=("delivery_batch","delivered_serials","batch_receipt_refs","acceptance_signing_clause","acceptance_signer"))
    report=confirm_printed_records(cid,folder,records)
    return check_training_watermark(cid,folder,records,report)


def validate(report,mode):
    calls=report["calls"]
    assert len(calls["pages"])==(5 if mode=="no_final" else 6)
    assert all(call["request_id"] and call["response_id"] for call in [*calls["pages"],calls["expert"]])
    findings=report["findings"]
    phases=[f for f in findings if f["rule"]=="H04"]
    acceptance=next(f for f in findings if f["rule"]=="H02")
    transfer=next(f for f in findings if f["rule"]=="H05")
    status={"joint":"ok","only_final":"ok","quality":"issue","substitute":"risk"}.get(mode,"missing")
    expected_phases=["missing"]*4 if mode in ("rider","image") else ["ok"]*3+["risk" if status=="issue" else status]
    observed=(acceptance["status"],[f["status"] for f in phases],transfer["status"])
    assert observed==(status,expected_phases,"ok" if mode in ("joint","only_final","no_final") else "missing"),(mode,observed,acceptance["detail"])
    assert [f["stage"]["share"] for f in phases]==["20","35","35","10"]
    assert (transfer["stage"]["name"],transfer["stage"]["share"])==(("第二期","35") if mode=="no_final" else ("第四期","10"))
    batch=acceptance["batch_acceptance"]
    final=batch["separate_final"]
    assert batch["completion_on"]==("2026-09-25" if status=="ok" else None)
    assert phases[-1]["warranty_check"]["calendar_end"]==("2026-11-25" if status=="ok" else None)
    assert len(final["records"])==(0 if mode=="no_final" else 1)
    record=next((r for r in batch["records"] if r["unit"] in final["records"]),None)
    signing=record.get("signing") if record else None
    names=["郑敏"] if mode=="only_final" else ["郑敏","陈琪"]
    if mode not in ("image","rider"):
        assert final["signing_requirement"]["required"]==names
        assert final["signing_requirement"]["clause_ref"] not in phases[1]["evidence"]+phases[2]["evidence"]
        if record:
            assert record["role"]=="final" and signing
            assert signing["status"]==("ok" if mode=="quality" else status)
            assert signing["missing_names"]==(["陈琪"] if mode in ("borrowed","substitute") else [])
            assert signing["other_names"]==(["林岚"] if mode=="substitute" else [])
            assert all(s["unit"]==record["unit"] for s in signing["signed"])
    graph=report["graph"]
    final_links=[e for e in graph["edges"] if e["type"]=="final_named_signature"]
    assert len(final_links)==(len(names) if status=="ok" else 0)
    assert sum(e["type"]=="batch_named_signature" for e in graph["edges"])==(0 if mode in ("only_final","image","rider") else 3)
    if final_links:
        assert signing
        assert all(e["from"]==final["signing_requirement"]["clause_ref"] for e in final_links)
        assert {e["to"] for e in final_links}=={s["fact"] for s in signing["signed"]}
    verdict=report["result"]["verdict"]
    if status=="ok" and verdict=="review":
        marks={f["id"] for f in graph["facts"] if normalize(f["quote"])==normalize(WATERMARK)}
        outstanding=[f for f in findings if f["status"]!="ok"]
        assert outstanding and all(f["rule"]=="X01" and f["evidence"] and set(f["evidence"])<=marks for f in outstanding)
    else:
        assert verdict=={"ok":"pass","issue":"reject"}.get(status,"review")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-final-signers-v1")
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
        queue.append((mode,cid,folder,records))
    for mode,cid,folder,records in queue:
        report=settle(cid,folder,records)
        validate(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
