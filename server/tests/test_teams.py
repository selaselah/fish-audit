import hashlib
import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from config import CaseError
from jobs import Worker
from main import create_app
from storage import Store
from verify import verify


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

    def test_rule_replay_is_scoped_to_the_selected_immutable_workpaper(self):
        owner,wid,headers=self.register("replay-owner")
        other,other_space,other_headers=self.register("replay-other")
        invite=owner.post("/api/workspaces/"+wid+"/invites",headers=headers,json={"role":"employee"}).json
        employee,_,member_headers=self.register("replay-employee",invite=invite["token"])
        cid=self.submit(employee,wid,member_headers)
        self.worker.run(self.store.claim())
        path=f"/api/w/{wid}/cases/{cid}/reports/1/replay"
        before=self.store.detail(cid)
        paper=self.store.report(cid,1)
        with patch("main.replay_from_git",return_value={"state":"verified","verdict":"review"}) as replay:
            self.assertEqual(employee.post(path,headers=member_headers,json={}).status_code,403)
            self.assertEqual(other.post(path.replace(wid,other_space),headers=other_headers,json={}).status_code,404)
            self.assertEqual(owner.post(path,json={}).status_code,403)
            self.assertEqual(owner.post(path,headers=headers,json={"ref":"another-version"}).status_code,400)
            self.assertEqual(owner.post(path.replace("/1/","/2/"),headers=headers,json={}).status_code,404)
            replay.assert_not_called()
            response=owner.post(path,headers=headers)
            self.assertEqual(response.status_code,200)
            result=response.json
            self.assertEqual((result["state"],result["case_id"],result["rev"],result["report_sha256"]),
                             ("verified",cid,1,paper["sha256"]))
            replay.assert_called_once_with(paper["report"])
        self.assertEqual(self.store.detail(cid),before)

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
        checkpoint = employee.get("/api/w/"+a+"/cases/"+emp_case).json["page_progress"]
        self.assertEqual(checkpoint["documents"],{"d01":[{"page":1,"state":"checked"}]})
        self.assertEqual(employee.get("/api/w/"+a+"/cases/"+emp_case+"/documents/d01/pages/1?rev=1").status_code,403)
        for tail in ("","/reports/1","/reports/1/bundle","/documents/d01/original","/documents/d01/pages/1"):
            self.assertEqual(other.get("/api/w/"+b+"/cases/"+emp_case+tail).status_code,404)
        self.assertEqual(employee.get("/api/w/"+a+"/cases/"+administrator_case).status_code,404)
        self.assertEqual(employee.get("/api/w/"+a+"/cases/"+emp_case+"/reports/1").status_code,403)
        source_link = "/w/"+a+"/workpaper/"+emp_case+"?rev=1&fact=d01%2Fp1%2Ff1"
        self.assertEqual(admin.get(source_link).headers["Location"],"/#w/"+a+"/case/"+emp_case+"?rev=1&fact=d01%2Fp1%2Ff1")
        self.assertEqual(admin.get("/workpaper/"+emp_case).status_code,404)
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
        matched = self.store.prior_invoices(administrator_case,[key])[0]
        self.assertEqual((matched["case_id"],matched["checked_field"]),(emp_case,True))
        self.assertRegex(matched["signoff_hash"],r"^[0-9a-f]{64}$")
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

    def test_returned_tasks_respect_employee_ownership_and_workspace(self):
        admin,a,ah = self.register("return-admin")
        other,b,bh = self.register("other-return-admin")
        def employee(login):
            token = admin.post("/api/workspaces/"+a+"/invites",headers=ah,json={"role":"employee"}).json["token"]
            return self.register(login,invite=token)
        first,_,fh = employee("return-owner")
        peer,_,ph = employee("return-peer")
        parent = self.submit(first,a,fh)
        self.worker.run(self.store.claim())
        base = "/api/w/"+a+"/cases/"+parent
        admin.post(base+"/signoff",headers=ah,json={"rev":1,"decision":"return","note":"演练补充原件"})
        body = {"title":"沿用原件","rev":"1","retain":"d01","note":"重新提交原页供复核"}
        def send(client, headers, url):
            return client.post(url+"/supplements",headers=headers,content_type="multipart/form-data",data=body)
        self.assertEqual(send(peer,ph,base).status_code,404)
        self.assertEqual(send(other,bh,"/api/w/"+b+"/cases/"+parent).status_code,404)
        self.assertEqual(send(first,{},base).status_code,403)
        own = send(first,fh,base)
        self.assertEqual(own.status_code,202,own.json)
        reviewer = send(admin,ah,base)
        self.assertEqual(reviewer.status_code,202,reviewer.json)
        detail = first.get(base).json
        self.assertEqual([r["id"] for r in detail["supplements"]],[own.json["id"]])
        self.assertEqual(len(admin.get(base).json["supplements"]),2)
        own_base = "/api/w/"+a+"/cases/"+own.json["id"]
        self.assertEqual(first.get(own_base).json["supplement_of"]["id"],parent)
        self.assertEqual(first.get(own_base+"/reports/1").status_code,403)
        self.assertEqual(peer.get(own_base).status_code,404)
        self.store.limits["storage_mib"] = 0
        self.assertEqual(send(first,fh,base).status_code,429)
        self.assertEqual(len(admin.get(base).json["supplements"]),2)

    def test_peer_review_requires_another_authorized_account(self):
        owner,wid,oh = self.register("first-reviewer",name="同名审计员")
        other,b,bh = self.register("other-enterprise")
        def join(login,role):
            token = owner.post("/api/workspaces/"+wid+"/invites",headers=oh,json={"role":role}).json["token"]
            client,_,headers = self.register(login,name="同名审计员",invite=token)
            return client,headers
        employee,eh = join("peer-employee","employee")
        auditor,ah = join("second-reviewer","auditor")
        cid = self.submit(employee,wid,eh)
        self.worker.run(self.store.claim())
        base = "/api/w/"+wid+"/cases/"+cid
        owner.post(base+"/signoff",headers=oh,json={"rev":1,"decision":"escalate","note":"请另一人复核。"})
        pin = owner.get(base).json["referrals"][0]
        self.assertNotIn("referrals",employee.get(base).json)
        self.assertEqual(employee.get("/api/w/"+wid+"/inbox?status=in_review").json["total"],1)
        fid = owner.get(base+"/reports/1").json["report"]["findings"][0]["id"]
        body = {"rev":1,"reviewer":"客户端填写的姓名","report_hash":pin["report_hash"],"signoff_hash":pin["signoff_hash"],
                "note":"已核所引记录，需要补件。","decision":"return","findings":[fid]}
        for client, headers, target, expected in ((owner,oh,base,403),(employee,eh,base,403),(auditor,{},base,403),
                                                  (other,bh,"/api/w/"+b+"/cases/"+cid,404)):
            self.assertEqual(client.post(target+"/peer-review",headers=headers,json=body).status_code,expected)
        session = auditor.get("/api/session").json
        aid = session["user"]["id"]
        members = "/api/workspaces/"+wid+"/members/"+aid
        owner.post(members,headers=oh,json={"role":"employee"})
        self.assertIn(auditor.post(base+"/peer-review",headers=ah,json=body).status_code,(403,404))
        owner.post(members,headers=oh,json={"role":"auditor"})
        result = auditor.post(base+"/peer-review",headers=ah,json=body)
        self.assertEqual((result.status_code,result.json.get("rev")),(200,2))
        first,second = owner.get(base).json["decisions"]
        self.assertNotEqual(first["actor"],second["actor"])
        self.assertEqual((first["reviewer"],second["reviewer"],second["actor"]),("同名审计员","同名审计员",aid))
        self.assertEqual(employee.get(base+"/reports/2").status_code,403)

    def test_same_invoice_exports_the_reviewed_historical_version(self):
        first,wid,fh = self.register("invoice-referrer")
        invite = first.post("/api/workspaces/"+wid+"/invites",headers=fh,json={"role":"auditor"}).json
        second,_,sh = self.register("invoice-peer",invite=invite["token"])
        cases = "/api/w/"+wid+"/cases/"
        def verified_invoice(client,headers):
            cid = self.submit(client,wid,headers)
            self.worker.run(self.store.claim())
            res = client.post(cases+cid+"/attest",headers=headers,json={"rev":1,"decision":"confirm",
                            "facts":["d01/p1/f1","d01/p1/f2"],"note":"演练核对同票号码及资料类型。"})
            self.assertEqual(res.status_code,202,res.json)
            self.worker.run(self.store.claim())
            return cid
        prior = verified_invoice(first,fh)
        base = cases+prior
        first.post(base+"/signoff",headers=fh,json={"rev":2,"decision":"escalate","note":"请复核资料范围。"})
        pin = first.get(base).json["referrals"][0]
        selected = first.get(base+"/reports/2").json["report"]["findings"][0]["id"]
        body = {"rev":2,"report_hash":pin["report_hash"],"signoff_hash":pin["signoff_hash"],
                "decision":"return","note":"已核该案资料范围，需补件。","findings":[selected]}
        self.assertEqual(second.post(base+"/peer-review",headers=sh,json=body).json["rev"],3)
        repeat = verified_invoice(second,sh)
        current = second.get(cases+repeat+"/reports/2").json["report"]
        row = current["graph"]["prior_invoices"][0]
        self.assertEqual((row["case_id"],row["rev"],row["peer_source_rev"],row["decision"]),(prior,3,2,"return"))
        with second.get(cases+repeat+"/reports/2/bundle") as response:
            archive = io.BytesIO(response.data)
            self.assertEqual(verify(archive,True)[:2],(repeat,2))
            with zipfile.ZipFile(archive) as saved:
                self.assertIn(f"prior/{prior}/r3/review/referral.json",saved.namelist())
                self.assertIn(f"prior/{prior}/r3/field-checks/r1/report.json",saved.namelist())
                self.assertEqual(hashlib.sha256(saved.read(f"prior/{prior}/r3/signoff.json")).hexdigest(),row["signoff_hash"])
        with self.store.connect(True) as db:
            db.execute("UPDATE invoice_index SET quote=? WHERE case_id=?",("不符的测试引文",prior))
        with self.assertRaisesRegex(CaseError,"同票索引"):
            self.store.prior_invoices(repeat,[row["number_key"]])

    def test_atomic_admission_and_accounted_requests(self):
        from concurrent.futures import ThreadPoolExecutor
        from capacity import job_scope, request_attempt, usage
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
