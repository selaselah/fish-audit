import copy
import unittest

from contract_effect import sources, verify
from controls import VERSION, execute
from performance import BATCH_FORMAT, compute, verify_findings
from test_performance import APPROVAL, BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


RIDER="附加生效条件：本合同须取得主管机构书面批准后方可生效"


class ContractEffectTests(unittest.TestCase):
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
