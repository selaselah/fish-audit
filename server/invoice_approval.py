"""Bind the tenant-scoped invoice lookup at approval to the human decision and its source workpaper."""

import hashlib
from collections import defaultdict

from invoice_proof import invoice_number_edges
from protocol import canonical


FORMAT = "invoice-approval-v1"
PROFILES = {"cn-procurement-full-settlement/v1","cn-travel-reimbursement/v1"}


def receipt(graph, matches, source_rev, report_hash, signoff):
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
    decision = {k:v for k,v in signoff.items() if k!="invoice_check_hash"}
    return {"format":FORMAT,"case_id":signoff["case_id"],"workspace":signoff["workspace"],
            "source_rev":source_rev,"source_sha256":report_hash,"signed_rev":signoff["rev"],"signed_at":signoff["time"],
            "decision_sha256":hashlib.sha256(canonical(decision).encode()).hexdigest(),
            "scope":"workspace-current-signed","numbers":numbers,"matches":pins,
            "outcome":"matched" if pins else ("no_match" if numbers else "no_usable_number")}


def validate(report, report_hash, signoff, raw):
    pin = signoff.get("invoice_check_hash")
    in_scope = signoff["decision"]=="approve" and report["policy"].get("profile") in PROFILES
    required = in_scope and report["policy"].get("invoice_approval")==FORMAT
    if pin is None and raw is None and not required:
        return
    if (not in_scope or not raw or not pin or signoff["case_id"] != report["case_id"]
            or hashlib.sha256(raw).hexdigest()!=pin):
        raise ValueError("签收时的同票检查回执缺失，或与人工签收摘要不符")
    peer = report.get("peer_review",{})
    expected = receipt(report["graph"],report["graph"].get("prior_invoices",[]),
                       peer.get("source_rev",signoff["rev"]),peer.get("source_hash",report_hash),signoff)
    if raw != canonical(expected).encode():
        raise ValueError("同票检查回执与签收决定、查验版本、票号或已签收命中不符")
