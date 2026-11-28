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
         "image":"两人验收签字另有影像代签说明",
         "before":"验收款早于第二人签认三天","same_day":"验收款与最后签认同日","after":"验收款晚于第二人签认一天",
         "clock_early":"验收款在最后签认前扣款","clock_late":"验收款在最后签认后扣款",
         "clock_print":"验收款回单仅列打印时刻","three_before":"第二期验收款早于第三位约定验收人的签认日期"}
PAID_DAYS = {"before":22, "same_day":25, "after":26}
CLOCKS = {"clock_early":("实际扣款时间","13:10","before"), "clock_late":("实际扣款时间","16:30","after"),
          "clock_print":("回单打印时间","16:30","missing")}
NOTE = "签认附注：林岚一栏为代签，须核对授权"


def generate(seed,mode):
    code=hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    folder=ROOT/"28-验收签认权限"/code
    folder.mkdir(parents=True,exist_ok=True)
    records=reinspection_records(code,"closed") if mode=="retest" else documents(code,"complete")
    clause="终验及整改复验均须由周宁、林岚共同签字确认" if mode=="retest" else "终验须由周宁、林岚共同签字确认"
    if mode=="three_before":
        clause="终验须由周宁、林岚、陈和平共同签字确认"
    records["采购合同"].append(("验收签认约定",clause))
    for title,label in (("验收报告","验收签认"),("复验报告","复验签认")):
        if title not in records:
            continue
        names=["周宁","林岚"]
        if mode=="missing" or title=="复验报告":
            names=["周宁"]
        elif mode=="different":
            names=["周宁","何平"]
        elif mode=="three_before":
            names.append("陈和平")
        records[title]=[(k,v) for k,v in records[title] if k!=label]+[(label,n+"（已签字）") for n in names]
    if mode in PAID_DAYS or mode in CLOCKS or mode=="three_before":
        records["验收报告"].extend([("周宁签认日期","2026年9月20日"), ("林岚签认日期","2026年9月25日")])
        if mode=="three_before":
            records["验收报告"].append(("陈和平签认日期","2026年9月27日"))
        title = next(k for k in records if "回单" in k)
        records[title] = [(k, f"2026年9月{PAID_DAYS.get(mode,25)}日" if k == "付款日期" else v) for k,v in records[title]]
        if mode in CLOCKS:
            label, at, _ = CLOCKS[mode]
            records["验收报告"].append(("林岚签认时间","2026年9月25日 15:20（北京时间）"))
            records[title].append((label,f"2026年9月25日 {at}（北京时间）"))
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
    payment = next(f for f in findings if f["rule"]=="H05")
    if mode=="three_before":
        timing=payment["signer_timing"]
        assert a["required"]==timing["required"]==["周宁","林岚","陈和平"]
        assert (payment["stage"]["name"],payment["status"],timing["state"],timing["days"])==("第二期","risk","before",-2)
        assert timing["latest_on"]=="2026-09-27" and paper["result"]["human_required"]
        return
    if mode in CLOCKS:
        timing = payment.get("signer_timing", {})
        clock = timing.get("clock", {})
        assert (timing.get("state"), clock.get("state")) == ("same_day", CLOCKS[mode][2]), payment
        assert clock["relevant"] == ["林岚"] and len(clock["rows"]) == 2
        assert set(clock["rows"]) <= set(payment["evidence"])
        assert bool(clock["debit"]) == (mode != "clock_print")
        assert payment["status"] == ("risk" if mode == "clock_early" else "missing")
        assert paper["result"]["verdict"] == "review"
        return
    if mode in PAID_DAYS:
        timing = payment["signer_timing"]
        assert (timing["state"],timing["days"],timing["latest_on"]) == (mode,PAID_DAYS[mode]-25,"2026-09-25"), timing
        assert set(timing["rows"]) <= set(payment["evidence"]) and len(timing["rows"]) == 2
        assert payment["status"] == ("risk" if mode=="before" else "missing")
        assert paper["result"]["verdict"] == "review" and a["required"] == ["周宁","林岚"]
        return
    expected={"joint":("ok","ok","ok","review"),"missing":("missing","missing","missing","review"),
              "different":("risk","risk","risk","review"),"retest":("missing","issue","risk","reject"),
              "image":("missing","missing","missing","review")}
    status,quality,stage,verdict=expected[mode]
    assert (a["status"],h["status"],paper["result"]["verdict"])==(status,quality,verdict),[(f["rule"],f["status"],f["detail"]) for f in findings]
    assert all(f["status"]=="ok" for f in findings if f["rule"] in ("H01","H03"))
    assert [f["status"] for f in findings if f["rule"]=="H04"]==["ok",stage,stage]
    assert payment["status"]=="missing"
    if mode=="joint":
        assert payment["signer_timing"]["state"]=="incomplete"
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
