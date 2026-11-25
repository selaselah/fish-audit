import copy
import unittest

from controls import VERSION
from equipment_models import edges, verify
from performance import verify_findings
from test_equipment_models import ORDER, findings, received
from test_performance import BANK_DOC, CONTRACT, WARRANTY, material
from test_reinspection import FINAL, FIX, OLD


SENT = "C2-01、C2-02、C2-03、C2-04"
GOT = "C4-01、C4-02、C4-03、C4-04"
FORM = [("equipment_exchange","","设备换货交接单"),*CONTRACT[1:5],
        ("exchange_number","交接单编号","HH-001"),("original_acceptance","原验收单编号","YS-01"),
        ("exchange_on","交接日期","2026-09-24"),("exchange_old_model","退回型号","YL-C2"),
        ("exchange_old_serials","退回设备编号",SENT),("exchange_new_model","换入型号","YL-C4"),
        ("exchange_new_serials","换入设备编号",GOT),("exchange_status","交接状态","旧机已退回，新机已交付"),
        *[row for row in CONTRACT if row[0] in ("buyer_signature","seller_signature")]]
INITIAL = OLD+[received("YL-C2"),("delivered_serials","验收设备编号",SENT)]
RETEST = FINAL+[received("YL-C4"),("delivered_serials","验收设备编号",GOT),("exchange_number","所据换货交接单号","HH-001")]


def packet(exchange=FORM, *, initial=INITIAL, final=RETEST, contract=CONTRACT, extra=(), edit=None, omissions=(), attestations=None):
    bank=[(f,l,"2026-09-27" if f=="paid_on" else v) for f,l,v in BANK_DOC]
    return material([contract+[ORDER],initial,FIX,final,WARRANTY,bank,*([exchange] if exchange else []),*extra],
                    edit=edit,omissions=omissions,attestations=attestations)


class EquipmentExchangeTests(unittest.TestCase):
    def test_disputed_model_blocks_closure_even_when_handover_lists_correspond(self):
        originals = packet()
        for doc in ("d02", "d04"):
            fact = next(f for f in originals["facts"] if f["doc"]==doc and f["field"]=="equipment_model")
            graph = packet(attestations={fact["id"]: {"decision": "dispute", "note": "合成异议"}})
            inspection, phases, checks = findings(graph)
            model = inspection["equipment_models"]
            row = next(r for r in model["records"] if r["unit"]==doc)
            self.assertEqual(row["comparison"], "unresolved")
            self.assertEqual(inspection["reinspection"]["state"], "open")
            self.assertEqual(model["exchange"]["status"], "risk")
            self.assertNotEqual(next(c for c in model["exchange"]["checks"] if c["key"]=="models")["status"], "ok")
            self.assertTrue(all(c["status"]=="ok" for c in model["exchange"]["checks"] if c["key"] in ("returned","received")))
            self.assertEqual([s["status"]=="ok" for s in phases], [True,False,False])
            self.assertFalse(any(e["to"]==doc+"/p1" for e in edges(checks) if e["type"]=="equipment_model_comparison"))

    def test_signed_exchange_reconciles_both_inventories_and_unlocks_final_inspection(self):
        g=packet()
        accepted,stages,checks=findings(g)
        models=accepted["equipment_models"]
        self.assertEqual(accepted["status"],"ok",[(c["key"],c["detail"]) for c in models["exchange"]["checks"] if c["status"]!="ok"])
        self.assertEqual(models["sequence"]["outcome"],"replacement_verified")
        self.assertEqual(accepted["reinspection"]["state"],"closed")
        self.assertTrue(all(s["status"]=="ok" for s in stages))
        exchange_edges=[e for e in edges(checks) if e["type"].startswith("equipment_exchange_")]
        self.assertEqual([(e["from"],e["to"],e["status"]) for e in exchange_edges],[("d02/p1","d07/p1","ok"),("d07/p1","d04/p1","ok")])
        self.assertIn("d07/p1",stages[1]["evidence"])
        self.assertNotIn("d07/p1",stages[0]["evidence"])
        for kind,value,key in (("exchange_new_serials","C4-01、C4-02、C4-03、C4-44","received"),
                               ("exchange_old_serials",GOT,"returned"),("exchange_status","拟办理退换","delivery"),
                               ("exchange_on","2026-09-26","date"),("exchange_on","2026-09-27","date"),
                               ("exchange_number","HH-002","references"),("original_acceptance","YS-10","references"),
                               ("contract_id","YL-122","identity"),("seller_signature","其他公司（已盖章）","signatures")):
            with self.subTest(field=kind,value=value):
                changed=packet(edit=lambda i,f,l,v:value if i==7 and f==kind else v)
                inspection,phases,checks=findings(changed)
                audit=inspection["equipment_models"]["exchange"]
                self.assertNotEqual(next(c for c in audit["checks"] if c["key"]==key)["status"],"ok")
                self.assertNotEqual(inspection["status"],"ok")
                self.assertEqual([s["status"]=="ok" for s in phases],[True,False,False])
                if key in ("identity","references"):
                    self.assertNotIn("path",audit)

    def test_riders_missing_records_and_partial_serials_cannot_release_funds(self):
        for g,first_ok in (
            (packet(exchange=None),True),(packet(extra=[FORM]),True),
            (packet(exchange=[r for r in FORM if r[0]!="seller_signature"]),True),
            (packet(omissions=[(7,"附注：第二期改为支付合同价的80%")]),False),
            (packet(omissions=[(4,"设备编号说明：仅列尾号")]),True),
            (packet(final=[r for r in RETEST if r[0]!="delivered_serials"]),True),
            (packet(edit=lambda i,f,l,v:"C4-01、C4-02、C4-03、C4-03" if i==7 and f=="exchange_new_serials" else v),True),
            (packet(edit=lambda i,f,l,v:"3台" if i in (2,4) and f=="quantity_accepted" else v),True),
            (packet(edit=lambda i,f,l,v:"YL-C2" if i==4 and f=="equipment_model" else v),True)):
            with self.subTest(forms=g["equipment_model_sources"]["exchange"]["forms"],first=first_ok):
                inspection,phases,_=findings(g)
                self.assertNotEqual(inspection["status"],"ok")
                self.assertEqual([s["status"]=="ok" for s in phases],[first_ok,False,False])
        board=packet(edit=lambda i,f,l,v:"本合同自双方盖章并经甲方董事会批准后生效" if i==1 and f=="effect_clause" else v)
        receipt,phases,_=findings(board)
        self.assertEqual(receipt["equipment_models"]["exchange"]["status"],"ok")
        self.assertTrue(all(s["status"]!="ok" for s in phases))

    def test_list_order_does_not_change_the_evidence_or_advance_the_payment_date(self):
        def edit(i,field,label,value):
            if i==7 and field=="exchange_new_serials":
                return "、".join(reversed(GOT.split("、")))
            return "2026-09-25" if field=="paid_on" else value
        graph=packet(edit=edit)
        receipt,phases,all_checks=findings(graph)
        self.assertEqual(receipt["equipment_models"]["exchange"]["status"],"ok")
        self.assertEqual([s["status"] for s in phases],["ok","ok","ok"])
        payment=next(f for f in all_checks if f["rule"]=="H05")
        self.assertEqual(payment["status"],"risk")
        self.assertIn("早于",payment["detail"])
        dates={f["value"] for f in graph["facts"] if f["id"] in payment["evidence"] and f["field"] in ("accepted_on","paid_on")}
        self.assertTrue({"2026-09-25","2026-09-26"}<=dates)

    def test_similar_serial_spellings_or_reused_devices_need_individual_identification(self):
        for entered in (SENT,SENT.lower(),SENT.replace("-",""),"C4-01、c401、C4-03、C4-04","C4-01、C4-02、C4-03、XX04"):
            def edit(i,field,label,value):
                return entered if (i,field) in ((4,"delivered_serials"),(7,"exchange_new_serials")) else value
            receipt,phases,_=findings(packet(edit=edit))
            self.assertNotEqual(receipt["equipment_models"]["exchange"]["status"],"ok",entered)
            self.assertEqual([s["status"]=="ok" for s in phases],[True,False,False])

    def test_archive_and_replay_detect_changed_registered_rows_edges_and_outcome(self):
        g=packet()
        _,_,checks=findings(g)
        g["edges"].extend(edges(checks))
        report={"policy":{**VERSION,"profile":g["profile"]},"findings":checks,"graph":g}
        text=["\n".join(l+"："+v if l else v for f,l,v in fields) for fields in (CONTRACT+[ORDER],INITIAL,FIX,RETEST,WARRANTY,
              [(f,l,"2026-09-27" if f=="paid_on" else v) for f,l,v in BANK_DOC],FORM)]
        def read(doc,n): return text[int(doc[1:])-1]
        verify(report,read)
        verify_findings(report)
        for which in ("row","edge","finding"):
            bad=copy.deepcopy(report)
            if which=="row":
                bad["graph"]["equipment_model_sources"]["exchange"]["pages"][-1]["rows"][-1]["quote"]="不同原行"
            if which=="edge":
                next(e for e in bad["graph"]["edges"] if e["type"]=="equipment_exchange_received")["to"]="d02/p1"
            if which=="finding":
                next(f for f in bad["findings"] if f["rule"]=="H02")["equipment_models"]["exchange"]["checks"][0]["status"]="risk"
            with self.assertRaises(ValueError):
                if which=="finding": verify_findings(bad)
                else: verify(bad,read)
