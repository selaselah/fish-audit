// Follow only the sources archived with this report revision and this bank receipt.
const PaymentAcceptance = (() => {
  const format='payment-acceptance-reference-v1';
  const codeFrom=quote=>typeof quote==='string' ? quote.slice(quote.search(/[:：]/u)+1).trim() : '';
  const fields={citation:'payment_acceptance_ref',number:'acceptance_number'};
  function sources(graph) {
    const ledger=graph?.payment_acceptance_sources;
    if (ledger?.format!==format || !Array.isArray(ledger.rows)) return [];
    const idx=graphIndex(graph),links=new Map(),owners=new Map(),pages=new Map();
    for (const e of graph.edges) {
      if (e.type==='payment_acceptance_source') links.set(e.to,e);
      if (e.type==='records' && e.evidence.includes(e.to)) owners.set(e.to,e.from);
      if (e.type==='contains' && e.evidence.includes(e.to)) pages.set(e.to,e.from);
    }
    return ledger.rows.filter(row=>{
      const pageId=row.doc+'/p'+row.page, doc=idx.documents.get(row.doc), page=idx.nodes.get(pageId), node=idx.nodes.get(row.id);
      const link=links.get(row.id),place=ledger.pages.find(p=>p.doc===row.doc && p.page===row.page && p.unit===row.unit && p.role===row.role);
      if (!place || pages.get(pageId)!==row.doc || !doc || idx.nodes.get(row.doc)?.sha256!==doc.sha256 || !page?.sha256 ||
          place.native!==(page.layer==='text') || place.text_only!==(page.clause_text_only===true) ||
          !Array.isArray(row.facts) || node?.type!=='payment_acceptance_line' || node.label!==row.quote ||
          node.doc!==row.doc || node.page!==row.page || node.line!==row.line || link?.from!==pageId ||
          link.evidence[0]!==pageId || link.evidence.length!==1+row.facts.length) return false;
      const key=row.line==null ? row.facts[0] : pageId+'/l'+row.line;
      if (row.id!=='payment-acceptance/'+key) return false;
      return row.facts.every((ref,i)=>{
        const f=idx.facts.get(ref);
        return owners.get(ref)===pageId && link.evidence[i+1]===ref && f?.doc===row.doc && f.page===row.page &&
          (f.unit || f.doc)===row.unit && f.source_sha256===doc.sha256 && f.page_sha256===page.sha256;
      });
    });
  }
  function observation(row,graph) {
    const matches=row.facts.map(id=>graphIndex(graph).facts.get(id)).filter(f=>f?.field===fields[row.kind] &&
      ['anchored','confirmed'].includes(f.status) && f.source_line?.number===row.line &&
      f.source_line.text===row.quote && f.source_line.rects.length);
    return matches.length===1?matches[0]:null;
  }
  function open(row,graph) {
    const fact=observation(row,graph);
    openPage(row.doc,row.page,fact?.id,fact?undefined:row.line);
  }
  function panel(report) {
    if (report?.policy.payment_acceptance!==format) return null;
    const graph=report.graph,idx=graphIndex(graph),rows=new Map(sources(graph).map(r=>[r.id,r]));
    const checks=report.findings.filter(f=>f.rule==='H05' && f.payment_acceptance?.format===format);
    if (!checks.length) return null;
    const units=graph.documents_by_kind, contract=units.contract?.length===1 && units.contract[0];
    const batch=report.findings.find(f=>f.rule==='H02')?.batch_acceptance;
    const items=checks.map((f,i)=>{
      const p=f.payment_acceptance, refs=new Set(traceReferences(graph,f));
      function validFact(id,field,unit,supported=refs) {
        const fact=idx.facts.get(id),pg=fact && idx.nodes.get(fact.doc+'/p'+fact.page);
        return supported.has(id) && fact?.field===field && (fact.unit || fact.doc)===unit && ['anchored','confirmed'].includes(fact.status) &&
          pg?.sha256===fact.page_sha256 && idx.documents.get(fact.doc)?.sha256===fact.source_sha256 &&
          fact.source_line?.rects?.length ? fact : null;
      }
      function located(id,unit,kind) {
        const row=rows.get(id);
        if (!row || row.unit!==unit || row.kind!==kind || !Number.isInteger(row.line) || row.disputed ||
            !refs.has(row.id) || !refs.has(row.doc+'/p'+row.page) || !row.facts.every(ref=>refs.has(ref))) return null;
        const page=report.calls.pages.find(c=>c.doc===row.doc && c.page===row.page);
        return page?.page_sha256===idx.nodes.get(row.doc+'/p'+row.page)?.sha256 ? row : null;
      }
      function source(row) {
        if (!row) return null;
        const fact=observation(row,graph);
        return {value:codeFrom(row.quote),excerpt:fact?()=>EvidenceCompare.lineExcerpt(fact,idx):null,location:'第 '+row.page+' 页 · 第 '+row.line+' 行',open:()=>open(row,graph)};
      }
      const bank=units.bank_receipt?.includes(p.bank) && f.scope.includes(p.bank);
      const citation=bank && p.citations.length===1 && located(p.citations[0],p.bank,'citation');
      const registers=p.register.map(r=>{
        const scope=validFact(r.scope_ref,'acceptance_scope',r.unit),record=batch?.records.find(a=>a.unit===r.unit && a.scope_ref===r.scope_ref);
        const row=located(r.number_row,r.unit,'number');
        return {...r,row,verified:Boolean(r.identified && scope && record?.index===r.batch && row && codeFrom(row.quote)===r.number &&
          (units.acceptance?.includes(r.unit) || units.reinspection?.includes(r.unit)) &&
          r.identity_refs.every(id=>refs.has(id)))};
      });
      const designated=validFact(p.designation_ref,'payment_designation',p.bank);
      const clause=validFact(p.clause_ref,'payment_stage',contract),allocation=validFact(p.allocation_ref,'delivery_batch',contract);
      const own=registers.filter(r=>r.batch===p.batch),cited=registers.filter(r=>r.row && p.number===r.number);
      const anchored=bank && citation && codeFrom(citation.quote)===p.number && p.evidence.every(ref=>refs.has(ref)) &&
        clause && allocation && f.stage?.clause_ref===clause.id && f.stage?.batch_index===p.batch &&
        designated && codeFrom(designated.source_line.text)===f.stage.name &&
        batch?.batches.some(b=>b.index===p.batch && b.clause_ref===allocation.id) && batch?.contract_clear && batch.independent &&
        own.length===1 && p.expected.length===1 && own[0].unit===p.expected[0] && registers.every(r=>r.verified) &&
        p.cited.length===cited.length && cited.every(r=>p.cited.includes(r.unit));
      const supported = anchored && (p.state==='matched' && p.status==='ok' && cited.length===1 && cited[0]===own[0] ||
        p.state==='other_batch' && p.status==='risk' && cited.length===1 && cited[0].batch && cited[0]!==own[0] ||
        p.state==='unlocated' && p.status==='missing' && !cited.length);
      const narrow=['matched','other_batch','unlocated'].includes(p.state);
      const state=supported || !narrow && p.status==='missing' && bank ? p.state : 'unverified';
      const expected=own.length===1 && own[0].verified?source(own[0].row):null;
      const factSource=(fact,label)=>({label,open:()=>openPage(fact.doc,fact.page,fact.id)});
      const paid=[...refs].map(id=>validFact(id,'transfer_amount',p.bank)).filter(Boolean);
      const total=report.findings.find(s=>s.rule==='H06' && PhaseEvidence.sameStage(s.stage,f.stage) && s.stage_payments?.state==='balanced' &&
        s.stage_payments.records.some(r=>r.unit===p.bank) && s.stage_payments.timing.some(r=>r.unit===p.bank && r.status===f.status));
      const operand=total?.stage_payments.records.find(r=>r.unit===p.bank)?.inputs.transfer_amount?.ref;
      const amountFact=paid.length===1?paid[0]:total && operand && validFact(operand,'transfer_amount',p.bank,new Set(traceReferences(graph,total)));
      const amount=amountFact?codeFrom(amountFact.source_line.text):'';
      return {key:f.id,choice:'第 '+(i+1)+' 笔',amount,stage:f.stage?.name,batch:p.batch,state,
        clauseRef:clause?.id,detail:state==='unverified'?'请核对本版底稿中的回单、合同及验收原件。':p.detail,
        bank:source(citation),expected,actual:state==='other_batch'?source(cited[0].row):null,actualBatch:cited[0]?.batch,
        total:total?.stage_payments.seen,
        basis:[clause && factSource(clause,'合同期款原行'),allocation && factSource(allocation,'分批交付原行'),designated && factSource(designated,'回单用途原行')].filter(Boolean)};
    });
    const card=PaymentReferenceCard.render(items,'payment-acceptance');
    card.addEventListener('change-reference',event=>{
      if (event.detail.clauseRef) card.dispatchEvent(new CustomEvent('select-contract-phase',{detail:event.detail.clauseRef}));
    });
    const empty=el('div','','payment-reference-empty');
    const reset=action('查看有回单的期次',()=>{
      const key=card.dataset.payment;
      card.dispatchEvent(new CustomEvent('select-reference',{detail:key}));
      card.focus({preventScroll:true});
    },'text-button');
    const noReceipt=el('p');empty.append(noReceipt,reset);empty.hidden=true;card.append(empty);
    card.addEventListener('change-reference',()=>{empty.hidden=true;});
    card.addEventListener('inspect-payment-stage',event=>{
      const matches=items.filter(i=>i.clauseRef===event.detail.clause_ref);
      empty.hidden=Boolean(matches.length);
      if (!matches.length) {
        noReceipt.textContent=event.detail.name+'尚无可核对验收单号的回单。';
      } else if (!matches.some(i=>i.key===card.dataset.payment)) {
        const next=matches.find(i=>i.state==='other_batch') || matches[0];
        card.dispatchEvent(new CustomEvent('select-reference',{detail:next.key}));
      }
    });
    card.addEventListener('reveal-evidence',()=>{if(card.dataset.clause) card.dispatchEvent(new CustomEvent('select-contract-phase',{detail:card.dataset.clause}));});
    return card;
  }
  function jump(f) {
    const b=action('核对回单所引单号',()=>{
      const target=document.getElementById('payment-acceptance');
      target?.dispatchEvent(new CustomEvent('select-reference',{detail:f.id}));
      revealPaperTarget(target);
    },'text-button');
    b.setAttribute('aria-controls','payment-acceptance');return b;
  }
  return {sources,observation,open,panel,jump};
})();
