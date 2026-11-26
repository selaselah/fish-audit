import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {size,inspect} from './review-screen.mjs';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const all=s=>'[...document.querySelectorAll('+JSON.stringify(s)+')]';
const card='.acceptance-roster', choice=name=>'.roster-row input[value="'+name+'"]';
const widths=[320,360,390,768,1024,1440];
const mismatch='a305bb228b69454ebd334ca975820262', retest='f5849128cc6942e68544e99f3c23b222';

function invalidBindings() {
  const current=state.bundle.report;
  return ['intact','version','support','record','page','location','contract name','copied attestation',
    'other record','missing name','receipt reused','phase support'].map(change=>{
    const report=structuredClone(current), graph=report.graph, item=report.findings.find(f=>f.rule==='H02');
    const entry=item.acceptance_authority, record=entry.records[0], row=record.signed[1];
    const field=graph.facts.find(f=>f.id===row.fact);
    if (change==='version') report.policy.acceptance_authority='different';
    if (change==='support') graph.edges=graph.edges.filter(e=>!(e.type==='supports_result' && e.from===row.fact && e.to==='finding/'+item.id));
    if (change==='record') graph.edges=graph.edges.filter(e=>!(e.type==='records' && e.to===row.fact));
    if (change==='page') field.page_sha256='stale';
    if (change==='location') field.source_line.rects=[[0,1,1,0]];
    if (change==='contract name') entry.required[1]='林';
    if (change==='copied attestation') field.attestation.source_check.original_sha256=graph.documents[0].sha256;
    if (change==='other record') row.unit='another';
    if (change==='missing name') record.missing_names=[];
    if (change==='receipt reused') record.signed.push({...row});
    if (change==='phase support') {
      const phase=report.findings.find(f=>f.rule==='H04' && f.stage.name==='第二期');
      graph.edges=graph.edges.filter(e=>!(e.type==='supports_result' && e.from===row.fact && e.to==='finding/'+phase.id));
    }
    const view=AcceptanceRoster.bind(item,report);
    return view?view.records[0].phases.map(p=>p.name):null;
  });
}

export async function checkAcceptanceRoster(ctx,publicOnly) {
  const {root,call,evaluate,wait}=ctx;
  const sample=await (await fetch(root+'/assets/acceptance-roster.json')).json();
  const refs=()=>evaluate(all('.roster-evidence [data-roster-source]')+'.map(n=>n.dataset.rosterSource)');
  const click=async selector=>evaluate(q(selector)+'.focus();'+q(selector)+'.click()');
  const key=async (key,code)=>{
    for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key,code:key,windowsVirtualKeyCode:code});
  };
  async function navigate(id,rev) {
    const meta=await (await fetch(root+'/api/cases/'+id)).json();
    assert.match(meta.title,/^合成演练/u);
    await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev='+rev+'&view=acceptance-checks'});
    await wait(q('#performance-index')+'?.open && state.bundle.rev==='+rev+' && state.bundle.report.case_id==='+JSON.stringify(id),'pinned H02 in '+meta.title);
  }
  async function verifyOriginal(ref,isPublic) {
    const selector='[data-roster-source="'+ref+'"]';
    await click(selector);
    const dialog=isPublic?'#sample-review':'#page-dialog';
    const target=isPublic?q(dialog+' canvas')+'?.dataset.fact':q(dialog+' .located')+'?.dataset.fact';
    await wait(q(dialog)+'?.open && '+target+'==='+JSON.stringify(ref),'open cited physical evidence '+ref);
    if (isPublic) {
      const doc=sample.documents.find(d=>d.lines.some(l=>l.ref===ref)), row=doc.lines.find(l=>l.ref===ref);
      assert.equal(await evaluate(q('#sample-location')+'.textContent'),'第 '+doc.page+' 页 · 第 '+row.line+' 行');
      assert.equal(await evaluate(q('.sample-records a')+'.pathname'),doc.pdf);
    }
    await key('Escape',27);
    await wait('!'+q(dialog)+'.open && document.activeElement==='+q(selector),'restore focus to '+ref);
  }
  if (publicOnly) {
    for (const doc of sample.documents) {
      for (const [path,sha] of [[doc.pdf,doc.source_sha256],[doc.image,doc.page_sha256]]) {
        const response=await fetch(root+path);
        assert.equal(response.status,200);
        assert.equal(createHash('sha256').update(Buffer.from(await response.arrayBuffer())).digest('hex'),sha);
      }
    }
    await call('Page.navigate',{url:root+'/?scene=acceptance-signers#workflow'});
    await wait(q('#inspection-version')+'?.textContent==="合成案例 · R5" && '+q(card)+'!=null','fixed public specimen');
  } else {
    await navigate(mismatch,5);
    assert.deepEqual(await evaluate('('+invalidBindings.toString()+')()'),[
      ['第二期','第三期'],...Array(10).fill(null),['第三期']]);
  }
  const [record]=sample.roster.records, other=record.signed.find(s=>s.name==='何平').ref;
  const first=record.signed.find(s=>s.name==='周宁').ref, contract=sample.roster.contract;
  const phases=all('.roster-phase-list .roster-locator strong');
  for (const width of widths) {
    await size(ctx,width);
    await click(choice('何平'));
    assert.equal(await evaluate(q(card)+'.dataset.person'),'何平');
    assert.equal(await evaluate(q('.roster-review-note')+'.textContent'),'何平 · 请核查代签授权或其他依据。');
    assert.deepEqual(await refs(),[contract,other]);
    await wait(all('.roster-evidence .roster-strip :is(canvas,img)')+'.length===2','both original line images');
    await wait(all('.roster-evidence .roster-sheet i')+'.length===2','document miniatures with physical highlights');
    for (const ref of [contract,other]) {
      const row=sample.documents.flatMap(d=>d.lines).find(l=>l.ref===ref);
      const marker=q('[data-roster-source="'+ref+'"] .roster-sheet i');
      const rect=await evaluate('["left","top","width","height"].map(k=>parseFloat('+marker+'.style[k])/100)');
      const [l,t,r,b]=row.rects[0];
      assert.ok(rect.every((n,i)=>Math.abs(n-[l,t,r-l,b-t][i])<.00001));
    }
    assert.deepEqual(await evaluate(all('.roster-row')+'.map(n=>n.innerText.replace(/\\s+/gu,""))'),
      ['周宁已列名已核图','林岚已列名缺已核栏','何平条款未列已核图']);
    const bounds=await evaluate(q(card)+'.scrollWidth<='+q(card)+'.clientWidth+1');
    assert.ok(bounds,'roster width '+width);
    await inspect(ctx,width,publicOnly?'.workflow .section-inner':'#performance-index',publicOnly?'public-acceptance-roster':'acceptance-roster');
    await click('.roster-formats [value=text]');
    assert.equal(await evaluate(q('.roster-formats [value=text]')+'.getAttribute("aria-pressed")'),'true');
    assert.equal(await evaluate(q('.roster-evidence .roster-strip')+'.checkVisibility()'),false);
    assert.deepEqual(await evaluate(all('.roster-evidence .roster-quote mark')+'.map(m=>m.textContent)'),['何平']);
    await click('.roster-formats [value=image]');
    await verifyOriginal(other,publicOnly); await verifyOriginal(contract,publicOnly);
    await evaluate(q(choice('何平'))+'.focus()'); await key('ArrowLeft',37);
    await wait(q(card)+'.dataset.person==="林岚"','arrow selects absent signer');
    assert.deepEqual(await refs(),[contract]);
    assert.match(await evaluate(q('.roster-absent')+'.textContent'),/本单缺少林岚/u);
    await key('ArrowLeft',37);
    assert.deepEqual(await refs(),[contract,first]);
    await click('.roster-phases summary');
    assert.deepEqual(await evaluate(phases+'.map(n=>n.textContent)'),['第二期 · 有风险','第三期 · 有风险']);
    await verifyOriginal(record.phases[0].ref,publicOnly); await click('.roster-phases summary');
  }
  if (publicOnly) {
    assert.equal(await evaluate('performance.getEntriesByType("resource").some(r=>new URL(r.name).pathname.startsWith("/api/"))'),false);
    console.log('PASS · watermarked R5, source hashes, three names, two cited installments, no tenant requests · '+widths.join('/'));
    return;
  }
  await navigate(retest,5);
  assert.equal(await evaluate(q('.roster-picker')+'.selectedOptions[0].textContent'),'整改复验 · 复验报告.pdf');
  assert.equal(await evaluate(q(card)+'.dataset.person'),'林岚');
  assert.deepEqual(await refs(),['d04/p1/f17']);
  assert.ok((await evaluate(q('.scope-reason')+'.textContent')).includes('不合格'));
  await evaluate(q('.roster-picker')+'.value="d06";'+q('.roster-picker')+'.dispatchEvent(new Event("change"))');
  await click(choice('林岚')); assert.deepEqual(await refs(),['d04/p1/f17','d06/p1/f15']);
  await evaluate(q('.roster-picker')+'.value="d01";'+q('.roster-picker')+'.dispatchEvent(new Event("change"))');
  await click(choice('周宁')); assert.deepEqual(await refs(),['d04/p1/f17','d01/p1/f18']);
  await verifyOriginal('d01/p1/f18',false);
  await navigate('1b0dcebe24334e4391956579519b775b',3);
  assert.equal(await evaluate(q(card)+'.dataset.person'),'林岚');
  assert.deepEqual(await refs(),['d02/p1/f17']);
  await navigate('647a4558f1464bcbb22fc3666d6075ef',1);
  assert.ok((await evaluate(all('.roster-row')+'.map(r=>r.innerText)')).every(txt=>txt.includes('待核图')));
  await navigate('647a4558f1464bcbb22fc3666d6075ef',2);
  assert.ok((await evaluate(all('.roster-row')+'.map(r=>r.innerText)')).every(txt=>txt.includes('已核图')));
  for (const [id,rev,ref,status] of [[mismatch,1,'d04/p1/f12','unsupported'],['de904f4b41324d1d842ae6e574cb0edb',3,'d04/p1/f15','visual']]) {
    await navigate(id,rev);
    assert.equal(await evaluate(q(card)),null);
    assert.ok(await evaluate(q('.scope-reason')+'.textContent.length>0'));
    assert.equal(await evaluate(q('.scope-source-quality .tag')+'.dataset.state'),status);
    assert.equal(await evaluate(q('.scope-source-crop')+'.childElementCount'),0);
    assert.equal(await evaluate(q('.scope-open-original')+'.dataset.fact'),ref);
    await click('.scope-open-original');
    await wait(q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(ref),'unresolved field on its own original');
    await key('Escape',27);
  }
  console.log('PASS · five cases, distinct original and reinspection records, uncertain sources, phase dependencies, keyboard, focus · '+widths.join('/'));
}
