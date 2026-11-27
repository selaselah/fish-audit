import unittest
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch

from config import PERFORMANCE
from controls import VERSION, execute
from performance import compute, verify_findings
import release_comparison
import release_execution
from test_acceptance_execution import printed
from test_payment_releases import BANK, RELEASE, fixture as payment_fixture


CONTINUE = "维持第二期验收款暂缓，继续暂停支付"


def fixture(**options):
    graph, text = payment_fixture(**options)
    files = {}
    for doc in graph["documents"]:
        if doc["id"] in release_comparison.units(graph["payment_release_sources"]):
            lines = [{"doc":doc["id"], "quote":s} for s in text(doc["id"],1).splitlines()]
            raw = printed({"facts":lines}, doc["id"])
            files[doc["id"]] = raw
            doc.update(ext=".pdf", pages=1, sha256=sha256(raw).hexdigest())
    ledgers = release_execution.sources(graph, lambda d:files[d["id"]], text)
    graph.update(ledgers)
    nodes, edges = release_execution.source_graph(ledgers)
    graph["nodes"].extend(nodes)
    graph["edges"].extend(edges)
    return graph, text


def slip(decision=CONTINUE, **changes):
    return [(k,l,decision if l == "放行决定" else changes.get(k,v)) for k,l,v in RELEASE]


def compared(graph):
    return [f for f in compute(graph) if f.get("payment_opinion",{}).get("release",{}).get("instruments")]


class ReleaseComparisonTests(unittest.TestCase):
    def test_opposed_written_decisions_stay_with_the_same_installment_and_receipt(self):
        graph, _ = fixture(extra=[slip(release_signed_on="2026-09-25"), BANK])
        fs = compute(graph)
        self.assertEqual([f["status"] for f in fs if f["rule"] in ("H01","H02","H03","H04","H05")],
                         ["ok","ok","ok","ok","risk","ok","risk","risk"])
        phase, first, second = compared(graph)
        for finding in (phase, first, second):
            check = finding["payment_opinion"]["release"]
            self.assertEqual((check["state"], finding["stage"]["name"]), ("decision_conflict","第二期"))
            self.assertEqual([(r["unit"], r["binding"], r["stance"], r["signed_on"]) for r in check["instruments"]],
                [("d05","same","resume","2026-09-23"), ("d06","same","hold","2026-09-25")])
            self.assertTrue(all(r["receipt_ref"] in finding["evidence"] and r["date_ref"] in finding["evidence"] for r in check["instruments"]))
            self.assertIn(check["original_ref"], finding["evidence"])
            self.assertIsNone(check["signed_on"])
        self.assertNotEqual(first["payment_opinion"]["release"]["paid_ref"], second["payment_opinion"]["release"]["paid_ref"])
        self.assertTrue(all(f["payment_opinion"]["release"]["timing"]=="unknown" for f in (first,second)))

    def test_cross_receipt_cross_phase_and_same_dispositions_require_review(self):
        for form, bound in ((slip(original_acceptance="YS-12345679"),"other_receipt"),
                            (slip(CONTINUE.replace("第二期","第三期")),"other_phase"),
                            (slip(RELEASE[6][2], release_signed_on="2026-09-25"),"same"),
                            (slip(original_acceptance="尾号5678"),"unresolved"),
                            (slip("原则上同意放行，仍须董事会批准"),"unresolved"),
                            (slip(buyer="其他演练采购方"),"unresolved")):
            with self.subTest(form=form):
                g, _ = fixture(extra=[form])
                for f in compared(g):
                    check = f["payment_opinion"]["release"]
                    self.assertEqual((check["state"], check["instruments"][1]["binding"], f["status"]),
                                     ("multiple_pending",bound,"missing"))
                self.assertEqual(len(compared(g)), 2)

    def test_disputed_or_qualified_source_cannot_create_a_conflict(self):
        for opts in ({"omissions":[(6,"附注：仅作会签草稿")]},
                     {"attestations":{"d06/p1/f7":{"decision":"dispute"}}},
                     {"omissions":[(2,"验收单编号说明：所列均为尾号")]},
                     {"extra":[[*slip(), ("other","放行决定", RELEASE[6][2])]]}):
            with self.subTest(opts=opts):
                g, _ = fixture(**{"extra":[slip()], **opts})
                self.assertFalse(any(f.get("payment_opinion",{}).get("release",{}).get("state")=="decision_conflict" for f in compute(g)))

    def test_historical_replay_and_modified_bindings(self):
        g, _ = fixture(extra=[slip()])
        paper = {"graph":g, "policy":{**VERSION,"profile":PERFORMANCE}, "findings":execute(g, PERFORMANCE)}
        release_comparison.program(paper)
        verify_findings(paper)
        changed = deepcopy(paper)
        f = next(f for f in changed["findings"] if f["rule"]=="H05")
        f["payment_opinion"]["release"]["instruments"][1]["receipt_ref"] = f["payment_opinion"]["release"]["instruments"][0]["receipt_ref"]
        with self.assertRaises(ValueError):
            verify_findings(changed)
        del changed["graph"][release_comparison.KEY]
        with self.assertRaises(ValueError):
            release_comparison.program(changed)
        changed["policy"]["version"] = "2026.11.27.11"
        del changed["policy"][release_comparison.KEY]
        with patch("controls.RULE_VERSION", changed["policy"]["version"]):
            changed["findings"] = execute(changed["graph"], PERFORMANCE)
        release_comparison.program(changed)
        verify_findings(changed)
        self.assertFalse(compared(changed["graph"]))
