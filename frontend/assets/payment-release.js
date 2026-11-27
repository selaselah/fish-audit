// Resolve the release record and mandate against the same issued case and finding.
const ReleaseEvidence = (() => {
  function fact(graph,finding,ref) {
    const release=finding?.payment_opinion?.release;
    const index=graphIndex(graph);
    if (!ref || !release?.evidence.includes(ref) || !finding.evidence.includes(ref) ||
        !index.supports.get('finding/'+finding.id)?.has(ref)) return null;
    const f=index.facts.get(ref);
    return f?.source_line?.rects?.length && f.source_line.text===f.quote ? f : null;
  }
  function sources(graph,finding) {
    const ledger=graph.payment_release_sources;
    if (!ledger) return [];
    const idx=graphIndex(graph);
    if (!idx.releaseSources) {
      const edges=graph.edges.filter(e=>e.type==='payment_release_basis');
      idx.releaseSources=ledger.lines.flatMap(row=>{
        const page=row.doc+'/p'+row.page;
        const edge=edges.find(e=>e.from===row.unit && e.to===page && e.line===row.line && e.evidence.includes(page) &&
          (row.line || row.facts.some(id=>e.evidence.includes(id))));
        return edge?[{...row,facts:row.facts.filter(id=>edge.evidence.includes(id))}]:[];
      });
    }
    if (!finding) return idx.releaseSources;
    const release=finding.payment_opinion?.release;
    if (!release) return [];
    const refs=idx.supports.get('finding/'+finding.id);
    return idx.releaseSources.filter(row=>{
      const page=row.doc+'/p'+row.page;
      return refs?.has(page) && release.evidence.includes(page) && finding.evidence.includes(page) &&
        release.sources.some(s=>s.unit===row.unit && s.doc===row.doc && s.page===row.page && s.line===row.line && s.quote===row.quote && s.role===row.role);
    }).map(row=>({...row,facts:row.facts.filter(id=>refs.has(id) && release.evidence.includes(id) && finding.evidence.includes(id))}));
  }
  function one(rows,role) {
    const found=rows.filter(s=>s.role===role);
    return found.length===1?found[0]:null;
  }
  function caption(release,rows) {
    if (release.state==='pending' && one(rows,'approval_date') && !rows.some(s=>s.role==='date')) return '缺放行签字日';
    if (release.signature_mismatch) return '签名校验不符';
    return {matched:'已核具名放行',signature_pending:'签署身份待核',scope_pending:'放行归属待核',
      signer_mismatch:release.signature_records?'签认栏列名不符':'签发人不符',reference_mismatch:'原验收单号不符',absent:'待补放行单',future:'签字日晚于提交日'}[release.state] || '放行依据待核';
  }
  function filedUnit(graph,id) {
    return sources(graph).some(s=>s.unit===id && s.role==='title' && s.line && s.quote.trim()==='付款放行单' &&
      graph.payment_release_sources.pages.some(p=>p.unit===id && p.doc===s.doc && p.page===s.page && p.role==='release' && p.printed_title));
  }
  function panel(phase,notes,report) {
    if (!report || !phase.payment_opinion?.release?.signature_records?.length) return null;
    const proofs=PerformanceIndex.releaseProofs(phase,report);
    if (proofs.length!==1) return null;
    const [proof]=proofs, {graph}=report, idx=graphIndex(graph), {doc,record}=proof;
    const release=phase.payment_opinion.release, rows=sources(graph,phase), filed=rows.filter(s=>s.unit===record.unit);
    function observation(f) {
      if (!f) return null;
      const loc=f.source_line, exact=loc?.rects?.length && loc.text===f.quote;
      return {value:f.value,verbatim:exact && f.value===f.quote,place:'第 '+f.page+' 页'+(exact?' · 第 '+loc.number+' 行':' · 整页'),
        excerpt:exact?()=>EvidenceCompare.lineExcerpt(f,idx):null,
        open:()=>openPage(f.doc,f.page,exact?f.id:undefined)};
    }
    function printed(row,value) {
      if (!row?.line || !row.native && row.native!==undefined) return null;
      const f=AcceptanceOpinion.observation(row,graph);
      return {value:value || row.quote,verbatim:!value || value===row.quote,place:'第 '+row.page+' 页 · 第 '+row.line+' 行',excerpt:f?.source_line?.rects?.length?()=>EvidenceCompare.lineExcerpt(f,idx):null,
        open:()=>openPage(row.doc,row.page,f?.id,f?null:row.line)};
    }
    const authority=one(rows,'authority'),signers=record.fields.map(id=>idx.facts.get(id));
    const signer=signers.length===1 && (signers[0].source_line?.text===signers[0].quote ||
      signers[0].status==='confirmed' && fieldReceiptOperation(signers[0],doc,idx.nodes.get(doc.id+'/p'+signers[0].page)))?signers[0]:null;
    const transfers=report.findings.filter(f=>f.rule==='H05' && f.stage?.clause_ref===phase.stage?.clause_ref &&
      f.payment_opinion?.release?.signature_records?.includes(record.id) &&
      PerformanceIndex.releaseProofs(f,report).some(p=>p.record.id===record.id));
    const payment=transfers.length===1?transfers[0]:null, timing=payment?.payment_opinion.release;
    const locations=proof.notes?.map(n=>({text:n.text,author:n.author,shortened:n.shortened,anchor:n.anchor?.selected,
      place:n.location?'第 '+n.location.page+' 页 · 第 '+n.location.line+' 行':'',
      open:n.location?()=>openPage(doc.id,n.location.page,undefined,n.location.line):null})) || [];
    const model={record,state:release.state,doc:{name:doc.name,hash:doc.sha256,original:workpaperSource(doc.id,'original')},
      page:{number:proof.page,open:()=>openPage(doc.id,proof.page),thumbnail:()=>EvidenceCompare.pageThumbnail({doc:doc.id,page:proof.page},idx)},
      flag:caption(release,rows),risk:release.signature_mismatch || ['signer_mismatch','reference_mismatch'].includes(release.state),
      digital:proof.signature,notes:locations,reviewCoverage:proof.word?.coverage,
      timing:timing?.written_timing,dates:{paid:timing?.paid_on,signed:timing?.signed_on},
      earlyPayment:payment?.status==='risk' && timing?.written_timing==='before',
      initial:['signer_mismatch','reference_mismatch'].includes(release.state)?'authority':'version',
      rows:{authority:printed(authority,release.required),signer:observation(signer) || printed(one(filed,'signature')),
        hold:notes.length===1?printed(notes[0]):null,original:observation(fact(graph,phase,release.original_ref)),
        receipt:observation(fact(graph,phase,release.receipt_ref)),date:observation(fact(graph,phase,release.date_ref)) || printed(one(filed,'date')),
        approval:printed(one(filed,'approval_date')),paid:payment && observation(fact(graph,payment,timing.paid_ref))}};
    const params=new URLSearchParams({rev:state.bundle.rev,view:'payment-release',stage:phase.id});
    model.permalink=Team.paperLink('固定链接',report.case_id,'release-download',params);
    model.permalink.setAttribute('aria-label','本版付款放行单核对固定链接');
    return ReleaseCard.render(model,'release-'+phase.id);
  }
  function reveal(overview,finding,report) {
    const proofs=finding && PerformanceIndex.releaseProofs(finding,report);
    if (!overview || proofs?.length!==1) return false;
    const phases=report.findings.filter(f=>f.rule==='H04' && f.stage?.clause_ref===finding.stage?.clause_ref &&
      f.payment_opinion?.release?.signature_records?.includes(proofs[0].record.id));
    if (phases.length!==1) return false;
    const choice=overview.querySelector('[data-phase-choice="'+CSS.escape(phases[0].id)+'"]');
    if (!choice) return false;
    choice.click();
    const phase=overview.querySelector('[data-phase-finding="'+CSS.escape(phases[0].id)+'"]');
    const card=phase?.querySelector('.release-card[data-release-record="'+CSS.escape(proofs[0].record.id)+'"]');
    if (!card) return false;
    phase.querySelector('.proof-mode[data-mode=opinion]').click();
    const tab=finding.rule==='H05' && card.querySelector('.release-tab[data-view=dates]') || card.querySelector('[role=tab][aria-selected=true]');
    tab.click();revealPaperTarget(tab);
    return true;
  }
  function locate(overview,params) {
    const bundle=state.bundle,valid=['stage','rev','view'].every(k=>params.getAll(k).length===1) && String(bundle.rev)===params.get('rev');
    const finding=valid && bundle.report.findings.find(f=>f.id===params.get('stage'));
    if (reveal(overview,finding,bundle.report)) return;
    const notice=el('p','本版所选检查尚无可定位的放行签署凭证。','note');
    notice.setAttribute('role','status');notice.tabIndex=-1;overview.prepend(notice);revealPaperTarget(notice);
  }
  function stops(phase,notes,graph) {
    const release=phase.payment_opinion?.release;
    if (!release || notes.length!==1) return [];
    const rows=sources(graph,phase), authority=one(rows,'authority');
    const kind={signer_mismatch:'signature',reference_mismatch:'receipt',future:'date'}[release.state];
    const entry=kind?one(rows,kind):release.state==='pending' && !one(rows,'date')?one(rows,'approval_date') || one(rows,'decision'):one(rows,'decision');
    const items=[{key:'hold',label:'暂缓',row:notes[0]}];
    if (authority) items.push({key:'authority',label:'权限',row:authority});
    if (entry) items.push({key:'release',label:'放行单',row:entry});
    return items;
  }
  return {fact,sources,one,caption,filedUnit,panel,reveal,locate,stops};
})();
