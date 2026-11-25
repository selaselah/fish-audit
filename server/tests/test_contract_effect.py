import copy
import unittest

from contract_effect import LEGACY, SEAL_FORMAT, sources, verify
from controls import VERSION, execute
from performance import BATCH_FORMAT, compute, verify_findings
from test_performance import APPROVAL, BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


RIDER="附加生效条件：本合同须取得主管机构书面批准后方可生效"
BOARD_CLAUSE="本合同自双方盖章并经甲方董事会批准后生效"
BOARD_NOTE="决议附注：仅批准谈判，签约须另行表决"


class ContractEffectTests(unittest.TestCase):
    def test_board_rider_with_and_without_extracted_fact_holds_each_installment(self):
        for extracted in (True,False):
            approval=[*APPROVAL,("other","决议附注","仅批准谈判，签约须另行表决")] if extracted else APPROVAL
            graph=material([CONTRACT,approval,RECEIPT,WARRANTY,BANK_DOC],
                           lambda i,k,l,v:BOARD_CLAUSE if k=="effect_clause" else v,
                           omissions=[] if extracted else [(2,BOARD_NOTE)])
            checks=compute(graph)
            h01=checks[0]
            self.assertEqual(h01["status"],"missing")
            note,=h01["effect_review"]["conditions"]
            self.assertEqual((note["doc"],note["page"],note["line"],note["quote"],note["kind"]),
                             ("d02",1,len(APPROVAL)+1,BOARD_NOTE,"approval_note"))
            self.assertEqual(bool(note["facts"]),extracted)
            self.assertLessEqual({"d02/p1",*note["facts"]},set(h01["evidence"]))
            self.assertEqual(h01["effect_review"]["approval_pages"][0]["doc"],"d02")
            self.assertEqual([f["status"] for f in checks if f["rule"] in ("H02","H03")],["ok","ok"])
            self.assertEqual([f["status"] for f in checks if f["rule"] in ("H04","H05")],["missing"]*4)

    def test_board_record_does_not_merge_split_dates_or_accept_image_only_coverage(self):
        graph=material([CONTRACT,APPROVAL,RECEIPT],lambda i,k,l,v:BOARD_CLAUSE if k=="effect_clause" else v)
        raws={doc["id"]:"\n".join(f["quote"] for f in graph["facts"] if f["doc"]==doc["id"]) for doc in graph["documents"]}
        read=lambda doc,page:raws[doc]
        page=next(n for n in graph["nodes"] if n["id"]=="d02/p1")
        for layer in ("image","text"):
            page["layer"]=layer
            page["clause_text_only"]=False
            graph["contract_effect_sources"]=sources(graph,read)
            signed=compute(graph)[0]
            self.assertEqual(signed["status"],"missing")
            self.assertEqual([p["doc"] for p in signed["effect_review"]["mixed_pages"]],["d02"])
        graph=material([CONTRACT,APPROVAL],lambda i,k,l,v:{'effect_clause':BOARD_CLAUSE,'approved_on':'2026-0 9-01'}.get(k,v))
        self.assertEqual(compute(graph)[0]["status"],"missing")
        self.assertIn("0 9",compute(graph)[0]["effect_review"]["conditions"][0]["quote"])

    def test_board_coverage_is_scoped_and_preserves_explicit_negative_decisions(self):
        for decision,expected in (("退回补议","risk"),("批准","ok")):
            graph=material([CONTRACT,APPROVAL,RECEIPT],
                           lambda i,k,l,v:{"effect_clause":BOARD_CLAUSE,"approval_result":decision}.get(k,v),
                           omissions=[(3,BOARD_NOTE)])
            signed=compute(graph)[0]
            self.assertEqual(signed["status"],expected)
            self.assertFalse(signed["effect_review"]["conditions"])
            self.assertEqual([p["doc"] for p in signed["effect_review"]["approval_pages"]],["d02"])

    def test_continuation_page_with_no_model_observation_keeps_its_line_reference(self):
        page={"doc":"d02","number":2,"sha256":"continuation","text":"第2页\n"+BOARD_NOTE,
              "layer":{"type":"text","clause_text_only":True,"lines":{"1":[[0,.1,.4,.2]],"2":[[0,.3,.9,.4]]}},
              "extraction":{"output":{"quality":"readable","facts":[]}}}
        graph=material([CONTRACT,APPROVAL],lambda i,k,l,v:BOARD_CLAUSE if k=="effect_clause" else v,extra_pages=[page])
        signed=compute(graph)[0]
        self.assertEqual(signed["status"],"missing")
        refs=[s for s in signed["effect_review"]["conditions"] if s["quote"]==BOARD_NOTE]
        self.assertEqual([(s["doc"],s["page"],s["line"],s["facts"]) for s in refs],[("d02",2,2,[])])
        self.assertIn("d02/p2",signed["evidence"])

    def test_historical_board_approval_replays_but_new_signoff_checks_originals(self):
        for retained in (False,True):
            graph=material([CONTRACT,APPROVAL],lambda i,k,l,v:BOARD_CLAUSE if k=="effect_clause" else v,
                           omissions=[(2,BOARD_NOTE)] if retained else [])
            def read(doc,page):
                lines=[f["quote"] for f in graph["facts"] if f["doc"]==doc]
                if retained and doc=="d02":
                    lines.append(BOARD_NOTE)
                return "\n".join(lines)
            current={"graph":graph,"policy":VERSION,"findings":execute(graph,graph["profile"])}
            verify(current,read)
            if retained:
                tampered=copy.deepcopy(current)
                tampered["graph"]["contract_effect_sources"]["conditions"]=[]
                with self.assertRaises(ValueError):
                    verify(tampered,read)
                with self.assertRaises(ValueError):
                    verify(current,lambda doc,page:read(doc,page).replace(BOARD_NOTE,""))
            graph["contract_effect_sources"]=sources(graph,read,SEAL_FORMAT)
            old={"graph":graph,"policy":{**VERSION,"contract_effect":SEAL_FORMAT,"version":"2026.11.25.16"},
                 "findings":execute(graph,graph["profile"])}
            self.assertEqual(next(f["status"] for f in old["findings"] if f["rule"]=="H01"),"ok")
            verify(old,read)
            if retained:
                with self.assertRaisesRegex(ValueError,"董事会"):
                    verify(old,read,signing=True)
            else:
                verify(old,read,signing=True)

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
