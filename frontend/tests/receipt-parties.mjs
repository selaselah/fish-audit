import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

export async function checkReceiptParties(ctx,cid,requestedRev) {
  const {root,call,evaluate,wait}=ctx, {click}=browserInput(ctx), q=s=>'document.querySelector('+JSON.stringify(s)+')';
  const base=root+'/api/cases/'+cid, task=await (await fetch(base)).json();
  assert.equal(task.title,'合成演练 · 出具委托书与代理签约同日');
  const rev=Number(requestedRev || task.rev), {report}=await (await fetch(base+'/reports/'+rev)).json();
  const payment=report.findings.find(f=>f.rule==='H05'), row=report.graph.bank_party_readings?.rows[0];
  const url=root+'/workpaper/'+cid+'?rev='+rev+'&view=payment-checks&stage='+payment.id;
  await call('Page.navigate',{url});
  await wait(q('#performance-index[open] .scope-check[aria-pressed=true]')+'?.dataset.check==='+JSON.stringify(payment.id),'payment selected');
  const id='#performance-index .bank-role-reading', card=q(id);
  if (!row) {
    assert.equal(await evaluate(card),null);
    console.log('PASS R'+rev+' archived procedure without bank role correction');return;
  }
  assert.equal(row.fact,'d04/p1/f3');assert.equal(payment.status,'missing');
  assert.equal(payment.stage?.name,row.state==='corrected'?'第二期':undefined);
  await wait(card+'?.dataset.state==='+JSON.stringify(row.state),'issued bank role comparison');
  const bank=q(id+' [data-bank-role-source="'+row.fact+'"]'), contract=q(id+' [data-bank-role-source="d03/p1/f3"]');
  const editor=q(id+' [data-bank-role-edit]');
  const editable=rev===task.rev && task.status==='ready' && row.state==='pending';
  assert.equal(await evaluate('Boolean('+editor+')'),editable);
  const defaultContext=await evaluate("import('/assets/walkthrough-context.js').then(m=>m.captureContext(document.getElementById('performance-index')))");
  assert.deepEqual(defaultContext.params,{view:'payment-checks',stage:payment.id});
  for (const width of [1440,1024,768,390,360,320]) {
    await size(ctx,width);
    assert.ok(await evaluate(card+'.scrollWidth<='+card+'.clientWidth+1'),'card fits '+width);
    await inspect(ctx,width,id,'receipt-party-'+row.state);
    if (![1440,390].includes(width)) continue;
    for (const [button,ref] of [[bank,row.fact],[contract,'d03/p1/f3']]) {
      await click(button);
      await wait(q('#page-dialog[open] .evidence-row.located')+'?.dataset.fact==='+JSON.stringify(ref),'correct document field');
      await wait(q('.source-plane svg rect')+'!=null','printed line overlay');
      await click(q('#page-dialog [data-close]'));
      await wait('document.activeElement==='+button,'restore selected source');
    }
    if (editable) {
      await click(editor);
      await wait(q('#amend-dialog[open]')+' && !'+q('#amend-submit')+'.disabled && '+q('#amend-marks rect'),'original reviewed before correction');
      assert.equal(await evaluate(q('#amend-field')+'.value'),'payer');
      assert.equal(await evaluate(q('#amend-quote')+'.value'),row.quote);
      assert.equal(await evaluate(q('#amend-value')+'.value'),row.value);
      assert.ok((await evaluate(q('#amend-context')+'.textContent')).includes('原模型字段 采购方'));
      if (width===390) {
        const preview=q('.bank-role-preview canvas'), full=q('#amend-image'), toggle=q('.bank-role-preview button');
        await wait(preview+'?.getClientRects().length && '+preview+'.width>0','original row enlarged on mobile');
        assert.equal(await evaluate(full+'.getClientRects().length'),0);
        await click(toggle);assert.ok(await evaluate(full+'.getClientRects().length'));
        await click(toggle);assert.ok(await evaluate(preview+'.getClientRects().length'));
      }
      await inspect(ctx,width,'#amend-dialog','receipt-party-amend');
      await click(q('#amend-dialog [data-close]'));
      await wait(q('#performance-index[open] #walk-launch')+'?.getClientRects().length','feedback returns to the payment check after closing the editor');
    }
  }
  for (const change of ["r.calls.expert.input.procedures.find(p=>p.rule==='H05').bank_party_readings=[]",
    "r.graph.edges=r.graph.edges.filter(e=>!(e.type==='records' && e.to===row.fact))",
    "r.calls.pages.find(c=>c.doc===row.doc).check.input=[]","row.rects=[]","delete row.quote","row.quote='收款户名：无'"]) {
    const ok=await evaluate('(()=>{const r=structuredClone(state.bundle.report),f=r.findings.find(f=>f.rule==="H05"),row=r.graph.bank_party_readings.rows[0];'+change+';return Boolean(ReceiptParties.bind(r,f,row.id));})()');
    assert.equal(ok,false,change);
  }
  for (const [button,doc] of [[bank,'d04'],[contract,'d03']]) {
    await click(q('#walk-launch'));
    await wait(q('#walk-dialog[open]')+' && !'+q('#walk-save')+'.disabled','walkthrough ready');
    await click(q('#walk-pick'));await click(button);
    const context=await evaluate(`import('/assets/walkthrough-context.js').then(m=>m.captureContext(document.getElementById('performance-index'),${button}))`);
    assert.deepEqual([context.doc,context.page,context.line,context.rev,context.params.fact],[doc,1,4,rev,doc+'/p1/f3']);
    const quote=report.graph.facts.find(f=>f.id===context.params.fact).source_line.text;
    assert.equal(await evaluate(q('#walk-excerpt blockquote')+'.textContent'),quote);
    await click(q('#walk-close'));
  }
  console.log('PASS R'+rev,row.state,'bank and contract originals, true source focus, amendment availability, six widths');
}
