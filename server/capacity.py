"""Per-workspace admission and metering for a single durable worker."""

import os
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from config import CaseError


CLIENT_ZONE = ZoneInfo("Asia/Shanghai")
CURRENT_JOB = ContextVar("audit_metered_job", default=None)
DEFAULTS = {"monthly_cases":150, "active_cases":4, "storage_mib":2048, "monthly_requests":3000}


def settings():
    limits = {key:int(os.getenv("AUDIT_"+key.upper(), default)) for key, default in DEFAULTS.items()}
    if any(value < 1 for value in limits.values()):
        raise ValueError("企业资源上限必须为正整数。")
    return limits


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def period():
    current = datetime.now(CLIENT_ZONE)
    start = current.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    return current.strftime("%Y-%m"), start.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def install(db):
    db.execute("""CREATE TABLE IF NOT EXISTS model_requests(id TEXT PRIMARY KEY, workspace TEXT NOT NULL,
               case_id TEXT NOT NULL REFERENCES cases(id), started TEXT NOT NULL, model TEXT NOT NULL, operation TEXT NOT NULL,
               status TEXT NOT NULL, response_id TEXT, input_tokens INTEGER, output_tokens INTEGER)""")
    db.execute("CREATE INDEX IF NOT EXISTS request_month ON model_requests(workspace,started)")
    db.execute("CREATE TABLE IF NOT EXISTS worker_turn(workspace TEXT PRIMARY KEY, turn INTEGER NOT NULL)")


def task_counts(db, workspace, beginning):
    return db.execute("""SELECT count(*) FILTER (WHERE created>=?) AS monthly_cases,
                      count(*) FILTER (WHERE status IN ('queued','running')) AS active_cases
                      FROM cases WHERE workspace=?""", (beginning,workspace)).fetchone()


def storage_bytes(db, workspace):
    return db.execute("""SELECT coalesce(sum(d.size),0) FROM docs d JOIN cases c ON c.id=d.case_id WHERE c.workspace=?""",
                      (workspace,)).fetchone()[0]


def admit(db, workspace, limits, size=None):
    if workspace == "local":
        return
    counts = task_counts(db,workspace,period()[1])
    if counts["active_cases"] >= limits["active_cases"]:
        raise CaseError("企业等待或执行中的任务已达上限，请待现有任务完成后重试。",429)
    if size is not None:
        if counts["monthly_cases"] >= limits["monthly_cases"]:
            raise CaseError("本月企业新建任务数已达上限。",429)
        if storage_bytes(db,workspace)+size > limits["storage_mib"]*1024**2:
            raise CaseError("企业原件存储空间不足。",429)


def usage(store, workspace):
    label, beginning = period()
    with store.connect() as db:
        db.execute("BEGIN")
        tasks = dict(task_counts(db,workspace,beginning))
        requests = db.execute("""SELECT count(*) AS requests,
                              count(*) FILTER (WHERE input_tokens IS NULL OR output_tokens IS NULL) AS unreported,
                              coalesce(sum(input_tokens),0) AS input_tokens,coalesce(sum(output_tokens),0) AS output_tokens
                              FROM model_requests WHERE workspace=? AND started>=?""", (workspace,beginning)).fetchone()
        return {"period":label,"limits": store.limits,**tasks,"storage_bytes":storage_bytes(db,workspace),**dict(requests)}


@contextmanager
def job_scope(store, case_id):
    with store.connect() as db:
        workspace = db.execute("SELECT workspace FROM cases WHERE id=?", (case_id,)).fetchone()["workspace"]
    token = CURRENT_JOB.set(None if workspace == "local" else (store,workspace,case_id))
    try:
        yield
    finally:
        CURRENT_JOB.reset(token)


@contextmanager
def request_attempt(model, operation):
    job = CURRENT_JOB.get()
    if job is None:
        yield lambda response: None
        return
    store, workspace, case_id = job
    request_id = uuid.uuid4().hex
    with store.connect(True) as db:
        issued = db.execute("SELECT count(*) FROM model_requests WHERE workspace=? AND started>=?",
                            (workspace,period()[1])).fetchone()[0]
        if issued >= store.limits["monthly_requests"]:
            raise CaseError("企业本月模型请求数已达上限。可调整配置或在下月从检查点继续。",429)
        db.execute("""INSERT INTO model_requests(id,workspace,case_id,started,model,operation,status)
                   VALUES(?,?,?,?,?,?,'sent')""",(request_id,workspace,case_id,now(),model,operation))

    def received(envelope):
        counts = envelope.get("usage") or {}
        with store.connect(True) as db:
            db.execute("UPDATE model_requests SET status=?,response_id=?,input_tokens=?,output_tokens=? WHERE id=?",
                       (envelope.get("status","received"),envelope.get("id"),counts.get("input_tokens"),
                        counts.get("output_tokens"),request_id))
    try:
        yield received
    except BaseException:
        with store.connect(True) as db:
            db.execute("UPDATE model_requests SET status='unconfirmed' WHERE id=? AND status='sent'",(request_id,))
        raise
