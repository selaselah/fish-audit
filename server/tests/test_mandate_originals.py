from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pypdfium2 as pdfium

import mandate_originals as originals
from acceptance_comments import W
from config import PERFORMANCE
from controls import VERSION, execute
from documents import prepare
from graph import build_graph
from performance import verify_findings
from test_acceptance_comments import SOURCE
from test_acceptance_execution import by_rule, printed
from test_delegation import GRANT, sample


NOTE = "签署前请另经采购总监书面批准"
WATERMARK = "合成演练资料　仅供系统测试　无交易效力"


def word_source(*, comment=False, second=None, tracked=False, rows=GRANT, anchor_field="grant_scope", note=NOTE):
    # Retain the real OPC relationships and content types of a marked sample.
    output = BytesIO()
    with ZipFile(BytesIO(SOURCE)) as src, ZipFile(output, "w") as dst:
        for info in src.infolist():
            raw = src.read(info)
            if info.filename == "word/document.xml":
                root = ET.fromstring(raw)
                body = root.find(W + "body")
                sect = body.find(W + "sectPr")
                body.clear()
                groups = [rows] if second is None else [rows, second]
                for group in groups:
                    for field, label, value in [("", "", WATERMARK), *group]:
                        p = ET.SubElement(body, W + "p")
                        if label:
                            ET.SubElement(ET.SubElement(p, W + "r"), W + "t").text = label + "："
                        selected = comment and field == anchor_field and body.find(".//" + W + "commentRangeStart") is None
                        if selected:
                            ET.SubElement(p, W + "commentRangeStart", {W + "id": "0"})
                        run = ET.SubElement(p, W + "r")
                        ET.SubElement(run, W + "t").text = value
                        if selected:
                            ET.SubElement(p, W + "commentRangeEnd", {W + "id": "0"})
                            ET.SubElement(ET.SubElement(p, W + "r"), W + "commentReference", {W + "id": "0"})
                if tracked:
                    ET.SubElement(ET.SubElement(body, W + "p"), W + "ins", {W + "id": "1"})
                if sect is not None:
                    body.append(sect)
                raw = ET.tostring(root, encoding="utf-8")
            elif info.filename == "word/comments.xml":
                root = ET.Element(W + "comments")
                if comment:
                    item = ET.SubElement(root, W + "comment", {W + "id": "0", W + "author": "演练审阅人"})
                    ET.SubElement(ET.SubElement(ET.SubElement(item, W + "p"), W + "r"), W + "t").text = note
                raw = ET.tostring(root, encoding="utf-8")
            dst.writestr(info, raw)
    return output.getvalue()


def filed(raw, ext=".docx", *, page=None, edit=None):
    texts = {}
    def attach(docs, pages, signed):
        docs[1].update(ext=ext, name="演练委托书" + ext, sha256=sha256(raw).hexdigest(), size=len(raw), pages=1)
        if page is not None:
            pages[1].update(page)
        for item in pages:
            texts[item["doc"], item["number"]] = item["text"]
        return build_graph(docs, pages, signed, read_original=lambda d: raw)
    confirmed = {f"d02/p1/f{i}": {"decision": "confirm", "source_check": {"fixture": True}} for i in range(1, len(GRANT)+1)}
    with patch("test_performance.build_graph", attach):
        graph = sample(edit=edit, attestations=confirmed)
    return {"graph": graph, "policy": {**VERSION, "profile": PERFORMANCE}, "findings": execute(graph, PERFORMANCE)}, texts


class OriginalMandateTests(unittest.TestCase):
    def test_typeset_word_holds_only_dependent_conclusions(self):
        raw = word_source()
        report, texts = filed(raw)
        row, = report["graph"]["mandate_original_sources"]["records"]
        self.assertEqual((row["state"], row["kind"], row["notes"]), ("word_text", "word", []))
        h01, = by_rule(report, "H01")
        grant, = h01["delegations"]
        self.assertEqual((h01["status"], grant["status"], grant["mandate_originals"]), ("missing", "missing", [row["id"]]))
        for f in [h01, *by_rule(report, "H04"), *by_rule(report, "H05")]:
            self.assertEqual(f["status"], "missing")
            self.assertLessEqual({row["id"], row["review"], "d02/p1", *row["fields"]}, set(f["evidence"]))
        for f in by_rule(report, "H02") + by_rule(report, "H03"):
            self.assertEqual(f["status"], "ok")
            self.assertNotIn(row["id"], f["evidence"])
        originals.verify(report, lambda doc: raw, lambda d, p: texts[d, p])
        verify_findings(report)

    def test_comment_and_selection_are_bound_to_their_own_review_and_field(self):
        raw = word_source(comment=True)
        report, texts = filed(raw)
        g = report["graph"]
        row, = g["mandate_original_sources"]["records"]
        word, = g["mandate_original_sources"]["documents"]
        note, = word["notes"]
        self.assertEqual((row["state"], row["notes"], row["unplaced"]), ("word_review", [note["id"]], 0))
        self.assertEqual((note["text"], note["anchor"]["selected"], note["location"]["unit"]),
                         (NOTE, "代表委托单位签署本采购合同", "d02"))
        edge, = [e for e in g["edges"] if e["type"] == "mandate_original_comment"]
        self.assertEqual(edge["evidence"], ["d02", word["id"], "d02/p1", *note["location"]["facts"]])
        grant, = by_rule(report, "H01")[0]["delegations"]
        self.assertIn(note["id"], grant["evidence"])
        clear, = grant["limits"]
        declared = next(f for f in g["facts"] if f["id"] == clear["field_ref"])
        self.assertEqual((clear["status"], declared["quote"]), ("ok", "附加限制：无"))
        originals.verify(report, lambda d: raw, lambda d, p: texts[d, p])
        for key in ("note", "selection", "edge", "marker", "original", "source", "finding"):
            with self.subTest(key=key):
                changed = deepcopy(report)
                g = changed["graph"]
                record = g["mandate_original_sources"]["records"][0]
                comment = g["mandate_original_sources"]["documents"][0]["notes"][0]
                if key == "note":
                    comment["text"] = "已经同意签署"
                elif key == "selection":
                    comment["location"]["line"] += 1
                elif key == "edge":
                    g["edges"] = [e for e in g["edges"] if e["type"] != "mandate_original_comment"]
                elif key == "marker":
                    del changed["policy"]["mandate_originals"]
                elif key == "source":
                    record["pages"][0]["sha256"] = "wrong-page"
                elif key == "finding":
                    by_rule(changed, "H01")[0]["delegations"][0]["evidence"].remove(note["id"])
                with self.assertRaises(ValueError):
                    if key == "finding":
                        verify_findings(changed)
                    else:
                        originals.verify(changed, lambda d: raw + b"." if key == "original" else raw, lambda d,p: texts[d,p])

    def test_photo_has_no_invented_text_coordinates_and_rerenders(self):
        with pdfium.PdfDocument(printed(sample(), "d02")) as doc:
            sheet = doc[0]
            bitmap = sheet.render(scale=1.3)
            buf = BytesIO()
            bitmap.to_pil().convert("RGB").save(buf, "JPEG")
            bitmap.close()
            sheet.close()
        raw = buf.getvalue()
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "grant.jpg"
            path.write_bytes(raw)
            page, = prepare(path, 1, save_images=False)
        report, texts = filed(raw, ".jpg", page=page)
        row, = report["graph"]["mandate_original_sources"]["records"]
        self.assertEqual((row["state"], row["kind"], row["review"], page["text"]), ("photo", "image", None, ""))
        self.assertEqual(row["pages"], [{"ref": "d02/p1", "sha256": page["sha256"], "layer": "image", "text_only": False}])
        self.assertTrue(row["fields"])
        self.assertTrue(all(f.get("source_line") is None for f in report["graph"]["facts"] if f["id"] in row["fields"]))
        originals.verify(report, lambda d: raw, lambda d, p: texts[d, p], signing=True)
        forged = deepcopy(row)
        forged["pages"][0]["sha256"] = "wrong-page"
        with self.assertRaisesRegex(ValueError, "重现"):
            originals.verify_rendered(report["graph"], [forged], lambda d: raw)

    def test_legacy_review_is_readable_but_dependent_positive_requires_rerun(self):
        raw = word_source()
        report, texts = filed(raw)
        g = report["graph"]
        del g["mandate_original_sources"]
        g["nodes"] = [n for n in g["nodes"] if not n["type"].startswith(("mandate_original_", "mandate_word_"))]
        g["edges"] = [e for e in g["edges"] if not e["type"].startswith(("mandate_original_", "mandate_word_review_"))]
        del report["policy"]["mandate_originals"]
        report["policy"]["version"] = "2026.11.27.03"
        report["findings"] = execute(g, PERFORMANCE)
        self.assertEqual(by_rule(report, "H01")[0]["delegations"][0]["status"], "ok")
        originals.verify(report, lambda d: raw, lambda d,p: texts[d,p])
        with self.assertRaisesRegex(ValueError, "旧版相符"):
            originals.verify(report, lambda d: raw, lambda d,p: texts[d,p], signing=True)
        for f in report["findings"]:
            if f["rule"] in ("H01", "H04", "H05"):
                f["status"] = "risk"
            for e in f.get("delegations", ()):
                e["status"] = "risk"
        originals.verify(report, lambda d: raw, lambda d,p: texts[d,p], signing=True)

    def test_active_revisions_old_word_and_explicit_restriction_require_review(self):
        for raw, ext in [(word_source(tracked=True), ".docx"), (b"legacy Word fixture", ".doc")]:
            with self.subTest(ext=ext):
                report, _ = filed(raw, ext, edit=lambda i,f,l,v: "仅限收货验收" if f == "grant_scope" else v)
                row, = report["graph"]["mandate_original_sources"]["records"]
                grant, = by_rule(report, "H01")[0]["delegations"]
                self.assertEqual((row["state"], grant["status"]), ("word_review", "risk"))
                self.assertIn("仅限收货验收", grant["detail"])

    def test_packet_note_never_supplies_evidence_for_another_grant(self):
        scope = "代表委托单位签署本采购合同"
        for other_scope in ("仅限收货验收", scope):
            with self.subTest(other_scope=other_scope):
                other = [(f,l, other_scope if f == "grant_scope" else v) for f,l,v in GRANT]
                raw = word_source(comment=True, second=other)
                report, texts = filed(raw)
                g = report["graph"]
                doc = next(d for d in g["documents"] if d["id"] == "d02")
                doc["pages"] = 2
                ids = ["unit/d02/p1", "unit/d02/p2"]
                g["documents_by_kind"]["power_of_attorney"] = ids
                g["audit_documents"] = [d for d in g["documents"] if d["id"] != "d02"] + [
                    {"id": ident, "source": "d02", "page": i} for i,ident in enumerate(ids, 1)]
                for f in g["facts"]:
                    if f["doc"] == "d02":
                        f["unit"] = ids[0]
                texts["d02",2] = texts["d02",1].replace(scope, other_scope)
                first = next(n for n in g["nodes"] if n["id"] == "d02/p1")
                g["nodes"].append({**first, "id": "d02/p2", "sha256": "page-2",
                                   "text_sha256": sha256(texts["d02",2].encode()).hexdigest()})
                ledger = originals.sources(g, lambda d: raw, lambda d,p: texts[d,p])
                one, two = ledger["records"]
                note, = ledger["documents"][0]["notes"]
                self.assertEqual((one["unit"], two["unit"]), tuple(ids))
                self.assertEqual(two["notes"], [])
                if other_scope == scope:
                    self.assertIsNone(note["location"])
                    self.assertEqual((one["notes"], one["unplaced"], two["unplaced"]), ([], 1, 1))
                    self.assertTrue(all(r["state"] == "word_review" for r in (one, two)))
                else:
                    self.assertEqual((one["state"], two["state"], one["notes"]), ("word_review", "word_text", [note["id"]]))
                    _, edges = originals.source_graph(ledger)
                    link, = [e for e in edges if e["type"] == "mandate_original_comment"]
                    self.assertEqual((link["from"], link["to"]), (one["id"], note["id"]))
