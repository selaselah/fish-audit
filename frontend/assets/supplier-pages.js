const SupplierPages = (() => {
  const formats=['pdf-supplier-pages-v1','pdf-supplier-pages-v2'];
  const verified=new WeakMap();
  const sha=value=>typeof value==='string' && /^[a-f0-9]{64}$/.test(value);
  const pageKey=p=>p.doc+'/p'+p.page;
  const samePlace=(a,b)=>a.unit===b.unit && a.doc===b.doc && a.page===b.page;
  const sameRow=(a,b)=>samePlace(a,b) && a.line===b.line && a.quote===b.quote && a.kind===b.kind &&
    Array.isArray(a.facts) && Array.isArray(b.facts) && a.facts.length===b.facts.length && a.facts.every((id,i)=>id===b.facts[i]);
  const equalRects=(a,b)=>Array.isArray(a) && a.length>0 && JSON.stringify(a)===JSON.stringify(b);

  function resolve(finding,graph,calls,policy) {
    const check=finding?.acceptance_reservations?.supplier, ledger=graph?.supplier_page_sources;
    if (!check?.page_inspections?.length || !formats.includes(ledger?.format) || !Array.isArray(ledger.pages) ||
        policy?.supplier_page_inspection!==ledger.format || !['ok','missing','risk'].includes(check.status) ||
        !check.names || ![check.pages,check.lines,check.page_inspections,check.matching_print].every(Array.isArray)) return null;
    const index=graphIndex(graph), refs=new Set(traceReferences(graph,finding));
    const origin=graph.acceptance_reservation_sources;
    if (!Array.isArray(origin?.supplier_pages) || !Array.isArray(origin.supplier_rows)) return null;
    const pages=origin.supplier_pages.filter(p=>finding.scope.includes(p.unit));
    const lines=origin.supplier_rows.filter(p=>finding.scope.includes(p.unit));
    const inspected=ledger.pages.filter(p=>finding.scope.includes(p.unit));
    if (pages.length!==check.pages.length || lines.length!==check.lines.length ||
        !lines.every((l,i)=>sameRow(l,check.lines[i])) || inspected.length!==check.page_inspections.length) return null;
    const units=new Map(), proofPages=[];
    for (const [i,p] of pages.entries()) {
      const saved=check.pages[i], doc=index.documents.get(p.doc), key=pageKey(p), node=index.nodes.get(key);
      const receipt=calls?.find(c=>c.doc===p.doc && c.page===p.page);
      if (!samePlace(saved,p) || !['contract','receipt'].includes(p.role) || p.role!==saved.role || p.native!==saved.native ||
          p.text_only!==saved.text_only || !graph.documents_by_kind[p.role==='contract'?'contract':'acceptance']?.includes(p.unit) ||
          !sha(doc?.sha256) || !refs.has(key) || node?.type!=='page' || !sha(node.sha256) || receipt?.page_sha256!==node.sha256) return null;
      if (!units.has(p.unit)) units.set(p.unit,{role:p.role,label:p.role==='contract'?'合同供应方':'验收供应方',
        filename:doc.name,doc:p.doc,name:check.names[p.unit],rows:[],unlocated:[]});
      const unit=units.get(p.unit);
      if (unit.doc!==p.doc || unit.role!==p.role) return null;
      const entries=lines.filter(l=>samePlace(l,p));
      if (!entries.length) unit.unlocated.push({page:p.page,open:()=>openPage(p.doc,p.page)});
      for (const row of entries) {
        const edge=graph.edges.find(e=>e.type==='supplier_identity_basis' && e.from===p.unit && e.to===key &&
          e.line===row.line && [key,...row.facts].every(id=>e.evidence.includes(id) && refs.has(id)));
        if (!edge) return null;
        const fact=row.facts.map(id=>index.facts.get(id)).find(f=>f && f.doc===p.doc && f.page===p.page &&
          f.source_sha256===doc.sha256 && f.page_sha256===node.sha256 && f.quote===row.quote &&
          (row.kind!=='seller' || f.field==='seller'));
        const anchored=fact && fact.source_line?.text===row.quote && fact.source_line.number===row.line && fact.source_line.rects?.length;
        unit.rows.push({page:p.page,line:row.line,quote:row.quote,kind:row.kind,fact,
          excerpt:anchored?()=>EvidenceCompare.lineExcerpt(fact,index):null,
          open:()=>openPage(p.doc,p.page,anchored || !row.line ? fact?.id : null,anchored ? null : row.line)});
      }
    }
    for (const unit of units.values()) {
      if (!unit.name) continue;
      const seller=unit.rows.filter(r=>r.kind==='seller');
      if (seller.length!==1 || typeof seller[0].fact?.value!=='string' || !['anchored','confirmed'].includes(seller[0].fact.status) ||
          ![unit.name,seller[0].quote].includes(seller[0].fact.value.trim()) ||
          seller[0].quote.replace('：',':').split(':').slice(1).join(':').trim()!==unit.name) return null;
    }
    for (const [i,p] of inspected.entries()) {
      const key=pageKey(p), doc=index.documents.get(p.doc), page=index.nodes.get(key), n=index.nodes.get(p.id);
      const place=pages.find(item=>samePlace(item,p));
      if (!place || p.role!==place.role || p.native!==place.native || p.text_only!==place.text_only ||
          p.id!=='supplier-page/'+key || check.page_inspections[i]!==p.id || !refs.has(p.id) ||
          n?.type!=='supplier_page_inspection' || n.doc!==p.doc || n.page!==p.page ||
          doc.ext!=='.pdf' || doc.sha256!==p.original_sha256 || page.sha256!==p.page_sha256 ||
          !['same_print','review','annotations'].includes(p.state) || !Array.isArray(p.annotations)) return null;
      const source=graph.edges.find(e=>e.type==='supplier_page_source' && e.from===key && e.to===p.id);
      if (![key,doc.id,...(p.signature_source?[p.signature_source]:[])].every(ref=>source?.evidence.includes(ref))) return null;
      if (p.signature_source) {
        const signature=graph.pdf_execution_sources?.documents.find(s=>s.id===p.signature_source && s.doc===doc.id);
        if (signature?.original_sha256!==doc.sha256 || index.nodes.get(p.signature_source)?.type!=='pdf_signature_inspection') return null;
      }
      if (p.count===null ? p.state!=='review' || p.annotations.length :
          !Number.isSafeInteger(p.count) || p.count<0 || p.count<p.annotations.length) return null;
      if (p.annotations.some((a,i)=>a.number!==i+1 || !['annotation','signature_field','signature_details','signature_reason'].includes(a.kind) ||
          typeof a.note!=='string' || (a.kind==='signature_reason' && typeof a.signing_reason!=='string'))) return null;
      if (p.state==='same_print') {
        const proof=p.comparison;
        if (!p.signature_source || !proof?.same_positions || proof.revision!==1 || !sha(proof.original_sha256) ||
            !Number.isSafeInteger(proof.ends_at) || proof.ends_at<=0 || proof.ends_at>=doc.size ||
            proof.first_page_sha256!==page.sha256 || proof.page_sha256!==page.sha256 ||
            !sha(page.text_sha256) || proof.first_text_sha256!==page.text_sha256 || proof.text_sha256!==page.text_sha256 ||
            !p.count || p.count!==p.annotations.length || p.annotations.some(a=>a.kind!=='signature_field')) return null;
        if (check.matching_print.includes(p.id)) {
          const seller=units.get(p.unit).rows.filter(r=>r.page===p.page && r.kind==='seller');
          if (p.role!=='contract' || !p.native || !seller.every(r=>p.readings?.some(l=>l.line===r.line && l.quote===r.quote &&
              equalRects(l.rects,r.fact?.source_line?.rects)))) return null;
        }
      } else if (check.matching_print.includes(p.id)) return null;
      proofPages.push({...p,filename:doc.name,download:true,original:workpaperSource(doc.id,'original'),
        thumbnail:workpaperSource(doc.id,'pages/'+p.page),open:()=>openPage(doc.id,p.page)});
    }
    const names=new Set([...units.values()].map(u=>u.name).filter(Boolean));
    if (check.status==='risk' && names.size<2) return null;
    if (check.status==='ok' && ([...units.values()].some(u=>!u.name) || names.size!==1 ||
        pages.some(p=>!p.native || (!p.text_only && !check.matching_print.includes('supplier-page/'+pageKey(p)))))) return null;
    return {id:'supplier-pages',units:[...units.values()],pages:proofPages,status:check.status,legacy:ledger.format===formats[0]};
  }

  function panel(report) {
    const source=current(report);
    if (!source) return null;
    const model={...source,pages:source.pages.map(page=>({...page}))};
    const effect=report.findings.find(f=>f.rule==='H01');
    for (const p of model.pages) {
      const related=[];
      if (p.signature_source && effect?.effect_review?.pdf_execution?.source===p.signature_source &&
          traceReferences(report.graph,effect).includes(p.signature_source)) {
        related.push({id:effect.id,label:'同一原件的签署凭证',open:()=>revealPaperTarget(document.getElementById('pdf-signatures') ||
          document.querySelector('[data-finding="'+CSS.escape(effect.id)+'"]'))});
      }
      for (const f of report.findings) {
        if (!f.stage || !['H04','H05'].includes(f.rule) || !f.scope.includes(p.unit) || !traceReferences(report.graph,f).includes(p.id)) continue;
        related.push({id:f.id,label:f.stage.name+' · '+(f.rule==='H05'?'实付时点':'付款条件')+' · '+statusName(f.status),
          open:()=>revealPaperTarget(document.querySelector('[data-finding="'+CSS.escape(f.id)+'"]'))});
      }
      p.related=related;
    }
    if (canReviewCurrentPaper() && model.status!=='ok') {
      const p=model.pages.find(p=>p.state==='annotations') || model.pages[0];
      const reason=p.annotations.some(a=>a.kind==='signature_reason');
      const note=model.status==='risk'?'请核对合同与验收原件所列的供应方及委托交付关系，并附交付依据。':
        '请核实《'+p.filename+'》第 '+p.page+' 页'+(reason?'签署原因':p.state==='annotations'?'批注或表单':'原件记载')+'对供货主体与验收范围的影响，并附交付依据。';
      model.request=()=>draftSupplement(note);
    }
    return SupplierCard.render(model);
  }
  function current(report) {
    if (!report) return null;
    const bundle=state.bundle?.report===report ? state.bundle : null;
    if (bundle && verified.has(bundle)) return verified.get(bundle);
    const model=resolve(report.findings.find(f=>f.rule==='H02'),report.graph,report.calls.pages,report.policy);
    if (bundle) verified.set(bundle,model);
    return model;
  }
  return {resolve,panel,current};
})();
