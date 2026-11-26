import copy
from io import BytesIO
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import acceptance_comments as reviews
from config import PERFORMANCE
from controls import execute
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "frontend/showcase/acceptance-review.docx").read_bytes()
NOTE = "本次仅核对到货数量，制冷性能须由技术部另行终验。"
W = reviews.W


def modify(part, change):
    output = BytesIO()
    with ZipFile(BytesIO(SOURCE)) as original, ZipFile(output, "w") as changed:
        for info in original.infolist():
            raw = original.read(info)
            if info.filename == part:
                xml = ET.fromstring(raw)
                change(xml)
                raw = ET.tostring(xml, encoding="utf-8")
            changed.writestr(info, raw)
    return output.getvalue()


def report(raw=SOURCE, edit=None):
    graph = material([CONTRACT, RECEIPT, WARRANTY, BANK_DOC], edit=edit)
    receipt = graph["documents"][1]
    receipt.update(ext=".docx", sha256=reviews.digest(raw))
    for fact in graph["facts"]:
        if fact["doc"] == receipt["id"]:
            fact["source_sha256"] = receipt["sha256"]
    text = "\n".join((label + "：" if label else "") + (edit(2, field, label, value) if edit else value)
                     for field, label, value in RECEIPT)
    ledger = reviews.sources(graph, lambda doc: raw, lambda doc, n: text)
    graph["acceptance_word_reviews"] = ledger
    nodes, edges = reviews.source_graph(ledger)
    graph["nodes"].extend(nodes)
    graph["edges"].extend(edges)
    return {"graph": graph, "findings": execute(graph, PERFORMANCE),
            "policy": {"version": reviews.SINCE, "acceptance_word_reviews": reviews.FORMAT}}, text


def acceptance(paper):
    return next(f for f in paper["findings"] if f["rule"] == "H02")


class WordAcceptanceTests(unittest.TestCase):
    def test_original_word_selection_and_only_dependent_payments(self):
        paper, text = report()
        reviews.verify(paper, lambda d: SOURCE, lambda d, n: text)
        h02 = acceptance(paper)
        doc, = paper["graph"]["acceptance_word_reviews"]["documents"]
        note, = doc["notes"]
        self.assertEqual((doc["count"], doc["coverage"], note["author"], note["text"]),
                         (1, "complete", "演练仓储复核员", NOTE))
        self.assertEqual(note["anchor"], {"paragraph": 9, "start": 5, "end": 7, "quote": "验收结论：合格", "selected": "合格"})
        self.assertEqual(text.splitlines()[note["location"]["line"]-1], note["anchor"]["quote"])
        self.assertEqual((h02["status"], h02["acceptance_comments"]["status"]), ("risk", "risk"))
        self.assertEqual([f.get("stage", {}).get("name", f["rule"]) for f in paper["findings"] if note["id"] in f["evidence"]],
                         ["H02", "第二期", "第三期", "第二期"])
        phases = [f for f in paper["findings"] if f["rule"] == "H04"]
        self.assertEqual([f["status"] for f in phases], ["ok", "risk", "risk"])

    def test_review_comment_does_not_override_a_measured_failure(self):
        paper, _ = report(edit=lambda i, k, label, value: "柜温8℃" if k == "measured_result" else value)
        self.assertEqual(acceptance(paper)["status"], "issue")
        self.assertIn("8", acceptance(paper)["detail"])
        self.assertEqual(acceptance(paper)["acceptance_comments"]["status"], "risk")

    def test_other_or_withdrawn_opinions_stay_for_review(self):
        for message in ("已阅", "仓库备注：“" + NOTE + "”该意见已撤回。", "同意最终验收。", NOTE + "补充：意见撤销。", NOTE * 100):
            with self.subTest(message=message[:24]):
                def change(xml):
                    xml.find(".//" + W + "t").text = message
                raw = modify("word/comments.xml", change)
                paper, _ = report(raw)
                self.assertEqual(acceptance(paper)["status"], "missing")

    def test_unmapped_or_duplicate_lines_do_not_invent_a_location(self):
        def duplicate(xml):
            added = ET.Element(W+"p")
            ET.SubElement(ET.SubElement(added, W+"r"), W+"t").text = "验收结论：合格"
            xml.find(W+"body").insert(0, added)
        for action in (duplicate, lambda xml: xml.find(".//"+W+"commentReference").set(W+"id", "10")):
            raw = modify("word/document.xml", action)
            paper, _ = report(raw)
            note, = paper["graph"]["acceptance_word_reviews"]["documents"][0]["notes"]
            self.assertIsNone(note["anchor"])
            self.assertIsNone(note["location"])
            self.assertEqual(acceptance(paper)["status"], "missing")

    def test_extended_or_unreadable_review_requires_original(self):
        def add_threaded_part(xml):
            ET.SubElement(xml, reviews.CT+"Override", {"PartName": "/word/commentsExtended.xml",
                          "ContentType": "application/vnd.ms-word.commentsExtended+xml"})
        for raw, coverage in ((modify("[Content_Types].xml", add_threaded_part), "partial"), (b"old Word", "unreadable")):
            paper, _ = report(raw)
            self.assertEqual(paper["graph"]["acceptance_word_reviews"]["documents"][0]["coverage"], coverage)
            self.assertEqual(acceptance(paper)["status"], "missing")

    def test_packet_comment_follows_its_receipt_and_an_unlocated_comment_is_held(self):
        paper, _ = report()
        graph = paper["graph"]
        ledger = graph["acceptance_word_reviews"]
        doc, = ledger["documents"]
        other, selected = "d02/purchase-a", "d02/purchase-b"
        doc["units"] = [other, selected]
        note, = doc["notes"]
        note["location"]["unit"] = selected
        facts = {f["id"]: f for f in graph["facts"]}
        earlier = reviews.assess(ledger, {other}, facts)
        self.assertEqual((earlier["status"], earlier["notes"]), ("ok", []))
        self.assertEqual(reviews.assess(ledger, {selected}, facts)["status"], "risk")
        note["location"] = None
        self.assertTrue(all(reviews.assess(ledger, {u}, facts)["status"] == "missing" for u in doc["units"]))

    def test_source_mutations_and_old_positive_signoff(self):
        paper, text = report()
        load_text = lambda doc, page: text
        with self.assertRaisesRegex(ValueError, "原件摘要"):
            reviews.verify(paper, lambda d: SOURCE + b"changed", load_text)
        with self.assertRaisesRegex(ValueError, "页文摘要"):
            reviews.verify(paper, lambda d: SOURCE, lambda d, n: text + " ")
        for mutate in ("text", "start", "edge", "ledger"):
            changed = copy.deepcopy(paper)
            ledger = changed["graph"]["acceptance_word_reviews"]
            note = ledger["documents"][0]["notes"][0]
            if mutate == "text":
                note["text"] = "同意付款"
            elif mutate == "start":
                note["anchor"]["start"] = 0
            elif mutate == "edge":
                changed["graph"]["edges"].pop()
            else:
                del changed["graph"]["acceptance_word_reviews"]
            with self.assertRaises(ValueError):
                reviews.verify(changed, lambda d: SOURCE, load_text)
        old = copy.deepcopy(paper)
        graph = old["graph"]
        del graph["acceptance_word_reviews"]
        graph["nodes"] = [n for n in graph["nodes"] if not n["type"].startswith("acceptance_word_")]
        graph["edges"] = [e for e in graph["edges"] if not e["type"].startswith("word_review_")]
        old["policy"] = {"version": "2026.11.26.16"}
        h02 = acceptance(old)
        h02["status"] = "ok"
        reviews.verify(old, lambda d: SOURCE, load_text)
        with self.assertRaisesRegex(ValueError, "重新审计"):
            reviews.verify(old, lambda d: SOURCE, load_text, signing=True)
