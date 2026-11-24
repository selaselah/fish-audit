const graphIndexes = new WeakMap();

function graphIndex(graph) {
  let index = graphIndexes.get(graph);
  if (!index) {
    const prior = new Map((graph.prior_invoices || []).map(row=>[row.id,row]));
    for (const row of graph.prior_invoices || []) {
      for (const code of row.code_evidence || []) {
        prior.set(code.id,{...code,label:'发票代码',case_id:row.case_id,rev:row.rev,title:row.title,decision:row.decision});
      }
    }
    const history = graph.payment_history;
    for (const match of [...(history?.matches || []),...(history?.installments?.matches || [])]) {
      for (const fact of match.evidence) {
        prior.set(fact.id,{...fact,case_id:match.case_id,rev:match.rev,title:match.title,decision:match.decision});
      }
    }
    index = {
      facts:new Map(graph.facts.map(f=>[f.id,f])),
      documents:new Map(graph.documents.map(d=>[d.id,d])),
      prior,
      nodes:new Map(graph.nodes.map(n=>[n.id,n])),
    };
    graphIndexes.set(graph,index);
  }
  return index;
}

function lazyFold(title, build) {
  const details = fold(title);
  const expand = () => {
    if (!details.open) return;
    details.removeEventListener('toggle',expand);
    details.append(...build());
  };
  details.addEventListener('toggle',expand);
  return details;
}

function performanceOverview(findings, graph) {
  const overview = el('section','','performance-overview');
  const summary = box('performance-statuses');
  const inspect = (item, label) => {
    const button = action('', () => {
      const target = document.querySelector('[data-finding="'+CSS.escape(item.id)+'"]');
      target?.focus({preventScroll:true});
      target?.scrollIntoView({block:'start'});
    }, 'performance-jump');
    button.dataset.jumpFinding = item.id;
    button.setAttribute('aria-label',label+' · '+statusName(item.status)+'，查看依据');
    button.append(el('span',label),tag(item.status));
    return button;
  };
  for (const [rule,label] of [['H01','签署与生效'],['H02','交付验收'],['H03','付款安排']]) {
    const item = findings.find(f=>f.rule===rule);
    if (item) summary.append(inspect(item,label));
  }
  overview.setAttribute('aria-label','履约结论与期次');
  overview.append(summary);
  const phases = findings.filter(f=>f.rule==='H04' && f.stage);
  if (!phases.length) return overview;
  const list = el('ol','','phase-summary');
  const payments = findings.filter(f=>f.rule==='H05');
  const index = graphIndex(graph);
  const paymentLabel = f => {
    const document = f.evidence.map(ref=>index.facts.get(ref)).find(fact=>fact?.field==='bank_receipt');
    return document?.name || f.id;
  };
  for (const phase of phases) {
    const stage = phase.stage;
    const row = el('li');
    row.dataset.phaseFinding = phase.id;
    const heading = stage.name+(stage.share ? ' · '+stage.share+'%' : '');
    const fact = index.facts.get(stage.clause_ref);
    const source = fact ? action(heading,()=>openPage(fact.doc,fact.page,fact.id),'phase-source') : el('strong',heading);
    if (fact) source.setAttribute('aria-label',heading+'，查看合同原文');
    const results = box('phase-results',inspect(phase,'付款条件'));
    const matched = payments.filter(f=>f.stage && ['name','clause_ref','clause','share'].every(k=>f.stage[k]===stage[k]));
    if (matched.length) {
      for (const item of matched) results.append(inspect(item,matched.length===1?'实付时点':paymentLabel(item)));
    } else {
      results.append(el('span','未关联回单','phase-unlinked'));
    }
    row.append(box('phase-contract',source,el('q',stage.clause)),results);
    list.append(row);
  }
  overview.append(list);
  for (const item of payments.filter(f=>!f.stage)) overview.append(inspect(item,'回单期次待核 · '+paymentLabel(item)));
  return overview;
}

function performanceComparison(finding, graph) {
  const comparisons = {
    H01: ['对照生效条件与签署依据',['effect_clause','signed_on','effect_on','valid_until','buyer_signature','seller_signature','contract_state','approval_authority','approval_result','approved_on','approval_signer']],
    H02: ['对照验收范围、标准与结果',['accepted_on','acceptance_scope','quantity_agreed','quantity_accepted','acceptance_criteria','inspection_basis','measured_result','acceptance_result','acceptance_exception','acceptance_signer']],
    H05: ['对照付款和履约日期',['payment_designation','paid_on','effect_on','approved_on','accepted_on','warranty_release']],
  };
  const spec = comparisons[finding.rule];
  if (!spec) return null;
  const [title,fields] = spec;
  const index = graphIndex(graph);
  const citations = finding.evidence.map(ref=>index.facts.get(ref)).filter(f=>f && fields.includes(f.field));
  citations.sort((a,b)=>fields.indexOf(a.field)-fields.indexOf(b.field));
  if (!citations.length) return null;
  const details = lazyFold(title,()=>citations.map(fact=>{
    const row = box('performance-source',el('blockquote',fact.quote),box('flow',tag(fact.status),citation(fact.id)));
    row.dataset.sourceFact = fact.id;
    return row;
  }));
  details.classList.add('performance-comparison');
  details.open = ['risk','issue'].includes(finding.status);
  return details;
}

function dateEvidencePanel(finding, graph) {
  const fields = new Set(['signed_on','effect_on','valid_until','approved_on','accepted_on','paid_on','warranty_release']);
  const index = graphIndex(graph);
  const refs = new Set(finding.date_checks.flatMap(check=>check.evidence));
  const panel = box('contract-date-evidence',el('h4','核对日期原文'));
  for (const check of finding.date_checks) {
    if (!finding.detail.includes(check.detail)) panel.append(box('flow',tag(check.status),el('p',check.detail)));
  }
  for (const ref of refs) {
    const fact = index.facts.get(ref);
    if (!fields.has(fact?.field)) continue;
    const row = box('change-source',el('q',fact.source_line?.text || fact.quote),citation(ref));
    row.dataset.dateFact = ref;
    panel.append(row);
  }
  return panel.children.length>1 ? panel : null;
}

function deliveryBatchPanel(entry, graph, phases) {
  const {facts,documents}=graphIndex(graph);
  const ledger=graph.delivery_batch_sources;
  const panel=el('section','','delivery-batches');
  const records=new Map(entry.records.map(r=>[r.unit,r]));
  const matched=new Set(entry.batches.flatMap(b=>b.records));
  const complete=entry.batches.filter(b=>b.status==='ok').length;
  const sourceRow = ref => {
    const fact=facts.get(ref);
    const row=box('batch-source',el('q',fact.source_line?.text || fact.quote),citation(ref));
    row.dataset.batchFact=ref;
    return row;
  };
  panel.setAttribute('aria-label','分批交付与验收');
  panel.append(box('batch-heading',el('h4','分批交付与验收'),el('span',complete+' / '+entry.batches.length+' 批有合格依据','small')));
  const rule=facts.get(entry.rule_ref);
  if (rule) panel.append(sourceRow(rule.id));
  if (entry.completion_on) panel.append(el('p','按合同达到终验条件 · '+entry.completion_on,'batch-final'));
  else if (!entry.deemed_final) panel.append(el('p',rule && /另行(组织最终验收|终验)/.test(rule.quote)?'合同约定另行终验，待核终验原件。':'各批验收与最终验收的关系待核。','batch-final'));
  function receipt(r) {
    const group=box('batch-receipt');
    const scope=facts.get(r.scope_ref);
    const head=box('flow',el('strong',r.number || '验收单号待核'),el('span',r.date || '日期待核','small'));
    if (scope) head.append(citation(r.scope_ref));
    group.append(head);
    const summary=[r.count!=null?'实收 '+r.count+r.unit_name:'实收数量待核',...r.serials].join(' · ');
    group.append(el('p',summary));
    return group;
  }
  const proofFields=new Set(['acceptance_number','accepted_on','delivered_serials','quantity_accepted','inspection_basis','measured_result',
                             'acceptance_result','acceptance_exception','acceptance_signer','acceptance_criteria']);
  for (const b of entry.batches) {
    const section=el('section','','batch-record');
    section.dataset.deliveryIndex=String(b.index);
    const title=box('flow',el('h5',b.label),tag(b.status));
    const due=phases.filter(f=>f.stage?.batch_index===b.index).map(f=>f.stage.name+' '+f.stage.share+'%');
    if (due.length) title.append(el('span',due.join('、'),'batch-payment'));
    section.append(title,sourceRow(b.clause_ref));
    for (const unit of b.records) section.append(receipt(records.get(unit)));
    section.append(el('p',b.detail,'batch-detail'));
    const refs=b.evidence.filter(ref=>proofFields.has(facts.get(ref)?.field));
    if (refs.length) section.append(lazyFold('核对标准、实测与签认原文',()=>refs.map(sourceRow)));
    panel.append(section);
  }
  for (const r of entry.records.filter(r=>!matched.has(r.unit))) {
    panel.append(box('batch-record',el('h5','归属待核的验收单'),receipt(r),el('p',r.detail)));
  }
  const observed=new Set();
  for (const p of ledger.pages) {
    if (!p.text_only) {
      const link=action((documents.get(p.doc)?.name || '原件')+' · 第 '+p.page+' 页',()=>openPage(p.doc,p.page),'ref');
      link.dataset.batchPage=p.doc+'/p'+p.page;
      panel.append(box('batch-source',el('strong','核对整页影像及附注'),link));
    }
    for (const l of p.uncovered) {
      const row=box('batch-source',el('q',l.quote),action('核对原件第 '+l.line+' 行',()=>openPage(p.doc,p.page,null,l.line),'ref'));
      row.dataset.batchLine=p.doc+'/p'+p.page+'/l'+l.line;
      panel.append(row);
      observed.add(p.doc+'/p'+p.page+'@'+l.quote);
    }
  }
  for (const item of ledger.visual_notes) {
    const row=sourceRow(item.fact);
    row.append(tag(facts.get(item.fact).status));
    panel.append(row);
    observed.add(item.fact);
  }
  for (const item of entry.riders) {
    if (facts.has(item.ref) && !observed.has(item.ref)) {
      panel.append(sourceRow(item.ref));
      observed.add(item.ref);
    }
  }
  if (!rule || !entry.batches.length) {
    for (const s of ledger.signals) {
      if (observed.has(s.doc+'/p'+s.page+'@'+s.quote)) continue;
      const fact=s.facts.find(ref=>facts.get(ref)?.quote===s.quote);
      if (fact) panel.append(sourceRow(fact));
      else panel.append(box('batch-source',el('q',s.quote),
        action('核对合同第 '+s.page+' 页',()=>openPage(s.doc,s.page,null,s.line),'ref')));
    }
  }
  return panel;
}

function contractEffectPanel(finding,graph) {
  const {conditions,mixed_pages}=finding.effect_review;
  if (!conditions.length && !mixed_pages.length) return null;
  const {facts,documents}=graphIndex(graph);
  const panel=box('effect-review',el('h4','需核对的生效条件'));
  const cited=new Set(conditions.flatMap(s=>s.facts));
  for (const ref of finding.evidence) {
    const fact=facts.get(ref);
    if (fact?.field==='effect_clause' && !cited.has(ref))
      panel.append(box('batch-source',el('q',fact.source_line?.text || fact.quote),citation(ref)));
  }
  for (const item of conditions) {
    const fact=item.facts.map(id=>facts.get(id)).find(f=>f?.quote===item.quote);
    const button=action((documents.get(item.doc)?.name || '合同')+' · 第 '+item.page+' 页',
      ()=>openPage(item.doc,item.page,fact?.id,fact?null:item.line),'ref');
    const row=box('batch-source',el('q',item.quote),button);
    row.append(el('small',item.line?'原页文字层第 '+item.line+' 行':'影像读图引文','small'));
    if (!item.line && fact) row.append(tag(fact.status));
    row.dataset.effectSource=fact?.id || item.doc+'/p'+item.page+'/l'+item.line;
    panel.append(row);
  }
  for (const page of mixed_pages) {
    const original=action((documents.get(page.doc)?.name || '合同')+' · 第 '+page.page+' 页',()=>openPage(page.doc,page.page),'ref');
    original.dataset.effectPage=page.doc+'/p'+page.page;
    panel.append(box('batch-source',el('strong','通读整页影像及批注'),original));
  }
  return panel;
}

function paymentWindowPanel(finding,graph) {
  const w=finding.payment_window;
  const {facts,documents}=graphIndex(graph);
  const panel=box('payment-window',el('h4','付款时限复算'));
  panel.dataset.windowState=w.outcome || w.state;
  panel.dataset.status=finding.status;
  const dates=el('dl','','warranty-dates');
  function addDate(title,value) {
    dates.append(box('warranty-date',el('dt',title),el('dd',value || '待核',value?'':'muted')));
  }
  addDate('履约起算日',w.trigger_on);
  addDate(w.state==='nominal'?'顺延前日历末日':'按约复算末日',w.calendar_end);
  if (finding.rule==='H05') addDate('回单付款日',w.paid_on);
  panel.append(dates);
  if (w.state==='nominal' && !finding.detail.includes('顺延'))
    panel.append(el('p','实际末日还需核对休假日顺延及合同约定。','small'));
  if (['unresolved','conflict'].includes(w.state) && w.detail && !finding.detail.includes(w.detail))
    panel.append(el('p',w.detail,'small'));
  const located=new Set();
  for (const item of w.lines) {
    const fact=item.facts.map(id=>facts.get(id)).find(f=>f?.quote===item.quote);
    const title=(documents.get(item.doc)?.name || '原件')+' · 第 '+item.page+' 页'+(item.line?' · 第 '+item.line+' 行':'');
    const ref=action(title,()=>openPage(item.doc,item.page,fact?.id,fact?null:item.line),'ref');
    const row=box('batch-source',el('q',item.quote),ref);
    row.dataset.windowSource=fact?.id || item.doc+'/p'+item.page+'/l'+item.line;
    panel.append(row);
    if (fact) located.add(fact.id);
  }
  for (const id of [w.trigger_ref,w.paid_ref]) {
    const fact=facts.get(id);
    if (!fact || located.has(id)) continue;
    const row=box('batch-source',el('q',fact.source_line?.text || fact.quote),citation(id));
    row.dataset.windowSource=id;
    panel.append(row);
  }
  for (const p of w.mixed_pages) {
    const ref=action((documents.get(p.doc)?.name || '原件')+' · 第 '+p.page+' 页',()=>openPage(p.doc,p.page),'ref');
    ref.dataset.windowPage=p.doc+'/p'+p.page;
    panel.append(box('batch-source',el('strong','通读整页影像及附注'),ref));
  }
  if (w.calendar_source) {
    if (w.days.length) {
      const trace=lazyFold('逐日核对工作日（已计 '+w.days.at(-1).total+' 天）',()=>{
        const table=el('table','','workday-table');
        const heads=table.createTHead().insertRow();
        for (const name of ['日期','日历安排','累计工作日']) {
          const th=el('th',name); th.scope='col'; heads.append(th);
        }
        const rows=table.createTBody();
        for (const d of w.days) {
          const row=rows.insertRow();
          row.classList.toggle('workday-counted',d.counted);
          for (const value of [d.date,d.kind,String(d.total)]) row.insertCell().textContent=value;
        }
        return [table];
      });
      trace.classList.add('workday-trace');
      panel.append(trace);
    }
    const source=citation('source/'+w.calendar_source);
    source.dataset.workdaySource=w.calendar_source;
    panel.append(box('batch-source',el('strong','本次采用的日历'),source));
  }
  return panel;
}

function warrantyPanel(finding,graph) {
  const entry=finding.warranty_check;
  const {facts,documents}=graphIndex(graph);
  const panel=box('warranty-review',el('h4','质保金释放依据'));
  const units=new Set(entry.scope);
  const lines=graph.warranty_sources.lines.filter(s=>units.has(s.unit));
  const dates=el('dl','','warranty-dates');
  function addDate(label,value) {
    dates.append(box('warranty-date',el('dt',label),el('dd',value || '待核',value?'':'muted')));
  }
  addDate('合格终验或复验日',entry.accepted_on);
  addDate('合同日历末日',entry.calendar_end);
  addDate('期满确认日',entry.confirmed_on);
  const cited=finding.evidence.map(ref=>facts.get(ref)).filter(Boolean);
  const transfers=cited.filter(f=>f.field==='paid_on');
  if (finding.rule==='H05') addDate('实际付款日',transfers[0]?.source_line?.text.split(/[:：]/u).slice(1).join('：').trim());
  panel.append(dates);
  if (!entry.period && !lines.some(s=>s.kind==='warranty_period') && entry.confirmed_on)
    panel.append(el('p','本案确认日取自签认记录，未取得可独立复算的期限条款。','small'));
  for (const pair of entry.identity_conflicts) {
    const proof=box('warranty-conflict',el('strong','合同与确认单的'+facts.get(pair.contract_ref).label+'不同'));
    for (const ref of [pair.contract_ref,pair.release_ref])
      proof.append(box('batch-source',el('q',facts.get(ref).source_line.text),citation(ref)));
    panel.append(proof);
  }
  const originals=fold('核对质保条款与履约原文');
  originals.open=finding.rule==='H04';
  const unitOrder=['contract','acceptance','reinspection','warranty','bank_receipt'].flatMap(k=>graph.documents_by_kind[k] || []);
  const rows=[];
  function record(unit,page,line,row) {
    const position=unitOrder.indexOf(unit);
    rows.push({position:position<0?unitOrder.length:position,page,line:line ?? Infinity,row});
  }
  const addFact=fact => {
    const row=box('batch-source',el('q',fact.source_line?.text || fact.quote),citation(fact.id));
    if (fact.field==='acceptance_signer') row.append(tag(fact.status));
    row.dataset.warrantySource=fact.id;
    record(fact.unit || fact.doc,fact.page,fact.source_line?.number,row);
  };
  const listed=new Set(lines.flatMap(s=>s.facts));
  const confirmations=new Set(graph.documents_by_kind.warranty || []);
  for (const fact of cited.filter(f=>['accepted_on','paid_on'].includes(f.field) || f.id===finding.stage.clause_ref ||
      f.field==='acceptance_signer' && confirmations.has(f.unit || f.doc)))
    if (!listed.has(fact.id)) addFact(fact);
  for (const item of lines) {
    const fact=item.facts.map(id=>facts.get(id)).find(f=>f?.quote===item.quote);
    const page=item.doc+'/p'+item.page;
    const title=(documents.get(item.doc)?.name || '原件')+' · 第 '+item.page+' 页'+(item.line?' · 第 '+item.line+' 行':'');
    const ref=action(title,()=>openPage(item.doc,item.page,fact?.id,fact?null:item.line),'ref');
    const row=box('batch-source',el('q',item.quote),ref);
    row.dataset.warrantySource=fact?.id || page+'/l'+item.line;
    if (item.kind==='unresolved' || item.kind==='observation') row.append(el('small','需核对原件','small'));
    record(item.unit,item.page,item.line,row);
  }
  for (const page of graph.warranty_sources.pages.filter(p=>units.has(p.unit) && (!p.native || !p.text_only))) {
    const ref=action((documents.get(page.doc)?.name || '原件')+' · 第 '+page.page+' 页',()=>openPage(page.doc,page.page),'ref');
    ref.dataset.warrantyPage=page.doc+'/p'+page.page;
    record(page.unit,page.page,null,box('batch-source',el('strong','通读整页影像及附注'),ref));
  }
  rows.sort((a,b)=>a.position-b.position || a.page-b.page || a.line-b.line);
  originals.append(...rows.map(item=>item.row));
  for (const problem of entry.problems)
    if (!finding.detail.includes(problem.detail)) originals.append(el('p',problem.detail,'small'));
  panel.append(originals);
  return panel;
}

function qualityChangePanel(change, graph) {
  const index = graphIndex(graph);
  const facts = change.evidence.map(id=>index.facts.get(id)).filter(Boolean);
  const units = new Set(change.units);
  const decision = {applied:'按补充协议',original:'按原合同',pending:'适用版本待核'}[change.state];
  const panel = box('quality-change',box('flow',el('h4','终验适用标准'),el('strong',decision,'quality-decision')));
  panel.dataset.qualityChange = change.state;
  if (change.applied_criterion) panel.append(el('p',change.applied_criterion,'quality-standard'));
  const docUnit = f => f.unit || f.doc;
  const originalPage = (fact,short=false) => {
    const page='第 '+fact.page+' 页';
    const location=fact.name+' · '+page;
    const button=action(short?page+'原文':location,()=>openPage(fact.doc,fact.page,fact.id),'ref');
    button.setAttribute('aria-label',location+' · '+fact.label);
    button.title=location+' · '+fact.label;
    return button;
  };
  const sourceRow = fact => {
    const row = box('change-source',el('q',fact.quote),originalPage(fact));
    row.dataset.changeFact = fact.id;
    return row;
  };
  const comparison = el('dl','','change-comparison');
  for (const [field,title] of [['acceptance_criteria','原合同标准'],['revised_criterion','协议所列新标准'],
                               ['inspection_basis','验收报告检验依据'],['measured_result','原页实测结果']]) {
    const value = el('dd');
    const matches = facts.filter(f=>f.field===field);
    if (matches.length) value.append(...matches.map(sourceRow));
    else value.append(el('span','待补原文','muted'));
    comparison.append(box('',el('dt',title),value));
  }
  panel.append(comparison);
  const dates = el('dl','','mandate-dates');
  for (const [key,title] of [['buyer_sealed_on','甲方盖章'],['seller_sealed_on','乙方盖章'],['effective_on','按约定生效'],['accepted_on','本次终验']]) {
    const value=el('dd');
    value.append(el('span',change[key] || '待核'));
    const fields=key==='effective_on'?['change_effect_clause']:[key];
    for (const f of facts.filter(f=>fields.includes(f.field))) value.append(originalPage(f,true));
    dates.append(box('',el('dt',title),value));
  }
  const fields = new Set(['addendum_number','base_contract_ref','previous_criterion','change_scope','change_timing',
                          'change_effect_clause','change_state','buyer_signature','seller_signature']);
  const clauses = facts.filter(f=>units.has(docUnit(f)) && fields.has(f.field));
  panel.append(dates);
  if (clauses.length) panel.append(lazyFold('核对协议编号、签章和完整条款',()=>clauses.map(sourceRow)));
  const ledger = graph.quality_addenda;
  for (const page of ledger.pages.filter(p=>units.has(p.unit))) {
    if (!page.text_only) {
      panel.append(box('change-source',el('span','本页含影像或待核版式，请通读原页'),
        action('查看第 '+page.page+' 页',()=>openPage(page.doc,page.page),'ref')));
      const notes = facts.filter(f=>f.doc===page.doc && f.page===page.page && !f.source_line && f.field!=='contract_addendum');
      if (notes.length) {
        const list=lazyFold('查看本页读图引文（'+notes.length+'）',()=>notes.map(f=>{
          const row=sourceRow(f);
          row.append(tag(f.status));
          return row;
        }));
        list.dataset.changeImage=page.doc+'/p'+page.page;
        panel.append(list);
      }
    }
    for (const line of page.uncovered) {
      const row = box('change-source',el('q',line.quote),action('定位第 '+line.line+' 行',()=>openPage(page.doc,page.page,null,line.line),'ref'));
      row.dataset.changeLine = String(line.line);
      panel.append(row);
    }
  }
  const coveredUnits = new Set(ledger.pages.map(p=>p.unit));
  for (const item of [...ledger.limited_numbers,...ledger.signals.filter(s=>!coveredUnits.has(s.unit))]) {
    panel.append(box('change-source',el('q',item.quote),item.fact?citation(item.fact):
      action('查看第 '+item.page+' 页第 '+item.line+' 行',()=>openPage(item.doc,item.page,null,item.line),'ref')));
  }
  return panel;
}

function acceptanceAuthorityPanel(entry, graph) {
  const index = graphIndex(graph);
  const sources = graph.acceptance_authority_sources;
  const panel = box('acceptance-authority', box('flow', el('h4','验收签认权限'), tag(entry.status)));
  panel.dataset.authorityStatus = entry.status;
  const requirement = {single:'指定验收人',joint:'须共同签字',unresolved:'签认约定待核'}[entry.mode];
  const names = el('strong',entry.required.join('、'),'signer-names');
  panel.append(box('flow signer-requirement', el('span',requirement), names));
  if (entry.applies_to) panel.append(el('p',entry.applies_to==='final'?'适用记录 · 终验':'适用记录 · 终验及整改复验','small'));
  function sourceRow(item, remark) {
    const fact = index.facts.get(item.fact || item.facts?.[0]);
    const pinpoint = fact && (!item.line || fact.quote===item.quote) ? fact.id : null;
    const doc = index.documents.get(item.doc);
    const page = (doc?.name || '原件')+' · 第 '+item.page+' 页';
    const link = action(page,()=>openPage(item.doc,item.page,pinpoint,pinpoint?null:item.line),'ref');
    const row = box('signer-source',el('q',item.quote),link);
    if (remark) row.append(el('span',remark,'small'));
    row.dataset.signerSource = pinpoint || item.doc+'/p'+item.page+'/l'+item.line;
    link.setAttribute('aria-label',page+'，查看“'+item.quote+'”');
    return row;
  }
  const contracts = new Set(graph.documents_by_kind.contract || []);
  for (const clause of sources.clauses) {
    const remark = !clause.native?'读图引文待核':contracts.has(clause.unit) && clause.fact?'合同原文':'其他签认线索待核';
    panel.append(sourceRow(clause,remark));
  }
  for (const record of entry.records) {
    const section = el('section','','signature-record');
    section.dataset.signerRecord = record.unit;
    section.append(box('flow',el('strong',record.role==='reinspection'?'整改复验':'原验收'),el('span',record.date || '日期待核','small'),tag(record.status)));
    for (const row of record.signed) section.append(sourceRow(row,row.confirmed?'签字栏已核图':'签字栏待核图'));
    if (record.missing_names.length) section.append(el('p','尚缺已核签认 · '+record.missing_names.join('、'),'signer-pending'));
    if (record.other_names.length) section.append(el('p','约定以外的签字人 · '+record.other_names.join('、'),'signer-pending'));
    if (!record.signed.length) section.append(el('p','待补可核对的签字栏','small'));
    panel.append(section);
  }
  const linesShown = new Set([...sources.clauses,...sources.signatures].map(s=>s.doc+'/p'+s.page+'/l'+s.line));
  for (const page of sources.pages) {
    if (!page.text_only) {
      const name = index.documents.get(page.doc)?.name || '原件';
      const button = action('查看'+name+'第 '+page.page+' 页',()=>openPage(page.doc,page.page),'ref');
      button.dataset.signerPage = page.doc+'/p'+page.page;
      panel.append(box('signer-review-note',el('span','本页含影像或版式待核，请通读签字栏和附注。'),button));
    }
    for (const line of page.uncovered) {
      if (!linesShown.has(page.doc+'/p'+page.page+'/l'+line.line))
        panel.append(sourceRow({...line,doc:page.doc,page:page.page},'待核原文'));
    }
  }
  for (const note of sources.visual_notes) panel.append(sourceRow(note,'读图附注待核'));
  return panel;
}

function reinspectionTrail(chain, graph) {
  const index = graphIndex(graph);
  const roles = [
    ['original','原验收',['acceptance_result','acceptance_exception','measured_result','defect_number']],
    ['repair','整改记录',['repair_action','repair_result','repair_number','defect_number']],
    ['final','最终复验',['measured_result','defect_closure','acceptance_result','defect_number']],
  ];
  const list = el('ol','','reinspection-steps');
  const panel = box('reinspection-trail',el('h4',chain.state==='closed'?'整改复验已关闭缺陷':'整改复验待核'),list);
  panel.dataset.disposition = chain.state;
  for (const [role,label,fields] of roles) {
    const steps=chain.steps.filter(s=>s.role===role);
    if (!steps.length) {
      const absent=el('li','尚无已核归属的'+label+'资料','muted');
      const heading={original:'acceptance',repair:'remediation',final:'reinspection'}[role];
      for (const gap of graph.gaps.filter(g=>g.quality==='uncovered_title' && g.title_hint===heading)) {
        absent.append(box('reinspection-line',el('span','待核页内标题“'+gap.quote+'”'),
          action('核对原页第 '+gap.line+' 行',()=>openPage(gap.doc,gap.page,null,gap.line),'ref')));
      }
      list.append(absent);
    }
    for (const step of steps) {
      const row = el('li');
      row.dataset.reinspectionRole = role;
      row.append(box('flow',el('strong',label),el('span',step.date || '日期待核','small')));
      const facts=step.evidence.map(ref=>index.facts.get(ref)).filter(f=>f && fields.includes(f.field));
      for (const fact of facts) {
        const line=box('reinspection-line',el('span',fact.quote),citation(fact.id));
        line.dataset.citedFact=fact.id;
        row.append(line);
      }
      if (!facts.length) row.append(citation(step.unit));
      list.append(row);
    }
  }
  return panel;
}

function mandatePanel(entries, graph) {
  const panel = box('mandate-review', el('h4', '书面签约授权'));
  const index = graphIndex(graph);
  for (const entry of entries) {
    const title = {buyer:'甲方',seller:'乙方',unassigned:'待归属'}[entry.side];
    const pending = {role:'仅列岗位或机构', joint:'受托人数待核', redacted:'姓名隐去', unclear:'姓名待核'}[entry.agent_kind];
    const identity = pending || entry.agent;
    const section = box('mandate-side', box('flow', el('strong', title+(identity?' · '+identity:'')), tag(entry.status)));
    section.dataset.mandateSide = entry.side;
    if (entry.agent_kind) section.dataset.agentKind = entry.agent_kind;
    const facts = entry.evidence.map(ref => index.facts.get(ref)).filter(Boolean);
    const dates = el('dl', '', 'mandate-dates');
    for (const [field,key,label] of [['signed_on','signed_on','合同签约'],['granted_on','issued_on','委托书出具'],
                                     ['grant_from','valid_from','授权起始'],['grant_until','valid_until','授权截止']]) {
      const value = el('dd');
      value.append(el('span',entry[key] || '待核'));
      for (const fact of facts.filter(f => f.field===field)) value.append(citation(fact.id));
      dates.append(box('', el('dt',label), value));
    }
    section.append(dates);
    const fields = new Set([entry.signature_field, 'grant_agent','grant_scope','grant_conditions','grant_signature','grant_state']);
    for (const fact of facts.filter(f => fields.has(f.field))) {
      const line = box('reinspection-line', el('span', fact.quote), citation(fact.id));
      line.dataset.mandateFact = fact.id;
      section.append(line);
    }
    for (const page of (graph.delegation_coverage?.pages || []).filter(p => entry.units.includes(p.unit))) {
      if (!page.native) {
        section.append(el('p', '委托书第 '+page.page+' 页为影像，需通读完整授权范围。', 'small'));
        const notes = graph.facts.filter(f=>f.doc===page.doc && f.page===page.page && f.field==='other');
        if (notes.length) {
          const details = lazyFold('查看同页其他读图引文（'+notes.length+'）',()=>notes.map(f=>{
            const row=box('reinspection-line',el('span',f.quote),tag(f.status),citation(f.id));
            row.dataset.mandateNote=f.id;
            return row;
          }));
          details.dataset.mandateImage=page.doc+'/p'+page.page;
          section.append(details);
        }
      }
      for (const line of page.uncovered) section.append(box('reinspection-line', el('span', line.quote),
        action('核对委托书第 '+line.line+' 行',()=>openPage(page.doc,page.page,null,line.line),'ref')));
    }
    panel.append(section);
  }
  return panel;
}

function accountPreview(fact, page) {
  const figure=el('figure','','account-preview');
  const caption=el('figcaption',fact.name+' · 第 '+fact.page+' 页');
  const surface=box('account-image',el('small','正在读取原页…','muted'));
  figure.append(surface,caption);
  const img=el('img');
  const title=fact.name+' 第 '+fact.page+' 页';
  img.alt=title+'整页图像';
  const rects=page?.layer==='text' ? fact.source_line?.rects || [] : [];
  const valid=rects.length && rects.every(r=>Array.isArray(r) && r.length===4 && r.every(n=>Number.isFinite(n) && n>=0 && n<=1) && r[0]<r[2] && r[1]<r[3]);
  loadReviewImage(img,workpaperSource(fact.doc,'pages/'+fact.page)).then(()=>{
    if (!valid) {
      surface.replaceChildren(img);
      return;
    }
    const width=img.naturalWidth,height=img.naturalHeight;
    const x=Math.max(0,Math.floor(Math.min(...rects.map(r=>r[0]))*width)-10);
    const y=Math.max(0,Math.floor(Math.min(...rects.map(r=>r[1]))*height)-8);
    const right=Math.min(width,Math.ceil(Math.max(...rects.map(r=>r[2]))*width)+10);
    const bottom=Math.min(height,Math.ceil(Math.max(...rects.map(r=>r[3]))*height)+8);
    const crop=el('canvas');
    crop.width=right-x; crop.height=bottom-y;
    const ctx=crop.getContext('2d');
    if (!ctx) { surface.replaceChildren(img); return; }
    ctx.drawImage(img,x,y,crop.width,crop.height,0,0,crop.width,crop.height);
    crop.setAttribute('role','img');
    crop.setAttribute('aria-label',title+'第 '+fact.source_line.number+' 行原图');
    surface.replaceChildren(crop);
    caption.textContent+=' · 原图第 '+fact.source_line.number+' 行';
  }).catch(()=>surface.replaceChildren(el('p','原页读取失败，可打开原页重试。','small')));
  return figure;
}

function accountComparison(item,graph) {
  const index=graphIndex(graph);
  const cited=[...new Set(item.evidence)].map(id=>index.facts.get(id)).filter(Boolean);
  const sides=[
    {kind:'contract',field:'contract_account',label:'合同约定收款账号'},
    {kind:'bank_receipt',field:'payee_account',label:'回单收款账号'}
  ].map(side=>({...side,facts:cited.filter(f=>f.field===side.field && graph.documents_by_kind[side.kind]?.includes(f.unit || f.doc))}));
  if (!sides.some(s=>s.facts.length)) return null;
  const details=lazyFold('逐位核对收款账号',()=>{
    const digits=f=>f.value.normalize('NFKC').replace(/\s/gu,'');
    const pair=sides.map(s=>s.facts.length===1 ? digits(s.facts[0]) : '');
    const completeDigits=/^[0-9]{8,32}$/;
    const gaps=sides.flatMap((s,i)=>{
      if (!s.facts.length) return [s.label+'缺少引文'];
      if (s.facts.length>1) return [s.label+'有 '+s.facts.length+' 条候选引文'];
      if (completeDigits.test(pair[i])) return [];
      return [s.label+(/[*•●…×]|^[0-9Xx]*[Xx]{2,}[0-9Xx]*$/.test(pair[i])?'含遮盖字符':'的字符或位数待核')];
    });
    const comparable=!gaps.length;
    const longer=pair[0].length>=pair[1].length ? pair[0] : pair[1];
    const first=Array.from(longer).findIndex((_,i)=>pair[0][i]!==pair[1][i]);
    const columns=box('account-evidence-grid');
    for (const [i,side] of sides.entries()) {
      const column=box('account-evidence-side',el('h4',side.label));
      if (!side.facts.length) column.append(el('p','本项尚缺该侧账号引文。','muted'));
      for (const f of side.facts) {
        const card=box('account-observation');
        card.dataset.accountFact=f.id;
        const number=digits(f);
        const isDigits=completeDigits.test(number);
        card.append(tag(f.status));
        if (isDigits) {
          const display=el('code','','account-digits');
          display.setAttribute('aria-label','抄录账号 '+number.split('').join(' '));
          for (let j=0;j<number.length;j+=4) {
            const group=el('span');
            for (let k=j;k<Math.min(number.length,j+4);k++) {
              if (comparable && number[k]!==pair[1-i][k]) group.append(el('mark',number[k]));
              else group.append(number[k]);
            }
            display.append(group);
          }
          card.append(display,el('small',number.length+' 位 · '+number.match(/^0*/)[0].length+' 个前导零','small'));
        } else {
          card.append(el('code',f.value,'account-digits'));
        }
        card.append(el('blockquote',f.quote));
        const uncovered=graph.gaps.filter(g=>g.quality==='uncovered' && g.doc===f.doc && g.page===f.page && g.field===f.field && g.quote);
        for (const gap of uncovered) {
          const printed=/^[^:0-9]+:([0-9]{8,32})$/.exec(gap.quote.normalize('NFKC').replace(/\s/gu,''));
          const length=printed?' · '+printed[1].length+' 位数字':'';
          card.append(box('account-native',el('small','待核文字层 · 第 '+gap.line+' 行'+length,'small'),el('blockquote',gap.quote)));
        }
        const preview=()=>accountPreview(f,index.nodes.get(f.doc+'/p'+f.page));
        card.append(side.facts.length===1 ? preview() : lazyFold('预览这处引文的原页',()=>[preview()]),
          action('打开原页核对引文',()=>openPage(f.doc,f.page,f.id),'ref'));
        column.append(card);
      }
      columns.append(column);
    }
    const detail=comparable ? (first<0?'两处抄录逐位相同。':'两处抄录从左数第 '+(first+1)+' 位开始不同。')
      : gaps.join('，')+'，请对照原页核实完整账号。';
    return [el('p',detail,'account-difference'),columns];
  });
  details.classList.add('account-comparison');
  return details;
}

const invoiceMatchLabel = {same:'完整标识相同',uncertain:'资料不足，需核对',different:'同号异代码，已排除'};

function signedInvoiceSource(row, comparison=row.comparison) {
  const source = row.source;
  const basis = {native_line:'原生文字层匹配',field_check:'审计人员已核对原件与页图',
    historical_record:'历史底稿记载的票号',historical_confirmation:'历史人工确认记录'}[source.basis];
  const origin = Team.paperLink('查看签收版原页',row.case_id,'source-jump',new URLSearchParams({rev:row.rev,fact:row.fact}));
  origin.target='_blank'; origin.rel='noopener';
  const original = link('下载前案原件',Team.cases()+'/'+row.case_id+'/documents/'+row.doc+'/original?rev='+row.rev,'source-jump');
  const where = '第 '+row.page+' 页'+(source.line ? ' · 第 '+source.line+' 行' : '');
  const hashes = lazyFold('核对文件摘要',()=>[
    el('p','原件 SHA-256'),el('code',row.source_hash),el('p','页图 SHA-256'),el('code',row.page_hash),
    el('p','文字层 SHA-256'),el('code',source.text_sha256),el('p','签收底稿 SHA-256'),el('code',row.report_hash),
    el('p','人工签收 SHA-256'),el('code',row.signoff_hash)]);
  const panel=box('invoice-source',el('strong',row.title+' · R'+row.rev),
    el('small','人工决定 · '+statusName(row.decision)+' · '+time(source.signed_at),'small'),
    el('blockquote',row.quote),el('small',basis+' · '+where,'small'),box('chips',origin,original));
  if (comparison) panel.append(el('strong',invoiceMatchLabel[comparison]));
  if (row.identity?.kind==='short_unresolved') panel.append(el('p','前案八位号码缺少可唯一核准的同页代码。','muted'));
  for (const code of row.code_evidence || []) {
    const jump=Team.paperLink('查看代码原文',row.case_id,'source-jump',new URLSearchParams({rev:row.rev,fact:code.fact}));
    jump.target='_blank'; jump.rel='noopener';
    const location='第 '+code.page+' 页'+(code.line?' · 第 '+code.line+' 行':'');
    panel.append(box('line',el('blockquote',code.quote),el('small',location+' · '+statusName(code.status),'small'),jump));
  }
  panel.append(hashes);
  return panel;
}

function invoiceApproval(check, digest) {
  const tasks = new Set(check.matches.map(m=>m.case_id));
  const exact = new Set(check.matches.filter(m=>!m.comparison || m.comparison==='same').map(m=>m.case_id));
  const uncertain = new Set(check.matches.filter(m=>m.comparison==='uncertain').map(m=>m.case_id));
  const label = check.outcome==='no_usable_number' ? '本版缺少可查的已核票号' :
    check.outcome==='incomplete_number' ? '有票号仅列部分字符，签收时无法完整查重' :
    check.outcome==='insufficient_identity' ? '八位票号的同页代码待核' :
    check.outcome==='possible_match' ? tasks.size+' 份同号任务需核对代码或单据归属' :
    '已查 '+check.numbers.length+(check.format==='invoice-approval-v1'?' 个票号':' 个票据标识')+' · '+
      (exact.size ? '命中 '+exact.size+' 份已签收任务'+(uncertain.size?'，另有 '+uncertain.size+' 份含待核引文':'') : '未命中已签收任务');
  const panel = fold('签收时的同票检查',el('strong',label),
    el('p','查验范围为本企业当时已签收的任务。所据底稿 R'+check.source_rev+'，签收版 R'+check.signed_rev+'。','muted'));
  panel.classList.add('invoice-approval');
  const index = graphIndex(state.bundle.report.graph);
  for (const number of check.numbers) {
    panel.append(box('line',el('strong',(number.code?number.code+' / ':'')+number.value),box('chips',...number.facts.map(citation))));
  }
  for (const item of check.withheld || []) {
    panel.append(box('line',el('strong',item.value+' · 号码待补全'),citation(item.fact)));
  }
  for (const match of check.matches) {
    const id='prior/'+match.case_id+'/r'+match.rev+'/'+match.fact;
    const row=index.prior.get(id);
    if (row) panel.append(Team.paperLink(row.title+' · R'+match.rev+' · '+statusName(match.decision),match.case_id,'source-jump',
      new URLSearchParams({rev:match.rev,fact:match.fact})));
  }
  panel.append(lazyFold('核对回执摘要',()=>[el('p','回执 SHA-256'),el('code',digest),
    el('p','查验底稿 SHA-256'),el('code',check.source_sha256),el('p','人工签收内容 SHA-256'),el('code',check.decision_sha256)]));
  if (check.screened?.length) panel.append(lazyFold('查看签收时的同号候选（'+check.screened.length+'）',
    ()=>check.screened.map(row=>signedInvoiceSource(row))));
  return panel;
}

function traceEvidence(report, finding, index) {
  const supported = new Set(report.graph.edges.filter(e=>e.type==='supports_result' && e.to==='finding/'+finding.id).map(e=>e.from));
  const groups = new Map();
  const archived = new Map();
  const other = [];
  for (const ref of finding.evidence) {
    if (!supported.has(ref)) continue;
    const fact = index.facts.get(ref);
    if (fact) {
      if (!groups.has(fact.doc)) groups.set(fact.doc,[]);
      groups.get(fact.doc).push(fact);
    } else if (index.prior.has(ref)) {
      const prior = index.prior.get(ref);
      const group = prior.case_id + '/' + prior.rev;
      if (!archived.has(group)) archived.set(group,[]);
      archived.get(group).push(prior);
    } else if (index.nodes.get(ref)?.type==='page') {
      other.push(citation(ref));
    }
  }
  const panel = box('trace-part trace-sources',el('h3','取用的原文'));
  for (const [doc,facts] of groups) {
    const source = lazyFold((index.documents.get(doc)?.name || doc)+' · '+facts.length+' 条',()=>facts.map(f=>{
      const button = action(f.label+' · 第 '+f.page+' 页',()=>openPage(f.doc,f.page,f.id),'source-jump');
      return box('trace-quote',box('panel-head',button,tag(f.status)),el('blockquote',f.quote));
    }));
    panel.append(source);
  }
  for (const rows of archived.values()) {
    const first = rows[0];
    panel.append(lazyFold(first.title+' · R'+first.rev+' · '+statusName(first.decision),()=>rows.map(row=>
      row.source?.format==='signed-invoice-v1' ? signedInvoiceSource(row,finding.invoice_lookup?.candidates.find(c=>c.id===row.id)?.comparison) :
        box('trace-quote',citation(row.id),el('blockquote',row.quote)))));
  }
  if (other.length) panel.append(box('chips',...other));
  if (!groups.size && !archived.size && !other.length) {
    panel.append(el('p','本项没有可定位的取值引文。','muted'));
    if (finding.scope.length) panel.append(el('p','检查范围包含 '+finding.scope.map(id=>index.nodes.get(id)?.label || id).join('、')));
  }
  return panel;
}

function provenancePanel(report) {
  const graph = report.graph;
  const index = graphIndex(graph);
  const programs = new Map(graph.edges.filter(e=>e.type==='procedure_result').map(e=>[e.to,e.from]));
  const severity = {issue:0,risk:1,missing:2,ok:3};
  const findings = report.findings.filter(f=>programs.has('finding/'+f.id)).sort((a,b)=>severity[a.status]-severity[b.status]);
  if (!findings.length) return null;
  const select=el('select'); select.id='trace-select';
  const key=report.case_id+'@'+state.bundle.rev;
  for (const f of findings) {
    const option=new Option(statusName(f.status)+' · '+f.rule+' '+f.title,f.id);
    if (f.id===state.traceId && state.traceKey===key) option.selected=true;
    select.add(option);
  }
  const label = el('label','选择审计发现'); label.append(select);
  const trail = box('trace-grid');
  function render() {
    const f = findings.find(item=>item.id===select.value);
    state.traceKey=key; state.traceId=f.id;
    const control=programs.get('finding/'+f.id);
    const rule=index.nodes.get(control);
    const methods=graph.edges.filter(e=>e.type==='method_reference' && e.to===control).map(e=>index.nodes.get(e.from)).filter(Boolean);
    const program=box('trace-part',el('h3','执行程序'),el('strong',rule.label+' · '+f.title),el('p',rule.basis));
    if (methods.length) program.append(lazyFold('制度出处与适用范围',()=>methods.map(sourceEntry)));
    const result=box('trace-part trace-result',el('h3','本项结论'),tag(f.status),el('p',f.detail));
    if (f.calculations?.length) result.append(lazyFold('复算金额',()=>f.calculations.map(calculationPanel)));
    trail.replaceChildren(program,traceEvidence(report,f,index),result);
    if (f.rule==='B03') {
      const comparison=accountComparison(f,graph);
      if (comparison) trail.append(comparison);
    }
    if (f.rule==='B08' && graph.payment_history?.installments) {
      const details=installmentDetails(graph.payment_history.installments);
      details.classList.add('trace-installments'); trail.append(details);
    }
  }
  select.addEventListener('change',render); render();
  return box('panel trace-panel',el('h2','审计证据路径'),label,trail);
}
