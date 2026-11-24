"""Watermarked eight-digit invoices in two code series, with explicitly itemized travel claims."""

import argparse
import hashlib
import json
from urllib.error import HTTPError
from reportlab.pdfgen import canvas

from generate import ROOT, draw_pdf_page, embedded_font, pdf, scan
from run import BASE, get, post, submit, wait


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


def cross_case(run_id):
    run_id += "-cross"
    number,codes,_,singles = materials(run_id)
    ids=[]
    names=("甲","乙","甲票副本")
    for tag,files in zip(names,[*singles,singles[0]]):
        title="合成演练 · 跨案同号异代码 · "+tag+" · "+number
        cid=submit(title,files,run_id+"-"+str(len(ids)),"cn-travel-reimbursement/v1")
        case=get("/api/cases/"+cid)
        assert case["title"]==title and {f["sha256"] for f in case["documents"]}=={hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        ids.append(cid)
    for cid in ids:
        wait(cid)
        r1=get("/api/cases/"+cid+"/reports/1")["report"]
        assert r1["policy"]["invoice_lookup"]=="signed-invoice-identity-v1" and r1["graph"]["prior_invoices"]==[]
        assert r1["result"]["verdict"]=="pass", [(f["rule"],f["status"]) for f in r1["findings"] if f["status"]!="ok"]
    for i in (0,1):
        base="/api/cases/"+ids[i]
        if get(base)["status"]=="ready":
            post(base+"/signoff",{"rev":1,"decision":"approve","reviewer":"演练审计员"+names[i],
                 "note":"已核水印资料，同页代码 "+codes[i]+"，号码 "+number+"，金额与本笔演练申请一致。"})
        checked=get(base+"/reports/1")["invoice_approval"]
        assert checked["outcome"]=="no_match" and checked["matches"]==[] and checked["numbers"][0]["code"]==codes[i]
        assert [(r["case_id"],r["comparison"]) for r in checked["screened"]]==([(ids[0],"different")] if i else [])
    base="/api/cases/"+ids[2]
    if get(base)["rev"]==1:
        try:
            post(base+"/signoff",{"rev":1,"decision":"approve","reviewer":"演练复查员","note":"验证重复申请在签收时能否发现前案。"})
        except HTTPError as error:
            assert error.code==409
            changes=json.load(error)["invoice_history"]["changes"]
            assert [r["current"]["case_id"] for r in changes]==[ids[0]]
        else:
            raise AssertionError("同代码同号码的副本通过了过期的签收检查")
        assert get(base)["decisions"]==[]
        post(base+"/rerun",{"rev":1})
        wait(ids[2])
    paper=get(base+"/reports/2")["report"]
    finding=next(f for f in paper["findings"] if f["rule"]=="I02")
    assert finding["status"]=="risk" and paper["result"]["verdict"]=="review"
    assert {r["case_id"]:r["comparison"] for r in paper["graph"]["prior_invoices"]}=={ids[0]:"same",ids[1]:"different"}
    assert all(r["code_evidence"][0]["id"] in finding["evidence"] for r in paper["graph"]["prior_invoices"])
    assert get(base)["decisions"]==[]
    print("同号异代码签收",BASE+"/workpaper/"+ids[1]+"?rev=1")
    print("相同组合待核",BASE+"/workpaper/"+ids[2]+"?rev=2&finding="+finding["id"])


def confirm_marked_photo(cid,source,number):
    base="/api/cases/"+cid
    case=get(base)
    assert case["title"].startswith("合成演练 · 遮盖票号照片 · ")
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    doc=next(d["id"] for d in case["documents"] if d["sha256"]==sha)
    fields={"invoice":("住宿服务发票","住宿服务发票"),"invoice_id":(number,"发票号码："+number)}
    for _ in range(4):
        rev=get(base)["rev"]
        paper=get(base+"/reports/"+str(rev))["report"]
        raw=[f for f in paper["graph"]["facts"] if f["doc"]==doc]
        action={"rev":rev,"reviewer":"演练核图许澄","note":"对照脚本生成的水印照片核对抬头及可见字符，星号原样保留。"}
        confirming=[]
        for field,(value,quote) in fields.items():
            entries=[f for f in raw if f["field"]==field]
            assert len(entries)<=1
            if not entries or entries[0]["value"]!=value or entries[0]["quote"].replace(":", "：")!=quote:
                post(base+"/amend",{**action,"doc":doc,"page":1,"target":entries[0]["id"] if entries else None,
                                    "field":field,"value":value,"quote":quote,"region":"top"})
                break
            if entries[0]["status"]!="confirmed":
                confirming.append(entries[0]["id"])
            else:
                assert entries[0]["attestation"]["source_check"]["original_sha256"]==sha
        else:
            if not confirming:
                return paper
            post(base+"/attest",{**action,"facts":confirming,"decision":"confirm"})
        wait(cid)
    raise AssertionError("未取得水印照片上两项可见引文的确认")


def masked_case(run_id,photo=False):
    run_id += "-mask-photo" if photo else "-mask"
    number,_,_,singles=materials(run_id)
    folder=singles[0][0].parent
    masked="26****90"+number
    font=embedded_font("InvoiceSeriesCJK")
    shared=[("出差人员","演练林川"),("币种","人民币"),("金额单位","元")]
    claim,invoice=folder/"遮盖票号的报销申请.pdf",folder/"遮盖号码的发票.pdf"
    pdf(claim,"差旅报销单",[*shared,("出差开始日期","2026年10月12日"),("出差结束日期","2026年10月15日"),
                        ("申请报销金额","636.00"),("随附发票号码",masked)],font=font)
    amounts=[("费用发生日期","2026年10月13日"),("含税总额","636.00")]
    if photo:
        invoice=folder/"号码有遮盖的水印照片.jpg"
        scan(invoice,"住宿服务发票",[("发票号码",masked),*shared,*amounts])
    else:
        pdf(invoice,"住宿服务发票",[*shared,("发票号码",masked),*amounts],font=font)
    title="合成演练 · "+("遮盖票号照片" if photo else "遮盖票号的费用申请")+" · "+number
    cid=submit(title,[claim,invoice],run_id,"cn-travel-reimbursement/v1")
    print(BASE+"/workpaper/"+cid,flush=True)
    paper=wait(cid)
    if photo:
        paper=confirm_marked_photo(cid,invoice,masked)
    fields=[f for f in paper["graph"]["facts"] if f["field"] in {"claim_ref","invoice_id"}]
    assert len(fields)==2 and all(f["value"]==masked and f["status"] in {"anchored","confirmed"} for f in fields)
    assert "number_masks" in paper["graph"],"请在支持遮盖号码核对的版本复算此案"
    checks={f["rule"]:f for f in paper["findings"]}
    assert all(checks[key]["status"]=="missing" for key in ("I01","I02","T02","T03"))
    assert paper["result"]["verdict"]=="review" and "calculations" not in checks["T03"]
    assert {f["id"] for f in fields}<=set(checks["T02"]["evidence"])
    if not photo:
        assert {f["id"] for f in fields}<=set(checks["T03"]["evidence"])
    print(masked,paper["result"]["verdict"],flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id",default="synthetic-invoice-series-v1")
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument("--run",action="store_true")
    modes.add_argument("--cross",action="store_true",help="签收两组同号异代码水印资料，并检查第三份同票副本")
    modes.add_argument("--masked",action="store_true",help="生成申请与附件均列相同遮盖票号的合成案例")
    modes.add_argument("--masked-photo",action="store_true",help="仅确认水印照片的可见抬头和带遮盖位的号码")
    args=parser.parse_args()
    if args.masked or args.masked_photo:
        masked_case(args.run_id,args.masked_photo)
    elif args.cross:
        cross_case(args.run_id)
    else:
        exercise(args.run_id,args.run)
