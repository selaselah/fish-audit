// Both times belong to the same installment. Read each from its own issued instrument.
const ApprovalClock = (() => {
  const format='cited-inspection-payment-use-v4';
  const supports=value=>value===format || ApprovalNames.supports(value);
  const signed=['审批签发时间','签批完成时间','审批签发时刻'];
  const debits=['实际扣款时间','扣款成功时间','成功扣款时间','实际扣款时刻'];
  const events=['银行受理时间','受理时间','交易发起时间','回单打印时间','打印时间','记账时间','到账时间','回单生成时间','交易时间',
    '扣款时间','申请时间','预约扣款时间','入账时间'];
  const labels={debit_first:'先扣款，后签批',approval_first:'签批在先，权限待核',overlap:'时刻重叠，先后待核',
    other_event:'实际扣款时刻待补',zone:'两单时区待核',conflict:'时间栏有冲突',missing:'签批或扣款时刻待补'};
  const same=(a,b)=>Array.isArray(a) && Array.isArray(b) && a.length===b.length && a.every((v,i)=>v===b[i]);
  const archived=report=>/^[a-f0-9]{64}$/u.test(report.policy.code_sha256?.['approval_clock.py']);
  const column=r=>r.quote.split(/[:：]/u,1)[0].trim();
  const field=r=>debits.includes(column(r))?'debit_time':events.includes(column(r))?'bank_event':'rider';
  function clock(row) {
    const sep=row.quote.search(/[:：]/u);
    if (sep<0) return null;
    const value=row.quote.slice(sep+1).trim().replace(/[０-９：＋（）－]/gu,c=>String.fromCharCode(c.charCodeAt(0)-0xfee0)).replaceAll('　',' ');
    return SignerEvidence.printedClock(value);
  }
  function bankPage(report,page) {
    const {graph}=report, idx=graphIndex(graph), doc=idx.documents.get(page.doc);
    const place=graph.payment_window_sources?.pages?.find(p=>p.unit===page.unit && p.doc===page.doc && p.page===page.page);
    return doc && place?.document_kind==='bank_receipt' && place.native && Array.isArray(page.rows) &&
      (!page.complete || page.page===1 && page.unit===doc.id && doc.ext==='.pdf' && doc.pages===1 && place.text_only &&
        !graph.gaps.some(g=>g.doc===doc.id) && !graph.facts.some(f=>f.doc===doc.id && f.status==='disputed') &&
        page.rows.every(r=>r.field!=='rider' && r.rects?.length));
  }
  function inspectionNotes(report,item,all) {
    const c=item.retest_reference || item.payment_acceptance, {graph}=report;
    if (!supports(report.policy.inspection_use)) return !c.timing_notes?.length;
    const ledger=graph.inspection_use_sources;
    if (!archived(report) || ledger?.format!==report.policy.inspection_use) return false;
    const pages=(ledger.bank_clocks || []).filter(p=>p.unit===c.bank);
    const bank=all.filter(r=>r.unit===c.bank && r.role==='bank_receipt');
    const filed=graph.payment_acceptance_sources.rows.filter(r=>r.unit===c.bank && r.role==='bank_receipt');
    if (!same(bank.map(r=>r.id),filed.map(r=>r.id)) || !pages.every(p=>bankPage(report,p))) return false;
    const pairs=[], citations=[];
    for (const row of bank) {
      const event=pages.filter(p=>p.complete && p.doc===row.doc && p.page===row.page).flatMap(p=>p.rows)
        .find(r=>r.line===row.line && r.quote===row.quote && ['debit_time','bank_event'].includes(field(r)) && field(r)===r.field && clock(r));
      if (event && row.kind==='note' && !row.disputed && row.facts.every(id=>event.facts.includes(id))) {
        if (event.unit!==c.bank || !event.id.startsWith('payment-clock/') || !c.evidence.includes(row.id) ||
            !InspectionUse.original(event,report,item.evidence)) return false;
        pairs.push({note:row.id,event:event.id});
      } else citations.push(row.id);
    }
    const claimed=c.timing_notes || [];
    return same(citations,c.citations) && Array.isArray(claimed) && claimed.length===pairs.length &&
      pairs.every((p,i)=>p.note===claimed[i].note && p.event===claimed[i].event && c.evidence.includes(p.event));
  }
  function compare(signature,debit,date) {
    if ([signature,debit].some(t=>t?.day && t.day!==date)) return {state:'conflict'};
    if (!signature || !debit) return {state:'missing'};
    if (signature.zone!=='+08:00' || debit.zone!=='+08:00') return {state:'zone'};
    const issued=SignerEvidence.interval(signature.at), paid=SignerEvidence.interval(debit.at);
    const state=paid[1]<=issued[0]?'debit_first':issued[1]<=paid[0]?'approval_first':'overlap';
    return {state,signed_at:signature.at,debited_at:debit.at,zone:'+08:00'};
  }
  function bind(item,report,sheet,readRow) {
    const c=item.inspection_use, a=c.approval, actual=a.clock;
    if (!supports(c.format)) return !actual?[]:null;
    if (!archived(report) || !Array.isArray(report.graph.inspection_use_sources.bank_clocks)) return null;
    const ledger=report.graph.inspection_use_sources.bank_clocks.filter(p=>p.unit===a.bank);
    const links=report.graph.edges.filter(e=>e.type==='compares_debit_time' && e.evidence?.[1]===c.citation);
    const signedRow=sheet.find(e=>e.row.field==='signed_at')?.row;
    if (a.state!=='same_day' || !signedRow && !ledger.some(p=>p.rows.length)) return !actual && !links.length?[]:null;
    const entries=[];
    for (const p of ledger) {
      if (!bankPage(report,p)) return null;
      for (const row of p.rows) {
        const doc=readRow(row);
        if (!doc || row.unit!==a.bank || row.doc!==p.doc || row.page!==p.page || !row.id.startsWith('payment-clock/') ||
            row.field!==field(row) || ![row.id,row.doc+'/p'+row.page,...row.facts].every(id=>a.evidence.includes(id))) return null;
        entries.push({row,doc,scope:'bank_time'});
      }
    }
    const debits=entries.filter(e=>e.row.field==='debit_time'), debit=debits.length===1?debits[0].row:null;
    if (!actual || actual.signed!==(signedRow?.id || null) || actual.debit!==(debit?.id || null) || !same(actual.rows,entries.map(e=>e.row.id))) return null;
    let expected;
    if (ledger.length>1 || debits.length>1 || ledger.some(p=>!p.complete)) expected={state:'conflict'};
    else if (!debit && entries.length && entries.every(e=>e.row.field==='bank_event')) expected={state:'other_event'};
    else if (!signedRow || !debit) expected={state:'missing'};
    else expected=compare(clock(signedRow),clock(debit),a.paid_on);
    if (['state','signed_at','debited_at','zone'].some(k=>actual[k]!==expected[k])) return null;
    if (expected.signed_at) {
      if (links.length!==1 || links[0].from!==signedRow.id || links[0].to!==debit.id ||
          !same(links[0].evidence,[a.request,c.citation,signedRow.id,debit.id])) return null;
    } else if (links.length) return null;
    return entries;
  }
  return {supports,signed,labels,clock,compare,bankPage,inspectionNotes,bind};
})();
