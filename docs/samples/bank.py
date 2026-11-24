"""Generate watermarked contract and bank-receipt specimens and optionally run two real local audits."""

import argparse
import os
from pathlib import Path
from decimal import Decimal

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from generate import ROOT, pdf
from run import BASE, submit, wait


def write_bank_pair(folder, ident, account, reference, changed=False, paid_on="2026年10月19日"):
    font_files = (os.getenv("AUDIT_CJK_FONT"),"/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                  "/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "C:/Windows/Fonts/msyh.ttc")
    source = next((Path(f) for f in font_files if f and Path(f).is_file()),None)
    if source is None:
        raise SystemExit("请通过 AUDIT_CJK_FONT 指定支持中文、可嵌入的 TrueType 字体。")
    pdfmetrics.registerFont(TTFont("BankSampleCJK",str(source)))
    folder.mkdir(exist_ok=True,parents=True)
    buyer,seller = "青岚演练商贸中心","石桥演练设备中心"
    currency = [("币种","人民币"),("金额单位","元")]
    contract = [("合同编号",ident),("采购方",buyer),("供应方",seller),
                ("约定收款账号",account),("含税总额","8,400.00"),("结算条款","一次性全额结算"),
                ("签约日期","2026年10月12日"),*currency]
    bank = [("合同编号",ident),("付款户名",buyer),("收款户名",seller),
            ("收款账号","000000000000000092" if changed else account),("付款金额","8,550.00" if changed else "8,400.00"),
            ("交易流水号",reference),("交易状态","交易成功"),("付款日期",paid_on),*currency]
    pdf(folder/"采购合同.pdf","采购合同",contract,font="BankSampleCJK")
    pdf(folder/"银行付款回单.pdf","银行付款回单",bank,font="BankSampleCJK")


def generate_bank(changed):
    title = "收款账户变更与超付" if changed else "合同与回单相符"
    folder = ROOT / (("09-" if changed else "08-")+title)
    suffix = "092" if changed else "081"
    write_bank_pair(folder, "YL-BANK-"+suffix, "000000000000000081", "YL-TRANSFER-"+suffix, changed)
    return title,folder


def check(report, changed):
    findings = report["findings"]
    accounts = next((r for r in findings if r["rule"]=="B03" and r["status"]==("risk" if changed else "ok")), None)
    amount = next((c for f in findings if f["rule"]=="B04" for c in f.get("calculations",[])), None)
    if not accounts or not amount or Decimal(amount["result"]) != (150 if changed else 0):
        raise AssertionError([(r["rule"],r["status"],r["detail"]) for r in findings if r["status"]!="ok"])
    expected = "reject" if changed else "pass"
    if report["result"]["verdict"] != expected:
        raise AssertionError(report["result"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true",help="使用真实模型并检查两套资料")
    parser.add_argument("--run-id",default="synthetic-bank-v2")
    args=parser.parse_args()
    cases=[]
    for changed in (False,True):
        title,folder=generate_bank(changed)
        if args.run:
            cid=submit("合成演练 · "+title,sorted(folder.glob("*.pdf")),args.run_id+"-"+str(int(changed)),"cn-bank-contract-payment/v1")
            cases.append((changed,cid))
            print(title,BASE+"/#case/"+cid,flush=True)
    for changed,cid in cases:
        result=wait(cid)
        check(result,changed)
        print(cid,result["result"]["verdict"],flush=True)
