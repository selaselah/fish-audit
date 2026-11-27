import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

export async function checkApprovalChange(ctx,task,report,rev,item) {
  const {root,call,evaluate,wait}=ctx,c=item.approval_change,id=item.id;
  const fixed=root+'/workpaper/'+task.id+'?rev='+rev,card='#approver-change-'+id;
  const q=s=>'document.querySelector('+JSON.stringify(s)+')', click=s=>evaluate(q(s)+'.click()');
  const visible=s=>q(s)+'?.getClientRects().length',go=url=>call('Page.navigate',{url});
  const pointer=browserInput(ctx),tap=s=>pointer.tap(q(s));
  const printed=report.graph.inspection_use_sources, all=[...printed.rows,...['approver_terms','approver_changes','approvals','bank_clocks'].flatMap(k=>printed[k].flatMap(p=>p.rows))];
  const row=id=>all.find(r=>r.id===id),button=id=>card+'-'+id.replaceAll('/','-');
  const changed=c.fields.revised,last=c.fields[c.seller_on>=c.buyer_on?'seller_date':'buyer_date'],approved=c.approval_fields.date;
  async function located(ref) {
    const r=row(ref),at='#page-content .evidence-row.located';
    await wait(q('#page-dialog')+'?.open && '+q(at)+'?.dataset.sourceRef==='+JSON.stringify(ref)+' && '+q('#page-content img')+'?.naturalWidth>0','issued original '+ref);
    assert.equal(await evaluate(q(at+' blockquote')+'.textContent'),r.quote);
    assert.equal(await evaluate(q('#reader-citation-picker')+'.value'),ref);
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    assert.equal(await evaluate('document.querySelectorAll("#page-content .source-plane svg rect").length'),r.rects.length);
  }
  const payment=fixed+'&view=payment-checks&stage='+id;
  await go(fixed);const finding='[data-finding="'+id+'"]';await wait(visible(finding+' summary'),'finding');await click(finding+' summary');
  const jump=finding+' a[href*="view=payment-checks"][href*="stage='+id+'"]';await wait(visible(jump),'versioned approval change link');await click(jump);
  await wait(visible(card),'named change of installment approver');
  assert.equal(await evaluate(q(card)+'.dataset.state'),c.state);
  if (['cited-inspection-payment-use-v8','cited-inspection-payment-use-v9'].includes(report.policy.inspection_use)) {
    const signing='#performance-index .addendum-jump[data-proof="'+c.execution+'"]';
    await wait(visible(signing),'physical signing evidence for this change');
    for (const finding of report.findings.filter(f=>f.approval_change_scope)) {
      const scope=finding.approval_change_scope;
      const related=await evaluate('(()=>{const p=state.bundle.report,f=p.findings.find(v=>v.id==='+JSON.stringify(finding.id)+');'+
        'return ApprovalChange.scopeEntries(f,p).map(x=>x.row.id)})()');
      assert.ok([scope.scope_ref,c.original,changed,last].every(ref=>related.includes(ref)));
      assert.deepEqual(await evaluate('(()=>{const p=structuredClone(state.bundle.report),f=p.findings.find(v=>v.id==='+JSON.stringify(finding.id)+');'+
        'f.approval_change_scope.scope_ref='+JSON.stringify(c.fields.revised)+';return ApprovalChange.scopeEntries(f,p)})()'),[]);
    }
    if (item.retest_reference?.state==='final') {
      assert.equal(await evaluate('Boolean(RetestReference.bind(state.bundle.report.findings.find(f=>f.id==='+JSON.stringify(id)+'),state.bundle.report))'),true);
    }
  }
  for (const ref of [c.original,changed,last,approved,c.approval_fields.signed_by]) {
    await click(button(ref));await located(ref);await evaluate(q('#page-dialog')+'.close()');
  }
  const invalid=await evaluate('["source","rect","method","names","signed","last","days","status","link","party","dated","missing","signature","unsigned"].map(mode=>{'+
    'const p=structuredClone(state.bundle.report),f=p.findings.find(v=>v.id==='+JSON.stringify(id)+'),c=f.approval_change,'+
    'r=p.graph.inspection_use_sources.approver_changes[0].rows.find(v=>v.id===c.fields.revised);'+
    'if(mode==="source")r.quote=r.quote.replace("第二期","第三期");if(mode==="rect")r.rects=[];if(mode==="method")delete p.policy.code_sha256["approval_changes.py"];'+
    'if(mode==="names")c.after=["周茵"];if(mode==="signed")c.listed=["周茵"];if(mode==="last")c.last_seal_on="2026-09-07";if(mode==="days")c.days_from_seals+=1;'+
    'if(mode==="status")c.status=c.status==="risk"?"missing":"risk";if(mode==="party")c.contract_fields.buyer=c.contract_fields.seller;'+
    'if(mode==="link")p.graph.edges=p.graph.edges.filter(e=>e.type!=="dates_approval_change");if(mode==="dated")c.issued_on="2026-09-06";'+
    'if(mode==="signature"){c.signature_state="current";p.graph.addendum_pdf_sources.records[0].state="current";}'+
    'if(mode==="unsigned")p.graph.edges=p.graph.edges.filter(e=>e.type!=="addendum_pdf_source");'+
    'if(mode==="missing")c.missing_names=["测试姓名"];return ApprovalChange.bind(f,p)===null;})');
  assert.deepEqual(invalid,Array(14).fill(true));
  if (c.other_names) {
    assert.ok(await evaluate(q(card)+'.innerText.includes('+JSON.stringify('审批单未列'+c.missing_names[0]+'，另列'+c.other_names[0]+'。')+')'));
    const invalid=await evaluate('["name","clause","sheet","proof","omitted"].map(mode=>{const p=structuredClone(state.bundle.report),'+
      'f=p.findings.find(v=>v.id==='+JSON.stringify(id)+'),c=f.approval_change,e=p.graph.edges.find(e=>e.type==="compares_approval_names");'+
      'if(mode==="name")c.other_names=c.missing_names;if(mode==="clause")e.from=c.fields.scope;'+
      'if(mode==="sheet")e.to=c.approval_fields.authority;if(mode==="proof")e.evidence=e.evidence.slice(2);'+
      'if(mode==="omitted")p.graph.edges.splice(p.graph.edges.indexOf(e),1);return ApprovalChange.bind(f,p)===null;})');
    assert.deepEqual(invalid,Array(5).fill(true));
  }
  for (const width of [320,390,768,820,1024,1440]) {
    await size(ctx,width);
    assert.ok(await evaluate('(()=>{const r='+q(button(changed))+'.getBoundingClientRect();return r.width>=44&&r.height>=44&&r.left>=0&&r.right<=innerWidth+1})()'));
    await inspect(ctx,width,card,'approval-change-'+c.state);
  }
  if (process.env.AUDIT_ISOLATED_USE_ORIGIN) {
    assert.equal(root,process.env.AUDIT_ISOLATED_USE_ORIGIN);assert.ok(!['8000','8010'].includes(new URL(root).port));
    const notes=async()=>{const r=await fetch(root+'/api/walkthrough');assert.equal(r.status,200);return (await r.json()).notes;};
    assert.deepEqual(await notes(),[]);
    const text='想在这条变更约定旁直接看到审批单当时列的是谁。',lineText='希望在这个签章日期旁标出与审批日期相差几天。';
    const fill=value=>evaluate(q('#walk-text')+'.value='+JSON.stringify(value)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
    await size(ctx,1440);await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-dock')+'.disabled','desk recorder');
    await click('#walk-dock');await wait(q('#performance-index #walk-rail')+'?.matches(":popover-open")','record alongside the workpaper');
    await click('#walk-pick');await pointer.click(q(button(changed)));await wait(q(button(changed))+'.classList.contains("walk-selected")','amended clause');
    await fill(text);await pointer.click(q(button(last)));await located(last);
    await wait(q('#page-dialog #walk-rail')+'?.matches(":popover-open")','write alongside the supplement');
    assert.equal(await evaluate(q('#walk-text')+'.value'),text);
    await inspect(ctx,1440,'#walk-rail','approval-change-walkthrough');
    await click('#walk-save');await wait(q('#walk-status')+'.textContent.includes("已保存")','first note');
    await size(ctx,390);await wait(q('#walk-dialog')+'?.matches(":modal")','mobile recorder on the same original');
    await fill(lineText);await tap('#walk-save');await wait('!'+q('#walk-dialog')+'.open','file original row note');
    const saved=await notes(),field=saved.find(n=>n.text===text).context,page=saved.find(n=>n.text===lineText).context;
    assert.equal(field.anchor,button(changed).slice(1));assert.deepEqual(field.params,{view:'payment-checks',stage:id});
    assert.deepEqual([page.raw_ref,page.line,page.doc,page.rev],[last,row(last).line,row(last).doc,rev]);
    async function book() {
      await go(root+'/app#desk');await wait(visible('body > #walk-launch')+' && '+visible('#desk'),'workbench');await click('#walk-launch');
      await wait(q('#walk-dialog')+'?.open && !'+q('#walk-saved')+'.disabled','notes');await click('#walk-saved');await wait(visible('#walk-history li a'),'history');
    }
    await book();await evaluate('Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:async t=>{window.copied=t}});true');
    await tap('#walk-copy');await wait('window.copied?.includes('+JSON.stringify(lineText)+')','copy to Codex');assert.ok((await evaluate('window.copied')).includes(text));
    await click('#walk-history a[href*="walkat=approver-change-"]');await wait(q(button(changed))+'?.classList.contains("walk-mark")','reopen the same issued clause');
    await book();await click('#walk-history a[href*="walkraw="]');await located(last);
    let absent=rev-1;
    for (;absent>0;absent--) {
      const prior=await fetch(root+'/api/cases/'+task.id+'/reports/'+absent);
      if (prior.status===404) continue;
      assert.equal(prior.status,200);
      if (!(await prior.json()).report.findings.some(f=>f.id===id && f.approval_change?.rows.includes(changed))) break;
    }
    // A case first issued with this feature can have the clause in every historical version.
    if (!absent) {
      absent=task.rev+1;
      assert.equal((await fetch(root+'/api/cases/'+task.id+'/reports/'+absent)).status,404);
    }
    for (const [context,status] of [[{...field,rev:absent},404],[{...field,anchor:card.slice(1)+'-approval-change-'+row(changed).doc+'-p1-l1'},404],
            [{...field,params:{view:'payment-checks',stage:'H05-999'}},400],[{...page,rev:absent},404],[{...page,line:1},400]]) {
      const r=await fetch(root+'/api/walkthrough',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:'7'.repeat(32),text,context})});assert.equal(r.status,status);
    }
    const after=await (await fetch(root+'/api/cases/'+task.id)).json();
    assert.deepEqual([after.rev,after.status,after.decisions,after.referrals],[task.rev,task.status,task.decisions,task.referrals]);
  }
  const condition=report.findings.find(f=>f.rule==='H04' && f.approval_change);
  await go(fixed+'&view=payment-checks&stage='+condition.id);
  await wait(visible('#approver-change-'+condition.id),'installment without a selected payment');assert.equal(await evaluate(q('#approver-change-'+condition.id)+'.dataset.state'),'terms');
  await go(fixed+'&finding='+id);await wait(q('#trace-select')+'?.value==='+JSON.stringify(id),'evidence graph');
  if (await evaluate(visible('.trace-modes [data-mode="details"]'))) await click('.trace-modes [data-mode="details"]');
  const trace='#trace-details [data-use-ref="'+changed+'"]';await wait(visible(trace),'change in the finding trace');await click(trace);await located(changed);
  for (const item of report.findings.filter(f=>f.approval_change_scope)) {
    await go(fixed+'&finding='+item.id);await wait(q('#trace-select')+'?.value==='+JSON.stringify(item.id),'scope of change in '+item.rule);
    if (await evaluate(visible('.trace-modes [data-mode="details"]'))) await click('.trace-modes [data-mode="details"]');
    const ref=item.approval_change_scope.scope_ref,btn='#trace-details [data-use-ref="'+ref+'"]';
    await wait(visible(btn),'filed change scope on this finding');await click(btn);await located(ref);
  }
  console.log('PASS · R'+rev+' · '+c.state+' · contract, change, seals and approval on their filed rows · six widths');
}
