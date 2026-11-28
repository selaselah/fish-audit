import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {inspect,size} from './review-screen.mjs';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const all=s=>'[...document.querySelectorAll('+JSON.stringify(s)+')]';
export async function checkPaymentProof(ctx,id) {
  const {root,call,evaluate,wait}=ctx;
  async function get(path) {const response=await fetch(root+path);assert.ok(response.ok);return response.json();}
  const detail=id && await get('/api/cases/'+id);
  if (id) assert.ok(detail.title.startsWith('合成演练 · '));
  const sample=!id && await get('/assets/payment-execution-notice.json');
  const rev=detail?.rev || sample.rev;
  const report=id && (await get('/api/cases/'+id+'/reports/'+rev)).report;
  const findings=report?.findings.filter(f=>f.execution_basis) || [];
  const f=findings.find(f=>f.execution_basis.state==='conflict') || findings[0];
  const panel=id?'#payment-proof':'#public-payment-proof';
  const expected=f?.execution_basis.state || sample.state;
  const path=id?'/workpaper/'+id+'?rev='+rev+'&view=payment-proof&receipt='+f.id:'/?scene=payment-proof#workflow';
  const source=f?report.graph.payment_execution_sources.rows.filter(r=>r.unit===f.execution_basis.unit):sample.document.lines;
  const returned=expected==='return_noted';
  const desired=source.filter(r=>(returned?['status','return_notice']:expected==='conflict'?['status','limit']:['request','pending_status']).includes(r.kind));
  assert.equal(desired.length,2);
  if (sample) {
    for (const [url,digest] of [[sample.document.pdf,sample.document.source_sha256],[sample.document.image,sample.document.page_sha256]]) {
      const response=await fetch(root+url);assert.ok(response.ok);
      assert.equal(createHash('sha256').update(Buffer.from(await response.arrayBuffer())).digest('hex'),digest);
    }
  }
  await call('Page.navigate',{url:root+path});
  await wait(q(panel)+'?.getClientRects().length','payment source panel');
  assert.equal(await evaluate(q(panel)+'.dataset.state'),expected);
  assert.ok(await evaluate(q(panel)+'.dataset.outOfStage!=="true"'));
  if (id) {
    const phaseRef=await evaluate(q(panel)+'.dataset.clause');
    assert.equal(phaseRef,f.stage?.clause_ref || '');
    assert.ok(await evaluate('!document.querySelector("#signer-timing")'));
    if (returned) {
      const row=desired.find(r=>r.kind==='return_notice'), ref=JSON.stringify(row.id);
      const quote=await evaluate('(()=>{const report=state.bundle.report,f=report.findings.find(x=>x.id==='+JSON.stringify(f.id)+');'+
        'const link=citation('+ref+',f);link.click();return link.textContent})()');
      assert.equal(quote,row.quote);
      await wait(q('#page-dialog')+'.open && '+q('.evidence-row.located')+'?.dataset.sourceRef==='+ref,'finding links directly to its bank note');
      await evaluate(q('#page-dialog [data-close]')+'.click()');
      assert.equal(await evaluate('PaymentProof.citation(state.bundle.report,'+ref+',state.bundle.report.findings.find(x=>x.rule==="H02"))===null'),true);
    }
    for (const mutation of [
      "r.graph.edges=r.graph.edges.filter(e=>!(e.type==='payment_execution_source' && e.to===row.id))",
      "r.graph.edges=r.graph.edges.filter(e=>!(e.type==='supports_result' && e.from===row.id))",
      "r.graph.gaps.push({doc:row.doc,page:row.page,quality:'partial'})",
      "delete r.calls.pages.find(c=>c.doc===row.doc && c.page===row.page).payment_execution_rects[row.line]",
      ...(returned?["r.calls.expert.input.payment_return_sources=r.calls.expert.input.payment_return_sources.filter(s=>s.id!==row.id)"]:[])
    ]) {
      const role=returned?'return_notice':expected==='conflict'?'limit':'request';
      const changed=await evaluate('(()=>{const r=structuredClone(state.bundle.report),row=r.graph.payment_execution_sources.rows.find(s=>s.kind==='+JSON.stringify(role)+');'+mutation+';return PaymentProof.panel(r).dataset.state})()');
      assert.equal(changed,'unverified');
    }
  }
  if (expected==='conflict') {
    const selected=await evaluate(`(()=>{
      const source={line:1,clear:true,rects:[[0,0,1,1]]};
      const rows=[{...source,kind:"status",pageImage:"first",quote:"交易状态：交易成功"},
        {...source,kind:"limit",pageImage:"second",quote:"示例",explicit:false},
        {...source,kind:"status",pageImage:"second",quote:"交易状态：交易成功"},
        {...source,kind:"limit",pageImage:"second",quote:"实际限定",explicit:true}];
      const p=PaymentProofCard.pairs(rows,"conflict");return [p.left[0].pageImage,p.right[0].quote];
    })()`);
    assert.deepEqual(selected,['second','实际限定']);
  }
  const pairs=panel+' .debit-pair', toggle=panel+' .debit-modes button';
  for (const w of [320,360,390,768,1024,1440]) {
    await size(ctx,w);
    if (id && w<650) {
      const tools=panel+' .debit-controls';
      await evaluate('scrollTo({top:0,behavior:"instant"})');
      await wait(q(tools+' > #walk-launch')+'===null','other sections keep their own feedback button');
      await evaluate(q(panel)+'.scrollIntoView({block:"center",behavior:"instant"})');
      await wait(q(tools+' > #walk-launch')+'!=null','mobile feedback toolbar');
      const edges=await evaluate('(()=>{const bar='+q(tools)+'.getBoundingClientRect();return [bar.left,bar.right-innerWidth,bar.bottom-innerHeight]})()');
      assert.ok(edges.every(value=>Math.abs(value)<=1),'mobile toolbar offsets at '+w+'px: '+edges.join(', '));
      for (const selector of [tools+' > #walk-launch',toggle,toggle+':last-child']) {
        assert.ok(await evaluate('(()=>{const el='+q(selector)+',r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))})()'));
      }
    }
    await wait(all(pairs+' .debit-strip :is(img,canvas)')+'.length===2','two original crops');
    await wait(q(panel+' .debit-map img')+'?.naturalWidth>0','genuine page miniature');
    assert.equal(await evaluate(all(panel+' .debit-map .debit-mark')+'.length'),2);
    assert.deepEqual(await evaluate(all(pairs+' blockquote')+'.map(n=>n.textContent)'),desired.map(r=>r.quote));
    assert.ok(await evaluate(q(panel)+'.scrollWidth<='+q(panel)+'.clientWidth+1'));
    await inspect(ctx,w,panel,'payment-proof-'+(id?expected:'public'));
    await evaluate(all(toggle)+'[1].focus()');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    assert.equal(await evaluate(q(panel)+'.dataset.mode'),'text');
    assert.equal(await evaluate(q(pairs+' .debit-strip')+'.getClientRects().length'),0);
    for (const [i,row] of desired.entries()) {
      const trigger=all(pairs+' .debit-open')+'['+i+']';
      await evaluate(trigger+'.focus()');
      assert.equal(await evaluate(q(panel+' .debit-map')+'.dataset.row'),row.id || row.ref);
      await evaluate(trigger+'.click()');
      if (id) {
        await wait(q('#page-dialog')+'.open && '+q('.evidence-row.located')+'?.textContent.includes('+JSON.stringify(row.quote)+')','correct source text');
        assert.equal(await evaluate(q('.evidence-row.located')+'.dataset.gapLine'),String(row.line));
        assert.equal(await evaluate(q('.evidence-row.located')+'.dataset.sourceRef'),row.id);
        await wait(q('.source-plane svg rect')+'!=null','physical page highlight');
        assert.ok(await evaluate(q('.source-tools a')+'.href.endsWith("?rev='+rev+'")'));
        await evaluate(q('#page-dialog [data-close]')+'.click()');
      } else {
        await wait(q('#sample-review')+'.open && '+q('#sample-review canvas')+'?.dataset.fact==='+JSON.stringify(row.ref),'pinned public page');
        await evaluate(q('#sample-review form button')+'.click()');
      }
      await wait('document.activeElement==='+trigger,'restore focus to original-page control');
    }
    await evaluate(all(toggle)+'[0].click()');
    if (id && f.stage && findings.length===1) {
      const other=report.findings.find(c=>c.rule==='H04' && c.stage.clause_ref!==f.stage.clause_ref);
      await evaluate(q('#phase-choice-'+other.id)+'.click()');
      assert.equal(await evaluate(q(panel)+'.dataset.outOfStage'),'true');
      assert.equal(await evaluate(q(pairs)+'.getClientRects().length'),0);
      await evaluate(q(panel+' .debit-empty button')+'.click()');
      assert.equal(await evaluate(q(panel)+'.dataset.outOfStage'),'false');
    }
  }
  if (id) {
    if (findings.length>1) {
      const other=findings.find(x=>x!==f);
      const chooser=q(panel+' .debit-picker');
      await evaluate(chooser+'.value='+JSON.stringify(other.id)+';'+chooser+'.dispatchEvent(new Event("change"))');
      assert.equal(await evaluate(q(panel)+'.dataset.state'),other.execution_basis.state);
      const own=report.graph.payment_execution_sources.rows.filter(r=>r.unit===other.execution_basis.unit);
      assert.equal(await evaluate('import("/assets/walkthrough-context.js").then(m=>m.captureContext(null).params.receipt)'),other.id);
      const quotes=await evaluate(all(pairs+' blockquote')+'.map(q=>q.textContent)');
      assert.ok(quotes.length>0 && quotes.every(s=>own.some(row=>row.quote===s)));
      assert.equal(await evaluate(q(panel)+'.dataset.clause'),other.stage?.clause_ref || '');
      const trigger=q(pairs+' .debit-open');
      await evaluate(trigger+'.click()');
      await wait(q('#page-dialog')+'.open && '+q('.source-tools a')+'?.href.includes("/documents/'+own[0].doc+'/")','selected document is scoped to its own file');
      await evaluate(q('#page-dialog [data-close]')+'.click()');
    }
    await call('Page.navigate',{url:root+path.replace(/receipt=H05-\d+$/,'receipt=H05-99999')});
    await wait(q(panel)+'?.dataset.invalidReceipt==="true"','unavailable payment remains distinct');
    assert.equal(await evaluate(q(pairs)+'.getClientRects().length'),0);
  }
  console.log('PASS · '+(id?'固定底稿':'公开水印案例')+' R'+rev+' · '+expected+' · 原行/文字、键盘、返回焦点与六档屏宽');
}
