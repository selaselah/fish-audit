"""Exercise two watermarked receipts with a partial transaction reference through the local website."""

import argparse
import hashlib
from urllib.parse import urlencode

from bank import write_bank_pair
from cross_payments import ACCOUNT, PROFILE
from generate import ROOT
from run import BASE, get, submit, wait


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-partial-receipts-v1")
    args = parser.parse_args()
    exercise(args.run_id,args.run)
