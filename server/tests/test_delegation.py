import copy
import unittest
from unittest.mock import patch

from config import BANK, PERFORMANCE
from controls import VERSION, conclusion, execute
from delegation import LEGACY_FORMAT, NAME_FORMAT, NATIVE_NAME_FORMAT, TERMS_FORMAT, coverage_gaps, rows_for_grants, unresolved_agents, verify_sources
from graph import build_graph
from performance import DELEGATION_FORMAT, IDENTITY_FORMAT, REINSPECTION_FORMAT, compute, verify_findings
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


def identity(signer, agent):
    return lambda i,f,l,v: {"buyer_agent_signature":signer+"（已签字）", "grant_agent":agent}.get(f,v)


def fixture_text(edit=None):
    pages={}
    for i,group in enumerate([CONTRACT_BY_AGENT,GRANT,RECEIPT,WARRANTY,BANK_DOC],1):
        lines=[]
        for field,label,value in group:
            value=edit(i,field,label,value) if edit else value
            lines.append(label+"："+value if label else value)
        pages[f"d{i:02d}",1]="\n".join(lines)
    return lambda doc,page:pages[doc,page]


class DelegationTests(unittest.TestCase):
    def test_issue_date_is_bound_to_the_originals_and_not_an_intraday_sequence(self):
        for issued,status,order in (("2026-08-31","ok","after"),("2026-09-01","missing","same_day"),("2026-09-02","risk","before")):
            with self.subTest(issued=issued):
                graph=sample(lambda i,f,l,v:issued if f=="granted_on" else v)
                signed,=rows(graph,"H01")
                entry,=signed["delegations"]
                self.assertEqual((signed["status"],entry["status"],entry["issuance_order"]["state"]),(status,status,order))
                for key,unit,field in (("signed_refs","d01","signed_on"),("issued_refs","d02","granted_on")):
                    ref,=entry["issuance_order"][key]
                    fact=next(f for f in graph["facts"] if f["id"]==ref)
                    self.assertEqual((fact["doc"],fact["field"]),(unit,field))
                    self.assertIn(ref,entry["evidence"]); self.assertIn(ref,signed["evidence"])
                self.assertEqual(rows(graph,"H02")[0]["status"],"ok")
                for rule in ("H04","H05"):
                    self.assertTrue(all(f["status"]==("ok" if status=="ok" else "missing") for f in rows(graph,rule)))
                if order=="same_day":
                    self.assertIn("时分",entry["detail"])
        for edit,reason in (({"grant_scope":"仅限收货验收"},"权限不足"),({"grant_until":"2026-08-31"},"授权期间")):
            graph=sample(lambda i,f,l,v:{"granted_on":"2026-09-01",**edit}.get(f,v))
            entry,=rows(graph,"H01")[0]["delegations"]
            self.assertEqual(entry["status"],"risk")
            self.assertIn(reason,entry["detail"]); self.assertIn("同一日期",entry["detail"])

    def test_mismatched_instruments_and_unread_dates_do_not_acquire_an_issuance_order(self):
        for graph in (sample(grants=[GRANT,GRANT]),sample(lambda i,f,l,v:"另一个单位" if f=="grant_principal" else v),
                      sample(lambda i,f,l,v:"2026年9月0 1日" if f=="granted_on" else v)):
            self.assertNotIn("issuance_order",rows(graph,"H01")[0]["delegations"][0])

    def test_archived_same_day_clearance_replays_and_requires_new_review_to_sign(self):
        edit=lambda i,f,l,v:"2026-09-01" if f=="granted_on" else v
        graph=sample(edit)
        policy={**VERSION,"profile":PERFORMANCE}
        paper={"graph":graph,"policy":policy,"findings":execute(graph,PERFORMANCE)}
        verify_sources(paper,fixture_text(edit)); verify_findings(paper)
        entry=next(f for f in paper["findings"] if f["rule"]=="H01")["delegations"][0]
        entry["issuance_order"]["issued_refs"]=entry["issuance_order"]["signed_refs"]
        with self.assertRaises(ValueError): verify_findings(paper)
        graph["delegation_coverage"]["format"]=TERMS_FORMAT
        paper={"graph":graph,"policy":dict(policy,version="2026.11.25.26",delegation_checks=TERMS_FORMAT),"findings":execute(graph,PERFORMANCE)}
        for finding in paper["findings"]:
            finding["version"]=paper["policy"]["version"]
        entry=next(f for f in paper["findings"] if f["rule"]=="H01")["delegations"][0]
        self.assertEqual(entry["status"],"ok"); self.assertNotIn("issuance_order",entry)
        verify_findings(paper); verify_sources(paper,fixture_text(edit))
        with self.assertRaisesRegex(ValueError,"同日出具"): verify_sources(paper,fixture_text(edit),signing=True)

    def test_all_restrictions_stay_bound_to_each_written_clause_and_affected_stages(self):
        grant=[r for r in GRANT if r[0]!="grant_conditions"]
        approval=("grant_conditions","授权限制","签约前须经负责人书面批准")
        prepay=("grant_conditions","附加限制","不得约定预付款")
        cap=("grant_conditions","授权条件","本合同含税总价不得超过人民币80,000.00元")
        contract=[*CONTRACT_BY_AGENT,("total","含税总额","人民币100,000.00元")]
        for limits,status in (([prepay,approval],"risk"),([approval,prepay],"risk"),([cap,approval],"risk"),
                              ([approval,("grant_conditions","授权条件","须经采购经理确认")],"missing"),
                              ([cap,("grant_conditions","授权金额上限","本合同含税总价不得超过人民币120,000.00元")],"missing")):
            with self.subTest(limits=limits):
                def numeric_amount(docs,pages,*args):
                    pages[0]["extraction"]["output"]["facts"][-1]["value"]="100,000.00"
                    return build_graph(docs,pages,*args)
                with patch("test_performance.build_graph",side_effect=numeric_amount):
                    g=material([contract,[*grant,*limits],RECEIPT,WARRANTY,BANK_DOC])
                signed,=rows(g,"H01")
                entry,=signed["delegations"]
                self.assertEqual(entry["status"],status)
                self.assertEqual(len(entry["limits"]),2)
                facts={f["id"]:f for f in g["facts"]}
                self.assertEqual([facts[c["field_ref"]]["value"] for c in entry["limits"]],[v for _,_,v in limits])
                for c in entry["limits"]:
                    self.assertIn(c["field_ref"],signed["evidence"])
                    if c["comparison_ref"]:
                        self.assertIn(c["comparison_ref"],signed["evidence"])
                        self.assertIn(facts[c["comparison_ref"]]["field"],("payment_stage","total"))
                self.assertEqual(rows(g,"H02")[0]["status"],"ok")
                self.assertTrue(all(f["status"]=="missing" for f in rows(g,"H04")))
        for raw in ("100,000.00","人民币1 00,000.00元","人民币10,00.00元","美元100,000.00元"):
            g=material([[*CONTRACT_BY_AGENT,("total","含税总额",raw)],[*grant,cap]])
            self.assertEqual(rows(g,"H01")[0]["delegations"][0]["limits"][0]["comparison_ref"],None)

    def test_ambiguous_states_broken_dates_and_mixed_pages_need_review(self):
        mixed=sample()
        mixed["delegation_coverage"]["pages"][0]["text_only"]=False
        broken=sample(lambda i,f,l,v:"2026年9月3 0日" if f=="grant_until" else v)
        conflict=sample(grants=[[*GRANT,("grant_state","授权状态","有效"),("grant_state","委托状态","已撤销")]])
        for graph in (mixed,broken,conflict):
            self.assertEqual(rows(graph,"H01")[0]["status"],"missing")
        self.assertIsNone(rows(broken,"H01")[0]["delegations"][0]["valid_until"])

    def test_past_positive_with_two_limits_replays_but_cannot_be_signed_as_clear(self):
        grant=[*GRANT,("grant_conditions","授权限制","不得约定预付款")]
        g=sample(grants=[grant])
        coverage=g["delegation_coverage"]
        coverage["format"]=NATIVE_NAME_FORMAT
        for p in coverage["pages"]: p.pop("text_only")
        findings=compute(g)
        self.assertEqual(next(f["status"] for f in findings if f["rule"]=="H01"),"ok")
        paper={"policy":dict(VERSION,version="2026.11.25.21",delegation_checks=NATIVE_NAME_FORMAT),"graph":g,"findings":findings}
        read=fixture_text()
        def source(d,p):
            return read(d,p)+("\n授权限制：不得约定预付款" if d=="d02" else "")
        verify_sources(paper,source)
        with self.assertRaisesRegex(ValueError,"按现行程序重审"): verify_sources(paper,source,signing=True)

    def test_role_joint_and_redacted_names_remain_observations_with_all_phases_pending(self):
        for observed, kind in (("采购负责人","role"),("法定代表人","role"),("采购部","role"),("演练林岚及演练方程","joint"),
                               ("张三、李四","joint"),("张三 李四","joint"),("王某","redacted"),("张＊","redacted"),
                               ("陈XX","redacted"),("待填写资料","unclear")):
            with self.subTest(observed=observed):
                graph=sample(identity(observed,observed))
                h01,=rows(graph,"H01")
                entry,=h01["delegations"]
                hold,=graph["delegation_coverage"]["agent_holds"]
                self.assertEqual((h01["status"],entry["agent_kind"],hold["kind"]),("missing",kind,kind))
                ref=hold["fact"]
                self.assertIn(ref,entry["evidence"])
                self.assertTrue(any(e["type"]=="unresolved_grant_agent" and e["from"]==hold["unit"]
                                    and e["to"]==ref and e["evidence"]==[ref] for e in graph["edges"]))
                self.assertFalse(any(n["type"]=="mandatary" for n in graph["nodes"]))
                self.assertEqual(rows(graph,"H02")[0]["status"],"ok")
                self.assertTrue(all(f["status"]=="missing" for f in rows(graph,"H04")+rows(graph,"H05")))
        for name in ("王和平","欧阳明月","艾力·阿布"):
            graph=sample(identity(name,name))
            self.assertEqual(rows(graph,"H01")[0]["status"],"ok")
            self.assertFalse(graph["delegation_coverage"]["agent_holds"])
        mixed=sample(identity("张三 李四","张三李四"))
        self.assertEqual(rows(mixed,"H01")[0]["delegations"][0]["agent_kind"],"joint")

    def test_identity_gap_preserves_separate_date_and_scope_risks_and_signing_roles(self):
        def edit(i,f,l,v):
            return {"grant_until":"2026-08-31","grant_scope":"仅限收货"}.get(f, identity("采购主管","采购主管")(i,f,l,v))
        entry=rows(sample(edit),"H01")[0]["delegations"][0]
        self.assertEqual((entry["status"],entry["agent_kind"]),("risk","role"))
        for value in ("采购主管","2026-08-31","仅限收货"):
            self.assertIn(value,entry["detail"])
        wrong_signature=[(f,"见证人签字" if f=="buyer_agent_signature" else l,v) for f,l,v in CONTRACT_BY_AGENT]
        self.assertEqual(rows(material([wrong_signature,GRANT]),"H01")[0]["status"],"missing")

    def test_verify_holds_requires_the_original_agent_field_and_prevents_shared_entity_recreation(self):
        graph=sample(identity("采购负责人","采购负责人"))
        paper={"policy":dict(VERSION,profile=PERFORMANCE),"graph":graph,"findings":execute(graph,PERFORMANCE)}
        source=fixture_text(identity("采购负责人","采购负责人"))
        verify_sources(paper,source)
        verify_findings(paper)
        for kind in ("remove","wrong_fact","extra_join","extra_person","type"):
            with self.subTest(kind=kind):
                changed=copy.deepcopy(paper)
                g=changed["graph"]
                edge=next(e for e in g["edges"] if e["type"]=="unresolved_grant_agent")
                if kind=="remove": g["delegation_coverage"]["agent_holds"].clear()
                if kind=="wrong_fact": edge["to"]="d01/p1/f1"
                if kind=="extra_join": g["edges"].append({**edge,"type":"grant_agent"})
                if kind=="extra_person": g["nodes"].append({"type":"mandatary","id":"invented","label":"采购负责人"})
                if kind=="type": g["delegation_coverage"]["agent_holds"][0]["kind"]="named"
                with self.assertRaises(ValueError): verify_sources(changed,source)

    def test_old_archived_decisions_replay_but_ambiguous_named_authority_needs_rerun_before_signoff(self):
        def legacy_coverage(graph,read):
            pages=rows_for_grants(graph,read)
            graph["delegation_coverage"]={"format":LEGACY_FORMAT,"pages":pages}
            graph["gaps"].extend(coverage_gaps(pages))
        for name,approve in (("采购负责人",False),("张某",False),("演练林岚及演练方程",False),("王和平",True)):
            with self.subTest(name=name),patch("graph.record_mandate_pages",legacy_coverage):
                graph=sample(identity(name,name))
                findings=compute(graph,DELEGATION_FORMAT)
                self.assertEqual(next(f["status"] for f in findings if f["rule"]=="H01"),"ok")
                paper={"graph":graph,"policy":{"delegation_checks":LEGACY_FORMAT,"performance_checks":DELEGATION_FORMAT},"findings":findings}
                source=fixture_text(identity(name,name))
                verify_sources(paper,source)
                if approve: verify_sources(paper,source,signing=True)
                else:
                    with self.assertRaisesRegex(ValueError,"旧版签约授权"):
                        verify_sources(paper,source,signing=True)

    def test_native_names_separated_by_space_remain_distinct_even_if_the_reader_joins_them(self):
        for signed,granted in (("周宁 方程","周宁 方程"),("周宁方程","周宁　方程"),("周宁 方程","周宁方程"),("欧阳明月","欧阳明月")):
            with self.subTest(signed=signed,granted=granted):
                source=fixture_text(identity(signed,granted))
                def originals(docs,pages,*args):
                    for p in pages: p["text"]=source(p["doc"],p["number"])
                    return build_graph(docs,pages,*args)
                with patch("test_performance.build_graph",side_effect=originals):
                    graph=sample(identity("".join(signed.split()),"".join(granted.split())))
                paper={"graph":graph,"policy":dict(VERSION,profile=PERFORMANCE),"findings":execute(graph,PERFORMANCE)}
                verify_sources(paper,source,signing=True)
                verify_findings(paper)
                evidence=graph["delegation_coverage"]
                separate=lambda value:any(c.isspace() for c in value)
                self.assertEqual(bool(evidence["signer_holds"]),separate(signed))
                self.assertEqual(bool(evidence["agent_holds"]),separate(granted))
                self.assertEqual(any(n["type"]=="mandatary" for n in graph["nodes"]),not separate(granted))
                for hold in evidence["signer_holds"]+evidence["agent_holds"]:
                    line,=hold["lines"]
                    self.assertEqual(hold["kind"],"joint")
                    self.assertEqual(line["quote"],source(hold["doc"],hold["page"]).splitlines()[line["line"]-1])
                expected="missing" if separate(signed) or separate(granted) else "ok"
                self.assertEqual(rows(graph,"H01")[0]["status"],expected)
                self.assertTrue(all(f["status"]==expected for f in rows(graph,"H04")+rows(graph,"H05")))
                if evidence["signer_holds"]:
                    hold,=evidence["signer_holds"]
                    edge,=[e for e in graph["edges"] if e["type"]==hold["field"] and e["evidence"]==[hold["fact"]]]
                    self.assertEqual(edge["to"],hold["fact"])
                    edge["to"]=hold["unit"]
                    with self.assertRaisesRegex(ValueError,"待核签署栏"): verify_sources(paper,source)
                    edge["to"]=hold["fact"]
                    evidence["signer_holds"][0]["lines"][0]["quote"]="甲方代理人签字：周宁方程（已签字）"
                    with self.assertRaises(ValueError): verify_sources(paper,source)

    def test_v2_positive_with_joined_transcription_cannot_be_signed_after_native_recheck(self):
        source=fixture_text(identity("周宁 方程","周宁 方程"))
        def originals(docs,pages,*args):
            for p in pages: p["text"]=source(p["doc"],p["number"])
            return build_graph(docs,pages,*args)
        def model_only(graph,read):
            pages=rows_for_grants(graph,read)
            graph["delegation_coverage"]={"format":NAME_FORMAT,"pages":pages,"agent_holds":unresolved_agents(graph)}
            graph["gaps"].extend(coverage_gaps(pages))
        with patch("test_performance.build_graph",side_effect=originals),patch("graph.record_mandate_pages",model_only):
            graph=sample(identity("周宁方程","周宁方程"))
        findings=compute(graph,IDENTITY_FORMAT)
        self.assertEqual(next(f["status"] for f in findings if f["rule"]=="H01"),"ok")
        report={"graph":graph,"policy":{"delegation_checks":NAME_FORMAT,"performance_checks":IDENTITY_FORMAT},"findings":findings}
        verify_sources(report,source)
        with self.assertRaisesRegex(ValueError,"旧版签约授权"): verify_sources(report,source,signing=True)

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
        source=fixture_text()
        verify_sources(paper,source)
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
                    verify_sources(changed,lambda doc,page:source(doc,page)+("\n另有限制" if case=="source" else ""))
