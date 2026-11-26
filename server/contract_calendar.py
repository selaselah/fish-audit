"""Read dates from complete, numbered lines of a contract's native text layer."""

import re
from collections import defaultdict
from datetime import date

from folio_transcription import BODIES, witness
from signing_parties import checked


FIELDS = ("signed_on", "effect_on", "valid_until")
SEPARATED = re.compile(r"([0-9]{4}) *([-./]) *([0-9]{1,2}) *\2 *([0-9]{1,2})")
LABELLED = re.compile(r"([^：:]+)([：:])(.*)")
READ = {"exact", "spacing"}


def tokens(body):
    body = body.strip(" ")
    chinese = BODIES["date"].fullmatch(body)
    if chinese:
        digits = chinese.groups()
        separator = "年月日"
    else:
        numeric = SEPARATED.fullmatch(body)
        if not numeric:
            return "notation", None, None
        digits = (numeric[1], numeric[3], numeric[4])
        separator = numeric[2]
    try:
        value = date(*map(int, digits))
    except ValueError:
        return "invalid", None, None
    return "exact", (separator, *digits), value.isoformat()


def row(place, raw, number, matches, graph, page_hash, original_hash, call):
    from acceptance_authority import parts
    from performance import DATE_LABELS

    label, _ = parts(raw)
    field = next((key for key in FIELDS if label in DATE_LABELS[key]), None)
    if field is None:
        return None
    matches = [f for f in matches if f.get("unit", f["doc"]) == place["unit"]]
    result = {**place, "field": field, "id": f"contract-date/{place['doc']}/p{place['page']}/l{number}",
              "line": number, "quote": raw, "facts": [f["id"] for f in matches], "state": "notation",
              "date": None, "witness": None, "original_sha256": original_hash, "page_sha256": page_hash}
    original = LABELLED.fullmatch(raw)
    if not original or original[1] != label:
        return result
    state, written, value = tokens(original[3])
    result["state"] = state
    if written is None:
        return result
    result["state"] = "unread"
    if len(matches) != 1:
        if matches:
            result["state"] = "multiple"
        return result
    fact = matches[0]
    line = fact.get("source_line") or {}
    if (fact["field"] != field or fact["status"] not in ("anchored", "confirmed") or
            not line.get("rects") or (line.get("text"), line.get("number")) != (raw, number) or
            not original_hash or not page_hash or
            (fact["source_sha256"], fact["page_sha256"]) != (original_hash, page_hash)):
        return result
    copy = LABELLED.fullmatch(fact["quote"])
    reading = copy[3] if copy and fact["value"] == fact["quote"] else fact["value"]
    if (not copy or (copy[1], copy[2]) != (original[1], original[2]) or
            any(tokens(text)[1] != written for text in (copy[3], reading))):
        result["state"] = "different"
        return result
    if fact["quote"] == raw and reading == original[3].strip(" "):
        result.update(state="exact", date=value, witness="native_line")
        return result
    support = witness(fact, call)
    if support == "field_receipt" and not checked(fact, graph):
        support = None
    if support:
        result.update(state="spacing", date=value, witness=support)
    else:
        result["state"] = "unverified"
    return result


def by_field(ledger, unit):
    groups = defaultdict(list)
    for item in ledger.get("date_rows", []):
        if item["unit"] == unit:
            groups[item["field"]].append(item)
    return groups


def reading(rows, material):
    field = rows[0]["field"]
    if len(rows) > 1:
        # A second readable date is contradictory even when one line was omitted
        # by the model. Inspect the native lines before considering transcription.
        printed = {tokens(match[3])[2] for row in rows if (match := LABELLED.fullmatch(row["quote"]))}
        return ("conflict" if len(printed - {None}) > 1 else "multiple"), None
    item = rows[0]
    if item["state"] not in READ:
        return item["state"], None
    if material.incomplete(field) or item["facts"] != [f["id"] for f in material.fields[field]]:
        return "unverified", None
    return item["state"], item["date"]


def source_graph(ledger):
    nodes, edges = [], []
    for row in ledger.get("date_rows", []):
        page = f"{row['doc']}/p{row['page']}"
        nodes.append({"id": row["id"], "type": "contract_date_line", "label": row["quote"],
                      "doc": row["doc"], "page": row["page"], "line": row["line"]})
        edges.append({"from": page, "to": row["id"], "type": "contract_date_source", "evidence": [page, *row["facts"]]})
    return nodes, edges


def review(finding, material):
    calendar = []
    for field in FIELDS:
        rows = material.calendar.get(field)
        if not rows:
            continue
        state, value = reading(rows, material)
        calendar.append({"field": field, "state": state, "date": value, "rows": [r["id"] for r in rows]})
        if state in READ:
            continue
        was_clear = finding["status"] == "ok"
        if state == "conflict":
            if finding["status"] != "issue":
                finding["status"] = "risk"
            message = "同一合同日期栏有不同日期，须核实现行原件。"
        else:
            if finding["status"] == "ok":
                finding["status"] = "missing"
            message = "合同日期栏的完整写法和提取读数待核。"
        if was_clear:
            finding["detail"] = message
        elif message not in finding["detail"]:
            finding["detail"] += " " + message
    if calendar:
        finding["effect_review"]["calendar"] = calendar
