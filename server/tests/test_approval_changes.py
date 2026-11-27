import unittest
from copy import deepcopy
from unittest.mock import patch

import approval_changes as change
import inspection_use as use
from config import PERFORMANCE
from controls import execute
from graph import build_graph
from performance import verify_findings
from test_approval_names import SINGLE
from test_installment_approval import paper,sheet
from test_retest_reference import payments


def sample(day="27",signer="顾明远",revisions=None,extra=(),signature="typeset",sheet_fields=None):
    fields={"补充协议编号":"BC-122","原合同编号":"YL-121","采购方":"演练甲","供应方":"演练乙","采购标的":"冷藏柜",
            "变更范围":"仅变更第二期验收款签批人，其余条款不变","原签批约定":"第二期验收款须由林知行签批。",
            "变更后签批约定":"第二期验收款须由顾明远签批。","变更适用时点":change.TIMING,"协议生效条款":"本协议自双方盖章之日起生效",
            "甲方签章":"演练甲（已盖章）","乙方签章":"演练乙（已盖章）","甲方盖章日期":"2026年9月23日","乙方盖章日期":f"2026年9月{day}日"}
    fields.update(revisions or {})
    agreement=[("contract_addendum","","采购合同补充协议"),*(("other",k,v) for k,v in fields.items()),*extra]
    def build(docs,pages,*args):
        docs[0].update(ext=".pdf",pages=1)
        g=build_graph(docs,pages,*args)
        g["addendum_pdf_sources"]["records"]=[{"doc":"d08","unit":"d08","id":"addendum-pdf/d08","state":signature,
                                               "pages":[{"ref":"d08/p1"}],"fields":[]}]
        return g
    with patch("test_installment_approval.build_graph",build):
        s={"审批日期":"2026-09-27","签批人姓名":signer,"审批签发时间":"09:15（北京时间）",**(sheet_fields or {})}
        return paper(sheet(**s),agreement,extra=[(1,SINGLE),(6,"实际扣款时间：10:30（北京时间）")])


class ApprovalChangeTests(unittest.TestCase):
    def test_prospective_change_uses_approval_day_and_keeps_authenticity_open(self):
        for day,signer,state,status,difference in (("26","顾明远","after","missing",False),("28","顾明远","before","risk",True),
                ("27","顾明远","same_day","missing",False),("26","林知行","after","risk",True),("28","林知行","before","missing",False),
                ("26","指定人","after","missing",False)):
            with self.subTest(day=day,signer=signer):
                p,read,layout=sample(day,signer);f,=payments(p);c=f["approval_change"]
                self.assertEqual((c["state"],c["status"],c["printed_difference"],c["days_from_seals"]),(state,status,difference,27-int(day)))
                self.assertEqual(c["signature_state"],"typeset")
                self.assertEqual(c["listed"],[] if signer=="指定人" else [signer])
                stages=[f for f in p["findings"] if f.get("approval_change")]
                self.assertEqual([(s["rule"],s["stage"]["name"]) for s in stages],[("H04","第二期"),("H05","第二期")])
                self.assertEqual(stages[0]["approval_change"]["state"],"terms")
                self.assertEqual(len(change.edges(stages)),1)
                use.verify(p,read,read_layout=layout);verify_findings(p)
        for sheet_fields,flag in (({"审批决定":"不同意支付"},"refused"),({"审批签发时间":"11:00（北京时间）"},"early_debit")):
            p,_,_=sample("26",sheet_fields=sheet_fields)
            c=payments(p)[0]["approval_change"];self.assertTrue(c[flag]);self.assertEqual(c["status"],"risk")
        p,_,_=sample("26",revisions={"变更后签批约定":"第二期验收款须由顾明远与周茵共同签批。"})
        c=payments(p)[0]["approval_change"];self.assertEqual((c["status"],c["missing_names"]),("missing",["周茵"]))

    def test_other_versions_riders_and_wrong_parties_never_select_an_applicable_list(self):
        for kwargs in ({"revisions":{"原合同编号":"YL-0121"}},{"revisions":{"供应方":"演练丙"}},{"revisions":{"甲方签章":"待签"}},
                {"revisions":{"变更适用时点":"适用于所有未付款项"}},{"revisions":{"原签批约定":"第二期验收款须由周茵签批。"}},
                {"extra":[("other","特别约定","须另经董事会批准")]},{"signature":"earlier"},{"signature":"mismatch"}):
            with self.subTest(kwargs=kwargs):
                p,read,layout=sample("28",**kwargs);c=payments(p)[0]["approval_change"]
                self.assertEqual(c["state"],"pending");self.assertNotIn("issued_on",c)
                use.verify(p,read,read_layout=layout)
        for vals in ({"审批期次":"第三期质保金"},{"所据验收单号":"FY-99"},{"审批签发时间":"09:15"},{"付款户名":"演练丙"}):
            p,_,_=sample("28",sheet_fields=vals);c=payments(p)[0]["approval_change"]
            self.assertEqual(c["state"],"terms");self.assertNotIn("listed",c)

    def test_altered_original_name_date_or_relationship_cannot_reproduce_the_result(self):
        p,read,layout=sample("28")
        for key in ("source","rect","issued_on","before","state","fields","edge","omitted"):
            with self.subTest(key=key),self.assertRaises(ValueError):
                bad=deepcopy(p);f,=payments(bad);c=f["approval_change"];g=bad["graph"]
                row=g[use.KEY]["approver_changes"][0]["rows"][-1]
                if key=="source":row["quote"]="乙方盖章日期：2026年9月25日"
                elif key=="rect":row["rects"]=[]
                elif key=="issued_on":c[key]="2026-09-25"
                elif key=="before":c[key]=c["after"]
                elif key=="state":c[key]="same_day"
                elif key=="fields":c[key]["revised"]=c[key]["previous"]
                elif key=="edge":g["edges"]=[e for e in g["edges"] if e["type"]!="dates_approval_change"]
                else:del f["approval_change"]
                use.verify(bad,read,read_layout=layout)

    def test_historical_report_still_replays_and_new_temporal_risk_requires_review(self):
        p,read,layout=sample("28");g=p["graph"]
        nodes,links=use.source_graph(g[use.KEY])
        g["nodes"]=[n for n in g["nodes"] if n not in nodes]
        g["edges"]=[e for e in g["edges"] if e not in links+use.edges(p["findings"])]
        g[use.KEY]=use.sources(g,read,layout,use.UNNAMED_FORMAT)
        nodes,links=use.source_graph(g[use.KEY]);g["nodes"].extend(nodes);g["edges"].extend(links)
        p["policy"].update(version="2026.11.28.2",inspection_use=use.UNNAMED_FORMAT)
        p["findings"]=execute(g,PERFORMANCE);g["edges"].extend(use.edges(p["findings"]))
        use.verify(p,read,read_layout=layout)
        with self.assertRaisesRegex(ValueError,"重审"):use.verify(p,read,read_layout=layout,signing=True)
