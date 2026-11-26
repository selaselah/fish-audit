"""Watermarked procurement cases with identical delivery counts and different equipment test records."""

import argparse
import hashlib
import sys
from pathlib import Path

from contract_milestones import PROFILE, confirm_printed_records, documents, normalize
from generate import ROOT, WATERMARK, embedded_font, pdf
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit, wait
from warranty_release import FIELDS, check_training_watermark

sys.path.insert(0,str(Path(__file__).resolve().parents[2] / "server"))
from documents import prepare


CASES = {
    "short": "足额交付四台而逐台测温只检测一台",
    "complete": "四台交付设备逐台测温且均达标",
    "sample": "合同至少抽检两台且有两台的测温原文",
    "repeat": "抽检两行却两次记录同一设备",
    "hot": "总表记载合格但第四台的柜温超限",
    "summary": "总表写已测四台而没有单机记录",
    "unspecified": "合同只约定抽检且未列最低台数",
    "named-gap": "已测两台但合同点名的QC-02缺少测温记录",
    "named-covered": "合同点名的两台设备各有合格测温记录",
    "named-hot": "一台必检设备缺读数且另一台柜温超限",
}
SERIALS = ["QC-01", "QC-02", "QC-03", "QC-04"]
NEW_FIELDS = {"性能检测要求":"inspection_requirement", "性能实测数量":"tested_quantity", "单机测温":"unit_temperature"}
STATES = {"short":"short","complete":"covered","sample":"covered","repeat":"repeated","hot":"out_of_limit",
          "summary":"records","unspecified":"terms"}
NAMED_STATES = {"named-gap":"named_records","named-covered":"covered","named-hot":"out_of_limit"}


def generate(seed, mode):
    code = hashlib.sha256((seed + "-" + mode).encode()).hexdigest()[:8].upper()
    folder = ROOT / "逐台测温与抽检范围" / code
    folder.mkdir(parents=True, exist_ok=True)
    records = documents(code, "complete")
    requirement = "全部交付设备逐台测温"
    if mode in ("sample", "repeat") or mode in NAMED_STATES:
        requirement = "至少抽检2台测温"
    elif mode == "unspecified":
        requirement = "按到货情况抽检测温"
    records["采购合同"].append(("性能检测要求", requirement))
    if mode in NAMED_STATES:
        records["采购合同"].append(("必检设备编号","QC-02、QC-03"))
    observed = [("QC-01","3")] if mode == "short" else [(s,"3") for s in SERIALS]
    if mode in ("sample","unspecified","named-gap"):
        observed = [("QC-01","3"),("QC-03","2.5")]
    elif mode == "named-covered":
        observed = [("QC-02","3"),("QC-03","2.5")]
    elif mode == "named-hot":
        observed = [("QC-01","3"),("QC-03","8")]
    elif mode == "repeat":
        observed = [("QC-01","3"),("QC-01","2.5")]
    elif mode == "hot":
        observed[-1] = ("QC-04","8")
    count = 4 if mode == "summary" else len(observed)
    records["验收报告"].extend([("验收设备编号","、".join(SERIALS)),("性能实测数量",f"{count}台")])
    if mode != "summary":
        records["验收报告"].extend(("单机测温",f"{serial}，柜温{reading}℃") for serial,reading in observed)
    font = embedded_font("InspectionScopeCJK")
    for title, rows in records.items():
        pdf(folder/(title+".pdf"),title,rows,font=font,spacing=28)
    return folder,records


def review(cid, mode, folder, records):
    detail = get("/api/cases/"+cid)
    assert detail["title"] == "合成演练 · "+CASES[mode] and not detail["decisions"]
    report = wait(cid)
    nodes = {n["id"]:n for n in report["graph"]["nodes"] if n["type"]=="page"}
    expected_files = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob("*.pdf")}
    assert {d["name"]:d["sha256"] for d in detail["documents"]} == expected_files
    for doc in detail["documents"]:
        p, = prepare(folder/doc["name"], 1, save_images=False)
        assert p["sha256"] == nodes[doc["id"]+"/p1"]["sha256"] and normalize(WATERMARK) in normalize(p["text"])
    # Older extractors stored these printed items as general observations.
    fields = NEW_FIELDS if report["policy"].get("inspection_coverage") else {key:"other" for key in NEW_FIELDS}
    if report["policy"].get("inspection_coverage") == "inspection-coverage-v2":
        fields = {**fields,"必检设备编号":"inspection_required_serials"}
    reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),row_spacing=28,
                             field_labels={**FIELDS,"验收设备编号":"delivered_serials",**fields},
                             exact_fields=("unit_temperature","inspection_required_serials"))
    report = check_training_watermark(cid,folder,records,confirm_printed_records(cid,folder,records))
    if report["policy"].get("inspection_coverage"):
        procedure = next(f for f in report["findings"] if f["rule"]=="H02")
        if mode in NAMED_STATES:
            proof = procedure["inspection_coverage"]
            if proof["format"] == "inspection-coverage-v2":
                assert proof["state"] == NAMED_STATES[mode] and proof["tested"] == 2, (mode,proof)
                assert proof["named"]["missing"] == ([] if mode == "named-covered" else ["QC-02"])
            return report
        assert procedure["inspection_coverage"]["state"] == STATES[mode], (mode,procedure["inspection_coverage"])
        stages = [f["status"] for f in report["findings"] if f["rule"]=="H04"]
        effective = next(f["status"]=="ok" for f in report["findings"] if f["rule"]=="H01")
        assert (stages[0]=="ok")==effective and (stages[1]=="ok")==(effective and mode in ("complete","sample")), (mode,stages)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-id", default="synthetic-inspection-coverage-v1")
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    args = parser.parse_args()
    pending = []
    for mode in args.cases:
        folder, records = generate(args.run_id, mode)
        if args.run:
            cid = submit("合成演练 · "+CASES[mode], sorted(folder.glob("*.pdf")), args.run_id+"-"+mode, PROFILE)
            print(mode,cid,flush=True)
            pending.append((cid, mode, folder, records))
        else:
            print(folder)
    for cid, mode, folder, records in pending:
        report = review(cid, mode, folder, records)
        print(mode,BASE+"/workpaper/"+cid+"?rev="+str(get("/api/cases/"+cid)["rev"]),
              [(f["rule"],f["status"]) for f in report["findings"] if f["rule"].startswith("H")],flush=True)
