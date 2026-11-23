import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from werkzeug.datastructures import MultiDict

from config import CaseError, TRAVEL
from controls import additional, conclusion, execute, money, parsed_date
from documents import prepare
from graph import build_graph
from jobs import Worker
from main import create_app
from model import attach_check, audit_graph, extract_page, validate
from storage import Store
from verify import verify, verify_request


def fact(field, value, quote=None):
    return {"field": field, "value": value, "quote": quote or value, "region": "top"}


def case_graph(edited=None, missing_line=None, no_text=False, packet=False, continuation=False, omit_titles=False):
    docs, pages = [], []
    for index, (kind, title) in enumerate([("contract", "设备采购合同"), ("invoice", "采购发票"), ("acceptance", "到货验收单")], 1):
        doc = f"d{index:02d}"
        fields = [fact(kind, title), fact("contract_id", "DEMO-015", "合同编号：DEMO-015"),
                  fact("buyer", "演练采购方", "采购方：演练采购方"), fact("seller", "演练供应方", "供应方：演练供应方"),
                  fact("subject", "档案柜", "采购标的：档案柜"), fact("currency", "人民币", "币种：人民币"),
                  fact("unit", "元", "金额单位：元"), fact("total", "113.00", "含税总额：113.00")]
        if kind == "contract":
            fields += [fact("payment_term", "验收后一次性全额结算", "结算条款：验收后一次性全额结算"),
                       fact("signed_on", "2026年10月1日", "签订日期：2026年10月1日")]
        elif kind == "invoice":
            fields += [fact("invoice_id", "YL-01", "发票号码：YL-01"), fact("issued_on", "2026-10-10", "开票日期：2026-10-10"),
                       fact("net", "100.00", "不含税合计：100.00"), fact("tax", "13.00", "税额合计：13.00")]
        else:
            fields += [fact("accepted_on", "2026/10/11", "验收日期：2026/10/11"), fact("acceptance_result", "合格", "验收结论：合格")]
        if edited:
            fields = [edited(kind, entry) for entry in fields]
        lines = [entry["quote"] for entry in fields]
        if omit_titles and kind != "contract":
            fields = [entry for entry in fields if entry["field"] != kind]
        if missing_line and kind == "contract":
            lines.append(missing_line)
        docs.append({"id": doc, "name": title, "sha256": doc})
        pages.append({"doc": doc, "number": 1, "sha256": doc+"pg", "text": "\n".join(lines),
                      "layer": {"type": "image_overlay" if no_text else "text",
                                "lines": {str(num): [[.1,.1,.8,.2]] for num in range(1, len(lines)+1)}},
                      "extraction": {"output": {"facts": fields, "quality": "readable"}}})
    if packet:
        docs = [{"id":"d01","name":"合成采购合订件.pdf","sha256":"packet"}]
        for number, page in enumerate(pages,1):
            page.update(doc="d01", number=number)
        if continuation:
            pages.append({"doc":"d01","number":4,"sha256":"opaque","text":"","layer":{"type":"image","lines":{}},
                          "extraction":{"output":{"facts":[],"quality":"partial"}}})
    return build_graph(docs, pages, {})


class ControlsTests(unittest.TestCase):
    def test_tied_sources_and_decimal_math(self):
        graph = case_graph()
        result = conclusion(execute(graph))
        self.assertEqual(result["verdict"], "pass")
        self.assertFalse(result["human_required"])
        self.assertTrue(result["signoff_required"])
        self.assertTrue(all(fact["source_line"]["rects"] for fact in graph["facts"]))
        mismatch = case_graph(lambda kind, entry: fact("tax", "13.01", "税额合计：13.01")
                              if entry["field"] == "tax" else entry)
        findings = execute(mismatch)
        self.assertEqual(conclusion(findings)["verdict"], "reject")
        self.assertIn("0.01", next(item for item in findings if item["rule"] == "M01")["detail"])

    def test_invented_truncated_or_misclassified_values_stay_unlinked(self):
        for invalid in [fact("total", "13", "含税总额：113.00"), fact("total", "113", "含税总额：113.00"),
                        fact("total", "113.00", "不含税合计：113.00"), fact("unit", "元", "金额单位：万元"),
                        fact("currency", "人民币", "币种：人民币或美元"), fact("buyer", "演练", "采购方：演练采购方")]:
            with self.subTest(invalid=invalid):
                graph = case_graph(lambda kind, entry: invalid if kind == "invoice" and entry["field"] == invalid["field"] else entry)
                self.assertNotEqual(conclusion(execute(graph))["verdict"], "pass")

    def test_conditions_and_omissions_block_pass(self):
        for line in ["含税总额：999.00", "本合同第二期预付款另按附表支付。", "补充协议另行约定付款条件。"]:
            with self.subTest(line=line):
                self.assertNotEqual(conclusion(execute(case_graph(missing_line=line)))["verdict"], "pass")
        graph = case_graph(lambda kind, entry: fact("payment_term", "不要求一次性全额付款", "结算条款：不要求一次性全额付款")
                           if entry["field"] == "payment_term" else entry)
        self.assertEqual(conclusion(execute(graph))["verdict"], "review")
        graph = case_graph(lambda kind, entry: fact("acceptance_result", "待整改", "验收结论：待整改")
                           if entry["field"] == "acceptance_result" else entry)
        self.assertEqual(next(row["status"] for row in execute(graph) if row["rule"] == "M02"), "missing")

    def test_bound_packet_pages_and_unassigned_continuation(self):
        graph = case_graph(packet=True)
        self.assertEqual(conclusion(execute(graph))["verdict"], "pass")
        self.assertEqual({row["source"] for row in graph["audit_documents"]}, {"d01"})
        self.assertEqual(graph["documents_by_kind"]["invoice"], ["unit/d01/p2"])
        self.assertEqual({f["unit"] for f in graph["facts"] if f["page"]==2}, {"unit/d01/p2"})
        indexed = Store.index_rows("sample", 1, {"graph":graph})
        self.assertEqual((indexed[0][2],indexed[0][4],indexed[0][-1]), ("d01",2,"invoice"))
        graph = case_graph(packet=True, continuation=True)
        self.assertEqual(conclusion(execute(graph))["verdict"], "review")
        self.assertTrue(any(gap["quality"]=="section_unresolved" and gap["page"]==4 for gap in graph["gaps"]))
        graph = case_graph(packet=True, omit_titles=True)
        self.assertEqual(len(graph["audit_documents"]), 3)
        self.assertEqual({gap["page"] for gap in graph["gaps"] if gap["quality"] == "uncovered_title"}, {2,3})
        self.assertFalse(graph["documents_by_kind"].get("invoice"))

    def test_scanned_text_and_bad_agent_refs(self):
        graph = case_graph(no_text=True)
        self.assertFalse(any(fact["status"] == "anchored" for fact in graph["facts"]))
        self.assertEqual(conclusion(execute(graph))["verdict"], "review")
        report = additional(graph, [{"procedure":"amendment","facts":["foreign/p2/f11"]}])
        self.assertEqual(report[0]["status"], "missing")
        self.assertEqual(report[0]["evidence"], [])

    def test_amount_units_and_dates(self):
        for value in ("1,00.13", "7.000", "NaN", "Infinity", "1e2", "12.0%"):
            self.assertIsNone(money(fact("total", value)))
        self.assertIsNone(money(fact("total", "1.00", "合计：1.00万元")))
        self.assertIsNone(parsed_date(fact("signed_on","2026-02-29")))
        self.assertIsNotNone(parsed_date(fact("signed_on","2024-02-29")))

    def test_travel_underclaim_and_unrelated_voucher(self):
        def travel(amount, linked_number):
            dates = [fact("trip_start", "2026-10-10", "出差开始日期：2026-10-10"),
                     fact("trip_end", "2026-10-12", "出差结束日期：2026-10-12")]
            shared = [fact("unit", "元","金额单位：元"), fact("currency", "人民币","币种：人民币"),
                      fact("traveler", "演练甲","出差人员：演练甲")]
            records = [[fact("claim","差旅报销单"), fact("claim_total",amount,"申请报销金额："+amount),
                        fact("claim_ref",linked_number,"随附发票号码："+linked_number), *dates, *shared],
                       [fact("invoice","住宿发票"), fact("invoice_id","YL-T1","发票号码：YL-T1"),
                        fact("service_on","2026-10-11","费用发生日期：2026-10-11"),
                        fact("total","100.00","含税总额：100.00"), *shared]]
            docs, pages = [], []
            for i, fields in enumerate(records):
                doc = f"d{i+1:02d}"
                docs.append({"name":fields[0]["value"],"id":doc,"sha256":"sample"})
                pages.append({"doc":doc,"number":1,"sha256":"page","text":"\n".join(f["quote"] for f in fields),
                              "layer":{"type":"text","lines":{str(j+1):[[0,0,.9,.1]] for j in range(len(fields))}},
                              "extraction":{"output":{"quality":"readable","facts":fields}}})
            return execute(build_graph(docs,pages,{}),TRAVEL)

        for amount, number, expected in [("50.00","YL-T1","risk"), ("100.00","YL-T1","ok"),
                                         ("120.01","YL-T1","issue"), ("120.01","YL-OTHER","missing")]:
            with self.subTest(amount=amount,number=number):
                row = next(r for r in travel(amount, number) if r["rule"] == "T03")
                self.assertEqual(row["status"], expected)

    def test_expert_subject_comparison_requires_shared_contract(self):
        def changed(kind, entry):
            return fact("subject","书柜","采购标的：书柜") if kind == "invoice" and entry["field"] == "subject" else entry

        graph = case_graph(changed)
        refs = [item["id"] for item in graph["facts"] if item["field"] == "subject" and item["doc"] != "d03"]
        request = [{"procedure":"subject_scope","facts":refs}]
        self.assertEqual(additional(graph, request)[0]["status"], "risk")
        for edge in graph["edges"]:
            if edge["from"] == "d02" and edge["type"] == "contract_id":
                edge["to"] = "other-contract"
        self.assertEqual(additional(graph, request)[0]["status"], "missing")

    def test_followup_options_and_field_citations(self):
        graph = case_graph(lambda kind, entry: fact("payment_term","分期付款","付款条款：分期付款")
                           if entry["field"] == "payment_term" else entry)
        change = {**graph["facts"][0], "id":"d01/p1/f31", "field":"adjustment",
                  "value":"价格变更", "quote":"补充协议载明价格变更"}
        graph["facts"].append(change)
        installments = next(fact for fact in graph["facts"] if fact["field"] == "payment_term")
        result = {"followups":[{"procedure":"installments","facts":[installments["id"]]},
                               {"procedure":"amendment","facts":[change["id"]]}]}

        def inspect_schema(model, instruction, content, schema, name):
            validate(result, schema)
            with self.assertRaises(ValueError):
                validate({"followups":[{"procedure":"installments","facts":[change["id"]]}]}, schema)
            return result, {"model":"fixture"}

        with patch("model.structured", inspect_schema):
            proposals, trace = audit_graph(graph, [])
        self.assertEqual(len(additional(graph, proposals)), 2)
        self.assertEqual(trace["input"]["eligible_citations"]["amendment"], [change["id"]])


class LocalFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.extract_calls = 0

        def extract(path):
            self.extract_calls += 1
            result = {"quality":"readable","facts":[fact("invoice", "采购发票")]}
            return result, {"model":"test-fixture", "output":result,
                            "check":{"model":"fixture","output":{"checks":[{"index":"1","support":"clear"}]}}}

        self.worker = Worker(self.store, extract, lambda graph, findings: ([], {"model":"test-fixture","output":{"followups":[]}}))
        self.app = create_app(self.store, self.worker)
        self.client = self.app.test_client()
        self.key = patch.dict("os.environ", {"OPENAI_API_KEY": "synthetic-test-only"})
        self.key.start()
        self.addCleanup(self.key.stop)
        sample = io.BytesIO()
        Image.new("RGB", (60,60), "white").save(sample, format="JPEG")
        self.photo = sample.getvalue()

    def submit(self, key="synthetic-idempotency-1234", title="合成测试"):
        return self.client.post("/api/cases", headers={"Idempotency-Key":key},
                                data=MultiDict([("title",title),("files",(io.BytesIO(self.photo), "合成照片.jpg"))]))

    def test_review_revisions_recovery_and_offline_export(self):
        response = self.submit()
        self.assertEqual(response.status_code, 202)
        case_id = response.json["id"]
        self.assertEqual(self.submit().json["id"], case_id)
        self.assertEqual(self.submit(title="另一份提交").status_code, 409)
        base = "/api/cases/" + case_id
        self.assertEqual(self.store.claim(), case_id)
        self.store.recover()
        self.assertEqual(self.store.claim(), case_id)
        self.worker.run(case_id)
        before = self.client.get(base + "/reports/1").json
        self.assertEqual(before["report"]["result"]["verdict"], "review")
        payload = {"rev":1, "reviewer":"合成审计员", "note":"测试核图", "decision":"confirm", "facts":["d01/p1/f1"]}
        self.assertEqual(self.client.post(base + "/attest", json={**payload,"facts":["d02/p1/f5"]}).status_code, 400)
        self.assertEqual(self.client.post(base + "/attest", json=payload).status_code, 202)
        self.worker.run(self.store.claim())
        self.assertEqual(self.extract_calls, 1)
        self.assertEqual(self.client.get(base + "/reports/1").json["sha256"], before["sha256"])
        method = self.client.get(base + "/reports/1/methods/controls.py")
        self.assertEqual(hashlib.sha256(method.data).hexdigest(), before["report"]["policy"]["code_sha256"]["controls.py"])
        self.assertEqual(self.client.get(base + "/reports/1/methods/unregistered.py").status_code, 404)
        self.assertEqual(self.client.get(base + "/reports/2").json["report"]["graph"]["facts"][0]["status"], "confirmed")
        decision = {**payload, "decision":"return", "rev":2}
        self.assertEqual(self.client.post(base + "/signoff", json={**decision, "rev":1}).status_code, 409)
        self.assertEqual(self.client.post(base + "/signoff", json=decision).status_code, 200)
        self.assertEqual(self.client.post(base + "/signoff", json=decision).status_code, 409)
        self.assertEqual(self.client.get(base).json["status"], "closed")
        archive = self.client.get(base + "/reports/2/bundle")
        with archive:
            self.assertEqual(verify(io.BytesIO(archive.data))[:2], (case_id,2))
        original = self.store.files / case_id / "d01" / "original.jpg"
        original.write_bytes(b"wrong source")
        self.assertEqual(self.client.get(base + "/reports/2/bundle").status_code, 409)

    def test_file_validation_and_scope(self):
        self.assertEqual(self.client.post("/api/cases", json={}).status_code, 415)
        self.assertEqual(self.client.post("/api/cases", headers={"Origin":"http://example.test"}).status_code, 403)
        self.assertEqual(self.client.get("/api/health", headers={"Host":"example.test"}).status_code, 400)
        self.assertEqual(self.client.get("/.env").status_code, 404)
        self.assertEqual(self.client.post("/api/cases", data={"title":"空","files":(io.BytesIO(b""),"empty.pdf")}).status_code,400)
        self.assertEqual(self.client.post("/api/cases", data={"title":"类型","files":(io.BytesIO(b"a"),"test.zip")}).status_code,415)
        source = self.root / "invalid.pdf"
        source.write_bytes(b"not a pdf")
        with self.assertRaises(CaseError):
            prepare(source, 2)
        self.assertFalse(list(self.store.files.iterdir()))

    def test_worker_restarts_between_extraction_and_visual_check(self):
        case_id = self.submit().json["id"]
        original_extract = self.worker.extract
        counts = {"check":0}

        def fresh_page(path):
            result, trace = original_extract(path)
            del trace["check"]
            return result, trace

        def interrupted_check(path, trace):
            counts["check"] += 1
            raise CaseError("合成的连接中断")

        def recovered_check(path, trace):
            counts["check"] += 1
            trace["check"] = {"model":"fixture", "output":{"checks":[{"index":"1","support":"clear"}]}}

        with patch("jobs.RECHECK_EVIDENCE", True):
            first = Worker(self.store, fresh_page, self.worker.audit, interrupted_check)
            with self.assertRaises(CaseError):
                first.run(self.store.claim())
            reopened = Store(self.root)
            reopened.recover()
            self.assertEqual(reopened.claim(), case_id)
            Worker(reopened, fresh_page, self.worker.audit, recovered_check).run(case_id)
        self.assertEqual(self.extract_calls, 1)
        self.assertEqual(counts["check"], 2)
        self.assertEqual(reopened.detail(case_id)["status"], "ready")

    def test_disputed_value_still_requires_literal_quote_to_confirm(self):
        def inconsistent(path):
            output = {"quality":"readable","facts":[fact("total","99.00","含税总额：12.00")]}
            return output, {"model":"fixture","output":output}

        self.worker.extract = inconsistent
        base = "/api/cases/" + self.submit().json["id"]
        with patch("jobs.RECHECK_EVIDENCE", False):
            self.worker.run(self.store.claim())
            payload = {"rev":1,"reviewer":"演练员","note":"所引数字不符","decision":"dispute","facts":["d01/p1/f1"]}
            self.assertEqual(self.client.post(base+"/attest",json=payload).status_code,202)
            self.worker.run(self.store.claim())
            self.assertEqual(self.client.post(base+"/attest",json={**payload,"rev":2,"decision":"confirm"}).status_code,422)

    def test_offline_reconstruction_of_all_request_types(self):
        source = self.root / "演练照片.jpg"
        source.write_bytes(self.photo)
        outputs = {"source_page":{"quality":"readable","facts":[fact("invoice","采购发票")]},
                   "page_check":{"checks":[{"index":"1","support":"clear"}]}, "audit_followups":{"followups":[]}}

        def response(request, timeout):
            body = json.loads(request.data)
            name = body["text"]["format"]["name"]
            message = {"type":"message","content":[{"type":"output_text","text":json.dumps(outputs[name])}]}
            stream = io.BytesIO(json.dumps({"status":"completed","output":[message],"model":"fixture"}).encode())
            stream.headers = {}
            return stream

        with patch("model.urlopen", response):
            _, page = extract_page(source)
            attach_check(source, page)
            _, expert = audit_graph(case_graph(), [])
        instructions = {call["prompt_sha256"]:call["instruction"] for call in (page,page["check"],expert)}
        verify_request(page, instructions, self.photo)
        verify_request(page["check"], instructions, self.photo)
        verify_request(expert, instructions)
        with self.assertRaises(ValueError):
            verify_request(page, instructions, self.photo + b"x")
        expert["input"]["entities"] = {}
        with self.assertRaises(ValueError):
            verify_request(expert, instructions)

    def test_amend_and_supplement_are_revisioned(self):
        case_id = self.submit().json["id"]
        self.worker.run(self.store.claim())
        base = "/api/cases/" + case_id
        first = self.client.get(base+"/reports/1").json
        edit = {"rev":1, "doc":"d01", "page":1, "target":"d01/p1/f1", "field":"invoice",
                "value":"采购发票", "quote":"演练采购发票", "region":"top", "reviewer":"演练审计员", "note":"测试原文更正"}
        self.assertEqual(self.client.post(base+"/amend", json={**edit, "value":"未引用的值"}).status_code,422)
        self.assertEqual(self.client.post(base+"/amend", json={**edit, "page":2}).status_code,400)
        self.assertEqual(self.client.post(base+"/amend", json=edit).status_code,202)
        self.worker.run(self.store.claim())
        revised = self.client.get(base+"/reports/2").json["report"]["graph"]["facts"][0]
        self.assertEqual(revised["quote"], "演练采购发票")
        self.assertEqual(revised["original_candidate"]["quote"], "采购发票")
        self.assertEqual(revised["status"], "confirmed")
        extra = {**edit, "rev":2, "target":None, "field":"invoice_id", "value":"YL-321", "quote":"发票号码：YL-321"}
        response = self.client.post(base+"/amend", json=extra)
        self.assertEqual(response.status_code, 202)
        ref = response.json["fact"]
        self.worker.run(self.store.claim())
        latest = self.client.get(base+"/reports/3").json["report"]["graph"]
        fact = next(item for item in latest["facts"] if item["id"] == ref)
        self.assertIsNone(fact["original_candidate"])
        self.assertTrue(any(edge["type"] == "invoice_id" and edge["evidence"] == [ref] for edge in latest["edges"]))
        self.assertEqual(self.client.get(base+"/reports/1").json["sha256"], first["sha256"])
        self.assertEqual(self.extract_calls, 1)
        signer = {"rev":3, "reviewer":"演练审计员", "note":"证据尚待补充", "decision":"return"}
        self.assertEqual(self.client.post(base+"/signoff", json=signer).status_code, 200)
        other = self.submit(key="synthetic-second-case-001", title="合成跨案测试").json["id"]
        self.worker.run(self.store.claim())
        another_edit = {**extra, "rev":1}
        another_base = "/api/cases/" + other
        self.assertEqual(self.client.post(another_base+"/amend", json=another_edit).status_code,202)
        self.worker.run(self.store.claim())
        title_confirm = {"rev":2,"reviewer":"演练审计员","decision":"confirm","note":"对照原图确认","facts":["d01/p1/f1"]}
        self.client.post(another_base+"/attest", json=title_confirm)
        self.worker.run(self.store.claim())
        cross = self.client.get(another_base+"/reports/3").json["report"]
        self.assertEqual(cross["graph"]["prior_invoices"][0]["case_id"], case_id)
        self.assertEqual(cross["graph"]["prior_invoices"][0]["decision"], "return")
        self.assertTrue(any(item["rule"] == "I02" and item["status"] == "risk" for item in cross["findings"]))
        with self.client.get(another_base+"/reports/3/bundle") as exported:
            self.assertEqual(verify(io.BytesIO(exported.data))[:2], (other,3))

    def test_older_text_endpoint(self):
        with patch.dict("os.environ", {"OLLAMA_MODEL":""}):
            reply = self.client.post("/api/reviews", json={"text":"文本兼容"})
            self.assertEqual(reply.json["mode"], "demo")
            self.assertEqual(self.client.post("/api/reviews", json={"text":"  "}).status_code,400)

    def test_multiframe_limit_and_ocr_overlay(self):
        image = Image.new("RGB", (96,128), "white")
        source = self.root / "pages.tiff"
        image.save(source, save_all=True, append_images=[image])
        with self.assertRaises(CaseError):
            prepare(source, 1)
        self.assertEqual(len(prepare(source,2)), 2)
        scan = self.root / "scan.pdf"
        image.save(scan, "PDF")
        result = prepare(scan, 3)
        self.assertEqual(result[0]["layer"]["type"], "image_overlay")
        self.assertEqual(result[0]["layer"]["lines"], {})


if __name__ == "__main__":
    unittest.main()
