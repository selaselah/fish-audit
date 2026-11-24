"""Two watermarked travel claims with the same invoice, ready before either one is signed."""

import argparse
import hashlib
import json
from urllib.error import HTTPError

from generate import ROOT, embedded_font, pdf
from run import BASE, get, post, submit, wait


def materials(run_id):
    code = hashlib.sha256(run_id.encode()).hexdigest()[:8].upper()
    folder = ROOT/"15-同票并发签收"/code
    folder.mkdir(parents=True,exist_ok=True)
    font = embedded_font("TravelSampleCJK")
    shared = [("出差人员","演练林川"),("币种","人民币"),("金额单位","元")]
    number = "YL-LV-"+code
    claim,invoice = folder/"报销申请.pdf",folder/"住宿发票.pdf"
    pdf(claim,"差旅报销单",[*shared,("出差开始日期","2026年10月12日"),("出差结束日期","2026年10月15日"),
                          ("申请报销金额","636.00"),("随附发票号码",number)],font=font)
    pdf(invoice,"住宿服务发票",[*shared,("发票号码",number),("费用发生日期","2026年10月13日"),("开票日期","2026年10月15日"),
                             ("不含税合计","600.00"),("税额合计","36.00"),("含税总额","636.00")],font=font)
    return code,number,[claim,invoice]


def exercise(run_id,mode):
    code,number,files = materials(run_id)
    if not mode:
        print(files[0].parent)
        return
    ids = []
    hashes = {hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    for name in ("甲","乙"):
        title = "合成演练 · 同票签收"+name+" · "+code
        cid = submit(title,files,run_id+"-"+("a" if name=="甲" else "b"),"cn-travel-reimbursement/v1")
        ids.append(cid)
        print(name,BASE+"/workpaper/"+cid,flush=True)
    for cid in ids:
        wait(cid)
        case = get("/api/cases/"+cid)
        assert case["title"].startswith("合成演练 · 同票签收") and {d["sha256"] for d in case["documents"]}==hashes
        paper = get("/api/cases/"+cid+"/reports/1")["report"]
        assert any(f["field"]=="invoice_id" and f["value"]==number and f["status"]=="anchored" for f in paper["graph"]["facts"])
        assert {(f["rule"],f["status"]) for f in paper["findings"]} >= {("I02","ok"),("T03","ok")}
    a,b = ids
    first,second = "/api/cases/"+a,"/api/cases/"+b
    original = get(second+"/reports/1")
    if get(first)["status"]=="ready":
        assert get(first+"/reports/1")["report"]["result"]["verdict"]=="pass"
        post(first+"/signoff",{"rev":1,"reviewer":"合成演练审计员甲","decision":"approve","note":"已核水印报销单与 636 元住宿发票。"})
    assert get(first)["decisions"][0]["decision"]=="approve"
    if get(second)["rev"]==1:
        try:
            post(second+"/signoff",{"rev":1,"reviewer":"合成演练审计员乙","decision":"approve","note":"检查旧版结论签收是否被拦截。"})
        except HTTPError as error:
            assert error.code==409
            change = json.load(error)["invoice_history"]
            assert change["count"]==1 and change["changes"][0]["current"]["case_id"]==a
        else:
            raise AssertionError("旧版签收应被阻止")
        assert get(second)["decisions"]==[] and get(second)["status"]=="ready"
        if mode=="pause":
            print("乙案 R1 等待浏览器核对最新签收。",flush=True)
            return
        post(second+"/rerun",{"rev":1})
        wait(b)
    revised = get(second+"/reports/2")["report"]
    risk = next(f for f in revised["findings"] if f["rule"]=="I02" and f["status"]=="risk")
    assert revised["graph"]["prior_invoices"][0]["case_id"]==a and get(second+"/reports/1")["sha256"]==original["sha256"]
    print("同票人工校验",BASE+"/workpaper/"+b+"?rev=2&finding="+risk["id"])


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id",default="synthetic-concurrent-invoice-v2")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--run",action="store_const",dest="mode",const="run")
    modes.add_argument("--pause-after-first",action="store_const",dest="mode",const="pause")
    args = parser.parse_args()
    exercise(args.run_id,args.mode)
