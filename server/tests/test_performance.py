import copy
import unittest

from config import BANK, PERFORMANCE, PROFILE, TRAVEL
from controls import VERSION, conclusion, execute
from graph import build_graph
from performance import FIRST_FORMAT, compute, verify_findings


CONTRACT = [
    ("contract","","采购合同"),("contract_id","合同编号","YL-121"),("buyer","采购方","演练甲"),
    ("seller","供应方","演练乙"),("subject","采购标的","冷藏柜"),("signed_on","签约日期","2026-09-01"),
    ("effect_on","实际生效日期","2026-09-01"),("effect_clause","生效条款","本合同自双方盖章之日起生效"),
    ("buyer_signature","甲方签章","演练甲（已盖章）"),("seller_signature","乙方签章","演练乙（已盖章）"),
    ("payment_term","付款条款","分三期付款"),("payment_stage","第一期","合同生效后支付30%"),
    ("payment_stage","第二期","最终验收合格后支付60%"),("payment_stage","第三期","质保期满后支付10%"),
    ("quantity_agreed","约定交付数量","4台"),("acceptance_criteria","约定验收标准","柜温不高于4℃"),
]
RECEIPT = [("acceptance","","验收报告"),*CONTRACT[1:5],("accepted_on","验收日期","2026-09-20"),
           ("acceptance_scope","验收范围","全部交付终验"),("acceptance_result","验收结论","合格"),
           ("acceptance_signer","验收签认","演练丁（已签字）"),("acceptance_exception","遗留事项","无"),
           ("quantity_accepted","实际验收数量","4台"),("inspection_basis","检验依据","柜温不高于4℃"),
           ("measured_result","实测结果","柜温3℃")]
WARRANTY = [("warranty","","质保期满确认单"),*CONTRACT[1:5],("warranty_release","质保期满确认","2026-11-20双方确认质保期已满"),
            ("acceptance_signer","验收签认","演练丁（已签字）")]
BANK_DOC = [("bank_receipt","","银行付款回单"),("contract_id","合同编号","YL-121"),("payer","付款户名","演练甲"),
            ("payee","收款户名","演练乙"),("paid_on","付款日期","2026-09-21"),("transfer_status","交易状态","交易成功"),
            ("payment_designation","款项用途","第二期")]
APPROVAL = [("contract_approval","","合同审批单"),*CONTRACT[1:4],("approval_authority","审批机构","演练甲董事会"),
            ("approval_result","审批决定","批准"),("approved_on","审批日期","2026-09-01"),
            ("approval_signer","审批签认","演练孙宁（已签字）")]
SIGN_FIELDS = {"buyer_signature","seller_signature","acceptance_signer","approval_signer","repair_signer",
               "buyer_agent_signature","seller_agent_signature","grant_signature"}


def material(groups, edit=None, confirm=True, omissions=()):
    docs, pages, signoffs = [], [], {}
    for i, rows in enumerate(groups,1):
        doc = f"d{i:02d}"
        docs.append(dict(id=doc, name=rows[0][-1], sha256="sample"))
        facts, lines = [], []
        for field,label,value in rows:
            if edit:
                value = edit(i,field,label,value)
            if value is None:
                continue
            quote = label + "：" + value if label else value
            lines.append(quote)
            facts.append(dict(field=field,value=value,quote=quote,region="top"))
            if confirm and field in SIGN_FIELDS:
                signoffs[f"{doc}/p1/f{len(facts)}"] = {"decision":"confirm","source_check":{"fixture":True}}
        lines += [line for unit,line in omissions if unit == i]
        pages.append(dict(doc=doc,number=1,sha256="page",text="\n".join(lines),
                          layer={"type":"text","lines":{str(j):[[0,.1,.9,.2]] for j in range(1,len(lines)+1)}},
                          extraction={"output":{"quality":"readable","facts":facts}}))
    graph = build_graph(docs,pages,signoffs)
    graph["profile"] = PERFORMANCE
    return graph


def rows(graph, rule):
    return [r for r in execute(graph,PERFORMANCE) if r["rule"] == rule]


class PerformanceTests(unittest.TestCase):
    def test_positive_closed_chain_and_citations(self):
        graph = material([CONTRACT,RECEIPT,WARRANTY,BANK_DOC])
        findings = execute(graph,PERFORMANCE)
        self.assertEqual(conclusion(findings)["verdict"],"pass",[(f["rule"],f["detail"]) for f in findings if f["status"]!="ok"])
        phases = rows(graph,"H04")
        self.assertEqual([r["stage"]["share"] for r in phases], ["30","60","10"])
        for row in phases:
            self.assertIn(row["stage"]["clause_ref"],row["evidence"])
        self.assertIn("d03",phases[2]["scope"])
        self.assertNotIn("d03",phases[0]["scope"])
        self.assertEqual(rows(graph,"H05")[0]["stage"]["name"],"第二期")

    def test_no_assumed_signatures_or_approval(self):
        for graph in (material([CONTRACT,RECEIPT],confirm=False),
                      material([CONTRACT,RECEIPT],lambda i,f,l,v:"本合同经双方签字并盖章且董事会批准后生效" if f=="effect_clause" else v),
                      material([CONTRACT,RECEIPT],lambda i,f,l,v:"演练丙（已盖章）" if f=="seller_signature" else v),
                      material([CONTRACT,RECEIPT],lambda i,f,l,v:"演练乙（已签字）" if f=="seller_signature" else v),
                      material([CONTRACT+[("contract_state","合同状态","已解除")],RECEIPT])):
            self.assertNotEqual(rows(graph,"H01")[0]["status"],"ok")
            self.assertTrue(all(r["status"]!="ok" for r in rows(graph,"H04")))

    def test_advance_partial_acceptance_and_warranty_are_independent(self):
        for field,value,status in (("acceptance_result","未通过","issue"),("acceptance_result","有条件通过","risk"),
                                   ("measured_result","柜温8℃","issue"),("measured_result","柜温3毫米","missing"),
                                   ("measured_result","室温3℃","missing"),("measured_result",None,"missing"),
                                   ("acceptance_scope","第一批到货初验","risk"),("acceptance_exception","密封条待更换","risk"),
                                   ("quantity_accepted","3台","risk"),("inspection_basis","另行约定","risk"),
                                   ("subject","打印机","missing"),("contract_id","YL-122","missing")):
            with self.subTest(field=field,value=value):
                g = material([CONTRACT,RECEIPT],lambda i,f,l,v:value if i==2 and f==field else v)
                self.assertEqual(rows(g,"H02")[0]["status"],status)
                self.assertEqual(rows(g,"H04")[0]["status"],"ok")
                self.assertNotEqual(rows(g,"H04")[1]["status"],"ok")
        g = material([CONTRACT,RECEIPT])
        self.assertEqual([r["status"] for r in rows(g,"H04")],["ok","ok","missing"])
        unrelated = material([CONTRACT,RECEIPT,WARRANTY],lambda i,f,l,v:"YL-122" if i==3 and f=="contract_id" else v)
        self.assertEqual(rows(unrelated,"H04")[-1]["status"],"missing")

    def test_contract_only_unknown_or_omitted_terms(self):
        g = material([CONTRACT])
        self.assertEqual([r["status"] for r in rows(g,"H04")],["ok","missing","missing"])
        for g in (material([CONTRACT],lambda i,f,l,v:"合同生效后支付31%" if l=="第一期" else v),
                  material([CONTRACT],lambda i,f,l,v:None if l=="第二期" else v),
                  material([CONTRACT],omissions=[(1,"第四期：另行约定")]),
                  material([CONTRACT, [("other","","补充协议")]])):
            self.assertNotEqual(rows(g,"H03")[0]["status"],"ok")
            self.assertTrue(all(r["status"]!="ok" for r in rows(g,"H04")))
        extra = material([CONTRACT],lambda i,f,l,v:"合同生效且开票后支付30%" if l=="第一期" else v)
        self.assertEqual(rows(extra,"H04")[0]["status"],"missing")

    def test_inline_plan_preserves_whole_source_and_unknown_deadline(self):
        clause = "合同生效后支付30%，最终验收合格后支付60%，质保期满后支付10%"
        c = [r for r in CONTRACT if r[0] not in ("payment_stage","payment_term")] + [("payment_term","结算条款",clause)]
        graph = material([c,RECEIPT])
        stages = rows(graph,"H04")
        self.assertEqual([r["status"] for r in stages],["ok","ok","missing"])
        self.assertEqual(len({r["stage"]["clause_ref"] for r in stages}),1)

    def test_explicit_stage_identity_and_earlier_release(self):
        c = [r for r in CONTRACT if r[0] not in ("payment_stage","payment_term")]
        c.append(("payment_term","结算条款","合同生效后支付30%，最终验收合格后支付60%，质保期满后支付10%"))
        edit = lambda i,f,l,v:"第2期" if f=="payment_designation" else v
        g = material([c,RECEIPT,BANK_DOC],edit)
        self.assertEqual(rows(g,"H04")[1]["stage"]["name"],"条款 2")
        self.assertEqual(rows(g,"H05")[0]["status"],"missing")
        self.assertEqual(next(f["status"] for f in compute(g,FIRST_FORMAT) if f["rule"]=="H05"),"ok")
        self.assertEqual(rows(material([CONTRACT,RECEIPT,BANK_DOC],edit),"H05")[0]["status"],"ok")

    def test_approval_condition_needs_matching_decision_and_date(self):
        c = [(f,l,"本合同自双方盖章并经甲方董事会批准后生效" if f=="effect_clause" else v) for f,l,v in CONTRACT]
        success = material([c,APPROVAL,RECEIPT])
        self.assertEqual(rows(success,"H01")[0]["status"],"ok")
        self.assertIn("d02",rows(success,"H04")[0]["scope"])
        self.assertEqual(rows(material([c,RECEIPT]),"H01")[0]["status"],"missing")
        for field,value,expect in (("buyer","演练丙","missing"),("approval_authority","演练乙董事会","missing"),
                                   ("approval_result","退回补议","risk"),("approved_on","2026-09-10","risk"),
                                   ("approval_signer",None,"missing"),("approval_result","有条件批准","missing")):
            with self.subTest(field=field):
                graph = material([c,APPROVAL,RECEIPT],lambda i,f,l,v:value if i==2 and f==field else v)
                self.assertEqual(rows(graph,"H01")[0]["status"],expect)
                self.assertNotEqual(rows(graph,"H04")[0]["status"],"ok")

    def test_actual_timing_requires_identified_phase_and_associated_transfer(self):
        for field,value,status in (("paid_on","2026-09-03","risk"),("payment_designation","货款","missing"),
                                   ("payer","演练乙","missing"),("transfer_status","失败","missing")):
            g = material([CONTRACT,RECEIPT,BANK_DOC],lambda i,f,l,v:value if i==3 and f==field else v)
            self.assertEqual(rows(g,"H05")[0]["status"],status)
        g = material([CONTRACT+[("valid_until","合同有效期至","2026-09-05")],RECEIPT])
        self.assertEqual(rows(g,"H02")[0]["status"],"risk")

    def test_all_relevant_profiles_and_recomputed_workpaper(self):
        g = material([CONTRACT,RECEIPT])
        for profile in (PROFILE,BANK,PERFORMANCE,TRAVEL):
            g["profile"] = profile
            findings = execute(g,profile)
            self.assertEqual(any(f["rule"]=="H01" for f in findings),profile!=TRAVEL)
            report = {"policy":{**VERSION,"profile":profile},"graph":g,"findings":findings}
            verify_findings(report)
            if profile != TRAVEL:
                fake = copy.deepcopy(report)
                next(f for f in fake["findings"] if f["rule"]=="H04")["stage"]["share"]="99"
                with self.assertRaises(ValueError):
                    verify_findings(fake)
