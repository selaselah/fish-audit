import unittest
from copy import deepcopy
from unittest.mock import patch

from graph import build_graph
from performance import verify_findings
from retest_reference import FIELD
from test_inspection_use import APPROVAL, packet
from test_retest_reference import BANK_DOC, CONTRACT, FINAL, FIX, OLD, WARRANTY, payments
import inspection_use as use
import installment_approval as approval


def sheet(**changes):
    values = {"合同编号":"YL-121", "付款户名":"演练甲", "收款户名":"演练乙", "审批期次":"第二期验收款",
              "所据验收单号":"FY-02", "审批岗位":"财务负责人", "审批决定":"同意支付", "审批日期":"2026年9月28日"}
    return [("other","","付款审批单"), *(("other",k,v) for k,v in (values | changes).items())]


def paper(*sheets, extra=(), banks=1, ext=".pdf"):
    bank = [*BANK_DOC, (FIELD,"付款依据验收单号","FY-02")]
    groups = [CONTRACT,OLD,FIX,FINAL,WARRANTY,*([bank]*banks),*sheets]
    def build(docs,pages,*args):
        for doc in docs[5+banks:]:
            doc.update(ext=ext,pages=1)
        return build_graph(docs,pages,*args)
    with patch("test_retest_reference.build_graph",build):
        return packet([(4,APPROVAL),*extra],groups=groups,dates=("2026-09-27",)*banks)


class InstallmentApprovalTests(unittest.TestCase):
    def test_compare_only_the_bank_installment_and_the_required_inspection(self):
        for fields,state in (({},"later"), ({"审批日期":"2026-09-26"},"earlier"), ({"审批日期":"2026-09-27"},"same_day"),
                             ({"审批决定":"不同意支付"},"refused"), ({"审批期次":"第三期质保金"},"other_stage"),
                             ({"所据验收单号":"YS-01"},"other_receipt"), ({"审批岗位":"总经理"},"other_authority")):
            with self.subTest(state=state):
                p,read,layout=paper(sheet(**fields))
                f,=payments(p)
                c=f["inspection_use"]["approval"]
                self.assertEqual((c["state"],c["required"],c["paid_on"]),(state,"财务负责人","2026-09-27"))
                self.assertEqual(f["status"],"risk" if state in {"refused","later"} else "missing")
                self.assertTrue(set(c["rows"])<=set(c["evidence"])<=set(f["evidence"]))
                self.assertEqual(set(c["fields"]),approval.FIELDS)
                self.assertTrue(set(c["bank_fields"].values())<=set(c["evidence"]))
                self.assertEqual(len([e for e in p["graph"]["edges"] if e["type"]=="compares_payment_approval"]),9)
                for row in p["graph"][use.KEY]["approvals"][0]["rows"]:
                    self.assertEqual(row["quote"],read(row["doc"],row["page"]).splitlines()[row["line"]-1])
                self.assertEqual(approval.recognized(p["graph"]),{"d07"})
                use.verify(p,read,read_layout=layout)
                verify_findings(p)

    def test_ambiguous_or_incomplete_sources(self):
        p,_,_=paper(sheet(),sheet())
        f,=payments(p)
        self.assertEqual(f["inspection_use"]["approval"]["state"],"multiple")
        p,_,_=paper(sheet(),banks=2)
        self.assertEqual([f["inspection_use"]["approval"]["state"] for f in payments(p)],["bank_scope","bank_scope"])
        for args in ({"extra":[(7,"备注：原审批已撤销。")]},{"extra":[(7,"审批期次：第三期质保金")]},{"ext":".jpg"}):
            p,_,_=paper(sheet(),**args)
            self.assertFalse(approval.recognized(p["graph"]))
            self.assertFalse(any(f.get("inspection_use",{}).get("approval",{}).get("state")=="later" for f in payments(p)))
        p,_,_=paper(sheet(收款户名="另一单位"))
        self.assertFalse(approval.recognized(p["graph"]))
        p,_,_=paper(sheet(审批日期="2026-02-30"))
        self.assertFalse(approval.recognized(p["graph"]))

    def test_issued_graph_rejects_an_altered_date_decision_raw_row_or_edge(self):
        original, read, layout=paper(sheet())
        for mode in ("date","decision","raw","geometry","link","scope"):
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                p=deepcopy(original)
                g=p["graph"]
                c=payments(p)[0]["inspection_use"]["approval"]
                if mode=="date":c["paid_on"]="2026-09-29"
                if mode=="decision":c["state"]="earlier"
                if mode=="raw":g[use.KEY]["approvals"][0]["rows"][-1]["quote"]="审批日期：2026-09-24"
                if mode=="geometry":g[use.KEY]["approvals"][0]["rows"][-1]["rects"]=[]
                if mode=="link":g["edges"]=[e for e in g["edges"] if e["type"]!="compares_payment_approval"]
                if mode=="scope":c["fields"]["stage"]=c["fields"]["date"]
                use.verify(p,read,read_layout=layout)

    def test_old_unassigned_approval_remains_readable_but_new_risk_blocks_signing(self):
        from config import PERFORMANCE
        from controls import execute
        for date,blocks in (("2026-09-28",True),("2026-09-26",False)):
            p,read,layout=paper(sheet(审批日期=date))
            g=p["graph"]
            g[use.KEY]=use.sources(g,read,layout,use.CROSS_FORMAT)
            p["policy"].update(version="2026.11.27.20",inspection_use=use.CROSS_FORMAT)
            g["nodes"]=[n for n in g["nodes"] if n["type"] not in ("inspection_use_line","payment_approval_line")]
            g["edges"]=[e for e in g["edges"] if e["type"] not in ("inspection_use_source","payment_approval_source","compares_payment_approval","cites_inspection_use")]
            nodes,edges=use.source_graph(g[use.KEY])
            g["nodes"].extend(nodes)
            g["edges"].extend(edges)
            p["findings"]=execute(g,PERFORMANCE)
            g["edges"].extend(use.edges(p["findings"]))
            self.assertFalse(any("inspection_use" in f for f in payments(p)))
            use.verify(p,read,read_layout=layout)
            if blocks:
                with self.assertRaisesRegex(ValueError,"重审"):
                    use.verify(p,read,read_layout=layout,signing=True)
            else:
                use.verify(p,read,read_layout=layout,signing=True)
