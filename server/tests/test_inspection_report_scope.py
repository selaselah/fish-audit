from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from documents import render
from inspection_report_scope import comparison
from inspection_reports import attachment, native_page
from test_inspection_reports import REASON, sheet, signed_copy


LINK = {"contract_id":"合同编号：HT-100", "buyer":"采购方：甲企业", "seller":"供应方：乙企业", "subject":"采购标的：四门冷藏柜"}


class ReportScopeTests(unittest.TestCase):
    def material(self, kind, doc, fields, *, signed=False, graphic=False, extra=()):
        raw = sheet(kind, *fields.values(), *extra, graphic=graphic)
        if signed:
            raw = signed_copy(raw, "QualityReview", reason=REASON)
        page = native_page(raw, report=True, basis=True)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "source.pdf"
            path.write_bytes(raw)
            render(path, path.parent, 1)
            manifest, = json.loads((path.parent / "manifest.json").read_text())
        digest = sha256(raw).hexdigest()
        node = {"id":doc+"/p1", "type":"page", "sha256":manifest["sha256"]}
        source = {"id":doc, "sha256":digest}
        facts = []
        for field, quote in fields.items():
            n = page[0].index(quote)+1
            facts.append({"id":f"{doc}/p1/f{n}", "doc":doc, "page":1, "field":field, "value":quote.split("：",1)[1],
                          "quote":quote, "source_sha256":digest, "page_sha256":node["sha256"], "status":"anchored",
                          "source_line":{"number":n,"text":quote,"rects":manifest["layer"]["lines"][str(n)]}})
        return (source,page), node, facts

    def evaluate(self, *, quantity="1台", scope="送检样机", metric="四门冷藏柜柜温", result="送检样机柜温符合约定值",
                 clause="全部交付设备逐台测温", accepted="4台", receipt_id="HT-100", contract_extra=(), report_extra=(),
                 graphic=False, mutate=None):
        terms = {**LINK, "quantity_agreed":"约定交付数量：4台"}
        if clause:
            terms["inspection_requirement"]="性能检测要求："+clause
        contract, cp, cf = self.material("采购合同","d01",terms,extra=contract_extra)
        receipt, ap, af = self.material("验收报告","d02",{**LINK, "contract_id":"合同编号："+receipt_id,
                                        "quantity_accepted":"实际验收数量："+accepted, "acceptance_scope":"验收范围：全部交付终验"},
                                        signed=True,graphic=graphic)
        fields = {"number":"报告编号：JC-2026-018","contract_id":"合同编号："+receipt_id,"metric":"检测项目："+metric}
        if scope:
            fields["scope"]="检测范围："+scope
        if quantity:
            fields["tested_quantity"]="实际测温台数："+quantity
        fields["conclusion"]="检测结论："+result
        (doc, report), rp, rf = self.material("检测报告","d05",fields,extra=report_extra)
        graph = {"facts":cf+af+rf, "nodes":[cp,ap,rp], "documents_by_kind":{"contract":["d01"],"acceptance":["d02"]}}
        if mutate:
            mutate(graph)
        linked = attachment(doc,rp,report)
        citation = {"state":"matched", "candidates":[linked], "signed_contract":{"fact":af[0]["id"]}}
        return comparison(graph, {"doc":"d02","role":"acceptance"}, citation, receipt, contract, report)

    def test_number_in_a_separately_referenced_report(self):
        c = self.evaluate()
        self.assertEqual([c[k] for k in ("state","received","reported","required","difference")], ["short",4,1,4,3])
        self.assertEqual(c["report_rows"]["count"]["quote"],"实际测温台数：1台")
        self.assertEqual(c["basis"]["clause"]["quote"],"性能检测要求：全部交付设备逐台测温")
        self.assertEqual(len(c["basis"]),12)
        c = self.evaluate(scope="本合同全部交付设备", quantity="4台", result="所检设备柜温符合约定值")
        self.assertEqual((c["state"],c["difference"]),("count_only",0))
        c = self.evaluate(clause="至少抽检2台测温")
        self.assertEqual((c["mode"],c["required"],c["difference"]),("minimum",2,1))
        c = self.evaluate(scope=None, quantity=None, clause=None)
        self.assertEqual((c["state"], c["received"], c["reported"],c["required"]),("sample",4,None,None))

    def test_ambiguous_fields_changes_and_conflicts_never_give_an_arithmetic_conclusion(self):
        def dispute(g):
            next(f for f in g["facts"] if f["doc"]=="d05" and f["field"]=="tested_quantity")["status"]="disputed"
        def moved(g):
            fact = next(f for f in g["facts"] if f["field"]=="quantity_agreed")
            fact["source_line"]=deepcopy(fact["source_line"])
            fact["source_line"]["rects"]=[[0.1,0.1,0.2,0.2]]
        examples = ({"accepted":"3台"}, {"receipt_id":"HT-101"}, {"metric":"冷库气温"}, {"quantity":"5台"},
                    {"quantity":"约1台"}, {"scope":"本合同全部交付设备"}, {"report_extra":["检测台数：2台"]},
                    {"contract_extra":["检测备注：其中一台免测"]}, {"report_extra":["台数按测次折算"]},
                    {"mutate":dispute}, {"mutate":moved}, {"mutate":lambda g:g["documents_by_kind"].update(contract_addendum=["d06"])})
        for args in examples:
            with self.subTest(args=args):
                c = self.evaluate(**args)
                self.assertNotIn(c["state"],("short","count_only"))
                self.assertIsNone(c["difference"])

    def test_drawings_on_the_signed_receipt_require_visual_review(self):
        c = self.evaluate(graphic=True)
        self.assertEqual((c["received"],c["reported"],c["required"],c["state"]),(None,1,None,"review"))
