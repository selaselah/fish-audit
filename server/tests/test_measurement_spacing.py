import json
import unittest
from copy import deepcopy
from unittest.mock import patch

import measurement_spacing as spacing
from config import PERFORMANCE
from controls import execute
from model import audit_graph
from performance import verify_findings
from test_payment_quality import example


class MeasurementSpacingTests(unittest.TestCase):
    def test_only_a_break_inside_one_numeric_measurement_is_held(self):
        for raw in ("柜温1 2℃", "柜温－ ４℃", "柜温7 . 50℃", "柜温７．　９℃", "柜温1\u00a02℃"):
            self.assertTrue(spacing.ambiguous("measured_result",raw),raw)
        for raw in ("柜温 7.50 ℃", "柜温 -4 ℃", "柜温12℃", "备注：第1 2号设备", "柜温1℃至2℃", "检测费用 1 2 元"):
            self.assertFalse(spacing.ambiguous("measured_result",raw),raw)
        self.assertTrue(spacing.ambiguous("inspection_basis","检验依据：柜温≤1 8℃"))

    def test_acceptance_and_only_its_dependent_payments_retain_the_original(self):
        for standard,basis,reading,key in (("柜温不高于8℃","柜温不高于8℃","柜温1 2℃","measured_result"),
                                            ("柜温不高于1 8℃","柜温不高于18℃","柜温12℃","acceptance_criteria"),
                                            ("柜温不高于8℃","柜温不高于7 . 9℃","柜温8℃","inspection_basis")):
            p,read=example(standard=standard,measure=reading,changes={(2,"inspection_basis"):basis})
            p["policy"]["measurement_numbers"]=spacing.FORMAT
            graph=p["graph"]
            row,=graph[spacing.KEY]["rows"]
            self.assertEqual((row["field"],row["origin"],read(row["doc"],1).splitlines()[row["line"]-1]),(key,"original",row["quote"]))
            linked=[f for f in p["findings"] if f.get("measurement_numbers")]
            self.assertEqual([(f["rule"],f.get("stage",{}).get("name")) for f in linked],
                             [("H02",None),("H04","第二期"),("H04","第三期"),("H05","第二期")])
            for f in linked:
                self.assertEqual(f["measurement_numbers"],[row["id"]])
                self.assertIn(row["id"],f["evidence"])
                self.assertNotEqual(f["status"],"ok")
                self.assertIn(row["quote"],f["detail"])
                self.assertNotIn("实测值超出",f["detail"])
            self.assertIn("2026-09-21",linked[-1]["detail"])
            self.assertFalse(any("payment_quality" in f for f in linked))
            verify_findings(p);spacing.verify(p,read)
        p,_=example(standard="柜温不高于8℃",measure="柜温 7.50 ℃")
        self.assertNotIn(spacing.KEY,p["graph"])
        self.assertEqual(next(f for f in p["findings"] if f["rule"]=="H05")["status"],"ok")

    def test_an_omitted_reading_and_an_independent_rejection_survive(self):
        p,read=example(changes={(2,"measured_result"):None,(2,"acceptance_result"):"不合格"},
                       omissions=[(2,"实测结果：柜温1 2℃")])
        p["policy"]["measurement_numbers"]=spacing.FORMAT
        row,=p["graph"][spacing.KEY]["rows"]
        self.assertEqual(row["facts"],[])
        h02=next(f for f in p["findings"] if f["rule"]=="H02")
        self.assertEqual(h02["status"],"issue")
        self.assertIn("不合格",h02["detail"]);self.assertIn(row["id"],h02["evidence"])
        spacing.verify(p,read)

    def test_split_transcription_keeps_its_own_reading_and_only_available_coordinates(self):
        p, read = example(measure="柜温12℃")
        graph = p["graph"]
        fact = next(f for f in graph["facts"] if f["field"] == "measured_result")
        fact["value"] = "柜温1 2℃"
        row, = spacing.sources(graph, read)
        self.assertEqual((row["origin"], row["quote"], row["line"]),
                         ("transcription", fact["source_line"]["text"], fact["source_line"]["number"]))
        self.assertEqual(row["readings"], [{key: fact[key] for key in ("id", "value", "quote")}])
        self.assertIn("12℃", row["quote"])
        page = next(p for p in graph["payment_window_sources"]["pages"]
                    if (p["doc"], p["page"]) == (fact["doc"], fact["page"]))
        page["native"] = False
        fact.pop("source_line")
        scanned, = spacing.sources(graph, read)
        self.assertEqual((scanned["id"], scanned["line"], scanned["quote"]),
                         ("measurement-number/" + fact["id"], None, fact["quote"]))
        self.assertEqual(scanned["readings"], row["readings"])

    def test_expert_and_legacy_review_retain_the_distinction(self):
        p,read=example(standard="柜温不高于18℃",measure="柜温1 7℃")
        p["policy"]["measurement_numbers"]=spacing.FORMAT
        with patch("model.structured",return_value=({"followups":[]},{})):
            _,expert=audit_graph(p["graph"],p["findings"])
        p["calls"]={"expert":expert}
        row,=p["graph"][spacing.KEY]["rows"]
        self.assertEqual(expert["input"]["measurement_number_sources"],[row])
        spacing.verify(p,read)
        for fault in ("expert","node","quote","finding"):
            changed=json.loads(json.dumps(p))
            if fault=="expert":changed["calls"]["expert"]["input"]["measurement_number_sources"][0]["quote"]="柜温17℃"
            if fault=="node":next(n for n in changed["graph"]["nodes"] if n["id"]==row["id"])["line"]+=1
            if fault=="quote":changed["graph"][spacing.KEY]["rows"][0]["quote"]="柜温17℃"
            if fault=="finding":next(f for f in changed["findings"] if f["rule"]=="H05")["status"]="ok"
            with self.assertRaisesRegex(ValueError,"专家输入" if fault=="expert" else "验收数值"):
                spacing.verify(changed,read)
        old=deepcopy(p)
        old.pop("calls");g=old["graph"];g.pop(spacing.KEY)
        g["nodes"]=[n for n in g["nodes"] if n["type"]!="measurement_number_review"]
        g["edges"]=[e for e in g["edges"] if e["type"]!="measurement_number_source"]
        old["policy"].pop("measurement_numbers");old["policy"]["version"]="2026.11.28.14"
        old["findings"]=execute(g,PERFORMANCE)
        self.assertEqual(next(f for f in old["findings"] if f["rule"]=="H02")["status"],"ok")
        spacing.verify(old,read)
        with self.assertRaisesRegex(ValueError,"重审"):spacing.verify(old,read,signing=True)
