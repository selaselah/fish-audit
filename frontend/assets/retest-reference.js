// A payment can name the failed inspection even when a later reinspection exists.
const RetestReference = (() => {
  const format='reinspection-receipt-reference-v1';
  const states={original:'指向初验',final:'指向复验',unlocated:'单号未对应',unresolved:'引用待核'};
  const terms={clause:'本期付款条件',payment_designation:'回单用途',transfer_status:'交易状态',
    original_accepted_on:'初验日期',original_acceptance_result:'初验结论',original_acceptance_scope:'初验范围',
    original_defect_number:'初验缺陷编号',repair_original_acceptance:'整改所引初验单',repair_defect_number:'整改缺陷编号',
    repair_repair_number:'整改记录编号',repair_repaired_on:'整改完成日期',final_original_acceptance:'复验所引初验单',
    final_repair_number:'复验所引整改单',final_defect_number:'复验缺陷编号',final_acceptance_scope:'复验范围',
    final_acceptance_result:'复验结论',final_defect_closure:'缺陷关闭结论'};
  const same=(a,b)=>Array.isArray(a) && Array.isArray(b) && a.length===b.length && a.every((v,i)=>v===b[i]);
  const value=s=>s.slice(s.search(/[:：]/u)+1).trim();
  function bind(item,report) {
    const c=item.retest_reference;
    if (!c || c.format!==format || item.rule!=='H05' || !item.stage || !Object.hasOwn(states,c.state)) return null;
    const {graph,policy}=report, kinds=graph.documents_by_kind, ledger=graph.retest_reference_sources;
    if (policy.retest_reference!==format || !/^[a-f0-9]{64}$/.test(policy.code_sha256?.['retest_reference.py']) ||
        ledger?.format!==format || !Array.isArray(ledger.rows) || !c.fields || c.fields.clause!==item.stage.clause_ref ||
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
    if (!rows.citation || citations.length!==1 || citations[0].disputed || !units || !contract || !bound('clause','clause',contract)) return null;
    const steps=report.findings.find(f=>f.rule==='H02')?.reinspection?.steps;
    if (!steps || steps.length!==3 || new Set(Object.values(units)).size!==3 ||
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
        literal('original_acceptance_result')!==c.original_result || literal('final_acceptance_result')!==c.final_result ||
        literal('final_defect_closure')!==c.final_closure || literal('citation')!==c.number) return null;
    const target=c.number===initial?'original':c.number===final?'final':'unlocated';
    if (target!==c.state || (target==='unlocated'?edges.length!==0:
        edges.length!==1 || edges[0].to!==c.fields[target+'_acceptance_number'] || !same(edges[0].evidence,c.evidence))) return null;
    const end=WarrantyDates.parse(rows.final_accepted_on.fact), paid=WarrantyDates.parse(rows.paid_on.fact);
    if (!end || !paid || end.iso!==c.final_on || paid.iso!==c.paid_on ||
        (target==='final'?paid.days-end.days!==c.days_from_final:Object.hasOwn(c,'days_from_final'))) return null;
    return rows;
  }
  function panel(item,report,rev) {
    const rows=bind(item,report);
    if (!rows) return null;
    const c=item.retest_reference, root=el('section','','quality-payment retest-reference');
    root.id='retest-'+item.id;root.setAttribute('aria-label','回单所引验收单');
    Object.assign(root.dataset,{retestFinding:item.id,caseId:report.case_id,rev:String(rev)});
    const control=(key,label,display,cls)=>PerformanceIndex.originalButton(root.id+'-'+key,rows[key],label,display,cls);
    root.append(box('quality-heading',el('h4','回单所引验收单'),el('span',states[c.state],c.status)));
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
    root.append(numbers,dates,more);return root;
  }
  return {bind,panel};
})();
