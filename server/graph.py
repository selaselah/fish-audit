import hashlib
import re
import unicodedata
from collections import defaultdict

from model import FIELDS


KINDS = {"invoice": "发票", "contract": "合同", "acceptance": "验收单"}
TITLE_FIELDS = {**KINDS, "claim": "报销"}
PRINTED_TITLES = {label: field for field, labels in {
    "invoice": ("发票", "采购发票", "住宿服务发票", "增值税专用发票", "增值税普通发票", "增值税电子普通发票",
                "电子发票(普通发票)", "电子发票(增值税专用发票)"),
    "contract": ("采购合同", "设备采购合同", "购销合同", "采购协议"),
    "acceptance": ("验收单", "到货验收单", "验收报告", "采购验收单", "设备验收单"),
    "claim": ("报销单", "差旅报销单", "差旅费报销单", "费用报销单"),
}.items() for label in labels}
LABELS = {
    "buyer": ("采购方", "购方", "购买方", "甲方", "买方", "需方", "采购单位", "验收单位"),
    "seller": ("供应方", "销方", "销售方", "乙方", "卖方", "供方", "供应商", "供货单位"),
    "contract_id": ("合同编号", "合同号"), "invoice_id": ("发票号码", "票据号码", "发票号"),
    "net": ("不含税金额", "不含税合计", "不含税价款", "金额合计"),
    "tax": ("税额", "税款"), "total": ("价税合计", "含税总额", "含税总价", "含税金额", "含税合计"),
    "currency": ("币种", "货币种类", "结算货币"),
    "unit": ("金额单位", "计价单位", "金额单位为"),
    "issued_on": ("开票日期", "开具日期"), "signed_on": ("签约日期", "签订日期", "签署日期"),
    "accepted_on": ("验收日期", "验收时间"),
    "acceptance_result": ("验收结果", "验收结论"),
    "subject": ("采购标的", "标的名称", "项目名称", "货物名称", "商品名称", "品名"),
    "payment_term": ("结算条款", "付款条款", "付款方式", "结算方式", "支付条件", "付款条件", "结算条件"),
    "adjustment": ("变更", "红冲", "冲销", "补充协议", "红字"),
    "claim_total": ("申请报销金额", "申请报销总额", "报销合计"),
    "traveler": ("出差人员", "出差人", "旅客姓名", "乘车人", "入住人"),
    "trip_start": ("出差开始日期", "出差起始日期"), "trip_end": ("出差结束日期", "出差截止日期"),
    "service_on": ("费用发生日期", "乘车日期", "消费日期", "住宿日期"),
    "claim_ref": ("随附发票号码", "附件票号", "报销所附票号"),
}
SCALAR = {"contract_id", "invoice_id", "net", "tax", "total", "buyer", "seller", "signed_on",
          "accepted_on", "issued_on", "acceptance_result", "subject", "currency", "unit", "payment_term",
          "claim_total", "traveler", "trip_start", "trip_end", "service_on", "claim_ref"}
FIELD_START = {field: re.compile(r"^(?:" + "|".join(sorted(LABELS[field], key=len, reverse=True)) + r")[:(（]")
               for field in SCALAR}
TERMS = re.compile(r"分期|预付|质保金|保留款|分批|定金|订金|尾款|部分交付|红字|冲销|红冲|变更单|补充协议")


def compact(value):
    return "".join(unicodedata.normalize("NFKC", value).split())


def index_lines(raw_text):
    positions = {}
    for index, line in enumerate(raw_text.splitlines(), 1):
        text = compact(line).strip("。;；")
        positions[text] = None if text in positions else (index, line)
    return positions


def labelled(field, value, quote):
    value, quote = compact(value), compact(quote)
    if field in TITLE_FIELDS:
        word = "验收" if field == "acceptance" else TITLE_FIELDS[field]
        return value == quote and word in value and len(value) <= 48 and not any(
            label in value for label in ("号码", "编号", "结论", "日期", "参见", "附录", "附件清单", "提交", "缺少"))
    if field == "other":
        return False
    if field == "total" and any(token in quote for token in ("不含税", "未税", "单价")):
        return False
    terms = LABELS[field]
    if field == "payment_term" and value == quote:
        return any(word in value for word in ("付款", "结算", "支付", "预付", "质保金"))
    if field not in SCALAR:
        return any(term in quote for term in terms)
    for term in terms:
        prefix, found, suffix = quote.partition(term)
        if not found:
            continue
        if prefix:
            continue
        suffix = suffix.strip(":").rstrip("。;；")
        if field in {"total", "net", "tax", "claim_total"}:
            suffix = re.sub(r"^(?:\(小写\)|小写|合计|:|人民币|CNY|[￥¥])+", "", suffix)
            suffix = suffix.removesuffix("元")
        if suffix == value:
            return True
    return False


def entity_id(kind, value):
    return kind + "-" + hashlib.sha256(compact(value).encode()).hexdigest()[:18]


def heading_candidates(page):
    """Offer a unique, visible native title to the independent visual reader after an omission."""
    layer = page.get("layer") or {}
    output = page["extraction"]["output"]
    if layer.get("type") != "text" or output["quality"] != "readable" or len(output["facts"]) >= 140:
        return []
    if any(item["field"] in TITLE_FIELDS for item in output["facts"]):
        return []
    candidates = []
    for number, line in enumerate(page["text"].splitlines(), 1):
        kind = PRINTED_TITLES.get(compact(line))
        rects = layer["lines"].get(str(number), [])
        if kind and rects and max(rect[3] for rect in rects) <= .36:
            candidates.append({"index": "t"+str(number), "field": FIELDS[kind], "value": line.strip(), "quote": line})
    return candidates if len(candidates) == 1 else []


def build_graph(docs, pages, attestations, amendments=()):
    nodes = {}
    edges, evidence, gaps, cautions = [], [], [], []
    by_kind = defaultdict(list)
    inventory = {doc["id"]: doc for doc in docs}
    edits = defaultdict(dict)
    for item in amendments:
        edits[item["doc"], item["page"]][item["target"]] = item
    for doc in docs:
        nodes[doc["id"]] = {"id": doc["id"], "type": "document", "label": doc["name"],
                             "sha256": doc["sha256"]}
    for page in pages:
        doc = page["doc"]
        number = page["number"]
        page_id = f"{doc}/p{number}"
        output = page["extraction"]["output"]
        observations = {f"{page_id}/f{index}": item for index, item in enumerate(output["facts"], 1)}
        check = page["extraction"].get("check")
        supports = {row["index"]: row["support"] for row in check["output"]["checks"]} if check else {}
        headings = {}
        for candidate in heading_candidates(page):
            index = candidate["index"]
            if supports.get(index) == "clear" and candidate in check.get("input", []):
                headings[index] = {"field": PRINTED_TITLES[compact(candidate["quote"])], "value": candidate["value"],
                                   "quote": candidate["quote"], "region": "top"}
                observations[f"{page_id}/{index}"] = headings[index]
        page_edits = edits[doc, number]
        for target, edit in page_edits.items():
            if edit["page_hash"] != page["sha256"]:
                raise ValueError("amendment source mismatch")
            observations[target] = {key: edit[key] for key in ("field", "value", "quote", "region")}
        lines = index_lines(page["text"])
        layer = page.get("layer") or {"type": "unknown", "lines": {}}
        nodes[page_id] = {"id": page_id, "type": "page", "label": f"第 {number} 页", "sha256": page["sha256"],
                          "text_sha256": hashlib.sha256(page["text"].encode()).hexdigest(), "layer": layer["type"]}
        edges.append({"from": doc, "to": page_id, "type": "contains", "evidence": [page_id]})
        if output["quality"] != "readable" or not observations:
            gaps.append({"doc": doc, "page": number, "quality": output["quality"], "id": page_id})
        for index, line in enumerate(page["text"].splitlines(), 1):
            title_hint = PRINTED_TITLES.get(compact(line))
            location = layer["lines"].get(str(index), [])
            if title_hint and layer["type"] == "text" and location and min(rect[1] for rect in location) < .36:
                if not any(item["field"] == title_hint and compact(item["quote"]) == compact(line)
                           for item in observations.values()):
                    gaps.append({"doc":doc, "page":number, "id":page_id, "quality":"uncovered_title",
                                 "line":index, "quote":line, "title_hint":title_hint})
            if TERMS.search(compact(line)):
                cautions.append({"page_id": page_id, "line": index, "quote": line, "doc": doc})
            if layer["type"] == "text" and any(pattern.match(compact(line)) and not any(
                    item["field"] == field and compact(item["quote"]) == compact(line) for item in observations.values())
                    for field, pattern in FIELD_START.items()):
                gaps.append({"doc": doc, "page": number, "id": page_id, "quality": "uncovered",
                             "line": index, "quote": line})
        for fact_id, item in observations.items():
            field, value, quote = item["field"], item["value"].strip(), item["quote"].strip()
            origin = fact_id.rsplit("/", 1)[1]
            index = origin[1:] if origin.startswith("f") else None
            edit = page_edits.get(fact_id)
            status = "visual"
            position = lines.get(compact(quote).strip("。;；"))
            rects = layer["lines"].get(str(position[0]), []) if position else []
            if compact(value) not in compact(quote):
                status = "unsupported"
            elif position and layer["type"] == "text" and rects and labelled(field, value, quote):
                status = "anchored"
            support = supports.get(origin if origin in headings else index) if not edit else None
            if support in ("conflict", "unreadable") and status != "unsupported":
                status = "visual"
            signoff = attestations.get(fact_id)
            if signoff and signoff["decision"] == "dispute":
                status = "disputed"
            elif signoff and status != "unsupported":
                status = "confirmed"
            fact = {"id": fact_id, "doc": doc, "name": inventory[doc]["name"], "page": number,
                    "page_sha256": page["sha256"], "source_sha256": inventory[doc]["sha256"],
                    "response_id": page["extraction"].get("response_id") if index else None,
                    "visual_check": support, "check_response_id": check.get("response_id") if check else None,
                    "field": field, "label": FIELDS[field], "value": value, "quote": quote,
                    "region": item["region"], "status": status, "attestation": signoff,
                    "source_line": {"number": position[0], "text": position[1], "rects": rects} if position else None}
            if origin in headings:
                fact["origin"] = "verified_printed_heading"
            if edit:
                fact["amendment"] = edit
                fact["original_candidate"] = output["facts"][int(index) - 1] if index else headings.get(origin)
            evidence.append(fact)
            nodes[fact_id] = {"id": fact_id, "type": "observation", "label": fact["label"], "status": status}
            edges.append({"from": page_id, "to": fact_id, "type": "records", "evidence": [fact_id]})
            if status not in ("anchored", "confirmed"):
                continue
            if field in TITLE_FIELDS:
                if doc not in by_kind[field]:
                    by_kind[field].append(doc)
            kind = {"buyer": "party", "seller": "party", "contract_id": "contract_number",
                    "invoice_id": "invoice_number", "claim_ref": "invoice_number"}.get(field, field)
            target = entity_id(kind, value)
            nodes[target] = {"id": target, "type": kind, "label": value}
            edges.append({"from": doc, "to": target, "type": field, "evidence": [fact_id]})
    graph = {"nodes": list(nodes.values()), "edges": edges, "facts": evidence,
             "documents_by_kind": dict(by_kind), "gaps": gaps, "cautions": cautions, "documents": docs}
    partition_documents(graph, pages)
    return graph


def audit_documents(graph):
    return graph.get("audit_documents", graph["documents"])


def partition_documents(graph, pages):
    page_numbers, by_page = defaultdict(list), defaultdict(list)
    hints = defaultdict(set)
    for gap in graph["gaps"]:
        if gap.get("title_hint"):
            hints[gap["doc"], gap["page"]].add(gap["title_hint"])
    for page in pages:
        page_numbers[page["doc"]].append(page["number"])
    for fact in graph["facts"]:
        by_page[fact["doc"], fact["page"]].append(fact)
    units, unit_by_fact = [], {}
    assignments = graph["documents_by_kind"]
    for doc in graph["documents"]:
        source = doc["id"]
        titles, invoice_numbers = {}, set()
        for number in page_numbers[source]:
            verified = [f for f in by_page[source, number] if f["status"] in ("anchored", "confirmed")]
            titles[number] = {f["field"] for f in verified if f["field"] in TITLE_FIELDS}
            if (titles[number] | hints[source, number]) == {"invoice"}:
                numbers = {compact(f["value"]) for f in verified if f["field"] == "invoice_id"}
                if len(numbers) == 1:
                    invoice_numbers.update(numbers)
        kinds = {kind for number, group in titles.items() for kind in group | hints[source, number]}
        if len(kinds) <= 1 and len(invoice_numbers) <= 1:
            units.append(doc)
            continue
        for group in assignments.values():
            if source in group:
                group.remove(source)
        for number, page_kinds in titles.items():
            page_id = f"{source}/p{number}"
            unit = "unit/" + page_id
            label = f"{doc['name']} · 第 {number} 页"
            units.append({"id": unit, "name": label, "source": source, "page": number})
            graph["nodes"].append({"id": unit, "type": "document_section", "label": label,
                                   "source": source, "page": number})
            graph["edges"].append({"from": source, "to": unit, "type": "contains_section", "evidence": [page_id]})
            graph["edges"].append({"from": unit, "to": page_id, "type": "section_page", "evidence": [page_id]})
            if len(page_kinds) == 1 and not hints[source, number] - page_kinds:
                assignments.setdefault(next(iter(page_kinds)), []).append(unit)
            else:
                graph["gaps"].append({"doc": source, "page": number, "id": page_id, "quality": "section_unresolved"})
            for fact in by_page[source, number]:
                fact["unit"] = unit
                unit_by_fact[fact["id"]] = unit
    if len(units) != len(graph["documents"]) or any("source" in item for item in units):
        graph["audit_documents"] = units
        for edge in graph["edges"]:
            if edge["type"] in FIELDS and edge["evidence"][0] in unit_by_fact:
                edge["from"] = unit_by_fact[edge["evidence"][0]]


def link_procedures(graph, findings, calls):
    nodes = graph["nodes"]
    edges = graph["edges"]
    expert_id = "model/expert"
    nodes.append({"id": expert_id, "type": "model_call", "label": "专家追加程序",
                  "response_id": calls["expert"].get("response_id"), "model": calls["expert"]["model"]})
    known_rules = set()
    for finding in findings:
        rule = finding["rule"]
        rule_id = "control/" + rule
        finding_id = "finding/" + finding["id"]
        if rule not in known_rules:
            nodes.append({"id": rule_id, "type": "control", "label": rule,
                          "version": finding["version"], "basis": finding["basis"]})
            known_rules.add(rule)
        nodes.append({"id": finding_id, "type": "finding", "label": finding["title"],
                      "status": finding["status"], "detail": finding["detail"]})
        basis = finding["evidence"] or finding["scope"]
        if not basis:
            basis = [expert_id]
        edges.append({"from": rule_id, "to": finding_id, "type": "procedure_result", "evidence": basis})
        for ref in basis:
            edges.append({"from": ref, "to": finding_id, "type": "supports_result", "evidence": [ref]})
        if rule == "X01":
            edges.append({"from": expert_id, "to": finding_id, "type": "selected_procedure", "evidence": [expert_id]})
    for call in calls["pages"]:
        call_id = f"model/{call['doc']}/p{call['page']}"
        page_id = f"{call['doc']}/p{call['page']}"
        nodes.append({"id": call_id, "type": "model_call", "label": "逐页多模态提取",
                      "response_id": call.get("response_id"), "model": call["model"]})
        edges.append({"from": page_id, "to": call_id, "type": "read_by", "evidence": [page_id]})
        if call.get("check"):
            check_id = call_id + "/check"
            check = call["check"]
            nodes.append({"id": check_id, "type": "model_call", "label": "逐字段视觉复检",
                          "response_id": check.get("response_id"), "model": check["model"]})
            edges.append({"from": page_id, "to": check_id, "type": "inspected_by", "evidence": [page_id]})


def invoice_number_edges(graph, include_unclassified=False):
    documents = set(graph["documents_by_kind"].get("invoice", []))
    if include_unclassified:
        classified = {doc for group in graph["documents_by_kind"].values() for doc in group}
        documents.update(doc["id"] for doc in audit_documents(graph) if doc["id"] not in classified)
    edges = [edge for edge in graph["edges"] if edge["type"] == "invoice_id" and edge["from"] in documents]
    by_doc = defaultdict(set)
    for edge in edges:
        by_doc[edge["from"]].add(edge["to"])
    return [edge for edge in edges if len(by_doc[edge["from"]]) == 1]


def attach_prior_invoices(graph, matches):
    history = []
    for row in matches:
        ref = f"prior/{row['case_id']}/r{row['rev']}/{row['fact']}"
        history.append({**row, "id": ref})
        graph["nodes"].append({"id": ref, "type": "archived_observation", "label": row["title"], **row})
        graph["edges"].append({"from": ref, "to": row["number_key"], "type": "archived_invoice",
                               "evidence": [ref]})
    graph["prior_invoices"] = history
