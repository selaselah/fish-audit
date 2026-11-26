"""Exercise signing authority, its dates and limits on watermarked synthetic procurement documents."""

import argparse
import hashlib
import sys
from pathlib import Path

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import BUYER, SELLER, ROOT, embedded_font, pdf
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"server"))
from delegation import LABELS


CASES = {"valid":"委托代理人在授权期内签约", "expired":"签约时书面授权已到期",
         "receipt":"受托人仅获授权收货验收", "restriction":"委托书备注明列签约审批限制",
         "role":"合同与委托书均仅列采购负责人", "joint":"委托书记载两名代理人",
         "redacted":"合同和委托书仅列隐去的姓名", "spaced":"受托人栏以空格隔开两组姓名",
         "compound":"同一位具名受托人的四字姓名",
         "prepay_limit":"委托书限制预付款并要求书面批准",
         "amount_limit":"签署总价超过委托上限且另需审批",
         "two_approvals":"委托书分别要求财务与采购批准",
         "split_expiry":"委托书截止日期的日数断字",
         "last_day":"代理人在授权最后一天签约","before_start":"代理人在授权开始前一天签约",
         "issued_later":"签约次日才出具委托书","same_issue":"出具委托书与代理签约同日"}
IDENTITIES = {"role":"采购负责人", "joint":"演练林岚及演练方程", "redacted":"张某", "spaced":"周宁 方程", "compound":"欧阳明月"}
HOLD_KIND = {"role":"role","joint":"joint","redacted":"redacted","spaced":"joint"}
FIELDS = {name:field for field,names in LABELS.items() for name in names}
FIELDS.update({"签约日期":"signed_on","实际生效日期":"effect_on","生效条款":"effect_clause","约定交付数量":"quantity_agreed",
               "约定验收标准":"acceptance_criteria","付款条款":"payment_term","第一期":"payment_stage","第二期":"payment_stage",
               "第三期":"payment_stage","交易状态":"transfer_status","付款日期":"paid_on","含税总额":"total"})
AGENT = "演练林岚"


def generate(seed, mode):
    code = hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    folder = ROOT/"26-签约代理权限"/code
    folder.mkdir(parents=True,exist_ok=True)
    records = documents(code,"complete")
    agent = IDENTITIES.get(mode,AGENT)
    contract = []
    for label,value in records["采购合同"]:
        if label=="生效条款":
            value="本合同自双方签字或盖章之日起生效"
        if label=="甲方签章":
            contract.extend([("甲方代理人签字",agent+"（已签字）"),("甲方委托书编号","WT-"+code)])
        else:
            contract.append((label,value))
    records["采购合同"] = contract
    grant = [("委托书编号","WT-"+code),contract[0],("委托单位",BUYER),("受托人",agent),("交易相对方",SELLER),
             ("采购标的","四门冷藏柜"),("代理事项","办理本合同采购"),
             ("授权权限","仅限收货验收" if mode=="receipt" else "代表委托单位签署本采购合同"),
             ("授权出具日期",{"issued_later":"2026年9月2日","same_issue":"2026年9月1日"}.get(mode,"2026年7月25日")),
             ("授权起始日","2026年9月2日" if mode=="before_start" else "2026年8月1日"),
             ("授权截止日",{"expired":"2026年8月31日","last_day":"2026年9月1日","split_expiry":"2026年9月3 0日"}.get(mode,"2026年9月30日")),
             ("委托单位签章",BUYER+"（已盖章）")]
    if mode=="restriction":
        grant.append(("备注","签约前须另经采购总监书面批准"))
    if mode in ("prepay_limit","amount_limit","two_approvals"):
        first={"prepay_limit":"不得约定预付款","amount_limit":"本合同含税总价不得超过人民币80,000.00元",
               "two_approvals":"签约前须经财务负责人书面批准"}[mode]
        grant.extend([("附加限制",first),("授权限制","签约前须经采购负责人书面批准")])
    if mode=="amount_limit":
        contract[:] = [(label,"人民币100,000.00元" if label=="含税总额" else value) for label,value in contract]
    records["授权委托书"] = grant
    font = embedded_font("MandateSampleCJK")
    for title,rows in records.items():
        pdf(folder/(title+".pdf"),title,rows,font=font)
    return folder, records


def verify_case(report, mode):
    h01, = [f for f in report["findings"] if f["rule"]=="H01"]
    entry, = h01["delegations"]
    positive = mode in ("valid","compound","last_day")
    status = "ok" if positive else ("risk" if mode in ("expired","receipt","prepay_limit","amount_limit","before_start","issued_later") else "missing")
    if report["policy"].get("mandate_pdf"):
        proof, = report["graph"]["mandate_pdf_sources"]["records"]
        assert proof["state"] == "typeset" and entry["mandate_execution"] == [proof["id"]]
        assert proof["id"] in entry["evidence"]
        if status == "ok":
            status = "missing"
    contract_status = "missing" if status == "ok" and h01.get("effect_review", {}).get("pdf_execution") else status
    observed = IDENTITIES.get(mode,AGENT)
    assert (h01["status"],entry["status"],entry["agent"])==(contract_status,status,"".join(observed.split())), h01
    if mode in HOLD_KIND:
        hold, = report["graph"]["delegation_coverage"]["agent_holds"]
        assert (hold["kind"],entry["agent_kind"],hold["value"])==(HOLD_KIND[mode],HOLD_KIND[mode],observed)
        edge, = [e for e in report["graph"]["edges"] if e["type"]=="unresolved_grant_agent"]
        assert edge["to"]==hold["fact"] and hold["fact"] in entry["evidence"]
        assert not any(n["type"]=="mandatary" for n in report["graph"]["nodes"])
        assert all(f["status"]=="missing" for f in report["findings"] if f["rule"]=="H05")
        if mode=="spaced":
            signer, = report["graph"]["delegation_coverage"]["signer_holds"]
            assert signer["kind"]=="joint"
            assert all(len(h["lines"])==1 and observed in h["lines"][0]["quote"] for h in (signer,hold))
    if mode=="compound":
        assert entry["agent_kind"]=="named"
        assert not any(report["graph"]["delegation_coverage"][k] for k in ("agent_holds","signer_holds"))
    assert entry["signed_on"]=="2026-09-01"
    assert entry["issued_on"]=={"issued_later":"2026-09-02","same_issue":"2026-09-01"}.get(mode,"2026-07-25")
    if mode in ("last_day","before_start","issued_later","same_issue"):
        assert entry["issuance_order"]["state"]=={"issued_later":"before","same_issue":"same_day"}.get(mode,"after")
    if mode=="split_expiry":
        assert entry["valid_until"] is None
    if mode in ("prepay_limit","amount_limit","two_approvals"):
        assert len(entry["limits"])==2 and len({c["field_ref"] for c in entry["limits"]})==2
        for limit in entry["limits"]:
            assert limit["field_ref"] in entry["evidence"]
            if limit["status"]=="risk":
                assert limit["comparison_ref"] in h01["evidence"]
    assert set(entry["evidence"])<=set(h01["evidence"])
    delivery_status = "missing" if report["policy"].get("acceptance_pdf") else "ok"
    assert next(f for f in report["findings"] if f["rule"]=="H02")["status"]==delivery_status
    assert next(f for f in report["findings"] if f["rule"]=="H03")["status"]=="ok"
    phases = [f for f in report["findings"] if f["rule"]=="H04"]
    assert [f["stage"]["share"] for f in phases]==["30","60","10"]
    cleared = positive and contract_status == delivery_status == "ok"
    assert all(f["status"]==("ok" if cleared else "missing") and set(entry["units"])<=set(f["scope"]) for f in phases)
    assert report["result"]["verdict"]==("pass" if cleared else "review"), report["findings"]
    page, = report["graph"]["delegation_coverage"]["pages"]
    assert page["native"] and page["unit"] in entry["units"]
    assert [l["quote"] for l in page["uncovered"]]==(["备注：签约前须另经采购总监书面批准"] if mode=="restriction" else [])


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-signing-mandate-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=["valid","expired","receipt","restriction"])
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
        reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=FIELDS,
                                 document_types={"授权委托书":"power_of_attorney"})
        report=confirm_printed_records(cid,folder,records)
        verify_case(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
