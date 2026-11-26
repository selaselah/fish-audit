import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {accessibility,browserInput,inspect,size} from './review-screen.mjs';

const scene='/?scene=batch-standards';
const panel='#standard-event-body';
const q=selector=>'document.querySelector('+JSON.stringify(selector)+')';
const listed=selector=>'Array.from(document.querySelectorAll('+JSON.stringify(selector)+'))';
const widths=[320,360,390,768,1024,1440];

async function openScene(ctx,suffix='') {
  await ctx.call('Page.navigate',{url:ctx.root+scene+suffix+'#workflow'});
  await ctx.wait(q(panel)+' && !'+q('#inspection-standards')+'.hidden','published batch and version');
}

async function select(ctx,selector,value) {
  const field=q(selector);
  await ctx.evaluate(field+'.value='+JSON.stringify(value)+';'+field+'.dispatchEvent(new Event("change"))');
}

async function issue(ctx,revision,batch) {
  assert.deepEqual(await ctx.evaluate('['+q(panel)+'.dataset.edition,'+q(panel)+'.dataset.event,'+
    'new URLSearchParams(location.search).get("edition"),new URLSearchParams(location.search).get("batch"),'+
    q('.standard-events [aria-selected=true]')+'.dataset.event]'),[revision,batch,revision,batch,batch]);
}

async function openSource(ctx,selector,ref,line,slug,revision) {
  const anchor=q(panel+' '+selector),dialog=q('#sample-review');
  assert.equal(await ctx.evaluate(anchor+'.dataset.fact'),ref);
  await ctx.evaluate(anchor+'.click()');
  await ctx.wait(dialog+'.open && '+q('#sample-review canvas')+'.dataset.fact==='+JSON.stringify(ref),'published source '+ref);
  assert.deepEqual(await ctx.evaluate('['+q('#sample-location')+'.textContent,'+q('#sample-review .sample-records a')+
    '.pathname,'+q('#sample-review .sample-review-head span')+'.textContent,document.activeElement.dataset.ref]'),
    ['第 1 页 · 第 '+line+' 行','/showcase/batch-version-'+slug+'.pdf','合成采购 · R'+revision,ref]);
  if (ref==='d02/p1/f10') await accessibility(ctx,'physical second-batch acceptance row');
  await browserInput(ctx).key('Escape');
  await ctx.wait('!'+dialog+'.open && document.activeElement==='+anchor,'return to '+ref);
}

async function checkBatch(ctx,revision,batch) {
  await issue(ctx,revision,batch);
  const pending=revision==='15', first=batch==='1';
  const chosen=pending?[]:[first?'original':'applied'];
  assert.deepEqual(await ctx.evaluate(listed(panel+' .chosen-limit')+'.map(e=>e.dataset.kind)'),chosen);
  assert.deepEqual(await ctx.evaluate(listed(panel+' .standard-tick strong')+'.map(e=>e.textContent)'),['≤ 4 °C','≤ 2 °C','3 °C']);
  const values=await ctx.evaluate(listed(panel+' .standard-tick')+'.map(a=>a.getBoundingClientRect().toJSON())');
  const [original,revised,reading]=values.map(box=>box.left+box.width/2);
  assert.ok(original>reading && reading>revised && Math.abs((original+revised)/2-reading)<1,'proportional scale for 2, 3 and 4 °C');
  assert.ok(values[1].right<values[0].left && values.every(box=>box.height>=44),'separate touch targets for the source lines');
  assert.ok(await ctx.evaluate(q('.standard-decision')+'.getBoundingClientRect().height>=44'));
  assert.equal(await ctx.evaluate(q(panel+' .standard-decision')+'.textContent'),
    pending?'适用标准待核':first?'本版采用原合同':'本版采用补充协议');
  assert.equal(await ctx.evaluate(q('.standard-installment .standard-status')+'.textContent'),
    '付款条件 · '+(pending?'证据不足':first?'相符':'风险'));
  assert.equal(await ctx.evaluate(q('.standard-stage strong')+'.textContent'),(first?'第二期':'第三期')+' · 35%');
  await ctx.wait(q('.standard-printed img')+'?.naturalWidth>0','original printed inspection basis');
  assert.equal(await ctx.evaluate(q('.standard-printed img')+'.alt'),'检验依据：柜温不高于4℃');
}

async function verifyFiles(root,index) {
  assert.equal(index.case_id,'7e3e44b82d394ed4a9324a0d3be0f8b7');
  assert.deepEqual(index.editions.map(e=>e.rev),[15,14]);
  assert.equal(index.docs.length,4);
  for (const doc of index.docs) {
    for (const [path,digest] of [[doc.pdf,doc.source_sha256],[doc.image,doc.page_sha256]]) {
      const response=await fetch(root+path);
      assert.ok(response.ok,path);
      const data=Buffer.from(await response.arrayBuffer());
      assert.equal(createHash('sha256').update(data).digest('hex'),digest,path);
    }
  }
}

async function verifyRecovery(ctx) {
  const retry=q('#inspection-standards .standard-retry');
  await ctx.call('Network.enable');
  await ctx.call('Network.setCacheDisabled',{cacheDisabled:true});
  await ctx.call('Network.setBlockedURLs',{urls:['*batch-standard-versions.json*']});
  await ctx.call('Page.navigate',{url:ctx.root+scene+'#workflow'});
  await ctx.wait(retry,'retry when index is unavailable');
  assert.deepEqual(await ctx.evaluate(listed('.public-standard-fallback a')+'.map(a=>a.pathname)'),
    ['/showcase/batch-version-addendum.pdf','/showcase/batch-version-second.pdf']);
  assert.equal(await ctx.evaluate('Boolean('+q(panel)+')'),false);
  await ctx.call('Network.setBlockedURLs',{urls:[]});
  // A mismatched manifest digest must preserve direct originals and show no decision.
  const slot=q('#inspection-standards');
  await ctx.evaluate(slot+'.dataset.verified='+slot+'.dataset.integrity;'+slot+'.dataset.integrity="sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="');
  await ctx.evaluate(retry+'.click()');
  await ctx.wait(slot+'.getAttribute("aria-busy")==="false"','mismatched index handled');
  assert.equal(await ctx.evaluate('Boolean('+q(panel)+')'),false);
  await ctx.evaluate(slot+'.dataset.integrity='+slot+'.dataset.verified;'+retry+'.focus();'+retry+'.click()');
  await ctx.wait(q(panel)+'?.dataset.edition==="15"','restore published version');
  assert.equal(await ctx.evaluate('document.activeElement.id'),'standard-edition');
}

export async function checkPublicBatchStandards(ctx) {
  const {root,call,evaluate,wait}=ctx;
  const response=await fetch(root+'/assets/batch-standard-versions.json');
  assert.equal(response.status,200);
  const bytes=Buffer.from(await response.arrayBuffer());
  await verifyFiles(root,JSON.parse(bytes));
  for (const width of widths) {
    await size(ctx,width);
    await openScene(ctx);
    assert.equal(await evaluate(q('#inspection-standards')+'.dataset.integrity'),'sha256-'+createHash('sha256').update(bytes).digest('base64'));
    await checkBatch(ctx,'15','2');
    await evaluate(q('.standard-decision')+'.click()');
    assert.match(await evaluate(q('#standard-decision-detail')+'.innerText'),/原合同生效依据.*签章原页/);
    assert.deepEqual(await evaluate('['+q('.standard-method small')+'.textContent,'+q('.standard-method a')+'.pathname]'),
      ['规则 2026.11.27.04','/assets/batch-standard-versions.json']);
    await evaluate(q('.standard-decision')+'.click()');
    const {key,tap}=browserInput(ctx);
    if (width===390 || width===1440) {
      await inspect(ctx,width,'#inspection-standards','public-standard-pending');
      await openSource(ctx,'.standard-date','d02/p1/f6',7,'second',15);
      await openSource(ctx,'.standard-printed','d02/p1/f10',11,'second',15);
    }
    await evaluate(q('#standard-event-2')+'.focus()');
    await key('Home');
    await checkBatch(ctx,'15','1');
    assert.equal(await evaluate('document.activeElement.id'),'standard-event-1');
    await key('ArrowRight');
    await issue(ctx,'15','change');
    assert.equal(await evaluate(q('.standard-decision')+'.textContent'),'生效日期待核');
    assert.deepEqual(await evaluate(listed('.standard-events time')+'.map(t=>t.dateTime)'),['2026-09-10','2026-09-12','2026-09-20']);
    await evaluate(q('.standard-details summary')+'.click()');
    if (width===390 || width===1440) {
      await accessibility(ctx,'printed amendment dates at '+width);
      for (const [selector,ref,line] of [['.standard-limit','d05/p1/f8',9],['.standard-limit:last-child','d05/p1/f9',10],
        ['.standard-source-row','d05/p1/f10',11],['[data-fact="d05/p1/f11"]','d05/p1/f11',12],
        ['[data-fact="d05/p1/f12"]','d05/p1/f12',13],['[data-fact="d05/p1/f13"]','d05/p1/f13',14]]) {
        await openSource(ctx,selector,ref,line,'addendum',15);
      }
    }
    await select(ctx,'#standard-edition','14');
    await issue(ctx,'14','change');
    assert.equal(await evaluate(q('.standard-decision')+'.textContent'),'本版生效日 2026-09-12');
    await evaluate(q('.standard-decision')+'.click()');
    assert.equal(await evaluate(q('.standard-method small')+'.innerText'),'规则 2026.11.25.20');
    if (width<600) {
      await call('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:1});
      await tap(q('#standard-event-2'));
      await call('Emulation.setTouchEmulationEnabled',{enabled:false});
    } else {
      await evaluate(q('#standard-event-change')+'.focus()');
      await key('End');
    }
    await wait(q(panel)+'.dataset.event==="2"','second batch selected');
    await checkBatch(ctx,'14','2');
    if (width===390 || width===1440) {
      await inspect(ctx,width,'#inspection-standards','public-standard-history');
      await openSource(ctx,'[data-kind=reading]','d02/p1/f11',12,'second',14);
      await openSource(ctx,'[data-kind=original]','d04/p1/f13',14,'contract',14);
      await openSource(ctx,'[data-kind=applied]','d05/p1/f9',10,'addendum',14);
      await openSource(ctx,'.standard-stage','d04/p1/f20',21,'contract',14);
    }
    await evaluate(q('#standard-event-1')+'.click()');
    await checkBatch(ctx,'14','1');
    if (width===390 || width===1440) {
      await openSource(ctx,'.standard-printed','d01/p1/f10',11,'first',14);
      await openSource(ctx,'.standard-stage','d04/p1/f19',20,'contract',14);
    }
    assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),true);
    assert.equal(await evaluate('performance.getEntriesByType("resource").some(e=>new URL(e.name).pathname.startsWith("/api/"))'),false);
  }
  await openScene(ctx,'&edition=14&batch=1');
  await checkBatch(ctx,'14','1');
  await select(ctx,'#inspection-example','readings');
  assert.deepEqual(await evaluate('["edition","batch"].map(k=>new URLSearchParams(location.search).has(k))'),[false,false]);
  await select(ctx,'#inspection-example','standards');
  await issue(ctx,'14','1');
  await openScene(ctx,'&edition=999&batch=9');
  await checkBatch(ctx,'15','2');
  await verifyRecovery(ctx);
  console.log('PASS · two fixed workpapers, two batches and an amendment, physical rows, payment states, source fallback and six viewport widths');
}
