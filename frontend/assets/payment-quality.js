// The workpaper binds all three documents to this installment. Recheck the filed original lines before displaying a comparison.
const PaymentQuality = (() => {
  const first='acceptance-quality-payment-v1', dual='acceptance-quality-payment-v2', current='acceptance-quality-payment-v3';
  const strict=operator=>['低于','小于','<','高于','大于','>'].includes(operator);
  const upperBound=operator=>['不高于','不超过','至多','≤','低于','小于','<'].includes(operator);
  function sign(operator) {
    if (upperBound(operator)) return strict(operator)?'<':'≤';
    return strict(operator)?'>':'≥';
  }
  function issued(version) {
    if (!/^\d{4}\.\d{1,2}\.\d{1,2}\.\d+$/u.test(version)) return null;
    const since=v=>version.localeCompare(v,'en',{numeric:true})>=0;
    return since('2026.11.28.10')?current:since('2026.11.28.9')?dual:since('2026.11.27.17')?first:null;
  }
  const same=(a,b)=>Array.isArray(a) && Array.isArray(b) && a.length===b.length && a.every((x,i)=>x===b[i]);
  const number='-?[0-9]{1,12}(?:\\.[0-9]{1,6})?';
  const metric=extra=>new RegExp('^([\\u4e00-\\u9fff]{1,16}?) *(不高于|不超过|不低于|至少|至多|≤|≥'+extra+')? *('+number+') *(°C|mm|cm|kg|MPa|kPa|%)$','u');
  const closedMetric=metric(''), openMetric=metric('|低于|小于|高于|大于|<|>');
  const qualifier=/(?:不|不得|不宜|不应|不能|不可|不必|不要求|无需|未|应|须|应当|必须|宜|最好|建议|参考|约|原则上|尽量|禁止|严禁|并非)$/u;
  const validRect=r=>Array.isArray(r) && r.length===4 && r.every(n=>Number.isFinite(n) && n>=0 && n<=1) && r[0]<r[2] && r[1]<r[3];
  function noteSource(report,n) {
    const page=report.calls?.pages?.find(p=>p.doc===n.doc && p.page===n.page);
    const rects=page?.measurement_note_rects?.[String(n.line)];
    if (!Array.isArray(rects) || !rects.every(validRect)) return null;
    return {ref:'measurement-note/'+n.doc+'/p'+n.page+'/l'+n.line,quote:n.quote,rawLine:n.line,rects,
      label:'测量精度说明',option:'测量精度说明 · 第 '+n.line+' 行',quality:'measurement_precision'};
  }
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
  function matchesLimit(limit,printed,observed,needsReading) {
    if (!limit?.operator || !same(printed,[limit.name,limit.operator,limit.limit,limit.unit])) return false;
    if (printed[0]!==observed[0] || printed[3]!==observed[3]) return limit.result==='incomparable' && !('outside_by' in limit);
    if (needsReading) return limit.result==='reading_required' && !('outside_by' in limit);
    const margin=(scaled(observed[2])-scaled(printed[2]))*(upperBound(limit.operator)?1n:-1n);
    if (margin===0n && strict(limit.operator)) return limit.result==='excluded_boundary' && !('outside_by' in limit);
    if (margin<=0n) return limit.result==='within' && !('outside_by' in limit);
    return limit.result==='outside' && /^[0-9]{1,13}(?:\.[0-9]{1,6})?$/.test(limit.outside_by) && scaled(limit.outside_by)===margin;
  }
  function bind(item,report) {
    const acceptance=item.rule==='H02', data=acceptance?item.quality_comparison:item.payment_quality;
    if (!data || (!acceptance && (!['H04','H05'].includes(item.rule) || !item.stage))) return null;
    const {graph,policy}=report, ledger=graph.payment_quality_sources, compared=acceptance?data:data.comparison;
    if (![first,dual,current].includes(policy.payment_quality) || issued(policy.version)!==policy.payment_quality || ledger?.format!==policy.payment_quality ||
        !/^[a-f0-9]{64}$/.test(policy.code_sha256?.['payment_quality.py']) || !Array.isArray(ledger.rows) || !data.fields ||
        !Array.isArray(data.evidence) || (compared?ledger.format===first || Boolean(data.measure):!data.measure)) return null;
    const notes=compared?.reading_notes ?? [];
    if (!Array.isArray(notes) || notes.some(n=>!n || !Number.isInteger(n.line) || n.line<1) ||
        (!acceptance && !['risk','issue'].includes(item.status) && !(item.status==='missing' && notes.length))) return null;
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
    const notePages=new Set(notes.map(n=>n.doc+'/p'+n.page));
    if (edges.length!==1 || edges[0].from!==fields.measured_result || !same(edges[0].evidence,data.evidence) ||
        !data.evidence.every(ref=>originals.get(ref)?.printedLine || notePages.has(ref) && item.evidence.includes(ref))) return null;
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
      const f=rows[key].fact, parsed=[f.source_line.text,f.quote,f.value].map(v=>{
        const text=body(v), tokens=ledger.format===current?openMetric.exec(text.replaceAll('＜','<').replaceAll('＞','>')):closedMetric.exec(text);
        return tokens && !(strict(tokens[2]) && qualifier.test(tokens[1]))?tokens.slice(1):null;
      });
      return parsed[0] && parsed.every(m=>same(m,parsed[0]))?parsed[0]:null;
    }
    const limit=readMetric('acceptance_criteria'), basis=readMetric('inspection_basis'), value=readMetric('measured_result');
    if (compared) {
      const {observed,limits}=compared;
      if (!observed || !limits || !same(value,[observed.name,undefined,observed.value,observed.unit]) ||
          !matchesLimit(limits.contract,limit,value,notes.length) || !matchesLimit(limits.inspection,basis,value,notes.length) ||
          [limits.contract,limits.inspection].every(x=>x.result==='incomparable')) return null;
      const hasOpen=[limit,basis].some(v=>strict(v[1]));
      if ([limit,basis].some(v=>strict(v[1]) && v[0]!==observed.name)) return null;
      const equivalent=limit[0]===basis[0] && limit[3]===basis[3] && sign(limit[1])===sign(basis[1]) && scaled(limit[2])===scaled(basis[2]);
      const met=equivalent && hasOpen && [limits.contract,limits.inspection].every(v=>v.result==='within');
      if (equivalent && !hasOpen || item.status==='ok' && !met || !acceptance && met) return null;
      if (acceptance && [limits.contract,limits.inspection].some(l=>['outside','excluded_boundary'].includes(l.result)) && item.status!=='issue') return null;
      const filed=hasOpen?ledger.rows.filter(r=>r.field==='measurement_note' && [data.contract,data.receipt].includes(r.unit) &&
        (r.quote.includes(observed.name) || /测量|读数|实测|检验|仪器|检测/u.test(r.quote))):[];
      if (filed.length!==notes.length || notes.some((n,i)=>{
        const pageRef=n.doc+'/p'+n.page, node=graph.nodes.find(p=>p.id===pageRef && p.type==='page');
        return !['doc','page','unit','line','quote'].every(k=>filed[i][k]===n[k]) || !node || !data.evidence.includes(pageRef) ||
          !pages.some(p=>p.doc===n.doc && p.page===n.page && p.unit===n.unit && p.native && p.text_only) ||
          !report.calls?.pages?.some(p=>p.doc===n.doc && p.page===n.page && p.page_sha256===node.sha256 && p.response_id && p.check?.response_id) || !noteSource(report,n);
      })) return null;
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
        control('measured_result',compared.reading_notes?'验收单读数':'终验实测',observed.value+' '+observed.unit,'quality-metric measured'),
        control('acceptance_result','验收单结论',body(rows.acceptance_result.fact.source_line.text),'quality-metric'));
      for (const [role,field,label] of [['contract','acceptance_criteria','合同约定'],['inspection','inspection_basis','检验依据']]) {
        const lim=limits[role], prefix=lim.name===observed.name?'':lim.name+' ';
        const b=control(field,label,prefix+sign(lim.operator)+' '+lim.limit+' '+lim.unit,'quality-metric');
        const labels={excluded_boundary:upperBound(lim.operator)?'等于上限 · 未满足':'等于下限 · 未满足',within:'符合限值',incomparable:'指标或单位待核',reading_required:'原始读数待核'};
        const note=lim.result==='outside'?'超出 '+lim.outside_by+' '+lim.unit:labels[lim.result];
        b.append(el('span',note,'quality-evaluation '+lim.result));
        evidence.append(b);
      }
      root.append(evidence);
      for (const n of compared.reading_notes || []) {
        const doc=report.graph.documents.find(d=>d.id===n.doc), where=doc.name+' · 第 '+n.page+' 页 · 第 '+n.line+' 行';
        const source=noteSource(report,n);
        const b=action('',()=>OriginalReader.open(doc,n.page,{lineHint:n.line,...(source.rects.length?{rawRef:source.ref,printedSource:source}:{})}),'quality-note');
        b.id=root.id+'-reading-'+n.doc+'-p'+n.page+'-l'+n.line;
        b.dataset.originalLabel='测量精度说明 · '+where;
        b.setAttribute('aria-haspopup','dialog');b.setAttribute('aria-controls','page-dialog');
        b.append(el('small',where),el('strong',n.quote),glyph('arrows-angle-expand'));root.append(b);
      }
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
  function pageReferences(report,doc,page) {
    const h=report?.findings.find(f=>f.quality_comparison?.reading_notes);
    const notes=h?.quality_comparison.reading_notes.filter(n=>n.doc===doc && n.page===page);
    return notes?.length && bind(h,report)?notes.map(n=>noteSource(report,n)).filter(s=>s.rects.length):[];
  }
  return {bind,panel,pageReferences};
})();
