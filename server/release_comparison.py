"""Compare the printed decisions on separately filed acceptance-payment instruments."""

import re

from acceptance_payments import same_original
from delegation import complete_id
from delivery_batches import NUM, ordinal
from payment_releases import RELEASE, exact_day, literal, mandate, recognized, scalar
from reinspection import LINK_KEYS


FORMAT = "payment-release-comparison-v1"
SINCE = (2026, 11, 27, 12)
KEY = "release_comparison"
HOLD = re.compile(r"放行决定:(?:维持第("+NUM+r")期验收款暂缓,继续暂停支付|继续暂缓第("+NUM+r")期验收款支付)")


def units(ledger):
    return list(dict.fromkeys(p["unit"] for p in ledger.get("pages", ()) if p["role"] == "release"))


def program(report):
    policy, graph = report["policy"], report["graph"]
    version = tuple(map(int, (policy.get("version") or "0").split(".")))
    marker = policy.get(KEY)
    expected = version >= SINCE
    multiple = len(units(graph.get("payment_release_sources", {}))) > 1
    methods = policy.get("code_sha256")
    if (marker != (FORMAT if expected else None)
            or graph.get(KEY) != (FORMAT if expected and multiple else None)
            or methods is not None and ("release_comparison.py" in methods) != expected):
        raise ValueError("多份放行单比对程序与本版底稿不符")


def decision(row):
    if row and row["line"] and row["native"]:
        text = literal(row["quote"])
        if match := RELEASE.fullmatch(text):
            return "resume", ordinal(match[1])
        if match := HOLD.fullmatch(text):
            return "hold", ordinal(match[1] or match[2])
    return "unclear", None


def receipt_number(material, field, labels, holds):
    value, ref = scalar(material, field, labels)
    if (ref in holds or not complete_id(value)
            or re.search(r"尾号|部分|同上|不详|末[几数\d一二三四五六七八九十]+位", value)):
        return None, ref
    return value, ref


def clear_receipt(graph, unit):
    pages = [p for p in graph["acceptance_reservation_sources"]["pages"] if p["unit"] == unit]
    return bool(pages and all(p["native"] and p["text_only"] for p in pages))


def plain_units(graph):
    return {r["unit"] for key in ("release_pdf_sources","release_original_sources")
            for r in graph.get(key, {}).get("records", ()) if r["state"] in ("typeset","word_text")}


def hold_mandate(graph, contract, receipt, notes):
    if len(notes) != 1 or not same_original(contract, receipt):
        return None
    note = notes[0]
    clauses = [r for r in graph["payment_release_sources"]["lines"]
               if r["unit"] == contract.unit and r["role"] == "authority" and r["line"]]
    if (len(clauses) != 1 or not note["line"] or note["unit"] != receipt.unit or note["target"] != "phase"
            or note["stance"] != "hold" or note["kind"] != "acceptance" or note["index"] != mandate(clauses[0]["quote"])[0]):
        return None
    return clauses[0]


def bounded_holds(graph, contract, receipts):
    """A complete hold on this same receipt and named installment adds no new contract or quality term."""
    from performance import Material

    if graph.get(KEY) != FORMAT or len(receipts) != 1:
        return set()
    ledger = graph["payment_release_sources"]
    holds = {h["fact"] for h in graph.get("quality_references", {}).get("holds", ())}
    original, _ = receipt_number(receipts[0], "acceptance_number", ("验收单编号","验收报告编号"), holds)
    notes = graph["acceptance_reservation_sources"]["payment_opinions"]
    clause = hold_mandate(graph, contract, receipts[0], notes)
    if not (original and clause and clause["text_only"] and clear_receipt(graph, receipts[0].unit)):
        return set()
    disputed = {f["id"] for f in graph["facts"] if f["status"] == "disputed"}
    bounded = set()
    for unit in recognized(ledger, HOLD) & plain_units(graph):
        slip = Material(graph, unit)
        rows = [r for r in ledger["lines"] if r["unit"] == unit]
        roles = sorted(r["role"] for r in rows)
        if roles != sorted(["title", *["identity"]*4, "decision", "receipt", "date", "signature"]):
            continue
        cited, _ = receipt_number(slip, "original_acceptance", ("原验收单编号","原验收报告编号"), holds)
        row = next(r for r in rows if r["role"] == "decision")
        if (original == cited and same_original(contract, slip) and decision(row) == ("hold", notes[0]["index"])
                and all(not disputed.intersection(r["facts"]) for r in [*rows, notes[0], clause])):
            bounded.add(unit)
    return bounded


def attach(check, graph, contract, record, opinion, stage):
    from performance import Material

    if graph.get(KEY) != FORMAT or record is None or stage["kind"] != "acceptance":
        return
    notes = opinion["notes"]
    clause = hold_mandate(graph, contract, record, notes)
    if not clause or notes[0]["index"] != stage["index"]:
        return
    note = notes[0]
    ledger = graph["payment_release_sources"]
    holds = {h["fact"] for h in graph.get("quality_references", {}).get("holds", ())}
    original, check["original_ref"] = receipt_number(record, "acceptance_number", ("验收单编号","验收报告编号"), holds)
    refs = [*record.evidence("acceptance_number", *LINK_KEYS), *contract.evidence(*LINK_KEYS), stage["ref"]]
    disputed = {f["id"] for f in graph["facts"] if f["status"] == "disputed"}
    source = next((f for f in contract.fields["payment_stage"] if f["id"] == stage["ref"]), None)
    loc = (source or {}).get("source_line") or {}
    printed = literal(loc["text"]).partition(":")[0] if loc.get("rects") and loc["text"] == source["quote"] else ""
    number = re.fullmatch(r"第("+NUM+r")期", printed)
    basis_clear = (original and number and ordinal(number[1]) == stage["index"]
                   and not disputed.intersection([*note["facts"], *clause["facts"]])
                   and clear_receipt(graph, record.unit) and clause["text_only"]
                   and set(graph["documents_by_kind"].get("acceptance", ())) == {record.unit})
    dates = opinion["record_dates"]
    if (basis_clear and len(dates) == 1 and dates[0]["unit"] == record.unit
            and exact_day(record, "accepted_on") == (dates[0]["date"], dates[0]["ref"])):
        check["held_on"] = dates[0]["date"]

    instruments = []
    plain = plain_units(graph)
    for unit in units(ledger):
        slip = Material(graph, unit)
        pages = [p for p in ledger["pages"] if p["unit"] == unit and p["role"] == "release"]
        lines = [r for r in ledger["lines"] if r["unit"] == unit]
        decisions = [r for r in lines if r["role"] == "decision"]
        printed_row = decisions[0] if len(decisions) == 1 else None
        stance, index = decision(printed_row)
        cited, ref = receipt_number(slip, "original_acceptance", ("原验收单编号","原验收报告编号"), holds)
        signed, date_ref = exact_day(slip, "release_signed_on")
        binding = "unresolved"
        if (basis_clear and unit in plain and index and cited and len(pages) == 1 and pages[0]["printed_title"] and pages[0]["identity_clear"]
                and pages[0]["text_only"] and same_original(contract, slip)
                and all(r["role"] != "qualification" and not disputed.intersection(r["facts"]) for r in lines)):
            binding = "other_receipt" if original != cited else "other_phase" if index != stage["index"] else "same"
        instruments.append({"unit":unit, "stance":stance, "phase":index, "binding":binding, "receipt_ref":ref,
                            "signed_on":signed, "date_ref":date_ref})
        refs.extend(slip.evidence("original_acceptance", "release_signed_on", *LINK_KEYS))
    check["evidence"] = list(dict.fromkeys([*check["evidence"], *refs]))
    check["instruments"] = instruments
    stances = {r["stance"] for r in instruments if r["binding"] == "same"}
    check["state"] = "decision_conflict" if stances == {"resume","hold"} else "multiple_pending"
