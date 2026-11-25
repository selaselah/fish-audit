import copy
import unittest

import reinspection_wait as waiting
from config import PERFORMANCE
from controls import VERSION, execute
from performance import verify_findings
from test_inspection_register import printed
from test_performance import rows
from test_reinspection import BANK_DOC, CONTRACT, FINAL, FIX, OLD, RECEIPT, WARRANTY, graph


TERM = "整改复验条件：整改完成后至少间隔48小时方可开始复验"
RUN = "试运行要求：整改完成后须连续试运行48小时无异常方可开始复验"
FIXED = "整改完成时刻：2026-09-23 09:00"
START = "复验开始时刻：2026-09-25 10:15"


def check(g):
    (finding,) = rows(g, "H02")
    return finding, finding["reinspection"]["timing"]


class ReinspectionWaitTests(unittest.TestCase):
    def test_wait_uses_only_native_recorded_events_and_flows_to_dependent_stages(self):
        for start, expected, status, bounds in (
            (START, "met", "ok", (177240, 177360)),
            ("复验开始时刻：2026-09-25 08:00", "early", "risk", (169140, 169260)),
            ("复验开始时刻：2026-09-25 09:00", "boundary", "missing", (172740, 172860)),
            ("复验开始日期：2026年9月25日", "boundary", "missing", (140340, 226800)),
        ):
            with self.subTest(start=start):
                g = graph(omissions=[(1, TERM), (3, FIXED), (4, start)])
                finding, t = check(g)
                self.assertEqual((t["state"], t["status"], finding["status"]), (expected, status, status))
                self.assertEqual((t["above_seconds"], t["below_seconds"]), bounds)
                self.assertTrue(set(t["sources"]) <= set(finding["evidence"]))
                phases = rows(g, "H04")
                self.assertEqual([p["status"] for p in phases], ["ok", status, status])
                self.assertNotIn(t["term_ref"], phases[0]["evidence"])
                self.assertTrue(
                    all(set(t["sources"]) <= set(f["evidence"]) for f in [*phases[1:], *rows(g, "H05")])
                )
                self.assertEqual(rows(g, "H05")[0]["status"], "risk" if expected == "met" else "missing")
                self.assertEqual((finding["reinspection"]["state"] == "closed"), expected == "met")

    def test_signed_day_bounds_start_but_does_not_prove_it(self):
        for day, expected, upper in (
            ("2026-09-24", "report_early", 172800),
            ("2026-09-26", "start_missing", 345600),
        ):
            g = graph(lambda i, f, l, v: day if i == 4 and f == "accepted_on" else v, omissions=[(1, TERM)])
            finding, t = check(g)
            self.assertEqual((t["state"], t["above_seconds"], t["below_seconds"]), (expected, None, upper))
            self.assertIsNone(t["start_ref"])
            self.assertIsNotNone(t["report_ref"])
            self.assertEqual(finding["reinspection"]["focus"], "final")
        g = graph(omissions=[(1, TERM), (4, "复验开始日期：2026-09-25")])
        _, t = check(g)
        self.assertEqual((t["above_seconds"], t["below_seconds"], t["state"]), (86400, 259200, "boundary"))

    def test_operation_scope_amendments_and_other_defects_require_review(self):
        for term, extras, expected in (
            (RUN, [], "operation_pending"),
            (TERM, [(1, TERM)], "terms_pending"),
            (TERM, [(1, "补充说明：门封整改另按双方函件处理")], "terms_pending"),
            (TERM, [(1, "付款条款：等待期缩短为24小时")], "terms_pending"),
            ("整改复验条件：整改后满两个工作日方可复验", [], "terms_pending"),
            (TERM, [(4, "未结整改项目：门封漏气待更换")], "chain_pending"),
            (TERM, [(3, "整改备注：目前仅作临时处理")], "chain_pending"),
            (TERM, [(3, FIXED)], "events_pending"),
            (TERM, [(4, START)], "events_pending"),
            (TERM, [(3, "整改完成时刻：2026-09-23 0 9:00")], "chain_pending"),
        ):
            with self.subTest(term=term, extras=extras):
                g = graph(omissions=[(1, term), (3, FIXED), (4, START), *extras])
                finding, t = check(g)
                self.assertEqual(t["state"], expected)
                self.assertNotEqual(finding["status"], "ok")
        for entry in ("复验开始时刻：2026-09-27 10:15", "整改完成时刻：2026-09-22 09:00"):
            extra = [(3, FIXED), (4, entry)] if entry.startswith("复验") else [(3, entry), (4, START)]
            finding, t = check(graph(omissions=[(1, TERM), *extra]))
            self.assertEqual((t["state"], finding["status"]), ("conflict", "risk"))

    def test_reinspection_scope_and_printed_precision(self):
        self.assertNotIn("timing", rows(graph(), "H02")[0]["reinspection"])
        simple = graph(groups=[CONTRACT, RECEIPT, WARRANTY, BANK_DOC], omissions=[(1, TERM)])
        self.assertEqual(rows(simple, "H02")[0]["status"], "ok")
        self.assertFalse(simple["reinspection_wait_sources"]["lines"])
        for bad in (
            "2026-02-29",
            "2026-09-23 09:60",
            "2026-09-23 09:00+08:00",
            "2026-09-2 3",
            "2026-09-23TT10:30",
            "2026-09-23 09:0*",
        ):
            self.assertIsNone(waiting.stamp(bad))
        self.assertEqual(waiting.stamp("2024年2月29日 23:59:59")["before"], "2024-03-01T00:00:00")
        generic = [("acceptance", "", "验收报告"), *FINAL[1:]]
        g = graph(groups=[CONTRACT, OLD, FIX, generic], omissions=[(1, TERM), (3, FIXED), (4, START)])
        self.assertEqual(check(g)[1]["state"], "met")
        page = dict(
            doc="d01",
            number=2,
            sha256="mixed",
            text="",
            layer={"type": "image", "clause_text_only": False},
            extraction={"output": {"quality": "readable", "facts": []}},
        )
        g = graph(omissions=[(1, TERM), (3, FIXED), (4, START)], extra_pages=[page])
        self.assertNotEqual(check(g)[0]["status"], "ok")
        unresolved, t = check(graph(extra_pages=[page]))
        self.assertNotEqual(unresolved["status"], "ok")
        self.assertEqual(t["state"], "terms_pending")
        self.assertIn("d01/p2", t["evidence"])

    def test_physical_source_rebuild_signed_history_and_tamper_checks(self):
        extra = [(1, TERM), (3, FIXED), (4, START)]
        g = graph(omissions=extra)
        paper = {
            "policy": {**VERSION, "profile": PERFORMANCE},
            "graph": g,
            "findings": execute(g, PERFORMANCE),
        }
        texts = printed(g, {(f"d{i:02d}", 1): [line] for i, line in extra})
        read = lambda d, n: texts[d, n]
        waiting.verify(paper, read)
        verify_findings(paper)
        for target in ("digest", "edge", "version", "hours", "conclusion"):
            broken = copy.deepcopy(paper)
            if target == "digest":
                broken["graph"]["reinspection_wait_sources"]["lines"][0]["page_sha256"] = "unrelated"
            elif target == "edge":
                next(e for e in broken["graph"]["edges"] if e["type"] == "reinspection_time_basis")["to"] += (
                    "x"
                )
            elif target == "version":
                del broken["policy"]["reinspection_wait"]
            else:
                timing = next(f for f in broken["findings"] if f["rule"] == "H02")["reinspection"]["timing"]
                timing["required_hours" if target == "hours" else "state"] = 1
            with self.subTest(target=target), self.assertRaises(ValueError):
                waiting.verify(broken, read)
                verify_findings(broken)
        with self.assertRaises(ValueError):
            waiting.verify(paper, lambda d, n: read(d, n) + " ")
        bare = graph(omissions=[(1, TERM)])
        old_text = printed(bare, {("d01", 1): [TERM]})
        del bare["reinspection_wait_sources"]
        bare["nodes"] = [n for n in bare["nodes"] if n["type"] != "reinspection_time_line"]
        bare["edges"] = [e for e in bare["edges"] if e["type"] != "reinspection_time_basis"]
        old = {"policy": {"version": "2026.11.26.07"}, "graph": bare, "findings": execute(bare, PERFORMANCE)}
        self.assertEqual(next(f for f in old["findings"] if f["rule"] == "H02")["status"], "ok")
        waiting.verify(old, lambda d, n: old_text[d, n])
        with self.assertRaisesRegex(ValueError, "重新审计"):
            waiting.verify(old, lambda d, n: old_text[d, n], signing=True)
