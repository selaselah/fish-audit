import copy
import unittest

from contract_effect import LEGACY, sources, verify
from controls import VERSION, execute
from performance import BATCH_FORMAT, compute, verify_findings
from test_performance import APPROVAL, BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


RIDER="附加生效条件：本合同须取得主管机构书面批准后方可生效"


class ContractEffectTests(unittest.TestCase):
    def test_seal_date_missed_by_old_workpaper_requires_review_before_approval(self):
        extra="乙方盖章日期：2026-09-12"
        graph=material([CONTRACT],omissions=[(1,extra)])
        raw="\n".join([f["quote"] for f in graph["facts"]]+[extra])
        read=lambda d,p:raw
        graph["contract_effect_sources"]=sources(graph,read,LEGACY)
        old={"graph":graph,"policy":{**VERSION,"version":"2026.11.25.02","contract_effect":LEGACY},
             "findings":compute(graph)}
        self.assertEqual(old["findings"][0]["status"],"ok")
        verify(old,read)
        with self.assertRaisesRegex(ValueError,"双方实际盖章日"):
            verify(old,read,signing=True)

    def test_main_contract_seals_and_early_advance(self):
        dates=[("buyer_sealed_on","甲方盖章日期","2026-09-01"),("seller_sealed_on","乙方盖章日期","2026-09-12")]
        def trial(declared,paid,rows,omissions=()):
            def edit(i,k,l,v):
                return {"effect_on":declared,"paid_on":paid,"payment_designation":"第一期"}.get(k,v)
            return compute(material([CONTRACT+rows,RECEIPT,WARRANTY,BANK_DOC],edit,omissions=omissions))
        good=trial("2026-09-12","2026-09-14",dates)
        self.assertEqual([f["status"] for f in good],["ok"]*7)
        self.assertEqual(good[0]["effect_review"]["seals"]["completed_on"],"2026-09-12")
        bad=trial("2026-09-01","2026-09-05",dates)
        self.assertEqual((bad[0]["status"],bad[-1]["status"]),("risk","risk"))
        self.assertIn("2026-09-12",bad[-1]["detail"])
        self.assertEqual([s["status"] for s in bad if s["rule"]=="H04"],["missing"]*3)
        graph=material([CONTRACT+dates,RECEIPT,WARRANTY,BANK_DOC],lambda i,k,l,v:"2026-09-04" if k=="accepted_on" else v)
        acceptance=compute(graph)[1]
        self.assertEqual(acceptance["status"],"risk")
        self.assertIn("双方最后盖章日",acceptance["date_checks"][0]["detail"])
        for rows,notes in [(dates[:1],()),(dates[:1],[(1,"乙方盖章日期：2026-09-12")]),
                           (dates,[(1,"盖章日期：另行确认")])]:
            check=trial("2026-09-01","2026-09-05",rows,notes)
            self.assertEqual(check[0]["status"],"missing")
            self.assertIsNone(check[0]["effect_review"]["seals"]["completed_on"])

    def test_omitted_rider_blocks_effect_and_the_triggered_payments(self):
        for clause in (RIDER,"特别约定：尚待主管机关核准","合同状态说明：本合同已解除","另须取得公证证明"):
            graph=material([CONTRACT,RECEIPT,WARRANTY,BANK_DOC],omissions=[(1,clause)])
            checks=compute(graph)
            signed=next(f for f in checks if f["rule"]=="H01")
            self.assertNotEqual(signed["status"],"ok")
            self.assertIn("d01/p1",signed["evidence"])
            condition,=signed["effect_review"]["conditions"]
            self.assertEqual((condition["doc"],condition["quote"],condition["line"]),("d01",clause,len(CONTRACT)+1))
            self.assertTrue(all(f["status"]!="ok" for f in checks if f["rule"] in ("H04","H05")))
        graph=material([CONTRACT,RECEIPT],omissions=[(2,RIDER)])
        self.assertEqual(compute(graph)[0]["status"],"ok")

    def test_named_effect_clause_and_payment_reference_are_reconciled_separately(self):
        for contract in (CONTRACT,[*CONTRACT,("other","付款备注","须取得财务批准后支付")],
                         [*CONTRACT,("other","付款条款","合同生效后五日内付款")]):
            signed=compute(material([contract,RECEIPT]))[0]
            self.assertEqual((signed["status"],signed["effect_review"]["conditions"]),("ok",[]))
        board="本合同自双方盖章并经甲方董事会批准后生效"
        graph=material([CONTRACT,APPROVAL],lambda i,k,l,v:board if k=="effect_clause" else v)
        self.assertEqual(compute(graph)[0]["status"],"ok")
        graph=material([CONTRACT,APPROVAL],lambda i,k,l,v:board if k=="effect_clause" else v,omissions=[(1,RIDER)])
        self.assertNotEqual(compute(graph)[0]["status"],"ok")

    def test_archive_source_replay_and_old_approval(self):
        graph=material([CONTRACT,RECEIPT],omissions=[(1,RIDER)])
        text="\n".join([f["quote"] for f in graph["facts"] if f["doc"]=="d01"]+[RIDER])
        read=lambda d,p:text
        report={"graph":graph,"findings":execute(graph,graph["profile"]),"policy":{**VERSION,"profile":graph["profile"]}}
        verify(report,read)
        verify_findings(report)
        for part in ("source","flag","finding"):
            altered=copy.deepcopy(report)
            if part=="source": altered["graph"]["contract_effect_sources"]["conditions"]=[]
            elif part=="flag": del altered["policy"]["contract_effect"]
            else: altered["findings"][1]["effect_review"]={}
            with self.assertRaises(ValueError):
                verify_findings(altered) if part=="finding" else verify(altered,read)
        old=copy.deepcopy(report)
        del old["graph"]["contract_effect_sources"],old["policy"]["contract_effect"]
        old["policy"]["performance_checks"]=BATCH_FORMAT
        old["findings"]=compute(old["graph"],BATCH_FORMAT)
        self.assertEqual(old["findings"][0]["status"],"ok")
        verify(old,read)
        with self.assertRaisesRegex(ValueError,"旧版"):
            verify(old,read,signing=True)

    def test_mixed_and_image_only_pages_stay_open_even_after_field_attestation(self):
        graph=material([CONTRACT])
        page=next(n for n in graph["nodes"] if n["type"]=="page")
        text="\n".join(f["quote"] for f in graph["facts"])
        page["clause_text_only"]=False
        for layer in ("text","image"):
            page["layer"]=layer
            graph["contract_effect_sources"]=sources(graph,lambda d,p:text)
            signed=compute(graph)[0]
            self.assertEqual(signed["status"],"missing")
            self.assertEqual(signed["effect_review"]["mixed_pages"][0]["doc"],"d01")
