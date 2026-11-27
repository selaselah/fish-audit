import re
from collections import defaultdict
from datetime import date
from calculations import CalculationEvidence, in_yuan, money

from config import BANK, PERFORMANCE, PROFILE, RULE_VERSION, TRAVEL
from conclusions import STATUS, conclusion
from graph import KINDS, audit_documents, compact
from invoice_approval import FORMAT as INVOICE_APPROVAL_FORMAT
from invoice_comparison import FORMAT as INVOICE_LOOKUP, check_history as check_invoice_history
from invoice_identity import FORMAT as INVOICE_IDENTITY_FORMAT, InvoiceIdentities, identity_key, match_claim, within_case
from invoice_masks import FORMAT as MASK_FORMAT, withheld_invoices
from invoice_proof import FORMAT as INVOICE_SOURCE_FORMAT
from model import FIELDS, SIGNALS, expert_candidates
from payment_history import HISTORY_RULES, attach_history, check_history, payment_record
from payment_checks import FORMAT as PAYMENT_CHECKS
from payment_reference import FORMAT as PAYMENT_REFERENCE_FORMAT
from performance import FORMAT as PERFORMANCE_FORMAT, RULES as PERFORMANCE_RULES, compute as check_performance
from policy import ACCOUNTING, MAPPING, SOURCES
from reinspection import closed_steps
from invoice_conditions import FORMAT as INVOICE_RECEIPT
from repair_completion import FORMAT as REPAIR_COMPLETION
from contract_folios import FORMAT as CONTRACT_FOLIOS
from reinspection_wait import FORMAT as REINSPECTION_WAIT
from quality_labels import FORMAT as QUALITY_NUMBER_FORMAT
from quality_references import FORMAT as QUALITY_REFERENCE_FORMAT
from acceptance_authority import FORMAT as ACCEPTANCE_AUTHORITY
from prior_installment import FORMAT as PRIOR_INSTALLMENT
from inspection_coverage import FORMAT as INSPECTION_COVERAGE
from equipment_models import FORMAT as EQUIPMENT_MODELS
from stage_payments import FORMAT as STAGE_PAYMENTS
from payment_execution import FORMAT as PAYMENT_EXECUTION
from advance_guarantee import FORMAT as ADVANCE_GUARANTEE
from payment_acceptance import FORMAT as PAYMENT_ACCEPTANCE
from receipt_packets import FORMAT as RECEIPT_PACKETS
from delivery_batches import FORMAT as DELIVERY_BATCHES
from contract_effect import FORMAT as CONTRACT_EFFECT
from acceptance_execution import FORMAT as ACCEPTANCE_PDF
from acceptance_originals import FORMAT as ACCEPTANCE_ORIGINALS
from addendum_originals import FORMAT as ADDENDUM_ORIGINALS
from addendum_execution import FORMAT as ADDENDUM_PDF
from mandate_execution import FORMAT as MANDATE_PDF
from mandate_originals import FORMAT as MANDATE_ORIGINALS
from pdf_execution import FORMAT as PDF_EXECUTION
from supplier_pages import FORMAT as SUPPLIER_PAGE_INSPECTION
from warranty_terms import FORMAT as WARRANTY_CHECKS
from payment_windows import FORMAT as PAYMENT_WINDOWS
from acceptance_comments import FORMAT as WORD_REVIEWS
from contract_comments import FORMAT as CONTRACT_WORD_REVIEWS
from acceptance_reservations import FORMAT as RESERVATIONS
from payment_releases import FORMAT as PAYMENT_RELEASES
from release_execution import FORMAT as RELEASE_EXECUTION
from release_comparison import FORMAT as RELEASE_COMPARISON
from warranty_execution import FORMAT as WARRANTY_EXECUTION
from payment_quality import FORMAT as PAYMENT_QUALITY
from retest_reference import FORMAT as RETEST_REFERENCE
from warranty_dates import FORMAT as WARRANTY_DATES
from board_execution import FORMAT as BOARD_DECISION
from contract_changes import FORMAT as ADDENDUM_FORMAT
from delegation import FORMAT as DELEGATION_FORMAT
from transfers import RULES as TRANSFER_RULES, check_transfers


CATALOG = {
    **PERFORMANCE_RULES,
    **TRANSFER_RULES,
    **HISTORY_RULES,
    "E01": ("原件与证据覆盖", "每页均可辨读，关键字段具备可定位文字或人工核图记录。"),
    "P01": ("采购资料完整性", "单合同、一次全额验收结算范围内需要一份合同、一份发票和一份验收资料。"),
    "P02": ("合同编号关联", "沿各份资料的合同编号关系，验证三份资料是否指向同一合同。"),
    "P03": ("交易双方一致性", "从合同、发票和验收单的采购方和供应方关系核对交易主体全称。"),
    "I01": ("发票标识重叠", "按原页比较发票标识。八位号码结合同页已核代码，二十位号码按完整号码比对。"),
    "I02": ("本工作区已归档票号比对", "在本企业签收底稿中检出相同号码，八位号码另核双方同页代码，按完整标识及单据归属判断。"),
    "M01": ("发票价税勾稽", "同一发票、相同人民币元口径下，不含税合计加税额合计应等于价税合计，精确到分。"),
    "C01": ("全额结算适用性", "从合同核对是否明确一次结清，分期、质保、红冲或变更转人工核对。"),
    "M02": ("合同、发票与验收金额", "相同合同、人民币元、一次全额结算范围内，比较合同、发票及验收含税总额。"),
    "D01": ("采购业务日期", "查验签约、开票和验收日期。发票或验收早于签约需了解背景。"),
    "A01": ("验收结论", "本程序要求全额结算具有明确无保留的验收合格记录。"),
    "S01": ("采购标的核对", "逐份比对标的名称，简称、规格差异或多行明细交由人工检查。"),
    "X01": ("专家追加程序", "模型仅从已登记的追加程序中选择，需引用本案对应字段的证据。"),
    "T01": ("报销资料组成", "单份差旅报销申请，附可识别的发票资料。"),
    "T02": ("随附票号关联", "报销申请列示的票号集合与本案提交的发票号码逐一勾稽。"),
    "T03": ("报销额与凭证合计", "按本案全凭票报销口径，申请金额与已关联、未重号的人民币元票据合计比较。"),
    "T04": ("差旅期间核对", "逐张检查费用实际发生日期是否落入申报行程的起止期间。"),
    "T05": ("出差人员关联", "对照报销单与具名票据中的出差人，缺姓名、别名和不一致均交人工。"),
}
VERSION = {"profile": PROFILE, "version": RULE_VERSION, "background": ACCOUNTING, "performance_checks":PERFORMANCE_FORMAT,
           "release_execution": RELEASE_EXECUTION, "release_comparison": RELEASE_COMPARISON, "warranty_execution": WARRANTY_EXECUTION,
           "warranty_dates": WARRANTY_DATES, "board_decision": BOARD_DECISION, "payment_quality": PAYMENT_QUALITY, "retest_reference": RETEST_REFERENCE,
           "advance_guarantee":ADVANCE_GUARANTEE,
           "invoice_receipt_conditions":INVOICE_RECEIPT, "acceptance_reservations":RESERVATIONS, "acceptance_word_reviews":WORD_REVIEWS, "contract_word_reviews":CONTRACT_WORD_REVIEWS, "payment_releases":PAYMENT_RELEASES, "equipment_models":EQUIPMENT_MODELS, "repair_completion":REPAIR_COMPLETION, "reinspection_wait": REINSPECTION_WAIT, "contract_folios": CONTRACT_FOLIOS, "inspection_coverage":INSPECTION_COVERAGE, "prior_installment":PRIOR_INSTALLMENT,
           "quality_number_classification":QUALITY_NUMBER_FORMAT, "quality_references":QUALITY_REFERENCE_FORMAT,
           "delegation_checks":DELEGATION_FORMAT, "quality_addenda":ADDENDUM_FORMAT, "acceptance_authority":ACCEPTANCE_AUTHORITY,"delivery_batches":DELIVERY_BATCHES,"receipt_packets":RECEIPT_PACKETS,"stage_payments":STAGE_PAYMENTS, "payment_acceptance":PAYMENT_ACCEPTANCE, "payment_execution":PAYMENT_EXECUTION,
           "supplier_page_inspection": SUPPLIER_PAGE_INSPECTION, "pdf_execution": PDF_EXECUTION, "acceptance_pdf": ACCEPTANCE_PDF, "acceptance_originals": ACCEPTANCE_ORIGINALS, "addendum_pdf": ADDENDUM_PDF, "addendum_originals": ADDENDUM_ORIGINALS, "mandate_pdf": MANDATE_PDF, "mandate_originals": MANDATE_ORIGINALS, "contract_effect":CONTRACT_EFFECT,"warranty_checks":WARRANTY_CHECKS,"payment_windows":PAYMENT_WINDOWS,"sources": SOURCES, "rule_sources": MAPPING, "invoice_sources": INVOICE_SOURCE_FORMAT,
           "invoice_approval": INVOICE_APPROVAL_FORMAT,"invoice_identity":INVOICE_IDENTITY_FORMAT,"invoice_lookup":INVOICE_LOOKUP,
           "invoice_number_masks":MASK_FORMAT,"payment_references":PAYMENT_REFERENCE_FORMAT,"payment_checks":PAYMENT_CHECKS}
FULL_TERMS = {"验收后一次性全额结算", "验收后一次性付清", "一次性全额结算", "一次性付清",
              "验收合格后一次性支付全款", "一次性全额付款", "一次结清", "一次性结清", "一次付清"}
FULL_ACCEPTANCE = {"合格", "验收合格", "通过", "验收通过", "全部合格"}


def ids(*groups):
    return list(dict.fromkeys(fact["id"] for group in groups for fact in group))


def parsed_date(fact):
    value = compact(fact["value"])
    match = re.fullmatch(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", value)
    if not match:
        return None
    try:
        return date(*map(int, match.groups()))
    except ValueError:
        return None


def execute(graph, profile=PROFILE, payment_lookup=None):
    findings = []
    performance = [] if profile==TRAVEL else check_performance(graph)
    chain = closed_steps(performance)
    evidence = CalculationEvidence(graph)
    docs = audit_documents(graph)
    kinds = graph["documents_by_kind"]
    facts = {fact["id"]: fact for fact in graph["facts"]}
    linked = defaultdict(list)
    for edge in graph["edges"]:
        if edge["type"] in FIELDS:
            linked[(edge["from"], edge["type"])].extend(facts[ref] for ref in edge["evidence"])

    def record(rule, status, observation, refs, scope=None, *, invoice_lookup=None):
        findings.append({"id": f"{rule}-{len(findings)+1}", "rule": rule, "version": RULE_VERSION,
                         "title": CATALOG[rule][0], "basis": CATALOG[rule][1], "status": status,
                         "detail": observation, "evidence": list(dict.fromkeys(refs)), "scope": scope or []})
        if invoice_lookup is not None:
            findings[-1]["invoice_lookup"] = invoice_lookup
        calculations = evidence.formulas(findings[-1],chain.get("final"))
        if calculations:
            findings[-1]["calculations"] = calculations
        return status

    def single(doc, field):
        values = linked[doc, field]
        distinct = {compact(fact["value"]) for fact in values}
        return values[0] if len(distinct) == 1 else None

    def values(rule, pairs):
        found = [single(doc, field) for doc, field in pairs]
        if None not in found:
            return found
        absent = [f"{names[doc]} · {FIELDS[field]}" for (doc, field), value in zip(pairs, found) if value is None]
        references = [fact["id"] for doc, field in pairs for fact in graph["facts"]
                      if fact.get("unit", fact["doc"]) == doc and fact["field"] == field]
        record(rule, "missing", "待补证或消除歧义：" + "、".join(absent), references, list(dict.fromkeys(doc for doc, field in pairs)))
        return None

    names = {doc["id"]: doc["name"] for doc in docs}
    doc_ids = list(names)
    gaps = [gap["id"] for gap in graph["gaps"]]
    unverified = [fact for fact in graph["facts"] if fact["status"] not in ("anchored", "confirmed")]
    record("E01", "missing" if gaps or unverified else "ok",
           f"共 {len(facts)} 条提取记录，{len(unverified)} 条待核或有异议，{len(set(gaps))} 页存在辨读或覆盖缺口。",
           gaps + ids(unverified), doc_ids)
    def with_performance():
        for item in performance:
            record(item["rule"],item["status"],item["detail"],item["evidence"],item["scope"])
            for key in ("stage","reinspection","delegations","quality_change","acceptance_authority","acceptance_execution","acceptance_originals",
                        "signer_timing","date_checks","batch_acceptance","effect_review","warranty_check","warranty_payment","warranty_difference",
                        "payment_window","payment_quality","retest_reference","invoice_receipt","payment_change","payment_opinion","acceptance_reservations",
                        "acceptance_comments","contract_comments","stage_payments","payment_acceptance","execution_basis",
                        "equipment_models","inspection_coverage","prior_installment","contract_folios","advance_guarantee"):
                if key in item:
                    findings[-1][key] = item[key]
        return findings

    if profile == PERFORMANCE:
        return with_performance()
    if profile == BANK:
        verified_grants = {unit for finding in performance if finding["rule"]=="H01" and finding["status"]=="ok"
                           for entry in finding.get("delegations", []) if entry["status"]=="ok" for unit in entry["units"]}
        check_transfers(graph, docs, values, record, parsed_date, verified_grants)
        signature = payment_record(graph, findings)
        if payment_lookup is not None:
            attach_history(graph, payment_lookup(signature))
        if "payment_history" in graph:
            check_history(signature, graph["payment_history"], record, doc_ids)
        return with_performance()
    numbers = defaultdict(list)
    amounts_valid = {}
    masked = withheld_invoices(graph)
    for doc in kinds.get("invoice", []):
        partial = [m for m in masked if m["unit"]==doc]
        if partial:
            record("I01","missing","票号引文包含遮盖位或只列尾号，需取得可核对的完整号码。",
                   [m["fact"] for m in partial],[doc])
            continue
        found = values("I01", [(doc, "invoice_id")])
        if found:
            numbers[compact(found[0]["value"])].extend(found)
    if not kinds.get("invoice"):
        record("I01", "missing", "缺少可核发票，无法比较票号。", [], doc_ids)
    identifier = InvoiceIdentities(graph)
    identities = {f["id"]:identifier.describe(f) for group in numbers.values() for f in group}
    for number, group in numbers.items():
        members = [identities[f["id"]] for f in group]
        status,detail = within_case(number,members)
        record("I01",status,detail,ids(group)+[ref for i in members for ref in i["code_refs"]])
    if "prior_invoices" in graph:
        if not numbers and not masked:
            record("I02", "missing", "缺少可比对的本案发票号码。", [], doc_ids)
        else:
            check_invoice_history(graph,record)

    if profile == TRAVEL:
        check_travel(graph, linked, identities, values, record)
        return findings
    support = set()
    if chain:
        support.update((chain["original"],chain["repair"]))
        kinds = {**kinds,"acceptance":[chain["final"]]}
    optional = set(kinds.get("contract_approval",[])+kinds.get("warranty",[])+kinds.get("power_of_attorney",[]))
    for item in performance:
        if item["status"]=="ok":
            support.update(optional.intersection(item["scope"]))
    for item in performance:
        change = item.get("quality_change")
        if change and change["state"] in ("applied","original") and item["status"]=="ok":
            support.update(change["units"])
    titles = [fact for fact in facts.values() if fact["field"] in {*KINDS,"reinspection","remediation"} and fact["status"] in ("anchored", "confirmed")]
    assignment = [doc for kind in KINDS for doc in kinds.get(kind, [])]
    complete = (all(len(kinds.get(kind, [])) == 1 for kind in KINDS) and
                len(assignment) == len(set(assignment)) and set(assignment) == set(doc_ids)-support and not (kinds.get("claim") or kinds.get("bank_receipt")))
    count_text = "、".join(f"{label} {len(kinds.get(kind, []))} 份" for kind, label in KINDS.items())
    record("P01", "ok" if complete else "missing", f"按已核标题识别到{count_text}。"
           + ("结算所据验收单取自已核的最终复验。" if chain else "")
           + ("" if complete else "请核对缺件、多单或未识别资料。"), ids(titles), doc_ids)

    for doc in kinds.get("invoice", []):
        found = values("M01", [(doc, field) for field in ("net", "tax", "total", "currency", "unit")])
        if not found:
            continue
        amounts = [money(fact) for fact in found[:3]]
        if not in_yuan(found[3]) or compact(found[4]["value"]) not in ("元", "人民币元") or None in amounts or any(value < 0 for value in amounts):
            record("M01", "risk", "币种、单位、金额格式或红字方向需人工确认。", ids(found))
            continue
        net, tax, total = amounts
        difference = net + tax - total
        record("M01", "ok" if difference == 0 else "issue",
               f"不含税 {net:,.2f} + 税额 {tax:,.2f} − 价税合计 {total:,.2f} = {difference:,.2f} 元。", ids(found))
        amounts_valid[doc] = difference == 0
    if not kinds.get("invoice"):
        record("M01", "missing", "缺少可归属的发票，价税尚无法复算。", [], doc_ids)

    if not complete:
        multi = False
        if len(kinds.get("contract", [])) == 1 and len(kinds.get("acceptance", [])) == 1 and len(kinds.get("invoice", [])) > 1:
            multi = check_multi_invoice(graph, kinds, linked, identities, amounts_valid, values, record,support)
        for rule in ("P02", "P03", "C01", "M02", "D01", "A01", "S01"):
            if rule == "M02" and multi:
                continue
            record(rule, "missing", "单合同、单发票、单验收单的资料集合尚未建立。", ids(titles), doc_ids)
        return with_performance()

    contract, invoice, acceptance = (kinds[kind][0] for kind in ("contract", "invoice", "acceptance"))
    ordered = [contract, invoice, acceptance]
    matches = {}
    for rule, field in (("P02", "contract_id"), ("P03", "buyer"), ("P03", "seller"), ("S01", "subject")):
        found = values(rule, [(doc, field) for doc in ordered])
        matches[field] = False
        if found:
            matched = len({compact(fact["value"]) for fact in found}) == 1
            matches[field] = matched
            record(rule, "ok" if matched else "risk", FIELDS[field] + "（合同 / 发票 / 验收）：" +
                   " / ".join(fact["value"] for fact in found), ids(found))

    terms = values("C01", [(contract, "payment_term")])
    changed = [fact for fact in facts.values() if fact["field"] == "adjustment"]
    cautions = graph.get("cautions", [])
    full = False
    if terms:
        term = compact(terms[0]["value"]).rstrip("。")
        full = term in FULL_TERMS and not (changed or cautions)
        record("C01", "ok" if full else "risk", "合同记载的结算条件：" + terms[0]["quote"]
               + ("。另有变更或分批结算线索，需核对上下文。" if changed or cautions else ""),
               ids(terms, changed) + [row["page_id"] for row in cautions])

    totals = values("M02", [(doc, field) for field in ("total", "currency", "unit") for doc in ordered])
    if totals:
        amounts = [money(fact) for fact in totals[:3]]
        preconditions = [fact for doc in ordered for field in ("contract_id", "buyer", "seller", "subject")
                         for fact in linked[doc, field]]
        accept = single(acceptance, "acceptance_result")
        accepted_in_full = accept and compact(accept["value"]).rstrip("。") in FULL_ACCEPTANCE
        refs = ids(totals, terms or [], changed, preconditions, linked[acceptance, "acceptance_result"])
        refs.extend(row["page_id"] for row in cautions)
        if not (all(matches.values()) and full and accepted_in_full and
                all(in_yuan(fact) for fact in totals[3:6]) and
                all(compact(fact["value"]) in ("元", "人民币元") for fact in totals[6:]) and None not in amounts and min(amounts) >= 0):
            record("M02", "missing", "合同、主体、标的、金额口径、全额结算或无保留验收的可比条件尚未齐备。", refs)
        else:
            record("M02", "ok" if len(set(amounts)) == 1 else "issue",
                   f"含税金额（元）：合同 {amounts[0]:,.2f}，发票 {amounts[1]:,.2f}，验收 {amounts[2]:,.2f}。", refs)
    dates = values("D01", [(contract, "signed_on"), (invoice, "issued_on"), (acceptance, "accepted_on")])
    if dates:
        signed, issued, accepted = map(parsed_date, dates)
        if None in (signed, issued, accepted):
            record("D01", "risk", "日期格式或日历日期需要核实。", ids(dates))
        else:
            record("D01", "ok" if min(issued, accepted) >= signed else "risk",
                   f"签约 {signed}，开票 {issued}，验收 {accepted}。", ids(dates))
    result = values("A01", [(acceptance, "acceptance_result")])
    if result:
        accepted = compact(result[0]["value"]).rstrip("。") in FULL_ACCEPTANCE
        record("A01", "ok" if accepted else "risk", "验收结论记载为“" + result[0]["value"] + "”。", ids(result))
    return with_performance()


def check_multi_invoice(graph, kinds, linked, identities, amounts_valid, values, record,support):
    contract = kinds["contract"][0]
    acceptance = kinds["acceptance"][0]
    invoices = kinds["invoice"]
    docs = [contract, acceptance, *invoices]
    if len(set(docs)) != len(docs) or set(docs) != {doc["id"] for doc in audit_documents(graph)}-support:
        return False
    pairs = [(doc, field) for field in ("contract_id", "buyer", "seller", "subject", "currency", "unit", "total") for doc in docs]
    facts = values("M02", pairs)
    if not facts:
        return True
    by_field = defaultdict(list)
    for fact in facts:
        by_field[fact["field"]].append(fact)
    unique = all(len({compact(fact["value"]) for fact in by_field[field]}) == 1
                 for field in ("contract_id", "buyer", "seller", "subject"))
    units = all(in_yuan(fact) for fact in by_field["currency"]) and all(
        compact(fact["value"]) in ("元", "人民币元") for fact in by_field["unit"])
    amounts = [money(fact) for fact in by_field["total"]]
    refs = ids(facts, *(linked[doc, "invoice_id"] for doc in invoices)) + [ref for i in identities.values() for ref in i["code_refs"]]
    keys = {identity_key(i) for i in identities.values()}
    if (not unique or not units or None in amounts or min(amounts) < 0 or
            None in keys or len(keys) != len(invoices) or not all(amounts_valid.get(doc) for doc in invoices)):
        record("M02", "missing", "多票汇总缺少一致的关联、币种、计量单位、唯一票号或正确价税数据，暂不累计。", refs)
        return True
    invoiced = sum(amounts[2:])
    detail = f"同合同 {len(invoices)} 张不同标识发票合计 {invoiced:,.2f} 元，合同 {amounts[0]:,.2f} 元，验收 {amounts[1]:,.2f} 元。"
    record("M02", "risk", detail + "请核对分票分摊、付款批次与合同变更。", refs)
    return True


def check_travel(graph, linked, identities, values, record):
    kinds = graph["documents_by_kind"]
    claims, invoices = kinds.get("claim", []), kinds.get("invoice", [])
    docs = [doc["id"] for doc in audit_documents(graph)]
    titles = [fact for fact in graph["facts"] if fact["field"] in ("claim", "invoice") and fact["status"] in ("anchored", "confirmed")]
    valid = len(claims) == 1 and bool(invoices) and len(set(claims + invoices)) == len(docs) == len(claims+invoices)
    valid = valid and not (kinds.get("contract") or kinds.get("acceptance") or kinds.get("bank_receipt"))
    record("T01", "ok" if valid else "missing", f"已识别报销申请 {len(claims)} 份、发票 {len(invoices)} 份，本案共核对 {len(docs)} 份单据范围。",
           ids(titles), docs)
    if not valid:
        for rule in ("T02", "T03", "T04", "T05"):
            record(rule, "missing", "尚未建立单份报销申请与所附发票的资料集合。", ids(titles), docs)
        return
    claim = claims[0]
    listed = linked[claim,"claim_ref"] + linked[claim,"claim_full_ref"]
    pending = [f["id"] for f in graph["facts"] if f.get("unit",f["doc"])==claim and f["field"] in {"claim_ref","claim_full_ref"}
               and f["status"] not in {"confirmed","anchored"}]
    pending += [g["id"] for g in graph["gaps"] if g.get("field") in {"claim_ref","claim_full_ref"}]
    matching,detail = match_claim(listed,identities.values())
    partial = [m for m in graph.get("number_masks",{}).get("facts",[])
               if (m["unit"]==claim and m["field"] in {"claim_ref","claim_full_ref"})
               or (m["unit"] in invoices and m["field"]=="invoice_id")]
    if partial:
        pending.extend(m["fact"] for m in partial)
        detail += "原件只列部分号码，暂缓关联："+"、".join(dict.fromkeys(m["value"] for m in partial))+"。"
    matching = matching and len(identities)==len(invoices) and not pending
    number_refs = ids(listed) + list(identities) + [ref for i in identities.values() for ref in i["code_refs"]] + pending
    record("T02","ok" if matching else "missing",detail,number_refs,docs)
    amount_pairs = [(claim, "claim_total")] + [(doc, "total") for doc in invoices]
    fields = values("T03", amount_pairs + [(doc, field) for field in ("currency", "unit") for doc in docs])
    if fields:
        n_docs = len(docs)
        amounts = [money(fact) for fact in fields[:n_docs]]
        valid = matching and all(in_yuan(fact) for fact in fields[n_docs:2*n_docs]) and all(
            compact(fact["value"]) in ("元", "人民币元") for fact in fields[2*n_docs:]) and None not in amounts and min(amounts) >= 0
        refs = ids(fields) + number_refs
        if valid:
            total = sum(amounts[1:])
            difference = amounts[0] - total
            status = "issue" if difference > 0 else ("risk" if difference < 0 else "ok")
            detail = (f"申请 {amounts[0]:,.2f} 元，已关联发票合计 {total:,.2f} 元，"
                      f"申请与凭证差额 {difference:,.2f} 元。")
            if difference < 0:
                detail += "申请低于票面金额，请核对个人承担、费用分摊或部分报销记录。"
            record("T03", status, detail, refs)
        else:
            reason = "票号含遮盖位或只列尾号，待核对完整号码后再比较申请与附件金额。" if partial else "票号、币种、金额单位、负数方向或金额格式不满足可比条件。"
            record("T03", "missing", reason, refs, docs)
    trip = values("T04", [(claim, "trip_start"), (claim,"trip_end")])
    for doc in invoices:
        incurred = values("T04", [(doc, "service_on")])
        if trip and incurred:
            start, end, incurred_on = map(parsed_date, trip + incurred)
            if None in (start, end, incurred_on) or start > end:
                record("T04", "risk", "行程起止或费用发生日期无效，需核实。", ids(trip, incurred))
            else:
                record("T04", "ok" if start <= incurred_on <= end else "risk",
                       f"申报行程 {start} 至 {end}，此笔费用发生于 {incurred_on}。", ids(trip, incurred))
        people = values("T05", [(claim,"traveler"), (doc,"traveler")])
        if people:
            same = compact(people[0]["value"]) == compact(people[1]["value"])
            record("T05", "ok" if same else "risk", "申请与票据所列人员：" +
                   " / ".join(fact["value"] for fact in people), ids(people))


def additional(graph, proposals):
    facts = {fact["id"]: fact for fact in graph["facts"]}
    candidates, subject_paths = expert_candidates(graph)
    eligible = {fact["id"] for fact in candidates}
    findings, invalid = [], 0
    seen = set()
    for item in proposals:
        field, procedure = SIGNALS[item["procedure"]]
        refs = list(dict.fromkeys(item["facts"]))
        if not refs or any(ref not in eligible or facts[ref]["field"] != field for ref in refs):
            invalid += 1
            continue
        if item["procedure"] == "subject_scope" and (len({subject_paths[ref][0] for ref in refs}) != 1 or
                len({subject_paths[ref][1] for ref in refs}) < 2):
            invalid += 1
            continue
        signature = (item["procedure"], tuple(sorted(refs)))
        if signature not in seen:
            seen.add(signature)
            findings.append({"id": f"X01-{len(findings)+1}", "rule": "X01", "version": RULE_VERSION,
                             "title": "专家建议追加核对", "basis": CATALOG["X01"][1], "status": "risk",
                             "detail": procedure, "evidence": refs, "scope": []})
    if invalid:
        findings.append({"id": "X01-invalid", "rule": "X01", "version": RULE_VERSION, "title": "专家引用待核",
                         "basis": CATALOG["X01"][1], "status": "missing", "detail":
                         f"{invalid} 条建议引用与本案证据不匹配，已隔离。请核阅模型调用记录。",
                         "evidence": [], "scope": [doc["id"] for doc in graph["documents"]]})
    return findings
