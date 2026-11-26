from copy import deepcopy
from io import BytesIO
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import acceptance_comments as word
import contract_comments as review
from config import PERFORMANCE
from controls import VERSION, execute
from performance import verify_findings
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material

SOURCE = (Path(__file__).resolve().parents[2] / "frontend/showcase/contract-payment-review.docx").read_bytes()
W = word.W


def rewrite(part, fn):
    output = BytesIO()
    with ZipFile(BytesIO(SOURCE)) as original, ZipFile(output, "w") as changed:
        for info in original.infolist():
            raw = original.read(info)
            if info.filename == part:
                xml = ET.fromstring(raw)
                fn(xml)
                raw = ET.tostring(xml, encoding="utf-8")
            changed.writestr(info, raw)
    return output.getvalue()


def report(raw=SOURCE, edit=None):
    graph = material([CONTRACT, RECEIPT, WARRANTY, BANK_DOC], edit=edit)
    doc = graph["documents"][0]
    doc.update(ext=".docx", sha256=word.digest(raw))
    for fact in graph["facts"]:
        if fact["doc"] == doc["id"]:
            fact["source_sha256"] = doc["sha256"]
    text = "\n".join((label + "：" if label else "") + (edit(1, field, label, value) if edit else value)
                     for field, label, value in CONTRACT)
    ledger = review.sources(graph, lambda d: raw, lambda d, n: text)
    graph["contract_word_reviews"] = ledger
    nodes, edges = review.source_graph(ledger)
    graph["nodes"].extend(nodes)
    graph["edges"].extend(edges)
    return {"graph": graph, "findings": execute(graph, PERFORMANCE), "policy": {**VERSION, "profile": PERFORMANCE}}, text


def strip_new_records(paper):
    paper = deepcopy(paper)
    graph = paper["graph"]
    del graph["contract_word_reviews"]
    graph["nodes"] = [n for n in graph["nodes"] if not n["type"].startswith("contract_word_")]
    graph["edges"] = [e for e in graph["edges"] if not e["type"].startswith("contract_word_review_")]
    paper["policy"] = {"version": "2026.11.26.17"}
    paper["findings"] = execute(graph, PERFORMANCE)
    return paper


class ContractWordReviewTests(unittest.TestCase):
    def test_scoped_suggestion_only_holds_second_trigger_and_its_bank_receipt(self):
        paper, text = report()
        review.verify(paper, lambda d: SOURCE, lambda d, n: text)
        verify_findings(paper)
        notes = paper["graph"]["contract_word_reviews"]["documents"][0]["notes"]
        note, = notes
        self.assertEqual(note["anchor"]["selected"], "最终验收合格后")
        affected = [f for f in paper["findings"] if note["id"] in f["evidence"]]
        self.assertEqual([(f["rule"], f.get("stage", {}).get("name"), f["status"]) for f in affected],
                         [("H03", None, "missing"), ("H04", "第二期", "missing"), ("H05", "第二期", "missing")])
        independent = lambda f: f["rule"] in {"H01","H02"} or f["rule"] == "H04" and f["stage"]["name"] != "第二期"
        self.assertEqual([f for f in paper["findings"] if independent(f)],
                         [f for f in strip_new_records(paper)["findings"] if independent(f)])
        self.assertTrue(all(f["contract_comments"]["clauses"][note["id"]] == affected[1]["stage"]["clause_ref"] for f in affected))
        self.assertEqual(affected[1]["stage"]["share"], "60")

    def test_layout_space_is_allowed_only_at_chinese_word_number_boundary(self):
        for amount, scoped in ((" 60%", True), ("6 0%", False), ("  60%", False), ("50%", False)):
            with self.subTest(amount=amount):
                paper, _ = report(edit=lambda i, k, label, value: value.replace("60%", amount) if label == "第二期" else value)
                plan, = [f["contract_comments"] for f in paper["findings"] if f["rule"] == "H03"]
                self.assertEqual(plan["whole"], not scoped)
                note, = paper["graph"]["contract_word_reviews"]["documents"][0]["notes"]
                self.assertEqual(bool(note["location"]), scoped)
                if scoped:
                    self.assertIn("支付 60%", note["location"]["printed"])

    def test_cross_installment_withdrawn_or_unlocated_notes_require_scope_review(self):
        def message(text):
            def write(xml):
                xml.find(".//" + W + "t").text = text
            return rewrite("word/comments.xml", write)
        raws = [message("第三期同时调整，首期付款暂缓。"), message("建议已撤回。"),
                rewrite("word/document.xml", lambda x: x.find(".//" + W + "commentReference").set(W+"id", "49")), b"legacy"]
        for raw in raws:
            paper, _ = report(raw)
            affected = [f for f in paper["findings"] if f["rule"] in {"H03", "H04", "H05"}]
            self.assertTrue(all(f["contract_comments"]["whole"] and f["status"] != "ok" for f in affected))

    def test_existing_early_payment_survives_and_unrelated_receipt_stays_clear(self):
        early, _ = report(edit=lambda i, k, l, v: "2026-09-15" if k == "paid_on" else v)
        payment, = [f for f in early["findings"] if f["rule"] == "H05"]
        self.assertEqual(payment["status"], "risk")
        self.assertIn("早于", payment["detail"])
        first, _ = report(edit=lambda i, k, l, v: "第一期" if k == "payment_designation" else v)
        payment, = [f for f in first["findings"] if f["rule"] == "H05"]
        previous, = [f for f in strip_new_records(first)["findings"] if f["rule"] == "H05"]
        self.assertEqual(payment, previous)
        self.assertNotIn("contract_comments", payment)

    def test_replay_and_signing_rebuild_from_the_original(self):
        paper, text = report()
        read = lambda d, n: text
        old = strip_new_records(paper)
        review.verify(old, lambda d: SOURCE, read)
        with self.assertRaisesRegex(ValueError, "重新审计"):
            review.verify(old, lambda d: SOURCE, read, signing=True)
        old["policy"]["version"] = paper["policy"]["version"]
        with self.assertRaisesRegex(ValueError, "缺少"):
            review.verify(old, lambda d: SOURCE, read)
        for change in ("original", "page", "target", "edges"):
            changed = deepcopy(paper)
            if change == "target":
                f = next(f for f in changed["findings"] if f["rule"] == "H03")
                f["contract_comments"]["clauses"].clear()
                with self.assertRaises(ValueError):
                    verify_findings(changed)
                continue
            if change == "edges":
                changed["graph"]["edges"] = [e for e in changed["graph"]["edges"] if e["type"] != "contract_word_review_anchor"]
            with self.assertRaises(ValueError):
                review.verify(changed, lambda d: SOURCE + b"!" if change == "original" else SOURCE,
                              lambda d, n: text + "!" if change == "page" else text)
