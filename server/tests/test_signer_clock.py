import copy
import unittest

from acceptance_authority import page_evidence, verify_sources, witness_edges
from controls import VERSION, execute
from performance import compute, verify_findings
from signer_timing import PRINTED_ROWS_FORMAT
from test_acceptance_authority import JOINT, contract, sign
from test_performance import BANK_DOC, RECEIPT, WARRANTY, material
from test_signer_timing import DATES, payment


SIGN_TIME = "林岚签认时间：2026年9月25日 15:20（北京时间）"
EARLY = "实际扣款时间：2026年9月25日 13:10（北京时间）"
LATE = "实际扣款时间：2026年9月25日 16:30（北京时间）"


def example(receipt=(*DATES, SIGN_TIME), bank=(EARLY,), *, typed=(), typed_bank=(), extra=(), edit=None, confirm=True):
    groups = [contract(JOINT), [*sign(RECEIPT, "周宁", "林岚"), *typed], WARRANTY, [*BANK_DOC, *typed_bank], *extra]
    def change(i, field, label, value):
        if field == "paid_on" and label == "付款日期":
            value = "2026-09-25"
        return edit(i, field, label, value) if edit else value
    omitted = [(2, line) for line in receipt] + [(4, line) for line in bank]
    graph = material(groups, change, omissions=omitted, confirm=confirm)
    def read(doc, page):
        return "\n".join([*(f["quote"] for f in graph["facts"] if f["doc"] == doc),
                          *(line for i, line in omitted if doc == f"d{i:02d}")])
    return graph, read


class SignerClockTests(unittest.TestCase):
    def test_only_proven_actual_debit_and_last_required_signature_determine_order(self):
        for source, state, status in ((EARLY, "before", "risk"), (LATE, "after", "missing"),
                                      (LATE.replace("16:30", "15:20:59"), "overlap", "missing"),
                                      (LATE.replace("16:30", "15:21"), "after", "missing"),
                                      (EARLY.replace("13:10", "15:19:59"), "before", "risk")):
            with self.subTest(source=source):
                graph, _ = example(bank=(source,))
                f = payment(graph)
                timing = f["signer_timing"]
                clock = timing["clock"]
                self.assertEqual((timing["state"], timing["days"], clock["state"], f["status"]), ("same_day", 0, state, status))
                self.assertEqual(clock["relevant"], ["林岚"])
                self.assertEqual(set(clock["rows"]), {clock["signers"]["林岚"], clock["debit"]})
                self.assertTrue(set(clock["rows"] + list(clock["days"].values())) <= set(f["evidence"]))
                self.assertEqual(next(f["status"] for f in compute(graph) if f["rule"] == "H02"), "missing")

    def test_receipt_printing_and_acceptance_are_never_a_debit(self):
        for label in ("回单打印时间", "受理时间", "交易时间", "记账时间", "到账时间"):
            graph, _ = example(bank=(LATE.replace("实际扣款时间", label),))
            f = payment(graph)
            self.assertEqual((f["status"], f["signer_timing"]["clock"]["debit"], f["signer_timing"]["clock"]["state"]),
                             ("missing", None, "missing"))
        graph, _ = example(bank=(EARLY, LATE.replace("实际扣款时间", "回单打印时间")))
        self.assertEqual(payment(graph)["signer_timing"]["clock"]["state"], "before")

    def test_ambiguity_timezone_and_incomplete_evidence_require_review(self):
        same = DATES[0].replace("20日", "25日")
        for receipt, bank, state in (
            ((same, DATES[1], SIGN_TIME), (LATE,), "missing"),
            ((same, DATES[1], SIGN_TIME, "周宁签认时间：17:05（北京时间）"), (LATE,), "before"),
            ((*DATES, SIGN_TIME.replace("（北京时间）", "")), (LATE,), "zone"),
            ((*DATES, SIGN_TIME), (LATE.replace("（北京时间）", ""),), "zone"),
            ((*DATES, SIGN_TIME, SIGN_TIME), (LATE,), "conflict"),
            ((*DATES, SIGN_TIME), (EARLY, LATE), "conflict"),
            ((*DATES, SIGN_TIME), (EARLY.replace("25日", "24日"),), "conflict"),
            ((*DATES, SIGN_TIME.replace("25日", "24日")), (LATE,), "conflict"),
            ((*DATES, SIGN_TIME, "周朗签认时间：16:20（北京时间）"), (LATE,), "conflict"),
            ((*DATES, SIGN_TIME, "附注：实际签认次日补办"), (LATE,), "scope"),
        ):
            with self.subTest(receipt=receipt, bank=bank):
                graph, _ = example(receipt, bank)
                f = payment(graph)
                self.assertEqual(f["signer_timing"]["clock"]["state"], state)
                self.assertEqual(f["status"], "risk" if state == "before" else "missing")
        graph, _ = example(confirm=False)
        self.assertEqual(payment(graph)["signer_timing"]["state"], "incomplete")
        graph, _ = example()
        graph["acceptance_authority_sources"]["bank_pages"][0]["text_only"] = False
        self.assertEqual(payment(graph)["signer_timing"]["clock"]["state"], "scope")

    def test_separately_labelled_clock_facts_never_replace_party_date_or_signature(self):
        graph, _ = example(receipt=(DATES[0],), bank=(),
                           typed=[("acceptance_signer", *SIGN_TIME.split("：", 1))],
                           typed_bank=[("paid_on", *EARLY.split("：", 1))])
        f = payment(graph)
        clock = f["signer_timing"]["clock"]
        self.assertEqual((clock["state"], f["status"]), ("before", "risk"))
        self.assertEqual(clock["days"]["林岚"], clock["signers"]["林岚"])
        self.assertNotEqual(clock["debit"], f["signer_timing"]["paid_ref"])
        for edits in (lambda i,k,l,v: "演练丙" if k == "payee" else v,
                      lambda i,k,l,v: "交易处理中" if k == "transfer_status" else v,
                      lambda i,k,l,v: "第一期" if k == "payment_designation" else v):
            g, _ = example(edit=edits)
            self.assertNotIn("signer_timing", payment(g))
        graph, _ = example(extra=([*BANK_DOC, ("paid_on", *LATE.split("：", 1))],))
        self.assertEqual([f["signer_timing"]["clock"]["state"] for f in compute(graph) if f["rule"] == "H05"], ["before", "after"])

    def test_archive_rebuilds_sources_refuses_tampered_order_and_preserves_v4_replay(self):
        g, read = example()
        def paper(graph, version, marker):
            findings = execute(graph, graph["profile"])
            graph["edges"].extend(witness_edges(findings))
            for f in findings:
                f["version"] = version
            return {"policy": {**VERSION, "version": version, "acceptance_authority": marker,
                               "profile": graph["profile"]}, "graph": graph, "findings": findings}
        issued = paper(g, VERSION["version"], VERSION["acceptance_authority"])
        verify_sources(issued, read)
        verify_findings(issued)
        for tamper in ("source", "edge", "clock", "policy"):
            bad = copy.deepcopy(issued)
            if tamper == "clock":
                next(f for f in bad["findings"] if f["rule"] == "H05")["signer_timing"]["clock"]["state"] = "after"
                with self.assertRaises(ValueError): verify_findings(bad)
                continue
            if tamper == "source":
                bad["graph"]["acceptance_authority_sources"]["clock_rows"][0]["at"] = "19:30"
            elif tamper == "edge":
                next(e for e in bad["graph"]["edges"] if e["type"] == "acceptance_clock_source")["from"] = "d01/p1"
            else:
                bad["policy"]["acceptance_authority"] = PRINTED_ROWS_FORMAT
            with self.assertRaises(ValueError): verify_sources(bad, read)
        old = copy.deepcopy(g)
        source = page_evidence(old, read, PRINTED_ROWS_FORMAT)
        old["acceptance_authority_sources"] = source
        old["edges"] = [e for e in old["edges"] if e["type"] not in ("named_acceptance_signature", "signer_date_source", "acceptance_clock_source")]
        old["nodes"] = [n for n in old["nodes"] if n["type"] not in ("acceptance_clock_line", "acceptance_signer_date")]
        from signer_timing import source_graph
        nodes, edges = source_graph(source["dates"])
        old["nodes"].extend(nodes)
        old["edges"].extend(edges)
        legacy = paper(old, "2026.11.26.23", PRINTED_ROWS_FORMAT)
        verify_sources(legacy, read)
        verify_findings(legacy)
        with self.assertRaisesRegex(ValueError, "旧版"): verify_sources(legacy, read, signing=True)

    def test_omitted_model_rows_get_their_own_verified_printed_coordinates(self):
        import signer_clock
        from contract_folios import geometry, line_numbers
        graph, _ = example()
        rows = signer_clock.located_rows(graph["acceptance_authority_sources"])
        rects = [[0.1, 0.3, 0.6, 0.4]]
        layout = {"lines": {str(r["line"]): rects for r in rows}}
        calls = [{"doc": doc, "page": page, "signer_timing_rects": geometry(numbers, layout)}
                 for (doc, page), numbers in line_numbers(rows).items()]
        paper = {"graph": graph, "calls": {"pages": calls}}
        signer_clock.verify_geometry(paper, lambda doc, page: layout)
        call = calls[-1]["signer_timing_rects"]
        line = next(iter(call))
        call[line] = [[0.2, 0.3, 0.6, 0.4]]
        with self.assertRaisesRegex(ValueError, "原件分页"): signer_clock.verify_geometry(paper, lambda doc, page: layout)
        del call[line]
        with self.assertRaisesRegex(ValueError, "行号"): signer_clock.verify_geometry(paper)
