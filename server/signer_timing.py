"""Compare the printed dates of a named joint final acceptance with one installment transfer."""

import re
from collections import Counter, defaultdict
from datetime import date
from unicodedata import normalize

from delegation import covered_rows
import signer_clock


FIRST_FORMAT = "named-acceptance-signatures-v2"
HEADER_INDEPENDENT_FORMAT = "named-acceptance-signatures-v3"
PRINTED_ROWS_FORMAT = "named-acceptance-signatures-v4"
FORMAT = signer_clock.FORMAT
FORMATS = (FIRST_FORMAT, HEADER_INDEPENDENT_FORMAT, PRINTED_ROWS_FORMAT, *signer_clock.FORMATS)
SINCE = "2026.11.26.21"
INDEPENDENT_SINCE = "2026.11.26.22"
PRINTED_ROWS_SINCE = "2026.11.26.23"
HINT = re.compile(r"(?:签认|签字|签署|签名|会签).{0,9}(?:日期|时间|日[：:])")
LABEL = re.compile(r"([\u3400-\u9fff]{2,8})(?:签认|签字|签署|签名)日期")
CHINESE_DAY = re.compile(r"([0-9]{4})年([0-9]{1,2})月([0-9]{1,2})日")
ISO_DAY = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
FINAL_SCOPES = {"全部交付终验", "全部交付最终验收", "全部标的最终验收", "最终验收", "终验"}


def dated_line(unit, doc, page, line, quote, facts):
    if not HINT.search(quote):
        return None
    label, _, body = normalize("NFKC", quote).strip().partition(":")
    name = LABEL.fullmatch(label.strip())
    match = CHINESE_DAY.fullmatch(body.strip()) or ISO_DAY.fullmatch(body.strip())
    day = None
    if match:
        try:
            day = date(*map(int, match.groups())).isoformat()
        except ValueError:
            pass
    page_id = f"{doc}/p{page}"
    key = f"{page_id}/l{line}" if line is not None else facts[0]["id"]
    return {"id": "signer-date/" + key, "unit": unit, "doc": doc, "page": page, "line": line,
            "quote": quote, "name": name[1] if name else None, "day": day,
            "facts": [f["id"] for f in facts], "disputed": any(f["status"] == "disputed" for f in facts)}


def bind_date_transcriptions(rows, pages):
    printed = defaultdict(dict)
    for row in rows:
        place = row["doc"],row["page"]
        if (row["line"] and row["name"] and row["day"] and not row["disputed"] and
                pages[f"{place[0]}/p{place[1]}"].get("clause_text_only") is True):
            printed[place][row["line"]] = row
    for observation in rows:
        if observation["line"] or observation["disputed"] or len(observation["facts"])!=1:
            continue
        lines = printed.get((observation["doc"],observation["page"]),{})
        matches = []
        for start,line in lines.items():
            text = observation["quote"]
            if not text.startswith(line["quote"]):
                continue
            run = []
            while text and (item:=lines.get(start+len(run))) and text.startswith(item["quote"]):
                run.append(item)
                text = text[len(item["quote"]):]
            if not text and len(run)>1 and len({r["name"] for r in run})==len(run):
                matches.append([r["id"] for r in run])
        if len(matches)==1:
            observation["printed_rows"] = matches[0]


def bank_pages(graph, read_text, pages):
    from stage_payments import BANK, is_printed

    units = set(graph["documents_by_kind"].get("bank_receipt", []))
    coverage = covered_rows(graph, read_text, units, BANK, is_printed, "共同签认对应的付款回单")
    for p in coverage:
        p["text_only"] = pages[f"{p['doc']}/p{p['page']}"].get("clause_text_only") is True
    return coverage


def source_graph(rows, clocks=()):
    nodes, edges = [], []
    for row in [*rows, *clocks]:
        page = f"{row['doc']}/p{row['page']}"
        node, edge = ("acceptance_clock_line", "acceptance_clock_source") if "kind" in row else ("acceptance_signer_date", "signer_date_source")
        nodes.append({"id": row["id"], "type": node, "label": row["quote"],
                      "doc": row["doc"], "page": row["page"], "line": row["line"]})
        edges.append({"from": page, "to": row["id"], "type": edge, "evidence": [page, *row["facts"]]})
        for ref in row.get("printed_rows", ()):
            edges.append({"from":row["id"],"to":ref,"type":"transcribed_signer_date","evidence":[*row["facts"],ref]})
    return nodes, edges


def expert_basis(graph, finding):
    timing = finding.get("signer_timing")
    if not timing or timing["format"]!=FORMAT or (len(timing["required"])<=2 and not timing.get("transcriptions")):
        return None
    ledger = graph["acceptance_authority_sources"]
    dates = set(timing["rows"]) | set(timing.get("transcriptions",()))
    clocks = set(timing.get("clock",{}).get("rows",()))
    return {"comparison":timing, "clause":[r for r in ledger["clauses"] if r["fact"] and r["fact"]==timing["clause_ref"]],
            "signatures":[r for r in ledger["signatures"] if r["unit"]==timing["receipt"]],
            "dates":[r for r in ledger["dates"] if r["id"] in dates],
            "clocks":[r for r in ledger["clock_rows"] if r["id"] in clocks]}


def verify_expert_basis(report):
    graph = report["graph"]
    expected = [(f["rule"],f["evidence"],basis) for f in report["findings"] if (basis:=expert_basis(graph,f))]
    packet = (report["calls"].get("expert") or {}).get("input") or {}
    actual = [(p["rule"],p["evidence"],p["joint_acceptance_timing"]) for p in packet.get("procedures",()) if "joint_acceptance_timing" in p]
    if expected!=actual:
        raise ValueError("专家所据会签名单、签认日期或对应付款检查与底稿不符")
    pages = {(p["doc"],p["page"]):p for p in report["calls"]["pages"]}
    for _,_,basis in expected:
        if basis["comparison"]["state"] not in ("before","after","same_day"):
            continue
        for row in [*basis["dates"],*basis["clocks"]]:
            if not row["line"]:
                continue
            call = pages.get((row["doc"],row["page"]),{})
            second = (call.get("check") or {}).get("response_id")
            if (not call.get("response_id") or not second or call["response_id"]==second or
                    not call.get("signer_timing_rects",{}).get(str(row["line"]))):
                raise ValueError("多人会签时序缺少独立读页记录或原行位置")


def compare(payment, graph, contract, bank, paid, authority, receipts, *, other_terms):
    from delivery_batches import body, raw_body
    from payment_reference import masked_value
    from reinspection import LINK_KEYS
    from stage_payments import printed
    from warranty_terms import bank_identity, identity

    source = graph.get("acceptance_authority_sources", {})
    version = source.get("format")
    if version not in FORMATS or not authority or authority["mode"] != "joint":
        return
    records = authority["records"]
    if len(records) != 1 or records[0]["role"] != "acceptance" or len(receipts) != 1:
        return
    receipt, record = receipts[0], records[0]
    names = authority["required"]
    observations = [r for r in source["dates"] if r["unit"] == receipt.unit]
    joined = [r for r in observations if version==FORMAT and r.get("printed_rows")]
    rows = [r for r in observations if r not in joined]
    clocks = [r for r in source.get("clock_rows", []) if version in signer_clock.FORMATS and
              (r["unit"] == receipt.unit and r["kind"] == "signer" or r["unit"] == bank.unit and r["kind"] in ("debit", "other"))]
    dates, conflict = signer_clock.calendar(rows, clocks, names, paid) if clocks else (rows, False)
    covered = [p for p in source["pages"] if p["unit"] in (contract.unit, receipt.unit)]
    banks = [p for p in source["bank_pages"] if p["unit"] == bank.unit]
    places = {(r["doc"], r["page"], r["line"], r["quote"]) for r in rows if r["line"]}
    places.update((r["doc"], r["page"], r["line"], r["quote"]) for r in clocks if signer_clock.legible(r))
    partial = {(g["doc"], g["page"]) for g in graph["gaps"] if g["quality"] in ("partial", "unreadable")}

    def clear(unit):
        pages = [p for p in [*covered, *banks] if p["unit"] == unit]
        if len(pages) != 1 or sum(unit in group for group in graph["documents_by_kind"].values()) != 1:
            return False
        p = pages[0]
        return (p["native"] and p["text_only"] and (p["doc"], p["page"]) not in partial and
                all((p["doc"], p["page"], x["line"], x["quote"]) in places for x in p["uncovered"]))

    signed = record["signed"]
    if version in (PRINTED_ROWS_FORMAT, *signer_clock.FORMATS):
        # Some extracts file an entire dated line under acceptance_signer. Its printed column
        # is still a date. Keep unlocated, disputed, or otherwise ambiguous signatures in scope.
        separate_dates = {(r["doc"], r["page"], r["line"], r["quote"]) for r in rows
                          if r["line"] and r["name"] in names and r["day"] and not r["disputed"]}
        separate_dates.update((r["doc"], r["page"], r["line"], r["quote"]) for r in clocks
                              if r["kind"] == "signer" and r["name"] in names and signer_clock.legible(r))
        joined_facts = {ref for r in joined for ref in r["facts"]}
        signed = [s for s in signed if s["name"] or (not joined_facts.intersection(s["facts"]) and
                  (not s["native"] or (s["doc"], s["page"], s["line"], s["quote"]) not in separate_dates))]
    checked_names = [s["name"] for s in signed if s["confirmed"]]
    clause = payment["stage"]["clause_ref"]
    term = next((f for f in contract.fields["payment_stage"] if f["id"] == clause), None)
    purpose, day = printed(bank, "payment_designation"), printed(bank, "paid_on")
    paid_ref = day["ref"] if day else None
    linked = (not other_terms and len(source["clauses"]) == 1 and all(clear(u) for u in (contract.unit, receipt.unit, bank.unit))
              and identity(contract, receipt) and bank_identity(contract, bank)
              and all(body(contract, k) and not masked_value(body(contract, k)) and
                      body(contract, k) not in {"同上", "待核", "未知", "无", "见附件", "略", "甲方", "乙方", "采购方", "供应方"} for k in LINK_KEYS)
              and body(receipt, "acceptance_scope") in FINAL_SCOPES and (version != FIRST_FORMAT or bool(record["date"]))
              and term and raw_body(term) == payment["stage"]["clause"] and purpose and purpose["value"] == payment["stage"]["name"] and day)
    complete = (len(signed) == len(names) and Counter(checked_names) == Counter(names)
                and not conflict and Counter(r["name"] for r in dates) == Counter(names)
                and all(r["line"] and r["day"] and not r["disputed"] for r in dates))
    latest, delta = None, None
    if not linked:
        state, detail = "scope", "需核对合同、终验范围、回单用途及原页附注后比对签认日期。"
    elif not complete:
        state, detail = "incomplete", "需核对每位约定验收人的独立签字及签认日期。"
    else:
        latest = max(r["day"] for r in dates)
        delta = (paid - date.fromisoformat(latest)).days
        if delta < 0:
            state, detail = "before", f"回单付款日 {paid} 早于最晚一栏签认日期 {latest}，相差 {-delta} 天。"
        elif delta == 0:
            state, detail = "same_day", f"回单与最晚签认日期同为 {paid}，需核对当日签认和扣款时分。"
        else:
            state, detail = "after", f"回单付款日 {paid} 晚于最晚一栏签认日期 {latest}，相差 {delta} 天。"
    refs = [*authority["clause_evidence"], *record["evidence"], *bank.evidence("paid_on", "payment_designation", "transfer_status"),
            clause, *(f"{p['doc']}/p{p['page']}" for p in [*covered, *banks])]
    for row in [*observations, *clocks]:
        refs.extend([row["id"], *row["facts"]])
    payment["signer_timing"] = {"format": version, "state": state, "bank": bank.unit, "receipt": receipt.unit,
        "required": names, "rows": [r["id"] for r in rows],
        "signed": {n: [s["fact"] for s in signed if s["name"] == n and s["confirmed"]] for n in names},
        "paid_on": paid.isoformat() if paid_ref else None, "paid_ref": paid_ref,
        "clause_ref": authority["clause_evidence"][0] if len(authority["clause_evidence"]) == 1 else None,
        "stage_ref": clause, "latest_on": latest, "days": delta}
    if joined:
        payment["signer_timing"]["transcriptions"] = [r["id"] for r in joined]
    clock_state = None
    if clocks:
        clock = signer_clock.assess(clocks, dates, names, paid, state, conflict)
        payment["signer_timing"]["clock"] = clock
        clock_state = clock["state"]
        if state != "scope" and clock_state in signer_clock.DETAILS:
            detail = signer_clock.DETAILS[clock_state]
    payment["evidence"] = list(dict.fromkeys([*payment["evidence"], *refs]))
    payment["scope"] = list(dict.fromkeys([*payment["scope"], receipt.unit]))
    early = state == "before" or clock_state == "before"
    if (early and payment["status"] in ("ok", "missing")) or (state != "after" and payment["status"] == "ok"):
        payment["status"] = "risk" if early else "missing"
        payment["detail"] = detail
    else:
        payment["detail"] += " " + detail
