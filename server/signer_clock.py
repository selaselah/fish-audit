"""Read civil times printed next to a named final signature or an actual bank debit."""

import copy
import re
from collections import defaultdict
from datetime import date
from unicodedata import normalize


FORMAT = "named-acceptance-signatures-v5"
SINCE = "2026.11.26.24"
SIGNER = re.compile(r"([\u3400-\u9fff]{2,8})(?:签认|签字|签署|签名)(?:时间|时刻|时分)")
DEBIT = {"实际扣款时间", "扣款成功时间", "成功扣款时间", "实际扣款时刻", "扣款时间"}
OTHER = {"银行受理时间", "受理时间", "交易发起时间", "回单打印时间", "打印时间", "记账时间", "到账时间", "回单生成时间", "交易时间"}
VALUE = re.compile(
    r"(?:(?:([0-9]{4})年([0-9]{1,2})月([0-9]{1,2})日|([0-9]{4})-([0-9]{2})-([0-9]{2}))[ T]+)?"
    r"([01][0-9]|2[0-3]):([0-5][0-9])(?::([0-5][0-9]))?"
    r"(?:\s*(?:\((北京时间|UTC\+08:00)\)|(北京时间|UTC\+08:00|\+08:00)))?"
)


def printed_clock(value):
    match = VALUE.fullmatch(value.strip())
    printed_day, at, zone = None, None, None
    if match and (match[1] or match[4]):
        year, month, day = match.groups()[:3] if match[1] else match.groups()[3:6]
        try:
            printed_day = date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            match = None
    if match:
        at = ":".join(p for p in match.groups()[6:9] if p is not None)
        zone = "+08:00" if match[10] or match[11] else None
    return printed_day, at, zone


def source(unit, doc, page, line, quote, facts, *, bank):
    label, separator, value = normalize("NFKC", quote).strip().partition(":")
    label = label.strip()
    person = SIGNER.fullmatch(label) if not bank else None
    if not separator or not (person or bank and label in DEBIT | OTHER):
        return None
    kind = "signer" if person else "debit" if label in DEBIT else "other"
    printed_day, at, zone = printed_clock(value)
    ref = f"{doc}/p{page}/l{line}" if line else facts[0]["id"]
    return {"id": "joint-clock/" + ref, "unit": unit, "doc": doc, "page": page, "line": line,
            "quote": quote, "kind": kind, "name": person[1] if person else None, "day": printed_day, "at": at, "zone": zone,
            "facts": [f["id"] for f in facts], "disputed": any(f["status"] == "disputed" for f in facts)}


def legible(row):
    return bool(row["line"] and row["at"] and not row["disputed"])


def located_rows(ledger):
    return [*ledger["dates"], *ledger["clock_rows"]] if ledger.get("format") == FORMAT else []


def verify_geometry(report, read_layout=None):
    from contract_folios import line_numbers, verify_page_geometry

    graph = report["graph"]
    rows = located_rows(graph.get("acceptance_authority_sources", {}))
    observed = defaultdict(dict)
    facts = {f["id"]: f for f in graph["facts"]}
    for row in rows:
        for ref in row["facts"]:
            loc = facts[ref].get("source_line") or {}
            if row["line"] and loc.get("number") == row["line"] and loc.get("text") == row["quote"] and loc.get("rects"):
                observed[row["doc"], row["page"]][str(row["line"])] = loc["rects"]
    verify_page_geometry(report["calls"]["pages"], line_numbers(rows), observed, "signer_timing_rects", "签认与付款时序", read_layout)


def bank_dates(material, ledger):
    """Allow a distinct native time column to coexist with the payment date, irrespective of the model's field label."""
    if ledger.get("format") != FORMAT:
        return material
    by_location = {(r["doc"], r["page"], r["line"], r["quote"]): r for r in ledger["clock_rows"]
                   if r["unit"] == material.unit and legible(r)}
    excluded = set()
    for fact in material.refs:
        loc = fact.get("source_line") or {}
        row = by_location.get((fact["doc"], fact["page"], loc.get("number"), fact["quote"]))
        if (fact["field"] == "paid_on" and row and fact["id"] in row["facts"]
                and loc.get("rects") and loc.get("text") == fact["quote"]):
            excluded.add(fact["id"])
    if not excluded:
        return material
    filtered = copy.copy(material)
    filtered.fields = material.fields.copy()
    filtered.fields["paid_on"] = [f for f in material.fields["paid_on"] if f["id"] not in excluded]
    known = excluded | {f["id"] for f in filtered.fields["paid_on"]}
    if all(f["id"] in known for f in material.refs if f["field"] == "paid_on"):
        filtered.uncertain = material.uncertain - {"paid_on"}
    return filtered


def calendar(dates, clocks, names, paid):
    """Pair each person's date and time without resolving competing original rows."""
    result = list(dates)
    conflict = False
    for name in names:
        days = [r for r in dates if r["name"] == name]
        times = [r for r in clocks if r["kind"] == "signer" and r["name"] == name]
        if len(times) > 1:
            conflict = True
        elif times:
            row = times[0]
            if not days and row["day"] and legible(row):
                result.append(row)
            elif row["day"] and any(r["day"] != row["day"] for r in days):
                conflict = True
    debits = [r for r in clocks if r["kind"] == "debit"]
    conflict |= len(debits) > 1 or any(r["day"] and r["day"] != paid.isoformat() for r in debits)
    conflict |= any(r["kind"] == "signer" and r["name"] not in names for r in clocks)
    return result, conflict


def interval(at):
    """Half-open interval in seconds covered by a printed minute or second."""
    parts = [int(s) for s in at.split(":")]
    start = parts[0] * 3600 + parts[1] * 60
    if len(parts) == 3:
        return start + parts[2], start + parts[2] + 1
    return start, start + 60


def assess(rows, dates, names, paid, calendar_state, conflict):
    signers = {n: [r for r in rows if r["kind"] == "signer" and r["name"] == n] for n in names}
    daily = {n: [r for r in dates if r["name"] == n] for n in names}
    relevant = [n for n in names if len(daily[n]) == 1 and daily[n][0]["day"] == paid.isoformat()]
    debits = [r for r in rows if r["kind"] == "debit"]
    debit = debits[0] if len(debits) == 1 else None
    evidence = {"rows": [r["id"] for r in rows], "days": {n: daily[n][0]["id"] for n in names if len(daily[n]) == 1},
                "signers": {n: r[0]["id"] for n, r in signers.items() if len(r) == 1},
                "debit": debit["id"] if debit else None, "relevant": relevant}
    if calendar_state == "scope":
        return {**evidence, "state": "scope"}
    if conflict:
        return {**evidence, "state": "conflict"}
    if calendar_state != "same_day":
        return {**evidence, "state": "other_day" if calendar_state in ("before", "after") else "scope"}
    if not debit or not relevant or any(len(signers[n]) != 1 for n in relevant):
        return {**evidence, "state": "missing"}
    clocks = [signers[n][0] for n in relevant]
    if not all(legible(r) for r in [*clocks, debit]):
        return {**evidence, "state": "missing"}
    if any(r["zone"] != "+08:00" for r in [*clocks, debit]):
        return {**evidence, "state": "zone"}
    bounds = [interval(r["at"]) for r in clocks]
    start, end = interval(debit["at"])
    if end <= max(lower for lower, upper in bounds):
        return {**evidence, "state": "before"}
    if start >= max(upper for lower, upper in bounds):
        return {**evidence, "state": "after"}
    return {**evidence, "state": "overlap"}


DETAILS = {
    "before": "回单所列实际扣款早于至少一位约定验收人的签认时刻，需核实提前付款依据。",
    "after": "回单所列实际扣款晚于最后一栏签认时刻，其他付款前提仍须逐项核对。",
    "overlap": "扣款与最后签认所列的时间区间重叠，现有精度不能确定先后。",
    "zone": "同日扣款或签认时刻缺少可对应的时区记载，需取得同一时间基准。",
    "missing": "比较同日先后所需的实际扣款或具名签认时刻尚不完整。",
    "conflict": "签认日期、扣款日期或时间记录不唯一或相互冲突，需核对原件。",
}
