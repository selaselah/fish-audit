"""Prospective changes to the second installment in a watermarked purchase agreement."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import BUYER, ROOT, SELLER, embedded_font, pdf
from quality_addenda import FIELDS as AGREEMENT_FIELDS, TITLE
from quality_reinspection import reconcile_training_pages
from receipt_before_payment import FIELDS as RECEIPT_FIELDS
from run import BASE, get, submit


CASES = {"later":"付款后补充收票前提", "earlier":"变更已生效，实付早于收票",
         "same_day":"补充协议生效与实付同日", "unsigned":"第二期变更乙方尚待盖章"}
FIELDS = {**AGREEMENT_FIELDS, **RECEIPT_FIELDS, "原付款条款":"previous_payment_stage",
          "变更后付款条款":"revised_payment_stage"}
OLD_TERM = "第二期：最终验收合格后支付60%"
NEW_TERM = "第二期：最终验收合格且买方收到本合同对应的发票后支付60%"


def materials(seed, mode):
    digest = hashlib.sha256((seed + mode).encode()).hexdigest()
    code = digest[:8].upper()
    number = "99" + str(int(digest[8:24], 16)).zfill(20)[-18:]
    records = documents(code, "complete")
    common = records["采购合同"][:4]
    records["采购发票"] = [*common,("发票号码",number),("开票日期","2026年9月18日")]
    if mode in ("earlier","same_day"):
        records["验收报告"].extend([("签收发票号码",number),("收票日期","2026年9月22日"),("收票方签章",BUYER+"（已盖章）")])
    change = [("补充协议编号","YL-BG-"+code),("原合同编号",common[0][1]),*common[1:],
              ("变更范围","仅新增第二期验收款收票前提，其余条款不变"),
              ("原付款条款",OLD_TERM),("变更后付款条款",NEW_TERM),
              ("变更适用时点","仅适用于本协议生效后支付的第二期验收款"),
              ("协议生效条款","本协议自双方盖章之日起生效"),("甲方签章",BUYER+"（已盖章）"),
              ("甲方盖章日期","2026年9月16日")]
    if mode=="unsigned":
        change.append(("乙方签章","待盖章"))
    else:
        day={"earlier":18,"same_day":21,"later":22}[mode]
        change.extend([("乙方签章",SELLER+"（已盖章）"),("乙方盖章日期",f"2026年9月{day}日")])
    records[TITLE]=change
    folder=ROOT / "验收款条款变更" / code
    folder.mkdir(parents=True,exist_ok=True)
    font=embedded_font("ProspectivePaymentChangeCJK")
    for title,rows in records.items():
        pdf(folder/(title+".pdf"),title,rows,font=font)
    return folder,records


def check(report, mode):
    def statuses(rule):
        return [f["status"] for f in report["findings"] if f["rule"]==rule]
    phases=[f for f in report["findings"] if f["rule"]=="H04"]
    payment,=[f for f in report["findings"] if f["rule"]=="H05"]
    condition, timing, edition = {"later":("missing","ok","original"),"earlier":("ok","risk","amended"),
                                  "same_day":("ok","missing","same_day"),"unsigned":("missing","missing","pending")}[mode]
    assert statuses("H01")==statuses("H02")==statuses("H03")==["ok"], [(f['rule'],f['detail']) for f in report['findings'] if f['status']!='ok']
    assert statuses("H04")==["ok",condition,"ok"] and payment["status"]==timing
    assert phases[1]["payment_change"]["scope_clear"] and payment["payment_change"]["applies"]==edition
    assert all("payment_change" not in f for f in (phases[0],phases[2]))
    if edition=="original":
        assert "invoice_receipt" not in payment and phases[1]["invoice_receipt"]["receipt"]["status"]=="missing"


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="prospective-payment-change-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    queue=[]
    for mode in args.cases:
        folder,records=materials(args.run_id,mode)
        if args.run:
            cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
            queue.append((cid,mode,folder,records)); print(mode,BASE+"/workpaper/"+cid,flush=True)
        else:
            print(folder)
    for cid,mode,folder,records in queue:
        reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=FIELDS,
                                 document_types={TITLE:"contract_addendum","采购发票":"invoice"})
        report=confirm_printed_records(cid,folder,records)
        check(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
