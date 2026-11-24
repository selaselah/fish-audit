"""Exercise a returned contract, a retained original and a newly supplied receipt in the local demo."""

import argparse
import hashlib
import json
import re
import subprocess
from urllib.request import Request, urlopen

from bank import write_bank_pair
from generate import ROOT, generate_resubmission
from run import BASE, get, submit, wait


def send_supplement(parent, rev, title, files, retained, key, note):
    command = ["curl","--silent","--show-error","--fail-with-body","-H","Idempotency-Key: "+key,
               "--form-string","title="+title,"--form-string","rev="+str(rev),"--form-string","note="+note]
    for doc in retained:
        command += ["--form-string", "retain="+doc]
    for file in files:
        command += ["-F", "files=@"+str(file)]
    return json.loads(subprocess.check_output(command+[BASE+"/api/cases/"+parent+"/supplements"]))["id"]


def exercise(run_id, mode):
    code = hashlib.sha256(run_id.encode()).hexdigest()[:8].upper()
    folder = ROOT / "11-退回补交银行回单" / code
    write_bank_pair(folder, "YL-S-"+code, "0123467891654325", "YL-S-"+code+"-A")
    contract, receipt = folder/"采购合同.pdf", folder/"银行付款回单.pdf"
    if not mode:
        return
    title = "合成演练 · 缺银行回单 · "+code
    parent = submit(title, [contract], run_id+"-parent", "cn-bank-contract-payment/v1")
    report = wait(parent)
    url = "/api/cases/"+parent
    detail = get(url)
    old_rev = detail["rev"]
    old_hash = detail["revisions"][0]["hash"]
    assert detail["title"] == title and len(detail["documents"]) == 1
    original = detail["documents"][0]
    assert original["sha256"] == hashlib.sha256(contract.read_bytes()).hexdigest()
    assert any(f["rule"] == "B01" and f["status"] == "missing" for f in report["findings"])
    if detail["status"] == "ready":
        payload = {"rev": old_rev, "decision": "return", "reviewer": "合成演练验收",
                   "note": "此水印样本只有采购合同，请保留合同并补交同一合同的银行付款回单。"}
        req = Request(BASE+url+"/signoff", data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
        with urlopen(req, timeout=20) as response:
            assert response.status == 200
    assert get(url)["decisions"][-1]["decision"] == "return"
    print("原退回任务", BASE+"/workpaper/"+parent, flush=True)
    if mode == "parent":
        return
    child = send_supplement(parent,old_rev,"合成演练 · 补交银行回单 · "+code,[receipt],[original["id"]],
                            run_id+"-child","沿用前案合同，补交对应的水印银行付款回单。")
    print("补件任务", BASE+"/workpaper/"+child, flush=True)
    current = wait(child)
    lineage = current["supplement"]
    assert lineage["parent"] == parent and lineage["report_hash"] == old_hash and lineage["rev"] == old_rev
    assert lineage["retained"] == [{"parent_doc": original["id"], "doc": "d01"}]
    before = next(g for g in lineage["comparisons"] if g["rule"] == "B01")
    assert [f["status"] for f in before["before"]] == ["missing"] and [f["status"] for f in before["after"]] == ["ok"]
    expected_verdict = "review" if current["policy"].get("performance_checks") else "pass"
    assert current["result"]["verdict"] == expected_verdict, [(f["rule"], f["detail"]) for f in current["findings"] if f["status"] != "ok"]
    assert get(url)["revisions"][0]["hash"] == old_hash
    print("通过 · 原退回版本、原件摘要、B01 对照及独立补件结论", flush=True)


def replace_training_photo(parent, run_id):
    if not re.fullmatch("[a-f0-9]{32}",parent):
        raise ValueError("请选择退回的合成照片任务")
    url = "/api/cases/"+parent
    detail = get(url)
    assert detail["title"].startswith("合成演练 · ") and detail["status"] == "closed" and detail["decisions"][-1]["decision"] == "return"
    rev = detail["rev"]
    old = get(url+"/reports/"+str(rev))["report"]
    assert any(f["field"] == "invoice_id" and f["value"] == "YL-FP-038" and f["status"] in {"confirmed","anchored"} for f in old["graph"]["facts"])
    folder = generate_resubmission()
    child = send_supplement(parent,rev,"合成演练 · 替换退回照片并复核同票",sorted(folder.glob("*.pdf")),[],
                            run_id+"-photo-"+parent,"本次用三份清晰的合成 PDF 替换此前的模糊照片。")
    print("整套替换",BASE+"/workpaper/"+child,flush=True)
    current = wait(child)
    assert current["supplement"]["retained"] == [] and current["supplement"]["parent"] == parent
    assert any(f["rule"] == "I02" and f["status"] == "risk" for f in current["findings"])
    assert any(m["case_id"] == parent and m["rev"] == rev and m["decision"] == "return" for m in current["graph"]["prior_invoices"])
    print("通过 · 旧底稿退回意见及同号原票均可追溯",flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="synthetic-returned-bank-v1")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--run", dest="mode", action="store_const", const="all", help="运行两案并验收")
    group.add_argument("--prepare-parent", dest="mode", action="store_const", const="parent", help="仅建立退回样本，用于网页提交补件")
    group.add_argument("--replace-photo", metavar="CASE_ID", help="用三份合成 PDF 替换已退回的 YL-FP-038 演练照片")
    args = parser.parse_args()
    if args.replace_photo:
        replace_training_photo(args.replace_photo,args.run_id)
    else:
        exercise(args.run_id, args.mode)
