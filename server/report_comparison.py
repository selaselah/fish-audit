"""Compare what two issued workpapers say about the same contract, inspection or payment."""

from collections import Counter
import re

from config import CaseError
from advance_guarantee import rectangles


RULES = {"H01", "H02", "H03", "H04", "H05", "H06", "H07"}
SHA256 = re.compile(r"[a-f0-9]{64}")
PRIORITY = {
    "H01": ("effect_clause", "buyer_signature", "seller_signature", "effect_on"),
    "H02": ("acceptance_result", "measured_result", "acceptance_signer", "accepted_on"),
    "H03": ("payment_stage", "payment_term"),
    "H04": ("payment_stage", "acceptance_result", "warranty_release"),
    "H05": ("paid_on", "payment_designation", "warranty_release", "payment_stage"),
    "H06": ("payment_stage", "payment_designation", "paid_on"),
    "H07": ("warranty_defects", "warranty_ticket_state", "warranty_ticket_id"),
}


class IssuedFindings:
    def __init__(self, bundle):
        report = bundle["report"]
        self.meta = {"rev": bundle["rev"], "sha256": bundle["sha256"], "created": bundle["created"],
                     "rules": report["policy"]["version"], "verdict": report["result"]["verdict"]}
        graph = report["graph"]
        self.docs = {d["id"]: d for d in graph["documents"]}
        self.units = {d["id"]: d for d in graph.get("audit_documents", graph["documents"])}
        self.nodes = {n["id"]: n for n in graph["nodes"]}
        self.facts = {f["id"]: f for f in graph["facts"]}
        self.kinds = graph["documents_by_kind"]
        self.section_parents = {(e["from"], e["to"], e["evidence"][0]) for e in graph["edges"]
                                if e["type"] == "contains_section" and len(e["evidence"]) == 1}
        self.links = {(e["type"], e["from"], e["to"]) for e in graph["edges"]
                      if e["type"] in ("records", "contains", "section_page", "supports_result") and
                      e["evidence"] == [e["from"] if e["type"] == "supports_result" else e["to"]]}
        self.findings = [self.read(f) for f in report["findings"] if f["rule"] in RULES]

    def document(self, unit):
        entry = self.units.get(unit)
        if not entry:
            return None
        source = entry.get("source", unit)
        doc = self.docs.get(source)
        node = self.nodes.get(source, {})
        if not doc or node.get("type") != "document" or not SHA256.fullmatch(doc.get("sha256") or "") or node.get("sha256") != doc["sha256"]:
            return None
        page = entry.get("page")
        if page is None:
            return (source, doc["sha256"], 0) if unit == source else None
        page_id = f"{source}/p{page}"
        section = self.nodes.get(unit, {})
        page_node = self.nodes.get(page_id, {})
        if (type(page) is not int or page < 1 or section.get("type") != "document_section"
                or section.get("source") != source or section.get("page") != page
                or page_node.get("type") != "page" or not SHA256.fullmatch(page_node.get("sha256") or "")
                or (source, unit, page_id) not in self.section_parents or ("section_page", unit, page_id) not in self.links
                or ("contains", source, page_id) not in self.links):
            return None
        return source, doc["sha256"], page

    def source(self, fact, finding):
        ref, doc, page = fact["id"], fact["doc"], fact["page"]
        page_id = f"{doc}/p{page}"
        page_node = self.nodes.get(page_id, {})
        observed = self.nodes.get(ref, {})
        line = fact.get("source_line") or {}
        unit = fact.get("unit", doc)
        original = self.document(unit)
        if (not ref.startswith(page_id+"/") or not original or original[0] != doc or original[1] != fact.get("source_sha256") or original[2] not in (0, page)
                or page_node.get("type") != "page" or page_node.get("layer") != "text"
                or not SHA256.fullmatch(page_node.get("sha256") or "") or page_node["sha256"] != fact.get("page_sha256")
                or observed.get("type") != "observation" or observed.get("status") != fact["status"]
                or type(line.get("number")) is not int or line["number"] < 1 or not rectangles(line.get("rects")) or not line.get("text")
                or ("contains", doc, page_id) not in self.links or ("records", page_id, ref) not in self.links
                or ("supports_result", ref, "finding/"+finding["id"]) not in self.links):
            return None
        identity = (*original, page, line["number"], line["text"])
        reading = (*identity, fact["field"], fact["status"], fact["value"], fact["quote"])
        return reading, {"ref": ref, "doc": doc, "name": self.docs[doc]["name"], "page": page, "line": line["number"],
                         "text": line["text"], "label": fact["label"], "field": fact["field"],
                         "value": fact["value"], "quote": fact["quote"], "status": fact["status"]}

    def match_key(self, f, originals):
        def scoped(role):
            return sorted(set(self.kinds.get(role, ())).intersection(f["scope"]))

        def cited(unit):
            identity = self.document(unit)
            if not identity:
                return None
            if any(self.facts[ref].get("unit", self.facts[ref]["doc"]) == unit for ref in originals):
                return identity
            doc, _, page = identity
            ref = f"{doc}/p{page}" if page else doc
            return identity if ref in f["evidence"] and ("supports_result", ref, "finding/"+f["id"]) in self.links else None

        contracts = scoped("contract")
        if len(contracts) != 1 or not (contract := cited(contracts[0])):
            return None
        rule = f["rule"]
        if rule in ("H01", "H03"):
            return rule, contract
        if rule == "H02":
            sheets = [(role, cited(u)) for role in ("acceptance", "reinspection") for u in scoped(role)]
            return (rule, contract, tuple(sheets)) if sheets and all(identity for _, identity in sheets) else None
        if rule == "H07":
            diff = f.get("warranty_difference") or {}
            units = [diff.get("release_unit"), diff.get("ticket_unit")]
            if any(u not in scoped(role) for u, role in zip(units, ("warranty", "warranty_ticket"))):
                return None
            ids = [cited(u) for u in units]
            return (rule, contract, *ids) if all(ids) else None
        stage = f.get("stage") or {}
        clause_ref = stage.get("clause_ref")
        clause = originals.get(clause_ref)
        # Finding ordinals and observation IDs can both change after a new extraction.
        if not clause or not stage.get("name"):
            return None
        if clause[1]["field"] == "revised_payment_stage":
            change = f.get("payment_change") or {}
            unit = change.get("unit")
            base = originals.get(change.get("original_ref"))
            if (clause_ref != change.get("revised_ref") or unit not in scoped("contract_addendum")
                    or clause[0][:3] != cited(unit) or not base or base[0][:3] != contract
                    or base[1]["field"] not in ("payment_stage", "payment_term")):
                return None
        elif clause[1]["field"] not in ("payment_stage", "payment_term") or clause[0][:3] != contract:
            return None
        key = (rule, contract, clause[0][:6], stage["name"])
        if rule == "H05":
            receipts = scoped("bank_receipt")
            if len(receipts) != 1 or not (receipt := cited(receipts[0])):
                return None
            key += (receipt,)
        return key

    def read(self, f):
        node = self.nodes.get("finding/"+f["id"], {})
        valid = node.get("type") == "finding" and node.get("detail") == f["detail"] and node.get("status") == f["status"]
        originals = {}
        if valid:
            for ref in f["evidence"]:
                fact = self.facts.get(ref)
                if fact and (source := self.source(fact, f)):
                    originals[ref] = source
        metadata = {"rule", "version", "id", "title", "basis", "status", "detail", "scope", "evidence"}
        recorded = {k: stable_references(v, originals) for k, v in f.items() if k not in metadata}
        instrument = None
        role = {"H05": "bank_receipt", "H07": "warranty_ticket"}.get(f["rule"])
        candidates = set(f["scope"]).intersection(self.kinds.get(role, ()))
        if len(candidates) == 1 and (identity := self.document(candidates.pop())):
            doc, _, page = identity
            instrument = {"name": self.docs[doc]["name"], "doc": doc, "page": page or None}
        return {"finding": f, "key": self.match_key(f, originals) if valid else None, "originals": originals,
                "recorded": recorded, "instrument": instrument}


def stable_references(value, originals):
    if isinstance(value, dict):
        return {k: stable_references(v, originals) for k, v in value.items()}
    if isinstance(value, list):
        return [stable_references(v, originals) for v in value]
    if isinstance(value, str) and value in originals:
        # Use the physical line and field for a reference, independently of its transcription ordinal.
        return ("field", *originals[value][0][:7])
    return value


def side(item, other):
    f = item["finding"]
    remaining = Counter(m for m, _ in other["originals"].values()) if other else Counter()
    stage = f.get("stage") or {}
    comparison = (f.get("warranty_payment") or {}).get("comparison") or {}
    preferred = [ref for ref in (comparison.get("stated_ref"), (comparison.get("bank") or {}).get("ref"), stage.get("clause_ref")) if ref]
    fields = PRIORITY[f["rule"]]
    board = f.get("effect_review", {}).get("board_decision")
    quality = f.get("payment_quality", {}).get("fields", {})
    if quality:
        preferred = [quality[key] for key in ("acceptance_criteria","measured_result","accepted_on","paid_on","clause") if key in quality]
    elif f["rule"] == "H01" and board:
        preferred = [board["fields"][k] for k in ("effect_clause", "approval_result", "approval_signer") if k in board["fields"]]
    elif f["rule"] == "H01" and len(f.get("delegations", [])) == 1:
        grant = f["delegations"][0]
        fields = ("grant_signature", "grant_scope", grant.get("signature_field"), *fields)
    elif f["rule"] == "H02" and f["status"] == "issue" and "实测" in f["detail"]:
        fields = ("measured_result", "acceptance_criteria", "acceptance_result", *fields)
    sources = []
    for mark, row in item["originals"].values():
        sources.append({**row, "different": bool(other and remaining[mark] <= 0)})
        remaining[mark] -= 1
    sources.sort(key=lambda s: (preferred.index(s["ref"]) if s["ref"] in preferred else len(preferred),
                                not s["different"], fields.index(s["field"]) if s["field"] in fields else len(fields),
                                s["doc"], s["page"], s["line"]))
    limit = 4 if quality else 3
    preview = sources[:limit]
    if preview and not any(s["different"] for s in preview):
        changed = next((s for s in sources[limit:] if s["different"]), None)
        if changed:
            preview[-1] = changed
    return {"id": f["id"], "rule": f["rule"], "title": f["title"], "status": f["status"], "detail": f["detail"], "basis": f.get("basis"),
            "stage": stage.get("name"), "instrument": item["instrument"], "source_count": len(sources), "sources": preview,
            "certificate": bool(((f.get("warranty_check") or {}).get("certificate") or {}).get("records")),
            "board_decision": bool(board and board["records"]), "payment_quality": bool(quality)}


def pair(older, newer):
    old = side(older, newer) if older else None
    new = side(newer, older) if newer else None
    changes = []
    if old and new:
        for field in ("status", "detail", "basis"):
            if old[field] != new[field]:
                changes.append(field)
        if Counter(m for m, _ in older["originals"].values()) != Counter(m for m, _ in newer["originals"].values()):
            changes.append("citations")
        if older["recorded"] != newer["recorded"]:
            changes.append("records")
    return {"id": "new-"+new["id"] if new else "old-"+old["id"], "earlier": old, "later": new, "changes": changes}


def compare(case_id, earlier, later):
    if not 0 < earlier["rev"] < later["rev"] or any(b["report"]["case_id"] != case_id for b in (earlier, later)):
        raise CaseError("请选择同一案件先后出具的两版底稿。", 400)
    old, new = IssuedFindings(earlier), IssuedFindings(later)
    counts = [Counter(i["key"] for i in rev.findings) for rev in (old, new)]
    matching = {key for key in counts[0] if key and counts[0][key] == counts[1][key] == 1}
    older = {i["key"]: i for i in old.findings if i["key"] in matching}
    rows = [pair(older.get(i["key"]), i) for i in new.findings]
    rows.extend(pair(i, None) for i in old.findings if i["key"] not in matching)
    return {"format": "contract-revision-comparison-v1", "case_id": case_id, "earlier": old.meta, "later": new.meta, "rows": rows}
