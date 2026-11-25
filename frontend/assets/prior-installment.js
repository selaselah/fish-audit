// Amounts come from the fixed edition's cited contract and bank rows. Keep cents exact.
const PriorInstallment = (() => {
  const formats=new Set(['prior-installment-bank-evidence-v1','prior-installment-bank-evidence-v2']);
  const labels={met:'回单合计足额',early:'早于所见足额日',same_day:'同日先后待核',partial:'首款凭证不足',
    absent:'缺首款回单',allocation:'回单归属待核',credit:'收款到账待核',disputed:'流水有疑点',
    payment_unknown:'实付时点待核',terms:'前款约定待核',unverified:'首款凭证待核'};
  const normalize=s=>String(s ?? '').normalize('NFKC').trim();
  const body=s=>normalize(s).split(':').slice(1).join(':').trim();
  function cents(value) {
    const match=normalize(value).match(/^((?:\d{1,3}(?:,\d{3})+|\d+))(?:\.(\d{1,2}))?$/);
    return match ? BigInt(match[1].replaceAll(',',''))*100n+BigInt((match[2]||'').padEnd(2,'0')) : null;
  }
  function money(value) {
    return value===null ? '待核' : '¥'+(value/100n).toLocaleString('zh-CN')+'.'+String(value%100n).padStart(2,'0');
  }
  function dateOf(fact) {
    return PhaseEvidence.dateOn(fact);
  }
  function sources(graph) {
    const ledger=graph?.prior_installment_sources;
    if (!formats.has(ledger?.format) || !Array.isArray(ledger.lines) || !Array.isArray(ledger.pages)) return [];
    const index=graphIndex(graph);
    return ledger.lines.filter(r=>{
      if (!Array.isArray(r?.facts) || typeof r.quote!=='string' || !Number.isInteger(r.page) || r.page<1) return false;
      const page=r.doc+'/p'+r.page, node=index.nodes.get(r.id), pageNode=index.nodes.get(page);
      const unit=(graph.audit_documents || graph.documents).find(d=>d.id===r.unit);
      const source=index.documents.get(r.doc);
      const id='prior-term/'+(r.line?page+'/l'+r.line:r.facts[0]);
      const links=graph.edges.filter(e=>e.type==='prior_installment_source' && e.to===r.id);
      const edge=links[0];
      if (!source || !unit || (unit.source||unit.id)!==r.doc || unit.page && unit.page!==r.page ||
          !ledger.pages.some(p=>p.doc===r.doc && p.page===r.page && p.unit===r.unit && p.role===r.role) ||
          !graph.documents_by_kind[r.role]?.includes(r.unit) || r.id!==id || node?.type!=='prior_installment_term' ||
          node.label!==r.quote || node.line!==r.line || node.doc!==r.doc || node.page!==r.page || pageNode?.type!=='page' ||
          !graph.edges.some(e=>e.type==='contains' && e.from===r.doc && e.to===page && e.evidence.includes(page)) ||
          links.length!==1 || edge.from!==page || edge.evidence.join('|')!==[page,...r.facts].join('|')) return false;
      return r.facts.every(ref=>{
        const f=index.facts.get(ref);
        return f?.doc===r.doc && f.page===r.page && (f.unit||f.doc)===r.unit && f.source_sha256===source.sha256 &&
          f.page_sha256===pageNode.sha256 && graph.edges.some(e=>e.type==='records' && e.from===page && e.to===ref && e.evidence.includes(ref));
      });
    });
  }
  function observation(row,graph) {
    return row.facts.map(ref=>graphIndex(graph).facts.get(ref)).find(f=>f?.source_line?.rects?.length &&
      f.source_line.number===row.line && f.source_line.text===row.quote && normalize(f.quote)===normalize(row.quote));
  }
  function open(row,graph) {
    const fact=observation(row,graph);
    openPage(row.doc,row.page,fact?.id || row.facts[0] || null,fact?undefined:row.line);
  }
  function read(finding,graph) {
    const proof=finding.prior_installment, index=graphIndex(graph), support=index.supports.get('finding/'+finding.id);
    if (!formats.has(proof?.format) || proof.format!==graph.prior_installment_sources?.format || proof.target_stage!==finding.stage?.clause_ref || proof.as_of!==graph.prior_installment_as_of ||
        !Object.hasOwn(labels,proof.state) || ![proof.scope,proof.evidence,proof.records,proof.terms].every(Array.isArray) ||
        proof.status!==({met:'ok',early:'risk',disputed:'risk'}[proof.state] || 'missing') ||
        !proof.evidence.every(ref=>support?.has(ref) && finding.evidence.includes(ref)) ||
        !proof.scope.every(id=>finding.scope.includes(id))) return null;
    const terms=sources(graph).filter(r=>proof.terms.includes(r.id) && proof.scope.includes(r.unit) && proof.evidence.includes(r.id));
    if (!terms.length || terms.length!==proof.terms.length || terms.length!==graph.prior_installment_sources.lines.length) return null;
    function factAt(ref,field) {
      const f=index.facts.get(ref), page=f && f.doc+'/p'+f.page, src=index.nodes.get(page);
      if (!f || f.field!==field || !proof.evidence.includes(ref) || !proof.scope.includes(f.unit||f.doc) ||
          !['anchored','confirmed'].includes(f.status) || !f.source_line?.rects?.length ||
          normalize(f.quote)!==normalize(f.source_line.text) || f.source_sha256!==index.documents.get(f.doc)?.sha256 ||
          f.page_sha256!==src?.sha256 || !graph.edges.some(e=>e.type==='records' && e.to===ref && e.from===page && e.evidence.includes(ref))) return null;
      return f;
    }
    const source=factAt(proof.source_stage,'payment_stage'), target=factAt(proof.target_stage,'payment_stage');
    const price=factAt(proof.base?.total?.ref,'total'), currency=factAt(proof.base?.currency?.ref,'currency'), unit=factAt(proof.base?.unit?.ref,'unit');
    const required=cents(proof.expected), seen=cents(proof.seen);
    if (proof.seen!==null && seen===null) return null;
    const model={finding,proof,terms,source,target,price,required,seen,records:[],designations:[],paid:null,before:null,onDay:null};
    if (proof.expected!==null) {
      const ratio=body(source?.quote).match(/^合同生效后(?:支付|付)(?:合同(?:含税)?总(?:价|额)的)?(\d{1,3})(?:\.(\d{1,4}))?%[。.]?$/u);
      const term=/^验收款(?:放款条件|支付前提|付款前提|前款条件):(?:首款|首期预付款|首付款)须(?:已付足|已付清|足额支付),以(?:付款银行成功回单为据|银行成功付款回单为准)[。]?$/u;
      if (required===null || !ratio || !target || !price || !currency || !unit || !term.test(normalize(terms[0].quote)) ||
          !/^第(?:一|0*1)期:/u.test(normalize(source.quote)) || source.id===target.id ||
          [source,target,price,currency,unit].some(f=>(f.unit||f.doc)!==terms[0].unit) ||
          terms.length!==1 || !terms[0].supported || !/^(?:人民币|人民币元|CNY|RMB)$/i.test(body(currency.quote)) ||
          !['元','人民币元'].includes(body(unit.quote)) || cents(body(price.quote))===null) return null;
      const numerator=BigInt(ratio[1]+(ratio[2]||'')), denominator=100n*10n**BigInt(ratio[2]?.length||0);
      if (required*denominator!==cents(body(price.quote))*numerator) return null;
    }
    for (const record of proof.records) {
      const refs=record?.refs;
      if (!refs) return null;
      const amount=factAt(refs.transfer_amount,'transfer_amount'), date=factAt(refs.paid_on,'paid_on'), serial=factAt(refs.transfer_ref,'transfer_ref');
      const value=cents(record.amount);
      if (seen!==null) {
        const bankFields=['payer','payee','contract_id','payment_designation','transfer_status','currency','unit'];
        const [payer,payee,id,stage,status,currency,unit]=bankFields.map(k=>factAt(refs[k],k));
        if ([amount,date,serial,payer,payee,id,stage,status,currency,unit].some(f=>!f || (f.unit||f.doc)!==record.unit) ||
            !graph.documents_by_kind.bank_receipt?.includes(record.unit) || record.duplicate_of || value===null ||
            value!==cents(body(amount.quote)) || dateOf(date)!==record.date || record.date>=proof.as_of ||
            !/^[A-Za-z0-9][A-Za-z0-9_-]*$/.test(body(serial.quote)) || !/^第(?:一|0*1)期$/u.test(body(stage.quote)) ||
            !['成功','已完成','交易成功','转账成功'].includes(body(status.quote)) || !/^(人民币|人民币元|CNY|RMB)$/i.test(body(currency.quote)) ||
            !['元','人民币元'].includes(body(unit.quote))) return null;
      }
      model.records.push({unit:record.unit,date:date && dateOf(date),value,amount,dateFact:date,serial});
    }
    if (proof.payment_date!==null) {
      model.paid=factAt(proof.payment_date_ref,'paid_on');
      const ownTitle=finding.evidence.map(ref=>index.facts.get(ref)).find(f=>f?.field==='bank_receipt');
      if (!model.paid || !ownTitle || (ownTitle.unit||ownTitle.doc)!==(model.paid.unit||model.paid.doc) ||
          dateOf(model.paid)!==proof.payment_date || proof.payment_date>=proof.as_of) return null;
    }
    if (seen!==null) {
      if (!model.records.length || required===null || new Set(model.records.map(r=>body(r.serial.quote).toLowerCase())).size!==model.records.length ||
          model.records.reduce((total,r)=>total+r.value,0n)!==seen) return null;
      const last=model.records.map(r=>r.date).sort().at(-1);
      if (seen>required || (seen===required ? proof.covered_on!==last : proof.covered_on!==null)) return null;
      if (model.paid) {
        model.before=model.records.reduce((sum,r)=>sum+(r.date<proof.payment_date?r.value:0n),0n);
        model.onDay=model.records.reduce((sum,r)=>sum+(r.date===proof.payment_date?r.value:0n),0n);
        if (model.before!==cents(proof.before) || model.onDay!==cents(proof.on_day)) return null;
      }
      const expectedState=seen<required?'partial':!model.paid?(finding.rule==='H05'?'payment_unknown':'met'):
        proof.covered_on>proof.payment_date?'early':proof.covered_on===proof.payment_date?'same_day':'met';
      if (proof.state!==expectedState) return null;
    } else if (['met','partial','early','same_day','payment_unknown'].includes(proof.state)) return null;
    if (seen===null) {
      model.designations=graph.facts.filter(f=>f.field==='payment_designation' &&
        graph.documents_by_kind.bank_receipt?.includes(f.unit||f.doc) && factAt(f.id,'payment_designation'));
    }
    model.records.sort((a,b)=>(a.date||'').localeCompare(b.date||''));
    return model;
  }
  function view(models, makeLink) {
    const panel=document.createElement('details'); panel.className='prior-panel';
    panel.open=models.some(m=>m.proof.status!=='ok');
    const header=document.createElement('summary');
    const title=box('prior-title',glyph('receipt'),el('strong','首款凭证'));
    const badge=el('span','','prior-badge'); header.append(title,badge,glyph('chevron-down')); panel.append(header);
    const area=box('prior-body'), switcher=box('prior-switch'); switcher.setAttribute('role','group');switcher.setAttribute('aria-label','核对时点');
    const perPayment=models.slice(1);
    const select=el('select'); select.setAttribute('aria-label','选择验收款回单'); select.className='prior-payments';
    perPayment.forEach((m,i)=>select.add(new Option((m.proof.payment_date || '日期待核')+' · '+(m.paid?.name || m.finding.id),String(i))));
    let atPayment=perPayment.some(m=>m.proof.status!=='ok');
    if (atPayment) select.selectedIndex=perPayment.findIndex(m=>m.proof.status!=='ok');
    const submitted=action('提交日',()=>choose(false)),paid=action('验收款实付日',()=>choose(true));
    switcher.append(submitted,paid); const details=box('prior-values');
    area.append(box('prior-controls',switcher,select),details); panel.append(area);
    function choose(next) {
      atPayment=next && perPayment.length>0; paid.disabled=!perPayment.length;
      submitted.setAttribute('aria-pressed',String(!atPayment)); paid.setAttribute('aria-pressed',String(atPayment));
      select.hidden=!atPayment || perPayment.length<2;
      const m=atPayment?perPayment[select.selectedIndex]:models[0], p=m.proof;
      panel.dataset.priorState=p.state; panel.dataset.priorMode=atPayment?'payment':'submission';
      badge.textContent=labels[p.state]; badge.dataset.status=p.status;
      const value=atPayment?m.before:m.seen, date=atPayment?p.payment_date:p.as_of;
      const summary=box('prior-amounts'), timeline=box('prior-timeline');
      summary.append(box('',el('small',atPayment?'实付日前已见':'提交时已见'),el('strong',money(value),'prior-money')),
        box('prior-required',el('small','合同约定首款'),el('strong',money(m.required))));
      details.replaceChildren(summary);
      if (value!==null && m.required>0n) {
        const bar=el('progress');bar.max=10000;bar.value=Number(value*10000n/m.required);
        bar.setAttribute('aria-label','此前已见首款占约定金额');bar.setAttribute('aria-valuetext',money(value)+' / '+money(m.required)); details.append(bar);
      }
      const asOf=box('prior-cutoff',el('span','核对至'),el('time',date || '待核'));
      if (atPayment && m.onDay>0n) asOf.append(el('span','同日另见 '+money(m.onDay),'prior-day'));
      details.append(asOf);
      if (m.seen!==null) for (const r of m.records) {
        const side=atPayment && !date ? '先后待核' : atPayment && r.date>=date ? (r.date===date?'当天':'日后') : '此前';
        const button=makeLink(r.amount, money(r.value),'回单原行'); button.classList.add('prior-slip');
        button.prepend(el('time',r.date),el('small',side));
        button.append(glyph('arrows-angle-expand'),el('span','查看首款回单','visually-hidden')); timeline.append(button);
      }
      if (timeline.childElementCount) details.append(timeline);
      if (m.designations.length) {
        const slips=el('details','','prior-designations');
        slips.append(el('summary','查看回单用途 · '+m.designations.length+' 处'));
        for (const fact of m.designations) {
          const ref=makeLink(fact,body(fact.quote),'回单用途');
          ref.prepend(el('small',fact.name+' · 第 '+fact.page+' 页')); slips.append(ref);
        }
        details.append(slips);
      }
      const links=box('prior-links');
      m.terms.forEach((row,i)=>links.append(makeLink(row,m.terms.length===1?'前款约定':'前款约定 '+(i+1),'合同原行')));
      if (m.source) links.append(makeLink(m.source,'首期比例','合同原行'));
      if (m.price) links.append(makeLink(m.price,'合同总额','合同原行'));
      if (atPayment && m.paid) links.append(makeLink(m.paid,'验收款实付日','回单原行'));
      details.append(links);
    }
    select.addEventListener('change',()=>choose(true));
    switcher.addEventListener('keydown',e=>{
      if (!perPayment.length || !['ArrowRight','ArrowLeft','Home','End'].includes(e.key)) return;
      e.preventDefault();choose(e.key==='Home'?false:e.key==='End'?true:!atPayment);(atPayment?paid:submitted).focus();
    });
    choose(atPayment); return panel;
  }
  function panel(phase,payments,graph) {
    if (!phase.prior_installment) return null;
    const models=[phase,...payments].map(f=>read(f,graph));
    if (models.some(m=>!m)) return box('prior-unavailable',glyph('question-circle'),el('span','首款凭证的原件或勾稽关系待核'));
    return view(models,(row,label)=>{
      const button=action(label,()=>row.id.startsWith('prior-term/')?open(row,graph):openPage(row.doc,row.page,row.id),'prior-link');
      button.dataset.priorRef=row.id;return button;
    });
  }
  return {sources,observation,open,read,panel};
})();
