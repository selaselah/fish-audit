const AcceptanceComments = (() => {
  const cache=new WeakMap();
  const digest=value=>typeof value==='string' && /^[a-f0-9]{64}$/.test(value);
  const listEqual=(a,b)=>Array.isArray(a) && a.length===b.length && a.every((value,i)=>value===b[i]);
  function validAnchor(a) {
    if (a===null) return true;
    if (!a || typeof a.quote!=='string' || !Number.isInteger(a.start) || !Number.isInteger(a.end) ||
        !Number.isInteger(a.paragraph) || a.paragraph<1 || a.start<0 || a.start>=a.end) return false;
    const letters=Array.from(a.quote);
    return a.end<=letters.length && letters.slice(a.start,a.end).join('')===a.selected;
  }
  const printedKey=text=>text.replace(/([\u3400-\u9fff]) (?=[0-9])/gu,'$1');
  function resolve(report,role='acceptance') {
    const contract=role==='contract', key=role+'_word_reviews', relation=contract?'contract_word_review':'word_review';
    const format=contract?'word-contract-payment-comments-v1':'word-acceptance-comments-v1';
    const graph=report?.graph, ledger=graph?.[key];
    const finding=report?.findings.find(f=>f.rule===(contract?'H03':'H02')), check=finding?.[role+'_comments'];
    if (report?.policy?.[key]!==format || ledger?.format!==format || !Array.isArray(ledger.documents) ||
        !check || !['ok','risk','missing'].includes(check.status) ||
        ![check.documents,check.notes,check.evidence].every(Array.isArray) || !check.documents.length) return null;
    const index=graphIndex(graph), cited=new Set(traceReferences(graph,finding));
    if (!check.evidence.every(ref=>cited.has(ref))) return null;
    function edge(from,to,type,evidence) {
      return graph.edges.some(e=>e.from===from && e.to===to && e.type===type && listEqual(e.evidence,evidence));
    }
    function related(ref,units) {
      return report.findings.filter(f=>f.stage && (contract?['H04','H05','H06']:['H04','H05']).includes(f.rule) && f.scope.some(unit=>units.includes(unit)) &&
        traceReferences(graph,f).includes(ref) && traceReferences(graph,f).includes(f.stage.clause_ref))
        .map(f=>({id:f.id,name:f.stage.name,share:f.stage.share,clause:f.stage.clause_ref,kind:{H04:'condition',H05:'payment',H06:'total'}[f.rule],
          status:f.status,statusName:statusName(f.status),open:()=>revealPaperTarget(document.querySelector('[data-finding="'+CSS.escape(f.id)+'"]'))}));
    }
    const documents=[];
    for (const record of ledger.documents.filter(d=>check.documents.includes(d.id))) {
      const doc=index.documents.get(record.doc), node=index.nodes.get(record.id);
      if (!doc || !['.docx','.doc'].includes(doc.ext) || !digest(record.original_sha256) || doc.sha256!==record.original_sha256 ||
          node?.type!==role+'_word_review' || node.doc!==doc.id || !edge(doc.id,node.id,relation+'_source',[doc.id]) ||
          !cited.has(node.id) || !record.units.some(id=>finding.scope.includes(id))) return null;
      if (!Array.isArray(record.notes) || !['complete','partial','unreadable'].includes(record.coverage) || record.coverage!=='unreadable' &&
          (!digest(record.body_sha256) || !Number.isInteger(record.count) || record.count<record.notes.length)) return null;
      const notes=[];
      for (const note of record.notes.filter(n=>check.notes.includes(n.id))) {
        const comment=index.nodes.get(note.id);
        if (comment?.doc!==doc.id || comment?.type!==role+'_word_comment' || !cited.has(note.id) ||
            !edge(node.id,note.id,relation+'_comment',[doc.id,node.id]) || !digest(record.part_sha256) ||
            !validAnchor(note.anchor) || typeof note.text!=='string') return null;
        const entry={...note,related:related(note.id,record.units)};
        const loc=note.location;
        if (loc) {
          const pageId=doc.id+'/p'+loc.page, page=index.nodes.get(pageId);
          if (!note.anchor || !Array.isArray(loc.facts) || !Number.isInteger(loc.line) || loc.line<1 || page?.type!=='page' || page.layer!=='text' ||
              !digest(loc.page_sha256) || page.sha256!==loc.page_sha256 || !digest(loc.text_sha256) || page.text_sha256!==loc.text_sha256 ||
              !report.calls.pages.some(p=>p.doc===doc.id && p.page===loc.page && p.page_sha256===page.sha256) ||
              !cited.has(pageId) || !edge(pageId,note.id,relation+'_anchor',[pageId,...loc.facts])) return null;
          const printed=contract?loc.printed:note.anchor.quote;
          if (typeof printed!=='string' || contract && printedKey(printed)!==printedKey(note.anchor.quote)) return null;
          const facts=loc.facts.map(id=>index.facts.get(id));
          if (!facts.every(f=>f?.doc===doc.id && f.page===loc.page && f.page_sha256===page.sha256 && f.source_sha256===doc.sha256 &&
              typeof f.quote==='string' && (contract?printedKey(f.quote)===printedKey(printed):f.quote===printed) &&
              f.source_line?.number===loc.line && f.source_line.text===printed &&
              f.source_line.rects?.length && cited.has(f.id))) return null;
          const fact=facts.find(f=>f.field===(contract?'payment_stage':'acceptance_result')) || facts[0];
          if (fact) {
            entry.open=()=>openPage(doc.id,loc.page,fact.id);
            entry.rects=fact.source_line.rects;
            entry.thumbnail=workpaperSource(doc.id,'pages/'+loc.page);
          }
        }
        notes.push(entry);
      }
      documents.push({...record,name:doc.name,notes,original:workpaperSource(doc.id,'original'),
        related:record.coverage==='complete'?[]:related(record.id,record.units)});
    }
    if (documents.length!==check.documents.length || documents.flatMap(d=>d.notes).length!==check.notes.length) return null;
    const model={id:role+'-comments',role,status:check.status,documents};
    if (!contract) return model;
    if (typeof check.whole!=='boolean' || !check.clauses || !listEqual(Object.keys(check.clauses).sort(),[...check.notes].sort())) return null;
    for (const note of documents.flatMap(d=>d.notes)) {
      const target=check.clauses[note.id];
      if (target===null && !check.whole) return null;
      if (target!==null && (!note.location?.facts.includes(target) || index.facts.get(target)?.field!=='payment_stage' ||
          !note.related.some(f=>f.kind==='condition' && f.clause===target) || note.related.some(f=>f.clause!==target))) return null;
    }
    if (check.whole || documents.length!==1 || documents[0].coverage!=='complete') return model;
    const doc=documents[0], stages=[];
    for (const phase of report.findings.filter(f=>f.rule==='H04' && f.stage)) {
      const stage=phase.stage, fact=index.facts.get(stage.clause_ref), loc=fact?.source_line;
      const page=fact && index.nodes.get(doc.doc+'/p'+fact.page);
      if (fact?.doc!==doc.doc || fact.field!=='payment_stage' || !['anchored','confirmed'].includes(fact.status) ||
          !loc?.rects?.length || !loc.text || !cited.has(fact.id) || !traceReferences(graph,phase).includes(fact.id) ||
          fact.source_sha256!==doc.original_sha256 || page?.sha256!==fact.page_sha256 || !digest(fact.page_sha256) ||
          !report.calls.pages.some(p=>p.doc===doc.doc && p.page===fact.page && p.page_sha256===page.sha256)) return model;
      stages.push({ref:fact.id,name:stage.name,share:stage.share,quote:loc.text,page:fact.page,line:loc.number,
        notes:doc.notes.filter(n=>check.clauses[n.id]===fact.id).map(n=>n.id),open:()=>openPage(doc.doc,fact.page,fact.id)});
    }
    if (stages.length && new Set(stages.map(s=>s.ref)).size===stages.length) model.stages=stages;
    return model;
  }
  function current(report,role='acceptance') {
    if (!report) return null;
    const bundle=state.bundle?.report===report?state.bundle:null;
    if (bundle && !cache.has(bundle)) cache.set(bundle,new Map());
    const models=bundle && cache.get(bundle);
    if (models?.has(role)) return models.get(role);
    const model=resolve(report,role);
    models?.set(role,model);
    return model;
  }
  function panel(report,role='acceptance') {
    const model=current(report,role);
    if (!model) return null;
    const request=canReviewCurrentPaper() && model.status!=='ok' ? (doc,note)=>{
      const place=note?.location?'第 '+note.location.page+' 页第 '+note.location.line+' 行':'的审阅记录';
      draftSupplement('请核实《'+doc.name+'》'+place+(role==='contract'?'所列付款前提的修订建议，并补交双方确认的条款、适用期次及生效时间。':'的审阅意见及正式终验范围，并补交技术验收和最终签认版本。'));
    }:null;
    return WordCommentCard.panel({...model,request,externalStages:role==='contract'});
  }
  function show(ref,id) {
    const target=document.getElementById(id);
    if (!target) return;
    revealPaperTarget(target);
    target.dispatchEvent(new CustomEvent('word-review-select',{detail:ref}));
  }
  function phaseLink(phase,model) {
    const note=model?.documents.flatMap(d=>d.notes).find(n=>n.related.some(f=>f.id===phase.id));
    if (!note) return null;
    const jump=action(model.role==='contract'?'核对此期合同批注':'核对此期验收批注',()=>show(note.id,model.id),'word-phase-link');
    jump.prepend(glyph('journal-text'));
    jump.dataset.commentRef=note.id;
    jump.setAttribute('aria-controls',model.id);
    return jump;
  }
  function citation(ref,role='acceptance') {
    const model=current(state.bundle?.report,role);
    const doc=model?.documents.find(d=>d.id===ref || d.notes.some(n=>n.id===ref));
    if (!doc) return el('span','Word 批注来源待核','small');
    return action(doc.name+(doc.id===ref?' · 审阅记录':' · 原文批注'),()=>show(ref,model.id),'ref');
  }
  return {current,resolve,panel,citation,phaseLink,validAnchor,printedKey};
})();
