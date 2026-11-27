import unittest
from copy import deepcopy
from unittest.mock import patch

from config import PERFORMANCE
from controls import execute
from performance import verify_findings
from test_acceptance_execution import printed
from test_acceptance_originals import filed
from test_mandate_originals import word_source
from test_pdf_execution import later_copy, signed_copy
from test_warranty_terms import audit
import warranty_execution as execution


def warranty_findings(report):
    return [f for f in report["findings"] if f.get("warranty_check")]


class WarrantyExecutionTests(unittest.TestCase):
    def test_pdf_signed_ranges_do_not_establish_execution_or_close_the_warranty(self):
        plain = printed(audit(), "d03")
        signed = signed_copy(plain)
        index = signed.index(b"%", signed.index(b"\n") + 1) + 1
        mismatch = signed[:index] + bytes([signed[index] ^ 1]) + signed[index+1:]
        for state, original in (("typeset",plain),("current",signed),("earlier",later_copy(signed)),("mismatch",mismatch)):
            with self.subTest(state=state):
                report, text = filed(original, audit, "d03", ".pdf", render=True)
                record, = report["graph"][execution.PDF]["records"]
                self.assertEqual(record["state"], state)
                checks = warranty_findings(report)
                self.assertEqual([f["rule"] for f in checks], ["H04","H05"])
                for f in checks:
                    w = f["warranty_check"]
                    self.assertEqual((w["stated_on"],w["confirmed_on"],w["calendar_end"]), ("2026-11-21",None,"2026-11-20"))
                    self.assertEqual((w["certificate"]["state"],w["certificate"]["linked"]), (state,True))
                    self.assertTrue({record["id"],"d03","d03/p1",*record["fields"]} <= set(f["evidence"]))
                    self.assertEqual(f["status"], "risk" if state=="mismatch" else "missing")
                other = [f for f in report["findings"] if f["rule"]=="H04" and f not in checks]
                self.assertTrue(all(f["status"]=="ok" and record["id"] not in f["evidence"] for f in other))
                self.assertFalse(any(e["type"]=="warranty_release_basis" for e in report["graph"]["edges"]))
                execution.verify(report, lambda _:original, text, signing=True)

    def test_word_comment_and_reported_date_are_independently_verifiable(self):
        rows = [(f["field"],f["quote"].split("：")[0] if "：" in f["quote"] else "",f["value"])
                for f in audit()["facts"] if f["doc"]=="d03"]
        raw = word_source(rows=rows,anchor_field="warranty_defects",comment=True,note="待核维修关闭原件")
        report, text = filed(raw, audit, "d03", ".docx", render=True)
        graph = report["graph"]
        record, = graph[execution.NATIVE]["records"]
        word, = graph[execution.NATIVE]["documents"]
        note, = word["notes"]
        self.assertEqual((record["state"],note["text"],note["location"]["line"]), ("word_review","待核维修关闭原件",9))
        for f in warranty_findings(report):
            self.assertTrue({word["id"], note["id"], *note["location"]["facts"]} <= set(f["warranty_check"]["certificate"]["evidence"]))
            self.assertNotEqual(f["status"], "ok")
        execution.verify(report, lambda _:raw, text, signing=True)
        for mode in ["original","edge","marker","date","status"]:
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                changed = deepcopy(report)
                check = warranty_findings(changed)[0]
                if mode in ("date","status"):
                    if mode=="date":
                        check["warranty_check"]["confirmed_on"] = "2026-11-22"
                    else:
                        check["status"] = "ok"
                    verify_findings(changed)
                else:
                    if mode=="edge":
                        changed["graph"]["edges"].remove(next(e for e in changed["graph"]["edges"] if e["type"]=="warranty_original_comment"))
                    if mode=="marker":
                        del changed["policy"]["warranty_execution"]
                    execution.verify(changed, lambda _:raw+b"!" if mode=="original" else raw, text)

    def test_payment_compares_printed_dates_only_with_its_own_installment(self):
        for designation, paid, status in (("第三期","2026-11-20","risk"),("第三期","2026-11-21","missing"),("第二期","2026-11-20","ok")):
            with self.subTest(designation=designation,paid=paid):
                fixture = lambda:audit(edit=lambda i,k,l,v:{"payment_designation":designation,"paid_on":paid}.get(k,v))
                raw = printed(fixture(), "d03")
                report, _ = filed(raw, fixture, "d03", ".pdf", render=True)
                bank, = [f for f in report["findings"] if f["rule"]=="H05"]
                self.assertEqual(bank["status"],status)
                if designation=="第三期":
                    self.assertIn("单上所列期满日" if status=="missing" else "确认单所列期满日", bank["detail"])
                else:
                    self.assertNotIn("warranty_check", bank)

    def test_historical_positive_execution_replays_but_requires_fresh_signoff_evidence(self):
        raw = printed(audit(), "d03")
        report, text = filed(raw, audit, "d03", ".pdf", render=True)
        graph = report["graph"]
        for key in (execution.NATIVE,execution.PDF):
            del graph[key]
        for key in ("nodes","edges"):
            graph[key] = [r for r in graph[key] if not r["type"].startswith(("warranty_original_","warranty_pdf_","warranty_word_"))]
        report["policy"].pop("warranty_execution")
        report["policy"]["version"] = "2026.11.27.12"
        with patch("controls.RULE_VERSION",report["policy"]["version"]):
            report["findings"] = execute(graph,PERFORMANCE)
        self.assertTrue(all(f["status"]=="ok" for f in warranty_findings(report)))
        execution.verify(report, lambda _:raw, text)
        with self.assertRaisesRegex(ValueError,"重审"):
            execution.verify(report, lambda _:raw, text, signing=True)
