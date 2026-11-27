import unittest
from copy import deepcopy
from unittest.mock import patch

import approval_names as names
import inspection_use as use
from config import PERFORMANCE
from controls import execute
from graph import build_graph
from performance import verify_findings
from test_installment_approval import paper, sheet
from test_retest_reference import payments


SINGLE="付款签批约定：第二期验收款须由林知行签批。"
JOINT="付款签批约定：第二期验收款须由林知行与顾明远共同签批。"


def sample(term=SINGLE, signer="林知行", extra=(), contract_ext=".pdf", **fields):
    def build(docs,pages,*args):
        docs[0].update(ext=contract_ext,pages=1)
        return build_graph(docs,pages,*args)
    with patch("test_installment_approval.build_graph",build):
        data={"审批日期":"2026-09-27","审批签发时间":"09:15（北京时间）"}
        if signer is not None:
            data["签批人姓名"]=signer
        return paper(sheet(**(data | fields)),extra=[(1,term),(6,"实际扣款时间：10:30（北京时间）"),*extra])


class ApprovalNamesTests(unittest.TestCase):
    def test_scope_and_lists(self):
        for term,person,state in ((SINGLE,"林知行","listed"),(SINGLE,"顾明远","different"),(JOINT,"林知行","partial"),
                (JOINT,"顾明远、林知行","listed"),(JOINT,None,"missing"),(SINGLE,"顾明远、林知行","scope"),
                (JOINT,"周茵","different"),(SINGLE.replace("第二期验收款","第三期质保金"),"顾明远","other_stage")):
            with self.subTest(term=term,person=person):
                p,read,layout=sample(term,person);f,=payments(p);a=f["inspection_use"]["approval"];c=a["names"]
                self.assertEqual((a["clock"]["state"],c["state"],f["status"]),("approval_first",state,"risk" if state=="different" else "missing"))
                self.assertTrue(set(c["rows"])<=set(a["evidence"])<=set(f["evidence"]))
                if "contract_fields" in c:self.assertTrue(set(c["contract_fields"].values())<=set(f["evidence"]))
                self.assertEqual(len([e for e in p["graph"]["edges"] if e["type"]=="compares_approval_names"]),int(state in {"listed","partial","different"}))
                use.verify(p,read,read_layout=layout);verify_findings(p)

    def test_riders_other_documents_and_incomplete_names_require_review(self):
        for args in ({"extra":[(1,"特别约定：经书面授权可由其他人代签。")]},{"extra":[(1,SINGLE)]}):
            p,_,_=sample(signer="顾明远",**args);f,=payments(p)
            self.assertEqual(f["inspection_use"]["approval"]["names"]["state"],"scope")
        p,_,_=sample(signer="顾明远",contract_ext=".docx")
        self.assertFalse(any(f.get("inspection_use",{}).get("approval",{}).get("names",{}).get("state")=="different" for f in payments(p)))
        for unclear in ("财务负责人","林知行或顾明远","任何人","未填写"):
            p,_,_=sample(SINGLE.replace("林知行",unclear),"顾明远")
            self.assertFalse(any(f.get("stage_approvers") for f in p["findings"]))
        for who in ("林某","财务部","待签","林知行、林知行","林知行代签","顾明远等","林知行／顾明远","林知行或顾明远"):
            with self.subTest(who=who):
                self.assertIsNone(names.listed(who))
        for fields in ({"审批期次":"第三期质保金"},{"所据验收单号":"YS-01"},{"付款户名":"其他单位"}):
            p,_,_=sample(**fields)
            self.assertFalse(any(f.get("inspection_use",{}).get("approval",{}).get("names") for f in payments(p)))
        p,_,_=sample(signer="顾明远",审批决定="不同意支付")
        self.assertEqual(payments(p)[0]["inspection_use"]["approval"]["state"],"refused")
        p,_,_=sample(signer="林知行",审批签发时间="11:00（北京时间）")
        f,=payments(p)
        self.assertEqual((f["status"],f["inspection_use"]["approval"]["names"]["state"]),("risk","listed"))

    def test_contract_condition_remains_on_its_installment_before_a_payment_approval_is_filed(self):
        from test_inspection_use import packet
        def build(docs,pages,*args):
            docs[0].update(ext=".pdf",pages=1)
            return build_graph(docs,pages,*args)
        with patch("test_retest_reference.build_graph",build):
            p,read,layout=packet([(1,JOINT)])
        g=p["graph"];row,=g[use.KEY]["approver_terms"][0]["rows"]
        self.assertNotIn("approvals",g[use.KEY])
        plan=next(f for f in p["findings"] if f["rule"]=="H03")
        self.assertEqual(plan["status"],"ok")
        self.assertIn(row["id"],plan["evidence"])
        for f in p["findings"]:
            if f["rule"] in ("H04","H05") and f["stage"]["name"]=="第二期":
                self.assertEqual(f["stage_approvers"],[row["id"]])
                self.assertNotEqual(f["status"],"ok")
            else:
                self.assertNotIn("stage_approvers",f)
        self.assertFalse(g["acceptance_authority_sources"]["clauses"])
        use.verify(p,read,read_layout=layout);verify_findings(p)

    def test_extra_delegation_document_keeps_the_printed_difference_pending(self):
        p,_,_=sample(signer="顾明远");g=p["graph"]
        g["documents"].append({"id":"d08","name":"另一份授权","sha256":"sample"})
        f,=payments(p);c=f["inspection_use"];raw,=g[use.KEY]["approver_terms"][0]["rows"]
        import installment_approval
        check=installment_approval.compare(g,f,c,g[use.KEY]["rows"][0],g[use.KEY]["approvals"])
        self.assertEqual((check["status"],check["names"]["state"]),("missing","scope"))
        self.assertIn(raw["id"],check["evidence"])

    def test_unnamed_signer_does_not_override_the_decision_or_debit(self):
        for signer,extra,state,clock,status in (
                ("指定人",{},"same_day","approval_first","missing"),("财务负责人",{},"same_day","approval_first","missing"),
                ("待签",{"审批决定":"不同意支付"},"refused",None,"risk"),("",{"审批签发时间":"11:00（北京时间）"},"same_day","debit_first","risk")):
            with self.subTest(signer=signer):
                p,read,layout=sample(signer=signer,**extra)
                f,=payments(p);a=f["inspection_use"]["approval"];n=a["names"]
                self.assertEqual((a["state"],a.get("clock",{}).get("state"),f["status"]),(state,clock,status))
                self.assertEqual((n["state"],n["listed"],n["signed_by"]),("missing",[],a["fields"]["signed_by"]))
                self.assertFalse(any(e["type"]=="compares_approval_names" for e in p["graph"]["edges"]))
                use.verify(p,read,read_layout=layout);verify_findings(p)
        for marker in ("指定人","董事会","不确定","详附件"):
            self.assertIsNone(names.clause(SINGLE.replace("林知行",marker)))
        for text in ("代签，限第三期","见授权书","详附件","林知行、待签"):
            p,_,_=sample(signer=text)
            self.assertFalse(any(f.get("inspection_use",{}).get("approval",{}).get("fields") for f in payments(p)))

    def test_historical_person_placeholder_replays_and_requires_new_review(self):
        p,read,layout=sample(signer="指定人");g=p["graph"];old=g[use.KEY]
        old_links=use.edges(p["findings"])
        g[use.KEY]={**old,"format":use.NAMES_FORMAT}
        p["policy"].update(version="2026.11.28.1",inspection_use=use.NAMES_FORMAT)
        p["findings"]=execute(g,PERFORMANCE)
        g["edges"]=[e for e in g["edges"] if e not in old_links]+use.edges(p["findings"])
        f,=payments(p)
        self.assertEqual((f["status"],f["inspection_use"]["approval"]["names"]["listed"]),("risk",["指定人"]))
        use.verify(p,read,read_layout=layout)
        with self.assertRaisesRegex(ValueError,"占位"):use.verify(p,read,read_layout=layout,signing=True)

    def test_binds_two_originals_and_rechecks_old_adverse_grounds(self):
        p,read,layout=sample(signer="顾明远")
        for what in ("quote","signer","required","listed","status","link","contract","rects","scope"):
            with self.subTest(what=what), self.assertRaises(ValueError):
                bad=deepcopy(p);g=bad["graph"];f,=payments(bad);a=f["inspection_use"]["approval"];c=a["names"]
                row,=g[use.KEY]["approver_terms"][0]["rows"]
                if what=="quote":row["quote"]=JOINT
                if what=="signer":c["signed_by"]=a["fields"]["authority"]
                if what=="required":c["required"]=["顾明远"]
                if what=="listed":c["listed"]=["林知行"]
                if what=="status":a["status"]="missing"
                if what=="link":g["edges"]=[e for e in g["edges"] if e["type"]!="compares_approval_names"]
                if what=="contract":c["contract_fields"]["seller"]=c["contract_fields"]["buyer"]
                if what=="rects":row["rects"]=[]
                if what=="scope":c["state"]="listed"
                use.verify(bad,read,read_layout=layout)
        g=p["graph"];old=g[use.KEY];nodes,edges=use.source_graph(old)
        g["nodes"]=[n for n in g["nodes"] if n not in nodes]
        g["edges"]=[e for e in g["edges"] if e not in edges+use.edges(p["findings"])]
        g[use.KEY]=use.sources(g,read,layout,use.CLOCK_FORMAT);nodes,edges=use.source_graph(g[use.KEY])
        g["nodes"].extend(nodes);g["edges"].extend(edges)
        p["policy"].update(version="2026.11.27.24",inspection_use=use.CLOCK_FORMAT)
        p["findings"]=execute(g,PERFORMANCE);g["edges"].extend(use.edges(p["findings"]))
        use.verify(p,read,read_layout=layout)
        with self.assertRaisesRegex(ValueError,"重审"):use.verify(p,read,read_layout=layout,signing=True)
