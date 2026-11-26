"""Reconcile a contract's sampling requirement with identified equipment and individual readings."""

import hashlib
import re
from collections import Counter, defaultdict
from decimal import Decimal

LEGACY = "inspection-coverage-v1"
FORMAT = "inspection-coverage-v2"
SINCE = "2026.11.26.04"
NAMED_SINCE = "2026.11.26.19"
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
READING = re.compile(r"([^，,]+)[，,]\s*柜温\s*("+NUMBER+r")\s*(?:℃|°C)")
SEVERITY = {"ok":0,"missing":1,"risk":2,"issue":3}


def split(quote):
    parts = re.split("[:：]", quote, maxsplit=1)
    return parts[0].strip(), parts[1].strip() if len(parts)==2 else ""


def classify(quote, field=None, *, version=FORMAT):
    label, _ = split(quote)
    kind = FIELDS.get(label) or AUXILIARY.get(label)
    if kind and (kind != NAMED or version == FORMAT):
        return kind
    if (field in LABELS and field != NAMED) or HINT.search(quote):
        return "note"
    if version == FORMAT and (field == NAMED or NAMED_HINT.search(quote)):
        return "note"


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
        for number, raw in enumerate(lines,1):
            kind = classify(raw,version=version)
            if following_named and raw.strip() and not re.search("[:：]",raw):
                kind = "note"
            if raw.strip():
                following_named = kind == NAMED or (following_named and kind == "note")
            if kind:
                facts = located[number,raw]
                rows.append({**place,"id":f"inspection-line/{doc}/p{page}/l{number}","line":number,"kind":kind,
                             "quote":raw,"facts":[f["id"] for f in facts],"disputed":any(f["status"]=="disputed" for f in facts)})
    triggered = any(r["kind"] in (*LABELS,"note") for r in rows)
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
    if ledger["format"] == FORMAT:
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


def verify(report,read_text,*,signing=False):
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
    expected = FORMAT if policy.get("version","") >= NAMED_SINCE else LEGACY
    if marker != expected:
        raise ValueError("逐台检验的程序版本标记与出具版本不符")
    ledger = sources(graph,read_text,version=marker)
    if graph.get("inspection_coverage_sources")!=ledger or (nodes,edges)!=source_graph(ledger):
        raise ValueError("逐台检验或抽检所据的原页、设备记录与归档不符")
    if signing and marker == LEGACY:
        check_legacy_approval(report,read_text,ledger)
