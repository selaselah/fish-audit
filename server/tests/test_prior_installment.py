import copy
import unittest

import prior_installment
import stage_payments
from config import PERFORMANCE
from controls import VERSION, execute
from performance import verify_findings
from test_stage_payments import fixture


TERM = "验收款放款条件：首款须已付足，以付款银行成功回单为据"
CREDIT = "验收款放款条件：须由供应方确认首款已足额到账"
SUBMISSION = "2026-11-25T22:10:00+00:00"


def paper(payments=(("第一期", "30000", "2026-09-10"), ("第二期", "60000", "2026-09-21")),
          term=TERM, extra=(), **kwargs):
    uses, amounts, dates = zip(*payments) if payments else ((), (), ())
    refs = kwargs.pop("refs", [f"YL-P-{i}" for i in range(len(uses))])
    graph = fixture(amounts, refs, dates, uses, omissions=[(1, term), *extra], **kwargs)
    graph["prior_installment_as_of"] = "2026-11-26"
    findings = execute(graph, PERFORMANCE)
    return {"graph": graph, "policy": {**VERSION, "profile": PERFORMANCE}, "findings": findings}


def phase(report, rule, name="第二期"):
    return next(f for f in report["findings"] if f["rule"] == rule and f.get("stage", {}).get("name") == name)


def reader(report, term=TERM):
    def read(doc, page):
        lines = [f["quote"] for f in report["graph"]["facts"] if (f["doc"], f["page"]) == (doc, page)]
        if doc == "d01":
            lines.append(term)
        return "\n".join(lines)
    return read


class PriorInstallmentTests(unittest.TestCase):
    def test_terms_and_bank_slip_have_independent_source_paths(self):
        report = paper()
        prior_installment.verify(report, reader(report), submitted=SUBMISSION)
        verify_findings(report)
        h04, h05 = (phase(report, code)["prior_installment"] for code in ("H04", "H05"))
        self.assertEqual((h04["state"], h04["expected"], h04["seen"], h04["covered_on"]),
                         ("met", "30000.00", "30000.00", "2026-09-10"))
        self.assertEqual((h05["before"], h05["on_day"], h05["payment_date"]), ("30000.00", "0.00", "2026-09-21"))
        self.assertIn(h05["payment_date_ref"], h05["evidence"])
        self.assertTrue(set(h05["records"][0]["refs"].values()) <= set(h05["evidence"]))
        self.assertNotIn("prior_installment", phase(report, "H04", "第三期"))
        self.assertNotIn("prior_installment", phase(report, "H05", "第一期"))

    def test_time_slices_follow_each_dependent_payment(self):
        report = paper((("第一期", "10000", "2026-09-10"), ("第一期", "20000", "2026-09-24"),
                        ("第二期", "25000", "2026-09-21"), ("第二期", "20000", "2026-09-24"),
                        ("第二期", "15000", "2026-09-25")))
        self.assertEqual(phase(report, "H04")["status"], "ok")
        rows = [f for f in report["findings"] if f["rule"] == "H05" and f.get("prior_installment")]
        self.assertEqual([(f["status"], f["prior_installment"]["state"], f["prior_installment"]["before"],
                           f["prior_installment"]["on_day"]) for f in rows],
                         [("risk", "early", "10000.00", "0.00"), ("missing", "same_day", "10000.00", "20000.00"),
                          ("ok", "met", "30000.00", "0.00")])
        self.assertEqual(phase(report, "H06")["status"], "risk")

    def test_missing_partial_unassigned_repeated_and_unverified_are_distinct(self):
        target = ("第二期", "60000", "2026-09-21")
        for first, params, state, seen in (
            ([], {}, "absent", None),
            ([("第一期", "10000", "2026-09-10")], {}, "partial", "10000.00"),
            ([("其他货款", "30000", "2026-09-10")], {}, "allocation", None),
            ([("第一期", "30000", "2026-11-26")], {}, "unverified", None),
            ([("第一期", "30000", "2026-09-10")], {"edits": {0: {"payer": "演练丙"}}}, "unverified", None),
            ([("第一期", "30000", "2026-09-10")], {"refs": ("***21", "YL-2")}, "unverified", None),
            ([("第一期", "30000", "2026-09-10")], {"extra": ((4, "其他：该笔后来退汇"),)}, "unverified", None),
            ([("第一期", "30000", "2026-09-10")] * 2, {"refs": ("YL-1", "YL-1", "YL-3")}, "disputed", None),
        ):
            with self.subTest(state=state, params=params):
                r = paper((*first, target), **params)
                for code in ("H04", "H05"):
                    entry = phase(r, code)["prior_installment"]
                    self.assertEqual((entry["state"], entry["seen"]), (state, seen))
                    self.assertNotEqual(phase(r, code)["status"], "ok")

    def test_credit_conflicting_terms_and_other_conditions(self):
        for r, expected in ((paper(term=CREDIT), "credit"), (paper(extra=[(1, CREDIT)]), "terms"),
                            (paper(term="验收款放款条件：首款已付足后另行确认"), "terms")):
            p = phase(r, "H04")["prior_installment"]
            self.assertEqual((p["state"], p["seen"], p["expected"]), (expected, None, None))
            self.assertEqual(phase(r, "H04", "第一期")["status"], "ok")
        r = paper(contract_edits={"acceptance_criteria": "柜温不高于2℃"})
        self.assertNotEqual(phase(r, "H04")["status"], "ok")
        self.assertNotEqual(next(f for f in r["findings"] if f["rule"]=="H02")["status"], "ok")

    def test_archive_recomputes_terms_source_graph_cutoff_and_historical_approval(self):
        report = paper()
        for what in ("cutoff", "node", "edge", "quote", "marker", "amount", "date"):
            r = copy.deepcopy(report)
            g = r["graph"]
            if what == "cutoff": g["prior_installment_as_of"] = "2026-11-25"
            if what == "node": next(n for n in g["nodes"] if n["type"] == "prior_installment_term")["page"] = 2
            if what == "edge": next(e for e in g["edges"] if e["type"] == "prior_installment_source")["evidence"] = []
            if what == "quote": g["prior_installment_sources"]["lines"][0]["quote"] = "另有约定"
            if what == "marker": del r["policy"]["prior_installment"]
            if what == "amount": phase(r, "H04")["prior_installment"]["seen"] = "80000.00"
            if what == "date": phase(r, "H05")["prior_installment"]["payment_date_ref"] = "foreign"
            with self.subTest(what=what), self.assertRaises(ValueError):
                if what in ("amount", "date"):
                    verify_findings(r)
                else:
                    prior_installment.verify(r, reader(r), submitted=SUBMISSION)
        g = report["graph"]
        g.pop("prior_installment_sources")
        g.pop("prior_installment_as_of")
        g["nodes"] = [n for n in g["nodes"] if n["type"] != "prior_installment_term"]
        g["edges"] = [e for e in g["edges"] if e["type"] != "prior_installment_source"]
        g["stage_payment_sources"] = stage_payments.sources(g, reader(report))
        report["policy"].pop("prior_installment")
        report["policy"]["version"] = "2026.11.26.04"
        report["findings"] = execute(g, PERFORMANCE)
        self.assertEqual(phase(report, "H04")["status"], "ok")
        prior_installment.verify(report, reader(report))
        with self.assertRaisesRegex(ValueError, "首款凭证约定"):
            prior_installment.verify(report, reader(report), signing=True)
