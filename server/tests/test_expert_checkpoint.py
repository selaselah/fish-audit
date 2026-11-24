import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from capacity import usage
from config import CaseError
from jobs import Worker
from main import create_app
from storage import Store, encode
from verify import verify


class ExpertCheckpointTests(unittest.TestCase):
    def setUp(self):
        area = tempfile.TemporaryDirectory()
        self.addCleanup(area.cleanup)
        self.root = Path(area.name)
        self.store = Store(self.root)
        env = patch.dict("os.environ",{"AUDIT_ACCESS_MODE":"saas","AUDIT_PUBLIC_ORIGIN":"","OPENAI_API_KEY":"synthetic-test"})
        env.start()
        self.addCleanup(env.stop)
        self.worker = Worker(self.store,self.extract)
        self.client = create_app(self.store,self.worker).test_client()
        registration = self.client.post("/api/auth/register",json={
            "login":"fixture-auditor","name":"演练审计员","password":"fixture-password-1234","workspace":"合成企业"}).json
        self.workspace = registration["selected"]
        self.base = "/api/w/"+self.workspace+"/cases"
        self.headers = {"X-CSRF-Token":registration["csrf"]}
        photo = io.BytesIO()
        Image.new("RGB",(36,36),"white").save(photo,format="JPEG")
        self.photo = photo.getvalue()
        self.requests = []
        self.response_status = "completed"
        self.identify_response = True
        remote = patch("model.urlopen",self.respond)
        remote.start()
        self.addCleanup(remote.stop)

    @staticmethod
    def extract(path):
        result = {"quality":"readable","facts":[]}
        return result,{"model":"fixture-page","output":result}

    def respond(self,request,timeout):
        self.requests.append(request.data)
        number = len(self.requests)
        body = json.loads(request.data)
        self.assertEqual(body["text"]["format"]["name"],"audit_followups")
        envelope = {"id":"resp-fixture-"+str(number),"model":body["model"],"status":self.response_status,
                    "usage":{"input_tokens":21,"output_tokens":6},
                    "output":[{"type":"message","content":[{"type":"output_text","text":'{"followups":[]}'}]}]}
        if not self.identify_response:
            del envelope["id"]
        response = io.BytesIO(json.dumps(envelope).encode())
        response.headers = {"x-request-id":"request-fixture-"+str(number)}
        return response

    def submit(self):
        upload = self.client.post(self.base,headers=self.headers,
                                  data={"title":"合成演练","files":(io.BytesIO(self.photo),"合成照片.jpg")})
        self.assertEqual(upload.status_code,202,upload.json)
        return upload.json["id"]

    def interrupt(self):
        cid = self.submit()
        with patch.object(self.store,"save_report",side_effect=RuntimeError("模拟提交底稿前退出")):
            with self.assertRaisesRegex(RuntimeError,"模拟提交"):
                self.worker.run(self.store.claim())
        return cid

    def resume(self):
        store = Store(self.root)
        store.recover()
        Worker(store,self.extract).run(store.claim())

    def test_recovery_reuses_only_this_revision_and_does_not_reserve_a_request(self):
        cid = self.interrupt()
        before = self.client.get(self.base+"/"+cid).json
        self.assertEqual((before["rev"],before["progress"],set(before["page_progress"]["expert"])),(0,96,{"target_rev","saved_at"}))
        self.assertEqual(before["page_progress"]["expert"]["target_rev"],1)
        with self.store.connect() as db:
            pending = json.loads(db.execute("SELECT content FROM expert_checkpoints WHERE case_id=?",(cid,)).fetchone()[0])["trace"]
        # The response was persisted before publication. Recover with the key absent and the request allowance exhausted.
        with patch.dict("os.environ",{"OPENAI_API_KEY":"","AUDIT_MONTHLY_REQUESTS":"1"}):
            self.resume()
        first = self.store.report(cid,1)
        trace = first["report"]["calls"]["expert"]
        self.assertEqual((trace["response_id"],trace["request_sha256"]),("resp-fixture-1",hashlib.sha256(self.requests[0]).hexdigest()))
        for key,value in pending.items():
            if key!="instruction":
                self.assertEqual(trace[key],value)
        self.assertEqual(first["report"]["calls"]["instructions"][trace["prompt_sha256"]],pending["instruction"])
        after = self.client.get(self.base+"/"+cid).json
        self.assertNotIn("expert",after["page_progress"])
        self.assertTrue(any("与已保存响应匹配" in row["message"] for row in after["events"]))
        self.assertEqual((usage(self.store,self.workspace)["requests"],len(self.requests)),(1,1))
        evidence = self.client.get(self.base+"/"+cid+"/reports/1/bundle")
        with evidence:
            self.assertEqual(verify(io.BytesIO(evidence.data),True)[:2],(cid,1))
        self.assertEqual(self.client.post(self.base+"/"+cid+"/rerun",json={"rev":1},headers=self.headers).status_code,202)
        self.worker.run(self.store.claim())
        self.assertEqual(len(self.requests),2)
        self.assertEqual(self.requests[0],self.requests[1])
        self.assertEqual(self.store.report(cid,2)["report"]["calls"]["expert"]["response_id"],"resp-fixture-2")
        self.assertEqual(self.store.report(cid,1)["sha256"],first["sha256"])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM expert_checkpoints").fetchone()[0],0)

    def test_changed_expert_input_requires_a_new_call(self):
        cid = self.interrupt()
        with patch("model.AUDIT","修改后的合成测试指令"):
            self.resume()
        self.assertEqual(len(self.requests),2)
        self.assertNotEqual(self.requests[0],self.requests[1])
        self.assertEqual(self.store.report(cid,1)["report"]["calls"]["expert"]["response_id"],"resp-fixture-2")
        self.assertTrue(any("输入不同" in e["message"] for e in self.store.detail(cid)["events"]))

    def test_newly_signed_invoice_changes_the_packet_on_recovery(self):
        def invoice(path):
            facts = [{"field":"invoice","value":"采购发票","quote":"采购发票","region":"top"},
                     {"field":"invoice_id","value":"YL-FP-RETRY","quote":"发票号码：YL-FP-RETRY","region":"top"}]
            page = {"quality":"readable","facts":facts}
            checks = [{"index":str(i),"support":"clear"} for i in (1,2)]
            return page,{"model":"fixture-page","output":page,"check":{"model":"fixture-check","output":{"checks":checks}}}
        worker = Worker(self.store,invoice)
        def confirmed_case():
            cid = self.submit()
            self.assertEqual(self.store.claim(),cid)
            worker.run(cid)
            choice = {"rev":1,"decision":"confirm","facts":["d01/p1/f1","d01/p1/f2"],"note":"已核合成照片与票号。"}
            self.assertEqual(self.client.post(self.base+"/"+cid+"/attest",json=choice,headers=self.headers).status_code,202)
            self.assertEqual(self.store.claim(),cid)
            return cid
        prior = confirmed_case()
        worker.run(prior)
        current = confirmed_case()
        with patch.object(self.store,"save_report",side_effect=RuntimeError("模拟中断")),self.assertRaises(RuntimeError):
            worker.run(current)
        original_request = self.requests[-1]
        decision = {"rev":2,"decision":"return","note":"退回演练资料核实其余凭证。"}
        self.assertEqual(self.client.post(self.base+"/"+prior+"/signoff",json=decision,headers=self.headers).status_code,200)
        self.resume()
        paper = self.store.report(current,2)["report"]
        self.assertEqual([row["case_id"] for row in paper["graph"]["prior_invoices"]],[prior])
        first_packet = json.loads(json.loads(original_request)["input"][0]["content"][0]["text"])
        last_packet = paper["calls"]["expert"]["input"]
        def status(packet):
            return next(item["status"] for item in packet["procedures"] if item["rule"]=="I02")
        self.assertEqual((status(first_packet),status(last_packet)),("ok","risk"))
        self.assertNotEqual(original_request,self.requests[-1])
        self.assertTrue(any("输入不同" in e["message"] for e in self.store.detail(current)["events"]))
        with self.client.get(self.base+"/"+current+"/reports/2/bundle") as bundle:
            self.assertEqual(verify(io.BytesIO(bundle.data),True)[:2],(current,2))

    def test_tampered_misbound_or_invalid_outputs_are_replaced(self):
        for issue in ("damaged","other-case","other-revision","altered-schema","invalid-output"):
            with self.subTest(issue=issue):
                start = len(self.requests)
                cid = self.interrupt()
                with self.store.connect(True) as db:
                    source,checksum = db.execute("SELECT content,sha256 FROM expert_checkpoints WHERE case_id=?",(cid,)).fetchone()
                    record = json.loads(source)
                    if issue=="damaged":
                        checksum = "0"*64
                    else:
                        if issue=="other-case": record["case_id"]="another-case"
                        if issue=="other-revision": record["base_rev"]=True
                        if issue=="altered-schema": record["trace"]["schema"]["additionalProperties"]=0
                        if issue=="invalid-output": record["trace"]["output"]={"missing":"followups"}
                        source = encode(record)
                        checksum = hashlib.sha256(source.encode()).hexdigest()
                    db.execute("UPDATE expert_checkpoints SET content=?,sha256=? WHERE case_id=?",(source,checksum,cid))
                self.resume()
                self.assertEqual(len(self.requests),start+2)
                self.assertEqual(self.store.report(cid,1)["report"]["calls"]["expert"]["response_id"],"resp-fixture-"+str(start+2))
                self.assertTrue(any("未通过完整性检查" in e["message"] for e in self.store.detail(cid)["events"]))

    def test_incomplete_response_and_changed_original(self):
        cid = self.submit()
        self.response_status = "incomplete"
        with self.assertRaisesRegex(CaseError,"不完整"):
            self.worker.run(self.store.claim())
        self.assertNotIn("expert",self.client.get(self.base+"/"+cid).json["page_progress"])
        self.response_status = "completed"
        self.resume()
        self.assertEqual(len(self.requests),2)
        cid = self.interrupt()
        original = self.store.files/cid/"d01"/"original.jpg"
        original.write_bytes(b"changed")
        with self.assertRaisesRegex(CaseError,"原件缺失或摘要"):
            self.resume()
        self.assertEqual(len(self.requests),3)
        original.write_bytes(self.photo)
        self.resume()
        self.assertEqual(len(self.requests),3)

    def test_unidentified_completed_response_requires_a_new_request(self):
        cid = self.submit()
        self.identify_response = False
        with self.assertRaisesRegex(CaseError,"缺少可核对的执行记录"):
            self.worker.run(self.store.claim())
        self.assertNotIn("expert",self.client.get(self.base+"/"+cid).json["page_progress"])
        self.identify_response = True
        self.resume()
        self.assertEqual(len(self.requests),2)
