import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model import MAX_ARRAY_ITEMS, attach_check
from quality_references import FORMAT, marked_fields, qualified_field, verify_report
from reinspection import verify_number_links
from test_performance import rows
from test_reinspection import graph


NOTE = "缺陷编号展示说明：本单仅列尾号"


class QualityReferenceTests(unittest.TestCase):
    def test_matching_partial_numbers_do_not_release_acceptance_or_final_payment(self):
        for value in ("尾号0042", "QX-12XX0042", "12＊＊0042", "仅显示末四位0042"):
            with self.subTest(value=value):
                result = graph(lambda _, field, label, old: value if field=="defect_number" else old)
                acceptance, = rows(result, "H02")
                self.assertEqual((acceptance["status"], acceptance["reinspection"]["state"]), ("issue", "open"))
                self.assertEqual(rows(result, "H04")[1]["status"], "risk")
                self.assertEqual(rows(result, "H05")[0]["status"], "missing")
                holds = result["quality_references"]["holds"]
                self.assertEqual(len(holds), 3)
                for item in holds:
                    self.assertIn(item["fact"], acceptance["evidence"])
                    self.assertTrue(any(e["type"]=="incomplete_defect_number" and e["to"]==item["fact"]
                                        for e in result["edges"]))
                self.assertFalse(any(e["type"]=="defect_number" for e in result["edges"]))
                verify_number_links(result)
                edited = copy.deepcopy(result)
                edge = next(e for e in edited["edges"] if e["type"]=="incomplete_defect_number")
                edge["type"] = "defect_number"
                with self.assertRaises(ValueError):
                    verify_number_links(edited)

    def test_note_applies_to_its_field_on_its_own_page_and_retains_short_complete_ids(self):
        def short(_, field, label, old):
            return "0042" if field=="defect_number" else old
        self.assertIsNone(qualified_field("缺陷编号：0042，收款账号仅列尾号"))
        for note in ("收款账号展示说明：仅列尾号", "缺陷编号展示说明：本单完整展示"):
            complete = graph(short, omissions=[(4, note)])
            self.assertEqual(complete["quality_references"]["holds"], [])
            self.assertEqual(rows(complete, "H02")[0]["reinspection"]["state"], "closed")
        result = graph(short, omissions=[(4, NOTE)])
        hold, = result["quality_references"]["holds"]
        self.assertEqual((hold["unit"], hold["field"], hold["value"], hold["lines"][0]["quote"]),
                         ("d04", "defect_number", "0042", NOTE))
        final = rows(result, "H02")[0]["reinspection"]["steps"][-1]
        self.assertIn("d04/p1", final["evidence"])
        self.assertIn(hold["fact"], final["evidence"])

    def test_signed_legacy_closure_and_offline_note_integrity(self):
        text = "缺陷编号：0042\n" + NOTE
        page = {"id":"d01/p1","type":"page","layer":"text","text_sha256":hashlib.sha256(text.encode()).hexdigest()}
        number = {"id":"d01/p1/f1","field":"defect_number","doc":"d01","page":1,"value":"0042",
                  "quote":"缺陷编号：0042","status":"confirmed"}
        source = {"facts":[number], "nodes":[page]}
        read = lambda *_: text
        result = {"policy": {}, "graph": source, "findings":[{"reinspection":{"state":"closed"}, "evidence":[number["id"]]}]}
        verify_report(result, read)
        with self.assertRaisesRegex(ValueError, "重审"):
            verify_report(result, read, signing=True)
        result["policy"]["quality_references"] = FORMAT
        source["quality_references"] = {"format":FORMAT, "holds":marked_fields(source, read)}
        verify_report(result, read)
        with self.assertRaisesRegex(ValueError, "摘要"):
            verify_report(result, lambda *_: text.replace("尾号","全号"))
        source["quality_references"]["holds"].clear()
        with self.assertRaisesRegex(ValueError, "原文"):
            verify_report(result, read)
        page["layer"] = "image"
        source["facts"].append({**number, "id":"d01/p1/f2", "field":"other", "value":NOTE, "quote":NOTE, "status":"visual"})
        hold, = marked_fields(source, lambda *_: self.fail("扫描页不应读取原生文字层"))
        self.assertEqual(hold["lines"], [])
        self.assertEqual(hold["observations"], [{"fact":"d01/p1/f2","quote":NOTE}])

    def test_additional_label_checks_do_not_displace_original_fields_on_dense_pages(self):
        raw = {"field":"other","value":"测试","quote":"测试","region":"middle"}
        extras = [{"index":key,"field":"整改记录编号","value":"ZG-01","quote":"整改记录编号：ZG-01"} for key in ("t2","q14","q21")]
        def reply(model, instruction, content, schema, name):
            choices = schema["properties"]["checks"]["items"]["properties"]["index"]["enum"]
            output = {"checks":[{"index":key,"support":"clear"} for key in choices]}
            return output, {"output":output}
        with tempfile.TemporaryDirectory() as temp, patch("model.structured", side_effect=reply):
            page = Path(temp) / "水印测试.jpg"
            page.write_bytes(b"controlled fixture")
            for count in (MAX_ARRAY_ITEMS-2, MAX_ARRAY_ITEMS-1, MAX_ARRAY_ITEMS):
                trace = {"output":{"facts":[raw]*count}, "native_candidates":extras}
                attach_check(page, trace)
                keys = [row["index"] for row in trace["check"]["input"]]
                self.assertEqual(keys, [str(i) for i in range(1,count+1)]+[e["index"] for e in extras[:MAX_ARRAY_ITEMS-count]])
