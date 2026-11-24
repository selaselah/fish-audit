import copy
import unittest

from controls import VERSION, execute
from delivery_batches import FINAL_REFS, SIGNING_FORMAT, evidence_edges, gaps, page_sources, verify_sources
from performance import compute, verify_findings
from test_delivery_batches import NAMED, RULE, contract, named_receipt, receipt, states
from test_performance import APPROVAL, BANK_DOC, RECEIPT, WARRANTY, material


SEPARATE = "各批独立验收付款，另行组织最终验收"
TERMS = [("warranty_period","质保期限","自终验合格之日起2个月，届满日不顺延"),
         ("warranty_condition","质保金返还条件","质保期满且无未关闭缺陷")]


def changed(rows, **values):
    return [(k,label,values.get(k,value)) for k,label,value in rows if values.get(k,value) is not None]


def final_record(**values):
    return changed([*changed(RECEIPT,accepted_on="2026-09-25"),("acceptance_number","验收单编号","ZY-30"),
                    ("delivered_serials","验收设备编号","E-11、E-12、E-21、E-22"),(FINAL_REFS,"所附批次验收单号","YS-10、YS-20")],**values)


def packet(*, batches=None, finals=None, agreement=None, paid="2026-11-27", omissions=(), supporting=()):
    agreement=contract(SEPARATE) if agreement is None else agreement
    batches=[receipt(1),receipt(2)] if batches is None else batches
    finals=[final_record()] if finals is None else finals
    warranty=changed(WARRANTY,warranty_release="2026-11-26双方确认质保期已满")+[("warranty_defects","质保遗留事项","无未关闭缺陷")]
    bank=changed(BANK_DOC,payment_designation="第四期",paid_on=paid)
    return material([[*agreement,*TERMS],*batches,*finals,warranty,bank,*supporting],omissions=omissions)


class BatchFinalTests(unittest.TestCase):
    def test_whole_delivery_reuses_equipment_only_as_an_express_final_and_starts_warranty(self):
        for order,paid,actual in (("YS-10、YS-20","2026-11-27","ok"),("YS-20、YS-10","2026-11-22","risk")):
            graph=packet(finals=[final_record(batch_receipt_refs=order)],paid=paid)
            h,phases,cash=states(graph)
            batch=h["batch_acceptance"]
            self.assertFalse(batch["deemed_final"])
            self.assertEqual((h["status"],batch["completion_on"],cash["status"]),("ok","2026-09-25",actual))
            self.assertEqual([p["status"] for p in phases],["ok"]*4)
            self.assertNotIn("d04",phases[1]["scope"]+phases[2]["scope"])
            warranty=phases[3]["warranty_check"]
            self.assertEqual([warranty[k] for k in ("accepted_on","calendar_end","confirmed_on")],["2026-09-25","2026-11-25","2026-11-26"])
            edges=[e for e in evidence_edges([h,*phases]) if e["type"]=="batch_final_basis"]
            facts={f["id"]:f for f in graph["facts"]}
            self.assertEqual([facts[e["to"]]["value"] for e in edges],["YS-10","YS-20"])
            self.assertTrue(all(facts[e["from"]]["value"]==order and e["from"] in e["evidence"] and e["to"] in e["evidence"] for e in edges))
        without_ids=packet(agreement=contract(SEPARATE,False),batches=[receipt(1,False),receipt(2,False)],
                           finals=[final_record(delivered_serials=None)])
        self.assertEqual(states(without_ids)[0]["status"],"ok")

    def test_final_references_quantity_dates_quality_and_signature_are_independently_tested(self):
        for edits,status,reason in (
            ({"batch_receipt_refs":None},"missing","单号"),({"batch_receipt_refs":"YS-10、YS-200"},"risk","YS-200"),
            ({"batch_receipt_refs":"YS-10、YS-10、YS-20"},"risk","重复"),({"quantity_accepted":"3台"},"risk","个数"),
            ({"quantity_accepted":"4套"},"risk","计量单位"),({"delivered_serials":None},"missing","清单"),
            ({"delivered_serials":"E-11、E-12、E-21、E-29"},"risk","设备编号"),({"accepted_on":"2026-09-18"},"risk","末批"),
            ({"accepted_on":"2026-09-20"},"missing","同一天"),({"acceptance_signer":None},"missing","核图"),
            ({"inspection_basis":"柜温不高于9℃","measured_result":"柜温8℃"},"issue","超出"),
            ({"acceptance_exception":"两台温控不稳"},"risk","遗留事项")):
            with self.subTest(edits=edits):
                h,phases,cash=states(packet(finals=[final_record(**edits)]))
                batch=h["batch_acceptance"]
                self.assertEqual((h["status"],batch["separate_final"]["status"],batch["completion_on"]),(status,status,None))
                self.assertIn(reason,batch["separate_final"]["detail"])
                self.assertEqual([p["status"] for p in phases[:3]],["ok"]*3)
                self.assertNotEqual(cash["status"],"ok")
                self.assertFalse(any(e["type"]=="batch_final_basis" for e in evidence_edges([h,*phases])))

    def test_missing_observation_never_creates_a_link_and_unknown_riders_hold_dependent_payments(self):
        raw="所附批次验收单号：YS-10、YS-20"
        g=packet(finals=[final_record(batch_receipt_refs=None)],omissions=[(4,raw)])
        h,phases,_=states(g)
        self.assertEqual([p["status"] for p in phases],["ok","ok","ok","missing"])
        self.assertIn("未经逐行核对",h["detail"])
        self.assertTrue(any(p["unit"]=="d04" and raw in [l["quote"] for l in p["uncovered"]] for p in g["delivery_batch_sources"]["pages"]))
        for line in ("附注：尚须监理书面确认","批注：暂停全部付款"):
            h,phases,_=states(packet(omissions=[(4,line)]))
            self.assertEqual([p["status"] for p in phases],["missing"]*4)
            self.assertFalse(h["batch_acceptance"]["completion_on"])
        for malformed in ("YS-1 0、YS-20","YS-**、YS-20"):
            h,phases,_=states(packet(finals=[final_record(batch_receipt_refs=malformed)]))
            self.assertNotEqual(h["status"],"ok")
            self.assertFalse(any(e["type"]=="batch_final_basis" for e in evidence_edges([h,*phases])))
        graph=packet()
        next(f for f in graph["facts"] if f["field"]==FINAL_REFS)["value"]="YS-1 0、YS-20"
        self.assertEqual(states(graph)[0]["status"],"missing")

    def test_identity_versions_prior_batches_and_clause_scope_must_agree(self):
        h,ps,_=states(packet(finals=[]))
        self.assertEqual((h["batch_acceptance"]["separate_final"]["records"],[p["status"] for p in ps]),([],["ok","ok","ok","missing"]))
        for finals in ([final_record(),final_record(acceptance_number="ZY-31")],[final_record(acceptance_number="YS-10")],
                      [final_record(buyer="另一采购方")],[final_record(acceptance_scope="全部")]):
            h,ps,_=states(packet(finals=finals))
            self.assertNotEqual(h["status"],"ok")
            self.assertNotEqual(ps[1]["status"],"ok")
        for clause in (RULE,"各批独立验收付款"):
            h,_,_=states(packet(agreement=contract(clause)))
            self.assertNotIn("separate_final",h["batch_acceptance"])
            self.assertFalse(h["batch_acceptance"]["completion_on"])
        h,phases,_=states(packet(batches=[receipt(1)]))
        self.assertEqual([p["status"] for p in phases],["ok","ok","missing","missing"])
        self.assertFalse(h["batch_acceptance"]["completion_on"])
        h,phases,_=states(packet(agreement=contract(SEPARATE)+[("acceptance_signing_clause","验收签认约定",v) for v in NAMED],
                                 batches=[named_receipt(1,["周宁"]),named_receipt(2,["林岚","何平"])]))
        self.assertIn("终验的签认权限",h["detail"])
        self.assertEqual([p["status"] for p in phases],["ok","ok","ok","missing"])

    def test_signed_final_and_full_payment_still_require_the_contracts_own_approval(self):
        agreement=changed(contract(SEPARATE),effect_clause="本合同自双方盖章并经甲方董事会批准后生效")
        for supporting,condition in (([],"missing"),([changed(APPROVAL,approval_result="退回补议")],"risk"),([APPROVAL],"ok")):
            with self.subTest(condition=condition):
                fs=compute(packet(agreement=agreement,supporting=supporting))
                signed=next(f for f in fs if f["rule"]=="H01")
                h=next(f for f in fs if f["rule"]=="H02")
                ps=[f["status"] for f in fs if f["rule"]=="H04"]
                cash=next(f for f in fs if f["rule"]=="H05")
                self.assertEqual(signed["status"],condition)
                self.assertEqual(len(ps),4)
                if condition=="ok":
                    self.assertEqual((h["batch_acceptance"]["completion_on"],ps),("2026-09-25",["ok"]*4))
                    self.assertEqual(cash["status"],"ok")
                else:
                    self.assertIsNone(h["batch_acceptance"]["completion_on"])
                    self.assertNotIn("ok",ps)
                    self.assertNotEqual(cash["status"],"ok")

    def test_verifier_replays_the_native_reference_list_and_each_original_endpoint(self):
        g=packet()
        read=lambda doc,page:"\n".join(f["quote"] for f in g["facts"] if f["doc"]==doc)
        fs=execute(g,g["profile"])
        g["edges"].extend(evidence_edges(fs))
        report={"policy":{**VERSION,"profile":g["profile"]},"graph":g,"findings":fs}
        verify_sources(report,read)
        verify_findings(report)
        for change in ("endpoint","date","basis","marker","raw"):
            altered=copy.deepcopy(report)
            batch=next(f["batch_acceptance"] for f in altered["findings"] if "batch_acceptance" in f)
            if change=="endpoint":
                next(e for e in altered["graph"]["edges"] if e["type"]=="batch_final_basis")["to"]="d04/p1/f1"
            elif change=="date":
                batch["completion_on"]="2026-09-20"
            elif change=="basis":
                batch["separate_final"]["basis"][0]["number"]="YS-200"
            elif change=="marker":
                altered["policy"]["delivery_batches"]=SIGNING_FORMAT
            else:
                next(e for e in altered["graph"]["edges"] if e["type"]==FINAL_REFS)["from"]="d02"
            with self.assertRaises(ValueError):
                verify_findings(altered) if change in ("date","basis") else verify_sources(altered,read)
        g["delivery_batch_sources"]=page_sources(g,read,SIGNING_FORMAT)
        g["gaps"]=[item for item in g["gaps"] if item["quality"]!="delivery_batch_clause"]+gaps(g["delivery_batch_sources"])
        legacy=compute(g)
        self.assertNotIn("separate_final",next(f["batch_acceptance"] for f in legacy if f["rule"]=="H02"))
        self.assertEqual([f["status"] for f in legacy if f["rule"]=="H04"],["ok","risk","risk","risk"])
