import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from config import CaseError, PROFILE
from graph import compact, invoice_number_edges
from workbench import prepare_index, project


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def event(db, case_id, stage, message):
    db.execute("INSERT INTO events(case_id,time,stage,message) VALUES(?,?,?,?)",
               (case_id, stamp(), stage, message))


def authorize_write(db, workspace, actor, *, review=False):
    if workspace == "local":
        return
    member = db.execute("SELECT role FROM members WHERE workspace=? AND account=?", (workspace, actor)).fetchone()
    if not member or (review and member["role"] == "employee"):
        raise CaseError("当前账号无权执行此次操作。", 403)


def authorize_case_write(db, case_id, actor):
    case = db.execute("SELECT workspace FROM cases WHERE id=?", (case_id,)).fetchone()
    if not case:
        raise CaseError("未找到该审计任务。", 404)
    authorize_write(db, case["workspace"], actor, review=True)


class Store:
    def __init__(self, root):
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

    def existing(self, key, fingerprint):
        with self.connect() as db:
            row = db.execute("SELECT id,fingerprint FROM cases WHERE request_key=?", (key,)).fetchone()
            if row and row["fingerprint"] != fingerprint:
                raise CaseError("同一提交编号对应了不同资料，请重新提交。", 409)
            return row["id"] if row else None

    def create(self, case_id, title, docs, request_key, fingerprint, profile=PROFILE, workspace="local", user=None):
        with self.connect(True) as db:
            now = stamp()
            user = user or {}
            authorize_write(db, workspace, user.get("id"))
            db.execute("""INSERT INTO cases(id,title,created,updated,status,stage,progress,message,request_key,fingerprint,profile,workspace,submitter,submitter_name)
                       VALUES(?,?,?,?,'queued','queued',0,'等待审计',?,?,?,?,?,?)""",
                       (case_id, title, now, now, request_key, fingerprint, profile, workspace,user.get("id"),user.get("name")))
            db.executemany("INSERT INTO docs(case_id,id,name,ext,size,sha256) VALUES(?,?,?,?,?,?)",
                           [(case_id, doc["id"], doc["name"], doc["ext"], doc["size"], doc["sha256"]) for doc in docs])
            event(db, case_id, "queued", f"收到 {len(docs)} 份原件。")

    def recover(self):
        with self.connect(True) as db:
            rows = db.execute("SELECT id FROM cases WHERE status='running'").fetchall()
            for row in rows:
                db.execute("UPDATE cases SET status='queued',stage='queued',message='服务重启，等待恢复',updated=? WHERE id=?",
                           (stamp(), row["id"]))
                event(db, row["id"], "queued", "服务重启，恢复已保存的分页与模型检查点。")

    def claim(self):
        with self.connect(True) as db:
            row = db.execute("SELECT id FROM cases WHERE status='queued' ORDER BY updated,id LIMIT 1").fetchone()
            if row:
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
            authorize_case_write(db, case_id, actor)
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

    def rerun(self, case_id, revision, actor=None):
        with self.connect(True) as db:
            authorize_case_write(db, case_id, actor)
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

    def detail(self, case_id):
        with self.connect() as db:
            db.execute("BEGIN")
            case = db.execute("SELECT id,title,profile,workspace,submitter,submitter_name,created,updated,status,stage,progress,message,error,rev FROM cases WHERE id=?", (case_id,)).fetchone()
            if not case:
                raise CaseError("未找到该审计任务。", 404)
            detail = dict(case)
            detail["documents"] = [dict(row) for row in db.execute("SELECT id,name,ext,size,sha256,pages FROM docs WHERE case_id=? ORDER BY id", (case_id,))]
            detail["events"] = [dict(row) for row in db.execute("SELECT seq,time,stage,message FROM events WHERE case_id=? ORDER BY seq", (case_id,))]
            detail["revisions"] = [dict(row) for row in db.execute("SELECT rev,created,hash FROM reports WHERE case_id=? ORDER BY rev DESC", (case_id,))]
            detail["decisions"] = [dict(row) for row in db.execute("SELECT rev,decision,reviewer,actor,note,time FROM signoffs WHERE case_id=? ORDER BY rev", (case_id,))]
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
            authorize_case_write(db, case_id, actor)
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
            authorize_case_write(db, case_id, actor)
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
                db.execute("INSERT INTO signoffs(case_id,rev,decision,reviewer,note,time,actor) VALUES(?,?,?,?,?,?,?)", (case_id, revision, decision, reviewer, note, now,actor))
                db.execute("UPDATE cases SET status='closed',message='人工验收已归档',updated=? WHERE id=?", (now, case_id))
                event(db, case_id, "closed", f"{reviewer} 已验收底稿 R{revision}。")
