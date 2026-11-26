import copy
import unittest

import inspection_coverage as inspection
from config import PERFORMANCE
from controls import VERSION, execute
from delivery_batches import evidence_edges
from performance import compute, verify_findings
from test_batch_final import packet
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


EQUIPMENT = ["QC-01", "QC-02", "QC-03", "QC-04"]
ALL = "全部交付设备逐台测温"
SAMPLE = "至少抽检2台测温"


def fixture(requirement=ALL, declared=4, observations=None, devices=EQUIPMENT, *, extra=(), edit=None, **kwargs):
    contract = [*CONTRACT, ("inspection_requirement", "性能检测要求", requirement)]
    receipt = [*RECEIPT, ("delivered_serials", "验收设备编号", "、".join(devices))]
    if declared is not None:
        receipt.append(("tested_quantity", "性能实测数量", f"{declared}台"))
    readings = [(s, "3") for s in EQUIPMENT] if observations is None else observations
    receipt.extend(("unit_temperature", "单机测温", f"{code}，柜温{value}℃") for code, value in readings)
    groups = [contract, receipt, WARRANTY, BANK_DOC, *extra]
    def read_text(doc, page):
        number = int(doc[1:])
        lines = []
        for field, label, value in groups[number-1]:
            value = edit(number, field, label, value) if edit else value
            if value is not None:
                lines.append(label + "：" + value if label else value)
        lines.extend(s for n, s in kwargs.get("omissions", ()) if n == number)
        return "\n".join(lines)
    return material(groups, edit, **kwargs), read_text


def findings(graph):
    items = compute(graph)
    accepted = next(f for f in items if f["rule"] == "H02")
    return accepted, [f["status"] for f in items if f["rule"] == "H04"], items[-1]


class InspectionCoverageTests(unittest.TestCase):
    def test_named_devices_follow_the_contract_and_actual_instalment(self):
        for ids,readings,state,missing in (
            ("QC-02、QC-03",[("QC-01","3"),("QC-03","2.5")],"named_records",["QC-02"]),
            ("QC-02、QC-03",[("QC-02","3"),("QC-03","2.5")],"covered",[]),
            ("QC-02、QC-03",[("QC-01","3"),("QC-03","8")],"out_of_limit",["QC-02"]),
            ("QC-02、QC-03",[("QC-02","3"),("QC-02","3")],"repeated",["QC-03"]),
            ("QC-02、QC-03、QC-04",[("QC-02","3"),("QC-03","3")],"named_records",["QC-04"]),
        ):
            with self.subTest(state=state,ids=ids):
                graph,read = fixture(SAMPLE,2,readings,omissions=[(1,"必检设备编号："+ids)])
                accepted,phases,payment = findings(graph)
                check = accepted["inspection_coverage"]
                self.assertEqual((check["state"],check["named"]["missing"]),(state,missing))
                row = next(r for r in graph["inspection_coverage_sources"]["rows"] if r["id"]==check["named"]["row"])
                self.assertEqual((row["facts"],read(row["doc"],row["page"]).splitlines()[row["line"]-1]),([],"必检设备编号："+ids))
                self.assertEqual(phases[0],"ok")
                self.assertEqual(phases[1]=="ok",state=="covered")
                self.assertEqual(payment["status"]=="ok",state=="covered")
                self.assertIn(row["id"],accepted["evidence"])
                self.assertIn(row["id"],payment["evidence"])
                prepay = next(f for f in compute(graph) if f["rule"]=="H04")
                self.assertNotIn(row["id"],prepay["evidence"])

    def test_unresolved_named_scope_retains_original_lines(self):
        for additions,state in (
            ([(1,"必检设备编号：QC-02、QC-02")],"named_scope"),
            ([(1,"必检设备编号：qc-02")],"named_scope"),
            ([(1,"指定抽检设备编号：QC-0X")],"named_scope"),
            ([(1,"必检设备编号：QC-01或QC-03")],"named_scope"),
            ([(1,"必检设备编号：QC-01"),(1,"必检设备编号：QC-03")],"named_scope"),
            ([(1,"必检设备编号：QC-01"),(1,"QC-03")],"terms"),
            ([(1,"设备指定：其中QC-03为必测设备")],"terms"),
            ([(1,"备注：建议必检设备编号为QC-03")],"terms"),
            ([(2,"必检设备编号：QC-03")],"terms"),
            ([(1,"合同设备编号：QC-01、QC-02、QC-03、QC-05"),(1,"必检设备编号：QC-03")],"population"),
        ):
            with self.subTest(additions=additions):
                graph,_=fixture(SAMPLE,2,[("QC-01","3"),("QC-03","3")],omissions=additions)
                check=findings(graph)[0]["inspection_coverage"]
                self.assertEqual((check["state"],check["status"]),(state,"missing"))
                self.assertNotIn("named",check)
                rows=graph["inspection_coverage_sources"]["rows"]
                for _,line in additions:
                    self.assertTrue(any(r["quote"]==line and r["id"] in check["evidence"] for r in rows))

    def test_v1_signed_workpapers_keep_their_original_device_rules(self):
        for named,affected in (("QC-02、QC-03",True),("QC-01、QC-03",False)):
            graph,read = fixture(SAMPLE,2,[("QC-01","3"),("QC-03","3")],omissions=[(1,"必检设备编号："+named)])
            old = inspection.sources(graph,read,version=inspection.LEGACY)
            graph["inspection_coverage_sources"]=old
            nodes,edges=inspection.source_graph(old)
            graph["nodes"]=[n for n in graph["nodes"] if n["type"]!="inspection_line"]+nodes
            graph["edges"]=[e for e in graph["edges"] if e["type"]!="inspection_coverage_source"]+edges
            report={"graph":graph,"policy":{**VERSION,"profile":PERFORMANCE,"version":"2026.11.26.18","inspection_coverage":inspection.LEGACY},
                    "findings":execute(graph,PERFORMANCE)}
            inspection.verify(report,read)
            self.assertEqual(findings(graph)[0]["inspection_coverage"]["state"],"covered")
            if affected:
                with self.assertRaisesRegex(ValueError,"重新审计"):
                    inspection.verify(report,read,signing=True)
                report["findings"]=[f for f in report["findings"] if f.get("stage",{}).get("name")=="第一期"]
            inspection.verify(report,read,signing=True)
            report["policy"]["version"]=inspection.NAMED_SINCE
            with self.assertRaisesRegex(ValueError,"版本"):
                inspection.verify(report,read)

    def test_coverage_and_independent_installments(self):
        for requirement, declared, readings, state, expected in (
            (ALL, 1, [("QC-01","3")], "short", "risk"),
            (ALL, 4, None, "covered", "ok"),
            (SAMPLE, 2, [("QC-01","3"),("QC-03","4")], "covered", "ok"),
            (SAMPLE, 2, [("QC-01","3"),("QC-01","2.5")], "repeated", "risk"),
            (ALL, 4, [(s,"8" if s=="QC-04" else "3") for s in EQUIPMENT], "out_of_limit", "issue"),
            (ALL, 4, [], "records", "missing"),
            ("按到货情况抽检测温", 2, [("QC-01","3"),("QC-03","2")], "terms", "missing"),
            (ALL, 1, None, "count_conflict", "risk"),
            (ALL, None, None, "covered", "ok"),
            (ALL, 0, [], "short", "risk"),
        ):
            with self.subTest(state=state, declared=declared):
                graph, _ = fixture(requirement, declared, readings)
                accepted, phases, payment = findings(graph)
                proof = accepted["inspection_coverage"]
                self.assertEqual((proof["state"], proof["status"], accepted["status"]), (state, expected, expected))
                self.assertEqual(phases, ["ok"] + [("risk" if expected=="issue" else expected)]*2)
                self.assertEqual(payment["status"], "ok" if expected=="ok" else "missing")
                if proof["tested"] is not None:
                    self.assertEqual(proof["tested"], len({m["serial"] for m in proof["measurements"]}))
                self.assertTrue(set(proof["evidence"]).issubset(accepted["evidence"]))

    def test_scope_identity_and_limit_uncertainty(self):
        for changes, edit, state in (
            ({"observations":[("QC-05","3")]}, None, "identity"),
            ({"devices":["QC-01","QC-02","QC-03","QC-XX"]}, None, "population"),
            ({"observations":[("QC- 01","3")]}, None, "reading"),
            ({"omissions":[(1,"附注：按比例抽检")]}, None, "terms"),
            ({"omissions":[(1,"约定设备编号：QC-01、QC-02、QC-03、QC-05")]}, None, "population"),
            ({"omissions":[(2,"性能实测数量：3台")]}, None, "count"),
            ({}, lambda i,k,l,v:"柜温不低于4℃" if k=="inspection_basis" else v, "criterion"),
            ({}, lambda i,k,l,v:"演练丙" if i==2 and k=="seller" else v, "identity"),
        ):
            with self.subTest(state=state):
                graph, _ = fixture(**changes, edit=edit)
                accepted, phases, _ = findings(graph)
                self.assertEqual(accepted["inspection_coverage"]["state"], state)
                self.assertNotIn("ok", phases[1:])

    def test_original_row_survives_model_omission_and_round_trip(self):
        graph, read_text = fixture(declared=4, observations=[(s,"3") for s in EQUIPMENT[:3]],
                                   omissions=[(2,"单机测温：QC-04，柜温8℃")])
        report = {"graph":graph, "policy":{**VERSION, "profile":PERFORMANCE}, "findings":execute(graph, PERFORMANCE)}
        inspection.verify(report, read_text)
        verify_findings(report)
        proof = next(f["inspection_coverage"] for f in report["findings"] if "inspection_coverage" in f)
        last = proof["measurements"][-1]
        source = next(r for r in graph["inspection_coverage_sources"]["rows"] if r["id"] == last["row"])
        self.assertEqual((proof["state"],source["doc"],source["facts"]), ("out_of_limit","d02",[]))
        self.assertEqual(read_text("d02",1).splitlines()[source["line"]-1], source["quote"])
        for corrupt in ("text","ledger","edge","node","proof","marker"):
            bad = copy.deepcopy(report)
            ledger = bad["graph"]["inspection_coverage_sources"]
            reader = read_text
            if corrupt=="text":
                reader=lambda d,p:read_text(d,p)+" "
            elif corrupt=="ledger":
                ledger["rows"][-1]["quote"]="单机测温：QC-04，柜温3℃"
            elif corrupt=="edge":
                bad["graph"]["edges"] = [e for e in bad["graph"]["edges"] if e["to"]!=last["row"]]
            elif corrupt=="node":
                bad["graph"]["nodes"] = [n for n in bad["graph"]["nodes"] if n["id"]!=last["row"]]
            elif corrupt=="marker":
                bad["policy"].pop("inspection_coverage")
            else:
                next(f for f in bad["findings"] if "inspection_coverage" in f)["inspection_coverage"]["tested"]=1
            with self.subTest(corrupt=corrupt), self.assertRaises(ValueError):
                inspection.verify(bad, reader)
                verify_findings(bad)

    def test_other_documents_and_unresolved_retests_do_not_become_test_evidence(self):
        graph = packet(omissions=[(1, "性能检测要求："+ALL)])
        accepted, phases, _ = findings(graph)
        self.assertEqual(accepted["inspection_coverage"]["state"], "scope")
        batch = accepted["batch_acceptance"]
        self.assertIsNone(batch["completion_on"])
        self.assertNotEqual(batch["separate_final"]["status"], "ok")
        self.assertTrue(all(b["status"]!="ok" and not b["date"] for b in batch["batches"]))
        self.assertFalse(any(e["type"] in ("batch_final_basis","batch_payment_basis") for e in evidence_edges(compute(graph))))
        ordinary = material([CONTRACT, RECEIPT, WARRANTY, BANK_DOC])
        self.assertEqual(ordinary["inspection_coverage_sources"]["rows"], [])
        self.assertNotIn("inspection_coverage", findings(ordinary)[0])

    def test_disputed_reading_and_image_page_need_original_review(self):
        graph, _ = fixture()
        raw = next(f for f in graph["facts"] if f["field"]=="unit_temperature")
        disputed, _ = fixture(attestations={raw["id"]:{"decision":"dispute"}})
        check = findings(disputed)[0]["inspection_coverage"]
        self.assertEqual((check["state"],check["tested"]), ("source",None))
        extra_page = dict(doc="d02",number=2,sha256="picture",text="",layer={"type":"image","lines":{}},
                          extraction={"output":{"quality":"readable","facts":[]}})
        mixed, _ = fixture(extra_pages=[extra_page])
        self.assertEqual(findings(mixed)[0]["inspection_coverage"]["state"], "scope")
        graph["inspection_coverage_sources"]["pages"][1]["text_only"] = False
        self.assertEqual(findings(graph)[0]["inspection_coverage"]["state"], "source")

    def test_historical_replay_and_approval_scope(self):
        graph, read_text = fixture(declared=1, observations=[("QC-01","3")])
        graph.pop("inspection_coverage_sources")
        graph["nodes"] = [n for n in graph["nodes"] if n["type"]!="inspection_line"]
        graph["edges"] = [e for e in graph["edges"] if e["type"]!="inspection_coverage_source"]
        policy = {**VERSION, "profile":PERFORMANCE, "version":"2026.11.26.03"}
        del policy["inspection_coverage"]
        report={"graph":graph, "policy":policy, "findings":execute(graph,PERFORMANCE)}
        inspection.verify(report,read_text)
        with self.assertRaisesRegex(ValueError,"旧版"):
            inspection.verify(report,read_text,signing=True)
        # A prepayment predicated only on effectiveness remains independent of acceptance.
        for f in report["findings"]:
            if f["rule"] in ("H02","H04","H05") and f.get("stage",{}).get("name")!="第一期":
                f["status"]="missing"
        inspection.verify(report,read_text,signing=True)
