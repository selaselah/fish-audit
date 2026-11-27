// Compare separately filed decisions without choosing a controlling instrument.
const ReleaseComparison = (() => {
  const bindings={same:'本期 · 原单一致',other_receipt:'所引验收单不同',other_phase:'指向其他期次',unresolved:'业务归属待核'};
  const stances={resume:'恢复支付',hold:'继续暂缓',unclear:'决定待核'};

  function render(phase,report,proofs) {
    const {graph,policy}=report, release=phase.payment_opinion.release, items=release.instruments;
    if (policy.release_comparison!=='payment-release-comparison-v1' || graph.release_comparison!==policy.release_comparison ||
        !/^[a-f0-9]{64}$/.test(policy.code_sha256?.['release_comparison.py']) || !Array.isArray(items) || items.length<2 ||
        proofs.length!==items.length || new Set(items.map(r=>r.unit)).size!==items.length) return null;
    const files=new Map(proofs.map(p=>[p.record.unit,p]));
    if (!items.every(item=>files.has(item.unit) && Object.hasOwn(bindings,item.binding) && Object.hasOwn(stances,item.stance))) return null;
    const sources=ReleaseEvidence.sources(graph,phase), conflict=release.state==='decision_conflict';
    const risk=conflict || release.signature_mismatch;
    const title=el('h4','放行单对照'), label=el('span',conflict?'书面意见相反':release.signature_mismatch?'签名校验不符':'有效版本待核','release-flag');
    title.tabIndex=-1;label.dataset.risk=String(risk);
    const root=box('release-comparison',box('release-head',title,label));
    root.dataset.releaseSet=phase.id;root.setAttribute('aria-label','多份付款放行单对照');

    function cited(f,prompt) {
      if (!f) return el('span','待定位','release-unknown');
      const b=action(f.value,()=>openPage(f.doc,f.page,f.id),'release-line-link');
      b.title=prompt+' · 第 '+f.page+' 页 · 第 '+f.source_line.number+' 行';
      b.setAttribute('aria-label',prompt+' '+f.value+'，查看原行');return b;
    }
    const original=ReleaseEvidence.fact(graph,phase,release.original_ref);
    if (original) root.append(box('release-compare-basis',el('span','暂缓所据验收单'),cited(original,'验收单编号')));
    for (const item of items) {
      const {doc,record,page}=files.get(item.unit);
      const rows=sources.filter(r=>r.unit===item.unit && r.doc===doc.id);
      const decision=ReleaseEvidence.one(rows,'decision');
      const row=box('release-instrument');row.dataset.instrument=item.unit;
      row.id='release-'+phase.id+'-'+item.unit.replaceAll('/','-');
      row.tabIndex=-1;row.setAttribute('role','group');row.setAttribute('aria-label',doc.name+' · '+bindings[item.binding]);
      const open=action(doc.name,()=>openPage(doc.id,page),'release-line-link release-instrument-name');
      open.id=row.id+'-file';open.setAttribute('aria-label','查看'+doc.name+'整页');
      row.append(box('release-instrument-head',open,el('span',ReleaseCard.states[record.state] || '签署版本待核','release-unknown')));
      const direction=el('strong',stances[item.stance]), binding=el('span',bindings[item.binding],'release-unknown');
      const fields=box('release-compare-fields');
      for (const [key,caption,ref] of [['receipt','所引验收单',item.receipt_ref],['date','单上签字日',item.date_ref]]) {
        const fact=ReleaseEvidence.fact(graph,phase,ref);
        const value=cited(fact && (fact.unit || fact.doc)===item.unit?fact:null,caption);
        value.id=row.id+'-'+key;fields.append(box('release-compare-field',el('small',caption),value));
      }
      row.append(box('release-instrument-state',direction,binding),fields);
      if (decision?.line && decision.native) {
        const f=AcceptanceOpinion.observation(decision,graph);
        const quote=action(decision.quote,()=>openPage(doc.id,decision.page,f?.id,f?null:decision.line),'release-decision-line');
        quote.append(el('small','第 '+decision.page+' 页 · 第 '+decision.line+' 行'));
        quote.id=row.id+'-decision';quote.setAttribute('aria-haspopup','dialog');
        quote.setAttribute('aria-describedby',open.id);row.append(quote);
      }
      root.append(row);
    }
    const banks=report.findings.filter(f=>f.rule==='H05' && f.stage?.clause_ref===phase.stage?.clause_ref &&
      f.payment_opinion?.release?.state===release.state && f.payment_opinion.release.signature_records?.length===items.length &&
      release.signature_records.every(id=>f.payment_opinion.release.signature_records.includes(id)));
    for (const bank of banks) {
      const paid=ReleaseEvidence.fact(graph,bank,bank.payment_opinion.release.paid_ref);
      if (paid) root.append(box('release-compare-basis',el('span','回单付款日'),cited(paid,'回单付款日')));
    }
    const params=new URLSearchParams({rev:state.bundle.rev,view:'payment-release',stage:phase.id});
    root.append(box('release-foot',el('span','须核实最终签发版本及签批顺序。','release-guidance'),
      Team.paperLink('固定链接',report.case_id,'release-download',params)));
    return root;
  }
  return {render};
})();
