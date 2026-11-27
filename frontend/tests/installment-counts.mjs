import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

export async function checkInstallmentCount(ctx,cid) {
  const {root,call,evaluate,wait}=ctx, doc='/api/cases/'+cid;
  const json=async path=>{const res=await fetch(root+path);assert.equal(res.status,200);return res.json();};
  const task=await json(doc);assert.match(task.title,/^合成演练 · /u);
  const {report,rev}=await json(doc+'/reports/'+(process.env.AUDIT_USE_REV || task.rev));
  const fixed=root+'/workpaper/'+cid+'?rev='+rev,plan=report.findings.find(f=>f.rule==='H03');
  const stage=fixed+'&view=payment-checks&stage='+plan.id, selector='#installment-count-'+plan.id;
  const q=s=>'document.querySelector('+JSON.stringify(s)+')',visible=s=>q(s)+'?.getClientRects().length';
  const click=s=>evaluate(q(s)+'.click()'), go=url=>call('Page.navigate',{url}), pointer=browserInput(ctx);
  await go(stage);await wait(q('#performance-index')+'?.open && '+q('.scope-check-select')+'?.value==='+JSON.stringify(plan.id),'issued installment schedule');
  if (!plan.installment_count) {
    assert.equal(await evaluate(q(selector)),null);
    console.log('PASS · R'+rev+' keeps the original schedule without a derived count');return;
  }
  const [r]=report.graph.installment_count_sources.rows,ref=r.id;
  const raw='#page-content .evidence-row.located',dialog='#page-dialog';
  async function located() {
    await wait(q(dialog)+'?.open && '+q(raw)+'?.dataset.sourceRef==='+JSON.stringify(ref)+' && '+q('#page-content img')+'?.naturalWidth>0','contract header at the filed line');
    assert.equal(await evaluate(q(raw+' blockquote')+'.textContent'),r.quote);
    assert.ok((await evaluate(q(raw)+'.textContent')).includes('模型摘录（独立复读支持） · '+r.model_quote));
    assert.equal(await evaluate(q('#reader-citation-picker')+'.value'),ref);
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    assert.equal(await evaluate('document.querySelectorAll("#page-content .source-plane svg rect").length'),r.rects.length);
  }
  const finding=report.findings.find(f=>f.rule==='H05' && f.installment_count);
  await wait(visible(selector),'declared count source on the installment schedule');
  const modes=['count','vote','input','model','status','raw','rect','geometry','sha','edge','method','finding','no-input','no-output','no-ledger'];
  const invalid=await evaluate(JSON.stringify(modes)+'.map(mode=>{const p=structuredClone(state.bundle.report),r=p.graph.installment_count_sources.rows[0],'+
    'f=p.findings.find(f=>f.rule==="H03"),m=p.graph.facts.find(x=>x.id===r.model_ref),c=p.calls.pages.find(v=>v.doc===r.doc),i=r.model_ref.split("/f")[1];'+
    'if(mode==="count")r.count++;if(mode==="vote")c.check.output.checks.find(v=>v.index===i).support="conflict";'+
    'if(mode==="input")c.check.input.find(v=>v.index===i).value="四期";if(mode==="model")c.output.facts[Number(i)-1].quote=r.quote;'+
    'if(mode==="status")m.status="confirmed";if(mode==="raw")r.quote+="，另收款";if(mode==="rect")r.rects=[];'+
    'if(mode==="geometry")c.installment_count_rects[r.line]=[[.1,.2,.5,.3]];if(mode==="sha")r.original_sha256="1".repeat(64);'+
    'if(mode==="edge")p.graph.edges=p.graph.edges.filter(e=>e.type!=="locates_installment_count");'+
    'if(mode==="method")delete p.policy.code_sha256["installment_counts.py"];if(mode==="finding")f.evidence=f.evidence.filter(v=>v!==r.model_ref);'+
    'if(mode==="no-input")delete c.check.input;if(mode==="no-output")delete c.check.output;if(mode==="no-ledger")delete p.graph.installment_count_sources.rows;'+
    'return InstallmentCount.bind(p,r.id,f)===null})');
  assert.deepEqual(invalid,modes.map(()=>true));
  for (const width of [320,390,768,820,1024,1440]) {
    await size(ctx,width);
    assert.ok(await evaluate('(()=>{const r='+q(selector)+'.getBoundingClientRect();return r.height>=44 && r.left>=0 && r.right<=innerWidth+1})()'));
    await inspect(ctx,width,selector,'installment-count');
  }
  await click(selector);await located();await evaluate(q(dialog)+'.close()');
  await go(fixed+'&finding='+plan.id);await wait(q('#trace-select')+'?.value==='+JSON.stringify(plan.id),'H03 evidence graph');
  if (await evaluate(visible('.trace-modes [data-mode="details"]'))) await click('.trace-modes [data-mode="details"]');
  const trace='#trace-details [data-count-ref="'+ref+'"]';await wait(visible(trace),'physical header on H03 graph');await click(trace);await located();
  await go(fixed+'&view=payment-checks&stage='+finding.id);
  const paid='#installment-count-'+finding.id;await wait(visible(paid),'reference from the actual installment');
  await click(paid);await located();
  if (process.env.AUDIT_ISOLATED_USE_ORIGIN) {
    assert.equal(root,process.env.AUDIT_ISOLATED_USE_ORIGIN);assert.ok(!['8000','8010'].includes(new URL(root).port));
    assert.deepEqual((await json('/api/walkthrough')).notes,[]);
    const fieldText='分期总述与明细的合计希望能同时看到。',lineText='在本行保留模型摘录和合同原文。';
    const fill=v=>evaluate(q('#walk-text')+'.value='+JSON.stringify(v)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
    await go(stage);await wait(visible(selector),'open the plan to leave feedback');await click('#walk-launch');await wait(visible('#walk-dock'),'recorder');
    await click('#walk-dock');await wait(q('#performance-index #walk-rail')+'?.matches(":popover-open")','side-by-side recording');
    await click('#walk-pick');await pointer.click(q(selector));await wait(q(selector)+'.classList.contains("walk-selected")','select filed count');
    await fill(fieldText);await pointer.click(q(selector));await located();await wait(q('#page-dialog #walk-rail')+'?.matches(":popover-open")','follow into contract');
    assert.equal(await evaluate(q('#walk-text')+'.value'),fieldText);
    await inspect(ctx,1440,'#walk-rail','installment-count-walkthrough');
    await click('#walk-save');await wait(q('#walk-status')+'.textContent.includes("已保存")','save control note');
    await size(ctx,390);await wait(q('#walk-dialog')+'?.matches(":modal")','mobile recorder');await fill(lineText);
    await pointer.tap(q('#walk-save'));await wait('!'+q('#walk-dialog')+'.open','save original line note');
    const notes=(await json('/api/walkthrough')).notes,field=notes.find(n=>n.text===fieldText).context,page=notes.find(n=>n.text===lineText).context;
    assert.deepEqual([field.anchor,field.params,field.rev],[selector.slice(1),{view:'payment-checks',stage:plan.id},rev]);
    assert.deepEqual([page.doc,page.page,page.line,page.raw_ref,page.rev],[r.doc,1,r.line,ref,rev]);
    async function notebook() {
      await go(root+'/app#desk');await wait(visible('#desk')+' && '+visible('body > #walk-launch'),'workbench');
      await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-saved')+'.disabled','notebook');
      await click('#walk-saved');await wait(visible('#walk-history a'),'notes list');
    }
    await notebook();await click('#walk-history a[href*="walkat=installment-count-"]');await wait(q(selector)+'?.classList.contains("walk-mark")','original H03 control');
    await notebook();await click('#walk-history a[href*="walkraw="]');await located();
    let absent=rev-1;
    for (;absent>0;absent--) {
      const res=await fetch(root+doc+'/reports/'+absent);if(res.status===404) continue;
      assert.equal(res.status,200);if (!(await res.json()).report.policy.installment_count) break;
    }
    assert.ok(absent>0);
    for (const [context,status] of [[{...page,rev:absent},404],[{...field,rev:absent},404],[{...page,line:r.line+1},400],
        [{...field,anchor:'installment-count-H03-999'},400],[{...field,anchor:'installment-count-H03-999',params:{view:'payment-checks',stage:'H03-999'}},404]]) {
      const res=await fetch(root+'/api/walkthrough',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:'a'.repeat(32),text:fieldText,context})});
      assert.equal(res.status,status);
    }
    const after=await json(doc);assert.deepEqual([after.rev,after.status,after.decisions,after.referrals],[task.rev,task.status,task.decisions,task.referrals]);
  }
  console.log('PASS · R'+rev+' · filed model quote, count and original contract line on H03 and H05 · six widths');
}
