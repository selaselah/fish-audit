import unittest
from copy import deepcopy
from unittest.mock import patch

from config import PERFORMANCE
from controls import VERSION, execute
from graph import build_graph
from performance import verify_findings
from test_performance import BANK_DOC, CONTRACT, WARRANTY, material
from test_reinspection import OLD, FIX, FINAL
import retest_reference as refs


def sample(codes=("FY-02",), *, dates=("2026-09-27",), changes=None, omissions=(), groups=None):
    texts={}
    def build(docs,pages,*args):
        texts.update({(p["doc"],p["number"]):p["text"] for p in pages})
        return build_graph(docs,pages,*args)
    def edit(i,k,label,v):
        if i>=6 and k=="paid_on":v=dates[i-6]
        return (changes or {}).get((i,k),v)
    banks=[[*BANK_DOC,*([] if code is None else [(refs.FIELD,"付款依据验收单号",code)])] for code in codes]
    with patch("test_performance.build_graph",build):
        graph=material(groups if groups is not None else [CONTRACT,OLD,FIX,FINAL,WARRANTY,*banks],edit=edit,omissions=omissions)
    findings=execute(graph,PERFORMANCE)
    graph["edges"].extend(refs.edges(findings))
    return {"policy":{**VERSION,"profile":PERFORMANCE},"graph":graph,"findings":findings},lambda d,n:texts[d,n]


def payments(report):
    return [f for f in report["findings"] if f["rule"]=="H05"]


class RetestReceiptTests(unittest.TestCase):
    def test_two_transfers_name_different_originals_on_the_same_installment(self):
        p,read=sample(("YS-01","FY-02"),dates=("2026-09-27","2026-09-28"))
        first,second=payments(p)
        for f,state,status in [(first,"original","risk"),(second,"final","ok")]:
            c=f["retest_reference"]
            self.assertEqual((f["stage"]["name"],f["status"],c["state"]),("第二期",status,state))
            self.assertNotIn("payment_acceptance",f)
            self.assertTrue(set(c["fields"].values())<=set(c["evidence"])<=set(f["evidence"]))
        self.assertNotIn(first["retest_reference"]["fields"]["citation"],second["evidence"])
        self.assertEqual(second["retest_reference"]["days_from_final"],2)
        self.assertEqual([e["to"] for e in refs.edges(p["findings"])],
                         [first["retest_reference"]["fields"]["original_acceptance_number"],second["retest_reference"]["fields"]["final_acceptance_number"]])
        self.assertTrue(all("retest_reference" not in f for f in p["findings"] if f["rule"]!="H05"))
        refs.verify(p,read);verify_findings(p)

    def test_referenced_final_does_not_clear_chronology_open_defects_or_signing(self):
        for day,status,days in (("2026-09-25","risk",-1),("2026-09-26","missing",0),("2026-09-27","ok",1)):
            with self.subTest(day=day):
                p,_=sample(dates=(day,));f,=payments(p)
                self.assertEqual((f["status"],f["retest_reference"]["days_from_final"]),(status,days))
        for field,value,status in (("acceptance_result","不合格","risk"),("defect_closure","未关闭","risk"),("defect_closure","等待核字","missing")):
            p,_=sample(changes={(4,field):value});f,=payments(p)
            self.assertEqual((f["status"],f["retest_reference"]["state"]),(status,"final"))
        p,_=sample(changes={(1,"seller_signature"):None});f,=payments(p)
        self.assertEqual((f["status"],f["retest_reference"]["status"]),("missing","ok"))

    def test_signing_rechecks_the_physical_lines_cited_by_each_receipt(self):
        report, read_text = sample()
        facts = {f["id"]: f for f in report["graph"]["facts"]}
        check = payments(report)[0]["retest_reference"]
        layouts = {}
        for fact in facts.values():
            line = fact.get("source_line")
            if line and line["rects"]:
                page = layouts.setdefault((fact["doc"], fact["page"]), {"type":"text","clause_text_only":True,"lines":{}})
                page["lines"][str(line["number"])] = line["rects"]
        refs.verify(report, read_text, read_layout=lambda doc, page: layouts[doc,page])
        for key in ("citation","paid_on","original_acceptance_number","repair_repaired_on","final_accepted_on","final_defect_closure"):
            fact = facts[check["fields"][key]]
            for change in ("moved","missing","layer","annotation"):
                with self.subTest(key=key, change=change), self.assertRaisesRegex(ValueError,"引文位置"):
                    current = deepcopy(layouts)
                    page = current[fact["doc"],fact["page"]]
                    line = str(fact["source_line"]["number"])
                    if change == "moved": page["lines"][line] = [[0.15,0.3,0.7,0.35]]
                    if change == "missing": del page["lines"][line]
                    if change == "layer": page["type"] = "image"
                    if change == "annotation": page["clause_text_only"] = False
                    refs.verify(report, read_text, read_layout=lambda doc, n: current[doc,n])
        unused = next(f for f in facts.values() if f["doc"] not in {facts[v]["doc"] for v in check["evidence"] if v in facts})
        layouts[unused["doc"],unused["page"]] = {}
        refs.verify(report, read_text, read_layout=lambda doc, n: layouts[doc,n])

    def test_prefix_case_and_separators_are_part_of_the_complete_number(self):
        for code in ("FY-03","FY02","fy-02","YS-02"):
            p,_=sample((code,));f,=payments(p)
            self.assertEqual((f["status"],f["retest_reference"]["state"]),("missing","unlocated"))
            self.assertNotIn("days_from_final",f["retest_reference"])
            self.assertEqual(refs.edges(p["findings"]),[])
        for code in ("FY-0*","FY-０２"):
            p,_=sample((code,));f,=payments(p)
            self.assertEqual(f["retest_reference"]["state"],"unresolved")

    def test_only_the_documentary_match_survives_an_incomplete_installment_schedule(self):
        for count, middle, code, paid, state, status, total in (
                ("四","60","FY-02","2026-09-27","final","missing","100"),
                ("四","60","YS-01","2026-09-27","original","risk","100"),
                ("三","50","FY-02","2026-09-21","final","risk","90"),
                ("四","50.25","FY-02","2026-09-26","final","missing","90.25"),
                ("三","50","FY-03","2026-09-27","unlocated","missing","90")):
            with self.subTest(count=count, middle=middle, code=code, paid=paid):
                contract = [(k,l,"分"+count+"期付款" if k=="payment_term" else
                             "最终验收合格后支付"+middle+"%" if l=="第二期" else v) for k,l,v in CONTRACT]
                bank = [*BANK_DOC,(refs.FIELD,"付款依据验收单号",code)]
                p,read = sample(groups=[contract,OLD,FIX,FINAL,WARRANTY,bank], dates=(paid,))
                payment, = payments(p)
                match = payment["retest_reference"]
                plan = next(f for f in p["findings"] if f["rule"] == "H03")
                proof = match["schedule_review"]
                self.assertEqual((plan["status"], payment["status"], match["state"], match["status"]), ("missing",status,state,status))
                self.assertEqual((proof["declared"],proof["listed"],proof["share_total"]), (4 if count=="四" else 3,3,total))
                self.assertTrue({proof["header"],*proof["clauses"]} <= set(plan["evidence"]) & set(match["evidence"]))
                self.assertEqual(proof["clauses"],[f["stage"]["clause_ref"] for f in p["findings"] if f["rule"]=="H04"])
                refs.verify(p,read)
                verify_findings(p)
                if state == "unlocated":
                    self.assertFalse(refs.edges(p["findings"]))
                else:
                    self.assertEqual(refs.edges(p["findings"])[0]["to"],match["fields"][state+"_acceptance_number"])

    def test_missing_clauses_are_not_inferred_from_arithmetic_or_ambiguous_originals(self):
        for kw in ({"omissions":[(1,"另签结算附件后生效")]}, {"omissions":[(1,"说明：其余项目见来函")]},
                   {"omissions":[(1,"设备采购合同")]}, {"omissions":[(1,"第二期：最终验收合格后支付40%")]},
                   {"omissions":[(1,"结算方式：分五期付款")]}, {"changes":{(4,"original_acceptance"):"YS-02"}},
                   {"changes":{(3,"contract_id"):"YL-122"}}, {"changes":{(6,"payee"):"另一个供应方"}}):
            with self.subTest(kw=kw):
                options = {**kw,"changes":{(1,"payment_term"):"分四期付款",**kw.get("changes",{})}}
                p,read = sample(**options)
                self.assertFalse(any(f.get("retest_reference",{}).get("schedule_review") for f in payments(p)))
                self.assertFalse(refs.edges(p["findings"]))
                refs.verify(p,read)

    def test_issued_schedule_evidence_and_earlier_signoffs(self):
        for code,status in (("FY-02","missing"),("YS-01","risk")):
            p,read = sample((code,),changes={(1,"payment_term"):"分四期付款"})
            for target in ("total","count","field","ledger","hold","result"):
                changed = deepcopy(p)
                f, = payments(changed)
                c = f["retest_reference"]
                if target == "total": c["schedule_review"]["share_total"] = "90"
                if target == "count": c["schedule_review"]["declared"] = 3
                if target == "field": c["schedule_review"]["clauses"].reverse()
                if target == "ledger": del changed["graph"][refs.KEY]["schedule_page"]
                if target == "hold": del c["schedule_review"]
                if target == "result": c["status"] = "ok"
                with self.subTest(target=target, code=code), self.assertRaises(ValueError):
                    refs.verify(changed,read)
            g = p["graph"]
            g[refs.KEY] = refs.sources(g,read,refs.FIRST_FORMAT)
            g["edges"] = [e for e in g["edges"] if e["type"] != refs.EDGE]
            p["policy"].update(version="2026.11.28.6",retest_reference=refs.FIRST_FORMAT)
            p["findings"] = execute(g,PERFORMANCE)
            self.assertEqual(payments(p)[0]["retest_reference"]["state"],"unresolved")
            refs.verify(p,read)
            if status == "risk":
                with self.assertRaisesRegex(ValueError,"重审"): refs.guard_prior_signoff(p,read)
            else:
                refs.guard_prior_signoff(p,read)

    def test_duplicate_raw_lines_foreign_identity_and_missing_chain_remain_unresolved(self):
        for kw in ({"omissions":[(4,"复验单编号：FY-03")]},{"omissions":[(3,"整改记录编号：ZG-02")]},
                   {"omissions":[(6,"付款依据验收单号：YS-01")]},{"omissions":[(6,"附注：本笔转账已撤销")]},
                   {"changes":{(4,"original_acceptance"):"YS-01A"}},{"changes":{(3,"seller"):"另一供应方"}},
                   {"changes":{(4,"acceptance_number"):"YS-01"}},{"changes":{(4,"accepted_on"):"2026-09-12"}}):
            with self.subTest(kw=kw):
                p,_=sample(**kw);f,=payments(p)
                self.assertEqual(f["retest_reference"]["state"],"unresolved")
                self.assertEqual(refs.edges(p["findings"]),[])
        p,_=sample((None,));self.assertNotIn("retest_reference",payments(p)[0])
        for field,value in (("payment_designation","设备采购款"),("transfer_status","受理中"),("payment_designation","第一期")):
            p,_=sample(changes={(6,field):value});self.assertNotIn("retest_reference",payments(p)[0])

    def test_issued_artifacts_reject_changed_sources_dates_links_and_scope(self):
        p,read=sample()
        for mode in ("line","edge","date","marker","sha","fields","scope"):
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                t=deepcopy(p);g=t["graph"];f,=payments(t);c=f["retest_reference"]
                if mode=="line":g[refs.KEY]["rows"][0]["line"]+=1
                if mode=="edge":g["edges"].pop()
                if mode=="date":c["days_from_final"]=12
                if mode=="marker":del t["policy"]["retest_reference"]
                if mode=="sha":next(v for v in g["facts"] if v["id"]==c["fields"]["final_acceptance_number"])["page_sha256"]="other"
                if mode=="fields":c["fields"]["final_acceptance_number"]=c["fields"]["original_acceptance_number"]
                if mode=="scope":f["scope"].remove(c["bank"])
                refs.verify(t,read)
        p["graph"].pop(refs.KEY);p["graph"]["edges"]=[e for e in p["graph"]["edges"] if e["type"]!=refs.EDGE]
        p["findings"]=execute(p["graph"],PERFORMANCE)
        p["policy"].update(version="2026.11.27.17");del p["policy"]["retest_reference"]
        self.assertEqual(payments(p)[0]["payment_acceptance"]["state"],"scope")
        refs.verify(p,None)
