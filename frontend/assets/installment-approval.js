const InstallmentApproval = (() => {
  const labels={unresolved:'审批原件待核',multiple:'多份审批单待辨',bank_scope:'扣款对应关系待核',identity:'户名或合同待核',
    other_stage:'审批单列了其他期款',other_receipt:'审批单引用其他验收单',other_authority:'所列审批岗位不同',
    refused:'决定列明不同意支付',later:'审批日期晚于付款',same_day:'同日先后待核',earlier:'审批日期早于付款，签批权限待核'};
  const headings={合同编号:'contract_id',付款户名:'payer',收款户名:'payee',审批期次:'stage',所据验收单号:'inspection',
    审批岗位:'authority',审批决定:'decision',审批日期:'date'};
  const titles=['付款审批单','对公付款审批单'];
  const bankFields=['contract_id','payer','payee','payment_designation','transfer_status','paid_on'];
  const same=(a,b)=>Array.isArray(a) && Array.isArray(b) && a.length===b.length && a.every((v,i)=>v===b[i]);
  const printed=quote=>quote.slice(quote.search(/[:：]/u)+1).trim();
  function bind(item,report,request,readRow) {
    const c=item.inspection_use, a=c.approval, g=report.graph, pages=g.inspection_use_sources.approvals;
    if (!request || !/^[a-f0-9]{64}$/u.test(report.policy.code_sha256?.['installment_approval.py']) ||
        !Object.hasOwn(labels,a.state) || a.bank!==c.bank || a.request!==request.id || a.required!==request.authority ||
        !request.quote.includes(request.authority) || !Array.isArray(a.evidence) || !a.evidence.every(id=>c.evidence.includes(id)) ||
        ![a.request,c.citation,c.number_ref,item.stage.clause_ref].every(id=>a.evidence.includes(id)) ||
        !same(a.documents,[...new Set(pages.map(p=>p.doc))]) || !same(a.rows,pages.flatMap(p=>p.rows.map(r=>r.id))) ||
        new Set(a.rows).size!==a.rows.length || a.status!==(['refused','later'].includes(a.state) || a.clock?.state==='debit_first' || a.names?.state==='different'?'risk':'missing')) return null;
    const links=g.edges.filter(e=>e.type==='compares_payment_approval' && e.from===a.request && e.evidence?.[1]===c.citation);
    if (!same(links.map(e=>e.to),a.rows) || links.some(e=>!same(e.evidence,[a.request,c.citation,e.to]))) return null;
    const entries=[];
    for (const page of pages) {
      if (!a.evidence.includes(page.doc+'/p'+page.page)) return null;
      for (const row of page.rows) {
        const doc=readRow(row);
        const column=row.quote.split(/[:：]/u,1)[0].trim();
        const field=titles.includes(row.quote.trim())?'title':ApprovalClock.supports(c.format) && ApprovalClock.signed.includes(column)?'signed_at':ApprovalNames.supports(c.format) && ApprovalNames.signers.includes(column)?'signed_by':headings[column] || 'other';
        if (!doc || !row.id.startsWith('payment-approval/') || page.doc!==row.doc || page.page!==row.page || page.unit!==row.unit || field!==row.field ||
            ![row.id,...row.facts].every(id=>a.evidence.includes(id))) return null;
        entries.push({row,doc,scope:'approval_sheet'});
      }
    }
    function withBankRows() {
      const bankRows=ApprovalClock.bind(item,report,entries,readRow);
      if (!bankRows) return null;
      const terms=ApprovalNames.bind(item,report,entries,readRow);
      return terms ? [...entries,...bankRows,...terms] : null;
    }
    if (a.documents.length!==1) return a.state==='multiple' && !a.fields && !a.bank_fields?withBankRows():null;
    if (!a.fields) return a.state==='unresolved' && !a.bank_fields?withBankRows():null;
    const [sheet]=pages, fields=Object.fromEntries(entries.map(e=>[e.row.field,e.row]));
    const names=['title',...Object.values(headings)];
    if (fields.signed_at) names.push('signed_at');
    if (fields.signed_by) names.push('signed_by');
    if (pages.length!==1 || !sheet.complete || sheet.unit!==sheet.doc || sheet.page!==1 || entries.length!==names.length ||
        entries[0]?.doc.ext!=='.pdf' || entries[0].doc.pages!==1 || entries[0].row.field!=='title' ||
        Object.keys(a.fields).length!==names.length || names.some(k=>!fields[k]?.rects.length || a.fields[k]!==fields[k].id)) return null;
    const v=Object.fromEntries(names.map(k=>[k,printed(fields[k].quote)]));
    if (fields.signed_by && !ApprovalNames.list(v.signed_by,c.format) && !(c.format!==ApprovalNames.firstFormat && ApprovalNames.unnamed.has(v.signed_by))) return null;
    const phase=/^第([0-9一二两三四五六七八九十]+)期(预付款|验收款|质保金)$/u.exec(v.stage);
    const listed=WarrantyDates.printedDay(v.date), index=phase && BatchPhase.ordinal(phase[1]);
    if (!index || !listed || listed!==a.listed_on || !['同意支付','批准支付','不同意支付','不批准支付'].includes(v.decision)) return null;
    if (!a.bank_fields) return a.state==='bank_scope' && !a.paid_on ? withBankRows() : null;
    const sources=new Map(PerformanceIndex.originals(item,g).map(source=>[source.fact.id,source]));
    const ledger=g.retest_reference_sources?.rows?.length?g.retest_reference_sources.rows:g.payment_quality_sources?.rows;
    if (!same(g.documents_by_kind.bank_receipt,[a.bank]) || !Array.isArray(ledger) || Object.keys(a.bank_fields).length!==bankFields.length) return null;
    const bank={};
    for (const k of bankFields) {
      const id=a.bank_fields[k], source=sources.get(id);
      if (!a.evidence.includes(id) || !PerformanceIndex.matchesPrintedField(source,report,ledger,a.bank,k)) return null;
      bank[k]=k==='paid_on'?WarrantyDates.parse(source.fact)?.iso:printed(source.fact.source_line.text);
    }
    if (!bank.paid_on || a.paid_on!==bank.paid_on || !['交易成功','转账成功','成功','已完成'].includes(bank.transfer_status)) return null;
    const stage=/^第(.+)期$/u.exec(item.stage.name)?.[1];
    let expected='earlier';
    if (['contract_id','payer','payee'].some(k=>bank[k]!==v[k])) expected='identity';
    else if (index!==BatchPhase.ordinal(stage) || phase[2]!=='验收款') expected='other_stage';
    else if (v.inspection!==c.number) expected='other_receipt';
    else if (v.authority!==a.required) expected='other_authority';
    else if (['不同意支付','不批准支付'].includes(v.decision)) expected='refused';
    else if (a.listed_on>bank.paid_on) expected='later';
    else if (a.listed_on===bank.paid_on) expected='same_day';
    return expected===a.state ? withBankRows() : null;
  }
  function panel(a,entries,button,finding) {
    const section=el('section','','installment-approval'), heading=el('h5','所附付款审批单');
    section.id='payment-approval-'+finding;section.dataset.approvalState=a.state;
    section.setAttribute('aria-label','所附付款审批单');
    if (a.fields) heading.textContent=entries[0].doc.name+' · 第 '+entries[0].row.page+' 页';
    const clock=a.clock;
    section.append(box('inspection-use-heading',heading,el('span',clock?ApprovalClock.labels[clock.state]:labels[a.state],clock?.state==='debit_first' || ['later','refused'].includes(a.state)?'risk':'missing')));
    if (a.names) {
      const group=el('section','','named-approvers'), head=el('h6','合同与签批人'), rows=el('div','','approval-rows approval-times');
      group.setAttribute('aria-label','合同与签批人');group.dataset.nameState=a.names.state;group.id='contract-approver-'+finding;
      const missing=a.names.state==='partial'?a.names.required.filter(n=>!a.names.listed.includes(n)):[];
      const status=missing.length?missing.join('、')+'签批待补':ApprovalNames.labels[a.names.state];
      group.append(box('inspection-use-heading',head,el('span',status,a.names.state==='different'?'risk':'missing')));
      const contract=entries.filter(e=>e.scope==='contract_term');
      const signers=entries.filter(e=>e.row.id===a.names.signed_by);
      if (a.names.required && contract.length===1 && signers.length===1) rows.classList.add('approval-name-pair');
      rows.append(...[...contract,...signers].map(button));
      group.append(rows);section.append(group);
    }
    if (clock) {
      section.dataset.clock=clock.state;
      const times=el('div','','approval-rows approval-times');
      times.id='payment-clock-'+finding;
      times.setAttribute('role','group');times.setAttribute('aria-label',a.paid_on+' 签批与银行时刻');
      for (const entry of entries.filter(e=>e.row.id===clock.signed || e.scope==='bank_time')) times.append(button(entry));
      section.append(el('p',a.paid_on+' · 本期付款','approval-days'),times);
    } else if (a.listed_on && a.paid_on) section.append(el('p','审批单 '+a.listed_on+'　/　回单付款 '+a.paid_on,'approval-days'));
    const primary=new Set(['stage','inspection','decision','date']), visible=entries.filter(e=>primary.has(e.row.field));
    if (!a.names) {
      const grid=el('div','','approval-rows');
      grid.append(...visible.map(button));section.append(grid);
    }
    const rest=entries.filter(e=>!primary.has(e.row.field) && e.scope!=='bank_time' && e.scope!=='contract_term' && e.row.id!==a.names?.signed_by && !(clock && e.row.id===clock.signed));
    const fields=a.names?[...visible,...rest]:rest;
    if (fields.length) {
      const details=el('details'), more=el('div','','approval-rows');
      details.append(el('summary',a.names?'核对期次、验收单号及审批原文':'核对标题、户名及审批岗位'));
      more.append(...fields.map(button));details.append(more);section.append(details);
    }
    return section;
  }
  return {bind,panel};
})();
