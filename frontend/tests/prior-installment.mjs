import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const key=async(call,name,modifiers=0)=>{
  for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key:name,modifiers,
    code:({k:'KeyK',' ':'Space'})[name]||name,windowsVirtualKeyCode:({k:75,Escape:27,Enter:13,ArrowUp:38,ArrowDown:40,ArrowLeft:37,ArrowRight:39,End:35,Home:36})[name]});
};
async function picture(call,evaluate,selector,name) {
  if (!process.env.AUDIT_UI_SHOTS) return;
  await evaluate('document.fonts.ready.then(()=>Promise.all(document.getAnimations().filter(a=>a.effect?.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})))).then(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))');
  const clip=await evaluate('(()=>{const r='+q(selector)+'.getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}})()');
  const {data}=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
  await writeFile(join(process.env.AUDIT_UI_SHOTS,name+'.png'),Buffer.from(data,'base64'));
}
async function viewport(call,width) {
  await call('Emulation.setDeviceMetricsOverride',{width,height:width<=390?844:900,deviceScaleFactor:1,mobile:false});
}

export async function checkPublicCompare({root,call,evaluate,wait}) {
  await call('Page.navigate',{url:root+'/'});
  await wait(q('#compare-sample')+' && !'+q('#compare-sample')+'.hidden','first-screen evidence compare');
  const pages=['/assets/showcase-contract-page.jpg','/assets/showcase-acceptance-page.png'];
  const hashes=['aa535f590439173143a8a0654f3c4ed2f482477502cf247b7b2438277394dfdb','fb4799101ab7c9ee46baa4705ed0712abeede3e50e22d8f0b8aebfb5a9ef27bd'];
  for (const [i,path] of pages.entries()) {
    const response=await fetch(root+path); assert.equal(response.status,200);
    assert.match(response.headers.get('content-type'),/^image\/jpeg/);
    assert.equal(createHash('sha256').update(Buffer.from(await response.arrayBuffer())).digest('hex'),hashes[i]);
  }
  for (const width of [1440,1024,820,768,390,320]) {
    await viewport(call,width);
    await evaluate(q('#compare-sample')+'.click()');
    await wait('[...document.querySelectorAll("#sample-compare canvas")].every(c=>c.dataset.scale==="2")','two original images');
    assert.deepEqual(await evaluate('[...document.querySelectorAll("#sample-compare canvas")].map(c=>c.dataset.fact)'),['d02/p1/f13','d04/p1/f11']);
    const layout=await evaluate('(()=>{const [a,b]=[...document.querySelectorAll(".public-compare-panes canvas")].map(e=>e.getBoundingClientRect());return [a.top===b.top,document.documentElement.scrollWidth<=innerWidth]})()');
    assert.deepEqual(layout,[width>650,true]);
    const image=await evaluate(q('#sample-compare canvas')+'.toDataURL()');
    await evaluate(q('#compare-zoom')+'.focus()');await key(call,'End');
    await wait(q('#compare-zoom')+'.value==="3"','synchronized zoom');
    assert.equal(await evaluate(q('#sample-compare canvas')+'.dataset.scale'),'3');
    assert.notEqual(await evaluate(q('#sample-compare canvas')+'.toDataURL()'),image);
    if ([1440,390].includes(width)) await picture(call,evaluate,'#sample-compare','public-compare-'+width);
    await key(call,'Home');assert.equal(await evaluate(q('#compare-zoom')+'.getAttribute("aria-valuetext")'),'整页');
    await key(call,'Escape');await wait('!'+q('#sample-compare')+'.open && document.activeElement==='+q('#compare-sample'),'restore first-screen control');
  }
}
export async function checkPrior({root,call,evaluate,wait},cid,fixed) {
  const api=root+'/api/cases/'+cid, detail=await (await fetch(api)).json();
  assert.match(detail.title,/^合成演练 · /);
  const rev=Number(fixed||detail.rev);
  const {report}=await (await fetch(api+'/reports/'+rev)).json();
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+rev});
  await wait(q('.performance-overview')+' && state.bundle.rev==='+rev,'fixed audit workspace');
  const phase=report.findings.find(f=>f.rule==='H04' && f.prior_installment);
  if (!phase) {assert.equal(await evaluate('!'+q('.prior-panel')),true);console.log('PASS · historical R'+rev);return;}
  const p=phase.prior_installment, payments=report.findings.filter(f=>f.rule==='H05' && f.prior_installment);
  const row='#phase-record-'+phase.id, panel=row+' .prior-panel';
  assert.ok(await evaluate('!!'+q(panel)),phase.id+' '+p.state+' '+await evaluate(q(row)+'.innerText'));
  await evaluate(q('#phase-choice-'+phase.id)+'.click();'+q(panel)+'.open=true');
  if (payments.length) {
    await evaluate(q(panel+' .prior-switch button:first-child')+'.focus()');await key(call,'End');
    assert.equal(await evaluate(q(panel)+'.dataset.priorMode'),'payment');await key(call,'Home');
    assert.equal(await evaluate(q(panel)+'.dataset.priorMode'),'submission');
  }
  for (const mode of ['submission','payment']) {
    if (mode==='payment' && !payments.length) continue;
    const state=mode==='submission'?p:payments[0].prior_installment;
    await evaluate(q(panel+' .prior-switch button:'+(mode==='submission'?'first-child':'last-child'))+'.click()');
    assert.equal(await evaluate(q(panel)+'.dataset.priorState'),state.state);
    const visible=await evaluate(q(panel+' .prior-money')+'.textContent');
    const value=mode==='submission'?p.seen:state.before;
    assert.equal(visible,value===null?'待核':'¥'+Number(value).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}));
    await evaluate('(()=>{const fold='+q(panel+' .prior-designations')+';if(fold) fold.open=true})()');
    const refs=await evaluate('[...'+q(panel)+'.querySelectorAll("[data-prior-ref]")].map(e=>e.dataset.priorRef)');
    assert.ok(refs.includes(p.terms[0]));
    if (mode==='payment' && state.payment_date_ref) assert.ok(refs.includes(state.payment_date_ref));
    for (const ref of refs) {
      await evaluate(q(panel+' [data-prior-ref="'+ref+'"]')+'.click()');
      const r=report.graph.prior_installment_sources.lines.find(r=>r.id===ref);
      const fact=report.graph.facts.find(f=>f.id===ref || r?.facts.includes(f.id) && f.quote===r.quote);
      const doc=r?.doc||fact.doc, page=r?.page||fact.page;
      await wait(q('#page-dialog')+'.open && '+q('#page-dialog .page-image')+'?.complete && '+q('#page-dialog .page-image')+'?.naturalWidth>0','cited receipt image');
      const src=await evaluate(q('#page-dialog a[href*="/pages/"]')+'.href');
      assert.match(src,new RegExp('/documents/'+doc+'/pages/'+page+'\\?rev='+rev+'$'));
      const sum=createHash('sha256').update(Buffer.from(await (await fetch(src)).arrayBuffer())).digest('hex');
      assert.equal(sum,report.graph.nodes.find(n=>n.id===doc+'/p'+page).sha256);
      const located=await evaluate(q('#page-dialog .located')+'?.innerText');
      assert.ok(located && (located.includes((r||fact).quote) || located.includes(fact?.value)),ref+' '+located);
      await key(call,'Escape');await wait('!'+q('#page-dialog')+'.open','return to comparison');
    }
  }
  for (const width of [1440,1024,820,768,390,320]) {
    await viewport(call,width);
    await evaluate(q(panel)+'.scrollIntoView({block:"center"})');
    assert.ok(await evaluate(q(panel)+'.scrollWidth<='+q(panel)+'.clientWidth+1 && document.documentElement.scrollWidth<=innerWidth'));
    if ([1440,390].includes(width) && payments[0]?.prior_installment.state==='early')
      await picture(call,evaluate,panel,'prior-time-'+width);
  }
  const valid=await evaluate('(()=>{const report=state.bundle.report,f=structuredClone(report.findings.find(x=>x.id==='+JSON.stringify(phase.id)+'));f.prior_installment.seen="98765.43";return PriorInstallment.read(f,report.graph)===null})()');
  assert.ok(valid);
  if (p.seen!==null) assert.ok(await evaluate('(()=>{const g=structuredClone(state.bundle.report.graph), f=state.bundle.report.findings.find(x=>x.id==='+JSON.stringify(phase.id)+');g.edges=g.edges.filter(e=>e.type!=="prior_installment_source");return PriorInstallment.read(f,g)===null})()'));
  if (payments.some(f=>f.prior_installment.state==='early')) await checkReceiptSelection(evaluate);
  console.log('PASS · '+detail.title+' · R'+rev+' · '+p.state);
}
// Exercise multiple dependent receipts with the same Python rule engine, in a detached component.
async function checkReceiptSelection(evaluate) {
  const source=[
    'import json,sys',
    'sys.path[:0]=["server","server/tests"]',
    'from test_prior_installment import paper',
    'from graph import link_procedures',
    'r=paper((("第一期","10000","2026-09-10"),("第一期","20000","2026-09-24"),("第二期","10000","2026-09-21"),("第二期","20000","2026-09-24"),("第二期","30000","2026-09-25")))',
    'link_procedures(r["graph"],r["findings"],{"expert":{"model":"fixture"},"pages":[]})',
    'print(json.dumps(r,ensure_ascii=False))'
  ].join('\n');
  const fixture=JSON.parse(execFileSync(process.env.AUDIT_PYTHON || 'server/.venv/bin/python',['-c',source],{encoding:'utf8'}));
  const actual=await evaluate('(()=>{const {graph,findings}='+JSON.stringify(fixture)+';'+
    'const [phase,...payments]=findings.filter(f=>f.prior_installment),panel=PriorInstallment.panel(phase,payments,graph);'+
    'const select=panel.querySelector("select");if (!select || select.hidden) return [];'+
    'return [...select.options].map((_,i)=>{select.selectedIndex=i;select.dispatchEvent(new Event("change"));return [panel.dataset.priorState,panel.querySelector(".prior-money").textContent]})})()');
  assert.deepEqual(actual,[['early','¥10,000.00'],['same_day','¥10,000.00'],['met','¥30,000.00']]);
}
export async function checkNavigation({root,call,evaluate,wait},cid) {
  await call('Page.navigate',{url:root+'/app'});
  await wait(q('.audit-card')+' && !'+q('#desk')+'.hidden','visible board');
  await evaluate(q('#desk-filters summary')+'.click()');
  assert.equal(await evaluate(q('#case-list')+'.dataset.density'),'compact');
  await evaluate(q('#desk-density')+'.click()');
  assert.equal(await evaluate(q('#case-list')+'.dataset.density'),'expanded');
  await call('Page.reload');await wait(q('.audit-card')+' && '+q('#case-list')+'.dataset.density==="expanded"','remembered board density');
  await evaluate(q('#desk-filters summary')+'.click();'+q('#desk-density')+'.click();'+q('#desk-filters summary')+'.click()');
  async function search(query) {
    await evaluate(q('#quick-query')+'.value='+JSON.stringify(query)+';'+q('#quick-query')+'.dispatchEvent(new Event("input"))');
  }
  await key(call,'k',2); await wait(q('#quick-dialog')+'.open','command palette');
  await search('进度');await key(call,'Enter');await wait('state.filter==="active"','processing queue');
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev=9'});
  await wait(q('.performance-overview')+' && state.bundle.rev===9','watermarked historical evidence');
  for (const width of [1440,390,320]) {
    await viewport(call,width);await evaluate('scrollTo(0,0);'+q('#quick-open')+'.click()');await wait(q('#quick-dialog')+'.open','open via pointer');
    await search('首款');await wait(q('#quick-results [role=option]')+' && '+q('#quick-scope')+'.innerText.includes("R9")','search issued findings');
    if (width!==320) await picture(call,evaluate,'#quick-dialog','quick-find-'+width);
    await search('不存在的项目xyz');assert.ok(await evaluate('!'+q('#quick-empty')+'.hidden && !'+q('#quick-query')+'.hasAttribute("aria-activedescendant")'));
    await search('H05');await key(call,'End');await key(call,'Enter');
    await wait('document.activeElement?.dataset.finding?.startsWith("H05-")','opened issued finding');
  }
  await evaluate(q('#quick-open')+'.click()');await search('采购合同.pdf');await key(call,'Enter');
  await wait(q('#page-dialog')+'.open','opened original');await key(call,'k',2);
  assert.equal(await evaluate(q('#quick-dialog')+'.open'),false);await key(call,'Escape');
  console.log('PASS · workspace quick navigation, compact cards, selected revision, keyboard and three widths');
}
