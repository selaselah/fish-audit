// The workpaper binds all three documents to this installment. Recheck the filed original lines before displaying a comparison.
const PaymentQuality = (() => {
  const first='acceptance-quality-payment-v1', current='acceptance-quality-payment-v2';
  const upperBound=operator=>['不高于','不超过','至多','≤'].includes(operator);
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
  function matchesLimit(limit,printed,observed) {
    if (!limit?.operator || !same(printed,[limit.name,limit.operator,limit.limit,limit.unit])) return false;
    if (printed[0]!==observed[0] || printed[3]!==observed[3]) return limit.result==='incomparable' && !('outside_by' in limit);
    const margin=(scaled(observed[2])-scaled(printed[2]))*(upperBound(limit.operator)?1n:-1n);
    if (margin<=0n) return limit.result==='within' && !('outside_by' in limit);
    return limit.result==='outside' && /^[0-9]{1,13}(?:\.[0-9]{1,6})?$/.test(limit.outside_by) && scaled(limit.outside_by)===margin;
  }
  function bind(item,report) {
    const acceptance=item.rule==='H02', data=acceptance?item.quality_comparison:item.payment_quality;
    if (!data || item.status==='ok' || (!acceptance && (!['H04','H05'].includes(item.rule) || !item.stage))) return null;
    const {graph,policy}=report, ledger=graph.payment_quality_sources, compared=acceptance?data:data.comparison;
    if (![first,current].includes(policy.payment_quality) || ledger?.format!==policy.payment_quality ||
        !/^[a-f0-9]{64}$/.test(policy.code_sha256?.['payment_quality.py']) || !Array.isArray(ledger.rows) || !data.fields ||
        !Array.isArray(data.evidence) || (compared?ledger.format!==current || Boolean(data.measure):!data.measure)) return null;
    if (!acceptance && !['risk','issue'].includes(item.status)) return null;
    const fields=data.fields, payment=data.payment, units={contract:data.contract,acceptance:data.receipt};
    if (Boolean(payment)!==(item.rule==='H05') || !acceptance && fields.clause!==item.stage.clause_ref) return null;
    if (payment) units.bank_receipt=payment.bank;
    const pages=graph.payment_window_sources?.pages || [];
    for (const [kind,unit] of Object.entries(units)) {
      const owned=pages.filter(p=>p.unit===unit);
      if (!item.scope.includes(unit) || !graph.documents_by_kind[kind]?.includes(unit) || !owned.length ||
          !owned.every(p=>p.native && p.text_only && p.document_kind===kind)) return null;
    }
    const originals=new Map(PerformanceIndex.originals(item,graph).map(s=>[s.fact.id,s]));
    const edgeType=acceptance?'measured_against_inspection_limits':'acceptance_reading_for_payment';
    const edges=graph.edges.filter(e=>e.type===edgeType && e.to==='finding/'+item.id);
    if (edges.length!==1 || edges[0].from!==fields.measured_result || !same(edges[0].evidence,data.evidence) ||
        !data.evidence.every(ref=>originals.get(ref)?.printedLine)) return null;
    const rows={}, required=['acceptance_criteria','inspection_basis','measured_result','acceptance_scope','acceptance_result'];
    if (!acceptance) required.push('clause');
    if (data.accepted_on || payment) required.push('accepted_on');
    if (payment) required.push('payment_designation','transfer_status','paid_on');
    for (const key of required) {
      const ref=fields[key], s=originals.get(ref);
      const unit=['clause','acceptance_criteria'].includes(key)?data.contract:
        ['payment_designation','transfer_status','paid_on'].includes(key)?payment?.bank:data.receipt;
      if (!data.evidence.includes(ref) || !PerformanceIndex.matchesPrintedField(s,report,ledger.rows,unit,key)) return null;
      rows[key]=s;
    }
    function readMetric(key) {
      const f=rows[key].fact, parsed=[f.source_line.text,f.quote,f.value].map(v=>metric.exec(body(v))?.slice(1));
      return parsed[0] && parsed.every(m=>same(m,parsed[0]))?parsed[0]:null;
    }
    const limit=readMetric('acceptance_criteria'), basis=readMetric('inspection_basis'), value=readMetric('measured_result');
    if (compared) {
      const {observed,limits}=compared;
      if (!observed || !limits || !same(value,[observed.name,undefined,observed.value,observed.unit]) ||
          !matchesLimit(limits.contract,limit,value) || !matchesLimit(limits.inspection,basis,value) ||
          (limit[0]===basis[0] && limit[3]===basis[3] && upperBound(limit[1])===upperBound(basis[1]) && scaled(limit[2])===scaled(basis[2])) ||
          [limits.contract,limits.inspection].every(x=>x.result==='incomparable')) return null;
      if (acceptance && [limits.contract,limits.inspection].some(l=>l.result==='outside') && item.status!=='issue') return null;
      if (!acceptance) {
        const h=report.findings.find(f=>f.rule==='H02' && f.quality_comparison);
        const proof=h?.quality_comparison;
        if (!proof || proof.contract!==data.contract || proof.receipt!==data.receipt ||
            !required.filter(k=>k in proof.fields).every(k=>proof.fields[k]===fields[k]) ||
            !proof.evidence.every(ref=>data.evidence.includes(ref)) || !bind(h,report)) return null;
      }
    } else {
      const m=data.measure;
      if (!m.operator || !same(limit,[m.name,m.operator,m.limit,m.unit]) || !same(basis,limit) ||
          !same(value,[m.name,undefined,m.observed,m.unit]) || !/^[0-9]{1,13}(?:\.[0-9]{1,6})?$/.test(m.outside_by)) return null;
      const margin=(scaled(m.observed)-scaled(m.limit))*(upperBound(m.operator)?1n:-1n);
      if (margin<=0n || margin!==scaled(m.outside_by)) return null;
    }
    if (acceptance) return {rows,compared};
    const accepted=rows.accepted_on && WarrantyDates.parse(rows.accepted_on.fact);
    if ((rows.accepted_on && !accepted) || (accepted?.iso || null)!==data.accepted_on) return null;
    if (payment) {
      const paid=WarrantyDates.parse(rows.paid_on.fact);
      if (!paid || paid.iso!==payment.paid_on || paid.days-accepted.days!==payment.days) return null;
    }
    return {rows,compared};
  }
  function panel(item,report,rev) {
    const bound=bind(item,report);
    if (!bound) return null;
    const {rows,compared}=bound, acceptance=item.rule==='H02', data=acceptance?item.quality_comparison:item.payment_quality;
    const {measure:m,payment}=data;
    const root=el('section','','quality-payment'); root.id=(acceptance?'limits-':'quality-')+item.id;
    Object.assign(root.dataset,{[acceptance?'limitFinding':'qualityFinding']:item.id,caseId:report.case_id,rev:String(rev)});
    root.setAttribute('aria-label',acceptance?'验收限值对照':'验收款质量对照');
    if (acceptance) root.tabIndex=-1;
    function control(field,label,display,cls) {
      return PerformanceIndex.originalButton(root.id+'-'+field,rows[field],label,display,cls);
    }
    if (compared) {
      const {observed,limits}=compared;
      root.append(box('quality-heading',el('h4',observed.name+'验收限值对照')));
      const evidence=box('quality-readings quality-limits',
        control('measured_result','终验实测',observed.value+' '+observed.unit,'quality-metric measured'),
        control('acceptance_result','验收单结论',body(rows.acceptance_result.fact.source_line.text),'quality-metric'));
      for (const [role,field,label] of [['contract','acceptance_criteria','合同约定'],['inspection','inspection_basis','检验依据']]) {
        const lim=limits[role], prefix=lim.name===observed.name?'':lim.name+' ';
        const b=control(field,label,prefix+(upperBound(lim.operator)?'≤ ':'≥ ')+lim.limit+' '+lim.unit,'quality-metric');
        const note=lim.result==='outside'?'超出 '+lim.outside_by+' '+lim.unit:lim.result==='within'?'符合限值':'指标或单位待核';
        b.append(el('span',note,'quality-evaluation '+lim.result));
        evidence.append(b);
      }
      root.append(evidence);
      if (acceptance) return root;
    } else {
      const upper=upperBound(m.operator);
      const header=box('quality-heading',el('h4',m.name+'核对'),el('span',(upper?'高于上限 ':'低于下限 ')+m.outside_by+' '+m.unit));
      root.append(header,box('quality-readings',control('acceptance_criteria',upper?'合同上限':'合同下限',m.limit+' '+m.unit,'quality-metric'),
        control('measured_result','终验实测',m.observed+' '+m.unit,'quality-metric measured')));
    }
    if (rows.accepted_on) {
      const dates=box('quality-dates',control('accepted_on','验收单所列日',item.payment_quality.accepted_on,'quality-day'));
      if (payment) {
        dates.append(control('paid_on','回单付款日',payment.paid_on,'quality-day'));
        const order=el('p',payment.days?'回单'+(payment.days<0?'早 ':'晚 ')+Math.abs(payment.days)+' 天':'同日，先后待核','quality-order');
        order.id=root.id+'-order';dates.append(order);
      }
      root.append(dates);
    }
    const clauses=el('details','','quality-terms'), summary=el('summary',compared?'核对付款条款与凭证':'核对条款与验收结论');
    summary.id=root.id+'-terms';clauses.append(summary);
    const labels={clause:'本期付款条款',acceptance_scope:'验收范围',inspection_basis:'检验依据',acceptance_result:'验收单结论',
      payment_designation:'回单用途',transfer_status:'交易状态'};
    for (const [key,label] of Object.entries(labels)) if (rows[key] && !(compared && ['inspection_basis','acceptance_result'].includes(key))) {
      const raw=rows[key].fact.source_line.text;
      clauses.append(control(key,label,raw.slice(raw.search(/[:：]/u)+1),'quality-term'));
    }
    root.append(clauses);return root;
  }
  return {bind,panel};
})();
