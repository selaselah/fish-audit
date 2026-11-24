"""Reconstruct a cited invoice number from a signed workpaper and its saved page text."""

import hashlib
from collections import defaultdict

from calculations import normalized


FORMAT = "signed-invoice-v1"


def invoice_number_edges(graph, include_unclassified=False):
    kinds = graph["documents_by_kind"]
    documents = set(kinds.get("invoice", []))
    if include_unclassified:
        classified = {doc for group in kinds.values() for doc in group}
        units = graph.get("audit_documents", graph["documents"])
        documents.update(doc["id"] for doc in units if doc["id"] not in classified)
    edges = [edge for edge in graph["edges"] if edge["type"] == "invoice_id" and edge["from"] in documents]
    by_doc = defaultdict(set)
    for edge in edges:
        by_doc[edge["from"]].add(edge["to"])
    return [edge for edge in edges if len(by_doc[edge["from"]]) == 1]


def source_record(fact, page_node, text, number_key, signed_at):
    value = normalized(fact["value"])
    quote = normalized(fact["quote"])
    if (fact["field"] != "invoice_id" or not value or value not in quote
            or number_key != "invoice_number-" + hashlib.sha256(value.encode()).hexdigest()[:18]):
        raise ValueError("历史发票号码与原版字段取值或引文不符")
    digest = hashlib.sha256(text.encode()).hexdigest()
    if "text_sha256" in page_node and page_node["text_sha256"] != digest:
        raise ValueError("历史发票文字层与原版摘要不符")
    line = fact.get("source_line")
    if line:
        lines = text.splitlines()
        number = line["number"]
        if (type(number) is not int or not 1 <= number <= len(lines) or lines[number-1] != line["text"]
                or normalized(line["text"]).strip("。;；") != quote.strip("。;；")):
            raise ValueError("历史票号的逐字引文与原页文字行不符")
    if fact["status"] == "anchored":
        basis = "historical_record"
        if page_node.get("layer") == "text":
            if not (line and line.get("rects") and page_node.get("text_sha256")):
                raise ValueError("历史票号缺少原生文字行或页内定位")
            basis = "native_line"
    elif fact["status"] == "confirmed" and (fact.get("attestation") or {}).get("decision") == "confirm":
        checked = any((fact.get(key) or {}).get("source_check") for key in ("attestation","amendment"))
        basis = "field_check" if checked else "historical_confirmation"
    else:
        raise ValueError("历史发票号码缺少文字锚点或人工确认")
    return {"format":FORMAT, "basis":basis, "line":line["number"] if line else None,
            "text_sha256":digest, "signed_at":signed_at}
