// Use the issued original-line ledger even when extraction produced no observation for a row.
const AcceptanceOpinion = (() => {
  const stanceName={hold:'暂缓',assent:'同意',unclear:'待核',qualification:'附注'};

  function rows(graph,finding) {
    const stored=graph.acceptance_reservation_sources?.payment_opinions;
    if (!stored?.length) return [];
    const index=graphIndex(graph);
    if (!index.opinionSources) {
      const edges=graph.edges.filter(e=>e.type==='acceptance_payment_opinion');
      index.opinionSources=stored.flatMap(row=>{
        const page=row.doc+'/p'+row.page;
        const edge=edges.find(e=>e.from===row.unit && e.to===page && e.line===row.line && e.evidence.includes(page) &&
          (row.line || row.facts.some(ref=>e.evidence.includes(ref))));
        return edge?[{...row,facts:row.facts.filter(ref=>edge.evidence.includes(ref))}]:[];
      });
    }
    const ledger=index.opinionSources;
    if (!finding) return ledger;
    const opinion=finding.payment_opinion;
    if (!opinion) return [];
    const supported=index.supports.get('finding/'+finding.id);
    const cited=ref=>supported?.has(ref) && opinion.evidence.includes(ref) && finding.evidence.includes(ref);
    const matches=opinion.notes.flatMap(note=>{
      if (!cited(note.doc+'/p'+note.page)) return [];
      const row=ledger.find(r=>r.doc===note.doc && r.unit===note.unit && r.page===note.page &&
        r.line===note.line && r.quote===note.quote && r.stance===note.stance);
      return row?[{...row,scope:note.scope,facts:row.facts.filter(id=>note.facts.includes(id) && cited(id))}]:[];
    });
    return matches.length===opinion.notes.length?matches:[];
  }

  function observation(row,graph) {
    const {facts}=graphIndex(graph);
    return row.facts.map(id=>facts.get(id)).find(f=>f && f.doc===row.doc && f.page===row.page &&
      (f.unit || f.doc)===row.unit && f.quote===row.quote && (row.line
        ? f.source_line?.number===row.line && f.source_line.text===row.quote && f.source_line.rects?.length
        : !f.source_line?.rects?.length || f.source_line.text===row.quote));
  }

  function source(row,graph) {
    const fact=observation(row,graph);
    if (!row.line && !fact) {
      const name=graphIndex(graph).documents.get(row.doc)?.name || '原件';
      const page=action(name+' · 第 '+row.page+' 页 · 核对整页影像',()=>openPage(row.doc,row.page),'ref');
      const excerpt=box('batch-source',page); excerpt.dataset.opinionOriginal=row.doc+'/p'+row.page;
      return excerpt;
    }
    const excerpt=reservationSource({...row,facts:fact?[fact.id]:[]},graph);
    excerpt.dataset.opinionOriginal=row.doc+'/p'+row.page+(row.line?'/l'+row.line:'');
    return excerpt;
  }

  function caption(opinion) {
    if (opinion.state==='conflict') return '付款意见相反';
    if (opinion.state==='unresolved') return '归属或范围待核';
    if (opinion.state==='assent') return '原件载明同意';
    return opinion.notes.some(n=>n.scope==='all')?'全部期款暂缓':'本期暂缓';
  }

  function printedQuality(accepted,notes,graph) {
    const index=graphIndex(graph), units=new Set(notes.map(n=>n.unit));
    const evidence=traceReferences(graph,accepted).map(id=>index.facts.get(id))
      .filter(f=>f && units.has(f.unit || f.doc) && ['anchored','confirmed'].includes(f.status) &&
        f.source_line?.rects?.length && f.source_line.text===f.quote);
    const measured=accepted.status==='issue' && /实测值超出/.test(accepted.detail);
    const candidates=evidence.filter(f=>f.field===(measured?'measured_result':'acceptance_result'));
    return candidates.length===1 ? candidates[0] : null;
  }

  function panel(phase,accepted,notes,graph) {
    const opinion=phase.payment_opinion;
    const root=box('proof-opinion');
    root.dataset.paymentOpinionState=opinion.state;
    const index=graphIndex(graph);
    function paper(row,fact) {
      const excerpt=source(row,graph), quote=excerpt.querySelector('q'), button=excerpt.querySelector('button');
      if (!quote) return excerpt;
      const caption=el('span','','opinion-location');
      caption.append(glyph('file-earmark-text'),el('span',button.textContent),glyph('arrows-angle-expand'));
      const strip=el('span','','opinion-strip'); strip.append(quote);
      button.setAttribute('aria-label','查看原件，'+row.quote+'，'+button.textContent);
      button.replaceChildren(strip,caption);
      if (row.line && fact?.source_line?.rects?.length && row.quote.length<=24) button.dataset.excerptFact=fact.id;
      return excerpt;
    }
    async function loadExcerpt(button) {
      const strip=button.querySelector('.opinion-strip');
      if (strip.dataset.loading || strip.querySelector('canvas')) return;
      strip.dataset.loading='true';
      try {
        const canvas=await EvidenceCompare.lineExcerpt(index.facts.get(button.dataset.excerptFact),index);
        if (canvas) { strip.append(canvas); strip.querySelector('q').classList.add('visually-hidden'); }
      } catch { /* Keep the archived quotation and the original-page action available. */ }
      finally { delete strip.dataset.loading; }
    }
    function show() {
      if (!root.isConnected || !root.getClientRects().length) return;
      for (const button of root.querySelectorAll('[data-excerpt-fact]')) loadExcerpt(button);
    }
    root.addEventListener('show-opinion',()=>requestAnimationFrame(show));
    if (accepted) {
      const head=box('opinion-card-head',glyph('clipboard-check'),el('h4','交付验收'),tag(accepted.status));
      const card=box('opinion-quality',head);
      const fact=printedQuality(accepted,notes,graph);
      if (fact?.field==='measured_result') card.dataset.measuredRef=fact.id;
      if (fact) card.append(paper({unit:fact.unit || fact.doc,doc:fact.doc,page:fact.page,line:fact.source_line.number,quote:fact.quote,facts:[fact.id]},fact));
      else card.append(action('查看验收核对项',()=>revealPaperTarget(document.querySelector('[data-finding="'+CSS.escape(accepted.id)+'"]')),'ref'));
      root.append(card);
    }
    const stops=ReleaseEvidence.stops(phase,notes,graph), release=opinion.release;
    if (release) root.dataset.releaseState=release.state;
    const head=box('opinion-card-head',glyph('journal-text'),el('h4',release?'暂缓与放行':'付款意见'));
    const card=box('opinion-record',head), excerpt=box('opinion-excerpt');
    const choicesForView=stops.length?stops.map(s=>s.row):notes;
    const buttons=[];
    function select(i) {
      const row=choicesForView[i];
      excerpt.replaceChildren(paper(row,observation(row,graph))); show();
      for (const [n,btn] of buttons.entries()) {
        btn.setAttribute('aria-pressed',String(n===i)); btn.tabIndex=n===i?0:-1;
      }
    }
    if ((stops.length>1 && stops.length<=3) || !stops.length && notes.length===2) {
      const choices=box('opinion-choices');
      choices.setAttribute('role','group'); choices.setAttribute('aria-label',stops.length?'核对暂缓、放行权限与签发原件':'选择付款意见原行');
      const total=choicesForView.length;
      for (const [i,row] of choicesForView.entries()) {
        const label=stops.length?stops[i].label:row.stance===notes[1-i].stance?'原文 '+(i+1):stanceName[row.stance];
        const btn=action(label,()=>select(i),'opinion-choice');
        if (stops.length) btn.dataset.releaseStage=stops[i].key;
        else btn.dataset.opinionChoice=row.stance;
        btn.addEventListener('keydown',e=>{
          const next={ArrowLeft:(i+total-1)%total,ArrowRight:(i+1)%total,Home:0,End:total-1}[e.key];
          if (next===undefined) return;
          e.preventDefault(); select(next); buttons[next].focus();
        });
        buttons.push(btn); choices.append(btn);
      }
      head.append(choices);
    } else if (notes.length>2) {
      const choices=el('select','','opinion-select');
      choices.setAttribute('aria-label','选择付款意见原行');
      for (const [i,row] of notes.entries()) choices.add(new Option((i+1)+' · '+stanceName[row.stance],i));
      choices.addEventListener('change',()=>select(choices.selectedIndex)); head.append(choices);
    }
    if (choicesForView.length>1) excerpt.setAttribute('aria-live','polite');
    select(stops.length?stops.length-1:0); card.append(excerpt); root.append(card);
    return root;
  }
  return {rows,observation,source,caption,panel};
})();
