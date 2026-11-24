import copy
import unittest

from graph import build_graph, heading_candidates
from quality_labels import FORMAT, NAMES, proposed, verify_report


DOC = {"id":"d01","name":"水印复验.pdf","sha256":"source"}
RAW = {"field":"remediation","quote":"整改记录编号：ZG-001","value":"ZG-001","region":"middle"}


def sample(raw=None,lines=None,layer="text",quality="readable",votes=("conflict","clear")):
    raw=raw or RAW
    lines=lines or ["复验报告",raw["quote"]]
    page={"doc":"d01","number":1,"sha256":"page","text":"\n".join(lines),
          "layer":{"type":layer,"lines":{str(n):[[0,.1,.9,.2]] for n in range(1,len(lines)+1)}},
          "extraction":{"output":{"quality":quality,"facts":[raw]}}}
    headings,numbers=heading_candidates(page),proposed(page)
    original={"index":"1","field":NAMES[raw["field"]],"quote":raw["quote"],"value":raw["value"]}
    inputs=[original,*headings,*numbers]
    page["extraction"]["check"]={"input":inputs,"response_id":"read2","output":{"checks":[
        {"index":item["index"],"support":votes[0] if item["index"]=="1" else votes[1] if item["index"]=="q1" else "clear"}
        for item in inputs]}}
    return page


def paper(page):
    graph=build_graph([DOC],[page],{})
    return {"policy":{"quality_number_classification":FORMAT,"code_sha256":{"quality_labels.py":"hash"}},
            "graph":graph,"calls":{"pages":[{"doc":"d01","page":1,**page["extraction"]}]}}


class QualityLabelsTests(unittest.TestCase):
    def test_competing_labels_and_omitted_heading_have_separate_image_votes(self):
        page=sample()
        result=paper(page)
        self.assertEqual(result["graph"]["documents_by_kind"],{"reinspection":["d01"]})
        fact=next(f for f in result["graph"]["facts"] if f["id"].endswith("/f1"))
        self.assertEqual((fact["field"],fact["model_field"],fact["value"],fact["status"]),
                         ("repair_number","remediation","ZG-001","anchored"))
        self.assertEqual(fact["classification_index"],"q1")
        self.assertEqual(result["graph"]["gaps"],[])
        verify_report(result,lambda *_:page["text"])

    def test_both_clear_ambiguous_or_incomplete_votes_withhold_reclassification(self):
        for votes in (("clear","clear"),("unreadable","clear"),("conflict","unreadable"),("conflict","conflict")):
            with self.subTest(votes=votes):
                result=paper(sample(votes=votes))
                self.assertFalse(any(f["field"]=="repair_number" for f in result["graph"]["facts"]))
                self.assertTrue(any(g.get("field")=="repair_number" for g in result["graph"]["gaps"]))
        for target in ("input","output"):
            page=sample()
            check=page["extraction"]["check"]
            rows=check["input"] if target=="input" else check["output"]["checks"]
            rows.append(copy.deepcopy(rows[-1]))
            self.assertFalse(any(f.get("origin")=="printed_quality_number" for f in paper(page)["graph"]["facts"]))

    def test_native_label_requires_one_printed_row_and_unchanged_complete_number(self):
        for page in (sample(layer="image"),sample(quality="partial"),sample(lines=["复验报告",RAW["quote"],RAW["quote"]]),
                     sample(lines=["复验报告",RAW["quote"],"整改单编号：ZG-002"]),sample(raw={**RAW,"value":"001"}),
                     sample(raw={**RAW,"value":"ZG-***1","quote":"整改记录编号：ZG-***1"})):
            self.assertEqual(proposed(page),[])
            self.assertFalse(any(f.get("origin")=="printed_quality_number" for f in paper(page)["graph"]["facts"]))

    def test_replay_checks_raw_field_image_votes_native_row_and_source_hash(self):
        page=sample()
        valid=paper(page)
        for change in ("raw","vote","input","digest","index","removed_origin","removed_method"):
            with self.subTest(change=change):
                r=copy.deepcopy(valid)
                f=next(f for f in r["graph"]["facts"] if f["id"].endswith("/f1"))
                trace=r["calls"]["pages"][0]
                if change=="raw": trace["output"]["facts"][0]["value"]="ZG-002"
                elif change=="vote": trace["check"]["output"]["checks"][-1]["support"]="conflict"
                elif change=="input": trace["check"]["input"][-1]["field"]="合同编号"
                elif change=="index": f["classification_index"]="q9"
                elif change=="removed_origin": del f["origin"]
                elif change=="removed_method": del r["policy"]["quality_number_classification"]
                text=page["text"] if change!="digest" else page["text"].replace("001","002")
                with self.assertRaises(ValueError):
                    verify_report(r,lambda *_:text)
