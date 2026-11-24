"""Exercise signed repair, reinspection, and payment timing with watermarked synthetic documents."""

import argparse
import hashlib
from collections import Counter
import pypdfium2 as pdfium

from contract_milestones import PROFILE, confirm_printed_records, documents, normalize
from generate import ROOT, embedded_font, pdf
from run import BASE, get, post, submit, wait


CASES = {"closed":"整改复验后支付第二期","early":"整改期间提前支付验收款","mismatch":"复验缺陷号与原件不符",
         "partial":"整改三份记录仅列同一缺陷尾号","noted":"复验报告单独注明仅列缺陷尾号",
         "short":"完整缺陷编号恰为四位"}
DEFECT = "柜温控制探头失准"
TITLES = {"复验报告":"reinspection","整改记录单":"remediation","验收报告":"acceptance","质保期满确认单":"warranty",
          "采购合同":"contract","银行付款回单":"bank_receipt"}
LABELS = {"验收单编号":"acceptance_number","复验单编号":"acceptance_number","缺陷编号":"defect_number",
          "原验收单编号":"original_acceptance","整改记录编号":"repair_number","整改对象":"repair_subject","复验对象":"repair_subject",
          "实际整改措施":"repair_action","整改状态":"repair_result","整改完成日期":"repaired_on","整改签认":"repair_signer",
          "复验日期":"accepted_on","复验范围":"acceptance_scope","复验结论":"acceptance_result","复验签认":"acceptance_signer",
          "缺陷关闭结论":"defect_closure","验收签认":"acceptance_signer","检验依据":"inspection_basis","实测结果":"measured_result",
          "款项用途":"payment_designation","甲方签章":"buyer_signature","乙方签章":"seller_signature",
          "合同编号":"contract_id","采购方":"buyer","供应方":"seller","采购标的":"subject","验收范围":"acceptance_scope",
          "验收结论":"acceptance_result","验收日期":"accepted_on","实际验收数量":"quantity_accepted","遗留事项":"acceptance_exception",
          "质保期满确认":"warranty_release"}


def materials(run_id,mode):
    code=hashlib.sha256((run_id+"-"+mode).encode()).hexdigest()[:8].upper()
    folder=ROOT/"25-整改复验"/code
    folder.mkdir(parents=True,exist_ok=True)
    records=documents(code,"complete")
    template=records["验收报告"]
    original="YS-"+code
    repair="ZG-"+code
    defect = {"partial":"尾号0042", "noted":"0042", "short":"0042"}.get(mode, "QX-"+code)
    initial={"验收日期":"2026年9月10日","验收结论":"不合格","实测结果":"柜温8℃","遗留事项":DEFECT}
    records["验收报告"]=[(label,initial.get(label,value)) for label,value in template]+[("验收单编号",original),("缺陷编号",defect)]
    links=[("原验收单编号",original),("整改记录编号",repair),("缺陷编号",defect)]
    records["整改记录单"]=[*template[:4],*links,("整改对象",DEFECT),("实际整改措施","已更换并校准控制探头"),
                        ("整改状态","已完成"),("整改完成日期","2026年9月16日"),("整改签认","演练林岚（已签字）")]
    labels={"验收日期":"复验日期","验收范围":"复验范围","验收结论":"复验结论","验收签认":"复验签认"}
    records["复验报告"]=[(labels.get(label,label),value) for label,value in template]
    records["复验报告"] += [("复验单编号","FY-"+code),("原验收单编号",original),("整改记录编号",repair),
                          ("缺陷编号",defect+"2" if mode=="mismatch" else defect),("复验对象",DEFECT),("缺陷关闭结论","已关闭")]
    if mode == "noted":
        records["复验报告"].append(("缺陷编号展示说明", "本单仅列尾号"))
    if mode=="early":
        records["银行付款回单"]=[(label,"2026年9月18日" if label=="付款日期" else value) for label,value in records["银行付款回单"]]
    font=embedded_font("QualityReinspectionCJK")
    for title,rows in records.items():
        pdf(folder/(title+".pdf"),title,rows,font=font)
    return folder,records


def verify_report(report, mode):
    by_rule={f["rule"]:f for f in report["findings"]}
    check=by_rule["H02"]
    expected={"closed":("closed","ok","ok","pass"), "short":("closed","ok","ok","pass"), "early":("closed","ok","risk","review")}.get(
        mode, ("open","issue","missing","reject"))
    actual=check["reinspection"]["state"],check["status"],by_rule["H05"]["status"],report["result"]["verdict"]
    assert actual==expected, (actual,expected,[(f["rule"],f["detail"]) for f in report["findings"] if f["status"]!="ok"])
    assert [s["date"] for s in check["reinspection"]["steps"]]==["2026-09-10","2026-09-16","2026-09-20"]
    assert all(s["evidence"] and set(s["evidence"])<=set(check["evidence"]) for s in check["reinspection"]["steps"])
    assert any(s["status"]==("risk" if expected[0]=="open" else "ok") for s in report["findings"]
               if s["rule"]=="H04" and s["stage"]["share"]=="60")
    if mode in ("partial", "noted"):
        holds = report["graph"]["quality_references"]["holds"]
        assert len(holds) == (3 if mode=="partial" else 1), holds
        assert all(h["field"]=="defect_number" and h["fact"] in check["evidence"] for h in holds)
        assert all(any(e["type"]=="incomplete_defect_number" and e["to"]==h["fact"]
                       for e in report["graph"]["edges"]) for h in holds)
        assert "完整编号" in check["detail"]
        if mode=="noted":
            assert holds[0]["lines"][0]["quote"]=="缺陷编号展示说明：本单仅列尾号"
    if mode=="short":
        assert report["graph"]["quality_references"]["holds"]==[]


def reconcile_training_pages(cid,folder,records,*,case_titles=None,field_labels=None,document_types=None):
    path="/api/cases/"+cid
    detail=get(path)
    expected={title+".pdf":hashlib.sha256((folder/(title+".pdf")).read_bytes()).hexdigest() for title in records}
    allowed = {"合成演练 · "+name for name in (case_titles or CASES.values())}
    if detail["title"] not in allowed or {d["name"]:d["sha256"] for d in detail["documents"]}!=expected:
        raise ValueError("案例名称或原件摘要与本次水印演练不符")
    fields = {**LABELS, **(field_labels or {})}
    types = {**TITLES, **(document_types or {})}
    docs={d["name"]:d["id"] for d in detail["documents"]}
    report=wait(cid)
    for title,rows in records.items():
        source=folder/(title+".pdf")
        with pdfium.PdfDocument(source) as pdf:
            assert len(pdf)==1
            printed=pdf[0].get_textpage().get_text_bounded()
        ordered_lines=[normalize(line) for line in printed.splitlines()]
        source_lines=set(ordered_lines)
        targets=[]
        for index,(label,value) in enumerate(rows):
            if label in fields:
                top=(842-649+34*index)/842
                region="top" if top<1/3 else "bottom" if top>=2/3 else "middle"
                targets.append((fields[label],value,label+"："+value,region))
        targets.append((types[title],title,title,"top"))
        counts=Counter(f for f,_,_,_ in targets)
        printed_phases={normalize(line) for field,_,line,_ in targets if field=="payment_stage"}
        for field,value,line,region in targets:
            assert normalize(line) in source_lines
            graph=report["graph"]
            doc=docs[source.name]
            facts=[f for f in graph["facts"] if f["doc"]==doc and f["page"]==1]
            same=[f for f in facts if normalize(f["quote"])==normalize(line)]
            correct=any(f["field"]==field and f["status"] in ("anchored","confirmed") for f in same)
            wrong=[f for f in same if f["field"]!=field and f["status"]=="visual" and not f.get("amendment")]
            if field=="payment_stage" and ordered_lines.count(normalize(line))==1:
                merged=normalize(line)
                for following in ordered_lines[ordered_lines.index(merged)+1:]:
                    if following not in printed_phases:
                        break
                    merged+=following
                    wrong.extend(f for f in facts if f["field"]==field and f["status"] in ("visual","unsupported")
                                 and not f.get("amendment") and not f.get("source_line") and normalize(f["quote"])==merged)
            if correct and not wrong:
                continue
            if not wrong:
                wrong=[f for f in facts if f["field"]==field and f["status"] in ("unsupported","visual") and
                       (normalize(f["quote"])==normalize(line) or (counts[field]==1 and not f.get("source_line")))]
            gap=any(g["doc"]==doc and normalize(g.get("quote",""))==normalize(line) for g in graph["gaps"])
            if len(wrong)>1 or not (wrong or gap):
                continue
            target=wrong[0] if wrong else None
            assert not target or not target.get("amendment")
            post(path+"/amend",{"rev":get(path)["rev"],"reviewer":"水印复验演练","doc":doc,"page":1,
                                "target":target["id"] if target else None,"field":field,"value":value,"quote":line,
                                "region":region,
                                "note":"经原件摘要及生成件原页核对，按水印资料印刷的整行补正字段类别或抄录。保留初次识别记录。"})
            report=wait(cid)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-quality-reinspection-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=["closed","early","mismatch"])
    args=parser.parse_args()
    queue=[]
    for mode in args.cases:
        folder,records=materials(args.run_id,mode)
        if not args.run:
            print(folder)
            continue
        cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
        print(mode,BASE+"/workpaper/"+cid,flush=True)
        queue.append((mode,cid,folder,records))
    for mode,cid,folder,records in queue:
        reconcile_training_pages(cid,folder,records)
        report=confirm_printed_records(cid,folder,records)
        verify_report(report,mode)
        print(mode,report["result"]["verdict"],flush=True)
