import unittest
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pypdfium2 as pdfium
from docx import Document

import acceptance_comments
import acceptance_originals as originals
from config import PERFORMANCE
from controls import VERSION, execute
from documents import prepare
from graph import build_graph
from performance import verify_findings
from test_acceptance_execution import by_rule, printed
from test_delivery_batches import sample as batches
from test_mandate_originals import word_source
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material
from test_reinspection import FINAL, graph as repairs


def procurement():
    return material([CONTRACT, RECEIPT, WARRANTY, BANK_DOC])


def filed(raw, fixture=procurement, unit="d02", ext=".docx", *, render=False):
    texts = {}
    def attach(docs, pages, checked):
        doc = next(d for d in docs if d["id"] == unit)
        doc.update(ext=ext, pages=1, size=len(raw), sha256=sha256(raw).hexdigest())
        if render:
            with TemporaryDirectory() as folder:
                path = Path(folder) / ("receipt" + ext)
                path.write_bytes(raw)
                physical, = prepare(path, 1, save_images=False)
            next(p for p in pages if p["doc"] == unit).update(physical)
            checked[unit + "/p1/f1"] = {"decision": "confirm", "source_check": {"fixture": True}}
        texts.update({(p["doc"], p["number"]): p["text"] for p in pages})
        return build_graph(docs, pages, checked, read_original=lambda _: raw)
    with patch("test_performance.build_graph", attach):
        graph = fixture()
    return {"graph": graph, "findings": execute(graph, PERFORMANCE), "policy": {**VERSION, "profile": PERFORMANCE}}, lambda d,p: texts[d,p]


def previous(report):
    graph = deepcopy(report["graph"])
    graph.pop(originals.KEY)
    graph["nodes"] = [n for n in graph["nodes"] if n["type"] != "acceptance_original_inspection"]
    graph["edges"] = [e for e in graph["edges"] if not e["type"].startswith("acceptance_original_")]
    policy = {**report["policy"], "version": "2026.11.27.09"}
    policy.pop("acceptance_originals")
    with patch("controls.RULE_VERSION", policy["version"]):
        return {"graph": graph, "policy": policy, "findings": execute(graph, PERFORMANCE)}


class AcceptanceOriginalTests(unittest.TestCase):
    def test_printed_signer_does_not_release_acceptance_payment_or_warranty(self):
        raw = word_source(rows=RECEIPT)
        report, text = filed(raw, render=True)
        old = previous(report)
        self.assertEqual(by_rule(old, "H02")[0]["status"], "ok")
        h02, = by_rule(report, "H02")
        record, = report["graph"][originals.KEY]["records"]
        self.assertEqual((record["state"], h02["status"], h02["acceptance_originals"]),
                         ("word_text", "missing", [record["id"]]))
        self.assertIn(record["review"], h02["evidence"])
        self.assertNotIn("documents", report["graph"][originals.KEY])
        first, second, warranty = by_rule(report, "H04")
        self.assertEqual(first["status"], "ok")
        self.assertNotIn(record["id"], first["evidence"])
        for f in (second, warranty, *by_rule(report, "H05")):
            self.assertNotEqual(f["status"], "ok")
            self.assertTrue({record["id"], *record["fields"], "d02/p1"}.issubset(f["evidence"]))
        verify_findings(report)
        originals.verify(report, lambda _: raw, text, signing=True)
        originals.verify(old, lambda _: raw, text)
        with self.assertRaisesRegex(ValueError, "重审"):
            originals.verify(old, lambda _: raw, text, signing=True)
        old["findings"] = by_rule(old, "H04")[:1]
        originals.verify(old, lambda _: raw, text, signing=True)

    def test_open_defect_survives_printed_reinspection_and_batches_keep_own_sources(self):
        report, _ = filed(word_source(rows=FINAL), repairs, "d04")
        old = previous(report)
        self.assertEqual(by_rule(old, "H02")[0]["reinspection"]["state"], "closed")
        old["findings"] = by_rule(old, "H02")
        old["findings"][0]["status"] = "missing"
        self.assertTrue(originals.positive_legacy(old["graph"], old["findings"]))
        f, = by_rule(report, "H02")
        self.assertEqual((f["status"], f["reinspection"]["state"]), ("issue", "open"))
        self.assertIn("不合格", f["detail"])
        self.assertIn("acceptance-original/d04", by_rule(report, "H04")[1]["evidence"])
        template = batches()
        unit = template["documents_by_kind"]["acceptance"][1]
        rows = [(f["field"], f["quote"].partition("：")[0] if "：" in f["quote"] else "", f["value"])
                for f in template["facts"] if f["doc"] == unit]
        report, _ = filed(word_source(rows=rows), batches, unit)
        ref = "acceptance-original/" + unit
        a,b,c,d = by_rule(report, "H04")
        self.assertEqual((a["status"], b["status"]), ("ok", "ok"))
        self.assertNotIn(ref, b["evidence"])
        for f in (c,d):
            self.assertNotEqual(f["status"], "ok")
            self.assertIn(ref, f["evidence"])
        r = next(r for r in by_rule(report, "H02")[0]["batch_acceptance"]["records"] if r["unit"] == unit)
        self.assertEqual(r["acceptance_originals"], [ref])

    def test_review_comment_and_missing_signature_share_one_cited_word_source(self):
        raw = word_source(rows=RECEIPT, comment=True, anchor_field="acceptance_result",
                          note="本次仅核对到货数量，制冷性能须由技术部另行终验。")
        report, text = filed(raw, render=True)
        graph = report["graph"]
        note, = graph["acceptance_word_reviews"]["documents"][0]["notes"]
        r, = graph[originals.KEY]["records"]
        self.assertEqual((r["state"], r["notes"]), ("word_review", [note["id"]]))
        self.assertEqual(by_rule(report, "H02")[0]["status"], "risk")
        for item in (by_rule(report,"H02")[0], by_rule(report,"H04")[1], *by_rule(report,"H05")):
            self.assertTrue({note["id"], r["id"]} <= set(item["evidence"]))
        self.assertEqual(sum(n["id"] == note["id"] for n in graph["nodes"]), 1)
        originals.verify(report,lambda _:raw,text,signing=True)
        for change in ("bytes", "page", "note", "edge", "review", "policy", "methods", "finding"):
            altered = deepcopy(report)
            g = altered["graph"]
            if change == "page": g[originals.KEY]["records"][0]["pages"][0]["sha256"] = "0" * 64
            if change == "note": g[originals.KEY]["records"][0]["notes"] = []
            if change == "edge": g["edges"] = [e for e in g["edges"] if e["type"] != "acceptance_original_word"]
            if change == "review": g["acceptance_word_reviews"]["documents"][0]["notes"][0]["text"] = "已正式终验"
            if change == "policy": del altered["policy"]["acceptance_originals"]
            if change == "methods": altered["policy"]["code_sha256"] = {"acceptance_originals.py": "absent shared methods"}
            with self.subTest(change=change), self.assertRaises(ValueError):
                if change == "finding":
                    by_rule(altered, "H02")[0]["acceptance_originals"] = []
                    verify_findings(altered)
                else:
                    originals.verify(altered, lambda _: raw + b"x" if change == "bytes" else raw, text)

    def test_photograph_keeps_original_pixels_and_only_observed_signer(self):
        out = BytesIO()
        with pdfium.PdfDocument(printed(procurement(), "d02")) as doc:
            doc[0].render(scale=1.3).to_pil().convert("RGB").save(out, "JPEG")
        raw = out.getvalue()
        report, text = filed(raw, ext=".jpg", render=True)
        record, = report["graph"][originals.KEY]["records"]
        self.assertEqual((record["state"], record["review"], record["notes"]), ("photo",None,[]))
        self.assertEqual(record["pages"][0]["layer"], "image")
        self.assertTrue(all(not f.get("source_line") for f in report["graph"]["facts"] if f["doc"] == "d02"))
        self.assertNotEqual(by_rule(report, "H02")[0]["status"], "ok")
        originals.verify(report, lambda _: raw, text, signing=True)

    def test_two_actual_word_pages_keep_their_own_review_and_signer(self):
        for repeated in (False, True):
            final = [(field,label,"待复核" if field == "acceptance_result" and not repeated else value)
                     for field,label,value in FINAL]
            raw = word_source(rows=RECEIPT, second=final, comment=True, anchor_field="acceptance_result")
            word = Document(BytesIO(raw))
            marks = [p for p in word.paragraphs if "仅供系统测试" in p.text]
            marks[1].paragraph_format.page_break_before = True
            out = BytesIO()
            word.save(out)
            raw = out.getvalue()
            with TemporaryDirectory() as folder:
                file = Path(folder) / "水印合册.docx"
                file.write_bytes(raw)
                physical = prepare(file, 2, save_images=False)
            self.assertEqual(len(physical), 2)
            doc = {"id":"d01", "ext":".docx", "sha256":sha256(raw).hexdigest(), "pages":2}
            graph = {"documents":[doc], "audit_documents":[], "documents_by_kind":{}, "nodes":[], "facts":[]}
            for page, kind in zip(physical, ("acceptance", "reinspection"), strict=True):
                n = page["number"]
                ref = "d01/p" + str(n)
                unit = "unit/" + ref
                graph["audit_documents"].append({"id":unit, "source":"d01", "page":n})
                graph["documents_by_kind"][kind] = [unit]
                graph["nodes"].append({"id":ref, "type":"page", "layer":page["layer"]["type"], "sha256":page["sha256"],
                                       "clause_text_only":page["layer"]["clause_text_only"], "text_sha256":sha256(page["text"].encode()).hexdigest()})
                graph["facts"].append({"id":ref+"/f1", "doc":"d01", "page":n, "unit":unit, "field":"acceptance_signer", "quote":"验收签认"})
            read = lambda d,n: physical[n-1]["text"]
            review = acceptance_comments.sources(graph, lambda _:raw, read)
            a,b = originals.sources(graph,lambda _:raw,read,review)["records"]
            self.assertEqual(([p["ref"] for p in a["pages"]],[p["ref"] for p in b["pages"]]), (["d01/p1"],["d01/p2"]))
            self.assertEqual((a["fields"],b["fields"]), (["d01/p1/f1"],["d01/p2/f1"]))
            self.assertEqual((len(a["notes"]), b["notes"], a["unplaced"], b["unplaced"]),
                             (0 if repeated else 1, [], int(repeated), int(repeated)))
            self.assertEqual(b["state"], "word_review" if repeated else "word_text")
