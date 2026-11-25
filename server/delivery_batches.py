"""Reconcile contract batch allocations with separately numbered acceptance records."""

import hashlib
import re
from collections import defaultdict
from unicodedata import normalize

import equipment_models
from acceptance_authority import CLAUSE, LABELS as SIGNING_LABELS, covers, instruction, parts, required_names, signed_name
from calculations import normalized
from contract_changes import labelled_sources
from delegation import complete_id, covered_rows
from performance_versions import BATCH_FORMATS
from reinspection import LINK_KEYS, linked


LEGACY = "contract-delivery-batches-v1"
SIGNING_FORMAT = "contract-delivery-batches-v2"
FINAL_FORMAT = "contract-delivery-batches-v3"
FINAL_SIGNING_FORMAT = "contract-delivery-batches-v4"
FORMAT = "contract-delivery-batches-v5"
FINAL_SIGNING_FORMATS = (FINAL_SIGNING_FORMAT,FORMAT)
FINAL_FORMS = (FINAL_FORMAT,*FINAL_SIGNING_FORMATS)
BATCH_SIGNING_FORMATS = (SIGNING_FORMAT,*FINAL_FORMS)
FINAL_REFS = "batch_receipt_refs"
LABELS = {"delivery_batch":("分批交付","约定交付批次","批次交付明细"),
          "batch_clause":("分批验收约定","分批验收条款","批次验收约定"),
          "delivered_serials":("验收设备编号","实收设备编号","验收序列号"),
          FINAL_REFS:("所附批次验收单号","所据批次验收单号","关联批次验收单号")}
NUM = r"(?:[1-9][0-9]?|[一二两三四五六七八九十]{1,3})"
BATCH = r"第("+NUM+r")批"
HINT = re.compile(r"分批(?:验收|交付|交货|付款)|批次(?:交付|验收|付款)|第"+NUM+r"批(?:次)?(?:交付|到货|验收|款|设备|[0-9])")
QUANTITY = r"([1-9][0-9]{0,8})\s*(台套|台|套|件|个|只|辆|箱)"
ALLOCATION = re.compile(BATCH+r"\s*"+QUANTITY+r"(?:\s*[,，]\s*(?:设备编号|序列号)\s*[:：]?\s*(.+))?")
SCOPE = re.compile(BATCH+r"(?:交付)?(?:验收|全部验收)")
PAYMENT = re.compile(BATCH+r"(?:交付)?验收合格后(?:支付|付)(?:合同(?:总价|价款|总额)的?)?\d{1,3}(?:\.\d{1,4})?%")
SIGNING = re.compile(r"(?:"+BATCH+r"|各批)(?:交付)?验收(?:均)?(?:须|应)由(.+?)(共同签字确认|共同签名确认|签字确认|签名确认)")
INDEPENDENT = {"各批独立验收付款","各批分别验收并独立付款"}
COMPLETION = {"全部批次验收合格视为终验合格","各批全部验收合格视为终验合格"}
SEPARATE_FINAL = {"另行组织最终验收","另行终验"}
FINAL_SCOPES = {"全部交付终验","全部交付最终验收","全部标的最终验收"}
LOCAL_NOTES = {"附注:本次为暂收,质量待验","附注:本批为暂收,质量待验","备注:本批质量待验"}
PAYMENT_RIDER = re.compile(r"预付款|首付款|第"+NUM+r"期.{0,16}(?:付款|支付|付前)|各期付款|暂停(?:全部)?付款|履约保函")
CONTRACT_RIDER = re.compile(r"(?:原合同|本合同|合同效力).{0,12}(?:作废|撤销|解除|终止|中止|无效)|补充协议")
DIGITS = dict(zip("一二两三四五六七八九", (1,2,2,3,4,5,6,7,8,9)))
RECEIPT_FIELDS = ("acceptance",*LINK_KEYS,"acceptance_scope","acceptance_number","accepted_on","quantity_accepted",
                  "delivered_serials","inspection_basis","measured_result","acceptance_result","acceptance_signer","acceptance_exception")


def ordinal(value):
    if value.isascii() and value.isdigit():
        return int(value)
    if value in DIGITS:
        return DIGITS[value]
    tens,mark,ones = value.partition("十")
    if mark and (not tens or tens in DIGITS) and (not ones or ones in DIGITS):
        return DIGITS.get(tens,1)*10+DIGITS.get(ones,0)
    return None


def serials(value):
    if not value:
        return []
    items = [v.strip() for v in re.split(r"[、,]",value)]
    if (not all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}",v) and identifier(v) for v in items)
            or len(items)!=len(set(items))):
        return None
    return items


def identifier(value):
    return complete_id(value) and value.upper() not in {"NA","NONE","UNKNOWN","待补","待填","未知","未提供"}


def receipt_numbers(value):
    numbers=[s.strip() for s in re.split(r"[、,]",value)]
    if all(identifier(s) and re.search(r"[0-9]",s) and re.fullmatch(r"[A-Za-z0-9._-]+",s) for s in numbers):
        return numbers
    return []


def printed_references(fact):
    if not fact:
        return []
    printed=receipt_numbers(raw_body(fact))
    label,value=parts(fact["value"])
    observed=value if label in LABELS[FINAL_REFS] else normalize("NFKC",fact["value"]).strip()
    return printed if printed==receipt_numbers(observed) else []


def raw_body(fact):
    line = (fact.get("source_line") or {})
    if (fact["status"] not in ("anchored","confirmed") or not line.get("rects") or
            not covers(fact["field"],fact["value"],fact["quote"]) or parts(line["text"])!=parts(fact["quote"])):
        return ""
    return parts(line["text"])[1]


def one(doc,field):
    facts=doc.fields[field]
    return facts[0] if len(facts)==1 and not doc.incomplete(field) and raw_body(facts[0]) else None


def body(doc,field):
    fact=one(doc,field)
    return raw_body(fact) if fact else ""


def quantity(value):
    match = re.fullmatch(QUANTITY,value)
    return (int(match[1]),match[2]) if match else (None,None)


def quantity_text(count,unit):
    return str(count)+unit if count is not None else None


def signing_clause(quote):
    label,body=parts(quote)
    match=SIGNING.fullmatch(body.rstrip("。")) if label in SIGNING_LABELS[CLAUSE] else None
    if not match or re.search(r"任选|任一|之一|或|代为|代签|授权|另行|同上|同前|待定|待填",match[2]):
        return None
    names=required_names(match[2],match[3].startswith("共同"))
    index=ordinal(match[1]) if match[1] else 0
    return (index,names) if index is not None and names else None


def final_signers(quote):
    _,body=parts(quote)
    if not body.startswith(("终验","最终验收")) or re.search(r"任选|任一|之一|或|代为|代签|授权|同上|同前|待定|待填",body):
        return None
    directive=instruction(quote)
    return directive[2] if directive and directive[1]=="final" else None


def separate_clause(fact):
    terms=raw_body(fact).strip("。").split(",") if fact else []
    return len(terms)==2 and terms[0] in INDEPENDENT and terms[1] in SEPARATE_FINAL


def literal_value(fact):
    body=raw_body(fact) if fact else ""
    return bool(body and normalize("NFKC",fact["value"]).strip() in (body,normalize("NFKC",fact["source_line"]["text"]).strip()))


def page_sources(graph,read_text,version=FORMAT):
    contracts=set(graph["documents_by_kind"].get("contract",[]))
    receipts=set(graph["documents_by_kind"].get("acceptance",[]))
    units={(d["source"],d["page"]):d["id"] for d in graph.get("audit_documents",[]) if "source" in d}
    signals=[]
    pages={n["id"]:n for n in graph["nodes"] if n["type"]=="page"}
    facts_by_page=defaultdict(list)
    for fact in graph["facts"]:
        facts_by_page[fact["doc"],fact["page"]].append(fact)
    for ref,page in pages.items():
        doc,suffix=ref.rsplit("/p",1)
        number=int(suffix)
        unit=units.get((doc,number),doc)
        if unit not in contracts:
            continue
        matches=defaultdict(list)
        for fact in facts_by_page[doc,number]:
            source=fact.get("source_line") or {}
            if source.get("rects"):
                matches[source["number"],source["text"]].append(fact["id"])
            elif fact["field"] in ("delivery_batch","batch_clause") or HINT.search(normalized(fact["quote"])):
                signals.append({"unit":unit,"doc":doc,"page":number,"line":None,"quote":fact["quote"],"facts":[fact["id"]]})
        if page.get("layer")=="text":
            text=read_text(doc,number)
            if not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=page.get("text_sha256"):
                raise ValueError("分批交付条款与归档文字摘要不符")
            for i,raw in enumerate(text.splitlines(),1):
                if HINT.search(normalized(raw)) or parts(raw)[0] in (*LABELS["delivery_batch"],*LABELS["batch_clause"]):
                    signals.append({"unit":unit,"doc":doc,"page":number,"line":i,"quote":raw,"facts":matches[i,raw]})
    coverage=[]
    notes=[]
    if signals:
        contract_fields={"contract",*LINK_KEYS,"signed_on","effect_on","valid_until","effect_clause","contract_state","buyer_signature",
                         "seller_signature","quantity_agreed","acceptance_criteria","delivery_batch","batch_clause","payment_term","payment_stage",
                         "total","net","tax","currency","unit"}
        def contract_row(field,value,quote):
            if field==CLAUSE:
                return bool(signing_clause(quote)) and covers(field,value,quote)
            if field=="payment_deadline":
                from payment_windows import scoped_row
                return scoped_row(quote) and covers(field,value,quote)
            if field in ("warranty_period","warranty_condition"):
                from warranty_terms import dedicated
                return dedicated(quote) and covers(field,value,quote)
            return covers(field,value,quote)
        if "equipment_model_sources" in graph:
            contract_fields.add("equipment_model")
        if "warranty_sources" in graph:
            contract_fields.update(("warranty_period","warranty_condition"))
        if "payment_window_sources" in graph:
            contract_fields.add("payment_deadline")
        if version in BATCH_SIGNING_FORMATS:
            contract_fields.add(CLAUSE)
        separate_units=set()
        if version in FINAL_SIGNING_FORMATS:
            separate_units={f.get("unit",f["doc"]) for f in graph["facts"] if f["field"]=="batch_clause"
                            and f.get("unit",f["doc"]) in contracts and separate_clause(f)}
        coverage=covered_rows(graph,read_text,contracts-separate_units,contract_fields,contract_row,"分批合同")
        def separate_row(field,value,quote):
            return contract_row(field,value,quote) or field==CLAUSE and bool(final_signers(quote)) and covers(field,value,quote)
        coverage+=covered_rows(graph,read_text,separate_units,contract_fields,separate_row,"另行终验合同")
        receipt_fields=set(RECEIPT_FIELDS)
        if "equipment_model_sources" in graph:
            receipt_fields.add("equipment_model")
        if version in FINAL_FORMS:
            receipt_fields.add(FINAL_REFS)
        def receipt_row(field,value,quote):
            return covers(field,value,quote) and (field!=FINAL_REFS or bool(receipt_numbers(parts(quote)[1])))
        coverage+=covered_rows(graph,read_text,receipts,receipt_fields,receipt_row,"分批验收材料")
        def release_field(field,value,quote):
            if field=="warranty":
                return normalized(value)==normalized(quote) and normalized(quote) in {"质保期满确认单","质保期满确认书"}
            return covers(field,value,quote)
        release_fields={"warranty",*LINK_KEYS,"warranty_release","acceptance_signer"}
        if "equipment_model_sources" in graph:
            contract_fields.add("equipment_model")
        if "warranty_sources" in graph:
            release_fields.add("warranty_defects")
        coverage+=covered_rows(graph,read_text,set(graph["documents_by_kind"].get("warranty",[])),
                              release_fields,release_field,"质保确认材料")
        # A disputed model can still be located on a specific batch. Other notes on the page retain their scope checks.
        model_rows=defaultdict(set)
        for hold in graph.get("equipment_model_sources",{}).get("review_holds",[]):
            kind,value=equipment_models.source_kind(hold["quote"])
            if (hold["line"] is not None and equipment_models.valid_code(value)
                    and (hold["role"],kind) in (("contract","ordered"),("acceptance","received"))):
                model_rows[hold["unit"],hold["page"]].add((hold["line"],hold["quote"]))
        mixed=set()
        for p in coverage:
            classified=model_rows.get((p["unit"],p["page"]))
            if classified:
                p["uncovered"]=[r for r in p["uncovered"] if (r["line"],r["quote"]) not in classified]
            p["text_only"]=pages[f"{p['doc']}/p{p['page']}"].get("clause_text_only") is True
            if not p["text_only"]:
                mixed.add((p["doc"],p["page"]))
        notes=[{"doc":f["doc"],"page":f["page"],"unit":f.get("unit",f["doc"]),"fact":f["id"],"quote":f["quote"]}
               for f in graph["facts"] if (f["doc"],f["page"]) in mixed and not (f.get("source_line") or {}).get("rects")]
    return {"format":version,"signals":signals,"pages":coverage,"visual_notes":notes}


def external_riders(graph,source,contract_unit):
    rows=[(p["unit"],f"{p['doc']}/p{p['page']}",l["quote"]) for p in source["pages"] for l in p["uncovered"]]
    covered_units={p["unit"] for p in source["pages"]}
    rows.extend((f.get("unit",f["doc"]),f["id"],f["quote"]) for f in graph["facts"] if f.get("unit",f["doc"]) in covered_units)
    riders=[]
    for unit,ref,quote in rows:
        if unit==contract_unit:
            continue
        line=normalized(quote)
        kind="contract" if CONTRACT_RIDER.search(line) else "payment" if PAYMENT_RIDER.search(line) else None
        if kind:
            riders.append({"unit":unit,"ref":ref,"quote":quote,"kind":kind})
    return riders


def gaps(source):
    return [{"id":f"{p['doc']}/p{p['page']}","doc":p["doc"],"page":p["page"],"quality":"delivery_batch_clause",
             "field":"delivery_batch",**line} for p in source["pages"] for line in p["uncovered"]]


def attach(graph,read_text):
    source=page_sources(graph,read_text)
    graph["delivery_batch_sources"]=source
    graph["gaps"].extend(gaps(source))


def readable(source,unit):
    pages=[p for p in source["pages"] if p["unit"]==unit]
    return bool(pages) and all(p["native"] and p["text_only"] and not p["uncovered"] for p in pages)


def rule(contract):
    fact=one(contract,"batch_clause")
    terms=raw_body(fact).strip("。").split(",") if fact else []
    recognised=bool(terms and terms[0] in INDEPENDENT and (len(terms)==1 or len(terms)==2 and terms[1] in COMPLETION|SEPARATE_FINAL))
    return recognised, bool(recognised and len(terms)==2 and terms[1] in COMPLETION), fact


def serial_field_text(fact,native_spacing):
    printed=raw_body(fact)
    if printed or not native_spacing:
        return printed
    line=fact.get("source_line") or {}
    if not line.get("rects") or fact["status"] not in ("anchored","confirmed") or not covers(fact["field"],fact["value"],line["text"]):
        return ""
    label,native=parts(line["text"])
    quoted_label,quoted=parts(fact["quote"])
    def strip_separators(value):
        value=re.sub(r"((?:设备编号|序列号):?)\s+(?=[A-Za-z0-9])",r"\1",value)
        return re.sub(r"\s*([、,])\s*",r"\1",value)
    if label==quoted_label and strip_separators(native)==strip_separators(quoted):
        return native
    return ""


def allocations(contract,native_spacing):
    rows=[]
    problem=""
    for fact in contract.fields["delivery_batch"]:
        parsed=ALLOCATION.fullmatch(serial_field_text(fact,native_spacing))
        if not parsed or not (index:=ordinal(parsed[1])):
            problem="合同交付批次、数量、单位或设备编号仍待逐行核对。"
            continue
        count,unit=int(parsed[2]),parsed[3]
        ids=serials(parsed[4])
        if ids is None or ids and len(ids)!=count:
            problem="合同一个批次所列设备编号不完整、重复或与约定数量不符。"
        rows.append({"index":index,"label":f"第{index}批","count":count,"unit_name":unit,"serials":ids or [],
                     "clause_ref":fact["id"],"quote":fact["source_line"]["text"]})
    rows.sort(key=lambda r:r["index"])
    total,unit=quantity(body(contract,"quantity_agreed"))
    if not problem and (len(rows)<2 or [r["index"] for r in rows]!=list(range(1,len(rows)+1))
                        or contract.incomplete("delivery_batch") or total!=sum(r["count"] for r in rows)
                        or any(r["unit_name"]!=unit for r in rows)):
        problem="合同各批次、计量单位和数量合计尚未与合同总量逐项对应。"
    ids=[i for r in rows for i in r["serials"]]
    if len(ids)!=len(set(ids)):
        problem="不同合同批次分配了同一设备编号，需核对交付清单。"
    return rows,problem


def signing_plan(graph,contract):
    source=graph.get("delivery_batch_sources",{})
    if source.get("format") not in BATCH_SIGNING_FORMATS or not source["signals"] or not readable(source,contract.unit) or not rule(contract)[0]:
        return {}
    clauses=graph.get("acceptance_authority_sources",{}).get("clauses",[])
    if not clauses or contract.incomplete(CLAUSE):
        return {}
    facts={f["id"]:f for f in contract.fields[CLAUSE]}
    schedule,problem=allocations(contract,True)
    if problem:
        return {}
    indices=[r["index"] for r in schedule]
    plan={}
    final=None
    separate=source["format"] in FINAL_SIGNING_FORMATS and separate_clause(one(contract,"batch_clause"))
    for row in clauses:
        fact=facts.get(row["fact"])
        if not row["native"] or row["unit"]!=contract.unit or not fact or (fact.get("source_line") or {}).get("text")!=row["quote"]:
            return {}
        names=final_signers(row["quote"]) if separate else None
        if names:
            if final or not literal_value(fact) or final_signers(fact["quote"])!=names:
                return {}
            final={"required":names,"clause_ref":fact["id"]}
            continue
        parsed=signing_clause(row["quote"])
        if not parsed or signing_clause(fact["quote"])!=parsed or separate and not literal_value(fact):
            return {}
        batch,names=parsed
        for index in indices if batch==0 else [batch]:
            if index not in indices or index in plan:
                return {}
            plan[index]={"required":names,"clause_ref":fact["id"]}
    if plan and plan.keys()!=set(indices) or not plan and not final:
        return {}
    return {"batches":plan,"final":final}


def check_batch_signatures(requirement,rows,*,applicable,complete,scope="本批"):
    required=requirement["required"]
    signed=[s["name"] for s in rows if s["confirmed"]]
    missing=[name for name in required if name not in signed]
    extra=list(dict.fromkeys(name for name in signed if name not in required))
    if not applicable:
        status,detail="missing","需先核对本单的合同、双方、标的及签认条款适用日期。"
    elif not complete:
        status,detail="missing",scope+"签认原页或附注待核，需核对整页及可能影响签认的其他约定。"
    elif extra:
        status,detail="risk",scope+"签字栏所列"+"、".join(extra)+"与合同指定人员不符，需核实代签授权。"
    elif missing:
        status,detail="missing",scope+"尚缺"+"、".join(missing)+"逐人核对原页的签字。"
    elif len(signed)!=len(required) or len(signed)!=len(rows):
        status,detail="missing",scope+"有多余、重复或待辨的签字栏，须核对每一栏的原件。"
    else:
        status,detail="ok",scope+"指定的"+"、".join(required)+"均有独立签字栏及核图记录。"
    return {**requirement,"signed":rows,"missing_names":missing,"other_names":extra,"status":status,"detail":detail}


def record(contract,doc,source,native_spacing,requirements,signatures,separate,final_requirement):
    from performance import CLEAN, PASS, inspect_quality, printed_day
    scope=one(doc,"acceptance_scope")
    match=SCOPE.fullmatch(raw_body(scope)) if scope else None
    index=ordinal(match[1]) if match else None
    number=body(doc,"acceptance_number")
    day=printed_day(doc,"accepted_on")
    effective,until=printed_day(contract,"effect_on"),printed_day(contract,"valid_until")
    qty,unit=quantity(body(doc,"quantity_accepted"))
    serial_facts=doc.fields["delivered_serials"]
    serial_text=serial_field_text(serial_facts[0],native_spacing) if len(serial_facts)==1 and not doc.incomplete("delivered_serials") else ""
    ids=serials(serial_text)
    fields=doc.evidence(*RECEIPT_FIELDS)
    fields.extend(n["fact"] for n in source["visual_notes"] if n["unit"]==doc.unit)
    fields.extend(f"{p['doc']}/p{p['page']}" for p in source["pages"] if p["unit"]==doc.unit)
    pages=[p for p in source["pages"] if p["unit"]==doc.unit]
    related=(linked(contract,doc) and complete_id(contract.body("contract_id")) and all(labelled_sources(m,LINK_KEYS) for m in (contract,doc))
             and all(body(contract,k) and body(contract,k)==body(doc,k) for k in LINK_KEYS))
    is_final=bool(separate and related and scope and raw_body(scope) in FINAL_SCOPES)
    requirement=final_requirement if is_final else requirements.get(index)
    ref_fact=one(doc,FINAL_REFS) if is_final else None
    unexpected_refs=source.get("format") in FINAL_FORMS and not is_final and bool(doc.fields[FINAL_REFS] or FINAL_REFS in doc.uncertain)
    if is_final or unexpected_refs:
        fields.extend(doc.evidence(FINAL_REFS))
    def local_line(line):
        if is_final and parts(line)[0] in LABELS[FINAL_REFS]:
            return bool(receipt_numbers(parts(line)[1]))
        return normalized(line).rstrip("。") in LOCAL_NOTES or (requirement and related and signed_name(line))
    open_scope=unexpected_refs or not pages or any(not p["text_only"] or not p["native"] or
               any(not local_line(l["quote"]) for l in p["uncovered"]) for p in pages)
    result={"unit":doc.unit,"index":index,"scope_ref":scope["id"] if scope else None,"number":number or None,"scope_unclear":open_scope,
            "date":day.isoformat() if day else None,"count":qty,"unit_name":unit,"serials":ids or [],
            "evidence":list(dict.fromkeys(fields))}
    if separate:
        numbered=one(doc,"acceptance_number")
        result["number_ref"]=numbered["id"] if numbered else None
    if is_final:
        result.update(role="final",refs_ref=ref_fact["id"] if ref_fact else None,
                      receipt_numbers=printed_references(ref_fact))
    signing=None
    raw_signatures_only=False
    if requirement:
        rows=[s for s in signatures if s["unit"]==doc.unit]
        if is_final:
            owned={f["id"]:f for f in doc.fields["acceptance_signer"]}
            rows=[{**s,"confirmed":bool(s["confirmed"] and literal_value(owned.get(s["fact"])))} for s in rows]
            uncovered=[line for p in pages for line in p["uncovered"]]
            raw_signatures_only=bool(uncovered and not open_scope and all(signed_name(l["quote"]) for l in uncovered))
        signing=check_batch_signatures(requirement,rows,
                    applicable=bool(related and day and effective and day>effective and (not until or day<=until)),
                    complete=readable(source,doc.unit) or raw_signatures_only,scope="终验" if is_final else "本批")
        result["signing"]=signing
        result["evidence"]=list(dict.fromkeys([*fields,signing["clause_ref"],
            *(ref for s in signing["signed"] for ref in (s["facts"] or [f"{s['doc']}/p{s['page']}"]))]))
    outcome=body(doc,"acceptance_result")
    required=normalized(body(contract,"acceptance_criteria"))
    basis,reading=(normalized(body(doc,k)) for k in ("inspection_basis","measured_result"))
    qc,detail=inspect_quality(required,basis,reading)
    if not all(labelled_sources(m,keys) for m,keys in ((contract,("acceptance_criteria",)),(doc,("inspection_basis","measured_result")))):
        qc,detail="missing","请核对原标准、检验依据和实测值的完整记录。"
    elif required and reading and required!=basis:
        against_contract,measurement=inspect_quality(required,required,reading)
        if against_contract=="issue":
            qc,detail="issue",measurement+" 验收报告所引检验依据同时需核对。"
    signer=one(doc,"acceptance_signer")
    signature=(signer or {}).get("attestation") or {}
    if not related:
        status,reason="missing","合同编号、双方及标的尚未逐项对应。"
    elif not index and not is_final:
        status,reason="missing","原验收记录缺少明确的本批范围。"
    elif outcome in {"不合格","验收不合格","未通过","拒收"} or qc=="issue":
        status,reason="issue",detail if qc=="issue" else "原验收记录明确记载“"+outcome+"”。"
    elif raw_signatures_only and signing["status"]!="ok":
        status,reason=signing["status"],signing["detail"]
    elif is_final and not open_scope and any(p["uncovered"] for p in pages):
        status,reason="missing","终验原页尚有未经逐行核对的引用或附注，须核对所附批次验收单号。"
    elif not readable(source,doc.unit) or doc.incomplete(*RECEIPT_FIELDS) or not identifier(number):
        status,reason="missing","需核对完整验收单编号、本批原页及附注。"
    elif not day or not effective or day==effective:
        status,reason="missing","需核对本批验收时合同已生效的日期或同日时分。"
    elif day<effective:
        status,reason="risk","本批验收早于所列合同生效日，请核查提前履行依据。"
    elif until and day>until:
        status,reason="risk","本批验收日在所列合同有效期之后，请核查延期依据。"
    elif qc!="ok":
        status,reason=qc,detail
    elif not outcome or not body(doc,"acceptance_exception"):
        status,reason="missing","缺少本批质量结论或遗留事项记录。"
    elif outcome not in PASS or body(doc,"acceptance_exception") not in CLEAN:
        status,reason="risk","本批质量结论或遗留事项仍待核实。"
    elif signing and signing["status"]!="ok":
        status,reason=signing["status"],signing["detail"]
    elif not signing and (not signer or not signed_name(signer["source_line"]["text"]) or signer["status"]!="confirmed" or signature.get("decision")!="confirm" or not signature.get("source_check")):
        status,reason="missing","待取得本批验收人的独立签字栏和原页核图记录。"
    elif qty is None or ids is None:
        status,reason="missing","实际验收数量、单位或设备编号的完整记载待核。"
    elif ids and len(ids)!=qty:
        status,reason="risk","验收单所列设备编号个数与本单实际验收数量不符。"
    else:
        status,reason="ok","本批验收记录的质量、日期及签认相符。"
    if is_final:
        reason=reason.replace("本批","终验").replace("完整验收单编号、终验原页及附注","完整的终验单编号、原页及附注")
    result.update(status=status,detail=reason)
    return result


def reconcile_final(finals, batches, records, *, held, needs_final_authority):
    by_unit={r["unit"]:r for r in records}
    basis=[{"index":b["index"],"unit":unit,"number":by_unit[unit]["number"],"number_ref":by_unit[unit]["number_ref"]}
           for b in batches for unit in b["records"]]
    def finding(status,detail):
        return {"status":status,"detail":detail,"records":[r["unit"] for r in finals],"basis":basis}
    failed=next((r for r in finals if r["status"]=="issue"),None)
    if failed:
        return finding("issue",failed["detail"])
    if not finals:
        return finding("missing","合同要求另行终验，尚缺同一合同、双方及标的的全部交付终验原件。")
    if len(finals)!=1:
        return finding("risk","有多份终验原件，需查明各自适用范围及有效版本。")
    final=finals[0]
    if final["status"]!="ok":
        return finding(final["status"],final["detail"])
    if held or not batches or any(b["status"]!="ok" for b in batches):
        return finding("missing","须先核清各批验收、合同效力和未决附注，再确认终验依据。")
    if needs_final_authority:
        return finding("missing","合同指定了分批验收人，另行终验的签认权限仍待核实。")
    if not final["receipt_numbers"]:
        return finding("missing","终验单缺少可逐项核对的完整批次验收单号，需核对原件的引用栏。")
    actual={b["number"] for b in basis}
    listed=set(final["receipt_numbers"])
    if len(listed)!=len(final["receipt_numbers"]):
        return finding("risk","终验单重复列入批次验收单号，须核实各份验收原件。")
    if actual!=listed:
        absent=sorted(actual-listed)
        extra=sorted(listed-actual)
        differences=(["缺列"+"、".join(absent)] if absent else [])+(["另列"+"、".join(extra)] if extra else [])
        return finding("risk","终验单与已验各批的单号不一致，"+"，".join(differences)+"。")
    if (final["count"],final["unit_name"])!=(sum(b["count"] for b in batches),batches[0]["unit_name"]):
        return finding("risk","终验单的合计数量或计量单位与各批验收原件不符。")
    serial_lists=[by_unit[b["unit"]]["serials"] for b in basis]
    if any(serial_lists) or final["serials"]:
        if not all(serial_lists) or not final["serials"]:
            return finding("missing","终验单与各批原件的逐台设备清单不齐，需核对原始编号。")
        if {s for ids in serial_lists for s in ids}!=set(final["serials"]):
            return finding("risk","终验单列明的设备编号与各批原件合并后的清单不符。")
    last=max(b["date"] for b in batches)
    if final["date"]==last:
        return finding("missing","终验与末批验收在同一天，两次签认的先后时分待核。")
    if final["date"]<last:
        return finding("risk","终验单日期早于其所引用的末批验收日期 "+last+"。")
    return finding("ok","终验单逐份列明各批验收单号，交付范围、实测质量及签认均有原件支持。")


def inspect(graph,contract,receipts,*,other_terms,native_spacing=False,requirements=None,final_requirement=None,model_checks=None):
    source=graph.get("delivery_batch_sources",{})
    if not source.get("signals"):
        return None
    requirements=requirements or {}
    schedule,plan_problem=allocations(contract,native_spacing)
    independent,final,rule_fact=rule(contract)
    separate=bool(source.get("format") in FINAL_FORMS and independent and separate_clause(rule_fact))
    contract_clear=readable(source,contract.unit)
    riders=external_riders(graph,source,contract.unit)
    if not contract_clear:
        plan_problem="合同含待辨原行、影像附注或尚未核清的页内条款。"
    base=contract.evidence("contract",*LINK_KEYS,"delivery_batch","batch_clause","quantity_agreed","acceptance_criteria","effect_on","valid_until")
    signing_refs={requirement["clause_ref"] for requirement in requirements.values()}
    if final_requirement:
        signing_refs.add(final_requirement["clause_ref"])
    base.extend(ref for s in source["signals"] for ref in (s["facts"] or [f"{s['doc']}/p{s['page']}"]) if ref not in signing_refs)
    base.extend(n["fact"] for n in source["visual_notes"] if n["unit"]==contract.unit)
    base.extend(f"{p['doc']}/p{p['page']}" for p in source["pages"] if p["unit"]==contract.unit)
    base.extend(r["ref"] for r in riders)
    signatures=graph.get("acceptance_authority_sources",{}).get("signatures",[])
    records=[record(contract,doc,source,native_spacing,requirements,signatures,separate,final_requirement) for doc in receipts]
    if model_checks:
        by_unit = {r["unit"]: r for r in model_checks["records"]}
        for item in records:
            model = by_unit.get(item["unit"])
            if model:
                equipment_models.apply(item, model)
                item["evidence"] = list(dict.fromkeys([*item["evidence"], *model["evidence"]]))
    finals=[r for r in records if r.get("role")=="final"]
    expected={r["index"] for r in schedule}
    unknown=[r for r in records if r["scope_unclear"] or r.get("role")=="final" and len(finals)>1 or
             r.get("role")!="final" and r["index"] not in expected]
    collisions=defaultdict(list)
    for r in records:
        if r["number"]:
            collisions["验收单号",r["number"]].append(r)
        if r.get("role")!="final":
            for serial in r["serials"]:
                collisions["设备编号",serial].append(r)
    results=[]
    for allocation in schedule:
        selected=[r for r in records if r["index"]==allocation["index"]]
        seen={r["unit"] for r in selected}
        involved=[*selected,*unknown]
        repeated=[]
        for (field,value),owners in collisions.items():
            if len(owners)>1 and any(r["unit"] in seen for r in owners):
                repeated.append(field+"“"+value+"”")
                involved.extend(owners)
        status,detail="missing","缺少对应本批的验收原件。"
        if selected:
            rec=selected[0]
            status,detail=rec["status"],rec["detail"]
            if len(selected)!=1:
                status,detail="risk","同一批次有多份验收原件，需查明版本和覆盖范围。"
            elif status=="ok":
                if (rec["count"],rec["unit_name"])!=(allocation["count"],allocation["unit_name"]):
                    status,detail="risk","本批实际验收数量或单位与合同约定不符。"
                elif allocation["serials"] and not rec["serials"]:
                    status,detail="missing","合同逐台列有设备编号，验收单尚缺对应清单。"
                elif allocation["serials"] and set(rec["serials"])!=set(allocation["serials"]):
                    status,detail="risk","本批验收设备编号与合同分配不符。"
            if repeated:
                status,detail="risk","不同验收记录重复使用"+"、".join(repeated)+"，需逐项核对。"
            failure=next((r for r in selected if r["status"]=="issue"),None)
            if failure:
                status="issue"
                detail=failure["detail"]+(" "+detail if detail!=failure["detail"] else "")
        hold=plan_problem or ("合同签署、生效、变更或其他履约依据仍待核对，需查明对各批的影响。" if other_terms or any(r["kind"]=="contract" for r in riders) else
              "验收记录的批次归属或页内附注影响范围待核。" if unknown else
              "各批是否独立验收付款仍需核对合同约定。" if not independent else "")
        if hold:
            if status=="ok":
                status,detail="missing",hold
            elif hold!=detail:
                detail+=" "+hold
        scope=list(dict.fromkeys([contract.unit,*(r["unit"] for r in involved),*(r["unit"] for r in riders)]))
        evidence=list(dict.fromkeys([*base,*(ref for r in involved for ref in r["evidence"])]))
        if allocation["index"] in requirements:
            authority=requirements[allocation["index"]]
            allocation["signing_requirement"]=authority
            evidence=list(dict.fromkeys([*evidence,authority["clause_ref"]]))
        results.append({**allocation,"status":status,"detail":detail,"records":[r["unit"] for r in selected],
                        "date":selected[0]["date"] if status=="ok" else None,"scope":scope,"evidence":evidence})
    final_check=reconcile_final(finals,results,records,held=bool(plan_problem or other_terms or riders or unknown),
                                needs_final_authority=bool(requirements and not final_requirement)) if separate else None
    if final_check and final_requirement:
        final_check["signing_requirement"]=final_requirement
    outcomes=[*results,*unknown]+([final_check] if final_check else [])
    status=next((s for s in ("issue","risk","missing") if any(r["status"]==s for r in outcomes)),"ok")
    if status=="ok" and (not results or not (final or final_check) or plan_problem or other_terms or unknown):
        status="missing"
    complete=None
    if status=="ok":
        complete=finals[0]["date"] if final_check else max(r["date"] for r in results)
    summary=" ".join(r["label"]+("验收材料相符。" if r["status"]=="ok" else "："+r["detail"]) for r in results)
    detail=(summary or plan_problem or "待核合同各批约定及验收原件。")
    if final_check:
        detail+=" "+final_check["detail"]
        if complete:
            detail+=f" 终验合格日期为 {complete}。"
    elif complete:
        detail+=f" 各批均有合格记录，按合同约定于 {complete} 达到终验条件。"
    elif not final:
        detail+=" 全部交付的最终验收依据仍待核实。"
    return {"status":status,"detail":detail,"independent":independent,"deemed_final":final,"completion_on":complete,
            **({"separate_final":final_check} if final_check else {}),
            "contract_clear":contract_clear,"riders":riders,"rule_ref":rule_fact["id"] if rule_fact else None,"records":records,"batches":results,
            "scope":list(dict.fromkeys([contract.unit,*(r["unit"] for r in records)])),
            "evidence":list(dict.fromkeys([*base,*(r["clause_ref"] for r in requirements.values()),
                *([final_requirement["clause_ref"]] if final_requirement else []),*(ref for r in records for ref in r["evidence"])]))}


def payment_index(row,contract):
    match=PAYMENT.fullmatch(row["text"])
    if not match:
        return None
    fact=next((f for f in contract.fields["payment_stage"] if f["id"]==row["ref"]),None)
    if not fact or not row["label"] or not PAYMENT.fullmatch(raw_body(fact)) or normalized(raw_body(fact))!=row["text"]:
        return None
    return ordinal(match[1])


def evidence_edges(findings):
    result=[]
    entry=next((f["batch_acceptance"] for f in findings if f.get("batch_acceptance")),None)
    if not entry:
        return result
    records={r["unit"]:r for r in entry["records"]}
    for batch in entry["batches"]:
        if batch["status"]=="ok":
            record=records[batch["records"][0]]
            result.append({"from":batch["clause_ref"],"to":record["scope_ref"],"type":"delivery_batch_acceptance","evidence":batch["evidence"]})
            signing=record.get("signing")
            if signing and signing["status"]=="ok":
                for row in signing["signed"]:
                    result.append({"from":signing["clause_ref"],"to":row["fact"],"type":"batch_named_signature",
                                   "evidence":list(dict.fromkeys([signing["clause_ref"],row["fact"],*batch["evidence"]]))})
            for f in findings:
                if f["rule"]=="H04" and f["status"]=="ok" and f.get("stage",{}).get("batch_index")==batch["index"]:
                    result.append({"from":f["stage"]["clause_ref"],"to":record["scope_ref"],"type":"batch_payment_basis","evidence":f["evidence"]})
    final=entry.get("separate_final")
    if final and final["status"]=="ok":
        receipt=records[final["records"][0]]
        for batch in final["basis"]:
            result.append({"type":"batch_final_basis","from":receipt["refs_ref"],"to":batch["number_ref"],
                           "evidence":entry["evidence"]})
        signing=receipt.get("signing")
        if signing and signing["status"]=="ok":
            for row in signing["signed"]:
                result.append({"type":"final_named_signature","from":signing["clause_ref"],"to":row["fact"],"evidence":entry["evidence"]})
    return result


def verify_sources(report,read_text,*,signing=False):
    policy,graph=report["policy"],report["graph"]
    if not policy.get("delivery_batches"):
        if "delivery_batches.py" in policy.get("code_sha256",{}) or "delivery_batch_sources" in graph or policy.get("performance_checks") in BATCH_FORMATS:
            raise ValueError("分批验收程序标记缺失")
        if signing and any(f["rule"]=="H02" and f["status"]=="ok" for f in report["findings"]) and page_sources(graph,read_text)["signals"]:
            raise ValueError("旧版终验尚未逐批核对，请按现行程序重审后签收。")
        return
    marker=policy["delivery_batches"]
    source=page_sources(graph,read_text,marker)
    version=policy.get("version","")
    if (marker not in (LEGACY,*BATCH_SIGNING_FORMATS) or "2026.11.25.07"<=version<"2026.11.25.08" and marker!=SIGNING_FORMAT or
        "2026.11.25.08"<=version<"2026.11.25.09" and marker!=FINAL_FORMAT or
        "2026.11.25.09"<=version<"2026.11.25.11" and marker!=FINAL_SIGNING_FORMAT or version>="2026.11.25.11" and marker!=FORMAT or
        policy.get("performance_checks") not in BATCH_FORMATS or
        graph.get("delivery_batch_sources")!=source or gaps(source)!=[g for g in graph["gaps"] if g["quality"]=="delivery_batch_clause"]):
        raise ValueError("分批条款原文、资料归属或页内覆盖与归档不符")
    edges=[e for e in graph["edges"] if e["type"] in ("delivery_batch_acceptance","batch_payment_basis","batch_named_signature","batch_final_basis","final_named_signature")]
    if evidence_edges(report["findings"])!=edges:
        raise ValueError("分批验收或分期付款的证据关系不符")
    expected=sorted((f.get("unit",f["doc"]),f["id"],f["field"],(f["id"],)) for f in graph["facts"]
                    if f["field"] in LABELS and f["status"] in ("anchored","confirmed"))
    actual=sorted((e["from"],e["to"],e["type"],tuple(e["evidence"])) for e in graph["edges"] if e["type"] in LABELS)
    if expected!=actual:
        raise ValueError("分批交付与设备编号的观察记录未指向所属原件")
