import json
import unittest
from unittest.mock import patch

import inspection_coverage as inspection
import substitution_dates
from config import PERFORMANCE
from controls import VERSION, execute
from model import audit_graph
from performance import verify_findings
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


def example(received, ordered="QC-001、QC-002", *, extra=(), edit=None, omitted=False, attestations=None, supplement=None):
    contract = ("other","约定设备序列号",ordered)
    receipt = ("delivered_serials","实收设备序列号",received)
    groups = [CONTRACT + [( "equipment_model","约定设备型号","YL-C4")],
              RECEIPT + [("equipment_model","实收设备型号","YL-C4")], WARRANTY, BANK_DOC]
    if supplement:
        groups.append(supplement)
    lines = list(extra)
    for i, row in enumerate((contract, receipt), 1):
        if row[2] is None:
            continue
        if omitted:
            lines.append((i,row[1]+"："+row[2]))
        else:
            groups[i-1].append(row)
    def change(i,field,label,value):
        if field in ("quantity_agreed","quantity_accepted"):
            value = "2台"
        return edit(i,field,label,value) if edit else value
    graph = material(groups, change, omissions=lines, attestations=attestations)
    def read(doc,page):
        i = int(doc[1:])
        raw = []
        for f,label,value in groups[i-1]:
            value = change(i,f,label,value)
            if value is not None:
                raw.append((label+"：" if label else "")+value)
        return "\n".join(raw + [text for target,text in lines if target==i])
    return {"graph":graph,"policy":{**VERSION,"profile":PERFORMANCE},"findings":execute(graph,PERFORMANCE)},read


def summary(paper):
    findings = paper["findings"]
    acceptance = next(f for f in findings if f["rule"]=="H02")
    phases = [f for f in findings if f["rule"]=="H04"]
    return acceptance,phases,next(f for f in findings if f["rule"]=="H05")


def dated(day=22, *, decision=None, state="已签署", more=(), edit=None, order="QC-002、QC-009", contract_note=None):
    permit=contract_note or "供货约定：经采购方事先书面批准，可用QC-009代替QC-001。"
    filed=decision or f"演练甲于2026年9月{day}日同意以QC-009代替QC-001。"
    change=[("contract_addendum","","采购合同补充协议"),("base_contract_ref","原合同编号","YL-121"),
            ("addendum_number","补充协议编号","BC-121"),*CONTRACT[2:5],("change_state","补充协议状态",state),
            *CONTRACT[8:10],("other","代用决定",filed)]
    return example(order,extra=[(1,permit),*more],supplement=change,edit=edit)


class DeliveryRegisterTests(unittest.TestCase):
    def test_filed_decision_dates_attach_to_the_actual_acceptance_installment(self):
        for day,days in ((19,(1,2)),(20,(0,1)),(21,(-1,0)),(22,(-2,-1))):
            paper,read=dated(day)
            h,phases,bank=summary(paper)
            for f,delta in [(h,days[0]),(phases[1],days[0]),(bank,days[1])]:
                c=f["substitution_dates"]
                self.assertEqual((c["original"],c["replacement"],c["issuer"],c["days"]),("QC-001","QC-009","演练甲",delta))
                self.assertEqual(f["status"],"risk" if delta<0 else "missing")
                self.assertTrue({c["condition"],c["decision"],c["date_ref"]}<=set(f["evidence"]))
            self.assertTrue(all("substitution_dates" not in f for f in (phases[0],phases[2])))
            edges=substitution_dates.edges(paper["findings"])
            self.assertEqual(len(edges),2)
            paper["graph"]["edges"].extend(edges)
            inspection.verify(paper,read)
            verify_findings(paper)
            paper["graph"]["edges"].remove(edges[0])
            with self.assertRaisesRegex(ValueError,"引证关系"):
                inspection.verify(paper,read)

    def test_unsigned_conditional_crossed_or_unrelated_decisions_do_not_date_payment(self):
        for args in ({"state":"待双方签署"},{"more":[(5,"附注：自复验合格后适用")]},
                     {"more":[(1,"特别约定：采购方可追认")]},{"decision":"演练甲于2026年2月30日同意以QC-009代替QC-001。"},
                     {"decision":"演练甲于2026年9月22日同意以QC-001代替QC-009。"},
                     {"decision":"演练乙于2026年9月22日同意以QC-009代替QC-001。"},
                     {"decision":"演练甲于2026年9月22日拟同意以QC-009代替QC-001。"},
                     {"decision":"演练甲于2026年9月22日同意以QC-099代替QC-002。"},
                     {"contract_note":"供货约定：若日后补交手续，可用QC-009代替QC-001。"},
                     {"edit":lambda i,k,l,v:"不同合同" if k=="base_contract_ref" else v},
                     {"order":"QC-001、QC-002"},{"order":"QC-002、QC-00*"}):
            with self.subTest(args=args):
                paper,_=dated(**args)
                self.assertFalse(any("substitution_dates" in f for f in paper["findings"]))
        paper,_=dated(edit=lambda i,k,l,v:"交易失败" if k=="transfer_status" else v)
        self.assertIn("substitution_dates",summary(paper)[0])
        self.assertNotIn("substitution_dates",summary(paper)[2])
        paper,_=dated(edit=lambda i,k,l,v:None if k=="measured_result" else v)
        self.assertIn("substitution_dates",summary(paper)[2])

    def test_dated_decision_preserves_old_edition_and_requires_rerun_before_approval(self):
        paper,read=dated()
        graph=paper["graph"];ledger=inspection.sources(graph,read,version=inspection.SUBSTITUTION_FORMAT)
        graph["inspection_coverage_sources"]=ledger
        paper["policy"].update(version="2026.11.28.17",inspection_coverage=inspection.SUBSTITUTION_FORMAT)
        paper["findings"]=execute(graph,PERFORMANCE)
        self.assertFalse(any("substitution_dates" in f for f in paper["findings"]))
        inspection.verify(paper,read)
        with self.assertRaisesRegex(ValueError,"日期.*重审"):
            inspection.verify(paper,read,signing=True)
        self.assertTrue(inspection.same_serial_list("清单：QC-001、QC-002","清单：QC-001、 QC-002"))
        self.assertFalse(inspection.same_serial_list("清单：QC-001、QC-002","清单：QC-00 1、QC-002"))

    def test_substitution_conditions_applications_and_an_express_prohibition(self):
        cases = [
            ([(1,"供货约定：经采购方书面批准，可用QC-009代替QC-001。")],"substitution","missing","missing"),
            ([(2,"验收备注：以QC-009代替QC-001的申请仍待批准。")],"substitution","missing","missing"),
            ([(1,"交付约定：不得以QC-009代替QC-001。")],"prohibited","issue","risk"),
            ([(1,"交付约定：不得以QC-001代替QC-009。")],"substitution","missing","missing"),
            ([(1,"交付约定：不得以QC-009代替QC-001，但经批准除外。")],"substitution","missing","missing"),
            ([(1,"交付约定：不得以QC-009代替QC-001。"),(1,"例外约定：采购方可另行书面同意。")],"source","missing","missing"),
            ([(1,"维护说明：定期更换空气滤芯。"),(1,"财务备注：收款账号由012345改为056789。")],"difference","issue","risk"),
        ]
        for notes,state,status,paid in cases:
            with self.subTest(notes=notes):
                paper,read=example("QC-002、QC-009",extra=notes,omitted=True)
                h,phases,bank=summary(paper)
                self.assertEqual((h["inspection_coverage"]["state"],h["status"],bank["status"]),("register_"+state,status,paid))
                refs=h["delivery_register"]
                self.assertEqual(len(refs),2 if state=="difference" else 3)
                self.assertNotIn("delivery_register",phases[0])
                for f in (*phases[1:],bank):
                    self.assertEqual(f["delivery_register"],refs)
                    self.assertTrue(set(refs)<=set(f["evidence"]))
                if state=="substitution":
                    self.assertIn("2026-09-21",bank["detail"])
                    self.assertIn("批准",bank["detail"])
                inspection.verify(paper,read)
                verify_findings(paper)
        paper,_=example("QC-002、QC-009",extra=cases[0][0],edit=lambda i,k,l,v:"不合格" if k=="acceptance_result" else v)
        self.assertEqual(summary(paper)[0]["status"],"issue")

    def test_addendum_note_needs_its_own_verified_identity(self):
        change=[("contract_addendum","","采购合同补充协议"),("base_contract_ref","原合同编号","YL-121"),
                ("addendum_number","补充协议编号","BC-121"),*CONTRACT[2:5]]
        wording="供货约定：本协议拟以QC-009代替QC-001，须双方签字后生效。"
        for change_fields,expected in (({},"substitution"),({"base_contract_ref":"YL-122"},"scope"),
                                        ({"buyer":"另一采购方"},"scope"),({"addendum_number":"待定"},"scope")):
            with self.subTest(change=change_fields):
                paper,read=example("QC-002、QC-009",extra=[(5,wording)],supplement=change,
                                   edit=lambda i,k,l,v:change_fields.get(k,v) if i==5 else v)
                h,_,bank=summary(paper)
                self.assertEqual(h["inspection_coverage"]["state"],"register_"+expected)
                ref=next(r["id"] for r in inspection.register_rows(paper["graph"]) if r["quote"]==wording)
                self.assertEqual(ref in h["delivery_register"],expected=="substitution")
                self.assertEqual(ref in bank["delivery_register"],expected=="substitution")
                if expected=="substitution":
                    fields={f["field"] for f in paper["graph"]["facts"] if f["doc"]=="d05" and f["id"] in h["evidence"]}
                    self.assertTrue({"base_contract_ref","addendum_number","buyer","seller","subject"}<=fields)
                inspection.verify(paper,read)
                verify_findings(paper)

    def test_issued_comparison_that_omitted_a_qualification_requires_review_before_approval(self):
        clause="供货约定：经书面批准，可用QC-009代替QC-001。"
        for note,hold in ((clause,True),("日常维护：更换滤芯。",False)):
            paper,read=example("QC-002、QC-009",extra=[(1,note)])
            graph=paper["graph"]
            ledger=inspection.sources(graph,read,version=inspection.REGISTER_FORMAT)
            graph["inspection_coverage_sources"]=ledger
            nodes,edges=inspection.source_graph(ledger)
            graph["nodes"]=[n for n in graph["nodes"] if n["type"]!="inspection_line"]+nodes
            graph["edges"]=[e for e in graph["edges"] if e["type"]!="inspection_coverage_source"]+edges
            paper["policy"].update(version="2026.11.28.16",inspection_coverage=inspection.REGISTER_FORMAT)
            paper["findings"]=execute(graph,PERFORMANCE)
            self.assertEqual(summary(paper)[0]["inspection_coverage"]["state"],"register_difference")
            inspection.verify(paper,read)
            if hold:
                with self.assertRaisesRegex(ValueError,"代用.*重审"):
                    inspection.verify(paper,read,signing=True)
            else:
                inspection.verify(paper,read,signing=True)

    def test_original_registers_bind_to_final_acceptance_and_its_payments(self):
        for actual,state,status,payment in (("QC-002、QC-009","difference","issue","risk"),
                                            ("QC-002、QC-002","duplicate","risk","risk"),
                                            ("QC-002、QC-001","match","ok","ok"),
                                            ("QC-00*、QC-002","incomplete","missing","missing"),
                                            ("qc-001、QC002","spelling","missing","missing"),
                                            (None,"incomplete","missing","missing")):
            with self.subTest(actual=actual):
                p,read = example(actual,omitted=True)
                h,phases,bank = summary(p)
                self.assertEqual((h["inspection_coverage"]["state"],h["status"],bank["status"]),("register_"+state,status,payment))
                self.assertNotIn("delivery_register",phases[0])
                self.assertEqual(phases[0]["status"],"ok")
                for f in (h,*phases[1:],bank):
                    self.assertEqual(f["delivery_register"],h["inspection_coverage"]["register"]["rows"])
                    self.assertTrue(set(f["delivery_register"])<=set(f["evidence"]))
                if state=="difference":
                    register=h["inspection_coverage"]["register"]
                    self.assertEqual((register["contract_only"],register["receipt_only"]),(["QC-001"],["QC-009"]))
                    self.assertIn("2026-09-21",bank["detail"])
                inspection.verify(p,read)
                verify_findings(p)

    def test_ambiguous_or_unlinked_lists_do_not_establish_a_substitution(self):
        for changes,extra,expected in (
                ({},[(1,"设备编号说明：其余编号另见附件")],"source"),
                ({},[(2,"QC-009")],"source"),
                ({},[(2,"实收设备编号：QC-002、QC-009")],"incomplete"),
                ({},[(1,"替代约定：经书面批准可改供同等设备")],"source"),
                ({(2,"contract_id"):"YL-122"},[],"scope"),
                ({(2,"acceptance_scope"):"到货初验"},[],"scope"),
                ({(2,"quantity_accepted"):"1台"},[],"incomplete")):
            p,_=example("QC-002、QC-009",extra=extra,edit=lambda i,k,l,v:changes.get((i,k),v))
            h,_,_=summary(p)
            self.assertEqual(h["inspection_coverage"]["state"],"register_"+expected)
            self.assertNotIn("contract_only",h["inspection_coverage"]["register"])
        p,_=example("QC-002、QC-001",edit=lambda i,k,l,v:"不合格" if k=="acceptance_result" else v)
        self.assertEqual(summary(p)[0]["status"],"issue")
        p,_=example("QC-002、QC-009",edit=lambda i,k,l,v:"交易失败" if k=="transfer_status" else v)
        self.assertNotIn("delivery_register",summary(p)[2])

    def test_disputed_or_unlocated_observations_do_not_become_equipment_identity(self):
        p,read=example("QC-002、QC-009")
        r=next(r for r in inspection.register_rows(p["graph"]) if r["kind"]=="population")
        f=next(f for f in p["graph"]["facts"] if f["id"]==r["facts"][0])
        p,_=example("QC-002、QC-009",attestations={f["id"]:{"decision":"dispute","note":"核对机身编号"}})
        self.assertEqual(summary(p)[0]["inspection_coverage"]["state"],"register_source")
        graph=p["graph"]
        next(n for n in graph["nodes"] if n["id"]=="d02/p1")["layer"]="image"
        ledger=inspection.sources(graph,read)
        self.assertTrue(any(r["kind"]=="population" and r["line"] is None for r in ledger["rows"]))
        graph["inspection_coverage_sources"]=ledger
        p["findings"]=execute(graph,PERFORMANCE)
        self.assertEqual(summary(p)[0]["inspection_coverage"]["state"],"register_source")

    def test_historical_approval_and_expert_input_are_bound_to_the_issued_rows(self):
        for actual,hold in (("QC-002、QC-001",False),("QC-002、QC-009",True)):
            p,read=example(actual)
            with patch("model.structured",return_value=({"followups":[]},{})):
                _,expert=audit_graph(p["graph"],p["findings"])
            p["calls"]={"expert":expert}
            inspection.verify(p,read)
            changed=json.loads(json.dumps(p))
            changed["calls"]["expert"]["input"]["delivery_register_sources"][0]["quote"]="改写原行"
            with self.assertRaisesRegex(ValueError,"专家输入"):
                inspection.verify(changed,read)
            changed=json.loads(json.dumps(p))
            next(f for f in changed["findings"] if f["rule"]=="H05").pop("delivery_register")
            with self.assertRaises(ValueError):
                verify_findings(changed)
            g=p["graph"]
            old=inspection.sources(g,read,version=inspection.NAMED_FORMAT)
            self.assertEqual(old["rows"],[])
            g["inspection_coverage_sources"]=old
            g["nodes"]=[n for n in g["nodes"] if n["type"]!="inspection_line"]
            g["edges"]=[e for e in g["edges"] if e["type"]!="inspection_coverage_source"]
            p["policy"].update(version="2026.11.28.15",inspection_coverage=inspection.NAMED_FORMAT)
            p["findings"]=execute(g,PERFORMANCE)
            self.assertEqual(summary(p)[2]["status"],"ok")
            inspection.verify(p,read)
            if hold:
                with self.assertRaisesRegex(ValueError,"重审"):
                    inspection.verify(p,read,signing=True)
            else:
                inspection.verify(p,read,signing=True)
