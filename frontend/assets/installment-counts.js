// The original model quote and the full native contract line are separate evidence.
const InstallmentCount = (() => {
  const format='printed-installment-count-v1';
  const headings=['付款条款','付款方式','结算条款','结算方式'];
  const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  function bind(report,id,item) {
    if (report?.policy?.installment_count!==format ||
        !/^[a-f0-9]{64}$/u.test(report.policy.code_sha256?.['installment_counts.py'])) return null;
    const g=report.graph, ledger=g.installment_count_sources, r=ledger?.rows?.[0];
    if (ledger?.format!==format || !r || ledger.rows.length!==1 || r.id!==id || !Array.isArray(r.rects) || !r.rects.length || !r.rects.every(box=>
      Array.isArray(box) && box.length===4 && box.every(n=>Number.isFinite(n) && n>=0 && n<=1) && box[0]<box[2] && box[1]<box[3])) return null;
    const pid=r.doc+'/p1', ix=graphIndex(g), doc=ix.documents.get(r.doc), page=ix.nodes.get(pid), node=ix.nodes.get(id);
    if (r.unit!==r.doc || r.page!==1 || !Number.isSafeInteger(r.line) || r.line<1 || id!=='installment-count/'+pid+'/l'+r.line ||
      !same(g.documents_by_kind.contract,[r.unit]) || doc?.ext!=='.pdf' || doc.pages!==1 || doc.sha256!==r.original_sha256 ||
      ix.nodes.get(r.doc)?.sha256!==doc.sha256 || page?.layer!=='text' || !page.clause_text_only || page.sha256!==r.page_sha256 ||
      node?.type!=='installment_count_line' || node.doc!==r.doc || node.page!==1 || node.line!==r.line || node.label!==r.quote || node.count!==r.count) return null;
    const raw=/^([^:：]+)[:：](.*)$/u.exec(r.quote), count=/^(?:合同价款)?分([1-9][0-9]?|[一二两三四五六七八九十]{1,3})期(?:付款|支付|结算)$/u.exec(r.value);
    const fields=g.facts.filter(f=>(f.unit || f.doc)===r.unit && f.field==='payment_term'),f=fields[0];
    if (!raw || !headings.includes(raw[1].trim()) || raw[2].trim()!==r.value || !count ||
        BatchPhase.ordinal(count[1])!==r.count || fields.length!==1 || f.id!==r.model_ref || f.field!==r.field ||
        f.quote!==r.model_quote || f.value!==r.value || f.quote!==f.value || f.source_line || f.amendment || f.attestation ||
        f.status!=='visual' || f.visual_check!=='clear' || f.source_sha256!==doc.sha256 || f.page_sha256!==page.sha256 ||
        !new RegExp('^'+pid+'/f[1-9][0-9]*$').test(f.id)) return null;
    const gaps=g.gaps.filter(v=>v.doc===r.doc && v.page===1 && v.line===r.line && v.field==='payment_term' && v.quality==='uncovered');
    const origins=g.edges.filter(e=>e.type==='locates_installment_count' && e.to===id);
    const records=g.edges.filter(e=>e.type==='records' && e.to===f.id);
    if (gaps.length!==1 || gaps[0].quote!==r.quote || origins.length!==1 || origins[0].from!==pid || !same(origins[0].evidence,[pid,f.id]) ||
        records.length!==1 || records[0].from!==pid || !same(records[0].evidence,[f.id])) return null;
    const calls=(report.calls?.pages || []).filter(c=>c.doc===r.doc && c.page===1), c=calls[0], index=f.id.split('/f')[1];
    if (calls.length!==1 || c.page_sha256!==page.sha256 || c.output?.quality!=='readable' || !c.response_id || c.response_id!==f.response_id ||
        !c.check?.response_id || c.check.response_id===c.response_id || c.check.response_id!==f.check_response_id ||
        !Array.isArray(c.output.facts) || !Array.isArray(c.check.input) || !Array.isArray(c.check.output?.checks) ||
        !same(c.installment_count_rects?.[r.line],r.rects)) return null;
    const first=c.output.facts[Number(index)-1], ins=c.check.input.filter(v=>v.index===index), votes=c.check.output.checks.filter(v=>v.index===index);
    if (first?.field!==f.field || first.value!==f.value || first.quote!==f.quote || ins.length!==1 || ins[0].field!==f.label ||
        ins[0].quote!==f.quote || ins[0].value!==f.value || votes.length!==1 || votes[0].support!=='clear') return null;
    if (item && (item.installment_count!==id || !item.scope.includes(r.unit) ||
        !['H03','H04','H05','H06'].includes(item.rule) || item.rule!=='H03' && !item.stage ||
        ![id,pid,f.id].every(ref=>item.evidence.includes(ref) && traceReferences(g,item).includes(ref)))) return null;
    return {row:r,doc};
  }
  function source(r) {
    return {ref:r.id,rawLine:r.line,quote:r.quote,rects:r.rects,modelQuote:r.model_quote,label:'合同分期总述',
      option:'合同分期总述 · 第 '+r.line+' 行',quality:'installment_count_source'};
  }
  function pageReferences(report,doc,page) {
    const f=report?.findings.find(f=>f.rule==='H03' && f.installment_count);
    const proof=f && bind(report,f.installment_count,f);
    return proof && proof.doc.id===doc && page===1?[source(proof.row)]:[];
  }
  function citation(report,id,item,panel=false) {
    const f=item || report.findings.find(f=>f.rule==='H03' && f.installment_count===id);
    const proof=f && bind(report,id,f);
    if (!proof) return el('span','合同分期总述待核','small');
    const {row:r,doc}=proof, place='第 1 页 · 第 '+r.line+' 行';
    const button=action('',()=>{
      if (state.bundle?.report===report) OriginalReader.open(doc,1,{lineHint:r.line,rawRef:r.id,printedSource:source(r)});
    },'ref installment-count-link');
    button.append(glyph('file-earmark-text'),el('strong','合同列明 '+r.count+' 期'),el('small',place),glyph('arrows-angle-expand'));
    button.dataset.countRef=id;button.dataset.originalLabel='合同分期总述 · '+doc.name+' · '+place;
    button.title=r.quote;button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-controls','page-dialog');
    if (panel) {
      button.id='installment-count-'+f.id;
      Object.assign(button.dataset,{countFinding:f.id,caseId:report.case_id,rev:String(state.bundle.rev)});
    }
    return button;
  }
  return {bind,pageReferences,citation};
})();
