"""Watermarked eight-digit invoices in two code series, with explicitly itemized travel claims."""

import argparse
import hashlib
from reportlab.pdfgen import canvas

from generate import ROOT, draw_pdf_page, embedded_font, pdf
from run import BASE, get, submit, wait


def materials(run_id):
    key = hashlib.sha256(run_id.encode()).hexdigest()
    number = "00"+str(int(key[:12],16)%1000000).zfill(6)
    codes = ("099926001011","099926002011")
    folder = ROOT/"16-八位号码与代码"/key[:8]
    folder.mkdir(parents=True,exist_ok=True)
    font = embedded_font("InvoiceSeriesCJK")
    common = [("出差人员","演练林川"),("币种","人民币"),("金额单位","元")]
    dates = [("出差开始日期","2026年10月12日"),("出差结束日期","2026年10月15日")]
    packet = folder/"两张住宿发票.pdf"
    book = canvas.Canvas(str(packet),pagesize=(595,842),invariant=1)
    book.setTitle("演练 · 同号异代码发票")
    singles=[]
    for tag,code,net,tax,total in zip(("甲","乙"),codes,("200.00","400.00"),("12.00","24.00"),("212.00","424.00")):
        fields = [("发票代码",code),("发票号码",number),*common,("费用发生日期","2026年10月13日"),
                  ("开票日期","2026年10月15日"),("不含税合计",net),("税额合计",tax),("含税总额",total)]
        inv,claim=folder/(tag+"发票.pdf"),folder/(tag+"申请.pdf")
        pdf(inv,"增值税电子普通发票",fields,font=font)
        pdf(claim,"差旅报销单",[*common,*dates,("申请报销金额",total),("随附发票代码及号码",code+" / "+number)],font=font)
        draw_pdf_page(book,"增值税电子普通发票",fields,font=font)
        book.showPage()
        singles.append([claim,inv])
    book.save()
    both=folder/"逐票列明的差旅报销单.pdf"
    pdf(both,"差旅报销单",[*common,*dates,("申请报销金额","636.00"),
        *(("随附发票代码及号码",c+" / "+number) for c in codes)],font=font)
    return number,codes,[both,packet],singles


def exercise(run_id,run):
    number,codes,pair,_ = materials(run_id)
    if not run:
        print(pair[0].parent)
        return
    title="合成演练 · 八位同号异代码双票 · "+number
    cid=submit(title,pair,run_id+"-packet","cn-travel-reimbursement/v1")
    paper=wait(cid)
    assert get("/api/cases/"+cid)["title"]==title
    assert {n["label"] for n in paper["graph"]["nodes"] if n["type"]=="invoice_identity"}=={c+" / "+number for c in codes}
    results={f["rule"]:f for f in paper["findings"]}
    assert results["I01"]["status"]=="ok"
    if paper["policy"]["version"]!="2026.11.24.6" or results["T02"]["status"]=="ok":
        assert results["T02"]["status"]=="ok"
        assert results["T03"]["status"]=="ok" and results["T03"]["calculations"][-1]["result"]=="0.00"
    else:
        assert results["T02"]["status"]==results["T03"]["status"]=="missing" and "calculations" not in results["T03"]
        assert any(g.get("field")=="claim_full_ref" for g in paper["graph"]["gaps"])
    print(BASE+"/workpaper/"+cid+"?rev="+str(get("/api/cases/"+cid)["rev"])+"&finding="+results["T03"]["id"],number,results["T03"]["status"])


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id",default="synthetic-invoice-series-v1")
    parser.add_argument("--run",action="store_true")
    args=parser.parse_args()
    exercise(args.run_id,args.run)
