import argparse
import base64
import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path

from calculations import CalculationEvidence, SUPPORTED, normalized
from field_receipts import verify_field_sources
from installments import LIMIT as INSTALLMENT_LIMIT, calculate as calculate_installments, finding as installment_finding
from invoice_approval import FORMAT as INVOICE_APPROVAL_FORMAT, LEGACY_FORMAT as LEGACY_APPROVAL, PROFILES as INVOICE_PROFILES, validate as validate_invoice_approval
from invoice_comparison import FORMAT as INVOICE_LOOKUP, archived_identity, check_history as check_invoice_history, code_relations, lookup_numbers, screen
from invoice_identity import FORMAT as INVOICE_IDENTITY_FORMAT, InvoiceIdentities, identity_relations, printed_claim_pair
from invoice_masks import FIELDS as NUMBER_FIELDS, FORMAT as MASK_FORMAT, verify_masks, withheld_invoices
from invoice_proof import FORMAT as INVOICE_SOURCE_FORMAT, invoice_number_edges, source_record as invoice_source_record
from payment_history import LIMIT, cited_facts, payment_record
from peer_review import journal_decision, verify_referrals, verify_review
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


def verify_payment_history(bundle, hashes, report, journal):
    graph = report["graph"]
    history = graph["payment_history"]
    as_of = datetime.fromisoformat(history["as_of"])
    require(as_of.tzinfo is not None and set(history["counts"]) == {"same", "full"}, "付款检索时点或范围无效")
    current = payment_record(graph, report["findings"])
    require(all(m["kind"] in {"same","full"} for m in history["matches"]),"历史流水核查的命中类型不符")
    seen = set()
    nodes = {n["id"]: n for n in graph["nodes"]}
    for kind, key in (("same", "reference"), ("full", "settlement")):
        count = history["counts"][kind]
        listed = sum(m["kind"] == kind for m in history["matches"])
        require(type(count) is int and count >= 0 and listed == min(count, LIMIT)
                and (not count or current[key]), "历史付款命中数量或本案依据不符")
    window = history.get("installments")
    if "installments.py" in report["policy"].get("code_sha256",{}):
        require((window is not None) == current["installment"]["requested"],"分期累计检查范围不符")
    matches = [(m["kind"],m) for m in history["matches"]]
    if window is not None:
        count = window["count"]
        require(type(count) is int and count>=0 and len(window["matches"])==min(count,INSTALLMENT_LIMIT)
                and (not count or current["installment"]["key"]),"历史分期底稿的范围或数量不符")
        matches.extend(("installment",m) for m in window["matches"])
    for kind,match in matches:
        prior,rev = match["case_id"],match["rev"]
        marker = (kind=="installment",prior)
        require(kind in {"same","full","installment"} and prior != report["case_id"] and marker not in seen, "历史付款归属重复或范围无效")
        seen.add(marker)
        root = f"prior/{prior}/r{rev}"
        report_path, signoff_path = root + "/report.json", root + "/signoff.json"
        require(hashes[report_path] == match["report_hash"] and hashes[signoff_path] == match["signoff_hash"], "历史底稿或签收摘要不符")
        previous, signoff = json.loads(bundle.read(report_path)), json.loads(bundle.read(signoff_path))
        verify_peer_source(bundle, hashes, previous, signoff, root+"/")
        verify_field_sources(bundle,hashes,previous,rev,folder=root+"/",pages=root+"/",selected={f["fact"] for f in match["evidence"]})
        require(previous["case_id"] == signoff["case_id"] == prior and signoff["rev"] == rev
                and signoff["title"] == match["title"] and signoff["workspace"] == journal["workspace"]
                and previous["graph"]["profile"] == graph["profile"], "历史签收归属或核查范围不符")
        signed_at = datetime.fromisoformat(signoff["time"])
        require(signoff["decision"] == match["decision"] and signoff["decision"] in {"approve", "return", "escalate"}
                and signoff["time"] == match["signed_at"] and signed_at.tzinfo is not None and signed_at <= as_of, "历史人工决定或时点不符")
        old_graph = previous["graph"]
        old = payment_record(old_graph, previous["findings"])
        if kind == "installment":
            source = old["installment"]
            require(signoff["decision"]=="approve" and source["key"]==current["installment"]["key"]
                    and source["entry"]==match["entry"],"历史分期付款主体、原件或金额与已签收底稿不符")
            refs = source["refs"]
        elif kind == "same":
            require(old["reference"] == current["reference"] and old["payer"] == current["payer"], "已签收回单流水或付款户名不符")
            refs = old["same_refs"]
        else:
            require(signoff["decision"] == "approve" and old["settlement"] == current["settlement"]
                    and old["reference"] != current["reference"], "历史全额付款口径或成功流水不符")
            refs = old["full_refs"]
        require(match["evidence"] == cited_facts(old_graph, prior, rev, refs), "历史凭证逐字引文或取值不符")
        documents = {d["id"]: d for d in old_graph["documents"]}
        facts = {f["id"]: f for f in old_graph["facts"]}
        old_nodes = {n["id"]: n for n in old_graph["nodes"]}
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
            if line:
                if prefix not in texts:
                    texts[prefix] = bundle.read(prefix + ".txt").decode().splitlines()
                require(0 < line["number"] <= len(texts[prefix]) and texts[prefix][line["number"]-1] == line["text"],
                        "历史引文与原页文字行不符")
    if window is not None:
        basis = current["installment"]
        require(calculate_installments(basis,window)==window["calculation"],"逐笔流水去重、累计或合同差额与原始取数不符")
        status,detail,refs = installment_finding(basis,window,history["as_of"])
        issued = [f for f in report["findings"] if f["rule"]=="B08"]
        require(len(issued)==1 and (issued[0]["status"],issued[0]["detail"],issued[0]["evidence"]) ==
                (status,detail,list(dict.fromkeys(refs))),"分期累计结论或所引证据不符")


def verify_workpaper_sources(bundle, hashes, report, page_dir, originals=None):
    graph = report["graph"]
    nodes = {node["id"]: node for node in graph["nodes"]}
    require(len(nodes) == len(graph["nodes"]), "图节点重复")
    for doc in graph["documents"]:
        path = originals[doc["id"]] if originals is not None else "originals/" + doc["id"] + doc["ext"]
        require(hashes[path] == doc["sha256"] == nodes[doc["id"]]["sha256"], "原件摘要不符")
    for trace in report["calls"]["pages"]:
        doc, page = trace["doc"], trace["page"]
        page_node = nodes[f"{doc}/p{page}"]
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
    texts = {}
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
        if report["policy"].get("invoice_number_masks")==MASK_FORMAT and fact["field"] in NUMBER_FIELDS:
            if fact["status"]=="anchored":
                require(line and line["rects"] and nodes[f"{fact['doc']}/p{fact['page']}"].get("layer")=="text" and
                        normalized(line["text"]).strip("。;；")==normalized(fact["quote"]).strip("。;；") and
                        normalized(fact["value"]) in normalized(fact["quote"]),"已定位的票号与原生文字行不符")
            raw_candidate=fact.get("amendment")
            if not raw_candidate:
                candidates=page_calls[fact["doc"],fact["page"]]["output"]["facts"]
                index=fact["id"].rsplit("/f",1)[-1]
                require(index.isdecimal() and 1<=int(index)<=len(candidates),"票号缺少原始抄录记录")
                raw_candidate=candidates[int(index)-1]
            expected_field="claim_ref" if fact.get("origin")=="printed_claim_pair" else fact["field"]
            require(raw_candidate["field"]==expected_field and raw_candidate["value"].strip()==fact["value"] and
                    raw_candidate["quote"].strip()==fact["quote"],"票号与当时模型抄录或人工补正不符")
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
    verify_workpaper_sources(bundle, hashes, parent, "supplement/pages", originals)
    verify_field_sources(bundle,hashes,parent,snapshot["rev"],folder="supplement/",pages="supplement/pages/",originals=originals)


def verify_peer_source(bundle, hashes, report, signoff, folder=""):
    peer = report.get("peer_review")
    if peer:
        source, referral = folder+"review/source-report.json", folder+"review/referral.json"
        require(hashes.get(source) == peer["source_hash"] and hashes.get(referral) == peer["referral_hash"],
                "缺少复核所依据的原版底稿或转交签收存证")
        verify_review(report, bundle.read(source), json.loads(bundle.read(referral)), signoff)


def verify(source, strict_rules=False, *, rule_checker=None):
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
        if report["policy"].get("archived_methods"):
            for name, expected in report["policy"]["code_sha256"].items():
                require(hashes.get("methods/" + name) == expected, "执行程序版本不符：" + name)
        nodes = verify_workpaper_sources(bundle, hashes, report, "pages")
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
            verify_payment_history(bundle, hashes, report, journal)
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
        case_id, revision, files = verify(args.bundle,rule_checker=check_selected_rules if selected else None)
        print(f"校验成功：{case_id} R{revision}，{files} 个文件。")
    except (KeyError, TypeError, ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, f"校验失败：{error}\n")
