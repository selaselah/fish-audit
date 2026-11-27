import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from config import CaseError
from documents import prepare
from invoice_proof import source_record
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

    def submit(self, client,wid,headers,key="constant-request-key"):
        response = client.post("/api/w/"+wid+"/cases",headers={**headers,"Idempotency-Key":key},
                               data={"title":"演练", "files":(io.BytesIO(self.source),"演练.jpg")})
        self.assertEqual(response.status_code,202,response.json)
        return response.json["id"]

    def checked_invoice(self,client,wid,headers,key):
        cid = self.submit(client,wid,headers,key)
        base = "/api/w/"+wid+"/cases/"+cid
        self.worker.run(self.store.claim())
        choice = {"rev":1,"decision":"confirm","facts":["d01/p1/f1","d01/p1/f2"],"note":"已对照合成票号与抬头。"}
        self.assertEqual(client.post(base+"/attest",headers=headers,json=choice).status_code,202)
        self.worker.run(self.store.claim())
        return cid

    def test_concurrent_approvals_recheck_invoice_history_inside_the_write_transaction(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        admin,wid,headers = self.register("invoice-race")
        token = admin.post("/api/workspaces/"+wid+"/invites",headers=headers,json={"role":"auditor"}).json["token"]
        peer,_,ph = self.register("invoice-race-peer",invite=token)
        foreign,other,oh = self.register("invoice-race-foreign")
        a = self.checked_invoice(admin,wid,headers,"invoice-race-A")
        b = self.checked_invoice(peer,wid,ph,"invoice-race-B")
        outside = self.checked_invoice(foreign,other,oh,"invoice-race-C")
        choice = {"rev":2,"decision":"approve","note":"已核合成发票。"}
        self.assertEqual(foreign.post(f"/api/w/{other}/cases/{outside}/signoff",headers=oh,json=choice).status_code,200)
        gate = Barrier(2)
        def approve(item):
            cid,client,auth = item
            gate.wait(5)
            response = client.post(f"/api/w/{wid}/cases/{cid}/signoff",headers=auth,json=choice)
            return response.status_code,cid,response.json
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = sorted(pool.map(approve,[(a,admin,headers),(b,peer,ph)]))
        self.assertEqual([r[0] for r in results],[200,409])
        prior,loser = results[0][1],results[1][1]
        delta = results[1][2]["invoice_history"]
        self.assertEqual(delta["count"],1)
        changed = delta["changes"][0]
        self.assertIsNone(changed["previous"])
        self.assertEqual((changed["current"]["case_id"],changed["current"]["rev"],changed["current"]["fact"]),(prior,2,"d01/p1/f2"))
        base = f"/api/w/{wid}/cases/{loser}"
        self.assertEqual(admin.get(base).json["decisions"],[])
        with admin.get(base+"/reports/2") as response:
            previous = response.json["sha256"]
        self.assertEqual(admin.post(base+"/rerun",headers=headers,json={"rev":2}).status_code,202)
        self.worker.run(self.store.claim())
        report = admin.get(base+"/reports/3").json["report"]
        self.assertEqual([r["case_id"] for r in report["graph"]["prior_invoices"]],[prior])
        self.assertTrue(any(f["rule"]=="I02" and f["status"]=="risk" for f in report["findings"]))
        self.assertEqual(admin.get(base+"/reports/2").json["sha256"],previous)
        self.assertEqual(admin.post(base+"/signoff",headers=headers,json={**choice,"rev":3,"note":"已核前案，按演练意见签收。"}).status_code,200)
        winner = admin.get(f"/api/w/{wid}/cases/{prior}/reports/2").json["invoice_approval"]
        self.assertEqual((winner["outcome"],winner["numbers"][0]["value"],winner["matches"]),("no_match","DEMO-537",[]))
        self.assertNotIn("invoice_approval",admin.get(base+"/reports/2").json)
        checked = admin.get(base+"/reports/3").json["invoice_approval"]
        self.assertEqual((checked["outcome"],checked["workspace"],[m["case_id"] for m in checked["matches"]]),("matched",wid,[prior]))
        with admin.get(base+"/reports/3/bundle") as response:
            data=io.BytesIO(response.data)
            self.assertEqual(verify(data,True)[:2],(loser,3))
            with zipfile.ZipFile(data) as archive:
                self.assertEqual(json.loads(archive.read("approval/invoices.json")),checked)
                self.assertEqual(json.loads(archive.read(f"prior/{prior}/r2/approval/invoices.json")),winner)
        with self.store.connect(True) as db:
            db.execute("UPDATE signoffs SET note='改写原签收' WHERE case_id=?",(prior,))
        self.assertEqual(admin.get(f"/api/w/{wid}/cases/{prior}/reports/2").status_code,409)
        self.assertEqual(admin.get(base+"/reports/3/bundle").status_code,409)

    def test_peer_invoice_approval_keeps_its_source_and_records_an_unsearchable_number(self):
        admin,wid,headers = self.register("approval-origin")
        token = admin.post("/api/workspaces/"+wid+"/invites",headers=headers,json={"role":"auditor"}).json["token"]
        peer,_,ph = self.register("approval-peer",invite=token)
        cid = self.submit(admin,wid,headers,"approval-visual-only")
        self.worker.run(self.store.claim())
        base=f"/api/w/{wid}/cases/{cid}"
        before=admin.get(base+"/reports/1").json
        self.assertNotIn("invoice_approval",before)
        self.assertEqual(admin.post(base+"/signoff",headers=headers,json={"rev":1,"decision":"escalate","note":"票号待线下复核。"}).status_code,200)
        pin=admin.get(base).json["referrals"][0]
        action={"rev":1,"decision":"approve","note":"合成线下核验演练。","report_hash":pin["report_hash"],
                "signoff_hash":pin["signoff_hash"],"findings":[before["report"]["findings"][0]["id"]]}
        for attempt in range(2):
            self.assertEqual(peer.post(base+"/peer-review",headers=ph,json=action).json["rev"],2)
        current=admin.get(base+"/reports/2").json
        checked=current["invoice_approval"]
        self.assertEqual((checked["source_rev"],checked["signed_rev"],checked["source_sha256"]),(1,2,before["sha256"]))
        self.assertEqual((checked["outcome"],checked["numbers"],checked["matches"]),("no_usable_number",[],[]))
        self.assertEqual(admin.get(base+"/reports/1").json,before)
        with admin.get(base+"/reports/2/bundle") as response:
            self.assertEqual(verify(io.BytesIO(response.data),True)[:2],(cid,2))
        with self.store.connect(True) as db:
            db.execute("UPDATE signoffs SET invoice_check=NULL,invoice_check_hash=NULL WHERE case_id=? AND rev=2",(cid,))
        self.assertEqual(admin.get(base+"/reports/2/bundle").status_code,409)

    def test_native_invoice_exports_signed_original_and_rejects_changed_evidence(self):
        admin,wid,headers = self.register("native-invoice")
        # Supply a controlled native layer. Both the original upload and the saved page are real files.
        lines = ["采购发票","发票号码：DEMO-537"]
        def native_page(*args,**kwargs):
            pages = prepare(*args,**kwargs)
            pages[0].update(text="\n".join(lines),layer={"type":"text","lines":{
                "1":[[.1,.1,.6,.2]],"2":[[.1,.3,.6,.4]]}})
            return pages
        cases = "/api/w/"+wid+"/cases/"
        with patch("jobs.prepare",native_page):
            first = self.submit(admin,wid,headers,"native-invoice-first")
            self.worker.run(self.store.claim())
            choice = {"rev":1,"decision":"approve","note":"已核演练发票。"}
            self.assertEqual(admin.post(cases+first+"/signoff",headers=headers,json=choice).status_code,200)
            second = self.submit(admin,wid,headers,"native-invoice-second")
            self.worker.run(self.store.claim())
        with admin.get(cases+second+"/reports/1/bundle") as response:
            self.assertEqual(response.status_code,200)
            data = response.data
        self.assertEqual(verify(io.BytesIO(data),True)[:2],(second,1))
        prefix = "prior/"+first+"/r1/"
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            files = {k:bundle.read(k) for k in bundle.namelist()}
        match = json.loads(files["report.json"])["graph"]["prior_invoices"][0]
        self.assertEqual((match["source"]["basis"],match["source"]["line"]),("native_line",2))
        self.assertEqual(files[prefix+"originals/d01.jpg"],self.source)
        self.assertEqual(files[prefix+"d01/1.txt"].decode().splitlines()[1],match["quote"])
        self.assertEqual(hashlib.sha256(files[prefix+"signoff.json"]).hexdigest(),match["signoff_hash"])
        for name,replacement in (("d01/1.txt","票号错误".encode()),("originals/d01.jpg",b"different"),
                                 ("signoff.json",files[prefix+"signoff.json"].replace("已核".encode(),"待核".encode())),
                                 ("report.json",None)):
            with self.subTest(file=name):
                changed = files.copy()
                path = prefix+name
                if replacement is None:
                    del changed[path]
                else:
                    changed[path] = replacement
                manifest = json.loads(changed.pop("manifest.json"))
                manifest["files"] = [{"path":p,"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()} for p,b in changed.items()]
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer,"w") as bundle:
                    for p,b in changed.items():
                        bundle.writestr(p,b)
                    bundle.writestr("manifest.json",json.dumps(manifest))
                with self.assertRaises(ValueError):
                    verify(buffer)
        with self.store.connect(True) as db:
            db.execute("UPDATE pages SET text='错误文字' WHERE case_id=?",(first,))
        with self.assertRaisesRegex(CaseError,"原文依据"):
            self.store.prior_invoices(second,[match["number_key"]])
        self.assertEqual(admin.post(cases+second+"/signoff",headers=headers,json=choice).status_code,409)
        with self.store.connect(True) as db:
            db.execute("UPDATE pages SET text=? WHERE case_id=?",("\n".join(lines),first))
        (self.store.files/first/"d01"/"original.jpg").write_bytes(b"changed original")
        with self.assertRaisesRegex(CaseError,"来源摘要"):
            self.store.prior_invoices(second,[match["number_key"]])
        self.assertEqual(admin.post(cases+second+"/signoff",headers=headers,json=choice).status_code,409)
        self.assertEqual(admin.get(cases+second).json["decisions"],[])

    def test_missing_signed_index_recovers_once_and_stale_approval_still_conflicts(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from graph import entity_id
        admin,wid,headers=self.register("repair-invoice-index")
        outsider,foreign,auth=self.register("foreign-invoice-index")
        first=self.checked_invoice(admin,wid,headers,"before-index-gap")
        second=self.checked_invoice(admin,wid,headers,"pending-at-index-gap")
        other=self.checked_invoice(outsider,foreign,auth,"foreign-index-gap")
        choice={"rev":2,"decision":"approve","note":"演练签收。"}
        root=f"/api/w/{wid}/cases/"
        self.assertEqual(admin.post(root+first+"/signoff",headers=headers,json=choice).status_code,200)
        self.assertEqual(outsider.post(f"/api/w/{foreign}/cases/{other}/signoff",headers=auth,json=choice).status_code,200)
        saved=self.store.report(first,2)
        with self.store.connect(True) as db:
            db.execute("DELETE FROM invoice_index WHERE case_id IN (?,?)",(first,other))
        conflict=admin.post(root+second+"/signoff",headers=headers,json=choice)
        self.assertEqual(conflict.status_code,409)
        self.assertEqual([row["current"]["case_id"] for row in conflict.json["invoice_history"]["changes"]],[first])
        self.assertEqual(admin.get(root+second).json["decisions"],[])
        keys=[entity_id("invoice_number","DEMO-537")]
        gate=Barrier(2)
        def lookup(_):
            gate.wait(5)
            return [r["case_id"] for r in self.store.prior_invoices(second,keys)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(lookup,[1,2])),[[first],[first]])
        with self.store.connect() as db:
            self.assertEqual([tuple(r) for r in db.execute("SELECT case_id,count(*) FROM events WHERE stage='invoice_index' GROUP BY case_id")],[(first,1)])
            self.assertEqual(db.execute("SELECT count(*) FROM invoice_index WHERE case_id=?",(other,)).fetchone()[0],0)
        self.assertEqual(self.store.report(first,2),saved)
        with self.store.connect(True) as db:
            db.execute("UPDATE invoice_index SET number_key='另一号码' WHERE case_id=?",(first,))
        with self.assertRaisesRegex(CaseError,"同票索引"):
            self.store.prior_invoices(second,keys)

    def test_upgrade_recovers_an_older_missing_index_and_stops_on_damaged_source(self):
        from graph import entity_id
        admin,wid,headers=self.register("legacy-index-recovery")
        first=self.checked_invoice(admin,wid,headers,"legacy-index-source")
        second=self.submit(admin,wid,headers,"legacy-index-next")
        root=f"/api/w/{wid}/cases/"
        self.assertEqual(admin.post(root+first+"/signoff",headers=headers,json={"rev":2,"decision":"return","note":"演练。"}).status_code,200)
        with self.store.connect(True) as db:
            db.execute("DROP TRIGGER invoice_check_invoice_index_delete")
            db.execute("DELETE FROM invoice_index WHERE case_id=?",(first,))
            db.execute("DELETE FROM invoice_index_pending")
            db.execute("PRAGMA user_version=4")
        upgraded=Store(self.store.root)
        keys=[entity_id("invoice_number","DEMO-537")]
        self.assertEqual([r["case_id"] for r in upgraded.prior_invoices(second,keys)],[first])
        with upgraded.connect(True) as db:
            db.execute("DELETE FROM invoice_index WHERE case_id=?",(first,))
            db.execute("UPDATE reports SET content=content||' ' WHERE case_id=? AND rev=2",(first,))
        with self.assertRaisesRegex(CaseError,"归档摘要"):
            upgraded.prior_invoices(second,keys)
        with upgraded.connect() as db:
            self.assertFalse(db.execute("SELECT 1 FROM invoice_index WHERE case_id=?",(first,)).fetchone())

    def test_legacy_masked_number_requires_a_new_review_at_either_approval(self):
        from jobs import VERSION
        admin,wid,headers=self.register("legacy-mask-review")
        token=admin.post("/api/workspaces/"+wid+"/invites",headers=headers,json={"role":"auditor"}).json["token"]
        peer,_,ph=self.register("legacy-mask-peer",invite=token)
        root=f"/api/w/{wid}/cases/"
        mask="26****001234"
        lines=["采购发票","发票号码："+mask]
        def native(*args,**kwargs):
            pages=prepare(*args,**kwargs)
            pages[0].update(text="\n".join(lines),layer={"type":"text","lines":{"1":[[.1,.1,.5,.2]],"2":[[.1,.3,.5,.4]]}})
            return pages
        out={"quality":"readable","facts":[{"field":field,"value":value,"quote":quote,"region":"top"} for field,value,quote in
             (("invoice","采购发票",lines[0]),("invoice_id",mask,lines[1]))]}
        trace={"model":"fixture","output":out,"check":{"model":"fixture","output":{"checks":[]}}}
        def legacy(key):
            cid=self.submit(admin,wid,headers,key)
            old={k:v for k,v in VERSION.items() if k!="invoice_number_masks"}
            with patch("jobs.prepare",native), patch.object(self.worker,"extract",return_value=(out,trace)), \
                 patch("graph.withhold_partial_numbers",lambda g:None),patch("jobs.VERSION",old):
                self.worker.run(self.store.claim())
            return cid
        first=legacy("legacy-masked-approval")
        old=self.store.report(first,1)
        choice={"rev":1,"decision":"approve","note":"演练核对旧版。"}
        blocked=admin.post(root+first+"/signoff",headers=headers,json=choice)
        self.assertEqual(blocked.status_code,409)
        self.assertEqual(blocked.json["incomplete_numbers"]["facts"][0]["fact"],"d01/p1/f2")
        self.assertEqual(self.store.report(first,1),old)
        self.assertEqual(admin.get(root+first).json["decisions"],[])
        self.assertEqual(admin.post(root+first+"/rerun",headers=headers,json={"rev":1}).status_code,202)
        self.worker.run(self.store.claim())
        self.assertEqual(admin.post(root+first+"/signoff",headers=headers,json={**choice,"rev":2}).status_code,200)
        receipt=admin.get(root+first+"/reports/2").json["invoice_approval"]
        self.assertEqual((receipt["outcome"],receipt["withheld"][0]["value"]),("incomplete_number",mask))
        with admin.get(root+first+"/reports/2/bundle") as response:
            self.assertEqual(verify(io.BytesIO(response.data),True)[:2],(first,2))
        second=legacy("legacy-masked-peer")
        self.assertEqual(admin.post(root+second+"/signoff",headers=headers,json={**choice,"decision":"escalate"}).status_code,200)
        pin=admin.get(root+second).json["referrals"][0]
        paper=self.store.report(second,1)["report"]
        body={**choice,"findings":[paper["findings"][0]["id"]],"report_hash":pin["report_hash"],"signoff_hash":pin["signoff_hash"]}
        blocked=peer.post(root+second+"/peer-review",headers=ph,json=body)
        self.assertEqual((blocked.status_code,blocked.json["incomplete_numbers"]["case_id"]),(409,second))
        self.assertEqual(admin.get(root+second).json["status"],"in_review")
        self.assertEqual(peer.post(root+second+"/peer-review",headers=ph,json={**body,"decision":"return"}).status_code,200)

    def test_same_serial_different_codes_at_issuance_and_at_signature(self):
        admin,wid,headers=self.register("printed-codes")
        base="/api/w/"+wid+"/cases/"
        number="00001234"
        def publish(key,code):
            entries=[("invoice","采购发票","采购发票"),("invoice_id",number,"发票号码："+number)]
            if code:
                entries.append(("invoice_code",code,"发票代码："+code))
            def native(*args,**kwargs):
                pages=prepare(*args,**kwargs)
                pages[0].update(text="\n".join(quote for _,_,quote in entries),layer={"type":"text","lines":{
                    str(i+1):[[.1,.2,.6,.23]] for i in range(len(entries))}})
                return pages
            facts=[{"field":k,"value":v,"quote":q,"region":"top"} for k,v,q in entries]
            output={"facts":facts,"quality":"readable"}
            trace={"model":"fixture","output":output,"check":{"model":"fixture","output":{"checks":[]}}}
            cid=self.submit(admin,wid,headers,key)
            with patch("jobs.prepare",native), patch.object(self.worker,"extract",return_value=(output,trace)):
                self.worker.run(self.store.claim())
            return cid
        a=publish("printed-code-A","099926001011")
        b=publish("printed-code-B","099926002011")
        c=publish("printed-code-copy","099926001011")
        unknown=publish("printed-code-unknown",None)
        choice={"rev":1,"decision":"approve","note":"水印演练。"}
        sign=lambda cid,body:admin.post(base+cid+"/signoff",headers=headers,json=body)
        self.assertEqual(sign(a,choice).status_code,200)
        self.assertEqual(sign(b,choice).status_code,200)
        receipt=admin.get(base+b+"/reports/1").json["invoice_approval"]
        self.assertEqual((receipt["outcome"],receipt["matches"]),("no_match",[]))
        self.assertEqual([(r["case_id"],r["comparison"]) for r in receipt["screened"]],[(a,"different")])
        self.assertEqual(receipt["screened"][0]["code_evidence"][0]["line"],3)
        self.assertFalse(self.store.report(b,1)["report"]["graph"]["prior_invoices"])
        with admin.get(base+b+"/reports/1/bundle") as response:
            self.assertEqual(verify(io.BytesIO(response.data),True)[:2],(b,1))
            with zipfile.ZipFile(io.BytesIO(response.data)) as bundle:
                self.assertIn(f"prior/{a}/r1/originals/d01.jpg",bundle.namelist())
        self.assertEqual(sign(unknown,{**choice,"decision":"return"}).status_code,200)
        stale=sign(c,choice)
        self.assertEqual(stale.status_code,409)
        self.assertEqual({r["current"]["case_id"] for r in stale.json["invoice_history"]["changes"]},{a,unknown})
        self.assertEqual(admin.post(base+c+"/rerun",headers=headers,json={"rev":1}).status_code,202)
        self.worker.run(self.store.claim())
        paper=self.store.report(c,2)["report"]
        rows=paper["graph"]["prior_invoices"]
        self.assertEqual({r["case_id"]:r["comparison"] for r in rows},{a:"same",b:"different",unknown:"uncertain"})
        finding=next(f for f in paper["findings"] if f["rule"]=="I02")
        self.assertEqual(finding["status"],"risk")
        self.assertTrue(all(code["id"] in finding["evidence"] for row in rows for code in row["code_evidence"]))
        with admin.get(base+c+"/reports/2/bundle") as response:
            self.assertEqual(verify(io.BytesIO(response.data),True)[:2],(c,2))
            with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
                files={name:archive.read(name) for name in archive.namelist()}
        # Keep all public checksums consistent after moving the purported code to the number's line.
        altered=json.loads(files["report.json"])
        graph=altered["graph"]
        excluded=next(r for r in graph["prior_invoices"] if r["comparison"]=="different")
        code=excluded["code_evidence"][0]
        code["line"]=2
        for node in graph["nodes"]:
            if node["id"]==excluded["id"]:
                node["code_evidence"]=[code]
            if node["id"]==code["id"]:
                node["line"]=2
        files["report.json"]=json.dumps(altered,ensure_ascii=False).encode()
        checksum=hashlib.sha256(files["report.json"]).hexdigest()
        journal=json.loads(files["journal.json"])
        next(r for r in journal["revisions"] if r["rev"]==2)["hash"]=checksum
        files["journal.json"]=json.dumps(journal).encode()
        manifest=json.loads(files.pop("manifest.json"))
        manifest.update(report_sha256=checksum,files=[{"path":k,"bytes":len(v),"sha256":hashlib.sha256(v).hexdigest()} for k,v in files.items()])
        tampered=io.BytesIO()
        with zipfile.ZipFile(tampered,"w") as archive:
            for path,content in files.items():
                archive.writestr(path,content)
            archive.writestr("manifest.json",json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,"组合标识与签收原页不符"):
            verify(tampered)
        d=publish("printed-code-unseen","099926003011")
        item=next(f for f in self.store.report(d,1)["report"]["findings"] if f["rule"]=="I02")
        self.assertEqual(item["status"],"missing")
        self.assertEqual(sign(d,choice).status_code,200)
        checked=admin.get(base+d+"/reports/1").json["invoice_approval"]
        self.assertEqual((checked["outcome"],[m["case_id"] for m in checked["matches"]]),("possible_match",[unknown]))

    def test_historical_invoice_source_describes_the_available_line_or_confirmation(self):
        from graph import entity_id
        key = entity_id("invoice_number","YL-01")
        fact = {"field":"invoice_id","quote":"发票号码：YL-01","value":"YL-01","status":"anchored"}
        self.assertEqual(source_record(fact,{},"",key,"t")["basis"],"historical_record")
        fact.update(status="confirmed",attestation={"decision":"confirm"})
        self.assertEqual(source_record(fact,{},"",key,"t")["basis"],"historical_confirmation")
        fact.update(status="anchored",source_line={"number":1,"text":"另一行","rects":[[.1,.2,.4,.3]]})
        with self.assertRaisesRegex(ValueError,"逐字引文"):
            source_record(fact,{},"另一行",key,"t")

    def test_changed_referral_blocks_peer_approval_and_keeps_return_available(self):
        admin,wid,headers = self.register("invoice-pin-owner")
        token = admin.post("/api/workspaces/"+wid+"/invites",headers=headers,json={"role":"auditor"}).json["token"]
        other,_,oh = self.register("invoice-pin-peer",invite=token)
        root = f"/api/w/{wid}/cases/"
        def refer(cid):
            self.assertEqual(admin.post(root+cid+"/signoff",headers=headers,json={"rev":2,"decision":"escalate","note":"请复核。"}).status_code,200)
            pin = admin.get(root+cid).json["referrals"][0]
            finding = next(f["id"] for f in self.store.report(cid,2)["report"]["findings"] if f["rule"]=="I02")
            return {"rev":2,"report_hash":pin["report_hash"],"signoff_hash":pin["signoff_hash"],
                    "decision":"return","note":"已核原版发现。","findings":[finding]}
        prior = self.checked_invoice(admin,wid,headers,"invoice-pin-prior")
        first = refer(prior)
        case = self.checked_invoice(admin,wid,headers,"invoice-pin-later")
        second = refer(case)
        self.assertEqual(other.post(root+prior+"/peer-review",headers=oh,json=first).status_code,200)
        url = root+case+"/peer-review"
        rejected = other.post(url,headers=oh,json={**second,"decision":"approve"})
        self.assertEqual(rejected.status_code,409)
        change = rejected.json["invoice_history"]["changes"][0]
        self.assertEqual([(change[key]["case_id"],change[key]["rev"],change[key]["decision"]) for key in ("previous","current")],
                         [(prior,2,"escalate"),(prior,3,"return")])
        self.assertIsNone(self.store.detail(case)["referrals"][0]["resolved_rev"])
        self.assertEqual(other.post(url,headers=oh,json=second).json["rev"],3)
        self.assertEqual(other.post(url,headers=oh,json=second).json["rev"],3)

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
        thumb=f"/api/w/{a}/cases/{emp_case}/documents/d01/pages/1/thumbnail"
        self.assertEqual(employee.get(thumb).status_code,200)
        self.assertEqual(employee.get(thumb+"?rev=1").status_code,403)
        self.assertEqual(employee.get(thumb.replace(emp_case,administrator_case)).status_code,404)
        for tail in ("","/reports/1","/reports/1/bundle","/documents/d01/original","/documents/d01/pages/1","/documents/d01/pages/1/thumbnail?rev=1"):
            self.assertEqual(other.get("/api/w/"+b+"/cases/"+emp_case+tail).status_code,404)
        self.assertEqual(employee.get("/api/w/"+a+"/cases/"+administrator_case).status_code,404)
        self.assertEqual(employee.get("/api/w/"+a+"/cases/"+emp_case+"/reports/1").status_code,403)
        source_link = "/w/"+a+"/workpaper/"+emp_case+"?rev=1&fact=d01%2Fp1%2Ff1"
        self.assertEqual(admin.get(source_link).headers["Location"],"/app#w/"+a+"/case/"+emp_case+"?rev=1&fact=d01%2Fp1%2Ff1")
        entity_link = "/w/"+a+"/workpaper/"+emp_case
        agreement_query = "?rev=1&view=addendum-signing"
        self.assertEqual(admin.get(entity_link+agreement_query).headers["Location"],"/app#w/"+a+"/case/"+emp_case+agreement_query)
        self.assertEqual(admin.get(entity_link+"?view=addendum-signing").status_code,400)
        for unit in ("d05","unit%2Fd02%2Fp3"):
            query = agreement_query+"&agreement="+unit
            self.assertEqual(admin.get(entity_link+query).headers["Location"],"/app#w/"+a+"/case/"+emp_case+query)
        for query in ("?view=addendum-signing&agreement=d05", "?rev=1&view=execution&agreement=d05", agreement_query+"&rev=2",
                      agreement_query+"&view=addendum-signing",
                      agreement_query+"&agreement=d05&agreement=d06", agreement_query+"&agreement=unit/d02/p0",
                      agreement_query+"&rev=2&agreement=d05"):
            self.assertEqual(admin.get(entity_link+query).status_code,400)
        register_query = "?rev=1&view=warranty-register&ticket=d03"
        self.assertEqual(admin.get(entity_link+register_query).headers["Location"],"/app#w/"+a+"/case/"+emp_case+register_query)
        for query in ("?view=warranty-register&ticket=d01", "?rev=1&view=execution&ticket=d03",
                      register_query+"&ticket=d01", register_query+"&rev=2", register_query+"&view=entities",
                      "?rev=1&view=warranty-register&ticket=d01/p1"):
            self.assertEqual(admin.get(entity_link+query).status_code,400)
        for step in ("d01%2Fp1%2Finitial","d01%2Fp1%2Fcheck","expert"):
            query = "?rev=1&view=execution&call="+step
            self.assertEqual(admin.get(entity_link+query).headers["Location"],"/app#w/"+a+"/case/"+emp_case+query)
        for query in ("?view=execution&call=expert","?rev=1&view=replay&call=expert","?rev=1&view=execution&call=d01/p0/check",
                      "?rev=1&view=execution&call=d01/p1/absent","?rev=1&view=execution&call=expert&call=expert",
                      "?rev=1&rev=2&view=execution&call=expert"):
            self.assertEqual(admin.get(entity_link+query).status_code,400)
        self.assertEqual(admin.get(entity_link+"?rev=1&view=entities").headers["Location"],
                         "/app#w/"+a+"/case/"+emp_case+"?rev=1&view=entities")
        self.assertEqual(admin.get(entity_link+"?view=entities").status_code,400)
        self.assertEqual(admin.get(source_link+"&view=entities").status_code,400)
        for view in ("contract-checks","acceptance-checks","payment-checks"):
            scoped=entity_link+"?rev=1&view="+view
            self.assertEqual(admin.get(scoped).headers["Location"],"/app#w/"+a+"/case/"+emp_case+"?rev=1&view="+view)
            self.assertEqual(admin.get(entity_link+"?view="+view).status_code,400)
            self.assertEqual(admin.get(scoped+"&receipt=H05-9").status_code,400)
        stage_view=entity_link+"?rev=1&view=payment-checks&stage=H04-6"
        self.assertEqual(admin.get(stage_view).headers["Location"],"/app#w/"+a+"/case/"+emp_case+"?rev=1&view=payment-checks&stage=H04-6")
        paid_view=entity_link+"?rev=1&view=payment-checks&stage=H05-9"
        self.assertEqual(admin.get(paid_view).headers["Location"],"/app#w/"+a+"/case/"+emp_case+"?rev=1&view=payment-checks&stage=H05-9")
        for invalid in (stage_view.replace("rev=1&",""), stage_view.replace("payment-checks","acceptance-checks"),
                        stage_view.replace("H04-6","H01-6"), stage_view+"&stage=H04-7"):
            self.assertEqual(admin.get(invalid).status_code,400)
        bank_view=entity_link+"?rev=1&view=payment-acceptance&receipt=H05-9"
        self.assertEqual(admin.get(bank_view).headers["Location"],"/app#w/"+a+"/case/"+emp_case+"?rev=1&view=payment-acceptance&receipt=H05-9")
        proof_view=bank_view.replace("payment-acceptance","payment-proof")
        self.assertEqual(admin.get(proof_view).headers["Location"],"/app#w/"+a+"/case/"+emp_case+"?rev=1&view=payment-proof&receipt=H05-9")
        self.assertEqual(admin.get(proof_view.replace("H05-9","B04-9")).status_code,400)
        self.assertEqual(admin.get(bank_view.replace("H05-9","H04-9")).status_code,400)
        self.assertEqual(admin.get(bank_view.replace("payment-acceptance","trial")).status_code,400)
        self.assertEqual(admin.get(entity_link+"?rev=1&view=trial").headers["Location"],
                         "/app#w/"+a+"/case/"+emp_case+"?rev=1&view=trial")
        self.assertEqual(admin.get(entity_link+"?view=trial").status_code,400)
        self.assertEqual(admin.get(source_link+"&view=trial").status_code,400)
        self.assertEqual(admin.get(entity_link+"?rev=1&view=contract-pages").headers["Location"],
                         "/app#w/"+a+"/case/"+emp_case+"?rev=1&view=contract-pages")
        self.assertEqual(admin.get(entity_link+"?view=contract-pages").status_code,400)
        self.assertEqual(admin.get(source_link+"&view=contract-pages").status_code,400)
        self.assertEqual(admin.get(entity_link+"?rev=1&view=signatures").headers["Location"],
                         "/app#w/"+a+"/case/"+emp_case+"?rev=1&view=signatures")
        self.assertEqual(admin.get(entity_link+"?view=signatures").status_code,400)
        self.assertEqual(admin.get(source_link+"&view=signatures").status_code,400)
        self.assertEqual(admin.get(entity_link+"?rev=1&view=calendar").headers["Location"],
                         "/app#w/"+a+"/case/"+emp_case+"?rev=1&view=calendar")
        self.assertEqual(admin.get(entity_link+"?view=calendar").status_code,400)
        self.assertEqual(admin.get(source_link+"&view=calendar").status_code,400)
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
        self.assertEqual(row["source"]["basis"],"field_check")
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
