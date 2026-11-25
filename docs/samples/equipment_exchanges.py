"""Watermarked exchange receipts for equipment initially delivered under a different model."""

import argparse
import hashlib
import tempfile
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.pdfgen import canvas

from contract_milestones import PROFILE, confirm_printed_records
from generate import BUYER, ROOT, SELLER, embedded_font, pdf
from quality_addenda import FIELDS
from quality_reinspection import reconcile_training_pages, reinspection_records
from run import BASE, get, submit, wait
from warranty_release import check_training_watermark


CASES = {
    "complete": "四台冷藏柜退换交接与最终复验逐台对应",
    "serial": "换入第四台设备编号与复验不符",
    "unsigned": "换货交接未附供应方签认",
    "late": "换货交接日期晚于最终复验",
    "rider": "交接单另约提高第二期付款比例",
    "other": "换货交接单列有另一合同编号",
    "scan": "扫描交接单上的退回与换入记录待核图",
}
FORM = "设备换货交接单"
OLD = "C2-01、C2-02、C2-03、C2-04"
NEW = "C4-01、C4-02、C4-03、C4-04"
LABELS = {
    **FIELDS, "约定设备型号":"equipment_model", "实收设备型号":"equipment_model", "复验实收型号":"equipment_model",
    "验收设备编号":"delivered_serials", "交接单编号":"exchange_number", "所据换货交接单号":"exchange_number",
    "退回型号":"exchange_old_model", "换入型号":"exchange_new_model",
    "退回设备编号":"exchange_old_serials", "换入设备编号":"exchange_new_serials",
    "交接日期":"exchange_on", "交接状态":"exchange_status",
}


def generate(seed, mode):
    key = hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    records = reinspection_records(key, "closed")
    number = "HH-"+key
    records["采购合同"].append(("约定设备型号","YL-C4"))
    records["验收报告"].extend([("实收设备型号","YL-C2"),("验收设备编号",OLD)])
    records["复验报告"].extend([("复验实收型号","YL-C4"),("验收设备编号",NEW),("所据换货交接单号", number)])
    rows = list(records["采购合同"][:4])
    if mode=="other":
        rows[0]=("合同编号","YL-LY-OTHER-42")
    rows.extend([("交接单编号",number),("原验收单编号","YS-"+key),
                 ("交接日期","2026年9月22日" if mode=="late" else "2026年9月17日"),
                 ("退回型号","YL-C2"),("退回设备编号",OLD),("换入型号","YL-C4"),
                 ("换入设备编号",NEW.replace("C4-04","C4-44") if mode=="serial" else NEW),
                 ("交接状态","旧机已退回，新机已交付"),("甲方签章",BUYER+"（已盖章）")])
    if mode!="unsigned":
        rows.append(("乙方签章",SELLER+"（已盖章）"))
    if mode=="rider":
        rows.append(("另行约定","第二期验收款改为合同价的80%"))
    records[FORM]=rows
    folder=ROOT/"43-设备退换交接"/key
    folder.mkdir(exist_ok=True,parents=True)
    font=embedded_font("EquipmentExchangeCJK")
    for title,fields in records.items():
        path=folder/(title+".pdf")
        if mode=="scan" and title==FORM:
            with tempfile.TemporaryDirectory() as scratch:
                original=Path(scratch)/"form.pdf"
                pdf(original,title,fields,font=font,spacing=23)
                with pdfium.PdfDocument(original) as source:
                    pixels=source[0].render(scale=2).to_pil().convert("RGB")
                out=canvas.Canvas(str(path),pagesize=(595,842),invariant=1)
                out.drawInlineImage(pixels,0,0,595,842)
                out.showPage()
                out.save()
        else:
            pdf(path,title,fields,font=font,spacing=23)
    return folder,records


def settle(cid, folder, records):
    with pdfium.PdfDocument(folder/(FORM+".pdf")) as source:
        scan=not source[0].get_textpage().get_text_bounded().strip()
    if scan:
        report=wait(cid)
        hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob("*.pdf")}
        assert hashes=={d["name"]:d["sha256"] for d in report["graph"]["documents"]}
        return report
    reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=LABELS,
                             document_types={FORM:"equipment_exchange"},row_spacing=23,
                             exact_fields=("contract_id","buyer","seller","subject","equipment_model","payment_stage",
                                           "delivered_serials","buyer_signature","seller_signature","exchange_number"))
    paper=confirm_printed_records(cid, folder, records)
    return check_training_watermark(cid, folder, records, paper)


def validate(paper, mode):
    calls=paper["calls"]
    assert len(calls["pages"])==7 and all(c["request_id"] and c["response_id"] for c in [*calls["pages"],calls["expert"]])
    fs=paper["findings"]
    inspected=next(f for f in fs if f["rule"]=="H02")
    comparison=inspected["equipment_models"]
    audit=comparison["exchange"]
    checks={c["key"]:c["status"] for c in audit["checks"]}
    stages=[f for f in fs if f["rule"]=="H04"]
    assert [s["stage"]["share"] for s in stages]==["30","60","10"]
    if mode=="scan":
        source=paper["graph"]["equipment_model_sources"]["exchange"]
        doc=next(d["id"] for d in paper["graph"]["documents"] if d["name"]==FORM+".pdf")
        assert any(p["doc"]==doc and p["form"] and not p["native"] and p["rows"] for p in source["pages"])
        assert checks["scope"]!="ok" and audit["status"]!="ok" and not any(s["status"]=="ok" for s in stages[1:])
        return
    assert (audit["status"]=="ok")== (mode=="complete")
    assert (inspected["reinspection"]["state"]=="closed")==(mode=="complete")
    assert [s["status"]=="ok" for s in stages]==[mode!="rider",mode=="complete",mode=="complete"]
    if mode=="complete":
        assert comparison["sequence"]["outcome"]=="replacement_verified" and all(s=="ok" for s in checks.values())
    else:
        expected={"serial":"received","unsigned":"signatures","late":"date","rider":"scope","other":"identity"}
        assert checks[expected[mode]]!="ok",(mode,checks)
    if mode=="serial":
        text=next(c["detail"] for c in audit["checks"] if c["key"]=="received")
        assert "C4-04" in text and "C4-44" in text
    if mode=="unsigned":
        assert "供应方" in next(c["detail"] for c in audit["checks"] if c["key"]=="signatures")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    parser.add_argument("--run-id",default="synthetic-equipment-exchange-v1")
    args=parser.parse_args()
    for mode in args.cases:
        folder,records=generate(args.run_id,mode)
        if args.run:
            cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
            print(mode,BASE+"/workpaper/"+cid,flush=True)
            paper=settle(cid,folder,records)
            validate(paper,mode)
            print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),paper["result"]["verdict"],flush=True)
        else:
            print(folder)
