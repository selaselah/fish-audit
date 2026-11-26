import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {inspect,size} from './review-screen.mjs';

const q = s => 'document.querySelector('+JSON.stringify(s)+')';
const all = s => '[...document.querySelectorAll('+JSON.stringify(s)+')]';
export async function checkSignerTiming(ctx, id, revision) {
  const {root,call,evaluate,wait}=ctx;
  async function get(path) {const r=await fetch(root+path);assert.ok(r.ok);return r.json();}
  const sample = !id && await get('/assets/joint-signing.json');
  const detail = id && await get('/api/cases/'+id);
  if (detail) assert.ok(detail.title.startsWith('合成演练 · '));
  const rev = revision || detail?.rev || sample.rev;
  const paper = id && (await get('/api/cases/'+id+'/reports/'+rev)).report;
  const f = paper && paper.findings.find(f=>f.signer_timing);
  const model = f?.signer_timing || sample.payment, state=model.state;
  const expected = f ? paper.graph.acceptance_authority_sources.dates.filter(r=>f.signer_timing.rows.includes(r.id)).map(r=>r.quote) :
    sample.documents.at(-1).lines.filter(r=>r.label.endsWith('签认日期')).map(r=>r.quote);
  const panel=id?'#signer-timing':'#public-signer-timing';
  if (sample) for (const doc of sample.documents) for (const [url,hash] of [[doc.pdf,doc.source_sha256],[doc.image,doc.page_sha256]]) {
    const res=await fetch(root+url);assert.ok(res.ok);
    assert.equal(createHash('sha256').update(Buffer.from(await res.arrayBuffer())).digest('hex'),hash);
  }
  await call('Page.navigate',{url:root+(id?'/workpaper/'+id+'?rev='+rev+'&view=signer-timing&receipt='+f.id:'/?scene=signer-timing#workflow')});
  await wait(q(panel)+'?.getClientRects().length','visible signer timeline');
  assert.equal(await evaluate(q(panel)+'.dataset.state'),state);
  if (id) {
    const active=q('.phase-choice[aria-selected=true]');
    assert.ok(await evaluate(active+'.textContent.includes('+JSON.stringify(f.stage.name)+')'));
    const other=paper.findings.find(g=>g.rule==='H04' && g.stage?.clause_ref!==model.stage_ref);
    if (other) {
      await evaluate(q('#phase-choice-'+other.id)+'.click()');
      assert.equal(await evaluate(q(panel)+'.dataset.outOfStage'),'true');
      assert.ok(await evaluate(q(panel+' .signer-body')+'.getClientRects().length===0'));
      await evaluate(q(panel+' .signer-empty button')+'.click()');
      await wait(q(panel)+'.dataset.outOfStage==="false"','return to the paid installment');
      assert.ok(await evaluate(active+'.textContent.includes('+JSON.stringify(f.stage.name)+')'));
    }
  }
  if (id && ['before','same_day','after'].includes(state)) {
    const forged=await evaluate(`(()=>{const r=structuredClone(state.bundle.report), f=r.findings.find(f=>f.signer_timing);r.graph.edges=r.graph.edges.filter(e=>!(e.type==='signer_date_source' && e.to===f.signer_timing.rows[0]));return SignerEvidence.panel(r).dataset.state})()`);
    assert.equal(forged,'unverified');
  }
  for (const width of [1440,1024,768,390,360,320]) {
    await size(ctx,width);
    assert.equal(await evaluate(all(panel+' .signer-event')+'.length'),3);
    await evaluate(q(panel+' [data-kind=payment]')+'.click()');
    const stamp=await evaluate(q(panel+' [aria-pressed=true] time')+'?.dateTime');
    assert.equal(stamp,f?model.paid_on:model.events.find(e=>e.kind==='payment').day);
    await wait(q(panel+' .signer-strip :is(img,canvas)')+'!=null','original payment date excerpt');
    await wait(q(panel+' .signer-thumbnail img')+'?.naturalWidth>0','actual payment page thumbnail');
    assert.ok(await evaluate(all(panel+' .signer-thumbnail-mark')+'.length>0'));
    if (state==='same_day') {
      assert.equal(await evaluate(all(panel+' .signer-day-group .signer-event')+'.length'),2);
      assert.ok(await evaluate(q(panel+' .signer-day-group')+'.getAttribute("aria-label").includes("同日")'));
    }
    await inspect(ctx,width,panel,'signer-timing-'+(id?'paper':'public')+'-'+state);
    const signers=all(panel+' [data-kind=signer]');
    await evaluate(signers+'.at(-1).focus()');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Home',code:'Home'});
    assert.ok(await evaluate('document.activeElement==='+q(panel+' .signer-event')));
    for (const [i,quote] of expected.entries()) {
      await evaluate(signers+'['+i+'].click()');
      assert.equal(await evaluate(q(panel+' .signer-quote')+'.textContent'),quote);
      await wait(q(panel+' .signer-strip :is(img,canvas)')+'!=null','printed personal date excerpt');
      const trigger=q(panel+' .signer-preview .signer-original');
      await evaluate(trigger+'.focus();'+trigger+'.click()');
      if (id) {
        await wait(q('#page-dialog')+'.open && '+q('.evidence-row.located')+'?.textContent.includes('+JSON.stringify(quote)+')','archived source line');
        assert.ok(await evaluate(q('.source-tools a')+'.href.endsWith("?rev='+rev+'")'));
        await evaluate(q('#page-dialog [data-close]')+'.click()');
      } else {
        const row=sample.documents.at(-1).lines.find(r=>r.quote===quote);
        await wait(q('#sample-review')+'.open && '+q('#sample-review canvas')+'?.dataset.fact==='+JSON.stringify(row.ref),'watermarked row marked');
        await evaluate(q('#sample-review form button')+'.click()');
      }
      await wait('document.activeElement==='+trigger,'focus returns to original opener');
    }
    assert.equal(await evaluate(all(panel+' .signer-basis .signer-original')+'.length'),2);
  }
  if (sample) {
    const contract=await get('/assets/installment-originals.json');
    await evaluate(q('#payments')+'.scrollIntoView({behavior:"instant"})');
    await wait(all('.phase-original-clause img')+'.length===3','three original installment clauses');
    for (const [i,row] of contract.lines.entries()) {
      await evaluate(all('.phase-ledger .phase')+'['+i+'].open=true');
      const link=all('.phase-original-clause')+'['+i+']';
      await evaluate(link+'.focus();'+link+'.click()');
      await wait(q('#sample-review canvas')+'?.dataset.fact==='+JSON.stringify(row.ref),'printed installment source');
      assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),contract.pdf);
      await evaluate(q('#sample-review form button')+'.click()');
      await wait('document.activeElement==='+link,'return to the examined installment');
    }
  }
  console.log('PASS · '+(id?'固定版底稿':'产品首页')+' R'+rev+' · '+state+' · 逐人原件、回单、键盘及六种宽度');
}
