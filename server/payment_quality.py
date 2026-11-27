"""Trace an acceptance installment to the contractual limit, filed readings and a particular transfer."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from hashlib import sha256
import re

from acceptance_payments import same_original
from contract_changes import LIMIT
from reinspection import LINK_KEYS
from warranty_dates import RECEIPT, read_date
from warranty_terms import bank_identity


FORMAT = "acceptance-quality-payment-v1"
KEY = "payment_quality_sources"
EDGE = "acceptance_reading_for_payment"
SINCE = (2026, 11, 27, 17)
CONTRACT = (*LINK_KEYS, "acceptance_criteria", "payment_stage", "payment_term")
RECEIPT_FIELDS = (*LINK_KEYS, "inspection_basis", "measured_result", "acceptance_scope", "acceptance_result", "accepted_on")
BANK = ("contract_id", "payer", "payee", "payment_designation", "transfer_status", "paid_on")
ROLES = {"contract": CONTRACT, "acceptance": RECEIPT_FIELDS, "bank_receipt": BANK}
# Only fold the printing conventions used in the supported field grammar. Keep digit groups intact.
PRINT = str.maketrans("０１２３４５６７８９：．－％　", "0123456789:.-% ")
METRIC = re.compile(r"([\u4e00-\u9fff]{1,16}?) *(不高于|不超过|不低于|至少|至多|≤|≥)? *(-?[0-9]{1,12}(?:\.[0-9]{1,6})?) *(°C|mm|cm|kg|MPa|kPa|%)")


def printed(text):
    return text.translate(PRINT).replace("℃","°C").strip(" ")


def column(text):
    label, sep, value = printed(text).partition(":")
    return (label.strip(" "), value.strip(" ")) if sep else ("",label)


def sources(graph, read_text):
    from graph import LABELS
    from performance import DATE_LABELS, STAGE_PREFIX

    ledger = {"format":FORMAT, "rows":[]}
    kinds = graph["documents_by_kind"]
    if not kinds.get("contract") or not kinds.get("acceptance") or not any(f["field"]=="measured_result" for f in graph["facts"]):
        return ledger
    labels = {role:{label:field for field in fields for label in DATE_LABELS.get(field,LABELS[field])}
              for role,fields in ROLES.items()}
    nodes = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    files = {d["id"]:d["sha256"] for d in graph["documents"]}
    refs = defaultdict(list)
    for f in graph["facts"]:
        loc = f.get("source_line") or {}
        page = nodes.get(f"{f['doc']}/p{f['page']}",{})
        if loc.get("rects") and f.get("source_sha256")==files.get(f["doc"]) and f.get("page_sha256")==page.get("sha256"):
            refs[f["doc"], f["page"], loc["number"], loc["text"]].append(f["id"])
    for p in graph.get("payment_window_sources",{}).get("pages",[]):
        doc, page, role, unit = p["doc"], p["page"], p["document_kind"], p["unit"]
        if role not in ROLES or not p["native"]:
            continue
        text = read_text(doc,page)
        if not isinstance(text,str) or sha256(text.encode()).hexdigest()!=nodes[f"{doc}/p{page}"]["text_sha256"]:
            raise ValueError("验收款核对所据原页文字与留存摘要不符")
        for number, raw in enumerate(text.splitlines(),1):
            label, _ = column(raw)
            field = labels[role].get(label)
            if role=="contract" and STAGE_PREFIX.match(printed(raw)):
                field = "payment_stage"
            if field:
                ledger["rows"].append({"doc":doc,"page":page,"unit":unit,"line":number,"field":field,
                                       "quote":raw,"facts":refs[doc,page,number,raw]})
    return ledger


def witness(rows, material, field, *, clause=None):
    facts = material.fields[field]
    selected = [r for r in rows if r["unit"]==material.unit and r["field"]==field]
    if clause:
        # Other installments have different headings. A repeated heading precludes assigning this clause.
        facts = [f for f in facts if f["id"]==clause]
        title = column(facts[0]["quote"])[0] if len(facts)==1 else ""
        selected = [r for r in selected if column(r["quote"])[0]==title]
    if material.incomplete(field) or len(facts)!=1 or len(selected)!=1:
        return None
    f, r = facts[0], selected[0]
    loc = f.get("source_line") or {}
    if (r["facts"] != [f["id"]] or not loc.get("rects") or (r["doc"],r["page"],r["line"],r["quote"]) !=
            (f["doc"],f["page"],loc["number"],loc["text"])):
        return None
    if field in ("accepted_on","paid_on"):
        from performance import DATE_LABELS
        reading = read_date(f,DATE_LABELS[field],RECEIPT)
        return (f["id"],reading["iso"]) if reading else None
    label, body = column(r["quote"])
    quoted, copied = column(f["quote"])
    value_label, value = column(f["value"])
    if not label or not body or quoted!=label or value_label not in ("",label):
        return None
    if field in ("acceptance_criteria","inspection_basis","measured_result"):
        parsed = [METRIC.fullmatch(v) for v in (body,copied,value)]
        if not all(parsed) or not all(m.groups()==parsed[0].groups() for m in parsed):
            return None
        body = "".join(v or "" for v in parsed[0].groups())
    elif copied!=body or value!=body:
        return None
    return f["id"], body


def readings(rows, material, fields):
    values = {field:witness(rows,material,field) for field in fields}
    return values if all(values.values()) else None


def records(graph, findings):
    from performance import CONDITIONS, FINAL_SCOPES, Material, inspect_quality, matches_stage, number, ORD, stage_terms

    rows = graph.get(KEY,{}).get("rows",[])
    kinds = graph["documents_by_kind"]
    if not rows or len(kinds.get("contract",()))!=1 or len(kinds.get("acceptance",()))!=1:
        return
    h02 = next((f for f in findings if f["rule"]=="H02"),{})
    signing = next((f for f in findings if f["rule"]=="H01"),{})
    plan = next((f for f in findings if f["rule"]=="H03"),{})
    if (h02.get("status")!="issue" or plan.get("status")!="ok" or h02.get("quality_change") or h02.get("batch_acceptance")
            or any(kinds.get(k) for k in ("remediation","reinspection","contract_addendum"))):
        return
    contract, receipt = (Material(graph,kinds[k][0]) for k in ("contract","acceptance"))
    if not same_original(contract,receipt):
        return
    pages = graph["payment_window_sources"]["pages"]
    def clean(unit):
        owned = [p for p in pages if p["unit"]==unit]
        return bool(owned) and all(p["native"] and p["text_only"] for p in owned)
    if not clean(contract.unit) or not clean(receipt.unit):
        return
    c = readings(rows,contract,(*LINK_KEYS,"acceptance_criteria"))
    a = readings(rows,receipt,(*LINK_KEYS,"acceptance_scope","acceptance_result","inspection_basis","measured_result"))
    if not c or not a or any(c[k][1]!=a[k][1] for k in LINK_KEYS) or a["acceptance_scope"][1] not in FINAL_SCOPES:
        return
    criterion, basis, measured = c["acceptance_criteria"][1],a["inspection_basis"][1],a["measured_result"][1]
    if inspect_quality(criterion,basis,measured)[0]!="issue":
        return
    spec, value = LIMIT.fullmatch(criterion), METRIC.fullmatch(measured)
    if not spec or not value or value[2] or not all(v[0] in h02["evidence"] for v in (*c.values(),*a.values())):
        return
    margin = abs(Decimal(value[3])-Decimal(spec[3]))
    measure = {"name":spec[1],"operator":spec[2],"limit":spec[3],"observed":value[3],"unit":spec[4],"outside_by":format(margin,"f")}
    accepted = witness(rows,receipt,"accepted_on")
    banks = set(kinds.get("bank_receipt",()))
    for f in findings:
        stage = f.get("stage")
        if f["rule"] not in ("H04","H05") or not stage or f.get("execution_basis") or f.get("payment_change"):
            continue
        if not {contract.unit,receipt.unit}.issubset(f["scope"]):
            continue
        clause = stage["clause_ref"]
        fields = [k for k in ("payment_stage","payment_term") if any(r["id"]==clause for r in contract.fields[k])]
        term = witness(rows,contract,fields[0],clause=clause) if len(fields)==1 else None
        if not term or stage["clause"]!=term[1] or stage_terms(term[1])[2] not in CONDITIONS["acceptance"]:
            continue
        refs = [term[0],*[v[0] for v in c.values()],*[v[0] for v in a.values()]]
        shown = {"clause":term[0],"acceptance_criteria":c["acceptance_criteria"][0],
                 **{k:a[k][0] for k in ("inspection_basis","measured_result","acceptance_scope","acceptance_result")}}
        result = {"contract":contract.unit,"receipt":receipt.unit,"fields":shown,"measure":measure,
                  "accepted_on":accepted[1] if accepted else None}
        if contract.unit in signing.get("scope",()) and signing["status"] in ("risk","missing","issue"):
            result["contract_check"] = signing["status"]
        if accepted:
            shown["accepted_on"]=accepted[0]
            refs.append(accepted[0])
        if f["rule"]=="H05":
            matched = banks.intersection(f["scope"])
            if len(matched)!=1 or not accepted or f.get("payment_acceptance"):
                continue
            unit, = matched
            bank = Material(graph,unit)
            b = readings(rows,bank,BANK) if clean(unit) and bank_identity(contract,bank) else None
            label = stage["name"]
            ordinal = re.fullmatch("第("+ORD+")期",label)
            if (not b or not matches_stage(b["payment_designation"][1],{"label":label,"index":number(ordinal[1]) if ordinal else None})
                    or any(b[bank_key][1]!=c[key][1] for bank_key,key in (("payer","buyer"),("payee","seller"),("contract_id","contract_id")))):
                continue
            paid = b["paid_on"][1]
            result["payment"] = {"bank":unit,"paid_on":paid,"days":(date.fromisoformat(paid)-date.fromisoformat(accepted[1])).days}
            shown.update({k:b[k][0] for k in ("payment_designation","transfer_status","paid_on")})
            refs.extend(v[0] for v in b.values())
        if not all(ref in f["evidence"] for ref in refs):
            continue
        result["evidence"] = list(dict.fromkeys(refs))
        yield f, result


def apply(graph, findings):
    for f, record in records(graph,findings):
        m = record["measure"]
        detail = (f"本期约定{f['stage']['clause']}。终验单载{m['name']}{m['observed']}{m['unit']}，"
                  f"合同要求{m['operator']}{m['limit']}{m['unit']}。")
        if transfer := record.get("payment"):
            days = transfer["days"]
            if days:
                detail += f"回单列示日{transfer['paid_on']}{'早于' if days<0 else '晚于'}该验收单所列日{record['accepted_on']}，相隔{abs(days)}天。"
            else:
                detail += "回单与该验收单所列日期相同，审批及付款的当日先后待核。"
            detail += "请核对付款时所据的合格终验、复验或另行审批记录。"
            if record.get("contract_check"):
                detail += "合同签署及生效依据亦待核实。"
        else:
            detail += "请查合格终验或复验依据。"
        if f["status"]=="ok" or f["detail"] in ("付款对应本期，现有材料尚不足以证实付款日已满足全部前提。","现有验收资料不足以支持本期付款。"):
            f["detail"]=detail
        else:
            f["detail"]+=" "+detail
        if f["status"]!="issue":
            f["status"]="risk"
        f["payment_quality"]=record


def edges(findings):
    return [{"from":r["fields"]["measured_result"],"to":"finding/"+f["id"],"type":EDGE,"evidence":r["evidence"]}
            for f in findings if (r:=f.get("payment_quality"))]


def verify(report, read_text, *, read_original=None):
    p, g, findings = report["policy"], report["graph"], report["findings"]
    method = p.get("payment_quality")
    current = tuple(map(int,p.get("version","0").split(".")))>=SINCE
    actual = [e for e in g["edges"] if e["type"]==EDGE]
    if not current:
        if method or KEY in g or "payment_quality.py" in p.get("code_sha256",{}) or actual or any("payment_quality" in f for f in findings):
            raise ValueError("历史底稿含未出具的验收款质量程序")
        return
    if (method!=FORMAT or "code_sha256" in p and "payment_quality.py" not in p["code_sha256"]
            or g.get(KEY)!=sources(g,read_text) or actual!=edges(findings)):
        raise ValueError("验收款所引合同限值、实测原行或图关系不符")
    expected = {f["id"]:v for f,v in records(g,findings)}
    if any(f.get("payment_quality")!=expected.get(f["id"]) or f["id"] in expected and f["status"] not in ("risk","issue") for f in findings):
        raise ValueError("验收款质量发现、所据期次或付款日期不符")
    if expected and read_original:
        from original_records import verify_rendered
        units = {u for r in expected.values() for u in (r["contract"],r["receipt"],r.get("payment",{}).get("bank")) if u}
        nodes = {n["id"]:n for n in g["nodes"] if n["type"]=="page"}
        files = []
        for page in g["payment_window_sources"]["pages"]:
            if page["unit"] in units:
                ref = f"{page['doc']}/p{page['page']}"
                node = nodes[ref]
                files.append({"doc":page["doc"],"pages":[{"ref":ref,"sha256":node["sha256"],"layer":node["layer"],
                                                        "text_only":node.get("clause_text_only") is True}]})
        verify_rendered(g,files,read_original,"验收款质量凭证")
