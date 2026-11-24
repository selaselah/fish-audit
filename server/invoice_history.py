"""Compare the signed invoice observations available to an auditor at two points in time."""

from config import CaseError


INDEX_FIELDS = ("case_id","rev","doc","fact","page","number_key","quote","source_hash","page_hash","document_kind")


def install_index_guard(db):
    """Track changed projections; upgrades also check the latest pre-existing workpapers."""
    triggers = (("invoice_index","insert",("NEW",)),("invoice_index","delete",("OLD",)),
                ("invoice_index","update",("OLD","NEW")),("reports","insert",("NEW",)),("reports","update",("OLD","NEW")))
    names = {f"invoice_check_{table}_{operation}" for table,operation,_ in triggers} | {"invoice_index_pending"}
    installed = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','trigger')")}
    db.execute("""CREATE TABLE IF NOT EXISTS invoice_index_pending(case_id TEXT NOT NULL,rev INTEGER NOT NULL,
               PRIMARY KEY(case_id,rev)) WITHOUT ROWID""")
    for table,operation,versions in triggers:
        steps = " ".join(f"""INSERT OR IGNORE INTO invoice_index_pending(case_id,rev)
                            VALUES({source}.case_id,{source}.rev);""" for source in versions)
        db.execute(f"""CREATE TRIGGER IF NOT EXISTS invoice_check_{table}_{operation}
                   AFTER {operation} ON {table} BEGIN {steps} END""")
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version<5 or names-installed:
        db.execute("""INSERT OR IGNORE INTO invoice_index_pending
                   SELECT r.case_id,r.rev FROM reports r JOIN cases c ON c.id=r.case_id AND c.rev=r.rev""")
        if version<5:
            db.execute("PRAGMA user_version=5")


def pending_signed_indexes(db,case_id):
    return db.execute("""SELECT p.case_id,p.rev FROM invoice_index_pending p
                      CROSS JOIN cases c ON c.id=p.case_id AND c.rev=p.rev
                      CROSS JOIN signoffs s ON s.case_id=p.case_id AND s.rev=p.rev
                      WHERE c.workspace=(SELECT workspace FROM cases WHERE id=?) AND c.id<>?
                      AND c.status IN ('closed','in_review')""",(case_id,case_id))


class InvoiceHistoryChanged(CaseError):
    def __init__(self, differences, peer):
        self.differences = differences
        next_step = ("请退回补件，沿用原件重审后核对前案。" if peer else "请保留本版并重新审计，核对前案后再决定。")
        super().__init__("本版出具后，同票签收记录发生变化。"+next_step,409)


def indexed_invoices(db,case_id,keys):
    if not keys:
        return []
    placeholders = ",".join("?" for _ in keys)
    rows = db.execute(f"""SELECT i.*,c.title,s.decision,r.hash AS report_hash,f.rev AS peer_source_rev,
                      EXISTS(SELECT 1 FROM attestations a WHERE a.case_id=i.case_id AND a.fact=i.fact
                             AND a.rev<i.rev AND a.source_check IS NOT NULL) AS checked_field FROM invoice_index i
                      JOIN cases c ON c.id=i.case_id AND c.rev=i.rev
                      JOIN signoffs s ON s.case_id=i.case_id AND s.rev=i.rev
                      JOIN reports r ON r.case_id=i.case_id AND r.rev=i.rev
                      LEFT JOIN case_referrals f ON f.case_id=i.case_id AND f.resolved_rev=i.rev
                      WHERE c.workspace=(SELECT workspace FROM cases WHERE id=?) AND c.status IN ('closed','in_review')
                      AND c.id<>? AND i.number_key IN ({placeholders})
                      ORDER BY i.case_id,i.rev,i.fact""",(case_id,case_id,*keys))
    return [dict(row) for row in rows]


def differences(previous,current):
    def by_field(rows):
        return {(row["case_id"],row["fact"],row["number_key"]):row for row in rows}
    def reference(row):
        if row:
            return {key:row[key] for key in ("case_id","rev","fact","title","quote","decision")}
        return None
    before,after = by_field(previous),by_field(current)
    fields = (*INDEX_FIELDS,"decision","report_hash","peer_source_rev")
    changes = []
    for key in sorted(before.keys() | after.keys()):
        old,new = before.get(key),after.get(key)
        if (old and new and all(old.get(field)==new.get(field) for field in fields)
                and ("signoff_hash" not in old or old["signoff_hash"]==new["signoff_hash"])
                and ("source" not in old or old["source"]==new["source"])):
            continue
        changes.append({"previous":reference(old),"current":reference(new)})
    return changes
