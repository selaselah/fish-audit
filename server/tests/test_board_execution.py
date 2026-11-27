import unittest
from copy import deepcopy
from io import BytesIO

from PIL import Image

import board_execution as execution
from config import PERFORMANCE
from controls import execute
from performance import verify_findings
from test_acceptance_execution import printed
from test_acceptance_originals import filed
from test_contract_effect import BOARD_CLAUSE
from test_mandate_originals import word_source
from test_pdf_execution import later_copy, signed_copy
from test_performance import APPROVAL, BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


def procurement(*, clause=BOARD_CLAUSE, decision="批准", approval_contract=None, second=False):
    docs = [CONTRACT, APPROVAL, RECEIPT, WARRANTY, BANK_DOC]
    if second:
        docs.append(APPROVAL)
    def edit(i,k,label,value):
        if k == "effect_clause":
            return clause
        if i == 2 and k == "contract_id" and approval_contract:
            return approval_contract
        return decision if k == "approval_result" else value
    return material(docs, edit)


def board(report):
    return next(f for f in report["findings"] if f["rule"] == "H01")


class BoardDecisionEvidence(unittest.TestCase):
    def test_submitted_pdf_revision_is_independent_of_an_original_positive_decision(self):
        plain = printed(procurement(), "d02")
        signed = signed_copy(plain)
        i = signed.index(b"%", signed.index(b"\n")+1)+1
        mismatch = signed[:i]+bytes([signed[i]^1])+signed[i+1:]
        for state,raw in (("typeset",plain),("current",signed),("earlier",later_copy(signed)),("mismatch",mismatch)):
            with self.subTest(state=state):
                p, text = filed(raw,procurement,"d02",".pdf",render=True)
                signed_finding = board(p)
                d = signed_finding["effect_review"]["board_decision"]
                rec, = p["graph"][execution.PDF]["records"]
                self.assertEqual((d["state"], d["linked"], d["records"]), (state,True,[rec["id"]]))
                self.assertEqual(signed_finding["status"],"risk" if state=="mismatch" else "missing")
                self.assertNotIn("日期和签认已有材料支持",signed_finding["detail"])
                self.assertTrue({"approval_result","effect_clause","approval_authority","approved_on","approval_signer"} <= d["fields"].keys())
                self.assertTrue({rec["id"],*d["fields"].values(),*rec["fields"]} <= set(signed_finding["evidence"]))
                for f in p["findings"]:
                    if f["rule"] in ("H02","H03"):
                        self.assertEqual(f["status"],"ok")
                    if f["rule"] in ("H04","H05"):
                        self.assertNotEqual(f["status"],"ok")
                        self.assertIn(rec["id"],f["evidence"])
                execution.verify(p,lambda _:raw,text,signing=True)
                verify_findings(p)

    def test_comment_remains_a_review_note_and_is_bound_to_the_decision_line(self):
        raw = word_source(rows=APPROVAL, anchor_field="approval_result", comment=True, note="仅同意谈判，签约另行表决")
        p, text = filed(raw,procurement,"d02",".docx",render=True)
        g=p["graph"]; d=board(p)["effect_review"]["board_decision"]
        word, = g[execution.NATIVE]["documents"]; note, = word["notes"]
        self.assertEqual(d["state"],"word_review")
        self.assertEqual(note["text"],"仅同意谈判，签约另行表决")
        self.assertIn(d["fields"]["approval_result"],note["location"]["facts"])
        self.assertTrue({note["id"],word["id"],*note["location"]["facts"]} <= set(d["evidence"]))
        self.assertEqual(board(p)["status"], "missing")
        execution.verify(p,lambda _:raw,text,signing=True)
        changed=deepcopy(p)
        changed["graph"][execution.NATIVE]["documents"][0]["notes"][0]["text"]="批准签约"
        with self.assertRaises(ValueError):
            execution.verify(changed,lambda _:raw,text)
        board(p)["effect_review"]["board_decision"]["fields"]["approval_result"]=d["fields"]["approval_signer"]
        with self.assertRaises(ValueError):
            verify_findings(p)

    def test_denial_wrong_contract_competing_approval_and_image_keep_distinct_dispositions(self):
        for change, state, expected, linked in (({"decision":"退回补议"},"typeset","risk",True),
                ({"approval_contract":"YL-OTHER"},"typeset","missing",False), ({"second":True},"multiple","missing",False)):
            with self.subTest(change=change):
                factory=lambda: procurement(**change)
                raw=printed(factory(),"d02")
                p,_=filed(raw,factory,"d02",".pdf",render=True)
                f=board(p);d=f["effect_review"]["board_decision"]
                self.assertEqual((d["state"],f["status"],d["linked"]),(state,expected,linked))
                if expected=="risk":
                    self.assertIn("退回补议",f["detail"])
        out=BytesIO();Image.new("RGB",(1000,1200),"white").save(out,format="PNG")
        p,t=filed(out.getvalue(),procurement,"d02",".png",render=True)
        d=board(p)["effect_review"]["board_decision"]
        self.assertEqual((d["state"],d["linked"]),("photo",False))
        self.assertNotIn("approval_result",d["fields"])
        execution.verify(p,lambda _:out.getvalue(),t,signing=True)

    def test_previous_approval_needs_review_but_archived_checks_and_unrelated_contracts_remain_readable(self):
        for decision in ("批准","退回补议"):
            g=procurement(decision=decision)
            g.pop(execution.PDF);g.pop(execution.NATIVE)
            p={"graph":g,"policy":{"version":"2026.11.27.14"},"findings":execute(g,PERFORMANCE)}
            execution.verify(p,None,None)
            if decision=="批准":
                self.assertEqual(board(p)["status"],"ok")
                with self.assertRaisesRegex(ValueError,"重审"):
                    execution.verify(p,None,None,signing=True)
            else:
                execution.verify(p,None,None,signing=True)
        f=lambda:procurement(clause="本合同自双方盖章之日起生效")
        p,_=filed(printed(f(),"d02"),f,"d02",".pdf",render=True)
        self.assertNotIn("board_decision",board(p).get("effect_review",{}))
