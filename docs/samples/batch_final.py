"""Exercise a separate final acceptance, its supporting receipts and warranty dates with marked originals."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from delivery_batches import FIELD_LABELS, SPACING, TITLES as BATCH_TITLES, batch_documents
from generate import ROOT, embedded_font, pdf
from quality_addenda import pdf_with_note
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit
from warranty_release import CONDITION, FIELDS, check_training_watermark


FINAL = "全套交付终验报告"
TITLES = {**BATCH_TITLES, FINAL:"验收报告"}
LABELS = {**FIELDS, **FIELD_LABELS, "所附批次验收单号":"batch_receipt_refs"}
CASES = {
    "complete":"分批后另行终验且引用两份验收原件", "no_refs":"总单缺少所附批次验收单号",
    "wrong_ref":"总单引用了另一份批次验收单号", "equipment":"总单列入合同外设备",
    "early_final":"总单签于第二批验收前", "quality":"总单勾选合格但实测超过合同上限",
    "early_paid":"质保期按另行终验起算且第四期提前实付", "image":"终验页另有暂停全部付款的影像批注",
}


def generate(seed, mode):
    code = hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    folder = ROOT/"37-另行终验与质保起算"/code
    folder.mkdir(parents=True, exist_ok=True)
    records = batch_documents(code, "separate")
    records["采购合同"].extend([("质保期限","自终验合格之日起2个月，届满日不顺延"),("质保金返还条件",CONDITION)])
    refs = [dict(records[name])["验收单编号"] for name in BATCH_TITLES]
    if mode=="wrong_ref":
        refs[1] += "9"
    values = {"验收日期":"2026年9月18日" if mode=="early_final" else "2026年9月25日"}
    if mode=="quality":
        values.update({"检验依据":"柜温不高于9℃","实测结果":"柜温8℃"})
    ids = "E-11、E-12、E-21、"+("E-29" if mode=="equipment" else "E-22")
    records[FINAL] = [(k,values.get(k,v)) for k,v in documents(code,"complete")["验收报告"]]
    records[FINAL].extend([("验收单编号","ZY-"+code),("验收设备编号",ids)])
    if mode!="no_refs":
        records[FINAL].append(("所附批次验收单号","、".join(refs)))
    release = records["质保期满确认单"]
    release[:] = [(k,"2026年11月26日双方确认质保期已满" if k=="质保期满确认" else v) for k,v in release]
    release.append(("质保遗留事项","无未关闭缺陷"))
    bank = {"付款日期":"2026年11月22日" if mode=="early_paid" else "2026年11月27日","款项用途":"第四期","付款金额":"10,000.00"}
    records["银行付款回单"] = [(k,bank.get(k,v)) for k,v in records["银行付款回单"]]
    font = embedded_font("BatchFinalCJK")
    for name,rows in records.items():
        path = folder/(name+".pdf")
        title = TITLES.get(name,name)
        if name==FINAL and mode=="image":
            pdf_with_note(path,title,rows,font,"附注：暂停全部付款，待双方书面核准",spacing=SPACING,note_y=110)
        else:
            pdf(path,title,rows,font=font,spacing=SPACING)
    return folder,records


def settle(cid,folder,records):
    reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=LABELS,printed_titles=TITLES,
                             row_spacing=SPACING,exact_fields=("delivery_batch","delivered_serials","batch_receipt_refs"))
    report = confirm_printed_records(cid,folder,records)
    return check_training_watermark(cid,folder,records,report)


def validate(report,mode):
    calls=report["calls"]
    assert len(calls["pages"])==6 and all(c["request_id"] and c["response_id"] for c in [*calls["pages"],calls["expert"]])
    findings=report["findings"]
    acceptance=next(f for f in findings if f["rule"]=="H02")
    phases=[f for f in findings if f["rule"]=="H04"]
    transfer=next(f for f in findings if f["rule"]=="H05")
    batch=acceptance["batch_acceptance"]
    status={"complete":"ok","early_paid":"ok","no_refs":"missing","image":"missing","quality":"issue"}.get(mode,"risk")
    expected_phases=["missing"]*4 if mode=="image" else ["ok"]*3+["risk" if status=="issue" else status]
    expected_transfer={"complete":"ok","early_paid":"risk"}.get(mode,"missing")
    observed=(acceptance["status"],[f["status"] for f in phases],transfer["status"])
    assert observed==(status,expected_phases,expected_transfer),(mode,observed,acceptance["detail"],transfer["detail"])
    assert batch["separate_final"]["status"]==status and not batch["deemed_final"]
    assert [f["stage"]["share"] for f in phases]==["20","35","35","10"]
    assert batch["completion_on"]==("2026-09-25" if status=="ok" else None)
    assert len(batch["separate_final"]["records"])==1
    warranty=phases[-1]["warranty_check"]
    assert warranty["calendar_end"]==("2026-11-25" if status=="ok" else None)
    links=[e for e in report["graph"]["edges"] if e["type"]=="batch_final_basis"]
    assert len(links)==(2 if status=="ok" else 0)
    if links:
        facts={f["id"]:f for f in report["graph"]["facts"]}
        cited=next(r for r in batch["records"] if r.get("role")=="final")
        assert all(e["from"]==cited["refs_ref"] and e["to"] in e["evidence"] for e in links)
        assert {facts[e["to"]]["value"] for e in links}==set(cited["receipt_numbers"])
    verdict=report["result"]["verdict"]
    if mode=="quality":
        assert verdict=="reject" and "超出" in acceptance["detail"]
    elif mode=="complete":
        assert verdict in ("pass","review")
        if verdict=="review":
            assert all(f["rule"]=="X01" for f in findings if f["status"]!="ok")
    else:
        assert verdict=="review"


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-batch-final-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args = parser.parse_args()
    queued = []
    for mode in args.cases:
        folder,records = generate(args.run_id,mode)
        if not args.run:
            print(folder)
            continue
        cid = submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
        print(mode,BASE+"/workpaper/"+cid,flush=True)
        queued.append((mode,cid,folder,records))
    for mode,cid,folder,records in queued:
        report = settle(cid,folder,records)
        validate(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
