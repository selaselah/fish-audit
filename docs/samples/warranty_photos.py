"""Exercise a sideways work-order photograph and a two-page image-only work order on localhost."""

import argparse
import hashlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from generate import WATERMARK, embedded_font, pdf
from contract_milestones import PROFILE, normalize
from run import BASE, get, post, submit, wait
from warranty_tickets import generate

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"server"))
from documents import prepare

CASES={"photo":"横置工单照片记载待维修","scan":"两页扫描工单的采购方签认栏被遮挡"}


def raster(path):
    with pdfium.PdfDocument(path) as doc:
        page=doc[0]
        assert normalize(WATERMARK) in normalize(page.get_textpage().get_text_bounded())
        return page.render(scale=2).to_pil().convert("RGB")


def materials(seed,mode,as_of):
    folder,records,_=generate(seed+"-image","open" if mode=="photo" else "closed",as_of)
    target=folder/"影像提交"
    target.mkdir(exist_ok=True)
    ordered=folder/"质保维修工单.pdf"
    image=raster(ordered)
    if mode=="photo":
        source=target/"报修附件.jpg"
        image.transpose(Image.Transpose.ROTATE_270).save(source,format="JPEG",quality=94)
    else:
        font=embedded_font("WarrantyTicketScanCJK")
        rows=records["质保维修工单"]
        signer=next(i for i,(label,_) in enumerate(rows) if label=="采购方关闭签认")
        baseline=649-28*signer
        left=int(2*(48+stringWidth("采购方关闭签认：",font,15)))
        top=int(2*(842-baseline-18))
        mask=ImageDraw.Draw(image)
        mask.rectangle((left,top,1000,top+43),fill="#55595f")
        source=target/"售后附件扫描件.pdf"
        with tempfile.TemporaryDirectory() as tmp:
            cover=Path(tmp)/"cover.pdf"
            pdf(cover,"附件移交清单",[("附件件数","1 件"),("正文位置","第 2 页")],font=font)
            out=canvas.Canvas(str(source),pagesize=(595,842),invariant=1)
            for picture in (raster(cover),image):
                out.drawImage(ImageReader(picture),0,0,width=595,height=842)
                out.showPage()
            out.save()
        with pdfium.PdfDocument(source) as scan:
            assert len(scan)==2 and all(not p.get_textpage().get_text_bounded().strip() for p in scan)
    files=[folder/(title+".pdf") for title in records if title!="质保维修工单"]+[source]
    return files,source


def validate(cid,files,source,mode):
    api="/api/cases/"+cid
    report=wait(cid)
    case=get(api)
    assert case["title"]=="合成演练 · "+CASES[mode] and not case["decisions"]
    assert {d["name"]:d["sha256"] for d in case["documents"]}=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    if report["policy"].get("warranty_checks")=="contract-warranty-release-v3":
        post(api+"/rerun",{"rev":case["rev"]})
        report=wait(cid)
        case=get(api)
    doc=next(d for d in case["documents"] if d["name"]==source.name)
    number=1 if mode=="photo" else 2
    pages=prepare(source,2,save_images=False)
    indicated=pages[number-1]
    def check(r):
        g=r["graph"]
        for page in pages:
            node=next(n for n in g["nodes"] if n["id"]==doc["id"]+"/p"+str(page["number"]))
            assert node["sha256"]==page["sha256"] and node["layer"] in ("image","image_overlay") and not page["text"].strip()
        phase=next(f for f in r["findings"] if f["rule"]=="H04" and f.get("warranty_check"))
        bank=next(f for f in r["findings"] if f["rule"]=="H05")
        signalled=[p for p in g["warranty_sources"]["pages"] if p["doc"]==doc["id"] and p.get("image_ticket_refs")]
        assert [p["page"] for p in signalled]==[number]
        assert doc["id"]+"/p"+str(number) in phase["evidence"]
        assert phase["status"]==bank["status"]=="missing" and r["result"]["verdict"]=="review"
        assert not any(edge["type"] in ("warranty_ticket_comparison","warranty_release_basis") for edge in g["edges"])
        assert any(t["state"]=="scope" for t in phase["warranty_check"]["tickets"])
    check(report)
    expected="工单状态："+("待维修" if mode=="photo" else "已关闭")
    candidates=[f for f in report["graph"]["facts"] if f["doc"]==doc["id"] and f["page"]==number and
                f["field"]=="warranty_ticket_state" and normalize(f["quote"])==normalize(expected) and
                normalize(f["value"])==normalize(expected.split("：")[1])]
    # Only the state line of the generated watermarked page is eligible for this simulated review.
    if len(candidates)==1 and candidates[0]["status"]=="visual":
        post(api+"/attest",{"rev":case["rev"],"reviewer":"水印影像演练","decision":"confirm","facts":[candidates[0]["id"]],
                           "note":"按生成件摘要及该页图核对工单状态栏，本次只确认这处可见文字。"})
        report=wait(cid)
        check(report)
    if len(candidates)==1:
        fact=next(f for f in report["graph"]["facts"] if f["id"]==candidates[0]["id"])
        assert fact["status"]=="confirmed"
        receipt=fact["attestation"]["source_check"]
        assert receipt["original_sha256"]==doc["sha256"] and receipt["page_sha256"]==indicated["sha256"]
    print(mode,BASE+"/workpaper/"+cid+"?rev="+str(get(api)["rev"]),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-warranty-photos-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    today=datetime.now(timezone(timedelta(hours=8))).date()
    pending=[]
    for mode in args.cases:
        files,source=materials(args.run_id,mode,today)
        print(source,flush=True)
        if args.run:
            cid=submit("合成演练 · "+CASES[mode],files,f"{args.run_id}-{mode}-{today}",PROFILE)
            pending.append((cid,files,source,mode))
            print(mode,cid,flush=True)
    for job in pending:
        validate(*job)
