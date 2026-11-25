"""Exercise the parties named in clearly watermarked procurement contracts and seal-name fields."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import BUYER, SELLER, ROOT, embedded_font, pdf
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit
from warranty_release import FIELDS as PROCUREMENT_FIELDS, check_training_watermark


BUY="青禾演练设备有限公司"
SELL="云桥演练冷链有限公司"
CASES={"branch":"甲方签章栏与单列印章单位名称不同","aligned":"双方印章单位与约定签署主体相符",
       "masked":"采购方印章单位名称部分遮挡","direct":"乙方签章栏记载名称相近的分公司",
       "duplicate":"合同同一方有两条不同的印章单位名称"}
FIELDS={**PROCUREMENT_FIELDS,"甲方印章单位名称":"buyer_seal_name","乙方印章单位名称":"seller_seal_name"}


def generate(seed,mode):
    code=hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    records=documents(code,"complete")
    for rows in records.values():
        rows[:]=[(k,v.replace(BUYER,BUY).replace(SELLER,SELL)) for k,v in rows]
    rows=records["采购合同"]
    if mode=="direct":
        rows[:]=[(k,SELL+"苏州分公司（已盖章）" if k=="乙方签章" else v) for k,v in rows]
    else:
        holder={"branch":BUY+"杭州分公司","masked":"青禾演练设备＊＊公司"}.get(mode,BUY)
        rows.extend([("甲方印章单位名称",holder),("乙方印章单位名称",SELL)])
        if mode=="duplicate":
            rows.append(("甲方印章单位名称",BUY+"杭州分公司"))
    bank={"付款日期":"2026年9月5日","款项用途":"第一期","付款金额":"30,000.00"}
    records["银行付款回单"]=[(k,bank.get(k,v)) for k,v in records["银行付款回单"]]
    folder=ROOT/"合同签署主体"/code
    folder.mkdir(parents=True,exist_ok=True)
    font=embedded_font("ContractPartiesCJK")
    for title,fields in records.items():
        pdf(folder/(title+".pdf"),title,fields,font=font,spacing=28)
    return folder,records


def run_case(cid,folder,records):
    reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=FIELDS,row_spacing=28,
                             exact_fields=("buyer_seal_name","seller_seal_name","buyer_signature","seller_signature"))
    report=confirm_printed_records(cid,folder,records)
    return check_training_watermark(cid,folder,records,report)


def validate(report,mode):
    findings=[f for f in report["findings"] if f["rule"].startswith("H")]
    signed=next(f for f in findings if f["rule"]=="H01")
    actual={r["side"]:r["state"] for r in signed["effect_review"]["party_seals"]}
    expected={"branch":"different","aligned":"match","masked":"partial","duplicate":"multiple"}
    assert actual==({"seller":"different"} if mode=="direct" else {"buyer":expected[mode],"seller":"match"}),actual
    status={"branch":"risk","aligned":"ok","masked":"missing","direct":"risk","duplicate":"missing"}[mode]
    assert signed["status"]==status,(signed["status"],signed["detail"])
    assert [f["status"] for f in findings if f["rule"] in ("H02","H03")]==["ok","ok"]
    assert [f["status"] for f in findings if f["rule"] in ("H04","H05")]==["ok" if mode=="aligned" else "missing"]*4
    graph=report["graph"]
    rows={r["id"]:r for r in graph["contract_effect_sources"]["signing_rows"]}
    for item in signed["effect_review"]["party_seals"]:
        for ids in item["rows"].values():
            assert all(i in signed["evidence"] and rows[i]["side"]==item["side"] for i in ids)
        if item["comparison"]:
            left,right=item["comparison"]
            assert any(e["type"]=="contract_seal_name_comparison" and (e["from"],e["to"])==(left,right)
                       and e["status"]==item["status"] for e in graph["edges"])


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-contract-party-seals-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    pending=[]
    for mode in args.cases:
        folder,records=generate(args.run_id,mode)
        if args.run:
            cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
            print(mode,cid,flush=True)
            pending.append((mode,cid,folder,records))
        else:
            print(folder)
    for mode,cid,folder,records in pending:
        r=run_case(cid,folder,records)
        validate(r,mode)
        print(mode,BASE+"/workpaper/"+cid+"?rev="+str(get("/api/cases/"+cid)["rev"]),
              [(f["rule"],f["status"]) for f in r["findings"] if f["rule"].startswith("H")],flush=True)
