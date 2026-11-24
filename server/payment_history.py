"""Derive cross-case payment keys and citations exclusively from verified workpaper facts."""

import hashlib
import json
import re

from calculations import money, normalized
from installments import RULE as INSTALLMENT_RULE, finding as installment_finding, installment_record
from payment_notes import note_refs, pending_notes
from payment_visibility import unchecked


LIMIT = 8
BASE_RULES = {"E01", "B01", "B02", "B03", "B04", "B05"}
HISTORY_RULES = {
    "B06": ("已签收底稿中的相同流水", "以银行回单上已核付款户名及完整流水号，在本工作区的已签收付款任务中精确查找。"),
    "B07": ("同合同多笔全额付款线索", "以合同号、收付双方和人民币元全额核对已人工通过的底稿，查找交易成功且流水号不同的另一笔全额付款。"),
    "B08": INSTALLMENT_RULE,
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def unmasked(value):
    return value and value not in {"未知", "不详", "略", "待核", "见附件"} and not re.search(r"[*＊…•●×]|[xX]{3,}", value)


def payment_record(graph, findings):
    record = receipt_keys(graph,findings)
    record["installment"] = installment_record(graph,findings,record["payer"],record["reference"])
    apply_reference_notes(record,graph.get("transfer_references",{}).get("facts",[]))
    return record


def apply_reference_notes(record, marked):
    if not marked:
        return
    record["installment"]["partial_reference"] = True
    if unchecked(marked):
        record["installment"]["visibility_unchecked"] = True
    extra = note_refs(marked)
    if extra:
        for name in ("same_refs","full_refs"):
            record[name] = list(dict.fromkeys([*record[name],*extra]))
        installment = record["installment"]
        installment["refs"] = list(dict.fromkeys([*installment["refs"],*extra]))
        if pending_notes(marked):
            installment["reference_note_pending"] = True


def comparable_record(graph, findings, marked):
    """Apply today's visible-source check to citations from any signed version, retaining its issued report."""
    record = payment_record(graph,findings)
    record["full_refs"] = list(dict.fromkeys([*record["full_refs"],*record["same_refs"]]))
    if marked:
        record.update(payer=None,reference=None,settlement=None)
        record["installment"]["entry"] = None
        apply_reference_notes(record,marked)
    return record


def receipt_keys(graph, findings):
    """Both keys are optional. A reused reference can be checked without assuming settlement."""
    record = {"payer": None, "reference": None, "settlement": None, "same_refs": [], "full_refs": []}
    receipts = graph["documents_by_kind"].get("bank_receipt", [])
    if len(receipts) != 1:
        return record
    bank = receipts[0]
    facts = {fact["id"]: fact for fact in graph["facts"]}
    controls = [f for f in findings if f["rule"] in BASE_RULES]
    record["full_refs"] = list(dict.fromkeys(ref for finding in controls for ref in finding["evidence"] if ref in facts))
    identity = [f for f in facts.values() if f.get("unit", f["doc"]) == bank and f["field"] in {"payer", "transfer_ref"}]
    record["same_refs"] = [f["id"] for f in identity]
    if any(f["status"] not in {"anchored", "confirmed"} for f in identity):
        return record
    links = {}
    for edge in graph["edges"]:
        if edge["from"] != bank:
            continue
        for ref in edge["evidence"]:
            fact = facts.get(ref)
            if fact and fact["field"] == edge["type"] and fact["status"] in {"anchored", "confirmed"}:
                links.setdefault(edge["type"], {})[normalized(fact["value"])] = fact

    def single(field):
        values = links.get(field, {})
        return next(iter(values.values())) if len(values) == 1 else None

    payer, reference = single("payer"), single("transfer_ref")
    if not payer or not reference:
        return record
    name, number = normalized(payer["value"]), normalized(reference["value"])
    if not (unmasked(name) and unmasked(number) and re.fullmatch(r"[A-Za-z0-9_-]{4,80}", number) and re.search(r"[A-Za-z0-9]", number)):
        return record
    record.update(payer=name, reference=number)
    if {f["rule"] for f in controls} != BASE_RULES or any(f["status"] != "ok" for f in controls):
        return record
    contract, payee, amount = single("contract_id"), single("payee"), single("transfer_amount")
    if not all((contract, payee, amount)):
        return record
    contract_id, beneficiary, paid = normalized(contract["value"]), normalized(payee["value"]), money(amount)
    if not (unmasked(contract_id) and unmasked(beneficiary) and paid is not None and paid > 0):
        return record
    key = [contract_id, name, beneficiary, format(paid, ".2f"), "CNY", "元"]
    record["settlement"] = hashlib.sha256(canonical(key)).hexdigest()
    return record


def cited_facts(graph, case_id, revision, refs):
    facts = {fact["id"]: fact for fact in graph["facts"]}
    citations = []
    for ref in refs:
        fact = facts[ref]
        citation = {k: fact[k] for k in ("doc", "page", "field", "label", "value", "quote", "status", "page_sha256", "source_sha256")}
        citations.append({**citation, "id": f"prior/{case_id}/r{revision}/{ref}", "fact": ref})
    return citations


def payment_matches_with_evidence(history):
    return [*history["matches"],*history.get("installments",{}).get("matches",[])]


def attach_history(graph, history):
    graph["payment_history"] = history
    known = {node["id"] for node in graph["nodes"]}
    for match in payment_matches_with_evidence(history):
        for fact in match["evidence"]:
            if fact["id"] not in known:
                graph["nodes"].append({"id": fact["id"], "type": "archived_observation", "label": fact["label"]})
                known.add(fact["id"])


def check_history(signature, history, record, scope):
    for rule, key, required, refs_key in (("B06", "same", "reference", "same_refs"), ("B07", "full", "settlement", "full_refs")):
        refs = list(signature[refs_key] or signature["same_refs"])
        if not signature[required]:
            detail = ("请核实单份回单的完整付款户名和交易流水号。" if key == "same" else
                      "核对同合同多笔全额付款需要已核实的收付主体、账户、一次全额条款、正金额、币种、交易状态及日期。")
            if signature["installment"].get("partial_reference"):
                detail = "原回单仅提供部分流水号。取得完整流水后可核对已签收回单。" if key=="same" else "本案流水号待补全，暂缓核对同合同的其他全额付款。"
            if signature["installment"].get("reference_note_pending"):
                detail = "回单同页有一条待核的流水展示说明，请先对照页图核实流水号的完整性。"
            if signature["installment"].get("visibility_unchecked"):
                detail = "流水栏的可见字符已核对。请对照整张回单，确认流水号是否完整显示。"
            record(rule, "missing", detail, refs, scope)
            continue
        matches = [m for m in history["matches"] if m["kind"] == key]
        count = history["counts"][key]
        if key == "same":
            detail = (f"同一付款户名及流水号「{signature['reference']}」出现在 {count} 份已签收底稿中。请核对是否为补件、回单副本或重复申请。"
                      if count else "在本工作区已签收、可核对完整流水号的付款底稿中，未找到相同付款户名和流水号。")
        else:
            detail = (f"有 {count} 份已人工通过的底稿记载同一合同、同一收付双方、相同人民币全额及另一成功流水。请核对银行对账单、冲正及退款。"
                      if count else "在本工作区已人工通过且可比的付款底稿中，未找到同合同、同主体、同全额的其他成功流水。")
        for match in matches:
            refs.extend(f["id"] for f in match["evidence"])
        if count > len(matches):
            detail += f"列示最近签收的 {len(matches)} 份。"
        record(rule, "risk" if count else "ok", detail + " 核查时点 " + history["as_of"], refs, scope)
    if "installments" in history:
        status,detail,refs = installment_finding(signature["installment"],history["installments"],history["as_of"])
        record("B08",status,detail,refs,scope)
