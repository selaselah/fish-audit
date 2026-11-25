// The controls read the issued finding and its own citations, including on historical revisions.
const PhaseEvidence = (() => {
  const priority=['issue','risk','missing','ok'];
  function combined(items) {
    return priority.find(status=>items.some(item=>item.status===status)) || 'missing';
  }
  function dateOn(fact) {
    const line=fact?.source_line;
    if (!line?.rects?.length || !['anchored','confirmed'].includes(fact.status)) return '';
    const match=line.text.normalize('NFKC').match(/:\s*(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?\s*$/u);
    if (!match) return '';
    const iso=match[1]+'-'+match[2].padStart(2,'0')+'-'+match[3].padStart(2,'0');
    const value=Date.parse(iso+'T00:00:00Z');
    return Number.isFinite(value) && new Date(value).toISOString().slice(0,10)===iso ? iso : '';
  }
  function original(fact) {
    return fact && (()=>openPage(fact.doc,fact.page,fact.id));
  }
  function pageReferences(graph,doc,page,facts) {
    const rows=graph?.invoice_receipt_sources?.lines || [];
    return rows.filter(s=>s.doc===doc && s.page===page && s.line &&
      ['clause','qualification','unreviewed'].includes(s.role) && !facts.some(f=>s.facts.includes(f.id) && f.quote===s.quote))
      .map(s=>{
        const label=s.role==='clause'?'收票约定':'收票所据原行';
        return {ref:'receipt-line/'+s.line,rawLine:s.line,label,quote:s.quote,option:label+' · 第 '+s.line+' 行',
          quality:'invoice_receipt_reference',rects:[]};
      });
  }
  function panel(phase,payments,findings,graph) {
    const gate=phase.invoice_receipt;
    const index=graphIndex(graph);
    const {facts}=index;
    index.phaseViews ??= new Map();
    const inPhase=new Set(phase.evidence);
    const checkpoints=[],events=[];
    function unique(item,field) {
      const matches=(item?.evidence || []).map(id=>facts.get(id)).filter(f=>f?.field===field && inPhase.has(f.id));
      return matches.length===1 ? matches[0] : null;
    }
    function inspect(item) {
      return ()=>revealPaperTarget(document.querySelector('[data-finding="'+CSS.escape(item.id)+'"]'));
    }
    function point(key,label,icon,status,fact,actionIfMissing,caption) {
      checkpoints.push({key,label,icon,status,caption,open:original(fact) || actionIfMissing});
    }
    function event(key,label,day,fact,status) {
      if (day && fact) events.push({key,label,day,fact,status,open:original(fact)});
    }
    const signed=findings.find(f=>f.rule==='H01');
    if (signed) {
      const day=unique(signed,'effect_on') || unique(signed,'signed_on');
      point('effect','合同生效','journal-text',signed.status,null,inspect(signed));
      event('effect',day?.field==='effect_on'?'生效记载':'合同签订',dateOn(day),day,signed.status);
    }
    const plan=findings.find(f=>f.rule==='H03');
    if (plan && plan.status!=='ok') point('schedule','付款约定','layers',plan.status,null,inspect(plan));
    const accepted=findings.find(f=>f.rule==='H02');
    const relevant=accepted?.evidence.some(ref=>inPhase.has(ref) && ['accepted_on','acceptance_result','acceptance_scope'].includes(facts.get(ref)?.field));
    if (relevant) {
      const day=unique(accepted,'accepted_on');
      point('acceptance','交付验收','clipboard-check',accepted.status,null,inspect(accepted));
      event('acceptance','交付验收',dateOn(day),day,accepted.status);
    }
    if (phase.warranty_check) {
      const w=phase.warranty_check, fact=unique(phase,'warranty_release');
      point('warranty','质保期满','shield-check',w.status,fact,inspect(phase));
      event('warranty','期满确认',w.confirmed_on,fact,w.status);
    }
    if (gate) {
      const bill=gate.invoice, ack=gate.receipt;
      if (!gate.scope_clear) {
        const row=gate.clauses[0], fact=row.facts.map(id=>facts.get(id)).find(f=>f?.quote===row.quote);
        point('terms','收票约定','journal-text','missing',fact,()=>openPage(row.doc,row.page,null,row.line));
      }
      point('invoice','对应发票','receipt',bill.status,facts.get(bill.number_ref));
      let caption;
      if (ack.status!=='ok') {
        if (bill.number && ack.number && /^[0-9]{20}$/.test(bill.number) && /^[0-9]{20}$/.test(ack.number) && bill.number!==ack.number) caption='票号不符';
        else if (!ack.number_ref && !ack.seal_ref && !ack.date_ref) caption='待补签收';
      }
      const ref=ack.status==='ok'?ack.seal_ref:ack.number_ref || ack.seal_ref || ack.date_ref;
      point('receipt','买方收票','inboxes',ack.status,facts.get(ref),null,caption);
      event('issued','发票开具',bill.issued_on,facts.get(bill.date_ref),bill.status);
      event('received',ack.status==='ok'?'买方收票':'签收登记',ack.received_on,facts.get(ack.date_ref),ack.status);
    }
    for (const payment of payments) {
      const dates=payment.evidence.map(id=>facts.get(id)).filter(f=>f?.field==='paid_on');
      if (dates.length===1) event('paid','实际付款',dateOn(dates[0]),dates[0],payment.status);
    }
    if (!checkpoints.length && !events.length) return null;
    const root=el('section','','phase-evidence');
    root.setAttribute('aria-label',phase.stage.name+'履约证据');
    const controls=box('proof-switch');
    controls.setAttribute('role','group'); controls.setAttribute('aria-label','本期证据视图');
    const checks=box('proof-checkpoints'), rail=box('proof-rail');
    const tools=box('proof-tools');
    const count=el('span','','proof-count');
    const header=box('proof-header',box('proof-name',el('h3','本期证据'),count),controls);
    root.append(header,checks,rail,tools);

    for (const step of checkpoints) {
      const tile=step.open?action('',step.open,'proof-check'):el('div','','proof-check');
      tile.dataset.check=step.key; tile.dataset.state=step.status;
      const status=tag(step.status);
      if (step.caption) status.textContent=step.caption;
      tile.append(glyph(step.icon),el('strong',step.label),status);
      if (step.open) tile.append(el('span',(step.caption?'，'+statusName(step.status):'')+'，查看依据','visually-hidden'));
      checks.append(tile);
    }
    events.sort((a,b)=>a.day.localeCompare(b.day));
    for (const [i,entry] of events.entries()) {
      const btn=action('',entry.open,'proof-event');
      btn.dataset.event=entry.key; btn.dataset.state=entry.status;
      const when=el('time',entry.day.slice(5).replace('-',' / ')); when.dateTime=entry.day;
      const year=i===0 || events[i-1].day.slice(0,4)!==entry.day.slice(0,4) ? entry.day.slice(0,4)+' 年' : '';
      const track=el('span','','proof-track'); track.setAttribute('aria-hidden','true'); track.append(el('i'));
      btn.append(el('small',year),track,when,el('span',entry.label));
      btn.append(el('span','。'+entry.day+'，'+statusName(entry.status)+'，打开原件','visually-hidden'));
      rail.append(btn);
    }
    let timing='';
    if (gate?.status==='ok' && gate.receipt.received_on) {
      const received=Date.parse(gate.receipt.received_on+'T00:00:00Z');
      const early=events.filter(e=>e.key==='paid' && e.status==='risk' && Date.parse(e.day+'T00:00:00Z')<received);
      if (early.length===1) timing='付款早于收票 '+Math.round((received-Date.parse(early[0].day+'T00:00:00Z'))/86400000)+' 天';
      else if (early.length>1) timing=early.length+' 笔付款早于收票';
      else if (events.some(e=>e.key==='paid' && e.status==='missing' && e.day===gate.receipt.received_on)) timing='同日收付 · 时分待核';
    }
    if (gate) {
      const lines=[...gate.clauses,...gate.qualifications];
      const details=el('details','','proof-clauses');
      const summary=el('summary',gate.scope_clear?'收票条款原文':'收票条款待核');
      summary.prepend(glyph('journal-text')); summary.append(glyph('chevron-down'));
      details.append(summary);
      for (const line of lines) {
        const source=reservationSource(line,graph);
        source.classList.add('proof-line');
        details.append(source);
      }
      tools.append(details);
      const linked=(item,key,label)=>{
        const traced=traceReferences(graph,item).map(id=>facts.get(id)).filter(Boolean);
        if (!EvidenceCompare.presets(item,traced,graph).some(p=>p.key===key)) return;
        const btn=action(label,()=>showFindingPath(item,true,key),'proof-pair');
        btn.prepend(glyph('layout-sidebar-inset-reverse')); btn.dataset.pair=key; tools.append(btn);
      };
      linked(phase,'receipt-number','对照票号');
      for (const payment of payments) linked(payment,'receipt-payment-date',payments.length===1?'对照收付日期':'对照收付日期 · '+payment.id);
    }
    const modes=[['checks','条件核对',checks],['timeline','时间线',rail]].filter(([, ,view])=>view.children.length);
    function select(key) {
      index.phaseViews.set(phase.id,key);
      root.dataset.mode=key;
      for (const [mode,,view] of modes) {
        const active=mode===key;
        view.hidden=!active;
        controls.querySelector('[data-mode="'+mode+'"]').setAttribute('aria-pressed',String(active));
      }
      count.textContent=key==='checks'?checkpoints.filter(s=>s.status==='ok').length+' / '+checkpoints.length+' 项相符':
        timing || events.length+' 项日期记录';
      count.classList.toggle('timing-alert',Boolean(timing && key==='timeline'));
    }
    for (const [key,label] of modes) {
      const btn=action(label,()=>select(key),'proof-mode'); btn.dataset.mode=key; controls.append(btn);
    }
    select(index.phaseViews.get(phase.id) || (timing?'timeline':modes[0][0]));
    return root;
  }
  return {combined,panel,pageReferences};
})();
