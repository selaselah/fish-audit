import unittest
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch

import installment_counts as counts
from config import PERFORMANCE
from model import FIELDS
from controls import VERSION, execute
from graph import build_graph, link_procedures
from performance import verify_findings
from test_performance import BANK_DOC, CONTRACT, WARRANTY, material
from test_reinspection import OLD, FIX, FINAL


def packet(*, body="分三期付款", suffix="", extra=(), vote="clear", rectangles=True, bank="FY-02", paid="2026-09-27", failure=None):
    payments = [*BANK_DOC, ("payment_acceptance_ref","付款依据验收单号",bank)]
    contract = [(key,label,body if key=="payment_term" else value) for key,label,value in CONTRACT]
    traces, texts, layouts = {}, {}, {}
    def build(docs, pages, signoffs):
        doc, page = docs[0], pages[0]
        doc.update(ext=".pdf",pages=1,sha256=sha256(b"fixture pdf").hexdigest())
        extraction = page["extraction"]
        fact = next(f for f in extraction["output"]["facts"] if f["field"]=="payment_term")
        offset = extraction["output"]["facts"].index(fact) + 1
        number = page["text"].splitlines().index(fact["quote"])+1
        if suffix:
            page["text"]=page["text"].replace(fact["quote"],fact["quote"]+suffix)
        if not rectangles:
            page["layer"]["lines"].pop(str(number))
        page["sha256"] = sha256(page["text"].encode()).hexdigest()
        fact["quote"] = body
        model_input={"index":str(offset),"field":FIELDS["payment_term"],"quote":body,"value":body}
        extraction.update(response_id="first-read", check={"response_id":"second-read","model":"fixture",
            "input":[model_input],"output":{"checks":[{"index":str(offset),"support":vote}]}})
        if failure: failure(doc,page,fact,extraction)
        for p in pages:
            addr=p["doc"],p["number"];texts[addr]=p["text"];layouts[addr]=p["layer"]
            traces[addr]={"model":"fixture","doc":p["doc"],"page":p["number"],"page_sha256":p["sha256"],**p["extraction"]}
        return build_graph(docs,pages,signoffs)
    with patch("test_performance.build_graph",build):
        g=material([contract,OLD,FIX,FINAL,WARRANTY,payments], edit=lambda i,k,l,v:paid if k=="paid_on" else v,
                   omissions=[(1,x) for x in extra])
    fs=execute(g,PERFORMANCE);policy={**VERSION,"profile":PERFORMANCE}
    for r in g.get(counts.KEY,{}).get("rows",[]):
        policy["installment_count"]=counts.FORMAT
        traces[r["doc"],1][counts.RECTS]={str(r["line"]):r["rects"]}
    calls={"expert":{"model":"fixture"},"pages":list(traces.values())}
    link_procedures(g,fs,calls)
    return {"policy":policy,"graph":g,"calls":calls,"findings":fs},lambda d,n:texts[d,n],lambda d,n:layouts[d,n]


class InstallmentCountTests(unittest.TestCase):
    def test_document_match_can_cite_the_complete_printed_header_without_passing_the_plan(self):
        p, text, layout = packet(body="分四期付款")
        plan = next(f for f in p["findings"] if f["rule"] == "H03")
        payment = next(f for f in p["findings"] if f["rule"] == "H05")
        row, = p["graph"][counts.KEY]["rows"]
        audit = payment["retest_reference"]
        self.assertEqual((plan["status"],payment["status"],audit["state"],audit["status"]),("missing","missing","final","missing"))
        self.assertEqual(audit["schedule_review"]["header"],row["id"])
        self.assertTrue({row["id"],row["model_ref"]} <= set(payment["evidence"]) & set(plan["evidence"]))
        counts.verify(p,text,read_layout=layout)
        verify_findings(p)

    def test_only_declared_count_is_derived_and_failed_inspection_is_still_adverse(self):
        for bank,state in (("FY-02","final"),("YS-01","original")):
            p,text,layout=packet(bank=bank);g=p["graph"]
            r,=g[counts.KEY]["rows"]
            fact=next(f for f in g["facts"] if f["id"]==r["model_ref"])
            self.assertEqual((r["count"],r["quote"],fact["quote"],fact["status"],fact["source_line"]),
                             (3,"付款条款：分三期付款","分三期付款","visual",None))
            plan=next(f for f in p["findings"] if f["rule"]=="H03")
            payment=next(f for f in p["findings"] if f["rule"]=="H05")
            self.assertEqual(plan["status"],"ok");self.assertEqual(payment["retest_reference"]["state"],state)
            if state=="original":self.assertEqual(payment["status"],"risk")
            self.assertTrue(all(r["id"] in f["evidence"] and f["installment_count"]==r["id"] for f in (plan,payment)))
            counts.verify(p,text,read_layout=layout);verify_findings(p)

    def test_riders_ambiguity_disagreement_and_missing_geometry(self):
        for params in ({"suffix":"，另收保证金"},{"extra":["验收备注：分三期付款"]},{"extra":["结算方式：另见附件"]},
                       {"vote":"conflict"},{"vote":"unreadable"},
                       {"failure":lambda doc,p,f,c:c["check"]["input"][0].update(quote="分四期付款")},
                       {"failure":lambda doc,p,f,c:c["check"].update(response_id=c["response_id"])},
                       {"failure":lambda doc,p,f,c:doc.update(pages=2)},
                       {"failure":lambda doc,p,f,c:p["layer"].update(clause_text_only=False)},{"rectangles":False}):
            with self.subTest(params=params):
                p,text,layout=packet(**params)
                self.assertFalse(any(f.get("installment_count") for f in p["findings"]))
                self.assertEqual(next(f["status"] for f in p["findings"] if f["rule"]=="H03"),"missing")
                counts.verify(p,text,read_layout=layout)
        for params in ({"body":"分四期付款"},{"extra":["补充协议：期款另有约定"]}):
            p,_,_=packet(**params);plan=next(f for f in p["findings"] if f["rule"]=="H03")
            self.assertTrue(plan["installment_count"]);self.assertEqual(plan["status"],"missing")

    def test_issued_claim_source_and_older_adverse_result(self):
        p,text,layout=packet(bank="YS-01");r,=p["graph"][counts.KEY]["rows"]
        for mode in ("count","quote","model","rect","edge","claim","vote","geometry","omission"):
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                bad=deepcopy(p);g=bad["graph"];row=g[counts.KEY]["rows"][0];call=bad["calls"]["pages"][0]
                if mode=="count":row["count"]+=1
                elif mode=="quote":row["quote"]+="另见附件"
                elif mode=="model":row["model_ref"]=g["facts"][0]["id"]
                elif mode=="rect":row["rects"]=[]
                elif mode=="vote":call["check"]["output"]["checks"][0]["support"]="unreadable"
                elif mode=="geometry":call[counts.RECTS][str(r["line"])]=[[.1,.1,.4,.3]]
                elif mode=="edge":g["edges"]=[e for e in g["edges"] if e["type"]!="locates_installment_count"]
                elif mode=="omission":g.pop(counts.KEY);call.pop(counts.RECTS)
                else:next(f for f in bad["findings"] if f["rule"]=="H03").pop("installment_count")
                counts.verify(bad,text,read_layout=layout)
        for bank,paid,adverse in (("YS-01","2026-09-27",True),("FY-02","2026-09-21",True),("FY-02","2026-09-27",False)):
            old,text,layout=packet(bank=bank,paid=paid);g=old["graph"];g.pop(counts.KEY)
            old["findings"]=execute(g,PERFORMANCE);g["nodes"]=[n for n in g["nodes"] if n["type"]!="installment_count_line"]
            g["edges"]=[e for e in g["edges"] if e["type"]!="locates_installment_count"]
            old["policy"].pop("installment_count");old["policy"]["version"]="2026.11.28.4";old["calls"]["pages"][0].pop(counts.RECTS)
            counts.verify(old,text,read_layout=layout)
            if adverse:
                with self.assertRaisesRegex(ValueError,"重审"):counts.verify(old,text,read_layout=layout,signing=True)
            else:counts.verify(old,text,read_layout=layout,signing=True)
