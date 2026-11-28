"""Compare what two issued workpapers say about the same contract, inspection or payment."""

from collections import Counter, defaultdict
from datetime import date
import re

from config import CaseError
from advance_guarantee import rectangles
from inspection_coverage import split
from installment_approval import printed_date
from performance import DATE_LABELS
from substitution_dates import CLAUSES, DECISIONS, INDICATION, PRIOR, RELATION, filing_objections
from warranty_dates import RECEIPT, read_date


RULES = {"H01", "H02", "H03", "H04", "H05", "H06", "H07"}
SHA256 = re.compile(r"[a-f0-9]{64}")
DATED_REGISTERS = ("inspection-coverage-v5","inspection-coverage-v6")
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
        self.policy = report["policy"]
        self.register = graph.get("inspection_coverage_sources", {})
        self.calls = defaultdict(list)
        for page in (report.get("calls") or {}).get("pages", []):
            self.calls[page.get("doc"), page.get("page")].append(page)
        self.register_edges = {(e["type"], e["from"], e["to"], tuple(e["evidence"])) for e in graph["edges"]
                               if e["type"] in ("inspection_coverage_source", RELATION)}
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

    def checked_page(self, doc, page):
        page_id = f"{doc}/p{page}"
        node = self.nodes.get(page_id, {})
        calls = self.calls[doc, page]
        if (len(calls) == 1 and node.get("type") == "page" and node.get("layer") == "text"
                and ("contains", doc, page_id) in self.links and SHA256.fullmatch(node.get("sha256") or "")
                and calls[0].get("page_sha256") == node["sha256"] and calls[0].get("response_id")
                and (calls[0].get("check") or {}).get("response_id") not in (None, "", calls[0]["response_id"])):
            return calls[0]

    def register_line(self, finding, row, role):
        ref, doc, page, line = row["id"], row["doc"], row["page"], row["line"]
        page_id = f"{doc}/p{page}"
        source, call = self.document(row["unit"]), self.checked_page(doc, page)
        boxes = (call or {}).get("delivery_register_rects", {}).get(str(line))
        node = self.nodes.get(ref, {})
        refs = [page_id, *row["facts"]]
        if (row["unit"] != doc or doc not in self.kinds.get(role, ()) or doc not in finding["scope"]
                or not source or type(line) is not int or line < 1 or row["disputed"] or not rectangles(boxes)
                or ref != f"inspection-line/{page_id}/l{line}"
                or node != {"id":ref,"type":"inspection_line","doc":doc,"page":page,"line":line,"label":row["quote"]}
                or ("inspection_coverage_source", page_id, ref, tuple(refs)) not in self.register_edges
                or any(r not in finding["evidence"] or ("supports_result", r, "finding/"+finding["id"]) not in self.links
                       for r in [ref, *refs])):
            return None
        return (source, call["page_sha256"], page, line, row["quote"], boxes), {
            "ref":ref, "doc":doc, "name":self.docs[doc]["name"], "page":page, "line":line, "text":row["quote"]}

    def approval_evidence(self, finding, originals):
        edition = self.policy.get("inspection_coverage")
        methods = self.policy.get("code_sha256") or {}
        if (finding["rule"] not in ("H02", "H04", "H05") or not finding.get("delivery_register") or finding.get("substitution_review")
                or edition not in ("inspection-coverage-v4", *DATED_REGISTERS) or self.register.get("format") != edition
                or self.register.get("purpose") != "delivery_register" or not SHA256.fullmatch(methods.get("inspection_coverage.py") or "")):
            return None
        lines, keys = {}, {}
        event = "payment" if finding["rule"] == "H05" else "acceptance"
        field, role = ("paid_on", "bank_receipt") if event == "payment" else ("accepted_on", "acceptance")
        for row in self.register["rows"]:
            if row["kind"] != "substitution" or row["id"] not in finding["delivery_register"]:
                continue
            slot = "condition" if row["doc"] in self.kinds.get("contract", ()) else "decision"
            kind = "contract" if slot == "condition" else "contract_addendum"
            source = self.register_line(finding, row, kind)
            if slot in lines or not source:
                return None
            keys[slot], lines[slot] = source
        if lines.keys() != {"condition","decision"}:
            return None
        if edition=="inspection-coverage-v6":
            unit = lines["decision"]["doc"]
            filed = [p["substitution_decision"] for p in self.register.get("pages",()) if p["unit"]==unit and p.get("substitution_decision")]
            if len(filed)!=1 or filing_objections(self.facts.values(),unit,filed[0]):
                return None
        units = set(finding["scope"]).intersection(self.kinds.get(role, ()))
        dates = [f for ref in dict.fromkeys(finding["evidence"]) if (f := self.facts.get(ref)) and f["field"] == field
                 and f.get("unit", f["doc"]) in units]
        if len(dates) != 1 or dates[0]["id"] not in originals:
            return None
        fact = dates[0]
        call = self.checked_page(fact["doc"], fact["page"])
        business_day = read_date(fact, DATE_LABELS[field], RECEIPT)
        if not call or not business_day:
            return None
        _, row = originals[fact["id"]]
        lines["event"] = {k:row[k] for k in ("ref","doc","name","page","line","text")}
        keys["event"] = (self.document(fact.get("unit",fact["doc"])), call["page_sha256"], row["page"], row["line"],
                         row["text"], fact["source_line"]["rects"])
        record = finding.get("substitution_dates")
        if record is not None:
            label, condition = split(lines["condition"]["text"])
            heading, decision = split(lines["decision"]["text"])
            prior, stated = PRIOR.fullmatch(condition), INDICATION.fullmatch(decision)
            refs = tuple(lines[k]["ref"] for k in ("condition","decision","event"))
            if (edition not in DATED_REGISTERS or not SHA256.fullmatch(methods.get("substitution_dates.py") or "") or not prior or not stated
                    or label not in CLAUSES or heading not in DECISIONS
                    or record.get("event") != event or record.get("event_on") != business_day["iso"]
                    or (record.get("condition"),record.get("decision"),record.get("date_ref")) != refs
                    or record.get("unit") != lines["decision"]["doc"] or record.get("issuer") != stated[1]
                    or (record.get("replacement"),record.get("original")) != prior.groups() or prior.groups() != stated.groups()[2:]
                    or not (day := printed_date(stated[2])) or record.get("stated_on") != day
                    or (RELATION, refs[1], refs[2], refs) not in self.register_edges):
                return None
            days = (date.fromisoformat(business_day["iso"]) - date.fromisoformat(day)).days
            if record.get("days") != days or record.get("order") != ("before" if days < 0 else "after" if days > 0 else "same_day"):
                return None
        return {"keys":keys, "lines":lines, "dated":record is not None}

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
                "recorded": recorded, "instrument": instrument, "approval": self.approval_evidence(f, originals) if valid else None}


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
    filing = f.get("substitution_review") or {}
    fields = PRIORITY[f["rule"]]
    board = f.get("effect_review", {}).get("board_decision")
    quality = f.get("payment_quality", {}).get("fields", {})
    retest = f.get("retest_reference", {}).get("fields", {})
    if filing:
        preferred = [o["ref"] for o in filing["objections"] if o["ref"] in item["originals"] and item["originals"][o["ref"]][1]["status"]=="disputed"] + preferred
    elif retest:
        preferred = [retest[k] for k in ("citation","original_acceptance_number","final_acceptance_number","paid_on","clause") if k in retest]
    elif quality:
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
    limit = 4 if quality or retest else 3
    preview = sources[:limit]
    if preview and not any(s["different"] for s in preview):
        changed = next((s for s in sources[limit:] if s["different"]), None)
        if changed:
            preview[-1] = changed
    return {"id": f["id"], "rule": f["rule"], "title": f["title"], "status": f["status"], "detail": f["detail"], "basis": f.get("basis"),
            "stage": stage.get("name"), "instrument": item["instrument"], "source_count": len(sources), "sources": preview,
            "certificate": bool(((f.get("warranty_check") or {}).get("certificate") or {}).get("records")),
            "board_decision": bool(board and board["records"]), "payment_quality": bool(quality), "retest_reference": bool(retest),
            "inspection_use": bool(f.get("inspection_use"))}


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
    row = {"id": "new-"+new["id"] if new else "old-"+old["id"], "earlier": old, "later": new, "changes": changes}
    previous = older and older["approval"]
    current = newer and newer["approval"]
    same = bool(previous and current and previous["keys"] == current["keys"])
    for column, proof, other in ((old,previous,current),(new,current,previous)):
        if proof and (proof["dated"] or same and other["dated"]):
            column["approval_dates"] = {"recorded":proof["dated"], "sources":proof["lines"]}
    if same and (previous["dated"] or current["dated"]):
        row["shared_approval_lines"] = {"recorded_in": [s for s,p in (("earlier",previous),("later",current)) if p["dated"]]}
    return row


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
