import copy
import unittest

from calculations import CalculationEvidence
from config import PERFORMANCE, PROFILE
from controls import VERSION, conclusion, execute
from model import expert_candidates
from performance import BOARD_FORMAT, compute, verify_findings
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material, rows


PROBLEM = "温控探头失准"
OLD = [(f,l,{"acceptance_result":"不合格","acceptance_exception":PROBLEM,"measured_result":"柜温8℃"}.get(f,v))
       for f,l,v in RECEIPT] + [("acceptance_number","验收单编号","YS-01"),("defect_number","缺陷编号","QX-01")]
LINKS = [("original_acceptance","原验收单编号","YS-01"),("defect_number","缺陷编号","QX-01"),
         ("repair_number","整改记录编号","ZG-01")]
FIX = [("remediation","","整改记录单"),*CONTRACT[1:5],*LINKS,("repair_subject","整改对象",PROBLEM),
       ("repair_action","实际整改措施","已更换并校准探头"),("repair_result","整改状态","已完成"),
       ("repaired_on","整改完成日期","2026-09-23"),("repair_signer","整改签认","演练乙工（已签字）")]
FINAL = [("reinspection","","复验报告"),*[(f,l,"2026-09-26" if f=="accepted_on" else v) for f,l,v in RECEIPT[1:]],
         *LINKS,("acceptance_number","复验单编号","FY-02"),("repair_subject","复验对象",PROBLEM),
         ("defect_closure","缺陷关闭结论","已关闭")]


def graph(edit=None,groups=None,**kwargs):
    return material(groups or [CONTRACT,OLD,FIX,FINAL,WARRANTY,BANK_DOC],edit,**kwargs)


class ReinspectionTests(unittest.TestCase):
    def test_closed_requires_all_three_steps_and_preserves_original(self):
        g = graph(lambda i,f,l,v:"2026-09-27" if f=="paid_on" else v)
        check, = rows(g,"H02")
        self.assertEqual(conclusion(execute(g,PERFORMANCE))["verdict"],"pass",check["detail"])
        trace = check["reinspection"]
        self.assertEqual(trace["state"],"closed")
        self.assertEqual([s["role"] for s in trace["steps"]],["original","repair","final"])
        self.assertEqual([s["date"] for s in trace["steps"]],["2026-09-20","2026-09-23","2026-09-26"])
        self.assertTrue(all(set(s["evidence"])<=set(check["evidence"]) for s in trace["steps"]))
        adverse = next(f["id"] for f in g["facts"] if f["field"]=="acceptance_result" and f["value"]=="不合格")
        self.assertIn(adverse,trace["steps"][0]["evidence"])
        self.assertNotIn(adverse,[f["id"] for f in expert_candidates(g)[0]])
        prior = next(f for f in compute(g,BOARD_FORMAT) if f["rule"]=="H02")
        self.assertEqual(prior["status"],"issue")
        self.assertNotIn("reinspection",prior)

    def test_bare_clean_retest_does_not_clear_adverse_finding(self):
        for groups in ([CONTRACT,OLD,FINAL],[CONTRACT,OLD,FIX],[CONTRACT,OLD,RECEIPT],[CONTRACT,OLD,FIX,FINAL,FINAL]):
            with self.subTest(groups=len(groups)):
                g = graph(groups=groups)
                self.assertEqual(rows(g,"H02")[0]["status"],"issue")
                self.assertEqual(rows(g,"H04")[1]["status"],"risk")
        alone = graph(groups=[CONTRACT,FINAL])
        self.assertEqual(rows(alone,"H02")[0]["status"],"missing")

    def test_mismatches_never_release_the_defect(self):
        for unit,field,value in ((3,"contract_id","YL-999"),(4,"subject","打印机"),(3,"seller","另一家"),
                                  (3,"original_acceptance","YS-02"),(4,"defect_number","QX-02"),(4,"repair_number","ZG-99"),
                                  (4,"acceptance_number","YS-01"),(3,"repair_subject","外壳缺漆"),(3,"repair_action","拟更换探头"),
                                  (3,"repair_result","部分完成"),(3,"repair_signer",None),(4,"defect_closure","待复验"),
                                  (4,"measured_result","柜温6℃"),(3,"repaired_on","2026-09-28"),(4,"acceptance_exception","仍有异响")):
            with self.subTest(field=field):
                g = graph(lambda i,f,l,v:value if (i,f)==(unit,field) else v)
                c = rows(g,"H02")[0]
                self.assertEqual((c["status"],c["reinspection"]["state"]),("issue","open"),c["detail"])

    def test_gaps_or_disputed_original_block_closure(self):
        g = graph(omissions=[(3,"整改记录编号：ZG-02")])
        self.assertEqual(rows(g,"H02")[0]["status"],"issue")
        g = graph()
        next(f for f in g["facts"] if f["field"]=="defect_closure")["status"]="disputed"
        self.assertEqual(rows(g,"H02")[0]["status"],"issue")

    def test_final_date_controls_actual_payment_and_warranty(self):
        for field,value,rule,status in (("paid_on","2026-09-21","H05","risk"),("paid_on","2026-09-26","H05","missing"),
                                        ("paid_on","2026-09-27","H05","ok"),("warranty_release","2026-09-24双方确认质保期已满","H04","missing")):
            with self.subTest(value=value):
                g = graph(lambda i,f,l,v:value if f==field else v)
                self.assertEqual(rows(g,rule)[-1]["status"],status)
        g = graph(lambda i,f,l,v:"第一期" if f=="payment_designation" else v)
        self.assertEqual(rows(g,"H05")[0]["status"],"ok")

    def test_generic_receipt_role_and_upload_order(self):
        form = [("acceptance","","验收报告"),*FINAL[1:]]
        for groups in ([CONTRACT,form,FIX,OLD],[CONTRACT,FIX,OLD,form]):
            c = rows(graph(groups=groups),"H02")[0]
            self.assertEqual(c["reinspection"]["state"],"closed",c["detail"])

    def test_offline_ledger_tampering_and_shared_reference_entity(self):
        g=graph()
        first=next(f for f in g["facts"] if f["field"]=="acceptance_number" and f["value"]=="YS-01")
        target=next(e["to"] for e in g["edges"] if e["type"]=="acceptance_number" and first["id"] in e["evidence"])
        self.assertEqual(len([e for e in g["edges"] if e["type"]=="original_acceptance" and e["to"]==target]),2)
        paper={"policy":{**VERSION,"profile":PERFORMANCE},"graph":g,"findings":execute(g,PERFORMANCE)}
        verify_findings(paper)
        for field,value in (("date","2026-09-19"),("unit","d01"),("evidence",[first["id"]])):
            fake=copy.deepcopy(paper)
            next(f for f in fake["findings"] if f["rule"]=="H02")["reinspection"]["steps"][2][field]=value
            with self.assertRaises(ValueError):
                verify_findings(fake)
        fake=copy.deepcopy(paper)
        edge=next(e for e in fake["graph"]["edges"] if e["type"]=="original_acceptance")
        edge["to"]=next(n["id"] for n in g["nodes"] if n["type"]=="acceptance_reference" and n["label"]=="FY-02")
        with self.assertRaises(ValueError):
            verify_findings(fake)

    def test_full_settlement_reads_value_and_date_from_closed_reinspection(self):
        units=[("currency","币种","人民币"),("unit","金额单位","元")]
        total=("total","含税总额","120.00")
        contract=[r for r in CONTRACT if r[0] not in ("payment_term","payment_stage")]
        contract += [("payment_term","付款条款","验收合格后一次性支付全款"),*units,total]
        invoice=[("invoice","","采购发票"),*CONTRACT[1:5],("invoice_id","发票号码","YL-AA-01"),
                 ("net","不含税合计","110.00"),("tax","税额合计","10.00"),("issued_on","开票日期","2026-09-27"),*units,total]
        g=material([contract,OLD+units+[("total","含税总额","99.00")],FIX,FINAL+units+[total],invoice])
        g["profile"]=PROFILE
        findings=execute(g,PROFILE)
        by_rule={f["rule"]:f for f in findings}
        for rule in ("P01","D01","A01","M02","H02"):
            self.assertEqual(by_rule[rule]["status"],"ok",by_rule[rule]["detail"])
        self.assertIn("2026-09-26",by_rule["D01"]["detail"])
        m02 = by_rule["M02"]
        original_total = next(f["id"] for f in g["facts"] if f["field"]=="total" and f["doc"]=="d02")
        self.assertNotIn(original_total,m02["evidence"])
        self.assertTrue(m02["calculations"])
        CalculationEvidence(g).verify(findings)
