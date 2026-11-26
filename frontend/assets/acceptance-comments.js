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
  function resolve(report) {
    const graph=report?.graph, ledger=graph?.acceptance_word_reviews;
    const finding=report?.findings.find(f=>f.rule==='H02'), check=finding?.acceptance_comments;
    if (report?.policy?.acceptance_word_reviews!=='word-acceptance-comments-v1' || ledger?.format!==report.policy.acceptance_word_reviews ||
        !check || !['ok','risk','missing'].includes(check.status) || !check.documents?.length) return null;
    const index=graphIndex(graph), cited=new Set(traceReferences(graph,finding));
    if (!check.evidence.every(ref=>cited.has(ref))) return null;
    function edge(from,to,type,evidence) {
      return graph.edges.some(e=>e.from===from && e.to===to && e.type===type && listEqual(e.evidence,evidence));
    }
    function related(ref,units) {
      return report.findings.filter(f=>f.stage && ['H04','H05'].includes(f.rule) && f.scope.some(unit=>units.includes(unit)) &&
        traceReferences(graph,f).includes(ref) && traceReferences(graph,f).includes(f.stage.clause_ref))
        .map(f=>({id:f.id,name:f.stage.name,share:f.stage.share,kind:f.rule==='H05'?'payment':'condition',
          status:f.status,statusName:statusName(f.status),open:()=>revealPaperTarget(document.querySelector('[data-finding="'+CSS.escape(f.id)+'"]'))}));
    }
    const documents=[];
    for (const record of ledger.documents.filter(d=>check.documents.includes(d.id))) {
      const doc=index.documents.get(record.doc), node=index.nodes.get(record.id);
      if (!doc || !['.docx','.doc'].includes(doc.ext) || !digest(record.original_sha256) || doc.sha256!==record.original_sha256 ||
          node?.type!=='acceptance_word_review' || node.doc!==doc.id || !edge(doc.id,node.id,'word_review_source',[doc.id]) ||
          !cited.has(node.id) || !record.units.some(id=>finding.scope.includes(id))) return null;
      if (!['complete','partial','unreadable'].includes(record.coverage) || record.coverage!=='unreadable' &&
          (!digest(record.body_sha256) || !Number.isInteger(record.count) || record.count<record.notes.length)) return null;
      const notes=[];
      for (const note of record.notes.filter(n=>check.notes.includes(n.id))) {
        const comment=index.nodes.get(note.id);
        if (comment?.doc!==doc.id || comment?.type!=='acceptance_word_comment' || !cited.has(note.id) ||
            !edge(node.id,note.id,'word_review_comment',[doc.id,node.id]) || !digest(record.part_sha256) ||
            !validAnchor(note.anchor) || typeof note.text!=='string') return null;
        const entry={...note,related:related(note.id,record.units)};
        const loc=note.location;
        if (loc) {
          const pageId=doc.id+'/p'+loc.page, page=index.nodes.get(pageId);
          if (!note.anchor || !Number.isInteger(loc.line) || loc.line<1 || page?.type!=='page' || page.layer!=='text' ||
              !digest(loc.page_sha256) || page.sha256!==loc.page_sha256 || !digest(loc.text_sha256) || page.text_sha256!==loc.text_sha256 ||
              !report.calls.pages.some(p=>p.doc===doc.id && p.page===loc.page && p.page_sha256===page.sha256) ||
              !cited.has(pageId) || !edge(pageId,note.id,'word_review_anchor',[pageId,...loc.facts])) return null;
          const facts=loc.facts.map(id=>index.facts.get(id));
          if (!facts.every(f=>f?.doc===doc.id && f.page===loc.page && f.page_sha256===page.sha256 && f.source_sha256===doc.sha256 &&
              f.quote===note.anchor.quote && f.source_line?.number===loc.line && f.source_line.text===note.anchor.quote &&
              f.source_line.rects?.length && cited.has(f.id))) return null;
          const fact=facts.find(f=>f.field==='acceptance_result') || facts[0];
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
    return {id:'acceptance-comments',status:check.status,documents};
  }
  function current(report) {
    if (!report) return null;
    const bundle=state.bundle?.report===report?state.bundle:null;
    if (bundle && cache.has(bundle)) return cache.get(bundle);
    const model=resolve(report);
    if (bundle) cache.set(bundle,model);
    return model;
  }
  function panel(report) {
    const model=current(report);
    if (!model) return null;
    const request=canReviewCurrentPaper() && model.status!=='ok' ? (doc,note)=>{
      const place=note?.location?'第 '+note.location.page+' 页第 '+note.location.line+' 行':'验收结论';
      draftSupplement('请核实《'+doc.name+'》'+place+'的审阅意见及正式终验范围，并补交技术验收和最终签认版本。');
    }:null;
    return WordCommentCard.render({...model,request});
  }
  function show(ref) {
    const target=document.getElementById('acceptance-comments');
    if (!target) return;
    revealPaperTarget(target);
    target.dispatchEvent(new CustomEvent('word-review-select',{detail:ref}));
  }
  function phaseLink(phase,model) {
    const note=model?.documents.flatMap(d=>d.notes).find(n=>n.related.some(f=>f.id===phase.id));
    if (!note) return null;
    const jump=action('核对此期验收批注',()=>show(note.id),'word-phase-link');
    jump.prepend(glyph('journal-text'));
    jump.dataset.commentRef=note.id;
    jump.setAttribute('aria-controls',model.id);
    return jump;
  }
  function citation(ref) {
    const model=current(state.bundle?.report);
    const doc=model?.documents.find(d=>d.id===ref || d.notes.some(n=>n.id===ref));
    if (!doc) return el('span','Word 验收批注来源待核','small');
    return action(doc.name+(doc.id===ref?' · 审阅记录':' · 原文批注'),()=>show(ref),'ref');
  }
  return {current,resolve,panel,citation,phaseLink};
})();
