import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {inspect,size} from './review-screen.mjs';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const all=s=>'[...document.querySelectorAll('+JSON.stringify(s)+')]';
const sha=raw=>createHash('sha256').update(Buffer.from(raw)).digest('hex');
const widths=[1440,1024,820,768,390,320];

export async function checkContractComments(ctx,id) {
  const {root,call,evaluate,wait}=ctx;
  const get=async path=>{const res=await fetch(root+path);assert.equal(res.status,200);return res.json();};
  const path='/api/cases/'+id;
  const task=id && await get(path);
  const revision=task && (Number(process.env.AUDIT_CONTRACT_COMMENT_REV) || task.rev);
  const report=task && (await get(path+'/reports/'+revision)).report;
  const sample=id?null:await get('/assets/contract-comment-sample.json');
  const card=id?'#contract-comments':'#public-contract-comments';
  const tabs=id?'.paper-contract-index .phase-choice':card+' .contract-stage';
  await call('Page.navigate',{url:root+(id?'/workpaper/'+id+'?rev='+revision+'&view=contract-comments':'/?scene=contract-comments#workflow')});
  if (report && !report.policy.contract_word_reviews) {
    await wait('state.bundle?.rev==='+revision,'archived workpaper');
    assert.equal(await evaluate('Boolean('+q(card)+')'),false);
    console.log('PASS · archived edition preserves its original scope');return;
  }
  const doc=sample?.document || report.graph.contract_word_reviews.documents[0];
  const note=doc.notes[0], expected=sample?.stages || report.findings.filter(f=>f.rule==='H04' && f.stage).map(f=>{
    const x=report.graph.facts.find(x=>x.id===f.stage.clause_ref);
    return {name:f.stage.name,share:f.stage.share,ref:x.id,line:x.source_line.number,quote:x.source_line.text,
      notes:note?.location?.facts.includes(x.id)?[note.id]:[]};
  });
  if (sample) {
    for (const src of Object.values(sample.sources)) {
      assert.equal(sha(await (await fetch(root+(src.original || src.pdf))).arrayBuffer()),src.source_sha256);
      assert.equal(sha(await (await fetch(root+src.image)).arrayBuffer()),src.page_sha256);
    }
  }
  await wait(q(tabs+'[aria-selected="true"]')+'!=null','stage-bound review');
  if (id) assert.equal(await evaluate(all(card+' [role=tablist].contract-index')+'.length'),0);
  const selected=Math.max(0,expected.findIndex(s=>s.notes.length));
  assert.equal(await evaluate(q(tabs+'[aria-selected="true"] strong')+'.textContent'),expected[selected].share+'%');
  assert.deepEqual(await evaluate(all(tabs)+'.map(b=>b.dataset.noted==="true")'),expected.map(s=>Boolean(s.notes.length)));
  const tag=id?(note?expected[selected].name:'clean'):'public';
  if (sample) assert.equal(await evaluate(q('#payment-version')+'.textContent'),'合成案例 · R'+sample.revision);
  for (const width of widths) {
    await size(ctx,width);
    await evaluate('document.activeElement?.blur();'+all(tabs)+'['+selected+'].click()');
    if (note) {
      if (id) assert.equal(await evaluate(q('.phase-summary li:not([hidden]) .phase-contract q')+'.textContent.includes("'+note.anchor.selected+'")'),true);
      assert.equal(await evaluate(q(card+' .word-quote mark')+'.textContent'),note.anchor.selected);
      assert.equal(await evaluate(q(card+' blockquote')+'.textContent'),note.text);
      await wait(q(card+' .word-mini img')+'?.naturalWidth>0','source thumbnail');
      await inspect(ctx,width,card,'contract-review-'+tag);
      await evaluate(q(card+' .word-page-jump')+'.click()');
      if (id) {
        await wait(q('#page-dialog')+'.open && '+q('#page-dialog .source-plane svg rect')+'!=null','archived original row');
        const refs=note.location.facts, fact=report.graph.facts.find(f=>refs.includes(f.id) && f.field==='payment_stage');
        const rects=await evaluate(all('#page-dialog .source-plane svg rect')+'.map(r=>["x","y","width","height"].map(k=>Number(r.getAttribute(k))))');
        assert.deepEqual(rects,fact.source_line.rects.map(([l,t,r,b])=>[l*1000,t*1000,(r-l)*1000,(b-t)*1000]));
        await evaluate(q('#page-dialog [data-close]')+'.click()');
      } else {
        await wait(q('#sample-review')+'.open && '+q('#sample-location')+'.textContent.includes("第 '+note.location.line+' 行")','public original row');
        await evaluate(q('#sample-review form button')+'.click()');
      }
      await evaluate(all(card+' .word-view-switch button')+'[1].click()');
      const related=sample?note.related:report.findings.filter(f=>f.stage && f.evidence.includes(note.id));
      assert.deepEqual(await evaluate(all(card+' .word-impact')+'.map(b=>b.dataset.findingId)'),related.map(f=>f.id));
      await inspect(ctx,width,card,'contract-payments-'+tag);
      await evaluate(q(card+' .word-impact:last-child')+'.click()');
      if (id) assert.equal(await evaluate(q('[data-finding="'+related.at(-1).id+'"] details')+'.open'),true);
      else {
        await wait(q('#sample-review')+'.open && '+q('#sample-review-title')+'.textContent==="银行付款回单"','related bank original');
        await evaluate(q('#sample-review form button')+'.click()');
      }
    }
    await evaluate(all(tabs)+'['+selected+'].focus()');
    for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key:'Home',code:'Home'});
    assert.equal(await evaluate('document.activeElement===('+all(tabs)+'[0])'),true);
    assert.equal(await evaluate(q(card+' .contract-printed-clause p')+'.textContent'),expected[0].quote);
    await evaluate(q(card+' .contract-printed-clause .word-page-jump')+'.click()');
    const dialog=id?'#page-dialog':'#sample-review';
    await wait(q(dialog)+'.open','first installment original');
    await evaluate(q(dialog+(id?' [data-close]':' form button'))+'.click()');
  }
  if (id && note) {
    await evaluate(all(tabs)+'['+selected+'].click()');
    const alternate='.paper-reader-tab:not(#reader-tab-contract-comments)';
    await evaluate(q(alternate)+'.click()');
    const backlink='.phase-summary li:not([hidden]) .word-phase-link[aria-controls="contract-comments"]';
    assert.ok(await evaluate(q(backlink)+'.getClientRects().length'));
    await evaluate(q(backlink)+'.click()');
    assert.equal(await evaluate(q('#reader-tab-contract-comments')+'.getAttribute("aria-selected")'),'true');
    assert.equal(await evaluate(q(backlink)+'.getClientRects().length'),0);
    assert.equal(await evaluate(q(card+' blockquote')+'.textContent'),note.text);
    if (task.rev===revision && task.status==='ready') {
      await evaluate(q(card+' .word-request')+'.click()');
      assert.ok((await evaluate(q('#review-note')+'.value')).includes('第 '+note.location.line+' 行所列付款前提'));
      await evaluate(q('#review-dialog [data-close]')+'.click()');
    }
    for (const change of ['n.location.printed+="0"','n.anchor.start+=1','g.edges=g.edges.filter(e=>e.type!=="contract_word_review_anchor")',
          'p.contract_comments.clauses[n.id]="other"']) {
      assert.equal(await evaluate('(()=>{const r=structuredClone(state.bundle.report),g=r.graph,n=g.contract_word_reviews.documents[0].notes[0],p=r.findings.find(f=>f.rule==="H03");'+change+';return AcceptanceComments.resolve(r,"contract")===null})()'),true);
    }
    assert.deepEqual((await get(path)).decisions,task.decisions);
  }
  if (sample) {
    await evaluate(q('#payment-example')+'.value="folios";'+q('#payment-example')+'.dispatchEvent(new Event("change"))');
    assert.equal(await evaluate('new URL(location.href).searchParams.get("scene")'),'folios');
    await evaluate(q('#payment-example')+'.value="comments";'+q('#payment-example')+'.dispatchEvent(new Event("change"))');
    assert.equal(await evaluate(q('#payment-version')+'.textContent'),'合成案例 · R'+sample.revision);
  }
  if (task && task.rev===revision) await checkPreview(ctx,task,report);
  console.log('PASS · '+tag+' installment scope, source rows and keyboard navigation at six widths');
}

async function checkPreview(ctx,task,report) {
  const {root,call,evaluate,wait}=ctx, dialog='#case-preview', tabs=dialog+' .preview-phase-tab';
  await call('Page.navigate',{url:root+'/app#desk'});
  await wait(q('#case-search')+'?.getClientRects().length && Desk.fingerprint','workspace queue');
  await evaluate(q('#case-search')+'.value='+JSON.stringify(task.title)+';'+q('#case-search')+'.dispatchEvent(new Event("input",{bubbles:true}))');
  const peek=q('[data-preview-case="'+task.id+'"]');
  await wait(peek+'!=null','filtered case');await evaluate(peek+'.click()');
  const panel=dialog+' .preview-contract';
  await wait(q(panel)+'?.getClientRects().length','contract preview');
  const phases=report.findings.filter(f=>f.rule==='H04' && f.stage);
  const link=(rule,stage)=>report.findings.find(f=>f.rule===rule && (!stage || f.stage?.clause_ref===stage.clause_ref));
  const url=f=>'/workpaper/'+task.id+'?rev='+task.rev+'&finding='+f.id;
  assert.deepEqual(await evaluate(all(panel+' .preview-check')+'.map(a=>a.getAttribute("href"))'),['H01','H02'].map(rule=>url(link(rule))));
  assert.equal(await evaluate(q(panel+' .preview-plan-jump')+'.getAttribute("href")'),url(link('H03')));
  assert.equal(await evaluate(q('#preview-body .preview-files')+'.closest("details").open'),false);
  for (const width of [1440,390,320]) {
    await size(ctx,width);
    const second=phases.findIndex(f=>f.stage.name==='第二期');
    await evaluate('document.activeElement?.blur();'+all(tabs)+'['+second+'].click()');
    const results=panel+' .preview-phase-detail .preview-finding';
    const ids=report.findings.filter(f=>f.stage?.clause_ref===phases[second].stage.clause_ref && ['H04','H05','H06'].includes(f.rule));
    assert.deepEqual(await evaluate(all(results)+'.map(a=>a.getAttribute("href"))'),ids.map(url));
    if (task.title.includes('第二期')) await inspect(ctx,width,dialog,'contract-preview-desk');
    await evaluate(all(tabs)+'['+second+'].focus()');
    for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key:'Home',code:'Home'});
    assert.equal(await evaluate(q(results)+'.dataset.findingId'),phases[0].id);
    assert.ok(await evaluate(q(panel+' .preview-no-receipt')+'.getClientRects().length'));
  }
  await evaluate(q('#preview-body .preview-files')+'.parentElement.querySelector("summary").click()');
  assert.equal(await evaluate(all('#preview-body .preview-files li')+'.length'),task.documents.length);
  const target=q(panel+' .preview-phase-detail .preview-finding');
  await evaluate(target+'.click()');
  await wait('state.bundle?.rev==='+task.rev+' && state.traceId==='+JSON.stringify(phases[0].id)+' && '+q('#trace-select')+'?.value==='+JSON.stringify(phases[0].id),'pinned preview evidence');
  assert.ok(await evaluate('!'+q(dialog)+'.open'));
}
