import copy
import unittest

from config import BANK, PERFORMANCE
from controls import VERSION, conclusion, execute
from delegation import verify_sources
from performance import REINSPECTION_FORMAT, compute, verify_findings
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material, rows


CONTRACT_BY_AGENT = [
    ("buyer_agent_signature","甲方代理人签字","演练林岚（已签字）") if field=="buyer_signature" else
    (field, label, "本合同自双方签字或盖章之日起生效" if field=="effect_clause" else value)
    for field,label,value in CONTRACT
] + [("buyer_grant_ref","甲方委托书编号","WT-001")]
GRANT = [
    ("power_of_attorney","","授权委托书"),("grant_number","委托书编号","WT-001"),
    ("contract_id","合同编号","YL-121"),("subject","采购标的","冷藏柜"),("grant_principal","委托单位","演练甲"),
    ("grant_counterparty","交易相对方","演练乙"),("grant_agent","受托人","演练林岚"),
    ("grant_task","代理事项","办理本合同采购"),("grant_scope","授权权限","代表委托单位签署本采购合同"),
    ("granted_on","授权出具日期","2026-08-01"),("grant_from","授权起始日","2026-08-15"),
    ("grant_until","授权截止日","2026-09-01"),("grant_conditions","附加限制","无"),
    ("grant_signature","委托单位签章","演练甲（已盖章）"),
]


def sample(edit=None, grants=None, **kwargs):
    return material([CONTRACT_BY_AGENT, *(grants if grants is not None else [GRANT]), RECEIPT, WARRANTY, BANK_DOC], edit, **kwargs)


class DelegationTests(unittest.TestCase):
    def test_last_authorized_day_connects_the_contract_and_all_three_payment_conditions(self):
        graph = sample()
        finding, = rows(graph, "H01")
        entry, = finding["delegations"]
        self.assertEqual((entry["status"],entry["side"],entry["agent"],entry["signed_on"],entry["valid_until"]),
                         ("ok","buyer","演练林岚","2026-09-01","2026-09-01"))
        self.assertTrue(set(entry["evidence"]) <= set(finding["evidence"]))
        self.assertTrue(all(f["status"]=="ok" and "d02" in f["scope"] for f in rows(graph,"H04")))
        self.assertEqual(conclusion(execute(graph,PERFORMANCE))["verdict"],"pass")
        legacy = next(f for f in compute(graph,REINSPECTION_FORMAT) if f["rule"]=="H01")
        self.assertNotEqual(legacy["status"],"ok")
        self.assertNotIn("delegations",legacy)
        links = [e["to"] for e in graph["edges"] if e["type"] in ("grant_number","buyer_grant_ref")]
        self.assertEqual(len(links),2)
        self.assertEqual(len(set(links)),1)
        bank = material([CONTRACT_BY_AGENT,GRANT,BANK_DOC])
        self.assertEqual(next(f for f in execute(bank,BANK) if f["rule"]=="B01")["status"],"ok")

    def test_permissions_dates_identity_and_contract_form(self):
        for field,value,status in (("grant_until","2026-08-31","risk"),("granted_on","2026-09-04","risk"),
                ("grant_from","2026-09-02","missing"),("grant_scope","仅限收货验收","risk"),
                ("grant_scope","签署本合同但应另行审批","missing"),("grant_scope","不得签署本合同","risk"),
                ("grant_principal","其他公司","missing"),("grant_counterparty","其他单位","missing"),
                ("grant_agent","演练陈宁","missing"),("grant_number","WT-0010","missing"),
                ("grant_number","尾号001","missing"),("grant_signature","其他公司（已盖章）","missing"),
                ("grant_conditions","不超过五万元","missing"),("effect_clause","本合同自双方盖章之日起生效","missing")):
            with self.subTest(field=field,value=value):
                g=sample(lambda i,f,l,v:value if f==field else v)
                self.assertEqual(rows(g,"H01")[0]["status"],status)
                self.assertTrue(all(f["status"]=="missing" for f in rows(g,"H04")))
                self.assertEqual(rows(g,"H02")[0]["status"],"ok")
        for g in (sample(grants=[]),sample(grants=[GRANT,GRANT]),sample(confirm=False),
                  sample(lambda i,f,l,v:"冷库" if i==2 and f=="subject" else v)):
            self.assertNotEqual(rows(g,"H01")[0]["status"],"ok")
        ordinary = [("buyer_signature","甲方签署",v) if f=="buyer_agent_signature" else (f,l,v) for f,l,v in CONTRACT_BY_AGENT]
        self.assertEqual(rows(material([ordinary,GRANT]),"H01")[0]["status"],"ok")

    def test_unread_conditions_and_shared_signer_are_never_silently_accepted(self):
        note = "备注：签约前须另经采购总监书面批准"
        g=sample(omissions=[(2,note)])
        self.assertEqual(rows(g,"H01")[0]["status"],"missing")
        gap, = [gap for gap in g["gaps"] if gap["quality"]=="mandate_clause"]
        self.assertEqual((gap["doc"],gap["quote"]),("d02",note))
        self.assertIn(gap["id"],rows(g,"H01")[0]["delegations"][0]["evidence"])
        graph=sample()
        graph["delegation_coverage"]["pages"][0]["native"]=False
        self.assertEqual(rows(graph,"H01")[0]["status"],"missing")
        both=[("seller_agent_signature","乙方代理人签字","演练林岚（已签字）") if f=="seller_signature" else (f,l,v)
              for f,l,v in CONTRACT_BY_AGENT]
        other=[(f,l,{"grant_principal":"演练乙","grant_counterparty":"演练甲","grant_number":"WT-002",
                     "grant_signature":"演练乙（已盖章）"}.get(f,v)) for f,l,v in GRANT]
        finding=rows(material([both,GRANT,other]),"H01")[0]
        self.assertEqual([e["status"] for e in finding["delegations"]],["risk","risk"])

    def test_offline_rechecks_every_mandate_line_entity_and_decision(self):
        g=sample()
        paper={"policy":{**VERSION,"profile":PERFORMANCE},"graph":g,"findings":execute(g,PERFORMANCE)}
        printed="\n".join(l+"："+v if l else v for _,l,v in GRANT)
        verify_sources(paper,lambda *_:printed)
        verify_findings(paper)
        for case in ("date","edge","source","coverage"):
            with self.subTest(case=case):
                changed=copy.deepcopy(paper)
                if case=="date":
                    next(f for f in changed["findings"] if f["rule"]=="H01")["delegations"][0]["valid_until"]="2026-09-10"
                    with self.assertRaises(ValueError): verify_findings(changed)
                    continue
                if case=="edge":
                    next(e for e in changed["graph"]["edges"] if e["type"]=="grant_agent")["to"]="d01"
                if case=="coverage":
                    changed["graph"]["delegation_coverage"]["pages"]=[]
                with self.assertRaises(ValueError):
                    verify_sources(changed,lambda *_:printed+"\n另有限制" if case=="source" else printed)
