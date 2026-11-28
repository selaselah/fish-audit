"""Evidence-based checks for contract effectiveness, acceptance and payment milestones."""

import re
import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal
from reinspection import LABELS as REINSPECTION_FIELDS, LINK_KEYS, assess as assess_reinspection, linked as same_contract, verify_number_links
from delegation import TERM_FORMATS as MANDATE_TERM_FORMATS, LABELS as DELEGATION_FIELDS, PARTY_SIGNATURES, checks as check_delegations, complete_id
from contract_changes import LABELS as ADDENDUM_FIELDS, LIMIT, SOURCE_LABELS, candidates as change_candidates, labelled_sources, resolve as resolve_change
from acceptance_authority import LABELS as AUTHORITY_FIELDS, SIGN_LABELS, check as check_acceptance_authority
import delivery_batches
import stage_payments
import advance_guarantee
import payment_acceptance
import payment_execution
import signer_timing
import signer_clock
import equipment_models
import equipment_exchanges
import contract_effect
import board_execution
import pdf_execution
import mandate_execution
import mandate_originals
import acceptance_execution
import acceptance_originals
import addendum_execution
import contract_calendar
import signing_parties
import inspection_coverage
import contract_folios
import prior_installment
import warranty_terms
import warranty_execution
import warranty_dates
import payment_quality
import retest_reference
import inspection_use
import installment_approval
import approval_names
import approval_changes
import party_readings
import installment_counts
import warranty_service
import warranty_register
import payment_windows
import invoice_conditions
import payment_amendments
import acceptance_comments
import contract_comments
import acceptance_reservations
import inspection_register
import acceptance_payments
import payment_releases
import release_execution
import release_comparison
import repair_completion
import reinspection_wait
from performance_versions import (FIRST_FORMAT, BOARD_FORMAT, REINSPECTION_FORMAT, DELEGATION_FORMAT, IDENTITY_FORMAT,
                                  NATIVE_FORMAT, ADDENDUM_FORMAT, SIGNATORY_FORMAT, DATE_FORMAT, BATCH_FORMAT, FORMAT,
                                  PAYMENT_WINDOW_FORMATS, WARRANTY_FORMATS, EFFECT_FORMATS, BATCH_FORMATS, DATE_FORMATS, SIGNATORY_FORMATS, ADDENDUM_FORMATS,
                                  MANDATE_FORMATS, SUPPORTED)


PROFILE = "cn-contract-performance/v1"
RULES = {
    "H01": ("合同签署与约定生效条件", "核对合同双方、签订日期、生效条款和签署栏的人工核图记录，保留附加条件及状态疑点。"),
    "H02": ("交付范围与验收质量", "按合同编号、标的和采购方关联验收资料，核对日期、验收范围、结论、签认和遗留事项。"),
    "H03": ("付款安排与期次完整性", "从合同原文提取期次及付款条件，按约定核对期序、期数及比例合计。"),
    "H04": ("本期付款条件", "逐期核对合同写明的付款前提与履约证据，分别列示预付款、验收款和质保金等约定。"),
    "H06": stage_payments.RULE,
    "H07": warranty_register.RULE,
    "H05": ("实付日期与合同前提", "按同一合同、回单明列期次及付款日期，核对付款时点已有的履约证据。"),
}
LABELS = {
    **REINSPECTION_FIELDS,
    **DELEGATION_FIELDS,
    **ADDENDUM_FIELDS,
    **AUTHORITY_FIELDS,
    **equipment_exchanges.LABELS,
    "equipment_model": tuple(sorted(equipment_models.ORDERED | equipment_models.RECEIVED)),
    **delivery_batches.LABELS,
    **payment_acceptance.LABELS,
    **warranty_terms.LABELS,
    **signing_parties.IMPRINT_FIELDS,
    **inspection_coverage.LABELS,
    **prior_installment.LABELS,
    **warranty_service.LABELS,
    **payment_windows.LABELS,
    **invoice_conditions.LABELS,
    "effect_clause": ("生效条款", "合同生效条件", "生效条件", "合同生效条款"),
    **PARTY_SIGNATURES,
    "contract_state": ("合同状态", "协议状态"),
    "valid_until": ("合同有效期至", "合同有效截止日"),
    "acceptance_criteria": ("约定验收标准", "合同验收标准"),
    "inspection_basis": ("实测验收标准", "实际验收标准", "检验依据"),
    "measured_result": ("实测结果", "检测结果", "实测数据"),
    "quantity_agreed": ("约定交付数量", "合同交付数量"),
    "quantity_accepted": ("实际验收数量", "验收数量"),
    "acceptance_scope": ("验收范围", "验收批次", "验收阶段", "复验范围"),
    "acceptance_signer": SIGN_LABELS,
    "acceptance_exception": ("遗留事项", "整改事项", "保留事项", "整改结论"),
    "payment_stage": ("付款期次", "首付款", "预付款", "进度款", "验收款", "质保金", "尾款"),
    "warranty_release": ("质保期满确认", "质保期满记录"),
    "effect_on": ("实际生效日期", "生效确认日期"),
    "approval_authority": ("审批机构", "决议机构"),
    "approval_result": ("审批决定", "决议结果"),
    "approved_on": ("审批日期", "决议日期"),
    "release_signed_on": ("放行签字日期",),
    "approval_signer": ("审批签认", "决议签认"),
    "payment_designation": ("付款期次说明", "款项用途", "转账用途", "付款用途"),
}
FIELD_NAMES = {k: names[0] for k, names in LABELS.items()}
ORD = r"[一二两三四五六七八九十\d]+"
STAGE_PREFIX = re.compile(r"^(?:第(" + ORD + r")期|(" + "|".join(LABELS["payment_stage"][1:]) + r"))[:、]")
CHINESE = dict(zip("一二三四五六七八九十两", (1,2,3,4,5,6,7,8,9,10,2)))
SIGNATURE = r"(?:[（(](?:已盖章|已签章|已签字|已签名)[）)]|已盖章|已签章|已签字|已签名)"
PARTIES = r"(?:甲乙|合同)?双方"
EFFECT = re.compile(r"(?:本合同|合同|本协议)?(?:自|经|在)?" + PARTIES +
                    r"(?:签字或盖章|签名或盖章|签署|签章|盖章|签字|签名)(?:之日|当日)?(?:起|后|时)?(?:即)?生效")
BOARD_CONDITION = re.compile(r"(?:本合同|合同|本协议)?(?:自|经)?" + PARTIES +
                             r"(?:签字或盖章|签名或盖章|签署|签章|盖章|签字|签名)(?:并|且)(?:经)?"
                             r"(甲方|乙方|采购方|供应方)董事会批准(?:之日|当日)?(?:起|后|时)?(?:即)?生效")
FINAL_SCOPES = {"全部","全部交付","全部交付终验","全部交付最终验收","全部标的最终验收","最终验收","整体验收","终验","全量验收"}
PASS = {"合格","验收合格","全部合格","通过","验收通过","最终验收合格","终验合格"}
FAILED_ACCEPTANCE = {"不合格","验收不合格","未通过","验收未通过","拒收","最终验收不合格","终验不合格"}
CLEAN = {"无","无遗留事项","无保留事项","无整改事项","无异常"}
SIMPLE_FULL = {"一次性全额结算","一次性付清","一次性全额付款","一次结清","一次性结清","一次付清"}
CONDITIONS = {
    "effect": ("合同生效","本合同生效"),
    "acceptance": ("最终验收合格","终验合格","验收合格","验收通过","全部验收合格"),
    "warranty": ("质保期满","质保期届满","保修期满"),
}


def norm(value):
    return "".join(unicodedata.normalize("NFKC", value).split()).strip("。;")


def number(value):
    return int(value) if value.isascii() and value.isdigit() and len(value) < 4 else CHINESE.get(value)


def day(value):
    match = re.fullmatch(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", value)
    try:
        return date(*map(int, match.groups())) if match else None
    except ValueError:
        return None


def row_body(fact):
    line = norm(fact["quote"])
    return line.split(":", 1)[1] if ":" in line else line


def complete_line(field, value, quote):
    """Bind an entire clause, including negations and trailing conditions."""
    value, quote = norm(value), norm(quote)
    if field==payment_windows.FIELD:
        label,sep,body=quote.partition(":")
        return bool(sep and body and payment_windows.label_matches(label) and value in (quote,body))
    if field == "payment_stage":
        prefix = STAGE_PREFIX.match(quote)
        if prefix:
            return value in (quote, quote[prefix.end():])
    for label in LABELS.get(field, ()):
        if quote.startswith(label + ":"):
            return value in (quote, quote[len(label) + 1:])
    return field == "effect_clause" and value == quote and "合同" in quote and "生效" in quote


class Material:
    def __init__(self, graph, unit):
        self.unit = unit
        self.calendar = contract_calendar.by_field(graph.get("contract_effect_sources", {}), unit)
        self.mandate_format = graph.get("delegation_coverage", {}).get("format")
        self.mandate_pages = [p for p in graph.get("delegation_coverage", {}).get("pages", []) if p["unit"]==unit]
        self.agent_holds = [h for h in graph.get("delegation_coverage", {}).get("agent_holds", []) if h["unit"]==unit]
        self.signer_holds = [h for h in graph.get("delegation_coverage", {}).get("signer_holds", []) if h["unit"]==unit]
        self.quality_holds = [h for h in graph.get("quality_references", {}).get("holds", []) if h["unit"] == unit]
        self.party_rows = {r["field"]:r for r in graph.get(party_readings.KEY,{}).get("rows",())
                          if r["unit"]==unit and r["state"]=="same_line"}
        self.fields = defaultdict(list)
        self.refs = []
        self.gaps = []
        self.uncertain = set()
        doc = next((d for d in graph.get("audit_documents", graph["documents"]) if d["id"] == unit), {})
        source = doc.get("source", unit)
        page = doc.get("page")
        owned = {(edge["type"], ref) for edge in graph["edges"] if edge["from"] == unit for ref in edge["evidence"]}
        for fact in graph["facts"]:
            if fact.get("unit", fact["doc"]) != unit:
                continue
            field = fact["field"]
            self.refs.append(fact)
            if fact["status"] in ("anchored","confirmed") and (field, fact["id"]) in owned:
                pair = self.party_rows.get(field)
                if not pair or fact["id"]!=pair["added_ref"]:
                    self.fields[field].append(fact)
            else:
                self.uncertain.add(field)
        self.gaps = [g for g in graph.get("gaps", []) if g["doc"] == source and (page is None or page == g["page"])]
        self.notes = [n for n in graph.get("cautions", []) + graph.get("performance_cautions", []) if n["doc"] == source and
                      (page is None or n["page_id"] == f"{source}/p{page}")]

    def evidence(self, *fields):
        refs = [f["id"] for f in self.refs if f["field"] in fields]
        refs += [g["id"] for g in self.gaps if not g.get("field") or g["field"] in fields]
        for field in fields:
            for row in self.calendar.get(field, []):
                refs.extend([row["id"], f"{row['doc']}/p{row['page']}", *row["facts"]])
        return list(dict.fromkeys(refs))

    def incomplete(self, *fields):
        return bool(self.uncertain.intersection(fields) or any(not g.get("field") or g["field"] in fields for g in self.gaps))

    def single(self, field):
        rows = self.fields[field]
        values = {norm(f["value"]) for f in rows}
        return next(iter(values)) if len(values) == 1 and not self.incomplete(field) else ""

    def date(self, field):
        if field in self.calendar:
            _, value = contract_calendar.reading(self.calendar[field], self)
            return date.fromisoformat(value) if value else None
        return day(self.body(field))

    def declared_date(self, field):
        return self.date(field) if field in self.calendar else day(self.single(field))

    def body(self, field):
        rows = self.fields[field]
        values = {row_body(f) for f in rows}
        return next(iter(values)) if len(values) == 1 and not self.incomplete(field) else ""

    def signed(self, field, party=None, mode=None):
        value = self.body(field)
        if not value or not any(f["status"] == "confirmed" for f in self.fields[field]):
            return False
        match = re.fullmatch(r"(.+?)" + SIGNATURE, value)
        if not match or (party is not None and match[1] != party):
            return False
        if mode == "seal" and "已盖章" not in value:
            return False
        if mode == "sign" and not any(s in value for s in ("已签字","已签名")):
            return False
        return True


def result(rule, status, detail, refs, units, stage=None):
    item = dict(rule=rule,status=status,detail=detail,evidence=list(dict.fromkeys(refs)),scope=list(dict.fromkeys(units)))
    if stage is not None:
        item["stage"] = stage
    return item


DATE_LABELS = {**SOURCE_LABELS, "accepted_on":("验收日期","验收时间","复验日期","复验时间"),"release_signed_on":("放行签字日期",),
               **{key:DELEGATION_FIELDS[key] for key in ("granted_on","grant_from","grant_until")},
               "repaired_on":REINSPECTION_FIELDS["repaired_on"],
               "issued_on":invoice_conditions.SOURCE["issued_on"], "invoice_received_on":invoice_conditions.LABELS["invoice_received_on"],
               "paid_on":("付款日期","转账日期","交易日期","支付日期")}


def printed_day(material, field):
    parsed = material.date(field)
    if field in material.calendar:
        return parsed
    if not parsed:
        return None
    for fact in material.fields[field]:
        source = fact.get("source_line") or {}
        if not source.get("rects") and not (fact.get("attestation") or {}).get("source_check"):
            return None
        for raw in (fact["quote"],source.get("text",fact["quote"])):
            label,sep,value = unicodedata.normalize("NFKC",raw).partition(":")
            if (not sep or norm(label) not in DATE_LABELS[field] or re.search(r"\d\s+\d",value)
                    or day(norm(value))!=parsed or norm(fact["value"]) not in (norm(raw),norm(value))):
                return None
    return parsed


def date_check(event, status, detail, evidence):
    return {"event":event, "status":status, "detail":detail, "evidence":list(dict.fromkeys(evidence))}


def add_date_checks(finding, checks):
    if not checks:
        return
    finding["date_checks"] = checks
    severity = {"ok":0,"missing":1,"risk":2,"issue":3}
    reasons = [] if finding["status"]=="ok" else [finding["detail"]]
    for check in checks:
        reasons.append(check["detail"])
        finding["evidence"].extend(check["evidence"])
        if severity[check["status"]] > severity[finding["status"]]:
            finding["status"] = check["status"]
    finding["detail"] = " ".join(dict.fromkeys(reasons))
    finding["evidence"] = list(dict.fromkeys(finding["evidence"]))


def period_checks(contract):
    fields = ("signed_on","effect_on","valid_until")
    checks = []
    effective, until = printed_day(contract,"effect_on"), printed_day(contract,"valid_until")
    if effective and until and effective>until:
        checks.append(date_check("contract_period","risk",f"所列生效日 {effective} 晚于合同有效截止日 {until}，请核对现行文本或延期依据。",
                                 contract.evidence("effect_on","valid_until")))
    unclear = [field for field in fields if any(f["field"]==field for f in contract.refs) and not printed_day(contract,field)]
    if unclear:
        checks.append(date_check("contract_period","missing","请核对合同日期栏的完整引文、原页和实际日期。",contract.evidence(*unclear)))
    return checks


def receipt_date_checks(contract, receipts, retests, seal_day=None):
    checks = []
    effective = printed_day(contract,"effect_on")
    for record in [*receipts,*retests]:
        if not all(contract.body(k) and contract.body(k)==record.body(k) for k in ("contract_id","buyer","subject")):
            continue
        is_retest = record in retests or any(record.fields[k] for k in ("original_acceptance","defect_closure","repair_number"))
        label = "复验" if is_retest else "验收"
        accepted = printed_day(record,"accepted_on")
        refs = contract.evidence("effect_on",*LINK_KEYS)+record.evidence("accepted_on",*LINK_KEYS)
        if seal_day and seal_day!=effective and accepted and accepted<=seal_day and warranty_terms.identity(contract,record):
            status="risk" if accepted<seal_day else "missing"
            checks.append(date_check("reinspection" if is_retest else "acceptance",status,
                f"{label}日期 {accepted} "+("早于" if accepted<seal_day else "等于")+f"双方最后盖章日 {seal_day}，请核实签章、验收的先后及实际履行依据。",
                refs+contract.evidence("buyer_sealed_on","seller_sealed_on")))
        event = "reinspection" if is_retest else "acceptance"
        if not accepted and any(f["field"]=="accepted_on" for f in record.refs):
            checks.append(date_check(event,"missing",label+"日期需从对应日期栏和原页核实。",refs))
        elif effective and accepted and accepted<=effective and not (same_contract(contract,record) and complete_id(contract.body("contract_id"))
                and all(labelled_sources(d,LINK_KEYS) for d in (contract,record))):
            checks.append(date_check(event,"missing","请先核对完整合同编号、双方与标的，再比较这份"+label+"记录的日期。",refs))
        elif effective and accepted and accepted<effective:
            checks.append(date_check(event,"risk",f"{label}日期 {accepted} 早于合同所列生效日 {effective}，请核实提前履行及双方确认依据。",refs))
        elif effective and accepted==effective:
            checks.append(date_check(event,"missing",f"{label}与合同生效同为 {effective}，需核实当日生效与履行的先后顺序。",refs))
    return checks


def check_approval(contract, approvals, party):
    fields = ("contract_approval","contract_id","buyer","seller","approval_authority","approval_result","approved_on","approval_signer")
    refs = [ref for doc in approvals for ref in doc.evidence(*fields)]
    if len(approvals) != 1:
        return "missing","待取得并确定本合同所据的一份董事会审批记录。",refs
    approval = approvals[0]
    if not all(contract.single(k) and contract.single(k) == approval.single(k) for k in ("contract_id","buyer","seller")):
        return "missing","审批记录的合同号和双方尚未与本合同逐项对应。",refs
    authority = contract.single("buyer" if party in ("甲方","采购方") else "seller") + "董事会"
    if approval.body("approval_authority") != authority:
        return "missing","审批记录所列机构尚未与约定的“"+authority+"”对应。",refs
    decision = approval.body("approval_result")
    if decision in ("未批准","不予批准","未通过","否决","暂缓批准","退回补议"):
        return "risk","约定的审批机构记载“"+decision+"”，请核实后续决议及生效条件。",refs
    if decision not in ("批准","已批准","同意批准","批准本合同") or not approval.signed("approval_signer") or approval.incomplete(*fields):
        return "missing","待核对明确的批准决定和经原页核图的审批签认。",refs
    approved = day(approval.single("approved_on"))
    effective = contract.declared_date("effect_on")
    if not approved:
        return "missing","审批记录缺少可核的决定日期。",refs
    if effective and effective < approved:
        return "risk","材料所列生效日早于约定审批机构的批准日，请核对生效时点。",refs
    return "ok","约定的董事会批准决定、日期和签认已有材料支持。",refs


def effect(contract, approvals=(), version=FORMAT, grants=(), mandate_records=(), original_sources=None, board_graph=None):
    fields = ("contract","contract_id","buyer","seller","signed_on","effect_clause","contract_state","effect_on","valid_until",
              "buyer_signature","seller_signature","adjustment")
    refs = contract.evidence(*fields)
    terms = contract.body("effect_clause")
    board = BOARD_CONDITION.fullmatch(terms) if version != FIRST_FORMAT else None
    state = contract.body("contract_state")
    missing = []
    if not contract.single("contract_id"):
        missing.append("唯一合同编号")
    buyer, seller = contract.single("buyer"), contract.single("seller")
    if not buyer or not seller or buyer == seller:
        missing.append("可区分的合同双方")
    if not contract.declared_date("signed_on"):
        missing.append("可核的签订日期")
    if not board and not EFFECT.fullmatch(terms):
        missing.append("生效约定及其中每项条件的证明")
    mode = "seal" if "盖章" in terms and "或" not in terms else "sign" if ("签字" in terms or "签名" in terms) and "或" not in terms else None
    read_date = printed_day if version==FORMAT and contract.mandate_format in MANDATE_TERM_FORMATS else None
    delegations = check_delegations(contract, grants, strict_names=version!=DELEGATION_FORMAT,read_date=read_date) if version in MANDATE_FORMATS else []
    mandate_execution.review(delegations, mandate_records)
    if original_sources:
        mandate_originals.review_entries(delegations, original_sources)
    for field, party, name in (("buyer_signature",buyer,"甲方"),("seller_signature",seller,"乙方")):
        side = field.removesuffix("_signature")
        delegate = next((item for item in delegations if item["side"]==side), None)
        if delegate and mode!="seal":
            if delegate["status"]!="ok":
                missing.append(name+"代理签署的书面授权")
            if (delegate["signature_field"]!=field and (contract.fields[field] or field in contract.uncertain)
                    and not contract.signed(field, party, mode)):
                missing.append(name+"同时列明的多个签署栏及其关系")
            continue
        if not party or not contract.signed(field, party, mode):
            missing.append(name + "签署栏及与该方相符的核图签认")
    changes = [n for n in contract.notes if re.search(r"补充协议|解除|终止|待审批|待批准|授权委托",n["quote"])]
    refs += [n["page_id"] for n in changes]
    effective, signed, expiry = (contract.declared_date(k) for k in ("effect_on","signed_on","valid_until"))
    if (contract.fields["effect_on"] and (not effective or signed and effective < signed)) or (
            contract.fields["valid_until"] and (not expiry or signed and expiry < signed)):
        missing.append("合同有效期间及生效日期的依据")
    changed = changes or contract.fields["adjustment"] or contract.incomplete(*fields) or (
        contract.fields["contract_state"] and state not in {"已签署","已生效","有效","履行中","已签订"})
    if changed:
        status, detail = "risk", "合同状态、变更记载或证据缺口影响判断，请核实现行文本及约定条件。"
    elif missing:
        status, detail = "missing", "待核对" + "、".join(missing) + "。"
    else:
        status, detail = "ok", "合同编号、双方、签订日期及签署栏相符；双方签署的约定生效条件已有材料支持。"
    scope = [contract.unit]
    decision = None
    if board:
        approval_status, note, evidence = check_approval(contract,approvals,board[1])
        decision = board_execution.decision(board_graph, contract, approvals, board[1])
        if decision:
            approval_status, note = board_execution.review(approval_status, note, decision)
            refs.extend(decision["evidence"])
        refs.extend(evidence)
        scope.extend(doc.unit for doc in approvals)
        if status == "ok" or approval_status == "risk":
            status = approval_status
        if status == "ok":
            detail = "双方签署栏与合同主体相符。" + note
        else:
            detail = (detail if missing or changed else "") + note
    elif approvals:
        status = "missing"
        detail += " 另有审批资料，请核对其与合同约定、授权和现行状态的关系。"
        scope.extend(doc.unit for doc in approvals)
        for doc in approvals:
            refs.extend(doc.evidence("contract_approval","approval_result","approval_authority"))
    if delegations:
        for item in delegations:
            refs.extend(item["evidence"])
            scope.extend(item["units"])
            detail += " " + item["detail"]
            if item["status"]=="risk" or status=="ok":
                status = item["status"]
    finding = result("H01",status,detail,refs,scope)
    if decision:
        finding["effect_review"] = {"board_decision":decision}
    if delegations:
        finding["delegations"] = delegations
    return finding


def inspect_quality(required, basis, reading):
    if not required or not basis or required != basis:
        return "risk" if required and basis else "missing","合同验收标准与实际检验依据需逐项对应。"
    if required in {"外观无破损","配件齐全","包装完好"} and required == reading:
        return "ok",""
    numeric = r"(-?\d{1,12}(?:\.\d{1,6})?)"
    units = r"(°C|mm|cm|kg|MPa|kPa|%)"
    spec = LIMIT.fullmatch(required)
    measured = re.fullmatch(r"([\u4e00-\u9fff]{1,16})" + numeric + units, reading)
    if not spec or not measured or spec[1] != measured[1] or spec[4] != measured[3]:
        return "missing","需核对标准全文、同一指标及单位的实测结果。"
    bound, value = Decimal(spec[3]), Decimal(measured[2])
    above = spec[2] in ("不高于","不超过","至多","≤")
    if (above and value > bound) or (not above and value < bound):
        return "issue",f"合同要求“{required}”，验收原页记载“{reading}”，实测值超出约定限值。"
    return "ok",""


def acceptance(contract, receipts, *, criterion=None, signature_ok=None, quantity_change=None, quality_graph=None, resolve_strict=True):
    keys = ("contract_id","buyer","subject")
    fields = (*keys,"acceptance","seller","accepted_on","acceptance_scope","acceptance_result","acceptance_signer",
              "acceptance_exception","quantity_accepted","inspection_basis","measured_result")
    refs = contract.evidence(*keys,"seller","signed_on","valid_until","quantity_agreed","acceptance_criteria")
    units = [contract.unit] + [r.unit for r in receipts]
    for receipt in receipts:
        refs.extend(receipt.evidence(*fields))
    def finding(status, detail):
        return result("H02",status,detail,refs,units)
    if not receipts:
        return finding("missing","缺少可关联的验收资料，交付范围与质量待核。")
    if len(receipts) != 1:
        return finding("missing","存在多份验收资料，需区分分批验收、整改复验与最终验收，并核定覆盖范围。")
    r = receipts[0]
    if not all(contract.single(k) and contract.single(k) == r.single(k) for k in keys):
        return finding("missing","合同编号、采购方及标的尚未逐项对应，不能引用这份验收记录作为本合同的履约证明。")
    if r.fields["seller"] and (not contract.single("seller") or r.single("seller") != contract.single("seller")):
        return finding("risk","验收资料所列供应方与合同未能一致对应，请核验主体。")
    outcome, scope = r.body("acceptance_result"), r.body("acceptance_scope")
    if outcome in FAILED_ACCEPTANCE:
        return finding("issue","本合同对应验收记录明确记载“" + outcome + "”，需查明缺陷及复验处置。")
    quality = None
    if contract.fields["acceptance_criteria"] or r.fields["inspection_basis"] or r.fields["measured_result"]:
        basis, reading = r.body("inspection_basis"), r.body("measured_result")
        standard = contract.body("acceptance_criteria") if criterion is None else criterion
        quality = inspect_quality(standard,basis,reading)
        if quality_graph is not None:
            proof = payment_quality.comparison(quality_graph,{"evidence":refs})
            if quality_graph[payment_quality.KEY]["format"]==payment_quality.FORMAT and (
                    proof.get("reading_notes") if proof else payment_quality.incomplete_notes(quality_graph,{"evidence":refs})):
                quality = ("reading_required","判定限值所需的原始检测记录及测量口径")
            elif resolve_strict and quality[0] in ("risk","missing") and payment_quality.same_within(proof):
                quality = ("ok","")
        if criterion and standard!=basis:
            observation = inspect_quality(standard,standard,reading)
            if observation[0]=="issue":
                quality = ("issue",observation[1]+" 验收报告所引检验依据同时需核对。")
        if quality[0]=="issue":
            return finding("issue",quality[1]+(" 验收结论栏同时记载“"+outcome+"”，请核对并复验。" if outcome else ""))
    if (outcome and outcome not in PASS) or (scope and scope not in FINAL_SCOPES) or (
        r.fields["acceptance_exception"] and r.body("acceptance_exception") not in CLEAN):
        return finding("risk","验收范围、质量结论或遗留事项存在限定，需核对分批交付、整改及复验记录。")
    signed, accepted = contract.declared_date("signed_on"), day(r.single("accepted_on"))
    if signed and accepted and accepted < signed:
        return finding("risk","验收记录日期早于签约日期，需核实履行背景和实际时间。")
    until = contract.declared_date("valid_until")
    if until and accepted and accepted > until:
        return finding("risk","验收日期在所列合同有效期之后，需核对延期、变更及继续履行依据。")
    missing = []
    if quantity_change is not None and quality is None:
        missing.append("本次终验的质量标准及实际检验记录")
    if quality and quality[0]=="reading_required":
        missing.append(quality[1])
    elif quality and quality[0] != "ok":
        return finding(*quality)
    if contract.incomplete("acceptance_criteria"):
        missing.append("合同验收标准原文")
    if quantity_change is not None:
        difference = quantity_change["difference"]
        if difference is None:
            missing.append("终验当日适用的交付数量、实际验收数量及相同计量单位")
        elif difference:
            needed, actual = quantity_change["applicable"], quantity_change["accepted"]
            unit = needed["unit"]
            delta = "少" if difference < 0 else "多"
            return finding("risk",f"当次约定应验 {needed['count']}{unit}，原件实收 {actual['count']}{unit}，{delta} {abs(difference)}{unit}。请核对交付范围和差异处置记录。")
    elif contract.fields["quantity_agreed"] or r.fields["quantity_accepted"] or contract.incomplete("quantity_agreed"):
        left, right = contract.body("quantity_agreed"), r.body("quantity_accepted")
        if not left or not right:
            missing.append("合同及验收资料双方记载的交付数量及单位")
        elif left != right:
            return finding("risk","合同约定与实际验收的交付数量或单位不一致，请核对差异及批准记录。")
    if not signed or not accepted:
        missing.append("签约与验收日期")
    if scope not in FINAL_SCOPES:
        missing.append("覆盖全部标的的验收范围")
    if outcome not in PASS:
        missing.append("明确质量结论")
    if not (r.signed("acceptance_signer") if signature_ok is None else signature_ok(r)):
        missing.append("合同指定人员的逐人签认" if signature_ok else "验收人签认及核图记录")
    if r.incomplete(*fields):
        missing.append("验收原页的完整引文")
    if missing:
        return finding("missing","待核对" + "、".join(missing) + "。")
    return finding("ok","同一合同、标的和采购方的终验资料记载合格，范围、日期与验收人签认已有原页支持。")


def stage_terms(text):
    if text in SIMPLE_FULL:
        return "100", "", ""
    if text in ("验收后一次性全额结算","验收后一次性付清","验收合格后一次性付清"):
        return "100","acceptance","验收" if text.startswith("验收后") else "验收合格"
    for kind, conditions in CONDITIONS.items():
        for condition in conditions:
            match = re.fullmatch(re.escape(condition) + r"后(?:一次性)?(?:支付|付清|付|结算)(?:合同(?:总价|价款|总额)的?)?(\d{1,3}(?:\.\d{1,4})?)%", text)
            if match:
                return match[1], kind, condition
            if text == condition + "后一次性支付全款":
                return "100", kind, condition
    ratio = re.findall(r"(?<![\d.])(\d{1,3}(?:\.\d{1,4})?)%", text)
    return ratio[0] if len(ratio) == 1 else "", "", ""


def schedule(contract, *, warranty_checks=False, deadlines=False, invoice_terms=(),release_terms=(),prior_terms=(),folio_sources=None, guarantees=(), named_approvals=(), count_row=None):
    fields = ("payment_term","payment_stage","adjustment")
    refs = contract.evidence("contract",*fields)
    rows, counts, issues = [], set(), []
    seen_lines = set()
    if count_row:
        counts.add(count_row["count"])
        seen_lines.add(norm(count_row["quote"]))
    for fact in contract.fields["payment_term"] + contract.fields["payment_stage"]:
        line = norm(fact["quote"])
        if line in seen_lines:
            continue
        seen_lines.add(line)
        if any(fact["id"] in r["facts"] and (fact.get("source_line") or {}).get("text")==r["quote"] for r,_,_ in named_approvals):
            continue
        guarantee=next((s for s in guarantees if fact["id"] in s["facts"] and (fact.get("source_line") or {}).get("text")==s["quote"]),None)
        if guarantee:
            if guarantee["field"]=="period_clause" or advance_guarantee.RIDER.fullmatch(guarantee["quote"].strip()):
                continue
            inline=advance_guarantee.inline_stage(guarantee["quote"])
            if inline and fact["field"]=="payment_stage":
                rows.append(dict(index=1,label=inline["stage"],share=inline["share"],kind="effect",condition="预付款保函签收",
                                 text=advance_guarantee.value(guarantee),ref=fact["id"]))
                continue
        if deadlines and fact["field"]=="payment_stage" and delivery_batches.raw_body(fact):
            source=fact["source_line"]["text"]
            terms=payment_windows.spec(source)
            if terms and terms["share"]:
                label,body=payment_windows.split_line(source)
                prefix=STAGE_PREFIX.fullmatch(label+":")
                rows.append(dict(index=number(prefix[1]) if prefix[1] else None,label=label,share=terms["share"],
                                 kind=terms["trigger"],condition=terms["trigger_text"],text=body,ref=fact["id"]))
                continue
        if invoice_terms and fact["field"]=="payment_stage":
            raw = (fact.get("source_line") or {}).get("text", "")
            term = invoice_conditions.INLINE.fullmatch(invoice_conditions.text(raw))
            if term and any(s["line"] and fact["id"] in s["facts"] and s["quote"]==raw for s in invoice_terms):
                prefix = STAGE_PREFIX.match(line)
                if prefix:
                    rows.append(dict(index=number(prefix[1]) if prefix[1] else None, label=term["stage"], share=term["share"],
                                     kind="acceptance", condition=term["trigger"], text=row_body(fact), ref=fact["id"]))
                    continue
        text = line if STAGE_PREFIX.match(line) else row_body(fact)
        for part in re.split(r"[;,，。]", text):
            if not part:
                continue
            header = re.fullmatch(r"(?:合同价款)?分(" + ORD + r")期(?:支付|付款|结算)?", part)
            if header:
                counts.add(number(header[1]))
                continue
            prefix = STAGE_PREFIX.match(part)
            index, label = None, ""
            if prefix:
                index = number(prefix[1]) if prefix[1] else None
                label = prefix[0][:-1]
                part = part[prefix.end():]
            share, kind, condition = stage_terms(part)
            if warranty_checks and fact["field"]=="payment_stage" and delivery_batches.raw_body(fact):
                inline=warranty_terms.inline_condition(fact["source_line"]["text"])
                if inline and part==inline[0]:
                    condition,share=inline.groups()
                    kind="warranty"
            rows.append(dict(index=index, label=label, share=share, kind=kind, condition=condition,
                             text=part, ref=fact["id"]))
    if folio_sources:
        contract_folios.withhold_shares(rows, folio_sources, contract.unit)
    if rows and all(r["index"] is not None for r in rows):
        rows.sort(key=lambda r:r["index"])
    if counts and counts != {len(rows)}:
        issues.append("明列期数与可逐项识别的期数不一致")
    if any(r["label"].startswith("第") for r in rows) and [r["index"] for r in rows] != list(range(1,len(rows)+1)):
        issues.append("期序重复、缺项或混用")
    labels = [r["label"] for r in rows if r["label"]]
    if len(set(labels)) != len(labels):
        issues.append("期名重复")
    if not rows or any(not r["share"] for r in rows):
        issues.append("完整付款方式或各期比例待核")
    elif any(Decimal(r["share"]) <= 0 for r in rows) or sum(Decimal(r["share"]) for r in rows) != 100:
        issues.append("各期正数比例未能合计至 100%")
    incomplete = contract.incomplete(*fields)
    if count_row:
        # Only the readings of this particular header have been reconciled.
        incomplete = contract.incomplete("payment_stage","adjustment") or any(
            g.get("field")=="payment_term" and (g.get("quality"),g.get("line"),g.get("quote"))!=
            ("uncovered",count_row["line"],count_row["quote"]) for g in contract.gaps)
    if contract.fields["adjustment"] or incomplete:
        issues.append("付款条款存在变更或原页覆盖缺口")
    assigned={(r["doc"],r["page"],r["line"],r["quote"]) for r,index,kind in named_approvals
              if sum(v["index"]==index and v["kind"]==kind for v in rows)==1}
    for r,_,_ in named_approvals:
        refs.extend((r["id"],f"{r['doc']}/p{r['page']}",*r["facts"]))
        if (r["doc"],r["page"],r["line"],r["quote"]) not in assigned:
            issues.append("具名签批约定所列期款待对应")
    uncovered = [n for n in contract.notes if re.search(r"分期|分[两二三四五六七八九十\d]+期|预付|尾款|质保金|保留款|第.+期|补充协议|另附|另行约定",n["quote"])
                 and not (assigned and (n["doc"],int(n["page_id"].rsplit("/p",1)[1]),n["line"],n["quote"]) in assigned)
                 and norm(n["quote"]) not in seen_lines and not (warranty_checks and warranty_terms.dedicated(n["quote"]))
                 and not (sum(r["index"]==1 for r in rows)==1 and any(n["page_id"]==f"{s['doc']}/p{s['page']}" and
                          (n["line"],n["quote"])==(s["line"],s["quote"]) for s in guarantees))
                 and not any(s["supported"] and s["unit"]==contract.unit and s["quote"]==n["quote"] and
                             s["doc"]==n["doc"] and s["line"]==n["line"] and n["page_id"]==f"{s['doc']}/p{s['page']}"
                             and sum(row["kind"]=="acceptance" for row in rows)==1 for s in prior_terms)
                 and not (deadlines and payment_windows.scoped_row(n["quote"]))
                 and not any(s["unit"]==contract.unit and s["role"]=="authority" and s["quote"]==n["quote"] and s["line"]==n["line"]
                             and any(r["index"]==payment_releases.mandate(s["quote"])[0] and r["kind"]=="acceptance" for r in rows)
                             for s in release_terms)
                 and not any(s["quote"]==n["quote"] and s["line"]==n["line"] and s["supported"] and
                             invoice_conditions.RIDER.fullmatch(invoice_conditions.text(s["quote"])) and
                             len(invoice_conditions.targets(s, rows))==1 for s in invoice_terms)]
    if uncovered:
        refs += [n["page_id"] for n in uncovered]
        issues.append("另有待归入付款安排的原文")
    if (issues == ["完整付款方式或各期比例待核"] and folio_sources and
            len([p for p in folio_sources["pages"] if p["unit"] == contract.unit]) == 1 and
            all(r.get("ambiguous_number") or r["kind"] and r["share"] and Decimal(r["share"]) > 0 for r in rows)
            and sum(Decimal(r["share"]) for r in rows if r["share"]) < 100):
        for row in rows:
            row["separate_numeric_clause"] = bool(row["share"])
    if issues:
        status, detail = "missing", "；".join(issues) + "。请对照现行合同及附表。"
    else:
        status, detail = "ok", f"合同原文列有 {len(rows)} 期，各期比例合计 100%。"
    return result("H03",status,detail,refs,[contract.unit]), rows


def warranty(contract, releases, accepted):
    refs = []
    for release in releases:
        refs += release.evidence("warranty","contract_id","buyer","subject","warranty_release","acceptance_signer")
    if len(releases) == 1 and accepted:
        release = releases[0]
        linked = all(contract.single(k) and contract.single(k) == release.single(k) for k in ("contract_id","buyer","subject"))
        match = re.fullmatch(r"(\d{4}(?:年|[-/.])\d{1,2}(?:月|[-/.])\d{1,2}日?)(?:双方确认)?质保期(?:已届满|届满|已满)", release.body("warranty_release"))
        end = day(match[1]) if match else None
        if linked and end and end >= accepted and release.signed("acceptance_signer"):
            return end, refs
    return None, refs


def matches_stage(designation, row):
    label = row["label"]
    if not label or not designation:
        return False
    if label == designation:
        return True
    ordinal = re.fullmatch(r"第(" + ORD + r")期",designation)
    return bool(ordinal and row["index"] is not None and row["index"] == number(ordinal[1]))


RECEIPT_COVERAGE_SINCE = "2026.11.25.05"


def receipts_without_schedule(graph, contracts, plan_evidence, plan_units):
    contract_units = [contract.unit for contract in contracts]
    sources = graph.get("payment_window_sources", {}).get("pages", [])
    contract_pages = [f"{p['doc']}/p{p['page']}" for p in sources if p["unit"] in contract_units]
    if len(contracts) == 1:
        detail = "已提交银行回单，合同付款方式与期次尚缺依据。请取得付款条款或附表，再核对此笔支付的用途和时点。"
    else:
        detail = "已提交银行回单，须先查明该笔对应的现行合同，再核对其付款约定和实际支付时点。"
    for unit in graph["documents_by_kind"].get("bank_receipt", []):
        bank = Material(graph, unit)
        refs = bank.evidence("bank_receipt","contract_id","payment_designation","paid_on","transfer_status",
                             "payer","payee","transfer_amount","transfer_ref")
        pages = [f"{p['doc']}/p{p['page']}" for p in sources if p["unit"] == unit]
        yield result("H05","missing",detail,[*refs,*pages,*plan_evidence,*contract_pages],[*plan_units,unit])


def compute(graph, version=FORMAT, *, include_unassigned_receipts=True, recheck_payment_opinions=False):
    results = performance_findings(graph,version,include_unassigned_receipts=include_unassigned_receipts,
                                  recheck_payment_opinions=recheck_payment_opinions)
    if version == FORMAT:
        records = contract_comments.checks(graph, results)
        plan = next((f for f in results if f["rule"] == "H03"), None)
        plan_review = contract_comments.assessment(records, plan) if records and plan else None
        if plan_review:
            for finding in results:
                if finding["rule"] in contract_comments.STAGE_RULES:
                    contract_comments.attach(finding, contract_comments.assessment(records, finding))
            if plan_review["whole"]:
                contract_comments.attach(plan, plan_review)
        payment_execution.apply(graph, results)
        retest_reference.apply(graph, results)
        payment_acceptance.apply(graph, results)
        inspection_use.apply(graph, results)
        advance_guarantee.apply(graph, results)
        grouped = stage_payments.findings(graph, results)
        if graph.get("prior_installment_sources", {}).get("lines"):
            prior_installment.condition(graph, results, grouped)
            ledger = graph["stage_payment_sources"]
            if len(ledger["banks"]) > 1 or ledger["ambiguous_units"]:
                grouped = stage_payments.findings(graph, results)
            else:
                grouped = []
        if plan_review:
            for finding in grouped:
                contract_comments.attach(finding, contract_comments.assessment(records, finding))
            # A suggestion limited to one trigger leaves printed shares available to amount checks.
            if not plan_review["whole"]:
                contract_comments.attach(plan, plan_review)
        results.extend(grouped)
        results.extend(warranty_register.findings(graph,results))
        addendum_execution.flag_mismatches(graph,results)
        payment_quality.apply(graph,results)
        party_readings.attach(graph,results)
        approval_names.apply_conditions(graph,results)
        approval_changes.apply(graph,results)
        for count in graph.get(installment_counts.KEY,{}).get("rows",()):
            installment_counts.attach(results,count)
    return results


def performance_findings(graph, version, *, include_unassigned_receipts,recheck_payment_opinions=False):
    kinds = graph["documents_by_kind"]
    def materials(kind):
        return [Material(graph, unit) for unit in kinds.get(kind, ())]
    contracts = materials("contract")
    if len(contracts) != 1:
        scope = [d["id"] for d in graph.get("audit_documents", graph["documents"])]
        refs = [f["id"] for f in graph["facts"] if f["field"] == "contract"]
        output = [result(rule,"missing","需先确定本次审查所据的一份现行合同及其资料归属。",refs,scope)
                  for rule in ("H01","H02","H03","H04")]
        if version == FORMAT and include_unassigned_receipts:
            output.extend(receipts_without_schedule(graph, contracts, refs, [c.unit for c in contracts]))
        return output
    contract = contracts[0]
    receipts, releases = materials("acceptance"), materials("warranty")
    packet_pages = [(p["doc"],p["page"]) for packet in graph.get("receipt_packet_sources",{}).get("packets",[])
                    if packet["status"]=="review" for p in packet["pages"]]
    pending_units = [d["id"] for d in graph.get("audit_documents",graph["documents"])
                     if any(d.get("source",d["id"])==doc and d.get("page",n)==n for doc,n in packet_pages)]
    if pending_units:
        receipts = [r for r in receipts if r.unit not in pending_units]
    approvals = materials("contract_approval") if version != FIRST_FORMAT else []
    grants = materials("power_of_attorney") if version in MANDATE_FORMATS else ()
    signed = effect(contract, approvals, version, grants, graph.get("mandate_pdf_sources", {}).get("records", ()),
                    graph.get("mandate_original_sources"), graph if version == FORMAT else None)
    if version in EFFECT_FORMATS:
        contract_effect.review(signed,graph.get("contract_effect_sources",{}),contract,graph)
        pdf_execution.review(signed, graph, contract.unit)
    if version in DATE_FORMATS:
        add_date_checks(signed,period_checks(contract))
    classified = {u for group in kinds.values() for u in group}
    cash=graph.get("payment_release_sources",{})
    classified.difference_update(kinds.get("payment_release",[]))
    classified.update(payment_releases.recognized(cash))
    classified.update(release_comparison.bounded_holds(graph, contract, receipts))
    ticket_units,bounded_tickets=warranty_service.classified(graph.get("warranty_sources",{}))
    classified.difference_update(ticket_units)
    classified.update(bounded_tickets)
    classified.update(advance_guarantee.bounded_units(graph))
    classified.update(installment_approval.recognized(graph))
    exchange_ledger = graph.get("equipment_model_sources",{}).get("exchange",{})
    classified.difference_update(equipment_exchanges.unscoped(exchange_ledger))
    extra_units = {d["id"] for d in graph.get("audit_documents",graph["documents"])} - classified
    changes = change_candidates(graph) if version in ADDENDUM_FORMATS else []
    repairs, retests = materials("remediation"), materials("reinspection")
    change = None
    amendments = [Material(graph,u) for u in changes]
    other_events = bool(repairs or retests or any(r.fields[k] or k in r.uncertain
                        for r in receipts for k in ("original_acceptance","repair_number","defect_closure")))
    approval_scope=approval_changes.scope(graph,contract,changes) if version==FORMAT and not extra_units else None
    payment_change = payment_amendments.resolve(graph,contract,amendments,base_decision=signed,unassigned=extra_units) if version==FORMAT and not approval_scope else None
    scoped_change = payment_change if payment_change and payment_change["scope_clear"] else None
    if changes and not scoped_change and not approval_scope:
        change = resolve_change(graph,contract,amendments,receipts,multiple_events=other_events or len(receipts)!=1,
                                contract_supported=signed["status"]=="ok",unclassified=extra_units)
        change["evidence"] = list(dict.fromkeys(change["evidence"]+signed["evidence"]))
    authority = None
    batch_signers = {}
    compare_printed_names = signed["status"]=="ok" or graph.get("delivery_batch_sources",{}).get("format") in delivery_batches.PRINTED_SIGNER_FORMATS
    if version in BATCH_FORMATS and compare_printed_names and not (extra_units or change or repairs or retests):
        batch_signers=delivery_batches.signing_plan(graph,contract)
    if version in SIGNATORY_FORMATS and not batch_signers:
        authority = check_acceptance_authority(graph,contract,receipts,retests,contract_supported=signed["status"]=="ok",
                                              other_terms=bool(extra_units or change and not change["scope_clear"]), name_records=version in DATE_FORMATS)
    by_unit = {r["unit"]:r for r in authority["records"]} if authority else {}
    pdf_records = acceptance_execution.relevant(graph,{r.unit for r in [*receipts,*retests]})
    pending_signatures = {r["unit"] for r in pdf_records if r["state"] in acceptance_execution.DETAIL}
    pending_signatures.update(r["unit"] for r in graph.get(acceptance_originals.KEY, {}).get("records", ()))
    def signatory(record):
        if record.unit in pending_signatures:
            return False
        return by_unit[record.unit]["status"]=="ok" if record.unit in by_unit else record.signed("acceptance_signer")
    def evaluate(contract, selected):
        quantity = change.get("quantity") if change else None
        criterion = (change["applied_criterion"] or "") if change and not (quantity and change["scope_clear"]) else None
        quality_graph = graph if (version==FORMAT and graph.get(payment_quality.KEY,{}).get("format") in payment_quality.OPEN_FORMATS
                                  and not (change or repairs or retests)) else None
        finding = acceptance(contract,selected,criterion=criterion,quantity_change=quantity,signature_ok=signatory if authority else None,
                             quality_graph=quality_graph,resolve_strict=not (extra_units or pending_units))
        units = {doc.unit for doc in selected}
        acceptance_execution.apply(finding,[r for r in pdf_records if r["unit"] in units])
        acceptance_originals.apply(finding, graph, units)
        return finding
    if version in (REINSPECTION_FORMAT, *MANDATE_FORMATS):
        ledger = graph.get("repair_completion_sources") if version == FORMAT else None
        waiting = graph.get("reinspection_wait_sources", {})
        checks = {r.unit: repair_completion.check(ledger, r, printed_day(r, "repaired_on"),
                  timing_lines=reinspection_wait.event_lines(waiting, r.unit, "fixed_time")) for r in repairs} if ledger else {}
        accepted, accepted_on = assess_reinspection(contract,receipts,repairs,retests,evaluate,signature_ok=signatory if authority or pending_signatures else None,
            read_date=printed_day if ledger else None,repair_checks=checks)
    else:
        accepted = acceptance(contract, receipts)
        accepted_on = day(receipts[0].single("accepted_on")) if accepted["status"]=="ok" else None
    ledger = graph.get("invoice_receipt_sources") if version==FORMAT else None
    invoice_terms = [s for s in ledger["lines"] if s["role"]=="clause"] if ledger else []
    guarantees = advance_guarantee.scoped_terms(graph,contract.unit) if version==FORMAT else ()
    plan, rows = schedule(contract, warranty_checks=version in WARRANTY_FORMATS, deadlines=version in PAYMENT_WINDOW_FORMATS,release_terms=cash.get("lines",[]),guarantees=guarantees,
                          count_row=next((r for r in graph.get(installment_counts.KEY,{}).get("rows",()) if r["unit"]==contract.unit and r["rects"]),None) if version==FORMAT else None,
                          named_approvals=approval_names.stage_terms(graph,contract.unit) if version==FORMAT else (),
                          prior_terms=graph.get("prior_installment_sources",{}).get("lines",[]) if version==FORMAT else (),
                          folio_sources=graph.get("contract_folio_sources") if version==FORMAT else None,
                          invoice_terms=[s for s in invoice_terms if s["unit"]==contract.unit])
    schedule_detail = plan["detail"]
    batch = None
    models = equipment_models.assess(graph, contract, [*receipts, *retests], effective=signed["status"] == "ok") if version == FORMAT else None
    if version in BATCH_FORMATS:
        terms_pending=bool(signed["status"]!="ok" or extra_units or pending_units or authority or other_events)
        change_proof=None
        source=graph.get("delivery_batch_sources",{})
        if change and source.get("format")==delivery_batches.FORMAT and source.get("signals"):
            change_proof=delivery_batches.change_basis(change,contract,amendments,receipts,
                eligible=not (terms_pending or contract.fields["acceptance_signing_clause"] or "acceptance_signing_clause" in contract.uncertain))
            if change_proof["effective_on"]:
                change.update(state="by_batch",applied_criterion=None,accepted_on=None,
                              detail="协议仅变更验收标准，双方于 "+change_proof["effective_on"]+" 完成盖章。逐批核对验收日期及当时适用的标准。")
        batch = delivery_batches.inspect(graph,contract,receipts,native_spacing=version in EFFECT_FORMATS,
                    requirements=batch_signers.get("batches"),final_requirement=batch_signers.get("final"),model_checks=models,change=change_proof,
                    other_terms=terms_pending or bool(change and change["state"]!="by_batch"))
    batch_rows = {r["index"]:r for r in batch["batches"]} if batch else {}
    if batch:
        for item,applicable in ((signed,[r for r in batch["riders"] if r["kind"]=="contract"]),(plan,batch["riders"])):
            if applicable:
                if item["status"]=="ok":
                    item["status"]="missing"
                item["detail"]+=" 另有材料记载影响合同或付款的条件，需核对其效力及适用范围。"
                item["evidence"]=list(dict.fromkeys(item["evidence"]+[r["ref"] for r in applicable]))
                item["scope"]=list(dict.fromkeys(item["scope"]+[r["unit"] for r in applicable]))
        batch["scope"] = list(dict.fromkeys(batch["scope"]+signed["scope"]))
        batch["evidence"] = list(dict.fromkeys(batch["evidence"]+signed["evidence"]))
        accepted["batch_acceptance"] = batch
        accepted["scope"] = list(dict.fromkeys(accepted["scope"]+batch["scope"]))
        accepted["evidence"] = list(dict.fromkeys(accepted["evidence"]+batch["evidence"]))
        if accepted["status"]=="issue" and batch["status"]!="issue":
            accepted["detail"] += " "+batch["detail"]
        else:
            accepted.update(status=batch["status"],detail=batch["detail"])
        accepted_on = day(batch["completion_on"] or "") if accepted["status"]=="ok" else None
        if accepted.get("reinspection") and not accepted_on:
            accepted["reinspection"]["state"]="open"
        if not batch["contract_clear"] or not batch["independent"]:
            plan.update(status="missing",detail="需核对分批条款、附注和完整付款前提。 "+plan["detail"])
            plan["evidence"]=list(dict.fromkeys(plan["evidence"]+contract.evidence("batch_clause","delivery_batch")+
                                               [r for r in batch["evidence"] if "/f" not in r and "/h" not in r]))
        unresolved=[r for r in batch["records"] if r.get("role")=="final" and r["scope_unclear"]]
        if unresolved:
            plan.update(status="missing",detail="终验单有待核的原页或附注，需查清对各期付款的影响。 "+plan["detail"])
            plan["evidence"]=list(dict.fromkeys(plan["evidence"]+[ref for r in unresolved for ref in r["evidence"]]))
            plan["scope"]=list(dict.fromkeys(plan["scope"]+[r["unit"] for r in unresolved]))
        for row in rows:
            index=delivery_batches.payment_index(row,contract)
            if index is not None:
                row.update(kind="batch",batch_index=index)
    if authority:
        authority["evidence"] = list(dict.fromkeys(authority["evidence"]+signed["evidence"]))
        authority["units"] = list(dict.fromkeys(authority["units"]+signed["scope"]))
        accepted["acceptance_authority"] = authority
        accepted["scope"] = list(dict.fromkeys(accepted["scope"]+authority["units"]))
        accepted["evidence"] = list(dict.fromkeys(accepted["evidence"]+authority["evidence"]))
        if authority["status"]!="ok":
            if accepted["status"] not in ("issue","risk") or authority["status"]=="risk" and accepted["status"]!="issue":
                accepted["status"] = authority["status"]
            accepted_on = None
            if accepted.get("reinspection"):
                accepted["reinspection"]["state"] = "open"
        accepted["detail"] += " "+authority["detail"]
    if version in DATE_FORMATS:
        seal_day=day(signed.get("effect_review",{}).get("seals",{}).get("completed_on") or "")
        chronology = receipt_date_checks(contract,receipts,retests,seal_day)
        if chronology and accepted.get("reinspection",{}).get("state")=="closed":
            initial_units = {s["unit"] for s in accepted["reinspection"]["steps"] if s["role"]=="original"}
            initial = evaluate(contract,[d for d in receipts if d.unit in initial_units])
            accepted.update(status=initial["status"] if initial["status"] in ("issue","risk") else "missing",
                            detail=initial["detail"]+" 整改复验能否关闭该项缺陷仍待核实。")
        add_date_checks(accepted,chronology)
        if chronology:
            accepted_on = None
            if accepted.get("reinspection"):
                accepted["reinspection"]["state"] = "open"
    if change:
        if change["state"]=="pending":
            accepted_on = None
            if accepted["status"]=="ok":
                accepted["detail"] = "尚待确定各次验收所据标准及结果。"
            if accepted["status"]!="issue":
                accepted["status"] = "missing" if accepted["status"]!="risk" else "risk"
            if accepted.get("reinspection"):
                accepted["reinspection"]["state"] = "open"
        accepted["quality_change"] = change
        affected = [accepted]
        if not change["scope_clear"]:
            for item in (signed,plan):
                if item["status"]=="ok":
                    item.update(status="missing",detail="需核对补充协议是否改变本项约定。")
            affected += [signed,plan]
        for item in affected:
            item["detail"] = change["detail"]+" "+item["detail"]
            item["evidence"] = list(dict.fromkeys(item["evidence"]+change["evidence"]))
            item["scope"] = list(dict.fromkeys(item["scope"]+changes))
        limited = [s["unit"] for s in graph.get("quality_addenda",{}).get("limited_numbers",[])]
        accepted["scope"] = list(dict.fromkeys(accepted["scope"]+signed["scope"]+limited))
    for doc in graph.get("audit_documents",graph["documents"]):
        if doc["id"] in classified:
            continue
        extra = Material(graph,doc["id"])
        refs = extra.evidence("adjustment","effect_clause","contract_state","payment_stage","payment_term","contract_id")
        refs += [n["page_id"] for n in extra.notes]
        if version in ADDENDUM_FORMATS:
            if accepted["status"]=="ok":
                accepted.update(status="missing",detail="终验记录已有签认，另有资料尚未归属，需核对其对本次验收标准或结果的影响。")
            accepted_on = None
            if accepted.get("reinspection"):
                accepted["reinspection"]["state"] = "open"
            accepted["evidence"] = list(dict.fromkeys(accepted["evidence"]+(refs or [doc["id"]])))
            accepted["scope"] = list(dict.fromkeys(accepted["scope"]+[doc["id"]]))
        for item in (signed,plan):
            note = "另有尚未归属的资料，请核对其是否变更本合同或付款约定。"
            if any(item.get("effect_review", {}).get(k) for k in ("word_signatures", "pdf_execution")):
                if item["status"] == "ok":
                    item["status"] = "missing"
                if note not in item["detail"]:
                    item["detail"] += " " + note
            else:
                item.update(status="missing", detail=note)
            item["evidence"] = list(dict.fromkeys(item["evidence"] + (refs or [doc["id"]])))
            if doc["id"] not in item["scope"]:
                item["scope"].append(doc["id"])
    if version==FORMAT and not batch:
        closed = accepted.get("reinspection",{}).get("state")=="closed"
        if acceptance_reservations.apply(accepted,graph.get("acceptance_reservation_sources",{}),graph):
            accepted_on = None
            if closed:
                original = evaluate(contract,receipts)
                if original["status"]=="issue":
                    accepted.update(status="issue",detail=original["detail"]+" "+accepted["detail"]+" 原验收缺陷仍需正式复验。")
    if models:
        legacy_models = graph["equipment_model_sources"]["format"] == equipment_models.LEGACY
        if not legacy_models:
            chain = accepted.get("reinspection")
            if chain and pending_units:
                chain = {**chain, "state": "open"}
            equipment_models.reconcile_reinspection(models, chain)
            equipment_exchanges.reconcile(graph,contract,[*receipts,*retests],models,chain)
        accepted["equipment_models"] = models
        accepted["evidence"] = list(dict.fromkeys([*accepted["evidence"], *models["evidence"]]))
        accepted["scope"] = list(dict.fromkeys([*accepted["scope"], *(p["unit"] for p in graph["equipment_model_sources"]["pages"])]))
        equipment_models.apply(accepted, models)
        if models.get("exchange",{}).get("status")=="ok":
            accepted["detail"] += " "+models["exchange"]["detail"]
        if models["status"] != "ok":
            accepted_on = None
            if accepted.get("reinspection"):
                accepted["reinspection"]["state"] = "open"
    pdf_pending = acceptance_execution.apply(accepted,pdf_records)
    native_pending = acceptance_originals.apply(accepted, graph, {r.unit for r in [*receipts,*retests]})
    if pdf_pending or native_pending:
        accepted_on = None
        if accepted.get("reinspection"):
            accepted["reinspection"]["state"] = "open"
    if pending_units:
        page_refs = [f"{doc}/p{n}" for doc,n in packet_pages]
        if accepted["status"]=="ok":
            accepted["status"]="missing"
        accepted["detail"] += " 合订件中有验收单编号、原页或续页归属待核。请按原页核对各单覆盖的设备和签字。"
        accepted["evidence"] = list(dict.fromkeys(accepted["evidence"]+page_refs))
        accepted["scope"] = list(dict.fromkeys(accepted["scope"]+pending_units))
        accepted_on = None
        if accepted.get("reinspection"):
            accepted["reinspection"]["state"]="open"
    if version==FORMAT:
        coverage = inspection_coverage.assess(graph, contract, receipts, complex_scope=bool(
            batch or repairs or retests or changes or extra_units or pending_units))
        if coverage:
            was_closed = accepted.get("reinspection",{}).get("state")=="closed"
            inspection_coverage.apply(accepted,coverage)
            if coverage["status"]!="ok":
                accepted_on = None
                if was_closed:
                    original = evaluate(contract,receipts)
                    if original["status"]=="issue":
                        accepted.update(status="issue",detail=original["detail"]+" "+accepted["detail"])
    register = graph.get("acceptance_reservation_sources", {}).get("final_register")
    if version == FORMAT and register is not None and inspection_register.apply(accepted, register, graph):
        accepted_on = None
    if version == FORMAT and graph.get("reinspection_wait_sources"):
        timing = reinspection_wait.assess(graph["reinspection_wait_sources"], accepted, contract.unit, graph)
        if timing and reinspection_wait.apply(accepted, timing):
            accepted_on = None
    if version == FORMAT:
        closed = accepted.get("reinspection", {}).get("state") == "closed"
        if acceptance_comments.apply(accepted, graph, set(accepted["scope"])):
            accepted_on = None
            if closed:
                original = evaluate(contract, receipts)
                if original["status"] == "issue":
                    accepted.update(status="issue", detail=original["detail"] + " " + accepted["detail"])
    if version==FORMAT:
        payment_quality.review_acceptance(graph,accepted)
        if accepted.get("quality_comparison") and accepted["status"]!="ok":
            accepted_on = None
    if payment_change and not scoped_change:
        payment_amendments.attach(plan,payment_change)
    if version == FORMAT and (batch or scoped_change):
        contract_folios.withhold_shares(rows, graph.get("contract_folio_sources", {}), contract.unit)
    folios = contract_folios.assess(graph.get("contract_folio_sources", {}), contract.unit,
                                   {r["ref"] for r in rows if r["kind"]}) if version == FORMAT else None
    standalone = folios and folios["standalone"] if plan["status"] == "ok" and not (batch or changes or extra_units) else None
    only_number = (folios and len(folios["pages"]) == 1 and folios["state"] == "numeral"
                   and all(i["state"] == "numeral" for i in folios["pages"][0]["issues"])
                   and plan["detail"] == schedule_detail and not (batch or changes or extra_units))
    if folios:
        plan["contract_folios"] = folios
        contract_folios.attach(plan, folios)
        if folios["whole"]:
            contract_folios.attach(signed, {**folios, "status": "missing",
                "detail": "合同原页载有整份协议待确认或草拟的说明，请取得最终签署版本。"})
    signing_rows = contract_effect.form_rows(signed.get("effect_review",{}))
    shared_rows = [row for row in signing_rows if row.get("applies_to")==list(contract_effect.SHARED_DOCUMENTS)]
    if shared_rows:
        contract_effect.review_acceptance(accepted, shared_rows)
        accepted_on = None
    output = [signed, accepted, plan]
    if approval_scope:
        for finding in (accepted,plan):
            finding["approval_change_scope"]=approval_scope
            finding["evidence"]=list(dict.fromkeys([*finding["evidence"],*approval_scope["evidence"]]))
            finding["scope"]=list(dict.fromkeys([*finding["scope"],approval_scope["unit"]]))
        if not contract.fields["adjustment"] and "adjustment" not in contract.uncertain:
            plan["detail"]=plan["detail"].replace("付款条款存在变更或原页覆盖缺口","原合同付款条款尚有未对应到完整原行的读数")
        plan["detail"]+=" 补充协议的范围栏仅列"+approval_scope["stage"]+"的签批人变更。"
    if not rows:
        output.append(result("H04","missing","缺少可逐期核对的付款约定。",plan["evidence"],plan["scope"]))
        if version == FORMAT and include_unassigned_receipts:
            output.extend(receipts_without_schedule(graph, contracts, plan["evidence"], plan["scope"]))
        return output
    expiry,warranty_refs,release_check=None,[],None
    if version in WARRANTY_FORMATS:
        warranty_stages=[r["ref"] for r in rows if r["kind"]=="warranty"]
        if warranty_stages:
            release_check=warranty_terms.assess(graph,contract,releases,[*receipts,*retests],accepted,accepted_on,warranty_stages)
            expiry=day(release_check["confirmed_on"] or "")
            warranty_refs=release_check["evidence"]
    else:
        expiry,warranty_refs=warranty(contract,releases,accepted_on)
        if batch and (len(releases)!=1 or not same_contract(contract,releases[0]) or
                      not labelled_sources(releases[0],LINK_KEYS) or not delivery_batches.readable(graph["delivery_batch_sources"],releases[0].unit)):
            expiry=None
    has_batch_notes=graph.get("delivery_batch_sources",{}).get("format") in (delivery_batches.REMARK_FORMAT,delivery_batches.FORMAT)
    opinions={}
    if version==FORMAT and (not batch or has_batch_notes or recheck_payment_opinions):
        opinions=acceptance_payments.for_stages(graph,contract,[*receipts,*retests],rows,plan)
    opinion_lines={(n["doc"],n["page"],n["line"],n["quote"]) for entry in opinions.values() for n in entry["notes"]
                   if n["scope"]!="unresolved" and n["line"] and n["stance"] in ("hold","assent")}
    for s in cash.get("lines",[]):
        if s["line"] and (s["role"]=="authority" or s["role"]=="decision" and payment_releases.RELEASE.fullmatch(payment_releases.literal(s["quote"]))):
            opinion_lines.add((s["doc"],s["page"],s["line"],s["quote"]))
    holds=[s for s in (batch or {}).get("payment_holds",[]) if not s.get("payment_only")
           or (s["doc"],s["page"],s["line"],s["quote"]) not in opinion_lines]
    hold_refs = [ref for note in holds for ref in (f"{note['doc']}/p{note['page']}",*note["facts"])]
    stages = []
    prior_checks = {}
    filenames = {doc["id"]:doc["name"] for doc in graph["documents"]} if signing_rows else {}
    def locations(records):
        return "、".join(f"《{filenames[r['doc']]}》第 {r['page']} 页第 {r['line']} 行" for r in records)
    signing_sources, acceptance_sources = locations(signing_rows), locations(shared_rows)
    for idx, row in enumerate(rows, 1):
        kind = row["kind"]
        fallback_label = f"第{idx}期" if version == FIRST_FORMAT else f"条款 {idx}"
        stage = {"name":row["label"] or fallback_label,"share":row["share"],"clause":row["text"],"clause_ref":row["ref"]}
        refs = [row["ref"], *signed["evidence"]]
        independent_first = bool(standalone and kind == "effect" and row["index"] == 1 and row["ref"] == standalone["clause_ref"])
        separate = independent_first or only_number and row.get("separate_numeric_clause")
        if folios and (separate or plan["status"] == "ok"):
            refs += folios["evidence"]
        scope = [contract.unit] if version == FIRST_FORMAT else signed["scope"].copy()
        this_batch = batch_rows.get(row.get("batch_index"))
        if kind=="batch":
            if pending_units:
                refs += page_refs
                scope += pending_units
            stage["batch_index"] = row["batch_index"]
            stage["batch_date"] = this_batch["date"] if this_batch else None
            refs += this_batch["evidence"] if this_batch else batch["evidence"]
            scope += this_batch["scope"] if this_batch else batch["scope"]
        if kind in ("acceptance","warranty"):
            refs += accepted["evidence"]
            scope += accepted["scope"]
        if kind == "warranty":
            refs += warranty_refs
            scope += [r.unit for r in releases]
            if release_check:
                scope += [r["unit"] for r in release_check.get("tickets",[])]
        if plan["status"] != "ok" and not separate:
            refs += plan["evidence"]
            if batch:
                scope += plan["scope"]
            status, detail = "missing","付款安排尚未核清，无法确认本期条件。"
        elif not kind:
            status, detail = "missing","需核对本期付款的完整前提及其履行材料。"
        elif signed["status"] != "ok":
            status, detail = "missing","合同签署或约定生效条件尚待核实。"
        elif kind=="batch" and models and models.get("exchange",{}).get("status")=="risk":
            status,detail="risk","换货交接与本批交付的关系待核，请核对批次及设备编号。"
            refs+=models["exchange"]["evidence"]
            scope+=accepted["scope"]
        elif kind=="batch":
            if this_batch:
                status="risk" if this_batch["status"]=="issue" else this_batch["status"]
                detail=this_batch["label"]+" · "+this_batch["detail"]
            else:
                status,detail="missing","本期明列的批次尚未与合同交付明细对应。"
        elif kind in ("acceptance","warranty") and accepted["status"] != "ok":
            status, detail = "risk" if accepted["status"] in ("issue","risk") else "missing","现有验收资料不足以支持本期付款。"
        elif kind=="warranty" and release_check:
            status,detail=release_check["status"],release_check["detail"]
        elif kind == "warranty" and not expiry:
            status, detail = "missing","缺少同一合同已签认的质保期满记录，请核对届满时间和放款前提。"
        else:
            status, detail = "ok","已提交资料支持本期所列的“" + row["condition"] + "”条件。"
        if holds:
            if status=="ok":
                status,detail="missing","另有付款意见，请核实签发权限、涉及期款、适用时间及后续处理。"
            else:
                detail+=" 另须核对付款意见、涉及的期款及其适用时间。"
            refs += hold_refs
            scope += [note["unit"] for note in holds]
        check = result("H04",status,detail,refs,scope,stage)
        if kind=="warranty" and release_check:
            check["warranty_check"]=release_check
            warranty_execution.attach(check,release_check)
        if version in PAYMENT_WINDOW_FORMATS:
            window=payment_windows.stage_window(graph,contract,rows,idx-1,[*receipts,*retests],signed,accepted,accepted_on,check,
                                                separate_opinions=opinion_lines)
            payment_windows.attach_stage(check,window)
        opinion=opinions.get(row["ref"])
        if opinion and cash:
            record=next((r for r in [*receipts,*retests] if opinion["units"]==[r.unit]),None)
            candidate=release_execution.proposed(graph,contract,opinion,row,record)
            release=payment_releases.assess(graph,contract,record,opinion,row) if candidate or opinion["state"]=="hold" else None
            if release:
                if candidate:
                    release["state"]="scope_pending"
                release_execution.apply(release,graph)
                release_comparison.attach(release,graph,contract,record,opinion,row)
                opinion={**opinion,"release":release,"units":list(dict.fromkeys([*opinion["units"],*release["units"]])),
                         "evidence":list(dict.fromkeys([*opinion["evidence"],*release["evidence"]]))}
        acceptance_payments.attach(check,opinion)
        if scoped_change and scoped_change["original_ref"]==row["ref"]:
            prior_checks[row["ref"]] = dict(check)
        if invoice_terms:
            entry = invoice_conditions.condition(ledger, contract, materials("invoice"), receipts, rows, idx-1, amendment=scoped_change)
            invoice_conditions.attach(check, entry)
        if row["ref"] in prior_checks:
            payment_amendments.attach(check,scoped_change)
        if kind=="effect" and signing_sources:
            check["detail"] += f" 本期以合同生效为前提，{signing_sources}所列签署要求仍须核实。"
        elif kind=="acceptance" and acceptance_sources:
            check["detail"] += f" {acceptance_sources}同时约定了验收文件的签署方式，须核对本期验收凭证。"
        output.append(check)
        stages.append((row,check))

    for bank in materials("bank_receipt"):
        designation = bank.body("payment_designation")
        refs = bank.evidence("bank_receipt","contract_id","payment_designation","paid_on","transfer_status","payer","payee")
        scope = [contract.unit,bank.unit]
        matching = [(r,s) for r,s in stages if matches_stage(designation,r)]
        if not matching and guarantees and advance_guarantee.FIRST_NAME.fullmatch(designation):
            matching = [(r,s) for r,s in stages if r["index"]==1 and advance_guarantee.FIRST_NAME.fullmatch(r["label"])]
        if version == FIRST_FORMAT:
            matching = [(r,s) for r,s in stages if designation and designation == s["stage"]["name"]]
        if version == FORMAT and authority and authority["mode"] == "joint" and len(matching) == 1 and matching[0][0]["kind"] == "acceptance":
            bank = signer_clock.bank_dates(bank, graph.get("acceptance_authority_sources", {}))
        paid = printed_day(bank,"paid_on") if version in DATE_FORMATS else day(bank.single("paid_on"))
        linked = all(contract.single(left) and contract.single(left) == bank.single(right)
                     for left,right in (("contract_id","contract_id"),("buyer","payer"),("seller","payee")))
        if release_check and any(row["kind"]=="warranty" for row,_ in matching):
            linked=linked and warranty_terms.bank_identity(contract,bank)
        refs += contract.evidence("contract_id","buyer","seller")
        if not linked or not paid or bank.single("transfer_status") not in {"交易成功","转账成功","成功","已完成"} or len(matching) != 1:
            payment = result("H05","missing","需取得本合同关联的成功回单、付款日期及回单明列的对应期次。",refs,scope)
            if version in DATE_FORMATS and bank.date("paid_on") and not paid:
                add_date_checks(payment,[date_check("payment","missing","请核对这笔款项实际支付日期的原始栏位及完整引文。",bank.evidence("paid_on"))])
            output.append(payment)
            continue
        row, check = matching[0]
        transfer_change = None
        if check.get("payment_change"):
            transfer_change = payment_amendments.at_payment(check["payment_change"],graph,contract,bank,paid)
            if transfer_change["applies"]=="original":
                check = prior_checks[row["ref"]]
        refs += check["evidence"] + contract.evidence("effect_on")
        scope += check["scope"]
        effective = printed_day(contract,"effect_on") if version in DATE_FORMATS else day(contract.body("effect_on"))
        milestones = [("合同生效","effect_on",effective)]
        if row["kind"]=="batch":
            milestones.append((f"第{row['batch_index']}批验收","accepted_on",day(check["stage"]["batch_date"] or "")))
        if row["kind"] in ("acceptance","warranty"):
            milestones.append(("验收","accepted_on",accepted_on))
        if row["kind"] == "warranty":
            milestones.append(("质保期满确认","warranty_release",expiry))
            if release_check and signed["status"]==plan["status"]=="ok" and release_check["calendar_end"]:
                milestones.append(("合同质保期间最后一日","warranty_period",day(release_check["calendar_end"])))
        dates = [when for _,_,when in milestones]
        timing = []
        if any(point and point > paid for point in dates):
            status, detail = "risk","回单付款日早于本期所据的履约日期，请复核提前支付的授权和依据。"
            if row["kind"]=="warranty" and release_check:
                future=[f"{label} {when}" for label,_,when in milestones if when and paid<when]
                detail=f"回单付款日 {paid} 早于{'、'.join(future)}，请核查提前支付的依据。"
        elif row["kind"]=="warranty" and release_check and release_check["defect_open"] and expiry and paid>=expiry:
            status,detail="risk","付款所据确认单载有未解决质量问题，需核实付款前是否已关闭及返还依据。"
        elif version in DATE_FORMATS and (row["kind"] in CONDITIONS or row["kind"]=="batch") and paid in dates:
            events = [label for label,_,when in milestones if when==paid]
            fields = [field for _,field,when in milestones if when==paid]
            status, detail = "missing",f"付款与{'、'.join(events)}同为 {paid}，需核对当日具体时分，确认付款时已满足约定。"
            relevant = {ref for doc in [contract,*receipts,*retests,*releases] for ref in doc.evidence(*fields)}
            timing = [date_check("payment","missing",detail,bank.evidence("paid_on","payment_designation")+[r for r in refs if r in relevant])]
        elif (accepted.get("reinspection",{}).get("state")=="closed" and row["kind"] in ("acceptance","warranty")
              and paid==accepted_on):
            status, detail = "missing","付款与缺陷关闭在同一天，需取得时分记录核对先后顺序。"
        elif (change or authority) and row["kind"] in ("acceptance","warranty") and (paid==accepted_on or row["kind"]=="warranty" and paid==expiry):
            status, detail = "missing","付款日与所据履约记录同日，请核对当日验收或质保确认与付款的具体时分。"
        elif check["status"] != "ok" or not all(dates):
            status, detail = "missing","付款对应本期，现有材料尚不足以证实付款日已满足全部前提。"
        else:
            status, detail = "ok","回单列明本期，付款日期达到所据履约日期。"
        payment = result("H05",status,detail,refs,scope,check["stage"])
        if row["kind"]=="warranty" and release_check:
            payment["warranty_check"]=release_check
            written = "date" in release_check.get("certificate",{})
            comparison = warranty_dates.compare(graph,release_check,bank,paid,row["ref"]) if written else None
            warranty_execution.attach(payment,release_check,paid=paid.isoformat() if not written or comparison else None)
            timing.extend(warranty_service.payment_checks(release_check.get("tickets",[]),bank,paid.isoformat()))
            snapshot=release_check.get("at_submission")
            if snapshot:
                dates_on_receipt=bank.evidence("paid_on")
                as_of=snapshot["as_of"]
                beyond=paid.isoformat()>as_of if as_of else None
                payment["warranty_payment"]={"paid_on":paid.isoformat(),"date_refs":dates_on_receipt,"after_submission":beyond}
                if written:
                    payment["warranty_payment"]["comparison"] = comparison
                    if comparison:
                        payment["evidence"] = list(dict.fromkeys([*payment["evidence"], *comparison["evidence"]]))
                if beyond:
                    timing.append(date_check("payment","risk",f"回单列示付款日 {paid} 晚于资料提交日 {as_of}，需核实实际扣款记录。",
                                             dates_on_receipt+bank.evidence("transfer_status","payment_designation")))
        add_date_checks(payment,timing)
        if version in PAYMENT_WINDOW_FORMATS:
            payment_windows.compare_transfer(payment,check,graph,contract,bank,row)
        if not transfer_change or transfer_change["applies"]=="amended":
            invoice_conditions.reconcile_payment(payment, check, graph, contract, bank, paid)
        if transfer_change:
            payment_amendments.attach(payment,transfer_change)
        sealed=signed.get("effect_review",{}).get("seals",{}).get("completed_on")
        if sealed and paid and paid.isoformat()<sealed and warranty_terms.bank_identity(contract,bank):
            bank_sources=graph.get("payment_window_sources",{})
            pages=[p for p in bank_sources.get("pages",[]) if p["unit"]==bank.unit]
            clean=pages and all(p["native"] and p["text_only"] for p in pages) and not any(s["unit"]==bank.unit for s in bank_sources["lines"])
            if clean:
                payment.update(status="risk",detail=f"本笔回单付款日 {paid} 早于合同双方最后盖章日 {sealed}，须核实提前支付的授权、追认或其他履约依据。")
        opinion=check.get("payment_opinion")
        if opinion and opinion.get("release"):
            opinion=payment_releases.at_payment(opinion,contract,bank)
        acceptance_payments.attach(payment,opinion)
        if version == FORMAT and row["kind"] == "acceptance":
            signer_timing.compare(payment, graph, contract, bank, paid, authority, receipts,
                                  other_terms=bool(extra_units or changes or repairs or retests or pending_units or batch))
        if row["kind"]=="effect" and signing_sources:
            payment["detail"] += f" 回单列示付款日 {paid}，请对照{signing_sources}，补核当时的签署依据。"
        elif row["kind"]=="acceptance" and acceptance_sources:
            payment["detail"] += f" 回单列示付款日 {paid}，请按{acceptance_sources}核对付款时已有的验收签署凭证。"
        output.append(payment)
    return output


def verify_findings(report, *, signing=False):
    policy = report["policy"]
    marker = policy.get("performance_checks")
    if "performance.py" in policy.get("code_sha256", {}) and marker not in SUPPORTED:
        raise ValueError("底稿缺少对应的合同履约程序版本")
    if marker is None:
        return
    profile = policy["profile"]
    if marker not in SUPPORTED or report["graph"].get("profile") != profile:
        raise ValueError("合同履约范围或程序版本不符")
    if marker in (REINSPECTION_FORMAT, *MANDATE_FORMATS):
        verify_number_links(report["graph"])
    include_receipts = policy.get("version", "") >= RECEIPT_COVERAGE_SINCE
    expected = [] if profile == "cn-travel-reimbursement/v1" else compute(
        report["graph"], marker, include_unassigned_receipts=include_receipts)
    found = [f for f in report["findings"] if f["rule"] in RULES]
    if len(found) != len(expected):
        raise ValueError("合同履约程序数量与证据图谱不符")
    # This issuer preserved every receipt proof in evidence but omitted the named list.
    legacy_receipts = (policy.get("version") == "2026.11.26.27" and
                       policy.get("code_sha256", {}).get("controls.py") ==
                       "eeff68cc20371bace1b158ebf70cc33885603b3913d8896f7b95236be19cd8a6")
    for entry, saved in zip(expected, found):
        rule = saved["rule"]
        position = report["findings"].index(saved) + 1
        if "acceptance_signing_requirements" in entry and contract_effect.omitted_acceptance_refs(policy):
            if signing:
                raise ValueError("旧版验收发现缺少签署条款定位清单，请重审后签收。")
            entry = {key:value for key,value in entry.items() if key!="acceptance_signing_requirements"}
        if legacy_receipts and "acceptance_execution" in entry:
            entry = {key: value for key, value in entry.items() if key != "acceptance_execution"}
        if (any(saved.get(key) != val for key, val in entry.items()) or saved.get("stage") != entry.get("stage")
                or saved.get("reinspection") != entry.get("reinspection") or saved.get("delegations") != entry.get("delegations")
                or saved.get("quality_change") != entry.get("quality_change")
                or saved.get("acceptance_execution") != entry.get("acceptance_execution")
                or saved.get("acceptance_originals") != entry.get("acceptance_originals")
                or saved.get("acceptance_authority") != entry.get("acceptance_authority")
                or saved.get("acceptance_signing_requirements") != entry.get("acceptance_signing_requirements")
                or saved.get("date_checks") != entry.get("date_checks")
                or saved.get("batch_acceptance") != entry.get("batch_acceptance")
                or saved.get("effect_review") != entry.get("effect_review")
                or saved.get("warranty_check") != entry.get("warranty_check")
                or saved.get("warranty_payment") != entry.get("warranty_payment")
                or saved.get("payment_quality") != entry.get("payment_quality")
                or saved.get("quality_comparison") != entry.get("quality_comparison")
                or saved.get("reading_caveats") != entry.get("reading_caveats")
                or saved.get("retest_reference") != entry.get("retest_reference")
                or saved.get("inspection_use") != entry.get("inspection_use")
                or saved.get("party_readings") != entry.get("party_readings")
                or saved.get("installment_count") != entry.get("installment_count")
                or saved.get("warranty_difference") != entry.get("warranty_difference")
                or saved.get("contract_folios") != entry.get("contract_folios")
                or saved.get("prior_installment") != entry.get("prior_installment")
                or saved.get("advance_guarantee") != entry.get("advance_guarantee")
                or saved.get("payment_acceptance") != entry.get("payment_acceptance")
                or saved.get("stage_approvers") != entry.get("stage_approvers")
                or saved.get("approval_change") != entry.get("approval_change")
                or saved.get("approval_change_scope") != entry.get("approval_change_scope")
                or saved.get("signer_timing") != entry.get("signer_timing")
                or saved.get("execution_basis") != entry.get("execution_basis")
                or saved.get("inspection_coverage") != entry.get("inspection_coverage")
                or saved.get("equipment_models") != entry.get("equipment_models")
                or saved.get("stage_payments") != entry.get("stage_payments")
                or saved.get("payment_change") != entry.get("payment_change")
                or saved.get("payment_opinion") != entry.get("payment_opinion")
                or saved.get("invoice_receipt") != entry.get("invoice_receipt")
                or saved.get("payment_window") != entry.get("payment_window")
                or saved.get("acceptance_comments") != entry.get("acceptance_comments")
                or saved.get("contract_comments") != entry.get("contract_comments")
                or saved.get("acceptance_reservations") != entry.get("acceptance_reservations")
                or (saved.get("id"),saved.get("version"),saved.get("title"),saved.get("basis")) !=
                (f"{rule}-{position}",policy["version"],*RULES[rule])):
            raise ValueError("合同履约结论、期次或引文与证据图谱不符")
    if (signing and not include_receipts and any(f["rule"]=="H04" for f in found)
            and not any(f["rule"]=="H05" for f in found) and report["graph"]["documents_by_kind"].get("bank_receipt")):
        raise ValueError("旧版底稿有银行回单未逐笔核对。请保留原版，重新审计后签收。")
    if signing and marker not in DATE_FORMATS and any(f["status"]=="ok" and f["rule"] in ("H01","H02","H05") for f in found):
        old_ok = {(f["rule"],tuple(sorted(f["scope"]))) for f in found if f["status"]=="ok"}
        for current in compute(report["graph"],FORMAT):
            if current.get("date_checks") and any(rule==current["rule"] and set(scope)<=set(current["scope"]) for rule,scope in old_ok):
                raise ValueError("旧版合同或付款日期仍有先后疑点，请按现行程序重审后签收。")
