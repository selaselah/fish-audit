import copy
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from acceptance_reservations import supplier_check
from documents import prepare
import pdf_execution
import supplier_pages

ROOT = Path(__file__).resolve().parents[2]
with patch.object(sys, "path", [str(ROOT / "docs" / "samples"), *sys.path]):
    from pdf_signing import signed_copy
    from supplier_annotations import NOTE, REASON, with_comment


def report_for(raw, receipt_name=None, *, format=supplier_pages.FORMAT):
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "采购合同.pdf"
        path.write_bytes(raw)
        page, = prepare(path, 1, False)
    text = page["text"]
    line, quote = next((n, s) for n, s in enumerate(text.splitlines(), 1) if s.startswith("供应方："))
    name = quote.split("：", 1)[1]
    doc = {"id": "d01", "ext": ".pdf", "sha256": supplier_pages.digest(raw), "name": "采购合同.pdf"}
    source = {"number": line, "text": quote, "rects": page["layer"]["lines"][str(line)]}
    field = {"id": "d01/p1/f1", "field": "seller", "value": name, "quote": quote, "doc": "d01", "page": 1,
             "source_line": source, "source_sha256": doc["sha256"], "page_sha256": page["sha256"], "status": "anchored"}
    receipt_name = receipt_name or name
    other = {**field, "id": "d02/p1/f1", "doc": "d02", "value": receipt_name, "quote": "供应方：" + receipt_name}
    node = {"id": "d01/p1", "type": "page", "sha256": page["sha256"], "text_sha256": supplier_pages.digest(text.encode())}
    place = {"doc": "d01", "page": 1, "unit": "d01", "role": "contract", "native": True, "text_only": False}
    receipt = {**place, "doc": "d02", "unit": "d02", "role": "receipt", "text_only": True}
    lines = [{**p, "kind": "seller", "line": line, "quote": f["quote"], "facts": [f["id"]]} for p, f in ((place, field), (receipt, other))]
    graph = {"documents": [doc, {"id": "d02"}], "documents_by_kind": {"contract": ["d01"], "acceptance": ["d02"]},
             "nodes": [node], "edges": [], "facts": [field, other],
             "acceptance_reservation_sources": {"supplier_pages": [place, receipt], "supplier_rows": lines}}
    graph["pdf_execution_sources"] = pdf_execution.sources(graph, lambda d: raw)
    graph["supplier_page_sources"] = ledger = supplier_pages.sources(graph, lambda d: raw, format)
    nodes, edges = supplier_pages.source_graph(ledger)
    graph["nodes"].extend(nodes)
    graph["edges"].extend(edges)
    version = supplier_pages.NOTES_SINCE if format == supplier_pages.FORMAT else supplier_pages.SINCE
    return {"graph": graph, "policy": {"version": version, "supplier_page_inspection": format}}


def check(report):
    graph = report["graph"]
    return supplier_check(graph["acceptance_reservation_sources"], {"d01", "d02"}, graph)


class SupplierPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plain, cls.signed, cls.later = [(ROOT / "frontend" / "showcase" / f"signature-{mode}.pdf").read_bytes()
                                             for mode in ("typeset", "current", "earlier")]

    def test_current_and_later_revisions_repeat_the_original_print(self):
        for raw in (self.signed, self.later):
            report = report_for(raw)
            page, = report["graph"]["supplier_page_sources"]["pages"]
            self.assertEqual((page["state"], page["annotations"][0]["kind"], page["count"]), ("same_print", "signature_field", 1))
            original = page["comparison"]
            self.assertEqual((original["ends_at"], original["original_sha256"]), (len(self.plain), supplier_pages.digest(self.plain)))
            self.assertEqual(original["first_page_sha256"], page["page_sha256"])
            self.assertEqual(original["text_sha256"], original["first_text_sha256"])
            self.assertEqual(check(report)["matching_print"], [page["id"]])
            self.assertEqual(check(report)["status"], "ok")
            supplier_pages.verify(report, lambda d: raw)

    def test_note_on_the_page_requires_review_and_preserves_its_literal(self):
        for raw in (self.plain, self.signed):
            original = with_comment(raw)
            report = report_for(original)
            page, = report["graph"]["supplier_page_sources"]["pages"]
            self.assertEqual(page["state"], "annotations")
            note, = [a for a in page["annotations"] if a["subtype"] == "/Text"]
            self.assertEqual(note["note"], NOTE)
            self.assertFalse(note["shortened"])
            self.assertNotIn("comparison", page)
            self.assertEqual((check(report)["status"], check(report)["matching_print"]), ("missing", []))

    def test_identity_and_field_receipts_remain_independent(self):
        report = report_for(self.signed, receipt_name="山岚演练交付中心")
        self.assertEqual(check(report)["status"], "risk")
        fact = report["graph"]["facts"][0]
        fact["source_line"]["rects"] = []
        self.assertEqual(check(report)["matching_print"], [])
        fact["status"] = "disputed"
        self.assertEqual(check(report)["status"], "missing")

    def test_signed_reason_is_reviewable_even_if_the_printed_page_is_unchanged(self):
        raw = signed_copy(self.plain, reason=REASON)
        report = report_for(raw)
        graph = report["graph"]
        self.assertEqual(graph["pdf_execution_sources"]["documents"][0]["state"], "current")
        page, = graph["supplier_page_sources"]["pages"]
        attribute, = page["annotations"]
        self.assertEqual((attribute["kind"], attribute["signing_reason"], attribute["reason_shortened"]),
                         ("signature_reason", REASON, False))
        self.assertEqual(page["state"], "annotations")
        self.assertEqual(page["page_sha256"], report_for(self.signed)["graph"]["supplier_page_sources"]["pages"][0]["page_sha256"])
        self.assertEqual((check(report)["status"], check(report)["matching_print"]), ("missing", []))
        supplier_pages.verify(report, lambda doc: raw, signing=True)
        attribute["signing_reason"] = "同意支付全款"
        with self.assertRaises(ValueError):
            supplier_pages.verify(report, lambda doc: raw)

    def test_archived_v1_reason_replays_but_a_positive_signoff_requires_rerun(self):
        raw = signed_copy(self.plain, reason=REASON)
        old = report_for(raw, format=supplier_pages.LEGACY)
        supplier = check(old)
        self.assertEqual(supplier["status"], "ok")
        old["findings"] = [{"rule": "H02", "status": "ok", "acceptance_reservations": {"supplier": supplier}}]
        supplier_pages.verify(old, lambda doc: raw)
        with self.assertRaisesRegex(ValueError, "重新审计"):
            supplier_pages.verify(old, lambda doc: raw, signing=True)
        old["policy"]["version"] = supplier_pages.NOTES_SINCE
        with self.assertRaises(ValueError):
            supplier_pages.verify(old, lambda doc: raw)

    def test_recheck_rejects_changed_note_source_and_missing_markers(self):
        raw = with_comment(self.signed)
        report = report_for(raw)
        for mutation in ("content", "original", "node", "edge", "marker"):
            altered = copy.deepcopy(report)
            page = altered["graph"]["supplier_page_sources"]["pages"][0]
            if mutation == "content":
                page["annotations"][-1]["note"] = "已确认供货"
            elif mutation == "original":
                page["original_sha256"] = "0" * 64
            elif mutation == "marker":
                del altered["policy"]["supplier_page_inspection"]
            else:
                altered["graph"][mutation + "s"].pop()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                supplier_pages.verify(altered, lambda d: raw)
        with self.assertRaises(ValueError):
            supplier_pages.verify(report, lambda d: self.signed)
        del report["graph"]["supplier_page_sources"]
        del report["policy"]["supplier_page_inspection"]
        with self.assertRaises(ValueError):
            supplier_pages.verify(report, None)
        report["policy"]["version"] = "2026.11.26.14"
        report["graph"]["nodes"] = [n for n in report["graph"]["nodes"] if n["type"] != "supplier_page_inspection"]
        report["graph"]["edges"] = []
        supplier_pages.verify(report, None)
