import copy
import unittest

import payment_acceptance as citations
from config import PERFORMANCE
from controls import VERSION, execute
from performance import verify_findings
from test_delivery_batches import contract, receipt
from test_performance import BANK_DOC, WARRANTY, material


CURRENCY = [("currency","币种","人民币"),("unit","金额单位","元")]
LABEL = "付款依据验收单号"


def specimen(numbers=("YS-10",), *, first=None, second=None, payer=None, omissions=(), attestations=None, uses=None):
    agreement = contract()+[("total","含税总额","100000.00"),*CURRENCY]
    groups = [agreement,first or receipt(1),second or receipt(2),WARRANTY]
    for i,code in enumerate(numbers):
        values = {"payment_designation":(uses or ["第三期"]*len(numbers))[i]}
        if payer:
            values["payer"] = payer
        bank = [(k,l,values.get(k,v)) for k,l,v in BANK_DOC]
        bank.extend([("transfer_amount","付款金额",("15000","20000")[i] if len(numbers)==2 else "35000"),
                     ("transfer_ref","交易流水号",f"TR-00{i+1}"),*CURRENCY])
        if code is not None:
            bank.append((citations.FIELD,LABEL,code))
        groups.append(bank)
    graph = material(groups,omissions=omissions,attestations=attestations)
    def read(doc,page):
        index = int(doc[1:])
        return "\n".join([lab+"："+v if lab else v for k,lab,v in groups[index-1]]
                         +[line for unit,line in omissions if unit==index])
    return graph,read


def findings(graph):
    return execute(graph,PERFORMANCE)


def transfers(graph):
    return [f for f in findings(graph) if f["rule"]=="H05"]


class PaymentAcceptanceTests(unittest.TestCase):
    def test_compares_the_printed_number_to_the_required_batch_despite_equal_shares(self):
        for code,state,status in (("YS-10","other_batch","risk"),("YS-20","matched","ok"),("YS-99","unlocated","missing"),
                                  ("ys-20","unlocated","missing"),("YS-**20","reference","missing")):
            with self.subTest(code=code):
                g,_ = specimen((code,))
                f, = transfers(g)
                item = f["payment_acceptance"]
                self.assertEqual((item["state"],item["status"],f["status"]),(state,status,status))
                self.assertEqual(item["expected"],["d03"])
                self.assertEqual(item["batch"],2)
                self.assertTrue(set([item["allocation_ref"],item["designation_ref"],item["clause_ref"],*item["citations"]])<=set(f["evidence"]))
                self.assertTrue(all(r["scope_ref"] in f["evidence"] and r["number_row"] in f["evidence"] and
                                    set(r["identity_refs"])<=set(f["evidence"]) for r in item["register"]))
                self.assertTrue(all(f["status"]=="ok" for f in findings(g) if f["rule"] in ("H02","H04")))

    def test_exact_native_line_survives_extraction_omission_and_ordinary_banks_are_unchanged(self):
        g,_=specimen((None,),omissions=[(5,LABEL+"：YS-10")])
        check=transfers(g)[0]["payment_acceptance"]
        raw=next(r for r in g[citations.GRAPH_KEY]["rows"] if r["id"] in check["citations"])
        self.assertEqual((check["state"],len(raw["facts"])),("other_batch",0))
        self.assertTrue(any(e["to"]==raw["id"] and e["from"]=="d05/p1" for e in g["edges"]))
        g,_=specimen((None,))
        self.assertNotIn("payment_acceptance",transfers(g)[0])
        self.assertFalse(g[citations.GRAPH_KEY]["pages"])

    def test_duplicate_unknown_disputed_and_incomplete_sources_stay_open(self):
        def replace_number(code):
            return [(k,l,code if k=="acceptance_number" else v) for k,l,v in receipt(2)]
        for options in ({"second":replace_number("YS-10")},{"payer":"演练丙"},{"uses":["预付款"]},
                        {"omissions":[(5,LABEL+"：YS-20")]},{"omissions":[(5,"展示说明：只显示末两位")]},
                        {"omissions":[(5,"或见第一批")]},{"second":replace_number("YS-XX20")}):
            with self.subTest(options=options):
                g,_=specimen(**options)
                self.assertEqual(transfers(g)[0]["payment_acceptance"]["status"],"missing")
        graph,read=specimen()
        node=next(n for n in graph["nodes"] if n["id"]=="d05/p1")
        node["clause_text_only"]=False
        graph[citations.GRAPH_KEY]=citations.sources(graph,read)
        self.assertEqual(transfers(graph)[0]["payment_acceptance"]["state"],"source")
        graph,read=specimen()
        f=next(f for f in graph["facts"] if f["field"]==citations.FIELD)
        f["status"]="disputed"
        graph[citations.GRAPH_KEY]=citations.sources(graph,read)
        self.assertEqual(transfers(graph)[0]["payment_acceptance"]["state"],"source")

    def test_split_transfers_keep_separate_citations_and_arithmetic(self):
        graph,_=specimen(("YS-10","YS-20"))
        wrong,right=transfers(graph)
        self.assertEqual([f["payment_acceptance"]["state"] for f in (wrong,right)],["other_batch","matched"])
        self.assertNotIn("d05",right["scope"])
        self.assertNotIn("d06",wrong["scope"])
        group,=[f for f in findings(graph) if f["rule"]=="H06"]
        item=group["stage_payments"]
        self.assertEqual((group["status"],item["state"],item["seen"],item["difference"]),("risk","balanced","35000.00","0.00"))
        self.assertEqual([t["status"] for t in item["timing"]],["risk","ok"])

    def test_archive_replay_and_legacy_signoff_use_physical_sources(self):
        graph,read=specimen()
        paper={"graph":graph,"policy":{**VERSION,"profile":PERFORMANCE},"findings":findings(graph)}
        citations.verify(paper,read);verify_findings(paper)
        for side in ("node","edge","row","conclusion"):
            forged=copy.deepcopy(paper);g=forged["graph"]
            if side=="node":
                next(n for n in g["nodes"] if n["type"]=="payment_acceptance_line")["label"]="YS-20"
            if side=="edge":
                g["edges"]=[e for e in g["edges"] if e["type"]!="payment_acceptance_source"]
            if side=="row":
                g[citations.GRAPH_KEY]["rows"][-1]["quote"]=LABEL+"：YS-20"
            if side=="conclusion":
                next(f for f in forged["findings"] if f["rule"]=="H05")["payment_acceptance"]["state"]="matched"
            with self.subTest(side=side),self.assertRaises(ValueError):
                citations.verify(forged,read);verify_findings(forged)
        graph.pop(citations.GRAPH_KEY)
        graph["nodes"]=[n for n in graph["nodes"] if n["type"]!="payment_acceptance_line"]
        graph["edges"]=[e for e in graph["edges"] if e["type"]!="payment_acceptance_source"]
        legacy={"policy":{"version":"2026.11.26.19"},"graph":graph,"findings":findings(graph)}
        citations.verify(legacy,read)
        with self.assertRaisesRegex(ValueError,"重新审计"):
            citations.verify(legacy,read,signing=True)
