"""Exercise delivery quantity amendments on watermarked contracts and acceptance originals."""

import argparse
import hashlib

from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, embedded_font, pdf
from quality_addenda import TITLE, pdf_with_note
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit
from warranty_release import FIELDS as PURCHASE_FIELDS, check_training_watermark


CASES = {
    "complete": "增购至六台并完成终验",
    "short": "增购后仍只验收原四台",
    "later": "数量协议在四台终验后生效",
    "same_day": "增购协议与终验同日",
    "quality": "增购六台齐套但柜温超限",
    "note": "六台合格结论另有欠交附注",
    "image": "终验影像另记两台待补交",
    "price": "数量协议另附价款调整条件",
    "orphan": "主合同另列六台未附变更协议",
}
COUNT_NOTE = "尚欠2台，剩余设备另行补交"
FIELDS = {**PURCHASE_FIELDS, "原交付数量":"previous_quantity", "变更后交付数量":"revised_quantity"}


def generate(seed, mode):
    code = hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    folder = ROOT/"37-补充协议交付数量"/code
    folder.mkdir(parents=True,exist_ok=True)
    records = documents(code,"complete")
    contract = dict(records["采购合同"])
    seller_date = {"later":"2026年9月22日","same_day":"2026年9月20日"}.get(mode,"2026年9月12日")
    amendment = [
        ("补充协议编号","BC-"+code),("原合同编号",contract["合同编号"]),("采购方",contract["采购方"]),
        ("供应方",contract["供应方"]),("采购标的",contract["采购标的"]),
        ("变更范围","仅变更交付数量，合同总价及其余条款不变"),("原交付数量","4台"),("变更后交付数量","6台"),
        ("变更适用时点","仅适用于本协议生效后进行的验收"),("协议生效条款","本协议自双方盖章之日起生效"),
        ("甲方盖章日期","2026年9月10日"),("乙方盖章日期",seller_date),
        ("甲方签章",contract["甲方签章"]),("乙方签章",contract["乙方签章"]),
    ]
    if mode=="price":
        amendment.append(("计价说明","增购设备的差价另行结算"))
    if mode=="orphan":
        records["采购合同"].append(("变更后交付数量","6台"))
    else:
        records[TITLE] = amendment
    actual = "4台" if mode in ("short","later","orphan") else "6台"
    acceptance = {"实际验收数量":actual,"实测结果":"柜温8℃" if mode=="quality" else "柜温3℃"}
    receipt = [(k,acceptance.get(k,v)) for k,v in records["验收报告"]]
    if mode=="note":
        receipt.append(("交付备注",COUNT_NOTE))
    records["验收报告"] = receipt
    font = embedded_font("QuantityAmendmentCJK")
    for title,rows in records.items():
        path = folder/(title+".pdf")
        if mode=="image" and title=="验收报告":
            pdf_with_note(path,title,rows,font,"交付备注："+COUNT_NOTE,spacing=27)
        else:
            pdf(path,title,rows,font=font,spacing=27)
    return folder,records


def validate(paper, mode):
    checks = paper["findings"]
    single = {f["rule"]:f for f in checks}
    inspection = single["H02"]
    change = inspection["quality_change"]
    quantity = change["quantity"]
    expected = {
        "complete":("applied",6,0,"ok"), "short":("applied",6,-2,"risk"),
        "later":("original",4,0,"ok"), "quality":("applied",6,0,"issue"),
    }
    result = (change["state"],(quantity["applicable"] or {}).get("count"),quantity["difference"],inspection["status"])
    assert result==expected.get(mode,("pending",None,None,"missing")), (mode,result,inspection["detail"])
    plan = "missing" if mode in ("price","orphan") else "ok"
    assert single["H01"]["status"]==single["H03"]["status"]==plan
    phases = [f for f in checks if f["rule"]=="H04"]
    assert [f["stage"]["share"] for f in phases]==["30","60","10"]
    dependent = {"ok":"ok","issue":"risk","risk":"risk","missing":"missing"}[inspection["status"]]
    assert [f["status"] for f in phases]==[plan,dependent,dependent]
    assert single["H05"]["status"]==("ok" if dependent=="ok" else "missing")
    assert all(ref in inspection["evidence"] for line in quantity["lines"] for ref in line["facts"])
    if mode=="quality":
        assert "超出" in inspection["detail"] and paper["result"]["verdict"]=="reject"
    if mode=="note":
        assert any(line["field"]=="quantity_note" and COUNT_NOTE in line["quote"] for line in quantity["lines"])
    if mode=="image":
        assert any(not p["text_only"] for p in quantity["pages"])


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-quantity-change-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args = parser.parse_args()
    queued = []
    for mode in args.cases:
        folder,records = generate(args.run_id,mode)
        if not args.run:
            print(folder)
            continue
        cid = submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
        queued.append((cid,mode,folder,records))
        print(mode,BASE+"/workpaper/"+cid,flush=True)
    for cid,mode,folder,records in queued:
        reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=FIELDS,
                                 document_types={TITLE:"contract_addendum"},row_spacing=27,
                                 exact_fields=("previous_quantity","revised_quantity","quantity_accepted","quantity_agreed"))
        paper = confirm_printed_records(cid,folder,records)
        paper = check_training_watermark(cid,folder,records,paper)
        validate(paper,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),paper["result"]["verdict"],flush=True)
