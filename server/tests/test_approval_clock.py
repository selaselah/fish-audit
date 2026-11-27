from copy import deepcopy
import unittest

from config import PERFORMANCE
from controls import execute
import inspection_use as use
from performance import verify_findings
from test_installment_approval import paper, payments, sheet


def specimen(signed="10:30（北京时间）", bank=("实际扣款时间：09:15（北京时间）",), **changes):
    extras=[(6,raw) for raw in bank]
    if signed is not None:
        extras.append((7,"审批签发时间："+signed))
    return paper(sheet(**({"审批日期":"2026-09-27"} | changes)),extra=extras)


class ApprovalTimeTests(unittest.TestCase):
    def test_only_the_signed_decision_and_successful_debit_on_this_installment_establish_order(self):
        for signed,bank,state in (
            ("10:30（北京时间）",["实际扣款时间：09:15（北京时间）"],"debit_first"),
            ("10:30:42 UTC+08:00",["实际扣款时间：10:31 +08:00"],"approval_first"),
            ("10:30（北京时间）",["实际扣款时间：10:30:42（北京时间）"],"overlap"),
            ("10:30:41（北京时间）",["实际扣款时间：10:30:42（北京时间）"],"approval_first"),
            ("10:30（北京时间）",["银行受理时间：09:15（北京时间）"],"other_event"),
            ("10:30（北京时间）",["回单打印时间：08:00（北京时间）","实际扣款时间：10:31（北京时间）"],"approval_first"),
            ("10:30",["实际扣款时间：09:15（北京时间）"],"zone"),
            ("2026-09-26 10:30（北京时间）",["实际扣款时间：09:15（北京时间）"],"conflict"),
            ("10:30（北京时间）",["实际扣款时间：2026-09-28 09:15（北京时间）"],"conflict"),
            ("10:30（北京时间）",["实际扣款时间：09:15（北京时间）","实际扣款时间：09:18（北京时间）"],"conflict"),
            ("1 0:30（北京时间）",["实际扣款时间：09:15（北京时间）"],"missing"),
            ("②③:00（北京时间）",["实际扣款时间：09:15（北京时间）"],"missing"),
            (None,["实际扣款时间：09:15（北京时间）"],"missing"),
            ("10:30（北京时间）",[],"missing"),
        ):
            with self.subTest(state=state,signed=signed,bank=bank):
                p,read,layout=specimen(signed,bank);f,=payments(p);a=f["inspection_use"]["approval"];clock=a["clock"]
                self.assertEqual((a["state"],clock["state"],f["status"]),("same_day",state,"risk" if state=="debit_first" else "missing"))
                self.assertTrue(set(clock["rows"])<=set(a["evidence"])<=set(f["evidence"]))
                links=[e for e in p["graph"]["edges"] if e["type"]=="compares_debit_time"]
                self.assertEqual(len(links),int(state in {"approval_first","debit_first","overlap"}))
                self.assertEqual("signed_at" in clock,bool(links))
                if links:
                    self.assertEqual((links[0]["from"],links[0]["to"],clock["zone"]),(a["fields"]["signed_at"],clock["debit"],"+08:00"))
                use.verify(p,read,read_layout=layout);verify_findings(p)
        for changes in ({"审批期次":"第三期质保金"},{"所据验收单号":"YS-01"},{"审批决定":"不同意支付"},{"审批岗位":"总经理"}):
            p,_,_=specimen(**changes)
            self.assertNotIn("clock",payments(p)[0]["inspection_use"]["approval"])
        for extra in ("备注：所列时间为预计时间","实际扣款时间：09:15（北京时间），另见验收单 FY-03"):
            p,_,_=specimen(bank=["实际扣款时间：09:15（北京时间）",extra])
            self.assertEqual(payments(p)[0]["retest_reference"]["state"],"unresolved")

    def test_superseded_method_keeps_its_original_judgment_and_blocks_signing_new_adverse_evidence(self):
        for at,blocks in (("09:15",True),("11:30",False)):
            p,read,layout=specimen(bank=["实际扣款时间："+at+"（北京时间）"])
            g=p["graph"]
            original=g[use.KEY]
            nodes,edges=use.source_graph(original)
            g["nodes"]=[n for n in g["nodes"] if n not in nodes]
            g["edges"]=[e for e in g["edges"] if e not in edges+use.edges(p["findings"])]
            g[use.KEY]=use.sources(g,read,layout,use.APPROVAL_FORMAT)
            nodes,edges=use.source_graph(g[use.KEY]);g["nodes"].extend(nodes);g["edges"].extend(edges)
            p["policy"].update(version="2026.11.27.23",inspection_use=use.APPROVAL_FORMAT)
            p["findings"]=execute(g,PERFORMANCE);g["edges"].extend(use.edges(p["findings"]))
            use.verify(p,read,read_layout=layout)
            if blocks:
                with self.assertRaisesRegex(ValueError,"重审"):use.verify(p,read,read_layout=layout,signing=True)
            else:
                use.verify(p,read,read_layout=layout,signing=True)

    def test_tampering_with_either_event_or_its_physical_location_fails_verification(self):
        p,read,layout=specimen()
        for key in ("clock","signed","debit","quote","rects","source","comparison","evidence","version"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                altered=deepcopy(p);g=altered["graph"];f,=payments(altered);clock=f["inspection_use"]["approval"]["clock"]
                bank,=g[use.KEY]["bank_clocks"];r,=bank["rows"]
                if key=="clock":clock["state"]="approval_first"
                if key=="signed":clock["signed"]=r["id"]
                if key=="debit":clock["debit"]=clock["signed"]
                if key=="quote":r["quote"]="银行受理时间：09:15（北京时间）"
                if key=="rects":r["rects"]=[]
                if key=="source":g["edges"]=[e for e in g["edges"] if e["type"]!="payment_clock_source"]
                if key=="comparison":g["edges"]=[e for e in g["edges"] if e["type"]!="compares_debit_time"]
                if key=="evidence":f["evidence"].remove(r["id"])
                if key=="version":altered["policy"]["version"]="2026.11.27.23"
                use.verify(altered,read,read_layout=layout)
