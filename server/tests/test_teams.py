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
