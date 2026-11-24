"""Retain readable partial identifiers as observations while withholding them from exact invoice matching."""

import re

from calculations import normalized


FORMAT = "visible-number-masks-v1"
FIELDS = {"invoice_id","claim_ref","claim_full_ref"}
MASK = re.compile(r"[*•●■□×…]|\.{2,}|尾号|仅(?:显示|保留)?(?:后|末)[0-9一二三四五六七八九十]+位")
NUMERIC_X = re.compile(r"[0-9Xx]*[Xx]{2,}[0-9Xx]*")


def marked_fields(graph):
    result=[]
    for fact in graph["facts"]:
        if fact["field"] not in FIELDS or fact["status"] not in {"anchored","confirmed"}:
            continue
        value = normalized(fact["value"])
        if MASK.search(normalized(fact["quote"])) or NUMERIC_X.fullmatch(value):
            result.append({"fact":fact["id"],"field":fact["field"],"value":fact["value"],"doc":fact["doc"],
                           "page":fact["page"],"unit":fact.get("unit",fact["doc"])})
    return result


def excluded_edges(graph,marked):
    units = {m["unit"] for m in marked if m["field"]=="invoice_id"}
    refs = {m["fact"] for m in marked}
    result={}
    for f in graph["facts"]:
        unit,field = f.get("unit",f["doc"]),f["field"]
        if (f["status"] not in {"anchored","confirmed"} or
                (f["id"] not in refs and not (field=="invoice_id" and unit in units))):
            continue
        result[f["id"]] = {"from":unit,"to":f["id"],"type":"incomplete_"+field,"evidence":[f["id"]]}
    return result


def withhold_partial_numbers(graph):
    marked = marked_fields(graph)
    graph["number_masks"] = {"format":FORMAT,"facts":marked}
    if not marked:
        return
    excluded = excluded_edges(graph,marked)
    replaced=set()
    for edge in graph["edges"]:
        if edge["type"] in FIELDS and edge["evidence"][0] in excluded:
            replaced.add(edge["to"])
            edge.update(excluded[edge["evidence"][0]])
    unused = replaced-{e["to"] for e in graph["edges"]}
    graph["nodes"] = [node for node in graph["nodes"] if node["id"] not in unused]


def verify_masks(graph):
    marked=marked_fields(graph)
    if graph.get("number_masks")!={"format":FORMAT,"facts":marked}:
        raise ValueError("遮盖号码清单与原页已核引文不符")
    expected=excluded_edges(graph,marked)
    edges=[e for e in graph["edges"] if e["type"] in {"incomplete_"+k for k in FIELDS}]
    if (len(edges)!=len(expected) or {e["evidence"][0]:e for e in edges}!=expected
            or any(e["type"] in FIELDS and any(ref in expected for ref in e["evidence"]) for e in graph["edges"])):
        raise ValueError("不完整的号码进入了精确匹配，或缺少原文关系")


def withheld_invoices(graph):
    invoices=set(graph["documents_by_kind"].get("invoice",[]))
    return [m for m in graph.get("number_masks",{}).get("facts",[]) if m["field"]=="invoice_id" and m["unit"] in invoices]
