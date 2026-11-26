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

export async function checkAcceptancePdf(ctx,id,rev) {
  const {root,call,evaluate,wait}=ctx, base=root+'/api/cases/'+id;
  const task=await (await fetch(base)).json();
  assert.match(task.title,/^合成演练/u);
  rev ||= task.rev;
  const {report}=await (await fetch(base+'/reports/'+rev)).json();
  const found=report.findings.find(f=>f.rule==='H02');
  const declared=report.policy.version==='2026.11.26.27'?found.evidence:found.acceptance_execution;
  const proof=report.graph.acceptance_pdf_sources.records.find(r=>declared.includes(r.id));
  assert.ok(proof && found.evidence.includes(proof.id));
  const holder=q('#performance-index [data-pdf-acceptance="'+proof.id+'"]');
  await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev='+rev+'&view=acceptance-checks'});
  await wait(q('#performance-index')+'?.open && '+holder+'?.checkVisibility()','acceptance signature inspection');
  function bindingErrors(proofId) {
    const results={};
    for (const change of ['as issued','original','unit','layer or signature','page','finding edge','edge evidence','linked field','version']) {
      const r=structuredClone(state.bundle.report), g=r.graph, h=r.findings.find(f=>f.rule==='H02');
      const record=g.acceptance_pdf_sources.records.find(row=>row.id===proofId);
      if (change==='original') record.original_sha256='stale';
      if (change==='unit') record.unit=g.documents_by_kind.contract[0];
      if (change==='layer or signature') {
        if (record.signatures.length) record.signatures[0].ends_at=0;
        else record.pages[0].layer='unknown';
      }
      if (change==='page') r.calls.pages.find(p=>p.doc===record.doc).page_sha256='stale';
      if (change==='finding edge') g.edges=g.edges.filter(e=>!(e.type==='supports_result' && e.from===proofId && e.to==='finding/'+h.id));
      if (change==='edge evidence') g.edges.find(e=>e.type==='supports_result' && e.from===proofId && e.to==='finding/'+h.id).evidence=[];
      if (change==='linked field') h.evidence=h.evidence.filter(ref=>!record.fields.includes(ref));
      if (change==='version') {r.policy.version='2026.11.27.01'; delete h.acceptance_execution;}
      results[change]=PerformanceIndex.receiptEvidence(h,r).some(p=>p.record.id===proofId);
    }
    return results;
  }
  const binding=await evaluate('('+bindingErrors.toString()+')('+JSON.stringify(proof.id)+')');
  for (const [change,visible] of Object.entries(binding)) assert.equal(visible,change==='as issued',change);
  const affected=await evaluate('state.bundle.report.findings.filter(f=>f.stage && PerformanceIndex.receiptEvidence(f,state.bundle.report).length).map(f=>f.id)');
  assert.deepEqual(affected,report.findings.filter(f=>f.stage && f.evidence.includes(proof.id)).map(f=>f.id));
  const range=q('#performance-index [data-receipt-range]'), related=q('#performance-index [data-receipt-payments]');
  const panel=q('#performance-index .scope-proof-detail'), technical=q('#performance-index .scope-proof-detail .pdf-technical');
  const back=q('#performance-index .scope-back');
  const states={typeset:'仅见排印文字',current:'本版有电子签名，身份待核',earlier:'签名覆盖较早版',mismatch:'签名校验不符',visual:'签认图像待核',review:'签署凭证待核'};
  for (const width of widths) {
    await size(ctx,width);
    assert.equal(await evaluate(holder+'.querySelector("strong").textContent'),states[proof.state]);
    await evaluate(holder+'.focus();'+holder+'.click()');
    await wait(q('#page-dialog')+'?.open && '+q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(proof.fields[0]),'signed row in its own PDF');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    await wait('!'+q('#page-dialog')+'.open && document.activeElement==='+holder,'restore the original signature proof');
    await evaluate(related+'.click()');
    assert.deepEqual(await evaluate(all('#performance-index [data-receipt-phase]')+'.map(b=>b.dataset.receiptPhase)'),affected);
    const target=q('#performance-index [data-receipt-phase="'+affected[0]+'"]');
    assert.match(await evaluate(target+'.innerText'),/第二期 · 60%/u);
    if (proof.state==='earlier') await inspect(ctx,width,'#performance-index','acceptance-pdf-payments');
    await evaluate(target+'.focus()');
    for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key:'Enter',code:'Enter',windowsVirtualKeyCode:13,
      ...(type==='keyDown'?{text:'\r',unmodifiedText:'\r'}:{})});
    await wait(q('#scope-title')+'.textContent==="分期与付款" && '+q('.scope-check-select')+'.value==='+JSON.stringify(affected[0]),'select linked payment');
    assert.ok(await evaluate('document.activeElement==='+back));
    await evaluate(back+'.click()');
    await wait(q('#scope-title')+'.textContent==="交付验收" && document.activeElement==='+target,'restore selected receipt and payment');
    if (['confirmed'].includes(report.graph.facts.find(f=>f.id===proof.fields[0])?.status))
      assert.match(await evaluate(q('#performance-index .scope-source-quality')+'.innerText'),/栏中文字已核/u);
    if (width===390 || width===1440) {
      await evaluate(range+'.click()');
      await wait(range+'.getAttribute("aria-expanded")==="true" && !!'+technical,'show signature coverage');
      assert.equal(await evaluate(related+'.getAttribute("aria-expanded")'),'false');
      assert.equal(await evaluate(panel+'.querySelector(".pdf-timeline").dataset.state'),proof.signatures[0]?.state || 'unsigned');
      await evaluate(technical+'.querySelector("summary").click()');
      const evidence=await evaluate(technical+'.innerText');
      assert.ok(evidence.includes(proof.original_sha256));
      if (proof.signatures[0]) assert.ok(evidence.includes(proof.signatures[0].certificate_sha256));
      if (proof.state==='earlier') assert.match(await evaluate(panel+'.innerText'),/签后追加 [\d,]+ 字节/u);
      await evaluate(technical+'.querySelector("summary").click()');
    }
    await inspect(ctx,width,'#performance-index','acceptance-pdf-'+proof.state);
    if (width===390 || width===1440) await evaluate(range+'.click()');
    else await evaluate(related+'.click()');
  }
  console.log('PASS · acceptance PDF '+proof.state+' · R'+rev+' · six widths, original field and return focus');
}
