"""Exercise quality amendments and payment riders on watermarked procurement documents."""

import argparse
import hashlib
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import BUYER, SELLER, ROOT, draw_pdf_page, embedded_font, pdf
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit


TITLE = "采购合同补充协议"
CASES = {"stricter":"终验仍用旧标准且实测超限", "met":"按已生效的新标准完成终验",
         "later":"放宽标准的补充协议在终验后生效", "rider":"补充协议页末另设付款前提",
         "image_rider":"补充协议附有影像付款条件"}
FIELDS = {"补充协议编号":"addendum_number","原合同编号":"base_contract_ref","变更范围":"change_scope",
          "原验收标准":"previous_criterion","变更后验收标准":"revised_criterion","变更适用时点":"change_timing",
          "协议生效条款":"change_effect_clause","甲方盖章日期":"buyer_sealed_on","乙方盖章日期":"seller_sealed_on",
          "签约日期":"signed_on","实际生效日期":"effect_on","生效条款":"effect_clause","约定交付数量":"quantity_agreed",
          "约定验收标准":"acceptance_criteria","付款条款":"payment_term","第一期":"payment_stage","第二期":"payment_stage",
          "第三期":"payment_stage","交易状态":"transfer_status","付款日期":"paid_on","含税总额":"total"}


def pdf_with_note(path,title,rows,font,note,*,spacing=34,note_y=125):
    page=canvas.Canvas(str(path),pagesize=(595,842),invariant=1)
    page.setTitle(title)
    draw_pdf_page(page,title,rows,font=font,spacing=spacing)
    image=Image.new("RGB",(945,98),"white")
    draw=ImageDraw.Draw(image)
    draw.rectangle((2,2,942,95),outline="#4d4d4d",width=2)
    draw.text((14,25),note,fill="#232323",font=ImageFont.truetype(pdfmetrics.getFont(font).face.filename,39))
    page.drawImage(ImageReader(image),48,note_y,width=435,height=45)
    page.save()


def agreement_rows(code, base, revision, seller_day):
    return [("补充协议编号","BC-"+code),("原合同编号",base["合同编号"]),("采购方",BUYER),("供应方",SELLER),
               ("采购标的",base["采购标的"]),("变更范围","仅变更验收标准，其余条款不变"),("原验收标准",base["约定验收标准"]),
               ("变更后验收标准",revision),("变更适用时点","仅适用于本协议生效后进行的验收"),
               ("协议生效条款","本协议自双方盖章之日起生效"),("甲方盖章日期","2026年9月10日"),
               ("乙方盖章日期",seller_day),
               ("甲方签章",base["甲方签章"]),("乙方签章",base["乙方签章"])]


def generate(seed, mode):
    code = hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    folder = ROOT/"27-合同变更与终验"/code
    folder.mkdir(parents=True,exist_ok=True)
    records = documents(code,"complete")
    base = dict(records["采购合同"])
    revision = "柜温不高于8℃" if mode=="later" else "柜温不高于2℃"
    changed = agreement_rows(code,base,revision,"2026年9月22日" if mode=="later" else "2026年9月12日")
    if mode=="rider":
        changed.append(("备注","第二期付款前另须提交银行保函"))
    records[TITLE] = changed
    receipt = {"实测结果":{"met":"柜温1℃","later":"柜温6℃"}.get(mode,"柜温3℃"),
               "检验依据":revision if mode in ("met","later") else base["约定验收标准"]}
    records["验收报告"] = [(k,receipt.get(k,v)) for k,v in records["验收报告"]]
    font = embedded_font("ContractChangeCJK")
    for title,rows in records.items():
        path=folder/(title+".pdf")
        if title==TITLE and mode=="image_rider":
            pdf_with_note(path,title,rows,font,"附注：第二期付款前须取得履约保函")
        else:
            pdf(path,title,rows,font=font)
    return folder,records


def check(paper, mode):
    findings = paper["findings"]
    def status(rule):
        return [f["status"] for f in findings if f["rule"]==rule]
    h02, = [f for f in findings if f["rule"]=="H02"]
    entry = h02["quality_change"]
    expected = {"stricter":("applied","issue",["ok","risk","risk"],"missing","reject"),
                "met":("applied","ok",["ok"]*3,"ok","pass"),
                "later":("original","issue",["ok","risk","risk"],"missing","reject"),
                "rider":("pending","missing",["missing"]*3,"missing","review"),
                "image_rider":("pending","missing",["missing"]*3,"missing","review")}
    actual = (entry["state"],h02["status"],status("H04"),status("H05")[0],paper["result"]["verdict"])
    assert actual==expected[mode], (actual,[(f["rule"],f["status"],f["detail"]) for f in findings if f["status"]!="ok"])
    assert status("H01")==status("H03")==(["missing"] if mode in ("rider","image_rider") else ["ok"])
    assert all(ref in h02["evidence"] for ref in entry["evidence"])
    page, = paper["graph"]["quality_addenda"]["pages"]
    assert page["text_only"]==(mode!="image_rider") and page["native"]
    assert [l["quote"] for l in page["uncovered"]]==(["备注：第二期付款前另须提交银行保函"] if mode=="rider" else [])
    assert entry["accepted_on"]=="2026-09-20"
    assert entry["effective_on"]=={"rider":None,"image_rider":None,"later":"2026-09-22"}.get(mode,"2026-09-12")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-quality-change-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    queue=[]
    for mode in args.cases:
        folder,records=generate(args.run_id,mode)
        if not args.run:
            print(folder)
            continue
        cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
        queue.append((cid,mode,folder,records))
        print(mode,BASE+"/workpaper/"+cid,flush=True)
    for cid,mode,folder,records in queue:
        reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=FIELDS,document_types={TITLE:"contract_addendum"})
        report=confirm_printed_records(cid,folder,records)
        check(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
