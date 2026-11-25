"""Run watermarked procurement cases with identical amounts and different warranty release evidence."""

import argparse
import hashlib
from datetime import datetime, timedelta, timezone
import pypdfium2 as pdfium

from contract_dates import DATE_FIELDS
from contract_milestones import PROFILE, confirm_printed_records, documents, normalize
from generate import ROOT, WATERMARK, embedded_font, pdf
from quality_addenda import pdf_with_note
from quality_reinspection import reconcile_training_pages
from run import BASE, get, post, submit, wait


CASES={"clear":"质保期届满且有缺陷清结记录","premature":"约定质保十二个月却在两个月后付款",
       "defect":"质保期满确认单仍载有未修复故障","supplier":"质保期满确认单列有另一家供应商",
       "boundary":"质保期间最后一日确认并付款","image":"质保确认单的影像附注暂缓返还",
       "absent":"合同要求清结缺陷但确认单缺少记录","fixed":"合同明确约定质保截止日且已清结",
       "future_release":"提交时质保期未满但确认单及回单均记载已履行","future_bank":"质保已到期但成功回单落款在提交日之后",
       "at_cutoff":"质保金回单日期等于资料提交日","open_at_cutoff":"确认单记载温控故障未修复仍有质保金回单"}
CUTOFF_CASES={"future_release","future_bank","at_cutoff","open_at_cutoff"}
FIELDS={**DATE_FIELDS,"质保期限":"warranty_period","质保金返还条件":"warranty_condition","质保遗留事项":"warranty_defects",
        "质保截止日":"warranty_period","付款户名":"payer","收款户名":"payee","付款金额":"transfer_amount"}
CONDITION="质保期满且无未关闭缺陷"


def generate(seed,mode,*,as_of=None):
    key=seed+"-"+mode
    if mode in CUTOFF_CASES:
        as_of=as_of or datetime.now(timezone(timedelta(hours=8))).date()
        key+="-"+as_of.isoformat()
    code=hashlib.sha256(key.encode()).hexdigest()[:8].upper()
    folder=ROOT/"32-质保金期限及缺陷清结"/code
    folder.mkdir(parents=True,exist_ok=True)
    records=documents(code,"complete")
    contract=records["采购合同"]
    duration="12个月" if mode=="premature" else "2个月"
    contract.append(("质保截止日","2026年11月18日，届满日不顺延") if mode=="fixed" else
                    ("质保期限","自终验合格之日起"+duration+"，届满日不顺延"))
    if mode=="clear":
        contract[:]=[(k,CONDITION+"后支付10%" if k=="第三期" else v) for k,v in contract]
    else:
        contract.append(("质保金返还条件",CONDITION))
    confirmed={"boundary":"2026年11月20日","fixed":"2026年11月19日"}.get(mode,"2026年11月21日")
    changes={"质保期满确认":confirmed+"双方确认质保期已满"}
    if mode=="supplier":
        changes["供应方"]="青川演练维修中心"
    release=records["质保期满确认单"]
    release[:]=[(k,changes.get(k,v)) for k,v in release]
    if mode!="absent":
        release.append(("质保遗留事项","温控探头故障尚未修复" if mode=="defect" else "无未关闭缺陷"))
    paid={"boundary":confirmed,"fixed":"2026年11月20日"}.get(mode,"2026年11月22日")
    bank={"款项用途":"第三期","付款金额":"10,000.00","付款日期":paid}
    records["银行付款回单"]=[(k,bank.get(k,v)) for k,v in records["银行付款回单"]]
    if mode in CUTOFF_CASES:
        start=as_of-timedelta(days=62)
        days=65 if mode=="future_release" else 56
        end=start+timedelta(days=days)
        confirm=end+timedelta(days=1)
        payment=confirm+timedelta(days=1) if mode=="future_release" else as_of+timedelta(days=3 if mode=="future_bank" else 0)
        def printed(value):
            return f"{value.year}年{value.month}月{value.day}日"
        rows={"签约日期":printed(start-timedelta(days=12)),"实际生效日期":printed(start-timedelta(days=12)),
              "验收日期":printed(start),"质保期限":f"自终验合格之日起{days}个自然日，届满日不顺延",
              "质保期满确认":printed(confirm)+"双方确认质保期已满","付款日期":printed(payment),
              "质保遗留事项":"温控探头故障尚未修复" if mode=="open_at_cutoff" else "无未关闭缺陷"}
        for fields in records.values():
            fields[:]=[(k,rows.get(k,v)) for k,v in fields]
    font=embedded_font("WarrantyReleaseCJK")
    for title,rows in records.items():
        path=folder/(title+".pdf")
        if mode=="image" and title=="质保期满确认单":
            pdf_with_note(path,title,rows,font,"附注：质保金暂缓返还，须取得维修确认",spacing=28)
        else:
            pdf(path,title,rows,font=font,spacing=28)
    return folder,records


def validate(report,mode,as_of=None):
    findings=report["findings"]
    phases=[f for f in findings if f["rule"]=="H04"]
    bank,=[f for f in findings if f["rule"]=="H05"]
    expected={"clear":"ok","fixed":"ok","premature":"risk","defect":"risk","future_release":"risk",
              "at_cutoff":"ok","future_bank":"ok","open_at_cutoff":"risk"}.get(mode,"missing")
    bank_status="risk" if mode=="future_bank" else expected
    assert [f["status"] for f in findings if f["rule"] in ("H01","H02","H03")]==["ok"]*3
    assert [f["status"] for f in phases]+[bank["status"]]==["ok","ok",expected,bank_status],[(f["rule"],f["status"],f["detail"]) for f in findings]
    entry=phases[-1]["warranty_check"]
    assert bank["warranty_check"]==entry and entry["requires_defect_clearance"]
    if mode in CUTOFF_CASES:
        day=lambda offset:(as_of+timedelta(days=offset)).isoformat()
        future=mode=="future_release"
        assert (entry["accepted_on"],entry["calendar_end"],entry["confirmed_on"])==(day(-62),day(3 if future else -6),day(4 if future else -5))
        snapshot=entry["at_submission"]
        assert snapshot["as_of"]==report["graph"]["warranty_as_of"]==day(0)
        assert snapshot["future"]==(["calendar_end","confirmed_on"] if future else [])
        assert snapshot["defects"]==("listed_open" if mode=="open_at_cutoff" else "stated_clear")
        assert bank["warranty_payment"]["paid_on"]==day(5 if future else 3 if mode=="future_bank" else 0)
        assert bank["warranty_payment"]["after_submission"]==(future or mode=="future_bank")
    else:
        assert entry["accepted_on"]=="2026-09-20"
        assert entry["calendar_end"]=={"premature":"2027-09-20","fixed":"2026-11-18"}.get(mode,"2026-11-20")
        assert entry["confirmed_on"]=={"supplier":None,"boundary":"2026-11-20","fixed":"2026-11-19"}.get(mode,"2026-11-21")
    assert entry["defect_open"]==(mode in ("defect","open_at_cutoff"))
    expected_verdict="review"
    if expected==bank_status=="ok":
        remaining=[f for f in findings if f["status"]!="ok"]
        marks={f["id"] for f in report["graph"]["facts"] if f["field"]=="other" and normalize(f["quote"])==normalize(WATERMARK)}
        assert all(f["rule"]=="X01" and f["evidence"] and set(f["evidence"])<=marks for f in remaining),remaining
        expected_verdict="review" if remaining else "pass"
    assert report["result"]["verdict"]==expected_verdict
    assert len([e for e in report["graph"]["edges"] if e["type"]=="warranty_release_basis"])==(expected=="ok")
    if mode=="image":
        assert any(not p["text_only"] for p in report["graph"]["warranty_sources"]["pages"])


def check_training_watermark(cid,folder,records,report):
    selected=[]
    api="/api/cases/"+cid
    for fact in report["graph"]["facts"]:
        if (fact["status"]!="visual" or
                normalize(fact["quote"])!=normalize(WATERMARK) or normalize(fact["value"])!=normalize(WATERMARK)):
            continue
        path=folder/fact["name"]
        assert path.name in {title+".pdf" for title in records}
        doc=next(d for d in report["graph"]["documents"] if d["id"]==fact["doc"])
        assert doc["sha256"]==hashlib.sha256(path.read_bytes()).hexdigest()
        with pdfium.PdfDocument(path) as source:
            first_line=source[fact["page"]-1].get_textpage().get_text_bounded().splitlines()[0]
            assert normalize(first_line)==normalize(WATERMARK)
        if fact["field"]=="other":
            selected.append(fact["id"])
        else:
            post(api+"/amend",{"rev":get(api)["rev"],"reviewer":"水印演练校验","doc":doc["id"],"page":fact["page"],
                               "target":fact["id"],"field":"other","value":first_line,"quote":first_line,"region":"top",
                               "note":"对照摘要一致的合成原页，此处为页首测试水印，已据实更正候选字段类别。"})
            report=wait(cid)
    if selected:
        post(api+"/attest",{"rev":get(api)["rev"],"reviewer":"水印演练校验","decision":"confirm","facts":selected,
                            "note":"已对照已登记合成 PDF 的页首，确认此引文为生成件的测试水印。"})
        return wait(cid)
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-warranty-release-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    queued=[]
    as_of=datetime.now(timezone(timedelta(hours=8))).date()
    for mode in args.cases:
        folder,records=generate(args.run_id,mode,as_of=as_of)
        if not args.run:
            print(folder)
            continue
        key=args.run_id+"-"+mode+("-"+as_of.isoformat() if mode in CUTOFF_CASES else "")
        cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),key,PROFILE)
        queued.append((mode,cid,folder,records))
        print(mode,BASE+"/workpaper/"+cid,flush=True)
    for mode,cid,folder,records in queued:
        reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=FIELDS,row_spacing=28)
        report=confirm_printed_records(cid,folder,records)
        report=check_training_watermark(cid,folder,records,report)
        validate(report,mode,as_of)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
