"""Exercise two installments and a repeated receipt, using only this generator's watermarked files."""

import argparse
import hashlib
from urllib.parse import urlencode

from bank import write_bank_pair
from cross_payments import ACCOUNT, PROFILE
from generate import ROOT
from run import BASE, get, post, submit, wait


def exercise(run_id, run):
    code = hashlib.sha256(run_id.encode()).hexdigest()[:8].upper()
    ident = "YL-INS-"+code
    directory = ROOT / "14-跨案分期付款" / code
    first,second = directory/"首期",directory/"次期"
    for path,suffix,amount,day in ((first,"A","4,200.00","19"),(second,"B","4,350.00","22")):
        write_bank_pair(path,ident,ACCOUNT,ident+"-"+suffix,paid_on=f"2026年10月{day}日",term="分期付款",payment_amount=amount)
    if not run:
        return
    for label,source,suffix,paid,delta,expected in (
            ("首期付款",first,"first","4200.00","-4200.00","ok"),("分期累计超额",second,"second","8550.00","150.00","risk"),
            ("分期回单副本",first,"copy","4200.00","-4200.00","ok")):
        files = sorted(source.glob("*.pdf"))
        title = "合成演练 · "+label+" · "+code
        cid = submit(title,files,run_id+"-"+suffix,PROFILE)
        print(label,BASE+"/workpaper/"+cid,flush=True)
        report = wait(cid)
        detail = get("/api/cases/"+cid)
        expected_files = {f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
        assert detail["title"] == title and {d["name"]:d["sha256"] for d in detail["documents"]} == expected_files
        finding = next(f for f in report["findings"] if f["rule"]=="B08")
        window = report["graph"]["payment_history"]["installments"]
        calc = window["calculation"]
        if calc.get("state")!="calculated":
            raise AssertionError([(f["rule"],f["detail"]) for f in report["findings"] if f["status"]!="ok"])
        assert finding["status"]==expected and (calc["paid_total"],calc["contract_total"],calc["difference"])==(paid,"8400.00",delta)
        assert {p["reference"] for p in calc["payments"]} == {ident+"-A",*([ident+"-B"] if suffix=="second" else [])}
        assert sum(len(p["copies"]) for p in calc["payments"])==int(suffix=="copy")
        if suffix=="first":
            assert window["count"]==0 and all(f["status"]=="ok" for f in report["findings"] if f["rule"] in {"E01","B01","B02","B03","B05"})
            if detail["status"]=="ready":
                post("/api/cases/"+cid+"/signoff",{"rev":detail["rev"],"decision":"approve","reviewer":"合成演练验收",
                     "note":"对照本脚本生成的合同和首期成功回单，核准首期 4,200 元、约定收款账号及流水。后续分期另行核对。"})
        print(finding["status"],BASE+"/workpaper/"+cid+"?"+urlencode({"rev":detail["rev"],"finding":finding["id"]}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-installments-v1")
    args = parser.parse_args()
    exercise(args.run_id,args.run)
