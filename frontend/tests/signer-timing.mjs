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
  const sources = f && paper.graph.acceptance_authority_sources;
  const expected = f ? model.required.flatMap(name=>{
    const day=sources.dates.find(r=>model.rows.includes(r.id) && r.name===name);
    const clock=sources.clock_rows?.find(r=>r.id===model.clock?.signers[name] && r.name===name && !r.disputed);
    const row=clock && (!day || !clock.day || clock.day===day.day) ? clock : day;
    return row ? [{name,quote:row.quote}] : [];
  }) : sample.documents.at(-1).lines.filter(r=>r.label.endsWith('签认日期'))
    .map(r=>({name:r.label.slice(0,-4),quote:r.quote}));
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
    if (model.transcriptions?.length) {
      for (const mutate of ["r.graph.edges=r.graph.edges.filter(e=>e.type!=='transcribed_signer_date')",
        "r.calls.expert.input.procedures.find(p=>p.joint_acceptance_timing).joint_acceptance_timing.dates.pop()",
        "t.required=t.required.slice(1)","r.calls.pages.find(p=>p.doc===t.receipt).signer_timing_rects={}"]) {
        const changed=await evaluate('(()=>{const r=structuredClone(state.bundle.report),t=r.findings.find(f=>f.signer_timing).signer_timing;'+mutate+';return SignerEvidence.panel(r).dataset.state})()');
        assert.equal(changed,'unverified');
      }
      const finalRow=paper.graph.acceptance_authority_sources.dates.find(r=>r.id===model.rows.at(-1));
      const cited=await evaluate('(()=>{const r=state.bundle.report,b=citation('+JSON.stringify(finalRow.id)+',r.findings.find(f=>f.signer_timing));b.click();return b.textContent})()');
      assert.equal(cited,finalRow.quote);
      await wait(q('#page-dialog')+'.open && '+q('.evidence-row.located')+'?.dataset.sourceRef==='+JSON.stringify(finalRow.id),'third signer date raw citation');
      await evaluate(q('#page-dialog [data-close]')+'.click()');
      assert.equal(await evaluate('SignerEvidence.citedRow(state.bundle.report,'+JSON.stringify(finalRow.id)+',state.bundle.report.findings.find(f=>f.rule==="H01"))'),null);
      const roster=await evaluate('(()=>{const r=state.bundle.report,h=r.findings.find(f=>f.rule==="H02");return AcceptanceRoster.bind(h,r)?.required})()');
      assert.deepEqual(roster,model.required);
      const details=panel+' .signer-candidates';
      await evaluate(q(details+' summary')+'.click()');
      const dates=paper.graph.acceptance_authority_sources.dates, joined=dates.find(r=>r.id===model.transcriptions[0]);
      assert.equal(await evaluate(q(details+' blockquote')+'.textContent'),joined.quote);
      assert.deepEqual(await evaluate(all(details+'[open] .signer-original')+'.map(b=>b.textContent)'),joined.printed_rows.map(ref=>dates.find(r=>r.id===ref).quote));
      await evaluate(q(details+' summary')+'.click()');
    }
  }
  for (const width of [1440,1024,768,390,360,320]) {
    await size(ctx,width);
    assert.equal(await evaluate(all(panel+' .signer-event')+'.length'),f?model.required.length+1:model.events.length);
    const bar='.signer-mobile-tools:not([hidden])';
    if (id && width<650) {
      await evaluate('scrollTo({top:0,behavior:"instant"})');
      await wait(q(bar)+'===null','walkthrough tools leave the other workpaper sections free');
      const topBar=await evaluate('(()=>{const r='+q('body > #walk-launch')+'.getBoundingClientRect();return [r.left,r.right-innerWidth]})()');
      assert.ok(topBar.every(n=>Math.abs(n)<=1));
      await evaluate(q(panel)+'.scrollIntoView({block:"center",behavior:"instant"})');
      await wait(q(bar+' > #walk-launch')+'!=null','mobile feedback and current original');
      const edges=await evaluate('(()=>{const r='+q(bar)+'.getBoundingClientRect();return [r.left,r.right-innerWidth,r.bottom-innerHeight]})()');
      assert.ok(edges.every(n=>Math.abs(n)<=1));
      for (const s of [bar+' > :first-child',bar+' > #walk-launch']) {
        assert.ok(await evaluate('(()=>{const el='+q(s)+',r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))})()'));
      }
    }
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
    for (const [i,{name,quote}] of expected.entries()) {
      await evaluate(signers+'.find(b=>b.querySelector(".signer-event-name").textContent==='+JSON.stringify(name+'签认')+').click()');
      assert.equal(await evaluate(q(panel+' .signer-quote')+'.textContent'),quote);
      if (id) {
        const chosen=q(panel+' [data-walk-selected]');
        await evaluate(chosen+'.scrollIntoView({block:"center",behavior:"instant"})');
        const pin=await evaluate('import("/assets/walkthrough-context.js").then(m=>m.captureContext(null))');
        assert.equal(pin.anchor,await evaluate(chosen+'.id'));
        assert.deepEqual(pin.params,{view:'signer-timing',receipt:f.id});
      }
      await wait(q(panel+' .signer-strip :is(img,canvas)')+'!=null','printed personal date excerpt');
      const trigger=q(panel+' .signer-preview .signer-original');
      if (id && width<650 && i===expected.length-1) {
        await wait(q(bar+' > :first-child')+'?.textContent.includes('+JSON.stringify(name)+')','toolbar follows chosen signer');
        await evaluate(q(bar+' > :first-child')+'.click()');
        await wait(q('#page-dialog')+'.open && '+q('.evidence-row.located')+'?.textContent.includes('+JSON.stringify(quote)+')','mobile toolbar opens current date');
        await evaluate(q('#page-dialog [data-close]')+'.click()');
      }
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
    assert.equal(await evaluate(all(panel+' .signer-basis > .signer-original')+'.length'),2);
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

export async function checkSignerClock(ctx,id,revision) {
  const {root,call,evaluate,wait}=ctx;
  const get=async path=>{const res=await fetch(root+path);assert.ok(res.ok);return res.json();};
  const detail=id && await get('/api/cases/'+id);
  if (id) assert.ok(detail.title.startsWith('合成演练 · '));
  const sample=!id && await get('/assets/signer-clock.json');
  const rev=revision || detail?.rev || sample.rev;
  const paper=id && (await get('/api/cases/'+id+'/reports/'+rev)).report;
  const finding=paper && paper.findings.find(f=>f.signer_timing?.clock);
  const clock=finding?.signer_timing.clock;
  const state=clock?.state || sample.payment.clockState;
  const panel=id?'#signer-timing':'#public-signer-clock';
  const pair=panel+' .signer-paired', body=panel+' .signer-body', mode=panel+' .signer-view-switch button';
  const path=id?'/workpaper/'+id+'?rev='+rev+'&view=signer-timing&receipt='+finding.id:'/?scene=signer-clock#workflow';
  const sourceRows=id?paper.graph.acceptance_authority_sources.clock_rows.filter(r=>clock.rows.includes(r.id)):
    sample.documents.flatMap(d=>d.lines).filter(r=>sample.payment.pair.includes(r.ref));
  const expected=sourceRows.map(r=>r.quote).sort();
  assert.equal(expected.length,2);
  if (sample) for (const doc of sample.documents) {
    for (const [url,sha] of [[doc.pdf,doc.source_sha256],[doc.image,doc.page_sha256]]) {
      const r=await fetch(root+url);assert.ok(r.ok);
      assert.equal(createHash('sha256').update(Buffer.from(await r.arrayBuffer())).digest('hex'),sha);
    }
  }
  await call('Page.navigate',{url:root+path});
  await wait(q(panel)+'?.getClientRects().length','visible same-day workpaper');
  assert.equal(await evaluate(q(panel)+'.dataset.clockState'),state);
  const outcome={before:'扣款早于签认',after:'签认后扣款',missing:'扣款时刻待核'}[state];
  assert.equal(await evaluate(q(panel+' .signer-outcome')+'.textContent'),outcome);
  if (id) {
    for (const mutation of [
      "r.graph.edges=r.graph.edges.filter(e=>!(e.type==='acceptance_clock_source' && e.to===row.id))",
      "r.graph.edges=r.graph.edges.filter(e=>!(e.type==='supports_result' && e.from===row.id))",
      ...(state==='missing'?[]:["row.at='04:00'","delete r.calls.pages.find(c=>c.doc===row.doc && c.page===row.page).signer_timing_rects[row.line]",
        "const t=r.findings.find(f=>f.signer_timing).signer_timing; t.signed[t.required[1]]=t.signed[t.required[0]]"])
    ]) {
      const actual=await evaluate("(()=>{const r=structuredClone(state.bundle.report), row=r.graph.acceptance_authority_sources.clock_rows.find(r=>r.kind==='signer');"+mutation+";return SignerEvidence.panel(r).dataset.clockState})()");
      assert.equal(actual,'unverified');
    }
  }
  for (const width of [1440,1024,768,390,360,320]) {
    await size(ctx,width);
    await evaluate(all(mode)+'[0].click()');
    assert.ok(await evaluate(q(panel+' .signer-day-group')+'.getAttribute("aria-label").includes("北京时间")'));
    assert.deepEqual(await evaluate(all(panel+' .signer-day-group .signer-clock')+'.map(e=>e.textContent)'),
      state==='before'?['13:10','15:20']:state==='after'?['15:20','16:30']:['15:20']);
    assert.equal(await evaluate(all(body+' .signer-event')+'.length'),3);
    await inspect(ctx,width,panel,'signer-clock-'+(id?'paper':'public')+'-'+state);
    await evaluate(all(mode)+'[1].focus()');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    await wait(q(pair)+'?.getClientRects().length && '+q(body)+'.hidden','two source extracts selected by keyboard');
    assert.equal(await evaluate(q(panel+' .signer-head h3')+'.textContent'),'2026/09/25 · 北京时间');
    assert.equal(await evaluate(all(mode)+'[1].getAttribute("aria-pressed")'),'true');
    assert.deepEqual(await evaluate(all(pair+' .signer-quote')+'.map(e=>e.textContent).sort()'),expected);
    await wait(all(pair+' .signer-strip :is(img,canvas)')+'.length===2','two physical line crops');
    await wait(all(pair+' .signer-thumbnail img')+'.every(i=>i.naturalWidth>0)','both original thumbnails loaded');
    assert.equal(await evaluate(all(pair+' .signer-thumbnail-mark')+'.length'),2);
    await inspect(ctx,width,panel,'signer-clock-pair-'+(id?'paper':'public')+'-'+state);
    const sides=all(pair+' .signer-pair-side');
    for (const i of [0,1]) {
      const side=sides+'['+i+']', trigger=side+'.querySelector(".signer-original")';
      const quote=await evaluate(side+'.querySelector("blockquote").textContent');
      await evaluate(trigger+'.focus();'+trigger+'.click()');
      if (id) {
        await wait(q('#page-dialog')+'.open && '+q('.evidence-row.located')+'?.textContent.includes('+JSON.stringify(quote)+')','raw clock source row');
        await wait(q('#page-dialog .source-plane svg rect')+'!=null','physical row marked');
        assert.ok(await evaluate(q('.source-tools a')+'.href.endsWith("?rev='+rev+'")'));
        await evaluate(q('#page-dialog [data-close]')+'.click()');
      } else {
        const ref=sourceRows.find(r=>r.quote===quote).ref;
        await wait(q('#sample-review')+'.open && '+q('#sample-review canvas')+'?.dataset.fact==='+JSON.stringify(ref),'public clock source marked');
        const rows=sample.documents.find(d=>d.lines.some(l=>l.ref===ref)).lines;
        assert.equal(await evaluate(all('#sample-review .sample-records button')+'.length'),rows.length);
        await call('Input.dispatchKeyEvent',{type:'keyDown',key:'End',code:'End'});
        await wait(q('#sample-review canvas')+'.dataset.fact==='+JSON.stringify(rows.at(-1).ref),'last line on this original');
        await evaluate(q('#sample-review form button')+'.click()');
      }
      await wait('document.activeElement==='+trigger,'source focus restored');
    }
    if (id) {
      const other=paper.findings.find(f=>f.rule==='H04' && f.stage?.clause_ref!==finding.stage.clause_ref);
      await evaluate(q('#phase-choice-'+other.id)+'.click()');
      assert.equal(await evaluate(q(panel)+'.dataset.outOfStage'),'true');
      assert.ok(await evaluate(q(pair)+'.getClientRects().length===0 && '+q(mode)+'.getClientRects().length===0'));
      await evaluate(q(panel+' .signer-empty button')+'.click()');
    }
    await evaluate(all(mode)+'[0].click()');
  }
  console.log('PASS · '+(id?'固定底稿':'公开水印演练')+' R'+rev+' · '+state+' · 原行对照、页图划线、键盘、六档屏宽');
}
