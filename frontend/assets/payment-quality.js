// The workpaper binds all three documents to this installment. Recheck the filed original lines before displaying a comparison.
const PaymentQuality = (() => {
  const format='acceptance-quality-payment-v1';
  const same=(a,b)=>Array.isArray(a) && Array.isArray(b) && a.length===b.length && a.every((x,i)=>x===b[i]);
  const number='-?[0-9]{1,12}(?:\\.[0-9]{1,6})?';
  const metric=new RegExp('^([\\u4e00-\\u9fff]{1,16}?) *(不高于|不超过|不低于|至少|至多|≤|≥)? *('+number+') *(°C|mm|cm|kg|MPa|kPa|%)$','u');
  function body(line) {
    const value=line.replace(/[０-９：．－％]/gu,c=>String.fromCharCode(c.charCodeAt(0)-0xfee0)).replaceAll('℃','°C').replaceAll('　',' ');
    const pos=value.indexOf(':');
    return (pos<0?value:value.slice(pos+1)).trim();
  }
  function scaled(value) {
    const [whole,fraction='']=value.replace(/^-/,'').split('.');
    const n=BigInt(whole+fraction.padEnd(6,'0'));
    return value.startsWith('-')?-n:n;
  }
  function bind(item,report) {
    const data=item.payment_quality;
    if (!data || !['risk','issue'].includes(item.status) || !['H04','H05'].includes(item.rule) || !item.stage) return null;
    const {graph,policy}=report, ledger=graph.payment_quality_sources;
    if (policy.payment_quality!==format || !/^[a-f0-9]{64}$/.test(policy.code_sha256?.['payment_quality.py']) ||
        ledger?.format!==format || !Array.isArray(ledger.rows) || !data.fields || !data.measure || !Array.isArray(data.evidence)) return null;
    const fields=data.fields, payment=data.payment, units={contract:data.contract,acceptance:data.receipt};
    if (Boolean(payment)!==(item.rule==='H05') || fields.clause!==item.stage.clause_ref) return null;
    if (payment) units.bank_receipt=payment.bank;
    const pages=graph.payment_window_sources?.pages || [];
    for (const [kind,unit] of Object.entries(units)) {
      const owned=pages.filter(p=>p.unit===unit);
      if (!item.scope.includes(unit) || !graph.documents_by_kind[kind]?.includes(unit) || !owned.length ||
          !owned.every(p=>p.native && p.text_only && p.document_kind===kind)) return null;
    }
    const originals=new Map(PerformanceIndex.originals(item,graph).map(s=>[s.fact.id,s]));
    const edges=graph.edges.filter(e=>e.type==='acceptance_reading_for_payment' && e.to==='finding/'+item.id);
    if (edges.length!==1 || edges[0].from!==fields.measured_result || !same(edges[0].evidence,data.evidence) ||
        !data.evidence.every(ref=>originals.get(ref)?.printedLine)) return null;
    const rows={}, required=['clause','acceptance_criteria','inspection_basis','measured_result','acceptance_scope','acceptance_result'];
    if (data.accepted_on || payment) required.push('accepted_on');
    if (payment) required.push('payment_designation','transfer_status','paid_on');
    for (const key of required) {
      const ref=fields[key], s=originals.get(ref);
      if (!s || !data.evidence.includes(ref)) return null;
      const f=s.fact, isClause=key==='clause';
      const unit=['clause','acceptance_criteria'].includes(key)?data.contract:
        ['payment_designation','transfer_status','paid_on'].includes(key)?payment?.bank:data.receipt;
      if ((f.unit || f.doc)!==unit || (isClause?!['payment_stage','payment_term'].includes(f.field):f.field!==key)) return null;
      const candidates=ledger.rows.filter(r=>r.unit===unit && r.field===f.field &&
        (!isClause || r.quote.split(/[:：]/u)[0]===f.source_line.text.split(/[:：]/u)[0]));
      const [r]=candidates;
      if (candidates.length!==1 || !same(r.facts,[ref]) || r.doc!==f.doc || r.page!==f.page ||
          r.line!==s.printedLine || r.quote!==f.source_line.text) return null;
      const calls=report.calls?.pages?.filter(c=>c.doc===f.doc && c.page===f.page);
      if (calls?.length!==1 || !calls[0].response_id || !calls[0].check?.response_id || calls[0].page_sha256!==f.page_sha256 ||
          issuedPageDocument(graph,calls[0])!==s.doc) return null;
      rows[key]=s;
    }
    function readMetric(key) {
      const f=rows[key].fact, parsed=[f.source_line.text,f.quote,f.value].map(v=>metric.exec(body(v))?.slice(1));
      return parsed[0] && parsed.every(m=>same(m,parsed[0]))?parsed[0]:null;
    }
    const m=data.measure, limit=readMetric('acceptance_criteria'), value=readMetric('measured_result');
    if (!m.operator || !same(limit,[m.name,m.operator,m.limit,m.unit]) || !same(readMetric('inspection_basis'),limit) ||
        !same(value,[m.name,undefined,m.observed,m.unit]) || !/^[0-9]{1,13}(?:\.[0-9]{1,6})?$/.test(m.outside_by)) return null;
    const upper=['不高于','不超过','至多','≤'].includes(m.operator);
    const margin=(scaled(m.observed)-scaled(m.limit))*(upper?1n:-1n);
    if (margin<=0n || margin!==scaled(m.outside_by)) return null;
    const accepted=rows.accepted_on && WarrantyDates.parse(rows.accepted_on.fact);
    if ((rows.accepted_on && !accepted) || (accepted?.iso || null)!==data.accepted_on) return null;
    if (payment) {
      const paid=WarrantyDates.parse(rows.paid_on.fact);
      if (!paid || paid.iso!==payment.paid_on || paid.days-accepted.days!==payment.days) return null;
    }
    return {rows,upper};
  }
  function panel(item,report,rev) {
    const bound=bind(item,report);
    if (!bound) return null;
    const {rows,upper}=bound, {measure:m,payment}=item.payment_quality;
    const root=el('section','','quality-payment'); root.id='quality-'+item.id;
    Object.assign(root.dataset,{qualityFinding:item.id,caseId:report.case_id,rev:String(rev)});
    root.setAttribute('aria-label','验收款质量对照');
    function control(field,label,display,cls) {
      const {fact,doc,printedLine}=rows[field], place='第 '+fact.page+' 页 · 第 '+printedLine+' 行';
      const button=action('',()=>openPage(fact.doc,fact.page,fact.id),cls);
      button.id=root.id+'-'+field;button.dataset.source=fact.id;button.dataset.qualityLabel=[label,doc.name,place].join(' · ');
      button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-controls','page-dialog');
      button.title=doc.name+' · '+place;
      button.append(el('small',label),el('strong',display),glyph('arrows-angle-expand'));
      button.append(el('span',button.title,'visually-hidden'));
      return button;
    }
    const header=box('quality-heading',el('h4',m.name+'核对'),el('span',(upper?'高于上限 ':'低于下限 ')+m.outside_by+' '+m.unit));
    const pair=box('quality-readings',control('acceptance_criteria',upper?'合同上限':'合同下限',m.limit+' '+m.unit,'quality-metric'),
      control('measured_result','终验实测',m.observed+' '+m.unit,'quality-metric measured'));
    root.append(header,pair);
    if (rows.accepted_on) {
      const dates=box('quality-dates',control('accepted_on','验收单所列日',item.payment_quality.accepted_on,'quality-day'));
      if (payment) {
        dates.append(control('paid_on','回单付款日',payment.paid_on,'quality-day'));
        const order=el('p',payment.days?'回单'+(payment.days<0?'早 ':'晚 ')+Math.abs(payment.days)+' 天':'同日，先后待核','quality-order');
        order.id=root.id+'-order';dates.append(order);
      }
      root.append(dates);
    }
    const clauses=el('details','','quality-terms'), summary=el('summary','核对条款与验收结论');
    summary.id=root.id+'-terms';clauses.append(summary);
    const labels={clause:'本期付款条款',acceptance_scope:'验收范围',inspection_basis:'检验依据',acceptance_result:'验收单结论',
      payment_designation:'回单用途',transfer_status:'交易状态'};
    for (const [key,label] of Object.entries(labels)) if (rows[key]) {
      const raw=rows[key].fact.source_line.text;
      clauses.append(control(key,label,raw.slice(raw.search(/[:：]/u)+1),'quality-term'));
    }
    root.append(clauses);return root;
  }
  return {bind,panel};
})();
