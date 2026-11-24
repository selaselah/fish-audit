"""Compare a board-approved procurement with additional effectiveness riders on text and image layers."""

import argparse
import hashlib

from contract_dates import DATE_FIELDS
from contract_milestones import PROFILE, confirm_printed_records, documents
from generate import ROOT, embedded_font, pdf
from quality_addenda import pdf_with_note
from quality_reinspection import reconcile_training_pages
from run import BASE, get, submit


CASES={"approved":"具备约定的董事会决议和签章",
       "written":"盖章条款之外另须取得主管机构批准",
       "image":"合同影像附注另定生效条件"}
NOTE="本合同须取得主管机构书面批准后方可生效"


def generate(seed,mode):
    code=hashlib.sha256((seed+"-"+mode).encode()).hexdigest()[:8].upper()
    folder=ROOT/"31-合同附加生效条件"/code
    folder.mkdir(parents=True,exist_ok=True)
    records=documents(code,"approved" if mode=="approved" else "complete")
    if mode=="written":
        records["采购合同"].append(("附加生效条件",NOTE))
    font=embedded_font("ContractEffectCJK")
    for title,rows in records.items():
        path=folder/(title+".pdf")
        if mode=="image" and title=="采购合同":
            pdf_with_note(path,title,rows,font,"附注："+NOTE,spacing=28,note_y=105)
        else:
            pdf(path,title,rows,font=font,spacing=28)
    return folder,records


def validate(report,mode):
    signed=next(f for f in report["findings"] if f["rule"]=="H01")
    entry=signed["effect_review"]
    phases=[f for f in report["findings"] if f["rule"] in ("H04","H05")]
    if mode=="approved":
        assert signed["status"]=="ok" and all(f["status"]=="ok" for f in phases),(signed,phases)
        assert entry=={"conditions":[],"mixed_pages":[]} and report["result"]["verdict"]=="pass"
    else:
        assert signed["status"] in ("risk","missing") and all(f["status"]!="ok" for f in phases),(signed,phases)
        assert report["result"]["verdict"]=="review",report["result"]
        if mode=="written":
            assert any(s["quote"]=="附加生效条件："+NOTE and s["line"] for s in entry["conditions"])
        else:
            assert any(p["native"] and not p["text_only"] for p in entry["mixed_pages"])
        assert all(f"{p['doc']}/p{p['page']}" in signed["evidence"] for p in [*entry["conditions"],*entry["mixed_pages"]])


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",action="store_true")
    parser.add_argument("--run-id",default="synthetic-contract-effect-v1")
    parser.add_argument("--cases",nargs="+",choices=CASES,default=list(CASES))
    args=parser.parse_args()
    queued=[]
    for mode in args.cases:
        folder,records=generate(args.run_id,mode)
        if not args.run:
            print(folder)
            continue
        cid=submit("合成演练 · "+CASES[mode],sorted(folder.glob("*.pdf")),args.run_id+"-"+mode,PROFILE)
        print(mode,BASE+"/workpaper/"+cid,flush=True)
        queued.append((mode,cid,folder,records))
    for mode,cid,folder,records in queued:
        reconcile_training_pages(cid,folder,records,case_titles=CASES.values(),field_labels=DATE_FIELDS,
                                 document_types={"合同审批单":"contract_approval"},row_spacing=28)
        report=confirm_printed_records(cid,folder,records)
        validate(report,mode)
        print(mode,"R"+str(get("/api/cases/"+cid)["rev"]),report["result"]["verdict"],flush=True)
