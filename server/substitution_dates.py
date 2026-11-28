"""Compare a named equipment substitution decision with the dates on this purchase's originals."""

from datetime import date
import re

from contract_changes import PRINTED, TITLES
from delegation import is_page_marker
from installment_approval import printed_date
from party_readings import checked
from payment_quality import BANK, native_text, printed_rows, readings, witness
from reinspection import LINK_KEYS
from stage_payments import SUCCESS


FORMAT = "inspection-coverage-v5"
FORM_FIELDS = ("addendum_number","base_contract_ref","buyer","seller","subject","change_state","buyer_signature","seller_signature")
DECISIONS = {"代用决定","设备代用决定","设备代用批准决定"}
CLAUSES = {"供货约定","设备代用约定","交付约定"}
CODE = r"([A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)"
PRIOR = re.compile(r"经采购方事先书面批准[，,]\s*可(?:以)?(?:用|以)\s*"+CODE+r"\s*(?:代替|替代)\s*"+CODE+r"[。.]?")
INDICATION = re.compile(r"(.+?)于(.+?)同意(?:以|用)\s*"+CODE+r"\s*(?:代替|替代)\s*"+CODE+r"[。.]?")
RELATION = "dates_equipment_substitution"
ROLES = {"contract":(*LINK_KEYS,"payment_stage"),"acceptance":(*LINK_KEYS,"accepted_on","acceptance_scope"),"bank_receipt":BANK}


def fields(graph,read_text):
    return printed_rows(graph,read_text,ROLES)


def form(lines):
    """Retain the filed status and seal captions only for a single unqualified decision form."""
    from inspection_coverage import split

    fields = {label:key for key in FORM_FIELDS for label in PRINTED[key]}
    fields.update(dict.fromkeys(DECISIONS,"decision"))
    content = [(n,line) for n,line in enumerate(lines,1) if not is_page_marker(line)]
    if not content or content[0][1].strip() not in TITLES or len(content)!=len(FORM_FIELDS)+2:
        return None
    columns = {}
    for n,line in content[1:]:
        label,body = split(line)
        key = fields.get(label)
        if not key or not body or key in columns:
            return None
        columns[key] = (n,body,line)
    if columns["change_state"][1]!="已签署" or columns["buyer"][1]==columns["seller"][1]:
        return None
    for side in ("buyer","seller"):
        name = columns[side][1]
        if columns[side+"_signature"][1] not in (name+"（已盖章）",name+"(已盖章)"):
            return None
    return {key:{"line":columns[key][0],"quote":columns[key][2]} for key in ("change_state","buyer_signature","seller_signature","decision")}


def decision(graph,contract,receipt,register,ledger):
    from inspection_coverage import count, population, split

    rows,pages=ledger["rows"],ledger["pages"]
    if (register["state"]!="register_substitution" or len(pages)!=3 or
            not all(p["native"] and p["text_only"] and not p.get("substitution_qualification") for p in pages)):
        return None
    kinds=graph["documents_by_kind"]
    changes=kinds.get("contract_addendum",())
    if len(changes)!=1 or (set(kinds)-{"contract","acceptance","contract_addendum","bank_receipt","warranty"}) or any(
            len(kinds.get(kind,()))!=1 for kind in ("contract","acceptance")):
        return None
    change=changes[0]
    if {p["unit"] for p in pages}!={contract.unit,receipt.unit,change} or any(
            p["doc"]!=p["unit"] or p["page"]!=1 for p in pages):
        return None
    form_page=next(p for p in pages if p["unit"]==change)
    filed=form_page.get("substitution_decision")
    if not filed or any(r["line"] is None or r["disputed"] or r["kind"]=="serial_note" and
                        (r["unit"]!=change or split(r["quote"])[0] not in PRINTED["addendum_number"]) for r in rows):
        return None
    if any(g["doc"] in register["scope"] and g.get("quality") in ("partial","unreadable","section_unresolved") for g in graph["gaps"]):
        return None
    def one(unit,kind):
        found=[r for r in rows if r["unit"]==unit and r["kind"]==kind]
        return found[0] if len(found)==1 else None
    left, right = one(contract.unit,"ordered_serials"), one(receipt.unit,"population")
    promised, received = one(contract.unit,"ordered"), one(receipt.unit,"received")
    clause, note = one(contract.unit,"substitution"), one(change,"substitution")
    if (not all((left,right,promised,received,clause,note)) or
            sum(r["kind"]=="substitution" for r in rows)!=2 or
            {r["id"] for r in (left,right,clause,note)}!=set(register["register"]["rows"]) or
            len(register["register"]["rows"])!=4):
        return None
    ordered, delivered=(population(split(r["quote"])[1]) for r in (left,right))
    if (not ordered or not delivered or len(ordered)!=len(delivered) or
            any(count(split(r["quote"])[1])!=len(ordered) for r in (promised,received))):
        return None
    old, new = set(ordered)-set(delivered), set(delivered)-set(ordered)
    key,term=split(clause["quote"]); label,body=split(note["quote"])
    permit=PRIOR.fullmatch(term); stated=INDICATION.fullmatch(body)
    if (key not in CLAUSES or label not in DECISIONS or not permit or not stated or
            permit.groups()!=stated.groups()[2:] or new!={permit[1]} or old!={permit[2]} or
            filed["decision"]!={"line":note["line"],"quote":note["quote"]}):
        return None
    obs=ledger.get("decision_fields",[])
    a,b=(readings(obs,m,LINK_KEYS) for m in (contract,receipt))
    stated_on=printed_date(stated[2])
    if not stated_on or not a or not b or a["buyer"][1]!=stated[1] or any(a[k][1]!=b[k][1] for k in LINK_KEYS):
        return None
    return {"decision":note["id"],"condition":clause["id"],"unit":change,"issuer":stated[1],"original":permit[2],
            "replacement":permit[1],"stated_on":stated_on}


def transfer_fields(graph,bank,rows):
    ordinary=readings(rows,bank,BANK)
    if ordinary:
        return ordinary,[]
    # A reviewer can assign an otherwise correctly transcribed "other" row to the payment stage.
    found=[r for r in rows if r["unit"]==bank.unit and r["field"]=="payment_designation"]
    assigned=bank.fields["payment_designation"]
    if len(found)!=1 or len(assigned)!=1 or len(found[0]["facts"])!=2:
        return None,[]
    row=found[0]; added=assigned[0]
    other=[f for f in bank.refs if f["id"] in row["facts"] and f["field"]=="other"]
    if len(other)!=1 or added["id"] not in row["facts"]:
        return None,[]
    old=other[0]
    doc=next((d for d in graph["documents"] if d["id"]==row["doc"]),None)
    page=next((n for n in graph["nodes"] if n["id"]==f"{row['doc']}/p{row['page']}"),None)
    if (not doc or not page or row["page"]!=1 or not checked(added,"add",doc,page) or added.get("original_candidate") or
            old.get("amendment") or old["status"] not in ("visual","anchored","confirmed") or not old.get("response_id") or
            not old.get("check_response_id") or old["quote"]!=row["quote"] or
            any(old.get(k)!=added.get(k) for k in ("doc","page","source_sha256","page_sha256","source_line","quote","value"))):
        return None,[]
    narrowed=[{**r,"facts":[added["id"]]} if r is row else r for r in rows]
    return readings(narrowed,bank,BANK),[old["id"],added["id"]]


def compare(finding,record,source,event):
    ref,day=source
    days=(date.fromisoformat(day)-date.fromisoformat(record["stated_on"])).days
    relation="before" if days<0 else "after" if days>0 else "same_day"
    subject="终验日期" if event=="acceptance" else "回单付款日"
    text=f"{subject}与协议所记批准日同为 {day}，当日先后待核。"
    if days:
        meaning="早于" if days<0 else "晚于"
        text=f"{subject} {day} {meaning}补充协议所记代用批准日 {record['stated_on']}。"
    finding["substitution_dates"]={**record,"event":event,"date_ref":ref,"event_on":day,"days":days,"order":relation}
    finding["evidence"]=list(dict.fromkeys([*finding["evidence"],ref]))
    finding["detail"]+=" "+text+" 请核实批准人权限、签署原件及当时收到的书面文件。"
    if days<0 and finding["status"] in ("ok","missing"):
        finding["status"]="risk"


def apply(graph,findings):
    from performance import FINAL_SCOPES, Material, stage_terms

    ledger=graph.get("inspection_coverage_sources",{})
    if ledger.get("format")!=FORMAT or not any(p.get("substitution_decision") for p in ledger["pages"]):
        return
    h02=next((f for f in findings if f["rule"]=="H02" and f.get("delivery_register")),None)
    kinds=graph["documents_by_kind"]
    if not h02 or len(kinds.get("contract",()))!=1 or len(kinds.get("acceptance",()))!=1:
        return
    contract,receipt=(Material(graph,kinds[k][0]) for k in ("contract","acceptance"))
    record=decision(graph,contract,receipt,h02["inspection_coverage"],ledger)
    if not record:
        return
    obs=ledger["decision_fields"]
    acceptance=readings(obs,receipt,("accepted_on","acceptance_scope"))
    if not acceptance or acceptance["acceptance_scope"][1] not in FINAL_SCOPES:
        return
    compare(h02,record,acceptance["accepted_on"],"acceptance")
    for f in findings:
        if f["rule"] not in ("H04","H05") or f.get("delivery_register")!=h02["delivery_register"] or not f.get("stage"):
            continue
        stage=f["stage"]
        term=witness(obs,contract,"payment_stage",clause=stage["clause_ref"])
        if not term or term[0] not in f["evidence"] or term[1]!=stage["clause"] or stage_terms(term[1])[1]!="acceptance":
            continue
        if f["rule"]=="H04":
            compare(f,record,acceptance["accepted_on"],"acceptance")
            continue
        banks=set(kinds.get("bank_receipt",())).intersection(f["scope"])
        if len(banks)!=1:
            continue
        bank=Material(graph,next(iter(banks)))
        if not native_text(graph,bank.unit):
            continue
        transfer,classified=transfer_fields(graph,bank,obs)
        if (not transfer or transfer["transfer_status"][1] not in SUCCESS or transfer["payment_designation"][1] not in (stage["name"],stage["name"]+"验收款") or
                any(transfer[k][1]!=contract.body(c) for k,c in (("payer","buyer"),("payee","seller"),("contract_id","contract_id"))) or
                any(v[0] not in f["evidence"] for v in transfer.values())):
            continue
        compare(f,record,transfer["paid_on"],"payment")
        if classified:
            f["substitution_dates"]["designation_refs"]=classified
            f["evidence"]=list(dict.fromkeys([*f["evidence"],*classified]))


def edges(findings):
    cited=dict.fromkeys((c["condition"],c["decision"],c["date_ref"]) for f in findings if (c:=f.get("substitution_dates")))
    return [{"type":RELATION,"from":decision,"to":event,"evidence":[condition,decision,event]} for condition,decision,event in cited]
