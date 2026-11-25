const ReinspectionTiming = (() => {
  const labels = {
    ...TrialLog.labels,
    minimum:'等待条款', operation:'连续试运行条款', term_unclear:'复验条件', qualification:'合同附注',
    fixed_day:'整改完成日期', fixed_time:'整改完成时刻', started:'实际复验开始', report_day:'复验单日期',
  };
  const states = {
    ...TrialLog.states,
    met:'满足等待期', early:'开验过早', report_early:'复验单日期过早', boundary:'时点精度待核',
    start_missing:'缺开验记录', operation_pending:'缺试运行记录', conflict:'日期冲突',
    terms_pending:'条款范围待核', events_pending:'起止记录待核', chain_pending:'整改归属或签认待核',
  };

  function sources(graph, finding) {
    const check=finding?.reinspection?.timing;
    if (!check) return [];
    const supported=new Set(traceReferences(graph,finding)), index=graphIndex(graph);
    const ledger=graph.reinspection_wait_sources;
    if (!['contract-reinspection-wait-v1','contract-reinspection-wait-v2'].includes(ledger?.format)) return [];
    return ledger.lines.filter(row=>{
      const ref=row.doc+'/p'+row.page, sheet=index.nodes.get(ref), node=index.nodes.get(row.id);
      if (!check.sources.includes(row.id) || !supported.has(row.id) || !supported.has(ref) ||
          sheet?.type!=='page' || sheet.sha256!==row.page_sha256 || index.documents.get(row.doc)?.sha256!==row.source_sha256 ||
          row.supported && (!row.line || sheet.layer!=='text' || sheet.clause_text_only!==true) ||
          node?.type!=='reinspection_time_line' || node.label!==row.quote || node.doc!==row.doc || node.page!==row.page || node.line!==row.line) return false;
      return row.facts.every(id=>{
        const f=index.facts.get(id);
        return supported.has(id) && f?.doc===row.doc && f.page===row.page && (f.unit || f.doc)===row.unit && (!row.supported || f.status!=='disputed') &&
          f.page_sha256===sheet.sha256 && f.source_sha256===row.source_sha256;
      }) && graph.edges.some(e=>e.type==='reinspection_time_basis' && e.from===ref && e.to===row.id &&
        e.evidence.length===1+row.facts.length && e.evidence[0]===ref && row.facts.every((id,i)=>e.evidence[i+1]===id));
    });
  }

  function open(row) {
    openPage(row.doc,row.page,row.line ? null : row.facts[0],row.line);
  }

  function pageReferences(finding,graph,doc,page) {
    return sources(graph,finding).filter(s=>s.doc===doc && s.page===page && s.line).map(s=>{
      const fact=s.facts.map(id=>graphIndex(graph).facts.get(id)).find(f=>f?.source_line?.number===s.line && f.source_line.text===s.quote);
      return {ref:s.id, label:labels[s.kind], option:'第 '+s.line+' 行 · '+labels[s.kind], quote:s.quote,
        rawLine:s.line, quality:'reinspection_time_reference', rects:fact?.source_line.rects || []};
    });
  }

  function duration(seconds) {
    const amount=Math.abs(seconds), hours=Math.floor(amount/3600), minutes=Math.floor(amount%3600/60);
    const parts=[hours && hours+'小时', minutes && minutes+'分', amount%60 && amount%60+'秒'].filter(Boolean);
    return (seconds<0?'−':'')+(parts.join('') || '0小时');
  }

  function linked(check, rows, chain, graph) {
    if (!states[check.state] || rows.length!==check.sources.length) return false;
    const find=id=>rows.find(r=>r.id===id);
    for (const id of [check.term_ref,check.repair_ref,check.start_ref,check.report_ref].filter(Boolean)) {
      if (!find(id)?.supported) return false;
    }
    if (check.required_hours!==null && find(check.term_ref)?.hours!==check.required_hours) return false;
    // Compare printed wall times on one uniform clock, independent of the device's time zone.
    const seconds=(id,key)=>Date.parse((find(id)?.stamp?.[key] || '')+'Z')/1000;
    if (check.below_seconds!==null && (!(check.repair_ref && check.report_ref) ||
        seconds(check.start_ref || check.report_ref,'before')-seconds(check.repair_ref,'from')!==check.below_seconds)) return false;
    if (check.above_seconds!==null && (!check.start_ref ||
        seconds(check.start_ref,'from')-seconds(check.repair_ref,'before')!==check.above_seconds)) return false;
    if (check.operation || check.state.startsWith('run_')) return TrialLog.checkSources(check,rows,chain,graph);
    return check.state!=='met' || (check.status==='ok' && find(check.term_ref)?.kind==='minimum' &&
      Number.isSafeInteger(check.above_seconds) && Number.isSafeInteger(check.below_seconds) &&
      check.above_seconds>=check.required_hours*3600 && check.below_seconds>check.above_seconds);
  }

  function metrics(check, term) {
    const minimum=el('strong',check.required_hours===null?'待核':'≥ '+duration(check.required_hours*3600));
    const clause=box('wait-metric',el('span',term?.kind==='operation'?'约定连续试运行':'约定最短间隔'),minimum);
    const measured=box('wait-metric');
    const lower=check.above_seconds, upper=check.below_seconds;
    measured.append(el('span',Number.isSafeInteger(lower)?'原件可证间隔':upper!==null?'按复验单日期推得的上界':'可证间隔'));
    const values=box('wait-values');
    if (Number.isSafeInteger(lower)) values.append(el('strong','> '+duration(lower)));
    if (Number.isSafeInteger(upper)) values.append(el('strong','< '+duration(upper)));
    if (!values.children.length) values.append(el('strong','待核'));
    measured.append(values);
    return box('wait-metrics',clause,measured);
  }

  function panel(finding,graph) {
    const check=finding.reinspection.timing;
    if (!check) return null;
    const rows=sources(graph,finding), verified=linked(check,rows,finding.reinspection,graph);
    const card=el('section','','retest-wait');
    card.id='reinspection-wait'; card.tabIndex=-1;
    const title=check.operation?'设备试运行':'复验等待期';
    card.setAttribute('aria-label',title);
    card.dataset.timingState=verified?check.state:'unverified';
    card.dataset.tone=verified?check.status:'missing';
    card.append(box('wait-head',el('h3',title),el('span',verified?states[check.state]:'证据关系待核','wait-state')));
    if (verified && check.operation) card.append(TrialLog.panel(check,rows));
    else if (verified) card.append(metrics(check,rows.find(r=>r.id===check.term_ref)));
    const hasStart=rows.some(r=>r.kind==='started');
    const groups=[
      {label:'合同约定', roles:['contract','contract_addendum'], kinds:['minimum','operation','term_unclear','qualification'], preferred:check.term_ref},
      {label:'整改完成', roles:['remediation'], kinds:['fixed_day','fixed_time'], preferred:check.repair_ref},
      {label:hasStart?'复验开始':'复验单日期', roles:['reinspection'], kinds:['started','report_day'], preferred:check.start_ref || check.report_ref},
    ];
    const switcher=box('wait-switch'), body=box('wait-source');
    switcher.setAttribute('role','group'); switcher.setAttribute('aria-label','选择复验间隔依据');
    body.id='wait-source-row'; body.setAttribute('aria-live','polite');
    const supported=new Set(traceReferences(graph,finding));
    const buttons=[];
    function render(groupIndex) {
      buttons.forEach((b,i)=>{b.setAttribute('aria-pressed',String(i===groupIndex)); b.tabIndex=i===groupIndex?0:-1;});
      const group=groups[groupIndex], index=graphIndex(graph);
      const choices=rows.filter(r=>group.kinds.includes(r.kind));
      body.replaceChildren();
      if (!choices.length) {
        const pages=(graph.reinspection_wait_sources?.pages || []).filter(p=>group.roles.includes(p.role) && supported.has(p.doc+'/p'+p.page));
        if (pages.length) for (const p of pages) {
          const doc=index.documents.get(p.doc);
          if (doc) body.append(action(doc.name+' · 第 '+p.page+' 页',()=>openPage(p.doc,p.page),'ref'));
        } else body.append(el('span','待补可定位的原件','wait-empty'));
        return;
      }
      const button=action('',()=>open(choices[Number(button.dataset.choice)]),'wait-open');
      const select=el('select','','wait-select'); select.setAttribute('aria-label','选择'+group.label+'原行');
      function show(i) {
        const row=choices[i], doc=index.documents.get(row.doc);
        const where=doc.name+' · 第 '+row.page+' 页'+(row.line?' '+row.line+' 行':' · 影像引文');
        button.dataset.choice=String(i); button.dataset.timingRef=row.id;
        button.replaceChildren(box('wait-quote',el('small',where),el('strong',row.quote)),glyph('arrows-angle-expand'));
        button.setAttribute('aria-label','核对原件，'+where+'，'+row.quote);
        select.value=String(i);
      }
      if (choices.length>1) {
        choices.forEach((row,i)=>select.add(new Option(labels[row.kind]+' · '+(row.line?'第 '+row.line+' 行':'影像'),String(i))));
        select.addEventListener('change',()=>show(Number(select.value))); body.append(select);
      }
      body.append(button);
      show(Math.max(0,choices.findIndex(r=>r.id===group.preferred)));
    }
    for (const [i,group] of groups.entries()) {
      const button=action(group.label,()=>render(i)); button.setAttribute('aria-controls',body.id);
      button.addEventListener('keydown',e=>{
        const j={ArrowLeft:(i+2)%3,ArrowRight:(i+1)%3,Home:0,End:2}[e.key];
        if (j===undefined) return;
        e.preventDefault(); render(j); buttons[j].focus();
      });
      buttons.push(button); switcher.append(button);
    }
    if (check.operation) {
      const evidence=box('run-basis',switcher,body);
      const additional=rows.filter(r=>['run_clock','run_attestation','run_signer'].includes(r.kind) && r.line && r.supported);
      if (additional.length) {
        const fields=box('run-fields');
        for (const row of additional) fields.append(action(labels[row.kind]+' · '+row.line+' 行',()=>open(row),'ref'));
        evidence.append(fields);
      }
      card.append(fold('合同与起止依据',evidence));
    } else card.append(switcher,body);
    render(0);
    return card;
  }

  function phaseLink(finding,phase,graph) {
    const check=finding.reinspection?.timing;
    if (!check || check.status==='ok' || phase.status==='ok') return null;
    const proof=new Set(traceReferences(graph,phase));
    if (!sources(graph,finding).some(s=>['minimum','operation','term_unclear'].includes(s.kind) && proof.has(s.id))) return null;
    const jump=action(check.operation?'核对设备试运行':'核对复验等待期',()=>{
      document.getElementById('trail-tab-final')?.click();
      revealPaperTarget(document.getElementById('reinspection-wait'));
    },'compare-jump');
    jump.dataset.timingPhase=phase.id;
    jump.setAttribute('aria-controls','reinspection-wait');
    return jump;
  }
  return {panel,sources,pageReferences,phaseLink,open,linked};
})();
