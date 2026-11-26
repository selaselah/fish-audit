import copy
import unittest

import contract_folios
from controls import VERSION, execute
from performance import PROFILE, verify_findings
from test_performance import BANK_DOC, CONTRACT, RECEIPT, WARRANTY, material

ROOT = [r for r in CONTRACT if r[1] not in ("第二期", "第三期")]
STAGES = [r for r in CONTRACT if r[1] in ("第二期", "第三期")]
DRAFT = "续页说明：本页付款安排仅供讨论，双方未确认"
FIRST = "首款约定：首笔款项按合同正文独立执行，续页修改不影响首笔款项"


def fixture(
    notes=(),
    *,
    first=(),
    stages=STAGES,
    unobserved=(),
    layer="text",
    text_only=True,
    attest=None,
    root=ROOT,
    bank=BANK_DOC,
    edit_second=None,
):
    lines = [*notes, *[label + "：" + value for _, label, value in stages], *unobserved]
    rects = {str(i): [[0.1, 0.1, 0.9, 0.2]] for i in range(1, len(lines) + 1)}
    page = {
        "doc": "d01",
        "number": 2,
        "sha256": "second",
        "text": "\n".join(lines),
        "layer": {"type": layer, "clause_text_only": text_only, "lines": rects},
        "extraction": {
            "output": {
                "quality": "readable",
                "facts": [
                    {"field": field, "value": v, "quote": k + "：" + v, "region": "top"}
                    for field, k, v in stages
                ],
            }
        },
    }
    if edit_second:
        edit_second(page)
    graph = material(
        [root, RECEIPT, WARRANTY, bank],
        extra_pages=[page],
        omissions=[(1, s) for s in first],
        attestations=attest,
    )
    report = {
        "graph": graph,
        "findings": execute(graph, PROFILE),
        "policy": {**VERSION, "profile": PROFILE},
    }
    pages = [
        ("d01", 1, [k + "：" + v if k else v for _, k, v in root] + list(first)),
        ("d01", 2, lines),
    ]
    texts = {(doc, n): "\n".join(rows) for doc, n, rows in pages}
    numbers = contract_folios.page_lines(graph["contract_folio_sources"])
    report["calls"] = {
        "pages": [
            {
                "doc": doc,
                "page": n,
                **(page["extraction"] if n == 2 else {}),
                "contract_folio_rects": contract_folios.geometry(
                    numbers[doc, n],
                    {
                        "lines": {
                            str(i): [[0.1, 0.1, 0.9, 0.2]]
                            for i in range(1, len(rows) + 1)
                        }
                    },
                ),
            }
            for doc, n, rows in pages
            if numbers.get((doc, n))
        ]
    }
    return report, lambda doc, n: texts[doc, n]


def rows(report, rule):
    return [f for f in report["findings"] if f["rule"] == rule]


class ContractFoliosTests(unittest.TestCase):
    def test_plain_continuation_recovers_each_original_stage(self):
        for notes in ([], ["采购合同续页"], ["付款条款续页", "关联协议编号：YL-121"]):
            report, read = fixture(notes)
            (plan,) = rows(report, "H03")
            self.assertEqual(plan["status"], "ok")
            check = plan["contract_folios"]
            self.assertEqual(
                (check["state"], [p["stages"] for p in check["pages"]]),
                ("continued", [["第一期"], ["第二期", "第三期"]]),
            )
            self.assertTrue(
                all(
                    f["status"] == "ok"
                    for f in report["findings"]
                    if f["rule"].startswith("H")
                )
            )
            self.assertTrue(
                all(
                    set(check["evidence"]) <= set(f["evidence"])
                    for f in rows(report, "H04") + rows(report, "H05")
                )
            )
            contract_folios.verify(report, read)

    def test_matching_figures_do_not_resolve_the_continuation(self):
        for note, state in [
            (DRAFT, "provisional"),
            ("关联协议编号：YL-999", "foreign"),
            ("附件二  付款计划", "attachment"),
            ("适用合同：YL-1 21", "identity"),
            ("适用合同：尾号121", "identity"),
            ("关联协议编号：YL-①21", "identity"),
            ("备注：最终条款由双方另签盖章件为准", "scope"),
        ]:
            with self.subTest(note=note):
                report, _ = fixture([note])
                (plan,) = rows(report, "H03")
                check = plan["contract_folios"]
                self.assertEqual(
                    (check["state"], plan["status"]),
                    (state, "risk" if state == "foreign" else "missing"),
                )
                self.assertEqual(
                    [f["status"] for f in rows(report, "H01") + rows(report, "H02")],
                    ["ok", "ok"],
                )
                self.assertTrue(
                    all(
                        f["status"] == "missing"
                        for f in rows(report, "H04") + rows(report, "H05")
                    )
                )
                entry = next(
                    r
                    for r in report["graph"]["contract_folio_sources"]["lines"]
                    if r["quote"] == note
                )
                self.assertEqual(entry["facts"], [])
                self.assertEqual(check["pages"][1]["focus"], entry["id"])
                self.assertTrue(
                    all(
                        entry["id"] in f["evidence"]
                        for f in [plan, *rows(report, "H04"), *rows(report, "H05")]
                    )
                )

    def test_independent_first_payment_needs_explicit_unqualified_root(self):
        first_bank = [
            (f, l, "第一期" if f == "payment_designation" else v)
            for f, l, v in BANK_DOC
        ]
        report, _ = fixture([DRAFT], first=[FIRST], bank=first_bank)
        self.assertEqual(
            [f["status"] for f in rows(report, "H04")], ["ok", "missing", "missing"]
        )
        self.assertEqual(rows(report, "H05")[0]["status"], "ok")
        for options in (
            {"notes": [DRAFT]},
            {"notes": [DRAFT, "另有内部口头条件"], "first": [FIRST]},
            {"notes": [DRAFT, "关联合同编号：YL-999"], "first": [FIRST]},
            {"notes": [FIRST, DRAFT]},
            {"notes": [DRAFT], "first": [FIRST, "首款须另行审批"]},
            {"notes": ["本合同仅供讨论"], "first": [FIRST]},
        ):
            report, _ = fixture(**options)
            self.assertTrue(all(f["status"] != "ok" for f in rows(report, "H04")))

    def test_entire_contract_qualification_applies_to_effect(self):
        report, _ = fixture(["本合同仅供讨论，双方未确认"])
        self.assertEqual(rows(report, "H01")[0]["status"], "missing")
        self.assertTrue(rows(report, "H03")[0]["contract_folios"]["whole"])

    def test_source_ambiguity_duplicate_stage_and_missing_line(self):
        cases = [
            ({"notes": ["付款条款续页"], "unobserved": ["第四期：另付5%"]}, "terms"),
            ({"unobserved": ["第二期：最终验收合格后支付60%"]}, "duplicate"),
            (
                {"notes": ["付款条款续页"], "layer": "image", "text_only": False},
                "source",
            ),
            ({"notes": ["付款条款续页"], "text_only": False}, "source"),
            ({"attest": {"d01/p2/f1": {"decision": "dispute"}}}, "source"),
            ({"root": [r for r in ROOT if r[0] != "contract_id"]}, "identity"),
        ]
        for spec, state in cases:
            with self.subTest(state=state):
                report, _ = fixture(**spec)
                plan = rows(report, "H03")[0]
                self.assertEqual(plan["contract_folios"]["state"], state)
                self.assertNotEqual(plan["status"], "ok")

    def test_normal_archive_fixed_revision_and_raw_row_guard(self):
        report, read = fixture([DRAFT])
        contract_folios.verify(report, read)
        verify_findings(report)
        for mutate in (
            lambda r: r["graph"]["contract_folio_sources"]["lines"].pop(),
            lambda r: r["graph"]["edges"].remove(
                next(
                    e
                    for e in r["graph"]["edges"]
                    if e["type"] == "contract_folio_basis"
                )
            ),
            lambda r: r["calls"]["pages"][1]["contract_folio_rects"].pop("1"),
            lambda r: r["policy"].pop("contract_folios"),
        ):
            wrong = copy.deepcopy(report)
            mutate(wrong)
            with self.assertRaises(ValueError):
                contract_folios.verify(wrong, read)
        with self.assertRaises(ValueError):
            contract_folios.verify(report, lambda d, n: read(d, n) + " ")
        with self.assertRaisesRegex(ValueError, "定位与原件"):
            contract_folios.verify(report, read, read_layout=lambda d, n: {"lines": {}})
        rows(report, "H03")[0]["contract_folios"]["pages"][1]["focus"] = "d01/p1"
        with self.assertRaises(ValueError):
            verify_findings(report)

    def test_old_archives_replay_but_unsupported_approval_requires_new_revision(self):
        for notes, allowed in [
            ([DRAFT], False),
            (["关联协议编号：YL-999"], False),
            (["付款条款续页"], True),
        ]:
            report, read = fixture(notes)
            graph = report["graph"]
            del report["policy"]["contract_folios"]
            report["policy"]["version"] = "2026.11.26.09"
            del graph["contract_folio_sources"]
            graph["nodes"] = [
                n for n in graph["nodes"] if n["type"] != "contract_folio_line"
            ]
            graph["edges"] = [
                e for e in graph["edges"] if e["type"] != "contract_folio_basis"
            ]
            report["findings"] = execute(graph, PROFILE)
            for t in report["calls"]["pages"]:
                t.pop("contract_folio_rects", None)
            contract_folios.verify(report, read)
            if allowed:
                contract_folios.verify(report, read, signing=True)
            else:
                with self.assertRaisesRegex(ValueError, "重新审计"):
                    contract_folios.verify(report, read, signing=True)
