import copy
import unittest

from acceptance_reservations import classify, edges, sources, verify
from controls import VERSION, execute
from performance import compute, verify_findings
from performance_versions import PAYMENT_WINDOW_FORMAT
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material
from test_reinspection import graph as repaired


NOTE = "验收备注：仅作到货签收，整机性能尚未检验，最终验收另行办理"


def original(read_note=True, reading="柜温3℃"):
    graph = material([CONTRACT, RECEIPT, WARRANTY, BANK_DOC],
                     lambda i,k,l,v:reading if i==2 and k=="measured_result" else v,
                     omissions=[(2,NOTE)] if read_note else ())
    raw = {d["id"]:"\n".join(f["quote"] for f in graph["facts"] if f["doc"]==d["id"]) for d in graph["documents"]}
    if read_note:
        raw["d02"] += "\n"+NOTE
    return graph,lambda doc,page:raw[doc]


class AcceptanceReservationsTests(unittest.TestCase):
    def test_printed_term_survives_an_omission_and_holds_only_dependent_payments(self):
        graph, read = original()
        findings = compute(graph)
        self.assertEqual([f["status"] for f in findings],["ok","risk","ok","ok","risk","risk","missing"])
        note, = findings[1]["acceptance_reservations"]["lines"]
        self.assertEqual((note["quote"],note["line"],note["facts"]),(NOTE,len(read("d02",1).splitlines()),[]))
        self.assertIn("d02/p1",findings[1]["evidence"])
        self.assertEqual(compute(graph,PAYMENT_WINDOW_FORMAT)[1]["status"],"ok")
        graph, _ = original(reading="柜温8℃")
        self.assertEqual(compute(graph)[1]["status"],"issue")
        self.assertIn("超出",compute(graph)[1]["detail"])

    def test_scan_requires_full_page_even_if_the_model_reads_no_reservation(self):
        graph, read = original(False)
        node = next(n for n in graph["nodes"] if n["id"]=="d02/p1")
        for native in (True,False):
            node.update(layer="text" if native else "image",clause_text_only=False)
            graph["acceptance_reservation_sources"] = sources(graph,read)
            finding = compute(graph)[1]
            self.assertEqual(finding["status"],"missing")
            self.assertEqual(finding["acceptance_reservations"]["lines"],[])
            self.assertEqual(finding["acceptance_reservations"]["mixed_pages"][0]["native"],native)
        self.assertIsNone(classify("验收备注：无保留意见"))
        self.assertIsNone(classify("备注：验收款以收款方实际到账日为准"))
        self.assertEqual(classify("验收备注：详见清单"),"unclear")
        self.assertEqual(classify("验收签认（仅作到货签收）：许澄"),"limited")

    def test_new_reservation_in_the_retest_keeps_the_original_failure_open(self):
        graph = repaired(omissions=[(4,"复验备注：整机性能待测，最终验收另行办理")])
        finding = compute(graph)[1]
        self.assertEqual((finding["status"],finding["reinspection"]["state"]),("issue","open"))
        self.assertIn("d04/p1",finding["evidence"])
        self.assertEqual(finding["acceptance_reservations"]["lines"][0]["unit"],"d04")
        self.assertEqual(compute(graph,PAYMENT_WINDOW_FORMAT)[1]["reinspection"]["state"],"closed")

    def test_archive_and_legacy_approval_rebuild_original_lines_and_edges(self):
        graph, read = original()
        report={"policy":{**VERSION,"profile":graph["profile"]},"graph":graph,"findings":execute(graph,graph["profile"])}
        verify(report,read)
        verify_findings(report)
        for what in ("marker","ledger","edge","finding"):
            changed=copy.deepcopy(report)
            if what=="marker":
                del changed["policy"]["acceptance_reservations"]
            if what=="ledger":
                changed["graph"]["acceptance_reservation_sources"]["lines"].clear()
            if what=="edge":
                changed["graph"]["edges"].remove(edges(graph["acceptance_reservation_sources"])[0])
            if what=="finding":
                next(f for f in changed["findings"] if f["rule"]=="H02")["acceptance_reservations"]["lines"]=[]
            with self.assertRaises(ValueError):
                verify_findings(changed) if what=="finding" else verify(changed,read)
        legacy={k:v for k,v in graph.items() if k!="acceptance_reservation_sources"}
        old={"policy":{"performance_checks":PAYMENT_WINDOW_FORMAT},"graph":legacy,"findings":compute(legacy,PAYMENT_WINDOW_FORMAT)}
        verify(old,read)
        with self.assertRaisesRegex(ValueError,"旧版终验"):
            verify(old,read,signing=True)
