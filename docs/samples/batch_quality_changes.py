"""Check independent acceptance dates against a prospective quality addendum using watermarked PDFs."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records
from delivery_batches import FIELD_LABELS, SPACING, TITLES, batch_documents
from generate import ROOT, embedded_font, pdf
from quality_addenda import TITLE, agreement_rows
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit
from warranty_release import check_training_watermark


CASES = {"relaxed":"两批之间放宽柜温上限，第二批实测六度",
         "stricter":"两批之间收紧柜温上限，第二批仍用旧标准",
         "same_day":"第二批验收与补充协议盖章同日",
         "split_date":"补充协议盖章日的两个数字隔开，第二批实测六度"}


def generate(seed, mode):
    code=hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    records=batch_documents(code,"complete")
    base=dict(records["采购合同"])
    revised="柜温不高于2℃" if mode=="stricter" else "柜温不高于8℃"
    seller_day={"same_day":"2026年9月20日","split_date":"2026年9月1 2日"}.get(mode,"2026年9月12日")
    records[TITLE]=agreement_rows(code,base,revised,seller_day)
    values={"检验依据":base["约定验收标准"] if mode=="stricter" else revised,
            "实测结果":"柜温3℃" if mode=="stricter" else "柜温6℃"}
    records["第二批验收报告"]=[(k,values.get(k,v)) for k,v in records["第二批验收报告"]]
    payment={"款项用途":"第三期","付款日期":"2026年9月21日"}
    records["银行付款回单"]=[(k,payment.get(k,v)) for k,v in records["银行付款回单"]]
    folder=ROOT/"44-两批验收之间变更标准"/code
    folder.mkdir(parents=True,exist_ok=True)
    font=embedded_font("BatchChangeCJK")
    for name,rows in records.items():
        pdf(folder/(name+".pdf"),TITLES.get(name,name),rows,font=font,spacing=SPACING)
    return folder,records


def validate(report,mode):
    findings=report["findings"]
    h=next(f for f in findings if f["rule"]=="H02")
    phases=[f for f in findings if f["rule"]=="H04"]
    paid=next(f for f in findings if f["rule"]=="H05")
    batch=h["batch_acceptance"]
    if mode=="split_date":
        change=h["quality_change"]
        assert change["state"]=="pending" and change["seller_sealed_on"] is None and change["effective_on"] is None
        assert h["status"]=="missing" and paid["status"]=="missing" and report["result"]["verdict"]=="review"
        assert all(r["standard"]["state"]=="pending" for r in batch["records"])
        assert all(f["status"]=="missing" for f in phases)
        assert not any(e["type"]=="batch_quality_comparison" for e in report["graph"]["edges"])
        return
    expected={"relaxed":("ok","ok","applied","ok","pass"),
              "stricter":("issue","risk","applied","missing","reject"),
              "same_day":("missing","missing","pending","missing","review")}[mode]
    assert len(phases)==4 and [p["status"] for p in phases]==["ok","ok",expected[1],expected[1]]
    first,second=sorted(batch["records"],key=lambda r:r["index"])
    assert first["standard"]["state"]=="original" and h["quality_change"]["state"]=="by_batch"
    assert (h["status"],second["standard"]["state"],paid["status"],report["result"]["verdict"])==(expected[0],*expected[2:])
    edges=[e for e in report["graph"]["edges"] if e["type"]=="batch_quality_comparison"]
    assert len(edges)==(1 if mode=="same_day" else 2)
    for record in (first,second):
        standard=record["standard"]
        stage=phases[record["index"]]
        assert set(standard["evidence"]).issubset(stage["evidence"])
    assert first["standard"]["reading_ref"] not in phases[2]["evidence"]
    assert second["standard"]["reading_ref"] not in phases[1]["evidence"]


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-batch-quality-change-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    queued=[]
    for mode in args.cases:
        folder,records=generate(args.run_id,mode)
        if not args.run:
            print(folder)
            continue
        cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
        queued.append((cid,mode,folder,records))
        print(mode,BASE+"/workpaper/"+cid,flush=True)
    for cid,mode,folder,records in queued:
        reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=FIELD_LABELS,
            document_types={TITLE:"contract_addendum"},printed_titles=TITLES,row_spacing=SPACING,
            exact_fields=("delivery_batch","delivered_serials","previous_criterion","revised_criterion"))
        report=confirm_printed_records(cid,folder,records)
        report=check_training_watermark(cid,folder,records,report)
        validate(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
