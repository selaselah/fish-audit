import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from backup import MARKER
from capacity import admit, install as install_capacity, settings
from config import BANK, CaseError, PROFILE
from graph import compact, invoice_number_edges
from payment_history import LIMIT as PAYMENT_HISTORY_LIMIT, canonical, cited_facts, payment_record
from supplements import compare_return
from workbench import prepare_index, project


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def source_hashes(content, signoff):
    return hashlib.sha256(content).hexdigest(), hashlib.sha256(canonical(signoff)).hexdigest()


def event(db, case_id, stage, message):
    db.execute("INSERT INTO events(case_id,time,stage,message) VALUES(?,?,?,?)",
               (case_id, stamp(), stage, message))


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
                if "actor" not in {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN actor TEXT")
            if db.execute("PRAGMA user_version").fetchone()[0] < 1:
                rows = db.execute("""SELECT c.id,c.rev,r.content FROM cases c
                                  JOIN reports r ON r.case_id=c.id AND r.rev=c.rev""")
                for row in rows:
                    db.executemany("INSERT OR REPLACE INTO invoice_index VALUES(?,?,?,?,?,?,?,?,?,?)",
                                   self.index_rows(row["id"], row["rev"], json.loads(row["content"])))
                db.execute("PRAGMA user_version=1")
            self.fts_enabled = prepare_index(db)
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
            if db.execute("PRAGMA user_version").fetchone()[0] < 3:
                rows = db.execute("""SELECT c.id,c.rev,r.content FROM cases c JOIN reports r ON r.case_id=c.id
                                   AND r.rev=c.rev WHERE c.profile=?""", (BANK,))
                for row in rows:
                    self.index_payment(db, row["id"], row["rev"], json.loads(row["content"]))
                db.execute("PRAGMA user_version=3")
            install_capacity(db)
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=12)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
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
                return row["id"]
        return None

    def progress(self, case_id, stage, percent, message):
        with self.connect(True) as db:
            db.execute("UPDATE cases SET stage=?,progress=?,message=?,updated=? WHERE id=?",
                       (stage, percent, message, stamp(), case_id))
            event(db, case_id, stage, message)

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
            project(db, case_id, revision, report)
            self.index_payment(db, case_id, revision, report)
            invoice_rows = self.index_rows(case_id, revision, report)
            db.executemany("INSERT INTO invoice_index VALUES(?,?,?,?,?,?,?,?,?,?)", invoice_rows)
            db.execute("""UPDATE cases SET rev=?,status='ready',stage='ready',progress=100,
                       error=NULL,message='审计底稿已生成，等待人工验收',updated=? WHERE id=?""", (revision, now, case_id))
            event(db, case_id, "ready", f"底稿 R{revision} 已保存，等待人工验收。")

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

    def prior_invoices(self, case_id, keys):
        if not keys:
            return []
        with self.connect() as db:
            placeholders = ",".join("?" for key in keys)
            rows = db.execute(f"""SELECT i.*,c.title,s.decision,r.hash AS report_hash FROM invoice_index i
                              JOIN cases c ON c.id=i.case_id AND c.rev=i.rev
                              JOIN signoffs s ON s.case_id=i.case_id AND s.rev=i.rev
                              JOIN reports r ON r.case_id=i.case_id AND r.rev=i.rev
                              WHERE c.workspace=(SELECT workspace FROM cases WHERE id=?) AND c.status='closed'
                              AND c.id<>? AND i.number_key IN ({placeholders})
                              ORDER BY i.case_id,i.rev,i.fact""", (case_id, case_id, *keys))
            return [dict(row) for row in rows]

    @staticmethod
    def index_payment(db, case_id, revision, report):
        if report["graph"].get("profile") != BANK:
            return
        signature = payment_record(report["graph"], report["findings"])
        db.execute("DELETE FROM payment_index WHERE case_id=?", (case_id,))
        if signature["reference"]:
            db.execute("INSERT INTO payment_index(case_id,rev,payer,reference,settlement) VALUES(?,?,?,?,?)",
                       (case_id, revision, signature["payer"], signature["reference"], signature["settlement"]))

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
                                  WHERE c.workspace=(SELECT workspace FROM cases WHERE id=?) AND c.status='closed'
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
        row = db.execute("""SELECT r.content,r.hash,c.workspace,c.title,s.case_id,s.rev,s.decision,s.reviewer,s.note,s.time,s.actor
                            FROM reports r JOIN cases c ON c.id=r.case_id
                            JOIN signoffs s ON s.case_id=r.case_id AND s.rev=r.rev
                            WHERE c.workspace=(SELECT workspace FROM cases WHERE id=?) AND c.id<>? AND c.id=? AND r.rev=?""",
                         (case_id, case_id, prior_id, revision)).fetchone()
        if not row:
            raise CaseError("未找到本工作区对应的历史签收底稿。", 409)
        signoff = dict(row)
        content, checksum = signoff.pop("content").encode(), signoff.pop("hash")
        if hashlib.sha256(content).hexdigest() != checksum:
            raise CaseError("历史底稿内容与归档摘要不符。", 409)
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
                match["evidence"] = cited_facts(report["graph"], prior, rev, refs)
            return history

    def recheck_payment_approval(self, db, case_id, revision):
        row = db.execute("SELECT * FROM payment_index WHERE case_id=? AND rev=?", (case_id, revision)).fetchone()
        if not row:
            return
        previous = json.loads(db.execute("SELECT content FROM reports WHERE case_id=? AND rev=?",
                                         (case_id, revision)).fetchone()[0])["graph"].get("payment_history", {})
        current = self.payment_matches(db, case_id, row, stamp())
        def keys(history):
            return [(m["kind"], m["case_id"], m["rev"]) for m in history.get("matches", [])]
        if previous.get("counts", {"same": 0, "full": 0}) != current["counts"] or keys(previous) != keys(current):
            raise CaseError("底稿生成后出现了新的已签收付款线索。请在执行记录中选择「保留此版并重新审计」，核对最新凭证后再通过。", 409)

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

    def detail(self, case_id, owner=None):
        with self.connect() as db:
            db.execute("BEGIN")
            case = db.execute("""SELECT id,title,profile,workspace,submitter,submitter_name,created,updated,status,stage,progress,message,error,rev
                               FROM cases WHERE id=? AND (? IS NULL OR submitter=?)""", (case_id, owner, owner)).fetchone()
            if not case:
                raise CaseError("未找到该审计任务。", 404)
            detail = dict(case)
            detail["documents"] = [dict(row) for row in db.execute("SELECT id,name,ext,size,sha256,pages FROM docs WHERE case_id=? ORDER BY id", (case_id,))]
            detail["events"] = [dict(row) for row in db.execute("SELECT seq,time,stage,message FROM events WHERE case_id=? ORDER BY seq", (case_id,))]
            detail["revisions"] = [dict(row) for row in db.execute("SELECT rev,created,hash FROM reports WHERE case_id=? ORDER BY rev DESC", (case_id,))]
            detail["decisions"] = [dict(row) for row in db.execute("SELECT rev,decision,reviewer,actor,note,time FROM signoffs WHERE case_id=? ORDER BY rev", (case_id,))]
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
            row = db.execute("SELECT content,hash,created FROM reports WHERE case_id=? AND rev=?", (case_id, rev)).fetchone()
            if not row:
                raise CaseError("未找到该版本底稿。", 404)
            return {"rev": rev, "sha256": row["hash"], "created": row["created"], "report": json.loads(row["content"])}

    def attestations(self, case_id):
        with self.connect() as db:
            return {row["fact"]: dict(row) for row in db.execute("SELECT fact,decision,reviewer,actor,note,time,rev FROM attestations WHERE case_id=? ORDER BY seq", (case_id,))}

    def amendments(self, case_id):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT target,doc,page,page_hash,field,value,quote,region,
                    reviewer,actor,note,time,rev FROM amendments WHERE case_id=? ORDER BY seq""", (case_id,))]

    def amend(self, case_id, revision, reviewer, note, target, doc, page, field, value, quote, region, actor=None):
        with self.connect(True) as db:
            workspace = authorize_case_write(db, case_id, actor)
            admit(db, workspace, self.limits)
            case = db.execute("SELECT status,rev FROM cases WHERE id=?", (case_id,)).fetchone()
            if not case or case["status"] != "ready" or case["rev"] != revision:
                raise CaseError("请对当前待验收底稿进行更正或补录。", 409)
            source = db.execute("SELECT sha256 FROM pages WHERE case_id=? AND doc=? AND number=?", (case_id, doc, page)).fetchone()
            if not source:
                raise CaseError("所选原页不属于此案。", 400)
            if target is not None:
                row = db.execute("SELECT content FROM reports WHERE case_id=? AND rev=?", (case_id, revision)).fetchone()
                facts = json.loads(row["content"])["graph"]["facts"]
                if not any(fact["id"] == target and fact["doc"] == doc and fact["page"] == page for fact in facts):
                    raise CaseError("更正记录与所选原页不匹配。", 400)
            else:
                target = f"{doc}/p{page}/h{uuid.uuid4().hex[:12]}"
            now = stamp()
            db.execute("""INSERT INTO amendments(case_id,rev,target,doc,page,page_hash,field,value,quote,region,reviewer,note,time,actor)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (case_id, revision, target, doc, page, source["sha256"], field, value, quote, region, reviewer, note, now,actor))
            db.execute("INSERT INTO attestations(case_id,rev,fact,decision,reviewer,note,time,actor) VALUES(?,?,?,'confirm',?,?,?,?)",
                       (case_id, revision, target, reviewer, note, now,actor))
            db.execute("""UPDATE cases SET status='queued',stage='queued',progress=0,
                       message='人工更正已留存，等待重算',updated=? WHERE id=?""", (now, case_id))
            event(db, case_id, "attestation", f"{reviewer} 新增了原页 {doc}/p{page} 的核验记录。")
            return target

    def review(self, case_id, revision, reviewer, note, decision, fact_ids=None, actor=None):
        with self.connect(True) as db:
            workspace = authorize_case_write(db, case_id, actor)
            if fact_ids is not None:
                admit(db, workspace, self.limits)
            case = db.execute("SELECT status,rev FROM cases WHERE id=?", (case_id,)).fetchone()
            if not case:
                raise CaseError("未找到该审计任务。", 404)
            if case["status"] != "ready" or case["rev"] != revision:
                raise CaseError("底稿已更新或已验收，请刷新后查看。", 409)
            now = stamp()
            if fact_ids is not None:
                row = db.execute("SELECT content FROM reports WHERE case_id=? AND rev=?", (case_id, revision)).fetchone()
                facts = {fact["id"]: fact for fact in json.loads(row["content"])["graph"]["facts"]}
                if not fact_ids or len(fact_ids) != len(set(fact_ids)) or set(fact_ids) - set(facts):
                    raise CaseError("待核记录不属于当前底稿。", 400)
                if decision == "confirm" and any(compact(facts[ref]["value"]) not in compact(facts[ref]["quote"]) for ref in fact_ids):
                    raise CaseError("取值与引文不符，请对照原页更正字段。")
                db.executemany("INSERT INTO attestations(case_id,rev,fact,decision,reviewer,note,time,actor) VALUES(?,?,?,?,?,?,?,?)",
                               [(case_id, revision, ref, decision, reviewer, note, now, actor) for ref in fact_ids])
                db.execute("""UPDATE cases SET status='queued',stage='queued',progress=0,
                           message='人工核图已保存，等待重算',updated=? WHERE id=?""", (now, case_id))
                event(db, case_id, "attestation", f"{reviewer} 核对 {len(fact_ids)} 条引文，已保存意见并提交重算。")
            else:
                if decision == "approve":
                    self.recheck_payment_approval(db, case_id, revision)
                db.execute("INSERT INTO signoffs(case_id,rev,decision,reviewer,note,time,actor) VALUES(?,?,?,?,?,?,?)", (case_id, revision, decision, reviewer, note, now,actor))
                db.execute("UPDATE cases SET status='closed',message='人工验收已归档',updated=? WHERE id=?", (now, case_id))
                event(db, case_id, "closed", f"{reviewer} 已验收底稿 R{revision}。")
