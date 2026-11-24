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
         "redacted":"合同和委托书仅列隐去的姓名"}
IDENTITIES = {"role":"采购负责人", "joint":"演练林岚及演练方程", "redacted":"张某"}
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
             ("授权出具日期","2026年7月25日"),("授权起始日","2026年8月1日"),
             ("授权截止日","2026年8月31日" if mode=="expired" else "2026年9月30日"),
             ("委托单位签章",BUYER+"（已盖章）")]
    if mode=="restriction":
        grant.append(("备注","签约前须另经采购总监书面批准"))
    records["授权委托书"] = grant
    font = embedded_font("MandateSampleCJK")
    for title,rows in records.items():
        pdf(folder/(title+".pdf"),title,rows,font=font)
    return folder, records


def verify_case(report, mode):
    h01, = [f for f in report["findings"] if f["rule"]=="H01"]
    entry, = h01["delegations"]
    status = {"valid":"ok","expired":"risk","receipt":"risk"}.get(mode,"missing")
    assert (h01["status"],entry["status"],entry["agent"])==(status,status,IDENTITIES.get(mode,AGENT)), h01
    if mode in IDENTITIES:
        hold, = report["graph"]["delegation_coverage"]["agent_holds"]
        assert (hold["kind"],entry["agent_kind"],hold["value"])==(mode,mode,IDENTITIES[mode])
        edge, = [e for e in report["graph"]["edges"] if e["type"]=="unresolved_grant_agent"]
        assert edge["to"]==hold["fact"] and hold["fact"] in entry["evidence"]
        assert not any(n["type"]=="mandatary" for n in report["graph"]["nodes"])
        assert all(f["status"]=="missing" for f in report["findings"] if f["rule"]=="H05")
    assert entry["signed_on"]=="2026-09-01" and entry["issued_on"]=="2026-07-25"
    assert set(entry["evidence"])<=set(h01["evidence"])
    assert next(f for f in report["findings"] if f["rule"]=="H02")["status"]=="ok"
    assert next(f for f in report["findings"] if f["rule"]=="H03")["status"]=="ok"
    phases = [f for f in report["findings"] if f["rule"]=="H04"]
    assert [f["stage"]["share"] for f in phases]==["30","60","10"]
    assert all(f["status"]==("ok" if mode=="valid" else "missing") and set(entry["units"])<=set(f["scope"]) for f in phases)
    assert report["result"]["verdict"]==("pass" if mode=="valid" else "review"), report["findings"]
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
