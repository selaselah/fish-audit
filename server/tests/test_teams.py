import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from jobs import Worker
from main import create_app
from storage import Store


class EnterpriseFlow(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name))
        env = patch.dict(os.environ, {"AUDIT_ACCESS_MODE":"saas","AUDIT_PUBLIC_ORIGIN":"",
                                      "OPENAI_API_KEY":"synthetic-unit-test"})
        env.start()
        self.addCleanup(env.stop)
        def extract(path):
            facts = [{"field":field,"value":value,"quote":quote,"region":"top"} for field,value,quote in
                     (("invoice","采购发票","采购发票"),("invoice_id","DEMO-537","发票号码：DEMO-537"))]
            out = {"facts":facts,"quality":"readable"}
            return out, {"model":"fixture","output":out,"check":{"model":"fixture","output":{"checks":[
                {"index":"1","support":"clear"},{"index":"2","support":"clear"}]}}}
        self.worker = Worker(self.store,extract,lambda graph,findings:([],{"model":"fixture","output":{"followups":[]}}))
        self.app = create_app(self.store,self.worker)
        data = io.BytesIO()
        Image.new("RGB",(32,32),"white").save(data,"JPEG")
        self.source = data.getvalue()

    def register(self, login, **more):
        client = self.app.test_client()
        res = client.post("/api/auth/register",json={"login":login,"name":login,"password":"synthetic-password-17",
                                                     "workspace":"测试企业","invite":None,**more})
        self.assertEqual(res.status_code,201,res.json)
        return client, res.json["selected"], {"X-CSRF-Token":res.json["csrf"]}

    def submit(self, client,wid,headers):
        response = client.post("/api/w/"+wid+"/cases",headers={**headers,"Idempotency-Key":"constant-request-key"},
                               data={"title":"演练", "files":(io.BytesIO(self.source),"演练.jpg")})
        self.assertEqual(response.status_code,202,response.json)
        return response.json["id"]

    def test_membership_and_scoped_evidence(self):
        admin,a,ah = self.register("org-a")
        other,b,bh = self.register("org-b")
        self.assertEqual(admin.get("/api/cases").status_code,404)
        self.assertEqual(admin.get("/api/w/"+b+"/cases").status_code,404)
        self.assertEqual(self.app.test_client().get("/api/w/"+a+"/cases").status_code,401)
        self.assertEqual(admin.post("/api/workspaces/"+a+"/invites",json={"role":"employee"}).status_code,403)
        invite = admin.post("/api/workspaces/"+a+"/invites",headers=ah,json={"role":"employee"}).json
        employee,joined,eh = self.register("employee-a",invite=invite["token"])
        self.assertEqual(joined,a)
        self.assertEqual(other.post("/api/workspaces/join",headers=bh,json={"invite":invite["token"]}).status_code,410)
        administrator_case = self.submit(admin,a,ah)
        emp_case = self.submit(employee,a,eh)
        other_case = self.submit(other,b,bh)
        self.assertEqual(self.submit(employee,a,eh),emp_case)
        self.assertEqual(len({administrator_case,emp_case,other_case}),3)
        while cid := self.store.claim():
            self.worker.run(cid)
        self.assertEqual([r["id"] for r in employee.get("/api/w/"+a+"/cases").json["cases"]],[emp_case])
        for tail in ("","/reports/1","/reports/1/bundle","/documents/d01/original","/documents/d01/pages/1"):
            self.assertEqual(other.get("/api/w/"+b+"/cases/"+emp_case+tail).status_code,404)
        self.assertEqual(employee.get("/api/w/"+a+"/cases/"+administrator_case).status_code,404)
        self.assertEqual(employee.get("/api/w/"+a+"/cases/"+emp_case+"/reports/1").status_code,403)
        base="/api/w/"+a+"/cases/"+emp_case
        payload={"rev":1,"decision":"confirm","facts":["d01/p1/f1","d01/p1/f2"],"note":"核对演练原图","reviewer":"客户端姓名"}
        self.assertEqual(employee.post(base+"/attest",headers=eh,json=payload).status_code,403)
        self.assertEqual(admin.post(base+"/attest",headers=ah,json=payload).status_code,202)
        self.worker.run(self.store.claim())
        sig={"rev":2,"decision":"return","note":"合成资料缺件","reviewer":"客户端姓名"}
        self.assertEqual(admin.post(base+"/signoff",headers=ah,json=sig).status_code,200)
        result=self.store.detail(emp_case)["decisions"][0]
        self.assertEqual(result["reviewer"],"org-a")
        self.assertEqual(result["actor"],admin.get("/api/session").json["user"]["id"])
        from graph import entity_id
        key=entity_id("invoice_number","DEMO-537")
        self.assertEqual(self.store.prior_invoices(other_case,[key]),[])
        self.assertEqual(self.store.prior_invoices(administrator_case,[key])[0]["case_id"],emp_case)
        ledger = "/api/w/"+a+"/inbox"
        self.assertEqual(employee.get(ledger).json["counts"]["all"], 1)
        self.assertEqual(admin.get(ledger+"?status=closed").json["cases"][0]["id"], emp_case)
        self.assertEqual(other.get("/api/w/"+b+"/inbox").json["counts"]["closed"], 0)
        search = "/api/w/"+a+"/evidence"
        self.assertEqual(employee.get(search+"?q=DEMO").status_code, 403)
        self.assertEqual(other.get(search+"?q=DEMO").status_code, 404)
        hits = admin.get(search+"?q=DEMO-537").json["hits"]
        self.assertEqual([(r["case_id"], r["rev"]) for r in hits], [(emp_case,2)])
        self.assertEqual(other.get("/api/w/"+b+"/evidence?q=DEMO").json["hits"], [])
        self.assertEqual(self.store.summary(),[])

    def test_atomic_admission_and_accounted_requests(self):
        from concurrent.futures import ThreadPoolExecutor
        from capacity import job_scope, request_attempt, usage
        from config import CaseError
        admin,w,headers=self.register("quota-owner")
        _,other,_=self.register("quota-second")
        uid=admin.get("/api/session").json["user"]
        self.store.limits.update(active_cases=1, monthly_cases=1, monthly_requests=1)
        def submit(i):
            try:
                return self.store.create("case"+str(i), "合成", [], "key"+str(i), "payload", workspace=w, user=uid)
            except CaseError as error:
                return error.status
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(submit,[1,2]))
        self.assertIn(429,results)
        cid=next(r for r in results if r!=429)
        self.assertEqual(self.store.create("duplicate","合成",[],"key"+cid[-1],"payload",workspace=w,user=uid),cid)
        with job_scope(self.store,cid):
            with request_attempt("model","source_page") as received:
                received({"id":"synthetic-request","status":"completed","usage":{"input_tokens":15,"output_tokens":3}})
            with self.assertRaises(CaseError) as stop:
                with request_attempt("model","page_check"):
                    self.fail("额度耗尽后的请求不应发出")
            self.assertEqual(stop.exception.status,429)
        stats=admin.get("/api/workspaces/"+w+"/team").json["usage"]
        self.assertEqual((stats["requests"], stats["input_tokens"], stats["output_tokens"]),(1,15,3))
        self.assertEqual(usage(self.store,other)["requests"],0)

    def test_rotating_worker_and_restored_credentials(self):
        from backup import snapshot, restore
        from config import CaseError
        a,w,h=self.register("fair-a")
        b,v,k=self.register("fair-b")
        ua,ub=(client.get("/api/session").json["user"] for client in (a,b))
        self.store.create("a1","演练",[],"a1","a1",workspace=w,user=ua)
        self.store.create("a2","演练",[],"a2","a2",workspace=w,user=ua)
        self.assertEqual(self.store.claim(),"a1")
        self.store.create("b1","演练",[],"b1","b1",workspace=v,user=ub)
        self.assertEqual(self.store.claim(),"b1")
        original=self.submit(a,w,h)
        invite=a.post("/api/workspaces/"+w+"/invites",headers=h,json={"role":"employee"}).json
        with tempfile.TemporaryDirectory() as d:
            out, fresh=Path(d)/"copy",Path(d)/"restored"
            snapshot(self.store.root,out)
            restore(out,fresh)
            copy=Store(fresh)
            directory=create_app(copy,Worker(copy)).extensions["directory"]
            self.assertIsNone(directory.user(a.get_cookie("fish_session").value))
            with self.assertRaises(CaseError):
                directory.accept(ub["id"],invite["token"])
            self.assertEqual(directory.spaces(ua["id"])[0]["id"],w)
            self.assertEqual((fresh/"cases"/original/"d01"/"original.jpg").read_bytes(),self.source)
            with self.assertRaises(FileExistsError):
                restore(out,fresh)

    def test_revoke_and_logout(self):
        admin,w,headers=self.register("owner")
        url="/api/workspaces/"+w
        invite=admin.post(url+"/invites",headers=headers,json={"role":"auditor"}).json
        self.assertNotIn("token",admin.get(url+"/team").json["invites"][0])
        admin.post(url+"/invites/"+invite["id"]+"/cancel",headers=headers,json={})
        other,_,oh=self.register("second")
        self.assertEqual(other.post("/api/workspaces/join",headers=oh,json={"invite":invite["token"]}).status_code,410)
        fresh=admin.post(url+"/invites",headers=headers,json={"role":"auditor"}).json
        self.assertEqual(other.post("/api/workspaces/join",headers=oh,json={"invite":fresh["token"]}).status_code,200)
        aid=admin.get("/api/session").json["user"]["id"]
        bid=other.get("/api/session").json["user"]["id"]
        self.assertEqual(admin.post(url+"/members/"+aid,headers=headers,json={"role":"remove"}).status_code,409)
        self.assertEqual(admin.post(url+"/members/"+bid,headers=headers,json={"role":"remove"}).status_code,200)
        self.assertEqual(other.get("/api/w/"+w+"/cases").status_code,404)
        cookie=admin.get_cookie("fish_session").value
        self.assertEqual(admin.post("/api/auth/logout",headers=headers,json={}).status_code,200)
        admin.set_cookie("fish_session",cookie)
        self.assertEqual(admin.get("/api/w/"+w+"/cases").status_code,401)
