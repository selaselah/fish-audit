import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

export async function checkRetestReference(ctx,cid) {
  const {root,call,evaluate,wait}=ctx, base='/api/cases/'+cid;
  async function json(path) {
    const response=await fetch(root+path);assert.equal(response.status,200);return response.json();
  }
  const task=await json(base);assert.match(task.title,/^合成演练 · /u);
  const {report,rev}=await json(base+'/reports/'+(process.env.AUDIT_RETEST_REV || task.rev));
  const item=report.findings.find(f=>f.retest_reference) ||
    report.findings.find(f=>f.payment_acceptance) || report.findings.find(f=>f.rule==='H05' && f.stage);
  const {id,retest_reference:c}=item, fixed=root+'/workpaper/'+cid+'?rev='+rev, card='#retest-'+id;
  const q=s=>'document.querySelector('+JSON.stringify(s)+')', click=s=>evaluate(q(s)+'.click()');
  const visible=s=>q(s)+'?.getClientRects().length', go=url=>call('Page.navigate',{url});
  const facts=new Map(report.graph.facts.map(f=>[f.id,f]));
  async function original(key,whileOpen) {
    const fact=facts.get(c.fields[key]), button=card+'-'+key;
    assert.equal(await evaluate(q(button)+'.dataset.source'),fact.id);
    assert.match(await evaluate(q(button)+'.title'),new RegExp('第 '+fact.page+' 页 · 第 '+fact.source_line.number+' 行'));
    await click(button);
    await wait(q('#page-dialog')+'?.open && '+q('#page-content .located')+'?.dataset.fact==='+JSON.stringify(fact.id)+
      ' && '+q('#page-content img')+'?.naturalWidth>0','filed original for '+key);
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    assert.equal(await evaluate(q('#page-content .page-view')+'.dataset.doc'),fact.doc);
    if (whileOpen) await whileOpen(fact);
    await evaluate(q('#page-dialog')+'.close()');
  }
  if (!c) {
    await go(fixed+'&view=payment-checks&stage='+id);
    await wait(q('#performance-index')+'?.open && '+q('.scope-check-select')+'?.value==='+JSON.stringify(id),'historical finding');
    assert.equal(await evaluate(q('[data-retest-finding]')),null);
    console.log('PASS · R'+rev+' historical finding retains its issued evidence');return;
  }
  await go(fixed);
  const section='[data-finding="'+id+'"]', summary=section+' .finding-disclosure > summary';
  await wait(visible(summary),'receipt in the findings ledger');await click(summary);
  const jump=section+' a[href*="view=payment-checks"][href*="stage='+id+'"]';
  await wait(visible(jump),'receipt citation on the ordinary workpaper');await click(jump);
  await wait(q('#performance-index')+'?.open && '+visible(card),'matching receipt, revision and installment');
  assert.equal(await evaluate(q(card)+'.dataset.caseId'),cid);assert.equal(await evaluate(q(card)+'.dataset.rev'),String(rev));
  const cited=card+'-citation';
  if (c.number) {assert.equal(await evaluate(q(cited+' strong')+'.textContent'),c.number);await original('citation');}
  if (c.state==='unresolved') {
    for (const key of ['-terms','-final_acceptance_number','-original_acceptance_number','-order'])
      assert.equal(await evaluate(q(card+key)),null);
  } else {
    for (const role of ['original','final']) {
      const key=role+'_acceptance_number', button=card+'-'+key;
      assert.equal(await evaluate(q(button+' strong')+'.textContent'),c[role+'_number']);
      assert.equal(await evaluate(q(button)+'.classList.contains("retest-match")'),c.state===role);
      await original(key);
    }
    for (const key of ['paid_on','final_accepted_on']) await original(key);
    const order=await evaluate(q(card+'-order')+'?.textContent || null'), days=c.days_from_final;
    assert.equal(order,c.state==='final'?(days?'回单'+(days<0?'早 ':'晚 ')+Math.abs(days)+' 天':'同日，先后待核'):null);
    await click(card+'-terms');
    for (const key of ['clause','repair_repaired_on','final_defect_closure']) await original(key);
    await click(card+'-terms');
    const checks=await evaluate('(()=>{return ["number","line","method","date","unit","edge"].map(fault=>{'+
      'const p=structuredClone(state.bundle.report),i=p.findings.find(x=>x.id==='+JSON.stringify(id)+'),c=i.retest_reference;'+
      'if (fault==="number") c.number+="-1";if (fault==="date") c.final_on="2000-09-20";if (fault==="method") delete p.policy.code_sha256["retest_reference.py"];'+
      'if (fault==="unit") c.units.original=c.units.final;if (fault==="line") p.graph.retest_reference_sources.rows.find(r=>r.facts.includes(c.fields.final_acceptance_number)).line++;'+
      'if (fault==="edge"){const e=p.graph.edges.find(x=>x.type==="receipt_names_inspection");if(e)e.to=c.fields.paid_on;else p.graph.edges.push({type:"receipt_names_inspection",from:c.fields.citation,to:c.fields.final_acceptance_number,evidence:c.evidence})}'+
      'return RetestReference.bind(i,p)===null})})()');
    assert.deepEqual(checks,Array(6).fill(true));
  }
  for (const width of [320,390,768,820,1024,1440]) {
    await size(ctx,width);
    assert.ok(await evaluate('[...'+q(card)+'.querySelectorAll("button,summary")].filter(e=>e.getClientRects().length).every(e=>{const r=e.getBoundingClientRect();return r.width>=44 && r.height>=44 && r.left>=-1 && r.right<=innerWidth+1})'),'controls at '+width);
    await inspect(ctx,width,card,'retest-'+cid.slice(0,8)+'-R'+rev);
  }
  if (process.env.AUDIT_ISOLATED_RETEST_ORIGIN) {
    assert.equal(root,process.env.AUDIT_ISOLATED_RETEST_ORIGIN);assert.ok(!['8000','8010'].includes(new URL(root).port));
    assert.deepEqual((await json('/api/walkthrough')).notes,[]);
    await size(ctx,390);
    const folded='final_original_acceptance', target=card+'-'+folded;
    const general='希望在本期付款旁补充审批记录入口。', opinion='这张复验单引用哪张初验单，希望同时看到初验结论。';
    async function write(text,pick) {
      await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','start a note');
      await evaluate(q('#walk-text')+'.value='+JSON.stringify(text)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
      if (pick) {
        await click('#walk-pick');await browserInput(ctx).tap(q(pick));
        await wait(q('#walk-dialog')+'.open && '+q(pick)+'.classList.contains("walk-selected")','pin a source control');
        await inspect(ctx,390,'#walk-dialog','retest-feedback');
      }
      await click('#walk-save');await wait('!'+q('#walk-dialog')+'.open','save the note');
    }
    await write(general);await click(card+'-terms');await write(opinion,target);
    assert.ok(await evaluate('!Object.keys(sessionStorage).some(k=>k.startsWith("fish-walk-draft:"))'),'successful save clears the pinned draft and its submission id');
    const [note,ordinary]=(await json('/api/walkthrough')).notes;
    assert.equal(ordinary.text,general);assert.equal(ordinary.context.anchor,card.slice(1));assert.equal(note.text,opinion);
    for (const row of [note,ordinary]) {
      assert.equal(row.context.case_id,cid);assert.equal(row.context.rev,rev);
      assert.deepEqual(row.context.params,{view:'payment-checks',stage:id});
    }
    assert.equal(note.context.anchor,target.slice(1));
    assert.match(note.context.target,/复验所引初验单.*第 1 页.*行/u);
    for (const [context,status] of [[{...note.context,rev:rev-1},404],[{...note.context,params:{view:'payment-checks',stage:'H05-300'}},400],
      [{...note.context,anchor:card.slice(1)+'-order'},404]]) {
      const response=await fetch(root+'/api/walkthrough',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({id:'4'.repeat(32),text:opinion,context})});assert.equal(response.status,status);
    }
    await go(root+'/app#desk');await wait(visible('#desk')+' && '+visible('body > #walk-launch'),'desk');
    await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-saved')+'.disabled','open saved notes');
    await click('#walk-saved');await wait(visible('#walk-history li a'),'recorded locations');
    await evaluate('Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:async t=>{window.copiedWalkthrough=t}});true');
    await browserInput(ctx).tap(q('#walk-copy'));await wait('typeof window.copiedWalkthrough==="string"','copy to Codex');
    const dest=await evaluate(q('#walk-history li a')+'.href'), handoff=await evaluate('window.copiedWalkthrough');
    assert.ok([dest,opinion,general,note.context.target].every(x=>handoff.includes(x)));
    await click('#walk-history li a');
    await wait(visible(target)+' && '+q(target)+'.classList.contains("walk-mark")','return to the same control and expand its source disclosure');
    await original(folded,async fact=>{
      await write('复验报告里这一行原单号也应出现在审批旁。');
      const [pageNote]=(await json('/api/walkthrough')).notes;
      assert.equal(pageNote.context.target,report.graph.documents.find(d=>d.id===fact.doc).name);
      assert.deepEqual([pageNote.context.rev,pageNote.context.doc,pageNote.context.page,pageNote.context.line,pageNote.context.params.fact],
        [rev,fact.doc,fact.page,fact.source_line.number,fact.id]);
    });
    const end=await json(base);
    assert.deepEqual([end.status,end.rev,end.decisions,end.referrals],[task.status,task.rev,task.decisions,task.referrals]);
  }
  console.log('PASS · R'+rev+' · '+c.state+' · source lines, receipt and six viewport widths'+(process.env.AUDIT_ISOLATED_RETEST_ORIGIN?', saved control and copied handoff':''));
}
