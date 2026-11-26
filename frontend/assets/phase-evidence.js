// The controls read the issued finding and its own citations, including on historical revisions.
const PhaseEvidence = (() => {
  const priority=['issue','risk','missing','ok'];
  function combined(items) {
    return priority.find(status=>items.some(item=>item.status===status)) || 'missing';
  }
  function sameStage(left,right) {
    return left && right && ['clause_ref','name','clause','share'].every(key=>left[key]===right[key]);
  }
  function dateOn(fact) {
    const line=fact?.source_line;
    if (!line?.rects?.length || !['anchored','confirmed'].includes(fact.status)) return '';
    let text=line.text.normalize('NFKC').trim();
    if (fact.field==='warranty_release') {
      const confirm=/(?:双方确认)?质保期(?:已届满|届满|已满)$/u;
      if (!confirm.test(text)) return '';
      text=text.replace(confirm,'');
    }
    const match=text.match(/:\s*(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?\s*$/u);
    if (!match) return '';
    const iso=match[1]+'-'+match[2].padStart(2,'0')+'-'+match[3].padStart(2,'0');
    const value=Date.parse(iso+'T00:00:00Z');
    return Number.isFinite(value) && new Date(value).toISOString().slice(0,10)===iso ? iso : '';
  }
  function original(fact) {
    return fact && (()=>openPage(fact.doc,fact.page,fact.id));
  }
  const editionFields=new Set(['previous_payment_stage','revised_payment_stage','change_scope','change_timing','change_effect_clause','buyer_sealed_on','seller_sealed_on']);
  function amendmentLines(graph) {
    const ledger=graph?.quality_addenda?.payments;
    return ledger?.lines.filter(s=>editionFields.has(s.field) || s.field==='payment_stage' || !s.field) || [];
  }
  function amendmentFact(graph,item,ref) {
    const index=graphIndex(graph);
    if (!ref || !item.payment_change.evidence.includes(ref) || !item.evidence.includes(ref)
        || !index.supports.get('finding/'+item.id)?.has(ref)) return null;
    const fact=index.facts.get(ref);
    return fact?.source_line?.rects?.length && ['anchored','confirmed'].includes(fact.status)?fact:null;
  }
  function pageReferences(graph,doc,page,facts,lineHint) {
    const rows=graph?.invoice_receipt_sources?.lines || [];
    const sources=new Map();
    function add(s,label,quality,prefix,hasFact,rects=[]) {
      if (!s.line || s.doc!==doc || s.page!==page || sources.has(s.line)) return;
      if (hasFact ?? facts.some(f=>s.facts.includes(f.id) && f.quote===s.quote)) return;
      sources.set(s.line,{ref:prefix+s.line,rawLine:s.line,label,quote:s.quote,option:label+' · 第 '+s.line+' 行',quality,rects});
    }
    for (const row of PaymentAcceptance.sources(graph)) {
      const fact=PaymentAcceptance.observation(row,graph);
      add(row,'验收单号原行','payment_acceptance_reference','bank-acceptance-line/',Boolean(fact) && row.line!==lineHint,fact?.source_line?.rects);
    }
    for (const row of SignerEvidence.datedRows(graph)) {
      const fact=SignerEvidence.observation(graph,row);
      add(row,'具名签认日期','signer_date_source','signer-date-line/',Boolean(fact) && row.line!==lineHint,fact?.source_line.rects);
    }
    for (const row of PriorInstallment.sources(graph)) {
      const fact=PriorInstallment.observation(row,graph);
      add(row,'前款约定原行','prior_reference','prior-line/',row.line!==lineHint && Boolean(fact),fact?.source_line?.rects);
    }
    for (const row of InspectionCoverage.sources(graph)) {
      const fact=InspectionCoverage.observation(row,graph);
      add(row,'设备检验原行','inspection_reference','inspection-line/',row.line!==lineHint && Boolean(fact),fact?.source_line?.rects);
    }
    for (const s of SigningParties.sources(graph))
      add(s,'合同签章原行','contract_signing_reference','signing-line/',s.line!==lineHint && Boolean(SigningParties.observation(s,graph)),SigningParties.rectangles(s,graph));
    for (const s of graph?AcceptanceOpinion.rows(graph):[])
      add(s,'付款意见原行','acceptance_opinion_reference','payment-opinion-line/',s.line!==lineHint && Boolean(AcceptanceOpinion.observation(s,graph)));
    for (const s of graph?ReleaseEvidence.sources(graph):[]) if (!['title','identity'].includes(s.role))
      add(s,'放行依据原行','payment_release_reference','release-line/',s.line!==lineHint && Boolean(AcceptanceOpinion.observation(s,graph)));
    for (const s of rows) if (['clause','qualification','unreviewed'].includes(s.role))
      add(s,s.role==='clause'?'收票约定':'收票所据原行','invoice_receipt_reference','receipt-line/');
    for (const s of amendmentLines(graph)) add(s,'付款变更所据原行','payment_amendment_reference','payment-change-line/');
    return [...sources.values()];
  }
  function panel(phase,payments,findings,graph) {
    const gate=phase.invoice_receipt;
    const change=phase.payment_change;
    const index=graphIndex(graph);
    const {facts}=index;
    index.phaseViews ??= new Map();
    const inPhase=new Set(phase.evidence);
    const checkpoints=[],events=[];
    const warranty=WarrantyTimeline.panel(phase,payments,graph);
    const tickets=WarrantyTickets.panel(phase,payments,graph);
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
    function event(key,label,day,fact,status,payment) {
      if (day && fact) events.push({key,label,day,fact,status,payment,open:original(fact)});
    }
    const signed=findings.find(f=>f.rule==='H01');
    if (signed) {
      const day=unique(signed,'effect_on') || unique(signed,'signed_on');
      point('effect','合同生效','journal-text',signed.status,null,inspect(signed));
      event('effect',day?.field==='effect_on'?(change?'主合同生效日':'生效记载'):'合同签订',dateOn(day),day,signed.status);
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
      point('warranty','质保期满','shield-check',w.status,warranty?null:fact,warranty?()=>select('warranty'):inspect(phase));
      event('warranty','期满确认',w.confirmed_on,fact,w.status);
    }
    if (change) {
      const seal=change.effective_on===change.seller_on?change.seller_date_ref:change.buyer_date_ref;
      const fact=change.effective_on?amendmentFact(graph,phase,seal):null;
      point('amendment','协议生效','layers',fact?'ok':'missing',fact || amendmentFact(graph,phase,change.effect_ref),inspect(phase));
      event('amendment','协议生效',change.effective_on,fact,'ok');
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
      if (dates.length===1) event('paid',payment.warranty_payment?'回单落款':'实际付款',dateOn(dates[0]),dates[0],payment.status,payment);
    }
    const notes=AcceptanceOpinion.rows(graph,phase);
    const opinion=notes.length?AcceptanceOpinion.panel(phase,accepted,notes,graph):null;
    const release=opinion && phase.payment_opinion.release;
    if (release) {
      const matched=release.state==='matched', signatureDay=ReleaseEvidence.fact(graph,phase,release.date_ref);
      point('release','具名放行','journal-text',matched?'ok':'missing',null,()=>select('opinion'));
      const hold=notes.length===1 && notes[0].stance==='hold' ? notes[0] : null;
      const held=phase.payment_opinion.record_dates.find(d=>d.unit===hold?.unit && d.date===release.held_on);
      const mandate=ReleaseEvidence.one(ReleaseEvidence.sources(graph,phase),'authority');
      if (mandate && hold?.line && held && inPhase.has(held.ref) && phase.payment_opinion.evidence.includes(held.ref) &&
          index.supports.get('finding/'+phase.id)?.has(held.ref) && dateOn(facts.get(held.ref))===release.held_on) {
        const observation=AcceptanceOpinion.observation(hold,graph);
        events.push({key:'hold',label:'本期暂缓',day:release.held_on,status:'ok',
          open:()=>openPage(hold.doc,hold.page,observation?.id,observation?null:hold.line)});
      }
      if (matched && signatureDay?.field==='release_signed_on') event('release','签字放行',release.signed_on,signatureDay,'ok');
    }
    if (!checkpoints.length && !events.length && !opinion) return null;
    const root=el('section','','phase-evidence');
    root.setAttribute('aria-label',phase.stage.name+'履约证据');
    const controls=box('proof-switch');
    controls.setAttribute('role','group'); controls.setAttribute('aria-label','本期证据视图');
    const checks=box('proof-checkpoints'), rail=box('proof-rail');
    const tools=box('proof-tools');
    const count=el('span','','proof-count');
    const header=box('proof-header',box('proof-name',el('h3','本期证据'),count),controls);
    root.append(header);
    for (const payment of payments) {
      const edition=payment.payment_change;
      if (!edition) continue;
      const label={original:'原合同',amended:'补充协议',same_day:'同日待核',pending:edition.effective_on?'回单待核':'生效待核'}[edition.applies];
      const ref={original:edition.original_ref,amended:edition.revised_ref,same_day:edition.timing_ref,pending:edition.effect_ref}[edition.applies];
      const fact=amendmentFact(graph,payment,ref);
      const button=fact?action('',original(fact),'edition-source'):el('span','','edition-source');
      button.append(glyph('journal-text'),el('strong',label));
      if (fact) {
        button.append(glyph('arrows-angle-expand'));
        button.setAttribute('aria-label',label+'，查看'+(edition.applies==='same_day'?'适用时点':edition.applies==='pending'?'生效条件':'付款条款')+'原件');
      }
      const row=box('proof-edition',el('span','实付依据'),button);
      row.dataset.paymentEdition=edition.applies;
      if (edition.paid_on) {
        const when=el('time',edition.paid_on); when.dateTime=edition.paid_on; row.append(when);
      }
      if (payments.length>1) {
        const name=facts.get(edition.paid_ref)?.name;
        if (name) row.append(el('small',name));
      }
      root.append(row);
    }
    root.append(checks,rail,tools);
    if (opinion) root.insertBefore(opinion,tools);
    if (warranty) root.insertBefore(warranty,tools);
    if (tickets) root.insertBefore(tickets,tools);

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
    const groups=[];
    for (const entry of events) {
      const last=groups.at(-1);
      if ((change || release) && last?.[0].day===entry.day) last.push(entry);
      else groups.push([entry]);
    }
    for (const [i,entries] of groups.entries()) {
      const [first]=entries, shared=entries.length>1;
      const item=shared?box('proof-event proof-date-group'):action('',first.open,'proof-event');
      item.dataset.day=first.day; item.dataset.state=combined(entries);
      const when=el('time',first.day.slice(5).replace('-',' / ')); when.dateTime=first.day;
      const year=i===0 || groups[i-1][0].day.slice(0,4)!==first.day.slice(0,4) ? first.day.slice(0,4)+' 年' : '';
      const track=el('span','','proof-track'); track.setAttribute('aria-hidden','true'); track.append(el('i'));
      item.append(el('small',[year,shared?'同日 '+entries.length+' 项':''].filter(Boolean).join(' · ')),track,when);
      if (shared) {
        item.setAttribute('role','group'); item.setAttribute('aria-label',first.day+'，同日原件');
        const records=box('proof-day-list');
        for (const entry of entries) {
          const btn=action(entry.label,entry.open,'proof-day-action');
          btn.dataset.event=entry.key; btn.dataset.state=entry.status;
          btn.setAttribute('aria-label',entry.label+'，'+entry.day+'，'+statusName(entry.status)+'，打开原件');
          records.append(btn);
        }
        item.append(records);
      } else {
        item.dataset.event=first.key; item.append(el('span',first.label),
          el('span','。'+first.day+'，'+statusName(first.status)+'，打开原件','visually-hidden'));
      }
      rail.append(item);
    }
    let timing='';
    const dated=events.filter(e=>e.payment?.invoice_receipt?.status==='ok');
    const early=dated.filter(e=>e.status==='risk' && e.day<e.payment.invoice_receipt.receipt.received_on);
    if (early.length===1) {
      const e=early[0], days=(Date.parse(e.payment.invoice_receipt.receipt.received_on)-Date.parse(e.day))/86400000;
      timing='付款早于收票 '+days+' 天';
    } else if (early.length>1) timing=early.length+' 笔付款早于收票';
    else if (payments.some(p=>p.payment_change?.applies==='same_day')) timing='生效与实付同日 · 时分待核';
    else if (dated.some(e=>e.status==='missing' && e.day===e.payment.invoice_receipt.receipt.received_on)) timing='同日收付 · 时分待核';
    const released=payments.map(p=>p.payment_opinion?.release).filter(Boolean);
    const before=released.filter(r=>r.timing==='before');
    let releaseTiming='';
    if (before.length===1) releaseTiming='实付早于放行 '+(Date.parse(before[0].signed_on)-Date.parse(before[0].paid_on))/86400000+' 天';
    else if (before.length) releaseTiming=before.length+' 笔实付早于放行';
    else if (released.some(r=>r.timing==='same_day')) releaseTiming='放行与实付同日 · 时分待核';
    if (releaseTiming) timing=[releaseTiming,timing].filter(Boolean).join(' · ');
    const shortcuts=new Map();
    function linked(item,key,label,destination=tools,rightRef) {
      if (!shortcuts.has(item)) {
        const traced=traceReferences(graph,item).map(id=>facts.get(id)).filter(Boolean);
        shortcuts.set(item,new Map(EvidenceCompare.presets(item,traced,graph).map(p=>[p.key,p])));
      }
      const pair=shortcuts.get(item).get(key);
      if (!pair || rightRef && pair.right.id!==rightRef) return;
      const btn=action(label,()=>showFindingPath(item,true,key),'proof-pair');
      btn.prepend(glyph('layout-sidebar-inset-reverse')); btn.dataset.pair=key; destination.append(btn);
    }
    let more=tools;
    if (opinion) {
      const actions=box('proof-tools opinion-tools');
      const measured=opinion.querySelector('[data-measured-ref]')?.dataset.measuredRef;
      if (measured) linked(accepted,'reading','对照标准与实测',actions,measured);
      if (release) {
        linked(phase,'release-authority','对照签发权限',actions);
        if (release.state==='reference_mismatch') linked(phase,'release-receipt','对照验收单号',actions);
        for (const payment of payments) linked(payment,'release-transfer',payments.length===1?'对照放行与实付':'对照放行与实付 · '+payment.id,tools);
      }
      linked(phase,'opinion-conflict','对照两项意见',actions);
      for (const payment of payments) linked(payment,'opinion-transfer',payments.length===1?'对照意见与回单':'对照意见与回单 · '+payment.id,actions);
      if (actions.children.length) opinion.append(actions);
    }
    if (change) {
      linked(phase,'amendment-terms','对照新旧条款');
      for (const payment of payments) linked(payment,'amendment-payment-date',payments.length===1?'对照生效与实付':'对照生效与实付 · '+payment.id);
      const details=el('details','','proof-clauses proof-more');
      const summary=el('summary','更多凭据'); summary.append(glyph('chevron-down'));
      more=box('proof-tools'); details.append(summary,more); tools.append(details);
      linked(phase,'amendment-seals','对照双方盖章日期',more);
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
      more.append(details);
      linked(phase,'receipt-number','对照票号',more);
      for (const payment of payments) linked(payment,'receipt-payment-date',payments.length===1?'对照收付日期':'对照收付日期 · '+payment.id,more);
    }
    if (more!==tools && !more.children.length) more.parentElement.remove();
    const modes=[['checks','条件核对',checks],['timeline','时间线',rail],['warranty','质保时点',warranty],['tickets','维修工单',tickets],['opinion','付款意见',opinion]].filter(([, ,view])=>view?.children.length);
    function select(key) {
      index.phaseViews.set(phase.id,key);
      root.dataset.mode=key;
      for (const [mode,,view] of modes) {
        const active=mode===key;
        view.hidden=!active;
        controls.querySelector('[data-mode="'+mode+'"]').setAttribute('aria-pressed',String(active));
      }
      count.textContent=key==='tickets' || key==='warranty'?'':key==='opinion'?(release?ReleaseEvidence.caption(release,ReleaseEvidence.sources(graph,phase)):AcceptanceOpinion.caption(phase.payment_opinion)):key==='checks'?checkpoints.filter(s=>s.status==='ok').length+' / '+checkpoints.length+' 项相符':
        timing || events.length+' 项日期记录';
      count.classList.toggle('timing-alert',Boolean(timing && key==='timeline' || key==='opinion' && phase.payment_opinion.state!=='assent' && release?.state!=='matched'));
      if (key==='opinion') opinion.dispatchEvent(new Event('show-opinion'));
      if (key==='warranty') warranty.dispatchEvent(new Event('show-warranty'));
      if (key==='tickets') tickets.dispatchEvent(new Event('show-tickets'));
    }
    for (const [key,label] of modes) {
      const btn=action(label,()=>select(key),'proof-mode'); btn.dataset.mode=key; controls.append(btn);
    }
    let initial=modes[0][0];
    if (warranty) initial='warranty';
    if (tickets) initial='tickets';
    if (opinion && phase.payment_opinion.state!=='assent') initial='opinion';
    if (timing || change && events.some(e=>e.payment)) initial='timeline';
    select(index.phaseViews.get(phase.id) || initial);
    return root;
  }
  return {combined,sameStage,panel,pageReferences,amendmentLines,amendmentFact,dateOn};
})();
