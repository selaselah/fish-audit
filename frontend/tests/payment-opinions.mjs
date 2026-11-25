import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

export async function checkPaymentOpinions({root,call,evaluate,wait},cid,revision) {
  const api=root+'/api/cases/'+cid, task=await (await fetch(api)).json();
  assert.ok(task.title.startsWith('合成演练 · '));
  const rev=Number(revision || task.rev); assert.ok(Number.isSafeInteger(rev) && rev>0);
  const {report}=await (await fetch(api+'/reports/'+rev)).json(), graph=report.graph;
  const node=s=>'document.querySelector('+JSON.stringify(s)+')';
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+rev});
  await wait(node('.performance-panel .phase-choice'),'issued workpaper');
  const phases=report.findings.filter(f=>f.rule==='H04');
  const phase=phases[1], payment=report.findings.find(f=>f.rule==='H05'), quality=report.findings.find(f=>f.rule==='H02');
  const section='[data-phase-finding="'+phase.id+'"] .phase-evidence';
  const inside=s=>node(section+' '+s);
  const opinion=phase.payment_opinion;
  if (!opinion) {
    assert.equal(graph.acceptance_reservation_sources?.payment_opinions,undefined);
    assert.equal(await evaluate('document.querySelectorAll("[data-payment-opinion-state],button[data-mode=opinion]").length'),0);
    console.log('PASS · historical R'+rev+' · issued controls preserved'); return;
  }
  await evaluate(node('[data-phase-choice="'+phase.id+'"]')+'.click()');
  assert.equal(await evaluate(node(section)+'.dataset.mode'),opinion.state==='assent'?'checks':'opinion');
  await evaluate(inside('button[data-mode=opinion]')+'.click()');
  assert.equal(await evaluate(inside('.proof-opinion')+'.dataset.paymentOpinionState'),opinion.state);
  assert.equal(await evaluate(inside('.opinion-quality .tag')+'.dataset.state'),quality.status);
  const q=graph.facts.find(f=>quality.evidence.includes(f.id) && opinion.units.includes(f.unit || f.doc) &&
    f.field===(quality.status==='issue'?'measured_result':'acceptance_result'));
  assert.equal(await evaluate(inside('.opinion-quality q')+'.textContent'),q.quote);
  const card=inside('.opinion-record'), notes=opinion.notes;
  const select=async key=>{
    await call('Input.dispatchKeyEvent',{type:'keyDown',key,code:key});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key,code:key});
  };
  async function original(row,raw=false) {
    const ref=raw?'payment-opinion-line/'+row.line:row.facts[0];
    const selected=node('#page-dialog .evidence-row.located');
    await wait(selected+'?.dataset.'+(raw?'sourceRef':'fact')+'==='+JSON.stringify(ref),'located issued original');
    assert.ok(await evaluate(selected+'.textContent.includes('+JSON.stringify(row.quote)+')'));
    await wait(node('#page-dialog .page-image')+'?.naturalWidth>0','page image');
    const url=new URL(await evaluate(node('#page-dialog .source-tools a')+'.href'));
    assert.ok(url.pathname.endsWith('/documents/'+row.doc+'/pages/'+row.page)); assert.equal(url.searchParams.get('rev'),String(rev));
    assert.equal(await evaluate('Boolean(document.querySelector("#page-dialog .image-sheet rect"))'),!raw);
    await evaluate(node('#page-dialog [data-close]')+'.click()');
  }
  for (const [i,row] of notes.entries()) {
    if (i) { await evaluate(inside('[data-opinion-choice]')+'.focus()'); await select('End'); }
    if (notes.length===2) assert.equal(await evaluate(card+'.querySelector("[aria-pressed=true]").dataset.opinionChoice'),row.stance);
    assert.equal(await evaluate(card+'.querySelector("q").textContent'),row.quote);
    if (row.facts.length) {
      await wait(card+'.querySelector(".opinion-strip canvas")?.width>0','native row preview');
      assert.equal(await evaluate(card+'.querySelector("[data-excerpt-fact]").dataset.excerptFact'),row.facts[0]);
    }
    await evaluate(card+'.querySelector(".ref").click()'); await original(row,!row.facts.length);
  }
  if (notes.length===2) {
    await evaluate(inside('[data-opinion-choice][aria-pressed=true]')+'.focus()'); await select('Home');
    assert.equal(await evaluate(card+'.querySelector("q").textContent'),notes[0].quote);
  }
  // Disconnect the finding's observation edges in a browser-only graph copy. The page still attests its literal row.
  const fallback=await evaluate([
    '(() => { const g=state.bundle.report.graph, f=state.bundle.report.findings.find(f=>f.id==='+JSON.stringify(phase.id)+');',
    'const n=f.payment_opinion.notes[0], cut=refs=>({...g,edges:g.edges.filter(e=>!(e.type==="supports_result" && e.to==="finding/"+f.id && refs.includes(e.from)))});',
    'const copy=cut(n.facts), [row]=AcceptanceOpinion.rows(copy,f);',
    'const observation=AcceptanceOpinion.observation(row,copy); AcceptanceOpinion.source(row,copy).querySelector("button").click();',
    'return [Boolean(observation),AcceptanceOpinion.rows(cut([n.doc+"/p"+n.page]),f).length]; })()'
  ].join('\n'));
  assert.deepEqual(fallback,[false,0]); await original(notes[0],true);
  if (opinion.state==='conflict') {
    const guards=await evaluate([
      '(() => { const g=state.bundle.report.graph,f=state.bundle.report.findings.find(f=>f.id==='+JSON.stringify(phase.id)+');',
      'const notes=AcceptanceOpinion.rows(g,f), first=notes[0];',
      'const cut={...g,edges:g.edges.filter(e=>!(e.type==="acceptance_payment_opinion" && e.line===first.line))};',
      'const scan=AcceptanceOpinion.source({...first,line:null,facts:[]},g);',
      'const panel=AcceptanceOpinion.panel(f,null,[...notes,first],g), select=panel.querySelector("select");',
      'select.selectedIndex=1; select.dispatchEvent(new Event("change"));',
      'return [AcceptanceOpinion.rows(cut,f).length,Boolean(scan.querySelector("q")),scan.textContent.includes("整页影像"),select.length,panel.querySelector("q").textContent]; })()'
    ].join('\n'));
    assert.deepEqual(guards,[0,false,true,3,notes[1].quote]);
  }
  async function capture(selector,name) {
    const panel=node(selector);
    await evaluate('document.activeElement.blur();'+panel+'.scrollIntoView({block:"center"});document.fonts.ready.then(()=>true)');
    const clip=await evaluate('(()=>{const b='+panel+'.getBoundingClientRect();return {x:b.x+scrollX,y:b.y+scrollY,width:b.width,height:b.height,scale:1}})()');
    const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
    await writeFile(join(process.env.AUDIT_UI_SHOTS,name+'.png'),Buffer.from(shot.data,'base64'));
  }
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:940,deviceScaleFactor:1,mobile:width<600});
    for (const mode of ['checks','timeline','opinion']) {
      await evaluate(inside('button[data-mode='+mode+']')+'.click()');
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && '+node(section)+'.scrollWidth<='+node(section)+'.clientWidth+1'),mode+' fits '+width);
    }
    if (width===1440) {
      const bounds=await evaluate('(()=>{const g='+inside('.proof-opinion')+', r=g.querySelector(".opinion-record");return [g.getBoundingClientRect().right,r.getBoundingClientRect().right]})()');
      assert.ok(Math.abs(bounds[0]-bounds[1])<2,'both cards fill the evidence panel');
    }
    if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width) && opinion.state==='conflict') await capture('.performance-panel','opinion-'+width);
  }
  const factIds=notes.map(n=>n.facts[0]).filter(Boolean);
  const paid=graph.facts.find(f=>f.field==='paid_on' && payment.evidence.includes(f.id));
  let pairKey=null, refs=[];
  if (opinion.state==='conflict' && factIds.length===2) { pairKey='opinion-conflict'; refs=factIds; }
  if (notes.length===1 && factIds.length && paid) { pairKey='opinion-transfer'; refs=[factIds[0],paid.id]; }
  const standard=quality.status==='issue' && graph.facts.find(f=>f.field==='acceptance_criteria' && quality.evidence.includes(f.id));
  assert.equal(await evaluate(inside('.opinion-tools')+'?.children.length || 0'),Number(Boolean(pairKey))+Number(Boolean(standard)));
  if (standard) {
    await evaluate(inside('[data-pair=reading]')+'.click()');
    await wait('document.querySelectorAll(".compare-leaf canvas").length===2','contract and measured temperature');
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".compare-leaf")].map(n=>n.dataset.fact)'),[standard.id,q.id]);
    await evaluate(node('#tabs [data-tab=report]')+'.click()');
  }
  if (pairKey) {
    await call('Emulation.setDeviceMetricsOverride',{width:1440,height:940,deviceScaleFactor:1,mobile:false});
    await evaluate(inside('[data-pair="'+pairKey+'"]')+'.click()');
    await wait('document.querySelectorAll(".compare-leaf canvas").length===2','two original excerpts');
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".compare-leaf")].map(n=>n.dataset.fact)'),refs);
    if (process.env.AUDIT_UI_SHOTS && pairKey==='opinion-conflict') await capture('.evidence-compare','opinion-pair');
    const fold=node('.opinion-relations');
    await evaluate(fold+'.querySelector("summary").click()');
    await wait(fold+'.querySelectorAll("[data-opinion-original]").length==='+notes.length,'graph original lines');
    await evaluate(node('#tabs [data-tab=report]')+'.click()');
    assert.equal(await evaluate(node('.phase-choice[aria-selected=true]')+'.dataset.phaseChoice'),phase.id);
    assert.equal(await evaluate(node(section)+'.dataset.mode'),'opinion');
  }
  for (const f of phases.filter(f=>!f.payment_opinion)) {
    await evaluate(node('[data-phase-choice="'+f.id+'"]')+'.click()');
    assert.equal(await evaluate(node('[data-phase-finding="'+f.id+'"] button[data-mode=opinion]')),null);
  }
  if (opinion.state==='conflict') {
    await call('Network.enable'); await call('Network.setBlockedURLs',{urls:['*'+cid+'/documents/*/pages/*']});
    await call('Page.reload',{ignoreCache:true});
    await wait(inside('.opinion-record [data-excerpt-fact]'),'original unavailable');
    await evaluate(node('[data-phase-choice="'+phase.id+'"]')+'.click()');
    await wait(inside('.opinion-record .opinion-strip:not([data-loading]) q:not(.visually-hidden)'),'archived text fallback');
    assert.equal(await evaluate(card+'.querySelector("q").textContent'),notes[0].quote);
    assert.equal(await evaluate(card+'.querySelector("canvas")'),null);
    await call('Network.setBlockedURLs',{urls:[]});
    await evaluate(inside('button[data-mode=checks]')+'.click()'); await evaluate(inside('button[data-mode=opinion]')+'.click()');
    await wait(card+'.querySelector("canvas")?.width>0','page image recovers');
  }
  console.log('PASS · R'+rev+' · '+opinion.state+' · quality, scope, original, raw line fallback, source pairs and six viewports');
}
