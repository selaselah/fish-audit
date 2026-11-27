"""Read the scope and decision printed on a separate payment approval required by an inspection."""
from collections import defaultdict
from datetime import date
from hashlib import sha256
from pathlib import Path
import re
import approval_clock

from delegation import is_page_marker
from delivery_batches import NUM, ordinal
from payment_acceptance import column, number
from payment_quality import BANK, readings
from stage_payments import SUCCESS
from warranty_dates import DISPLAY, RECEIPT


TITLES = {"付款审批单", "对公付款审批单"}
COLUMNS = {"合同编号":"contract_id", "付款户名":"payer", "收款户名":"payee", "审批期次":"stage",
           "所据验收单号":"inspection", "审批岗位":"authority", "审批决定":"decision", "审批日期":"date"}
FIELDS = {"title", *COLUMNS.values()}
STAGE = re.compile(r"第("+NUM+r")期(预付款|验收款|质保金)")
DECISIONS = {"同意支付":"approved", "批准支付":"approved", "不同意支付":"refused", "不批准支付":"refused"}
WORDING = {
    "unresolved":"所附付款审批资料的版本、原文或适用范围待核，请核对完整审批记录。",
    "multiple":"有多份候选审批资料，请确定本笔扣款所据的签发版本。",
    "bank_scope":"所附审批单与实际扣款的逐笔对应关系待核。",
    "identity":"审批单所列合同或收付款户名与本笔回单未全部对应。",
    "other_stage":"所附审批单列的是其他期款，本期审批依据待补。",
    "other_receipt":"审批单所据验收单号与银行回单引用的单号不同，本笔审批依据待核。",
    "other_authority":"审批单所列岗位与验收原件要求的审批岗位不同，请核对实际授权。",
    "refused":"所附审批单对本期列明不同意支付，回单列交易成功。请查实际扣款时适用的审批决定。",
    "later":"审批单所列同意支付日期晚于回单付款日，请核查扣款时的审批依据。",
    "same_day":"审批与付款列在同一天，需查签批、扣款的时分及签批权限。",
    "earlier":"审批单的期款、验收单号与回单相符，所列同意支付日期在付款日前。签批人身份、权限及实际签发仍待核。",
}


def sources(graph, read_text, read_layout, *, with_time=False):
    files = {d["id"]:d for d in graph["documents"]}
    nodes = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    observed = defaultdict(list)
    for fact in graph["facts"]:
        observed[fact["doc"],fact["page"]].append(fact)
    collected, candidates = [], set()
    for place in graph.get("payment_window_sources",{}).get("pages",[]):
        doc, page = place["doc"], place["page"]
        node = nodes[f"{doc}/p{page}"]
        text = read_text(doc,page) if place["native"] else ""
        if place["native"] and (not isinstance(text,str) or sha256(text.encode()).hexdigest()!=node["text_sha256"]):
            raise ValueError("付款审批单所据打印页与归档文字摘要不符")
        lines = [(i,s) for i,s in enumerate(text.splitlines(),1) if s.strip() and not is_page_marker(s)]
        facts = observed[doc,page]
        if (any(s.strip() in TITLES for _,s in lines) or "付款审批" in Path(files[doc]["name"]).stem
                or any(f["quote"].strip() in TITLES for f in facts)):
            candidates.add(doc)
        collected.append((place,node,lines,facts))

    pages = []
    for place,node,lines,facts in collected:
        doc, page, unit = place["doc"], place["page"], place["unit"]
        if doc not in candidates:
            continue
        source = files[doc]
        complete = (source.get("ext")==".pdf" and source.get("pages")==1 and unit==doc and page==1 and place["document_kind"]=="other"
                    and place["native"] and place["text_only"] and bool(lines) and lines[0][1].strip() in TITLES
                    and not any(f["status"]=="disputed" for f in facts)
                    and not any(g["doc"]==doc and g.get("quality") in {"partial","unreadable","section_unresolved"} for g in graph.get("gaps",())))
        rects = read_layout(doc,page).get("lines",{}) if lines else {}
        rows = []
        for i,raw in lines:
            label,_ = column(raw)
            field = "title" if raw.strip() in TITLES else COLUMNS.get(label,"other")
            if with_time and label in approval_clock.SIGNED:
                field="signed_at"
            seen = [f["id"] for f in facts if (f.get("source_line") or {}).get("number")==i and f["source_line"]["text"]==raw]
            rows.append({"id":f"payment-approval/{doc}/p{page}/l{i}", "doc":doc,"page":page,"unit":unit,"line":i,
                         "field":field,"quote":raw,"rects":rects.get(str(i),[]),"facts":seen,"page_sha256":node["sha256"]})
        pages.append({"doc":doc,"page":page,"unit":unit,"complete":complete,"rows":rows})
    return pages


def printed_date(value):
    match = RECEIPT.fullmatch(value.translate(DISPLAY))
    if match:
        try:
            return date(int(match["year"]),int(match["month"] or match["nmonth"]),int(match["day"] or match["nday"])).isoformat()
        except ValueError:
            pass
    return None


def contents(page):
    rows=page["rows"]
    fields={r["field"]:r for r in rows}
    if (not page["complete"] or set(fields) not in (FIELDS,FIELDS | {"signed_at"}) or len(rows)!=len(fields)
            or not all(r["rects"] for r in rows)):
        return None
    values={k:column(r["quote"])[1] for k,r in fields.items() if k!="title"}
    phase=STAGE.fullmatch(values["stage"])
    decision=DECISIONS.get(values["decision"])
    when=printed_date(values["date"])
    if (phase and ordinal(phase[1]) and decision and when and number(values["contract_id"]) and number(values["inspection"])
            and values["authority"] in {"财务负责人","总经理","有权审批人","采购负责人"} and all(values.values())):
        return fields,values,phase,decision,when
    return None


def recognized(graph):
    from performance import Material

    pages=graph.get("inspection_use_sources",{}).get("approvals",())
    contracts=graph["documents_by_kind"].get("contract",())
    if not pages or len(contracts)!=1:
        return set()
    contract=Material(graph,contracts[0])
    rows=graph.get("retest_reference_sources",{}).get("rows") or graph.get("payment_quality_sources",{}).get("rows",[])
    if not readings(rows,contract,("contract_id","buyer","seller")):
        return set()
    expected={k:column(contract.fields[f][0]["source_line"]["text"])[1]
              for k,f in (("contract_id","contract_id"),("payer","buyer"),("payee","seller"))}
    return {p["unit"] for p in pages if (data:=contents(p)) and all(data[1][k]==v for k,v in expected.items())}


def compare(graph, finding, use, required, pages):
    from performance import Material

    rows = [r for p in pages for r in p["rows"]]
    refs = [required["id"], use["citation"], use["number_ref"], finding["stage"]["clause_ref"]]
    for p in pages:
        refs.append(f"{p['doc']}/p{p['page']}")
    for r in rows:
        refs.extend((r["id"],*r["facts"]))
    check = {"request":required["id"], "required":required["authority"], "bank":use["bank"],
             "documents":list(dict.fromkeys(p["doc"] for p in pages)), "rows":[r["id"] for r in rows],
             "evidence":list(dict.fromkeys(refs)), "state":"unresolved", "status":"missing"}
    if len(check["documents"])!=1:
        check["state"]="multiple"
        return check
    data=contents(pages[0]) if len(pages)==1 else None
    if not data:
        return check
    fields,values,phase,decision,when=data
    check.update(fields={k:r["id"] for k,r in fields.items()}, listed_on=when)
    bank = Material(graph,use["bank"])
    proof_rows = graph.get("retest_reference_sources",{}).get("rows") or graph.get("payment_quality_sources",{}).get("rows",[])
    bank_fields = readings(proof_rows,bank,BANK)
    if (set(graph["documents_by_kind"].get("bank_receipt",()))!={bank.unit} or not bank_fields
            or bank_fields["transfer_status"][1] not in SUCCESS or any(ref not in finding["evidence"] for ref,_ in bank_fields.values())):
        check["state"]="bank_scope"
        return check
    check.update(bank_fields={k:v[0] for k,v in bank_fields.items()}, paid_on=bank_fields["paid_on"][1])
    check["evidence"]=list(dict.fromkeys([*check["evidence"],*check["bank_fields"].values()]))
    stage = re.fullmatch("第("+NUM+")期",finding["stage"]["name"])
    if any(values[k]!=column(bank.fields[k][0]["source_line"]["text"])[1] for k in ("contract_id","payer","payee")):
        state = "identity"
    elif not stage or ordinal(phase[1])!=ordinal(stage[1]) or phase[2]!="验收款":
        state = "other_stage"
    elif values["inspection"]!=use["number"]:
        state = "other_receipt"
    elif values["authority"]!=required["authority"]:
        state = "other_authority"
    elif decision=="refused":
        state = "refused"
    elif when>check["paid_on"]:
        state = "later"
    elif when==check["paid_on"]:
        state = "same_day"
    else:
        state = "earlier"
    check.update(state=state,status="risk" if state in {"refused","later"} else "missing")
    clock_pages=graph["inspection_use_sources"].get("bank_clocks")
    if state=="same_day" and clock_pages is not None:
        clock=approval_clock.assess(fields.get("signed_at"),bank.unit,clock_pages,when)
        if clock:
            check["clock"]=clock
            if clock["state"]=="debit_first":
                check["status"]="risk"
            for p in clock_pages:
                if p["unit"]==bank.unit:
                    check["evidence"].append(f"{p['doc']}/p{p['page']}")
                    for row in p["rows"]:
                        check["evidence"].extend([row["id"],*row["facts"]])
            check["evidence"]=list(dict.fromkeys(check["evidence"]))
    return check
