"""Compact workspace ledger and a searchable projection of the latest revision of each case."""

import json
import sqlite3
import unicodedata

from config import CaseError, PROFILES


def searchable(value):
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def prepare_index(db):
    db.execute("""CREATE TABLE IF NOT EXISTS case_stats(case_id TEXT PRIMARY KEY REFERENCES cases(id),
                  verdict TEXT NOT NULL, issues INTEGER NOT NULL, risks INTEGER NOT NULL, missing INTEGER NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS evidence_index(
                  rowid INTEGER PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), rev INTEGER NOT NULL,
                  fact TEXT NOT NULL, doc TEXT NOT NULL, page INTEGER NOT NULL, name TEXT NOT NULL, field TEXT NOT NULL,
                  label TEXT NOT NULL, value TEXT NOT NULL, quote TEXT NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL,
                  UNIQUE(case_id,fact))""")
    had_fts = db.execute("SELECT 1 FROM sqlite_master WHERE name='evidence_terms'").fetchone()
    try:
        db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS evidence_terms USING fts5(body,
                      content='evidence_index', content_rowid='rowid', tokenize='trigram')""")
    except sqlite3.OperationalError as error:
        if not any(reason in str(error).lower() for reason in ("no such module", "no such tokenizer")):
            raise
        enabled = False
    else:
        enabled = True
        if not had_fts:
            db.execute("INSERT INTO evidence_terms(evidence_terms) VALUES('rebuild')")
        db.execute("""CREATE TRIGGER IF NOT EXISTS evidence_insert AFTER INSERT ON evidence_index BEGIN
                      INSERT INTO evidence_terms(rowid,body) VALUES(new.rowid,new.body); END""")
        db.execute("""CREATE TRIGGER IF NOT EXISTS evidence_delete AFTER DELETE ON evidence_index BEGIN
                      INSERT INTO evidence_terms(evidence_terms,rowid,body) VALUES('delete',old.rowid,old.body); END""")
    if db.execute("PRAGMA user_version").fetchone()[0] < 2:
        rows = db.execute("""SELECT c.id,c.rev,r.content FROM cases c JOIN reports r ON r.case_id=c.id AND r.rev=c.rev""")
        for row in rows:
            project(db, row["id"], row["rev"], json.loads(row["content"]))
        db.execute("PRAGMA user_version=2")
    return enabled


def project(db, case_id, rev, report):
    result = report["result"]
    counts = result["counts"]
    db.execute("INSERT OR REPLACE INTO case_stats VALUES(?,?,?,?,?)",
               (case_id, result["verdict"], counts["issue"], counts["risk"], counts["missing"]))
    db.execute("DELETE FROM evidence_index WHERE case_id=?", (case_id,))
    rows = []
    for fact in report["graph"]["facts"]:
        body = "\n".join(searchable(fact[k]) for k in ("name","label","value","quote"))
        rows.append((case_id, rev, fact["id"], fact["doc"], fact["page"], fact["name"], fact["field"], fact["label"],
                     fact["value"], fact["quote"], fact["status"], body))
    db.executemany("""INSERT INTO evidence_index(case_id,rev,fact,doc,page,name,field,label,value,quote,status,body)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", rows)


def page_number(params):
    try:
        number = int(params.get("page", "1"))
    except (ValueError, TypeError):
        number = 0
    if not 1 <= number <= 10_000_000:
        raise CaseError("页码无效。", 400)
    return number


def page_info(total, requested, size):
    pages = max(1, (total + size - 1) // size)
    current = min(requested, pages)
    return {"page": current, "pages": pages, "total": total, "page_size": size}


def inbox(store, workspace, owner, params):
    group = params.get("status", "all")
    query = params.get("q", "").strip()
    profile = params.get("profile", "")
    order = params.get("sort", "updated")
    groups = {"all":"1", "active":"c.status IN ('queued','running')", "ready":"c.status='ready'",
              "attention":"c.status='ready' AND t.verdict IN ('reject','review')",
              "closed":"c.status='closed'", "failed":"c.status='failed'"}
    if group not in groups or (profile and profile not in PROFILES) or len(query) > 100 or order not in ("updated","created"):
        raise CaseError("台账筛选条件无效。", 400)
    conditions, args = ["c.workspace=?"], [workspace]
    if owner:
        conditions.append("c.submitter=?")
        args.append(owner)
    if profile:
        conditions.append("c.profile=?")
        args.append(profile)
    if query:
        conditions.append("instr(lower(c.title||' '||coalesce(c.submitter_name,'')||' '||c.id),lower(?))>0")
        args.append(query)
    source = " FROM cases c LEFT JOIN case_stats t ON t.case_id=c.id LEFT JOIN signoffs s ON s.case_id=c.id AND s.rev=c.rev WHERE " + " AND ".join(conditions)
    with store.connect() as db:
        db.execute("BEGIN")
        measures = ",".join(f"count(*) FILTER (WHERE {expr}) AS [{key}]" for key, expr in groups.items())
        counts = dict(db.execute("SELECT "+measures+source,args).fetchone())
        page = page_info(counts[group], page_number(params), 12)
        rows = db.execute("""SELECT c.id,c.title,c.profile,c.created,c.updated,c.status,c.stage,c.progress,
                          c.message,c.rev,c.submitter_name,t.verdict,t.issues,t.risks,t.missing,s.decision,
                          (SELECT count(*) FROM docs WHERE case_id=c.id) AS files""" + source + " AND ("+groups[group]+")"
                          +f" ORDER BY c.{order} DESC,c.id LIMIT ? OFFSET ?",
                          [*args,page["page_size"],(page["page"]-1)*page["page_size"]])
        return {"cases": [dict(row) for row in rows], "counts": counts, **page}


def search_evidence(store, workspace, params):
    query = params.get("q","").strip()
    status = params.get("status","verified")
    requested = page_number(params)
    if len(query) > 120 or len(query.split()) > 8 or status not in ("verified","pending","all"):
        raise CaseError("请输入 120 字以内、最多八段的检索词，并选择证据状态。", 400)
    tokens = list(dict.fromkeys(searchable(word) for word in query.split() if searchable(word)))
    if not tokens:
        return {"hits": [], **page_info(0, requested, 15)}
    source = " FROM evidence_index e JOIN cases c ON c.id=e.case_id AND c.rev=e.rev"
    conditions, args = ["c.workspace=?"], [workspace]
    if status != "all":
        operator = "IN" if status == "verified" else "NOT IN"
        conditions.append(f"e.status {operator} ('anchored','confirmed')")
    indexed = [token for token in tokens if len(token) >= 3]
    if store.fts_enabled and indexed:
        source += " JOIN evidence_terms ON evidence_terms.rowid=e.rowid"
        conditions.append("evidence_terms MATCH ?")
        args.append(" AND ".join('"'+token.replace('"','""')+'"' for token in indexed))
    for token in tokens:
        conditions.append("instr(e.body,?)>0")
        args.append(token)
    source += " WHERE "+" AND ".join(conditions)
    with store.connect() as db:
        db.execute("BEGIN")
        total = db.execute("SELECT count(*)"+source,args).fetchone()[0]
        page = page_info(total,requested,15)
        rows = db.execute("""SELECT c.title,e.case_id,e.rev,e.fact,e.doc,e.page,e.name,e.field,e.label,e.value,e.quote,e.status"""
                          +source+" ORDER BY c.updated DESC,c.id,e.doc,e.page,e.rowid LIMIT ? OFFSET ?",
                          [*args,page["page_size"],(page["page"]-1)*page["page_size"]])
        return {"hits": [dict(row) for row in rows], **page}
