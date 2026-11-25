"""Exercise same-period transfers against the contractual release milestone using watermarked originals."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, embedded_font, pdf
from quality_addenda import FIELDS as CONTRACT_FIELDS
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit
from warranty_release import check_training_watermark


CASES={"balanced":"两笔不同流水合计恰为合同第二期", "partial":"本次两笔验收款仅覆盖第二期的一部分",
       "excess":"两笔成功验收款分别支付后合计超过本期", "repeat":"同一笔验收款的两份回单副本",
       "conflict":"同流水两份回单金额相异", "early":"第二期金额齐备但首笔早于验收",
       "approval":"第二期金额相符而合同约定的董事会批准缺件", "reversal":"银行回单附带该笔后来冲正的说明",
       "allocation":"一笔回单同时记载第一期和第二期", "quality":"两笔合计相符而验收原页实测柜温超限",
       "separate":"预付款和验收款各有独立期次和流水"}
TITLES={n:"银行付款回单" for n in ("第一张银行回单","第二张银行回单")}
LABELS={**CONTRACT_FIELDS,"付款金额":"transfer_amount","交易流水号":"transfer_ref","交易状态":"transfer_status",
        "付款日期":"paid_on","付款户名":"payer","收款户名":"payee","币种":"currency","金额单位":"unit"}


def generate(seed,mode):
    code=hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    records=documents(code,"complete")
    bank=records.pop("银行付款回单")
    contract=records["采购合同"]
    contract.extend([("币种","人民币"),("金额单位","元")])
    if mode=="approval":
        contract[:]=[(k,"本合同自双方盖章并经甲方董事会批准后生效" if k=="生效条款" else v) for k,v in contract]
    if mode=="quality":
        records["验收报告"]=[(k,"柜温8℃" if k=="实测结果" else v) for k,v in records["验收报告"]]
    amounts={"partial":["25,000.00","15,000.00"],"excess":["40,000.00","30,000.00"],
             "repeat":["30,000.00","30,000.00"],"separate":["30,000.00","60,000.00"]}.get(mode,["25,000.00","35,000.00"])
    for i,name in enumerate(TITLES):
        reference="YL-"+code+"-"+("1" if mode in ("repeat","conflict") else str(i+1))
        data={"付款金额":amounts[i],"付款日期":("2026年9月15日" if mode=="early" and not i else
                                          "2026年9月21日" if not i or mode in ("repeat","conflict") else "2026年9月22日"),
              "款项用途":"第一期及第二期" if mode=="allocation" and i else "第一期" if mode=="separate" and not i else "第二期"}
        records[name]=[(k,data.get(k,v)) for k,v in bank]+[("交易流水号",reference),("币种","人民币"),("金额单位","元")]
        if mode=="reversal" and i:
            records[name].append(("银行附注","本笔后来已冲正，净额另核"))
    folder=ROOT/"40-同一期分笔付款"/code
    folder.mkdir(parents=True,exist_ok=True)
    font=embedded_font("StageTransfersCJK")
    for name,rows in records.items():
        pdf(folder/(name+".pdf"),TITLES.get(name,name),rows,font=font,spacing=25)
    return folder,records


def settle(cid,folder,records):
    reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=LABELS,printed_titles=TITLES,
                             row_spacing=25,exact_fields=("total","transfer_amount","transfer_ref","payment_stage","payment_designation"))
    report=confirm_printed_records(cid,folder,records)
    return check_training_watermark(cid,folder,records,report)


def validate(report,mode):
    calls=report["calls"]
    assert len(calls["pages"])==5 and all(c["response_id"] and c["request_id"] for c in [*calls["pages"],calls["expert"]])
    fs=report["findings"]
    rows=[f for f in fs if f["rule"]=="H06"]
    ledger=report["graph"]["stage_payment_sources"]
    assert len(ledger["banks"])==2
    assert len([f for f in fs if f["rule"]=="H05"])==2
    assert [f["stage"]["share"] for f in fs if f["rule"]=="H04" and f.get("stage")]==["30","60","10"]
    verdict=report["result"]["verdict"]
    if mode=="separate":
        assert [(f["stage"]["name"],f["stage_payments"]["seen"],len(f["stage_payments"]["records"]),f["status"]) for f in rows]==[
            ("第一期","30000.00",1,"ok"),("第二期","60000.00",1,"ok")]
        assert verdict=="pass"
        return
    if mode=="allocation":
        assert [(f.get("stage",{}).get("name"),f["stage_payments"]["seen"]) for f in rows]==[("第二期",None),(None,None)]
        assert all(f["status"]=="missing" for f in rows) and verdict=="review"
        return
    f,=rows
    entry=f["stage_payments"]
    assert len(entry["records"])==2 and f["stage"]["name"]=="第二期"
    assert entry["expected"]=="60000.00"
    if mode in ("conflict","reversal"):
        assert f["status"]=="missing" and entry["seen"] is None and entry["difference"] is None
        if mode=="reversal":
            assert any("冲正" in n["quote"] for n in ledger["notes"])
        else:
            assert any("同一流水" in why for why in entry["reasons"])
    elif mode in ("balanced","partial","excess","repeat"):
        state,seen,delta,status={"balanced":("balanced","60000.00","0.00","ok"),"partial":("partial","40000.00","-20000.00","missing"),
            "excess":("over","70000.00","10000.00","risk"),"repeat":("partial","30000.00","-30000.00","missing")}[mode]
        assert (entry["state"],entry["seen"],entry["difference"],f["status"])==(state,seen,delta,status)
        assert [t["status"] for t in entry["timing"]]==["ok","ok"]
        assert sum(bool(r["duplicate_of"]) for r in entry["records"])==int(mode=="repeat")
    else:
        assert entry["state"]=="balanced" and entry["difference"]=="0.00" and f["status"]!="ok"
        if mode=="early":
            assert [t["status"] for t in entry["timing"]]==["risk","ok"]
        if mode=="approval":
            assert any(h["rule"]=="H01" and h["status"]=="missing" and "董事会" in h["detail"] for h in fs)
        if mode=="quality":
            assert any(h["rule"]=="H02" and h["status"]=="issue" for h in fs)
    assert verdict=={"balanced":"pass","quality":"reject"}.get(mode,"review"),(mode,verdict,f["detail"])


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-stage-transfers-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    pending=[]
    for mode in args.cases:
        folder,records=generate(args.run_id,mode)
        if not args.run:
            print(folder)
            continue
        cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
        print(mode,BASE+"/workpaper/"+cid,flush=True)
        pending.append((mode,cid,folder,records))
    for mode,cid,folder,records in pending:
        report=settle(cid,folder,records)
        validate(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
