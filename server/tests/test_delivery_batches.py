import copy
import unittest

from controls import VERSION, execute
from delivery_batches import LEGACY, evidence_edges, gaps, page_sources, verify_sources
from performance import BATCH_FORMAT, DATE_FORMAT, compute, verify_findings
from test_performance import CONTRACT, RECEIPT, WARRANTY, BANK_DOC, material


RULE="各批独立验收付款，全部批次验收合格视为终验合格"
PLAN=[("payment_term","付款条款","分四期付款"),("payment_stage","第一期","合同生效后支付20%"),
      ("payment_stage","第二期","第一批验收合格后支付35%"),("payment_stage","第三期","第二批验收合格后支付35%"),
      ("payment_stage","第四期","质保期满后支付10%")]
ORIGINAL={1:"第一批",2:"第二批"}
NAMED=["第一批验收须由周宁签字确认","第二批验收须由林岚、何平共同签字确认"]


def named_receipt(index,names):
    return [r for r in receipt(index) if r[0]!="acceptance_signer"]+[
        ("acceptance_signer","验收签认",name+"（已签字）") for name in names]


def named_case(second=("林岚","何平"),clauses=NAMED,common=False,**kwargs):
    c=contract()+[("acceptance_signing_clause","验收签认约定",clause) for clause in clauses]
    records=[named_receipt(1,("周宁","林岚") if common else ("周宁",))]
    if second is not None:
        records.append(named_receipt(2,second))
    return sample(records,c,**kwargs)


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
    def test_named_and_joint_signatures_are_compared_with_only_their_own_batch(self):
        for names,overall,third,last,edges in ((("林岚","何平"),"ok","ok","ok",3),(("林岚",),"missing","missing","missing",1),
                (("林岚","吴松"),"risk","risk","risk",1),(("林岚","何平","何平"),"missing","missing","missing",1),
                (("林岚、何平",),"missing","missing","missing",1),(None,"missing","missing","missing",1)):
            with self.subTest(names=names):
                g=named_case(names)
                h,ps,paid=states(g)
                self.assertEqual((h["status"],[p["status"] for p in ps],paid["status"]),(overall,["ok","ok",third,last],"ok"))
                batches=h["batch_acceptance"]["batches"]
                self.assertEqual(batches[1]["signing_requirement"]["required"],["林岚","何平"])
                self.assertNotIn(batches[1]["signing_requirement"]["clause_ref"],ps[1]["evidence"])
                if names:
                    rec=h["batch_acceptance"]["records"][1]
                    self.assertNotIn(rec["unit"],ps[1]["scope"])
                    self.assertEqual(rec["signing"]["other_names"],["吴松"] if "吴松" in names else [])
                witnesses=[e for e in evidence_edges([h,*ps]) if e["type"]=="batch_named_signature"]
                self.assertEqual(len(witnesses),edges)
                self.assertTrue(all(e["from"] in e["evidence"] and e["to"] in e["evidence"] for e in witnesses))
        both=named_case(("周宁","林岚"),["各批验收均须由周宁、林岚共同签字确认"],common=True)
        h,ps,_=states(both)
        self.assertEqual([f["status"] for f in ps],["ok"]*4)
        self.assertEqual(len([e for e in evidence_edges([h,*ps]) if e["type"]=="batch_named_signature"]),4)
        g=named_case(edit=lambda i,f,l,v:"柜温8℃" if i==3 and f=="measured_result" else v)
        h,ps,paid=states(g)
        self.assertEqual((h["status"],[p["status"] for p in ps],paid["status"]),("issue",["ok","ok","risk","risk"],"ok"))
        self.assertEqual(h["batch_acceptance"]["records"][1]["signing"]["status"],"ok")
        for field,value in (("buyer","另一采购方"),("accepted_on","2026-09-01")):
            g=named_case(edit=lambda i,f,l,v:value if i==3 and f==field else v)
            h,ps,_=states(g)
            other=h["batch_acceptance"]["records"][1]
            self.assertEqual((other["signing"]["status"],ps[1]["status"],ps[2]["status"]),("missing","ok","missing"))
            self.assertFalse(any(e["type"]=="batch_named_signature" and e["to"].startswith(other["unit"]+"/")
                                 for e in evidence_edges([h,*ps])))

    def test_batch_signing_requires_complete_native_terms_and_separate_confirmed_signatures(self):
        for clauses in ([NAMED[0]], [*NAMED,NAMED[1]], [*NAMED,"终验须由何平签字确认"],
                [NAMED[0],"第二批验收须由林岚或何平签字确认"],[NAMED[0],"第二批验收须由验收负责人签字确认"],
                [NAMED[0],"第二批验收须由林 岚签字确认"], [NAMED[0],"第二批验收须由同上签字确认"]):
            with self.subTest(clauses=clauses):
                h,ps,_=states(named_case(clauses=clauses))
                self.assertNotEqual(h["status"],"ok")
                self.assertFalse(any("signing_requirement" in b for b in h["batch_acceptance"]["batches"]))
                self.assertTrue(all(p["status"]!="ok" for p in ps[1:]))
        for unit,line in ((1,"另列条件：第二批验收另须监理代表会签"),(3,"签认附注：两份验收记录均属代签")):
            h,ps,_=states(named_case(omissions=[(unit,line)]))
            self.assertNotEqual(h["status"],"ok")
            self.assertNotEqual(ps[1]["status"],"ok")
        from test_acceptance_authority import reconstruct
        g=reconstruct(named_case(),lambda item:not(item[0]=="d03" and "何平" in item[1]["quote"]))
        h,ps,paid=states(g)
        self.assertEqual((h["status"],ps[1]["status"],ps[2]["status"],paid["status"]),("missing","ok","missing","ok"))
        self.assertEqual(h["batch_acceptance"]["records"][1]["signing"]["missing_names"],["何平"])
        g=named_case(("林岚",),omissions=[(3,"验收签认：何平（已签字）")])
        h,ps,paid=states(g)
        signing=h["batch_acceptance"]["records"][1]["signing"]
        raw=next(row for row in signing["signed"] if row["name"]=="何平")
        self.assertTrue(raw["line"] and raw["native"] and not raw["facts"] and not raw["confirmed"])
        self.assertEqual((signing["missing_names"],ps[1]["status"],ps[2]["status"],paid["status"]),(["何平"],"ok","missing","ok"))

    def test_named_batch_signatures_replay_with_originals_and_versioned_scope(self):
        g=named_case()
        fs=execute(g,g["profile"])
        g["edges"].extend(evidence_edges(fs))
        p={"graph":g,"findings":fs,"policy":{**VERSION,"profile":g["profile"]}}
        texts={d["id"]:"\n".join(f["quote"] for f in g["facts"] if f["doc"]==d["id"]) for d in g["documents"]}
        read=lambda d,n:texts[d]
        verify_sources(p,read)
        verify_findings(p)
        for part in ("edge","names","signer","version"):
            altered=copy.deepcopy(p)
            h=next(f for f in altered["findings"] if f["rule"]=="H02")
            if part=="edge":
                next(e for e in altered["graph"]["edges"] if e["type"]=="batch_named_signature")["to"]="d03/p1/f1"
            elif part=="names":
                h["batch_acceptance"]["batches"][1]["signing_requirement"]["required"]=["吴松"]
            elif part=="signer":
                h["batch_acceptance"]["records"][1]["signing"]["signed"][1]["confirmed"]=False
            else:
                altered["policy"]["delivery_batches"]=LEGACY
            with self.assertRaises(ValueError):
                verify_sources(altered,read) if part in ("edge","version") else verify_findings(altered)
        g["delivery_batch_sources"]=page_sources(g,read,LEGACY)
        g["gaps"]=[r for r in g["gaps"] if r["quality"]!="delivery_batch_clause"]+gaps(g["delivery_batch_sources"])
        g["edges"]=[e for e in g["edges"] if e["type"] not in ("batch_named_signature","delivery_batch_acceptance","batch_payment_basis")]
        legacy={**VERSION,"version":"2026.11.25.06","delivery_batches":LEGACY,"profile":g["profile"]}
        self.assertTrue(all(f["status"]=="missing" for f in states(g)[1]))
        verify_sources({"policy":legacy,"graph":g,"findings":compute(g)},read)

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
