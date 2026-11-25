const ReinspectionTrail = (() => {
  const roles = [
    {key:'original', title:'原验收', heading:'acceptance', fields:['acceptance_result','acceptance_exception','measured_result','defect_number','acceptance_signer']},
    {key:'repair', title:'整改', heading:'remediation', fields:['repair_action','repair_result','repair_subject','repair_number','repair_signer','defect_number']},
    {key:'final', title:'复验', heading:'reinspection', fields:['acceptance_result','defect_closure','measured_result','defect_number','acceptance_signer']},
  ];
  const notes = {open:'待整改', conditional:'附条件签认', unreviewed:'原文待核', reported_closed:'关闭依据待核', matched:'与整改记录相符', clear:'原件记载为无'};
  const priority = ['open','conditional','reported_closed','unreviewed','matched','clear'];

  function originalCard(quote, location, open, warning) {
    const card = action('',open,'trail-source');
    const split = quote.search(/[:：]/u);
    const pair = split > 0 && split < 18;
    const label = pair ? quote.slice(0,split) : '原文';
    const value = pair ? quote.slice(split+1).trim() : quote;
    card.append(el('span',warning || label,'trail-field'), el('strong',value || quote), box('trail-location',glyph('file-earmark-text'),el('span',location)));
    if (warning) card.dataset.attention = 'true';
    card.title=quote;
    card.append(el('span','打开原件','visually-hidden'));
    return card;
  }

  function sourceFacts(step, fields, index, supported) {
    return step.evidence.map(id=>index.facts.get(id)).filter(f=>{
      if (!f || !fields.includes(f.field) || !supported.has(f.id) || (f.unit || f.doc)!==step.unit) return false;
      const page=index.nodes.get(f.doc+'/p'+f.page), doc=index.documents.get(f.doc);
      return page?.type==='page' && doc && f.source_sha256===doc.sha256 && f.page_sha256===page.sha256;
    }).sort((a,b)=>fields.indexOf(a.field)-fields.indexOf(b.field));
  }

  function verifiedRows(step, check, graph, supported) {
    const index=graphIndex(graph);
    const ledger=graph.acceptance_reservation_sources?.final_register;
    return (check?.lines || []).filter(r=>r.unit===step.unit).map(row=>{
      const page=row.doc+'/p'+row.page;
      const same=r=>r.unit===step.unit && r.doc===row.doc && r.page===row.page && r.line===row.line && r.quote===row.quote &&
        r.facts.length===row.facts.length && r.facts.every((id,i)=>row.facts[i]===id);
      const printed=ledger?.lines.find(same);
      const validKind=printed && (printed.kind===row.kind || printed.kind==='reported_closed' && row.kind==='matched');
      const edge=graph.edges.some(e=>e.type==='reinspection_register_line' && e.from===step.unit && e.to===page &&
        e.line===row.line && e.quote===row.quote && e.kind===printed?.kind && e.evidence[0]===page &&
        e.evidence.length===1+row.facts.length && row.facts.every((id,i)=>e.evidence[i+1]===id));
      const doc=index.documents.get(row.doc), node=index.nodes.get(page);
      const bound=validKind && edge && node?.type==='page' && doc && supported.has(page) &&
        row.facts.every(id=>{
          const f=index.facts.get(id);
          return supported.has(id) && f?.doc===row.doc && f.page===row.page && (f.unit || f.doc)===step.unit &&
            f.source_sha256===doc.sha256 && f.page_sha256===node.sha256;
        });
      return {row,bound};
    }).sort((a,b)=>priority.indexOf(a.row.kind)-priority.indexOf(b.row.kind));
  }

  function pageReferences(finding,graph,doc,page) {
    const chain=finding?.reinspection;
    if (!chain?.register) return [];
    const supported=new Set(traceReferences(graph,finding)), index=graphIndex(graph);
    return chain.steps.filter(s=>s.role==='final').flatMap(step=>verifiedRows(step,chain.register,graph,supported))
      .filter(({row,bound})=>bound && row.doc===doc && row.page===page && row.line).map(({row})=>{
        const f=row.facts.map(id=>index.facts.get(id)).find(f=>f?.quote===row.quote &&
          f.source_line?.text===row.quote && f.source_line.number===row.line);
        return {ref:'register-line/'+doc+'/p'+page+'/l'+row.line, label:'复验附注', quote:row.quote,
          option:'第 '+row.line+' 行 · '+notes[row.kind], rawLine:row.line, quality:'register_reference', rects:f?.source_line.rects || []};
      });
  }

  function phaseLink(finding,phase,graph) {
    const chain=finding.reinspection;
    if (!chain.register || chain.register.status==='ok' || phase.status==='ok') return null;
    const proof=new Set(traceReferences(graph,phase)), supported=new Set(traceReferences(graph,finding));
    const held=chain.steps.filter(s=>s.role==='final' && phase.scope.includes(s.unit))
      .flatMap(step=>verifiedRows(step,chain.register,graph,supported)).filter(({bound,row})=>bound &&
        !['clear','matched'].includes(row.kind) && proof.has(row.doc+'/p'+row.page) && row.facts.every(ref=>proof.has(ref)));
    if (!held.length) return null;
    const button=action('核对复验附注',()=>{
      if (held.length===1) {
        const {row}=held[0];
        openPage(row.doc,row.page,row.line?null:row.facts[0],row.line);
      } else {
        revealPaperTarget(document.getElementById('equipment-reinspection-trail'));
        document.getElementById('trail-tab-final').click();
        document.querySelectorAll('#trail-view-final details').forEach(d=>{d.open=true;});
      }
    },'compare-jump');
    button.dataset.registerPhase=phase.id;
    return button;
  }

  function repairNotes(step,graph,supported) {
    const check=step.completion;
    if (!check || check.status==='ok') return [];
    const index=graphIndex(graph);
    const rows=check.lines.filter(s=>['qualification','unreviewed'].includes(s.kind) || s.kind==='date' && !check.date);
    return rows.map(row=>{
      const page=row.doc+'/p'+row.page;
      const printed=graph.repair_completion_sources?.lines.find(s=>s.unit===step.unit && s.doc===row.doc &&
        s.page===row.page && s.line===row.line && s.kind===row.kind && s.quote===row.quote &&
        s.facts.length===row.facts.length && s.facts.every((ref,i)=>row.facts[i]===ref));
      if (!printed || !supported.has(page) || !row.facts.every(ref=>supported.has(ref)) ||
          !graph.edges.some(e=>e.type==='repair_completion_basis' && e.from===step.unit && e.to===page && e.line===row.line && e.kind===row.kind))
        return el('span','整改依据的原件关系待核','trail-empty');
      const fact=row.facts.map(id=>index.facts.get(id)).find(f=>f?.doc===row.doc && f.page===row.page && f.quote===row.quote &&
        (f.unit || f.doc)===step.unit && f.source_sha256===index.documents.get(row.doc)?.sha256 && f.page_sha256===index.nodes.get(page)?.sha256 &&
        (!row.line || f.source_line?.number===row.line && f.source_line.text===row.quote));
      if (!fact && !row.line) return el('span','整改影像引文待核','trail-empty');
      const location='第 '+row.page+' 页'+(row.line?' '+row.line+' 行':' · 读图');
      const card=originalCard(row.quote,location,()=>openPage(row.doc,row.page,fact?.id,fact?null:row.line),
        row.kind==='date'?'完成日期待核':'整改附注待核');
      card.dataset.repairNote=row.kind;
      return card;
    });
  }

  function scene(role, steps, finding, graph, supported) {
    const index=graphIndex(graph);
    const view=el('div','','trail-view');
    view.dataset.reinspectionRole=role.key;
    const check=finding.reinspection.register;
    if (!steps.length) {
      view.append(el('strong','缺少可归属的'+role.title+'资料','trail-empty'));
      for (const gap of graph.gaps.filter(g=>g.quality==='uncovered_title' && g.title_hint===role.heading)) {
        view.append(box('reinspection-line',el('span',gap.quote),
          action('核对原页第 '+gap.line+' 行',()=>openPage(gap.doc,gap.page,null,gap.line),'ref')));
      }
    }
    for (const step of steps) {
      const facts=sourceFacts(step,role.fields,index,supported);
      const cards=[];
      const annotations=role.key==='final' ? verifiedRows(step,check,graph,supported) : [];
      const lineCards=annotations.map(({row,bound})=>{
        if (!bound) return el('span','该行的原件关系待核','trail-empty');
        const where='第 '+row.page+' 页'+(row.line?' '+row.line+' 行':' · 读图');
        const card=originalCard(row.quote,where,()=>openPage(row.doc,row.page,row.line?null:row.facts[0],row.line),
          ['clear','matched'].includes(row.kind)?null:notes[row.kind]);
        card.dataset.registerKind=row.kind;
        card.dataset.registerLine=row.line ?? '';
        return card;
      });
      const factCards=facts.map(f=>{
        const loc=f.source_line;
        const where='第 '+f.page+' 页'+(loc?.number?' '+loc.number+' 行':' · 读图')+
          (['anchored','confirmed'].includes(f.status)?'':' · '+statusName(f.status));
        const card=originalCard(f.quote,where,()=>openPage(f.doc,f.page,f.id));
        card.dataset.citedFact=f.id;
        return card;
      });
      if (factCards.length) cards.push(factCards.shift());
      cards.push(...lineCards,...(role.key==='repair'?repairNotes(step,graph,supported):[]),...factCards);
      const doc=index.nodes.get(step.unit);
      const header=box('trail-document',glyph('journal-text'),el('strong',doc?.label || role.title+'原件'));
      if (steps.length>1) header.append(el('span',step.date || '日期待核'));
      const outcomes=facts.filter(f=>f.field==='acceptance_result' && f.source_line?.rects?.length);
      const outcome=outcomes.length===1?outcomes[0]:null;
      const paired=annotations.find(({row,bound})=>bound && row.line && row.doc===outcome?.doc && row.page===outcome.page &&
        row.line!==outcome.source_line.number && !['clear','matched'].includes(row.kind));
      if (paired) {
        const note=paired.row;
        const compare=action('页内对照',()=>openPage(note.doc,note.page,outcome.id,undefined,{fact:outcome.id,line:note.line}),'trail-compare');
        compare.prepend(glyph('layout-sidebar-inset-reverse'));
        compare.setAttribute('aria-label','页内对照，切换复验结论与附注');
        header.append(compare);
      }
      view.append(header);
      if (cards.length) {
        view.append(box('trail-cards',...cards.slice(0,2)));
        if (cards.length>2) {
          const rest=cards.slice(2), pending=rest.filter(c=>c.dataset.attention==='true' || c.classList.contains('trail-empty')).length;
          view.append(fold('其他原文（'+rest.length+'）'+(pending?' · 含 '+pending+' 条待核':''),box('trail-cards',...rest)));
        }
      } else if (doc) view.append(citation(step.unit));
      if (role.key==='final') for (const page of check?.mixed_pages || []) {
        const ref=page.doc+'/p'+page.page;
        if (page.unit===step.unit && supported.has(ref)) view.append(action('核对第 '+page.page+' 页影像及批注',()=>openPage(page.doc,page.page),'ref'));
      }
    }
    return view;
  }

  function panel(finding, graph) {
    const chain=finding.reinspection, index=graphIndex(graph);
    const trail=el('details','','reinspection-trail');
    trail.id='equipment-reinspection-trail';
    trail.tabIndex=-1;
    trail.dataset.disposition=chain.state;
    trail.setAttribute('aria-label','整改复验');
    const supported=new Set(traceReferences(graph,finding));
    const closed=chain.state==='closed' && finding.status==='ok';
    let stateLabel=closed?(chain.register?'已关闭':'该版记为已关闭'):'终验待核';
    if (chain.register && chain.steps.some(s=>s.role==='final' &&
        verifiedRows(s,chain.register,graph,supported).some(entry=>!entry.bound))) {
      stateLabel='证据关系待核';
      trail.dataset.disposition='unverified';
    }
    const heading=el('summary','','trail-heading');
    heading.append(glyph('clock-history'),el('strong','整改复验'),el('span',stateLabel,'trail-state'),glyph('chevron-down'));
    trail.open=index.reinspectionOpen ?? (!closed || trail.dataset.disposition==='unverified');
    trail.addEventListener('toggle',()=>{index.reinspectionOpen=trail.open;});
    const tabs=box('trail-tabs');
    tabs.setAttribute('role','tablist'); tabs.setAttribute('aria-label','验收与整改阶段');
    const scenes=roles.map(role=>{
      const steps=chain.steps.filter(s=>s.role===role.key);
      const tab=action('',()=>select(role.key),'trail-tab');
      tab.id='trail-tab-'+role.key; tab.setAttribute('role','tab');
      const view=scene(role,steps,finding,graph,supported);
      view.id='trail-view-'+role.key; view.setAttribute('role','tabpanel');
      view.setAttribute('aria-labelledby',tab.id); tab.setAttribute('aria-controls',view.id);
      const date=steps.length===1?steps[0].date:null;
      const when=steps.length>1?steps.length+' 份记录':date || (steps.length?'日期待核':'待补件');
      tab.append(el('span','','trail-mark'),el('strong',role.title),el('small',when));
      tabs.append(tab);
      return {role,tab,view,steps};
    });
    function select(key) {
      index.reinspectionRole=key;
      for (const row of scenes) {
        const selected=row.role.key===key;
        row.tab.setAttribute('aria-selected',String(selected));
        row.tab.tabIndex=selected?0:-1; row.view.hidden=!selected;
      }
    }
    scenes.forEach(({tab},i)=>tab.addEventListener('keydown',event=>{
      const position={ArrowRight:(i+1)%scenes.length,ArrowLeft:(i+scenes.length-1)%scenes.length,Home:0,End:scenes.length-1}[event.key];
      if (position===undefined) return;
      event.preventDefault(); select(scenes[position].role.key); scenes[position].tab.focus();
    }));
    trail.append(heading,tabs,...scenes.map(s=>s.view));
    const gap=scenes.find(s=>!s.steps.length);
    const preferred=chain.focus==='final'?'final':gap?.role.key || (chain.focus?'repair':'final');
    select(index.reinspectionRole || preferred);
    return trail;
  }
  return {panel,pageReferences,phaseLink};
})();
