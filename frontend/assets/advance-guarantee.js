// Show the advance-payment clause, guarantee and acknowledgment from the selected workpaper.
const AdvanceGuarantee = (() => {
  const fields={
    stage:'本期付款条款',term:'收函前提',buyer:'合同采购方',seller:'合同供应方',beneficiary:'保函受益人',recipient:'签收单位',
    number:'保函编号',receiptNumber:'签收保函编号',issued:'保函开立',received:'签收单记载',paid:'回单付款',
    contractId:'本合同编号',guaranteeContract:'保函引用合同',receiptContract:'签收单引用合同',paymentContract:'回单引用合同'
  };
  const legacy='advance-payment-guarantee-v1', current='advance-payment-guarantee-v2';
  const roles={
    clause:{clause:'term',period_clause:'periodClause'}, contract:{buyer:'buyer',seller:'seller',contract_id:'contractId'},
    guarantee:{beneficiary:'beneficiary',guarantee_id:'number',issued_on:'issued',contract_id:'guaranteeContract'},
    receipt:{recipient:'recipient',received_guarantee_id:'receiptNumber',received_on:'received',contract_id:'receiptContract'},
    payment:{paid_on:'paid',contract_id:'paymentContract',payer:'payer',payee:'payee',payment_designation:'designation',transfer_status:'transferStatus'}
  };
  const summary={before_receipt:'付款早于签收',same_day:'同日先后待核',after_receipt:'付款晚于签收',
    recorded:'已见签收记录',missing:'凭证待补',mismatch:'主体或编号待核',review:'原件待核'};
  const sameList=(a,b)=>Array.isArray(a) && Array.isArray(b) && a.length===b.length &&
    new Set(a).size===a.length && a.every(x=>b.includes(x)) && new Set(b).size===b.length;
  const quoteValue=quote=>quote.replace(/^[^：:]+[：:]\s*/u,'').trim();
  function validRects(rects) {
    return Array.isArray(rects) && rects.length>0 && rects.every(r=>Array.isArray(r) && r.length===4 &&
      r.every(n=>Number.isFinite(n) && n>=0 && n<=1) && r[0]<r[2] && r[1]<r[3]);
  }
  function issuedSource(row,ctx) {
    if (!row || !Array.isArray(row.facts) || typeof row.quote!=='string' || !row.quote) return null;
    const {item,graph,index,ledger,links,calls}=ctx, pageId=row.doc+'/p'+row.page;
    const doc=index.documents.get(row.doc), page=index.nodes.get(pageId), node=index.nodes.get(row.id);
    const owners=ledger.pages.filter(p=>p.doc===row.doc && p.page===row.page && p.unit===row.unit &&
      (p.role===(row.role==='clause'?'contract':row.role) || ledger.format===current && row.role==='extension' &&
        ['extension_note','attachment'].includes(row.field)));
    const raw=ledger.rows.filter(s=>s.id===row.id), edges=graph.edges.filter(e=>e.type==='advance_guarantee_source' && e.to===row.id);
    if (raw.length!==1 || owners.length!==1 || edges.length!==1 || node?.type!=='advance_guarantee_line' ||
        node.label!==row.quote || raw[0].quote!==row.quote || !doc?.sha256 || doc.sha256!==row.original_sha256 ||
        index.nodes.get(doc.id)?.sha256!==doc.sha256 || page?.type!=='page' || page.sha256!==row.page_sha256 ||
        owners[0].original_sha256!==doc.sha256 || owners[0].page_sha256!==page.sha256 ||
        !['role','field','doc','unit','page','line','page_sha256','original_sha256'].every(k=>raw[0][k]===row[k] && node[k]===row[k]) ||
        !sameList(raw[0].facts,row.facts) || edges[0].from!==pageId || !sameList(edges[0].evidence,[pageId,...row.facts]) ||
        !item.scope?.includes(row.unit) || ![row.id,row.doc,pageId,...row.facts].every(ref=>item.evidence.includes(ref) && links.has(ref+' finding/'+item.id))) return null;
    const recordedUnit=graph.audit_documents?.find(d=>d.source===row.doc && d.page===row.page)?.id || row.doc;
    if (row.unit!==recordedUnit || !row.facts.every(id=>{
      const f=index.facts.get(id);
      return f?.doc===row.doc && f.page===row.page && (f.unit || f.doc)===row.unit &&
        f.source_sha256===doc.sha256 && f.page_sha256===page.sha256 && links.has(pageId+' '+id);
    })) return null;
    const trace=calls.filter(p=>p.doc===row.doc && p.page===row.page && p.page_sha256===page.sha256);
    if (trace.length!==1) return null;
    const located=Number.isSafeInteger(row.line) && row.line>0 && owners[0].clean && page.layer==='text' &&
      page.text_sha256 && validRects(row.rects) && JSON.stringify(raw[0].rects)===JSON.stringify(row.rects) &&
      JSON.stringify(trace[0].advance_guarantee_rects?.[row.line])===JSON.stringify(row.rects);
    if (row.line!==null && !located || row.line===null && (!Array.isArray(row.rects) || row.rects.length)) return null;
    const field=roles[row.role]?.[row.field];
    const open=()=>{
      if (state.bundle?.report!==ctx.report) return;
      if (!located) { openPage(row.doc,row.page); return; }
      const label=fields[field] || row.quote.split(/[:：]/u,1)[0];
      const anchor={ref:row.id,label,option:label+' · 第 '+row.line+' 行',quality:'advance_guarantee_source',
        rawLine:row.line,quote:row.quote,rects:row.rects};
      OriginalReader.open(doc,row.page,{lineHint:row.line,rawRef:row.id,printedSource:anchor});
    };
    const excerpt=located?()=>state.bundle?.report===ctx.report &&
      EvidenceCompare.lineExcerpt({doc:row.doc,page:row.page,source_line:{rects:row.rects}},index):null;
    return {...row,fieldKey:field,file:doc.name,value:located?quoteValue(row.quote):'',open,excerpt};
  }
  const views=new WeakMap();
  function resolve(item,report) {
    if (!item?.advance_guarantee || !report) return null;
    let items=views.get(report);
    if (!items) { items=new WeakMap(); views.set(report,items); }
    if (!items.has(item)) items.set(item,bind(item,report));
    return items.get(item);
  }
  function bind(item,report) {
    const proof=item?.advance_guarantee, graph=report?.graph, ledger=graph?.advance_guarantee_sources;
    if (!proof || !['H04','H05'].includes(item.rule) || ![legacy,current].includes(ledger?.format) || report.policy?.advance_guarantee!==ledger.format ||
        !Array.isArray(ledger.rows) || !Array.isArray(ledger.pages) || !Array.isArray(proof.sources) || !Array.isArray(proof.evidence) ||
        !Array.isArray(item.evidence) || !Array.isArray(item.scope) || typeof proof.detail!=='string' || !proof.detail) return null;
    if (ledger.format===current && (!(report.policy.version>='2026.11.27.06') ||
        !['advance_guarantee.py','guarantee_period.py'].every(name=>/^[a-f0-9]{64}$/.test(report.policy.code_sha256?.[name])))) return null;
    const index=graphIndex(graph), finding=index.nodes.get('finding/'+item.id);
    if (finding?.type!=='finding' || finding.status!==item.status || finding.detail!==item.detail) return null;
    const linked=new Map(), byId=new Map();
    function add(key,row) {
      byId.set(row.id,row);
      if (key && row.line) {
        if (!linked.has(key)) linked.set(key,[]);
        linked.get(key).push(row);
      }
    }
    const stage=PerformanceIndex.originals(item,graph).find(s=>s.fact.id===item.stage?.clause_ref && s.fact.field==='payment_stage' && s.line);
    if (stage) {
      const f=stage.fact;
      add('stage',{id:f.id,doc:f.doc,page:f.page,line:stage.line,file:stage.doc.name,quote:f.source_line.text,
        value:quoteValue(f.source_line.text),open:()=>{ if (state.bundle?.report===report) openPage(f.doc,f.page,f.id); },
        excerpt:()=>state.bundle?.report===report && EvidenceCompare.lineExcerpt(f,index)});
    }
    const ctx={item,report,graph,ledger,index,links:PerformanceIndex.fieldLinks(graph),calls:report.calls?.pages || []};
    const refs=new Set(proof.sources.flatMap(s=>s && Array.isArray(s.facts)?[s.id,s.doc,s.doc+'/p'+s.page,...s.facts]:[]));
    let bound=Boolean(stage) && refs.size>0 && sameList([...refs],proof.evidence) && proof.evidence.every(ref=>item.evidence.includes(ref));
    for (const input of proof.sources) {
      const row=issuedSource(input,ctx);
      if (!row || byId.has(row.id)) { bound=false; continue; }
      add(row.fieldKey,row);
    }
    const outcome=proof.state, paid=item.rule==='H05';
    let label=summary[outcome], subjectFirst=false, elapsed=null;
    function single(key) { const rows=linked.get(key); return rows?.length===1?rows[0]:null; }
    const term=single('term'), buyer=single('buyer')?.value, contract=single('contractId')?.value;
    const owner=stage?.fact.unit || stage?.fact.doc;
    if (!term || !label || !item.detail.includes(proof.detail) || term.unit!==owner ||
        !sameList(graph.documents_by_kind?.contract,[owner]) || !graph.edges.some(e=>e.type==='payment_stage' &&
          e.from===owner && sameList(e.evidence,[stage?.fact.id]))) bound=false;
    if (['before_receipt','same_day','after_receipt','recorded'].includes(outcome)) {
      const issued=dateValue(single('issued')?.value || ''), acknowledged=dateValue(single('received')?.value || '');
      const payment=dateValue(single('paid')?.value || '');
      const related=buyer && ['beneficiary','recipient'].every(k=>single(k)?.value===buyer) &&
        contract && ['guaranteeContract','receiptContract'].every(k=>single(k)?.value===contract) &&
        single('number')?.value && single('number').value===single('receiptNumber')?.value;
      bound=bound && Boolean(related && issued && acknowledged && issued<=acknowledged && issued===proof.issued_on && acknowledged===proof.received_on);
      if (outcome==='recorded') bound=bound && !paid;
      else bound=bound && paid && payment && payment===proof.paid_on && single('paymentContract')?.value===contract &&
        single('payer')?.value===buyer && single('payee')?.value===single('seller')?.value &&
        ['交易成功','转账成功','成功','已完成'].includes(single('transferStatus')?.value) &&
        ({before_receipt:payment<acknowledged,same_day:payment===acknowledged,after_receipt:payment>acknowledged})[outcome];
      if (bound && paid && payment!==acknowledged)
        elapsed=Math.abs(Date.parse(payment)-Date.parse(acknowledged))/86400000;
    } else if (outcome==='mismatch') {
      subjectFirst=true;
      if (proof.status==='risk' && /(?:采购方|买方|甲方)为受益人/u.test(term?.quote || '') && contract &&
          single('guaranteeContract')?.value===contract && buyer && single('beneficiary') && single('beneficiary').value!==buyer)
        label='受益人与约定不符';
    } else if (outcome==='missing' && single('number') && !single('received')) label='签收依据待补';
    if (!bound) { label='依据待核'; subjectFirst=false; }
    const documented=bound && ['recorded','after_receipt'].includes(outcome);
    const period=ledger.format===current && (proof.period || linked.has('periodClause'))?
      bindPeriod(proof,ctx,byId,owner,bound):null;
    return {fields:linked,byId,paid,paidOn:bound?proof.paid_on:null,state:bound?outcome:'unverified',label,subjectFirst,elapsed,documented,period,
      tone:documented?'documented':bound && proof.status==='issue'?'issue':'review'};
  }

  function dateValue(text) {
    return GuaranteePeriodCard.iso(text);
  }

  function bindPeriod(proof,ctx,byId,owner,bound) {
    const {item,ledger}=ctx, p=proof.period, paidItem=item.rule==='H05';
    const evidence=Array.from(byId.values()).filter(row=>row.role);
    const take=(role,...fields)=>evidence.filter(row=>row.role===role && fields.includes(row.field));
    const rows={clause:take('clause','period_clause'),start:take('guarantee','valid_from'),
      end:take('guarantee','valid_until','valid_until_inclusive'),paid:take('payment','paid_on'),
      extension:evidence.filter(row=>row.field==='extension_note'),
      unknown:evidence.filter(row=>row.field==='period_note' || row.role==='extension' && row.field!=='extension_note')};
    const physical=key=>rows[key].length===1 && rows[key][0].line?dateValue(rows[key][0].value):null;
    const start=physical('start'),end=physical('end'),paid=physical('paid');
    const held={state:'review',start:null,end:null,paid:null,inclusive:null,rows:{...rows,
      unknown:[...rows.unknown,...rows.start,...rows.end,...rows.paid]}};
    if (!p || !bound || !Array.isArray(p.sources) || !sameList(p.sources.map(s=>s?.id),proof.sources.map(s=>s.id)) ||
        !sameList(p.evidence,proof.evidence) || !sameList(p.units,proof.units) || !sameList(p.units,[...new Set(evidence.map(s=>s.unit))]) ||
        !p.units.every(unit=>item.scope.includes(unit)) || !p.detail || !item.detail.includes(p.detail)) return held;
    // Both projections must be identical to the individual rows already verified against this revision.
    if (!p.sources.every(s=>{
      const row=byId.get(s.id);
      return row && ['field','role','doc','unit','page','line','quote','original_sha256','page_sha256'].every(k=>s[k]===row[k]) &&
        sameList(s.facts,row.facts) && JSON.stringify(s.rects)===JSON.stringify(row.rects);
    })) return held;
    if (ledger.rows.some(s=>(['guarantee','receipt','extension'].includes(s.role) ||
        s.role==='clause' && s.unit===owner || s.role==='payment' && p.units.includes(s.unit)) && !byId.has(s.id))) return held;
    const clause=rows.clause.length===1 && rows.clause[0];
    if (!clause?.line || clause.unit!==owner || !/^保函有效期要求[:：]\s*(?:第[一1]期|首期)预付款的付款日须在本合同项下的?预付款保函的有效期内。?$/u.test(clause.quote.trim()) ||
        !['recorded','after_receipt','before_receipt','same_day'].includes(proof.state)) return held;
    const inclusive=end && rows.end[0].field==='valid_until_inclusive'?true:null;
    if (p.valid_from!==start || p.valid_until!==end || p.end_inclusive!==inclusive || p.paid_on!==paid ||
        paid!==proof.paid_on || paid && !paidItem) return held;
    let state='review';
    if (rows.extension.length) state='extension_review';
    else if (!rows.unknown.length && start && end && start<=end && end>=proof.issued_on) {
      if (!paidItem) state='stated';
      else if (paid) {
        if (paid<start) state='before_start';
        else if (paid>end) state='expired';
        else if (paid===end && !inclusive) state='end_unspecified';
        else if (paid!==start || paid===end) state='covered';
      }
    }
    const status=['before_start','expired'].includes(state)?'risk':'missing';
    return state===p.state && status===p.status && ['risk','issue',...(status==='missing'?['missing']:[])].includes(item.status)?
      {state,start,end,paid,inclusive,rows}:held;
  }

  function sourceButton(row,label,content) {
    const button=action('',row.open,'guarantee-source');
    button.dataset.source=row.id;
    button.setAttribute('aria-haspopup','dialog'); button.setAttribute('aria-controls','page-dialog');
    button.setAttribute('aria-description',row.file+'，第 '+row.page+' 页'+(row.line?'第 '+row.line+' 行，'+row.quote:'，查看整页'));
    button.append(box('guarantee-source-body',el('span',label),el('strong',content)),glyph('arrows-angle-expand'));
    return button;
  }

  function dates(view) {
    const list=el('ol','','guarantee-dates'), days=new Map(), uncertain=[];
    const keys=view.paid?['issued','received','paid']:['issued','received'];
    for (const key of keys) {
      const rows=view.fields.get(key) || [];
      if (!rows.length) uncertain.push({key});
      for (const row of rows) {
        const value=dateValue(row.value);
        if (!value) { uncertain.push({key,row}); continue; }
        if (!days.has(value)) days.set(value,[]);
        days.get(value).push({key,row});
      }
    }
    for (const date of [...days.keys()].sort()) {
      const item=el('li'), time=el('time',date.replaceAll('-','.')), entries=box('guarantee-day-sources');
      time.dateTime=date;
      for (const {key,row} of days.get(date)) {
        const label=key==='paid' && date!==view.paidOn?'回单日期 · 执行待核':fields[key];
        const button=sourceButton(row,label,row.file);
        button.dataset.event=key; entries.append(button);
      }
      item.append(time,entries); list.append(item);
    }
    for (const {key,row} of uncertain) {
      const item=el('li','','guarantee-undated');
      item.append(el('span','待核','guarantee-undated-label'),row?
        sourceButton(row,fields[key],row.value):el('span',({issued:'开立日期待核',received:'签收日期待核',paid:'付款日期待核'})[key],'guarantee-no-source'));
      list.append(item);
    }
    return list;
  }

  function rows(view,keys) {
    const list=box('guarantee-lines');
    const seen=new Set();
    for (const key of keys) {
      const sources=view.fields.get(key) || [];
      if (!sources.length) {
        if (key!=='stage' && key!=='term') list.append(el('p',fields[key]+'待核','guarantee-no-source'));
        continue;
      }
      for (const row of sources) {
        const location=row.doc+'/p'+row.page+'/l'+row.line;
        if (seen.has(location)) continue;
        const button=sourceButton(row,fields[key],row.value);
        if (key==='beneficiary' && view.label==='受益人与约定不符') button.dataset.discrepancy='true';
        seen.add(location); list.append(button);
      }
    }
    if (!list.childElementCount) list.append(el('p','合同条款原行待核','guarantee-no-source'));
    return list;
  }
  function parties(view) {
    const list=rows(view,['recipient']);
    list.classList.add('guarantee-parties');
    const names=rows(view,['buyer','beneficiary']), references=rows(view,['number','receiptNumber']);
    names.classList.add('guarantee-pair'); references.classList.add('guarantee-pair');
    list.prepend(names); list.append(references);
    const numbers=['contractId','guaranteeContract','receiptContract',...(view.paid?['paymentContract']:[])];
    if (numbers.some(k=>view.fields.has(k))) list.append(fold('核对合同编号',rows(view,numbers)));
    return list;
  }

  function panel(item,report) {
    const view=resolve(item,report);
    if (!view) return null;
    const section=el('section','','advance-guarantee');
    section.dataset.state=view.state;
    if (view.period) section.classList.add('has-period');
    const label=el('h4','预付款保函');
    label.id='guarantee-heading-'+item.id; section.setAttribute('aria-labelledby',label.id);
    const status=el('span','','guarantee-status');
    section.append(box('guarantee-heading',box('guarantee-title',glyph('file-earmark-text'),label),status));
    const tabs=box('guarantee-tabs'), body=box('guarantee-panel');
    tabs.setAttribute('role','tablist'); tabs.setAttribute('aria-label','核对预付款保函');
    body.id='guarantee-panel-'+item.id; body.setAttribute('role','tabpanel');
    const toggle=el('input'); toggle.type='checkbox'; toggle.setAttribute('role','switch'); toggle.setAttribute('aria-controls',body.id);
    const switcher=el('label','','guarantee-switch');
    switcher.append(toggle,el('span','看原行'));
    function showOriginalLines() {
      body.dataset.originals=String(toggle.checked);
      for (const button of body.querySelectorAll('.guarantee-source')) {
        button.querySelector('.guarantee-strip')?.remove();
        const row=view.byId.get(button.dataset.source);
        if (!toggle.checked || !row?.excerpt) continue;
        const strip=el('span','','guarantee-strip'), quote=el('span',row.quote);
        strip.append(el('small','原文抄录'),quote); button.append(strip);
        Promise.resolve(row.excerpt()).then(canvas=>{
          if (!canvas || !button.contains(strip) || state.bundle?.report!==report) return;
          canvas.setAttribute('aria-hidden','true');
          strip.replaceChildren(canvas); strip.dataset.image='true';
        }).catch(()=>{ /* The issued quotation remains readable if the page image cannot load. */ });
      }
    }
    toggle.addEventListener('change',showOriginalLines);
    body.addEventListener('guarantee-day-change',showOriginalLines);
    const choices=[
      ['dates','单据日期',()=>dates(view)],
      ['parties','主体与编号',()=>parties(view)],
      ['clause','合同约定',()=>rows(view,['term','stage'])]
    ];
    if (view.period) choices.unshift(['period','保函期间',()=>GuaranteePeriodCard.render(view.period,'period-'+item.id,(row,title)=>
      sourceButton(row,title+' · 第 '+row.page+' 页'+(row.line?' / '+row.line+' 行':''),row.file))]);
    function select(position) {
      for (const [i,tab] of Array.from(tabs.children).entries()) {
        tab.tabIndex=i===position?0:-1; tab.setAttribute('aria-selected',String(i===position));
      }
      body.dataset.tab=choices[position][0]; body.setAttribute('aria-labelledby',tabs.children[position].id);
      const period=body.dataset.tab==='period';
      const shown=period?GuaranteePeriodCard.describe(view.period):view;
      status.textContent=shown.label; status.dataset.tone=shown.tone;
      if (!period && view.elapsed!==null) status.append(el('b',String(view.elapsed),'guarantee-elapsed'),document.createTextNode('天'));
      body.replaceChildren(choices[position][2]());
      showOriginalLines();
    }
    for (const [i,[key,title]] of choices.entries()) {
      const tab=action(title,()=>select(i));
      if (view.period) {
        const compact={period:'期间',dates:'收函',parties:'主体',clause:'条款'};
        tab.replaceChildren(el('span',title,'guarantee-tab-full'),el('span',compact[key],'guarantee-tab-short'));
        tab.setAttribute('aria-description',title);
      }
      tab.setAttribute('role','tab'); tab.id='guarantee-'+item.id+'-'+key;
      tab.setAttribute('aria-controls',body.id);
      tab.addEventListener('keydown',event=>{
        const n=choices.length,next={ArrowRight:(i+1)%n,ArrowLeft:(i+n-1)%n,Home:0,End:n-1}[event.key];
        if (next===undefined) return;
        event.preventDefault(); select(next); tabs.children[next].focus();
      });
      tabs.append(tab);
    }
    select(view.subjectFirst?choices.findIndex(([key])=>key==='parties'):0);
    section.append(box('guarantee-tools',tabs,switcher),body);
    if (view.documented) section.append(box('guarantee-followup',glyph('eye'),el('span','待人工核验保函真伪、效力及付款授权')));
    const held=new Map();
    for (const row of view.byId.values()) if (row.line===null) held.set(row.doc+'/p'+row.page,row);
    if (held.size) section.append(fold('待核原页 · '+held.size,...Array.from(held.values(),
      row=>sourceButton(row,'第 '+row.page+' 页',row.file))));
    return section;
  }
  function open(item) {
    document.querySelector('[data-audit-scope="payment"]')?.dispatchEvent(new CustomEvent('open-payment-stage',{detail:item.id}));
  }
  function jump(item,label='核对预付款保函') {
    const button=action(label,()=>open(item),'text-button');
    button.setAttribute('aria-haspopup','dialog'); button.setAttribute('aria-controls','performance-index');
    return button;
  }
  function citation(ref,finding,report) {
    const matches=finding && typeof finding==='object'?[finding]:report?.findings?.filter(f=>f.advance_guarantee?.evidence.includes(ref)) || [];
    const row=matches.map(f=>resolve(f,report)?.byId.get(ref)).find(Boolean);
    return row?action(row.line?row.quote:row.file+' · 第 '+row.page+' 页',row.open,'ref'):null;
  }
  function receiptName(item,report) {
    const names=new Set();
    for (const row of resolve(item,report)?.byId.values() || []) if (row.role==='payment') names.add(row.file);
    return names.size===1?[...names][0]:item.id;
  }
  return {panel,jump,open,citation,receiptName};
})();
