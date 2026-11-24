"""Evidence-based checks for contract effectiveness, acceptance and payment milestones."""

import re
import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal
from reinspection import LABELS as REINSPECTION_FIELDS, LINK_KEYS, assess as assess_reinspection, linked as same_contract, verify_number_links
from delegation import LABELS as DELEGATION_FIELDS, PARTY_SIGNATURES, checks as check_delegations, complete_id
from contract_changes import LABELS as ADDENDUM_FIELDS, LIMIT, SOURCE_LABELS, candidates as change_candidates, labelled_sources, resolve as resolve_change
from acceptance_authority import LABELS as AUTHORITY_FIELDS, SIGN_LABELS, check as check_acceptance_authority


PROFILE = "cn-contract-performance/v1"
FIRST_FORMAT = "contract-performance-v1"
BOARD_FORMAT = "contract-performance-v2"
REINSPECTION_FORMAT = "contract-performance-v3"
DELEGATION_FORMAT = "contract-performance-v4"
IDENTITY_FORMAT = "contract-performance-v5"
NATIVE_FORMAT = "contract-performance-v6"
ADDENDUM_FORMAT = "contract-performance-v7"
SIGNATORY_FORMAT = "contract-performance-v8"
FORMAT = "contract-performance-v9"
SIGNATORY_FORMATS = (SIGNATORY_FORMAT,FORMAT)
ADDENDUM_FORMATS = (ADDENDUM_FORMAT,*SIGNATORY_FORMATS)
MANDATE_FORMATS = (DELEGATION_FORMAT, IDENTITY_FORMAT, NATIVE_FORMAT, *ADDENDUM_FORMATS)
SUPPORTED = (FIRST_FORMAT, BOARD_FORMAT, REINSPECTION_FORMAT, *MANDATE_FORMATS)
RULES = {
    "H01": ("合同签署与约定生效条件", "核对合同双方、签订日期、生效条款和签署栏的人工核图记录，保留附加条件及状态疑点。"),
    "H02": ("交付范围与验收质量", "按合同编号、标的和采购方关联验收资料，核对日期、验收范围、结论、签认和遗留事项。"),
    "H03": ("付款安排与期次完整性", "从合同原文提取期次及付款条件，按约定核对期序、期数及比例合计。"),
    "H04": ("本期付款条件", "逐期核对合同写明的付款前提与履约证据，分别列示预付款、验收款和质保金等约定。"),
    "H05": ("实付日期与合同前提", "按同一合同、回单明列期次及付款日期，核对付款时点已有的履约证据。"),
}
LABELS = {
    **REINSPECTION_FIELDS,
    **DELEGATION_FIELDS,
    **ADDENDUM_FIELDS,
    **AUTHORITY_FIELDS,
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
        self.mandate_pages = [p for p in graph.get("delegation_coverage", {}).get("pages", []) if p["unit"]==unit]
        self.agent_holds = [h for h in graph.get("delegation_coverage", {}).get("agent_holds", []) if h["unit"]==unit]
        self.signer_holds = [h for h in graph.get("delegation_coverage", {}).get("signer_holds", []) if h["unit"]==unit]
        self.quality_holds = [h for h in graph.get("quality_references", {}).get("holds", []) if h["unit"] == unit]
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
                self.fields[field].append(fact)
            else:
                self.uncertain.add(field)
        self.gaps = [g for g in graph.get("gaps", []) if g["doc"] == source and (page is None or page == g["page"])]
        self.notes = [n for n in graph.get("cautions", []) + graph.get("performance_cautions", []) if n["doc"] == source and
                      (page is None or n["page_id"] == f"{source}/p{page}")]

    def evidence(self, *fields):
        refs = [f["id"] for f in self.refs if f["field"] in fields]
        refs += [g["id"] for g in self.gaps if not g.get("field") or g["field"] in fields]
        return list(dict.fromkeys(refs))

    def incomplete(self, *fields):
        return bool(self.uncertain.intersection(fields) or any(not g.get("field") or g["field"] in fields for g in self.gaps))

    def single(self, field):
        rows = self.fields[field]
        values = {norm(f["value"]) for f in rows}
        return next(iter(values)) if len(values) == 1 and not self.incomplete(field) else ""

    def date(self, field):
        return day(self.body(field))

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


DATE_LABELS = {**SOURCE_LABELS, "accepted_on":("验收日期","验收时间","复验日期","复验时间"),
               "paid_on":("付款日期","转账日期","交易日期","支付日期")}


def printed_day(material, field):
    parsed = material.date(field)
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


def receipt_date_checks(contract, receipts, retests):
    checks = []
    effective = printed_day(contract,"effect_on")
    for record in [*receipts,*retests]:
        if not all(contract.body(k) and contract.body(k)==record.body(k) for k in ("contract_id","buyer","subject")):
            continue
        is_retest = record in retests or any(record.fields[k] for k in ("original_acceptance","defect_closure","repair_number"))
        label = "复验" if is_retest else "验收"
        accepted = printed_day(record,"accepted_on")
        refs = contract.evidence("effect_on",*LINK_KEYS)+record.evidence("accepted_on",*LINK_KEYS)
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
    effective = day(contract.single("effect_on"))
    if not approved:
        return "missing","审批记录缺少可核的决定日期。",refs
    if effective and effective < approved:
        return "risk","材料所列生效日早于约定审批机构的批准日，请核对生效时点。",refs
    return "ok","约定的董事会批准决定、日期和签认已有材料支持。",refs


def effect(contract, approvals=(), version=FORMAT, grants=()):
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
    if not day(contract.single("signed_on")):
        missing.append("可核的签订日期")
    if not board and not EFFECT.fullmatch(terms):
        missing.append("生效约定及其中每项条件的证明")
    mode = "seal" if "盖章" in terms and "或" not in terms else "sign" if ("签字" in terms or "签名" in terms) and "或" not in terms else None
    delegations = check_delegations(contract, grants, strict_names=version!=DELEGATION_FORMAT) if version in MANDATE_FORMATS else []
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
    effective, signed, expiry = (day(contract.single(k)) for k in ("effect_on","signed_on","valid_until"))
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
    if board:
        approval_status, note, evidence = check_approval(contract,approvals,board[1])
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


def acceptance(contract, receipts, *, criterion=None, signature_ok=None):
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
    if outcome in {"不合格","验收不合格","未通过","验收未通过","拒收","最终验收不合格","终验不合格"}:
        return finding("issue","本合同对应验收记录明确记载“" + outcome + "”，需查明缺陷及复验处置。")
    quality = None
    if contract.fields["acceptance_criteria"] or r.fields["inspection_basis"] or r.fields["measured_result"]:
        basis, reading = r.body("inspection_basis"), r.body("measured_result")
        standard = contract.body("acceptance_criteria") if criterion is None else criterion
        quality = inspect_quality(standard,basis,reading)
        if criterion and standard!=basis:
            observation = inspect_quality(standard,standard,reading)
            if observation[0]=="issue":
                quality = ("issue",observation[1]+" 验收报告所引检验依据同时需核对。")
        if quality[0]=="issue":
            return finding("issue",quality[1]+(" 验收结论栏同时记载“"+outcome+"”，请核对并复验。" if outcome else ""))
    if (outcome and outcome not in PASS) or (scope and scope not in FINAL_SCOPES) or (
        r.fields["acceptance_exception"] and r.body("acceptance_exception") not in CLEAN):
        return finding("risk","验收范围、质量结论或遗留事项存在限定，需核对分批交付、整改及复验记录。")
    signed, accepted = day(contract.single("signed_on")), day(r.single("accepted_on"))
    if signed and accepted and accepted < signed:
        return finding("risk","验收记录日期早于签约日期，需核实履行背景和实际时间。")
    until = day(contract.single("valid_until"))
    if until and accepted and accepted > until:
        return finding("risk","验收日期在所列合同有效期之后，需核对延期、变更及继续履行依据。")
    missing = []
    if quality and quality[0] != "ok":
        return finding(*quality)
    if contract.incomplete("acceptance_criteria"):
        missing.append("合同验收标准原文")
    if contract.fields["quantity_agreed"] or r.fields["quantity_accepted"] or contract.incomplete("quantity_agreed"):
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


def schedule(contract):
    fields = ("payment_term","payment_stage","adjustment")
    refs = contract.evidence("contract",*fields)
    rows, counts, issues = [], set(), []
    seen_lines = set()
    for fact in contract.fields["payment_term"] + contract.fields["payment_stage"]:
        line = norm(fact["quote"])
        if line in seen_lines:
            continue
        seen_lines.add(line)
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
            rows.append(dict(index=index, label=label, share=share, kind=kind, condition=condition,
                             text=part, ref=fact["id"]))
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
    if contract.fields["adjustment"] or contract.incomplete(*fields):
        issues.append("付款条款存在变更或原页覆盖缺口")
    uncovered = [n for n in contract.notes if re.search(r"分期|分[两二三四五六七八九十\d]+期|预付|尾款|质保金|保留款|第.+期|补充协议|另附|另行约定",n["quote"])
                 and norm(n["quote"]) not in seen_lines]
    if uncovered:
        refs += [n["page_id"] for n in uncovered]
        issues.append("另有待归入付款安排的原文")
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


def compute(graph, version=FORMAT):
    kinds = graph["documents_by_kind"]
    def materials(kind):
        return [Material(graph, unit) for unit in kinds.get(kind, ())]
    contracts = materials("contract")
    if len(contracts) != 1:
        scope = [d["id"] for d in graph.get("audit_documents", graph["documents"])]
        refs = [f["id"] for f in graph["facts"] if f["field"] == "contract"]
        return [result(rule,"missing","需先确定本次审查所据的一份现行合同及其资料归属。",refs,scope)
                for rule in ("H01","H02","H03","H04")]
    contract = contracts[0]
    receipts, releases = materials("acceptance"), materials("warranty")
    approvals = materials("contract_approval") if version != FIRST_FORMAT else []
    grants = materials("power_of_attorney") if version in MANDATE_FORMATS else ()
    signed = effect(contract, approvals, version, grants)
    if version==FORMAT:
        add_date_checks(signed,period_checks(contract))
    classified = {u for group in kinds.values() for u in group}
    extra_units = {d["id"] for d in graph.get("audit_documents",graph["documents"])} - classified
    changes = change_candidates(graph) if version in ADDENDUM_FORMATS else []
    repairs, retests = materials("remediation"), materials("reinspection")
    change = None
    if changes:
        multiple = bool(repairs or retests or len(receipts)!=1 or any(r.fields[k] or k in r.uncertain
                        for r in receipts for k in ("original_acceptance","repair_number","defect_closure")))
        change = resolve_change(graph,contract,[Material(graph,u) for u in changes],receipts,multiple_events=multiple,
                                contract_supported=signed["status"]=="ok",unclassified=extra_units)
        change["evidence"] = list(dict.fromkeys(change["evidence"]+signed["evidence"]))
    authority = None
    if version in SIGNATORY_FORMATS:
        authority = check_acceptance_authority(graph,contract,receipts,retests,contract_supported=signed["status"]=="ok",
                                              other_terms=bool(extra_units or change and not change["scope_clear"]), name_records=version==FORMAT)
    by_unit = {r["unit"]:r for r in authority["records"]} if authority else {}
    def signatory(record):
        return by_unit[record.unit]["status"]=="ok" if record.unit in by_unit else record.signed("acceptance_signer")
    def evaluate(contract, selected):
        return acceptance(contract,selected,criterion=(change["applied_criterion"] or "") if change else None,
                          signature_ok=signatory if authority else None)
    if version in (REINSPECTION_FORMAT, *MANDATE_FORMATS):
        accepted, accepted_on = assess_reinspection(contract,receipts,repairs,retests,evaluate,signature_ok=signatory if authority else None)
    else:
        accepted = acceptance(contract, receipts)
        accepted_on = day(receipts[0].single("accepted_on")) if accepted["status"]=="ok" else None
    plan, rows = schedule(contract)
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
    if version==FORMAT:
        chronology = receipt_date_checks(contract,receipts,retests)
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
            item.update(status="missing", detail="另有尚未归属的资料，请核对其是否变更本合同或付款约定。")
            item["evidence"] = list(dict.fromkeys(item["evidence"] + (refs or [doc["id"]])))
            if doc["id"] not in item["scope"]:
                item["scope"].append(doc["id"])
    output = [signed, accepted, plan]
    if not rows:
        output.append(result("H04","missing","缺少可逐期核对的付款约定。",plan["evidence"],plan["scope"]))
        return output
    expiry, warranty_refs = warranty(contract, releases, accepted_on)
    stages = []
    for idx, row in enumerate(rows, 1):
        kind = row["kind"]
        fallback_label = f"第{idx}期" if version == FIRST_FORMAT else f"条款 {idx}"
        stage = {"name":row["label"] or fallback_label,"share":row["share"],"clause":row["text"],"clause_ref":row["ref"]}
        refs = [row["ref"], *signed["evidence"]]
        scope = [contract.unit] if version == FIRST_FORMAT else signed["scope"].copy()
        if kind in ("acceptance","warranty"):
            refs += accepted["evidence"]
            scope += accepted["scope"]
        if kind == "warranty":
            refs += warranty_refs
            scope += [r.unit for r in releases]
        if plan["status"] != "ok":
            refs += plan["evidence"]
            status, detail = "missing","付款安排尚未核清，无法确认本期条件。"
        elif not kind:
            status, detail = "missing","需核对本期付款的完整前提及其履行材料。"
        elif signed["status"] != "ok":
            status, detail = "missing","合同签署或约定生效条件尚待核实。"
        elif kind in ("acceptance","warranty") and accepted["status"] != "ok":
            status, detail = "risk" if accepted["status"] in ("issue","risk") else "missing","现有验收资料不足以支持本期付款。"
        elif kind == "warranty" and not expiry:
            status, detail = "missing","缺少同一合同已签认的质保期满记录，请核对届满时间和放款前提。"
        else:
            status, detail = "ok","已提交资料支持本期所列的“" + row["condition"] + "”条件。"
        check = result("H04",status,detail,refs,scope,stage)
        output.append(check)
        stages.append((row,check))

    for bank in materials("bank_receipt"):
        designation = bank.body("payment_designation")
        refs = bank.evidence("bank_receipt","contract_id","payment_designation","paid_on","transfer_status","payer","payee")
        scope = [contract.unit,bank.unit]
        matching = [(r,s) for r,s in stages if matches_stage(designation,r)]
        if version == FIRST_FORMAT:
            matching = [(r,s) for r,s in stages if designation and designation == s["stage"]["name"]]
        paid = printed_day(bank,"paid_on") if version==FORMAT else day(bank.single("paid_on"))
        linked = all(contract.single(left) and contract.single(left) == bank.single(right)
                     for left,right in (("contract_id","contract_id"),("buyer","payer"),("seller","payee")))
        refs += contract.evidence("contract_id","buyer","seller")
        if not linked or not paid or bank.single("transfer_status") not in {"交易成功","转账成功","成功","已完成"} or len(matching) != 1:
            payment = result("H05","missing","需取得本合同关联的成功回单、付款日期及回单明列的对应期次。",refs,scope)
            if version==FORMAT and bank.date("paid_on") and not paid:
                add_date_checks(payment,[date_check("payment","missing","请核对这笔款项实际支付日期的原始栏位及完整引文。",bank.evidence("paid_on"))])
            output.append(payment)
            continue
        row, check = matching[0]
        refs += check["evidence"] + contract.evidence("effect_on")
        scope += check["scope"]
        effective = printed_day(contract,"effect_on") if version==FORMAT else day(contract.body("effect_on"))
        milestones = [("合同生效","effect_on",effective)]
        if row["kind"] in ("acceptance","warranty"):
            milestones.append(("验收","accepted_on",accepted_on))
        if row["kind"] == "warranty":
            milestones.append(("质保期满确认","warranty_release",expiry))
        dates = [when for _,_,when in milestones]
        timing = []
        if any(point and point > paid for point in dates):
            status, detail = "risk","回单付款日早于本期所据的履约日期，请复核提前支付的授权和依据。"
        elif version==FORMAT and row["kind"] in CONDITIONS and paid in dates:
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
        add_date_checks(payment,timing)
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
    expected = [] if profile == "cn-travel-reimbursement/v1" else compute(report["graph"],marker)
    found = [f for f in report["findings"] if f["rule"] in RULES]
    if len(found) != len(expected):
        raise ValueError("合同履约程序数量与证据图谱不符")
    for entry, saved in zip(expected, found):
        rule = saved["rule"]
        position = report["findings"].index(saved) + 1
        if (any(saved.get(key) != val for key, val in entry.items()) or saved.get("stage") != entry.get("stage")
                or saved.get("reinspection") != entry.get("reinspection") or saved.get("delegations") != entry.get("delegations")
                or saved.get("quality_change") != entry.get("quality_change")
                or saved.get("acceptance_authority") != entry.get("acceptance_authority")
                or saved.get("date_checks") != entry.get("date_checks")
                or (saved.get("id"),saved.get("version"),saved.get("title"),saved.get("basis")) !=
                (f"{rule}-{position}",policy["version"],*RULES[rule])):
            raise ValueError("合同履约结论、期次或引文与证据图谱不符")
    if signing and marker!=FORMAT and any(f["status"]=="ok" and f["rule"] in ("H01","H02","H05") for f in found):
        old_ok = {(f["rule"],tuple(sorted(f["scope"]))) for f in found if f["status"]=="ok"}
        for current in compute(report["graph"],FORMAT):
            if current.get("date_checks") and any(rule==current["rule"] and set(scope)<=set(current["scope"]) for rule,scope in old_ok):
                raise ValueError("旧版合同或付款日期仍有先后疑点，请按现行程序重审后签收。")
