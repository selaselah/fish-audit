const PdfSignatures = (() => {
  function panel(finding, graph, findings, calls, policy) {
    const check=finding?.effect_review?.pdf_execution, ledger=graph?.pdf_execution_sources;
    if (!check || finding.status==='ok' || ledger?.format!=='pdf-execution-v1' || !finding.scope.includes(check.unit) ||
        !graph.documents_by_kind.contract?.includes(check.unit)) return null;
    const record=ledger.documents.find(r=>r.id===check.source && r.units.includes(check.unit));
    if (!record || !['unsigned','current','earlier','mismatch','review'].includes(record.state) ||
        !Array.isArray(record.signatures) || record.state==='unsigned' && record.signatures.length) return null;
    for (const item of record.signatures) {
      if (!['current','earlier','mismatch','review','timestamp'].includes(item.state)) return null;
      if (['current','earlier','mismatch'].includes(item.state) &&
          (!Number.isSafeInteger(item.revision) || item.revision<1 || !Number.isSafeInteger(item.ends_at) ||
           item.ends_at<1 || !Number.isSafeInteger(record.size) || item.ends_at>record.size ||
           !/^[a-f0-9]{64}$/.test(item.certificate_sha256) ||
           item.state==='current' && (item.coverage!=='ENTIRE_FILE' || item.ends_at!==record.size) ||
           item.state==='earlier' && (item.coverage!=='ENTIRE_REVISION' || item.ends_at>=record.size))) return null;
    }
    if (['current','earlier','mismatch'].includes(record.state) && !record.signatures.some(s=>s.state===record.state)) return null;
    const index=graphIndex(graph), doc=index.documents.get(record.doc), audit=index.nodes.get(record.id);
    const refs=new Set(traceReferences(graph,finding));
    if (doc?.ext!=='.pdf' || !doc.sha256 || doc.sha256!==record.original_sha256 || audit?.type!=='pdf_signature_inspection' ||
        audit.doc!==doc.id || audit.sha256!==doc.sha256 || ![record.id,doc.id].every(r=>refs.has(r)) ||
        !graph.edges.some(e=>e.type==='pdf_signature_source' && e.from===doc.id && e.to===record.id && e.evidence.includes(doc.id))) return null;
    const pages=graph.contract_effect_sources.pages.filter(p=>p.unit===check.unit && p.doc===doc.id);
    const state=record.state==='unsigned' ? (pages.length && pages.every(p=>p.native && p.text_only)?'typeset':'visual') : record.state;
    if (state!==check.state || !pages.length || pages.length!==check.pages.length || !pages.every((p,i)=>{
      const id=doc.id+'/p'+p.page, page=index.nodes.get(id), call=calls?.find(c=>c.doc===doc.id && c.page===p.page);
      return id===check.pages[i] && refs.has(id) && page?.type==='page' && call?.page_sha256===page.sha256;
    })) return null;
    const lines=SigningParties.sources(graph).filter(r=>r.unit===check.unit && r.doc===doc.id && r.role==='signature');
    if (lines.length!==check.rows.length || !lines.every((r,i)=>r.id===check.rows[i] && [r.id,...r.facts].every(ref=>refs.has(ref)))) return null;
    const model={id:'pdf-signatures',record,state,filename:doc.name,originalLabel:'下载原件',original:workpaperSource(doc.id,'original'),
      thumbnail:workpaperSource(doc.id,'pages/'+pages[0].page),page:()=>openPage(doc.id,pages[0].page),request:canReviewCurrentPaper()?draftSupplement:null,
      rows:lines.map(r=>{
        const fact=r.facts.map(ref=>index.facts.get(ref)).find(f=>f?.doc===doc.id && f.page===r.page &&
          f.source_sha256===doc.sha256 && f.page_sha256===index.nodes.get(doc.id+'/p'+r.page)?.sha256 &&
          f.source_line?.text===r.quote && f.source_line.number===r.line && f.source_line.rects?.length);
        return {side:r.side==='buyer'?'甲方':'乙方',page:r.page,line:r.line,quote:r.quote,
          excerpt:fact?()=>EvidenceCompare.lineExcerpt(fact,index):null,
          open:()=>openPage(doc.id,r.page,r.line?null:r.facts[0],r.line)};
      })};
    const basis=index.nodes.get('source/electronic-signature'), method=policy?.sources?.['electronic-signature'];
    if (method && basis?.type==='method_reference' && basis.url===method.url && basis.url.startsWith('https://') &&
        graph.edges.some(e=>e.type==='method_reference' && e.from===basis.id && e.to==='control/H01')) {
      model.basis={label:method.title+' '+method.locator,url:method.url};
    }
    const root=PdfSignatureCard.render(model);
    const related=findings.filter(f=>['H04','H05'].includes(f.rule) && f.stage && f.scope.includes(check.unit) && traceReferences(graph,f).includes(record.id));
    if (related.length) {
      const links=box('pdf-related',el('small','引用此凭证'));
      for (const f of related) {
        const label=f.stage.name+(f.rule==='H05'?'实付':'');
        const button=action(label,()=>revealPaperTarget(document.querySelector('[data-finding="'+CSS.escape(f.id)+'"]')),'word-phase');
        button.dataset.pdfPhase=f.id; button.setAttribute('aria-label',label+' · '+statusName(f.status)+'，查看审计依据'); links.append(button);
      }
      root.append(links);
    }
    return root;
  }
  return {panel};
})();
