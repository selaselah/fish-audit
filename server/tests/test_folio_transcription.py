import copy
import unittest

import contract_folios
from folio_transcription import compare, witness
from model import FIELDS
from controls import execute
from performance import PROFILE
from test_contract_folios import STAGES, fixture, rows
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


def candidate(field, quote, value):
    return {"id": "d01/p2/f1", "status": "anchored", "visual_check": "clear", "field": field, "quote": quote, "value": value}


def installment(raw="最终验收合格后支付 60%", quote="最终验收合格后支付60%", *, value=None, support="clear", duplicate=False,
                omit_rect=False, edit_call=None, **options):
    def edit(page):
        first, *_ = page["extraction"]["output"]["facts"]
        first.update(quote="第二期：" + quote, value=quote if value is None else value)
        page["extraction"]["response_id"] = "synthetic-extraction"
        page["extraction"]["check"] = {
            "response_id": "synthetic-visual", "input": [{"index": "1", "quote": first["quote"], "value": first["value"],
                                                           "field": FIELDS[first["field"]]}],
            "output": {"checks": [{"index": "1", "support": support}]},
        }
        if edit_call:
            edit_call(page["extraction"]["check"])
        if duplicate:
            page["extraction"]["output"]["facts"].append(dict(first))
        if omit_rect:
            page["layer"]["lines"].pop("1")

    return fixture(stages=[("payment_stage", "第二期", raw), STAGES[1]], edit_second=edit, **options)


class FolioTranscriptionTests(unittest.TestCase):
    def test_physical_label_value_and_quote_agree_at_typed_boundaries(self):
        for form, field, label, raw, quoted, value in [
            ("date", "signed_on", "签约日期", "2026 年 9 月 1 日", "2026年9月1日", "2026年9月1日"),
            ("date", "effect_on", "实际生效日期", "2024 年 2 月 29 日", "2024年2月29日", "2024年2月29日"),
            ("quantity", "quantity_agreed", "约定交付数量", "4 台", " 4台", "4台"),
            ("temperature", "acceptance_criteria", "约定验收标准", "柜温不高于 4℃", "柜温不高于4°C", "柜温不高于4°C"),
            ("installment", "payment_stage", "第一期", "合同生效后支付 30%", "合同生效后支付30%", "合同生效后支付30%"),
        ]:
            with self.subTest(field=field):
                fact = candidate(field, label + "：" + quoted, value)
                self.assertEqual(compare(label + "：" + raw, fact), {"ref": fact["id"], "form": form, "quote": fact["quote"], "value": value})
                self.assertIsNone(compare(label + "：" + raw, {**fact, "status": "visual"}))
                self.assertIsNone(compare(label + "：" + raw, {**fact, "status": "disputed"}))
                self.assertIsNone(compare(label + "：" + raw, {**fact, "visual_check": None}))
                self.assertIsNotNone(compare(label + "：" + raw, {**fact, "visual_check": "conflict", "status": "confirmed", "attestation": {"decision": "confirm"}}))

    def test_no_joining_digits_ids_signatures_or_omitting_conditions(self):
        for field, label, physical, claim in [
            ("payment_stage", "第一期", "合同生效后支付3 0%", "合同生效后支付30%"),
            ("payment_stage", "第一期", "合同生效后支付 30%（须另行批准）", "合同生效后支付30%"),
            ("payment_stage", "第一期", "合同生效后支付 3.0%", "合同生效后支付30%"),
            ("payment_stage", "第一期", "合同生效后支付 30‰", "合同生效后支付30%"),
            ("payment_stage", "第一期", "合同生效后支付 ３０%", "合同生效后支付30%"),
            ("payment_stage", "第一期", "合同生效后支付 101%", "合同生效后支付101%"),
            ("acceptance_criteria", "约定验收标准", "柜温不高于 -4℃", "柜温不高于4°C"),
            ("acceptance_criteria", "约定验收标准", "柜温不低于 4℃", "柜温不高于4°C"),
            ("acceptance_criteria", "约定验收标准", "柜温不高于 4℉", "柜温不高于4°C"),
            ("acceptance_criteria", "约定验收标准", "柜温不高于 4℃", "柜温不高于4C"),
            ("quantity_agreed", "约定交付数量", "4 套", "4台"),
            ("quantity_agreed", "约定交付数量", "④ 台", "4台"),
            ("signed_on", "签约日期", "2026 年 02 月 29 日", "2026年02月29日"),
            ("signed_on", "签约日期", "2026 年 09 月 01 日", "2026年9月1日"),
            ("signed_on", "实际生效日期", "2026 年 9 月 1 日", "2026年9月1日"),
            ("contract_id", "合同编号", "YL-35 16", "YL-3516"),
            ("buyer_signature", "甲方签章", "青禾 演练", "青禾演练"),
        ]:
            with self.subTest(field=field, raw=physical):
                self.assertIsNone(compare(label + "：" + physical, candidate(field, label + "：" + claim, claim)))

    def test_each_supported_phase_cites_its_only_physical_row(self):
        report, read = installment()
        plan, = rows(report, "H03")
        self.assertEqual(plan["contract_folios"]["state"], "continued")
        self.assertTrue(all(f["status"] == "ok" for f in rows(report, "H04") + rows(report, "H05")))
        ledger = report["graph"]["contract_folio_sources"]
        row, = [r for r in ledger["lines"] if r.get("transcription")]
        self.assertEqual((row["quote"], row["transcription"]["quote"]), ("第二期：最终验收合格后支付 60%", "第二期：最终验收合格后支付60%"))
        self.assertEqual((row["line"], row["page"], row["facts"]), (1, 2, ["d01/p2/f1"]))
        self.assertEqual(row["transcription"]["basis"], "visual_check")
        self.assertTrue({row["id"], row["transcription"]["ref"], "d01/p2"} <= set(plan["evidence"]))
        contract_folios.verify(report, read)
        for change in ("quote", "value", "form", "ref", "coords", "marker", "call_input", "vote"):
            forged = copy.deepcopy(report)
            target = next(r for r in forged["graph"]["contract_folio_sources"]["lines"] if r.get("transcription"))
            if change == "coords":
                forged["calls"]["pages"][1]["contract_folio_rects"]["1"] = []
            elif change == "marker":
                forged["policy"]["contract_folios"] = contract_folios.LEGACY
            elif change == "call_input":
                forged["calls"]["pages"][1]["check"]["input"][0]["field"] = "合同编号"
            elif change == "vote":
                forged["calls"]["pages"][1]["check"]["output"]["checks"][0]["support"] = "unreadable"
            else:
                target["transcription"][change] += "x"
            with self.subTest(change=change), self.assertRaises(ValueError):
                contract_folios.verify(forged, read)

    def test_missing_witness_ambiguous_rows_and_conflicts_stay_open(self):
        for options in (
            {"support": "unreadable"}, {"layer": "image"}, {"text_only": False}, {"omit_rect": True},
            {"duplicate": True}, {"unobserved": ["第二期：最终验收合格后支付60%"]},
            {"raw": "最终验收合格后支付6 0%"}, {"raw": "最终验收合格后支付 60%须见票"},
            {"value": "最终验收合格后支付80%"}, {"attest": {"d01/p2/f1": {"decision": "dispute"}}},
            {"edit_call": lambda c: c.update(input=[])},
            {"edit_call": lambda c: c["input"][0].update(quote="第二期：支付80%")},
            {"edit_call": lambda c: c.update(response_id="synthetic-extraction")},
            {"edit_call": lambda c: c["output"]["checks"].append(dict(c["output"]["checks"][0]))},
        ):
            with self.subTest(options=options):
                report, _ = installment(**options)
                self.assertNotEqual(rows(report, "H03")[0]["contract_folios"]["state"], "continued")
                self.assertFalse(any(r.get("transcription") for r in report["graph"]["contract_folio_sources"]["lines"]))

    def test_confirmation_needs_receipt_for_same_document_page_and_field(self):
        receipt = {"format": "field-source-v1", "operation": "confirm", "rev": 2, "report_hash": "previous",
                   "doc": "d01", "page": 2, "original_sha256": "sample", "page_sha256": "second"}
        decision = {"fact": "d01/p2/f1", "decision": "confirm", "rev": 2, "source_check": receipt}
        report, read = installment(support="unreadable", attest={"d01/p2/f1": decision})
        match, = [r["transcription"] for r in report["graph"]["contract_folio_sources"]["lines"] if r.get("transcription")]
        self.assertEqual(match["basis"], "field_receipt")
        contract_folios.verify(report, read)
        fact = next(f for f in report["graph"]["facts"] if f["id"] == decision["fact"])
        for key in ("doc", "page", "original_sha256", "page_sha256", "rev", "format"):
            with self.subTest(key=key):
                altered = {**decision, "source_check": {**receipt, key: "different"}}
                self.assertIsNone(witness({**fact, "attestation": altered}, {}))

    def test_agreeing_transcriptions_cannot_close_an_ambiguous_printed_percentage(self):
        for literal in ("最终验收合格后支付6 0%", "最终验收合格后支付６０%", "最终验收合格后支付⑥0%"):
            with self.subTest(literal=literal):
                report, read = installment(raw=literal, quote=literal)
                self.assertNotEqual(rows(report, "H03")[0]["status"], "ok")
                self.assertEqual(rows(report, "H03")[0]["contract_folios"]["state"], "numeral")
                self.assertTrue(all(f["status"] != "ok" for f in rows(report, "H04") + rows(report, "H05")))
                phase = rows(report, "H04")[1]["stage"]
                self.assertEqual((phase["share"], phase["clause"]), ("", literal))
                contract_folios.verify(report, read)

    def test_single_page_split_percentage_and_transfer_have_no_computed_share(self):
        graph = material([CONTRACT, RECEIPT, WARRANTY, BANK_DOC],
                         lambda i, field, label, value: "最终验收合格后支付6 0%" if i == 1 and label == "第二期" else value)
        report = {"findings": execute(graph, PROFILE)}
        plan, = rows(report, "H03")
        self.assertEqual((len(plan["contract_folios"]["pages"]), plan["contract_folios"]["state"]), (1, "numeral"))
        for rule in ("H04", "H05"):
            phase, = [f for f in rows(report, rule) if f.get("stage", {}).get("name") == "第二期"]
            self.assertEqual((phase["status"], phase["stage"]["share"]), ("missing", ""))
            self.assertIsNone((phase.get("stage_payment") or {}).get("expected"))
        self.assertEqual([f["status"] for f in rows(report, "H01") + rows(report, "H02")], ["ok", "ok"])

    def test_legacy_archives_keep_strict_layout_and_reject_unsafe_compatibility_at_signoff(self):
        for raw, old_state, refused in [
            ("最终验收合格后支付 60%", "source", False),
            ("最终验收合格后支付６０%", "continued", True),
        ]:
            with self.subTest(raw=raw):
                report, read = installment(raw=raw)
                graph = report["graph"]
                old = contract_folios.sources(graph, read, contract_folios.LEGACY)
                graph["contract_folio_sources"] = old
                nodes, edges = contract_folios.source_graph(old)
                graph["nodes"] = [n for n in graph["nodes"] if n["type"] != "contract_folio_line"] + nodes
                graph["edges"] = [e for e in graph["edges"] if e["type"] != "contract_folio_basis"] + edges
                report["policy"].update(version="2026.11.26.10", contract_folios=contract_folios.LEGACY)
                report["findings"] = execute(graph, PROFILE)
                self.assertEqual(rows(report, "H03")[0]["contract_folios"]["state"], old_state)
                contract_folios.verify(report, read)
                if refused:
                    with self.assertRaisesRegex(ValueError, "重新审计"):
                        contract_folios.verify(report, read, signing=True)
                else:
                    contract_folios.verify(report, read, signing=True)
