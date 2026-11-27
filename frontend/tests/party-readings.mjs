import assert from 'node:assert/strict';
import {setTimeout as delay} from 'node:timers/promises';
import {browserInput,inspect,size} from './review-screen.mjs';

export async function checkPartyReadings(ctx,cid) {
  const {root,call,evaluate,wait}=ctx, api='/api/cases/'+cid;
  const json=async path=>{const res=await fetch(root+path);assert.equal(res.status,200);return res.json();};
  const task=await json(api);assert.match(task.title,/^合成演练 · /u);
  const {report,rev}=await json(api+'/reports/'+(process.env.AUDIT_PARTY_REV || task.rev));
  const [r]=report.graph.reviewed_party_lines.rows;
  const f=report.findings.find(v=>v.rule==='H05' && v.party_readings?.includes(r.id));assert.ok(f);
  const q=s=>'document.querySelector('+JSON.stringify(s)+')', visible=s=>q(s)+'?.getClientRects().length';
  const click=s=>evaluate(q(s)+'.click()'), go=url=>call('Page.navigate',{url});
  const path=version=>root+'/workpaper/'+cid+'?rev='+version;
  const card='#party-reading-'+r.model_ref.replaceAll('/','-');
  const compare=card+' .party-reading-actions button:first-child', correct=card+' .party-reading-actions .primary';
  async function opened(version,state) {
    await wait(q('#page-dialog')+'?.open && '+visible(card)+' && '+q(card)+'.dataset.state==='+JSON.stringify(state)+
      ' && '+q(card)+'.dataset.rev==='+JSON.stringify(String(version))+' && '+q('#page-content img')+'?.naturalWidth>0','two filed observations on their original page');
    assert.deepEqual(await evaluate('Array.from('+q(card)+'.querySelectorAll("dd"),n=>n.textContent)'),[r.model_quote,r.quote]);
    assert.equal(await evaluate(q('#page-content .located')+'.dataset.fact'),r.model_ref);
  }
  await go(path(rev));
  const disclosure='[data-finding="'+f.id+'"] .finding-disclosure > summary';
  await wait(visible(disclosure),'ordinary payment finding');await click(disclosure);
  const ordinary='[data-finding="'+f.id+'"] .party-reading-jump';
  await wait(visible(ordinary),'party-line source on the payment finding');await click(ordinary);await opened(rev,r.state);
  await go(path(rev)+'&view=payment-checks&stage='+f.id);
  const jump='#performance-index[open] .party-reading-jump';
  await wait(visible(jump),'payment index cites the same source');await click(jump);await opened(rev,r.state);
  await click(compare);
  assert.equal(await evaluate('document.querySelectorAll("#page-content .source-plane svg rect").length'),r.rects.length);
  await click(card+' .party-reading-actions button:nth-child(2)');
  await wait(q('#page-content .located')+'?.dataset.fact==='+JSON.stringify(r.added_ref),'supplement observation');
  const record='#page-content .located .field-source-check';await click(record+' summary');
  assert.ok((await evaluate(q(record)+'.textContent')).includes(r.original_sha256));
  await evaluate('[...document.querySelectorAll("#page-content .located button")].find(b=>b.textContent==="对照模型初读").click()');
  await opened(rev,r.state);await click(compare);
  const checks=await evaluate('["call","reread","vote","proof","frame","role","owner","status","edge","extra","support","result","method","version"].map(mode=>{'+
    'const p=structuredClone(state.bundle.report),g=p.graph,r=g.reviewed_party_lines.rows[0],f=p.findings.find(f=>f.rule==="H05"),m=g.facts.find(v=>v.id===r.model_ref),h=g.facts.find(v=>v.id===r.added_ref);'+
    'if(mode==="call")p.calls.pages.find(c=>c.doc===r.doc).output.facts[Number(m.id.split("/f")[1])-1].quote="损坏";'+
    'if(mode==="reread")p.calls.pages.find(c=>c.doc===r.doc).check.input.find(v=>v.index===m.id.split("/f")[1]).quote="另一行";'+
    'if(mode==="vote")p.calls.pages.find(c=>c.doc===r.doc).check.output.checks=[];'+
    'if(mode==="proof")h.amendment.source_check.report_hash="0".repeat(64);if(mode==="frame")r.rects=[[.1,.2,.4,.3]];'+
    'if(mode==="role")r.field="buyer";if(mode==="owner")g.edges=g.edges.filter(e=>!(e.type===r.field && e.evidence.includes(h.id)));'+
    'if(mode==="status")r.state=r.state==="pending"?"same_line":"pending";if(mode==="edge")g.edges=g.edges.filter(e=>e.type!=="locates_party_reading");'+
    'if(mode==="extra")g.edges.push({from:m.id,to:h.id,type:r.state==="pending"?"shares_party_line":"compares_party_readings",evidence:[m.id,r.id,h.id]});'+
    'if(mode==="support")g.edges=g.edges.filter(e=>!(e.from===r.id && e.to==="finding/"+f.id));if(mode==="result")f.status="ok";'+
    'if(mode==="method")delete p.policy.code_sha256["party_readings.py"];if(mode==="version")p.policy.version="2026.11.27.21";'+
    'return PartyReadings.bind(p,r.id,f)===null})');
  assert.deepEqual(checks,Array(14).fill(true));
  for (const width of [320,390,768,820,1024,1440]) {
    await size(ctx,width);
    await evaluate(q(compare)+'.scrollIntoView({block:"center",behavior:"instant"})');
    assert.ok(await evaluate('(()=>{const b='+q(compare)+'.getBoundingClientRect();return b.width>=44 && b.height>=44 && b.left>=-1 && b.right<=innerWidth+1})()'),'reachable line on '+width);
    await inspect(ctx,width,card,'party-reading-'+r.state);
  }
  if (!process.env.AUDIT_ISOLATED_PARTY_ORIGIN) {
    assert.equal(await evaluate('Boolean('+q(correct)+')'),r.state==='pending' && rev===task.rev && task.status==='ready');
    console.log('PASS · archived '+r.state+' party line on R'+rev);return;
  }
  assert.equal(root,process.env.AUDIT_ISOLATED_PARTY_ORIGIN);assert.ok(!['8000','8010'].includes(new URL(root).port));
  assert.deepEqual((await json('/api/walkthrough')).notes,[]);assert.equal(r.state,'pending');assert.equal(rev,task.rev);
  const text='建议突出栏名里漏抄的“应”字，方便核对两条读数。';
  await size(ctx,390);await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','site recorder');
  await evaluate(q('#walk-text')+'.value='+JSON.stringify(text)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
  await click('#walk-pick');await browserInput(ctx).tap(q(compare));
  await wait(q('#walk-dialog')+'?.open && '+q(compare)+'.classList.contains("walk-selected")','pin the reading control');
  await inspect(ctx,390,'#walk-dialog','party-reading-walkthrough');
  await size(ctx,1440);await click('#walk-dock');
  await wait(q('#page-dialog #walk-rail')+'?.matches(":popover-open") && '+q('#walk-text')+'.value==='+JSON.stringify(text),'keep the draft beside the original');
  await inspect(ctx,1440,'#walk-rail','party-reading-walkthrough');
  await click('#walk-save');await wait(q('#walk-text')+'.value===""','save docked feedback');
  await click('#walk-close');await size(ctx,390);
  const [note]=(await json('/api/walkthrough')).notes, c=note.context;
  assert.deepEqual([note.text,c.case_id,c.rev,c.anchor,c.doc,c.page,c.line,c.params,c.dialog],[text,cid,rev,card.slice(1),r.doc,1,r.line,{fact:r.model_ref},'page-dialog']);
  for (const [changes,status] of [[{rev:rev-1},404],[{line:r.line+1},404],[{page:2},400],[{params:{fact:r.added_ref}},400]]) {
    const res=await fetch(root+'/api/walkthrough',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:'3'.repeat(32),text,context:{...c,...changes}})});assert.equal(res.status,status);
  }
  async function returnToPin() {
    await go(root+'/app#desk');await wait(visible('body > #walk-launch')+' && '+visible('#desk'),'desk');
    await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-saved')+'.disabled','saved walkthrough');
    await click('#walk-saved');const link='#walk-history a[href*="walkat='+card.slice(1)+'"]';
    await wait(visible(link),'link to source at saved revision');
    await evaluate('Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:async t=>{window.copiedNotes=t}});true');
    await browserInput(ctx).tap(q('#walk-copy'));await wait('window.copiedNotes?.includes('+JSON.stringify(c.anchor)+')','copy link to Codex');
    const copied=await evaluate('window.copiedNotes');assert.ok(copied.includes(text) && copied.includes('rev='+rev));
    await click(link);await opened(rev,'pending');await wait(q(card)+'.classList.contains("walk-mark")','return to the selected reading');
  }
  await returnToPin();await click(correct);await wait(q('#amend-dialog')+'?.open && !'+q('#amend-submit')+'.disabled','original page ready for correction');
  assert.deepEqual(await evaluate('["field","quote","value","reviewer","note"].map(n=>document.getElementById("amend-"+n).value)'),
    [r.field,r.quote,r.value,'','']);
  assert.equal(await evaluate('document.querySelectorAll("#amend-marks rect").length'),r.rects.length);
  assert.ok(await evaluate(q('#amend-context')+'.textContent.includes('+JSON.stringify('第 '+r.line+' 行')+')'));
  assert.equal(await evaluate(q('#amend-form')+'.checkValidity()'),false);
  await evaluate(q('#amend-reviewer')+'.value="供应方水印核字";'+q('#amend-note')+'.value="核对本页水印母本，栏名按第 '+r.line+' 行逐字更正。";');
  await click('#amend-submit');await wait('!'+q('#amend-dialog')+'.open','submit to recompute the workpaper');
  let detail;
  for (let i=0;i<150;i++) {
    detail=await json(api);assert.notEqual(detail.status,'failed',detail.error);
    if (detail.rev===rev+1 && detail.status==='ready') break;
    await delay(1000);
  }
  assert.equal(detail.rev,rev+1);assert.equal(detail.status,'ready');assert.deepEqual(detail.decisions,[]);
  const next=(await json(api+'/reports/'+detail.rev)).report, payment=next.findings.find(v=>v.id===f.id);
  assert.equal(payment.inspection_use.approval.state,'same_day');assert.equal(payment.status,'missing');
  await go(path(detail.rev)+'&fact='+encodeURIComponent(r.model_ref));await opened(detail.rev,'same_line');
  assert.equal(await evaluate(q(correct)),null);
  await returnToPin();assert.equal(await evaluate(q(correct)),null);
  const stale={rev,doc:r.doc,page:1,target:r.model_ref,field:r.field,quote:r.quote,value:r.value,region:'middle',reviewer:'水印核字',note:'复制旧版更正请求'};
  const conflict=await fetch(root+api+'/amend',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(stale)});
  assert.equal(conflict.status,409);assert.equal((await json('/api/walkthrough')).notes.length,1);
  console.log('PASS · original R'+rev+' walkthrough pin and copied link survive correction in R'+detail.rev+'; same-day payment still needs review');
}
