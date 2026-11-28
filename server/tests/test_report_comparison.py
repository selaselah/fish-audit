import unittest
from copy import deepcopy
from hashlib import sha256

from config import CaseError, PERFORMANCE
from controls import execute
from graph import link_procedures
from report_comparison import compare
import inspection_coverage as inspection
import substitution_dates
from test_delivery_register import dated
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material
from test_receipt_packets import packet


CID = "c" * 32


def digest(text):
    return sha256(text.encode()).hexdigest()


def bundle(graph, findings, revision):
    g, fs = deepcopy(graph), deepcopy(findings)
    for doc in g["documents"]:
        doc["sha256"] = digest(doc["id"])
    for n in g["nodes"]:
        if n["type"] in ("document", "page"):
            n["sha256"] = digest(n["id"])
    for f in g["facts"]:
        f["source_sha256"] = digest(f["doc"])
        f["page_sha256"] = digest(f"{f['doc']}/p{f['page']}")
    link_procedures(g, fs, {"expert": {"model": "fixture"}, "pages": []})
    return {"rev": revision, "sha256": digest(str(revision)), "created": str(revision), "report": {
        "case_id": CID, "policy": {"version": str(revision)}, "result": {"verdict": "review"}, "graph": g, "findings": fs}}


def replace_refs(value, names):
    if isinstance(value, list):
        return [replace_refs(v, names) for v in value]
    if isinstance(value, dict):
        return {k: replace_refs(v, names) for k, v in value.items()}
    return names.get(value, value) if isinstance(value, str) else value


def approval_bundle(revision, edition):
    paper, read = dated()
    g = paper["graph"]
    ledger = g["inspection_coverage_sources"] = inspection.sources(g, read, version=edition)
    findings = execute(g, PERFORMANCE)
    g["edges"].extend(substitution_dates.edges(findings))
    result = bundle(g, findings, revision)
    report = result["report"]
    report["policy"].update(inspection_coverage=edition,code_sha256={
        name:digest(name) for name in ("inspection_coverage.py","substitution_dates.py")})
    report["calls"] = {"pages":[{"doc":d["id"],"page":1,"page_sha256":digest(d["id"]+"/p1"),
        "response_id":"first","check":{"response_id":"second"},
        "delivery_register_rects":{str(r["line"]):[[0,.1,.9,.2]] for r in ledger["rows"] if r["doc"]==d["id"] and r["line"]}}
        for d in g["documents"]]}
    return result


class ContractRevisionComparison(unittest.TestCase):
    def setUp(self):
        self.graph = material([CONTRACT, RECEIPT, WARRANTY, BANK_DOC, BANK_DOC])
        self.findings = execute(self.graph, PERFORMANCE)
        self.old = bundle(self.graph, self.findings, 2)

    def compare(self, current):
        return compare(CID, self.old, current)["rows"]

    def test_renumbered_fields_and_findings_match_the_same_physical_clause_and_bank(self):
        current = deepcopy(self.findings)
        banks = [f for f in current if f["rule"] == "H05"]
        self.assertEqual(len(banks), 2)
        first, second = banks
        first["id"], second["id"] = second["id"], first["id"]
        first["status"] = "risk"
        first["detail"] = "水印回单另有提前付款疑点。"
        new = bundle(self.graph, current, 3)
        clause = first["stage"]["clause_ref"]
        new = replace_refs(new, {clause: "d01/p1/f999"})
        rows = self.compare(new)
        for r in rows:
            self.assertTrue(r["earlier"] and r["later"], r["id"])
            if r["later"]["id"] == first["id"]:
                self.assertEqual(r["earlier"]["id"], second["id"])
                self.assertEqual(set(r["changes"]), {"status", "detail"})
            else:
                self.assertEqual(r["changes"], [], r["id"])

    def test_duplicate_keys_or_a_broken_clause_link_stay_separate(self):
        current = deepcopy(self.findings)
        stage = next(f for f in current if f["rule"] == "H04")
        current.append({**stage, "id": "H04-99"})
        rows = self.compare(bundle(self.graph, current, 3))
        separate = [r for r in rows if not (r["earlier"] and r["later"])]
        self.assertEqual(len(separate), 3)
        self.assertTrue(all(not r["changes"] for r in separate))
        new = bundle(self.graph, self.findings, 3)
        clause = stage["stage"]["clause_ref"]
        g = new["report"]["graph"]
        g["edges"] = [e for e in g["edges"] if not (e["type"] == "records" and e["to"] == clause)]
        rows = self.compare(new)
        later = next(r for r in rows if r["id"] == "new-"+stage["id"])
        self.assertIsNone(later["earlier"])
        self.assertNotIn(clause, [s["ref"] for s in later["later"]["sources"]])

    def test_changed_originals_and_ambiguous_receipt_scope_cannot_pair_by_ordinal(self):
        new = bundle(self.graph, self.findings, 4)
        f = next(f for f in new["report"]["findings"] if f["rule"] == "H05")
        f["scope"] = list(dict.fromkeys([*f["scope"], "d04", "d05"]))
        self.assertIsNone(next(r for r in self.compare(new) if r["id"] == "new-"+f["id"])["earlier"])
        new = bundle(self.graph, self.findings, 4)
        g = new["report"]["graph"]
        new_sha = digest("changed contract")
        next(d for d in g["documents"] if d["id"] == "d01")["sha256"] = new_sha
        next(n for n in g["nodes"] if n["id"] == "d01")["sha256"] = new_sha
        for fact in g["facts"]:
            if fact["doc"] == "d01":
                fact["source_sha256"] = new_sha
        self.assertTrue(all(not (r["earlier"] and r["later"]) for r in self.compare(new)))

    def test_acceptance_packet_requires_each_page_role_and_its_issued_section_edges(self):
        g, _ = packet()
        findings = execute(g, PERFORMANCE)
        old = bundle(g, findings, 1)
        new = bundle(g, findings, 2)
        fid = next(f["id"] for f in findings if f["rule"] == "H02")
        def row(later):
            return next(r for r in compare(CID, old, later)["rows"] if r["id"] == "new-"+fid)
        self.assertEqual(row(new)["changes"], [])
        self.assertIsNotNone(row(new)["earlier"])
        unit = "unit/file/p2"
        for edge_type in ("section_page", "contains_section"):
            broken = deepcopy(new)
            edge = next(e for e in broken["report"]["graph"]["edges"] if e["type"] == edge_type and unit in (e["from"], e["to"]))
            edge["evidence"] = ["file/p3"]
            self.assertIsNone(row(broken)["earlier"])
        roles = new["report"]["graph"]["documents_by_kind"]
        roles["acceptance"].remove(unit)
        roles["reinspection"] = [unit]
        self.assertIsNone(row(new)["earlier"])

    def test_issued_basis_can_change_independently_of_the_finding_or_the_result(self):
        findings = deepcopy(self.findings)
        contract = next(f for f in findings if f["rule"] == "H01")
        contract["basis"] = "演练程序另要求核对代理人的授权书原页。"
        row = next(r for r in self.compare(bundle(self.graph, findings, 3)) if r["id"] == "new-"+contract["id"])
        self.assertEqual(row["changes"], ["basis"])
        self.assertEqual(row["later"]["basis"], contract["basis"])
        self.assertNotEqual(row["earlier"]["basis"], row["later"]["basis"])

    def test_a_receipt_field_cannot_be_used_as_the_contract_clause_even_if_both_reports_cite_it(self):
        new = bundle(self.graph, self.findings, 3)
        for revision in (self.old, new):
            report = revision["report"]
            bank = next(f for f in report["findings"] if f["rule"] == "H05")
            source = next(f for f in report["graph"]["facts"] if f["doc"] == "d04" and f["id"] in bank["evidence"])
            source["field"] = "payment_stage"
            bank["stage"]["clause_ref"] = source["id"]
        row = next(r for r in self.compare(new) if r["id"] == "new-"+bank["id"])
        self.assertIsNone(row["earlier"])

    def test_structured_program_or_cited_reading_can_change_without_a_status_change(self):
        current = deepcopy(self.findings)
        phase = next(f for f in current if f["rule"] == "H04")
        phase["date_checks"] = [{"status": "missing", "detail": "演练待核事项"}]
        new = bundle(self.graph, current, 3)
        fact = next(f for f in new["report"]["graph"]["facts"] if f["id"] == phase["stage"]["clause_ref"])
        fact["value"] += "（新转录）"
        item = next(r for r in self.compare(new) if r["id"] == "new-"+phase["id"])
        self.assertEqual(set(item["changes"]), {"records", "citations"})
        self.assertIn(fact["source_line"]["text"], [s["text"] for s in item["later"]["sources"]])
        self.assertTrue(item["later"]["sources"][0]["different"])

    def test_only_two_issued_versions_of_the_same_case_in_order(self):
        with self.assertRaises(CaseError):
            self.compare(self.old)
        new = bundle(self.graph, self.findings, 3)
        new["report"]["case_id"] = "d"*32
        with self.assertRaises(CaseError):
            self.compare(new)

    def test_new_dated_check_keeps_the_three_earlier_citations_without_backdating_a_conclusion(self):
        old=approval_bundle(2,inspection.SUBSTITUTION_FORMAT)
        new=approval_bundle(3,substitution_dates.FORMAT)
        def payment(a,b):
            return next(r for r in compare(CID,a,b)["rows"] if r["id"]=="new-H05-8")
        r=payment(old,new)
        self.assertEqual(r["shared_approval_lines"],{"recorded_in":["later"]})
        self.assertFalse(r["earlier"]["approval_dates"]["recorded"])
        self.assertTrue(r["later"]["approval_dates"]["recorded"])
        for slot in ("condition","decision","event"):
            self.assertEqual(r["earlier"]["approval_dates"]["sources"][slot],r["later"]["approval_dates"]["sources"][slot])
        date_ref=r["later"]["approval_dates"]["sources"]["event"]["ref"]
        renamed=replace_refs(old,{date_ref:"d04/p1/f990"})
        self.assertEqual(payment(renamed,new)["shared_approval_lines"],{"recorded_in":["later"]})
        same=payment(new,{**new,"rev":4})
        self.assertEqual(same["shared_approval_lines"],{"recorded_in":["earlier","later"]})
        self.assertEqual(same["changes"],[])
        for fault in ("call","box","physical_page","support"):
            earlier=deepcopy(old);report=earlier["report"]; g=report["graph"]
            call=next(c for c in report["calls"]["pages"] if c["doc"]=="d05")
            s=r["earlier"]["approval_dates"]["sources"]["decision"]
            if fault=="call":call["check"]["response_id"]=""
            if fault=="box":call["delivery_register_rects"][str(s["line"])]=[[.1,.15,.9,.25]]
            if fault=="physical_page":call["page_sha256"]=digest("different page")
            if fault=="support":g["edges"]=[e for e in g["edges"] if (e["from"],e["to"])!=(s["ref"],"finding/H05-8")]
            changed=payment(earlier,new)
            self.assertNotIn("shared_approval_lines",changed,fault)
            self.assertNotIn("approval_dates",changed["earlier"],fault)
            self.assertTrue(changed["later"]["approval_dates"]["recorded"])
        for fault in ("direction","day","edge"):
            later=deepcopy(new); report=later["report"]
            c=next(f["substitution_dates"] for f in report["findings"] if f["rule"]=="H05")
            if fault=="direction":c["replacement"]=c["original"]
            if fault=="day":c["days"]+=1
            if fault=="edge":report["graph"]["edges"]=[e for e in report["graph"]["edges"] if e["type"]!=substitution_dates.RELATION]
            changed=payment(old,later)
            self.assertNotIn("shared_approval_lines",changed,fault)
            self.assertNotIn("approval_dates",changed["later"],fault)
