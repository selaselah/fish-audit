"""Validate a proposed defect/repair identifier classification against print and an independent image read."""

import hashlib
import unicodedata
from collections import Counter

from reinspection import CODE, LABELS, NUMBER_TYPES


FORMAT = "printed-quality-number-v1"
PRINTED = {label:field for field in NUMBER_TYPES for label in LABELS[field]}
NAMES = {"remediation":"整改记录单标题","reinspection":"整改复验报告标题","acceptance":"验收单标题","contract":"合同标题",
         "contract_id":"合同编号","other":"其他有待核实的记载",**{f:LABELS[f][0] for f in NUMBER_TYPES}}


def compact(value):
    return "".join(unicodedata.normalize("NFKC",value).split())


def numbered_lines(lines):
    found = {}
    counts = Counter()
    for n,line in enumerate(lines,1):
        label,sep,code = compact(line).partition(":")
        field = PRINTED.get(label)
        if field and sep:
            counts[field] += 1
            if CODE.fullmatch(code):
                found[field]=(n,compact(line),code)
    return {field:row for field,row in found.items() if counts[field]==1}


def alternative(raw, lines, index):
    if raw["field"] not in NAMES:
        return None
    quote = compact(raw["quote"])
    field = PRINTED.get(quote.partition(":")[0])
    if not field or field==raw["field"] or field not in lines:
        return None
    number,line,value = lines[field]
    if line!=quote or compact(raw["value"])!=value:
        return None
    return field,number,{"index":"q"+index,"field":NAMES[field],"value":raw["value"],"quote":raw["quote"]}


def proposed(page):
    layer, raw = page.get("layer") or {},page["extraction"]["output"]
    if layer.get("type")!="text" or raw["quality"]!="readable" or len(raw["facts"])>=140:
        return []
    lines = numbered_lines(page["text"].splitlines())
    proposals = []
    for i,fact in enumerate(raw["facts"],1):
        alternate = alternative(fact,lines,str(i))
        if alternate and layer["lines"].get(str(alternate[1])):
            proposals.append(alternate[2])
    return proposals


def verified(raw, lines, line_number, index, check):
    alternate = alternative(raw,lines,index)
    if not check or not alternate or alternate[1]!=line_number:
        return None
    field,_,candidate = alternate
    original = {"index":index,"field":NAMES[raw["field"]],"quote":raw["quote"],"value":raw["value"]}
    inputs = check.get("input",[])
    votes = check.get("output",{}).get("checks",[])
    for expected,required in ((original,"conflict"),(candidate,"clear")):
        key = expected["index"]
        if ([row for row in inputs if row["index"]==key] != [expected] or
                [row["support"] for row in votes if row["index"]==key] != [required]):
            return None
    return field


def verify_report(report, load_text):
    policy = report["policy"]
    enabled = policy.get("quality_number_classification")==FORMAT
    if "quality_labels.py" in policy.get("code_sha256",{}) and not enabled:
        raise ValueError("整改编号复检程序的版本标记不符")
    if not enabled:
        if any(f.get("origin")=="printed_quality_number" for f in report["graph"]["facts"]):
            raise ValueError("整改编号归类缺少对应版本的复检程序")
        return
    candidates = [f for f in report["graph"]["facts"] if f.get("origin")=="printed_quality_number"
                  or (f["field"] in NUMBER_TYPES and not f.get("amendment"))]
    if not candidates:
        return
    pages = {(t["doc"],t["page"]):t for t in report["calls"]["pages"]}
    nodes = {n["id"]:n for n in report["graph"]["nodes"] if n["type"]=="page"}
    texts = {}
    for fact in candidates:
        classified = fact.get("origin")=="printed_quality_number"
        address = fact["doc"],fact["page"]
        trace = pages[address]
        raw_facts = trace["output"]["facts"]
        page_id = f"{address[0]}/p{address[1]}"
        i = fact["id"].removeprefix(page_id+"/f")
        if not i.isascii() or not i.isdigit() or not 1<=int(i)<=len(raw_facts):
            raise ValueError("整改编号缺少原模型候选记录")
        raw = raw_facts[int(i)-1]
        if not classified:
            if raw["field"]!=fact["field"]:
                raise ValueError("整改编号分类变化缺少独立读图依据")
            continue
        if address not in texts:
            text=load_text(*address)
            if not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=nodes[page_id].get("text_sha256"):
                raise ValueError("整改编号所据的文字层与留存摘要不符")
            lines=text.splitlines()
            texts[address]=lines,numbered_lines(lines)
        lines,markers=texts[address]
        line=fact.get("source_line") or {}
        n=line.get("number")
        check=trace.get("check") or {}
        if (trace["output"]["quality"]!="readable" or len(raw_facts)>=140 or nodes[page_id].get("layer")!="text"
                or not isinstance(n,int) or not 1<=n<=len(lines) or not line.get("rects") or line.get("text")!=lines[n-1]
                or fact.get("amendment") or raw["field"]!=fact.get("model_field") or fact.get("classification_index")!="q"+i
                or raw["quote"].strip()!=fact["quote"] or raw["value"].strip()!=fact["value"] or fact["visual_check"]!="clear"
                or fact.get("check_response_id")!=check.get("response_id")
                or verified(raw,markers,n,i,check)!=fact["field"]):
            raise ValueError("整改编号与初读、原页标签或两项逐字段视觉复检不符")
