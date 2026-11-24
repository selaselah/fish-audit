"""Read the persisted page checkpoints without returning extraction text or model traces."""


PAGE_STATE = """CASE WHEN extraction IS NULL THEN 'prepared'
                WHEN NOT json_valid(extraction) THEN 'invalid'
                WHEN json_type(extraction,'$.output.facts') IS NOT 'array' THEN 'invalid'
                WHEN json_type(extraction,'$.check.output.checks')='array' THEN 'checked'
                ELSE 'read' END"""


def install(db):
    db.execute(f"CREATE INDEX IF NOT EXISTS page_checkpoint_states ON pages(case_id,doc,number,({PAGE_STATE}))")
    db.execute("""CREATE TABLE IF NOT EXISTS case_activity(
        case_id TEXT PRIMARY KEY, doc TEXT NOT NULL, page INTEGER CHECK(page IS NULL OR page>0),
        operation TEXT NOT NULL CHECK(operation IN ('prepare','read','check','integrity')),
        FOREIGN KEY(case_id,doc) REFERENCES docs(case_id,id))""")


def set_activity(db, case_id, activity):
    if activity is None:
        db.execute("DELETE FROM case_activity WHERE case_id=?", (case_id,))
    else:
        db.execute("INSERT OR REPLACE INTO case_activity(case_id,doc,page,operation) VALUES(?,?,?,?)", (case_id, *activity))


def checkpoints(db, case, documents):
    pages = {doc["id"]: [] for doc in documents}
    counts = {"prepared": 0, "read": 0, "checked": 0}
    rows = db.execute(f"""SELECT doc,number,{PAGE_STATE} AS state FROM pages INDEXED BY page_checkpoint_states
                          WHERE case_id=? ORDER BY doc,number""", (case["id"],))
    for row in rows:
        state = row["state"]
        pages[row["doc"]].append({"page": row["number"], "state": state})
        counts["prepared"] += 1
        counts["read"] += state in {"read", "checked"}
        counts["checked"] += state == "checked"
    active = None
    if case["status"] in {"running", "failed"}:
        row = db.execute("SELECT doc,page,operation FROM case_activity WHERE case_id=?", (case["id"],)).fetchone()
        if row:
            active = dict(row)
    return {"counts": counts, "documents": pages, "activity": active}
