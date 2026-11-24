"""Exercise physical PDF pages shared by independent, plainly watermarked acceptance forms."""

import argparse
import hashlib

from reportlab.pdfgen import canvas

from batch_final import FINAL, LABELS, TITLES
from contract_milestones import PROFILE, confirm_printed_records
from final_signers import SPACING, signed_records
from generate import ROOT, draw_pdf_page, embedded_font
from quality_reinspection import reconcile_training_pages, reinspection_records, verify_report as verify_reinspection
from run import BASE, get, submit
from warranty_release import check_training_watermark


PACKET = "交付验收合订件"
CASES = {"ordered":"终验在首页的三张独立验收单", "borrowed":"同一本合订件的分批签字未出现在终验页",
         "quality":"合订终验页签齐但实测柜温超限", "duplicate":"合订件两张验收单印有同一编号",
         "continuation":"三张有编号的验收单另附一页未标所属单号的续页", "masked":"合订验收单自己的编号仅见尾号",
         "retest":"初验、整改和合格复验三种资料合订", "wrong_defect":"合订复验引用了另一项缺陷编号",
         "approval":"验收单全部签齐而合同约定的董事会批准缺件"}


def generate(seed, mode):
    code=hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    folder=ROOT/"39-同类验收单合订件"/code
    folder.mkdir(parents=True,exist_ok=True)
    if mode in ("retest","wrong_defect"):
        records=reinspection_records(code,"closed" if mode=="retest" else "mismatch")
        pages=["复验报告","整改记录单","验收报告"]
    else:
        records=signed_records(code,mode if mode in ("borrowed","quality") else "joint")
        if mode=="approval":
            records["采购合同"]=[(k,"本合同自双方盖章并经甲方董事会批准后生效" if k=="生效条款" else v)
                                 for k,v in records["采购合同"]]
        first,second="第一批验收报告","第二批验收报告"
        if mode in ("duplicate","masked"):
            reference=dict(records[first])["验收单编号"] if mode=="duplicate" else "****-"+code[-4:]
            records[second]=[(k,reference if k=="验收单编号" else v) for k,v in records[second]]
        pages=[FINAL,second,first]
        if mode=="continuation":
            extra="验收记录续页"
            pages.append(extra)
            records[extra]=[("交接说明","封条待核实，本页所属验收单号待补")]
    layout={name:[name] for name in records if name not in pages}
    layout[PACKET]=pages
    font=embedded_font("ReceiptPacketCJK")
    for filename,forms in layout.items():
        paper=canvas.Canvas(str(folder/(filename+".pdf")),pagesize=(595,842),invariant=1)
        paper.setTitle(filename)
        for form in forms:
            draw_pdf_page(paper,TITLES.get(form,form),records[form],font=font,spacing=SPACING)
            paper.showPage()
        paper.save()
    return folder,records,layout


def settle(cid,folder,records,layout):
    fields={**LABELS,"终验签认约定":"acceptance_signing_clause"}
    reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=fields,printed_titles=TITLES,
        document_types={"验收记录续页":"other"},row_spacing=SPACING,layout=layout,
        exact_fields=("acceptance_number","delivery_batch","delivered_serials","batch_receipt_refs","acceptance_signing_clause","acceptance_signer"))
    report=confirm_printed_records(cid,folder,records,layout=layout)
    return check_training_watermark(cid,folder,layout,report)


def validate(report,mode):
    graph=report["graph"]
    if mode in ("retest","wrong_defect"):
        assert graph["receipt_packet_sources"]["packets"]==[]
        verify_reinspection(report,"closed" if mode=="retest" else "mismatch")
        return
    packet,=graph["receipt_packet_sources"]["packets"]
    doc=next(d for d in graph["documents"] if d["id"]==packet["doc"])
    assert doc["name"]==PACKET+".pdf" and len(graph["documents"])==4
    checks=report["findings"]
    phases=[f for f in checks if f["rule"]=="H04"]
    inspection=next(f for f in checks if f["rule"]=="H02")
    payment=next(f for f in checks if f["rule"]=="H05")
    contract=next(f for f in checks if f["rule"]=="H01")
    assert contract["status"]==("missing" if mode=="approval" else "ok")
    assert [p["stage"]["share"] for p in phases]==["20","35","35","10"]
    assert payment["stage"]["share"]=="10"
    pages=packet["pages"]
    assert [p["page"] for p in pages]==list(range(1,1+len(pages)))
    expected_pages=7 if mode=="continuation" else 6
    assert len(report["calls"]["pages"])==expected_pages
    assert all(call["request_id"] and call["response_id"] for call in [*report["calls"]["pages"],report["calls"]["expert"]])
    accepted=inspection["batch_acceptance"]
    verdict=report["result"]["verdict"]
    if mode in ("duplicate","continuation","masked"):
        assert packet["status"]=="review" and verdict=="review"
        assert inspection["status"]==payment["status"]=="missing"
        assert [p["status"] for p in phases]==["ok","missing","missing","missing"]
        assert accepted["completion_on"] is None
        reasons={r for p in pages for r in p["reasons"]}
        expected={"duplicate":"本单编号在合订件内重复","continuation":"页内标有续页或跨页说明",
                  "masked":"本单编号不完整或字符间隔待核"}[mode]
        assert expected in reasons,(mode,reasons)
        assert not any(e["type"]=="acceptance_page_identity" for e in graph["edges"])
        return
    assert packet["status"]=="split" and all(not p["reasons"] for p in pages)
    assert len(set(p["number"] for p in pages))==3
    assert sum(e["type"]=="acceptance_page_identity" for e in graph["edges"])==6
    units=[f"unit/{doc['id']}/p{n}" for n in (3,2,1)]
    assert [b["records"] for b in accepted["batches"]]==[[units[0]],[units[1]]]
    assert accepted["separate_final"]["records"]==[units[2]]
    if mode=="approval":
        assert "董事会" in contract["detail"] and all(r["signing"]["status"]=="ok" for r in accepted["records"])
        assert [p["status"] for p in phases]==["missing"]*4 and payment["status"]=="missing"
        assert not accepted["completion_on"] and verdict=="review"
        return
    expected={"ordered":("ok","ok","ok","pass"),"borrowed":("missing","missing","missing","review"),
              "quality":("issue","risk","missing","reject")}[mode]
    assert (inspection["status"],phases[-1]["status"],payment["status"],verdict)==expected,(mode,verdict,inspection["detail"])
    assert [p["status"] for p in phases[:3]]==["ok"]*3
    final=next(r for r in accepted["records"] if r["unit"]==units[-1])
    assert final["signing"]["missing_names"]==(["陈琪"] if mode=="borrowed" else [])
    assert accepted["completion_on"]==("2026-09-25" if mode=="ordered" else None)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-receipt-packets-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    queue=[]
    for mode in args.cases:
        folder,records,layout=generate(args.run_id,mode)
        if not args.run:
            print(folder)
            continue
        cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
        print(mode,BASE+"/workpaper/"+cid,flush=True)
        queue.append((mode,cid,folder,records,layout))
    for mode,cid,folder,records,layout in queue:
        report=settle(cid,folder,records,layout)
        validate(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
