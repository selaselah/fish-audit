"""Reconcile a contract's sampling requirement with identified equipment and individual readings."""

import hashlib
import re
from collections import Counter, defaultdict
from decimal import Decimal

LEGACY = "inspection-coverage-v1"
NAMED_FORMAT = "inspection-coverage-v2"
REGISTER_FORMAT = "inspection-coverage-v3"
FORMAT = "inspection-coverage-v4"
REGISTER_FORMATS = (REGISTER_FORMAT, FORMAT)
SINCE = "2026.11.26.04"
NAMED_SINCE = "2026.11.26.19"
REGISTER_SINCE = "2026.11.28.16"
SUBSTITUTION_SINCE = "2026.11.28.17"
REGISTER = "delivery_register"
RECTS = "delivery_register_rects"
NAMED = "inspection_required_serials"
LABELS = {
    "inspection_requirement": ("性能检测要求", "测温抽检要求", "测温范围", "性能检测方式"),
    "tested_quantity": ("性能实测数量", "实际测温台数", "测温台数"),
    "unit_temperature": ("单机测温", "逐台测温记录", "单台测温"),
    NAMED: ("必检设备编号", "指定抽检设备编号", "必测设备编号"),
}
FIELDS = {label: field for field, labels in LABELS.items() for label in labels}
AUXILIARY = {
    "约定交付数量":"ordered", "合同交付数量":"ordered", "实际验收数量":"received", "验收数量":"received",
    "验收设备编号":"population", "实收设备编号":"population", "验收序列号":"population",
    "约定设备编号":"ordered_serials", "合同设备编号":"ordered_serials",
    "约定验收标准":"limit", "合同验收标准":"limit", "检验依据":"basis", "验收依据":"basis",
}
SERIAL_LABELS = {"约定设备序列号":"ordered_serials", "合同设备序列号":"ordered_serials",
                 "验收设备序列号":"population", "实收设备序列号":"population"}
REGISTER_KINDS = {"ordered_serials","population","ordered","received","serial_note","substitution"}
SERIAL_NOTE = re.compile(r"换货|换机|替换设备|替代设备|代用设备|调换|"
                         r"(?:编号|序列号|机身号).{0,20}(?:另|以|按|调整|变更|仅|节选|尾号|续|见|准)|"
                         r"(?:另行|变更|补充|只列|仅列|其余).{0,20}(?:编号|序列号|设备清单)")
HINT = re.compile(r"逐台.{0,6}(?:测温|检测|检验)|(?:抽检|抽测|抽样检验|全数检验|全检).{0,15}(?:台|设备|测温|温度)|(?:设备|性能|测温).{0,12}(?:抽检|抽测|全检)|(?:按比例|按百分之[一二三四五六七八九十]+|按[0-9]+[%％])抽检")
NAMED_HINT = re.compile(
    r"必检|必测|免检|免测|指定.{0,16}(?:抽检|抽测|测温|检验)|"
    r"(?:抽检|抽测|测温).{0,16}(?:指定|对象|名单|清单|编号|包含|须含|调整|替代)|"
    r"(?:另须|还须|另需|应对|须对|必须对).{0,48}(?:抽检|抽测|测温)")
ALL = {"全部交付设备逐台测温", "每台设备均须测温", "逐台测温", "全部设备逐台测温"}
MINIMUM = re.compile(r"(?:至少|不少于)抽检([1-9][0-9]{0,4})台测温|抽检不少于([1-9][0-9]{0,4})台测温")
NUMBER = r"-?[0-9]{1,3}(?:\.[0-9]{1,4})?"
LIMIT = re.compile(r"柜温(不高于|不超过|至多|≤|不低于|不少于|至少|≥)("+NUMBER+r")\s*(?:℃|°C)")
CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{1,47}")
SERIAL_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*")
SUBSTITUTION = re.compile(r"代替|替代|顶替|置换|替换|换货|改供|更换(?:成|为)|换(?:成|为)|改为")
NO_SUBSTITUTE = re.compile(r"(?:不得|禁止|严禁)(?:以|用)\s*("+SERIAL_TOKEN.pattern+r")\s*(?:代替|替代)\s*("+SERIAL_TOKEN.pattern+r")[。.]?")
READING = re.compile(r"([^，,]+)[，,]\s*柜温\s*("+NUMBER+r")\s*(?:℃|°C)")
SEVERITY = {"ok":0,"missing":1,"risk":2,"issue":3}


def split(quote):
    parts = re.split("[:：]", quote, maxsplit=1)
    return parts[0].strip(), parts[1].strip() if len(parts)==2 else ""


def classify(quote, field=None, *, version=FORMAT):
    label, body = split(quote)
    kind = FIELDS.get(label) or AUXILIARY.get(label)
    if kind and (kind != NAMED or version != LEGACY):
        return kind
    if version in REGISTER_FORMATS and label in SERIAL_LABELS:
        return SERIAL_LABELS[label]
    if (field in LABELS and field != NAMED) or HINT.search(quote):
        return "note"
    if version != LEGACY and (field == NAMED or NAMED_HINT.search(quote)):
        return "note"
    if version == FORMAT and SUBSTITUTION.search(quote):
        if len({s for s in SERIAL_TOKEN.findall(body or quote) if serial(s)}) >= 2:
            return "substitution"
        if re.search(r"(?:整机|设备|冷藏柜).{0,12}(?:代替|顶替|置换|更换成|更换为)|(?:代替|顶替|置换).{0,12}(?:整机|设备|冷藏柜)",quote):
            return "serial_note"
    if version in REGISTER_FORMATS:
        from equipment_models import ALTERNATIVE
        if SERIAL_NOTE.search(quote) or ALTERNATIVE.search(quote):
            return "serial_note"
    if version == FORMAT and (re.search(r"例外|但书|除外|除非",quote) or label in ("特别约定","补充约定")):
        return "exception"


def equivalent_quote(text):
    return text.replace("℃","°C").replace("，",",").replace("：",":")


def sources(graph, read_text, *, version=FORMAT):
    roles = {u:kind for kind in ("contract","acceptance","reinspection","contract_addendum")
             for u in graph["documents_by_kind"].get(kind,())}
    sections = {(d["source"],d["page"]):d["id"] for d in graph.get("audit_documents",[]) if "source" in d}
    observed = defaultdict(list)
    for f in graph["facts"]:
        observed[f["doc"],f["page"]].append(f)
    rows, pages = [], []
    for node in graph["nodes"]:
        if node["type"]!="page":
            continue
        doc, suffix = node["id"].rsplit("/p",1)
        page = int(suffix)
        unit = sections.get((doc,page),doc)
        if unit not in roles:
            continue
        place = {"doc":doc,"page":page,"unit":unit}
        native = node.get("layer")=="text"
        pages.append({**place,"role":roles[unit],"native":native,"text_only":node.get("clause_text_only") is True})
        lines = []
        if native:
            text = read_text(doc,page)
            if not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=node.get("text_sha256"):
                raise ValueError("逐台检验所据的原页文字摘要不符")
            lines = text.splitlines()
        printed = set(lines)
        located = defaultdict(list)
        for fact in observed[doc,page]:
            source = fact.get("source_line") or {}
            raw_source = source.get("text","")
            same_line = bool(native and source.get("rects") and 0 < source["number"] <= len(lines)
                             and lines[source["number"]-1] == raw_source)
            if same_line:
                located[source["number"],source["text"]].append(fact)
            kind = classify(fact["quote"],fact["field"],version=version)
            rendered = same_line and equivalent_quote(raw_source)==equivalent_quote(fact["quote"])
            if kind and ((fact["quote"] not in printed and not rendered) or not classify(fact["quote"],version=version) or
                         (fact["status"]=="disputed" and not same_line)):
                rows.append({**place,"id":"inspection-line/"+fact["id"],"line":None,"kind":kind,
                             "quote":fact["quote"],"facts":[fact["id"]],"disputed":fact["status"]=="disputed"})
        following_named = False
        following_register = False
        for number, raw in enumerate(lines,1):
            kind = classify(raw,version=version)
            if following_named and raw.strip() and not re.search("[:：]",raw):
                kind = "note"
            elif following_register and raw.strip() and not re.search("[:：]",raw):
                kind = "serial_note"
            if raw.strip():
                following_named = kind == NAMED or (following_named and kind == "note")
                following_register = version in REGISTER_FORMATS and kind in ("ordered_serials","population","serial_note","substitution")
            if kind:
                facts = located[number,raw]
                rows.append({**place,"id":f"inspection-line/{doc}/p{page}/l{number}","line":number,"kind":kind,
                             "quote":raw,"facts":[f["id"] for f in facts],"disputed":any(f["status"]=="disputed" for f in facts)})
    if version == FORMAT:
        roster_codes = {code for r in rows if r["kind"] in ("ordered_serials","population")
                        for code in SERIAL_TOKEN.findall(split(r["quote"])[1]) if serial(code)}
        rows = [r for r in rows if r["kind"]!="substitution" or not re.search(r"账号|账户|开户行|开票信息|收款信息|付款日期",r["quote"])
                or roster_codes.intersection(SERIAL_TOKEN.findall(r["quote"]))]
        qualified = {r["unit"] for r in rows if r["kind"]=="substitution"}
        rows = [{**r,"kind":"serial_note"} if r["kind"]=="exception" else r for r in rows
                if r["kind"]!="exception" or r["unit"] in qualified]
    triggered = any(r["kind"] in (*LABELS,"note") for r in rows)
    assigned = any(r["kind"]=="ordered_serials" and roles[r["unit"]]=="contract" for r in rows)
    if not triggered and version in REGISTER_FORMATS and assigned:
        return {"format":version,"purpose":REGISTER,"rows":[r for r in rows if r["kind"] in REGISTER_KINDS],"pages":pages}
    if version in REGISTER_FORMATS and not assigned:
        rows = [r for r in rows if r["kind"] not in ("serial_note","substitution")]
    return {"format":version,"rows":rows if triggered else [],"pages":pages if triggered else []}


def source_graph(ledger):
    nodes, edges = [], []
    for r in ledger["rows"]:
        ref = f"{r['doc']}/p{r['page']}"
        nodes.append({"id":r["id"],"type":"inspection_line","label":r["quote"],"doc":r["doc"],"page":r["page"],"line":r["line"]})
        edges.append({"type":"inspection_coverage_source","from":ref,"to":r["id"],"evidence":[ref,*r["facts"]]})
    return nodes,edges


def count(value):
    match = re.fullmatch(r"(0|[1-9][0-9]{0,5})\s*台",value)
    return int(match[1]) if match else None


def serial(value):
    from quality_references import incomplete_number
    return bool(CODE.fullmatch(value) and re.search("[0-9]",value) and not incomplete_number(value))


def population(value):
    values = [s.strip() for s in re.split("[、,，]",value)]
    return values if all(serial(s) for s in values) and len(set(values))==len(values) else None


def register_rows(graph):
    ledger = graph.get("inspection_coverage_sources", {})
    return ledger["rows"] if ledger.get("purpose") == REGISTER else []


def substitution_sources(graph, contract, receipt, clauses, rosters):
    from contract_changes import SOURCE_LABELS
    from delegation import complete_id, native_value
    from performance import Material
    from reinspection import LINK_KEYS

    codes = {v.strip() for row in rosters for v in re.split("[、，,]",split(row["quote"])[1]) if serial(v.strip())}
    matched = [r for r in clauses if codes.intersection(SERIAL_TOKEN.findall(r["quote"]))]
    allowed = {contract.unit,receipt.unit}
    evidence = []
    def printed(doc, key):
        facts = doc.fields[key]
        if len(facts)==1 and not doc.incomplete(key):
            return native_value(facts[0],SOURCE_LABELS[key])

    # The title of a submitted addendum alone cannot associate it with this purchase.
    for unit in graph["documents_by_kind"].get("contract_addendum",()):
        if not any(r["unit"]==unit for r in matched):
            continue
        change = Material(graph,unit)
        keys = ("base_contract_ref","buyer","seller","subject")
        original = [printed(contract,k) for k in LINK_KEYS]
        counterpart = [printed(change,k) for k in keys]
        if (all(original) and original == counterpart and complete_id(printed(change,"addendum_number"))
                and complete_id(counterpart[0]) and original[1]!=original[2]):
            allowed.add(unit)
            evidence.extend(change.evidence("addendum_number",*keys))
    return [r for r in matched if r["unit"] in allowed],evidence


def delivery_register(graph, check, rows, pages, contract, receipts, complex_scope):
    from performance import FINAL_SCOPES
    from reinspection import LINK_KEYS
    from warranty_terms import identity

    ordered = [r for r in rows if r["unit"]==contract.unit and r["kind"]=="ordered_serials"]
    received = [r for r in rows if r["unit"] in {m.unit for m in receipts} and r["kind"]=="population"]
    check.update(mode=REGISTER, register={"rows":[r["id"] for r in [*ordered,*received]]})
    def result(state, status, detail):
        return {**check,"state":state,"status":status,"detail":detail}
    clauses = [r for r in rows if r["kind"]=="substitution"]
    notes = []
    if (clauses and len(receipts)==1 and identity(contract,receipts[0])
            and receipts[0].body("acceptance_scope") in FINAL_SCOPES):
        notes, refs = substitution_sources(graph,contract,receipts[0],clauses,[*ordered,*received])
        check["register"]["rows"].extend(r["id"] for r in notes)
        check["evidence"] = list(dict.fromkeys([*check["evidence"],*contract.evidence(*LINK_KEYS),
                                                *receipts[0].evidence(*LINK_KEYS),*refs]))
    def review_substitution():
        return result("register_substitution","missing","资料载有设备代用说明，需核对约定、批准原件、批准人权限及生效时间，确认本次终验适用的清单。")
    if complex_scope or len(receipts)!=1 or set(check["scope"])!={contract.unit,receipts[0].unit}:
        if (notes and all(r["line"] and not r["disputed"] for r in notes)
                and any(r["unit"] in graph["documents_by_kind"].get("contract_addendum",()) for r in notes)):
            return review_substitution()
        return result("register_scope","missing","需确定设备清单适用的合同版本、交付批次及最终验收单。")
    receipt = receipts[0]
    check["evidence"] = list(dict.fromkeys([*check["evidence"],*contract.evidence(*LINK_KEYS),*receipt.evidence(*LINK_KEYS)]))
    if not identity(contract, receipt) or receipt.body("acceptance_scope") not in FINAL_SCOPES:
        return result("register_scope","missing","须先核实双方、合同编号、标的和本次终验范围，再逐台对应设备编号。")
    if (len(pages)!=2 or any(not p["native"] or not p["text_only"] for p in pages) or
            any(g.get("quality") in ("partial","unreadable") for g in [*contract.gaps,*receipt.gaps]) or
            any(r["line"] is None or r["disputed"] or r["kind"]=="serial_note" or r["kind"]=="substitution" and r not in notes for r in rows) or
            any(r["kind"]!="substitution" and r["unit"]!=(contract.unit if r["kind"] in ("ordered","ordered_serials") else receipt.unit) for r in rows)):
        return result("register_source","missing","设备清单有续页、附带条件、影像或待核抄录，请核对原件、铭牌及适用的交付约定。")
    if len(ordered)!=1 or len(received)!=1:
        return result("register_incomplete","missing","需取得唯一、完整的合同约定编号和本次终验实收编号清单。")
    groups = {kind:[split(r["quote"])[1] for r in rows if r["kind"]==kind] for kind in ("ordered","received")}
    def entries(row):
        return [item.strip() for item in re.split("[、，,]",split(row["quote"])[1])]
    left, right = entries(ordered[0]), entries(received[0])
    if (any(not serial(item) for item in [*left,*right]) or
            len(groups["ordered"])!=1 or len(groups["received"])!=1 or not count(groups["ordered"][0]) or
            count(groups["ordered"][0])!=len(left) or count(groups["received"][0])!=len(right) or len(left)!=len(right)):
        return result("register_incomplete","missing","至少一张清单的完整编号或与交付台数的对应关系待核，请核对逐台原始登记。")
    repeated = list(dict.fromkeys(i for values in (left,right) for i,n in Counter(values).items() if n>1))
    if repeated:
        return result("register_duplicate","risk","设备清单重复列示编号 "+"、".join(repeated)+"，需核对送货单和铭牌，确认各台设备的实际编号。")
    ordered_ids, received_ids = set(left), set(right)
    missing = [i for i in left if i not in received_ids]
    extra = [i for i in right if i not in ordered_ids]
    if notes:
        if len(notes)==1 and notes[0]["unit"]==contract.unit:
            label, wording = split(notes[0]["quote"])
            ban = NO_SUBSTITUTE.fullmatch(wording.strip())
            if label in ("供货约定","设备代用约定","交付约定") and ban and extra==[ban[1]] and missing==[ban[2]]:
                check["register"].update(contract_only=missing,receipt_only=extra)
                return result("register_prohibited","issue",f"合同明列不得以 {ban[1]} 代替 {ban[2]}，终验实收清单却列 {ban[1]}、缺 {ban[2]}。请核对铭牌、交接和后续变更原件。")
        return review_substitution()
    if missing:
        def codes(values):
            return {re.sub("[-._]", "", i).casefold() for i in values}
        if codes(missing)==codes(extra):
            return result("register_spelling","missing","两张清单的编号大小写或分隔符有差别，需按铭牌核实编码口径。")
        check["register"].update(contract_only=missing,receipt_only=extra)
        return result("register_difference","issue","合同列有 "+"、".join(missing)+"，终验清单另列 "+"、".join(extra)+
                      "，两份清单的设备编号不一致。请核对送货单、铭牌及可能的换货批准。")
    return result("register_match","ok",f"合同与终验清单列出的 {len(left)} 个完整设备编号逐一相符。")


def assess(graph, contract, receipts, *, complex_scope):
    ledger = graph.get("inspection_coverage_sources",{})
    rows = ledger.get("rows",[])
    if not rows:
        return None
    pages = ledger["pages"]
    scope = list(dict.fromkeys(p["unit"] for p in pages))
    evidence = [f"{p['doc']}/p{p['page']}" for p in pages]
    evidence.extend(ref for r in rows for ref in [r["id"],*r["facts"]])
    check = {"format":ledger["format"],"scope":scope,"evidence":list(dict.fromkeys(evidence)),"mode":None,"required":None,
             "declared":None,"equipment":[],"measurements":[],"tested":None,"limit":None}
    if ledger.get("purpose")==REGISTER:
        return delivery_register(graph,check,rows,pages,contract,receipts,complex_scope)
    def result(state,status,detail):
        return {**check,"state":state,"status":status,"detail":detail}
    if complex_scope or len(receipts)!=1 or set(scope)!={contract.unit,receipts[0].unit}:
        return result("scope","missing","需先确定逐台或抽检约定适用的合同版本、批次及本次验收原件。")
    receipt = receipts[0]
    from reinspection import LINK_KEYS, linked
    from contract_changes import labelled_sources
    from delegation import complete_id
    check["evidence"] = list(dict.fromkeys([*evidence,*contract.evidence(*LINK_KEYS),*receipt.evidence(*LINK_KEYS)]))
    if not (linked(contract,receipt) and complete_id(contract.body("contract_id")) and
            all(labelled_sources(m,LINK_KEYS) for m in (contract,receipt))):
        return result("identity","missing","检验记录的合同编号、双方名称和标的仍须与合同对应。")
    if (any(not p["native"] or not p["text_only"] for p in pages) or
            any(r["line"] is None or r["disputed"] for r in rows)):
        return result("source","missing","检验范围所据的原页含影像、异议或待定位字段，需逐页核对。")
    groups = defaultdict(list)
    for r in rows:
        groups[r["unit"],r["kind"]].append(r)
    def single(unit, kind):
        selected = groups[unit,kind]
        return split(selected[0]["quote"])[1] if len(selected)==1 else ""
    requirement = single(contract.unit,"inspection_requirement")
    ordered, received = count(single(contract.unit,"ordered")), count(single(receipt.unit,"received"))
    declared = count(single(receipt.unit,"tested_quantity"))
    devices = population(single(receipt.unit,"population"))
    check["declared"] = declared
    check["equipment"] = devices or []
    minimum = MINIMUM.fullmatch(requirement)
    if requirement in ALL:
        check.update(mode="all",required=ordered)
    elif minimum:
        check.update(mode="sample",required=int(minimum[1] or minimum[2]))
    supported = {contract.unit:{"inspection_requirement","ordered","ordered_serials","limit"},
                 receipt.unit:{"received","population","basis","tested_quantity","unit_temperature"}}
    if ledger["format"] != LEGACY:
        supported[contract.unit].add(NAMED)
    if not check["mode"] or any(r["kind"] not in supported[r["unit"]] for r in rows):
        return result("terms","missing","须核对检验方式、抽检数量及附加条件的完整原文。")
    if not ordered or ordered!=received or not check["required"] or check["required"]>ordered:
        return result("population","missing","合同数量、实际验收数量与本次应检台数尚未对应。")
    if groups[receipt.unit,"tested_quantity"] and (declared is None or declared>received):
        return result("count","missing","实测台数的记载重复、单位不明或超出本次验收范围。")
    spec = LIMIT.fullmatch(single(contract.unit,"limit"))
    basis = LIMIT.fullmatch(single(receipt.unit,"basis"))
    upper_limits = ("不高于","不超过","至多","≤")
    if (not spec or not basis or (spec[1] in upper_limits)!=(basis[1] in upper_limits)
            or Decimal(spec[2])!=Decimal(basis[2])):
        return result("criterion","missing","逐台读数需与合同和验收单上同一指标、单位及限值对应。")
    bound = Decimal(spec[2])
    upper = spec[1] in upper_limits
    check["limit"] = {"metric":"柜温","operator":"≤" if upper else "≥","value":spec[2],"unit":"℃"}
    tested = []
    for row in groups[receipt.unit,"unit_temperature"]:
        match = READING.fullmatch(split(row["quote"])[1])
        if not match or not serial(match[1].strip()):
            return result("reading","missing","单机记录的设备编号、测量指标、数值或单位待核。")
        code = match[1].strip()
        value = Decimal(match[2])
        tested.append(code)
        check["measurements"].append({"row":row["id"],"serial":code,"value":match[2],
                                      "within":value<=bound if upper else value>=bound})
    if not devices or len(devices)!=received:
        return result("population","missing","需将本次验收的设备清单与交付数量逐台对应。")
    if groups[contract.unit,"ordered_serials"]:
        agreed = population(single(contract.unit,"ordered_serials"))
        if not agreed or set(agreed)!=set(devices):
            return result("population","missing","合同所列设备编号与验收清单尚未逐台对应。")
    if set(tested)-set(devices):
        return result("identity","missing","单机记录中有编号未与这份验收清单对应。")
    named_rows = groups[contract.unit,NAMED]
    if named_rows:
        designated = population(single(contract.unit,NAMED))
        if (not designated or not set(designated).issubset(devices) or
                sum(p["unit"]==contract.unit for p in pages) != 1):
            return result("named_scope","missing","需将合同点名的完整设备编号与本次验收清单逐一对应。")
        measured_ids = set(tested)
        check["named"] = {"row":named_rows[0]["id"], "equipment":designated,
                          "missing":[code for code in designated if code not in measured_ids]}
    check["tested"] = len(set(tested))
    duplicates = {code for code,n in Counter(tested).items() if n>1}
    if any(not m["within"] and m["serial"] not in duplicates for m in check["measurements"]):
        return result("out_of_limit","issue","验收单所列单机柜温超出合同限值，需核对异常设备及后续整改、复验。")
    if duplicates:
        return result("repeated","risk","多条测温记录指向同一设备，重复记录按一台计，需核对其他设备和复测先后。")
    required = check["required"]
    if declared is not None and declared<check["tested"]:
        return result("count_conflict","risk",f"验收单记载实测 {declared} 台，单机记录却对应 {check['tested']} 台不同设备，需核对两处原文。")
    if declared is not None and declared<required:
        return result("short","risk",f"合同应检至少 {required} 台，验收单记载实际检测 {declared} 台，检测范围不足。")
    if len(tested)<required or (declared is not None and declared!=len(tested)):
        return result("records","missing",f"现有可对应的单机记录覆盖 {len(tested)} 台，需核对所报台数并补齐原始检验记录。")
    if named_rows:
        missing = check["named"]["missing"]
        if missing:
            return result("named_records","missing",f"已有 {len(tested)} 台的读数，合同点名的 {len(missing)} 台尚缺可对应的测温记录。")
        return result("covered","ok",f"{len(tested)} 台不同设备各有符合所列限值的测温记录，覆盖合同应检数量及点名的 {len(designated)} 台。")
    return result("covered","ok",f"合同应检至少 {required} 台，{len(tested)} 台不同设备各有符合所列限值的测温记录。")


def apply(finding,check):
    finding["inspection_coverage"] = check
    finding["scope"] = list(dict.fromkeys([*finding["scope"],*check["scope"]]))
    finding["evidence"] = list(dict.fromkeys([*finding["evidence"],*check["evidence"]]))
    if check.get("mode")==REGISTER:
        finding[REGISTER] = check["register"]["rows"]
    if finding["status"]=="ok" and check["status"]!="ok":
        finding["detail"] = check["detail"]
    else:
        finding["detail"] += " "+check["detail"]
    if SEVERITY[check["status"]]>SEVERITY[finding["status"]]:
        finding["status"] = check["status"]
    if check["status"]=="ok":
        return
    if finding.get("reinspection"):
        finding["reinspection"]["state"]="open"
    batch = finding.get("batch_acceptance")
    if batch:
        for item in [batch,*batch["batches"]]:
            if item["status"]=="ok":
                item.update(status="missing",detail=check["detail"])
            item["evidence"]=list(dict.fromkeys([*item["evidence"],*check["evidence"]]))
            item["scope"]=list(dict.fromkeys([*item.get("scope",[]),*check["scope"]]))
        for allocation in batch["batches"]:
            allocation["date"]=None
        final = batch.get("separate_final")
        if final and final["status"]=="ok":
            final.update(status="missing",detail=check["detail"])
        batch["completion_on"]=None


def check_legacy_approval(report,read_text,archived=None):
    from performance import compute
    graph = report["graph"]
    affected = {"H02","H04","H05"}
    positive = [f for f in report["findings"] if f["rule"] in affected and f["status"]=="ok"]
    if not positive:
        return
    current = sources(graph,read_text)
    if not current["rows"] or archived and current["rows"] == archived["rows"]:
        return
    items = compute({**graph,"inspection_coverage_sources":current})
    coverage = next((f["inspection_coverage"] for f in items if "inspection_coverage" in f),None)
    if coverage and coverage["status"]!="ok":
        def key(item):
            banks = set(graph["documents_by_kind"].get("bank_receipt",())) if item["rule"]=="H05" else set()
            return item["rule"],item.get("stage",{}).get("clause_ref"),tuple(sorted(banks.intersection(item["scope"])))
        statuses = {key(item):item["status"] for item in items if item["rule"] in affected}
        if any(statuses.get(key(f))!="ok" for f in positive):
            raise ValueError("旧版底稿尚未列明逐台或合同指定抽检范围的证据缺口，请按现行程序重新审计后签收。")


def verify(report,read_text,*,signing=False,read_original=None,read_layout=None):
    graph,policy = report["graph"],report["policy"]
    marker = policy.get("inspection_coverage")
    nodes = [n for n in graph["nodes"] if n["type"]=="inspection_line"]
    edges = [e for e in graph["edges"] if e["type"]=="inspection_coverage_source"]
    if not marker:
        if (policy.get("version","")>=SINCE or "inspection_coverage.py" in policy.get("code_sha256",{}) or
                "inspection_coverage_sources" in graph or nodes or edges or any("inspection_coverage" in f for f in report["findings"])):
            raise ValueError("逐台检验依据的程序标记缺失")
        if signing:
            check_legacy_approval(report,read_text)
        return
    version = policy.get("version","")
    expected = FORMAT if version >= SUBSTITUTION_SINCE else REGISTER_FORMAT if version >= REGISTER_SINCE else NAMED_FORMAT if version >= NAMED_SINCE else LEGACY
    if marker != expected:
        raise ValueError("逐台检验的程序版本标记与出具版本不符")
    ledger = sources(graph,read_text,version=marker)
    if graph.get("inspection_coverage_sources")!=ledger or (nodes,edges)!=source_graph(ledger):
        raise ValueError("逐台检验或抽检所据的原页、设备记录与归档不符")
    if signing and marker == LEGACY:
        check_legacy_approval(report,read_text,ledger)
    if signing and marker != FORMAT and any(f["rule"]=="H02" for f in report["findings"]):
        current = sources(graph,read_text)
        changed = marker!=REGISTER_FORMAT or current.get("rows")!=ledger["rows"]
        if current.get("purpose")==REGISTER and changed:
            from performance import compute
            rebuilt = compute({**graph,"inspection_coverage_sources":current})
            review = next((f["inspection_coverage"] for f in rebuilt if f.get("inspection_coverage")),None)
            saved = next(f for f in report["findings"] if f["rule"]=="H02").get("inspection_coverage") or {}
            if marker==REGISTER_FORMAT:
                if review and (review["state"]!=saved.get("state") or review.get("register")!=saved.get("register")):
                    raise ValueError("旧版设备清单未核对本次代用的约定或批准依据，请重审后签收。")
            elif review and review["status"]!="ok":
                raise ValueError("旧版验收未核实合同指定设备与终验编号清单，请重审后签收。")
    rows = register_rows(graph)
    if marker in REGISTER_FORMATS:
        expert = report.get("calls",{}).get("expert",{})
        if "input" in expert or expert.get("request_format"):
            packet = expert.get("input")
            issued = [(f["rule"],f[REGISTER]) for f in report["findings"] if REGISTER in f]
            if (not isinstance(packet,dict) or packet.get("delivery_register_sources") != (rows or None) or
                    [(f["rule"],f[REGISTER]) for f in packet.get("procedures",()) if REGISTER in f] != issued):
                raise ValueError("专家输入未保留出具底稿所据的合同与验收设备清单")
    calls = report.get("calls",{}).get("pages",())
    if calls or policy.get("archived_methods"):
        from contract_folios import line_numbers, verify_page_geometry
        verify_page_geometry(calls,line_numbers(rows),{},RECTS,"合同与验收设备清单",read_layout)
    if rows and read_original:
        from payment_quality import verify_units
        pages = {(p["doc"],p["page"]):p for p in calls}
        located = [{**r,"rects":pages[r["doc"],r["page"]][RECTS][str(r["line"])]} for r in rows if r["line"]]
        verify_units(graph,{p["unit"] for p in ledger["pages"]},read_original,"设备清单原件",extra_lines=located)
