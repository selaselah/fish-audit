"""Trace the equipment named at intake and on a linked post-repair inspection."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records
from generate import ROOT, embedded_font, pdf
from quality_addenda import FIELDS
from quality_reinspection import reconcile_training_pages, reinspection_records
from run import BASE, get, submit
from warranty_release import check_training_watermark


CASES = {
    "generic": "通用验收报告作复验原型号变为合同型号",
    "formal": "具名复验报告中型号变为合同型号",
    "wrong": "温控缺陷已修复但复验仍收另一型号",
    "same": "初验与复验型号相同且温控缺陷已关闭",
}


def generate(seed, mode):
    code = hashlib.sha256((seed + "-" + mode).encode()).hexdigest()[:8].upper()
    records = reinspection_records(code, "closed")
    records["采购合同"].append(("约定设备型号", "YL-C4"))
    records["验收报告"].append(("实收设备型号", "YL-C2" if mode in ("generic","formal") else "YL-C4"))
    records["复验报告"].append(("复验实收型号", "YL-C2" if mode == "wrong" else "YL-C4"))
    titles = {"复验报告": "验收报告"} if mode == "generic" else {}
    folder = ROOT / "42-整改前后设备型号" / code
    folder.mkdir(parents=True, exist_ok=True)
    font = embedded_font("ModelRetestCJK")
    for name, rows in records.items():
        pdf(folder / (name+".pdf"), titles.get(name,name), rows, font=font, spacing=25)
    return folder, records, titles


def settle(cid, folder, records, titles):
    fields = {**FIELDS, **dict.fromkeys(("约定设备型号","实收设备型号","复验实收型号"),"equipment_model")}
    reconcile_training_pages(cid, folder, records, case_titles=CASES.values(), field_labels=fields,
                             printed_titles=titles, row_spacing=25,
                             exact_fields=("contract_id","buyer","seller","subject","equipment_model","payment_stage"))
    report = confirm_printed_records(cid, folder, records)
    return check_training_watermark(cid, folder, records, report)


def validate(report, mode):
    calls=report["calls"]
    assert len(calls["pages"])==6 and all(c["response_id"] and c["request_id"] for c in [*calls["pages"],calls["expert"]])
    fs=report["findings"]
    inspected=next(f for f in fs if f["rule"]=="H02")
    compare=inspected["equipment_models"]
    status,outcome,verdict={"generic":("risk","replacement_unverified","review"),
                            "formal":("risk","replacement_unverified","review"),
                            "wrong":("issue","final_differs","reject"),"same":("ok","same_model","pass")}[mode]
    assert compare["sequence"]=={"record_chain_state":"closed","outcome":outcome},(mode,compare["detail"])
    assert {r.get("inspection_role") for r in compare["records"]}=={"original","final"}
    assert inspected["status"]==compare["status"]==status
    assert inspected["reinspection"]["state"]==("closed" if mode=="same" else "open")
    phases=[f for f in fs if f["rule"]=="H04"]
    assert [f["stage"]["share"] for f in phases]==["30","60","10"] and phases[0]["status"]=="ok"
    assert all((f["status"]=="ok")==(mode=="same") for f in phases[1:])
    assert report["result"]["verdict"]==verdict,(mode,report["result"]["verdict"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--cases", choices=CASES, nargs="+", default=list(CASES))
    parser.add_argument("--run-id", default="synthetic-equipment-reinspection-v1")
    args = parser.parse_args()
    submitted = []
    for mode in args.cases:
        folder,records,titles=generate(args.run_id,mode)
        if not args.run:
            print(folder)
            continue
        cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
        submitted.append((mode,cid,folder,records,titles))
        print(mode,BASE+"/workpaper/"+cid,flush=True)
    for mode,cid,folder,records,titles in submitted:
        report=settle(cid,folder,records,titles)
        validate(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
