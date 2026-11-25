import copy
import unittest

from contract_changes import candidates
from contract_effect import SIGNING_FORMAT, sources, verify
from controls import VERSION, execute
from graph import link_procedures
from performance import compute, verify_findings
from test_signing_parties import BRANCH, BUYER, FIELD, SELLER, original_reader, sample


def annex(values, *, confirmed=(), disputed=(), kind="image_overlay", text="", clean=False):
    rows=[dict(field=f,value=v,quote=l+"："+v if l else v,region="top") for f,l,v in values]
    layer={"type":kind,"clause_text_only":clean,"lines":{str(n):[[.1,.2,.5,.3]] for n,_ in enumerate(text.splitlines(),1)}}
    page={"doc":"d01","number":2,"sha256":"second","text":text,"layer":layer,
          "extraction":{"output":{"quality":"readable","facts":rows}}}
    checks={}
    for i in (*confirmed,*disputed):
        ref=f"d01/p2/f{i}"
        receipt={"format":"field-source-v1","operation":"confirm","rev":2,"doc":"d01","page":2,
                 "original_sha256":"sample","page_sha256":"second","report_hash":"a"*64}
        checks[ref]={"decision":"dispute" if i in disputed else "confirm","fact":ref,"rev":2,"source_check":receipt}
    return sample(extra_pages=[page],extra_attestations=checks)


class ScannedSigningTests(unittest.TestCase):
    def test_only_individually_checked_image_fields_establish_a_difference(self):
        fields=[("buyer_seal_name",FIELD,BRANCH),("seller_seal_name","乙方印章单位名称",SELLER)]
        for checks, expected in [([],["image_pending","image_pending"]),([1],["different","image_pending"]),
                                 ([2],["image_pending","match"]),([1,2],["different","match"])]:
            g=annex(fields,confirmed=checks)
            found=compute(g)
            records=found[0]["effect_review"]["party_seals"]
            self.assertEqual([r["state"] for r in records],expected)
            self.assertEqual(found[0]["status"],"risk" if 1 in checks else "missing")
            self.assertTrue(all(f["status"]=="missing" for f in found if f["rule"] in ("H04","H05")))
            for i,record in enumerate(records,1):
                image,=[s for s in record["field_sources"] if s["kind"]=="image"]
                self.assertEqual((image["fact"],image["receipt_rev"]),(f"d01/p2/f{i}",2 if i in checks else None))
                self.assertTrue(set(record["comparison"])<=set(record["evidence"]))
        for name,expected in [(BUYER,"match"),("青禾演练＊＊公司","partial")]:
            g=annex([("buyer_seal_name",FIELD,name)],confirmed=[1])
            h01=compute(g)[0]
            self.assertEqual(h01["effect_review"]["party_seals"][0]["state"],expected)
            self.assertEqual(h01["status"],"missing","field-level agreement cannot clear a whole scanned page")

    def test_disputed_misclassified_unlocated_and_duplicate_candidates_stay_pending(self):
        good=("buyer_seal_name",FIELD,BRANCH)
        for g,state in [
            (annex([good],disputed=[1]),"disputed"),
            (annex([("buyer_sealed_on",FIELD,BRANCH)],confirmed=[1]),"image_pending"),
            (annex([good],kind="text",text="正文续页",clean=True,confirmed=[1]),"unlocated"),
            (annex([good],kind="text",text=FIELD+"："+BRANCH),"image_pending"),
            (annex([good,("buyer_seal_name",FIELD,BUYER)],confirmed=[1]),"ambiguous"),
            (annex([good,("buyer_seal_name",FIELD,BUYER)],confirmed=[1,2]),"multiple")]:
            r=compute(g)[0]["effect_review"]["party_seals"][0]
            self.assertEqual((r["state"],r["comparison"]),(state,[]))
        g=annex([good],kind="text",text=FIELD+"："+BRANCH,confirmed=[1])
        self.assertEqual(compute(g)[0]["effect_review"]["party_seals"][0]["state"],"different")
        for key,value in [("doc","d02"),("page",1),("original_sha256","different"),("page_sha256","wrong")]:
            changed=copy.deepcopy(g)
            f=next(f for f in changed["facts"] if f["id"]=="d01/p2/f1")
            f["attestation"]["source_check"][key]=value
            self.assertEqual(compute(changed)[0]["effect_review"]["party_seals"][0]["state"],"image_pending")

    def test_unverified_heading_on_main_contract_and_historical_replay(self):
        fields=[("contract_addendum","","合同用印记录"),("buyer_seal_name",FIELD,BRANCH)]
        g=annex(fields,confirmed=[2])
        self.assertEqual(candidates(g),[])
        native=annex(fields,kind="text",text="合同用印记录\n"+FIELD+"："+BRANCH,clean=True)
        self.assertEqual(candidates(native),[])
        self.assertEqual(candidates(annex(fields,confirmed=[1])),["unit/d01/p2"])
        def read(doc,page):
            return "" if page==2 else original_reader(g)(doc,page)
        found=execute(g,g["profile"])
        link_procedures(g,found,{"expert":{"model":"fixture"},"pages":[]})
        report={"graph":g,"policy":{**VERSION,"profile":g["profile"]},"findings":found}
        verify(report,read)
        verify_findings(report)
        changed=copy.deepcopy(report)
        signer=next(f for f in changed["findings"] if f["rule"]=="H01")
        signer["effect_review"]["party_seals"][0]["field_sources"][-1]["receipt_rev"]=42
        with self.assertRaises(ValueError):
            verify_findings(changed)
        old=annex(fields,confirmed=[2])
        old["contract_effect_sources"]=sources(old,read,SIGNING_FORMAT)
        self.assertEqual(candidates(old),["d01"])
        signed=compute(old)[0]
        self.assertEqual(signed["effect_review"]["party_seals"][0]["state"],"image")
        self.assertNotIn("field_sources",signed["effect_review"]["party_seals"][0])
        previous={"graph":old,"findings":compute(old),"policy":{**VERSION,"version":"2026.11.26.02","contract_effect":SIGNING_FORMAT}}
        verify(previous,read)
        with self.assertRaisesRegex(ValueError,"已核差异"):
            verify(previous,read,signing=True)
        for title in ("合同补充协议","双方另签补充协议变更付款条件"):
            self.assertEqual(candidates(annex([("contract_addendum","",title)])),["d01"])
