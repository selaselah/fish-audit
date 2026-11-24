"""Bind the tenant-scoped invoice lookup at approval to the human decision and its source workpaper."""

import hashlib
import json
from collections import defaultdict

from invoice_comparison import FORMAT as LOOKUP_FORMAT, actionables, lookup_numbers, screen
from invoice_masks import withheld_invoices
from invoice_proof import invoice_number_edges
from protocol import canonical


LEGACY_FORMAT = "invoice-approval-v1"
FORMAT = "invoice-approval-v2"
PROFILES = {"cn-procurement-full-settlement/v1","cn-travel-reimbursement/v1"}


def receipt(graph, matches, source_rev, report_hash, signoff):
    decision = {k:v for k,v in signoff.items() if k!="invoice_check_hash"}
    header = {"case_id":signoff["case_id"],"workspace":signoff["workspace"],
              "source_rev":source_rev,"source_sha256":report_hash,"signed_rev":signoff["rev"],"signed_at":signoff["time"],
              "decision_sha256":hashlib.sha256(canonical(decision).encode()).hexdigest(),"scope":"workspace-current-signed"}
    if graph.get("invoice_lookup")==LOOKUP_FORMAT:
        numbers = lookup_numbers(graph)
        screened = screen(numbers,matches)
        if len({r["id"] for r in screened})!=len(screened):
            raise ValueError("同票查验回执重复引用同一字段")
        pins = lookup_pins(screened)
        partial = withheld_invoices(graph)
        if any(m["comparison"]=="same" for m in pins):
            outcome = "matched"
        elif pins:
            outcome = "possible_match"
        elif partial:
            outcome = "incomplete_number"
        elif any(n["kind"]=="short_unresolved" for n in numbers):
            outcome = "insufficient_identity"
        else:
            outcome = "no_match" if numbers else "no_usable_number"
        result = {**header,"format":FORMAT,"numbers":numbers,"matches":pins,"screened":screened,"outcome":outcome}
        if partial:
            result["withheld"] = partial
        return result
    by_number = defaultdict(set)
    facts = {f["id"]:f for f in graph["facts"]}
    for edge in invoice_number_edges(graph):
        by_number[edge["to"]].update(edge["evidence"])
    numbers = []
    for key,refs in sorted(by_number.items()):
        ordered = sorted(refs)
        numbers.append({"key":key,"value":facts[ordered[0]]["value"],"facts":ordered})
    pins = [{k:m[k] for k in ("case_id","rev","fact","number_key","report_hash","decision")} for m in matches]
    pins.sort(key=lambda m:(m["case_id"],m["rev"],m["fact"],m["number_key"]))
    return {**header,"format":LEGACY_FORMAT,"numbers":numbers,"matches":pins,
            "outcome":"matched" if pins else ("no_match" if numbers else "no_usable_number")}


def lookup_pins(rows):
    keys = ("case_id","rev","fact","number_key","decision","report_hash","signoff_hash","comparison")
    return [{k:r[k] for k in keys} for r in actionables(rows)]


def validate(report, report_hash, signoff, raw):
    pin = signoff.get("invoice_check_hash")
    in_scope = signoff["decision"]=="approve" and report["policy"].get("profile") in PROFILES
    required = in_scope and report["policy"].get("invoice_approval") in {FORMAT,LEGACY_FORMAT}
    if pin is None and raw is None and not required:
        return
    if (not in_scope or not raw or not pin or signoff["case_id"] != report["case_id"]
            or hashlib.sha256(raw).hexdigest()!=pin):
        raise ValueError("签收时的同票检查回执缺失，或与人工签收摘要不符")
    peer = report.get("peer_review",{})
    graph = report["graph"]
    matches = graph.get("prior_invoices",[])
    if graph.get("invoice_lookup")==LOOKUP_FORMAT:
        checked = json.loads(raw)
        numbers = lookup_numbers(graph)
        received = screen(numbers,checked["screened"])
        if lookup_pins(received)!=lookup_pins(screen(numbers,matches)):
            raise ValueError("签收时可疑的前案记录与审阅的底稿不符")
        matches = received
    expected = receipt(graph,matches,
                       peer.get("source_rev",signoff["rev"]),peer.get("source_hash",report_hash),signoff)
    if raw != canonical(expected).encode():
        raise ValueError("同票检查回执与签收决定、查验版本、票号或已签收命中不符")
    return expected
