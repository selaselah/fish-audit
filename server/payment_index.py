"""Keep the two searchable projections of a bank workpaper consistent with its archived facts."""

from config import BANK, CaseError


PROJECTIONS = (
    ("payment_index", ("payer", "reference", "settlement"), "流水", "历史付款索引与已签收底稿中的原文不一致"),
    ("contract_payments", ("contract_key",), "合同付款", "累计付款索引与历史合同及收付主体的原文不一致"),
)


def install(db):
    # A row is keyed by case, so even an update pointing it to the wrong revision must dirty the current case.
    tables = ("payment_index", "contract_payments", "reports")
    operations = {"insert": ("NEW",), "delete": ("OLD",), "update": ("OLD", "NEW")}
    existing = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','trigger')")}
    required = {"payment_index_pending"}
    db.execute("CREATE TABLE IF NOT EXISTS payment_index_pending(case_id TEXT PRIMARY KEY) WITHOUT ROWID")
    for table in tables:
        for operation, sources in operations.items():
            name = f"payment_check_{table}_{operation}"
            required.add(name)
            changes = " ".join(f"INSERT OR IGNORE INTO payment_index_pending VALUES({source}.case_id);" for source in sources)
            db.execute(f"CREATE TRIGGER IF NOT EXISTS {name} AFTER {operation} ON {table} BEGIN {changes} END")
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version < 6 or required - existing:
        db.execute("INSERT OR IGNORE INTO payment_index_pending SELECT id FROM cases WHERE profile=? AND rev>0", (BANK,))
        if version < 6:
            db.execute("PRAGMA user_version=6")


def pending_signed(db, case_id):
    return db.execute("""SELECT c.id,c.rev FROM payment_index_pending p
                      CROSS JOIN cases c ON c.id=p.case_id
                      CROSS JOIN signoffs s ON s.case_id=c.id AND s.rev=c.rev
                      WHERE c.workspace=(SELECT workspace FROM cases WHERE id=?) AND c.id<>?
                      AND c.profile=? AND c.status IN ('closed','in_review')""", (case_id, case_id, BANK))


def update(db, case_id, revision, signature, *, reconcile):
    keys = (
        (signature["payer"], signature["reference"], signature["settlement"]) if signature["reference"] else None,
        (signature["installment"]["key"],) if signature["installment"]["key"] else None,
    )
    added = []
    for (table, columns, description, conflict), values in zip(PROJECTIONS, keys):
        fields = ",".join(("case_id", "rev", *columns))
        expected = (case_id, revision, *values) if values else None
        if reconcile:
            row = db.execute(f"SELECT {fields} FROM {table} WHERE case_id=?", (case_id,)).fetchone()
            if row is not None:
                if tuple(row) != expected:
                    raise CaseError(conflict + "，已停止本次查验。", 409)
                continue
        else:
            db.execute(f"DELETE FROM {table} WHERE case_id=?", (case_id,))
        if expected:
            params = ",".join("?" for _ in expected)
            db.execute(f"INSERT INTO {table}({fields}) VALUES({params})", expected)
            added.append(description)
    return added
