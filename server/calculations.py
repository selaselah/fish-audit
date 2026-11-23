"""Reconstruct typed monetary formulas from cited, verified facts using only the standard library."""

import re
import unicodedata
from collections import defaultdict
from decimal import Decimal


FORMAT = "cny-evidence-v1"
AMOUNT = re.compile(r"-?(?:[0-9]{1,17}|[0-9]{1,3}(?:,[0-9]{3}){1,5})(?:\.[0-9]{1,2})?")
INCOMPATIBLE = ("万", "亿", "千元", "美元", "港元", "欧元", "%", "折合")
NAMES = {"vat_balance": "不含税额加税额与票面总额的差额", "accepted_minus_contract": "验收与合同差额",
         "invoice_minus_contract": "发票与合同差额", "invoice_minus_acceptance": "发票与验收差额",
         "invoice_sum": "发票合计", "claim_minus_invoices": "申请与凭证差额"}
FIELDS = {"net":"不含税合计", "tax":"税额合计", "total":"含税总额", "claim_total":"申请金额"}
KINDS = {"invoice":"发票", "contract":"合同", "acceptance":"验收单", "claim":"报销单"}


def normalized(value):
    return "".join(unicodedata.normalize("NFKC", value).split())


def money(fact):
    value = normalized(fact["value"])
    if not AMOUNT.fullmatch(value) or any(unit in normalized(fact["quote"]) for unit in INCOMPATIBLE):
        return None
    return Decimal(value.replace(",", ""))


def in_yuan(fact):
    return normalized(fact["value"]).upper() in {"人民币", "CNY", "RMB", "人民币元"}


class CalculationEvidence:
    def __init__(self, graph):
        self.kinds = graph["documents_by_kind"]
        self.facts = {f["id"]: f for f in graph["facts"]}
        self.by_field = defaultdict(list)
        for edge in graph["edges"]:
            if edge["type"] not in {*FIELDS, "currency", "unit"}:
                continue
            for ref in edge["evidence"]:
                fact = self.facts.get(ref)
                if (fact and fact["status"] in ("anchored", "confirmed") and fact["field"] == edge["type"]
                        and fact.get("unit", fact["doc"]) == edge["from"]):
                    self.by_field[edge["from"], edge["type"]].append(fact)

    def operand(self, allowed, kind, scope, field, sign):
        def cited(key):
            candidates = self.by_field[scope, key]
            if len({normalized(f["value"]) for f in candidates}) != 1:
                raise ValueError("运算项的已核数值缺失或存在歧义")
            for fact in candidates:
                if fact["id"] in allowed and normalized(fact["value"]) in normalized(fact["quote"]):
                    return fact
            raise ValueError("算式缺少对应单据的已核引文")

        amount, currency, unit = (cited(key) for key in (field, "currency", "unit"))
        number = money(amount)
        if number is None or number < 0 or not in_yuan(currency) or normalized(unit["value"]) not in ("元", "人民币元"):
            raise ValueError("算式的金额、币种或单位不在本程序范围内")
        return {"scope": scope, "kind": kind, "field": field, "sign": sign, "label": KINDS[kind]+" · "+FIELDS[field],
                "amount_fact": amount["id"], "raw": amount["value"], "currency_fact": currency["id"],
                "unit_fact": unit["id"], "decimal": format(number, ".2f")}

    def formulas(self, finding):
        rule, status = finding["rule"], finding["status"]
        if rule not in {"M01", "M02", "T03"} or status == "missing" or (rule == "M01" and status == "risk"):
            return []
        allowed = set(finding["evidence"])
        invoices = self.kinds.get("invoice", [])
        def one(kind):
            docs = self.kinds.get(kind, [])
            if len(docs) != 1:
                raise ValueError("算式的单据范围不唯一")
            return docs[0]

        def terms(kind, docs, field="total", sign=1):
            return [self.operand(allowed, kind, doc, field, sign) for doc in docs]

        def formula(operation, operands):
            result = sum(Decimal(op["decimal"]) * op["sign"] for op in operands)
            return {"operation": operation, "label": NAMES[operation], "currency": "CNY", "unit": "元",
                    "operands": operands, "result": format(result, ".2f")}

        if not invoices or len(invoices) != len(set(invoices)):
            raise ValueError("算式的发票范围为空或重复")
        if rule == "M01":
            scopes = {self.facts[ref].get("unit", self.facts[ref]["doc"]) for ref in allowed
                      if ref in self.facts and self.facts[ref]["field"] == "net"}
            if len(scopes) != 1 or not scopes.issubset(invoices):
                raise ValueError("价税算式引用的发票归属不一致")
            doc = scopes.pop()
            result = formula("vat_balance", [self.operand(allowed, "invoice", doc, field, sign)
                                             for field, sign in (("net", 1), ("tax", 1), ("total", -1))])
            calculations = [result]
            expected = "issue" if Decimal(result["result"]) else "ok"
        elif rule == "T03":
            claim = terms("claim", [one("claim")], "claim_total")
            total = formula("invoice_sum", terms("invoice", invoices))
            delta = formula("claim_minus_invoices", claim + terms("invoice", invoices, sign=-1))
            difference = Decimal(delta["result"])
            expected = "issue" if difference > 0 else ("risk" if difference < 0 else "ok")
            calculations = [total, delta]
        else:
            contract = terms("contract", [one("contract")], sign=-1)
            acceptance = [one("acceptance")]
            invoiced = terms("invoice", invoices)
            delta = formula("invoice_minus_contract", invoiced + contract)
            if len(invoices) > 1:
                calculations = [formula("invoice_sum", invoiced), delta,
                                formula("invoice_minus_acceptance", invoiced + terms("acceptance", acceptance, sign=-1))]
                expected = "risk"
            else:
                received = formula("accepted_minus_contract", terms("acceptance", acceptance) + contract)
                calculations = [delta, received]
                expected = "issue" if any(Decimal(f["result"]) for f in calculations) else "ok"
        if status != expected:
            raise ValueError("算式结果与本项程序的结论不一致")
        return calculations

    def verify(self, findings):
        for finding in findings:
            if self.formulas(finding) != finding.get("calculations", []):
                raise ValueError("金额算式、引文或计算结果不一致")
