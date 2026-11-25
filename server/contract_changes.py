"""Resolve one expressly prospective change to an acceptance limit from the cited originals."""

import hashlib
import re
import unicodedata
from collections import defaultdict

from calculations import normalized
from delegation import PARTY_SIGNATURES, complete_id, covered_rows
from performance_versions import ADDENDUM_FORMATS
from quality_references import incomplete_number


import payment_amendments


LEGACY = "acceptance-addendum-v1"
QUANTITY_FORMAT = "acceptance-addendum-v2"
PRINTED_DATES = "acceptance-addendum-v3"
FORMAT = "contract-addendum-v4"
DATED_FORMATS = (PRINTED_DATES, FORMAT)
QUANTITY_FORMATS = (QUANTITY_FORMAT, *DATED_FORMATS)
QUANTITY_FIELDS = {"previous_quantity": ("原交付数量", "变更前交付数量"),
                   "revised_quantity": ("变更后交付数量", "调整后交付数量")}
TITLES = ("补充协议", "合同补充协议", "采购合同补充协议", "验收标准变更协议", "采购合同变更协议")
LABELS = {
    **QUANTITY_FIELDS,
    **payment_amendments.LABELS,
    "addendum_number": ("补充协议编号", "变更协议编号"),
    "base_contract_ref": ("原合同编号", "原采购合同编号"),
    "change_scope": ("变更范围", "协议变更范围"),
    "previous_criterion": ("原验收标准",),
    "revised_criterion": ("变更后验收标准", "新验收标准"),
    "change_timing": ("变更适用时点", "验收标准适用时点"),
    "change_effect_clause": ("协议生效条款", "补充协议生效条款"),
    "buyer_sealed_on": ("甲方盖章日期",),
    "seller_sealed_on": ("乙方盖章日期",),
    "change_state": ("补充协议状态", "变更协议状态"),
}
PRINTED = {**LABELS, **PARTY_SIGNATURES, "buyer":("采购方","甲方","买方"), "seller":("供应方","乙方","卖方"),
           "subject":("采购标的","项目名称","标的名称","货物名称")}
FIELDS = ("contract_addendum", *PRINTED)
NUMBER_TYPES = {"addendum_number":"addendum_number", "base_contract_ref":"contract_number"}
SIGNAL = re.compile(r"补充协议|变更协议|原验收标准|变更后验收标准|新验收标准|验收标准.{0,6}(?:另行|变更|修订)")
QUANTITY_SIGNAL = re.compile(r"原交付数量|变更前交付数量|(?:变更|调整)后交付数量|(?:变更|调整)交付数量")
QUANTITY_NOTE = re.compile(r"短交|欠交|少交|尚欠|未齐套|未到货|未交齐|尚未交付|数量待(?:清点|核)"
                           r"|(?:其余|剩余|余下).{0,12}(?:后送|补交|补送|待交)|另行补交"
                           r"|^(?:交付备注|数量备注|数量说明|实收说明|实收备注|交货备注):(?!无[。.]?$)")
QUANTITY_SCOPE = {"仅变更交付数量,合同总价及其余条款不变", "仅变更交付数量,合同总价、验收标准及付款条款不变"}
QUANTITY = re.compile(r"([1-9][0-9]{0,8})[ \t]*(台|件|套|个|箱|辆|把|张|组|套件)")
QUANTITY_LABELS = {**QUANTITY_FIELDS, "quantity_agreed": ("约定交付数量", "合同交付数量"),
                   "quantity_accepted": ("实际验收数量", "验收数量")}
CONTRACT_NUMBER = re.compile(r"(?:合同(?:编)?号|协议编号)")
LIMIT = re.compile(r"([\u4e00-\u9fff]{1,16}?)(不高于|不超过|不低于|至少|至多|≤|≥)(-?\d{1,12}(?:\.\d{1,6})?)(°C|mm|cm|kg|MPa|kPa|%)")
SCOPES = {"仅变更验收标准,其余条款不变", "仅变更验收标准,合同其余条款不变"}
TIMING = {"仅适用于本协议生效后进行的验收", "仅适用于本协议生效后的验收"}
SEALS = {"本协议自双方盖章之日起生效", "本补充协议自双方盖章之日起生效"}
SOURCE_LABELS = {**PRINTED, "contract_id":("合同编号","合同号"),"acceptance_criteria":("约定验收标准","合同验收标准"),
                 "signed_on":("签约日期","签订日期","签署日期"),"effect_on":("实际生效日期","生效确认日期"),
                 "valid_until":("合同有效期至","合同有效截止日"),"accepted_on":("验收日期","验收时间"),
                 "acceptance_scope":("验收范围","验收批次","验收阶段"),"inspection_basis":("检验依据","实测验收标准","实际验收标准"),
                 "measured_result":("实测结果","检测结果","实测数据")}


def printed_value(field, value, quote):
    line, value = normalized(quote), normalized(value)
    if field=="contract_addendum":
        return value if value==line and line in TITLES else ""
    label, separator, body = line.partition(":")
    if separator and label in PRINTED.get(field, ()) and value in (line,body):
        return body
    return ""


def number_target(field, value, quote, ref):
    body = printed_value(field,value,quote)
    raw = unicodedata.normalize("NFKC",quote).partition(":")[2].strip()
    if not complete_id(body) or re.search(r"\s",raw):
        return ref, None
    kind = NUMBER_TYPES[field]
    return kind+"-"+hashlib.sha256(body.encode()).hexdigest()[:18], body


def labelled_sources(material, fields):
    for field in fields:
        for fact in material.fields[field]:
            line = normalized(fact["quote"])
            label,sep,body = line.partition(":")
            if not sep or label not in SOURCE_LABELS[field] or normalized(fact["value"]) not in (line,body):
                return False
            originals = [fact["quote"], (fact.get("source_line") or {}).get("text","")]
            for source in originals:
                raw = unicodedata.normalize("NFKC",source).partition(":")[2].strip()
                if field in ("contract_id",*NUMBER_TYPES) and re.search(r"\s",raw):
                    return False
                if field in ("acceptance_criteria","previous_criterion","revised_criterion","inspection_basis","measured_result") and re.search(r"[-+.\d]\s+(?=[.\d])",raw):
                    return False
    return True


def page_signals(graph, read_text, version=FORMAT):
    """Find mentions even when the visual transcriber omitted or misclassified a title."""
    pages = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    sections = {(d["source"],d["page"]):d["id"] for d in graph.get("audit_documents",[]) if "source" in d}
    signals, limited = [], []
    quantity_lines, quantity_pages, identity_lines = [], [], []
    kinds = {unit: kind for kind in ("contract","contract_addendum","acceptance","reinspection")
             for unit in graph["documents_by_kind"].get(kind,[])}
    fields = {label: field for field,labels in QUANTITY_LABELS.items() for label in labels}
    identity = {label: field for field in ("buyer","seller","subject","contract_id","base_contract_ref","addendum_number",
                "signed_on","effect_on","valid_until","accepted_on","buyer_sealed_on","seller_sealed_on")
                for label in SOURCE_LABELS[field]}
    anchors = defaultdict(list)
    if version in QUANTITY_FORMATS:
        for fact in graph["facts"]:
            loc = fact.get("source_line") or {}
            if loc.get("rects") and loc["text"] == fact["quote"]:
                anchors[fact["doc"],fact["page"],loc["number"],loc["text"]].append(fact["id"])
    quantity_seen = False
    for ref, page in pages.items():
        doc, page_number = ref.rsplit("/p",1)
        number = int(page_number)
        place = {"doc":doc,"page":number,"unit":sections.get((doc,number),doc)}
        if version in QUANTITY_FORMATS and place["unit"] in kinds:
            quantity_pages.append({**place,"native":page.get("layer")=="text","text_only":page.get("clause_text_only") is True})
        if page.get("layer")!="text":
            continue
        source = read_text(doc,number)
        if not isinstance(source,str) or hashlib.sha256(source.encode()).hexdigest()!=page.get("text_sha256"):
            raise ValueError("核对补充协议时原页文字摘要与归档不符")
        for i, raw in enumerate(source.splitlines(),1):
            line = normalized(raw)
            observed = {**place,"line":i,"quote":raw}
            quantity_signal = version in QUANTITY_FORMATS and QUANTITY_SIGNAL.search(line)
            if quantity_signal:
                quantity_seen = True
            if SIGNAL.search(line) or quantity_signal:
                signals.append(observed)
            printed_label,_,printed_body = unicodedata.normalize("NFKC",raw).partition(":")
            if version in QUANTITY_FORMATS and place["unit"] in kinds:
                field = fields.get(printed_label.strip())
                if field or QUANTITY_NOTE.search(line):
                    quantity_lines.append({**observed,"field":field or "quantity_note",
                                           "facts":anchors[doc,number,i,raw]})
                key = identity.get(printed_label.strip())
                if key:
                    identity_lines.append({**observed,"field":key,"facts":anchors[doc,number,i,raw]})
            separated = normalized(printed_label) in (*LABELS["base_contract_ref"],*LABELS["addendum_number"],"合同编号","合同号") and re.search(r"\s",printed_body.strip())
            if CONTRACT_NUMBER.search(line) and (incomplete_number(line) or separated):
                limited.append(observed)
    for f in graph["facts"]:
        if version in QUANTITY_FORMATS and (f["field"] in QUANTITY_FIELDS or QUANTITY_SIGNAL.search(normalized(f["quote"]))):
            quantity_seen = True
        if pages[f"{f['doc']}/p{f['page']}"].get("layer")!="text" and CONTRACT_NUMBER.search(normalized(f["quote"])) and incomplete_number(f["quote"]):
            limited.append({"doc":f["doc"],"page":f["page"],"unit":f.get("unit",f["doc"]),"fact":f["id"],"quote":f["quote"]})
    quantity = {"lines":quantity_lines,"pages":quantity_pages,"identities":identity_lines} if quantity_seen else None
    return signals, limited, quantity


def observed_units(graph):
    from contract_effect import FORMAT as SEAL_FORMAT
    originals=set(graph["documents_by_kind"].get("contract",[])) if graph.get("contract_effect_sources",{}).get("format")==SEAL_FORMAT else set()
    current = graph.get("quality_addenda",{}).get("format") in QUANTITY_FORMATS
    return {f.get("unit",f["doc"]) for f in graph["facts"] if (f["field"] in LABELS and (current or f["field"] not in QUANTITY_FIELDS) and not
            (f["field"] in ("buyer_sealed_on","seller_sealed_on") and f.get("unit",f["doc"]) in originals)) or f["field"]=="contract_addendum"
            or SIGNAL.search(normalized(f["quote"])) or current and QUANTITY_SIGNAL.search(normalized(f["quote"]))}


def ledger(graph, read_text, version=FORMAT):
    units = set(graph["documents_by_kind"].get("contract_addendum",[]))
    nodes = {n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    fields = [f for f in FIELDS if (version==FORMAT or f not in payment_amendments.LABELS)
              and (version in QUANTITY_FORMATS or f not in QUANTITY_FIELDS)]
    pages = covered_rows(graph,read_text,units,fields,printed_value,"补充协议")
    for p in pages:
        p["text_only"] = nodes[f"{p['doc']}/p{p['page']}"].get("clause_text_only") is True
    signals, limited, quantity = page_signals(graph,read_text,version)
    result = {"format":version, "signals":signals,"limited_numbers":limited,"pages":pages}
    if version==FORMAT:
        payments = payment_amendments.sources(graph,read_text)
        if payments:
            result["payments"] = payments
    if quantity:
        result["quantities"] = quantity
    return result


def quantity_edges(coverage):
    return [{"type":"delivery_quantity_basis","from":line["unit"],"to":f"{line['doc']}/p{line['page']}",
             "line":line["line"],"evidence":[f"{line['doc']}/p{line['page']}",*line["facts"]]}
            for line in coverage.get("quantities",{}).get("lines",[])]


def gaps(coverage):
    return [{"id":f"{p['doc']}/p{p['page']}", "doc":p["doc"], "page":p["page"], "quality":"addendum_clause",
             "field":"change_scope", **line} for p in coverage["pages"] for line in p["uncovered"]]


def attach(graph, read_text):
    coverage = ledger(graph,read_text)
    graph["quality_addenda"] = coverage
    graph["edges"].extend(quantity_edges(coverage))
    graph["edges"].extend(payment_amendments.edges(coverage.get("payments")))
    graph["gaps"].extend(gaps(coverage))
    allowed = fully_read_units(coverage)
    removed = set()
    for edge in graph["edges"]:
        if edge["type"] in NUMBER_TYPES and edge["from"] not in allowed:
            ref, = edge["evidence"]
            if edge["to"]!=ref:
                removed.add(edge["to"])
                edge["to"] = ref
    unused = removed - {edge["to"] for edge in graph["edges"]}
    graph["nodes"] = [n for n in graph["nodes"] if n["id"] not in unused]


def fully_read_units(coverage):
    pages = coverage["pages"]
    if coverage["limited_numbers"]:
        return set()
    return {p["unit"] for p in pages} - {p["unit"] for p in pages if not p["native"] or not p["text_only"] or p["uncovered"]}


def verify_sources(report, read_text, *, signing=False):
    policy, graph = report["policy"], report["graph"]
    if not policy.get("quality_addenda"):
        if ("contract_changes.py" in policy.get("code_sha256",{}) or "quality_addenda" in graph
                or policy.get("performance_checks") in ADDENDUM_FORMATS):
            raise ValueError("缺少对应的补充协议核对程序")
        if signing and any(f["rule"]=="H02" and f["status"]=="ok" for f in report["findings"]):
            signals, _, quantity = page_signals(graph,read_text)
            if observed_units(graph) or signals or quantity:
                raise ValueError("旧版终验底稿存在补充协议线索，请按现行程序复核适用标准后签收。")
        return
    marker = policy["quality_addenda"]
    current = ledger(graph,read_text,marker)
    version=policy.get("version","")
    if (marker not in (LEGACY,*QUANTITY_FORMATS) or "2026.11.25.06"<=version<"2026.11.25.20" and marker!=QUANTITY_FORMAT
            or "2026.11.25.20"<=version<payment_amendments.SINCE and marker!=PRINTED_DATES
            or (version>=payment_amendments.SINCE or "payment_amendments.py" in policy.get("code_sha256",{})) and marker!=FORMAT
            or policy.get("performance_checks") not in ADDENDUM_FORMATS
            or graph.get("quality_addenda")!=current or gaps(current)!=[g for g in graph["gaps"] if g["quality"]=="addendum_clause"]):
        raise ValueError("补充协议的原页、变更条款或未覆盖的约定与底稿不符")
    if [e for e in graph["edges"] if e["type"]=="delivery_quantity_basis"] != quantity_edges(current):
        raise ValueError("变更前后交付数量及验收数量的原页关系与底稿不符")
    if signing and marker == LEGACY and any(f["rule"]=="H02" and f["status"]=="ok" for f in report["findings"]):
        if page_signals(graph,read_text)[2]:
            raise ValueError("旧版终验有交付数量变更线索，请按现行程序重审后签收。")
    if [e for e in graph["edges"] if e["type"]=="payment_amendment_basis"] != payment_amendments.edges(current.get("payments")):
        raise ValueError("补充协议与原付款条款、所据原行的图谱关系不符")
    if signing and marker not in DATED_FORMATS:
        from performance import Material, printed_day
        for finding in report["findings"]:
            change=finding.get("quality_change")
            if not change or change["state"] not in ("original","applied","by_batch"):
                continue
            contracts=graph["documents_by_kind"].get("contract",[])
            receipts=graph["documents_by_kind"].get("acceptance",[])
            dates=[(u,k) for u in contracts for k in ("signed_on","effect_on")]
            dates.extend((u,k) for u in change["units"] for k in ("buyer_sealed_on","seller_sealed_on"))
            if change.get("accepted_on"):
                dates.extend((u,"accepted_on") for u in receipts)
            materials={u:Material(graph,u) for u in {unit for unit,_ in dates}}
            dates.extend((u,"valid_until") for u in contracts if materials[u].fields["valid_until"] or "valid_until" in materials[u].uncertain)
            if any(not printed_day(materials[u],field) for u,field in dates):
                raise ValueError("该版所据签署或验收日期需逐字核对，请用现行程序重审后签收。")
    nodes = {n["id"]:n for n in graph["nodes"]}
    expected = []
    allowed = fully_read_units(current)
    for f in graph["facts"]:
        if f["field"] not in NUMBER_TYPES or f["status"] not in ("anchored","confirmed"):
            continue
        target, body = number_target(f["field"],f["value"],f["quote"],f["id"])
        if f.get("unit",f["doc"]) not in allowed:
            target,body = f["id"],None
        if body and (nodes.get(target,{}).get("type")!=NUMBER_TYPES[f["field"]] or normalized(nodes[target]["label"])!=body):
            raise ValueError("补充协议所引编号与图谱实体不符")
        expected.append((f.get("unit",f["doc"]),target,f["field"],(f["id"],)))
    actual = [(e["from"],e["to"],e["type"],tuple(e["evidence"])) for e in graph["edges"] if e["type"] in NUMBER_TYPES]
    if sorted(expected)!=sorted(actual):
        raise ValueError("补充协议的编号关系与原件归属不符")


def candidates(graph):
    units = observed_units(graph) | {s["unit"] for s in graph.get("quality_addenda",{}).get("signals",[])}
    units.update(graph["documents_by_kind"].get("contract_addendum",[]))
    return sorted(units)


def exact_body(material, field, rows):
    printed = [r for r in rows if r["unit"] == material.unit and r["field"] == field]
    facts = material.fields[field]
    if len(printed) != 1 or len(facts) != 1 or material.incomplete(field):
        return None
    row, fact = printed[0], facts[0]
    body = unicodedata.normalize("NFKC",row["quote"]).partition(":")[2].strip()
    if fact["id"] not in row["facts"] or material.body(field) != normalized(body):
        return None
    return body


def supported_quantity(material, field, rows):
    match = QUANTITY.fullmatch(exact_body(material,field,rows) or "")
    return {"count":int(match[1]), "unit":match[2]} if match else None


def quantity_identity(contract, other, fields, originals):
    for key in fields:
        body = exact_body(contract,key,originals)
        other_key = "base_contract_ref" if key=="contract_id" and other.unit!=contract.unit and other.fields["contract_addendum"] else key
        if (not body or re.search(r"[＊*×□…]|待定|待填|同上|同(?:主)?合同|不详|仅列尾号",body)
                or body!=exact_body(other,other_key,originals)):
            return False
    return True


def exact_date(material, field, originals):
    raw = exact_body(material,field,originals) or ""
    return material.date(field) if not re.search(r"\d\s+\d",raw) and raw else None


def quantities(coverage, contract, changes, receipts):
    units = {doc.unit for doc in [contract,*changes,*receipts]}
    rows = [r for r in coverage["lines"] if r["unit"] in units]
    pages = [p for p in coverage["pages"] if p["unit"] in units]
    change = changes[0] if len(changes)==1 else None
    receipt = receipts[0] if len(receipts)==1 else None
    return {"original":supported_quantity(contract,"quantity_agreed",rows),
            "previous":supported_quantity(change,"previous_quantity",rows) if change else None,
            "revised":supported_quantity(change,"revised_quantity",rows) if change else None,
            "accepted":supported_quantity(receipt,"quantity_accepted",rows) if receipt else None,
            "applicable":None, "difference":None, "pages":pages, "lines":rows}


def resolve(graph, contract, changes, receipts, *, multiple_events, contract_supported, unclassified):
    # Dates and criteria collected here are included in the reproducible workpaper.
    old = contract.body("acceptance_criteria")
    refs = contract.evidence("contract","contract_id","subject","buyer","seller","acceptance_criteria","signed_on","effect_on","valid_until")
    ledger = graph.get("quality_addenda",{})
    for doc in changes:
        refs.extend(f["id"] for f in doc.refs)
    refs.extend(f"{s['doc']}/p{s['page']}" for s in ledger.get("signals",[]))
    refs.extend(s.get("fact") or f"{s['doc']}/p{s['page']}" for s in ledger.get("limited_numbers",[]))
    for receipt in receipts:
        refs.extend(receipt.evidence("accepted_on","inspection_basis","measured_result"))
    quantity_sources = ledger.get("quantities")
    def dated(material,field):
        if quantity_sources:
            return exact_date(material,field,quantity_sources["identities"])
        if ledger.get("format") in DATED_FORMATS:
            from performance import printed_day
            return printed_day(material,field)
        return material.date(field)
    receipt_date = dated(receipts[0],"accepted_on") if len(receipts)==1 else None
    dates = {"accepted_on":receipt_date.isoformat() if receipt_date else None,
             "buyer_sealed_on":None,"seller_sealed_on":None,"effective_on":None}
    entry = {"state":"pending","scope_clear":False,"original_criterion":old or None,"revised_criterion":None,
             "applied_criterion":None,"units":[d.unit for d in changes],"evidence":list(dict.fromkeys(refs))}
    quantity = None
    if quantity_sources:
        quantity = quantities(quantity_sources,contract,changes,receipts)
        entry["quantity"] = quantity
        pages = [f"{p['doc']}/p{p['page']}" for p in quantity["pages"]]
        facts = [ref for line in quantity["lines"] for ref in line["facts"]]
        entry["evidence"] = list(dict.fromkeys([*refs,*pages,*facts]))
    def decision(detail, state="pending", criterion=None):
        return {**entry, **dates, "state":state, "detail":detail, "applied_criterion":criterion}

    if ledger.get("payments"):
        return decision("补充协议涉及付款前提，须核对其范围、适用期次及双方签署的完整约定。")
    if len(changes)!=1 or changes[0].unit not in graph["documents_by_kind"].get("contract_addendum",[]):
        return decision("存在其他变更线索或多个版本，请核对补充协议全文、原合同和各次签署的对应关系。")
    change, = changes
    revised = change.body("revised_criterion")
    entry["revised_criterion"] = revised or None
    buyer_day, seller_day = (dated(change,key) for key in ("buyer_sealed_on","seller_sealed_on"))
    dates.update(buyer_sealed_on=buyer_day.isoformat() if buyer_day else None, seller_sealed_on=seller_day.isoformat() if seller_day else None)
    if ledger.get("limited_numbers"):
        return decision("资料中的合同或协议编号有遮盖、分隔或仅显示部分号码的记载，请核对完整编号与原件归属。")
    if not labelled_sources(contract,("contract_id","buyer","seller","subject","signed_on","effect_on","valid_until","acceptance_criteria")):
        return decision("原合同的编号、合同双方、标准或日期尚需对照完整的原页字段。")
    if not (labelled_sources(change,("addendum_number","base_contract_ref","previous_criterion","revised_criterion"))
            and complete_id(change.body("addendum_number")) and complete_id(change.body("base_contract_ref"))
            and change.body("base_contract_ref")==contract.single("contract_id")
            and all(contract.single(k) and contract.single(k)==change.body(k) for k in ("buyer","seller","subject"))
            and contract.single("buyer")!=contract.single("seller")):
        return decision("补充协议的编号、所引原合同、双方或标的未能唯一对应，请核对原件归属。")
    pages = [p for p in ledger.get("pages",[]) if p["unit"]==change.unit]
    scope = change.body("change_scope")
    if (unclassified or not pages or any(not p["native"] or not p["text_only"] or p["uncovered"] for p in pages)
            or scope not in (QUANTITY_SCOPE if quantity else SCOPES) or change.incomplete(*FIELDS)):
        return decision("补充协议的变更范围、全部原页或其他附件尚待核对，付款条款也需复查。")
    if quantity:
        identities = quantity_sources["identities"]
        parties = ("contract_id","buyer","seller","subject")
        if (not quantity_identity(contract,change,parties,identities) or
                any((not p["native"] or not p["text_only"]) and p["unit"] in (contract.unit,change.unit)
                    for p in quantity["pages"])):
            return decision("须核实主合同及协议原行的完整编号、双方、交付标的及影像条款。")
        before, after = quantity["previous"], quantity["revised"]
        if change.fields["previous_criterion"] or change.fields["revised_criterion"]:
            return decision("协议声明仅变更数量，同时列有验收标准变更，请核实完整范围及付款约定。")
        if not before or not after or before!=quantity["original"] or before["unit"]!=after["unit"] or before==after:
            return decision("请核对主合同数量与协议原数量、变更后数量及完整计量单位。")
    else:
        first, second = LIMIT.fullmatch(old), LIMIT.fullmatch(revised)
        if not (first and second and first[1]==second[1] and first[4]==second[4] and change.body("previous_criterion")==old):
            return decision("请对照原合同核对修改前后的约定、实测指标和计量单位。")
    if change.body("change_timing") not in TIMING or change.body("change_effect_clause") not in SEALS:
        return decision("需核对补充协议约定的生效条件、适用时点及是否涉及既往验收。")
    state = change.body("change_state")
    if change.fields["change_state"] and state not in {"已签署","已生效","草案","草稿","待签署","未签署"}:
        return decision("补充协议记载的状态或附带条件需逐项核对。")
    for side,date_value in (("buyer",buyer_day),("seller",seller_day)):
        signature = change.body(side+"_signature")
        if (change.fields[side+"_signature"] and signature not in {
                contract.body(side)+"(已盖章)",contract.body(side)+"已盖章","待盖章","未盖章"}
                or change.fields[side+"_sealed_on"] and not date_value):
            return decision("补充协议签署栏或日期栏的完整记载仍有待辨，请核对各项附注。")
    entry["scope_clear"] = True
    if state in {"草案","草稿","待签署","未签署"}:
        return decision("补充协议记载的状态为“"+state+"”，请核对双方最终签署的生效文本。")
    if not (contract_supported and change.signed("buyer_signature",contract.body("buyer"),"seal")
            and change.signed("seller_signature",contract.body("seller"),"seal") and buyer_day and seller_day):
        return decision("需分别核对原合同生效依据、补充协议双方签章原页和各自的盖章日期。")
    effective = max(buyer_day,seller_day)
    signed, base_effect, expiry = (dated(contract,k) for k in ("signed_on","effect_on","valid_until"))
    expiry_printed = (quantity and any(r["unit"]==contract.unit and r["field"]=="valid_until" for r in identities)
                      or ledger.get("format") in DATED_FORMATS and (contract.fields["valid_until"] or "valid_until" in contract.uncertain))
    if expiry_printed and not expiry:
        return decision("原合同列有待辨的有效截止日，须核对协议生效时的合同期间。")
    if not signed or not base_effect or min(buyer_day,seller_day)<max(signed,base_effect) or expiry and effective>expiry:
        return decision("补充协议签章与原合同生效、有效期间的先后仍待核对。")
    dates["effective_on"] = effective.isoformat()
    if multiple_events or not receipt_date:
        return decision("须逐次对应验收、整改及复验的交付数量和原始日期。" if quantity else
                        "需逐次对应验收、整改和复验的日期、实测结果与当时标准。")
    receipt, = receipts
    if (not labelled_sources(receipt,("contract_id","buyer","seller","subject","accepted_on","acceptance_scope","inspection_basis","measured_result"))
            or any(not contract.single(k) or contract.single(k)!=receipt.single(k) for k in ("contract_id","buyer","subject"))
            or receipt.fields["seller"] and contract.single("seller")!=receipt.single("seller")
            or receipt.body("acceptance_scope") not in {"全部交付终验","全部交付最终验收","全部标的最终验收","最终验收","终验"}):
        return decision("需先确定同一原合同、采购方和标的所对应的最终验收记录，再选用该次验收的标准。")
    if receipt_date==effective:
        return decision("验收日与双方完成盖章为同一天，需核对签章和验收的具体时分。")
    if quantity:
        prior = receipt_date < effective
        applicable = quantity["previous" if prior else "revised"]
        accepted = quantity["accepted"]
        if not quantity_identity(contract,receipt,parties,identities):
            return decision("须逐份核实主合同、补充协议及终验原行的完整编号、双方和交付标的。")
        if (any(not p["native"] or not p["text_only"] for p in quantity["pages"])
                or any(r["field"]=="quantity_note" for r in quantity["lines"])):
            return decision("原页另有数量限制或影像附注，须核实此次验收实际覆盖的交付数量。")
        quantity["applicable"] = applicable
        if accepted and accepted["unit"]==applicable["unit"]:
            quantity["difference"] = accepted["count"]-applicable["count"]
        when = "早于" if prior else "晚于"
        source = "原合同" if prior else "补充协议"
        detail = f"终验日 {receipt_date} {when}协议生效日 {effective}，本次按{source}所列数量核对。"
        return decision(detail, "original" if prior else "applied")
    if receipt_date<effective:
        return decision(f"终验日 {receipt_date} 早于双方完成盖章日 {effective}。协议明确仅适用于生效后的验收，本次按原标准核对。","original",old)
    return decision(f"双方于 {effective} 完成盖章，协议明确适用于其后验收。终验日为 {receipt_date}，本次按变更后的标准核对。","applied",revised)
