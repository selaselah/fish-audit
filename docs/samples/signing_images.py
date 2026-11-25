"""Read a scanned signing page in its original contract, or a photograph of the entire contract."""

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

import pypdfium2 as pdfium
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from contract_milestones import PROFILE, normalize
from generate import WATERMARK, draw_pdf_page, embedded_font, pdf
from run import BASE, get, post, submit, wait
sys.path.append(str(Path(__file__).resolve().parents[2]))
from docs.samples.signing_parties import generate
from warranty_photos import prepare, raster


CASES = {
    "branch": "合同扫描用印续页另记杭州分公司",
    "aligned": "合同扫描用印续页与双方名称相符",
    "masked": "两张扫描附件中用印栏的单位名称遮挡",
    "photo": "整份采购合同照片列明分公司用印",
    "cover": "电子合同另附一页无用印栏的交接影像",
    "split": "合同双方分别回传各自的扫描用印页",
}
LABELS = {
    "采购方": "buyer", "供应方": "seller", "甲方签章": "buyer_signature", "乙方签章": "seller_signature",
    "甲方印章单位名称": "buyer_seal_name", "乙方印章单位名称": "seller_seal_name",
}


def materials(seed, mode):
    flavor = {"photo":"branch","split":"branch","cover":"aligned"}.get(mode,mode)
    root, records = generate(seed+"-"+mode, flavor)
    folder = root/"用印影像"
    folder.mkdir(exist_ok=True)
    rows = records["采购合同"]
    body = [(label,value) for label,value in rows if "印章单位名称" not in label]
    holders = [(label,value) for label,value in rows if "印章单位名称" in label]
    font = embedded_font("SigningImageCJK")
    expected = []

    def read_source(path, number, fields, title=None, title_field="contract"):
        with pdfium.PdfDocument(path) as doc:
            lines = {normalize(s) for s in doc[0].get_textpage().get_text_bounded().splitlines()}
        assert normalize(WATERMARK) in lines
        if title:
            assert normalize(title) in lines
            expected.append((number,title_field,title,title,"top"))
        for index,(label,value) in enumerate(fields):
            if label not in LABELS:
                continue
            quote=label+"："+value
            assert normalize(quote) in lines
            top=(842-649+28*index)/842
            expected.append((number,LABELS[label],value,quote,"top" if top<1/3 else "bottom" if top>=2/3 else "middle"))

    if mode=="photo":
        target=folder/"采购合同照片.jpg"
        read_source(root/"采购合同.pdf",1,rows,"采购合同")
        raster(root/"采购合同.pdf").save(target,format="JPEG",quality=94)
    else:
        target=folder/"采购合同.pdf"
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"source.pdf"
            pdf(source,"采购合同",body,font=font,spacing=28)
            read_source(source,1,body)
            out=canvas.Canvas(str(target),pagesize=(595,842),invariant=1)
            draw_pdf_page(out,"采购合同",body,font=font,spacing=28)
            out.showPage()
            if mode in ("masked","cover"):
                pdf(source,"附件交接清单",[("移交件数","1 件")],font=font)
                read_source(source,2,[],"附件交接清单","other")
                out.drawImage(ImageReader(raster(source)),0,0,width=595,height=842)
                out.showPage()
            if mode!="cover":
                sections=[holders[:1],holders[1:]] if mode=="split" else [holders]
                for number,section in enumerate(sections,3 if mode=="masked" else 2):
                    pdf(source,"合同用印记录",section,font=font,spacing=28)
                    read_source(source,number,section,"合同用印记录","other")
                    out.drawImage(ImageReader(raster(source)),0,0,width=595,height=842)
                    out.showPage()
            out.save()
    files=[target,*(root/(title+".pdf") for title in records if title!="采购合同")]
    return target,files,expected


def review(cid, mode, target, files, expected):
    api="/api/cases/"+cid
    report=wait(cid)
    case=get(api)
    assert case["title"]=="合成演练 · "+CASES[mode] and not case["decisions"]
    assert {d["name"]:d["sha256"] for d in case["documents"]}=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    doc=next(d["id"] for d in case["documents"] if d["name"]==target.name)
    pages=prepare(target,3,save_images=False)
    for p in pages:
        page=next(n for n in report["graph"]["nodes"] if n["id"]==f"{doc}/p{p['number']}")
        assert page["sha256"]==p["sha256"] and page["layer"]==p["layer"]["type"]
        if mode=="photo" or p["number"]>1:
            assert page["layer"] in ("image","image_overlay") and not p["text"].strip()

    confirm=[]
    for number,field,value,quote,region in expected:
        facts=[f for f in report["graph"]["facts"] if f["doc"]==doc and f["page"]==number]
        same=[f for f in facts if normalize(f["quote"])==normalize(quote)]
        if field=="other":
            # Only correct a misclassified document title actually printed on this training annex.
            same=[f for f in same if f["field"] in ("contract","contract_addendum") and f["status"]=="visual"]
            if not same:
                continue
        correct=[f for f in same if f["field"]==field and f["quote"]==quote and f["value"] in (value,quote) and f["status"]!="unsupported"]
        if len(same)==len(correct)==1:
            f=correct[0]
            if f["status"]!="confirmed" and (mode=="photo" or number>1 or field.endswith("_signature")):
                confirm.append(f["id"])
            continue
        substitutes=same or [f for f in facts if f["field"]==field]
        assert len(substitutes)<=1 and all(not f.get("amendment") for f in substitutes),(mode,field,substitutes)
        post(api+"/amend",{"rev":get(api)["rev"],"reviewer":"合同扫描页水印演练","doc":doc,"page":number,
             "target":substitutes[0]["id"] if substitutes else None,"field":field,"value":value,"quote":quote,"region":region,
             "note":"该引文是已核对的水印合同附件页标题，资料类别已更正。" if field=="other" else
                    "逐页对照生成件和提交件的摘要，按此水印栏的可见原文记录。"})
        report=wait(cid)
    if confirm:
        post(api+"/attest",{"rev":get(api)["rev"],"reviewer":"合同扫描页水印演练","decision":"confirm","facts":confirm,
                            "note":"对照本次水印生成页、提交原件和页图，逐项确认列出的可见签章文字。"})
        report=wait(cid)
    return report


def validate(report, mode):
    graph=report["graph"]
    assert graph["contract_effect_sources"]["format"]=="contract-effect-sources-v5"
    signed=next(f for f in report["findings"] if f["rule"]=="H01")
    parties=signed["effect_review"].get("party_seals",[])
    states={p["side"]:p["state"] for p in parties}
    expected={"branch":"different","photo":"different","split":"different","aligned":"match","masked":"partial"}
    assert states==({"buyer":expected[mode],"seller":"match"} if mode!="cover" else {}),(mode,states)
    # H01 also carries independent evidence gaps about the contract and its effect.
    assert signed["status"] in (("risk",) if mode in ("branch","photo","split") else ("missing","risk")),(mode,signed["status"],signed["detail"])
    mixed=signed["effect_review"]["mixed_pages"]
    assert [p["page"] for p in mixed]==([1] if mode=="photo" else [2,3] if mode in ("masked","split") else [2])
    rows={r["id"]:r for r in graph["contract_effect_sources"]["signing_rows"]}
    for party in parties:
        for origin in party["field_sources"]:
            assert origin["row"] in signed["evidence"] and rows[origin["row"]]["side"]==party["side"]
            if origin["kind"]=="image":
                fact=next(f for f in graph["facts"] if f["id"]==origin["fact"])
                assert origin["receipt_rev"]==fact["attestation"]["source_check"]["rev"] and rows[origin["row"]]["line"] is None
    assert all(f["status"]!="ok" for f in report["findings"] if f["rule"] in ("H04","H05"))
    assert report["result"]["verdict"]!="pass"


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-contract-signing-images-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    pending=[]
    for mode in args.cases:
        source, files, fields=materials(args.run_id,mode)
        if args.run:
            cid=submit("合成演练 · "+CASES[mode],files,args.run_id+"-"+mode,PROFILE)
            print(mode,cid,flush=True)
            pending.append((cid,mode,source,files,fields))
        else:
            print(source)
    for cid,mode,source,files,fields in pending:
        report=review(cid,mode,source,files,fields)
        validate(report,mode)
        signed=next(f for f in report["findings"] if f["rule"]=="H01")
        print(mode,BASE+"/workpaper/"+cid+"?rev="+str(get("/api/cases/"+cid)["rev"]),signed["status"],
              [(r["side"],r["state"]) for r in signed.get("effect_review",{}).get("party_seals",[])],flush=True)
