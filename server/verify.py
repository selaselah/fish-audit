import argparse
import base64
import hashlib
import json
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from calculations import CalculationEvidence, SUPPORTED, normalized
from conclusions import verify_result
from field_receipts import verify_field_sources
from invoice_approval import FORMAT as INVOICE_APPROVAL_FORMAT, LEGACY_FORMAT as LEGACY_APPROVAL, PROFILES as INVOICE_PROFILES, validate as validate_invoice_approval
from invoice_comparison import FORMAT as INVOICE_LOOKUP, archived_identity, check_history as check_invoice_history, code_relations, lookup_numbers, screen
from invoice_identity import FORMAT as INVOICE_IDENTITY_FORMAT, InvoiceIdentities, identity_relations, printed_claim_pair
from invoice_masks import FIELDS as NUMBER_FIELDS, FORMAT as MASK_FORMAT, verify_masks, withheld_invoices
from invoice_proof import FORMAT as INVOICE_SOURCE_FORMAT, invoice_number_edges, source_record as invoice_source_record
from payment_checks import FORMAT as PAYMENT_CHECKS, comparison_refs, verify_findings as verify_payment_findings
from payment_history import cited_facts, comparable_record, payment_record
from payment_notes import note_refs
from payment_reference import LEGACY_FORMAT as FIRST_REFERENCE_FORMAT, SUPPORTED as REFERENCE_FORMATS, check as check_references, issued_format
from peer_review import journal_decision, verify_referrals, verify_review
from performance import LABELS as PERFORMANCE_FIELDS, verify_findings as verify_performance
from performance_versions import DATE_FORMATS
from quality_labels import verify_report as verify_quality_numbers
from quality_references import verify_report as verify_quality_references
from acceptance_authority import verify_sources as verify_acceptance_authority
import payment_execution
import advance_guarantee
from equipment_models import REVIEW_SINCE as MODEL_REVIEW_SINCE, source_kind as model_source_kind, verify as verify_equipment_models
from stage_payments import verify as verify_stage_payments
from receipt_packets import verify_sources as verify_receipt_packets
from delivery_batches import verify_sources as verify_delivery_batches
from contract_effect import verify as verify_contract_effect
from pdf_execution import verify as verify_pdf_execution
from acceptance_execution import verify as verify_acceptance_pdf
from acceptance_originals import verify as verify_acceptance_originals
from addendum_originals import verify as verify_addendum_originals
from addendum_execution import verify as verify_addendum_pdf
from mandate_execution import verify as verify_mandate_pdf
from mandate_originals import verify as verify_mandate_originals
from supplier_pages import verify as verify_supplier_pages
from acceptance_comments import verify as verify_word_reviews
from contract_comments import verify as verify_contract_reviews
from warranty_terms import verify as verify_warranty
from payment_windows import verify as verify_payment_windows
from acceptance_reservations import verify as verify_reservations
from inspection_coverage import verify as verify_inspection
from payment_acceptance import verify as verify_payment_acceptance
from prior_installment import verify as verify_prior_installment
from payment_releases import verify as verify_payment_releases
import release_execution
import warranty_execution
import warranty_dates
import payment_quality
import retest_reference
import inspection_use
import party_readings
import board_execution
from invoice_conditions import verify as verify_invoice_conditions
from repair_completion import verify as verify_repair_completion
from contract_folios import verify as verify_contract_folios
from reinspection_wait import verify as verify_reinspection_wait
from contract_changes import verify_sources as verify_addendum_sources
from delegation import verify_sources as verify_delegation_sources
from protocol import canonical, response_request
from rule_replay import check_receipt, replay_from_git, replay_installed
from supplements import compare_return


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_request(trace, instructions, page_image=None):
    if "request_format" not in trace:
        return
    require(trace["request_format"] == "responses-json-v1", "未知的模型请求格式")
    prompt = instructions.get(trace["prompt_sha256"])
    require(prompt and sha(prompt.encode()) == trace["prompt_sha256"], "无法还原模型指令")
    content = []
    if page_image is not None:
        image = base64.b64encode(page_image).decode("ascii")
        content.append({"type": "input_image", "image_url": "data:image/jpeg;base64," + image, "detail": "high"})
    if "input" in trace:
        content.append({"type": "input_text", "text": canonical(trace["input"])})
    body = response_request(trace["requested_model"], prompt, content, trace["schema"], trace["schema_name"], trace["max_output_tokens"])
    require(sha(body) == trace["request_sha256"], "模型请求与归档的输入、指令或输出约束不符")


def replay_rules(report):
    outcome = replay_installed(report)
    require(outcome["state"]=="verified",outcome.get("message","本机程序复算结果与底稿不符。"))


def verify_signed_invoices(bundle, hashes, report, journal, revision, nodes, approval=None):
    graph = report["graph"]
    current_keys = {e["to"] for e in invoice_number_edges(graph)}
    history_edges = {(e["from"],e["to"]) for e in graph["edges"] if e["type"]=="archived_invoice" and e["evidence"]==[e["from"]]}
    if approval is None:
        created = datetime.fromisoformat(next(r["created"] for r in journal["revisions"] if r["rev"]==revision))
        matches = graph.get("prior_invoices",[])
        require(history_edges == {(m["id"],m["number_key"]) for m in matches},"历史票号清单与跨案图谱关系不符")
    else:
        matches = approval["screened"]
        created = datetime.fromisoformat(approval["signed_at"])
    require(len(matches)==len({m["id"] for m in matches}),"同一历史票号引文重复")
    combined = graph.get("invoice_lookup")==INVOICE_LOOKUP
    if combined:
        require(screen(lookup_numbers(graph),matches)==matches,"签收票号的同号候选分类不符")
        if approval is None:
            code_nodes,code_edges = code_relations(matches)
            require(code_nodes==[n for n in graph["nodes"] if n["type"]=="archived_code"] and
                    code_edges==[e for e in graph["edges"] if e["type"]=="supports_invoice_code"],"历史发票代码的证据关系不符")
            if report["policy"]["profile"] in INVOICE_PROFILES and (lookup_numbers(graph) or withheld_invoices(graph)):
                expected=[]
                def record(rule,status,detail,refs,*,invoice_lookup):
                    expected.append((status,detail,list(dict.fromkeys(refs)),invoice_lookup))
                check_invoice_history(graph,record)
                actual=[(f["status"],f["detail"],f["evidence"],f.get("invoice_lookup")) for f in report["findings"] if f["rule"]=="I02"]
                require(actual==expected,"I02 发现与逐票核对的同号候选、代码或证据不符")
    groups = {}
    for match in matches:
        groups.setdefault((match["case_id"],match["rev"]),[]).append(match)
    for (prior,rev),group in groups.items():
        root = f"prior/{prior}/r{rev}/"
        require(root+"report.json" in hashes and root+"signoff.json" in hashes, "历史票号缺少签收底稿或人工决定")
        archived = json.loads(bundle.read(root+"report.json"))
        signoff = json.loads(bundle.read(root+"signoff.json"))
        signed_at = datetime.fromisoformat(signoff["time"])
        require(archived["case_id"] == signoff["case_id"] == prior != report["case_id"] and signoff["rev"] == rev
                and signoff["workspace"] == journal["workspace"] and signoff["decision"] in {"approve","return","escalate"}
                and signed_at.tzinfo and signed_at <= created, "历史票号签收的企业、版本、决定或时间不符")
        verify_peer_source(bundle,hashes,archived,signoff,root)
        verify_invoice_approval(bundle,hashes,archived,hashes[root+"report.json"],signoff,root)
        selected = {m["fact"] for m in group} | {c["fact"] for m in group for c in m.get("code_evidence",[])}
        verify_field_sources(bundle,hashes,archived,rev,folder=root,pages=root,selected=selected)
        old = archived["graph"]
        identities = InvoiceIdentities(old) if combined else None
        docs = {d["id"]:d for d in old["documents"]}
        facts = {f["id"]:f for f in old["facts"]}
        old_nodes = {n["id"]:n for n in old["nodes"]}
        invoices = set(old["documents_by_kind"].get("invoice",[]))
        eligible = {(f,e["from"],e["to"]):("invoice" if e["from"] in invoices else "unclassified")
                    for e in invoice_number_edges(old,include_unclassified=True) for f in e["evidence"]}
        page_texts = {}
        for match in group:
            doc,page,key = match["doc"],match["page"],match["number_key"]
            fact = facts[match["fact"]]
            ref = root+match["fact"]
            require(match["id"]==ref and key in current_keys and
                    (approval is not None or nodes.get(ref)=={**match,"type":"archived_observation","label":match["title"]})
                    and match["document_kind"] in {"invoice","unclassified"}
                    and eligible.get((fact["id"],fact.get("unit",doc),key))==match["document_kind"],
                    "同票引用与本案、历史单据归属或编号不符")
            require(match["report_hash"]==hashes[root+"report.json"] and match["signoff_hash"]==hashes[root+"signoff.json"]
                    and match["decision"]==signoff["decision"] and match["title"]==signoff["title"]
                    and match.get("peer_source_rev")==archived.get("peer_review",{}).get("source_rev"),
                    "历史票号所据的底稿或签收意见不符")
            prefix = f"{root}{doc}/{page}"
            node = old_nodes[f"{doc}/p{page}"]
            require((doc,page,match["quote"])==(fact["doc"],fact["page"],fact["quote"])
                    and hashes.get(root+"originals/"+doc+docs[doc]["ext"])==fact["source_sha256"]==match["source_hash"]==docs[doc]["sha256"]==old_nodes[doc]["sha256"]
                    and hashes.get(prefix+".jpg")==fact["page_sha256"]==match["page_hash"]==node["sha256"]
                    and prefix+".txt" in hashes, "同票原件、原页或票号引文不符")
            if prefix not in page_texts:
                page_texts[prefix] = bundle.read(prefix+".txt").decode()
            source = invoice_source_record(fact,node,page_texts[prefix],key,signoff["time"])
            require(match.get("source")==source and bool(match.get("checked_field"))==(source["basis"]=="field_check"),
                    "历史票号的原文定位或人工核图依据不符")
            if combined:
                archived_code = archived_identity(identities.describe(fact),fact,facts,node,page_texts[prefix],signoff)
                require(all(match.get(k)==v for k,v in archived_code.items()),"历史发票代码或组合标识与签收原页不符")


def verify_invoice_approval(bundle, hashes, report, checksum, signoff, root=""):
    path = root+"approval/invoices.json"
    require(hashes.get(path)==signoff.get("invoice_check_hash"), "同票检查回执与签收时留存的摘要不符")
    return validate_invoice_approval(report,checksum,signoff,bundle.read(path) if path in hashes else None)


def verify_payment_history(bundle, hashes, report, journal, *, issued_at=None):
    graph = report["graph"]
    history = graph["payment_history"]
    current = payment_record(graph,report["findings"])
    as_of,matches = verify_payment_findings(current,history,report["findings"],report["policy"],issued_at=issued_at)
    nodes = {n["id"]:n for n in graph["nodes"]}
    for kind,match in matches:
        prior,rev = match["case_id"],match["rev"]
        require(prior!=report["case_id"],"历史付款归属重复或范围无效")
        root = f"prior/{prior}/r{rev}"
        report_path, signoff_path = root + "/report.json", root + "/signoff.json"
        require(hashes[report_path] == match["report_hash"] and hashes[signoff_path] == match["signoff_hash"], "历史底稿或签收摘要不符")
        previous, signoff = json.loads(bundle.read(report_path)), json.loads(bundle.read(signoff_path))
        verify_peer_source(bundle, hashes, previous, signoff, root+"/")
        verify_field_sources(bundle,hashes,previous,rev,folder=root+"/",pages=root+"/",selected={f["fact"] for f in match["evidence"]})
        require(previous["case_id"] == signoff["case_id"] == prior and signoff["rev"] == rev
                and signoff["workspace"] == journal["workspace"]
                and previous["graph"]["profile"] == graph["profile"], "历史签收归属或核查范围不符")
        old_graph = previous["graph"]
        if report["policy"].get("payment_execution"):
            held = payment_execution.sources(old_graph, lambda d,n: bundle.read(f"{root}/{d}/{n}.txt").decode(), banks_only=True)
            require(not held["units"], "所引历史付款凭证的受理或扣款限定尚未核实")
        old = payment_record(old_graph, previous["findings"])
        marked = None
        version = report["policy"].get("payment_references")
        if version in REFERENCE_FORMATS:
            marked = check_references(old_graph,previous["policy"],
                         lambda doc,page: bundle.read(f"{root}/{doc}/{page}.txt").decode(),compare_as=version)
            old = comparable_record(old_graph,previous["findings"],marked)
        refs = comparison_refs(current,old,kind,match,signoff,as_of,marked=marked)
        require(match["evidence"] == cited_facts(old_graph, prior, rev, refs), "历史凭证逐字引文或取值不符")
        documents = {d["id"]: d for d in old_graph["documents"]}
        facts = {f["id"]: f for f in old_graph["facts"]}
        old_nodes = {n["id"]: n for n in old_graph["nodes"]}
        selected_notes = set(note_refs(marked or []))
        page_calls = {(t["doc"],t["page"]):t for t in previous["calls"]["pages"]}
        texts = {}
        for citation in match["evidence"]:
            doc, page = citation["doc"], citation["page"]
            meta = documents[doc]
            prefix = f"{root}/{doc}/{page}"
            require(nodes[citation["id"]]["type"] == "archived_observation" and
                    hashes[root + "/originals/" + doc + meta["ext"]] == citation["source_sha256"] == meta["sha256"]
                    and hashes[prefix + ".jpg"] == citation["page_sha256"] == old_nodes[f"{doc}/p{page}"]["sha256"],
                    "历史引用缺少对应原件或页图")
            if text_hash := old_nodes[f"{doc}/p{page}"].get("text_sha256"):
                require(hashes[prefix + ".txt"] == text_hash, "历史文字层摘要不符")
            line = facts[citation["fact"]].get("source_line")
            if citation["fact"] in selected_notes:
                verify_transcription(facts[citation["fact"]],page_calls,old_nodes,"流水展示说明",note_policy=previous["policy"])
            if line:
                if prefix not in texts:
                    texts[prefix] = bundle.read(prefix + ".txt").decode().splitlines()
                require(0 < line["number"] <= len(texts[prefix]) and texts[prefix][line["number"]-1] == line["text"],
                        "历史引文与原页文字行不符")


def verify_transcription(fact, page_calls, nodes, subject, *, note_policy=None):
    line = fact.get("source_line")
    if fact["status"]=="anchored":
        require(line and line["rects"] and nodes[f"{fact['doc']}/p{fact['page']}"].get("layer")=="text" and
                normalized(line["text"]).strip("。;；")==normalized(fact["quote"]).strip("。;；") and
                normalized(fact["value"]) in normalized(fact["quote"]),"已定位的"+subject+"与原生文字行不符")
    raw = fact.get("amendment")
    if not raw:
        candidates = page_calls[fact["doc"],fact["page"]]["output"]["facts"]
        index = fact["id"].rsplit("/f",1)[-1]
        require(index.isdecimal() and 1<=int(index)<=len(candidates),subject+"缺少原始抄录记录")
        raw = candidates[int(index)-1]
    expected = "claim_ref" if fact.get("origin")=="printed_claim_pair" else fact["field"]
    if fact.get("origin")=="printed_quality_number":
        expected = fact["model_field"]
    require(raw["field"]==expected and raw["value"].strip()==fact["value"] and
            raw["quote"].strip()==fact["quote"],subject+"与当时模型抄录或人工补正不符")
    if note_policy is not None:
        decision = fact.get("attestation") or {}
        require((fact["status"]=="confirmed")== (decision.get("decision")=="confirm"),subject+"与人工核图决定不符")
        if fact["status"]=="confirmed" and "field_receipts.py" in note_policy.get("code_sha256",{}):
            require(decision.get("source_check"),subject+"缺少当时的人工核图回执")


def verify_workpaper_sources(bundle, hashes, report, page_dir, originals=None,*,submitted=None,signed=None):
    verify_performance(report)
    def page_text(doc, page):
        return bundle.read(f"{page_dir}/{doc}/{page}.txt").decode()
    verify_quality_numbers(report, page_text)
    verify_quality_references(report, page_text)
    verify_delegation_sources(report, page_text)
    verify_addendum_sources(report, page_text)
    verify_acceptance_authority(report,page_text)
    verify_receipt_packets(report,page_text)
    verify_stage_payments(report,page_text)
    verify_equipment_models(report,page_text)
    verify_delivery_batches(report,page_text)
    verify_contract_effect(report,page_text)
    def read_original(doc):
        path = originals[doc["id"]] if originals is not None else "originals/" + doc["id"] + doc["ext"]
        return bundle.read(path)
    try:
        verify_pdf_execution(report, read_original)
        verify_acceptance_pdf(report, read_original)
        verify_addendum_pdf(report, read_original)
        verify_mandate_pdf(report, read_original)
        verify_supplier_pages(report, read_original)
    except ModuleNotFoundError as error:
        raise ValueError("重验 PDF 签署凭证需要安装 server/requirements.txt 中的依赖，请使用服务端虚拟环境运行校验。") from error
    verify_addendum_originals(report, read_original, page_text)
    verify_mandate_originals(report, read_original, page_text)
    reviews = verify_word_reviews(report, read_original, page_text)
    verify_acceptance_originals(report, read_original, page_text, verified_reviews=reviews)
    verify_contract_reviews(report, read_original, page_text)
    verify_warranty(report,page_text,submitted=submitted,signed=signed)
    verify_payment_windows(report,page_text)
    verify_reservations(report,page_text)
    verify_inspection(report,page_text)
    verify_payment_acceptance(report,page_text)
    payment_execution.verify(report,page_text)
    advance_guarantee.verify(report,page_text)
    verify_prior_installment(report,page_text,submitted=submitted,signed=signed)
    verify_payment_releases(report,page_text,submitted=submitted,signed=signed)
    release_execution.verify(report, read_original, page_text)
    warranty_execution.verify(report, read_original, page_text)
    warranty_dates.verify(report, page_text)
    payment_quality.verify(report, page_text)
    retest_reference.verify(report,page_text)
    inspection_use.verify(report,page_text)
    party_readings.verify(report,page_text)
    party_readings.verify_originals(report,read_original)
    board_execution.verify(report, read_original, page_text)
    verify_repair_completion(report,page_text)
    verify_reinspection_wait(report,page_text)
    verify_contract_folios(report,page_text)
    verify_invoice_conditions(report,page_text)
    if "conclusions.py" in report["policy"].get("code_sha256",{}):
        verify_result(report)
    graph = report["graph"]
    nodes = {node["id"]: node for node in graph["nodes"]}
    require(len(nodes) == len(graph["nodes"]), "图节点重复")
    for doc in graph["documents"]:
        path = originals[doc["id"]] if originals is not None else "originals/" + doc["id"] + doc["ext"]
        require(hashes[path] == doc["sha256"] == nodes[doc["id"]]["sha256"], "原件摘要不符")
    for trace in report["calls"]["pages"]:
        doc, page = trace["doc"], trace["page"]
        page_node = nodes[f"{doc}/p{page}"]
        inspected = [*graph.get("quality_addenda",{}).get("pages",[]),*graph.get("acceptance_authority_sources",{}).get("pages",[]),*graph.get("delivery_batch_sources",{}).get("pages",[]),*graph.get("contract_effect_sources",{}).get("pages",[]),*graph.get("warranty_sources",{}).get("pages",[]),*graph.get("payment_window_sources",{}).get("pages",[]),*graph.get("acceptance_reservation_sources",{}).get("pages",[])]
        inspected.extend(graph.get("stage_payment_sources",{}).get("pages",[]))
        inspected.extend(graph.get("payment_release_sources",{}).get("pages",[]))
        inspected.extend(graph.get("repair_completion_sources",{}).get("pages",[]))
        inspected.extend(graph.get("contract_folio_sources",{}).get("pages",[]))
        inspected.extend(graph.get("reinspection_wait_sources",{}).get("pages",[]))
        inspected.extend(graph.get("invoice_receipt_sources",{}).get("pages",[]))
        inspected.extend(graph.get("quality_addenda",{}).get("payments",{}).get("pages",[]))
        inspected.extend(graph.get("prior_installment_sources",{}).get("pages",[]))
        inspected.extend(graph.get(advance_guarantee.KEY,{}).get("pages",[]))
        inspected.extend(graph.get("warranty_sources",{}).get("register_pages",[]))
        inspected.extend(graph.get("payment_acceptance_sources",{}).get("pages",[]))
        inspected.extend(graph.get("acceptance_authority_sources",{}).get("bank_pages",[]))
        inspected.extend(graph.get("inspection_coverage_sources",{}).get("pages",[]))
        inspected.extend(graph.get("equipment_model_sources",{}).get("pages",[]))
        inspected.extend(p for packet in graph.get("receipt_packet_sources",{}).get("packets",[]) for p in packet["pages"])
        if report["policy"].get("quality_addenda") and ("clause_text_only" in trace or
                any(p["doc"]==doc and p["page"]==page for p in inspected)):
            require(isinstance(trace.get("clause_text_only"),bool) and trace["clause_text_only"] is page_node.get("clause_text_only"),
                    "补充协议的页面版式与分页记录不符")
        require(hashes[f"{page_dir}/{doc}/{page}.jpg"] == trace["page_sha256"] == page_node["sha256"], "页图摘要不符")
        if "text_sha256" in page_node:
            require(hashes[f"{page_dir}/{doc}/{page}.txt"] == page_node["text_sha256"], "文字层摘要不符")
        calls = [trace, *([trace["check"]] if trace.get("check") else [])]
        if any(call.get("request_format") for call in calls):
            photo = bundle.read(f"{page_dir}/{doc}/{page}.jpg")
            for call in calls:
                verify_request(call, report["calls"].get("instructions", {}), photo)
    verify_request(report["calls"]["expert"], report["calls"].get("instructions", {}))
    page_checks = {(t["doc"],t["page"]): t.get("check") for t in report["calls"]["pages"]}
    page_calls = {(t["doc"],t["page"]):t for t in report["calls"]["pages"]}
    version = report["policy"].get("payment_references")
    selected_notes = set(note_refs(graph.get("transfer_references",{}).get("facts",[]))) if version in REFERENCE_FORMATS-{FIRST_REFERENCE_FORMAT} else set()
    quality_notes = {note["fact"] for h in graph.get("quality_references", {}).get("holds", [])
                     for note in h["observations"]}
    mandate_images = {(p["doc"],p["page"]) for p in graph.get("delegation_coverage",{}).get("pages",[]) if not p["native"]}
    texts = {}
    performance_refs = {ref for item in report["findings"] if item.get("reinspection") or item.get("delegations") or item.get("quality_change") or item.get("acceptance_authority") for ref in item["evidence"]}
    for fact in graph["facts"]:
        require(fact["source_sha256"] == nodes[fact["doc"]]["sha256"] and
                fact["page_sha256"] == nodes[f"{fact['doc']}/p{fact['page']}"]["sha256"], "取值与来源不符")
        if fact.get("origin") == "verified_printed_heading":
            check = page_checks.get((fact["doc"],fact["page"])) or {}
            key = fact["id"].rsplit("/", 1)[-1]
            candidate = fact.get("original_candidate") or fact
            inputs = [row for row in check.get("input", []) if row["index"] == key]
            votes = [row["support"] for row in check.get("output", {}).get("checks", []) if row["index"] == key]
            require(len(inputs) == 1 and inputs[0]["quote"] == candidate["quote"] and
                    inputs[0]["value"] == candidate["value"] and votes == ["clear"], "印刷标题缺少对应的视觉复检")
        if "unit" in fact:
            section = nodes[fact["unit"]]
            require(section["type"] == "document_section" and section["source"] == fact["doc"]
                    and section["page"] == fact["page"], "合订单据归属与原页不符")
        line = fact.get("source_line")
        if line:
            path = f"{page_dir}/{fact['doc']}/{fact['page']}.txt"
            if path not in texts:
                texts[path] = bundle.read(path).decode().splitlines()
            text = texts[path]
            require(1 <= line["number"] <= len(text) and text[line["number"]-1] == line["text"], "引文定位与原文字层不符")
        invoice_number = report["policy"].get("invoice_number_masks")==MASK_FORMAT and fact["field"] in NUMBER_FIELDS
        if fact["id"] in selected_notes:
            verify_transcription(fact,page_calls,nodes,"流水展示说明",note_policy=report["policy"])
        elif fact["id"] in quality_notes:
            verify_transcription(fact,page_calls,nodes,"验收或整改编号展示说明")
        elif fact["field"]=="other" and (fact["doc"],fact["page"]) in mandate_images:
            verify_transcription(fact,page_calls,nodes,"委托书同页读图引文",note_policy=report["policy"])
        elif invoice_number or (version in REFERENCE_FORMATS and fact["field"]=="transfer_ref"):
            verify_transcription(fact,page_calls,nodes,"票号" if invoice_number else "流水号")
        elif (report["policy"].get("performance_checks") and fact["field"] in PERFORMANCE_FIELDS or
              fact["id"] in performance_refs and fact.get("origin")!="verified_printed_heading"):
            verify_transcription(fact,page_calls,nodes,"履约条款与签认")
            decision = fact.get("attestation") or {}
            require((fact["status"]=="confirmed") == (decision.get("decision")=="confirm"),"履约字段与核图决定不符")
            if fact["status"]=="confirmed":
                require(decision.get("source_check"),"履约字段缺少当时的原页核图回执")
        if fact.get("origin")=="printed_claim_pair" or (fact["field"]=="claim_full_ref" and not fact.get("amendment")):
            trace = page_calls[fact["doc"],fact["page"]]
            index = fact["id"].rsplit("/f",1)[-1]
            raw = trace["output"]["facts"]
            require(index.isdecimal() and 1<=int(index)<=len(raw),"组合票号缺少原模型候选")
            candidate = raw[int(index)-1]
            require((fact["value"],fact["quote"])==(candidate["value"].strip(),candidate["quote"].strip()),"组合票号与原模型抄录不符")
            if candidate["field"]=="claim_full_ref" and fact.get("origin")!="printed_claim_pair":
                continue
            require(fact.get("origin")=="printed_claim_pair" and line and line.get("rects")
                    and nodes[f"{fact['doc']}/p{fact['page']}"].get("layer")=="text","组合票号的归类记录或原生文字定位不符")
            require(fact["field"]=="claim_full_ref" and fact.get("model_field")==candidate["field"] and
                    printed_claim_pair(candidate,line["text"],trace.get("check"),index),"组合票号与原模型抄录、印刷标签或复检不符")
    for item in graph["edges"]:
        require(item["from"] in nodes and item["to"] in nodes and item["evidence"] and
                set(item["evidence"]) <= nodes.keys(), "图谱存在未登记引用")
    for finding in report["findings"]:
        require(set(finding["evidence"]) <= nodes.keys(), "程序引用不存在")
    if "calculations" in report["policy"]:
        require(report["policy"]["calculations"] in SUPPORTED, "未知的金额复算格式")
        CalculationEvidence(graph).verify(report["findings"])
    for checksum, instruction in report["calls"].get("instructions", {}).items():
        require(sha(instruction.encode()) == checksum, "提示词摘要不符")
    return nodes


def verify_returned_source(bundle, hashes, report, journal):
    snapshot = report["supplement"]
    intake = journal["supplement_of"]
    parent = json.loads(bundle.read("supplement/report.json"))
    signoff = json.loads(bundle.read("supplement/signoff.json"))
    verify_peer_source(bundle, hashes, parent, signoff, "supplement/")
    require(snapshot["parent"] == intake["id"] == parent["case_id"] and snapshot["rev"] == intake["rev"] == signoff["rev"]
            and intake["title"] == signoff["title"] and signoff["workspace"] == journal["workspace"]
            and datetime.fromisoformat(signoff["time"]) <= datetime.fromisoformat(journal["created"]), "前案归属、签收版本或时间不符")
    require(hashes["supplement/report.json"] == snapshot["report_hash"] and hashes["supplement/signoff.json"] == snapshot["signoff_hash"],
            "前案底稿或签收摘要不符")
    if "parent_hash" in intake or "signoff_hash" in intake:
        require(intake.get("parent_hash") == snapshot["report_hash"] and intake.get("signoff_hash") == snapshot["signoff_hash"],
                "前案底稿或签收摘要与补件受理时不符")
    expected = compare_return(report, parent, signoff, hashes["supplement/report.json"], intake["retained"], intake["note"])
    require(snapshot == expected, "补件资料清单、退回理由或程序对照不符")
    if parent["policy"].get("archived_methods"):
        current_methods = report["policy"].get("code_sha256", {}) if report["policy"].get("archived_methods") else {}
        for name, checksum in parent["policy"]["code_sha256"].items():
            folder = "methods/" if current_methods.get(name) == checksum else "supplement/methods/"
            require(hashes[folder+name] == checksum, "前案执行程序与留存的源码不符")
    retained = {row["parent_doc"]: row["doc"] for row in intake["retained"]}
    originals = {}
    for doc in parent["graph"]["documents"]:
        old = doc["id"]
        prefix = "originals/" + retained[old] if old in retained else "supplement/originals/" + old
        originals[old] = prefix + doc["ext"]
    verify_workpaper_sources(bundle, hashes, parent, "supplement/pages", originals,signed=signoff["time"])
    verify_field_sources(bundle,hashes,parent,snapshot["rev"],folder="supplement/",pages="supplement/pages/",originals=originals)


def verify_peer_source(bundle, hashes, report, signoff, folder=""):
    peer = report.get("peer_review")
    if peer:
        source, referral = folder+"review/source-report.json", folder+"review/referral.json"
        require(hashes.get(source) == peer["source_hash"] and hashes.get(referral) == peer["referral_hash"],
                "缺少复核所依据的原版底稿或转交签收存证")
        verify_review(report, bundle.read(source), json.loads(bundle.read(referral)), signoff)


def render_addendum_sources(bundle, report, nodes):
    graph = report["graph"]
    ledger = graph.get("quality_addenda",{})
    selected = {p["doc"] for key in ("pages","signals","limited_numbers") for p in ledger.get(key,[])}
    selected.update(p["doc"] for p in graph.get("acceptance_authority_sources",{}).get("pages",[]))
    selected.update(p["doc"] for p in graph.get("acceptance_authority_sources",{}).get("bank_pages",[]))
    selected.update(p["doc"] for p in graph.get("stage_payment_sources",{}).get("pages",[]))
    selected.update(p["doc"] for p in graph.get("prior_installment_sources",{}).get("pages",[]))
    selected.update(p["doc"] for p in graph.get(advance_guarantee.KEY,{}).get("pages",[]))
    if any(f.get("advance_guarantee",{}).get("period") or f.get("warranty_difference") for f in report["findings"]):
        selected.update(d["id"] for d in graph["documents"])
    selected.update(p["doc"] for p in graph.get("contract_folio_sources",{}).get("pages",[]))
    selected.update(p["doc"] for p in graph.get("reinspection_wait_sources",{}).get("pages",[]))
    selected.update(p["doc"] for p in graph.get("payment_acceptance_sources",{}).get("pages",[]))
    selected.update(r["doc"] for r in graph.get(retest_reference.KEY,{}).get("rows",[]))
    selected.update(r["doc"] for r in graph.get(inspection_use.KEY,{}).get("rows",[]))
    selected.update(p["doc"] for p in graph.get(inspection_use.KEY,{}).get("approvals",[]))
    selected.update(r["doc"] for r in graph.get(party_readings.KEY,{}).get("rows",[]))
    for key in ("acceptance_pdf_sources", "acceptance_original_sources", "addendum_pdf_sources", "addendum_original_sources", "mandate_pdf_sources", "mandate_original_sources", release_execution.PDF, release_execution.NATIVE, warranty_execution.PDF, warranty_execution.NATIVE, board_execution.PDF, board_execution.NATIVE):
        selected.update(r["doc"] for r in graph.get(key,{}).get("records",[]))
    selected.update(p["doc"] for p in graph.get("inspection_coverage_sources",{}).get("pages",[]))
    selected.update(p["doc"] for p in graph.get("equipment_model_sources",{}).get("pages",[]))
    selected.update(p["doc"] for p in graph.get("receipt_packet_sources",{}).get("packets",[]))
    units = {d["id"]:d.get("source",d["id"]) for d in graph.get("audit_documents",graph["documents"])}
    selected.update(units[u] for f in report["findings"] if f.get("quality_change") or f.get("acceptance_authority") for u in f["scope"])
    if report["policy"].get("performance_checks") in DATE_FORMATS:
        selected.update(units[u] for f in report["findings"] if f["rule"] in ("H01","H02","H04","H05") for u in f["scope"])
    require(selected,"本版底稿没有可按合同日期、补充协议或具名签认程序重新分页的原件。")
    try:
        from documents import CaseError, prepare
    except ImportError as error:
        raise ValueError("重新分页需使用安装了服务端依赖的 Python 环境。") from error
    require(sha(Path(__file__).with_name("documents.py").read_bytes())==report["policy"]["code_sha256"].get("documents.py"),
            "请使用与底稿出具时相同版本的分页程序。")
    count = 0
    for doc in (d for d in graph["documents"] if d["id"] in selected):
        ext, doc_id = doc["ext"], doc["id"]
        require(ext in {".pdf",".doc",".docx",".jpg",".jpeg",".png",".webp",".tif",".tiff",".heic",".heif"},"原件格式不符。")
        pages = [p for p in report["calls"]["pages"] if p["doc"]==doc_id]
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder)/("original"+ext)
            original.write_bytes(bundle.read("originals/"+doc_id+ext))
            try:
                rendered = prepare(original,len(pages),save_images=False)
            except CaseError as error:
                raise ValueError(f"无法重现《{doc['name']}》的原页。{error}") from error
        require(len(rendered)==len(pages),"履约所据原件重新分页后的页数不符")
        for page in rendered:
            number = page["number"]
            node = nodes[f"{doc_id}/p{number}"]
            layout = page["layer"]
            require(page["sha256"]==node["sha256"] and sha(page["text"].encode())==node["text_sha256"]
                    and layout["type"]==node["layer"] and (layout.get("clause_text_only") is True) is node["clause_text_only"],
                    f"《{doc['name']}》第 {number} 页的影像、文字或版式未能从原件重现。")
            trace = next(t for t in pages if t["page"] == number)
            for line_number, rects in trace.get("contract_folio_rects", {}).items():
                require(layout["lines"].get(line_number, []) == rects, "合同付款续页的行坐标未能从原件重现")
            for line_number, rects in trace.get("payment_execution_rects", {}).items():
                require(layout["lines"].get(line_number, []) == rects, "付款凭证说明的行坐标未能从原件重现")
            for line_number, rects in trace.get(inspection_use.RECTS, {}).items():
                require(layout["lines"].get(line_number, []) == rects, "验收单付款用途附注的行坐标未能从原件重现")
            for line_number, rects in trace.get(advance_guarantee.RECTS, {}).items():
                require(layout["lines"].get(line_number, []) == rects, "预付款保函的行坐标未能从原件重现")
            for line_number, rects in trace.get("signer_timing_rects", {}).items():
                require(layout["lines"].get(line_number, []) == rects, "签认与付款时序的行坐标未能从原件重现")
            for fact in graph["facts"]:
                line = fact.get("source_line")
                if fact["doc"]==doc_id and fact["page"]==number and line:
                    require(layout["lines"].get(str(line["number"]),[])==line["rects"],"引文在原页的定位未能重现")
            count += 1
    return count


def verify_model_review_history(report, revision, journal):
    graph = report["graph"]
    if report["policy"].get("version", "") < MODEL_REVIEW_SINCE or not graph.get("equipment_model_sources", {}).get("pages"):
        return
    facts = {fact["id"]: fact for fact in graph["facts"]}
    # An action on R8 first appears in R9. The export journal can also include actions taken after R9.
    latest = {row["fact"]: row for row in sorted(journal["attestations"], key=lambda r: r["seq"]) if row["rev"] < revision}
    def is_model(row):
        return row["field"] == "equipment_model" or model_source_kind(row["quote"])[0] in ("ordered", "received")
    refs = {ref for ref, fact in facts.items() if is_model(fact)}
    refs.update(f"{p['doc']}/p{p['page']}/f{i}" for p in report["calls"]["pages"]
                for i, row in enumerate(p["output"]["facts"], 1) if is_model(row))
    refs.update(row["target"] for row in journal["amendments"] if row["rev"] < revision and is_model(row))
    for ref in refs:
        row = latest.get(ref)
        if ref not in facts:
            require(not row or row["decision"] != "dispute", "底稿遗漏仍有人工异议的型号观察")
            continue
        fact = facts[ref]
        decision = {k:v for k,v in row.items() if k != "seq"} if row else None
        require(fact.get("attestation") == decision and
                (fact["status"] == "disputed") == bool(row and row["decision"] == "dispute"),
                "设备型号的核图状态、意见或经办人与该版出具前的操作记录不符")


def verify(source, strict_rules=False, *, rule_checker=None, render_addenda=False):
    with zipfile.ZipFile(source) as bundle:
        names = bundle.namelist()
        require(len(names) == len(set(names)), "包内出现同名文件")
        manifest = json.loads(bundle.read("manifest.json"))
        entries = manifest["files"]
        expected = {item["path"] for item in entries}
        require(len(entries) == len(expected) and set(names) == expected | {"manifest.json"}, "文件目录不匹配")
        for item in entries:
            with bundle.open(item["path"]) as stream:
                hasher = hashlib.sha256()
                size = 0
                while chunk := stream.read(1024 * 1024):
                    hasher.update(chunk)
                    size += len(chunk)
            require(size == item["bytes"] and hasher.hexdigest() == item["sha256"], "文件校验失败：" + item["path"])
        hashes = {item["path"]: item["sha256"] for item in entries}
        report = json.loads(bundle.read("report.json"))
        journal = json.loads(bundle.read("journal.json"))
        case_id, revision = manifest["case_id"], manifest["revision"]
        require(case_id == report["case_id"] == journal["id"], "底稿归属不一致")
        verify_referrals(journal)
        resolved = next((p for p in journal.get("referrals",[]) if p["resolved_rev"] == revision), None)
        require(bool(resolved) == ("peer_review" in report), "复核版与签收日志的归属不符")
        if resolved:
            peer = report["peer_review"]
            require((resolved["rev"],resolved["report_hash"],resolved["signoff_hash"]) ==
                    (peer["source_rev"],peer["source_hash"],peer["referral_hash"]), "复核所据版本与日志不符")
            verify_peer_source(bundle, hashes, report, journal_decision(journal,revision))
        require(hashes["report.json"] == manifest["report_sha256"] and any(
            item["rev"] == revision and item["hash"] == hashes["report.json"] for item in journal["revisions"]), "底稿版本摘要不符")
        modules = report["policy"].get("code_sha256",{})
        require(report["policy"].get("payment_checks")== (PAYMENT_CHECKS if "payment_checks.py" in modules else None),
                "付款发现核对格式与发行程序不符")
        combined = "invoice_comparison.py" in modules
        require(report["policy"].get("invoice_lookup")==report["graph"].get("invoice_lookup")==(INVOICE_LOOKUP if combined else None),
                "跨案票号比较格式与程序版本不符")
        required_approval = INVOICE_APPROVAL_FORMAT if combined else LEGACY_APPROVAL if "invoice_approval.py" in modules else None
        require(report["policy"].get("invoice_approval")==required_approval,
                "签收时的同票查验格式与发行程序不符")
        approval = None
        if any(d["rev"]==revision for d in journal["decisions"]):
            approval = verify_invoice_approval(bundle,hashes,report,hashes["report.json"],journal_decision(journal,revision))
        else:
            require("approval/invoices.json" not in hashes,"同票检查回执缺少对应的签收决定")
        graph = report["graph"]
        if report["policy"].get("payment_checks")==PAYMENT_CHECKS and graph.get("profile")=="cn-bank-contract-payment/v1":
            require("payment_history" in graph,"本版付款底稿缺少出具时的跨案检索记录")
        if report["policy"].get("archived_methods"):
            for name, expected in report["policy"]["code_sha256"].items():
                require(hashes.get("methods/" + name) == expected, "执行程序版本不符：" + name)
        nodes = verify_workpaper_sources(bundle, hashes, report, "pages",submitted=journal["created"])
        if render_addenda:
            count = render_addendum_sources(bundle,report,nodes)
            print(f"已独立从提交原件重现 {count} 页，页图、文字、引文位置及页面版式一致。")
        reference_format = issued_format(report["policy"])
        require(graph.get("transfer_references",{}).get("format")==report["policy"].get("payment_references")==reference_format,
                "流水完整性核验格式与程序版本不符")
        if reference_format:
            marked = check_references(graph,report["policy"],lambda doc,page: bundle.read(f"pages/{doc}/{page}.txt").decode(),
                                      compare_as=reference_format)
            if marked and graph.get("profile")=="cn-bank-contract-payment/v1":
                dependent = {"B04","B05","B06","B07","B08"}
                require(all(f["status"]=="missing" and not f.get("calculations") for f in report["findings"]
                            if f["rule"] in dependent),"部分流水号被用作已核实付款或金额结论")
        guarded = "invoice_masks.py" in modules
        mask_format = graph.get("number_masks",{}).get("format")
        require(mask_format==report["policy"].get("invoice_number_masks")== (MASK_FORMAT if guarded else None),
                "遮盖票号的核对格式与程序版本不符")
        if guarded:
            verify_masks(graph)
        if "invoice_identity.py" in report["policy"].get("code_sha256",{}):
            require(report["policy"].get("invoice_identity")==graph.get("invoice_identity")==INVOICE_IDENTITY_FORMAT,
                    "发票标识的比对格式与程序版本不符")
            derived,relations = identity_relations(graph)
            require(derived==[n for n in graph["nodes"] if n["type"]=="invoice_identity"]
                    and relations==[e for e in graph["edges"] if e["type"]=="identified_invoice"],"发票标识与原页字段关系不符")
        verify_model_review_history(report, revision, journal)
        verify_field_sources(bundle,hashes,report,revision,journal=journal)
        full_invoices = "invoice_proof.py" in report["policy"].get("code_sha256",{})
        require(report["policy"].get("invoice_sources") == (INVOICE_SOURCE_FORMAT if full_invoices else None),
                "签收票号的存证格式与当版程序不符")
        if full_invoices:
            verify_signed_invoices(bundle,hashes,report,journal,revision,nodes)
            if approval and combined:
                verify_signed_invoices(bundle,hashes,report,journal,revision,nodes,approval)
        for match in ([] if full_invoices else graph.get("prior_invoices", [])):
            path = f"prior/{match['case_id']}/r{match['rev']}/{match['doc']}/{match['page']}.jpg"
            require(hashes[path] == match["page_hash"] and match["id"] in nodes, "历史票号证据不符")
            if "peer_source_rev" in match or match.get("checked_field"):
                root = f"prior/{match['case_id']}/r{match['rev']}/"
                require(hashes.get(root+"report.json") == match["report_hash"], "历史同票复核版摘要不符")
                archived = json.loads(bundle.read(root+"report.json"))
                signoff = json.loads(bundle.read(root+"signoff.json"))
                if "peer_source_rev" in match:
                    require(archived["peer_review"]["source_rev"] == match["peer_source_rev"],"同票复核版所引的转交版本错误")
                require(archived["case_id"] == signoff["case_id"] == match["case_id"] != case_id and signoff["rev"] == match["rev"]
                        and signoff["workspace"] == journal["workspace"] and signoff["decision"] == match["decision"],
                        "同票复核版归属或人工决定不符")
                fact = next((f for f in archived["graph"]["facts"] if f["id"] == match["fact"]), None)
                require(fact and fact["page_sha256"] == match["page_hash"] and fact["quote"] == match["quote"],
                        "同票复核版中的原页或票号引文不符")
                verify_peer_source(bundle, hashes, archived, signoff, root)
                if match.get("checked_field"):
                    require(hashes[root+"signoff.json"] == match["signoff_hash"],"历史票号所据的签收意见摘要不符")
                    require((fact["doc"],fact["page"],fact["source_sha256"],fact["field"]) ==
                            (match["doc"],match["page"],match["source_hash"],"invoice_id") and
                            any(e["type"] == "invoice_id" and e["to"] == match["number_key"] and fact["id"] in e["evidence"]
                                for e in archived["graph"]["edges"]),"历史核图票号与引用的原件、页码或编号不符")
                    require(any((fact.get(key) or {}).get("source_check") for key in ("attestation","amendment")),
                            "历史同票记录缺少所引用的人工核图依据")
                    verify_field_sources(bundle,hashes,archived,match["rev"],folder=root,pages=root,selected={match["fact"]})
        if "payment_history" in graph:
            verify_payment_history(bundle,hashes,report,journal,issued_at=next(r["created"] for r in journal["revisions"] if r["rev"]==revision))
        require(("supplement" in report) == ("supplement_of" in journal), "底稿与受理记录中的补件归属不符")
        if "supplement" in report:
            verify_returned_source(bundle, hashes, report, journal)
        if strict_rules:
            replay_rules(report)
        if rule_checker is not None:
            created = next(item["created"] for item in journal["revisions"] if item["rev"]==revision)
            rule_checker(report,revision,hashes["report.json"],created)
        return case_id, revision, len(entries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="离线核对 Fish Audit 导出包的文件与引用。")
    parser.add_argument("--render-performance","--render-addenda",dest="render_addenda",action="store_true",
                        help="从合同及各版履约程序所据原件重新生成页图，核对文字、引文位置和版式")
    parser.add_argument("bundle", type=Path)
    rules = parser.add_mutually_exclusive_group()
    rules.add_argument("--rules", action="store_true", help="使用与底稿一致的本机程序，从图谱完整复算规则、追加程序及总建议")
    rules.add_argument("--rules-from-git",metavar="本地可信提交或分支",help="从指定提交的本地发布历史中匹配规则源码并复算")
    parser.add_argument("--replay-receipt",metavar="复算记录.json",type=Path,help="核对网页下载的复算记录，默认使用本地 HEAD 的发布历史")
    args = parser.parse_args()
    if args.rules and args.replay_receipt:
        parser.error("复算记录使用本地 Git 发布历史，请选择 --rules-from-git 或省略 --rules。")
    try:
        def check_selected_rules(report,revision,report_hash,created):
            ref = args.rules_from_git or "HEAD"
            if args.rules:
                outcome = replay_installed(report)
            elif args.replay_receipt:
                receipt = json.loads(args.replay_receipt.read_bytes())
                require(isinstance(receipt,dict),"复算记录须为 JSON 对象")
                outcome = check_receipt(receipt,report,revision,report_hash,created,ref)
            else:
                outcome = replay_from_git(report,ref)
            require(outcome["state"]=="verified",outcome.get("message","规则与底稿不符"))
            source = f"本地提交 {outcome['commit']}" if "commit" in outcome else "本机部署目录"
            print(f"规则复算一致，{outcome['finding_count']} 项发现。规则来自{source}，共核对 {len(outcome['modules'])} 份源码。")
        selected = args.rules or args.rules_from_git or args.replay_receipt
        case_id, revision, files = verify(args.bundle,rule_checker=check_selected_rules if selected else None,render_addenda=args.render_addenda)
        print(f"校验成功：{case_id} R{revision}，{files} 个文件。")
    except (KeyError, TypeError, ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, f"校验失败：{error}\n")
