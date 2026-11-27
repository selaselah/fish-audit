// A payment can name the failed inspection even when a later reinspection exists.
const RetestReference = (() => {
  const legacy='reinspection-receipt-reference-v1', current='reinspection-receipt-reference-v2';
  const states={original:'指向初验',final:'指向复验',unlocated:'单号未对应',unresolved:'引用待核'};
  const terms={clause:'本期付款条件',payment_designation:'回单用途',transfer_status:'交易状态',
    original_accepted_on:'初验日期',original_acceptance_result:'初验结论',original_acceptance_scope:'初验范围',
    original_defect_number:'初验缺陷编号',repair_original_acceptance:'整改所引初验单',repair_defect_number:'整改缺陷编号',
    repair_repair_number:'整改记录编号',repair_repaired_on:'整改完成日期',final_original_acceptance:'复验所引初验单',
    final_repair_number:'复验所引整改单',final_defect_number:'复验缺陷编号',final_acceptance_scope:'复验范围',
    final_acceptance_result:'复验结论',final_defect_closure:'缺陷关闭结论'};
  const same=(a,b)=>Array.isArray(a) && Array.isArray(b) && a.length===b.length && a.every((v,i)=>v===b[i]);
  const value=s=>s.slice(s.search(/[:：]/u)+1).trim();
  const heading=s=>s.split(/[:：]/u,1)[0].trim();
  const ordinal=label=>BatchPhase.ordinal(/^第([1-9][0-9]?|[一二两三四五六七八九十]{1,3})期$/u.exec(label)?.[1]);
  function issuedFormat(version) {
    if (!/^\d{4}\.\d{1,2}\.\d{1,2}\.\d+$/u.test(version)) return null;
    const since=v=>version.localeCompare(v,'en',{numeric:true})>=0;
    return since('2026.11.28.7')?current:since('2026.11.27.18')?legacy:null;
  }
  // The body and its complete heading must agree across the physical line and both filed readings.
  function printedBody(fact) {
    const raw=fact?.source_line?.text, quote=fact?.quote, copy=fact?.value;
    if (![raw,quote,copy].every(s=>typeof s==='string') || !/[:：]/u.test(raw) ||
        heading(quote)!==heading(raw) || value(quote)!==value(raw)) return null;
    return (copy===value(raw) || heading(copy)===heading(raw) && value(copy)===value(raw))?value(raw):null;
  }
  const condition=/^(合同生效|本合同生效|最终验收合格|终验合格|验收合格|验收通过|全部验收合格|质保期满|质保期届满|保修期满)后(?:(?:一次性)?(?:支付|付清|付|结算)(?:合同(?:总价|价款|总额)的?)?([0-9]{1,3}(?:\.[0-9]{1,4})?)%|一次性支付全款)$/u;
  function stageShare(body) {
    if (['验收后一次性全额结算','验收后一次性付清','验收合格后一次性付清'].includes(body)) return '100';
    const match=condition.exec(body);
    return match && (match[2] || '100');
  }
  function scheduleMatches(item,report,plan,contract,planSources) {
    const c=item.retest_reference, review=c.schedule_review, {graph}=report, ledger=graph.retest_reference_sources;
    const pid=contract+'/p1', pages=graph.payment_window_sources.pages.filter(p=>p.unit===contract);
    const index=graphIndex(graph), page=index.nodes.get(pid), control=index.nodes.get('control/H03');
    const procedures=graph.edges.filter(e=>e.type==='procedure_result' && e.to==='finding/'+plan.id);
    if (!review || !Array.isArray(review.clauses) || !Number.isSafeInteger(review.listed) || review.listed<1 ||
        !Number.isSafeInteger(review.declared) || !same(plan.scope,[contract]) || plan.status!=='missing' ||
        control?.type!=='control' || control.version!==plan.version || plan.version!==report.policy.version ||
        procedures.length!==1 || procedures[0].from!==control.id || !same(procedures[0].evidence,plan.evidence) ||
        ledger.schedule_page!==pid || pages.length!==1 || pages[0].doc!==contract || pages[0].page!==1 ||
        pages[0].document_kind!=='contract' || !pages[0].native || !pages[0].text_only ||
        index.documents.get(contract)?.pages!==1 || page?.layer!=='text' || page.clause_text_only!==true) return false;
    const links=PerformanceIndex.fieldLinks(graph);
    const cited=ref=>c.evidence.includes(ref) && plan.evidence.includes(ref) &&
      [item,plan].every(f=>links.has(ref+' finding/'+f.id));
    const rows=ledger.rows.filter(r=>r.unit===contract && ['payment_stage','payment_term'].includes(r.field));
    const headers=rows.filter(r=>r.field==='payment_term'), clauses=rows.filter(r=>r.field==='payment_stage');
    const clauseIds=new Set(review.clauses), facts=graph.facts.filter(f=>(f.unit || f.doc)===contract && f.field==='payment_stage');
    const stages=report.findings.filter(f=>f.rule==='H04' && f.stage);
    if (!c.evidence.includes(pid) || !links.has(pid+' finding/'+item.id) ||
        !rows.every(r=>r.doc===contract && r.page===1 && typeof r.quote==='string' && Number.isSafeInteger(r.line) && r.line>0) ||
        headers.length!==1 || clauses.length!==review.listed || stages.length!==clauses.length ||
        review.clauses.length!==clauses.length || clauseIds.size!==clauses.length ||
        facts.length!==clauses.length || !facts.every(f=>clauseIds.has(f.id)) ||
        !clauseIds.has(item.stage.clause_ref) || !cited(review.header)) return false;
    const [header]=headers, count=/^(?:合同价款)?分([1-9][0-9]?|[一二两三四五六七八九十]{1,3})期(?:付款|支付|结算)$/u.exec(value(header.quote));
    if (!count || BatchPhase.ordinal(count[1])!==review.declared ||
        !['付款条款','付款方式','结算条款','结算方式'].includes(heading(header.quote))) return false;
    if (plan.installment_count) {
      const raw=InstallmentCount.bind(report,review.header,plan)?.row;
      if (!raw || !InstallmentCount.bind(report,review.header,item) || !same(header.facts,[]) ||
          raw.count!==review.declared || raw.line!==header.line || raw.quote!==header.quote) return false;
    } else {
      const source=planSources.get(review.header);
      if (!PerformanceIndex.matchesPrintedField(source,report,rows,contract,'payment_term') ||
          printedBody(source.fact)!==value(header.quote)) return false;
    }
    let total=0, previous=header.line;
    for (const [i,row] of clauses.entries()) {
      const ref=review.clauses[i], source=planSources.get(ref), phase=stages[i], stage=phase.stage;
      if (row.line<=previous || ordinal(heading(row.quote))!==i+1 || !same(row.facts,[ref]) || !cited(ref) ||
          !PerformanceIndex.matchesPrintedField(source,report,rows,contract,'clause') ||
          !phase.evidence?.includes(ref) || !links.has(ref+' finding/'+phase.id)) return false;
      const body=printedBody(source.fact), share=stageShare(body);
      if (body!==value(row.quote) || !share || Number(share)<=0 || Number(share)>100 ||
          stage.clause_ref!==ref || stage.name!==heading(row.quote) || stage.clause!==body || stage.share!==share) return false;
      if (ref===item.stage.clause_ref && (!PhaseEvidence.sameStage(stage,item.stage) ||
          !/^(?:最终验收合格|终验合格|验收合格|验收通过|全部验收合格)后/u.test(body))) return false;
      // Printed shares have at most four decimal places. Add them as integers.
      const [whole,fraction='']=share.split('.');
      total+=Number(whole)*10000+Number(fraction.padEnd(4,'0'));
      previous=row.line;
    }
    return String(total/10000)===review.share_total && (review.declared!==review.listed || total!==1000000);
  }
  const failures=new Set(['不合格','验收不合格','未通过','验收未通过','拒收','最终验收不合格','终验不合格','有条件通过','待整改','整改后复验']);
  function receiptStatus(c) {
    if (c.state==='original' && failures.has(c.original_result)) return 'risk';
    if (c.state==='final') {
      if (c.days_from_final<0 || failures.has(c.final_result) || ['未关闭','待关闭','未完成','未结清'].includes(c.final_closure)) return 'risk';
      if (!c.schedule_review && c.days_from_final>0 &&
          ['合格','验收合格','全部合格','通过','验收通过','最终验收合格','终验合格'].includes(c.final_result) &&
          ['已关闭','全部关闭','缺陷已关闭'].includes(c.final_closure)) return 'ok';
    }
    return 'missing';
  }
  function bind(item,report) {
    const c=item.retest_reference;
    if (!c || item.rule!=='H05' || !item.stage || !Object.hasOwn(states,c.state)) return null;
    const {graph,policy}=report, kinds=graph.documents_by_kind, ledger=graph.retest_reference_sources;
    const format=issuedFormat(policy.version), hasReview=Object.hasOwn(c,'schedule_review');
    if (!format || c.format!==format || item.version!==policy.version || policy.retest_reference!==format ||
        !/^[a-f0-9]{64}$/.test(policy.code_sha256?.['retest_reference.py']) || ledger?.format!==format ||
        hasReview && (format!==current || c.state==='unresolved') ||
        !Array.isArray(ledger.rows) || !Array.isArray(item.evidence) || !Array.isArray(item.scope) ||
        !c.fields || c.fields.clause!==item.stage.clause_ref ||
        !Array.isArray(c.evidence) || !c.evidence.every(ref=>item.evidence.includes(ref)) || !Array.isArray(c.citations) ||
        !kinds.bank_receipt?.includes(c.bank) || !item.scope.includes(c.bank)) return null;
    const originals=new Map(PerformanceIndex.originals(item,graph).map(s=>[s.fact.id,s])), rows={};
    function bound(key,field,unit) {
      const id=c.fields[key], source=originals.get(id);
      if (!c.evidence.includes(id) || !PerformanceIndex.matchesPrintedField(source,report,ledger.rows,unit,field)) return false;
      rows[key]=source;return true;
    }
    const edges=graph.edges.filter(e=>e.type==='receipt_names_inspection' && e.from===c.fields.citation);
    const originalsOfPayment=PaymentAcceptance.sources(graph);
    if (!ApprovalClock.inspectionNotes(report,item,originalsOfPayment)) return null;
    const citations=originalsOfPayment.filter(r=>c.citations.includes(r.id) && r.unit===c.bank && r.role==='bank_receipt');
    if (!c.citations.length || citations.length!==c.citations.length || !citations.every(r=>c.evidence.includes(r.id))) return null;
    if (c.fields.citation) {
      const own=citations.filter(r=>r.kind==='citation' && PaymentAcceptance.observation(r,graph)?.id===c.fields.citation);
      if (own.length!==1 || !bound('citation','payment_acceptance_ref',c.bank) || value(own[0].quote)!==c.number ||
          !/^(?=.*[0-9])[a-zA-Z0-9][a-zA-Z0-9._-]{1,63}$/.test(c.number)) return null;
    }
    if (c.state==='unresolved') return !edges.length && !c.units && c.status==='missing'?rows:null;
    const units=c.units, contract=kinds.contract?.length===1 && kinds.contract[0];
    if (kinds.contract_addendum?.length && !ApprovalChange.scopeEntries(report.findings.find(f=>f.rule==='H02') || {},report).length) return null;
    if (!rows.citation || citations.length!==1 || citations[0].disputed || !units || !contract || !bound('clause','clause',contract)) return null;
    const h02=report.findings.find(f=>f.rule==='H02'), steps=h02?.reinspection?.steps;
    if (!Array.isArray(steps) || steps.length!==3 || new Set(Object.values(units)).size!==3 ||
        !['original','repair','final'].every(role=>steps.some(s=>s.role===role && s.unit===units[role]) && item.scope.includes(units[role])) ||
        !kinds.remediation?.includes(units.repair) ||
        ![units.original,units.final].every(u=>kinds.acceptance?.includes(u) || kinds.reinspection?.includes(u))) return null;
    for (const unit of [contract,c.bank,units.original,units.repair,units.final]) {
      const pages=graph.payment_window_sources?.pages?.filter(p=>p.unit===unit);
      if (!pages?.length || !pages.every(p=>p.native && p.text_only)) return null;
    }
    for (const key of ['payment_designation','transfer_status','paid_on']) if (!bound(key,key,c.bank)) return null;
    const keys=['original_acceptance_number','final_acceptance_number','final_accepted_on',...Object.keys(terms).filter(k=>/^(original|repair|final)_/u.test(k))];
    for (const key of keys) {
      const split=key.indexOf('_'), role=key.slice(0,split);
      if (!bound(key,key.slice(split+1),units[role])) return null;
    }
    function literal(key) {
      const f=rows[key].fact, raw=value(f.source_line.text);
      return value(f.quote)===raw && (f.value===raw || f.value===f.quote)?raw:null;
    }
    const initial=literal('original_acceptance_number'), final=literal('final_acceptance_number'), defect=literal('original_defect_number');
    if (!initial || !final || initial===final || initial!==c.original_number || final!==c.final_number ||
        initial!==literal('repair_original_acceptance') || initial!==literal('final_original_acceptance') ||
        !defect || defect!==literal('repair_defect_number') || defect!==literal('final_defect_number') ||
        !literal('repair_repair_number') || literal('repair_repair_number')!==literal('final_repair_number') ||
        !c.original_result || !c.final_result || !c.final_closure ||
        literal('original_acceptance_result')!==c.original_result || literal('final_acceptance_result')!==c.final_result ||
        literal('final_defect_closure')!==c.final_closure || literal('citation')!==c.number) return null;
    const target=c.number===initial?'original':c.number===final?'final':'unlocated';
    if (target!==c.state || (target==='unlocated'?edges.length!==0:
        edges.length!==1 || edges[0].to!==c.fields[target+'_acceptance_number'] || !same(edges[0].evidence,c.evidence))) return null;
    const end=WarrantyDates.parse(rows.final_accepted_on.fact), paid=WarrantyDates.parse(rows.paid_on.fact);
    const levels=['ok','missing','risk','issue'];
    if (!end || !paid || end.iso!==c.final_on || paid.iso!==c.paid_on || c.status!==receiptStatus(c) ||
        levels.indexOf(item.status)<levels.indexOf(c.status) ||
        (target==='final'?paid.days-end.days!==c.days_from_final:Object.hasOwn(c,'days_from_final'))) return null;
    if (format===current) {
      const dates={original:WarrantyDates.parse(rows.original_accepted_on.fact)?.iso,
        repair:WarrantyDates.parse(rows.repair_repaired_on.fact)?.iso,final:end.iso};
      const designation=literal('payment_designation'), index=ordinal(item.stage.name);
      const registered=new Set(PerformanceIndex.originals(h02,graph).map(s=>s.fact.id));
      if (!keys.every(k=>registered.has(c.fields[k])) || !dates.original || !dates.repair ||
          dates.original>dates.repair || dates.repair>end.iso ||
          !steps.every(s=>s.date===dates[s.role] && h02.scope?.includes(s.unit)) ||
          !['交易成功','转账成功','成功','已完成'].includes(literal('transfer_status')) ||
          designation!==item.stage.name && (!index || ordinal(designation)!==index)) return null;
      const plans=report.findings.filter(f=>f.rule==='H03');
      const plan=plans[0];
      if (plans.length!==1 || !/^H03-[1-9]\d*$/u.test(plan.id) || !Array.isArray(plan.evidence) ||
          !plan.scope?.includes(contract) || !item.scope.includes(contract)) return null;
      const planSources=new Map(PerformanceIndex.originals(plan,graph).map(s=>[s.fact.id,s]));
      if (!planSources.has(c.fields.clause)) return null;
      if (hasReview) {
        if (!scheduleMatches(item,report,plan,contract,planSources)) return null;
        rows.schedule=plan;
      } else if (plan.status!=='ok') return null;
    }
    return rows;
  }
  function panel(item,report,rev) {
    const rows=bind(item,report);
    if (!rows) return null;
    const c=item.retest_reference, root=el('section','','quality-payment retest-reference');
    root.id='retest-'+item.id;root.setAttribute('aria-label','回单所引验收单');
    Object.assign(root.dataset,{retestFinding:item.id,caseId:report.case_id,rev:String(rev)});
    const control=(key,label,display,cls)=>PerformanceIndex.originalButton(root.id+'-'+key,rows[key],label,display,cls);
    const stateLabel=states[c.state]+(rows.schedule && c.status==='risk'?' · 风险':'');
    root.append(box('quality-heading',el('h4','回单所引验收单'),el('span',stateLabel,c.status)));
    if (rows.citation) root.append(control('citation','回单引用单号',c.number,'retest-citation'));
    if (c.state==='unresolved') {
      root.append(el('p','需核实回单、初验、整改和复验之间的对应关系。','retest-note'));
      return root;
    }
    const numbers=box('quality-readings');
    for (const [role,label] of [['original','初验'],['final','复验']]) {
      const key=role+'_acceptance_number', button=control(key,label+' · '+c[role+'_result'],c[role+'_number'],'quality-term');
      if (c.state===role) button.classList.add('retest-match');
      numbers.append(button);
    }
    const dates=box('quality-dates',control('final_accepted_on','复验单所列日',c.final_on,'quality-day'),
      control('paid_on','回单付款日',c.paid_on,'quality-day'));
    if (c.state==='final') {
      const days=c.days_from_final, order=el('p',days?'回单'+(days<0?'早 ':'晚 ')+Math.abs(days)+' 天':'同日，先后待核','quality-order');
      order.id=root.id+'-order';dates.append(order);
    }
    if (c.state==='unlocated') numbers.append(el('p','请补取回单所引编号的验收原件。','quality-order'));
    const more=el('details','','quality-terms'), summary=el('summary','核对付款条件与整改原行');summary.id=root.id+'-terms';more.append(summary);
    for (const [key,label] of Object.entries(terms)) more.append(control(key,label,value(rows[key].fact.source_line.text),'quality-term'));
    root.append(numbers,dates);
    if (rows.schedule) {
      const review=c.schedule_review, summary='合同约定 '+review.declared+' 期，列出 '+review.listed+' 期，比例合计 '+review.share_total+'%。';
      const jump=Team.paperLink('',report.case_id,'retest-schedule',new URLSearchParams({rev,finding:rows.schedule.id}));
      jump.id=root.id+'-schedule';
      jump.dataset.originalLabel='付款安排待核 · R'+rev+' · '+rows.schedule.id+' · '+summary;
      jump.append(box('',el('strong','付款安排待核'),el('span',summary)),el('span','查看 R'+rev+' · H03 依据','retest-schedule-link'));
      root.append(jump);
    }
    root.append(more);return root;
  }
  return {bind,panel};
})();
