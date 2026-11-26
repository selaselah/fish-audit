import copy
import unittest

import contract_calendar
from contract_effect import WORD_FORMAT, sources, verify
from controls import VERSION, execute
from graph import link_procedures
from model import FIELDS
from performance import Material, compute, printed_day, verify_findings
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material
from test_signing_parties import original_reader


def sample(value, omitted=()):
    return material([CONTRACT, RECEIPT, WARRANTY, BANK_DOC],
                    lambda i, f, label, v: value if f == "effect_on" else v, omissions=omitted)


def paper(graph, policy=VERSION):
    findings = execute(graph, graph["profile"])
    for f in findings:
        f["version"] = policy["version"]
    link_procedures(graph, findings, {"expert": {"model": "fixture"}, "pages": []})
    return {"policy": {**policy, "profile": graph["profile"]}, "graph": graph, "findings": findings}


class ContractCalendarTests(unittest.TestCase):
    def test_requires_complete_consistently_separated_real_dates(self):
        for value, expected in (("2024 年 02 月 29 日", "2024-02-29"), ("2026 - 9 - 1", "2026-09-01"),
                                ("2026/9/1", "2026-09-01"), ("2026.09.01", "2026-09-01")):
            self.assertEqual(contract_calendar.tokens(value)[2], expected)
        for value in ("2026/9月1日", "2026年9月1", "2026-09/01", "2026 年 9 月 1 0 日",
                      "２０２６年９月１日", "2026年⑨月①日", "2026年9月**日", "2026年02月29日", "2026-00-01"):
            with self.subTest(value=value):
                graph = sample(value)
                self.assertIsNone(printed_day(Material(graph, "d01"), "effect_on"))
                readings = compute(graph)
                self.assertEqual([f["status"] for f in readings], ["missing","ok","ok",*(["missing"] * 4)])
                row = next(r for r in graph["contract_effect_sources"]["date_rows"] if r["field"] == "effect_on")
                self.assertIn(row["id"], readings[0]["evidence"])
                self.assertTrue(all(row["id"] in f["evidence"] for f in readings[3:]))

    def test_whole_transcription_and_independent_check_bound_to_exact_source(self):
        graph = sample("2026 年 9 月 1 日")
        fact = next(f for f in graph["facts"] if f["field"] == "effect_on")
        native = fact["quote"]
        fact.update(quote="实际生效日期：2026年9月1日", value="2026年9月1日", visual_check="clear",
                    response_id="first", check_response_id="second")
        ref = fact["id"].rsplit("f",1)[1]
        raw = {k:fact[k] for k in ("field","value","quote")}
        call = {"response_id":"first", "output":{"facts":[{}] * (int(ref)-1) + [raw]},
                "check":{"response_id":"second", "input":[{**raw,"field":FIELDS["effect_on"],"index":ref}],
                         "output":{"checks":[{"index":ref,"support":"clear"}]}}}
        def inspect(c):
            return contract_calendar.row({"doc":"d01","unit":"d01","page":1}, native, fact["source_line"]["number"],
                                         [fact], graph, "page", "sample", c)
        self.assertEqual((inspect(call)["state"], inspect(call)["date"], inspect(call)["witness"]),
                         ("spacing","2026-09-01","visual_check"))
        for key in ("input", "votes", "same_call", "other_digit", "other_field", "no_geometry", "page_hash"):
            with self.subTest(key=key):
                changed = copy.deepcopy(call)
                old = copy.deepcopy(fact)
                if key == "input":
                    changed["check"]["input"][0]["quote"] += " "
                    changed["check"]["input"][0]["value"] = "2026年9月01日"
                elif key == "votes":
                    changed["check"]["output"]["checks"] *= 2
                elif key == "same_call":
                    changed["check"]["response_id"] = "first"
                elif key == "other_digit":
                    fact["value"] = "2026年9月01日"
                elif key == "other_field":
                    fact["field"] = "signed_on"
                elif key == "no_geometry":
                    fact["source_line"]["rects"] = []
                else:
                    fact["page_sha256"] = "different"
                self.assertIsNone(inspect(changed)["date"])
                fact.clear()
                fact.update(old)
        fact.update(status="confirmed",attestation={"fact":fact["id"],"decision":"confirm","rev":1,"source_check":{
            "format":"field-source-v1","operation":"confirm","rev":1,"report_hash":"a"*64,"doc":"d01","page":1,
            "original_sha256":"sample","page_sha256":"page"}})
        self.assertEqual(inspect({})["witness"], "field_receipt")
        fact["attestation"]["source_check"]["report_hash"] = "short"
        self.assertIsNone(inspect({})["date"])

    def test_duplicate_or_unread_native_line_never_selects_a_convenient_date(self):
        for other, expected in (("2026年9月1日","multiple"), ("2026年9月23日","conflict")):
            omitted = [(1, "生效确认日期：" + other)]
            graph = sample("2026年9月1日", omitted)
            record = paper(graph)
            h01 = next(f for f in record["findings"] if f["rule"]=="H01")
            event = next(e for e in h01["effect_review"]["calendar"] if e["field"]=="effect_on")
            self.assertEqual((event["state"],event["date"],len(event["rows"])), (expected,None,2))
            self.assertNotEqual(h01["status"], "ok")
            if expected == "conflict":
                self.assertEqual(h01["status"], "risk")
            self.assertFalse(graph["contract_effect_sources"]["date_rows"][-1]["facts"])
            self.assertTrue(set(event["rows"]).issubset(h01["evidence"]))
            read = original_reader(graph, omitted)
            verify(record, read)
            verify_findings(record)
            for key in ("row", "edge", "ledger", "finding"):
                changed = copy.deepcopy(record)
                g = changed["graph"]
                if key == "row":
                    next(n for n in g["nodes"] if n["type"]=="contract_date_line")["label"] += "改"
                elif key == "edge":
                    next(e for e in g["edges"] if e["type"]=="contract_date_source")["evidence"] = []
                elif key == "ledger":
                    g["contract_effect_sources"]["date_rows"][-1]["line"] = 1
                else:
                    next(f for f in changed["findings"] if f["rule"]=="H01")["effect_review"]["calendar"] = []
                with self.assertRaises(ValueError):
                    (verify_findings(changed) if key == "finding" else verify(changed,read))

    def test_legacy_dates_replay_and_prevent_only_an_unsupported_signoff(self):
        for value, blocked in (("2026/9月1日", True), ("2026-09-01", False)):
            graph = sample(value)
            read = original_reader(graph)
            graph["contract_effect_sources"] = sources(graph,read,WORD_FORMAT)
            saved = paper(graph,{**VERSION,"version":"2026.11.26.12","contract_effect":WORD_FORMAT})
            self.assertTrue(all(f["status"]=="ok" for f in saved["findings"] if f["rule"].startswith("H")))
            verify(saved, read)
            verify_findings(saved)
            if blocked:
                with self.assertRaisesRegex(ValueError,"合同日期"):
                    verify(saved, read, signing=True)
            else:
                verify(saved, read, signing=True)

    def test_extra_approval_in_same_date_line_is_retained(self):
        graph = sample("2026年9月1日，另须经董事会批准")
        h01 = compute(graph)[0]
        self.assertTrue(any("董事会" in r["quote"] for r in h01["effect_review"]["conditions"]))
        self.assertIsNone(printed_day(Material(graph, "d01"), "effect_on"))
