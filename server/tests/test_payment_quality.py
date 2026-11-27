import unittest
from copy import deepcopy
from unittest.mock import patch

from config import PERFORMANCE
from controls import VERSION, execute
from graph import build_graph
from performance import verify_findings
import payment_quality as quality
from test_performance import BANK_DOC, CONTRACT, RECEIPT, material


def example(*, date="2026-09-21", standard="柜温不高于4℃", measure="柜温8℃", other=(), changes=None, omissions=()):
    texts = {}
    def build(docs,pages,*args,**kwargs):
        texts.update({(p["doc"],p["number"]):p["text"] for p in pages})
        return build_graph(docs,pages,*args,**kwargs)
    values = {"paid_on":date,"measured_result":measure,"inspection_basis":standard,"acceptance_criteria":standard}
    def edit(i,k,label,v):
        return (changes or {}).get((i,k),values.get(k,v))
    with patch("test_performance.build_graph",build):
        graph=material([CONTRACT,RECEIPT,BANK_DOC,*other],edit,omissions=omissions)
    found=execute(graph,PERFORMANCE)
    graph["edges"].extend(quality.edges(found))
    return {"graph":graph,"policy":{**VERSION,"profile":PERFORMANCE},"findings":found}, lambda d,n:texts[d,n]


class PaymentQualityEvidence(unittest.TestCase):
    def test_only_the_acceptance_installment_inherits_the_measured_breach(self):
        for when,days in (("2026-09-19",-1),("2026-09-20",0),("2026-09-21",1)):
            with self.subTest(when=when):
                p,text=example(date=when)
                checks=[f for f in p["findings"] if "payment_quality" in f]
                self.assertEqual([(c["rule"],c["stage"]["name"],c["status"]) for c in checks],[("H04","第二期","risk"),("H05","第二期","risk")])
                stage,transfer=[f["payment_quality"] for f in checks]
                self.assertNotIn("payment",stage)
                self.assertEqual((transfer["payment"]["days"],transfer["payment"]["paid_on"]),(days,when))
                self.assertEqual(stage["measure"],{"name":"柜温","unit":"°C","operator":"不高于","limit":"4","observed":"8","outside_by":"4"})
                self.assertIn("当日先后待核" if not days else ("早于" if days<0 else "晚于"),checks[-1]["detail"])
                for f in checks:
                    q=f["payment_quality"]
                    self.assertLessEqual(set(q["fields"].values()),set(q["evidence"]))
                    self.assertLessEqual(set(q["evidence"]),set(f["evidence"]))
                quality.verify(p,text)
                verify_findings(p)

    def test_minimum_decimal_negative_temperatures_and_exact_limits(self):
        p,_=example(standard="柜温不低于-2.50℃",measure="柜温-3.75℃")
        records=[f["payment_quality"] for f in p["findings"] if "payment_quality" in f]
        self.assertEqual([r["measure"]["outside_by"] for r in records],["1.25","1.25"])
        for value in ("柜温4℃","柜温3℃","柜温8mm","压力8MPa","柜温1 0℃"):
            with self.subTest(value=value):
                p,_=example(measure=value)
                self.assertFalse(quality.edges(p["findings"]))

    def test_an_unread_second_entry_or_different_transaction_cannot_supply_the_comparison(self):
        for opts,roles in [
            ({"omissions":[(2,"实测结果：柜温3℃")]},[]),
            ({"omissions":[(1,"约定验收标准：柜温不高于10℃")]},[]),
            ({"omissions":[(1,"第二期：到货后支付60%")]},[]),
            ({"changes":{(2,"seller"):"另一家单位"}},[]),
            ({"changes":{(2,"acceptance_scope"):"数量签收"}},[]),
            ({"other":[RECEIPT]},[]),
            ({"omissions":[(2,"验收日期：2026-09-18")]},["H04"]),
            ({"omissions":[(3,"交易日期：2026-09-10")]},["H04"]),
            ({"changes":{(3,"payment_designation"):"设备采购款"}},["H04"]),
            ({"changes":{(3,"payment_designation"):"第一期"}},["H04"]),
            ({"changes":{(3,"payee"):"另一家公司"}},["H04"]),
            ({"changes":{(3,"transfer_status"):"受理中"}},["H04"]),
        ]:
            with self.subTest(opts=opts):
                p,_=example(**opts)
                self.assertEqual([f["rule"] for f in p["findings"] if f.get("payment_quality")],roles)

    def test_each_successful_receipt_has_its_own_date_and_evidence(self):
        p,text=example(other=[BANK_DOC],changes={(4,"paid_on"):"2026-09-18"})
        a,b=[f["payment_quality"] for f in p["findings"] if f["rule"]=="H05"]
        self.assertEqual([(x["payment"]["bank"],x["payment"]["days"]) for x in (a,b)],[("d03",1),("d04",-2)])
        self.assertNotIn(a["fields"]["paid_on"],b["evidence"])
        quality.verify(p,text)

    def test_archive_rejects_changed_observations_edges_dates_and_methods(self):
        p,text=example()
        for mode in ("source","coordinate","sha","delta","edge","state","marker"):
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                changed=deepcopy(p)
                f=next(r for r in changed["findings"] if r["rule"]=="H05")
                measure=next(r for r in changed["graph"]["facts"] if r["id"]==f["payment_quality"]["fields"]["measured_result"])
                if mode=="source": changed["graph"][quality.KEY]["rows"][-1]["quote"]="不同的付款原行"
                if mode=="coordinate": measure["source_line"]["number"]+=1
                if mode=="sha": measure["page_sha256"]="unrelated"
                if mode=="delta": f["payment_quality"]["payment"]["days"]=5
                if mode=="edge": changed["graph"]["edges"].pop()
                if mode=="state": f["status"]="ok"
                if mode=="marker": changed["policy"].pop("payment_quality")
                quality.verify(changed,text)
        graph=p["graph"]
        graph.pop(quality.KEY)
        graph["edges"]=[e for e in graph["edges"] if e["type"]!=quality.EDGE]
        p["policy"].update(version="2026.11.27.16")
        p["policy"].pop("payment_quality")
        p["findings"]=execute(graph,PERFORMANCE)
        quality.verify(p,None)
        self.assertFalse(any("payment_quality" in f for f in p["findings"]))
