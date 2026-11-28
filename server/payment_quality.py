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


FIRST_FORMAT = "acceptance-quality-payment-v1"
BASIS_FORMAT = "acceptance-quality-payment-v2"
OPEN_FORMAT = "acceptance-quality-payment-v3"
FORMAT = "acceptance-quality-payment-v4"
OPEN_FORMATS = (OPEN_FORMAT,FORMAT)
KEY = "payment_quality_sources"
EDGE = "acceptance_reading_for_payment"
BASIS_EDGE = "measured_against_inspection_limits"
RECTS = "measurement_note_rects"
SINCE = (2026, 11, 27, 17)
BASIS_SINCE = (2026, 11, 28, 9)
OPEN_SINCE = (2026, 11, 28, 10)
PRECISION_SINCE = (2026, 11, 28, 11)
CLOSED = ("不高于","不超过","不低于","至少","至多","≤","≥")
OPEN = ("低于","小于","<","高于","大于",">")
UPPER = {"不高于","不超过","至多","≤","低于","小于","<"}
FAILURES = {"outside","excluded_boundary"}
CONTRACT = (*LINK_KEYS, "acceptance_criteria", "payment_stage", "payment_term")
RECEIPT_FIELDS = (*LINK_KEYS, "inspection_basis", "measured_result", "acceptance_scope", "acceptance_result", "accepted_on")
BANK = ("contract_id", "payer", "payee", "payment_designation", "transfer_status", "paid_on")
ROLES = {"contract": CONTRACT, "acceptance": RECEIPT_FIELDS, "bank_receipt": BANK}
# Only fold the printing conventions used in the supported field grammar. Keep digit groups intact.
PRINT = str.maketrans("０１２３４５６７８９：．－％　", "0123456789:.-% ")
def metric_pattern(operators):
    return re.compile(r"([\u4e00-\u9fff]{1,16}?) *("+"|".join(operators)+
                      r")? *(-?[0-9]{1,12}(?:\.[0-9]{1,6})?) *(°C|mm|cm|kg|MPa|kPa|%)")


METRIC = metric_pattern(CLOSED)
OPEN_METRIC = metric_pattern((*CLOSED,*OPEN))
ANGLES = str.maketrans("＜＞","<>")
QUALIFIER = re.compile(r"(?:不|不得|不宜|不应|不能|不可|不必|不要求|无需|未|应|须|应当|必须|宜|最好|建议|参考|约|原则上|尽量|禁止|严禁|并非)$")
PRECISION = re.compile(r"取整|四舍五入|修约|舍入|允许误差|允许偏差|容许误差|容许偏差|不确定度|允差|公差|容差|分辨率|±|\+/-")
MEASUREMENT = re.compile(r"测量|读数|实测|检验|仪器|检测")
MONEY_SUBJECT = r"(?:检验|检测|测量|验收|结算|付款|发票)?(?:费用|费|金额|价款|税额|单价|总价)(?:金额)?"
MONEY_LABEL = re.compile(MONEY_SUBJECT+r"(?:结算|说明|计算|规则|处理)?")
MONEY_ROUNDING = re.compile(r"(?:"+MONEY_SUBJECT+r")?(?:按人民币)?(?:四舍五入|舍入|取整|修约)(?:至|到)(?:人民币)?[元角分][。.]?")


def metric_reading(value, open_bounds):
    if not open_bounds:
        return METRIC.fullmatch(value)
    match = OPEN_METRIC.fullmatch(value.translate(ANGLES))
    if match and match[2] in OPEN and QUALIFIER.search(match[1]):
        return None
    return match


def printed(text):
    return text.translate(PRINT).replace("℃","°C").strip(" ")


def column(text):
    label, sep, value = printed(text).partition(":")
    return (label.strip(" "), value.strip(" ")) if sep else ("",label)


def sources(graph, read_text, method=FORMAT):
    kinds = graph["documents_by_kind"]
    if not kinds.get("contract") or not kinds.get("acceptance") or not any(f["field"]=="measured_result" for f in graph["facts"]):
        return {"format":method, "rows":[]}
    return {"format":method,"rows":printed_rows(graph,read_text,ROLES,precision=method in OPEN_FORMATS)}


def printed_rows(graph, read_text, roles, *, extra_labels=None, precision=False):
    from graph import LABELS
    from performance import DATE_LABELS, STAGE_PREFIX

    rows = []
    labels = {role:{label:field for field in fields for label in (*DATE_LABELS.get(field,LABELS[field]),*(extra_labels or {}).get(field,()))}
              for role,fields in roles.items()}
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
        if role not in roles or not p["native"]:
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
                rows.append({"doc":doc,"page":page,"unit":unit,"line":number,"field":field,
                             "quote":raw,"facts":refs[doc,page,number,raw]})
            if (precision and role in ("contract","acceptance") and field not in ("acceptance_criteria","inspection_basis","measured_result")
                    and PRECISION.search(raw)):
                rows.append({"doc":doc,"page":page,"unit":unit,"line":number,"field":"measurement_note",
                             "quote":raw,"facts":refs[doc,page,number,raw]})
    return rows


def witness(rows, material, field, *, clause=None, open_bounds=False):
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
    pair = material.party_rows.get(field)
    expected = [pair["model_ref"],pair["added_ref"]] if pair and f["id"]==pair["model_ref"] else [f["id"]]
    if (sorted(r["facts"]) != sorted(expected) or not loc.get("rects") or (r["doc"],r["page"],r["line"],r["quote"]) !=
            (f["doc"],f["page"],loc["number"],loc["text"])):
        return None
    if field in ("accepted_on","paid_on","repaired_on"):
        from performance import DATE_LABELS
        reading = read_date(f,DATE_LABELS[field],RECEIPT)
        return (f["id"],reading["iso"]) if reading else None
    label, body = column(r["quote"])
    quoted, copied = column(f["quote"])
    value_label, value = column(f["value"])
    if not label or not body or quoted!=label or value_label not in ("",label):
        return None
    if field in ("acceptance_criteria","inspection_basis","measured_result"):
        parsed = [metric_reading(v,open_bounds) for v in (body,copied,value)]
        if not all(parsed) or not all(m.groups()==parsed[0].groups() for m in parsed):
            return None
        body = "".join(v or "" for v in parsed[0].groups())
    elif copied!=body or value!=body:
        return None
    return f["id"], body


def readings(rows, material, fields, *, open_bounds=False):
    values = {field:witness(rows,material,field,open_bounds=open_bounds) for field in fields}
    return values if all(values.values()) else None


def native_text(graph, unit):
    owned = [p for p in graph["payment_window_sources"]["pages"] if p["unit"]==unit]
    return bool(owned) and all(p["native"] and p["text_only"] for p in owned)


def acceptance_readings(graph, h02):
    from performance import FINAL_SCOPES, Material
    rows = graph.get(KEY,{}).get("rows",[])
    kinds = graph["documents_by_kind"]
    if not rows or len(kinds.get("contract",()))!=1 or len(kinds.get("acceptance",()))!=1:
        return
    if (h02.get("quality_change") or h02.get("batch_acceptance")
            or any(kinds.get(k) for k in ("remediation","reinspection","contract_addendum"))):
        return
    contract, receipt = (Material(graph,kinds[k][0]) for k in ("contract","acceptance"))
    if not same_original(contract,receipt) or not all(native_text(graph,u) for u in (contract.unit,receipt.unit)):
        return
    open_bounds = graph[KEY]["format"] in OPEN_FORMATS
    c = readings(rows,contract,(*LINK_KEYS,"acceptance_criteria"),open_bounds=open_bounds)
    a = readings(rows,receipt,(*LINK_KEYS,"acceptance_scope","acceptance_result","inspection_basis","measured_result"),open_bounds=open_bounds)
    if not c or not a or any(c[k][1]!=a[k][1] for k in LINK_KEYS) or a["acceptance_scope"][1] not in FINAL_SCOPES:
        return
    if not all(v[0] in h02.get("evidence",()) for v in (*c.values(),*a.values())):
        return
    return contract, receipt, c, a


def judge_limit(limit, measured):
    metric, operator, bound, unit = limit.groups()
    result = {"name":metric,"operator":operator,"limit":bound,"unit":unit,"result":"incomparable"}
    if (metric,unit)==(measured[1],measured[4]):
        difference = Decimal(measured[3])-Decimal(bound) if operator in UPPER else Decimal(bound)-Decimal(measured[3])
        result["result"] = "outside" if difference>0 else "within"
        if difference>0:
            result["outside_by"] = format(difference,"f")
        elif difference==0 and operator in OPEN:
            result["result"] = "excluded_boundary"
    return result


def meaning(name,operator,bound,unit):
    return name,operator in UPPER,operator in OPEN,Decimal(bound),unit


def same_limits(limits):
    return len({meaning(v["name"],v["operator"],v["limit"],v["unit"]) for v in limits.values()})==1


def same_within(proof):
    if not proof:
        return False
    a,b = (proof["limits"][role] for role in ("contract","inspection"))
    return a["result"]==b["result"]=="within" and a["operator"] in OPEN and same_limits(proof["limits"])


def measurement_notes(ledger, units, name):
    notes = []
    for r in ledger["rows"]:
        if r["field"]!="measurement_note" or r["unit"] not in units:
            continue
        raw = r["quote"]
        if ledger["format"]==FORMAT:
            label, body = column(raw)
            if MONEY_LABEL.fullmatch(label) and MONEY_ROUNDING.fullmatch(body):
                continue
        if name in raw or MEASUREMENT.search(raw):
            notes.append({key:r[key] for key in ("doc","page","unit","line","quote")})
    return notes


def incomplete_notes(graph, finding):
    """Locate a qualified reading even when the receipt lacks the sources needed for a final comparison."""
    from performance import Material, FAILED_ACCEPTANCE
    ledger = graph.get(KEY,{})
    if (ledger.get("format")!=FORMAT or not any(r["field"]=="measurement_note" for r in ledger["rows"])
            or any(finding.get(k) for k in ("reinspection","quality_change","batch_acceptance"))):
        return []
    kinds = graph["documents_by_kind"]
    if any(len(kinds.get(k,()))!=1 for k in ("contract","acceptance")) or any(kinds.get(k) for k in ("remediation","reinspection","contract_addendum")):
        return []
    contract, receipt = (Material(graph,kinds[k][0]) for k in ("contract","acceptance"))
    if not native_text(graph,receipt.unit) or receipt.body("acceptance_result") in FAILED_ACCEPTANCE:
        return []
    value = witness(ledger["rows"],receipt,"measured_result",open_bounds=True)
    if not value or value[0] not in finding.get("evidence",()):
        return []
    measured = metric_reading(value[1],True)
    if not measured or measured[2]:
        return []
    units = [receipt.unit]
    if same_original(contract,receipt) and native_text(graph,contract.unit):
        units.append(contract.unit)
    return measurement_notes(ledger,units,measured[1])


def comparison(graph, h02):
    from performance import PASS
    method = graph.get(KEY,{}).get("format")
    if method not in (BASIS_FORMAT,*OPEN_FORMATS) or h02.get("reinspection"):
        return
    readings = acceptance_readings(graph,h02)
    if not readings:
        return
    contract, receipt, c, a = readings
    if a["acceptance_result"][1] not in PASS:
        return
    limits = [metric_reading(text,method in OPEN_FORMATS) for text in (c["acceptance_criteria"][1],a["inspection_basis"][1])]
    measured = metric_reading(a["measured_result"][1],method in OPEN_FORMATS)
    if not all(lim and lim[2] for lim in limits) or not measured or measured[2]:
        return
    if any(lim[2] in OPEN and lim[1]!=measured[1] for lim in limits):
        return
    judged = {key:judge_limit(lim,measured) for key,lim in zip(("contract","inspection"),limits)}
    if all(v["result"]=="incomparable" for v in judged.values()):
        return
    has_open = any(lim[2] in OPEN for lim in limits)
    notes = measurement_notes(graph[KEY],(contract.unit,receipt.unit),measured[1]) if method==FORMAT or has_open else []
    if not notes and not has_open and same_limits(judged):
        return
    proof = {"contract":contract.unit,"receipt":receipt.unit,"limits":judged,
             "observed":{"name":measured[1],"value":measured[3],"unit":measured[4]},
             "fields":{"acceptance_criteria":c["acceptance_criteria"][0],
                       **{k:a[k][0] for k in ("inspection_basis","measured_result","acceptance_result","acceptance_scope")}},
             "evidence":list(dict.fromkeys(v[0] for v in (*c.values(),*a.values())))}
    if notes:
        proof["reading_notes"]=notes
        proof["evidence"].extend(dict.fromkeys(f"{n['doc']}/p{n['page']}" for n in notes))
        for entry in judged.values():
            if entry["result"]!="incomparable":
                entry["result"]="reading_required"
                entry.pop("outside_by",None)
    return proof


def explain_limits(proof, *, contract=None):
    observed = proof["observed"]
    label = "终验所列读数" if proof.get("reading_notes") else "终验实测"
    parts = [f"{label}{observed['name']}{observed['value']}{observed['unit']}。"]
    for key,label in (("contract","合同约定"),("inspection","验收单所引标准")):
        entry = proof["limits"][key]
        result = {"within":"实测符合该限值","incomparable":"与实测的指标或单位无法对应",
                  "reading_required":"原始读数及判定口径待核",
                  "excluded_boundary":"实测恰等于边界，未满足该严格限值"}.get(entry["result"])
        if result is None:
            result = f"实测超出限值{entry['outside_by']}{entry['unit']}"
        parts.append(f"{label}{entry['name']}{entry['operator']}{entry['limit']}{entry['unit']}，{result}。")
    for note in proof.get("reading_notes",()):
        origin = ("合同" if note["unit"]==contract else "验收单") if contract else ""
        parts.append(f"{origin}第 {note['page']} 页第 {note['line']} 行载“{note['quote']}”。")
    return "".join(parts)


def review_acceptance(graph, h02):
    proof = comparison(graph,h02)
    if not proof:
        notes = incomplete_notes(graph,h02)
        if notes:
            h02["reading_caveats"]=notes
            h02["evidence"]=list(dict.fromkeys([*h02["evidence"],*(f"{n['doc']}/p{n['page']}" for n in notes)]))
            names = {d["id"]:d["name"] for d in graph["documents"]}
            for n in notes:
                h02["detail"] += f" 《{names[n['doc']]}》第 {n['page']} 页第 {n['line']} 行载“{n['quote']}”。"
            if h02["status"]=="ok":
                h02["status"]="missing"
        return
    receipt_result = next(f for f in graph["facts"] if f["id"]==proof["fields"]["acceptance_result"])
    met = same_within(proof)
    qualified = graph[KEY]["format"]==FORMAT and bool(proof.get("reading_notes"))
    different = not same_limits(proof["limits"])
    detail = explain_limits(proof,contract=proof["contract"] if qualified else None)
    detail += "验收结论栏记载“"+column(receipt_result["quote"])[1]+"”"+("。" if met or qualified and not different else "，请核对采用该标准的依据。")
    generic = "合同验收标准与实际检验依据需逐项对应。"
    remaining = h02["detail"].removeprefix(generic)
    if any(lim["operator"] in OPEN for lim in proof["limits"].values()):
        remaining = remaining.removeprefix("需核对标准全文、同一指标及单位的实测结果。")
    h02["detail"] = (detail+" "+remaining).strip()
    if any(lim["result"] in FAILURES for lim in proof["limits"].values()):
        h02["status"]="issue"
    elif qualified and different and h02["status"] in ("ok","missing"):
        h02["status"]="risk"
    elif h02["status"]=="ok" and not met:
        h02["status"]="missing" if proof.get("reading_notes") else "risk"
    h02["evidence"]=list(dict.fromkeys([*h02["evidence"],*proof["evidence"]]))
    h02["quality_comparison"]=proof


def records(graph, findings):
    from performance import CONDITIONS, Material, inspect_quality, matches_stage, number, ORD, stage_terms
    h02 = next((f for f in findings if f["rule"]=="H02"),{})
    signing = next((f for f in findings if f["rule"]=="H01"),{})
    plan = next((f for f in findings if f["rule"]=="H03"),{})
    paired = h02.get("quality_comparison")
    if plan.get("status")!="ok" or h02.get("reading_caveats") or same_within(paired) or not paired and h02.get("status")!="issue":
        return
    readings_for_case = acceptance_readings(graph,h02)
    if not readings_for_case:
        return
    contract, receipt, c, a = readings_for_case
    if paired:
        observation = {"comparison":{"limits":paired["limits"],"observed":paired["observed"]}}
        if paired.get("reading_notes"):
            observation["comparison"]["reading_notes"]=paired["reading_notes"]
    else:
        criterion, basis, measured = c["acceptance_criteria"][1],a["inspection_basis"][1],a["measured_result"][1]
        spec, value = LIMIT.fullmatch(criterion), METRIC.fullmatch(measured)
        if inspect_quality(criterion,basis,measured)[0]!="issue" or not spec or not value or value[2]:
            return
        margin = abs(Decimal(value[3])-Decimal(spec[3]))
        observation = {"measure":{"name":spec[1],"operator":spec[2],"limit":spec[3],"observed":value[3],"unit":spec[4],"outside_by":format(margin,"f")}}
    rows = graph[KEY]["rows"]
    accepted = witness(rows,receipt,"accepted_on")
    banks = set(graph["documents_by_kind"].get("bank_receipt",()))
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
        if paired and paired.get("reading_notes"):
            refs.extend(f"{n['doc']}/p{n['page']}" for n in paired["reading_notes"])
        shown = {"clause":term[0],"acceptance_criteria":c["acceptance_criteria"][0],
                 **{k:a[k][0] for k in ("inspection_basis","measured_result","acceptance_scope","acceptance_result")}}
        result = {"contract":contract.unit,"receipt":receipt.unit,"fields":shown,**observation,
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
            b = readings(rows,bank,BANK) if native_text(graph,unit) and bank_identity(contract,bank) else None
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
        detail = f"本期约定{f['stage']['clause']}。"
        if "comparison" in record:
            detail += explain_limits(record["comparison"],contract=record["contract"] if graph[KEY]["format"]==FORMAT else None)
        else:
            m = record["measure"]
            detail += f"终验单载{m['name']}{m['observed']}{m['unit']}，合同要求{m['operator']}{m['limit']}{m['unit']}。"
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
        if record.get("comparison",{}).get("reading_notes") and f["status"] in ("ok","missing"):
            f["status"]="missing"
        elif f["status"]!="issue":
            f["status"]="risk"
        f["payment_quality"]=record


def edges(findings):
    return [{"from":r["fields"]["measured_result"],"to":"finding/"+f["id"],"type":edge,"evidence":r["evidence"]}
            for f in findings for key,edge in (("quality_comparison",BASIS_EDGE),("payment_quality",EDGE)) if (r:=f.get(key))]


def reading_notes(findings):
    return [n for f in findings for n in (f.get("quality_comparison",{}).get("reading_notes") or f.get("reading_caveats",()))]


def verify(report, read_text, *, read_original=None, read_layout=None, signing=False):
    p, g, findings = report["policy"], report["graph"], report["findings"]
    method = p.get("payment_quality")
    revision = tuple(map(int,p.get("version","0").split(".")))
    actual = [e for e in g["edges"] if e["type"] in (EDGE,BASIS_EDGE)]
    calls = report.get("calls",{}).get("pages",[])
    if method not in OPEN_FORMATS and any(RECTS in c for c in calls):
        raise ValueError("旧版底稿含未出具的测量精度说明行框")
    if revision<SINCE:
        if method or KEY in g or "payment_quality.py" in p.get("code_sha256",{}) or actual or any("payment_quality" in f or "quality_comparison" in f or "reading_caveats" in f for f in findings):
            raise ValueError("历史底稿含未出具的验收款质量程序")
        return
    versions = ((PRECISION_SINCE,FORMAT),(OPEN_SINCE,OPEN_FORMAT),(BASIS_SINCE,BASIS_FORMAT),(SINCE,FIRST_FORMAT))
    expected_method = next(marker for since,marker in versions if revision>=since)
    if (method!=expected_method or "code_sha256" in p and "payment_quality.py" not in p["code_sha256"]
            or g.get(KEY)!=sources(g,read_text,method) or actual!=edges(findings)):
        raise ValueError("验收款所引合同限值、实测原行或图关系不符")
    comparisons = []
    partial = []
    for f in findings:
        proof = comparison(g,f) if f["rule"]=="H02" else None
        caveats = incomplete_notes(g,f) if not proof and f["rule"]=="H02" else []
        if f.get("reading_caveats")!=(caveats or None) or caveats and (
                f["status"]=="ok" or any(f"{n['doc']}/p{n['page']}" not in f["evidence"] for n in caveats)):
            raise ValueError("验收范围或结论尚待核的读数与原页精度说明不符")
        if caveats:
            partial.append(f)
        breach = proof and any(v["result"] in FAILURES for v in proof["limits"].values())
        if (f.get("quality_comparison")!=proof or breach and f["status"]!="issue" or proof and (
                not set(proof["evidence"])<=set(f["evidence"]) or f["status"]=="ok" and not same_within(proof))):
            raise ValueError("合同和验收单各自的限值、实测对照或所引原行不符")
        if proof:
            comparisons.append(proof)
        if signing and method!=FORMAT and f["rule"]=="H02":
            current_graph = {**g,KEY:sources(g,read_text,FORMAT)}
            updated = comparison(current_graph,f)
            if (updated and updated!=proof and not same_within(updated)) or (not updated and incomplete_notes(current_graph,f)):
                raise ValueError("旧版未列出合同或验收单所载限值的实测对照。请按现行程序重审后签收。")
    expected = {f["id"]:v for f,v in records(g,findings)}
    for f in findings:
        record=expected.get(f["id"])
        permitted=("risk","issue","missing") if record and record.get("comparison",{}).get("reading_notes") else ("risk","issue")
        if f.get("payment_quality")!=record or record and f["status"] not in permitted:
            raise ValueError("验收款质量发现、所据期次或付款日期不符")
    proofs = [*comparisons,*expected.values()]
    located = []
    notes = reading_notes(findings)
    if method in OPEN_FORMATS and (calls or p.get("archived_methods")):
        from contract_folios import line_numbers, verify_page_geometry
        verify_page_geometry(calls,line_numbers(notes),{},RECTS,"测量精度说明",read_layout)
        by_page = {(c["doc"],c["page"]):c for c in calls}
        nodes = {n["id"]:n for n in g["nodes"] if n["type"]=="page"}
        for note in notes:
            call=by_page[note["doc"],note["page"]]
            page=nodes[f"{note['doc']}/p{note['page']}"]
            if not call.get("response_id") or not call.get("check",{}).get("response_id") or call.get("page_sha256")!=page["sha256"]:
                raise ValueError("测量精度说明所据页图与独立核读记录不符")
            located.append({**note,"rects":call[RECTS][str(note["line"])]})
    if read_layout and (proofs or partial):
        from retest_reference import verify_positions
        verify_positions(g,[*proofs,*partial],read_layout,"合同与验收单限值对照")
    if (proofs or partial) and read_original:
        units = {u for r in proofs for u in (r["contract"],r["receipt"],r.get("payment",{}).get("bank")) if u}
        if partial:
            units.update(u for kind in ("contract","acceptance") for u in g["documents_by_kind"].get(kind,()))
        verify_units(g,units,read_original,"验收款质量凭证",extra_lines=located)


def verify_units(graph, units, read_original, label, *, extra_lines=()):
    from original_records import verify_rendered
    nodes = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    files = []
    for page in graph["payment_window_sources"]["pages"]:
        if page["unit"] in units:
            ref = f"{page['doc']}/p{page['page']}"
            node = nodes[ref]
            files.append({"doc":page["doc"],"pages":[{"ref":ref,"sha256":node["sha256"],"layer":node["layer"],
                                                     "text_only":node.get("clause_text_only") is True}]})
    verify_rendered(graph,files,read_original,label,extra_lines=extra_lines)
