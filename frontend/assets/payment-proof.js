// Resolve the selected finding against its issued graph and the same revision's page geometry.
const PaymentProof = (() => {
  const format='payment-execution-basis-v1';
  function sources(graph) {
    const ledger=graph?.payment_execution_sources;
    if (ledger?.format!==format) return [];
    const index=graphIndex(graph);
    const links=new Map(graph.edges.filter(e=>e.type==='payment_execution_source').map(e=>[e.to,e]));
    const units=new Map(graph.audit_documents?.filter(d=>d.source).map(d=>[d.source+'/p'+d.page,d.id]));
    return ledger.rows.filter(r=>{
      const pageId=r.doc+'/p'+r.page, page=index.nodes.get(pageId), doc=index.documents.get(r.doc);
      const edge=links.get(r.id), n=index.nodes.get(r.id);
      return doc?.sha256 && index.nodes.get(r.doc)?.sha256===doc.sha256 && page?.sha256 && page.type==='page' &&
        (units.get(pageId) || r.doc)===r.unit && n?.type==='payment_execution_line' && n.label===r.quote &&
        n.doc===r.doc && n.page===r.page && n.line===r.line && edge?.from===pageId && edge.evidence[0]===pageId &&
        edge.evidence.length===r.facts.length+1 && r.facts.every((id,i)=>{
          const f=index.facts.get(id);
          return edge.evidence[i+1]===id && f?.doc===r.doc && f.page===r.page && (f.unit || f.doc)===r.unit &&
            f.source_sha256===doc.sha256 && f.page_sha256===page.sha256 && (r.line || f.quote===r.quote);
        }) && (r.line ? Number.isInteger(r.line) && r.line>0 && page.text_sha256 : r.facts.length===1);
    });
  }
  function rectangles(graph,calls,row) {
    if (!row.line) return [];
    const index=graphIndex(graph), page=index.nodes.get(row.doc+'/p'+row.page);
    const call=calls?.find(p=>p.doc===row.doc && p.page===row.page && p.page_sha256===page?.sha256);
    const rects=call?.payment_execution_rects?.[row.line];
    if (!Array.isArray(rects) || !rects.every(r=>Array.isArray(r) && r.length===4 &&
        r.every(v=>Number.isFinite(v) && v>=0 && v<=1) && r[2]>r[0] && r[3]>r[1])) return [];
    for (const id of row.facts) {
      const loc=index.facts.get(id)?.source_line;
      if (loc && (loc.number!==row.line || loc.text!==row.quote || JSON.stringify(loc.rects)!==JSON.stringify(rects))) return [];
    }
    return rects;
  }
  function entries(report,findings=report?.findings || []) {
    if (report?.policy.payment_execution!==format || report.graph.payment_execution_sources?.format!==format) return [];
    const graph=report.graph, index=graphIndex(graph), ledger=graph.payment_execution_sources, all=sources(graph);
    const items=[];
    for (const finding of findings) {
      const basis=finding.execution_basis;
      if (finding.rule!=='H05' || !basis || !finding.scope.includes(basis.unit)) continue;
      const unit=ledger.units.find(u=>u.unit===basis.unit);
      const complete=unit && unit.state===basis.state && unit.bank===basis.bank && Array.isArray(basis.rows) &&
        unit.rows.length===basis.rows.length && unit.rows.every((id,i)=>id===basis.rows[i]);
      const refs=new Set(traceReferences(graph,finding));
      const valid=all.filter(r=>r.unit===basis.unit && unit?.rows.includes(r.id) && refs.has(r.id) &&
        refs.has(r.doc+'/p'+r.page) && r.facts.every(id=>refs.has(id)));
      const rows=valid.map(r=>{
        const rects=rectangles(graph,report.calls.pages,r), file=index.documents.get(r.doc).name;
        const clear=Boolean(r.line && rects.length && !r.disputed && index.nodes.get(r.doc+'/p'+r.page)?.clause_text_only===true &&
          !graph.gaps.some(g=>g.doc===r.doc && g.page===r.page && ['partial','unreadable','section_unresolved'].includes(g.quality)) &&
          !Object.entries(graph.documents_by_kind).some(([kind,units])=>kind!=='bank_receipt' && units.includes(r.unit)));
        const explicit=clear && ['request','limit'].includes(r.kind) && !/如遇|如果|若|当状态为|当交易|如交易|如为|如显示|示例/u.test(r.quote);
        return {...r,file,rects,clear,explicit,pageImage:workpaperSource(r.doc,'pages/'+r.page),place:'第 '+r.page+' 页'+(r.line?' · 第 '+r.line+' 行':' · 行号待核'),
          excerpt:rects.length?()=>EvidenceCompare.lineExcerpt({doc:r.doc,page:r.page,source_line:{rects}},index):null,
          open:()=>r.line?openPage(r.doc,r.page,undefined,r.line,undefined,'execution-line/'+r.line):openPage(r.doc,r.page,r.facts[0])};
      });
      let state='unverified';
      const node=index.nodes.get('finding/'+finding.id);
      const sameFinding=node?.type==='finding' && node.status===finding.status && node.detail===finding.detail;
      if (complete && rows.length===unit.rows.length && sameFinding && finding.status===(basis.state==='conflict'?'risk':'missing')) {
        if (basis.state==='review' || (basis.state==='application' && rows.some(r=>r.explicit && r.kind==='request')) ||
            (basis.state==='limited' && rows.some(r=>r.explicit && r.kind==='limit'))) state=basis.state;
        if (basis.state==='conflict' && basis.bank && rows.some(s=>s.clear && s.kind==='status' && PaymentProofCard.success(s.quote) &&
            rows.some(r=>r.explicit && r.doc===s.doc && r.page===s.page))) state='conflict';
      }
      const stage=finding.stage, clause=stage?.clause_ref;
      const picked=clause && refs.has(clause) && index.facts.get(clause)?.field==='payment_stage' ? stage : null;
      const file=rows[0]?.file || index.documents.get(basis.unit)?.name || '付款凭证';
      items.push({key:finding.id,clause:picked?.clause_ref,stage:picked?.name,
        name:file+' · '+(picked?picked.name:'期次待核'),state,rows,...PaymentProofCard.pairs(rows,state)});
    }
    return items;
  }
  function panel(report) {
    const items=entries(report);
    return items.length?PaymentProofCard.render(items,'payment-proof'):null;
  }
  function jump(finding,label='核对扣款凭证') {
    const button=action(label,()=>{
      const panel=document.getElementById('payment-proof');
      panel?.dispatchEvent(new CustomEvent('select-proof',{detail:finding.id}));revealPaperTarget(panel);
    },'text-button');
    button.setAttribute('aria-controls','payment-proof');
    return button;
  }
  return {panel,jump,sources,rectangles,entries};
})();
