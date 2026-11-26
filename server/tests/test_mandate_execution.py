import json
import unittest
from copy import deepcopy
from functools import partial
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pypdfium2 as pdfium
from reportlab.pdfgen import canvas

with patch.dict("os.environ", PYTHON_DOTENV_DISABLED="1"):
    from config import PERFORMANCE

import mandate_execution as execution
from controls import VERSION, execute
from documents import render
from graph import build_graph
from performance import verify_findings
from test_acceptance_execution import by_rule, printed
from test_delegation import CONTRACT_BY_AGENT, GRANT, sample
from test_pdf_execution import later_copy, signed_copy
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material


PREVIOUS = "2026.11.27.01"


def pdf_report(raw, fixture=sample, *, parts=("d02",)):
    """File the fixture's single-page documents as successive pages of one physical PDF."""
    physical = parts[0]
    originals = {physical: raw}

    def read_original(doc):
        return originals[doc["id"]]

    with TemporaryDirectory() as tmp:
        folder = Path(tmp)
        path = folder / "fixture.pdf"
        path.write_bytes(raw)
        render(path, folder, len(parts))
        rendered = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

    def file_original(docs, pages, attestations):
        documents = {d["id"]: d for d in docs}
        documents[physical].update(ext=".pdf", pages=len(rendered), sha256=sha256(raw).hexdigest())
        by_doc = {p["doc"]: p for p in pages}
        for part, meta in zip(parts, rendered, strict=True):
            by_doc[part].update(doc=physical, **meta)
            if part != physical:
                del documents[part]
                prefix = part + "/p1/"
                for ref in list(attestations):
                    if ref.startswith(prefix):
                        new_ref = f"{physical}/p{meta['number']}/{ref.removeprefix(prefix)}"
                        attestations[new_ref] = attestations.pop(ref)
        return build_graph(list(documents.values()), pages, attestations, read_original=read_original)

    with patch("test_performance.build_graph", file_original):
        graph = fixture()
    return {"graph": graph, "policy": {**VERSION, "profile": PERFORMANCE},
            "findings": execute(graph, PERFORMANCE)}, read_original


def archived(report):
    graph = deepcopy(report["graph"])
    del graph["mandate_pdf_sources"]
    graph["nodes"] = [n for n in graph["nodes"] if n["type"] != "mandate_pdf_inspection"]
    graph["edges"] = [e for e in graph["edges"] if e["type"] != "mandate_pdf_source"]
    policy = dict(report["policy"], version=PREVIOUS)
    del policy["mandate_pdf"]
    with patch("controls.RULE_VERSION", PREVIOUS):
        findings = execute(graph, PERFORMANCE)
    return {"graph": graph, "policy": policy, "findings": findings}


def both_sides(edit=None):
    contract = [("seller_agent_signature", "乙方代理人签字", "演练方程（已签字）") if f == "seller_signature"
                else (f, label, value) for f, label, value in CONTRACT_BY_AGENT]
    seller = {"grant_principal": "演练乙", "grant_counterparty": "演练甲", "grant_number": "WT-002",
              "grant_agent": "演练方程", "grant_signature": "演练乙（已盖章）"}
    seller_grant = [(f, label, seller.get(f, value)) for f, label, value in GRANT]
    return material([contract, GRANT, seller_grant, RECEIPT, WARRANTY, BANK_DOC], edit)


def scanned_copy(raw, *, ocr):
    result = BytesIO()
    with pdfium.PdfDocument(raw) as pdf:
        page = pdf[0]
        width, height = page.get_size()
        sheet = canvas.Canvas(result, pagesize=(width, height), invariant=True)
        bitmap = page.render()
        sheet.drawInlineImage(bitmap.to_pil(), 0, 0, width, height)
        if ocr:
            text = sheet.beginText(48, 790)
            text.setFont("STSong-Light", 11)
            text.setLeading(21)
            text.setTextRenderMode(3)
            text.textLines(page.get_textpage().get_text_bounded())
            sheet.drawText(text)
        sheet.save()
    return result.getvalue()


class MandateExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plain = printed(sample(), "d02")
        cls.signed = signed_copy(cls.plain)

    def test_confirmed_typeset_seal_leaves_authority_and_dependent_payments_pending(self):
        report, read = pdf_report(self.plain)
        graph = report["graph"]
        ledger = graph["mandate_pdf_sources"]
        record, = ledger["records"]
        page, = record["pages"]
        seal, = [f for f in graph["facts"] if f["field"] == "grant_signature"]
        self.assertEqual(execution.FORMAT, "pdf-mandate-execution-v1")
        self.assertEqual((ledger["format"], report["policy"]["mandate_pdf"]), (execution.FORMAT,) * 2)
        self.assertEqual((record["id"], record["unit"], record["doc"]), ("mandate-pdf/d02", "d02", "d02"))
        self.assertEqual((record["state"], record["signatures"], record["fields"]), ("typeset", [], [seal["id"]]))
        self.assertEqual((seal["status"], seal["value"]), ("confirmed", "演练甲（已盖章）"))
        self.assertEqual(record["original_sha256"], sha256(self.plain).hexdigest())
        self.assertEqual((page["ref"], page["sha256"]), ("d02/p1", seal["page_sha256"]))
        inspection, = [n for n in graph["nodes"] if n["type"] == "mandate_pdf_inspection"]
        self.assertEqual((inspection["id"], inspection["sha256"], inspection["state"]),
                         (record["id"], record["original_sha256"], "typeset"))

        signing, = by_rule(report, "H01")
        grant, = signing["delegations"]
        self.assertEqual((grant["agent"], grant["signed_on"], grant["valid_until"]),
                         ("演练林岚", "2026-09-01", "2026-09-01"))
        self.assertEqual((grant["status"], signing["status"]), ("missing", "missing"))
        self.assertIn("排印", grant["detail"])
        self.assertRegex(grant["detail"], r"(核对|核实|补充).*(原件|签署记录)")
        self.assertEqual(grant["mandate_execution"], [record["id"]])
        proof = {record["id"], page["ref"], seal["id"]}
        self.assertLessEqual(proof, set(grant["evidence"]))
        self.assertLessEqual(set(grant["evidence"]), set(signing["evidence"]))
        stages, payments = by_rule(report, "H04"), by_rule(report, "H05")
        self.assertEqual((len(stages), len(payments)), (3, 1))
        for finding in stages + payments:
            self.assertEqual(finding["status"], "missing")
            self.assertLessEqual(proof, set(finding["evidence"]))
        for rule in ("H02", "H03"):
            independent, = by_rule(report, rule)
            self.assertEqual(independent["status"], "ok")
            self.assertNotIn(record["id"], independent["evidence"])
        execution.verify(report, read, signing=True)
        verify_findings(report)

    def test_image_only_and_searchable_scans_require_visual_review(self):
        # Simulate individually confirmed transcriptions, including the title identifying the grant.
        confirmed = {f"d02/p1/f{i}": {"decision": "confirm", "source_check": {"fixture": True}}
                     for i in range(1, len(GRANT) + 1)}
        for ocr in (False, True):
            with self.subTest(ocr=ocr):
                report, read = pdf_report(scanned_copy(self.plain, ocr=ocr), partial(sample, attestations=confirmed))
                record, = report["graph"]["mandate_pdf_sources"]["records"]
                page, = record["pages"]
                self.assertEqual((page["layer"], page["has_text"], record["state"]), ("image_overlay", ocr, "visual"))
                signing, = by_rule(report, "H01")
                grant, = signing["delegations"]
                self.assertEqual((grant["status"], signing["status"]), ("missing", "missing"))
                self.assertEqual(grant["mandate_execution"], [record["id"]])
                execution.verify(report, read)

    def test_embedded_signature_coverage_identity_and_mismatch(self):
        producer = b"/Producer (ReportLab"
        self.assertIn(producer, self.signed)
        damaged = self.signed.replace(producer, b"/Producer (ReporXLab", 1)
        for raw, state, status, coverage, reason in (
            (self.signed, "current", "missing", "ENTIRE_FILE", "身份"),
            (later_copy(self.signed), "earlier", "missing", "ENTIRE_REVISION", "版本"),
            (damaged, "mismatch", "risk", "ENTIRE_FILE", "校验"),
        ):
            with self.subTest(state=state):
                report, read = pdf_report(raw)
                record, = report["graph"]["mandate_pdf_sources"]["records"]
                signature, = record["signatures"]
                self.assertEqual((record["state"], signature["state"], signature["coverage"]), (state, state, coverage))
                self.assertEqual(signature["ends_at"], len(self.signed))
                self.assertRegex(signature["certificate_sha256"], r"^[0-9a-f]{64}$")
                signing, = by_rule(report, "H01")
                grant, = signing["delegations"]
                self.assertEqual((grant["status"], signing["status"]), (status, status))
                self.assertIn(reason, grant["detail"])
                self.assertEqual(grant["mandate_execution"], [record["id"]])
                execution.verify(report, read)

    def test_written_restrictions_and_expiry_remain_risks_with_pdf_evidence(self):
        for field, value, reason in (("grant_scope", "仅限收货验收", "仅限收货验收"),
                                     ("grant_conditions", "不得约定预付款", "限制"),
                                     ("grant_until", "2026-08-31", "2026-08-31")):
            with self.subTest(field=field):
                fixture = partial(sample, lambda i, f, l, v: value if f == field else v)
                report, _ = pdf_report(printed(fixture(), "d02"), fixture)
                signing, = by_rule(report, "H01")
                grant, = signing["delegations"]
                fact, = [f for f in report["graph"]["facts"] if f["field"] == field]
                self.assertEqual((grant["status"], signing["status"]), ("risk", "risk"))
                self.assertIn(reason, grant["detail"])
                self.assertIn("排印", grant["detail"])
                self.assertLessEqual({fact["id"], "mandate-pdf/d02"}, set(grant["evidence"]))
                self.assertLessEqual(set(grant["evidence"]), set(signing["evidence"]))

    def test_two_grants_in_one_pdf_bind_to_their_own_party_page_and_seal(self):
        original = both_sides()
        parts = ("d02", "d03", "d04")
        out = BytesIO()
        with pdfium.PdfDocument.new() as packet:
            for part in parts:
                with pdfium.PdfDocument(printed(original, part, mark=part == "d03")) as page:
                    packet.import_pages(page)
            packet.save(out)
        report, read = pdf_report(out.getvalue(), both_sides, parts=parts)
        graph = report["graph"]
        records = {r["unit"]: r for r in graph["mandate_pdf_sources"]["records"]}
        self.assertEqual(set(records), {"unit/d02/p1", "unit/d02/p2"})
        signing, = by_rule(report, "H01")
        grants = {g["side"]: g for g in signing["delegations"]}
        for side, number, state in (("buyer", 1, "typeset"), ("seller", 2, "visual")):
            with self.subTest(side=side):
                ref = f"d02/p{number}"
                unit = "unit/" + ref
                record, grant = records[unit], grants[side]
                seal, = [f for f in graph["facts"] if f.get("unit") == unit and f["field"] == "grant_signature"]
                self.assertEqual((record["state"], record["doc"], record["fields"]), (state, "d02", [seal["id"]]))
                self.assertEqual([p["ref"] for p in record["pages"]], [ref])
                self.assertEqual((grant["units"], grant["mandate_execution"]), ([unit], ["mandate-pdf/" + unit]))
                self.assertEqual(set(grant["evidence"]) & {r["id"] for r in records.values()}, {record["id"]})
                edge, = [e for e in graph["edges"] if e["type"] == "mandate_pdf_source" and e["from"] == unit]
                self.assertEqual((edge["to"], set(edge["evidence"])), (record["id"], {"d02", ref, seal["id"]}))
        execution.verify(report, read)
        verify_findings(report)

    def test_verification_rejects_substituted_original_page_graph_and_issued_finding(self):
        report, read = pdf_report(self.signed)
        execution.verify(report, read, signing=True)
        verify_findings(report)
        with self.assertRaisesRegex(ValueError, "摘要"):
            execution.verify(report, lambda doc: self.plain, signing=True)
        graph = report["graph"]
        record, = graph["mandate_pdf_sources"]["records"]
        page = next(n for n in graph["nodes"] if n["id"] == "d02/p1")
        edge, = [e for e in graph["edges"] if e["type"] == "mandate_pdf_source"]
        foreign_seal = next(f["id"] for f in graph["facts"] if f["field"] == "seller_signature")
        edits = (
            ("certificate", record["signatures"][0], {"certificate_sha256": "0" * 64}),
            ("page digest", page, {"sha256": "0" * 64}),
            ("field", record, {"fields": [foreign_seal]}),
            ("node", graph, {"nodes": [n for n in graph["nodes"] if n["id"] != record["id"]]}),
            ("edge", edge, {"from": "d01"}),
            ("format", report["policy"], {"mandate_pdf": "unknown-format"}),
        )
        for target, obj, edit in edits:
            with self.subTest(target=target), patch.dict(obj, edit), self.assertRaises(ValueError):
                execution.verify(report, read)
        for rule in ("delegation", "H01", "H04", "H05"):
            with self.subTest(finding=rule):
                changed = deepcopy(report)
                if rule == "delegation":
                    del by_rule(changed, "H01")[0]["delegations"][0]["mandate_execution"]
                else:
                    by_rule(changed, rule)[0]["evidence"].remove("mandate-pdf/d02")
                with self.assertRaises(ValueError):
                    verify_findings(changed)

    def test_legacy_positive_replays_but_approval_checks_dependent_findings(self):
        current, read = pdf_report(self.plain)
        old = archived(current)
        verify_findings(old)
        execution.verify(old, None)
        signing, = by_rule(old, "H01")
        grant, = signing["delegations"]
        self.assertEqual((grant["status"], signing["status"]), ("ok", "ok"))
        self.assertNotIn("mandate_execution", grant)
        with self.assertRaisesRegex(ValueError, "重审"):
            execution.verify(old, read, signing=True)
        # A historical payment finding can cite the grant directly, without a nested delegation.
        for rule in ("H04", "H05"):
            with self.subTest(rule=rule):
                finding = by_rule(old, rule)[0]
                self.assertEqual(finding["status"], "ok")
                with self.assertRaisesRegex(ValueError, "重审"):
                    execution.verify({**old, "findings": [finding]}, read, signing=True)
        cutover = "2026.11.27.02"
        at_cutover = {**old, "policy": {**old["policy"], "version": cutover},
                      "findings": [{**f, "version": cutover} for f in old["findings"]]}
        with self.assertRaisesRegex(ValueError, "缺少"):
            execution.verify(at_cutover, read)

    def test_legacy_signoff_requires_review_only_for_the_positive_pdf_delegation(self):
        def limit_buyer(doc, field, label, value):
            return "仅限收货验收" if doc == 2 and field == "grant_scope" else value

        fixture = partial(both_sides, limit_buyer)
        source = fixture()
        for doc, side in (("d02", "buyer"), ("d03", "seller")):
            with self.subTest(pdf=side):
                current, read = pdf_report(printed(source, doc), fixture, parts=(doc,))
                old = archived(current)
                signing, = by_rule(old, "H01")
                self.assertEqual(signing["status"], "risk")
                self.assertEqual({g["side"]: g["status"] for g in signing["delegations"]},
                                 {"buyer": "risk", "seller": "ok"})
                verify_findings(old)
                execution.verify(old, None)
                if side == "buyer":
                    execution.verify(old, read, signing=True)
                else:
                    with self.assertRaisesRegex(ValueError, "重审"):
                        execution.verify(old, read, signing=True)

    def test_legacy_independent_risk_and_unrelated_pdf_do_not_block_approval(self):
        terms = {"grant_scope": "仅限收货验收", "paid_on": "2026-08-31"}
        restricted = partial(sample, lambda i, f, l, v: terms.get(f, v))
        current, read = pdf_report(printed(restricted(), "d02"), restricted)
        old = archived(current)
        self.assertEqual([by_rule(old, r)[0]["status"] for r in ("H01", "H04", "H05")], ["risk", "missing", "risk"])
        verify_findings(old)
        execution.verify(old, read, signing=True)

        direct = partial(material, [CONTRACT, RECEIPT, WARRANTY, BANK_DOC])
        current, read = pdf_report(printed(direct(), "d02"), direct)
        old = archived(current)
        self.assertEqual(by_rule(old, "H01")[0]["status"], "ok")
        self.assertNotIn("power_of_attorney", old["graph"]["documents_by_kind"])
        verify_findings(old)
        execution.verify(old, read, signing=True)
