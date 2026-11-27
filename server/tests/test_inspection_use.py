from copy import deepcopy
import unittest

from config import PERFORMANCE
from controls import execute
import inspection_use as use
from performance import verify_findings
from test_payment_acceptance import specimen, transfers
from test_retest_reference import payments, sample

BAN = "用途说明：本复验单不得作为第二期验收款的付款依据。"
APPROVAL = "审批说明：本复验单仅确认质量，第二期验收款须另经财务负责人审批。"
CONDITION = "用途说明：未经财务负责人签字，本复验单不得作为第二期验收款的付款依据。"


def packet(omissions, **kwargs):
    p, read = sample(omissions=omissions, **kwargs)
    p["graph"]["edges"].extend(use.edges(p["findings"]))
    def layout(doc, number):
        return {"lines": {str(i): [[0,.1,.9,.2]] for i,_ in enumerate(read(doc, number).splitlines(), 1)}}
    return p, read, layout


class InspectionUseTests(unittest.TestCase):
    def test_scope_and_conditions_are_independent_of_acceptable_quality(self):
        for unit, text, state, status, scope in [
            (4,BAN,"ban","risk","cited"), (4,APPROVAL,"approval","missing","cited"),
            (4,CONDITION,"conditional","missing","cited"),
            (2,BAN.replace("复验单","验收单"),"other_document","ok","other_document"),
            (4,BAN.replace("第二期验收款","第三期质保金"),"other_stage","ok","other_stage"),
        ]:
            with self.subTest(state=state):
                p, read, layout = packet([(unit,text)])
                f, = payments(p)
                c, g = f["inspection_use"], p["graph"]
                self.assertEqual((c["state"],c["status"]),(state,status))
                self.assertEqual(f["status"], "missing" if state=="other_stage" else status)
                self.assertEqual((f["retest_reference"]["state"],f["retest_reference"]["status"]),("final","ok"))
                row, = g[use.KEY]["rows"]
                self.assertEqual((row["quote"],row["facts"],read(row["doc"],1).splitlines()[row["line"]-1]),(text,[],text))
                self.assertEqual(c["notes"],[{"row":row["id"],"scope":scope}])
                self.assertEqual(bool(use.edges(p["findings"])),scope=="cited")
                self.assertIn(row["id"], f["evidence"])
                self.assertTrue(all("inspection_use" not in x for x in p["findings"] if x["rule"]!="H05"))
                verify_findings(p)
                use.verify(p,read,read_layout=layout)

    def test_each_receipt_is_bound_to_its_own_inspection(self):
        p,read,layout = packet([(2,BAN.replace("复验单","验收单"))],codes=("YS-01","FY-02"),dates=("2026-09-27","2026-09-28"))
        initial, final = payments(p)
        self.assertEqual([f["inspection_use"]["state"] for f in (initial,final)],["ban","other_document"])
        self.assertEqual([f["status"] for f in (initial,final)],["risk","ok"])
        self.assertEqual([r["from"] for r in use.edges(p["findings"])],[initial["retest_reference"]["fields"]["citation"]])
        use.verify(p,read,read_layout=layout)

    def test_no_inference_from_unmatched_pending_or_ambiguous_sources(self):
        for kwargs in ({"codes":("FY-999",)}, {"codes":(None,)}, {"changes":{(6,"transfer_status"):"受理中"}}):
            p,_,_ = packet([(4,BAN)],**kwargs)
            self.assertNotIn("inspection_use",payments(p)[0])
        for texts in ([BAN,"例外说明：本限制经补签可解除。"],[BAN,APPROVAL],
                      ["用途说明：另见补充约定，审批条件另定。"],[BAN+"例外见背面。"]):
            p,_,_=packet([(4,t) for t in texts])
            self.assertEqual(payments(p)[0]["inspection_use"]["state"],"unclear")
        p,_,_=packet([(2,"审批说明：第二期验收款须另经财务负责人审批。")])
        self.assertEqual(payments(p)[0]["inspection_use"]["state"],"unclear")
        p,_,_=packet([(4,"付款意见：同意支付。")])
        self.assertNotIn("inspection_use",payments(p)[0])
        graph,_=specimen(("YS-20",),omissions=[(3,BAN)])
        f,=transfers(graph)
        self.assertEqual(f["payment_acceptance"]["state"],"records")
        self.assertNotIn("inspection_use",f)

    def test_word_review_or_dispute_keeps_the_claim_open(self):
        p,_,_ = packet([(4,BAN)])
        g = p["graph"]
        g["acceptance_word_reviews"]["documents"]=[{"id":"review/d04","units":["d04"],"coverage":"incomplete","notes":[]}]
        _,check=next(use.checks(g,p["findings"]))
        self.assertEqual(check["state"],"unclear")
        self.assertIn("review/d04",check["evidence"])
        g["acceptance_word_reviews"]["documents"].clear()
        g[use.KEY]["rows"][0]["disputed"]=True
        _,check=next(use.checks(g,p["findings"]))
        self.assertEqual(check["state"],"unclear")

    def test_forged_links_and_legacy_release_are_rejected(self):
        p,read,layout=packet([(4,BAN)])
        for mutation in ("coordinates","quote","edge","scope","state","marker","page","version"):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                t=deepcopy(p);g=t["graph"];c=payments(t)[0]["inspection_use"];row=g[use.KEY]["rows"][0]
                if mutation=="coordinates":row["rects"]=[[0,.5,.9,.6]]
                if mutation=="quote":row["quote"]=APPROVAL
                if mutation=="edge":g["edges"][-1]["from"]=c["number_ref"]
                if mutation=="scope":c["notes"][0]["scope"]="other_document"
                if mutation=="state":c["state"]="approval"
                if mutation=="marker":del t["policy"]["inspection_use"]
                if mutation=="page":row["page_sha256"]="another"
                if mutation=="version":t["policy"]["version"]="2026.11.27.18"
                use.verify(t,read,read_layout=layout)
        g=p["graph"];del g[use.KEY]
        g["nodes"]=[n for n in g["nodes"] if n["type"]!="inspection_use_line"]
        g["edges"]=[e for e in g["edges"] if e["type"] not in ("inspection_use_source","cites_inspection_use")]
        p["findings"]=execute(g,PERFORMANCE)
        p["policy"]["version"]="2026.11.27.18";del p["policy"]["inspection_use"]
        self.assertEqual(payments(p)[0]["retest_reference"]["status"],"ok")
        use.verify(p,read)
        with self.assertRaisesRegex(ValueError,"重审"):
            use.verify(p,read,read_layout=layout,signing=True)
