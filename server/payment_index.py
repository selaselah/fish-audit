"""Keep the two searchable projections of a bank workpaper consistent with its archived facts."""

from config import BANK, CaseError
from payment_notes import pending_notes
from payment_reference import FORMAT, check


PROJECTIONS = (
    ("payment_index", ("payer", "reference", "settlement", "reference_eligible"), "流水", "历史付款索引与已签收底稿中的原文不一致"),
    ("contract_payments", ("contract_key",), "合同付款", "累计付款索引与历史合同及收付主体的原文不一致"),
)


def prepare_reference_column(db):
    if "reference_eligible" in {r[1] for r in db.execute("PRAGMA table_info(payment_index)")}:
        return False
    db.execute("ALTER TABLE payment_index ADD COLUMN reference_eligible INTEGER CHECK(reference_eligible IN (0,1))")
    return True


def install(db, *, new_column):
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
    if version < 8 or new_column or required - existing:
        if version < 8:
            db.execute("UPDATE payment_index SET reference_eligible=NULL WHERE reference_eligible IS NOT NULL")
        db.execute("INSERT OR IGNORE INTO payment_index_pending SELECT id FROM cases WHERE profile=? AND rev>0", (BANK,))
        if version < 8:
            db.execute("PRAGMA user_version=8")


def checked_references(db, case_id, paper, *, compare_as=FORMAT):
    graph = paper["graph"]
    def text(doc,page):
        row = db.execute("SELECT text FROM pages WHERE case_id=? AND doc=? AND number=?", (case_id,doc,page)).fetchone()
        if row is None:
            raise ValueError("缺少回单流水说明所在的归档文字层")
        return row[0]
    try:
        return check(graph,paper["policy"],text,compare_as=compare_as)
    except (KeyError,TypeError,ValueError) as exc:
        raise CaseError("回单流水的原文或完整性核验记录不符，请核对来源。",409) from exc


class LegacyPartialTransfer(CaseError):
    def __init__(self, case_id, revision, fields, peer, *, historical=False):
        self.case_id,self.revision,self.fields = case_id,revision,fields
        action = "请退回补件并核对完整流水。" if peer else "请保留本版并重新审计，核对完整流水。"
        detail = "旧版累计金额引用了历史回单上的部分流水号。" if historical else "旧版底稿将含遮盖位或仅列尾号的回单用于流水核对。"
        if pending_notes(fields):
            detail = "所据回单的流水展示说明仍待核图，旧版底稿已将该流水用于比对或累计。"
        super().__init__(detail+action,409)


def pending_signed(db, case_id):
    return db.execute("""SELECT c.id,c.rev FROM payment_index_pending p
                      CROSS JOIN cases c ON c.id=p.case_id
                      CROSS JOIN signoffs s ON s.case_id=c.id AND s.rev=c.rev
                      WHERE c.workspace=(SELECT workspace FROM cases WHERE id=?) AND c.id<>?
                      AND c.profile=? AND c.status IN ('closed','in_review')""", (case_id, case_id, BANK))


def update(db, case_id, revision, signature, *, eligible, reconcile):
    keys = (
        (signature["payer"], signature["reference"], signature["settlement"], int(eligible)) if signature["reference"] else None,
        (signature["installment"]["key"],) if signature["installment"]["key"] else None,
    )
    added = []
    for (table, columns, description, conflict), values in zip(PROJECTIONS, keys):
        fields = ",".join(("case_id", "rev", *columns))
        expected = (case_id, revision, *values) if values else None
        if reconcile:
            row = db.execute(f"SELECT {fields} FROM {table} WHERE case_id=?", (case_id,)).fetchone()
            if row is not None:
                if table=="payment_index" and row[-1] is None and expected and tuple(row)[:-1]==expected[:-1]:
                    db.execute("UPDATE payment_index SET reference_eligible=? WHERE case_id=?", (int(eligible),case_id))
                    continue
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
