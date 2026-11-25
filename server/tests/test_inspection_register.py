import copy
import unittest

import acceptance_reservations as reservations
from config import PERFORMANCE
from controls import VERSION, execute
from performance import verify_findings
from test_performance import rows
from test_reinspection import BANK_DOC, CONTRACT, FINAL, FIX, OLD, WARRANTY, graph


OPEN = "未结整改项目：QX-02 门封漏气，待更换门封条"
CLEAR = "未结整改项目：无"


def printed(graph, extras):
    table = {}
    for f in graph["facts"]:
        loc = f.get("source_line")
        if loc:
            table.setdefault((f["doc"], f["page"]), {})[loc["number"]] = loc["text"]
    return {(doc, page): "\n".join([*(raw[n] for n in sorted(raw)), *extras.get((doc, page), [])])
            for (doc, page), raw in table.items()}


class InspectionRegisterTests(unittest.TestCase):
    def test_all_final_rows_remain_locatable_and_only_acceptance_dependent_installments_are_held(self):
        g = graph(omissions=[(4, CLEAR), (4, OPEN), (4, OPEN)])
        check, = rows(g, "H02")
        self.assertEqual((check["status"], check["reinspection"]["state"]), ("risk", "open"))
        register = check["reinspection"]["register"]
        self.assertEqual([s["kind"] for s in register["lines"]], ["clear", "open", "open"])
        self.assertEqual(len({s["line"] for s in register["lines"]}), 3)
        self.assertTrue(all(not s["facts"] for s in register["lines"]))
        phases = rows(g, "H04")
        self.assertEqual([s["status"] for s in phases], ["ok", "risk", "risk"])
        self.assertNotIn("d04/p1", phases[0]["evidence"])
        self.assertTrue(all("d04/p1" in s["evidence"] for s in [check, *phases[1:], *rows(g, "H05")]))
        self.assertEqual(rows(g, "H05")[0]["status"], "missing")

    def test_closure_must_match_defect_id_and_subject_on_substantiated_reinspection(self):
        for raw, kind, status in (
            (CLEAR, "clear", "ok"),
            ("整改明细：QX-01 温控探头失准，已关闭", "matched", "ok"),
            ("整改明细：QX-02 温控探头失准，已关闭", "reported_closed", "missing"),
            ("整改明细：QX-01 门封漏气，已关闭", "reported_closed", "missing"),
            ("整改明细：QX-01 温控探头失准和门封漏气，已关闭", "reported_closed", "missing"),
            ("整改明细：QX-0 1 温控探头失准，已关闭", "reported_closed", "missing"),
            ("签认附言：待连续试运行72小时后签发最终报告", "conditional", "risk"),
            ("签认附言：若门封漏气待更换门封条", "unreviewed", "missing"),
            ("验收建议：按另函办理", "unreviewed", "missing"),
            ("  QX-05 门封条情况另附", "unreviewed", "missing"),
        ):
            with self.subTest(raw=raw):
                g = graph(omissions=[(4, raw)])
                check, = rows(g, "H02")
                line, = check["reinspection"]["register"]["lines"]
                self.assertEqual((line["kind"], check["status"]), (kind, status))
        broken = graph(lambda i,f,l,v: None if (i,f)==(3,"repair_signer") else v,
                       omissions=[(4,"整改明细：QX-01 温控探头失准，已关闭")])
        check, = rows(broken, "H02")
        self.assertEqual((check["status"],check["reinspection"]["register"]["lines"][0]["kind"]), ("issue","reported_closed"))

    def test_generic_final_form_attachment_and_image_require_same_scope(self):
        generic = [("acceptance","","验收报告"), *FINAL[1:]]
        page = dict(doc="d04", number=2, sha256="page-2", text=OPEN,
                    layer={"type":"text","clause_text_only":True,"lines":{"1":[[0,.1,.9,.2]]}},
                    extraction={"output":{"quality":"readable","facts":[]}})
        groups = [CONTRACT, OLD, FIX, generic, WARRANTY, BANK_DOC]
        single = graph(groups=groups, omissions=[(4,OPEN)])
        self.assertEqual(rows(single,"H02")[0]["reinspection"]["register"]["lines"][0]["unit"], "d04")
        packet = graph(groups=groups, extra_pages=[page])
        self.assertNotEqual(rows(packet,"H02")[0]["status"], "ok")
        self.assertEqual(packet["acceptance_reservation_sources"]["final_register"]["lines"][0]["page"], 2)
        g = graph(extra_pages=[page])
        r = rows(g, "H02")[0]["reinspection"]["register"]
        self.assertEqual([(s["unit"],s["page"],s["line"],s["kind"]) for s in r["lines"]], [("d04",2,1,"open")])
        g = graph(extra_pages=[{**page,"text":"","layer":{"type":"image","lines":{}}}])
        r = rows(g, "H02")[0]["reinspection"]["register"]
        self.assertEqual((r["status"], [p["page"] for p in r["mixed_pages"]]), ("missing",[2]))
        # A bank note has its own scope and cannot become a reinspection finding.
        self.assertEqual(rows(graph(omissions=[(6,OPEN)]), "H02")[0]["status"], "ok")

    def test_signed_result_field_can_itself_carry_a_qualifying_condition(self):
        g = graph(lambda i,f,l,v: v+"，待试运行后签发最终报告" if (i,f)==(4,"acceptance_signer") else v)
        check, = rows(g, "H02")
        row, = check["reinspection"]["register"]["lines"]
        self.assertEqual(row["kind"], "conditional")
        self.assertIn("验收签认", row["quote"])
        self.assertNotEqual(check["status"], "ok")

    def test_native_coverage_replays_and_old_positive_requires_reaudit(self):
        g = graph(omissions=[(4,OPEN)])
        texts = printed(g, {("d04",1):[OPEN]})
        reader = lambda doc, page: texts[doc,page]
        paper = {"graph":g, "policy":{**VERSION,"profile":PERFORMANCE}, "findings":execute(g,PERFORMANCE)}
        reservations.verify(paper, reader)
        verify_findings(paper)
        for part in ("edge", "ledger", "finding", "hash"):
            with self.subTest(part=part):
                bad = copy.deepcopy(paper)
                if part=="edge":
                    next(e for e in bad["graph"]["edges"] if e["type"]=="reinspection_register_line")["line"]+=1
                elif part=="ledger":
                    bad["graph"]["acceptance_reservation_sources"]["final_register"]["lines"].clear()
                elif part=="finding":
                    next(f for f in bad["findings"] if f["rule"]=="H02")["reinspection"]["register"]["lines"][0]["kind"]="clear"
                else:
                    next(n for n in bad["graph"]["nodes"] if n["id"]=="d04/p1")["text_sha256"]="wrong"
                with self.assertRaises(ValueError):
                    (verify_findings(bad) if part=="finding" else reservations.verify(bad,reader))
        old = copy.deepcopy(paper)
        old["policy"].update(version="2026.11.26.06",acceptance_reservations=reservations.OPINIONS)
        old["graph"]["acceptance_reservation_sources"].pop("final_register")
        old["graph"]["acceptance_reservation_sources"]["format"] = reservations.OPINIONS
        old["graph"]["edges"]=[e for e in old["graph"]["edges"] if e["type"]!="reinspection_register_line"]
        old["findings"]=execute(old["graph"],PERFORMANCE)
        self.assertEqual(next(f for f in old["findings"] if f["rule"]=="H02")["status"], "ok")
        reservations.verify(old,reader)
        with self.assertRaisesRegex(ValueError,"重新审计"):
            reservations.verify(old,reader,signing=True)
