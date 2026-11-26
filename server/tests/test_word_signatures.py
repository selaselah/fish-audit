import copy
import unittest

from contract_effect import IMAGE_FORMAT, sources, verify
from controls import VERSION, execute
from graph import link_procedures
from performance import compute, verify_findings
from test_signing_parties import original_reader, sample


class WordSignaturesTests(unittest.TestCase):
    def test_confirmed_word_text_holds_effect_and_payments_but_not_physical_acceptance(self):
        for ext in (".docx", ".doc", ".pdf"):
            with self.subTest(ext=ext):
                graph = sample()
                graph["documents"][0]["ext"] = ext
                found = compute(graph)
                statuses = [f["status"] for f in found]
                if ext == ".pdf":
                    self.assertEqual(statuses, ["ok"] * 7)
                    self.assertNotIn("word_signatures", found[0]["effect_review"])
                    continue
                self.assertEqual(statuses, ["missing","ok","ok","missing","missing","missing","missing"])
                check = found[0]["effect_review"]["word_signatures"]
                self.assertEqual(check["pages"], ["d01/p1"])
                self.assertEqual([(r["state"], r["receipt_rev"]) for r in check["rows"]], [("checked",1)] * 2)
                for row in check["rows"]:
                    for f in [found[0], *found[3:]]:
                        self.assertIn(row["row"], f["evidence"])
                    self.assertNotIn(row["row"], found[1]["evidence"])

    def test_misclassified_date_omission_and_multiple_candidates_are_separate(self):
        graph = sample()
        graph["documents"][0]["ext"] = ".docx"
        ledger = graph["contract_effect_sources"]
        buyer = next(r for r in ledger["signing_rows"] if r["field"] == "buyer_signature")
        fact = next(f for f in graph["facts"] if f["id"] in buyer["facts"])
        fact["field"] = "buyer_sealed_on"
        def reading():
            return compute(graph)[0]["effect_review"]["word_signatures"]["rows"][0]
        self.assertEqual((reading()["state"], reading()["fact"]), ("field",fact["id"]))
        fact["status"] = "disputed"
        self.assertEqual(reading()["state"], "disputed")
        buyer["facts"] = []
        self.assertEqual((reading()["state"], reading()["fact"]), ("unread",None))
        buyer["facts"] = [fact["id"], "another"]
        self.assertEqual((reading()["state"], reading()["fact"]), ("multiple",None))
        ledger["signing_rows"] = []
        self.assertEqual(compute(graph)[0]["effect_review"]["word_signatures"]["rows"], [])
        ledger["pages"][0]["text_only"] = False
        self.assertNotIn("word_signatures", compute(graph)[0]["effect_review"])

    def test_old_word_positive_replays_and_requires_new_check_at_approval(self):
        graph = sample()
        graph["documents"][0]["ext"] = ".docx"
        read = original_reader(graph)
        old = copy.deepcopy(graph)
        old["contract_effect_sources"] = sources(old, read, IMAGE_FORMAT)
        def paper(g, policy):
            found = execute(g, g["profile"])
            for f in found:
                f["version"] = policy["version"]
            link_procedures(g, found, {"expert":{"model":"fixture"}, "pages":[]})
            return {"graph":g, "findings":found, "policy":{**policy,"profile":g["profile"]}}
        previous = paper(old, {**VERSION,"version":"2026.11.26.11","contract_effect":IMAGE_FORMAT})
        self.assertEqual(next(f for f in previous["findings"] if f["rule"] == "H01")["status"], "ok")
        verify(previous, read)
        verify_findings(previous)
        with self.assertRaisesRegex(ValueError, "签署凭证"):
            verify(previous, read, signing=True)
        current = paper(graph, VERSION)
        verify(current, read, signing=True)
        verify_findings(current)
        h01 = next(f for f in current["findings"] if f["rule"] == "H01")
        h01["effect_review"]["word_signatures"]["rows"][0]["receipt_rev"] = 27
        with self.assertRaisesRegex(ValueError, "证据图谱"):
            verify_findings(current)
        previous["policy"]["version"] = VERSION["version"]
        with self.assertRaises(ValueError):
            verify(previous, read)
