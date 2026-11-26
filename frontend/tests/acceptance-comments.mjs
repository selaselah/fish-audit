import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {size,inspect} from './review-screen.mjs';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const all=s=>'[...document.querySelectorAll('+JSON.stringify(s)+')]';
const widths=[1440,1024,820,768,390,320];
const sha=b=>createHash('sha256').update(Buffer.from(b)).digest('hex');
export async function checkWordComments(ctx,id,revision) {
  const {root,evaluate,call,wait}=ctx, task=await (await fetch(root+'/api/cases/'+id)).json();
  const rev=revision || task.rev, report=(await (await fetch(root+'/api/cases/'+id+'/reports/'+rev)).json()).report;
  await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev='+rev+'&view=acceptance-comments'});
  await wait('state.bundle?.rev==='+rev,'requested revision');
  const ledger=report.graph.acceptance_word_reviews, card='#acceptance-comments';
  if (!ledger) {
    assert.equal(await evaluate('Boolean('+q(card)+')'),false);
    assert.equal(await evaluate('Boolean('+q('.word-request')+')'),false);
    const h02=report.findings.find(f=>f.rule==='H02'), ids=report.policy.rule_sources[h02.rule];
    await evaluate('revealPaperTarget('+q('[data-finding="'+h02.id+'"]')+')');
    const scope='[data-finding="'+h02.id+'"]';
    await evaluate(all(scope+' summary')+'.find(s=>s.textContent.includes("核对制度出处与适用范围")).click()');
    await wait(q(scope+' .catalog-sources select')+'?.options.length>0','archived sources');
    assert.deepEqual(await evaluate(all(scope+' .catalog-sources option')+'.map(o=>o.value)'),ids);
    const source=ids.at(-1), control=q(scope+' .catalog-sources select');
    await evaluate(control+'.value='+JSON.stringify(source)+';'+control+'.dispatchEvent(new Event("change"))');
    assert.equal(await evaluate(q(scope+' .catalog-version')+'.textContent'),'规则版本 '+report.policy.version);
    assert.equal(await evaluate(q(scope+' .catalog-official')+'.href'),report.policy.sources[source].url);
    console.log('PASS · historical Word review keeps its original evidence');
    return;
  }
  const h02=report.findings.find(f=>f.rule==='H02'), doc=ledger.documents[0], note=doc.notes[0];
  await wait(q(card)+'?.getClientRects().length','Word review panel');
  assert.equal(await evaluate(q(card)+'.dataset.state'),h02.acceptance_comments.status);
  const href=await evaluate(q(card+' .word-file')+'.href');
  assert.ok(href.endsWith('/'+doc.doc+'/original?rev='+rev));
  assert.equal(sha(await (await fetch(href)).arrayBuffer()),doc.original_sha256);
  if (!note) {
    assert.match(await evaluate(q(card+' .word-empty')+'.textContent'),/未检出标准审阅批注/);
    assert.equal(await evaluate('Boolean('+q(card+' mark')+')'),false);
    assert.equal(await evaluate('Boolean('+q(card+' .word-request')+')'),false);
    console.log('PASS · original without Word comments');
    return;
  }
  const facts=note.location.facts.map(id=>report.graph.facts.find(f=>f.id===id));
  const refs=report.findings.filter(f=>f.stage && f.evidence.includes(note.id));
  const tag=h02.status==='issue'?'measured':'limited';
  const phases=refs.filter(f=>f.rule==='H04').map(f=>f.id);
  assert.deepEqual(await evaluate(all('.word-phase-link')+'.map(n=>n.closest("[data-phase-finding]").dataset.phaseFinding)'),phases);
  assert.equal(await evaluate(q('.phase-choice[aria-selected=true]')+'.dataset.phaseChoice'),phases[0]);
  await evaluate(q('#phase-record-'+phases[0]+' .word-phase-link')+'.click()');
  assert.equal(await evaluate(q(card+'-tab-0')+'.getAttribute("aria-selected")'),'true');
  for (const width of widths) {
    await size(ctx,width);
    await evaluate(q(card+'-tab-0')+'.click()');
    assert.equal(await evaluate(q(card+' .word-quote mark')+'.textContent'),note.anchor.selected);
    assert.equal(await evaluate(q(card+' .word-quote')+'.textContent'),note.anchor.quote);
    assert.equal(await evaluate(q(card+' blockquote')+'.textContent'),note.text);
    await wait(q(card+' .word-mini img')+'?.naturalWidth>0','versioned Word page');
    await inspect(ctx,width,card,'word-'+tag+'-comparison');
    await evaluate(q(card+' .word-page-jump')+'.click()');
    await wait(q('#page-dialog')+'.open && '+q('#page-dialog .page-image')+'?.naturalWidth>0 && '+q('#page-dialog svg rect')+'!=null','bound original line');
    const rects=await evaluate(all('#page-dialog .source-plane svg rect')+'.map(r=>["x","y","width","height"].map(k=>Number(r.getAttribute(k))))');
    assert.deepEqual(rects,facts[0].source_line.rects.map(([l,t,r,b])=>[l*1000,t*1000,(r-l)*1000,(b-t)*1000]));
    await evaluate(q('#page-dialog [data-close]')+'.click()');
    await evaluate(q(card+'-tab-0')+'.focus()');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight'});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight'});
    assert.equal(await evaluate('document.activeElement.id'),'acceptance-comments-tab-1');
    assert.deepEqual(await evaluate(all(card+' .word-impact')+'.map(a=>a.dataset.findingId)'),refs.map(f=>f.id));
    await inspect(ctx,width,card,'word-'+tag+'-payments');
    await evaluate(q(card+' .word-impact')+'.click()');
    assert.ok(await evaluate(q('[data-finding="'+refs[0].id+'"] details')+'.open'));
    await evaluate(q(card+'-tab-0')+'.click()');
  }
  await evaluate(q(card+' .word-proof summary')+'.click()');
  assert.ok(await evaluate(q(card+' .word-proof dl')+'.innerText.includes('+JSON.stringify(doc.part_sha256)+')'));
  if (task.rev===rev && task.status==='ready') {
    await evaluate(q(card+' .word-request')+'.click()'); await wait(q('#review-dialog')+'.open','supplement draft');
    assert.equal(await evaluate(q('#review-decision')+'.value'),'return');
    assert.match(await evaluate(q('#review-note')+'.value'),/第 1 页第 9 行.*终验/);
    await evaluate(q('#review-dialog [data-close]')+'.click()');
  }
  for (const change of ["note.anchor.start=0","note.location.page_sha256='0'.repeat(64)",
    "g.edges=g.edges.filter(e=>e.type!=='word_review_anchor')","g.edges=g.edges.filter(e=>!(e.type==='supports_result' && e.from===note.id))"]) {
    assert.equal(await evaluate('(()=>{const r=structuredClone(state.bundle.report),g=r.graph,note=g.acceptance_word_reviews.documents[0].notes[0];'+change+';return AcceptanceComments.resolve(r)===null})()'),true);
  }
  assert.deepEqual((await (await fetch(root+'/api/cases/'+id)).json()).decisions,task.decisions);
  console.log('PASS · '+tag+' Word original, selection, phase links, supplementary draft and six viewports');
}
export async function checkPublicWordComments(ctx) {
  const {root,call,evaluate,wait}=ctx, card='#public-acceptance-comments';
  const data=await (await fetch(root+'/assets/acceptance-comment-sample.json')).json();
  const doc=data.document, note=doc.notes[0];
  for (const source of Object.values(data.sources)) {
    assert.equal(sha(await (await fetch(root+(source.pdf || source.original))).arrayBuffer()),source.source_sha256);
    assert.equal(sha(await (await fetch(root+source.image)).arrayBuffer()),source.page_sha256);
  }
  await call('Page.navigate',{url:root+'/?scene=word-comments#workflow'});
  await wait(q(card)+'?.getClientRects().length','public Word scene');
  assert.equal(await evaluate(q('#inspection-example')+'.value'),'comments');
  assert.equal(await evaluate(q('#inspection-version')+'.textContent'),'合成案例 · R7');
  assert.equal(await evaluate(q(card+' .word-quote mark')+'.textContent'),note.anchor.selected);
  const jump=q(card+' .word-page-jump');
  for (const width of widths) {
    await size(ctx,width); await evaluate(q(card+'-tab-0')+'.click()');
    assert.equal(await evaluate(q(card+' blockquote')+'.textContent'),note.text);
    await inspect(ctx,width,card,'word-home-comparison');
    await evaluate(jump+'.click()');
    const canvas=q('#sample-review canvas');
    await wait(q('#sample-review')+'.open && '+canvas+'.dataset.fact==='+JSON.stringify(note.ref),'public selected source');
    assert.equal(await evaluate(q('#sample-location')+'.textContent'),'第 1 页 · 第 9 行');
    await evaluate(q('#sample-review form button')+'.click()');
    assert.equal(await evaluate('document.activeElement==='+jump),true);
    await evaluate(q(card+'-tab-1')+'.click()');
    assert.deepEqual(await evaluate(all(card+' .word-impact')+'.map(el=>el.dataset.findingId)'),note.related.map(f=>f.id));
    await inspect(ctx,width,card,'word-home-payments');
    for (const f of note.related) {
      await evaluate(q(card+' [data-finding-id="'+f.id+'"]')+'.click()');
      await wait(q('#sample-review')+'.open && '+canvas+'.dataset.fact==='+JSON.stringify(f.ref),'public clause or bank original');
      assert.equal(await evaluate(q('#sample-review-title')+'.textContent'),data.sources[f.doc].title);
      await evaluate(q('#sample-review form button')+'.click()');
    }
  }
  await evaluate(q('#inspection-example')+'.value="supplier";'+q('#inspection-example')+'.dispatchEvent(new Event("change"))');
  assert.equal(await evaluate('new URL(location.href).searchParams.get("scene")'),'suppliers');
  await evaluate(q('#inspection-example')+'.value="comments";'+q('#inspection-example')+'.dispatchEvent(new Event("change"))');
  assert.equal(await evaluate('new URL(location.href).searchParams.get("scene")'),'word-comments');
  console.log('PASS · watermarked public Word original, contract, transfer and six viewports');
}
