import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

export async function checkEvidenceCompare({root,call,evaluate,wait},caseId,requestedRev) {
  const base=root+'/api/cases/'+caseId;
  const task=await (await fetch(base)).json();
  assert.ok(task.title.startsWith('合成演练 · '));
  const rev=requestedRev || task.rev;
  const {report}=await (await fetch(base+'/reports/'+rev)).json();
  const h=report.findings.find(f=>f.rule==='H02');
  const witnesses=new Set(report.graph.edges.filter(e=>e.type==='supports_result' && e.to==='finding/'+h.id).map(e=>e.from));
  const facts=report.graph.facts.filter(f=>h.evidence.includes(f.id) && witnesses.has(f.id));
  const byId=new Map(facts.map(f=>[f.id,f]));
  const $=s=>'document.querySelector('+JSON.stringify(s)+')';
  const ids=()=>evaluate('[...document.querySelectorAll(".compare-leaf")].map(n=>n.dataset.fact)');
  const opens=()=>evaluate('[...document.querySelectorAll(".compare-original")].map(e=>e.getAttribute("aria-label"))');
  async function key(name,code) {
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:name,code:name,windowsVirtualKeyCode:code,...(name==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:name,code:name,windowsVirtualKeyCode:code});
  }
  async function search(value) {
    await evaluate('(()=>{const q=document.querySelector(".finder-search input");q.value='+JSON.stringify(value)+';q.dispatchEvent(new Event("input"))})()');
  }
  async function picker(side) {
    await evaluate('document.querySelectorAll(".compare-pick")['+side+'].focus()');
    await key('Enter',13);
    await wait('document.querySelector(".citation-finder").open && document.activeElement===document.querySelector(".finder-search input")','focused search field');
  }
  async function selectFact(side, id) {
    await picker(side);
    await search(id);
    const result=await evaluate('Array.from(document.querySelectorAll(".finder-choice"),b=>b.dataset.ref)');
    assert.ok(result.includes(id));
    await evaluate($('[data-ref="'+id+'"].finder-choice')+'.focus()');
    await key('Enter',13);
    await wait('!document.querySelector(".citation-finder").open','choice applied');
  }
  await call('Page.navigate',{url:root+'/workpaper/'+caseId+'?rev='+rev});
  await wait('!!document.querySelector(".compare-jump")','report shortcut for cited acceptance observations');
  await evaluate($('.compare-jump')+'.click()');
  await wait('document.querySelector("#trace-select")?.value==='+JSON.stringify(h.id)+' && !document.querySelector("#trace-compare").hidden','issued finding in comparison');
  assert.equal(await evaluate('document.activeElement.dataset.mode'),'compare');
  assert.equal(await evaluate($('#trace-details')+'.hidden'),true);
  const [,excluded]=await ids();
  await picker(0);
  assert.deepEqual(await evaluate('Array.from(document.querySelectorAll(".finder-choice"),b=>b.dataset.ref).sort()'),[...byId.keys()].filter(id=>id!==excluded).sort());
  await search('没有这个字段__');
  assert.ok(await evaluate('!!document.querySelector(".finder-empty") && !document.querySelector(".finder-choice")'));
  await search('');
  await key('ArrowDown',40); assert.ok(await evaluate('document.activeElement.matches(".finder-choice")'));
  await key('End',35); assert.ok(await evaluate('document.activeElement===document.querySelector(".finder-results").lastElementChild'));
  await key('Escape',27); assert.ok(await evaluate('document.activeElement===document.querySelector(".compare-pick")'));
  const pairs=await evaluate('[...document.querySelectorAll("[data-pair]")].map(b=>b.dataset.pair)');
  const defaultPair=await evaluate('document.querySelector("[data-pair][aria-pressed=true]")?.dataset.pair');
  const change=h.quality_change;
  if (change && !change.quantity) {
    const fields=await ids().then(a=>a.map(id=>byId.get(id)?.field));
    if (change.applied_criterion) assert.deepEqual(fields,[change.state==='applied'?'revised_criterion':'acceptance_criteria','measured_result']);
    if (change.state==='pending') {
      assert.ok(!pairs.includes('reading') && !pairs.includes('basis'));
      assert.equal(await evaluate($('.compare-version')+'.dataset.state'),'pending');
    }
  }
  for (const pair of pairs) {
    await evaluate($('[data-pair="'+pair+'"]')+'.click()');
    const [left,right]=await ids();
    assert.ok(left!==right && byId.has(left) && byId.has(right));
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".compare-quote blockquote")].map(q=>q.textContent)'),[byId.get(left).quote,byId.get(right).quote]);
    if (pair==='dates') {
      assert.equal(change[byId.get(left).field],change.effective_on);
      assert.equal(byId.get(right).field,'accepted_on');
    }
    if (pair.startsWith('batch-')) {
      const batch=h.batch_acceptance.batches.find(b=>b.index===Number(pair.slice(6)));
      assert.ok(batch.records.includes(byId.get(right).unit || byId.get(right).doc));
    }
  }
  if (defaultPair) await evaluate($('[data-pair="'+defaultPair+'"]')+'.click()');
  else { await selectFact(0,facts[0].id); await selectFact(1,facts[1].id); }
  await wait('document.querySelectorAll(".compare-scan canvas").length===2','two archived page images');
  const initial=await ids();
  for (const [i,id] of initial.entries()) {
    const fact=byId.get(id);
    assert.ok((await opens())[i].includes(fact.label));
  }
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    const boxes=await evaluate('[...document.querySelectorAll(".compare-leaf,.compare-original,.compare-scan canvas")].map(n=>n.getBoundingClientRect().toJSON())');
    assert.ok(boxes.every(r=>r.width>0 && r.left>=0 && r.right<=width+1),'comparison fits '+width);
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'page width '+width);
    const leaves=await evaluate('[...document.querySelectorAll(".compare-leaf")].map(n=>n.getBoundingClientRect().toJSON())');
    if (width>700) assert.equal(leaves[0].top,leaves[1].top);
    else assert.ok(leaves[1].top>=leaves[0].bottom);
    if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
      const clip=await evaluate('(()=>{const r=document.querySelector(".trace-panel").getBoundingClientRect();return {x:r.left+scrollX,y:r.top+scrollY,width:r.width,height:r.height,scale:1}})()');
      const capture=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'compare-'+caseId+'-'+width+'.png'), Buffer.from(capture.data,'base64'));
    }
  }
  await evaluate('document.querySelectorAll(".compare-original")[1].focus()');
  await key('Enter',13);
  await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(initial[1]),'original focused on selected observation');
  await wait('document.querySelector("#page-dialog img")?.naturalWidth>0','full original decoded');
  await key('Escape',27);
  await wait('!document.querySelector("#page-dialog").open','original dismissed');
  assert.ok(await evaluate('document.activeElement===document.querySelectorAll(".compare-original")[1]'));
  const alternative=facts.find(f=>!initial.includes(f.id) && !f.source_line?.rects?.length) || facts.find(f=>!initial.includes(f.id));
  if (alternative) {
    await selectFact(0,alternative.id);
    await wait('!!document.querySelector(".compare-leaf .compare-scan canvas")','new first original loaded');
    assert.deepEqual(await ids(),[alternative.id,initial[1]]);
    assert.equal(await evaluate($('.compare-scan')+'.dataset.located'),String(Boolean(alternative.source_line?.rects?.length)));
    assert.equal(await evaluate($('.compare-quote blockquote')+'.textContent'),alternative.quote);
  }
  await evaluate($('[data-mode="details"]')+'.click()');
  assert.ok(await evaluate('document.querySelector("#trace-compare").hidden && !document.querySelector("#trace-details").hidden'));
  assert.equal(await evaluate($('.trace-result p')+'.textContent'),h.detail);
  await evaluate($('[data-mode="compare"]')+'.click()');
  if (alternative) assert.equal((await ids())[0],alternative.id);
  const images=await evaluate('performance.getEntriesByType("resource").map(r=>r.name).filter(s=>s.includes("/documents/") && s.includes("/pages/"))');
  assert.ok(images.length && images.every(url=>url.startsWith(base+'/documents/') && new URL(url).searchParams.get('rev')===String(rev)));
  console.log('PASS · R'+rev+' · '+facts.length+' supported observations · '+pairs.join(', ')+' · pinned originals, keyboard and six widths');
}
