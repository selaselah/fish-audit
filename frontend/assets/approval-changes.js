// Compare the filed approval with the wording and dates printed on the supplementary agreement.
const ApprovalChange = (() => {
  const supportsScope=version=>version==='cited-inspection-payment-use-v8' || version===ApprovalNames.jointFormat;
  const stateLabels={pending:'版本及范围待核',terms:'两版条款已定位',before:'审批早于所列盖章日',after:'审批晚于所列盖章日',same_day:'同日先后待核'};
  const columns={补充协议编号:'number',原合同编号:'base_number',采购方:'buyer',供应方:'seller',采购标的:'subject',
    变更范围:'scope',原签批约定:'previous',变更后签批约定:'revised',变更适用时点:'timing',协议生效条款:'effect',
    甲方签章:'buyer_seal',乙方签章:'seller_seal',甲方盖章日期:'buyer_date',乙方盖章日期:'seller_date'};
  const same=(a,b)=>Array.isArray(a) && Array.isArray(b) && a.length===b.length && a.every((x,i)=>x===b[i]);
  const value=r=>r.quote.slice(r.quote.search(/[:：]/u)+1).trim();
  const label=r=>r.quote.split(/[:：]/u,1)[0].trim();
  function bind(item,report) {
    const c=item.approval_change,g=report.graph,ledger=g.inspection_use_sources,format=report.policy.inspection_use;
    if (!c || !['H04','H05'].includes(item.rule) || !item.stage || !item.stage_approvers?.length ||
        (format!=='cited-inspection-payment-use-v7' && !supportsScope(format)) || ledger?.format!==format || !/^[a-f0-9]{64}$/u.test(report.policy.code_sha256?.['approval_changes.py']) ||
        !Object.hasOwn(stateLabels,c.state) || !['risk','missing'].includes(c.status) || item.status==='ok' || (c.status==='risk' && item.status==='missing')) return null;
    const supported=new Set(traceReferences(g,item)),refs=new Set(c.evidence);
    if (refs.size!==c.evidence.length || c.evidence.some(r=>!supported.has(r) || !item.evidence.includes(r)) || !refs.has(item.stage.clause_ref)) return null;
    const changes=ledger.approver_changes;
    if (!changes?.length || !same(c.documents,changes.map(p=>p.doc)) || !same(c.rows,changes.flatMap(p=>p.rows.map(r=>r.id)))) return null;
    const rows=[...ledger.rows,...['approver_changes','approver_terms','approvals','bank_clocks'].flatMap(k=>(ledger[k] || []).flatMap(p=>p.rows))];
    const entries=new Map();
    for (const r of rows.filter(r=>refs.has(r.id))) {
      const doc=InspectionUse.original(r,report,c.evidence);
      if (!doc || entries.has(r.id)) return null;
      entries.set(r.id,{row:r,doc});
    }
    if ([...c.rows,...item.stage_approvers,...c.evidence.filter(s=>/^(approval-change|contract-approver|payment-approval|payment-clock|inspection-use)\//u.test(s))].some(r=>!entries.has(r))) return null;
    const row=id=>entries.get(id)?.row;
    if (c.state==='pending') return !c.fields && !c.issued_on && c.status==='missing'?[...entries.values()]:null;
    const p=changes[0],amendment=Object.fromEntries(p.rows.map(r=>[r.field,r]));
    const original=row(c.original),proof=PerformanceIndex.unitPdfOriginal(g,c.execution,'addendum'),signature=proof?.record;
    if (changes.length!==1 || !p.complete || p.doc!==p.unit || !same(g.documents_by_kind.contract_addendum,[p.unit]) ||
        p.rows.length!==Object.keys(columns).length+1 || p.rows.some(r=>c.fields?.[r.field]!==r.id || !r.rects.length ||
        r.unit!==p.doc || r.page!==1 || r.field!=='title' && columns[label(r)]!==r.field) ||
        !Object.values(columns).every(k=>amendment[k]) || !amendment.title || !original || !same(item.stage_approvers,[original.id]) ||
        report.policy.addendum_pdf!=='pdf-addendum-execution-v1' || !/^[a-f0-9]{64}$/u.test(report.policy.code_sha256?.['addendum_execution.py']) ||
        !['typeset','current'].includes(signature?.state) || signature.state!==c.signature_state || !refs.has(signature.id) || !proof.refs.every(id=>refs.has(id)) ||
        signature.unit!==p.doc || signature.original_sha256!==entries.get(amendment.title.id).doc.sha256) return null;
    const before=ApprovalNames.clause(original,format);
    const after=ApprovalNames.clause({quote:'付款签批约定：'+value(amendment.revised)},format);
    if (!before || !after || before.index!==after.index || before.role!==after.role ||
        !same(before.names,c.before) || !same(after.names,c.after) || value(original)!==value(amendment.previous) ||
        value(amendment.scope)!=='仅变更'+item.stage.name+before.role+'签批人，其余条款不变' ||
        value(amendment.timing)!=='仅适用于本协议生效后签发的付款审批单' ||
        !['本协议自双方盖章之日起生效','本补充协议自双方盖章之日起生效'].includes(value(amendment.effect))) return null;
    const sources=new Map(PerformanceIndex.originals(item,g).map(s=>[s.fact.id,s]));
    const observations=g.retest_reference_sources?.rows?.length?g.retest_reference_sources.rows:g.payment_quality_sources?.rows || [];
    function fieldsOK(fields,unit,keys) {
      return fields && keys.every(k=>{
        const id=fields[k];return refs.has(id) && PerformanceIndex.matchesPrintedField(sources.get(id),report,observations,unit,k);
      }) && Object.keys(fields).length===keys.length;
    }
    const identity=['contract_id','buyer','seller','subject'];
    const text=id=>value({quote:sources.get(id).fact.source_line.text});
    if (!fieldsOK(c.contract_fields,original.unit,identity) ||
        identity.some(k=>text(c.contract_fields[k])!==value(amendment[k==='contract_id'?'base_number':k])) ||
        ['buyer','seller'].some(k=>![value(amendment[k])+'（已盖章）',value(amendment[k])+'(已盖章)'].includes(value(amendment[k+'_seal'])))) return null;
    const buyer=WarrantyDates.printedDay(value(amendment.buyer_date)),seller=WarrantyDates.printedDay(value(amendment.seller_date));
    if (!buyer || !seller || c.buyer_on!==buyer || c.seller_on!==seller || c.last_seal_on!==[buyer,seller].sort()[1]) return null;
    if (c.state==='terms') return !c.issued_on && c.status==='missing'?[...entries.values()]:null;
    const sheets=ledger.approvals,af=c.approval_fields,kinds=g.documents_by_kind;
    if (item.rule!=='H05' || sheets?.length!==1 || !sheets[0].complete || c.approval!==sheets[0].doc ||
        !af || Object.keys(af).length!==sheets[0].rows.length || sheets[0].rows.some(r=>af[r.field]!==r.id || !r.rects.length || !row(r.id)) ||
        kinds.bank_receipt?.length!==1 || kinds.reinspection?.length!==1 || kinds.acceptance?.length!==1 ||
        !fieldsOK(c.bank_fields,kinds.bank_receipt[0],['contract_id','payer','payee','payment_designation','transfer_status','paid_on','payment_acceptance_ref']) ||
        !fieldsOK(c.receipt_fields,kinds.reinspection[0],[...identity,'acceptance_number']) ||
        !fieldsOK(c.initial_fields,kinds.acceptance[0],[...identity,'acceptance_number'])) return null;
    const raw=k=>row(af[k])?value(row(af[k])):'',b=k=>text(c.bank_fields[k]),receipt=text(c.receipt_fields.acceptance_number);
    const note=row(c.request);
    if (!note || note.kind!=='approval' || note.unit!==kinds.reinspection[0] || note.authority!==raw('authority') || note.disputed ||
        note.index!==before.index || note.role!==before.role || raw('stage')!==item.stage.name+before.role ||
        receipt===text(c.initial_fields.acceptance_number) || raw('inspection')!==receipt || b('payment_acceptance_ref')!==receipt ||
        ![item.stage.name,raw('stage')].includes(b('payment_designation')) || !['交易成功','转账成功','成功','已完成'].includes(b('transfer_status')) ||
        identity.some(k=>[c.receipt_fields,c.initial_fields].some(fs=>text(fs[k])!==text(c.contract_fields[k]))) ||
        Object.entries({contract_id:'contract_id',payer:'buyer',payee:'seller'}).some(([k,v])=>b(k)!==raw(k) || b(k)!==text(c.contract_fields[v]))) return null;
    const issued=WarrantyDates.printedDay(raw('date')),paid=WarrantyDates.printedDay(b('paid_on'));
    if (!issued || c.issued_on!==issued || !paid || c.paid_on!==paid || !af.signed_at) return null;
    const signed=ApprovalClock.clock(row(af.signed_at));
    if (!signed?.at || signed.day && signed.day!==issued || signed.zone!=='+08:00') return null;
    const days=(Date.parse(issued)-Date.parse(c.last_seal_on))/86400000;
    const listed=(af.signed_by && ApprovalNames.list(raw('signed_by'),format)) || [];
    const expected=days<0?before.names:days>0?after.names:[];
    const joint=ApprovalNames.jointDifference(expected,listed,format);
    const different=Boolean(joint || listed.length && expected.length && listed.every(n=>!expected.includes(n)));
    const partial=listed.length && listed.length<expected.length && listed.every(n=>expected.includes(n));
    const missing=joint || partial ? expected.filter(n=>!listed.includes(n)) : [];
    const nameLinks=g.edges.filter(e=>e.type==='compares_approval_names' && e.to===af.signed_by);
    if (joint) {
      const clause=days<0?original.id:amendment.revised.id;
      if (!same(c.other_names,joint.other) || nameLinks.length!==1 || nameLinks[0].from!==clause || !same(nameLinks[0].evidence,c.evidence)) return null;
    } else if (Object.hasOwn(c,'other_names') || nameLinks.length) return null;
    const refused=['不同意支付','不批准支付'].includes(raw('decision'));
    const clocks=ledger.bank_clocks;
    if (clocks?.length!==1 || !clocks[0].complete || !ApprovalClock.bankPage(report,clocks[0]) || clocks[0].unit!==kinds.bank_receipt[0] ||
        clocks[0].rows.some(r=>!row(r.id))) return null;
    const debits=clocks[0].rows.filter(r=>r.field==='debit_time');
    const early=paid<issued || (paid===issued && debits.length===1 && ApprovalClock.compare(signed,ApprovalClock.clock(debits[0]),paid).state==='debit_first');
    const edge=g.edges.filter(e=>e.type==='dates_approval_change' && e.from===amendment.revised.id && e.to===af.date);
    if (c.state!==(days<0?'before':days>0?'after':'same_day') || days!==c.days_from_seals || !same(c.listed,listed) || !same(missing,c.missing_names) ||
        c.printed_difference!==different || c.refused!==refused || c.early_debit!==early || c.status!==(different || refused || early?'risk':'missing') ||
        edge.length!==1 || !same(edge[0].evidence,c.evidence)) return null;
    return [...entries.values()];
  }

  function scopeEntries(item,report) {
    const scope=item.approval_change_scope;
    if (!supportsScope(report.policy.inspection_use) || !scope || !['H02','H03'].includes(item.rule) ||
        !item.scope.includes(scope.unit) || !Array.isArray(scope.evidence)) return [];
    const terms=report.findings.find(f=>f.rule==='H04' && f.stage?.clause_ref===scope.clause_ref && f.stage.name===scope.stage &&
      f.approval_change?.state==='terms' && f.approval_change.fields.scope===scope.scope_ref && f.approval_change.execution===scope.execution &&
      same(f.approval_change.documents,[scope.unit]) && same(f.approval_change.evidence,scope.evidence));
    if (!terms) return [];
    const refs=new Set(traceReferences(report.graph,item));
    if (scope.evidence.some(ref=>!refs.has(ref) || !item.evidence.includes(ref))) return [];
    return bind(terms,report) || [];
  }

  function panel(item,report,rev) {
    const entries=bind(item,report),c=item.approval_change;
    if (!entries) return el('p','签批变更的原件定位待核。','scope-empty');
    const field=new Map(entries.map(e=>[e.row.id,e])),used=new Set();
    const root=el('section','','inspection-use approval-change'), prefix='approver-change-'+item.id;
    root.id=prefix;Object.assign(root.dataset,{useFinding:item.id,caseId:report.case_id,rev:String(rev),status:c.status,state:c.state});
    root.setAttribute('aria-label','签批人变更');
    root.append(box('inspection-use-heading',el('h4','签批人变更'),el('span',stateLabels[c.state])));
    function button(id,heading,display) {
      const e=field.get(id),r=e.row,button=action('',()=>InspectionUse.open(e,report),'inspection-use-row');
      const place='第 '+r.page+' 页 · 第 '+r.line+' 行';used.add(id);
      button.id=prefix+'-'+id.replaceAll('/','-');button.dataset.source=id;
      button.title=e.doc.name+' · '+place;button.dataset.originalLabel=(heading || label(r))+' · '+button.title;
      button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-controls','page-dialog');button.setAttribute('aria-description',e.doc.name);
      button.append(el('span',heading || label(r),'time-label'),el('strong',display || value(r)),el('small',place),glyph('arrows-angle-expand'));
      return button;
    }
    if (c.fields) {
      const names=el('div','','approval-rows approval-times approval-name-pair');
      names.append(button(c.original,'原合同约定',c.before.join('、')),button(c.fields.revised,'补充协议约定',c.after.join('、')));root.append(names);
      if (c.approval_fields) {
        const dates=el('div','','approval-rows approval-times approval-name-pair');
        const last=c.seller_on>=c.buyer_on?'seller_date':'buyer_date';
        dates.append(button(c.fields[last],'最后所列盖章日',c.last_seal_on),button(c.approval_fields.date,'审批单日期',c.issued_on));root.append(dates);
        if (c.approval_fields.signed_by) root.append(button(c.approval_fields.signed_by,'审批单具名栏',c.listed.join('、')));
        const pending=c.missing_names.length?'，'+c.missing_names.join('、')+'签批待补':'';
        root.append(el('p',c.other_names?ApprovalNames.jointSummary(c):c.printed_difference?'审批单具名与按纸面日期对应的名单不同。':
          c.state==='same_day'?'盖章时刻待补，无法确定当天先后。':'实际签批权限待核'+pending+'。','approval-change-note'));
        if (c.refused || c.early_debit) root.append(el('p',[c.refused?'审批单列明不同意支付。':'',c.early_debit?'所记扣款早于审批签发。':''].join(''),'approval-change-note'));
      }
      root.append(el('p',c.signature_state==='typeset'?'补充协议为排印件，双方实际签署待核。':'请核验电子签署人的身份、权限及双方同意。','approval-change-note'));
    }
    const rest=entries.filter(e=>!used.has(e.row.id) && e.row.rects.length);
    if (rest.length) {
      const more=el('details'),grid=el('div','','approval-rows');
      more.append(el('summary','核对适用时点、签章及原文'));
      grid.append(...rest.map(({row:r})=>button(r.id,label(r),value(r))));more.append(grid);root.append(more);
    }
    return root;
  }
  return {bind,scopeEntries,panel,supportsScope};
})();
