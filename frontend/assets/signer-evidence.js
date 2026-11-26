const SignerEvidence = (() => {
  const formats = ['named-acceptance-signatures-v2','named-acceptance-signatures-v3','named-acceptance-signatures-v4'];
  function datedRows(graph) {
    const ledger = graph?.acceptance_authority_sources;
    if (!formats.includes(ledger?.format)) return [];
    const index = graphIndex(graph);
    const links = new Map(graph.edges.filter(e=>e.type==='signer_date_source').map(e=>[e.to,e]));
    return ledger.dates.filter(row=>{
      const pageId=row.doc+'/p'+row.page, pg=index.nodes.get(pageId), doc=index.documents.get(row.doc);
      const node=index.nodes.get(row.id), edge=links.get(row.id);
      return pg?.sha256 && doc?.sha256 && index.nodes.get(row.doc)?.sha256===doc.sha256 &&
        ledger.pages.some(p=>p.doc===row.doc && p.page===row.page && p.unit===row.unit) &&
        node?.type==='acceptance_signer_date' && node.label===row.quote && node.doc===row.doc &&
        node.page===row.page && node.line===row.line && edge?.from===pageId && edge.evidence[0]===pageId &&
        edge.evidence.length===1+row.facts.length && row.facts.every((id,i)=>edge.evidence[i+1]===id);
    });
  }
  function observation(graph,row) {
    return row.facts.map(id=>graphIndex(graph).facts.get(id)).find(f=>f?.source_line?.number===row.line &&
      f.source_line.text===row.quote && f.source_line.rects?.length && f.doc===row.doc && f.page===row.page &&
      f.page_sha256===graphIndex(graph).nodes.get(f.doc+'/p'+f.page)?.sha256 &&
      f.source_sha256===graphIndex(graph).documents.get(f.doc)?.sha256);
  }
  function panel(report) {
    if (!formats.includes(report?.policy.acceptance_authority)) return null;
    const graph=report.graph, index=graphIndex(graph), rows=datedRows(graph);
    const sourceFor=(doc,page,line,quote,open,fact)=>({
      file:index.documents.get(doc).name, place:'第 '+page+' 页'+(line?' · 第 '+line+' 行':' · 行号待核'), quote,open,
      excerpt:fact ? ()=>EvidenceCompare.lineExcerpt(fact,index) : null,
      pageImage:workpaperSource(doc,'pages/'+page), rects:fact?.source_line?.rects
    });
    const items=[];
    for (const f of report.findings) {
      const t=f.signer_timing;
      if (f.rule!=='H05' || t?.format!==report.policy.acceptance_authority || !f.scope.includes(t.bank) || !f.scope.includes(t.receipt)) continue;
      const refs=new Set(traceReferences(graph,f));
      function factRef(id,field,unit) {
        const fact=index.facts.get(id);
        if (!refs.has(id) || fact?.field!==field || (fact.unit || fact.doc)!==unit ||
            !['anchored','confirmed'].includes(fact.status) || !fact.source_line?.rects?.length ||
            fact.page_sha256!==index.nodes.get(fact.doc+'/p'+fact.page)?.sha256 ||
            fact.source_sha256!==index.documents.get(fact.doc)?.sha256) return null;
        return sourceFor(fact.doc,fact.page,fact.source_line.number,fact.source_line.text,()=>openPage(fact.doc,fact.page,id),fact);
      }
      const candidates=rows.filter(r=>t.rows.includes(r.id) && refs.has(r.id) && r.unit===t.receipt);
      const sourceRow=r=>sourceFor(r.doc,r.page,r.line,r.quote,()=>openPage(r.doc,r.page,undefined,r.line),observation(graph,r));
      const contract=graph.documents_by_kind.contract?.[0];
      const clause=factRef(t.clause_ref,'acceptance_signing_clause',contract), term=factRef(t.stage_ref,'payment_stage',contract);
      const payment=factRef(t.paid_ref,'paid_on',t.bank);
      const paid=payment && PhaseEvidence.dateOn(index.facts.get(t.paid_ref));
      const used=new Set();
      const events=t.required.map(name=>{
        const own=candidates.filter(r=>r.name===name);
        const row=own.length===1 && own[0].line && !own[0].disputed ? own[0] : null;
        if (row) used.add(row.id);
        const signatures=t.signed[name] || [];
        const signature=signatures.length===1 ? factRef(signatures[0],'acceptance_signer',t.receipt) : null;
        return {label:name+'签认',kind:'signer',day:row?.day,source:row && sourceRow(row),signature};
      });
      const last=events.map(e=>e.day || '').sort().at(-1);
      const delta=(Date.parse(paid)-Date.parse(last))/86400000;
      const direction=delta<0?'before':delta===0?'same_day':'after';
      const verified=payment && paid===t.paid_on && clause && term && t.rows.length===candidates.length &&
        events.every(e=>e.signature && e.day && e.source) && delta===t.days && last===t.latest_on && direction===t.state;
      events.push({label:'回单付款',kind:'payment',day:paid || null,source:payment});
      items.push({key:f.id,stage:f.stage.name,stageRef:t.stage_ref,choice:f.stage.name+' · '+(payment?.file || '回单')+' · '+(paid || '日期待核'),
        state:['before','same_day','after'].includes(t.state) && !verified ? 'unverified' : t.state,
        days:t.days,events,clause,term,candidates:candidates.filter(r=>!used.has(r.id)).map(sourceRow)});
    }
    if (!items.length) return null;
    const card=SignerTimeline.render(items,'signer-timing');
    const explanation=el('span');
    const back=action('',()=>selectPhase(),'text-button');
    const empty=box('signer-empty',explanation,back); empty.hidden=true; card.append(empty);
    function selectPhase() {
      card.dispatchEvent(new CustomEvent('select-contract-phase',{detail:card.dataset.clause}));
    }
    card.addEventListener('reveal-evidence',selectPhase);
    card.addEventListener('signer-payment-changed',selectPhase);
    card.addEventListener('inspect-payment-stage',event=>{
      const matches=items.filter(i=>i.stageRef===event.detail.clause_ref);
      empty.hidden=Boolean(matches.length); card.dataset.outOfStage=String(!matches.length);
      if (!matches.length) {
        explanation.textContent=event.detail.name+'尚无可比对共同签认日期的回单。';
        back.textContent='返回'+items.find(i=>i.key===card.dataset.findingKey).stage;
      } else if (!matches.some(i=>i.key===card.dataset.findingKey)) {
        card.dispatchEvent(new CustomEvent('select-signer-payment',{detail:matches[0].key}));
      }
    });
    return card;
  }
  function jump(finding) {
    const b=action('核对签认与付款日',()=>{
      const card=document.getElementById('signer-timing');
      card?.dispatchEvent(new CustomEvent('select-signer-payment',{detail:finding.id}));
      revealPaperTarget(card);
    },'text-button');
    b.setAttribute('aria-controls','signer-timing');
    return b;
  }
  return {panel,jump,datedRows,observation};
})();
