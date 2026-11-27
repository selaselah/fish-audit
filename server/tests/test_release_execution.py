import unittest
from copy import deepcopy

from config import PERFORMANCE
from controls import VERSION, execute
from performance import verify_findings
import release_execution as execution
from test_acceptance_originals import filed
from test_acceptance_execution import printed
from test_mandate_originals import word_source
from test_payment_releases import RELEASE, fixture
from test_pdf_execution import signed_copy


class ReleaseExecutionTests(unittest.TestCase):
    def test_pdf_digest_conflict_reaches_only_the_held_phase(self):
        raw = signed_copy(printed(fixture()[0], "d05"))
        # A change to the binary header comment leaves the printed release unchanged.
        offset = raw.index(b"%", raw.index(b"\n")+1)+1
        damaged = raw[:offset] + bytes([raw[offset]^1]) + raw[offset+1:]
        paper, text = filed(damaged, lambda:fixture()[0], unit="d05", ext=".pdf", render=True)
        record, = paper["graph"][execution.PDF]["records"]
        self.assertEqual(record["state"], "mismatch")
        checks = [f for f in paper["findings"] if record["id"] in f["evidence"]]
        self.assertEqual([(f["rule"], f["status"], f["stage"]["name"]) for f in checks],
                         [("H04","risk","第二期"),("H05","risk","第二期")])
        for f in checks:
            self.assertTrue(f["payment_opinion"]["release"]["signature_mismatch"])
            self.assertIn("电子签名与所签内容校验不符",f["detail"])
        execution.verify(paper, lambda _:damaged, text, signing=True)

    def test_word_comment_links_to_its_release_and_original(self):
        raw = word_source(rows=RELEASE, anchor_field="approval_signer", comment=True, note="请另经财务会签")
        paper, text = filed(raw, lambda: fixture()[0], unit="d05", render=True)
        graph = paper["graph"]
        proof, = graph[execution.NATIVE]["records"]
        word, = graph[execution.NATIVE]["documents"]
        note, = word["notes"]
        self.assertEqual((proof["state"], note["text"], note["location"]["unit"]), ("word_review", "请另经财务会签", "d05"))
        self.assertEqual(proof["notes"], [note["id"]])
        cited = [f for f in paper["findings"] if proof["id"] in f["evidence"]]
        self.assertEqual([f["rule"] for f in cited], ["H04", "H05"])
        for f in cited:
            r = f["payment_opinion"]["release"]
            self.assertNotEqual(f["status"], "ok")
            self.assertEqual(r["signature_records"], [proof["id"]])
            self.assertTrue({proof["id"], word["id"], note["id"], "d05", "d05/p1", *proof["fields"]} <= set(r["evidence"]))
        execution.verify(paper, lambda _:raw, text, signing=True)
        for edit in ("bytes","edge","note","program","case","stripped","decision"):
            with self.subTest(edit=edit):
                changed = deepcopy(paper)
                ledger = changed["graph"][execution.NATIVE]
                if edit=="edge":
                    changed["graph"]["edges"].remove(next(e for e in changed["graph"]["edges"] if e["type"]=="release_original_source"))
                if edit=="note":
                    ledger["documents"][0]["notes"][0]["text"]="已签批"
                if edit=="program":
                    changed["policy"]["code_sha256"]={}
                if edit=="case":
                    ledger["records"][0]["unit"]="d02"
                if edit=="decision":
                    next(f for f in changed["findings"] if f["rule"]=="H05")["payment_opinion"]["release"]["state"]="matched"
                if edit=="stripped":
                    del changed["policy"]["release_execution"]
                with self.assertRaises(ValueError):
                    if edit=="decision":
                        verify_findings(changed)
                    else:
                        execution.verify(changed, lambda _: raw+b"!" if edit=="bytes" else raw, text)

    def test_historical_named_release_replays_but_requires_review_before_new_signoff(self):
        graph, text = fixture()
        for key in (execution.NATIVE, execution.PDF):
            del graph[key]
        old = {**VERSION, "profile": PERFORMANCE, "version": "2026.11.27.10"}
        del old["release_execution"]
        del old["release_comparison"]
        report = {"policy":old, "graph":graph, "findings":execute(graph, PERFORMANCE)}
        r, = [f["payment_opinion"]["release"] for f in report["findings"] if f["rule"]=="H05"]
        self.assertEqual((r["state"],r["timing"]), ("matched","after"))
        execution.verify(report, lambda _:None, text)
        with self.assertRaisesRegex(ValueError,"重审"):
            execution.verify(report, lambda _:None, text, signing=True)
