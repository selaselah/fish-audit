import copy
import sys
import unittest
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.writer import PageObject, PdfFileWriter

from controls import VERSION
from pdf_execution import FORMAT, inspect_original, source_graph, sources, verify
from performance import compute
from test_performance import BANK_DOC, CONTRACT, RECEIPT, material

with patch.object(sys, "path", [str(Path(__file__).resolve().parents[2] / "docs" / "samples"), *sys.path]):
    from pdf_signing import later_copy, signed_copy


class PdfExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = BytesIO()
        writer = PdfFileWriter()
        content = writer.add_object(generic.StreamObject(stream_data=b"% synthetic fixture A"))
        writer.insert_page(PageObject(content, (0, 0, 300, 400)))
        writer.write(out)
        cls.plain = out.getvalue()
        cls.signed = signed_copy(cls.plain)
        cls.later = later_copy(cls.signed)

    def paper(self, raw, *, visual=False):
        graph = material([CONTRACT, RECEIPT, BANK_DOC])
        doc = graph["documents"][0]
        doc.update(ext=".pdf", sha256=sha256(raw).hexdigest())
        graph["contract_effect_sources"]["pages"][0]["text_only"] = not visual
        ledger = sources(graph, lambda d: raw)
        graph["pdf_execution_sources"] = ledger
        nodes, edges = source_graph(ledger)
        graph["nodes"].extend(nodes)
        graph["edges"].extend(edges)
        return {"graph": graph, "policy": VERSION, "findings": compute(graph)}

    def test_checked_transcription_is_distinct_from_signing(self):
        paper = self.paper(self.plain)
        check, acceptance, plan, *payments = paper["findings"]
        execution = check["effect_review"]["pdf_execution"]
        self.assertEqual((execution["state"], check["status"], acceptance["status"], plan["status"]),
                         ("typeset", "missing", "ok", "ok"))
        self.assertEqual(len(execution["rows"]), 2)
        self.assertIn(execution["source"], check["evidence"])
        self.assertTrue(all(p["status"] != "ok" and execution["source"] in p["evidence"]
                            for p in payments if p["rule"] in ("H04", "H05")))
        self.assertEqual(self.paper(self.plain, visual=True)["findings"][0]["effect_review"]["pdf_execution"]["state"], "visual")

    def test_cryptographic_integrity_and_later_version(self):
        state, (whole,) = inspect_original(self.signed)
        self.assertEqual((state, whole["coverage"], whole["ends_at"]), ("current", "ENTIRE_FILE", len(self.signed)))
        state, (prior,) = inspect_original(self.later)
        self.assertEqual((state, prior["coverage"], prior["ends_at"]), ("earlier", "ENTIRE_REVISION", len(self.signed)))
        self.assertEqual(whole["certificate_sha256"], prior["certificate_sha256"])
        for raw in (self.signed, self.later):
            self.assertEqual(self.paper(raw)["findings"][0]["status"], "missing")
        state, rows = inspect_original(signed_copy(self.signed, "SecondSyntheticSignature"))
        self.assertEqual((state, [r["state"] for r in rows]), ("current", ["earlier", "current"]))

    def test_damaged_signed_document_is_flagged_from_the_actual_bytes(self):
        self.assertEqual(self.signed.count(b"synthetic fixture A"), 1)
        damaged = self.signed.replace(b"synthetic fixture A", b"synthetic fixture B")
        state, (entry,) = inspect_original(damaged)
        self.assertEqual((state, entry["state"]), ("mismatch", "mismatch"))
        self.assertEqual(self.paper(damaged)["findings"][0]["status"], "risk")

    def test_inconclusive_inputs_and_integrity_failure(self):
        self.assertEqual(inspect_original(b"unreadable synthetic fixture"), ("review", []))
        for outcome in ((False, True), (True, False)):
            with patch("pyhanko.sign.validation.generic_cms.validate_sig_integrity", return_value=outcome):
                check = self.paper(self.signed)["findings"][0]
                self.assertEqual((check["status"], check["effect_review"]["pdf_execution"]["state"]), ("risk", "mismatch"))

    def test_verification_uses_original_and_checks_membership(self):
        paper = self.paper(self.later)
        verify(paper, lambda doc: self.later)
        with self.assertRaises(ValueError):
            verify(paper, lambda doc: self.signed)
        for change in ("certificate", "node", "edge", "unit", "marker"):
            changed = copy.deepcopy(paper)
            ledger = changed["graph"]["pdf_execution_sources"]
            if change == "certificate":
                ledger["documents"][0]["signatures"][0]["certificate_sha256"] = "a" * 64
            if change == "unit":
                ledger["documents"][0]["units"].append("d02")
            if change in ("edge", "node"):
                changed["graph"][change + "s"].pop()
            if change == "marker":
                changed["policy"].pop("pdf_execution")
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify(changed, lambda doc: self.later)
        graph = paper["graph"]
        graph["documents"][1]["ext"] = ".pdf"
        self.assertEqual(sources(graph, lambda doc: self.later)["documents"][0]["units"], ["d01"])
        graph["audit_documents"] = [{"id": "d01/contract", "source": "d01", "page": 1},
                                    {"id": "d01/receipt", "source": "d01", "page": 2}]
        graph["documents_by_kind"]["contract"] = ["d01/contract"]
        self.assertEqual(sources(graph, lambda doc: self.later)["documents"][0]["units"], ["d01/contract"])

    def test_legacy_approval_requires_current_evidence(self):
        paper = self.paper(self.plain)
        del paper["graph"]["pdf_execution_sources"]
        paper["policy"] = {"version": "2026.11.26.13"}
        paper["findings"][0]["status"] = "ok"
        verify(paper, None)
        with self.assertRaisesRegex(ValueError, "重审"):
            verify(paper, None, signing=True)
        paper["policy"] = dict(VERSION)
        self.assertEqual(paper["policy"]["pdf_execution"], FORMAT)
        with self.assertRaisesRegex(ValueError, "不符"):
            verify(paper, lambda d: self.plain)
