import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

export async function checkRelease({root,call,evaluate,wait},cid,revision) {
  const api=root+'/api/cases/'+cid, task=await (await fetch(api)).json();
  assert.ok(task.title.startsWith('合成演练 · '));
  const rev=Number(revision || task.rev), {report}=await (await fetch(api+'/reports/'+rev)).json();
  const node=s=>'document.querySelector('+JSON.stringify(s)+')';
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+rev});
  await wait(node('.phase-choice'),'issued phases');
  const phase=report.findings.filter(f=>f.rule==='H04')[1], bank=report.findings.find(f=>f.rule==='H05');
  const r=phase.payment_opinion?.release;
  if (!r) {
    assert.ok(!report.graph.payment_release_sources);
    assert.equal(await evaluate(node('[data-release-state]')),null);
    console.log('PASS · R'+rev+' · historical workpaper before signed releases'); return;
  }
  const timing=bank.payment_opinion.release.timing;
  const section='[data-phase-finding="'+phase.id+'"] .phase-evidence', inside=s=>node(section+' '+s);
  await evaluate(node('[data-phase-choice="'+phase.id+'"]')+'.click()');
  assert.equal(await evaluate(node(section)+'.dataset.mode'),['before','same_day'].includes(timing)?'timeline':'opinion');
  const choices=inside('.opinion-record .opinion-choices');
  const mode=k=>evaluate(inside('button[data-mode="'+k+'"]')+'.click()');
  const text=()=>evaluate(inside('.opinion-record q')+'.textContent');
  await mode('opinion');assert.equal(await evaluate(inside('.proof-opinion')+'.dataset.releaseState'),r.state);
  const note=phase.payment_opinion.notes[0], authority=r.sources.find(s=>s.role==='authority');
  const entryKind={signer_mismatch:'signature',reference_mismatch:'receipt',pending:'approval_date'}[r.state] || 'decision';
  const entry=r.sources.find(s=>s.role===entryKind);
  assert.ok(entry && authority); assert.equal(await text(),entry.quote);
  const press=async key=>{
    await call('Input.dispatchKeyEvent',{type:'keyDown',key,code:key});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key,code:key});
  };
  await evaluate(choices+'.querySelector("[aria-pressed=true]").focus()');
  for (const [key,row] of [['Home',note],['ArrowRight',authority],['End',entry]]) {
    await press(key); assert.equal(await text(),row.quote);
    await evaluate(inside('.opinion-record .ref')+'.click()');
    await wait(node('#page-dialog .located')+'?.textContent.includes('+JSON.stringify(row.quote)+')','the selected original row');
    await wait(node('#page-dialog .page-image')+'?.naturalWidth>0','issued page image');
    const url=new URL(await evaluate(node('#page-dialog .source-tools a')+'.href'));
    assert.ok(url.pathname.endsWith('/documents/'+row.doc+'/pages/'+row.page));assert.equal(url.searchParams.get('rev'),String(rev));
    await evaluate(node('#page-dialog [data-close]')+'.click()');
    await evaluate(choices+'.querySelector("[aria-pressed=true]").focus()');
  }
  const fallback=await evaluate(`(() => {
    const {graph,findings}=state.bundle.report;
    const finding=findings.find(f=>f.id===${JSON.stringify(phase.id)});
    const mandate=ReleaseEvidence.one(ReleaseEvidence.sources(graph,finding),'authority');
    const page=mandate.doc+'/p'+mandate.page;
    const without=skip=>({...graph,edges:graph.edges.filter(edge=>!skip(edge))});
    const supports=edge=>edge.type==='supports_result' && edge.to==='finding/'+finding.id;
    const copy=without(edge=>supports(edge) && mandate.facts.includes(edge.from));
    const row=ReleaseEvidence.one(ReleaseEvidence.sources(copy,finding),'authority');
    const roleIn=g=>ReleaseEvidence.sources(g,finding).some(s=>s.role==='authority');
    AcceptanceOpinion.source(row,copy).querySelector('button').click();
    return {
      facts:row.facts,
      pageMissing:roleIn(without(edge=>supports(edge) && edge.from===page)),
      lineMissing:roleIn(without(edge=>edge.type==='payment_release_basis' && edge.from===row.unit && edge.to===page && edge.line===row.line))
    };
  })()`);
  assert.deepEqual(fallback,{facts:[],pageMissing:false,lineMissing:false});
  const located=node('#page-dialog .evidence-row.located');
  await wait(located+'?.dataset.sourceRef==='+JSON.stringify('release-line/'+authority.line),'unboxed mandate on its printed line');
  assert.ok(await evaluate(located+'.textContent.includes('+JSON.stringify(authority.quote)+')'));
  assert.equal(await evaluate(node('#page-dialog .image-sheet svg rect')),null);
  assert.equal(new URL(await evaluate(node('#page-dialog .source-tools a')+'.href')).searchParams.get('rev'),String(rev));
  await evaluate(node('#page-dialog [data-close]')+'.click()');
  const state={matched:'已核具名放行',signer_mismatch:'签发人不符',reference_mismatch:'原验收单号不符',pending:'缺放行签字日'}[r.state];
  assert.equal(await evaluate(inside('.proof-count')+'.textContent'),state);
  async function capture(selector,name) {
    const panel=node(selector);
    await evaluate('document.activeElement.blur();'+panel+'.scrollIntoView({block:"center"});document.fonts.ready.then(()=>true)');
    const clip=await evaluate('(()=>{const b='+panel+'.getBoundingClientRect();return {x:b.x+scrollX,y:b.y+scrollY,width:b.width,height:b.height,scale:1}})()');
    const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
    await writeFile(join(process.env.AUDIT_UI_SHOTS,name+'.png'),Buffer.from(shot.data,'base64'));
  }
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:940,deviceScaleFactor:1,mobile:width<600});
    for (const k of ['checks','opinion','timeline']) {
      await mode(k);
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && '+node(section)+'.scrollWidth<='+node(section)+'.clientWidth+1'),k+' fits '+width);
      if (k==='checks') assert.equal(await evaluate(inside('[data-check=release]')+'.dataset.state'),r.state==='matched'?'ok':'missing');
      if (process.env.AUDIT_UI_SHOTS && (width===390 || width===1440) &&
        (k==='opinion' && r.state==='signer_mismatch' || k==='timeline' && timing==='before'))
        await capture('.performance-panel','release-'+(k==='timeline'?'dates':'signer')+'-'+width);
    }
    const event=inside('[data-event=release]');
    assert.equal(await evaluate(event+'?.closest("[data-day]")?.dataset.day ?? null'),r.state==='matched'?r.signed_on:null);
    const hold=inside('[data-event=hold]');
    assert.equal(await evaluate(hold+'?.closest("[data-day]")?.dataset.day ?? null'),r.held_on);
    if (r.held_on) assert.ok(await evaluate(hold+'.closest("[data-day]")==='+inside('[data-event=acceptance]')+'.closest("[data-day]")'));
    const count=await evaluate(inside('.proof-count')+'.textContent');
    if (timing==='before') assert.equal(count,'实付早于放行 1 天');
    if (timing==='same_day') {
      assert.equal(count,'放行与实付同日 · 时分待核');
      assert.ok(await evaluate(event+'.closest("[data-day]")==='+inside('[data-event=paid]')+'.closest("[data-day]")'));
    }
  }
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:940,deviceScaleFactor:1,mobile:false});
  if (r.held_on) {
    await evaluate(inside('[data-event=hold]')+'.click()');
    await wait(node('#page-dialog .located')+'?.textContent.includes('+JSON.stringify(note.quote)+')','hold event opens the original hold instruction');
    const url=new URL(await evaluate(node('#page-dialog .source-tools a')+'.href'));
    assert.ok(url.pathname.endsWith('/documents/'+note.doc+'/pages/'+note.page));assert.equal(url.searchParams.get('rev'),String(rev));
    await evaluate(node('#page-dialog [data-close]')+'.click()');
  }
  await mode('opinion');
  const party=authority.facts.find(id=>report.graph.facts.some(f=>f.id===id && f.source_line?.text===authority.quote && f.source_line?.rects.length));
  const pairs=[['release-authority',[party,r.signature_ref]],['release-receipt',[r.original_ref,r.receipt_ref]],
    ['release-transfer',[r.date_ref,bank.payment_opinion.release.paid_ref]]];
  for (const [key,ids] of pairs) {
    const target=inside('[data-pair="'+key+'"]');
    const needed=ids.every(Boolean) && (key!=='release-receipt' || r.state==='reference_mismatch') && (key!=='release-transfer' || r.state==='matched');
    assert.equal(await evaluate('Boolean('+target+')'),needed,key);
    if (!needed) continue;
    await evaluate(target+'.click()');await wait('document.querySelectorAll(".compare-leaf canvas").length===2','two original lines');
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".compare-leaf")].map(n=>n.dataset.fact)'),ids);
    const fold=node('.release-relations');
    if (!(await evaluate(fold+'.open'))) await evaluate(fold+'.querySelector("summary").click()');
    await wait(fold+'.querySelectorAll(".reservation-note").length>1','related original lines');
    await evaluate(node('#tabs [data-tab=report]')+'.click()');
    assert.equal(await evaluate(node('.phase-choice[aria-selected=true]')+'.dataset.phaseChoice'),phase.id);
  }
  console.log('PASS · R'+rev+' · '+r.state+' / '+timing+' · six widths, originals, signer, receipt number and dated release');
}
