"""Match a contractual receipt-before-payment condition to original, dated buyer evidence."""

import hashlib
import re
import unicodedata
from collections import defaultdict

from delegation import complete_id, is_page_marker, native_value


FORMAT = "stage-invoice-receipt-v1"
SINCE = "2026.11.25.23"
LABELS = {
    "invoice_receipt_clause": ("验收款支付前提", "验收款付款前提", "收票约定", "收票条件", "付款收票条件"),
    "received_invoice_id": ("签收发票号码", "本次签收发票号码"),
    "invoice_received_on": ("收票日期", "发票签收日期"),
    "invoice_received_seal": ("收票方签章", "收票单位盖章"),
}
KEYS = ("contract_id", "buyer", "seller")
SOURCE = {**LABELS, "contract_id": ("合同编号", "合同号"),
          "buyer": ("采购方", "购买方", "买方", "甲方", "购方"),
          "seller": ("供应方", "销售方", "卖方", "乙方", "销方"),
          "invoice_id": ("发票号码", "票据号码", "发票号"), "issued_on": ("开票日期", "开具日期")}
FIELDS_BY_LABEL = {label: field for field, labels in SOURCE.items() for label in labels}
ORDINAL = r"第[一二两三四五六七八九十百0-9]+期"
TARGET = re.compile(ORDINAL + r"|验收款|预付款|首付款|质保金|尾款|进度款")
RECEIPT = r"(?:采购方|买方|甲方)(?:须|已)?收到(?:供应方就本合同开具的|本合同对应的)发票"
INLINE = re.compile(r"(?P<stage>" + ORDINAL + r"|验收款):(?P<trigger>最终验收合格|终验合格|验收合格)且" +
                    RECEIPT + r"后支付(?P<share>[0-9]{1,3}(?:\.[0-9]{1,4})?)%")
RIDER = re.compile(r"(?P<stage>" + ORDINAL + r"|验收款|首付款|预付款|质保金)(?:支付|付款)前提:" + RECEIPT)
INVOICE_TERM = re.compile(r"先票后款|票到|收票|收妥.{0,20}票|(?:发票|票据).{0,12}(?:签收|送达)|(?:收[到齐]|取得|签收).{0,55}(?:发票|票据)")
PAYMENT = re.compile(r"款|支付|结算|第.{1,5}期")
INVOICE_HOLD = re.compile(r"红冲|冲红|作废|红字|退票|撤回|退回|拒收|未收|尚未收到|收票.{0,8}(?:待核|待确认)|仅.{0,8}尾号|另附|另见")
SCOPES = {"验收款":"acceptance", "首付款":"effect", "预付款":"effect", "质保金":"warranty"}


def text(raw):
    return unicodedata.normalize("NFKC", raw).strip().rstrip("。")


def clause(raw):
    value = text(raw)
    if not (INVOICE_TERM.search(value) or "发票" in value and PAYMENT.search(value)):
        return None
    matched = INLINE.fullmatch(value) or RIDER.fullmatch(value)
    targets = [matched["stage"]] if matched else list(dict.fromkeys(TARGET.findall(value)))
    return {"supported": bool(matched), "targets": targets}


def sources(graph, read_text):
    units = {unit: kind for kind in ("contract", "contract_addendum", "invoice", "acceptance")
             for unit in graph["documents_by_kind"].get(kind, [])}
    sections = {(d["source"], d["page"]): d["id"] for d in graph.get("audit_documents", []) if "source" in d}
    by_page = defaultdict(list)
    for f in graph["facts"]:
        by_page[f["doc"], f["page"]].append(f)
    pages, lines = [], []
    for node in graph["nodes"]:
        if node["type"] != "page":
            continue
        doc, suffix = node["id"].rsplit("/p", 1)
        page = int(suffix)
        unit = sections.get((doc, page), doc)
        kind = units.get(unit)
        if not kind:
            continue
        place = {"unit": unit, "doc": doc, "page": page}
        native = node.get("layer") == "text"
        where = {**place, "native": native, "text_only": node.get("clause_text_only") is True}
        pages.append(where)
        def record(raw, number, facts):
            refs = [f["id"] for f in facts]
            label = text(raw).partition(":")[0].strip()
            term = clause(raw) if kind in ("contract", "contract_addendum") else None
            field = FIELDS_BY_LABEL.get(label)
            if term:
                lines.append({**place, "role":"clause", "quote":raw, "line":number, "facts":refs,
                              **term, "supported":bool(term["supported"] and kind=="contract" and number)})
            elif field and field != "invoice_receipt_clause":
                lines.append({**place, "role":field, "quote":raw, "line":number, "facts":refs})
            elif kind in ("invoice", "acceptance") and (INVOICE_HOLD.search(raw) or INVOICE_TERM.search(raw)):
                lines.append({**place, "role":"qualification", "quote":raw, "line":number, "facts":refs})
            elif number and not is_page_marker(raw) and not any(
                    f["field"]!="other" and f["status"] in ("anchored","confirmed") for f in facts):
                lines.append({**place, "role":"unreviewed", "quote":raw, "line":number, "facts":refs})
        anchored = defaultdict(list)
        for f in by_page[doc, page]:
            loc = f.get("source_line") or {}
            if native and loc.get("rects"):
                anchored[loc["number"], loc["text"]].append(f)
            else:
                record(f["quote"], None, [f])
        if native:
            original = read_text(doc, page)
            if not isinstance(original, str) or hashlib.sha256(original.encode()).hexdigest() != node.get("text_sha256"):
                raise ValueError("收票条件所据的原页文字摘要不符")
            for number, raw in enumerate(original.splitlines(), 1):
                record(raw, number, anchored[number, raw])
    if not any(s["role"]=="clause" for s in lines):
        return {"format":FORMAT, "pages":[], "lines":[]}
    return {"format":FORMAT, "pages":pages, "lines":lines}


def edges(ledger):
    return [{"from":s["unit"], "to":f"{s['doc']}/p{s['page']}", "type":"stage_invoice_clause",
             "line":s["line"], "evidence":s["facts"] or [f"{s['doc']}/p{s['page']}"]}
            for s in ledger["lines"] if s["role"]=="clause"]


def targets(s, rows):
    return {i for i, r in enumerate(rows) if r["label"] in s["targets"] or any(
        target in SCOPES and r["kind"]==SCOPES[target] for target in s["targets"])}


def applicable(s, rows, index):
    exact = targets(s, rows)
    # Unassigned terms may apply to any of the contract’s phases.
    return not exact or index in exact


def condition(ledger, contract, invoices, receipts, rows, index):
    from performance import day, printed_day
    clauses = [s for s in ledger["lines"] if s["role"]=="clause" and applicable(s, rows, index)]
    if not clauses:
        return None
    involved = [contract, *invoices, *receipts]
    units = {d.unit for d in involved} | {s["unit"] for s in clauses}
    all_lines = [s for s in ledger["lines"] if s["unit"] in units]
    pages = [p for p in ledger["pages"] if p["unit"] in units]
    def clean(unit):
        owned = [p for p in pages if p["unit"]==unit]
        return bool(owned) and all(p["native"] and p["text_only"] for p in owned)
    def reading(doc, field):
        physical = [s for s in all_lines if s["unit"]==doc.unit and s["role"]==field]
        facts = doc.fields[field]
        if len(physical)!=1 or len(facts)!=1 or doc.incomplete(field) or facts[0]["id"] not in physical[0]["facts"]:
            return "", None
        value = native_value(facts[0], SOURCE[field])
        if not value or re.search(r"\s", value):
            return "", None
        return value, facts[0]["id"]
    def identity(doc):
        return [reading(doc, k)[0] for k in KEYS]
    def reasons(doc):
        return [s for s in all_lines if s["unit"]==doc.unit and s["role"] in ("qualification","unreviewed")]
    base = identity(contract)
    linked = all(base) and complete_id(base[0]) and base[1]!=base[2]
    supported = clean(contract.unit) and not reasons(contract) and all(s["supported"] and s["unit"]==contract.unit and len(targets(s, rows))==1 for s in clauses)
    invoice = {"status":"missing", "number":None, "issued_on":None, "number_ref":None, "date_ref":None}
    receipt = {"status":"missing", "number":None, "received_on":None, "number_ref":None, "date_ref":None, "seal_ref":None}
    issue_day = None
    if len(invoices)==1:
        doc = invoices[0]
        number, number_ref = reading(doc, "invoice_id")
        dated, date_ref = reading(doc, "issued_on")
        issue_day = day(dated)
        invoice.update(number=number or None, number_ref=number_ref, date_ref=date_ref,
                       issued_on=issue_day.isoformat() if issue_day else None)
        if (linked and identity(doc)==base and clean(doc.unit) and re.fullmatch(r"[0-9]{20}", number)
                and issue_day and printed_day(doc, "issued_on")==issue_day and not reasons(doc)):
            invoice["status"] = "ok"
    registry = [doc for doc in receipts if any(s["unit"]==doc.unit and s["role"] in (
        "received_invoice_id","invoice_received_on","invoice_received_seal","qualification") for s in all_lines)]
    if len(registry)==1:
        doc = registry[0]
        number, number_ref = reading(doc, "received_invoice_id")
        dated, date_ref = reading(doc, "invoice_received_on")
        _, seal_ref = reading(doc, "invoice_received_seal")
        received = day(dated)
        receipt.update(number=number or None, number_ref=number_ref, date_ref=date_ref, seal_ref=seal_ref,
                       received_on=received.isoformat() if received else None)
        if (invoice["status"]=="ok" and identity(doc)==base and clean(doc.unit) and not reasons(doc)
                and number==invoice["number"] and received and printed_day(doc, "invoice_received_on")==received
                and issue_day<=received and seal_ref and doc.signed("invoice_received_seal", base[1], "seal")
                and len({ref.rsplit("/f",1)[0] for ref in (number_ref,date_ref,seal_ref)})==1):
            receipt["status"] = "ok"
    holds = [s for s in all_lines if s["role"] in ("qualification","unreviewed")]
    refs = [f"{p['doc']}/p{p['page']}" for p in pages]
    refs += [ref for s in all_lines if s["role"]!="clause" or s in clauses for ref in s["facts"]]
    return {"status":"ok" if supported and receipt["status"]=="ok" else "missing", "scope_clear":supported,
            "clauses":clauses, "invoice":invoice, "receipt":receipt, "qualifications":holds,
            "evidence":list(dict.fromkeys(refs)), "units":sorted(units)}


def attach(check, entry):
    if not entry:
        return
    check["invoice_receipt"] = entry
    check["evidence"] = list(dict.fromkeys([*check["evidence"], *entry["evidence"]]))
    check["scope"] = list(dict.fromkeys([*check["scope"], *entry["units"]]))
    if not entry["scope_clear"]:
        detail = "合同另有发票约定，适用期次或完整收票条件须核对原文。"
    elif entry["invoice"]["status"]!="ok":
        detail = "本期约定先收票，需核对合同、购销双方、完整发票号码和开票日期。"
    elif entry["receipt"]["status"]!="ok":
        detail = "本期约定先收票，尚缺可与该发票匹配的买方签收记录。"
    else:
        detail = "收票登记与合同、发票原件相符。"
    if check["status"]=="ok" and entry["status"]!="ok":
        check.update(status="missing", detail=detail)
    else:
        check["detail"] += " " + detail


def reconcile_payment(payment, check, graph, contract, bank, paid):
    from payment_windows import located_day
    from warranty_terms import bank_identity
    entry = check.get("invoice_receipt")
    if not entry:
        return
    payment["invoice_receipt"] = entry
    paid_day, _ = located_day(bank, "paid_on")
    pages = [p for p in graph.get("payment_window_sources", {}).get("pages", []) if p["unit"]==bank.unit]
    holds = any(s["unit"]==bank.unit for s in graph.get("payment_window_sources", {}).get("lines", []))
    if (entry["status"]!="ok" or not paid or paid!=paid_day or not bank_identity(contract, bank)
            or not pages or not all(p["native"] and p["text_only"] for p in pages) or holds):
        if payment["status"]=="ok":
            payment.update(status="missing", detail="需核对本期收票前提和成功回单的原始记载。")
        return
    received = entry["receipt"]["received_on"]
    if paid.isoformat()<received:
        payment.update(status="risk", detail=f"回单付款日 {paid} 早于买方收票日 {received}，请核查提前支付的依据。")
    elif paid.isoformat()==received and payment["status"] not in ("risk", "issue"):
        payment.update(status="missing", detail=f"付款与收票同为 {paid}，需取得当日具体时分以核对先后。")


def verify(report, read_text, *, signing=False):
    graph, policy = report["graph"], report["policy"]
    marker = policy.get("invoice_receipt_conditions")
    actual = [e for e in graph["edges"] if e["type"]=="stage_invoice_clause"]
    if marker is None:
        if (policy.get("version", "")>=SINCE or "invoice_conditions.py" in policy.get("code_sha256", {})
                or "invoice_receipt_sources" in graph or actual):
            raise ValueError("底稿缺少对应的分期收票核查版本")
        if signing and any(f["rule"] in ("H04","H05") and f["status"]=="ok" for f in report["findings"]):
            from performance import compute
            ledger = sources(graph, read_text)
            if any(s["role"]=="clause" for s in ledger["lines"]):
                previous = {(f["rule"], f["stage"]["clause_ref"], f["stage"]["name"]) for f in report["findings"]
                            if f["rule"] in ("H04","H05") and f["status"]=="ok" and f.get("stage")}
                for item in compute({**graph, "invoice_receipt_sources":ledger}):
                    stage = item.get("stage") or {}
                    if item.get("invoice_receipt") and (item["rule"], stage["clause_ref"], stage["name"]) in previous:
                        raise ValueError("旧版已通过的期款尚未核对约定收票前提，请重新审计后签收。")
        return
    expected = sources(graph, read_text)
    if marker!=FORMAT or graph.get("invoice_receipt_sources")!=expected or actual!=edges(expected):
        raise ValueError("合同收票条件、所据原行或证据关系与归档不符")
