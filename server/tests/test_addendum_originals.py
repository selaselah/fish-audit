import unittest
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pypdfium2 as pdfium

import addendum_originals as originals
from config import PERFORMANCE
from controls import VERSION, execute
from documents import prepare
from graph import build_graph
from performance import verify_findings
from test_acceptance_execution import by_rule, printed
from test_contract_changes import CHANGE, case, quantity_case
from test_mandate_originals import word_source
from test_payment_amendments import AMENDMENT, fixture


def filed(raw, ext, fixture, *, physical=False, confirmed_title=False):
    texts = {}

    def attach(docs, pages, checked):
        docs[1].update(ext=ext, pages=1, sha256=sha256(raw).hexdigest(), size=len(raw))
        if physical:
            with TemporaryDirectory() as directory:
                path = Path(directory) / ("agreement" + ext)
                path.write_bytes(raw)
                page, = prepare(path, 1, save_images=False)
            pages[1].update(page)
        if confirmed_title:
            checked["d02/p1/f1"] = {"decision": "confirm", "source_check": {"fixture": True}}
        texts.update({(p["doc"], p["number"]): p["text"] for p in pages})
        return build_graph(docs, pages, checked, read_original=lambda _: raw)
    with patch("test_performance.build_graph", attach):
        graph = fixture()
    report = {"graph": graph, "findings": execute(graph, PERFORMANCE), "policy": {**VERSION, "profile": PERFORMANCE}}
    return report, lambda doc, page: texts[doc, page]


def old_paper(report):
    graph = deepcopy(report["graph"])
    del graph[originals.KEY]
    graph["nodes"] = [n for n in graph["nodes"] if not n["type"].startswith(("addendum_original_", "addendum_word_"))]
    graph["edges"] = [e for e in graph["edges"] if not e["type"].startswith(("addendum_original_", "addendum_word_"))]
    policy = dict(report["policy"], version="2026.11.27.08")
    del policy["addendum_originals"]
    with patch("controls.RULE_VERSION", policy["version"]):
        return {"graph": graph, "policy": policy, "findings": execute(graph, PERFORMANCE)}


def changes(report):
    return [c for f in report["findings"] for c in (f.get("quality_change"), f.get("payment_change")) if c]


class AddendumOriginalTests(unittest.TestCase):
    def test_word_holds_selection_and_preserves_printed_dates_and_other_installments(self):
        for load, rows in ((case, CHANGE), (quantity_case, None), (lambda: fixture()[0], AMENDMENT)):
            if rows is None:
                rows = [(f["field"], *f["quote"].split("：", 1)) if "：" in f["quote"] else (f["field"], "", f["quote"])
                        for f in load()["facts"] if f["doc"] == "d02"]
            with self.subTest(field=rows[7][0]):
                raw = word_source(rows=rows)
                report, text = filed(raw, ".docx", load)
                old = old_paper(report)
                selected = changes(old)
                self.assertTrue(any(c.get("effective_on") for c in selected))
                row, = report["graph"][originals.KEY]["records"]
                self.assertEqual((row["state"], row["unit"]), ("word_text", "d02"))
                for c in changes(report):
                    self.assertEqual((c["original_execution"], c["effective_on"]), ([row["id"]], None))
                    self.assertEqual(c.get("state") or c["applies"], "pending")
                    self.assertTrue(c.get("seller_on") or c.get("seller_sealed_on"))
                    self.assertTrue({row["review"], row["id"], *row["fields"]} <= set(c["evidence"]))
                for f, prev in zip(report["findings"], old["findings"], strict=True):
                    if f["rule"] == "H01" or f.get("stage", {}).get("name") != "第二期" and rows == AMENDMENT:
                        self.assertEqual(f["status"], prev["status"])
                    if f["rule"] == "H01":
                        self.assertNotIn(row["id"], f["evidence"])
                verify_findings(report)
                originals.verify(report, lambda _: raw, text)
                originals.verify(old, lambda _: raw, text)
                with self.assertRaisesRegex(ValueError, "重审"):
                    originals.verify(old, lambda _: raw, text, signing=True)

    def test_notes_and_tracked_changes_never_authorise_the_proposed_criterion(self):
        for track in (True, False):
            raw = word_source(rows=CHANGE, anchor_field="revised_criterion", note="需双方确认", comment=True, tracked=track)
            report, text = filed(raw, ".docx", case)
            ledger = report["graph"][originals.KEY]
            row, = ledger["records"]
            word, = ledger["documents"]
            note, = word["notes"]
            self.assertEqual((row["state"], word["coverage"], note["text"]), ("word_review", "partial" if track else "complete", "需双方确认"))
            self.assertEqual((note["anchor"]["selected"], note["location"]["unit"]), ("柜温不高于2℃", "d02"))
            h02, = by_rule(report, "H02")
            self.assertIsNone(h02["quality_change"]["applied_criterion"])
            self.assertIn(note["id"], h02["evidence"])
            self.assertIn("审阅", h02["quality_change"]["detail"])
            for key in ("part", "field", "unit", "edge", "line", "policy", "version", "methods", "raw", "finding"):
                altered = deepcopy(report)
                g = altered["graph"]
                r = g[originals.KEY]["records"][0]
                w = g[originals.KEY]["documents"][0]
                if key == "part": w["part_sha256"] = "0" * 64
                if key == "field": r["fields"].clear()
                if key == "unit": r["unit"] = "d01"
                if key == "edge": g["edges"] = [e for e in g["edges"] if e["type"] != "addendum_original_comment"]
                if key == "line": w["notes"][0]["location"]["line"] += 1
                if key == "policy": del altered["policy"]["addendum_originals"]
                if key == "version": altered["policy"]["version"] = "2026.11.27.08"
                if key == "methods": altered["policy"]["code_sha256"] = {"addendum_originals.py": "missing shared source"}
                with self.subTest(modified=key), self.assertRaises(ValueError):
                    if key == "finding":
                        by_rule(altered, "H02")[0]["quality_change"]["original_execution"].clear()
                        verify_findings(altered)
                    else:
                        originals.verify(altered, lambda _: raw + b"x" if key == "raw" else raw, text)

    def test_scanned_agreement_has_only_physical_page_and_legacy_pending_can_be_reviewed(self):
        buf = BytesIO()
        with pdfium.PdfDocument(printed(case(), "d02")) as agreement:
            agreement[0].render(scale=1.4).to_pil().convert("RGB").save(buf, "JPEG")
        raw = buf.getvalue()
        unassigned, _ = filed(raw, ".jpg", case, physical=True)
        self.assertFalse(unassigned["graph"][originals.KEY]["records"])
        report, text = filed(raw, ".jpg", case, physical=True, confirmed_title=True)
        row, = report["graph"][originals.KEY]["records"]
        self.assertEqual((row["state"], row["review"], row["notes"], row["unplaced"]), ("photo", None, [], 0))
        self.assertEqual(row["pages"][0]["layer"], "image")
        h02, = by_rule(report, "H02")
        self.assertIn("上传影像", h02["quality_change"]["detail"])
        self.assertTrue(all(not f.get("source_line") for f in report["graph"]["facts"] if f["doc"] == "d02"))
        originals.verify(report, lambda _: raw, text, signing=True)
        old = old_paper(report)
        self.assertFalse(any(c.get("effective_on") for c in changes(old)))
        originals.verify(old, lambda _: raw, text, signing=True)

    def test_bound_pages_never_borrow_another_agreements_comment(self):
        selected = "柜温不高于2℃"
        first, second = "unit/d02/p1", "unit/d02/p2"
        for alternative in ("柜温不高于3℃", selected):
            other = [(field, label, alternative if field == "revised_criterion" else value) for field, label, value in CHANGE]
            raw = word_source(rows=CHANGE, second=other, comment=True, anchor_field="revised_criterion", note="拟议变更")
            report, text = filed(raw, ".docx", case)
            g = report["graph"]
            doc = next(d for d in g["documents"] if d["id"] == "d02")
            doc["pages"] = 2
            g["documents_by_kind"]["contract_addendum"] = [first, second]
            g["audit_documents"] = [d for d in g["documents"] if d["id"] != "d02"] + [
                {"id": first, "source": "d02", "page": 1}, {"id": second, "source": "d02", "page": 2}]
            for f in g["facts"]:
                if f["doc"] == "d02":
                    f["unit"] = first
            other_page = text("d02", 1).replace(selected, alternative)
            original = next(n for n in g["nodes"] if n["id"] == "d02/p1")
            g["nodes"].append({**original, "id": "d02/p2", "text_sha256": sha256(other_page.encode()).hexdigest()})
            g[originals.KEY] = originals.sources(g, lambda _: raw, lambda d,p: other_page if p == 2 else text(d,p))
            a, b = g[originals.KEY]["records"]
            note, = g[originals.KEY]["documents"][0]["notes"]
            self.assertEqual((a["unit"], b["unit"], b["notes"]), (first, second, []))
            entry = {"evidence": []}
            originals.bind(entry, g, [second])
            self.assertNotIn(note["id"], entry["evidence"])
            self.assertNotIn("d02/p1", entry["evidence"])
            if selected == alternative:
                self.assertIsNone(note["location"])
                self.assertEqual((a["unplaced"], b["unplaced"], a["notes"]), (1, 1, []))
            else:
                self.assertEqual((a["state"], b["state"], a["notes"]), ("word_review", "word_text", [note["id"]]))

    def test_independently_paged_word_preserves_old_reading_without_applying_it(self):
        raw = word_source(rows=CHANGE)
        report, text = filed(raw, ".docx", case, physical=True)
        old = old_paper(report)
        prior, = changes(old)
        self.assertEqual((prior["state"], prior["effective_on"]), ("applied", "2026-09-12"))
        revised, = changes(report)
        self.assertEqual((revised["buyer_sealed_on"], revised["seller_sealed_on"]), ("2026-09-10", "2026-09-12"))
        self.assertEqual(revised["revised_criterion"], prior["revised_criterion"])
        self.assertEqual((revised["state"], revised["effective_on"], revised["applied_criterion"]), ("pending", None, None))
        originals.verify(report, lambda _: raw, text, signing=True)
        with self.assertRaisesRegex(ValueError, "重审"):
            originals.verify(old, lambda _: raw, text, signing=True)
