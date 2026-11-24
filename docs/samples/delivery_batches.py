"""Upload watermarked purchase files with two independent deliveries and two equal payment shares."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, embedded_font, pdf
from quality_addenda import FIELDS, pdf_with_note
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit


CASES = {
    "complete":"两批各两台均完成验收",
    "missing":"第一批已验收而第二批缺单",
    "quality":"第二批报告写合格但实测超出合同上限",
    "duplicate":"两批验收单列有同一组设备",
    "early":"两期比例相同但第三期早于第二批验收",
    "separate":"两批均合格且合同仍约定另行终验",
    "image":"第二批验收单另有影像附注",
}
TITLES={"第一批验收报告":"验收报告","第二批验收报告":"验收报告"}
FIELD_LABELS={**FIELDS,"第四期":"payment_stage","分批交付":"delivery_batch","分批验收约定":"batch_clause",
              "验收设备编号":"delivered_serials","付款户名":"payer","收款户名":"payee","付款金额":"transfer_amount"}
SPACING=28


def generate(seed,mode):
    code=hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    folder=ROOT/"30-分批交付与独立验收付款"/code
    folder.mkdir(parents=True,exist_ok=True)
    records=documents(code,"complete")
    records["采购合同"]=[(k,v) for k,v in records["采购合同"] if k not in {"付款条款","第一期","第二期","第三期"}]+[
        ("分批交付","第一批2台，设备编号 E-11、E-12"),("分批交付","第二批2台，设备编号 E-21、E-22"),
        ("分批验收约定","各批独立验收付款，"+("另行组织最终验收" if mode=="separate" else "全部批次验收合格视为终验合格")),
        ("付款条款","分四期付款"),("第一期","合同生效后支付20%"),("第二期","第一批验收合格后支付35%"),
        ("第三期","第二批验收合格后支付35%"),("第四期","质保期满后支付10%")]
    template=records.pop("验收报告")
    for n,ordinal in enumerate(("第一批","第二批"),1):
        if n==2 and mode=="missing":
            continue
        values={"验收范围":ordinal+"交付验收","验收日期":f"2026年9月{n*10}日","实际验收数量":"2台"}
        if n==2 and mode=="quality":
            values.update({"检验依据":"柜温不高于9℃","实测结果":"柜温8℃"})
        equipment=1 if mode=="duplicate" else n
        records[ordinal+"验收报告"]=[(k,values.get(k,v)) for k,v in template]+[
            ("验收单编号",f"YS-{code}-{n}"),("验收设备编号",f"E-{equipment}1、E-{equipment}2")]
    values={"款项用途":"第三期" if mode=="early" else "第二期","付款金额":"35,000.00","付款日期":"2026年9月15日"}
    records["银行付款回单"]=[(k,values.get(k,v)) for k,v in records["银行付款回单"]]
    font=embedded_font("BatchDeliveryCJK")
    for name,rows in records.items():
        path=folder/(name+".pdf")
        title=TITLES.get(name,name)
        if name=="第二批验收报告" and mode=="image":
            pdf_with_note(path,title,rows,font,"附注：第二批暂收，须复核现场情况",spacing=SPACING,note_y=110)
        else:
            pdf(path,title,rows,font=font,spacing=SPACING)
    return folder,records


def validate(report,mode):
    h,actual=(next(f for f in report["findings"] if f["rule"]==rule) for rule in ("H02","H05"))
    phases=[f for f in report["findings"] if f["rule"]=="H04"]
    expected={
        "complete":("ok",["ok"]*4,"ok","pass"),
        "missing":("missing",["ok","ok","missing","missing"],"ok","review"),
        "quality":("issue",["ok","ok","risk","risk"],"ok","reject"),
        "duplicate":("risk",["ok","risk","risk","risk"],"missing","review"),
        "early":("ok",["ok"]*4,"risk","review"),
        "separate":("missing",["ok","ok","ok","missing"],"ok","review"),
        "image":("missing",["ok","missing","missing","missing"],"missing","review"),
    }
    assert [f["stage"]["share"] for f in phases]==["20","35","35","10"]
    observation=(h["status"],[f["status"] for f in phases],actual["status"],report["result"]["verdict"])
    assert observation==expected[mode],(mode,observation,[(f["rule"],f["detail"]) for f in report["findings"] if f["status"]!="ok"])
    batch=h["batch_acceptance"]
    assert [(b["index"],b["count"],b["unit_name"]) for b in batch["batches"]]==[(1,2,"台"),(2,2,"台")]
    assert [f["stage"]["batch_index"] for f in phases[1:3]]==[1,2]
    assert batch["completion_on"]==("2026-09-20" if mode in {"complete","early"} else None)
    edges=report["graph"]["edges"]
    assert sum(e["type"]=="batch_payment_basis" for e in edges)==sum(f["status"]=="ok" for f in phases[1:3])
    if mode=="image":
        assert any(not p["text_only"] for p in report["graph"]["delivery_batch_sources"]["pages"])


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-delivery-batches-v1")
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
        reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=FIELD_LABELS,
                                 printed_titles=TITLES,row_spacing=SPACING,exact_fields=("delivery_batch","delivered_serials"))
        report=confirm_printed_records(cid,folder,records)
        validate(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
