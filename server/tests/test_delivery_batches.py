import copy
import unittest

from controls import VERSION, execute
from delivery_batches import evidence_edges, verify_sources
from performance import BATCH_FORMAT, DATE_FORMAT, compute, verify_findings
from test_performance import CONTRACT, RECEIPT, WARRANTY, BANK_DOC, material


RULE="各批独立验收付款，全部批次验收合格视为终验合格"
PLAN=[("payment_term","付款条款","分四期付款"),("payment_stage","第一期","合同生效后支付20%"),
      ("payment_stage","第二期","第一批验收合格后支付35%"),("payment_stage","第三期","第二批验收合格后支付35%"),
      ("payment_stage","第四期","质保期满后支付10%")]
ORIGINAL={1:"第一批",2:"第二批"}


def contract(rule=RULE,with_serials=True):
    rows=[f for f in CONTRACT if f[0] not in ("payment_term","payment_stage")]
    rows+=[("delivery_batch","分批交付",f"{name}2台"+(f"，设备编号 E-{i}1、E-{i}2" if with_serials else "")) for i,name in ORIGINAL.items()]
    return [*rows,("batch_clause","分批验收约定",rule),*PLAN]


def receipt(i,with_serials=True):
    changes={"acceptance_scope":ORIGINAL[i]+"交付验收","quantity_accepted":"2台","accepted_on":f"2026-09-{10*i}"}
    return [(f,l,changes.get(f,v)) for f,l,v in RECEIPT]+[("acceptance_number","验收单编号",f"YS-{i}0")]+(
            [("delivered_serials","验收设备编号",f"E-{i}1、E-{i}2")] if with_serials else [])


def sample(receipts=None,c=None,edit=None,**kwargs):
    return material([contract() if c is None else c,*(receipts if receipts is not None else [receipt(1),receipt(2)]),WARRANTY,BANK_DOC],edit,**kwargs)


def states(graph):
    fs=compute(graph)
    get=lambda k:next(f for f in fs if f["rule"]==k)
    return get("H02"),[f for f in fs if f["rule"]=="H04"],get("H05")


class DeliveryBatchTests(unittest.TestCase):
    def test_independent_receipts_cover_whole_only_with_express_terms(self):
        for with_serials in (True,False):
            g=sample([receipt(2,with_serials),receipt(1,with_serials)],contract(with_serials=with_serials))
            h,phases,paid=states(g)
            batch=h["batch_acceptance"]
            self.assertEqual((h["status"],batch["completion_on"],paid["status"]),("ok","2026-09-20","ok"),h)
            self.assertEqual([p["status"] for p in phases],["ok"]*4)
            self.assertEqual([r["index"] for r in batch["batches"]],[1,2])
            self.assertEqual(phases[1]["stage"]["batch_date"],"2026-09-10")
            self.assertNotIn("d02",phases[1]["scope"])
            self.assertNotIn("d03",phases[2]["scope"])
            self.assertEqual(len(evidence_edges([h,*phases])),4)
        h,ps,paid=states(sample(c=contract("各批独立验收付款，另行组织最终验收")))
        self.assertEqual((h["status"],[p["status"] for p in ps],paid["status"]),("missing",["ok","ok","ok","missing"],"ok"))

    def test_first_batch_payment_remains_supported_with_missing_or_failed_second(self):
        for second,status,overall in (([], "missing","missing"),([receipt(2)],"risk","issue")):
            g=sample([receipt(1),*second],edit=lambda i,f,l,v:"柜温8℃" if i==3 and f=="measured_result" else v)
            h,phases,paid=states(g)
            self.assertEqual((h["status"],[p["status"] for p in phases],paid["status"]),(overall,["ok","ok",status,status],"ok"),h)
            self.assertIsNone(h["batch_acceptance"]["completion_on"])
            self.assertEqual(len(evidence_edges([h,*phases])),2)

    def test_cross_batch_identity_quantity_and_version_conflicts(self):
        for field,value,out in (("delivered_serials","E-11、E-12",["risk","risk"]),
            ("acceptance_number","YS-10",["risk","risk"]),("delivered_serials","E-30、E-40",["ok","risk"]),
            ("quantity_accepted","2箱",["ok","risk"]),("contract_id","YL-999",["ok","missing"]),
            ("quantity_accepted","3台",["ok","risk"]),("acceptance_exception",None,["ok","missing"]),
            ("acceptance_scope","第一批交付验收",["risk","missing"]),("acceptance_scope","到货初验",["missing","missing"]),
            ("delivered_serials",None,["ok","missing"])):
            with self.subTest(field=field,value=value):
                g=sample(edit=lambda i,f,l,v:value if i==3 and f==field else v)
                h,ps,_=states(g)
                self.assertEqual([p["status"] for p in ps[1:3]],out,h)
                self.assertNotEqual(h["status"],"ok")
                if field in ("delivered_serials","acceptance_number") and out==["risk","risk"]:
                    self.assertTrue({"d02","d03"}<=set(ps[1]["scope"]))

    def test_scope_riders_and_separate_preconditions(self):
        for value in ("各批全部验收后统一付款","各批独立验收付款，另须履约保函"):
            h,phases,_=states(sample(c=contract(value)))
            self.assertNotEqual(h["status"],"ok")
            self.assertTrue(all(p["status"]!="ok" for p in phases))
        h,phases,_=states(sample(omissions=[(1,"附注：第一期付款前须经甲方财务总监批准")]))
        self.assertTrue(all(p["status"]!="ok" for p in phases))
        self.assertFalse(h["batch_acceptance"]["contract_clear"])
        g=sample(omissions=[(3,"附注：本次为暂收，质量待验")])
        self.assertEqual([p["status"] for p in states(g)[1]],["ok","ok","missing","missing"])
        g=sample(omissions=[(3,"附注：第一批验收记录作废，款项暂停")])
        self.assertEqual([p["status"] for p in states(g)[1]],["ok","missing","missing","missing"])
        self.assertIn("d03",states(g)[1][1]["scope"])
        g=sample(omissions=[(3,"附注：第一期预付款另须银行保函")])
        self.assertTrue(all(p["status"]=="missing" and "d03" in p["scope"] for p in states(g)[1]))
        g=sample(omissions=[(3,"附注：原合同已解除")])
        self.assertEqual(next(f["status"] for f in compute(g) if f["rule"]=="H01"),"missing")

    def test_date_and_measured_defects_follow_their_own_batch(self):
        g=sample(edit=lambda i,f,l,v:"2026-09-12" if f=="effect_on" else v)
        self.assertEqual([p["status"] for p in states(g)[1]],["ok","risk","ok","risk"])
        g=sample(edit=lambda i,f,l,v:{"inspection_basis":"柜温不高于9℃","measured_result":"柜温8℃"}.get(f,v) if i==3 else v)
        h,phases,_=states(g)
        self.assertIn("8°C",h["batch_acceptance"]["batches"][1]["detail"])
        self.assertEqual([p["status"] for p in phases],["ok","ok","risk","risk"])

    def test_spaces_after_printed_serial_label_and_inside_serial_are_distinct(self):
        graph=sample()
        fact=next(f for f in graph["facts"] if f["field"]=="delivery_batch")
        fact["quote"]=fact["quote"].replace("编号 E","编号E")
        self.assertEqual(states(graph)[0]["status"],"ok")
        self.assertNotEqual(next(f for f in compute(graph,BATCH_FORMAT) if f["rule"]=="H02")["status"],"ok")
        fact["source_line"]["text"]=fact["source_line"]["text"].replace("E-11","E-1 1")
        self.assertNotEqual(states(graph)[0]["status"],"ok")
        graph=sample()
        fact=next(f for f in graph["facts"] if f["field"]=="delivered_serials")
        fact["quote"]=fact["quote"].replace("、","、 ")
        self.assertEqual(states(graph)[0]["status"],"ok")
        self.assertNotEqual(next(f for f in compute(graph,BATCH_FORMAT) if f["rule"]=="H02")["status"],"ok")

    def test_payment_uses_only_its_batch_date_and_identity(self):
        for designation,paid,expected in (("第二期","2026-09-15","ok"),("第三期","2026-09-15","risk"),
                ("第二期","2026-09-10","missing"),("货款","2026-09-15","missing")):
            g=sample(edit=lambda i,f,l,v:{"paid_on":paid,"payment_designation":designation}.get(f,v))
            payment=states(g)[2]
            self.assertEqual(payment["status"],expected,payment)
            if designation=="第二期":
                self.assertNotIn("d03",payment["scope"])
            if paid=="2026-09-10":
                self.assertIn("第1批验收",payment["detail"])

    def test_replay_checks_source_ledger_and_each_edge(self):
        g=sample()
        fs=execute(g,g["profile"])
        g["edges"].extend(evidence_edges(fs))
        p={"graph":g,"findings":fs,"policy":{**VERSION,"profile":g["profile"]}}
        texts={d["id"]:"\n".join(f["quote"] for f in g["facts"] if f["doc"]==d["id"]) for d in g["documents"]}
        read=lambda d,n:texts[d]
        verify_findings(p)
        verify_sources(p,read)
        for kind in ("source","edge","raw","row","stage","method"):
            altered=copy.deepcopy(p)
            if kind=="source": altered["graph"]["delivery_batch_sources"]["signals"][0]["quote"]="已收货"
            elif kind=="edge": altered["graph"]["edges"].pop()
            elif kind=="raw": next(e for e in altered["graph"]["edges"] if e["type"]=="delivery_batch")["to"]="d04"
            elif kind=="row": next(f for f in altered["findings"] if f["rule"]=="H02")["batch_acceptance"]["completion_on"]=None
            elif kind=="stage": next(f for f in altered["findings"] if f.get("stage",{}).get("batch_index")==1)["stage"]["batch_index"]=2
            else: del altered["policy"]["delivery_batches"]
            with self.assertRaises(ValueError):
                verify_findings(altered) if kind in ("row","stage") else verify_sources(altered,read)
        self.assertNotEqual(next(f for f in compute(g,DATE_FORMAT) if f["rule"]=="H02")["status"],"ok")
