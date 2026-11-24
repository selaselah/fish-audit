import copy
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import pypdfium2 as pdfium
from PIL import Image

from contract_changes import LEGACY, ledger, verify_sources
from controls import VERSION, execute
from documents import clause_text_only, layer_type
from jobs import refresh_addendum_layout
from performance import NATIVE_FORMAT, compute, verify_findings
from test_performance import CONTRACT, RECEIPT, WARRANTY, BANK_DOC, material


CHANGE = [("contract_addendum","","采购合同补充协议"),("addendum_number","补充协议编号","BC-121"),
          ("base_contract_ref","原合同编号","YL-121"),*CONTRACT[2:5],
          ("change_scope","变更范围","仅变更验收标准，其余条款不变"),
          ("previous_criterion","原验收标准","柜温不高于4℃"),("revised_criterion","变更后验收标准","柜温不高于2℃"),
          ("change_timing","变更适用时点","仅适用于本协议生效后进行的验收"),("change_effect_clause","协议生效条款","本协议自双方盖章之日起生效"),
          ("buyer_sealed_on","甲方盖章日期","2026-09-10"),("seller_sealed_on","乙方盖章日期","2026-09-12"),*CONTRACT[8:10]]
GROUPS = [CONTRACT,CHANGE,RECEIPT,WARRANTY,BANK_DOC]


def case(changed=None, receipt=None, *extra, omissions=()):
    def edit(i,field,label,value):
        return ((changed or {}) if i==2 else (receipt or {}) if i==3 else {}).get(field,value)
    return material([*GROUPS,*extra],edit,omissions=omissions)


def assessment(graph):
    findings=compute(graph)
    return next(f for f in findings if f["rule"]=="H02"), [f["status"] for f in findings if f["rule"]=="H04"]


def quantity_case(*, actual="6台", sealed="2026-09-12", reading="柜温3℃", revised="6台", omissions=()):
    updates = {"change_scope":("change_scope","变更范围","仅变更交付数量，合同总价及其余条款不变"),
               "previous_criterion":("previous_quantity","原交付数量","4台"),
               "revised_criterion":("revised_quantity","变更后交付数量",revised),
               "seller_sealed_on":("seller_sealed_on","乙方盖章日期",sealed)}
    amendment = [updates.get(k,(k,l,v)) for k,l,v in CHANGE]
    overrides = {"quantity_accepted":actual, "measured_result":reading}
    receipt = [(k,l,overrides.get(k,v)) for k,l,v in RECEIPT if overrides.get(k,v) is not None]
    return material([CONTRACT,amendment,receipt,WARRANTY,BANK_DOC],omissions=omissions)


class ContractChangeTests(unittest.TestCase):
    def test_quantity_change_has_its_own_effective_date_and_does_not_replace_quality_tests(self):
        for args,state,count,diff,status,phases in (
            ({}, "applied",6,0,"ok",["ok"]*3),
            ({"actual":"4台"}, "applied",6,-2,"risk",["ok","risk","risk"]),
            ({"actual":"7台"}, "applied",6,1,"risk",["ok","risk","risk"]),
            ({"sealed":"2026-09-22","actual":"4台"}, "original",4,0,"ok",["ok"]*3),
            ({"actual":None}, "applied",6,None,"missing",["ok","missing","missing"]),
            ({"actual":"6套"}, "applied",6,None,"missing",["ok","missing","missing"]),
            ({"reading":"柜温8℃"}, "applied",6,0,"issue",["ok","risk","risk"]),
            ({"sealed":"2026-09-20"}, "pending",None,None,"missing",["ok","missing","missing"]),
        ):
            with self.subTest(args=args):
                graph = quantity_case(**args)
                inspection,stages = assessment(graph)
                change = inspection["quality_change"]
                quantity = change["quantity"]
                self.assertEqual((change["state"],(quantity["applicable"] or {}).get("count"),quantity["difference"],
                                  inspection["status"],stages),(state,count,diff,status,phases))
                self.assertIsNone(change["applied_criterion"])
                self.assertTrue(all(ref in inspection["evidence"] for row in quantity["lines"] for ref in row["facts"]))
                self.assertTrue(any(e["type"]=="delivery_quantity_basis" for e in graph["edges"]))

    def test_quantity_needs_the_original_unit_and_all_count_entries_on_the_page(self):
        for args in ({"revised":"6套"},{"revised":"1 6台"},{"sealed":"2026-09-1 2"},
                     {"omissions":[(2,"价款调整：差额另行结算")]},
                     {"omissions":[(3,"交付备注：尚欠2台，另行补交")]}):
            check, stages = assessment(quantity_case(**args))
            self.assertEqual(check["quality_change"]["state"],"pending",args)
            self.assertNotEqual(check["status"],"ok")
            self.assertTrue(all(s!="ok" for s in stages[1:]))
        check, _ = assessment(quantity_case(omissions=[(3,"实际验收数量：4台")]))
        self.assertIsNone(check["quality_change"]["quantity"]["difference"])
        self.assertEqual(check["status"],"missing")

    def test_omitted_quantity_change_blocks_old_positive_signoff_and_forged_edges(self):
        note = "变更后交付数量：6台"
        graph = material([CONTRACT,RECEIPT,WARRANTY,BANK_DOC],omissions=[(1,note)])
        text = {d["id"]:"\n".join(f["quote"] for f in graph["facts"] if f["doc"]==d["id"]) for d in graph["documents"]}
        text["d01"]+="\n"+note
        read=lambda d,p:text[d]
        current={"graph":graph,"policy":VERSION,"findings":compute(graph)}
        self.assertNotEqual(current["findings"][1]["status"],"ok")
        verify_sources(current,read)
        graph["edges"]=[e for e in graph["edges"] if e["type"]!="delivery_quantity_basis"]
        with self.assertRaisesRegex(ValueError,"原页关系"):
            verify_sources(current,read)
        graph["quality_addenda"]=ledger(graph,read,LEGACY)
        old={"policy":{**VERSION,"version":"2026.11.25.05","quality_addenda":LEGACY},"graph":graph,"findings":compute(graph)}
        self.assertEqual(old["findings"][1]["status"],"ok")
        verify_sources(old,read)
        with self.assertRaisesRegex(ValueError,"数量变更"):
            verify_sources(old,read,signing=True)

    def test_stricter_limit_overrides_stale_basis_with_both_pages(self):
        graph=case()
        finding, phases=assessment(graph)
        change=finding["quality_change"]
        self.assertEqual((finding["status"],phases),("issue",["ok","risk","risk"]))
        self.assertEqual((change["state"],change["effective_on"],change["accepted_on"]),("applied","2026-09-12","2026-09-20"))
        self.assertIn("所引检验依据",finding["detail"])
        self.assertIn("柜温3°C",finding["detail"])
        edges={e["to"] for e in graph["edges"] if e["type"] in ("contract_id","base_contract_ref")}
        self.assertEqual(len(edges),1)
        cited={f["field"] for f in graph["facts"] if f["id"] in finding["evidence"]}
        self.assertTrue({"previous_criterion","revised_criterion","change_timing","change_effect_clause","measured_result",
                         "buyer_signature","seller_signature","accepted_on","inspection_basis"}<=cited)
        self.assertEqual(next(f for f in compute(graph) if f["rule"]=="H05")["status"],"missing")

    def test_positive_and_wrong_basis_and_prospective_late_relaxation(self):
        reading={"measured_result":"柜温1℃","inspection_basis":"柜温不高于2℃"}
        f,phases=assessment(case(receipt=reading))
        self.assertEqual((f["status"],phases),("ok",["ok"]*3))
        f,_=assessment(case(receipt={**reading,"inspection_basis":"柜温不高于4℃"}))
        self.assertEqual(f["status"],"risk")
        late={"revised_criterion":"柜温不高于8℃","seller_sealed_on":"2026-09-22"}
        f,phases=assessment(case(late,{"measured_result":"柜温6℃","inspection_basis":"柜温不高于8℃"}))
        self.assertEqual((f["status"],f["quality_change"]["state"],phases),("issue","original",["ok","risk","risk"]))

    def test_clauses_and_identity_that_cannot_establish_a_version(self):
        for field,value in (("base_contract_ref","YL-122"),("addendum_number","尾号121"),("seller","演练丙"),
                            ("subject","冷冻车"),("previous_criterion","柜温不高于8℃"),("revised_criterion","重量至少4kg"),
                            ("change_scope","验收标准、支付比例同时变更"),("change_timing","追溯至原合同签订日"),
                            ("change_effect_clause","经双方盖章并报董事会批准后生效"),
                            ("seller_signature","第三方（已盖章）"),("seller_sealed_on","2026-08-31"),
                            ("seller_sealed_on","2026-09-20"),("seller_signature",None)):
            with self.subTest(field=field,value=value):
                f,phases=assessment(case({field:value}))
                self.assertEqual((f["quality_change"]["state"],f["status"]),("pending","missing"))
                self.assertEqual(phases[1:],["missing","missing"])
        f,phases=assessment(case(None,None,CHANGE))
        self.assertEqual((f["quality_change"]["state"],phases),("pending",["missing"]*3))
        signed_failure={"acceptance_result":"不合格"}
        f,_=assessment(case({"seller_signature":None},signed_failure))
        self.assertEqual(f["status"],"issue")

    def test_draft_unsigned_mislinked_partial_and_unverified_sources(self):
        additional = [("change_state","补充协议状态","草案")]
        for graph,expected in ((material([CONTRACT,CHANGE+additional,RECEIPT,WARRANTY,BANK_DOC]),"missing"),
                               (case(receipt={"contract_id":"YL-X"}),"missing"),(case(receipt={"acceptance_scope":"分批验收"}),"risk")):
            f,phases=assessment(graph)
            self.assertEqual((f["quality_change"]["state"],phases),("pending",["ok",expected,expected]))
        graph=case()
        next(f for f in graph["facts"] if f["doc"]=="d02" and f["field"]=="seller_signature")["status"]="anchored"
        f,_=assessment(graph)
        self.assertEqual(f["quality_change"]["state"],"pending")
        for omission in ("付款备注：另须取得抵押担保", "原合同编号展示说明：本单只列尾号"):
            graph=case(omissions=[(2,omission)])
            f,phases=assessment(graph)
            self.assertEqual((f["quality_change"]["state"],phases),("pending",["missing"]*3))
            self.assertEqual(graph["quality_addenda"]["pages"][0]["uncovered"][0]["quote"],omission)
            edge,=[e for e in graph["edges"] if e["type"]=="base_contract_ref"]
            self.assertEqual(edge["to"],edge["evidence"][0])
        graph=case(omissions=[(1,"合同编号：仅列尾号")])
        self.assertTrue(graph["quality_addenda"]["limited_numbers"])
        self.assertEqual(assessment(graph)[0]["quality_change"]["state"],"pending")

    def test_unclassified_or_mixed_layout_and_closed_history(self):
        f,_=assessment(material([CONTRACT,RECEIPT],omissions=[(1,"合同另见双方签订的补充协议")]))
        self.assertEqual(f["quality_change"]["state"],"pending")
        graph=case()
        graph["quality_addenda"]["pages"][0]["text_only"]=False
        self.assertEqual(assessment(graph)[0]["quality_change"]["state"],"pending")
        f,phases=assessment(case(None,None,RECEIPT))
        self.assertEqual((f["quality_change"]["state"],phases),("pending",["ok","missing","missing"]))
        f,_=assessment(case(None,None,[("other","","待辨附件")]))
        self.assertEqual(f["quality_change"]["state"],"pending")
        self.assertNotIn("quality_change",next(f for f in compute(case(),NATIVE_FORMAT) if f["rule"]=="H02"))

    def test_small_raster_rider_requires_visual_read_even_on_a_native_page(self):
        with pdfium.PdfDocument.new() as pdf:
            page=pdf.new_page(595,842)
            self.assertTrue(clause_text_only(page))
            picture=pdfium.PdfImage.new(pdf)
            bitmap=pdfium.PdfBitmap.from_pil(Image.new("RGB",(20,12),"black"))
            picture.set_bitmap(bitmap)
            picture.set_matrix(pdfium.PdfMatrix(60,0,0,15,40,50))
            page.insert_obj(picture)
            page.gen_content()
            self.assertEqual(layer_type(page),"text")
            self.assertFalse(clause_text_only(page))
            page.close()
            bitmap.close()

    def test_day_only_payment_and_separated_digits_do_not_authorize_settlement(self):
        def same_day(i,field,label,value):
            return {"paid_on":"2026-09-20","inspection_basis":"柜温不高于2℃","measured_result":"柜温1℃"}.get(field,value)
        findings=compute(material(GROUPS,same_day))
        paid=next(f for f in findings if f["rule"]=="H05")
        self.assertEqual(paid["status"],"missing")
        self.assertIn("时分",paid["detail"])
        for change in ({"revised_criterion":"柜温不高于2 0℃"},{"base_contract_ref":"YL-1 21"}):
            f,_=assessment(case(change))
            self.assertEqual(f["quality_change"]["state"],"pending")

    def test_rederive_sources_findings_links_and_old_positive_signoff(self):
        graph=case()
        report={"policy":{**VERSION,"profile":graph["profile"]},"graph":graph,"findings":execute(graph,graph["profile"])}
        texts={f"d{i:02d}":"\n".join(l+"："+v if l else v for _,l,v in group) for i,group in enumerate(GROUPS,1)}
        read=lambda doc,page:texts[doc]
        verify_sources(report,read)
        verify_findings(report)
        for kind in ("quote","number","evidence","marker"):
            forged=copy.deepcopy(report)
            if kind=="quote":
                forged["graph"]["quality_addenda"]["signals"][0]["quote"]="补充协议另有约定"
            elif kind=="number":
                next(e for e in forged["graph"]["edges"] if e["type"]=="base_contract_ref")["to"]="d03"
            elif kind=="marker":
                del forged["policy"]["quality_addenda"]
            else:
                next(f for f in forged["findings"] if f["rule"]=="H02")["quality_change"]["effective_on"]="2026-08-01"
            with self.assertRaises(ValueError):
                verify_findings(forged) if kind=="evidence" else verify_sources(forged,read)
        old=copy.deepcopy(report)
        old["policy"]={"performance_checks":NATIVE_FORMAT}
        del old["graph"]["quality_addenda"]
        old["findings"]=[{"rule":"H02","status":"ok"}]
        verify_sources(old,read)
        with self.assertRaisesRegex(ValueError,"旧版"):
            verify_sources(old,read,signing=True)

    def test_refresh_only_enriches_matching_archived_pages_of_amendment_cases(self):
        store=Mock(files=Path("/synthetic"))
        docs=[{"id":"d01","ext":".pdf"}]
        page={"doc":"d01","text":"采购发票","number":1,"sha256":"issued","layer":{"type":"text","lines":{}},
              "extraction":{"output":{"facts":[]}}}
        with patch("jobs.prepare") as render:
            refresh_addendum_layout(store,"test",docs,[page])
            render.assert_not_called()
            page["text"]="采购合同补充协议"
            fresh={**page,"layer":{**page["layer"],"clause_text_only":True}}
            render.return_value=[{**fresh,"sha256":"different"}]
            refresh_addendum_layout(store,"test",docs,[page])
            store.add_layers.assert_not_called()
            self.assertNotIn("clause_text_only",page["layer"])
            render.return_value=[fresh]
            refresh_addendum_layout(store,"test",docs,[page])
            store.add_layers.assert_called_once_with("test","d01",[fresh])
            self.assertTrue(page["layer"]["clause_text_only"])
