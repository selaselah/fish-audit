import json
import unittest
from unittest.mock import patch

import inspection_coverage as inspection
from config import PERFORMANCE
from controls import VERSION, execute
from model import audit_graph
from performance import verify_findings
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


def example(received, ordered="QC-001、QC-002", *, extra=(), edit=None, omitted=False, attestations=None):
    contract = ("other","约定设备序列号",ordered)
    receipt = ("delivered_serials","实收设备序列号",received)
    groups = [CONTRACT + [( "equipment_model","约定设备型号","YL-C4")],
              RECEIPT + [("equipment_model","实收设备型号","YL-C4")], WARRANTY, BANK_DOC]
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


class DeliveryRegisterTests(unittest.TestCase):
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
