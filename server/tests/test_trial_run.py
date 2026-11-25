import copy
import unittest

import reinspection_wait as waiting
from config import PERFORMANCE
from controls import VERSION, execute
from performance import verify_findings
from test_inspection_register import printed
from test_performance import rows
from test_reinspection import graph
from test_reinspection_wait import FIXED, RUN, START

SERIAL = "SN-FR-70123"
HEADER = [
    "试运行设备：" + SERIAL,
    "日志口径：北京时间，区间含起不含止，边界为整分",
    "日志签认范围：本页复验签认涵盖全部试运行记录",
]
FIRST = "运行记录：2026-09-23 09:15 至 2026-09-24 09:15 | 连续无异常"
SECOND = "运行记录：2026-09-24 09:15 至 2026-09-25 09:45 | 连续无异常"


def scoped(i, f, label, value):
    if f == "subject":
        return "冷藏柜（序列号 " + SERIAL + "）"
    if f in ("quantity_agreed", "quantity_accepted"):
        return "1台"
    return value


def material(records, *, edit=scoped, extra=(), start=START):
    additions = [(1, RUN), (3, FIXED), *([(4, start)] if start else []), *((4, r) for r in records), *extra]
    return graph(edit, omissions=additions), additions


def assess(g):
    (finding,) = rows(g, "H02")
    t = finding["reinspection"]["timing"]
    return finding, t, t.get("operation", {})


class TrialRunTests(unittest.TestCase):
    def test_adjacent_exact_intervals_use_only_same_signed_device_and_originals(self):
        g, _ = material([*HEADER, SECOND, FIRST])
        finding, t, run = assess(g)
        self.assertEqual((finding["status"], t["state"], run["longest_seconds"]), ("ok", "run_met", 174600))
        self.assertEqual(run["serial"], run["log_serial"])
        self.assertEqual([r["seconds"] for r in run["intervals"]], [86400, 88200])
        self.assertEqual(run["gaps"], [])
        self.assertTrue(set(run["sources"]) <= set(t["sources"]) <= set(finding["evidence"]))
        phases = rows(g, "H04")
        self.assertEqual([r["status"] for r in phases], ["ok", "ok", "ok"])
        self.assertNotIn(t["term_ref"], phases[0]["evidence"])
        self.assertTrue(
            all(set(run["sources"]) <= set(f["evidence"]) for f in [*phases[1:], *rows(g, "H05")])
        )
        self.assertEqual(
            assess(material([*HEADER, FIRST, SECOND.replace("25 09:45", "25 09:15")])[0])[1]["state"],
            "run_met",
        )

    def test_missing_short_overlapping_and_faulty_intervals(self):
        later = SECOND.replace("24 09:15", "24 09:45")
        fault = "运行记录：2026-09-24 09:15 至 2026-09-24 09:45 | 故障停机"
        for records, state, status, longest in (
            ([FIRST, later], "run_gap", "missing", 86400),
            ([FIRST, fault, later], "run_fault", "risk", 86400),
            ([FIRST], "run_short", "missing", 86400),
            ([FIRST, SECOND, FIRST], "run_overlap", "missing", None),
            ([FIRST, SECOND.replace("24 09:15", "24 09:14")], "run_overlap", "missing", None),
            ([FIRST.replace("连续无异常", "抽测无异常"), SECOND], "run_record", "missing", None),
            ([FIRST.replace("23 09:15", "23 08:59"), SECOND], "run_window", "missing", None),
            ([FIRST, SECOND.replace("25 09:45", "25 10:16")], "run_window", "missing", None),
        ):
            with self.subTest(state=state):
                g, _ = material([*HEADER, *records])
                f, t, op = assess(g)
                self.assertEqual((t["state"], f["status"], op["longest_seconds"]), (state, status, longest))
                self.assertEqual([p["status"] for p in rows(g, "H04")], ["ok", status, status])
                self.assertEqual(rows(g, "H05")[0]["status"], "missing")
                if state == "run_gap":
                    self.assertEqual([gap["seconds"] for gap in op["gaps"]], [1800])
                if state == "run_fault":
                    self.assertEqual([i["seconds"] for i in op["intervals"] if i["state"] == "fault"], [1800])
        self.assertEqual(assess(material([*HEADER, FIRST, SECOND], start=None)[0])[1]["state"], "run_window")
        # The contract only requires one full consecutive run. An earlier gap cannot be counted in that run.
        g, _ = material(
            [*HEADER, FIRST.replace("24 09:15", "23 09:20"), SECOND.replace("24 09:15", "23 09:45")]
        )
        self.assertEqual((assess(g)[1]["state"], assess(g)[2]["longest_seconds"]), ("run_met", 172800))

    def test_scope_clock_and_confirmed_signature_are_indispensable(self):
        for header, extra, state in (
            ([HEADER[0] + "7", *HEADER[1:]], [], "run_device"),
            ([HEADER[0].replace("70123", "XX123"), *HEADER[1:]], [], "run_device"),
            ([*HEADER, HEADER[0]], [], "run_device"),
            ([HEADER[0], "日志口径：北京时间", HEADER[2]], [], "run_record"),
            (HEADER[:2], [], "run_record"),
            (HEADER, [(2, "设备编号另见附页")], "run_device"),
            (HEADER, [(4, "签认附言：门封待更换")], "chain_pending"),
        ):
            g, _ = material([*header, FIRST, SECOND], extra=extra)
            self.assertEqual(assess(g)[1]["state"], state)
        for f, value in (("subject", "冷藏柜"), ("quantity_accepted", "2台")):
            g, _ = material(
                [*HEADER, FIRST, SECOND], edit=lambda i, k, l, v: value if k == f else scoped(i, k, l, v)
            )
            self.assertNotEqual(assess(g)[0]["status"], "ok")
        g, _ = material([*HEADER, FIRST, SECOND])
        next(f for f in g["facts"] if f["doc"] == "d04" and f["field"] == "acceptance_signer")["status"] = (
            "anchored"
        )
        self.assertNotEqual(assess(g)[0]["status"], "ok")

    def test_source_rebuild_downgrade_and_forged_gaps(self):
        g, additions = material([*HEADER, FIRST, SECOND.replace("24 09:15", "24 09:45")])
        extra = {}
        for i, line in additions:
            extra.setdefault((f"d{i:02d}", 1), []).append(line)
        pages = printed(g, extra)
        read = lambda d, n: pages[d, n]
        report = {
            "graph": g,
            "policy": {**VERSION, "profile": PERFORMANCE},
            "findings": execute(g, PERFORMANCE),
        }
        waiting.verify(report, read)
        verify_findings(report)
        for target in ("page", "hash", "edge", "version", "duration", "gap", "serial"):
            r = copy.deepcopy(report)
            row = next(
                s for s in r["graph"]["reinspection_wait_sources"]["lines"] if s["kind"] == "run_segment"
            )
            if target == "page":
                row["page"] += 1
            elif target == "hash":
                row["source_sha256"] += "x"
            elif target == "edge":
                r["graph"]["edges"].remove(next(e for e in r["graph"]["edges"] if e["to"] == row["id"]))
            elif target == "version":
                r["policy"]["reinspection_wait"] = waiting.LEGACY
            else:
                op = next(f for f in r["findings"] if f["rule"] == "H02")["reinspection"]["timing"][
                    "operation"
                ]
                if target == "duration":
                    op["longest_seconds"] += 1800
                elif target == "gap":
                    op["gaps"] = []
                else:
                    op["serial"] += "9"
            with self.subTest(target=target), self.assertRaises(ValueError):
                waiting.verify(r, read)
                verify_findings(r)
