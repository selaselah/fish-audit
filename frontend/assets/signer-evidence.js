const SignerEvidence = (() => {
  const clockFormat='named-acceptance-signatures-v5';
  const formats = ['named-acceptance-signatures-v2','named-acceptance-signatures-v3','named-acceptance-signatures-v4',clockFormat];
  function datedRows(graph, clocks=false) {
    const ledger = graph?.acceptance_authority_sources;
    if (!formats.includes(ledger?.format)) return [];
    const index = graphIndex(graph);
    const type=clocks?'acceptance_clock_line':'acceptance_signer_date';
    const links = new Map(graph.edges.filter(e=>e.type===(clocks?'acceptance_clock_source':'signer_date_source')).map(e=>[e.to,e]));
    const rows=clocks ? (ledger.format===clockFormat && ledger.clock_rows || []) : ledger.dates;
    if (!Array.isArray(rows)) return [];
    return rows.filter(row=>{
      const pageId=row.doc+'/p'+row.page, pg=index.nodes.get(pageId), doc=index.documents.get(row.doc);
      const node=index.nodes.get(row.id), edge=links.get(row.id);
      return pg?.sha256 && doc?.sha256 && index.nodes.get(row.doc)?.sha256===doc.sha256 &&
        (clocks && row.kind!=='signer'?ledger.bank_pages:ledger.pages).some(p=>p.doc===row.doc && p.page===row.page && p.unit===row.unit) &&
        node?.type===type && node.label===row.quote && node.doc===row.doc &&
        node.page===row.page && node.line===row.line && edge?.from===pageId && edge.evidence[0]===pageId && Array.isArray(row.facts) &&
        edge.evidence.length===1+row.facts.length && row.facts.every((id,i)=>{
          const f=index.facts.get(id);
          return edge.evidence[i+1]===id && f?.doc===row.doc && f.page===row.page && (f.unit || f.doc)===row.unit;
        });
    });
  }
  function observation(graph,row) {
    return row.facts.map(id=>graphIndex(graph).facts.get(id)).find(f=>f?.source_line?.number===row.line &&
      f.source_line.text===row.quote && f.source_line.rects?.length && f.doc===row.doc && f.page===row.page &&
      f.page_sha256===graphIndex(graph).nodes.get(f.doc+'/p'+f.page)?.sha256 &&
      f.source_sha256===graphIndex(graph).documents.get(f.doc)?.sha256);
  }
  function rectangles(graph,calls,row) {
    const observed=observation(graph,row)?.source_line.rects;
    if (graph.acceptance_authority_sources.format!==clockFormat) return observed || [];
    const pg=graphIndex(graph).nodes.get(row.doc+'/p'+row.page);
    const call=calls?.find(c=>c.doc===row.doc && c.page===row.page && c.page_sha256===pg?.sha256);
    const rects=call?.signer_timing_rects?.[row.line];
    return Array.isArray(rects) && rects.every(r=>Array.isArray(r) && r.length===4 &&
      r.every(v=>Number.isFinite(v) && v>=0 && v<=1) && r[2]>r[0] && r[3]>r[1]) &&
      (!observed || JSON.stringify(observed)===JSON.stringify(rects)) ? rects : [];
  }
  function interval(clock) {
    const [h,m,s]=clock.split(':').map(Number), start=h*3600+m*60+(s || 0);
    return [start,start+(s===undefined?60:1)];
  }
  function namedDay(row,name) {
    const text=row.quote.normalize('NFKC').trim(), sep=text.indexOf(':');
    if (sep<0 || !text.startsWith(name) || !/^(签认|签字|签署|签名)日期$/u.test(text.slice(name.length,sep).trim())) return false;
    const value=text.slice(sep+1).trim();
    const match=value.match(/^(\d{4})年(\d{1,2})月(\d{1,2})日$/u) || value.match(/^(\d{4})-(\d{2})-(\d{2})$/u);
    return match && match.slice(1).map(v=>v.padStart(2,'0')).join('-')===row.day;
  }
  function printedClock(value) {
    const match=/^(?:(\d{4}年\d{1,2}月\d{1,2}日|\d{4}-\d{2}-\d{2})[ T]+)?((?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?)(?:\s*(?:\((北京时间|UTC\+08:00)\)|(北京时间|UTC\+08:00|\+08:00)))?$/u.exec(value);
    if (!match) return null;
    const day=match[1] && WarrantyDates.printedDay(match[1]);
    return match[1] && !day ? null : {day:day || null,at:match[2],zone:match[3] || match[4]?'+08:00':null};
  }
  function clockMatches(row) {
    if (!row?.at || row.disputed || !row.line) return false;
    const text=row.quote.normalize('NFKC').trim(), sep=text.indexOf(':');
    const label=text.slice(0,sep).trim(), value=text.slice(sep+1).trim();
    if (row.kind==='debit' && !['实际扣款时间','扣款成功时间','成功扣款时间','实际扣款时刻','扣款时间'].includes(label)) return false;
    if (row.kind==='signer' && (!row.name || !label.startsWith(row.name) ||
        !/^(签认|签字|签署|签名)(时间|时刻|时分)$/u.test(label.slice(row.name.length)))) return false;
    const reading=printedClock(value);
    return reading && row.at===reading.at && row.day===reading.day && row.zone===reading.zone;
  }
  function panel(report) {
    if (!formats.includes(report?.policy.acceptance_authority) || report.policy.acceptance_authority!==report.graph.acceptance_authority_sources?.format) return null;
    const graph=report.graph, index=graphIndex(graph), rows=datedRows(graph), clocks=datedRows(graph,true);
    const sourceFor=(doc,page,line,quote,open,rects)=>({
      file:index.documents.get(doc).name, place:'第 '+page+' 页'+(line?' · 第 '+line+' 行':' · 行号待核'), quote,open,
      excerpt:rects?.length ? ()=>EvidenceCompare.lineExcerpt({doc,page,source_line:{rects}},index) : null,
      pageImage:workpaperSource(doc,'pages/'+page), rects
    });
    const items=[];
    for (const f of report.findings) {
      const t=f.signer_timing;
      if (f.rule!=='H05' || t?.format!==report.policy.acceptance_authority || !f.scope.includes(t.bank) || !f.scope.includes(t.receipt)) continue;
      const refs=new Set(traceReferences(graph,f));
      function factRef(id,field,unit) {
        const fact=index.facts.get(id);
        if (!refs.has(id) || fact?.field!==field || (fact.unit || fact.doc)!==unit ||
            !['anchored','confirmed'].includes(fact.status) || !fact.source_line?.rects?.length ||
            fact.page_sha256!==index.nodes.get(fact.doc+'/p'+fact.page)?.sha256 ||
            fact.source_sha256!==index.documents.get(fact.doc)?.sha256) return null;
        return sourceFor(fact.doc,fact.page,fact.source_line.number,fact.source_line.text,()=>openPage(fact.doc,fact.page,id),fact.source_line.rects);
      }
      const candidates=rows.filter(r=>t.rows.includes(r.id) && refs.has(r.id) && r.unit===t.receipt);
      const sourceRow=r=>sourceFor(r.doc,r.page,r.line,r.quote,()=>openPage(r.doc,r.page,undefined,r.line),rectangles(graph,report.calls.pages,r));
      const clock=t.clock, readings=clocks.filter(r=>clock?.rows.includes(r.id) && refs.has(r.id) && refs.has(r.doc+'/p'+r.page) && r.facts.every(id=>refs.has(id)) &&
        (r.kind==='signer'?r.unit===t.receipt:r.unit===t.bank));
      const mapped=new Map(readings.map(r=>[r.id,r]));
      const sourceTime=r=>r && clockMatches(r) && rectangles(graph,report.calls.pages,r).length ? r : null;
      const contract=graph.documents_by_kind.contract?.[0];
      const clause=factRef(t.clause_ref,'acceptance_signing_clause',contract), term=factRef(t.stage_ref,'payment_stage',contract);
      const payment=factRef(t.paid_ref,'paid_on',t.bank);
      const paid=payment && PhaseEvidence.dateOn(index.facts.get(t.paid_ref));
      const used=new Set();
      const events=t.required.map(name=>{
        const own=candidates.filter(r=>r.name===name);
        const clockRow=sourceTime(mapped.get(clock?.signers[name]));
        const namedTime=clockRow?.name===name && clockRow.kind==='signer'?clockRow:null;
        const dayRow=own.length===1 && namedDay(own[0],name)?own[0]:!own.length && namedTime?.id===clock?.days[name]?namedTime:null;
        const row=dayRow?.line && !dayRow.disputed ? dayRow : null;
        if (row) used.add(row.id);
        const signatures=t.signed[name] || [];
        const signed=signatures.length===1 && graph.acceptance_authority_sources.signatures.some(s=>
          s.native && s.confirmed && s.name===name && s.unit===t.receipt && s.fact===signatures[0]);
        const signature=signed ? factRef(signatures[0],'acceptance_signer',t.receipt) : null;
        const time=namedTime && (!namedTime.day || namedTime.day===row?.day)?namedTime:null;
        if (time) used.add(time.id);
        return {label:name+'签认',name,kind:'signer',day:row?.day,dayRef:row?.id,at:time?.at,zone:time?.zone,signature,
          source:time?sourceRow(time):row && sourceRow(row),daySource:time && row && time.id!==row.id && sourceRow(row)};
      });
      const last=events.map(e=>e.day || '').sort().at(-1);
      const delta=(Date.parse(paid)-Date.parse(last))/86400000;
      const direction=delta<0?'before':delta===0?'same_day':'after';
      const verified=payment && paid===t.paid_on && clause && term && t.rows.length===candidates.length &&
        events.every(e=>e.signature && e.day && e.source) && delta===t.days && last===t.latest_on && direction===t.state;
      const rawDebit=sourceTime(mapped.get(clock?.debit));
      const debit=rawDebit?.kind==='debit' && (!rawDebit.day || rawDebit.day===paid)?rawDebit:null;
      let clockState=clock?.state;
      const today=events.filter(e=>e.day===paid);
      if (clock && (readings.length!==clock.rows.length || new Set(clock.rows).size!==readings.length)) clockState='unverified';
      if (['before','after','overlap'].includes(clockState)) {
        const complete=verified && t.state==='same_day' && t.days===0 && debit?.zone==='+08:00' && today.length &&
          events.every(e=>e.dayRef===clock.days[e.name]) &&
          today.every(e=>e.zone==='+08:00' && e.at) && today.length===clock.relevant.length && today.every(e=>clock.relevant.includes(e.name));
        if (complete) {
          const bounds=today.map(e=>interval(e.at)), [start,end]=interval(debit.at);
          const order=end<=Math.max(...bounds.map(b=>b[0]))?'before':start>=Math.max(...bounds.map(b=>b[1]))?'after':'overlap';
          if (clockState!==order) clockState='unverified';
        } else clockState='unverified';
      }
      if (debit) used.add(debit.id);
      const bankEvent={label:debit?'实际扣款':'回单付款',kind:'payment',day:paid || null,at:debit?.at,zone:debit?.zone,
        source:debit?sourceRow(debit):payment,daySource:debit && payment};
      const print=readings.filter(r=>r.kind==='other' && sourceTime(r));
      const bankSide=debit ? bankEvent : print.length===1 ? {label:print[0].quote.split(/[:：]/u)[0],
        day:print[0].day,at:print[0].at,zone:print[0].zone,source:sourceRow(print[0])} : null;
      const signerSide=today.filter(e=>e.at).sort((a,b)=>interval(b.at)[0]-interval(a.at)[0])[0];
      const pair=signerSide && bankSide && clockState!=='unverified' ? [signerSide,bankSide] : null;
      if (pair && !debit) used.add(print[0].id);
      events.push(bankEvent);
      items.push({key:f.id,stage:f.stage.name,stageRef:t.stage_ref,choice:f.stage.name+' · '+(payment?.file || '回单')+' · '+(paid || '日期待核'),
        state:['before','same_day','after'].includes(t.state) && !verified ? 'unverified' : t.state,
        clockState,pair,
        days:t.days,events,clause,term,candidates:[...candidates,...readings].filter(r=>!used.has(r.id)).map(sourceRow)});
    }
    if (!items.length) return null;
    const card=SignerTimeline.render(items,'signer-timing');
    const explanation=el('span');
    const back=action('',()=>selectPhase(),'text-button');
    const empty=box('signer-empty',explanation,back); empty.hidden=true; card.append(empty);
    function selectPhase() {
      card.dispatchEvent(new CustomEvent('select-contract-phase',{detail:card.dataset.clause}));
    }
    card.addEventListener('reveal-evidence',selectPhase);
    card.addEventListener('signer-payment-changed',selectPhase);
    card.addEventListener('inspect-payment-stage',event=>{
      const matches=items.filter(i=>i.stageRef===event.detail.clause_ref);
      empty.hidden=Boolean(matches.length); card.dataset.outOfStage=String(!matches.length);
      if (!matches.length) {
        explanation.textContent=event.detail.name+'尚无可比对共同签认日期的回单。';
        back.textContent='返回'+items.find(i=>i.key===card.dataset.findingKey).stage;
      } else if (!matches.some(i=>i.key===card.dataset.findingKey)) {
        card.dispatchEvent(new CustomEvent('select-signer-payment',{detail:matches[0].key}));
      }
    });
    return card;
  }
  function jump(finding) {
    const b=action('核对签认与付款日',()=>{
      const card=document.getElementById('signer-timing');
      card?.dispatchEvent(new CustomEvent('select-signer-payment',{detail:finding.id}));
      revealPaperTarget(card);
    },'text-button');
    b.setAttribute('aria-controls','signer-timing');
    return b;
  }
  return {panel,jump,datedRows,observation,rectangles,printedClock,interval};
})();
