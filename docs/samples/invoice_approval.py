"""Return an invoice without its travel claim, retain the original, and sign the corrected synthetic filing."""

import argparse
import hashlib

from concurrent_invoices import materials
from returned_files import send_supplement
from run import BASE, get, post, submit, wait


def exercise(run_id, mode):
    if mode=="single":
        run_id += "-single"
    code,number,(claim,invoice) = materials(run_id)
    if not mode:
        print(invoice.parent)
        return
    if mode=="single":
        title = "合成演练 · 单笔差旅签收 · "+code
        cid = submit(title,[claim,invoice],run_id,"cn-travel-reimbursement/v1")
        paper = wait(cid)
        assert get("/api/cases/"+cid)["title"]==title and paper["result"]["verdict"]=="pass"
        assert not paper["graph"]["prior_invoices"] and any(f["field"]=="invoice_id" and f["value"]==number for f in paper["graph"]["facts"])
        print("单笔签收",BASE+"/workpaper/"+cid,flush=True)
        return
    title = "合成演练 · 差旅缺报销单 · "+code
    parent = submit(title,[invoice],run_id+"-parent","cn-travel-reimbursement/v1")
    paper = wait(parent)
    before = "/api/cases/"+parent
    task = get(before)
    original = task["documents"][0]
    assert task["title"]==title and original["sha256"]==hashlib.sha256(invoice.read_bytes()).hexdigest()
    assert any(f["field"]=="invoice_id" and f["value"]==number and f["status"]=="anchored" for f in paper["graph"]["facts"])
    assert any(f["rule"]=="T01" and f["status"]=="missing" for f in paper["findings"])
    if task["status"]=="ready":
        post(before+"/signoff",{"rev":1,"decision":"return","reviewer":"演练初审陆平",
             "note":"只有水印发票，缺少差旅报销单，退回补件。本演练前案未办理报销。"})
    assert get(before)["decisions"][-1]["decision"]=="return"
    corrected = "合成演练 · 补齐差旅报销单 · "+code
    child = send_supplement(parent,1,corrected,[claim],[original["id"]],run_id+"-child","沿用前案住宿发票，补交 636 元水印差旅报销单。")
    wait(child)
    current = "/api/cases/"+child
    task = get(current)
    print("补件",BASE+"/workpaper/"+child,flush=True)
    assert task["title"]==corrected and task["supplement_of"]["id"]==parent and {
        d["sha256"] for d in task["documents"]} == {hashlib.sha256(p.read_bytes()).hexdigest() for p in (claim,invoice)}
    saved = get(current+"/reports/1")
    graph = saved["report"]["graph"]
    assert [(m["case_id"],m["decision"]) for m in graph["prior_invoices"]]==[(parent,"return")]
    statuses = {(f["rule"],f["status"]) for f in saved["report"]["findings"]}
    assert {("T01","ok"),("T03","ok"),("I02","risk")} <= statuses
    finding = next(f for f in saved["report"]["findings"] if f["rule"]=="I02")
    if task["status"]=="ready":
        post(current+"/signoff",{"rev":1,"decision":"escalate","reviewer":"演练初审陆平",
             "note":"补交申请金额与发票相符，见前案退回记录。请独立复核同票命中。"})
    pin = get(current)["referrals"][0]
    if mode=="refer":
        return
    if pin["resolved_rev"] is None:
        post(current+"/peer-review",{"rev":1,"reviewer":"演练复核沈禾","decision":"approve","findings":[finding["id"]],
             "report_hash":pin["report_hash"],"signoff_hash":pin["signoff_hash"],
             "note":"已对照前案退回意见、沿用的原发票及补交的 636 元差旅报销单，演练仅在本案签收一次。"})
    approved = get(current+"/reports/2")
    check = approved["invoice_approval"]
    assert check["source_sha256"]==saved["sha256"] and check["source_rev"]==1 and check["signed_rev"]==2
    assert check["outcome"]=="matched" and [n["value"] for n in check["numbers"]]==[number]
    assert [m["case_id"] for m in check["matches"]]==[parent] and check["matches"][0]["decision"]=="return"
    print("复核签收",BASE+"/workpaper/"+child+"?rev=2",number,flush=True)


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id",default="synthetic-returned-invoice-approval-v1")
    options=parser.add_mutually_exclusive_group()
    options.add_argument("--run",dest="mode",action="store_const",const="approve")
    options.add_argument("--refer",dest="mode",action="store_const",const="refer")
    options.add_argument("--single-ready",dest="mode",action="store_const",const="single")
    args=parser.parse_args()
    exercise(args.run_id,args.mode)
