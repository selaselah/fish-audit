"""Identify the inspection actually named on an acceptance installment's bank receipt."""
from datetime import date
import re
import approval_clock

from acceptance_payments import same_original
from payment_acceptance import FIELD, GRAPH_KEY, LEVEL, column, number
from payment_quality import BANK, printed_rows, readings, witness
from reinspection import CLOSED, LINK_KEYS, SIGNED_FAILURE
from warranty_terms import bank_identity

FIRST_FORMAT = "reinspection-receipt-reference-v1"
FORMAT = "reinspection-receipt-reference-v2"
KEY = "retest_reference_sources"
EDGE = "receipt_names_inspection"
SINCE = (2026,11,27,18)
SCHEDULE_SINCE = (2026,11,28,7)
INITIAL = (*LINK_KEYS,"acceptance_number","defect_number","accepted_on","acceptance_result","acceptance_scope")
REPAIR = (*LINK_KEYS,"original_acceptance","repair_number","defect_number","repaired_on")
FINAL = (*INITIAL,"original_acceptance","repair_number","defect_closure")
ROLES = {"contract":(*LINK_KEYS,"payment_stage","payment_term"),"bank_receipt":(*BANK,FIELD),"remediation":REPAIR,
         "acceptance":FINAL,"reinspection":FINAL}
IDS = {"acceptance_number","original_acceptance","repair_number","defect_number"}
STEPS = (("original",INITIAL),("repair",REPAIR),("final",FINAL))


def sources(graph,read_text,method=FORMAT):
    from graph import LABELS
    from installment_counts import schedule_page
    related = graph.get(GRAPH_KEY,{}).get("rows",[])
    kinds = graph["documents_by_kind"]
    chain = kinds.get("remediation") or kinds.get("reinspection") or any(f["field"]=="original_acceptance" for f in graph["facts"])
    active = chain and any(r["role"]=="bank_receipt" for r in related)
    rows = printed_rows(graph,read_text,ROLES,extra_labels=LABELS) if active else []
    ledger = {"format":method,"rows":rows}
    if method == FORMAT and rows and (page := schedule_page(graph, read_text, rows)):
        ledger["schedule_page"] = page
    return ledger


def clean(graph, unit):
    pages=[p for p in graph["payment_window_sources"]["pages"] if p["unit"]==unit]
    return bool(pages) and all(p["native"] and p["text_only"] for p in pages)


def literal_code(material, field, pair):
    # Preserve the filed identifier's case, punctuation and digit groups on all three readings.
    if not pair or not number(pair[1]):
        return False
    f=material.fields[field][0]
    return all(column(raw)[1]==pair[1] for raw in (f["source_line"]["text"],f["quote"])) and f["value"] in (pair[1],f["quote"])


def register(graph,h02,contract,rows):
    from performance import FINAL_SCOPES, Material

    steps=h02["reinspection"]["steps"]
    units={s["role"]:s["unit"] for s in steps}
    if len(steps)!=3 or units.keys()!={"original","repair","final"} or len(set(units.values()))!=3:
        return None
    kinds=graph["documents_by_kind"]
    if (set(kinds.get("acceptance",()))|set(kinds.get("reinspection",()))!={units["original"],units["final"]} or
            set(kinds.get("remediation",()))!={units["repair"]} or not all(u in h02["scope"] for u in units.values())):
        return None
    facts={}
    for role,fields in STEPS:
        unit=units[role];m=Material(graph,unit)
        if not clean(graph,unit) or not same_original(contract,m) or m.quality_holds:
            return None
        values=readings(rows,m,fields)
        if not values or not all(literal_code(m,k,values[k]) for k in IDS.intersection(fields)):
            return None
        reported=next(s for s in steps if s["role"]==role)
        when=values["repaired_on" if role=="repair" else "accepted_on"][1]
        if when!=reported["date"] or not all(v[0] in h02["evidence"] for v in values.values()):
            return None
        facts[role]=values
    old,fix,final=(facts[k] for k in ("original","repair","final"))
    if (not old["accepted_on"][1]<=fix["repaired_on"][1]<=final["accepted_on"][1] or
            old["acceptance_number"][1]==final["acceptance_number"][1] or
            not old["acceptance_number"][1]==fix["original_acceptance"][1]==final["original_acceptance"][1] or
            fix["repair_number"][1]!=final["repair_number"][1] or
            not old["defect_number"][1]==fix["defect_number"][1]==final["defect_number"][1] or
            final["acceptance_scope"][1] not in FINAL_SCOPES):
        return None
    return units,facts


def records(graph,findings):
    from installment_counts import pending_schedule
    from performance import CONDITIONS, Material, ORD, PASS, matches_stage, number as ordinal_number, stage_terms

    rows=graph.get(KEY,{}).get("rows")
    h02=next((f for f in findings if f["rule"]=="H02"),{})
    if not rows or not h02.get("reinspection") or h02.get("batch_acceptance"):
        return
    kinds=graph["documents_by_kind"]
    scope=h02.get("approval_change_scope",{})
    if len(kinds.get("contract",()))!=1 or kinds.get("contract_addendum") and (
            graph.get("inspection_use_sources",{}).get("format")!="cited-inspection-payment-use-v8" or kinds["contract_addendum"]!=[scope.get("unit")]):
        return
    contract=Material(graph,kinds["contract"][0])
    bank_units=set(kinds.get("bank_receipt",()))
    ledger=graph[GRAPH_KEY]
    reg=register(graph,h02,contract,rows)
    plan=next((f for f in findings if f["rule"]=="H03"),{})
    method = graph[KEY]["format"]
    partial = None
    if method == FORMAT and reg and graph[KEY].get("schedule_page") == contract.unit + "/p1":
        partial = pending_schedule(graph,contract,plan,findings,rows)
    contract_ids=readings(rows,contract,LINK_KEYS)
    for f in findings:
        stage=f.get("stage")
        if (f["rule"]!="H05" or not stage or f.get("execution_basis") or f.get("payment_change") or stage.get("batch_index")
                or stage_terms(stage["clause"])[2] not in CONDITIONS["acceptance"]):
            continue
        matched=bank_units.intersection(f["scope"])
        if len(matched)!=1:continue
        unit,=matched
        originals=[r for r in ledger["rows"] if r["unit"]==unit and r["role"]=="bank_receipt"]
        if not originals:continue
        citations,timing=approval_clock.split_receipt_notes(graph,unit,originals)
        if not citations:continue
        bank=Material(graph,unit)
        fields={"clause":stage["clause_ref"]}
        refs=[stage["clause_ref"]]
        for row in originals:
            refs.extend([row["id"],f"{row['doc']}/p{row['page']}",*row["facts"]])
        check={"format":method,"bank":unit,"state":"unresolved","status":"missing","fields":fields,
               "citations":[r["id"] for r in citations],"evidence":refs}
        if timing:
            check["timing_notes"]=timing
            refs.extend(pair["event"] for pair in timing)
        clause=None
        for k in ("payment_stage","payment_term"):
            if any(fact["id"]==stage["clause_ref"] for fact in contract.fields[k]):
                clause=witness(rows,contract,k,clause=stage["clause_ref"])
        b=readings(rows,bank,(*BANK,FIELD))
        labels=re.fullmatch("第("+ORD+")期",stage["name"])
        receipt_pages=[p for p in ledger["pages"] if p["unit"]==unit]
        citation=witness(rows,bank,FIELD)
        if citation and literal_code(bank,FIELD,citation):
            fields["citation"]=citation[0]
            check["number"]=citation[1]
        eligible_plan = plan.get("status") == "ok" or partial and stage["clause_ref"] in partial["clauses"]
        if (not reg or not contract_ids or not eligible_plan or stage["clause_ref"] not in plan["evidence"] or
                not clause or clause[1]!=stage["clause"] or not clean(graph,contract.unit) or not clean(graph,unit)
                or not b or not bank_identity(contract,bank) or "citation" not in fields or
                not receipt_pages or any(p["ambiguous"] for p in receipt_pages) or
                len(citations)!=1 or citations[0]["kind"]!="citation" or citations[0]["disputed"] or
                citations[0]["facts"]!=[fields["citation"]] or not matches_stage(b["payment_designation"][1],
                {"label":stage["name"],"index":ordinal_number(labels[1]) if labels else None})):
            check["evidence"]=list(dict.fromkeys(refs))
            yield f,check
            continue
        units,proofs=reg
        check["units"]=units
        if partial:
            check["schedule_review"] = partial
            refs.extend([partial["header"], *partial["clauses"], contract.unit + "/p1"])
        refs.extend(v[0] for v in contract_ids.values())
        refs.extend(v[0] for v in b.values())
        fields.update({k:b[k][0] for k in ("payment_designation","transfer_status","paid_on")})
        for role,data in proofs.items():
            refs.extend(v[0] for v in data.values())
            fields.update({role+"_"+k:v[0] for k,v in data.items() if k not in LINK_KEYS})
        old,final=proofs["original"],proofs["final"]
        code=check["number"]
        role=next((k for k in ("original","final") if code==proofs[k]["acceptance_number"][1]),"unlocated")
        paid=b["paid_on"][1];end=final["accepted_on"][1];days=(date.fromisoformat(paid)-date.fromisoformat(end)).days
        check.update(state=role,paid_on=paid,final_on=end,original_number=old["acceptance_number"][1],
                     final_number=final["acceptance_number"][1],original_result=old["acceptance_result"][1],final_result=final["acceptance_result"][1],
                     final_closure=final["defect_closure"][1],evidence=list(dict.fromkeys(refs)))
        if role=="final":
            check["days_from_final"]=days
        failure = check["final_result"] in SIGNED_FAILURE or check["final_closure"] in {"未关闭","待关闭","未完成","未结清"}
        if role=="original" and check["original_result"] in SIGNED_FAILURE or role=="final" and (days<0 or failure):
            check["status"]="risk"
        elif not partial and role=="final" and days>0 and final["acceptance_result"][1] in PASS and final["defect_closure"][1] in CLOSED:
            check["status"]="ok"
        yield f,check


def explanation(check):
    state=check["state"]
    if state=="unresolved":
        return "回单引用了验收资料，需核对其完整单号、合同归属以及初验、整改和复验之间的对应关系。"
    if state=="unlocated":
        return f"回单引用的 {check['number']} 与已核初验单 {check['original_number']}、复验单 {check['final_number']} 均不相符，请补取付款所据凭证。"
    if state=="original":
        return (f"回单引用初验单 {check['number']}，该单结论列「{check['original_result']}」。"
                f"整改后的复验单编号为 {check['final_number']}，请核实支付验收款所据的合格终验和审批记录。")
    wording=f"回单引用复验单 {check['number']}，该单结论列「{check['final_result']}」，缺陷关闭栏列「{check['final_closure']}」。"
    days=check["days_from_final"]
    if not days:return wording+"两单所列日期相同，需查签批与付款的当日先后。"
    return wording+f"回单付款日 {check['paid_on']} {'早于' if days<0 else '晚于'}该复验单所列日 {check['final_on']}，相隔 {abs(days)} 天。"


def apply(graph,findings):
    for f,c in records(graph,findings):
        f["retest_reference"]=c
        detail = explanation(c)
        if schedule := c.get("schedule_review"):
            detail += (f" 合同列明 {schedule['declared']} 期，原页逐项列出 {schedule['listed']} 期，"
                       f"比例合计 {schedule['share_total']}%。完整付款安排仍待核。")
        if c["status"]!="ok" and f["status"]=="ok":f["detail"]=detail
        else:f["detail"]+=" "+detail
        if LEVEL[c["status"]]>LEVEL[f["status"]]:f["status"]=c["status"]
        f["evidence"]=list(dict.fromkeys([*f["evidence"],*c["evidence"]]))
        f["scope"]=list(dict.fromkeys([*f["scope"],*c.get("units",{}).values()]))


def edges(findings):
    return [{"type":EDGE,"from":r["fields"]["citation"],"to":r["fields"][r["state"]+"_acceptance_number"],"evidence":r["evidence"]}
            for f in findings if (r:=f.get("retest_reference")) and r["state"] in ("original","final")]


def verify_positions(graph, checks, read_layout):
    cited = {ref for check in checks for ref in check["evidence"]}
    if not cited:
        return
    locations = {}
    for fact in graph["facts"]:
        line = fact.get("source_line")
        if fact["id"] in cited and line and line["rects"]:
            locations.setdefault((fact["doc"], fact["page"]), []).append(line)
    pages = {n["id"]: n for n in graph["nodes"] if n["type"] == "page"}
    for (doc, page), lines in locations.items():
        issued = pages[f"{doc}/p{page}"]
        current = read_layout(doc, page)
        if (not isinstance(current, dict) or current.get("type") != issued["layer"]
                or (current.get("clause_text_only") is True) != (issued.get("clause_text_only") is True)
                or not isinstance(current.get("lines"), dict)
                or any(current["lines"].get(str(line["number"])) != line["rects"] for line in lines)):
            raise ValueError(f"回单所据初验与复验的引文位置与底稿不符（{doc} 第 {page} 页）")


def guard_prior_signoff(report, read_text):
    from performance import FORMAT as PERFORMANCE, compute

    graph, findings = report["graph"], report["findings"]
    ledger = graph.get(KEY, {})
    if (ledger.get("format") != FIRST_FORMAT or report["policy"].get("performance_checks") != PERFORMANCE
            or not any(f["rule"] == "H03" and f["status"] == "missing" for f in findings)
            or not any(f.get("retest_reference", {}).get("state") == "unresolved" for f in findings)):
        return
    revised = compute({**graph, KEY: sources(graph, read_text)})
    for f in revised:
        ref = f.get("retest_reference", {})
        if ref.get("schedule_review") and (ref["status"] == "risk" or f.get("inspection_use", {}).get("status") == "risk"):
            raise ValueError("分期安排待核，本笔回单所引的验收凭证出现旧版未列的付款风险，请重审后签收。")


def verify(report,read_text,*,read_original=None,read_layout=None):
    graph,p,findings=report["graph"],report["policy"],report["findings"]
    actual=[e for e in graph["edges"] if e["type"]==EDGE]
    revision=tuple(map(int,p.get("version","0").split(".")))
    if revision < SINCE:
        if KEY in graph or p.get("retest_reference") or "retest_reference.py" in p.get("code_sha256",{}) or actual or any("retest_reference" in f for f in findings):
            raise ValueError("历史底稿含未出具的复验回单引用判断")
        return
    method = FORMAT if revision >= SCHEDULE_SINCE else FIRST_FORMAT
    if (p.get("retest_reference")!=method or "code_sha256" in p and "retest_reference.py" not in p["code_sha256"] or
            graph.get(KEY)!=sources(graph,read_text,method) or actual!=edges(findings)):
        raise ValueError("复验回单引用所据原行、方法或图关系不符")
    expected={f["id"]:c for f,c in records(graph,findings)}
    for f in findings:
        c=expected.get(f["id"])
        if (f.get("retest_reference")!=c or c and (f.get("payment_acceptance") or LEVEL[f["status"]]<LEVEL[c["status"]]
                or not set(c["evidence"]).issubset(f["evidence"]))):
            raise ValueError("回单所据初验、复验或日期与本期发现不符")
    if read_layout:
        verify_positions(graph, expected.values(), read_layout)
    if read_original and expected:
        from payment_quality import verify_units
        units={u for c in expected.values() for u in (c["bank"],*c.get("units",{}).values())}
        verify_units(graph,units|set(graph["documents_by_kind"]["contract"]),read_original,"回单所据初验与复验")
