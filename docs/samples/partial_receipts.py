"""Exercise two watermarked receipts with a partial transaction reference through the local website."""

import argparse
import hashlib
import unicodedata
from urllib.parse import urlencode

from bank import write_bank_pair
from cross_payments import ACCOUNT, PROFILE
from generate import ROOT
from run import BASE, get, post, submit, wait


def exercise(run_id, run):
    batch = hashlib.sha256(run_id.encode()).hexdigest()[:8].upper()
    for key,label,reference,note in (("masked","流水中段遮盖","26XX0042",None),
                                     ("tail","流水尾号与同页展示说明","0042","仅显示后四位")):
        folder = ROOT / ("流水完整性-"+batch) / key
        write_bank_pair(folder,"YL-REF-"+batch+"-"+key,ACCOUNT,reference,term="分期付款",
                        payment_amount="4,200.00",reference_note=note)
        if not run:
            continue
        files = sorted(folder.glob("*.pdf"))
        title = "合成演练 · "+label+" · "+batch
        case = submit(title,files,run_id+"-"+key,PROFILE)
        paper = wait(case)
        detail = get("/api/cases/"+case)
        assert detail["title"]==title and {d["name"]:d["sha256"] for d in detail["documents"]}=={
            p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        fields = paper["graph"]["transfer_references"]["facts"]
        field = next(item for item in fields if item["value"]==reference)
        if note:
            assert any(note in row["text"] for row in field["lines"])
        checks = [f for f in paper["findings"] if f["rule"] in {"B04","B05","B06","B07","B08"}]
        assert {f["rule"] for f in checks}=={"B04","B05","B06","B07","B08"}
        assert all(f["status"]=="missing" and not f.get("calculations") for f in checks)
        window = paper["graph"]["payment_history"]["installments"]
        assert window["calculation"]["state"]=="missing" and "paid_total" not in window["calculation"]
        print(label,BASE+"/workpaper/"+case+"?"+urlencode({"rev":detail["rev"],"fact":field["fact"]}),flush=True)


def exercise_photo(run_id, run):
    import pypdfium2
    batch = hashlib.sha256(run_id.encode()).hexdigest()[:8].upper()
    folder = ROOT / ("流水照片-"+batch)
    write_bank_pair(folder,"YL-PHOTO-"+batch,ACCOUNT,"0042",term="分期付款",payment_amount="4,200.00",
                    reference_note="仅显示后四位")
    photo = folder/"银行回单照片.jpg"
    with pypdfium2.PdfDocument(folder/"银行付款回单.pdf") as pdf:
        pdf[0].render(scale=2).to_pil().convert("RGB").save(photo,quality=93,subsampling=0)
    if not run:
        return
    title = "合成演练 · 流水照片与页脚说明 · "+batch
    case = submit(title,[folder/"采购合同.pdf",photo],run_id+"-photo",PROFILE)
    base = "/api/cases/"+case
    checksum = hashlib.sha256(photo.read_bytes()).hexdigest()
    fields = (("bank_receipt","银行付款回单","银行付款回单","top"),
              ("payer","青岚演练商贸中心","付款户名：青岚演练商贸中心","top"),
              ("transfer_ref","0042","交易流水号：0042","middle"),
              ("transfer_ref_note","仅显示后四位","交易流水号说明：仅显示后四位","bottom"))
    def compact(value):
        return "".join(unicodedata.normalize("NFKC",value).split())
    for _ in range(8):
        paper = wait(case)
        detail = get(base)
        assert detail["title"]==title and detail["profile"]==PROFILE
        doc = next(d["id"] for d in detail["documents"] if d["sha256"]==checksum)
        observations = [f for f in paper["graph"]["facts"] if f["doc"]==doc and f["page"]==1]
        payload = {"rev":detail["rev"],"reviewer":"水印样本校验","note":"按本次生成的水印照片逐字核对抬头、付款户名、可见流水与展示说明。"}
        confirming = []
        for field,value,quote,region in fields:
            matches = [f for f in observations if f["field"]==field]
            if field=="transfer_ref_note" and not matches:
                matches = [f for f in observations if f["field"]=="other" and compact(f["quote"])==compact(quote)]
            assert len(matches)<=1, "样本中有多个同名候选，须逐项对照页图"
            fact = matches[0] if matches else None
            same_line = fact and compact(fact["quote"])==compact(quote)
            allowed = {compact(value),compact(quote)} if field=="transfer_ref_note" else {compact(value)}
            if not same_line or compact(fact["value"]) not in allowed:
                post(base+"/amend",{**payload,"doc":doc,"page":1,"target":fact["id"] if fact else None,
                                    "field":field,"value":value,"quote":quote,"region":region})
                break
            if fact["status"]!="confirmed":
                confirming.append(fact["id"])
            else:
                assert fact["attestation"]["source_check"]["original_sha256"]==checksum
        else:
            if confirming:
                post(base+"/attest",{**payload,"facts":confirming,"decision":"confirm"})
                continue
            ref = next(m for m in paper["graph"]["transfer_references"]["facts"] if m["value"]=="0042")
            assert ref["state"]=="partial" and any(n["status"]=="confirmed" for n in ref["notes"])
            assert [f["status"] for f in paper["findings"] if f["rule"]=="B06"]==["missing"]
            calc=paper["graph"]["payment_history"]["installments"]["calculation"]
            assert calc["state"]=="missing" and "paid_total" not in calc
            print(title,BASE+"/workpaper/"+case+"?"+urlencode({"rev":detail["rev"],"fact":ref["fact"]}),flush=True)
            return
    raise AssertionError("未能在限定轮次中核对本次水印照片的四处原文")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--photo",action="store_true",help="生成独立照片与说明，并仅按样本真值核对四处印刷字段")
    parser.add_argument("--run-id",default="synthetic-partial-receipts-v1")
    args = parser.parse_args()
    if args.photo:
        exercise_photo(args.run_id,args.run)
    else:
        exercise(args.run_id,args.run)
