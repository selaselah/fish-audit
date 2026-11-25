"""Review a written mandate for a named party signing one identified procurement contract."""

import hashlib
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal

from calculations import AMOUNT, normalized
from performance_versions import NATIVE_FORMATS
from quality_references import incomplete_number


LEGACY_FORMAT = "written-contract-mandate-v1"
NAME_FORMAT = "written-contract-mandate-v2"
NATIVE_NAME_FORMAT = "written-contract-mandate-v3"
FORMAT = "written-contract-mandate-v4"
TERMS_SINCE = "2026.11.25.22"
TITLES = ("授权委托书", "签约授权委托书", "合同签署授权委托书", "采购合同授权委托书")
LABELS = {
    "buyer_agent_signature": ("甲方代理人签字", "甲方授权代理人签字", "采购方委托代理人签字"),
    "seller_agent_signature": ("乙方代理人签字", "乙方授权代理人签字", "供应方委托代理人签字"),
    "buyer_grant_ref": ("甲方委托书编号", "采购方委托书编号"),
    "seller_grant_ref": ("乙方委托书编号", "供应方委托书编号"),
    "grant_number": ("委托书编号", "授权委托书编号"),
    "grant_principal": ("委托单位", "授权单位", "委托人"),
    "grant_agent": ("受托人", "受托人姓名", "代理人姓名"),
    "grant_counterparty": ("交易相对方", "授权交易相对方"),
    "grant_task": ("代理事项", "委托事项", "授权事项"),
    "grant_scope": ("授权权限", "代理权限", "授权范围"),
    "grant_conditions": ("附加限制", "授权限制", "授权条件", "授权金额上限"),
    "granted_on": ("授权出具日期", "委托书出具日期"),
    "grant_from": ("授权起始日", "授权起始日期", "授权开始日期"),
    "grant_until": ("授权截止日", "授权截止日期", "授权终止日期"),
    "grant_signature": ("委托单位签章", "委托人签章", "授权单位签章"),
    "grant_state": ("授权状态", "委托状态"),
}
GRANT_FIELDS = ("power_of_attorney", "contract_id", "subject", *(key for key in LABELS if not key.startswith(("buyer_", "seller_"))))
ENTITY_TYPES = {"buyer_grant_ref":"mandate_number", "seller_grant_ref":"mandate_number", "grant_number":"mandate_number",
                "grant_principal":"party", "grant_counterparty":"party", "grant_agent":"mandatary"}
PAGE_MARK = re.compile(r"第?[0-9]{1,4}页(?:[/／共][0-9]{1,4}页)?")
SIGNER = re.compile(r"(?:(?:委托代理人|授权代理人|代理人):?)?([\u3400-\u9fff·A-Za-z]{2,40})\((?:已签字|已签名)\)")
PRINTED_SIGNER = re.compile(r"(?:(?:委托代理人|授权代理人|代理人):?)?(.{1,100})\((?:已签字|已签名)\)")
NATIVE_SIGNER = re.compile(r"(?:(?:委托代理人|授权代理人|代理人)\s*:?\s*)?(.{1,100}?)\s*\(\s*已\s*签\s*[字名]\s*\)")
HAN = r"[\u3400-\u9fff]"
SINGLE_NAME = re.compile(HAN+r"{2,4}|"+HAN+r"{1,12}(?:·"+HAN+r"{1,12}){1,3}")
JOINT_NAME = re.compile(r"[、,/&;+]|等人|共同|联合|两人|二人|分别|任选|之一|任一|"+HAN+r"{2,}[和与及暨或]"+HAN+r"{2,}")
REDACTED_NAME = re.compile(r"某|[*×□●_…]|[xX]{2,}|"+HAN+r"[xX]|匿名|隐去|遮盖|脱敏|不详|略去")
ROLE_NAME = re.compile(r"(?:代表(?:人)?|负责人|经办(?:人|员)|主管|经理|董事(?:长)?|总监|专员|员工|人员|"
                       r"主任|部长|组长|科长|职员|代理人|法人|签字人|法务|会计|出纳|[处科部室]|公司|项目组)$")
IDENTITY_NOTES = {
    "role": "仅列岗位或机构，请核对受托人全名及其本人签署依据。",
    "redacted": "姓名有隐去或遮盖，请核对完整姓名及对应签署依据。",
    "joint": "列有多人或共同代理表述，请核对是否须共同签署、各人权限及实际签名。",
    "unclear": "尚不能从该栏辨明一位具名受托人，请核对完整姓名和授权原文。",
}
SIGNING_SCOPE = re.compile(r"(?:仅限)?(?:代表委托(?:单位|人))?(?:签署|签订)本(?:采购)?合同")
NON_SIGNING = {"仅限收货验收", "仅限收货", "仅限验收", "仅办理收货和验收", "不得签署本合同", "无签约权限"}
CLEAR_TERMS = {"无","无附加限制","无其他限制","无附加条件"}
TOTAL_CAP = re.compile(r"本合同含税总价不得超过人民币("+AMOUNT.pattern+r")元")
YUAN_TOTAL = re.compile(r"人民币("+AMOUNT.pattern+r")元")
ADVANCE = re.compile(r"(?:本)?合同生效后支付(?:合同总价的)?([0-9]{1,3}(?:\.[0-9]{1,4})?)%(?:预付款)?")
SIDES = {"buyer":"甲方", "seller":"乙方"}
PARTY_SIGNATURES = {"buyer_signature":("甲方签署","甲方签章","采购方签署","买方签章"),
                    "seller_signature":("乙方签署","乙方签章","供应方签署","卖方签章")}
PRINTED_LABELS = {**LABELS, **PARTY_SIGNATURES, "contract_id":("合同编号","合同号"), "subject":("采购标的","合同标的","标的名称","货物名称")}


def printed_value(field, value, quote):
    line, value = normalized(quote), normalized(value)
    if field=="power_of_attorney":
        return value if value==line and line in TITLES else ""
    label, separator, body = line.partition(":")
    if separator and label in PRINTED_LABELS.get(field, ()) and value in (line, body):
        return body
    return ""


def agent_kind(value):
    spaced = unicodedata.normalize("NFKC",value).strip()
    value = normalized(spaced)
    if REDACTED_NAME.search(value):
        return "redacted"
    if JOINT_NAME.search(value) or re.search(HAN+r"{2,}\s+"+HAN+r"{2,}", spaced):
        return "joint"
    if ROLE_NAME.search(value):
        return "role"
    if value in {"未填", "未填写", "未载明", "空白", "待定", "待签", "无", "本人", "不适用", "见附件", "见签章",
                 "甲方", "乙方", "采购", "销售", "授权", "代理", "无法辨认", "模糊", "待补充"}:
        return "unclear"
    return "named" if SINGLE_NAME.fullmatch(value) else "unclear"


def unresolved_agents(graph):
    holds = []
    for fact in graph["facts"]:
        if fact["field"]!="grant_agent" or fact["status"] not in ("anchored", "confirmed"):
            continue
        body = (unicodedata.normalize("NFKC", fact["quote"]).partition(":")[2].strip()
                if printed_value("grant_agent", fact["value"], fact["quote"]) else "")
        kind = agent_kind(body)
        if kind != "named":
            holds.append({"fact":fact["id"], "field":fact["field"], "doc":fact["doc"], "page":fact["page"],
                          "unit":fact.get("unit", fact["doc"]), "value":body or fact["value"], "kind":kind})
    return holds


def printed_name(field, line):
    body = unicodedata.normalize("NFKC",line).partition(":")[2].strip()
    if field=="grant_agent":
        return body
    signed = NATIVE_SIGNER.fullmatch(body)
    return signed[1] if signed else ""


def identity_holds(graph, read_text):
    """Compare the transcription to each matching native line before identifying a person."""
    pages = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    by_page = {}
    agents, signers = [], []
    signature_fields = {*PARTY_SIGNATURES, "buyer_agent_signature", "seller_agent_signature"}
    for fact in graph["facts"]:
        field = fact["field"]
        if fact["status"] not in ("anchored", "confirmed") or field not in signature_fields and field!="grant_agent":
            continue
        address = fact["doc"],fact["page"]
        quoted = printed_name(field,fact["quote"])
        if field in signature_fields and not quoted:
            continue
        native = pages[f"{address[0]}/p{address[1]}"]
        lines = []
        if native.get("layer")=="text":
            if address not in by_page:
                source = read_text(*address)
                if not isinstance(source,str) or hashlib.sha256(source.encode()).hexdigest()!=native.get("text_sha256"):
                    raise ValueError("受托人或签字栏与原页文字层摘要不符")
                indexed = defaultdict(list)
                for number, line in enumerate(source.splitlines(),1):
                    indexed[normalized(line)].append({"line":number, "quote":line})
                by_page[address] = indexed
            lines = by_page[address].get(normalized(fact["quote"]), [])
        value,kind = quoted,agent_kind(quoted)
        for line in lines:
            visible = printed_name(field,line["quote"])
            visible_kind = agent_kind(visible)
            if visible_kind!="named":
                value,kind = visible,visible_kind
                break
        if not printed_value(field, fact["value"], fact["quote"]) or native.get("layer")=="text" and not lines:
            kind = "unclear"
        if kind!="named":
            target = agents if field=="grant_agent" else signers
            target.append({"fact":fact["id"], "field":field, "doc":fact["doc"], "page":fact["page"],
                           "unit":fact.get("unit",fact["doc"]), "value":value or fact["value"], "kind":kind, "lines":lines})
    return agents,signers


def rows_for_grants(graph, read_text, *, check_images=False):
    units = set(graph["documents_by_kind"].get("power_of_attorney", []))
    pages = covered_rows(graph, read_text, units, GRANT_FIELDS, printed_value, "授权委托书")
    if check_images:
        nodes = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
        for p in pages:
            p["text_only"] = nodes[f"{p['doc']}/p{p['page']}"].get("clause_text_only") is True
    return pages


def is_page_marker(text):
    plain = normalized(text)
    return not plain or plain == "合成演练资料仅供系统测试无交易效力" or bool(PAGE_MARK.fullmatch(plain))


def covered_rows(graph, read_text, units, fields, validate, subject):
    """Account for each native line of a bounded legal instrument, including unclassified riders."""
    if not units:
        return []
    positions = defaultdict(set)
    for fact in graph["facts"]:
        unit = fact.get("unit", fact["doc"])
        line = fact.get("source_line")
        if (unit in units and fact["field"] in fields and fact["status"] in ("anchored", "confirmed")
                and validate(fact["field"], fact["value"], fact["quote"])
                and line and line["rects"] and normalized(line["text"]) == normalized(fact["quote"])):
            positions[unit, fact["page"]].add((line["number"], line["text"]))
    pages = {n["id"]: n for n in graph["nodes"] if n["type"]=="page"}
    result = []
    for unit in graph.get("audit_documents", graph["documents"]):
        if unit["id"] not in units:
            continue
        doc = unit.get("source", unit["id"])
        numbers = [unit["page"]] if "page" in unit else sorted(int(p.split("/p")[1]) for p in pages if p.startswith(doc+"/p"))
        for number in numbers:
            page = pages[f"{doc}/p{number}"]
            missing = []
            if page.get("layer") == "text":
                source = read_text(doc, number)
                if not isinstance(source, str) or hashlib.sha256(source.encode()).hexdigest() != page.get("text_sha256"):
                    raise ValueError(subject+"的文字层摘要与归档不符")
                for index, text in enumerate(source.splitlines(), 1):
                    if is_page_marker(text) or (index, text) in positions[unit["id"], number]:
                        continue
                    missing.append({"line": index, "quote": text})
            result.append({"unit":unit["id"], "doc":doc, "page":number, "native":page.get("layer")=="text", "uncovered":missing})
    return result


def coverage_gaps(pages):
    return [{"id":f"{p['doc']}/p{p['page']}", "doc":p["doc"], "page":p["page"], "quality":"mandate_clause",
             "field":"grant_conditions", **line} for p in pages for line in p["uncovered"]]


def attach(graph, read_text):
    pages = rows_for_grants(graph, read_text, check_images=True)
    holds,signers = identity_holds(graph, read_text)
    graph["delegation_coverage"] = {"format":FORMAT, "pages":pages, "agent_holds":holds, "signer_holds":signers}
    graph["gaps"].extend(coverage_gaps(pages))
    if holds or signers:
        withheld = {h["fact"] for h in holds}
        local_signatures = {(h["field"],h["fact"]) for h in signers}
        removed = set()
        for edge in graph["edges"]:
            ref = edge["evidence"][0]
            if edge["type"]=="grant_agent" and ref in withheld:
                removed.add(edge["to"])
                edge.update(type="unresolved_grant_agent", to=ref)
            elif (edge["type"],ref) in local_signatures:
                removed.add(edge["to"])
                edge["to"] = ref
        unused = removed - {edge["to"] for edge in graph["edges"]}
        graph["nodes"] = [n for n in graph["nodes"] if n["id"] not in unused]


def verify_sources(report, read_text, *, signing=False):
    policy, graph = report["policy"], report["graph"]
    marker = policy.get("delegation_checks")
    if policy.get("version","")>=TERMS_SINCE and marker!=FORMAT:
        raise ValueError("缺少逐项核对书面授权限制的程序")
    if not marker:
        if "delegation.py" in policy.get("code_sha256", {}) or "delegation_coverage" in graph:
            raise ValueError("缺少书面代理授权核对程序")
        return
    pages = rows_for_grants(graph, read_text, check_images=marker==FORMAT)
    coverage = {"format":marker, "pages":pages}
    if marker in (NATIVE_NAME_FORMAT,FORMAT):
        holds,signers = identity_holds(graph,read_text)
        coverage["signer_holds"] = signers
    elif marker==NAME_FORMAT:
        holds = unresolved_agents(graph)
    else:
        holds = []
    withheld = set()
    if marker in (NAME_FORMAT,NATIVE_NAME_FORMAT,FORMAT):
        coverage["agent_holds"] = holds
        withheld = {h["fact"] for h in holds}
    versions = {LEGACY_FORMAT:("contract-performance-v4",), NAME_FORMAT:("contract-performance-v5",),
                NATIVE_NAME_FORMAT:NATIVE_FORMATS, FORMAT:NATIVE_FORMATS}
    if (policy.get("performance_checks") not in versions.get(marker,()) or graph.get("delegation_coverage")!=coverage
            or coverage_gaps(pages) != [g for g in graph["gaps"] if g["quality"]=="mandate_clause"]):
        raise ValueError("授权委托书的已核页面或未覆盖条款与原页不符")
    nodes = {n["id"]: n for n in graph["nodes"]}
    expected = []
    persons = set()
    for fact in graph["facts"]:
        if fact["field"] not in ENTITY_TYPES or fact["status"] not in ("anchored", "confirmed"):
            continue
        kind = ENTITY_TYPES[fact["field"]]
        unit = fact.get("unit", fact["doc"])
        if fact["id"] in withheld:
            expected.append((unit, fact["id"], "unresolved_grant_agent", (fact["id"],)))
            continue
        value = printed_value(fact["field"], fact["value"], fact["quote"]) or normalized(fact["value"])
        target = kind+"-"+hashlib.sha256(value.encode()).hexdigest()[:18]
        node = nodes.get(target)
        if not node or node["type"] != kind or normalized(node["label"]) != value:
            raise ValueError("代理授权的人员、主体或编号实体与引文不符")
        if kind=="mandatary":
            persons.add(target)
        expected.append((unit, target, fact["field"], (fact["id"],)))
    actual = [(e["from"],e["to"],e["type"],tuple(e["evidence"])) for e in graph["edges"]
              if e["type"] in ENTITY_TYPES or e["type"]=="unresolved_grant_agent" or nodes.get(e["to"],{}).get("type")=="mandatary"]
    if sorted(actual)!=sorted(expected) or marker!=LEGACY_FORMAT and persons!={n["id"] for n in nodes.values() if n["type"]=="mandatary"}:
        raise ValueError("代理授权图谱关系与原件归属不符")
    if marker in (NATIVE_NAME_FORMAT,FORMAT):
        located = {(h["field"],h["fact"]):h["unit"] for h in signers}
        expected_signers = [(unit,ref,field,(ref,)) for (field,ref),unit in located.items()]
        actual_signers = [(e["from"],e["to"],e["type"],tuple(e["evidence"])) for e in graph["edges"]
                          if any((e["type"],ref) in located for ref in e["evidence"])]
        if sorted(actual_signers)!=sorted(expected_signers):
            raise ValueError("待核签署栏应指向其所在原页的签字记录")
    if signing and marker not in (NATIVE_NAME_FORMAT,FORMAT):
        approved = [entry for f in report["findings"] for entry in f.get("delegations",[]) if entry["status"]=="ok"]
        if approved:
            agents,signers = identity_holds(graph,read_text)
            ambiguous = {h["fact"] for h in agents+signers}
            if any(agent_kind(e["agent"] or "")!="named" or ambiguous.intersection(e["evidence"]) for e in approved):
                raise ValueError("旧版签约授权所据姓名仅列岗位、多人或不完整，请按现行程序重审。")
    if signing and marker!=FORMAT:
        approved = [d for f in report["findings"] for d in f.get("delegations",[]) if d["status"]=="ok"]
        for entry in approved:
            refs = set(entry["evidence"])
            fields = [f for f in graph["facts"] if f["id"] in refs]
            states = {native_value(f,LABELS["grant_state"]) for f in fields if f["field"]=="grant_state"}
            dates = {"signed_on","grant_from","grant_until","granted_on"}
            if (any(native_value(f,LABELS["grant_conditions"]) not in CLEAR_TERMS for f in fields if f["field"]=="grant_conditions")
                    or states - {"有效","已生效"}
                    or any(re.search(r"\d\s+\d",(f.get("source_line") or {}).get("text",f["quote"])) for f in fields if f["field"] in dates)
                    or any(not p["text_only"] for p in rows_for_grants(graph,read_text,check_images=True) if p["unit"] in entry["units"])):
                raise ValueError("旧版签约授权所据限制、状态、日期或附注需要按现行程序重审。")


def present(doc, field):
    return bool(doc.fields[field] or field in doc.uncertain or any(g.get("field")==field for g in doc.gaps))


def complete_id(value):
    return bool(value and value not in {"无","未编号","未填写","待定"} and not incomplete_number(value)
                and re.fullmatch(r"[A-Za-z0-9\u3400-\u9fff][A-Za-z0-9\u3400-\u9fff._-]{0,79}", value))


def native_value(fact, labels):
    source = fact.get("source_line") or {}
    raw = unicodedata.normalize("NFKC",source.get("text","")).strip()
    label, sep, value = raw.partition(":")
    permitted = {normalized(raw),normalized(value)}
    amount = YUAN_TOTAL.fullmatch(value.strip()) if fact["field"]=="total" else None
    if amount:
        permitted.update((amount[1],amount[1].replace(",","")))
    if (not source.get("rects") or not sep or label.strip() not in labels
            or normalized(raw)!=normalized(fact["quote"]) or normalized(fact["value"]) not in permitted):
        return ""
    return value.strip()


def check_limits(contract, grant):
    checks = []
    for fact in grant.fields["grant_conditions"]:
        value = native_value(fact,LABELS["grant_conditions"])
        item = {"field_ref":fact["id"], "kind":"condition", "status":"missing", "comparison_ref":None}
        if value in CLEAR_TERMS:
            item["status"]="ok"
        elif value=="不得约定预付款":
            item["kind"]="prepayment"
            for term in contract.fields["payment_stage"]:
                label = unicodedata.normalize("NFKC",term["quote"]).partition(":")[0].strip()
                if not re.fullmatch(r"第[一二两三四五六七八九十0-9]+期|预付款|首付款",label):
                    continue
                advance = ADVANCE.fullmatch(native_value(term,(label,)))
                if advance and 0 < Decimal(advance[1]) <= 100:
                    checks.append({**item, "status":"risk", "comparison_ref":term["id"]})
            if any(c["field_ref"]==fact["id"] for c in checks):
                continue
        elif (cap:=TOTAL_CAP.fullmatch(value)) and Decimal(cap[1].replace(",",""))>0:
            item["kind"]="total_cap"
            totals = contract.fields["total"]
            if (len(totals)==1 and not contract.incomplete("total","currency","unit")
                    and all(normalized(f["value"]).upper() in {"人民币","人民币元","CNY","RMB"} for f in contract.fields["currency"])
                    and all(normalized(f["value"]) in {"元","人民币元"} for f in contract.fields["unit"])):
                total = YUAN_TOTAL.fullmatch(native_value(totals[0],("含税总额","合同含税总价")))
                if total and Decimal(total[1].replace(",",""))>0:
                    item["comparison_ref"]=totals[0]["id"]
                    if Decimal(total[1].replace(",",""))>Decimal(cap[1].replace(",","")):
                        item["status"]="risk"
        checks.append(item)
    caps = {native_value(f,LABELS["grant_conditions"]) for f in grant.fields["grant_conditions"]}
    if sum(bool(TOTAL_CAP.fullmatch(value)) for value in caps)>1:
        for item in checks:
            if item["kind"]=="total_cap":
                item["status"]="missing"
    return checks


def decision(contract, side, signature, grants, *, strict_names, read_date=None):
    label = SIDES[side]
    reference = side+"_grant_ref"
    counterparty = "seller" if side=="buyer" else "buyer"
    refs = contract.evidence(signature, reference, "contract_id", "subject", side, counterparty, "signed_on")
    for grant in grants:
        refs.extend(grant.evidence(*GRANT_FIELDS))
    sign = (PRINTED_SIGNER if strict_names else SIGNER).fullmatch(contract.body(signature))
    entry = {"side":side, "signature_field":signature, "agent":sign[1] if sign else None,
             "units":[g.unit for g in grants], "evidence":list(dict.fromkeys(refs)),
             "signed_on":None, "issued_on":None, "valid_from":None, "valid_until":None}
    def outcome(status, detail):
        return {**entry, "status":status, "detail":detail}
    if strict_names:
        entry["agent_kind"] = agent_kind(sign[1] if sign else "")
        for fact in contract.fields[signature]:
            printed = unicodedata.normalize("NFKC", fact["quote"]).partition(":")[2].strip()
            matched = PRINTED_SIGNER.fullmatch(printed)
            if matched and agent_kind(matched[1])!="named":
                entry["agent_kind"] = agent_kind(matched[1])
                break
        printed_signer = next((h for h in contract.signer_holds if h["field"]==signature),None)
        if printed_signer:
            entry["agent_kind"] = printed_signer["kind"]
    signed = read_date(contract,"signed_on") if read_date else contract.date("signed_on")
    entry["signed_on"] = signed.isoformat() if signed else None
    if len(grants) != 1:
        return outcome("missing", label+"需核对一份适用于该次签约的委托书及其替代关系。")
    grant, = grants
    issued, start, end = ((read_date(grant,key) if read_date else grant.date(key)) for key in ("granted_on", "grant_from", "grant_until"))
    entry.update(issued_on=issued.isoformat() if issued else None, valid_from=start.isoformat() if start else None,
                 valid_until=end.isoformat() if end else None)
    principal = contract.body(side)
    if (not complete_id(contract.body("contract_id")) or not principal or not contract.body(counterparty) or not contract.body("subject")
            or any(contract.body(left)!=grant.body(right) for left,right in (
                ("contract_id","contract_id"), ("subject","subject"), (side,"grant_principal"), (counterparty,"grant_counterparty")))):
        return outcome("missing", label+"的委托单位、相对方、合同号和标的尚未与委托书逐项对应。")
    if present(contract, reference):
        value = contract.body(reference)
        if not complete_id(value) or value != grant.body("grant_number"):
            return outcome("missing", label+"签署栏所引的委托书编号与提交的委托书尚未对应。")
    if read_date and grant.fields["grant_conditions"]:
        entry["limits"] = check_limits(contract,grant)
        entry["evidence"] = list(dict.fromkeys([*entry["evidence"],*(c["comparison_ref"] for c in entry["limits"] if c["comparison_ref"])]))
    agent = grant.body("grant_agent")
    if strict_names and (grant.agent_holds or entry["agent_kind"]!="named"):
        if grant.agent_holds:
            observed = grant.agent_holds[0]
            entry["agent_kind"] = observed["kind"]
            source = "委托书受托人栏“"+observed["value"]+"”"
        else:
            source = "合同代理签字栏“"+(printed_signer["value"] if printed_signer else contract.body(signature))+"”"
        note = label+source+IDENTITY_NOTES[entry["agent_kind"]]
        risks = []
        if all((issued,start,end,signed)) and start<=end and (issued>signed or not start<=signed<=end):
            risks.append(f"签约日 {signed}，委托书出具日 {issued}，授权期间 {start} 至 {end}。")
        if grant.body("grant_scope") in NON_SIGNING:
            risks.append("授权范围为“"+grant.body("grant_scope")+"”，需另核签约授权。")
        return outcome("risk" if risks else "missing", note+"".join(risks))
    if not sign or not agent or sign[1] != agent or any(token in agent for token in ("某某", "待签", "未填写", "代理人", "XX")):
        return outcome("missing", label+"代理签字人的姓名与委托书所列受托人尚未对应。")
    if (not (contract.signed(signature) and grant.signed("grant_signature", principal, "seal"))
            or strict_names and any(not printed_value(f["field"],f["value"],f["quote"])
                                    for f in contract.fields[signature]+grant.fields["grant_signature"])):
        return outcome("missing", label+"代理签字栏和委托单位签章需分别对照原页核准。")
    if not all((issued, start, end, signed)) or start>end:
        return outcome("missing", label+"委托书的出具日、授权起止日期或签约日期待核。")
    if issued>signed or not start<=signed<=end:
        return outcome("risk", f"{label}签约日 {signed}，委托书出具于 {issued}，授权期间为 {start} 至 {end}。请核对当日授权或后续追认材料。")
    permission = grant.body("grant_scope")
    if permission in NON_SIGNING:
        return outcome("risk", label+"委托书记载“"+permission+"”，现有权限不足以支持代理签约，请核对其他授权或追认。")
    if not SIGNING_SCOPE.fullmatch(permission):
        return outcome("missing", label+"委托书中的签约权限及限定条件仍需逐项辨明。")
    state = grant.body("grant_state")
    if state and state not in {"有效","已生效"}:
        return outcome("risk", label+"委托书记载授权状态“"+state+"”，请核对撤销、变更或追认发生的时间。")
    if read_date and present(grant,"grant_state") and not state:
        return outcome("missing", label+"委托书的状态记录不一致或尚待核对，请核实签约当日适用的授权。")
    if present(grant, "grant_task") and grant.body("grant_task") not in {"本合同采购","办理本合同采购","签署本合同","签署本采购合同"}:
        return outcome("missing", label+"委托事项与本合同签署的适用范围待核。")
    conditions = grant.body("grant_conditions")
    if read_date and any(c["status"]=="risk" for c in entry.get("limits",())):
        return outcome("risk",label+"所签条款与委托书限制不一致，请核对签约时的补充授权或事后追认。")
    if (conditions and conditions not in CLEAR_TERMS
            or read_date and any(c["status"]!="ok" for c in entry.get("limits",()))
            or grant.incomplete(*GRANT_FIELDS) or not grant.mandate_pages
            or any(not p["native"] or p["uncovered"] or read_date and not p.get("text_only") for p in grant.mandate_pages)):
        return outcome("missing", label+"授权委托书还有待核的限制、原页文字或影像范围，请核对完整委托书。")
    return outcome("ok", f"{label}代理人{agent}的签字与受托人一致，签约日 {signed} 在已核授权期间内，委托书明确允许签署本合同。")


def checks(contract, grants, *, strict_names=True, read_date=None):
    active = {}
    for side in SIDES:
        dedicated, ordinary = side+"_agent_signature", side+"_signature"
        signer = (PRINTED_SIGNER if strict_names else SIGNER).fullmatch(contract.body(ordinary))
        if present(contract, dedicated):
            active[side] = dedicated
        elif signer and signer[1]!=contract.body(side):
            active[side] = ordinary
        elif present(contract, side+"_grant_ref"):
            active[side] = dedicated
    entries = []
    used = set()
    for side, signature in active.items():
        principal = contract.body(side)
        matches = [g for g in grants if principal and g.body("grant_principal")==principal]
        if not matches and len(active)==1 and len(grants)==1:
            matches = list(grants)
        used.update(g.unit for g in matches)
        entries.append(decision(contract, side, signature, matches, strict_names=strict_names,read_date=read_date))
    if (len(entries)==2 and entries[0]["agent"] and entries[0]["agent"]==entries[1]["agent"]
            and (not strict_names or all(e["agent_kind"]=="named" for e in entries))):
        for entry in entries:
            note = " 双方代理签署栏所列姓名相同，请核对本人身份及各方同意或追认。" if strict_names else " 同一人列入双方代理签署栏，请核对各方同意或追认。"
            entry.update(status="risk", detail=entry["detail"]+note)
    unassigned = [g for g in grants if g.unit not in used]
    if unassigned:
        refs = [ref for g in unassigned for ref in g.evidence(*GRANT_FIELDS)]
        entries.append({"side":"unassigned", "signature_field":None, "agent":None, "units":[g.unit for g in unassigned], "status":"missing",
                        "detail":"另有委托书尚未对应到合同的代理签署栏，请核对委托关系。",
                        "evidence":list(dict.fromkeys(refs)), "signed_on":None, "issued_on":None, "valid_from":None, "valid_until":None})
    return entries
