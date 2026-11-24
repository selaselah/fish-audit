"""Confirm the printed invoice number on a marked training photo and inspect its source check."""

import argparse
import hashlib
from urllib.parse import urlencode

from generate import ROOT, scan
from run import BASE, get, post, submit, wait


def exercise(run_id, run):
    code = hashlib.sha256(run_id.encode()).hexdigest()[:8].upper()
    number = "YL-PH-"+code
    folder = ROOT / "13-照片票号核图存证" / code
    folder.mkdir(parents=True,exist_ok=True)
    photo = folder/"水印票据照片.jpg"
    scan(photo,"采购发票",[("发票号码",number),("合同编号","YL-C-"+code),("采购方","青岚演练商贸中心"),
                         ("供应方","石桥演练设备中心"),("含税总额","11,300.00"),("币种","人民币"),("金额单位","元")])
    if not run:
        return
    title = "合成演练 · 照片票号核图存证 · "+code
    cid = submit(title,[photo],run_id)
    base = "/api/cases/"+cid
    print(BASE+"/workpaper/"+cid,flush=True)
    wait(cid)
    detail = get(base)
    sha = hashlib.sha256(photo.read_bytes()).hexdigest()
    assert detail["title"] == title and len(detail["documents"]) == 1 and detail["documents"][0]["sha256"] == sha
    source = get(base+"/reports/1")
    candidates = [f for f in source["report"]["graph"]["facts"] if f["field"] == "invoice_id"]
    assert len(candidates) <= 1
    if detail["rev"] == 1:
        note = "仅核对本脚本生成的带水印照片，确认清晰可见的发票号码。"
        payload = {"rev":1,"reviewer":"演练核图许澄","note":note}
        if candidates and candidates[0]["value"] == number and number in candidates[0]["quote"]:
            post(base+"/attest",{**payload,"facts":[candidates[0]["id"]],"decision":"confirm"})
        else:
            post(base+"/amend",{**payload,"doc":"d01","page":1,"target":candidates[0]["id"] if candidates else None,
                                "field":"invoice_id","value":number,"quote":"发票号码："+number,"region":"top"})
        wait(cid)
    result = get(base+"/reports/2")["report"]
    verified = next(f for f in result["graph"]["facts"] if f["field"]=="invoice_id" and f["value"]==number)
    receipt = verified["attestation"]["source_check"]
    assert verified["status"] == "confirmed" and receipt["report_hash"] == source["sha256"]
    assert receipt["original_sha256"] == sha and receipt["page_sha256"] == verified["page_sha256"]
    assert result["result"]["verdict"] == "review" and all(f["status"] != "confirmed" for f in result["graph"]["facts"] if f["field"]=="total")
    print(receipt["operation"],number,BASE+"/workpaper/"+cid+"?"+urlencode({"rev":2,"fact":verified["id"]}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-photo-check-v1")
    args = parser.parse_args()
    exercise(args.run_id,args.run)
