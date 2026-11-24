import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from backup import MARKER
from capacity import admit, install as install_capacity, settings
from config import BANK, CaseError, PROFILE
from field_receipts import field_actions, validate_field_actions
from field_sources import FieldSources, check_archived_files, check_cited_files, source_row
from graph import compact, invoice_number_edges
from installments import LIMIT as INSTALLMENT_LIMIT, calculate as calculate_installments
from invoice_approval import receipt as invoice_approval_receipt, validate as validate_invoice_approval
from invoice_comparison import FORMAT as INVOICE_LOOKUP, actionables, archived_identity, lookup_numbers, screen
from invoice_identity import InvoiceIdentities
from invoice_history import INDEX_FIELDS, InvoiceHistoryChanged, differences as invoice_differences, indexed_invoices
from invoice_proof import source_record as invoice_source_record
from payment_history import LIMIT as PAYMENT_HISTORY_LIMIT, canonical, cited_facts, payment_record
from peer_review import different_reviewers, review_record, valid_findings, verify_review
from supplements import compare_return
from work_progress import checkpoints, install as install_progress, set_activity
from workbench import prepare_index, project


BACKGROUND_WRITER = ContextVar("fish_audit_background_writer",default=None)
TRANSIENT_WRITER_CODES = {getattr(sqlite3,k) for k in ("SQLITE_BUSY","SQLITE_BUSY_RECOVERY","SQLITE_BUSY_TIMEOUT") if hasattr(sqlite3,k)}


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def source_hashes(content, signoff):
    return hashlib.sha256(content).hexdigest(), hashlib.sha256(canonical(signoff)).hexdigest()


def event(db, case_id, stage, message):
    db.execute("INSERT INTO events(case_id,time,stage,message) VALUES(?,?,?,?)",
               (case_id, stamp(), stage, message))


def record_progress(db,case_id,stage,percent,message,activity=None):
    db.execute("UPDATE cases SET stage=?,progress=?,message=?,updated=? WHERE id=?",
               (stage,percent,message,stamp(),case_id))
    set_activity(db,case_id,activity)
    event(db,case_id,stage,message)


def authorize_write(db, workspace, actor, *, review=False):
    if workspace == "local":
        return "admin"
    member = db.execute("SELECT role FROM members WHERE workspace=? AND account=?", (workspace, actor)).fetchone()
    if not member or (review and member["role"] == "employee"):
        raise CaseError("当前账号无权执行此次操作。", 403)
    return member["role"]


def authorize_case_write(db, case_id, actor):
    case = db.execute("SELECT workspace FROM cases WHERE id=?", (case_id,)).fetchone()
    if not case:
        raise CaseError("未找到该审计任务。", 404)
    authorize_write(db, case["workspace"], actor, review=True)
    return case["workspace"]


class Store:
    def __init__(self, root):
        if (root/MARKER).exists():
            raise RuntimeError("资料目录仍在复制中，请使用已完成恢复的目录。")
        self.limits = settings()
        self.root = root
        self.waiting_for_write = threading.Event()
        self.files = root / "cases"
        self.files.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "audit.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cases(
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL,
                    status TEXT NOT NULL, stage TEXT NOT NULL, progress INTEGER NOT NULL, message TEXT NOT NULL,
                    error TEXT, rev INTEGER NOT NULL DEFAULT 0, request_key TEXT UNIQUE, fingerprint TEXT NOT NULL,
                    profile TEXT NOT NULL DEFAULT 'cn-procurement-full-settlement/v1');
                CREATE TABLE IF NOT EXISTS docs(
                    case_id TEXT NOT NULL REFERENCES cases(id), id TEXT NOT NULL, name TEXT NOT NULL,
                    ext TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, pages INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(case_id,id));
                CREATE TABLE IF NOT EXISTS pages(
                    case_id TEXT NOT NULL, doc TEXT NOT NULL, number INTEGER NOT NULL, sha256 TEXT NOT NULL,
                    width INTEGER NOT NULL, height INTEGER NOT NULL, text TEXT NOT NULL, extraction TEXT, layer TEXT,
                    PRIMARY KEY(case_id,doc,number), FOREIGN KEY(case_id,doc) REFERENCES docs(case_id,id));
                CREATE TABLE IF NOT EXISTS events(
                    seq INTEGER PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), time TEXT NOT NULL,
                    stage TEXT NOT NULL, message TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_case ON events(case_id,seq);
                CREATE TABLE IF NOT EXISTS reports(
                    case_id TEXT NOT NULL REFERENCES cases(id), rev INTEGER NOT NULL, created TEXT NOT NULL,
                    hash TEXT NOT NULL, content TEXT NOT NULL, PRIMARY KEY(case_id,rev));
                CREATE TABLE IF NOT EXISTS attestations(
                    seq INTEGER PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), rev INTEGER NOT NULL,
                    fact TEXT NOT NULL, decision TEXT NOT NULL, reviewer TEXT NOT NULL,
                    note TEXT NOT NULL, time TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS signoffs(
                    case_id TEXT NOT NULL, rev INTEGER NOT NULL, decision TEXT NOT NULL, reviewer TEXT NOT NULL,
                    note TEXT NOT NULL, time TEXT NOT NULL, PRIMARY KEY(case_id,rev),
                    FOREIGN KEY(case_id,rev) REFERENCES reports(case_id,rev));
                CREATE TABLE IF NOT EXISTS amendments(
                    seq INTEGER PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), rev INTEGER NOT NULL,
                    target TEXT NOT NULL, doc TEXT NOT NULL, page INTEGER NOT NULL, page_hash TEXT NOT NULL,
                    field TEXT NOT NULL, value TEXT NOT NULL, quote TEXT NOT NULL, region TEXT NOT NULL,
                    reviewer TEXT NOT NULL, note TEXT NOT NULL, time TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS invoice_index(
                    case_id TEXT NOT NULL REFERENCES cases(id), rev INTEGER NOT NULL, doc TEXT NOT NULL,
                    fact TEXT NOT NULL, page INTEGER NOT NULL, number_key TEXT NOT NULL, quote TEXT NOT NULL,
                    source_hash TEXT NOT NULL, page_hash TEXT NOT NULL, document_kind TEXT NOT NULL,
                    PRIMARY KEY(case_id,rev,fact));
                CREATE INDEX IF NOT EXISTS invoice_keys ON invoice_index(number_key);
                CREATE TABLE IF NOT EXISTS method_sources(sha256 TEXT PRIMARY KEY, source BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS case_supplements(
                    child TEXT PRIMARY KEY REFERENCES cases(id), parent TEXT NOT NULL, parent_rev INTEGER NOT NULL,
                    note TEXT NOT NULL, retained TEXT NOT NULL, parent_hash TEXT NOT NULL, signoff_hash TEXT NOT NULL, CHECK(child<>parent),
                    FOREIGN KEY(parent,parent_rev) REFERENCES signoffs(case_id,rev));
                CREATE INDEX IF NOT EXISTS supplements_parent ON case_supplements(parent);
                CREATE TABLE IF NOT EXISTS case_referrals(
                    case_id TEXT NOT NULL, rev INTEGER NOT NULL, report_hash TEXT NOT NULL,
                    signoff_hash TEXT NOT NULL, resolved_rev INTEGER, origin TEXT NOT NULL,
                    PRIMARY KEY(case_id,rev), CHECK(resolved_rev IS NULL OR resolved_rev=rev+1),
                    FOREIGN KEY(case_id,rev) REFERENCES signoffs(case_id,rev),
                    FOREIGN KEY(case_id,resolved_rev) REFERENCES signoffs(case_id,rev));
            """)
            db.execute("BEGIN IMMEDIATE")
            if "layer" not in {row["name"] for row in db.execute("PRAGMA table_info(pages)")}:
                db.execute("ALTER TABLE pages ADD COLUMN layer TEXT")
            if "profile" not in {row["name"] for row in db.execute("PRAGMA table_info(cases)")}:
                db.execute("ALTER TABLE cases ADD COLUMN profile TEXT NOT NULL DEFAULT 'cn-procurement-full-settlement/v1'")
            case_columns = {row["name"] for row in db.execute("PRAGMA table_info(cases)")}
            for column, definition in (("workspace", "TEXT NOT NULL DEFAULT 'local'"), ("submitter", "TEXT"),
                                       ("submitter_name", "TEXT")):
                if column not in case_columns:
                    db.execute(f"ALTER TABLE cases ADD COLUMN {column} {definition}")
            db.execute("CREATE INDEX IF NOT EXISTS cases_space ON cases(workspace,created DESC,id)")
            for table in ("attestations", "amendments", "signoffs"):
                columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
                if "actor" not in columns:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN actor TEXT")
                if table != "signoffs" and "source_check" not in columns:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN source_check TEXT")
                if table == "signoffs":
                    for field in ("invoice_check_hash","invoice_check"):
                        if field not in columns:
                            db.execute(f"ALTER TABLE signoffs ADD COLUMN {field} TEXT")
            db.execute("""CREATE INDEX IF NOT EXISTS checked_fact_versions ON attestations(case_id,fact,rev)
                          WHERE source_check IS NOT NULL""")
            old_referrals = db.execute("""SELECT c.workspace,c.title,s.case_id,s.rev,s.decision,s.reviewer,s.note,s.time,s.actor,r.hash
                    FROM signoffs s JOIN cases c ON c.id=s.case_id JOIN reports r ON r.case_id=s.case_id AND r.rev=s.rev
                    WHERE s.decision='escalate' AND NOT EXISTS(
                        SELECT 1 FROM case_referrals f WHERE f.case_id=s.case_id AND f.rev=s.rev)""").fetchall()
            for row in old_referrals:
                first = dict(row)
                report_hash = first.pop("hash")
                self.record_referral(db, report_hash, first, "migration")
            if db.execute("PRAGMA user_version").fetchone()[0] < 1:
                rows = db.execute("""SELECT c.id,c.rev,r.content FROM cases c
                                  JOIN reports r ON r.case_id=c.id AND r.rev=c.rev""")
                for row in rows:
                    db.executemany("INSERT OR REPLACE INTO invoice_index VALUES(?,?,?,?,?,?,?,?,?,?)",
                                   self.index_rows(row["id"], row["rev"], json.loads(row["content"])))
                db.execute("PRAGMA user_version=1")
            self.fts_enabled = prepare_index(db)
            install_progress(db)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(case_supplements)")}
            for name in ("parent_hash", "signoff_hash"):
                if name not in columns:
                    db.execute(f"ALTER TABLE case_supplements ADD COLUMN {name} TEXT")
            if not {"parent_hash", "signoff_hash"} <= columns:
                rows = db.execute("""SELECT x.child,x.parent,x.parent_rev,json_extract(r.content,'$.supplement.report_hash') AS captured,
                                  json_extract(r.content,'$.supplement.signoff_hash') AS signed FROM case_supplements x
                                  LEFT JOIN reports r ON r.case_id=x.child AND r.rev=1""")
                for row in rows:
                    digests = (row["captured"], row["signed"])
                    if not all(digests):
                        digests = source_hashes(*self.signed_source(db, row["child"], row["parent"], row["parent_rev"]))
                    db.execute("UPDATE case_supplements SET parent_hash=?,signoff_hash=? WHERE child=?", (*digests, row["child"]))
            db.execute("""CREATE TABLE IF NOT EXISTS payment_index(
                case_id TEXT PRIMARY KEY, rev INTEGER NOT NULL, payer TEXT NOT NULL, reference TEXT NOT NULL,
                settlement TEXT, FOREIGN KEY(case_id,rev) REFERENCES reports(case_id,rev))""")
            db.execute("CREATE INDEX IF NOT EXISTS payment_reference ON payment_index(payer,reference)")
            db.execute("CREATE INDEX IF NOT EXISTS payment_settlement ON payment_index(settlement) WHERE settlement IS NOT NULL")
            db.execute("""CREATE TABLE IF NOT EXISTS contract_payments(
                       case_id TEXT PRIMARY KEY, rev INTEGER NOT NULL, contract_key TEXT NOT NULL,
                       FOREIGN KEY(case_id,rev) REFERENCES reports(case_id,rev))""")
            db.execute("CREATE INDEX IF NOT EXISTS contract_payment_key ON contract_payments(contract_key)")
            if db.execute("PRAGMA user_version").fetchone()[0] < 4:
                rows = db.execute("""SELECT c.id,c.rev,r.content,r.hash FROM cases c JOIN reports r ON r.case_id=c.id
                                   AND r.rev=c.rev WHERE c.profile=?""", (BANK,))
                for row in rows:
                    if hashlib.sha256(row["content"].encode()).hexdigest() != row["hash"]:
                        raise CaseError("已有付款底稿摘要不符，无法重建合同付款索引。",409)
                    self.index_payment(db, row["id"], row["rev"], json.loads(row["content"]))
                db.execute("PRAGMA user_version=4")
            install_capacity(db)
        os.chmod(self.path, 0o600)

    @contextmanager
    def background_writes(self):
        token = BACKGROUND_WRITER.set(self)
        try:
            yield
        finally:
            BACKGROUND_WRITER.reset(token)

    def write_boundary(self, operation, *args):
        background = BACKGROUND_WRITER.get() is self
        try:
            while True:
                try:
                    return operation(*args)
                except sqlite3.OperationalError as error:
                    if getattr(error,"sqlite_errorcode",None) not in TRANSIENT_WRITER_CODES:
                        raise
                    if not background:
                        raise CaseError("任务数据库正处理另一笔写入，请稍后重试。",503) from error
                    self.waiting_for_write.set()
                    time.sleep(.1)
        finally:
            if background:
                self.waiting_for_write.clear()

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=12)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                self.write_boundary(db.execute,"BEGIN IMMEDIATE")
            yield db
            if write:
                self.write_boundary(db.commit)
            else:
                db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def create(self, case_id, title, docs, request_key, fingerprint, profile=PROFILE, workspace="local", user=None, supplement=None):
        with self.connect(True) as db:
            now = stamp()
            user = user or {}
            role = authorize_write(db, workspace, user.get("id"))
            if supplement:
                source = self.returned_case(db, supplement["parent"], supplement["rev"], workspace,
                                            user.get("id") if role == "employee" else None)
                if profile != source["profile"]:
                    raise CaseError("补件须沿用前案的审计范围。", 409)
            previous = db.execute("SELECT id,fingerprint FROM cases WHERE request_key=?", (request_key,)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise CaseError("同一提交编号对应了不同资料，请重新提交。",409)
                return previous["id"]
            admit(db, workspace, self.limits, sum(doc["size"] for doc in docs))
            db.execute("""INSERT INTO cases(id,title,created,updated,status,stage,progress,message,request_key,fingerprint,profile,workspace,submitter,submitter_name)
                       VALUES(?,?,?,?,'queued','queued',0,'等待审计',?,?,?,?,?,?)""",
                       (case_id, title, now, now, request_key, fingerprint, profile, workspace,user.get("id"),user.get("name")))
            db.executemany("INSERT INTO docs(case_id,id,name,ext,size,sha256) VALUES(?,?,?,?,?,?)",
                           [(case_id, doc["id"], doc["name"], doc["ext"], doc["size"], doc["sha256"]) for doc in docs])
            if supplement:
                digests = source_hashes(*self.signed_source(db, case_id, supplement["parent"], supplement["rev"]))
                db.execute("""INSERT INTO case_supplements(child,parent,parent_rev,note,retained,parent_hash,signoff_hash)
                              VALUES(?,?,?,?,?,?,?)""", (case_id, supplement["parent"], supplement["rev"], supplement["note"],
                                                        encode(supplement["retained"]), *digests))
            event(db, case_id, "queued", f"收到 {len(docs)} 份原件。")
            return case_id

    def recover(self):
        with self.connect(True) as db:
            rows = db.execute("SELECT id FROM cases WHERE status='running'").fetchall()
            for row in rows:
                db.execute("UPDATE cases SET status='queued',stage='queued',message='服务重启，等待恢复',updated=? WHERE id=?",
                           (stamp(), row["id"]))
                event(db, row["id"], "queued", "服务重启，恢复已保存的分页与模型检查点。")

    def claim(self):
        with self.connect(True) as db:
            row = db.execute("""SELECT c.id,c.workspace FROM cases c LEFT JOIN worker_turn w ON w.workspace=c.workspace
                             WHERE c.status='queued' ORDER BY coalesce(w.turn,0),c.updated,c.id LIMIT 1""").fetchone()
            if row:
                db.execute("""INSERT OR REPLACE INTO worker_turn(workspace,turn)
                           SELECT ?,coalesce(max(turn),0)+1 FROM worker_turn""",(row["workspace"],))
                db.execute("UPDATE cases SET status='running',updated=? WHERE id=?", (stamp(), row["id"]))
                set_activity(db, row["id"], None)
                return row["id"]
        return None

    def progress(self, case_id, stage, percent, message, activity=None):
        with self.connect(True) as db:
            record_progress(db,case_id,stage,percent,message,activity)

    def expert_checkpoint(self,case_id,base_rev,request_hash,validate_trace):
        with self.connect(True) as db:
            row = db.execute("""SELECT e.* FROM expert_checkpoints e JOIN cases c ON c.id=e.case_id
                                WHERE e.case_id=? AND c.status='running' AND c.rev=?""",(case_id,base_rev)).fetchone()
            if not row:
                return None
            message = "专家请求与已保存记录的版本或输入不同，重新调用模型。"
            if row["base_rev"]==base_rev and row["request_hash"]==request_hash:
                try:
                    if not isinstance(row["content"],str) or hashlib.sha256(row["content"].encode()).hexdigest()!=row["sha256"]:
                        raise ValueError("摘要不符")
                    saved = json.loads(row["content"])
                    if saved["case_id"]!=case_id or type(saved["base_rev"]) is not int or saved["base_rev"]!=base_rev:
                        raise ValueError("版本不符")
                    trace = saved["trace"]
                    if not isinstance(trace,dict) or trace["request_sha256"]!=request_hash:
                        raise ValueError("请求不符")
                    validate_trace(trace)
                except (KeyError,TypeError,ValueError):
                    message = "已保存的专家响应未通过完整性检查，重新调用模型。"
                else:
                    record_progress(db,case_id,"expert",97,"本版专家请求与已保存响应匹配，正在恢复底稿。")
                    return trace
            db.execute("DELETE FROM expert_checkpoints WHERE case_id=?",(case_id,))
            event(db,case_id,"expert",message)
            return None

    def save_expert_checkpoint(self,case_id,base_rev,trace):
        content = encode({"case_id":case_id,"base_rev":base_rev,"trace":trace})
        checksum = hashlib.sha256(content.encode()).hexdigest()
        with self.connect(True) as db:
            if not db.execute("SELECT 1 FROM cases WHERE id=? AND rev=? AND status='running'",(case_id,base_rev)).fetchone():
                raise CaseError("专家请求所属的任务版本已变化。",409)
            db.execute("""INSERT OR REPLACE INTO expert_checkpoints(case_id,base_rev,request_hash,saved_at,sha256,content)
                          VALUES(?,?,?,?,?,?)""",(case_id,base_rev,trace["request_sha256"],stamp(),checksum,content))
            record_progress(db,case_id,"expert",96,"已保存专家响应，正在生成本版底稿。")

    def fail(self, case_id, message):
        with self.connect(True) as db:
            db.execute("UPDATE cases SET status='failed',error=?,message=?,updated=? WHERE id=?",
                       (message, "任务中断", stamp(), case_id))
            event(db, case_id, "failed", message)

    def retry(self, case_id, actor=None):
        with self.connect(True) as db:
            workspace = authorize_case_write(db, case_id, actor)
            admit(db, workspace, self.limits)
            if db.execute("""UPDATE cases SET status='queued',stage='queued',progress=0,error=NULL,
                          message='等待重试',updated=? WHERE id=? AND status='failed'""",
                          (stamp(), case_id)).rowcount != 1:
                raise CaseError("只有中断的任务可以重试。", 409)
            event(db, case_id, "queued", "审计人员重新提交任务，沿用已经完成的页面。")

    def documents(self, case_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id,name,ext,size,sha256,pages FROM docs WHERE case_id=? ORDER BY id", (case_id,))]

    def pages(self, case_id):
        with self.connect() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM pages WHERE case_id=? ORDER BY doc,number", (case_id,))]
        for row in rows:
            row["extraction"] = json.loads(row["extraction"]) if row["extraction"] else None
            row["layer"] = json.loads(row["layer"]) if row["layer"] else None
        return rows

    def put_pages(self, case_id, doc, pages):
        with self.connect(True) as db:
            db.executemany("INSERT INTO pages(case_id,doc,number,sha256,width,height,text,layer) VALUES(?,?,?,?,?,?,?,?)",
                           [(case_id, doc, page["number"], page["sha256"], page["width"], page["height"],
                             page["text"], encode(page["layer"])) for page in pages])
            db.execute("UPDATE docs SET pages=? WHERE case_id=? AND id=?", (len(pages), case_id, doc))

    def add_layers(self, case_id, doc, pages):
        with self.connect(True) as db:
            for page in pages:
                result = db.execute("""UPDATE pages SET layer=? WHERE case_id=? AND doc=? AND number=? AND sha256=? AND text=?""",
                                    (encode(page["layer"]), case_id, doc, page["number"], page["sha256"], page["text"]))
                if result.rowcount != 1:
                    raise CaseError("新分页与原页图摘要不一致，请保留原案并新建审计。")

    def save_extraction(self, case_id, page, trace):
        with self.connect(True) as db:
            db.execute("UPDATE pages SET extraction=? WHERE case_id=? AND doc=? AND number=? AND extraction IS NULL",
                       (encode(trace), case_id, page["doc"], page["number"]))

    def save_check(self, case_id, page, check):
        with self.connect(True) as db:
            db.execute("""UPDATE pages SET extraction=json_set(extraction,'$.check',json(?)) WHERE case_id=? AND doc=? AND number=?
                       AND json_extract(extraction,'$.check') IS NULL""",
                       (encode(check), case_id, page["doc"], page["number"]))

    def save_report(self, case_id, report, digest, methods):
        with self.connect(True) as db:
            revision = db.execute("SELECT rev FROM cases WHERE id=?", (case_id,)).fetchone()["rev"] + 1
            now = stamp()
            db.executemany("INSERT OR IGNORE INTO method_sources VALUES(?,?)",
                           [(report["policy"]["code_sha256"][name], contents) for name, contents in methods.items()])
            db.execute("INSERT INTO reports VALUES(?,?,?,?,?)", (case_id, revision, now, digest, encode(report)))
            db.execute("DELETE FROM expert_checkpoints WHERE case_id=? AND base_rev=?",(case_id,revision-1))
            self.index_report(db, case_id, revision, report)
            db.execute("""UPDATE cases SET rev=?,status='ready',stage='ready',progress=100,
                       error=NULL,message='审计底稿已生成，等待人工验收',updated=? WHERE id=?""", (revision, now, case_id))
            event(db, case_id, "ready", f"底稿 R{revision} 已保存，等待人工验收。")

    def index_report(self, db, case_id, revision, report):
        project(db, case_id, revision, report)
        self.index_payment(db, case_id, revision, report)
        db.executemany("INSERT INTO invoice_index VALUES(?,?,?,?,?,?,?,?,?,?)", self.index_rows(case_id, revision, report))

    def method_source(self, checksum):
        with self.connect() as db:
            row = db.execute("SELECT source FROM method_sources WHERE sha256=?", (checksum,)).fetchone()
            if not row:
                raise CaseError("本版本缺少对应的程序源码快照。", 409)
            return row["source"]

    @staticmethod
    def index_rows(case_id, revision, report):
        graph = report["graph"]
        facts = {fact["id"]: fact for fact in graph["facts"]}
        invoices = set(graph["documents_by_kind"].get("invoice", []))
        rows = []
        for edge in invoice_number_edges(graph, include_unclassified=True):
            for key in edge["evidence"]:
                fact = facts[key]
                kind = "invoice" if edge["from"] in invoices else "unclassified"
                rows.append((case_id, revision, fact["doc"], key, fact["page"], edge["to"],
                             fact["quote"], fact["source_sha256"], fact["page_sha256"], kind))
        return rows

    def verify_invoice_sources(self,db,matches,include_identity=True):
        groups = {}
        for match in matches:
            groups.setdefault((match["case_id"],match["rev"]),[]).append(match)
        for (prior,rev),group in groups.items():
            content,signoff = self.signed_version(db,prior,rev)
            archived = json.loads(content)
            indexed = set(self.index_rows(prior,rev,archived))
            if any(tuple(match[key] for key in INDEX_FIELDS) not in indexed for match in group):
                raise CaseError("历史同票索引与已签收底稿所记的票号或引文不符。",409)
            graph = archived["graph"]
            facts = {f["id"]:f for f in graph["facts"]}
            nodes = {n["id"]:n for n in graph["nodes"]}
            identities = {}
            if include_identity:
                reader = InvoiceIdentities(graph)
                identities = {m["fact"]:reader.describe(facts[m["fact"]]) for m in group}
            codes = {r for identity in identities.values() for r in identity["code_refs"]}
            cited = {m["fact"] for m in group} | codes
            check_cited_files(db,prior,self.files/prior,graph,[facts[ref] for ref in cited])
            selected = {m["fact"] for m in group if m["checked_field"]}
            observed = {m["fact"] for m in group if any((facts[m["fact"]].get(k) or {}).get("source_check")
                                                        for k in ("attestation","amendment"))}
            if selected != observed:
                raise CaseError("同票索引与历史票号的人工核图存证不符。",409)
            selected.update(codes)
            if selected:
                self.check_graph_field_history(prior,rev,graph,selected)
            signature = hashlib.sha256(canonical(signoff)).hexdigest()
            texts = {}
            for match in group:
                doc,page = match["doc"],match["page"]
                if (doc,page) not in texts:
                    texts[doc,page] = db.execute("SELECT text FROM pages WHERE case_id=? AND doc=? AND number=?",
                                                (prior,doc,page)).fetchone()["text"]
                try:
                    source = invoice_source_record(facts[match["fact"]],nodes[f"{doc}/p{page}"],texts[doc,page],
                                                   match["number_key"],signoff["time"])
                    if include_identity:
                        match.update(archived_identity(identities[match["fact"]],facts[match["fact"]],facts,
                                                       nodes[f"{doc}/p{page}"],texts[doc,page],signoff))
                except (KeyError,TypeError,ValueError) as error:
                    raise CaseError("已签收票号的原文依据不符，无法引用前案。",409) from error
                match.update(source=source,signoff_hash=signature)

    def prior_invoices(self, case_id, keys):
        if not keys:
            return []
        with self.connect() as db:
            db.execute("BEGIN")
            matches = indexed_invoices(db,case_id,keys)
            self.verify_invoice_sources(db,matches)
            for match in matches:
                if match["peer_source_rev"] is None:
                    del match["peer_source_rev"]
                if not match["checked_field"]:
                    del match["checked_field"]
            return matches

    @staticmethod
    def index_payment(db, case_id, revision, report):
        if report["graph"].get("profile") != BANK:
            return
        signature = payment_record(report["graph"], report["findings"])
        db.execute("DELETE FROM payment_index WHERE case_id=?", (case_id,))
        if signature["reference"]:
            db.execute("INSERT INTO payment_index(case_id,rev,payer,reference,settlement) VALUES(?,?,?,?,?)",
                       (case_id, revision, signature["payer"], signature["reference"], signature["settlement"]))
        db.execute("DELETE FROM contract_payments WHERE case_id=?",(case_id,))
        if signature["installment"]["key"]:
            db.execute("INSERT INTO contract_payments(case_id,rev,contract_key) VALUES(?,?,?)",
                       (case_id,revision,signature["installment"]["key"]))

    @staticmethod
    def payment_matches(db, case_id, signature, as_of):
        """One snapshot shared by the evidence query and the approval-time recheck."""
        counts, matches = {"same": 0, "full": 0}, []
        checks = []
        if signature["reference"]:
            checks.append(("same", "i.payer=? AND i.reference=?", (signature["payer"], signature["reference"])))
        if signature["settlement"]:
            checks.append(("full", "i.settlement=? AND i.reference<>? AND s.decision='approve'",
                           (signature["settlement"], signature["reference"])))
        for kind, predicate, params in checks:
            rows = db.execute(f"""SELECT i.case_id,i.rev,c.title,r.hash AS report_hash,s.decision,s.time AS signed_at,
                                  count(*) OVER() AS total FROM payment_index i
                                  JOIN cases c ON c.id=i.case_id AND c.rev=i.rev
                                  JOIN signoffs s ON s.case_id=i.case_id AND s.rev=i.rev
                                  JOIN reports r ON r.case_id=i.case_id AND r.rev=i.rev
                                  WHERE c.workspace=(SELECT workspace FROM cases WHERE id=?) AND c.status IN ('closed','in_review')
                                  AND c.id<>? AND s.time<=? AND {predicate}
                                  ORDER BY s.time DESC,i.case_id LIMIT ?""",
                              (case_id, case_id, as_of, *params, PAYMENT_HISTORY_LIMIT))
            for row in rows:
                match = dict(row)
                counts[kind] = match.pop("total")
                matches.append({"kind": kind, **match})
        return {"as_of": as_of, "counts": counts, "matches": matches}

    @staticmethod
    def signed_source(db, case_id, prior_id, revision):
        same_workspace = db.execute("""SELECT 1 FROM cases c JOIN cases p ON c.workspace=p.workspace
                                    WHERE c.id=? AND p.id=? AND c.id<>p.id""", (case_id, prior_id)).fetchone()
        if not same_workspace:
            raise CaseError("未找到本工作区对应的历史签收底稿。", 409)
        return Store.signed_version(db, prior_id, revision)

    @staticmethod
    def signed_version(db, case_id, revision):
        row = db.execute("""SELECT r.content,r.hash,c.workspace,c.title,s.case_id,s.rev,s.decision,s.reviewer,s.note,s.time,s.actor,
                            s.invoice_check_hash,s.invoice_check
                            FROM reports r JOIN cases c ON c.id=r.case_id
                            JOIN signoffs s ON s.case_id=r.case_id AND s.rev=r.rev
                            WHERE c.id=? AND r.rev=?""", (case_id, revision)).fetchone()
        if not row:
            raise CaseError("未找到本工作区对应的历史签收底稿。", 409)
        signoff = dict(row)
        content, checksum = signoff.pop("content").encode(), signoff.pop("hash")
        if hashlib.sha256(content).hexdigest() != checksum:
            raise CaseError("历史底稿内容与归档摘要不符。", 409)
        checked = signoff.pop("invoice_check")
        if signoff["invoice_check_hash"] is None:
            del signoff["invoice_check_hash"]
        report = json.loads(content)
        try:
            validate_invoice_approval(report,checksum,signoff,checked.encode() if checked is not None else None)
        except (KeyError,TypeError,ValueError) as exc:
            raise CaseError("签收时的同票检查回执与所据底稿或人工意见不符。",409) from exc
        pin = db.execute("""SELECT rev,report_hash,signoff_hash,resolved_rev FROM case_referrals
                          WHERE case_id=? AND (rev=? OR resolved_rev=?)""", (case_id,revision,revision)).fetchone()
        if pin and pin["rev"] == revision and source_hashes(content,signoff) != (pin["report_hash"],pin["signoff_hash"]):
            raise CaseError("原底稿或转交意见与提交复核时的摘要不符。",409)
        if pin and pin["resolved_rev"] == revision:
            original, first = Store.signed_version(db,case_id,pin["rev"])
            try:
                verify_review(report,original,first,signoff)
            except (KeyError, TypeError, ValueError) as exc:
                raise CaseError("复核签收版与原版底稿或签收记录不一致。",409) from exc
        return content, signoff

    def payment_history(self, case_id, signature):
        with self.connect() as db:
            db.execute("BEGIN")
            history = self.payment_matches(db, case_id, signature, stamp())
            for match in history["matches"]:
                prior, rev = match["case_id"], match["rev"]
                content, signoff = self.signed_source(db, case_id, prior, rev)
                report = json.loads(content)
                record = payment_record(report["graph"], report["findings"])
                indexed = db.execute("SELECT payer,reference,settlement FROM payment_index WHERE case_id=? AND rev=?",
                                     (prior, rev)).fetchone()
                if any(record[field] != indexed[field] for field in indexed.keys()):
                    raise CaseError("历史付款索引与已签收底稿中的原文不一致，无法出具本次跨案结果。", 409)
                match["signoff_hash"] = hashlib.sha256(canonical(signoff)).hexdigest()
                refs = record["same_refs" if match["kind"] == "same" else "full_refs"]
                verified = self.check_graph_field_history(prior,rev,report["graph"],set(refs))
                check_archived_files(db,prior,self.files/prior,verified)
                match["evidence"] = cited_facts(report["graph"], prior, rev, refs)
            current = signature["installment"]
            if current["requested"]:
                window = self.installment_matches(db,case_id,current["key"],history["as_of"])
                for match in window["matches"]:
                    prior,rev = match["case_id"],match["rev"]
                    content,signoff = self.signed_source(db,case_id,prior,rev)
                    paper = json.loads(content)
                    source = payment_record(paper["graph"],paper["findings"])["installment"]
                    if source["key"] != current["key"]:
                        raise CaseError("累计付款索引与历史合同及收付主体的原文不一致。",409)
                    self.check_graph_field_history(prior,rev,paper["graph"],set(source["refs"]))
                    match["entry"] = source["entry"]
                    match["signoff_hash"] = hashlib.sha256(canonical(signoff)).hexdigest()
                    match["evidence"] = cited_facts(paper["graph"],prior,rev,source["refs"])
                    check_cited_files(db,prior,self.files/prior,paper["graph"],match["evidence"])
                window["calculation"] = calculate_installments(current,window)
                history["installments"] = window
            return history

    @staticmethod
    def installment_matches(db, case_id, key, as_of):
        rows = [dict(r) for r in db.execute("""SELECT i.case_id,i.rev,c.title,r.hash AS report_hash,s.decision,
                    s.time AS signed_at,COUNT(*) OVER() AS total FROM contract_payments i
                    JOIN cases c ON c.id=i.case_id AND c.rev=i.rev
                    JOIN reports r ON r.case_id=i.case_id AND r.rev=i.rev
                    JOIN signoffs s ON s.case_id=i.case_id AND s.rev=i.rev
                    WHERE c.workspace=(SELECT workspace FROM cases WHERE id=?) AND i.contract_key=? AND i.case_id<>?
                      AND c.status='closed' AND s.decision='approve' AND s.time<=?
                    ORDER BY s.time DESC,i.case_id LIMIT ?""",(case_id,key,case_id,as_of,INSTALLMENT_LIMIT))]
        count = rows[0]["total"] if rows else 0
        for row in rows:
            del row["total"]
        return {"count":count,"matches":rows}

    def recheck_approval(self, db, case_id, revision, signoff, *, peer=False):
        row = db.execute("SELECT content,hash FROM reports WHERE case_id=? AND rev=?",(case_id,revision)).fetchone()
        if not row or hashlib.sha256(row["content"].encode()).hexdigest()!=row["hash"]:
            raise CaseError("待签收底稿与留存的版本摘要不符。",409)
        paper = json.loads(row["content"])
        graph = paper["graph"]
        if graph.get("profile",paper["policy"].get("profile")) != BANK:
            keys = sorted({edge["to"] for edge in invoice_number_edges(graph)})
            current = indexed_invoices(db,case_id,keys)
            combined = paper["policy"].get("invoice_lookup")==INVOICE_LOOKUP
            self.verify_invoice_sources(db,current,include_identity=combined)
            previous = graph.get("prior_invoices",[])
            if combined:
                current = screen(lookup_numbers(graph),current)
                changes = invoice_differences(actionables(previous),actionables(current))
            else:
                changes = invoice_differences(previous,current)
            if changes:
                raise InvoiceHistoryChanged(changes,peer)
            return invoice_approval_receipt(graph,current,revision,row["hash"],signoff)
        row = db.execute("SELECT * FROM payment_index WHERE case_id=? AND rev=?", (case_id, revision)).fetchone()
        contract = db.execute("SELECT contract_key FROM contract_payments WHERE case_id=? AND rev=?",(case_id,revision)).fetchone()
        if not row and not contract:
            return
        previous = paper["graph"].get("payment_history", {})
        now = stamp()
        current = self.payment_matches(db,case_id,row,now) if row else {"counts":{"same":0,"full":0},"matches":[]}
        def keys(history):
            return [(m["kind"], m["case_id"], m["rev"]) for m in history.get("matches", [])]
        changed = previous.get("counts", {"same":0,"full":0}) != current["counts"] or keys(previous) != keys(current)
        if contract and payment_record(paper["graph"],paper["findings"])["installment"]["requested"]:
            prior = previous.get("installments",{"count":0,"matches":[]})
            latest = self.installment_matches(db,case_id,contract["contract_key"],now)
            def pins(window):
                return [(m["case_id"],m["rev"],m["report_hash"],m["signed_at"]) for m in window["matches"]]
            changed = changed or latest["count"]!=prior["count"] or pins(latest)!=pins(prior)
        if changed:
            if peer:
                raise CaseError("底稿生成后出现了新的已签收付款线索。请退回补件，沿用原件提交重审并核对最新付款记录。", 409)
            raise CaseError("底稿生成后出现了新的已签收付款线索。请在执行记录中选择「保留此版并重新审计」，核对最新凭证后再通过。", 409)

    def prepare_signoff(self, db, signoff, source_rev, *, peer=False):
        if signoff["decision"]=="approve":
            receipt = self.recheck_approval(db,signoff["case_id"],source_rev,signoff,peer=peer)
            if receipt is not None:
                raw = encode(receipt)
                return {**signoff,"invoice_check_hash":hashlib.sha256(raw.encode()).hexdigest()},raw
        return signoff,None

    @staticmethod
    def save_signoff(db, signoff, raw):
        db.execute("""INSERT INTO signoffs(case_id,rev,decision,reviewer,note,time,actor,invoice_check_hash,invoice_check)
                      VALUES(:case_id,:rev,:decision,:reviewer,:note,:time,:actor,:invoice_check_hash,:raw)""",
                   {**signoff,"invoice_check_hash":signoff.get("invoice_check_hash"),"raw":raw})

    def rerun(self, case_id, revision, actor=None):
        with self.connect(True) as db:
            workspace = authorize_case_write(db, case_id, actor)
            admit(db, workspace, self.limits)
            result = db.execute("""UPDATE cases SET status='queued',stage='queued',progress=0,error=NULL,
                                message='等待重新执行审计',updated=? WHERE id=? AND status='ready' AND rev=?""",
                                (stamp(), case_id, revision))
            if result.rowcount != 1:
                raise CaseError("仅可对当前待验收底稿重新执行程序。", 409)
            event(db, case_id, "queued", f"基于 R{revision} 的已保存提取记录重新建图并审计。")

    def require_case(self, case_id, workspace, submitter=None):
        with self.connect() as db:
            row = db.execute("SELECT submitter FROM cases WHERE id=? AND workspace=?", (case_id, workspace)).fetchone()
        if not row or (submitter is not None and row["submitter"] != submitter):
            raise CaseError("未找到该审计任务。", 404)

    def summary(self, workspace="local", submitter=None):
        with self.connect() as db:
            rows = db.execute("""SELECT c.id,c.title,c.profile,c.created,c.updated,c.status,c.stage,c.progress,c.message,c.rev,
                              (SELECT count(*) FROM docs WHERE case_id=c.id) AS files,
                              json_extract(r.content,'$.result.verdict') AS verdict, s.decision AS decision, c.submitter_name
                              FROM cases c LEFT JOIN reports r ON r.case_id=c.id AND r.rev=c.rev
                              LEFT JOIN signoffs s ON s.case_id=c.id AND s.rev=c.rev
                              WHERE c.workspace=? AND (? IS NULL OR c.submitter=?) ORDER BY c.created DESC,c.id""",
                              (workspace,submitter,submitter))
            return [dict(row) for row in rows]

    @staticmethod
    def returned_case(db, parent, rev, workspace, owner):
        case = db.execute("""SELECT c.id,c.title,c.profile,c.status,c.rev,s.decision,r.hash FROM cases c
                             LEFT JOIN signoffs s ON s.case_id=c.id AND s.rev=c.rev
                             LEFT JOIN reports r ON r.case_id=c.id AND r.rev=c.rev
                             WHERE c.id=? AND c.workspace=? AND (? IS NULL OR c.submitter=?)""",
                          (parent, workspace, owner, owner)).fetchone()
        if not case:
            raise CaseError("未找到该审计任务。", 404)
        if case["status"] != "closed" or case["rev"] != rev or case["decision"] != "return":
            raise CaseError("请从已签收为「退回补件」的底稿版本发起补件。", 409)
        return case

    def supplement_input(self, parent, rev, workspace, actor):
        with self.connect() as db:
            db.execute("BEGIN")
            role = authorize_write(db, workspace, actor)
            source = self.returned_case(db, parent, rev, workspace, actor if role == "employee" else None)
            data = db.execute("SELECT content FROM reports WHERE case_id=? AND rev=?", (parent, rev)).fetchone()[0].encode()
            if hashlib.sha256(data).hexdigest() != source["hash"]:
                raise CaseError("前案底稿与签收版本的摘要不符。", 409)
            return source["profile"], json.loads(data)["graph"]["documents"]

    def supplement_record(self, current):
        with self.connect() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM case_supplements WHERE child=?", (current["case_id"],)).fetchone()
            if not row:
                return None
            data, signoff = self.signed_source(db, row["child"], row["parent"], row["parent_rev"])
            if source_hashes(data, signoff) != (row["parent_hash"], row["signoff_hash"]):
                raise CaseError("前案底稿或签收意见与补件受理时的摘要不符，已停止生成补件底稿。", 409)
            return compare_return(current, json.loads(data), signoff, row["parent_hash"],
                                  json.loads(row["retained"]), row["note"])

    def detail(self, case_id, owner=None, *, with_progress=False, with_actions=False):
        with self.connect() as db:
            db.execute("BEGIN")
            case = db.execute("""SELECT id,title,profile,workspace,submitter,submitter_name,created,updated,status,stage,progress,message,error,rev
                               FROM cases WHERE id=? AND (? IS NULL OR submitter=?)""", (case_id, owner, owner)).fetchone()
            if not case:
                raise CaseError("未找到该审计任务。", 404)
            detail = dict(case)
            detail["documents"] = [dict(row) for row in db.execute("SELECT id,name,ext,size,sha256,pages FROM docs WHERE case_id=? ORDER BY id", (case_id,))]
            if with_progress:
                detail["page_progress"] = checkpoints(db, case, detail["documents"])
                if case["status"] in {"queued","running"} and self.waiting_for_write.is_set():
                    detail["waiting_for_database"] = True
            detail["events"] = [dict(row) for row in db.execute("SELECT seq,time,stage,message FROM events WHERE case_id=? ORDER BY seq", (case_id,))]
            detail["revisions"] = [dict(row) for row in db.execute("SELECT rev,created,hash FROM reports WHERE case_id=? ORDER BY rev DESC", (case_id,))]
            detail["decisions"] = []
            for row in db.execute("SELECT rev,decision,reviewer,actor,note,time,invoice_check_hash FROM signoffs WHERE case_id=? ORDER BY rev",(case_id,)):
                decision = dict(row)
                if not decision["invoice_check_hash"] or owner is not None:
                    del decision["invoice_check_hash"]
                detail["decisions"].append(decision)
            if with_actions:
                detail["attestations"] = [source_row(row) for row in db.execute("""SELECT seq,rev,fact,decision,reviewer,actor,note,time,source_check
                            FROM attestations WHERE case_id=? ORDER BY seq""", (case_id,))]
                detail["amendments"] = self.amendment_rows(db,case_id)
            detail["referrals"] = [dict(row) for row in db.execute("""SELECT rev,report_hash,signoff_hash,resolved_rev,origin
                                             FROM case_referrals WHERE case_id=? ORDER BY rev""", (case_id,))]
            family = (case_id, case["workspace"], owner, owner)
            parent = db.execute("""SELECT c.id,c.title,s.parent_rev AS rev,s.note,s.retained,s.parent_hash,s.signoff_hash FROM case_supplements s
                        JOIN cases c ON c.id=s.parent WHERE s.child=? AND c.workspace=? AND (? IS NULL OR c.submitter=?)""", family).fetchone()
            detail["supplement_of"] = {**dict(parent), "retained": json.loads(parent["retained"])} if parent else None
            detail["supplements"] = [dict(r) for r in db.execute("""SELECT c.id,c.title,c.rev,c.status,c.created,s.parent_rev FROM case_supplements s
                        JOIN cases c ON c.id=s.child WHERE s.parent=? AND c.workspace=? AND (? IS NULL OR c.submitter=?)
                        ORDER BY c.created,c.id""", family)]
            return detail

    def report(self, case_id, rev):
        with self.connect() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT content,hash,created FROM reports WHERE case_id=? AND rev=?", (case_id, rev)).fetchone()
            if not row:
                raise CaseError("未找到该版本底稿。", 404)
            if hashlib.sha256(row["content"].encode()).hexdigest() != row["hash"]:
                raise CaseError("底稿内容与该版本留存的摘要不符。", 409)
            report = json.loads(row["content"])
            referral = db.execute("SELECT resolved_rev FROM case_referrals WHERE case_id=? AND (rev=? OR resolved_rev=?)",
                                  (case_id,rev,rev)).fetchone()
            if "peer_review" in report and (not referral or referral["resolved_rev"] != rev):
                raise CaseError("复核签收版缺少对应的转交记录。",409)
            if referral:
                self.signed_version(db,case_id,rev)
            result = {"rev": rev, "sha256": row["hash"], "created": row["created"], "report": report}
            action = db.execute("SELECT invoice_check FROM signoffs WHERE case_id=? AND rev=? AND decision='approve'",(case_id,rev)).fetchone()
            if action:
                if not referral:
                    self.signed_version(db,case_id,rev)
                if action["invoice_check"] is not None:
                    result["invoice_approval"] = json.loads(action["invoice_check"])
            return result

    def attestations(self, case_id):
        with self.connect() as db:
            return {row["fact"]:source_row(row) for row in db.execute("SELECT fact,decision,reviewer,actor,note,time,rev,source_check FROM attestations WHERE case_id=? ORDER BY seq", (case_id,))}

    def amendments(self, case_id):
        with self.connect() as db:
            return self.amendment_rows(db,case_id)

    @staticmethod
    def amendment_rows(db, case_id):
        return [source_row(row) for row in db.execute("""SELECT target,doc,page,page_hash,field,value,quote,region,
                reviewer,actor,note,time,rev,source_check FROM amendments WHERE case_id=? ORDER BY seq""", (case_id,))]

    def check_field_sources(self, case_id, revision, selected, address, actor):
        with self.connect() as db:
            db.execute("BEGIN")
            authorize_case_write(db,case_id,actor)
            sources = FieldSources.prepare(db,self.files/case_id,case_id,revision,selected,address)
        sources.read_files()
        return sources

    def check_graph_field_history(self, case_id, revision, graph, selected=None):
        def load_version(rev):
            original = self.report(case_id,rev)
            return original["sha256"],original["report"]
        report = {"case_id":case_id,"graph":graph}
        try:
            return validate_field_actions(report,revision,field_actions(report,revision,selected=selected),load_version)
        except (KeyError, ValueError, TypeError) as exc:
            raise CaseError("人工核图依据与当时的底稿或原页不符，已停止建图。",409) from exc

    def amend(self, case_id, revision, reviewer, note, target, doc, page, field, value, quote, region, actor=None):
        sources = self.check_field_sources(case_id,revision,[target] if target is not None else None,(doc,page),actor)
        with self.connect(True) as db:
            workspace = authorize_case_write(db, case_id, actor)
            admit(db, workspace, self.limits)
            case = db.execute("SELECT status,rev FROM cases WHERE id=?", (case_id,)).fetchone()
            if not case or case["status"] != "ready" or case["rev"] != revision:
                raise CaseError("请对当前待验收底稿进行更正或补录。", 409)
            sources.guard(db)
            receipt = sources.receipt(doc,page,"add" if target is None else "correct")
            if target is None:
                target = f"{doc}/p{page}/h{uuid.uuid4().hex[:12]}"
            now = stamp()
            encoded = encode(receipt)
            db.execute("""INSERT INTO amendments(case_id,rev,target,doc,page,page_hash,field,value,quote,region,reviewer,note,time,actor,source_check)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (case_id, revision, target, doc, page, receipt["page_sha256"], field, value, quote, region, reviewer, note, now,actor,encoded))
            db.execute("INSERT INTO attestations(case_id,rev,fact,decision,reviewer,note,time,actor,source_check) VALUES(?,?,?,'confirm',?,?,?,?,?)",
                       (case_id, revision, target, reviewer, note, now,actor,encoded))
            db.execute("""UPDATE cases SET status='queued',stage='queued',progress=0,
                       message='人工更正已留存，等待重算',updated=? WHERE id=?""", (now, case_id))
            event(db, case_id, "attestation", f"{reviewer} 新增了原页 {doc}/p{page} 的核验记录。")
            return target

    def review(self, case_id, revision, reviewer, note, decision, fact_ids=None, actor=None):
        sources = self.check_field_sources(case_id,revision,fact_ids,None,actor) if fact_ids is not None and decision=="confirm" else None
        with self.connect(True) as db:
            workspace = authorize_case_write(db, case_id, actor)
            if fact_ids is not None:
                admit(db, workspace, self.limits)
            case = db.execute("SELECT status,rev,title FROM cases WHERE id=?", (case_id,)).fetchone()
            if not case:
                raise CaseError("未找到该审计任务。", 404)
            if case["status"] != "ready" or case["rev"] != revision:
                raise CaseError("底稿已更新或已验收，请刷新后查看。", 409)
            now = stamp()
            if fact_ids is not None:
                if sources:
                    sources.guard(db)
                    facts = sources.facts
                else:
                    row = db.execute("SELECT content,hash FROM reports WHERE case_id=? AND rev=?", (case_id, revision)).fetchone()
                    if not row or hashlib.sha256(row["content"].encode()).hexdigest() != row["hash"]:
                        raise CaseError("所选底稿与留存的版本摘要不符。",409)
                    facts = {fact["id"]: fact for fact in json.loads(row["content"])["graph"]["facts"]}
                if not fact_ids or len(fact_ids) != len(set(fact_ids)) or set(fact_ids) - set(facts):
                    raise CaseError("待核记录不属于当前底稿。", 400)
                if decision == "confirm" and any(compact(facts[ref]["value"]) not in compact(facts[ref]["quote"]) for ref in fact_ids):
                    raise CaseError("取值与引文不符，请对照原页更正字段。")
                db.executemany("INSERT INTO attestations(case_id,rev,fact,decision,reviewer,note,time,actor,source_check) VALUES(?,?,?,?,?,?,?,?,?)",
                               [(case_id, revision, ref, decision, reviewer, note, now,actor,
                                 encode(sources.receipt(facts[ref]["doc"],facts[ref]["page"],"confirm")) if sources else None) for ref in fact_ids])
                db.execute("""UPDATE cases SET status='queued',stage='queued',progress=0,
                           message='人工核图已保存，等待重算',updated=? WHERE id=?""", (now, case_id))
                event(db, case_id, "attestation", f"{reviewer} 核对 {len(fact_ids)} 条引文，已保存意见并提交重算。")
            else:
                signoff = {"case_id":case_id,"workspace":workspace,"title":case["title"],"rev":revision,"decision":decision,
                           "reviewer":reviewer,"note":note,"time":now,"actor":actor}
                signoff,raw = self.prepare_signoff(db,signoff,revision)
                self.save_signoff(db,signoff,raw)
                db.execute("UPDATE cases SET status='closed',message='人工验收已归档',updated=? WHERE id=?", (now, case_id))
                if decision == "escalate":
                    content, first = self.signed_version(db, case_id, revision)
                    self.record_referral(db, hashlib.sha256(content).hexdigest(), first, "signoff")
                    event(db, case_id, "in_review", f"{reviewer} 已将底稿 R{revision} 提交复核。")
                else:
                    event(db, case_id, "closed", f"{reviewer} 已验收底稿 R{revision}。")

    @staticmethod
    def record_referral(db, report_hash, first, origin):
        key = (first["case_id"], first["rev"])
        db.execute("""INSERT INTO case_referrals(case_id,rev,report_hash,signoff_hash,origin)
                      VALUES(?,?,?,?,?)""", (*key, report_hash, hashlib.sha256(canonical(first)).hexdigest(), origin))
        db.execute("""UPDATE cases SET status='in_review',stage='in_review',message='已提交复核，等待另一位审计人员签收'
                      WHERE id=? AND rev=? AND status='closed'""", key)

    def resolve_referral(self, case_id, revision, report_hash, signoff_hash, reviewer, note, decision, findings, actor=None):
        with self.connect(True) as db:
            authorize_case_write(db, case_id, actor)
            referral = db.execute("""SELECT f.*,c.rev AS latest,c.status FROM case_referrals f JOIN cases c ON c.id=f.case_id
                                  WHERE f.case_id=? AND f.rev=?""", (case_id, revision)).fetchone()
            if not referral or (referral["report_hash"],referral["signoff_hash"]) != (report_hash,signoff_hash):
                raise CaseError("待复核版本或转交意见与当前请求不符，请重新打开原底稿。", 409)
            source, first = self.signed_version(db, case_id, revision)
            if source_hashes(source, first) != (report_hash,signoff_hash):
                raise CaseError("原底稿或转交意见与提交复核时的摘要不符。", 409)
            next_rev = revision + 1
            second = {**first, "rev":next_rev, "time":stamp(), "decision":decision, "actor":actor,
                      "reviewer":reviewer, "note":note}
            if not different_reviewers(first,second):
                raise CaseError("请由另一位审计人员复核这份底稿。", 403)
            report = json.loads(source)
            if decision not in ("approve", "return") or not valid_findings(report, findings):
                raise CaseError("请选择复核决定和原底稿中相应的审计发现。", 400)
            if referral["resolved_rev"] is not None:
                raw, actual = self.signed_version(db, case_id, next_rev)
                previous = json.loads(raw)
                try:
                    verify_review(previous, source, first, actual)
                except (ValueError, KeyError, TypeError) as exc:
                    raise CaseError("已签收的复核版与原底稿不一致。", 409) from exc
                submitted = {k:v for k,v in actual.items() if k!="invoice_check_hash"}
                if submitted == {**second, "time":actual["time"]} and previous["peer_review"]["findings"] == findings:
                    return next_rev
                raise CaseError(f"复核已由 {actual['reviewer']} 完成，请查看 R{next_rev}。", 409)
            if referral["latest"] != revision or referral["status"] != "in_review":
                raise CaseError("此版本已不在待复核队列。", 409)
            second,checked = self.prepare_signoff(db,second,revision,peer=True)
            try:
                report["peer_review"] = review_record(source, first, second, findings)
            except (ValueError, KeyError, TypeError) as exc:
                raise CaseError("原版签收或复核依据不完整，无法生成复核签收版。", 409) from exc
            content = encode(report)
            now = second["time"]
            db.execute("INSERT INTO reports VALUES(?,?,?,?,?)", (case_id, next_rev, now, hashlib.sha256(content.encode()).hexdigest(), content))
            self.save_signoff(db,second,checked)
            db.execute("UPDATE case_referrals SET resolved_rev=? WHERE case_id=? AND rev=?", (next_rev, case_id, revision))
            self.index_report(db, case_id, next_rev, report)
            db.execute("""UPDATE cases SET rev=?,status='closed',stage='closed',message='复核签收版已归档',updated=? WHERE id=?""",
                       (next_rev, now, case_id))
            event(db, case_id, "closed", f"{reviewer} 完成 R{revision} 复核，签收版 R{next_rev} 已归档。")
            return next_rev
