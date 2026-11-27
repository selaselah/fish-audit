import unittest
from copy import deepcopy
from unittest.mock import patch

import addendum_execution as execution
from config import PERFORMANCE
from controls import execute
from performance import verify_findings
from test_acceptance_execution import by_rule, printed
from test_contract_changes import case, quantity_case
from test_mandate_execution import pdf_report
from test_payment_amendments import fixture
from test_pdf_execution import later_copy, signed_copy


def payment_case():
    return fixture()[0]


def legacy(report):
    graph = deepcopy(report["graph"])
    del graph[execution.KEY]
    graph["nodes"] = [n for n in graph["nodes"] if n["type"] != "addendum_pdf_inspection"]
    graph["edges"] = [e for e in graph["edges"] if e["type"] != "addendum_pdf_source"]
    policy = dict(report["policy"], version="2026.11.27.07")
    del policy["addendum_pdf"]
    with patch("controls.RULE_VERSION", policy["version"]):
        findings = execute(graph, PERFORMANCE)
    return {"graph": graph, "policy": policy, "findings": findings}


class AddendumExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = printed(case(), "d02")
        cls.signed = signed_copy(cls.raw)

    def test_supplement_is_independent_of_the_supported_main_contract(self):
        for variant in (case, quantity_case, payment_case):
            with self.subTest(variant=variant.__name__):
                report, read = pdf_report(printed(variant(), "d02"), fixture=variant)
                old = legacy(report)
                h01, = by_rule(report, "H01")
                self.assertEqual(h01["status"], "ok")
                proof, = report["graph"][execution.KEY]["records"]
                self.assertEqual((proof["unit"], proof["state"]), ("d02", "typeset"))
                facts = {f["id"]: f for f in report["graph"]["facts"]}
                self.assertEqual({facts[ref]["field"] for ref in proof["fields"]}, {"buyer_signature", "seller_signature"})
                affected = [f for f in report["findings"] if proof["id"] in f["evidence"]]
                self.assertTrue(affected)
                self.assertTrue(all(f["status"] != "ok" for f in affected))
                self.assertNotIn(proof["id"], h01["evidence"])
                if variant is payment_case:
                    changes = [f["payment_change"] for f in affected if f.get("payment_change")]
                    self.assertTrue(changes)
                    self.assertTrue(all(c["applies"] == "pending" for c in changes))
                else:
                    changes = [by_rule(report, "H02")[0]["quality_change"]]
                    self.assertEqual(changes[0]["state"], "pending")
                    self.assertIsNone(changes[0]["applied_criterion"])
                self.assertTrue(all(c["execution"] == [proof["id"]] and c["effective_on"] is None for c in changes))
                verify_findings(report)
                execution.verify(report, read, signing=True)
                execution.verify(old, read)
                with self.assertRaisesRegex(ValueError, "重审"):
                    execution.verify(old, read, signing=True)

    def test_version_coverage_has_its_own_evidence_and_status(self):
        self.assertIn(b"/Producer (ReportLab", self.signed)
        for raw, state in ((printed(case(), "d02", mark=True), "visual"), (self.signed, "current"),
                           (later_copy(self.signed), "earlier"),
                           (self.signed.replace(b"/Producer (ReportLab", b"/Producer (ReporXLab", 1), "mismatch")):
            with self.subTest(state=state):
                report, read = pdf_report(raw, fixture=case)
                record, = report["graph"][execution.KEY]["records"]
                finding, = by_rule(report, "H02")
                self.assertEqual(record["state"], state)
                self.assertEqual(finding["quality_change"]["state"], "pending")
                self.assertEqual(finding["status"], "risk" if state == "mismatch" else "missing")
                self.assertEqual(by_rule(report, "H01")[0]["status"], by_rule(legacy(report), "H01")[0]["status"])
                execution.verify(report, read)

    def test_physical_evidence_and_rule_binding_are_rechecked(self):
        report, read = pdf_report(self.raw, fixture=case)
        for damaged in ("hash", "state", "page", "fields", "edge", "marker", "method", "version"):
            with self.subTest(damaged=damaged):
                altered = deepcopy(report)
                graph, policy = altered["graph"], altered["policy"]
                record, = graph[execution.KEY]["records"]
                if damaged == "hash": record["original_sha256"] = "0" * 64
                if damaged == "state": record["state"] = "current"
                if damaged == "page": record["pages"][0]["ref"] = "d01/p1"
                if damaged == "fields": record["fields"].clear()
                if damaged == "edge": graph["edges"] = [e for e in graph["edges"] if e["type"] != "addendum_pdf_source"]
                if damaged == "marker": del policy["addendum_pdf"]
                if damaged == "method": policy["code_sha256"] = {}
                if damaged == "version": policy["version"] = "2026.11.27.07"
                with self.assertRaises(ValueError): execution.verify(altered, read)
        proof = by_rule(report, "H02")[0]["quality_change"]
        proof["execution"] = ["addendum-pdf/d01"]
        with self.assertRaises(ValueError): verify_findings(report)
