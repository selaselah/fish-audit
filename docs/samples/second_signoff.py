"""Exercise the two human signoffs on this script's watermarked overpayment specimen."""

import argparse
import hashlib
import json
from decimal import Decimal
from urllib.request import Request, urlopen

from bank import write_bank_pair
from generate import ROOT
from run import BASE, get, submit, wait


def post(path, body):
    request = Request(BASE+path, data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def exercise(run_id, mode):
    code = hashlib.sha256(run_id.encode()).hexdigest()[:8].upper()
    folder = ROOT / "12-超付独立复核" / code
    write_bank_pair(folder,"YL-P-"+code,"0123456789123456","YL-P-"+code+"-A",changed=True)
    if not mode:
        return
    files = sorted(folder.glob("*.pdf"))
    title = "合成演练 · 超付独立复核 · "+code
    cid = submit(title,files,run_id,"cn-bank-contract-payment/v1")
    path = "/api/cases/"+cid
    print(BASE+"/workpaper/"+cid,flush=True)
    wait(cid)
    case = get(path)
    assert case["title"] == title
    assert {d["name"]:d["sha256"] for d in case["documents"]} == {f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    original = get(path+"/reports/1")
    report = original["report"]
    finding = next(f for f in report["findings"] if f["rule"] == "B04")
    assert finding["status"] == "issue" and any(Decimal(c["result"]) == 150 for c in finding["calculations"]), finding["detail"]
    assert report["result"]["verdict"] == "reject"
    if case["status"] == "ready":
        post(path+"/signoff",{"rev":1,"reviewer":"演练初审林岚","decision":"escalate","note":"合同 8,400 元，回单 8,550 元，请独立复核 150 元差额。"})
    case = get(path)
    first = case["decisions"][0]
    pin = case["referrals"][0]
    assert (first["reviewer"],first["decision"],pin["rev"],pin["report_hash"]) == ("演练初审林岚","escalate",1,original["sha256"])
    if mode == "refer":
        print("原版",BASE+"/workpaper/"+cid+"?rev=1","状态",case["status"],flush=True)
        return
    if pin["resolved_rev"] is None:
        result = post(path+"/peer-review",{"rev":1,"reviewer":"演练复核沈禾","decision":"return","findings":[finding["id"]],
                      "report_hash":pin["report_hash"],"signoff_hash":pin["signoff_hash"],
                      "note":"已核付款差额算式与两份水印原页，请补交 150 元超额款项的处理依据。"})
        assert result["rev"] == 2
    resolved = get(path+"/reports/2")["report"]
    peer = resolved.pop("peer_review")
    assert resolved == report and peer["resolution"]["decision"] == "return" and peer["findings"] == [finding["id"]]
    assert get(path+"/reports/1")["sha256"] == original["sha256"]
    print("已复核退回",BASE+"/workpaper/"+cid+"?rev=2", "B04 差额 150.00 元",flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--run",dest="mode",action="store_const",const="resolve")
    modes.add_argument("--refer",dest="mode",action="store_const",const="refer")
    parser.add_argument("--run-id",default="synthetic-peer-overpayment-v1")
    args = parser.parse_args()
    exercise(args.run_id,args.mode)
