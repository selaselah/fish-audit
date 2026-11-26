import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {inspect,size} from './review-screen.mjs';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const all=s=>'[...document.querySelectorAll('+JSON.stringify(s)+')]';
const widths=[1440,1024,768,390,360,320];

export async function checkPaymentAcceptance(ctx,id,revision) {
  const {root,call,evaluate,wait}=ctx;
  async function get(path) {const res=await fetch(root+path);assert.ok(res.ok);return res.json();}
  const detail=id && await get('/api/cases/'+id);
  if (detail) assert.ok(detail.title.startsWith('合成演练 · '));
  const rev=revision || detail?.rev;
  const report=id && (await get('/api/cases/'+id+'/reports/'+rev)).report;
  const sample=!id && await get('/assets/batch-payment-reference.json');
  const panel=id?'#payment-acceptance':'#public-payment-acceptance';
  const item=q(panel);
  await call('Page.navigate',{url:root+(id?'/workpaper/'+id+'?rev='+rev+'&view=payment-acceptance':'/?scene=payment-acceptance#workflow')});
  if (report && !report.policy.payment_acceptance) {
    await wait('state.bundle?.rev==='+rev,'historical report');
    assert.equal(await evaluate(item),null);return;
  }
  await wait(item+'?.getClientRects().length','reference comparison');
  const checks=report?.findings.filter(f=>f.payment_acceptance);
  const expected=checks?.map(f=>f.payment_acceptance.state) || sample.payments.map(r=>r.state);
  const wrong=expected.indexOf('other_batch'),matched=expected.indexOf('matched');
  assert.equal(await evaluate(item+'.dataset.referenceState'),expected[wrong<0?0:wrong]);
  if (sample) {
    for (const doc of sample.documents) {
      for (const [path,digest] of [[doc.pdf,doc.source_sha256],[doc.image,doc.page_sha256]]) {
        const result=await fetch(root+path);assert.ok(result.ok);
        assert.equal(createHash('sha256').update(Buffer.from(await result.arrayBuffer())).digest('hex'),digest);
      }
    }
  }
  if (id && wrong>=0) {
    const forged=await evaluate(`(()=>{const r=structuredClone(state.bundle.report),f=r.findings.find(f=>f.payment_acceptance?.state==='other_batch');const ref=f.payment_acceptance.citations[0];r.graph.edges=r.graph.edges.filter(e=>!(e.type==='payment_acceptance_source' && e.to===ref));const x=PaymentAcceptance.panel(r);x.dispatchEvent(new CustomEvent('select-reference',{detail:f.id}));return x.dataset.referenceState})()`);
    assert.equal(forged,'unverified');
  }
  const tabs=all(panel+' [role=tab]');
  for (const width of widths) {
    await size(ctx,width);
    if (wrong>=0 && expected.length>1) await evaluate(tabs+'['+wrong+'].click()');
    if (wrong>=0) {
      await evaluate(q(panel+' [data-mode=number]')+'?.click()');
      const mark=all(panel+' .payment-reference-number mark'),toggle=q(panel+' [role=switch]');
      await evaluate('if(!'+toggle+'.checked) '+toggle+'.click()');
      assert.equal(await evaluate(mark+'.length'),2);await evaluate(toggle+'.click()');assert.equal(await evaluate(mark+'.length'),0);
      await evaluate(toggle+'.click()');
    }
    if ([1440,390].includes(width)) {
      await inspect(ctx,width,panel,'bank-'+(id?'workpaper':'public')+'-'+expected.join('-'));
      const source=q(panel+' .payment-reference-source:is(button,a)');
      if (await evaluate('!!'+source)) {
        await evaluate(source+'.focus();'+source+'.click()');
        if (id) {
          const row=report.graph.payment_acceptance_sources.rows.find(r=>r.id===checks[wrong<0?0:wrong].payment_acceptance.citations[0]);
          await wait(q('#page-dialog')+'.open && '+q('#page-dialog .located')+'?.textContent.includes('+JSON.stringify(row.quote)+')','specific cited original line');
          await evaluate(q('#page-dialog [data-close]')+'.click()');
        } else {
          const ref=sample.payments[wrong].bank,doc=sample.documents.find(d=>d.lines.some(r=>r.ref===ref));
          await wait(q('#sample-review')+'.open && '+q('#sample-review canvas')+'.dataset.fact==='+JSON.stringify(ref),'same archived sample row');
          assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),doc.pdf);
          await evaluate(q('#sample-review form button')+'.click()');
        }
        await wait('document.activeElement==='+source,'focus returns to source');
      }
      if (await evaluate('!!'+q(panel+' [data-mode=source]'))) {
        await evaluate(q(panel+' [data-mode=source]')+'.click()');
        await wait(q(panel+' .payment-reference-strip :is(canvas,img)')+'!=null','readable original crop');
        await inspect(ctx,width,panel,'bank-lines-'+(id?'workpaper':'public')+'-'+expected.join('-'));
        await evaluate(q(panel+' [data-mode=number]')+'.click()');
      }
    }
    if (wrong>=0 && matched>=0) {
      await evaluate(tabs+'['+wrong+'].focus()');
      await call('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight'});
      assert.equal(await evaluate(item+'.dataset.referenceState'),'matched');
      assert.equal(await evaluate(all(panel+' .payment-reference-number mark')+'.length'),0);
      assert.ok(await evaluate(item+'.textContent.includes("35,000.00")'));
    }
    await evaluate(q(panel+' details')+'.open=true');
    assert.ok(await evaluate(q(panel+' details')+'.textContent.length')>10);await evaluate(q(panel+' details')+'.open=false');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'));
  }
  if (id && matched>=0 && expected.length>1) {
    const target=checks[matched].id;
    if (rev===detail.rev) {
      await call('Page.navigate',{url:root+'/app#desk'});
      const search=q('#case-search'),peek=q('[data-preview-case="'+id+'"]');
      await wait(search+'?.getClientRects().length && Desk.fingerprint','normal desk');
      await evaluate(search+'.value='+JSON.stringify(detail.title)+';'+search+'.dispatchEvent(new Event("input"))');
      await wait(peek+'?.getClientRects().length','watermarked task in current queue');
      await evaluate(peek+'.click()');
      const source=q('#case-preview a[href*="view=payment-acceptance"][href*="receipt="]');
      await wait(source+'?.checkVisibility()','pinned receipt from work queue');
      const candidate=await evaluate(source+'.dataset.findingId');
      await evaluate(source+'.click()');
      await wait(item+'?.checkVisibility() && '+item+'.dataset.payment==='+JSON.stringify(candidate),'queue opens that receipt');
    }
    await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev='+rev+'&view=payment-acceptance&receipt='+target});
    await wait(item+'?.dataset.payment==='+JSON.stringify(target),'bookmark selects this transfer');
    const first=q('.phase-choice');
    await evaluate(first+'.click()');assert.equal(await evaluate(q(panel+' .payment-reference-empty')+'.hidden'),false);
    await evaluate(q(panel+' .payment-reference-empty button')+'.click()');
    assert.equal(await evaluate(item+'.dataset.payment'),target);
    assert.equal(await evaluate(q(panel+' .payment-reference-empty')+'.hidden'),true);
  }
  console.log('PASS · '+(id?'固定版 R'+rev:'首页水印演练')+' · '+expected.join(' / ')+' · 6 种屏宽');
}

export async function checkPreviewQueue(ctx) {
  const {root,call,evaluate,wait}=ctx;
  await call('Page.navigate',{url:root+'/app#desk'});
  await wait('typeof Desk!=="undefined" && Desk.fingerprint && '+q('[data-preview-case]'),'visible desk');
  const search=q('#case-search'),drawer=q('#case-preview'),next=q('#preview-next'),prev=q('#preview-prev');
  await evaluate(search+'.value="合成演练";'+search+'.dispatchEvent(new Event("input"))');
  await wait('decodeURIComponent(Desk.queryKey).includes("合成演练") && '+q('[data-preview-case]')+'!=null','synthetic queue');
  for (const [view,width] of [['board',1440],['list',390]]) {
    await size(ctx,width);
    await evaluate(q('[data-desk-view='+view+']')+'.click()');
    const prefix=view==='board'?'.verdict-lane':'#case-list';
    const prep='(()=>{const scope=[...document.querySelectorAll('+JSON.stringify(prefix)+')].find(e=>e.checkVisibility() && e.querySelectorAll("[data-preview-case]").length>=2);return [...scope.querySelectorAll("[data-preview-case]")]';
    await wait(q(view==='board'?'.verdict-lane':'.ledger-row:not(.ledger-header)')+'!==null','queue in selected view');
    const ids=await evaluate(prep+'.map(b=>b.dataset.previewCase)})()');
    await evaluate(prep+'[0].click()})()');
    await wait(drawer+'.open && '+prev+'.disabled && !'+next+'.disabled','bounded sequence');
    await evaluate(next+'.click()');
    await wait(drawer+'.dataset.caseId==='+JSON.stringify(ids[1])+' && '+q('#preview-action a')+'?.href.includes('+JSON.stringify(ids[1])+')','next case only');
    await inspect(ctx,width,'#case-preview','queue-preview');
    await evaluate(next+'.dispatchEvent(new KeyboardEvent("keydown",{key:"ArrowUp",altKey:true,bubbles:true,cancelable:true}))');
    await wait(drawer+'.dataset.caseId==='+JSON.stringify(ids[0]),'previous case by shortcut');
    await evaluate(next+'.click()');
    await wait(q('#preview-action a')+'?.href.includes('+JSON.stringify(ids[1])+')','updated source');
    await evaluate(q('#case-preview [data-close]')+'.click()');
    await wait('document.activeElement?.dataset.previewCase==='+JSON.stringify(ids[1]),'focus on last reviewed case');
  }
  console.log('PASS · 建议看板与台账连续速览、快捷键、返回焦点');
}
