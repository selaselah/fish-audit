"""Determine which of two expressly prospective acceptance-payment clauses a transfer used."""

import hashlib
import re
from collections import defaultdict
from unicodedata import normalize

import invoice_conditions
from delegation import complete_id, is_page_marker, native_value


LABELS = {"previous_payment_stage": ("原付款条款", "变更前付款条款"),
          "revised_payment_stage": ("变更后付款条款", "新付款条款")}
SIGNAL = re.compile(r"(?:原|变更前|变更后|新)付款条款[:：]|(?:变更范围|变更适用时点)[:：].{0,40}(?:收票|付款前提|验收款)")
PRIOR = re.compile(r"(?P<stage>" + invoice_conditions.ORDINAL + r"):(?P<trigger>最终验收合格|终验合格|验收合格)后支付(?P<share>[0-9]{1,3}(?:\.[0-9]{1,4})?)%")
AMBIGUOUS = re.compile(r"[＊*×□…]|尾号|待定|待填|不详|同上|同(?:主)?合同")
PARTIES = ("buyer", "seller", "subject")
AGREEMENT = {"contract_addendum","base_contract_ref","addendum_number",*PARTIES,"change_scope","previous_payment_stage",
             "revised_payment_stage","change_timing","change_effect_clause","change_state","buyer_signature","seller_signature",
             "buyer_sealed_on","seller_sealed_on"}
SINCE = "2026.11.25.24"


def sources(graph, read_text):
    from graph import LABELS as field_labels, PRINTED_TITLES
    from performance import STAGE_PREFIX
    agreements = set(graph["documents_by_kind"].get("contract_addendum", []))
    if not agreements:
        return None
    units = agreements | set(graph["documents_by_kind"].get("contract", []))
    sections = {(d["source"],d["page"]):d["id"] for d in graph.get("audit_documents", []) if "source" in d}
    by_page = defaultdict(list)
    for f in graph["facts"]:
        by_page[f["doc"],f["page"]].append(f)
    names = {label:key for key, labels in field_labels.items() for label in labels}
    pages, lines = [], []
    relevant = False
    for node in graph["nodes"]:
        if node["type"]!="page":
            continue
        doc, suffix = node["id"].rsplit("/p", 1)
        number = int(suffix)
        unit = sections.get((doc,number),doc)
        if unit not in units:
            continue
        where = {"unit":unit,"doc":doc,"page":number}
        native = node.get("layer")=="text"
        pages.append({**where,"native":native,"text_only":node.get("clause_text_only") is True})
        anchored = defaultdict(list)
        for fact in by_page[doc,number]:
            loc = fact.get("source_line") or {}
            if unit in agreements and (fact["field"] in LABELS or SIGNAL.search(fact["quote"])):
                relevant = True
            if loc.get("rects"):
                anchored[loc["number"],loc["text"]].append(fact["id"])
        if not native:
            continue
        content = read_text(doc,number)
        if not isinstance(content,str) or hashlib.sha256(content.encode()).hexdigest()!=node.get("text_sha256"):
            raise ValueError("核对付款变更时原页文字摘要与归档不符")
        for index,raw in enumerate(content.splitlines(),1):
            if is_page_marker(raw):
                continue
            value = normalize("NFKC",raw).strip()
            label = value.partition(":")[0].strip()
            field = PRINTED_TITLES.get(value) or ("payment_stage" if STAGE_PREFIX.match(value) else names.get(label))
            lines.append({**where,"line":index,"quote":raw,"field":field,"facts":anchored[index,raw]})
            if unit in agreements and SIGNAL.search(value):
                relevant = True
    return {"pages":pages,"lines":lines} if relevant else None


def edges(ledger):
    if not ledger:
        return []
    return [{"from":row["unit"],"to":f"{row['doc']}/p{row['page']}","type":"payment_amendment_basis",
             "line":row["line"],"evidence":[f"{row['doc']}/p{row['page']}",*row["facts"]]}
            for row in ledger["lines"] if row["field"] in (*LABELS,"change_scope","change_timing","change_effect_clause",
                                                             "buyer_sealed_on","seller_sealed_on","payment_stage")]


def resolve(graph, contract, changes, *, base_decision, unassigned):
    import addendum_execution
    import addendum_originals
    from contract_changes import SEALS, SOURCE_LABELS
    from performance import day, printed_day
    ledger = graph.get("quality_addenda",{}).get("payments")
    if not ledger:
        return None
    lines, pages = ledger["lines"], ledger["pages"]
    ids = [f"{p['doc']}/p{p['page']}" for p in pages] + [ref for row in lines for ref in row["facts"]]
    units = list(dict.fromkeys(p["unit"] for p in pages))
    entry = {"scope_clear":False,"applies":"pending","effective_on":None,"buyer_on":None,"seller_on":None,
             "original_ref":None,"previous_ref":None,"revised_ref":None,"scope_ref":None,"timing_ref":None,
             "buyer_date_ref":None,"seller_date_ref":None,"effect_ref":None,"unit":None,"evidence":list(dict.fromkeys(ids)),"units":units}
    proof = addendum_execution.bind(entry, graph, [c.unit for c in changes])
    native_proof = addendum_originals.bind(entry, graph, [c.unit for c in changes])
    def decision(detail):
        if native_proof and detail != native_proof:
            detail += " " + native_proof
        return {**entry,"detail":detail}
    def reading(doc,field):
        rows = [s for s in lines if s["unit"]==doc.unit and s["field"]==field]
        facts = doc.fields[field]
        if len(rows)!=1 or len(facts)!=1 or doc.incomplete(field) or facts[0]["id"] not in rows[0]["facts"]:
            return "", None
        value = native_value(facts[0],SOURCE_LABELS[field])
        if not value or re.search(r"\s",value):
            return "", None
        return value,facts[0]["id"]
    def at(doc,field):
        raw,ref = reading(doc,field)
        value = day(raw)
        return (value,ref) if value and printed_day(doc,field)==value else (None,ref)
    if unassigned or len(changes)!=1 or changes[0].unit not in graph["documents_by_kind"].get("contract_addendum",[]):
        return decision("需先确定这一版补充协议与原合同、其余附件的归属。")
    agreement, = changes
    entry["unit"] = agreement.unit
    local = [s for s in lines if s["unit"]==agreement.unit]
    if (not pages or any(not p["native"] or not p["text_only"] for p in pages)
            or not local or any(s["field"] not in AGREEMENT for s in local)
            or graph["quality_addenda"]["limited_numbers"]
            or any(p["uncovered"] for p in graph["quality_addenda"]["pages"])):
        return decision("协议存在未归属的条款、影像、附注或不完整编号，请核实变更范围。")
    ident,_ = reading(contract,"contract_id")
    base,_ = reading(agreement,"base_contract_ref")
    number,_ = reading(agreement,"addendum_number")
    if (not complete_id(ident) or not complete_id(number) or ident!=base or ident==number
            or any(not reading(contract,k)[0] or AMBIGUOUS.search(reading(contract,k)[0]) or
                   reading(contract,k)[0]!=reading(agreement,k)[0] for k in PARTIES)
            or reading(contract,"buyer")[0]==reading(contract,"seller")[0]):
        return decision("协议编号、所引原合同、买卖双方及采购标的须逐项对应。")
    prior,entry["previous_ref"] = reading(agreement,"previous_payment_stage")
    changed,entry["revised_ref"] = reading(agreement,"revised_payment_stage")
    before,after = PRIOR.fullmatch(prior),invoice_conditions.INLINE.fullmatch(changed)
    matches = [s for s in lines if s["unit"]==contract.unit and s["field"]=="payment_stage" and
               invoice_conditions.text(s["quote"])==prior]
    native_clause = [f for f in contract.fields["payment_stage"] if len(matches)==1 and f["id"] in matches[0]["facts"]]
    if (not before or not after or any(before[k]!=after[k] for k in ("stage","trigger","share")) or len(native_clause)!=1
            or contract.incomplete("payment_stage")):
        return decision("需逐字勾稽原合同与协议修改前后的期次、验收前提及付款比例。")
    entry["original_ref"] = native_clause[0]["id"]
    stage = before["stage"]
    scope,entry["scope_ref"] = reading(agreement,"change_scope")
    timing,entry["timing_ref"] = reading(agreement,"change_timing")
    receipt_lines = graph.get("invoice_receipt_sources",{}).get("lines",[])
    revised_matches = [s for s in receipt_lines if s["role"]=="clause" and entry["revised_ref"] in s["facts"] and s["line"]]
    original_holds = any(s["unit"]==contract.unit and s["role"] in ("clause","qualification","unreviewed") for s in receipt_lines)
    effect_clause,entry["effect_ref"] = reading(agreement,"change_effect_clause")
    if (scope!=f"仅新增{stage}验收款收票前提,其余条款不变" or timing!=f"仅适用于本协议生效后支付的{stage}验收款"
            or effect_clause not in SEALS or len(revised_matches)!=1 or original_holds):
        return decision("需核对补充协议变更的事项、是否涉及既往付款及原合同的其他前提。")
    entry["scope_clear"] = True
    buyer,bref = at(agreement,"buyer_sealed_on")
    seller,sref = at(agreement,"seller_sealed_on")
    entry.update(buyer_on=buyer.isoformat() if buyer else None,seller_on=seller.isoformat() if seller else None,
                 buyer_date_ref=bref,seller_date_ref=sref)
    disposition = reading(agreement,"change_state")[0]
    if (any(s["field"]=="change_state" for s in local) and disposition not in ("已签署","已生效")):
        return decision("协议状态尚待确认，请取得双方最终签订的文本。")
    if proof or native_proof:
        return decision(proof or native_proof)
    for side in ("buyer","seller"):
        seal,ref = reading(agreement,side+"_signature")
        facts = agreement.fields[side+"_signature"]
        if (not seal or not ref or not agreement.signed(side+"_signature",reading(contract,side)[0],"seal")
                or not (facts[0].get("attestation") or {}).get("source_check")):
            return decision("协议仅涉及本期收票，双方签章或盖章日期尚待原件证实。")
    signed,_ = at(contract,"signed_on")
    effective,_ = at(contract,"effect_on")
    expires,_ = at(contract,"valid_until")
    has_expiry = any(s["unit"]==contract.unit and s["field"]=="valid_until" for s in lines)
    last_seal = day(base_decision.get("effect_review",{}).get("seals",{}).get("completed_on") or "")
    if (base_decision["status"]!="ok" or not signed or not effective or not buyer or not seller
            or min(buyer,seller)<=max(signed,effective,last_seal or effective)
            or has_expiry and (not expires or max(buyer,seller)>expires)):
        return decision("需核实原合同生效、有效期间和补充协议双方盖章的日期。")
    entry.update(applies="amended",effective_on=max(buyer,seller).isoformat())
    return decision("双方签章及适用时点有据，协议仅为本期新增收票前提。")


def at_payment(change, graph, contract, bank, paid):
    from payment_windows import located_day
    from warranty_terms import bank_identity
    dated,ref = located_day(bank,"paid_on")
    ledger = graph.get("payment_window_sources",{})
    pages = [p for p in ledger.get("pages",[]) if p["unit"]==bank.unit]
    notes = [row for row in ledger.get("lines",[]) if row["unit"]==bank.unit]
    refs = bank.evidence("bank_receipt","paid_on","contract_id","payer","payee","transfer_status","payment_designation")
    refs.extend(f"{p['doc']}/p{p['page']}" for p in pages)
    refs.extend(r for n in notes for r in n["facts"])
    entry = {**change,"applies":"pending","paid_on":None,"paid_ref":ref,
             "evidence":list(dict.fromkeys([*change["evidence"],*refs])),
             "units":list(dict.fromkeys([*change["units"],bank.unit]))}
    if (not paid or dated!=paid or not bank_identity(contract,bank) or not pages or notes
            or any(not p["native"] or not p["text_only"] for p in pages)):
        return {**entry,"detail":"需核实本笔回单的原始付款日期、交易状态和归属，确定当时适用的条款。"}
    when = paid.isoformat()
    entry["paid_on"] = when
    if change["applies"]!="amended":
        return entry
    cutover = change["effective_on"]
    applies = "original" if when<cutover else "amended" if when>cutover else "same_day"
    return {**entry,"applies":applies}


def attach(item, entry):
    item["payment_change"] = entry
    item["evidence"] = list(dict.fromkeys([*item["evidence"],*entry["evidence"]]))
    item["scope"] = list(dict.fromkeys([*item["scope"],*entry["units"]]))
    details = {"original":"本笔实付早于协议生效，按原合同验收款前提核对。",
               "same_day":"实付与协议生效同日，须取得双方盖章及付款时分以选择适用条款。"}
    if item["rule"]=="H05":
        details["amended"] = "付款时协议已生效，依变更后的验收及收票条款核对。"
    detail = details.get(entry["applies"],entry["detail"])
    if entry["applies"] in ("pending","same_day") and item["status"]=="ok":
        item.update(status="missing",detail=detail)
    else:
        item["detail"] += " " + detail
