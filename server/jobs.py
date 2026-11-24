import fcntl
import logging
import threading

from calculations import FORMAT
from capacity import job_scope
from config import CaseError, MAX_PAGES, RECHECK_EVIDENCE, SERVER
from controls import additional, conclusion, execute, VERSION
from documents import digest, prepare
from graph import attach_prior_invoices, build_graph, heading_candidates, invoice_number_edges, link_procedures
from model import AUDIT, EXTRACT, VISUAL_CHECK, attach_check, audit_graph, extract_page
from policy import link_sources
from storage import encode


METHODS = {name: (SERVER / name).read_bytes() for name in
           ("calculations.py", "capacity.py", "config.py", "controls.py", "documents.py", "field_receipts.py", "field_sources.py", "graph.py", "installments.py", "jobs.py", "model.py", "payment_history.py", "peer_review.py", "policy.py", "protocol.py", "storage.py", "supplements.py", "transfers.py", "work_progress.py")}
CODE_DIGESTS = {name: digest(source) for name, source in METHODS.items()}


class Worker:
    def __init__(self, store, extractor=extract_page, auditor=audit_graph, checker=attach_check):
        self.store = store
        self.extract = extractor
        self.audit = auditor
        self.check = checker
        self.wakeup = threading.Event()
        self.lock = None

    def start(self):
        self.lock = (self.store.root / "worker.lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self.lock.close()
            raise RuntimeError("此资料目录已有一个服务进程正在工作。") from error
        self.store.recover()
        threading.Thread(target=self.loop, daemon=True, name="case-worker").start()

    def loop(self):
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
        old_layers = {page["doc"] for page in store.pages(case_id) if page["layer"] is None}
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
            candidates = heading_candidates(page) if RECHECK_EVIDENCE and not trace.get("check") else []
            if RECHECK_EVIDENCE and (trace["output"]["facts"] or candidates) and not trace.get("check"):
                store.progress(case_id, "extract", 18 + 54 * index // page_count, f"第 {index+1}/{page_count} 页逐字段视觉复检。",
                               (page["doc"], page["number"], "check"))
                trace["heading_candidates"] = candidates
                self.check(path, trace)
                trace.pop("heading_candidates", None)
                store.save_check(case_id, page, trace["check"])
        store.progress(case_id, "graph", 74, f"已读取 {page_count} 页，正在校验引文并建立关系。")
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
