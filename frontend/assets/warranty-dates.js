// Re-read the two printed lines before offering their calendar-day comparison.
const WarrantyDates = (() => {
  const format='warranty-written-dates-v1';
  const labels={warranty_release:['质保期满确认','质保期满记录'],paid_on:['付款日期','转账日期','交易日期','支付日期'],
    accepted_on:['验收日期','验收时间','复验日期','复验时间'],repaired_on:['整改完成日期']};
  const literal='(?<literal>(?<year>[0-9]{4}) *(?:年 *(?<month>[0-9]{1,2}) *月 *(?<day>[0-9]{1,2}) *日|(?<sep>[-/.]) *(?<nmonth>[0-9]{1,2}) *\\k<sep> *(?<nday>[0-9]{1,2})))';
  const dateOnly=new RegExp('^ *'+literal+' *$','u');
  const patterns={warranty_release:new RegExp('^ *'+literal+' *(?:双方确认 *)?质保期(?:已届满|届满|已满) *。? *$','u'),
    paid_on:dateOnly,accepted_on:dateOnly,repaired_on:dateOnly};
  const fold=s=>s.replace(/[０-９：／－．]/gu,c=>String.fromCharCode(c.charCodeAt(0)-0xfee0)).replace(/[\u00a0\u2002\u2003\u2009\u202f\u3000]/gu,' ');
  const same=(a,b)=>Array.isArray(a) && Array.isArray(b) && a.length===b.length && a.every((v,i)=>v===b[i]);
  function calendarDay(groups) {
    if (!groups) return null;
    const iso=groups.year+'-'+(groups.month || groups.nmonth).padStart(2,'0')+'-'+(groups.day || groups.nday).padStart(2,'0');
    const ms=Date.parse(iso+'T00:00:00Z');
    return groups.year!=='0000' && Number.isFinite(ms) && new Date(ms).toISOString().slice(0,10)===iso ? {iso,days:ms/86400000} : null;
  }
  function printedDay(value) {
    return typeof value==='string' ? calendarDay(dateOnly.exec(fold(value))?.groups)?.iso || null : null;
  }
  function parse(f) {
    const raw=f?.source_line?.text, field=f?.field, pattern=patterns[field];
    if (typeof raw!=='string' || !pattern || !['anchored','confirmed'].includes(f.status) || !f.source_line.rects?.length) return null;
    const text=fold(raw), i=text.indexOf(':'), label=text.slice(0,i).replace(/^ +| +$/gu,''), body=text.slice(i+1);
    if (i<0 || !labels[field].includes(label) || /[\r\n]/u.test(text)) return null;
    const m=pattern.exec(body)?.groups;
    if (!m) return null;
    for (const [citation,needsLabel] of [[f.quote,true],[f.value,false]]) {
      if (typeof citation!=='string' || /[\r\n]/u.test(citation)) return null;
      const value=fold(citation), j=value.indexOf(':'), part=value.slice(j+1);
      if (needsLabel && j<0 || j>=0 && value.slice(0,j).replace(/^ +| +$/gu,'')!==label ||
          !pattern.test(part) || part.replaceAll(' ','')!==body.replaceAll(' ','')) return null;
    }
    const day=calendarDay(m), start=i+1+body.indexOf(m.literal);
    return day && {...day,literal:raw.slice(start,start+m.literal.length)};
  }
  function printed(item,report,unit,field) {
    const {graph,policy}=report;
    if (policy?.warranty_dates!==format || graph.warranty_date_sources?.format!==format ||
        !/^[a-f0-9]{64}$/.test(policy.code_sha256?.['warranty_dates.py'])) return null;
    const cert=field==='warranty_release', kind=cert?'warranty':'bank_receipt';
    if (!item.scope.includes(unit) || !graph.documents_by_kind[kind]?.includes(unit)) return null;
    const ledger=cert?graph.warranty_sources:graph.warranty_date_sources;
    const pages=ledger?.pages?.filter(p=>p.unit===unit), rows=ledger?.lines?.filter(r=>r.unit===unit && (!cert || r.kind===field));
    if (!pages?.length || !pages.every(p=>p.native) || rows?.length!==1) return null;
    const [row]=rows, pageId=row.doc+'/p'+row.page, index=graphIndex(graph);
    const supports=PerformanceIndex.fieldLinks(graph), result=' finding/'+item.id;
    if (!pages.some(p=>p.doc===row.doc && p.page===row.page) || index.nodes.get(pageId)?.layer!=='text' ||
        ![row.doc,pageId].every(id=>supports.has(id+result) && item.evidence.includes(id))) return null;
    const source=PerformanceIndex.originals(item,graph).find(s=>s.fact.id===row.facts[0]);
    const f=source?.fact;
    if (f?.field!==field || (f.unit || f.doc)!==unit || f.doc!==row.doc || f.page!==row.page || !same(row.facts,[f.id]) ||
        source.printedLine!==row.line || f.source_line.text!==row.quote) return null;
    const calls=report.calls?.pages?.filter(c=>c.doc===row.doc && c.page===row.page);
    if (calls?.length!==1 || !calls[0].response_id || !calls[0].check?.response_id || calls[0].page_sha256!==f.page_sha256 ||
        issuedPageDocument(graph,calls[0])!==source.doc) return null;
    return {fact:f,doc:source.doc,row};
  }
  function source(item,report,read,field) {
    if (!read) return null;
    const s=printed(item,report,read.unit,field), f=s?.fact;
    if (!f || read.ref!==f.id || read.doc!==f.doc || read.page!==f.page || read.line!==s.row.line ||
        read.original_sha256!==s.doc.sha256 || read.page_sha256!==f.page_sha256) return null;
    const parsed=parse(f);
    return parsed && parsed.iso===read.iso && parsed.literal===read.literal?{...s,...parsed,read}:null;
  }
  function confirmation(item,report,proofs=[]) {
    if (!report || !item) return null;
    const check=item.warranty_check, cert=check?.certificate, read=cert?.date;
    if (!cert?.linked || !read || check.confirmed_on!==null || check.stated_on!==read.iso || check.confirmation_ref!==read.ref ||
        !cert.evidence.includes(read.ref) || !same(cert.records,[proofs?.[0]?.record.id]) || proofs.length!==1 ||
        proofs[0].record.unit!==read.unit || proofs[0].doc.id!==read.doc) return null;
    const s=source(item,report,read,'warranty_release');
    if (!s) return null;
    const extra=report.graph.facts.filter(f=>(f.unit || f.doc)===read.unit && f.field==='warranty_release' && f.id!==read.ref);
    if (!extra.length) return read.heading_refs?.length?null:s;
    const titles=report.graph.facts.filter(f=>(f.unit || f.doc)===read.unit && f.field==='warranty');
    const [title]=titles, loc=title?.source_line;
    if (titles.length!==1 || !loc?.rects?.length || !['质保期满确认单','质保期满确认书'].includes(loc.text)) return null;
    const expected=[title.id,...extra.map(f=>f.id)];
    if (!same(read.heading_refs,expected) || !expected.every(id=>cert.evidence.includes(id) && item.evidence.includes(id)) ||
        !extra.every(f=>f.status==='visual' && f.value===f.quote && f.quote===loc.text && f.doc===title.doc && f.page===title.page &&
          f.page_sha256===title.page_sha256 && f.source_sha256===title.source_sha256 && f.source_line?.number===loc.number &&
          f.source_line.text===loc.text && JSON.stringify(f.source_line.rects)===JSON.stringify(loc.rects))) return null;
    return s;
  }
  function unreadRow(item,report,proofs) {
    const cert=item.warranty_check?.certificate;
    if (!report || !cert?.linked || cert.date!==null || item.warranty_check.stated_on!==null ||
        proofs.length!==1 || !same(cert.records,[proofs[0].record.id])) return null;
    const s=printed(item,report,proofs[0].record.unit,'warranty_release');
    if (!s || s.doc.id!==proofs[0].doc.id || !proofs[0].record.pages.some(p=>p.ref===s.doc.id+'/p'+s.row.page && p.sha256===s.fact.page_sha256)) return null;
    return s.row;
  }
  function issued(item,graph) {
    const report=state.bundle?.report;
    if (!item?.warranty_check?.certificate?.date || report?.graph!==graph) return null;
    return confirmation(item,report,PerformanceIndex.warrantyProofs(item,report));
  }
  function pageReference(graph,doc,page,line,calls) {
    if (!line || graph?.warranty_date_sources?.format!==format) return null;
    const certificate=graph.warranty_sources.lines.filter(r=>r.kind==='warranty_release');
    const matches=[...certificate,...graph.warranty_date_sources.lines].filter(r=>r.doc===doc && r.page===page && r.line===line);
    if (matches.length!==1) return null;
    const [row]=matches, index=graphIndex(graph), pageId=doc+'/p'+page, f=index.facts.get(row.facts[0]);
    const label=row.kind?'确认单日期原行':'回单付款日期原行', trace=calls?.filter(c=>c.doc===doc && c.page===page);
    if (trace?.length!==1 || !f || !same(row.facts,[f.id]) || f.doc!==doc || f.page!==page || (f.unit || f.doc)!==row.unit ||
        f.field!==(row.kind?'warranty_release':'paid_on') || f.source_line?.number!==line || f.source_line.text!==row.quote ||
        !f.source_line.rects?.length || !PerformanceIndex.fieldLinks(graph).has(pageId+' '+f.id) || index.nodes.get(pageId)?.layer!=='text' ||
        f.page_sha256!==trace[0].page_sha256 || issuedPageDocument(graph,trace[0])?.sha256!==f.source_sha256) return null;
    return {ref:'warranty-date-line/'+line,rawLine:line,label,quote:row.quote,rects:f.source_line.rects,
      quality:'warranty_date_source',option:label+' · 第 '+line+' 行'};
  }
  function comparison(phase,payment,report,stated) {
    const filed=payment.warranty_payment, c=filed?.comparison, cert=payment.warranty_check?.certificate;
    if (!stated || payment.rule!=='H05' || !PhaseEvidence.sameStage(phase.stage,payment.stage) ||
        !c || !cert?.linked || !same(cert.records,phase.warranty_check.certificate.records) || c.stated_ref!==stated.fact.id ||
        cert.date?.ref!==c.stated_ref || cert.date.iso!==stated.iso || cert.date.literal!==stated.literal ||
        !c.bank || filed.paid_on!==c.bank.iso || !same(filed.date_refs,[c.bank.ref]) || !Array.isArray(c.evidence)) return null;
    const bank=source(payment,report,c.bank,'paid_on');
    if (!bank || bank.days-stated.days!==c.days || !Number.isSafeInteger(c.days)) return null;
    const graph=report.graph, supports=graphIndex(graph).supports.get('finding/'+payment.id);
    const keys=['contract_id','payer','payee','transfer_status','payment_designation'];
    const refs=graph.facts.filter(f=>(f.unit || f.doc)===bank.read.unit && keys.includes(f.field));
    if (keys.some(k=>refs.filter(f=>f.field===k).length!==1)) return null;
    const expected=[...new Set([phase.stage.clause_ref,...cert.records,stated.doc.id,stated.doc.id+'/p'+stated.fact.page,
      stated.fact.id,...(cert.date.heading_refs || []),bank.doc.id,bank.doc.id+'/p'+bank.fact.page,bank.fact.id,...refs.map(f=>f.id)])];
    const links=graph.edges.filter(e=>e.type==='warranty_payment_dates' && e.from===stated.fact.id && e.to===bank.fact.id);
    if (!same(c.evidence,expected) || !expected.every(id=>payment.evidence.includes(id) && supports?.has(id)) ||
        links.length!==1 || !same(links[0].evidence,expected)) return null;
    return {id:payment.id,stated,bank,days:c.days};
  }
  function panel(pairs,cardId) {
    if (!pairs.length) return null;
    const root=el('section','','warranty-written-dates'), select=el('select'), body=box('warranty-date-pair');
    root.setAttribute('aria-label','确认单与回单所列日期');root.tabIndex=-1;
    const outcome=el('strong'), head=box('warranty-date-heading',el('h5','两单日期'),outcome);
    if (pairs.length>1) {
      select.setAttribute('aria-label','选择本期所据的银行回单');
      for (const p of pairs) select.add(new Option(p.bank.doc.name+' · '+p.id,p.id));
      head.append(select);
    }
    function choose(id) {
      const p=pairs.find(pair=>pair.id===id);
      root.hidden=!p;
      if (!p) {delete root.dataset.warrantyPayment;body.replaceChildren();return;}
      select.value=id;root.dataset.warrantyPayment=id;
      root.dataset.order=p.days===0?'same':p.days<0?'before':'after';
      outcome.id=cardId+'-'+id+'-order';outcome.dataset.warrantyOrder=root.dataset.order;
      outcome.textContent=p.days===0?'同日 · 时分待核':'回单'+(p.days<0?'早 ':'晚 ')+Math.abs(p.days)+' 天';
      body.replaceChildren();
      for (const [side,label,r] of [['stated','确认单',p.stated],['bank','银行回单',p.bank]]) {
        const f=r.fact, button=action('',()=>openPage(f.doc,f.page,null,r.read.line,null,'warranty-date-line/'+r.read.line),'warranty-date-source');
        button.id=cardId+'-'+id+'-'+side;button.dataset.source=f.id;
        const time=el('time',r.literal);time.dateTime=r.iso;
        if (r.literal.includes('年')) {
          time.replaceChildren(...r.literal.split(/(?<=[年月])/u).flatMap((part,i)=>i?[el('wbr'),el('span',part)]:[el('span',part)]));
        }
        button.append(el('small',label),time,box('warranty-date-place',el('span',f.page+' 页 · '+r.read.line+' 行'),glyph('arrows-angle-expand')));
        button.append(el('span','，打开原页','visually-hidden'));
        body.append(button);
      }
    }
    select.addEventListener('change',()=>choose(select.value));
    root.addEventListener('select-warranty-payment',e=>choose(e.detail));
    root.append(head,body);choose(pairs[0].id);
    return root;
  }
  return {parse,printedDay,confirmation,comparison,unreadRow,issued,pageReference,panel};
})();
