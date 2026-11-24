import hashlib
import re
import unicodedata
from collections import defaultdict

from invoice_comparison import FORMAT as INVOICE_LOOKUP, code_relations, lookup_numbers, screen
from invoice_identity import CLAIM_PAIR_LABELS, FORMAT as IDENTITY_FORMAT, SHORT, identity_relations, printed_claim_pair
from invoice_masks import withhold_partial_numbers
from invoice_proof import invoice_number_edges
from model import FIELDS
from performance import LABELS as PERFORMANCE_LABELS, STAGE_PREFIX, complete_line
from payment_reference import attach as attach_payment_references, partial_line, printed_partial_value
from reinspection import NUMBER_TYPES as QUALITY_NUMBERS
from quality_labels import numbered_lines, verified as verified_quality_number
from quality_references import attach as record_quality_references
from delegation import ENTITY_TYPES as DELEGATION_ENTITIES, TITLES as MANDATE_TITLES, attach as record_mandate_pages, printed_value as mandate_value
from contract_changes import NUMBER_TYPES as ADDENDUM_NUMBERS, TITLES as ADDENDUM_TITLES, attach as record_addenda, number_target
import delivery_batches
import contract_effect
import warranty_terms
from acceptance_authority import CLAUSE as AUTHORITY_CLAUSE, SIGNER as ACCEPTANCE_SIGNATURE, attach as record_signatories, witness_edges


KINDS = {"invoice": "发票", "contract": "合同", "acceptance": "验收单"}
TITLE_FIELDS = {**KINDS, "claim": "报销", "bank_receipt":"回单", "warranty":"质保期满确认","contract_approval":"审批",
                "remediation":"整改","reinspection":"复验","power_of_attorney":"委托书","contract_addendum":"补充协议"}
PRINTED_TITLES = {label: field for field, labels in {
    "invoice": ("发票", "采购发票", "住宿服务发票", "增值税专用发票", "增值税普通发票", "增值税电子普通发票",
                "电子发票(普通发票)", "电子发票(增值税专用发票)"),
    "contract": ("采购合同", "设备采购合同", "购销合同", "采购协议"),
    "acceptance": ("验收单", "到货验收单", "验收报告", "采购验收单", "设备验收单"),
    "warranty": ("质保期满确认单", "质保期满确认书"),
    "contract_approval": ("合同审批单","合同审批记录","董事会合同审批记录"),
    "power_of_attorney": MANDATE_TITLES,
    "contract_addendum": ADDENDUM_TITLES,
    "remediation": ("整改记录单","缺陷整改记录","整改完成记录"),
    "reinspection": ("复验报告","整改复验单","最终复验报告","整改复验报告"),
    "bank_receipt": ("银行付款回单", "银行转账回单", "电子银行回单", "银行电子回单", "转账回单"),
    "claim": ("报销单", "差旅报销单", "差旅费报销单", "费用报销单"),
}.items() for label in labels}
LABELS = {
    **PERFORMANCE_LABELS,
    "payer": ("付款户名","付款人名称","付款人户名"), "payee": ("收款户名","收款人名称","收款人户名"),
    "contract_account": ("约定收款账号","合同收款账号"), "payee_account": ("收款账号","收款人账号"),
    "transfer_amount": ("付款金额","转账金额","交易金额"), "paid_on": ("付款日期","转账日期","交易日期"),
    "transfer_ref": ("交易流水号","银行流水号"), "transfer_status": ("交易状态","转账状态"),
    "buyer": ("采购方", "购方", "购买方", "甲方", "买方", "需方", "采购单位", "验收单位"),
    "seller": ("供应方", "销方", "销售方", "乙方", "卖方", "供方", "供应商", "供货单位"),
    "contract_id": ("合同编号", "合同号"), "invoice_id": ("发票号码", "票据号码", "发票号"),
    "invoice_code": ("发票代码",), "claim_full_ref": CLAIM_PAIR_LABELS,
    "net": ("不含税金额", "不含税合计", "不含税价款", "金额合计"),
    "tax": ("税额", "税款"), "total": ("价税合计", "含税总额", "含税总价", "含税金额", "含税合计"),
    "currency": ("币种", "货币种类", "结算货币"),
    "unit": ("金额单位", "计价单位", "金额单位为"),
    "issued_on": ("开票日期", "开具日期"), "signed_on": ("签约日期", "签订日期", "签署日期"),
    "accepted_on": ("验收日期", "验收时间","复验日期"),
    "acceptance_result": ("验收结果", "验收结论","复验结果","复验结论"),
    "subject": ("采购标的", "标的名称", "项目名称", "货物名称", "商品名称", "品名"),
    "payment_term": ("结算条款", "付款条款", "付款方式", "结算方式", "支付条件", "付款条件", "结算条件"),
    "adjustment": ("变更", "红冲", "冲销", "补充协议", "红字"),
    "claim_total": ("申请报销金额", "申请报销总额", "报销合计"),
    "traveler": ("出差人员", "出差人", "旅客姓名", "乘车人", "入住人"),
    "trip_start": ("出差开始日期", "出差起始日期"), "trip_end": ("出差结束日期", "出差截止日期"),
    "service_on": ("费用发生日期", "乘车日期", "消费日期", "住宿日期"),
    "claim_ref": ("随附发票号码", "附件票号", "报销所附票号"),
}
SCALAR = {"contract_id", "invoice_id", "invoice_code", "claim_full_ref", "net", "tax", "total", "buyer", "seller", "signed_on",
          "accepted_on", "issued_on", "acceptance_result", "subject", "currency", "unit", "payment_term",
          "claim_total", "traveler", "trip_start", "trip_end", "service_on", "claim_ref","payer","payee","contract_account","payee_account",
          "transfer_amount","paid_on","transfer_ref","transfer_status"}
FIELD_START = {field: re.compile(r"^(?:" + "|".join(sorted(LABELS[field], key=len, reverse=True)) + r")[:(（]")
               for field in SCALAR | PERFORMANCE_LABELS.keys()}
FIELD_START["payment_stage"] = re.compile(STAGE_PREFIX.pattern + r"|^付款期次:")
FIELD_START["effect_clause"] = re.compile(FIELD_START["effect_clause"].pattern + r"|^本合同.{0,80}生效")
TERMS = re.compile(r"分期|分[两二三四五六七八九十\d]+期|预付|质保金|保留款|分批|定金|订金|尾款|部分交付|红字|冲销|红冲|退款|退汇|冲正|撤销|抵扣|扣减|变更单|补充协议")
PERFORMANCE_CAUTION = re.compile(r"解除|终止|待审批|待批准|授权委托|另附|另行约定|第[两一二三四五六七八九十\d]+期")


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
    if field=="transfer_ref" and printed_partial_value(quote,value):
        return True
    if field=="transfer_ref_note":
        return value in quote and partial_line(quote)
    if field in TITLE_FIELDS:
        if field=="power_of_attorney":
            return value==quote and quote in MANDATE_TITLES
        if field=="contract_addendum":
            return value==quote and quote in ADDENDUM_TITLES
        printed = PRINTED_TITLES.get(quote)
        if printed and printed != field:
            return False
        word = "验收" if field == "acceptance" else TITLE_FIELDS[field]
        return value == quote and word in value and len(value) <= 48 and not any(
            label in value for label in ("号码", "编号", "结论", "日期", "参见", "附录", "附件清单", "提交", "缺少"))
    if field == "other":
        return False
    if field in PERFORMANCE_LABELS:
        return complete_line(field, value, quote)
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
        if field in {"total", "net", "tax", "claim_total","transfer_amount"}:
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
    if any(item["field"] in TITLE_FIELDS and labelled(item["field"],item["value"],item["quote"]) for item in output["facts"]):
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
    performance_cautions = []
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
        printed_numbers = {}
        if check and output["quality"]=="readable" and layer["type"]=="text" and len(output["facts"])<140:
            markers = numbered_lines(page["text"].splitlines())
            for i,raw in enumerate(output["facts"],1):
                ref = f"{page_id}/f{i}"
                pos = lines.get(compact(raw["quote"]).strip("。;；"))
                if ref in page_edits or not pos or not layer["lines"].get(str(pos[0])):
                    continue
                corrected = verified_quality_number(raw,markers,pos[0],str(i),check)
                if corrected:
                    observations[ref] = {**raw,"field":corrected}
                    printed_numbers[ref] = raw["field"]
        printed_pairs = set()
        for ref,candidate in observations.items():
            if candidate["field"]!="claim_ref" or ref in page_edits or layer["type"]!="text":
                continue
            position = lines.get(compact(candidate["quote"]).strip("。;；"))
            if (position and layer["lines"].get(str(position[0])) and
                    printed_claim_pair(candidate,position[1],check,ref.rsplit("/f",1)[-1])):
                observations[ref] = {**candidate,"field":"claim_full_ref"}
                printed_pairs.add(ref)
        nodes[page_id] = {"id": page_id, "type": "page", "label": f"第 {number} 页", "sha256": page["sha256"],
                          "text_sha256": hashlib.sha256(page["text"].encode()).hexdigest(), "layer": layer["type"],
                          "clause_text_only":layer.get("clause_text_only") is True}
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
            if PERFORMANCE_CAUTION.search(compact(line)):
                performance_cautions.append({"page_id":page_id, "line":index, "quote":line, "doc":doc})
            if layer["type"] == "text":
                missing = [field for field, pattern in FIELD_START.items() if pattern.match(compact(line)) and not any(
                    (item["field"] == field or {item["field"],field} == {"payment_stage","payment_term"}) and
                    compact(item["quote"]) == compact(line) for item in observations.values())]
                if missing:
                    gaps.append({"doc": doc, "page": number, "id": page_id, "quality": "uncovered", "line": index,
                                 "quote": line, "field": missing[0] if len(missing) == 1 else None})
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
            if fact_id in printed_numbers:
                support = supports["q"+index]
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
            if fact_id in printed_pairs:
                fact.update(origin="printed_claim_pair",model_field="claim_ref")
            if fact_id in printed_numbers:
                fact.update(origin="printed_quality_number",model_field=printed_numbers[fact_id],classification_index="q"+index)
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
            kind = {"buyer": "party", "seller": "party", "payer":"party", "payee":"party",
                    "payee_account":"bank_account", "contract_account":"bank_account", "contract_id": "contract_number",
                    **QUALITY_NUMBERS, **DELEGATION_ENTITIES,
                    "invoice_id": "invoice_number", "claim_ref": "invoice_number"}.get(field, field)
            entity_label = (mandate_value(field, value, quote) or value) if field in DELEGATION_ENTITIES else value
            target = entity_id(kind, entity_label)
            if field in ADDENDUM_NUMBERS:
                target, entity_label = number_target(field,value,quote,fact_id)
                kind = ADDENDUM_NUMBERS[field]
            if field in (AUTHORITY_CLAUSE,ACCEPTANCE_SIGNATURE) or field in delivery_batches.LABELS or field in warranty_terms.LABELS:
                target = fact_id
            if target!=fact_id:
                nodes[target] = {"id": target, "type": kind, "label": entity_label}
            edges.append({"from": doc, "to": target, "type": field, "evidence": [fact_id]})
    graph = {"nodes": list(nodes.values()), "edges": edges, "facts": evidence,
             "documents_by_kind": dict(by_kind), "gaps": gaps, "cautions": cautions,
             "performance_cautions":performance_cautions, "documents": docs}
    partition_documents(graph, pages)
    withhold_partial_numbers(graph)
    texts = {(page["doc"],page["number"]):page["text"] for page in pages}
    graph["contract_effect_sources"]=contract_effect.sources(graph,lambda doc,number:texts[doc,number])
    graph["warranty_sources"]=warranty_terms.sources(graph,lambda doc,number:texts[doc,number])
    record_mandate_pages(graph, lambda doc, number: texts[doc, number])
    record_addenda(graph, lambda doc, number: texts[doc, number])
    delivery_batches.attach(graph, lambda doc, number: texts[doc,number])
    record_signatories(graph, lambda doc, number: texts[doc, number])
    record_quality_references(graph, lambda doc, number: texts[doc, number])
    attach_payment_references(graph, lambda doc, number: texts[doc,number])
    graph["invoice_identity"] = IDENTITY_FORMAT
    graph["invoice_lookup"] = INVOICE_LOOKUP
    identities,links = identity_relations(graph)
    graph["nodes"].extend(identities)
    graph["edges"].extend(links)
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
        short_pages = defaultdict(set)
        for number in page_numbers[source]:
            verified = [f for f in by_page[source, number] if f["status"] in ("anchored", "confirmed")]
            titles[number] = {f["field"] for f in verified if f["field"] in TITLE_FIELDS}
            if (titles[number] | hints[source, number]) == {"invoice"}:
                numbers = {compact(f["value"]) for f in verified if f["field"] == "invoice_id"}
                if len(numbers) == 1:
                    invoice_numbers.update(numbers)
                    for printed_number in numbers:
                        if SHORT.fullmatch(printed_number):
                            short_pages[printed_number].add(number)
        kinds = {kind for number, group in titles.items() for kind in group | hints[source, number]}
        if len(kinds) <= 1 and len(invoice_numbers) <= 1 and not any(len(p)>1 for p in short_pages.values()):
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
    edges.extend(witness_edges(findings))
    edges.extend(delivery_batches.evidence_edges(findings))
    edges.extend(warranty_terms.edges(findings))
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


def attach_prior_invoices(graph, matches):
    history = screen(lookup_numbers(graph),matches)
    for row in history:
        ref = row["id"]
        graph["nodes"].append({"id": ref, "type": "archived_observation", "label": row["title"], **row})
        graph["edges"].append({"from": ref, "to": row["number_key"], "type": "archived_invoice",
                               "evidence": [ref]})
    graph["prior_invoices"] = history
    nodes,edges = code_relations(history)
    graph["nodes"].extend(nodes)
    graph["edges"].extend(edges)
