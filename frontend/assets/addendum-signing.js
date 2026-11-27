const AddendumSigning = (() => {
  function jump(proof) {
    const button=action('',()=>{
      const target=document.getElementById('addendum-signing');
      if (!target || !PerformanceIndex.addendumEvidence(state.bundle.report).includes(proof)) return;
      target.hidden=false;
      target.dispatchEvent(new CustomEvent('select-agreement',{detail:proof.record.id}));
      revealPaperTarget(target);
    },'addendum-jump');
    button.append(glyph('file-earmark-text'),el('strong','补充协议签署'),el('span',proof.label),glyph('chevron-down'));
    button.dataset.proof=proof.record.id; return button;
  }
  function citation(ref,finding) {
    const proof=PerformanceIndex.addendumEvidence(state.bundle.report).find(p=>p.record.id===ref && (!finding || p.related.includes(finding)));
    return proof?jump(proof):el('span','补充协议签署来源待核','small');
  }
  function panel(report) {
    const proofs=PerformanceIndex.addendumEvidence(report);
    if (!proofs.length) return null;
    const bundle=state.bundle, workspace=Team.current?.id || null, index=graphIndex(report.graph);
    function current() {
      const route=Team.route(), pins=route.params.getAll('rev');
      return state.bundle===bundle && state.detail?.id===report.case_id && state.detail.workspace===(workspace || 'local') &&
        route.id===workspace && route.page==='case/'+report.case_id && (!pins.length || pins.length===1 && Number(pins[0])===bundle.rev) &&
        (!state.pinned || state.pinned===bundle.rev);
    }
    function model(proof) {
      const {record,doc}=proof, original=workpaperSource(doc.id,'original');
      const open=f=>()=>{if (current()) openPage(doc.id,f.page,f.id);};
      const rows=proof.lines.filter(r=>record.fields.includes(r.fact.id)).map(({fact,line})=>({
        side:fact.field==='buyer_signature'?'甲方签章栏':'乙方签章栏',page:fact.page,line,quote:fact.source_line.text,
        excerpt:async()=>current() && EvidenceCompare.lineExcerpt(fact,index),open:open(fact),
      }));
      const terms=[];
      for (const [before,after] of [['previous_criterion','revised_criterion'],['previous_quantity','revised_quantity'],['previous_payment_stage','revised_payment_stage']]) {
        const first=proof.lines.filter(r=>r.fact.field===before), last=proof.lines.filter(r=>r.fact.field===after);
        if (first.length!==1 || last.length!==1 || !proof.bindings.some(b=>b.lines.some(r=>r.fact.id===first[0].fact.id) &&
            b.lines.some(r=>r.fact.id===last[0].fact.id))) continue;
        for (const [label,{fact}] of [['变更前',first[0]],['协议拟用',last[0]]]) {
          const quote=fact.source_line.text, suffix=quote.replace(/^[^:：]+[:：]\s*/u,'');
          const value=suffix.normalize('NFKC')===String(fact.value).normalize('NFKC')?suffix:quote;
          terms.push({label,value,quote,page:fact.page,line:fact.source_line.number,
            excerpt:async()=>current() && EvidenceCompare.lineExcerpt(fact,index),control:()=>{
            const button=action('',open(fact)); button.dataset.fact=fact.id;
            button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-controls','page-dialog');return button;
          }});
        }
      }
      const pdf={record:proof.signature,state:record.state,filename:doc.name,original,originalLabel:'下载原件',rows,
        thumbnail:workpaperSource(doc.id,'pages/'+proof.page),page:()=>{if(current()) openPage(doc.id,proof.page);},
        request:canReviewCurrentPaper()?text=>{if(current() && canReviewCurrentPaper()) draftSupplement(doc.name+'。'+text);}:null};
      const phases=proof.related.filter(f=>f.stage && ['H04','H05'].includes(f.rule));
      const related=phases.length && (()=>{
        const box=el('div','','pdf-related'); box.append(el('small','引用此协议'));
        for (const f of phases) {
          const control=action(f.stage.name+(f.rule==='H05'?'实付':'条件'),()=>{
            if (current()) document.querySelector('[data-audit-scope="payment"]')?.dispatchEvent(new CustomEvent('open-payment-stage',{detail:f.id}));
          },'word-phase');
          control.dataset.findingRef=f.id; box.append(control);
        }
        return box;
      });
      const ambiguous=proofs.some(p=>p.doc.id!==doc.id && p.doc.name===doc.name);
      const filename=ambiguous?doc.name+' · 资料 '+doc.id.toUpperCase():doc.name;
      const label=record.unit===doc.id?filename:filename+' · 第 '+proof.page+' 页';
      const permalink=()=>{
        const params=new URLSearchParams({rev:String(bundle.rev),view:'addendum-signing',agreement:record.unit});
        const link=Team.paperLink('固定链接',report.case_id,'addendum-permalink',params);
        link.setAttribute('aria-label','固定链接，'+label+'，底稿 R'+bundle.rev); return link;
      };
      return {key:record.id,label,pdf,terms,related,permalink};
    }
    return AddendumCard.render(proofs.map(model),'addendum-signing');
  }
  function locate(container,params) {
    const target=container.querySelector('#addendum-signing');
    const units=params.getAll('agreement'), proofs=PerformanceIndex.addendumEvidence(state.bundle.report);
    const revisions=params.getAll('rev'), written=revisions.length===1 && revisions[0]===String(state.bundle.rev) && params.getAll('view').length===1;
    if (target && written && !units.length) { revealPaperTarget(target); return; }
    const selected=units.length===1 && proofs.find(proof=>proof.record.unit===units[0]);
    if (target && written && selected) {
      target.dispatchEvent(new CustomEvent('select-agreement',{detail:selected.record.id})); revealPaperTarget(target); return;
    }
    if (target) target.hidden=true;
    const detail=written?(target?'本版没有所选补充协议的签署凭证。':'本版未收录补充协议 PDF 签署凭证。'):'请选择一个明确的底稿版本。';
    const message=el('p',detail,'note');
    message.setAttribute('role','status'); message.tabIndex=-1;
    container.prepend(message); revealPaperTarget(message);
  }
  return {panel,jump,citation,locate};
})();
