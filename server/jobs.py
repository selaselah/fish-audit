import fcntl
import logging
import threading

from calculations import FORMAT, normalized
from capacity import job_scope
from config import CaseError, MAX_PAGES, RECHECK_EVIDENCE, SERVER
from controls import additional, conclusion, execute, VERSION
from acceptance_authority import CLAUSE as ACCEPTANCE_CLAUSE, mentions as mentions_acceptance_clause
from delivery_batches import HINT as BATCH_HINT
from contract_changes import LABELS as ADDENDUM_FIELDS, SIGNAL as CHANGE_MENTION
from documents import digest, prepare
from graph import attach_prior_invoices, build_graph, heading_candidates, invoice_number_edges, link_procedures
from model import AUDIT, EXTRACT, VISUAL_CHECK, attach_check, audit_graph, extract_page
from policy import link_sources
from quality_labels import proposed as quality_candidates
from storage import encode


METHODS = {name: (SERVER / name).read_bytes() for name in
           ("acceptance_authority.py", "acceptance_reservations.py", "calculations.py", "capacity.py", "cn_workdays.py", "conclusions.py", "config.py", "contract_changes.py", "contract_effect.py", "controls.py", "delegation.py", "delivery_batches.py", "documents.py", "equipment_exchanges.py", "equipment_models.py", "field_receipts.py", "field_sources.py", "graph.py", "installments.py", "invoice_approval.py", "invoice_comparison.py", "invoice_history.py", "invoice_identity.py", "invoice_masks.py", "invoice_proof.py", "jobs.py", "model.py", "payment_checks.py", "payment_history.py", "payment_index.py", "payment_notes.py", "payment_reference.py", "payment_visibility.py", "payment_windows.py", "peer_review.py", "performance.py", "performance_versions.py", "policy.py", "protocol.py", "stage_payments.py", "quality_labels.py", "quality_references.py", "receipt_packets.py", "reinspection.py", "storage.py", "supplements.py", "transfers.py", "warranty_terms.py", "work_progress.py")}
CODE_DIGESTS = {name: digest(source) for name, source in METHODS.items()}


def refresh_addendum_layout(store, case_id, docs, pages):
    legacy = {p["doc"] for p in pages if (p.get("layer") or {}).get("type")=="text" and "clause_text_only" not in p["layer"]}
    if not legacy:
        return
    if not any(any(f["field"] in ("contract","warranty") for f in p["extraction"]["output"]["facts"]) or CHANGE_MENTION.search(normalized(p["text"])) or BATCH_HINT.search(normalized(p["text"])) or any(mentions_acceptance_clause(line) for line in p["text"].splitlines()) or
               any(f["field"] in ADDENDUM_FIELDS or f["field"] in ("contract_addendum",ACCEPTANCE_CLAUSE) or BATCH_HINT.search(normalized(f["quote"])) or mentions_acceptance_clause(f["quote"]) or CHANGE_MENTION.search(normalized(f["quote"]))
                   for f in p["extraction"]["output"]["facts"]) for p in pages):
        return
    for doc in docs:
        if doc["id"] not in legacy:
            continue
        existing = [p for p in pages if p["doc"]==doc["id"]]
        original = store.files/case_id/doc["id"]/("original"+doc["ext"])
        try:
            current = prepare(original,len(existing),save_images=False)
        except CaseError:
            # The issued page remains the source. Unknown layout already requires full-page review.
            continue
        if len(current)!=len(existing) or any(
                any(new[k]!=old[k] for k in ("number","sha256","text")) or
                any(new["layer"][k]!=old["layer"][k] for k in ("type","lines")) for new,old in zip(current,existing)):
            continue
        store.add_layers(case_id,doc["id"],current)
        for old,new in zip(existing,current):
            old["layer"] = new["layer"]


class Worker:
    def __init__(self, store, extractor=extract_page, auditor=audit_graph, checker=attach_check):
        self.store = store
        self.extract = extractor
        self.audit = auditor
        self.check = checker
        self.wakeup = threading.Event()
        self.lock = None
        self.thread = None

    def start(self):
        self.lock = (self.store.root / "worker.lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self.lock.close()
            raise RuntimeError("此资料目录已有一个服务进程正在工作。") from error
        with self.store.background_writes():
            self.store.recover()
        self.thread = threading.Thread(target=self.loop, daemon=True, name="case-worker")
        self.thread.start()

    def loop(self):
        with self.store.background_writes():
            while True:
                case_id = self.store.claim()
                if not case_id:
                    self.wakeup.wait(3)
                    self.wakeup.clear()
                    continue
                try:
                    self.run(case_id)
                except CaseError as error:
                    self.store.fail(case_id, str(error))
                except Exception as error:
                    logging.error("Worker failed for %s (%s)", case_id, type(error).__name__)
                    self.store.fail(case_id, "处理遇到内部错误，已保存已完成的检查点。")

    def run(self, case_id):
        with job_scope(self.store, case_id):
            self.process(case_id)

    def process(self, case_id):
        store = self.store
        case = store.detail(case_id)
        profile = case["profile"]
        folder = store.files / case_id
        docs = store.documents(case_id)
        old_layers = {p["doc"] for p in store.pages(case_id) if p["layer"] is None}
        page_count = 0
        for index, doc in enumerate(docs):
            source = folder / doc["id"] / ("original" + doc["ext"])
            store.progress(case_id, "prepare", 3 + 13 * index // len(docs), f"核对原件并分页（{index+1}/{len(docs)}）· {doc['name']}",
                           (doc["id"], None, "prepare"))
            if not source.is_file() or digest(source.read_bytes()) != doc["sha256"]:
                raise CaseError("原件缺失或摘要与提交时不一致，已停止计算。")
            if not doc["pages"]:
                pages = prepare(source, MAX_PAGES - page_count)
                store.put_pages(case_id, doc["id"], pages)
                doc["pages"] = len(pages)
            elif doc["id"] in old_layers:
                new_pages = prepare(source, MAX_PAGES - page_count, save_images=False)
                if len(new_pages) != doc["pages"]:
                    raise CaseError("新分页页数与旧底稿不一致，请新建审计。")
                store.add_layers(case_id, doc["id"], new_pages)
            page_count += doc["pages"]
        names = {doc["id"]: doc["name"] for doc in docs}
        pages = store.pages(case_id)
        for index, page in enumerate(pages):
            path = folder / page["doc"] / f"{page['number']}.jpg"
            if not path.is_file() or digest(path.read_bytes()) != page["sha256"]:
                store.progress(case_id, "extract", 18 + 54 * index // page_count, "校验已分页的原页图。",
                               (page["doc"], page["number"], "integrity"))
                raise CaseError("页图缺失或摘要与分页记录不一致，已停止计算。")
            trace = page["extraction"]
            if trace is None:
                store.progress(case_id, "extract", 18 + 54 * index // page_count,
                               f"多模态读取第 {index+1}/{page_count} 页 · {names[page['doc']]} 第 {page['number']} 页",
                               (page["doc"], page["number"], "read"))
                _, trace = self.extract(path)
                store.save_extraction(case_id, page, trace)
                page["extraction"] = trace
            candidates = heading_candidates(page)+quality_candidates(page) if RECHECK_EVIDENCE and not trace.get("check") else []
            if RECHECK_EVIDENCE and (trace["output"]["facts"] or candidates) and not trace.get("check"):
                store.progress(case_id, "extract", 18 + 54 * index // page_count, f"第 {index+1}/{page_count} 页逐字段视觉复检。",
                               (page["doc"], page["number"], "check"))
                trace["native_candidates"] = candidates
                self.check(path, trace)
                trace.pop("native_candidates", None)
                store.save_check(case_id, page, trace["check"])
        store.progress(case_id, "graph", 74, f"已读取 {page_count} 页，正在校验引文并建立关系。")
        refresh_addendum_layout(store,case_id,docs,pages)
        graph = build_graph(docs, pages, store.attestations(case_id), store.amendments(case_id))
        store.check_graph_field_history(case_id,case["rev"]+1,graph)
        graph["profile"] = profile
        keys = {edge["to"] for edge in invoice_number_edges(graph)}
        attach_prior_invoices(graph, store.prior_invoices(case_id, sorted(keys)))
        store.progress(case_id, "controls", 82, f"图谱含 {len(graph['edges'])} 条关系，正在执行所选范围的检查程序。")
        findings = execute(graph, profile, lambda signature: store.payment_history(case_id, signature))
        store.progress(case_id, "expert", 91, "专家代理正在核阅证据关系与规则结果。")
        proposals, trace = self.audit(graph, findings)
        findings += additional(graph, proposals)
        result = conclusion(findings)
        traces = [{"doc": page["doc"], "page": page["number"], "page_sha256": page["sha256"],
                   "clause_text_only":(page.get("layer") or {}).get("clause_text_only") is True,
                   **page["extraction"]} for page in pages]
        instructions = {digest(prompt.encode()): prompt for prompt in (EXTRACT, AUDIT, VISUAL_CHECK)}
        all_calls = [*traces, trace, *(item["check"] for item in traces if "check" in item)]
        for call in all_calls:
            instruction = call.pop("instruction", None)
            if instruction:
                instructions[digest(instruction.encode())] = instruction
        used = {call.get("prompt_sha256") for call in all_calls}
        calls = {"pages": traces, "expert": trace, "instructions": {key: value for key, value in instructions.items() if key in used}}
        link_procedures(graph, findings, calls)
        link_sources(graph)
        policy = {**VERSION, "profile": profile, "code_sha256": CODE_DIGESTS, "archived_methods": True, "calculations": FORMAT}
        report = {"case_id": case_id, "policy": policy, "graph": graph, "findings": findings,
                  "result": result, "calls": calls}
        supplement = store.supplement_record(report)
        if supplement:
            report["supplement"] = supplement
        store.save_report(case_id, report, digest(encode(report).encode()), METHODS)
