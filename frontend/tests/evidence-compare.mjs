import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

export async function checkEvidenceCompare({root,call,evaluate,wait},caseId,requestedRev) {
  const base=root+'/api/cases/'+caseId;
  const task=await (await fetch(base)).json();
  assert.ok(task.title.startsWith('合成演练 · '));
  const rev=requestedRev || task.rev;
  const {report}=await (await fetch(base+'/reports/'+rev)).json();
  const h=report.findings.find(f=>f.rule==='H02');
  const witnesses=new Set(report.graph.edges.filter(e=>e.type==='supports_result' && e.to==='finding/'+h.id).map(e=>e.from));
  const facts=report.graph.facts.filter(f=>h.evidence.includes(f.id) && witnesses.has(f.id));
  const byId=new Map(facts.map(f=>[f.id,f]));
  const $=s=>'document.querySelector('+JSON.stringify(s)+')';
  const ids=()=>evaluate('[...document.querySelectorAll(".compare-leaf")].map(n=>n.dataset.fact)');
  const opens=()=>evaluate('[...document.querySelectorAll(".compare-original")].map(e=>e.textContent)');
  const originalText=f=>f.source_line?.rects?.length && f.source_line.text || f.quote;
  async function key(name,code) {
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:name,code:name,windowsVirtualKeyCode:code,...(name==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:name,code:name,windowsVirtualKeyCode:code});
  }
  async function search(value) {
    await evaluate('(()=>{const q=document.querySelector(".finder-search input");q.value='+JSON.stringify(value)+';q.dispatchEvent(new Event("input"))})()');
  }
  async function picker(side) {
    await evaluate('document.querySelectorAll(".compare-pick")['+side+'].focus()');
    await key('Enter',13);
    await wait('document.querySelector(".citation-finder").open && document.activeElement===document.querySelector(".finder-search input")','focused search field');
  }
  async function selectFact(side, id) {
    await picker(side);
    await search(id);
    const result=await evaluate('Array.from(document.querySelectorAll(".finder-choice"),b=>b.dataset.ref)');
    assert.ok(result.includes(id));
    await evaluate($('[data-ref="'+id+'"].finder-choice')+'.focus()');
    await key('Enter',13);
    await wait('!document.querySelector(".citation-finder").open','choice applied');
  }
  await call('Page.navigate',{url:root+'/workpaper/'+caseId+'?rev='+rev});
  await wait('!!document.querySelector(".compare-jump")','report shortcut for cited acceptance observations');
  await evaluate($('.compare-jump')+'.click()');
  await wait('document.querySelector("#trace-select")?.value==='+JSON.stringify(h.id)+' && !document.querySelector("#trace-compare").hidden','issued finding in comparison');
  assert.equal(await evaluate('document.activeElement.dataset.mode'),'compare');
  assert.equal(await evaluate($('#trace-details')+'.hidden'),true);
  const [,excluded]=await ids();
  await picker(0);
  assert.deepEqual(await evaluate('Array.from(document.querySelectorAll(".finder-choice"),b=>b.dataset.ref).sort()'),[...byId.keys()].filter(id=>id!==excluded).sort());
  await search('没有这个字段__');
  assert.ok(await evaluate('!!document.querySelector(".finder-empty") && !document.querySelector(".finder-choice")'));
  await search('');
  await key('ArrowDown',40); assert.ok(await evaluate('document.activeElement.matches(".finder-choice")'));
  await key('End',35); assert.ok(await evaluate('document.activeElement===document.querySelector(".finder-results").lastElementChild'));
  await key('Escape',27); assert.ok(await evaluate('document.activeElement===document.querySelector(".compare-pick")'));
  const pairs=await evaluate('[...document.querySelectorAll("[data-pair]")].map(b=>b.dataset.pair)');
  const defaultPair=await evaluate('document.querySelector("[data-pair][aria-pressed=true]")?.dataset.pair');
  const chain=h.reinspection;
  const retestFields={
    'retest-readings':[['original','measured_result'],['final','measured_result']],
    'retest-repair':[['repair','repair_result'],['final','defect_closure']],
    'retest-dates':[['repair','repaired_on'],['final','accepted_on']],
    'retest-defect':[['original','defect_number'],['final','defect_number']]
  };
  if (chain?.focus && pairs.includes('retest-'+chain.focus)) assert.equal(defaultPair,'retest-'+chain.focus);
  const change=h.quality_change;
  if (change && !change.quantity) {
    const fields=await ids().then(a=>a.map(id=>byId.get(id)?.field));
    if (change.applied_criterion) assert.deepEqual(fields,[change.state==='applied'?'revised_criterion':'acceptance_criteria','measured_result']);
    if (change.state==='pending') {
      assert.ok(!pairs.includes('reading') && !pairs.includes('basis'));
      assert.equal(await evaluate($('.compare-version')+'.dataset.state'),'pending');
    }
  }
  for (const pair of pairs) {
    await evaluate($('[data-pair="'+pair+'"]')+'.click()');
    const [left,right]=await ids();
    assert.ok(left!==right && byId.has(left) && byId.has(right));
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".compare-quote blockquote")].map(q=>q.textContent)'),[left,right].map(id=>originalText(byId.get(id))));
    if (retestFields[pair]) {
      for (const [i,id] of [left,right].entries()) {
        const [role,field]=retestFields[pair][i];
        const step=chain.steps.find(s=>s.role===role), fact=byId.get(id);
        assert.ok(step.evidence.includes(id) && (fact.unit || fact.doc)===step.unit && fact.field===field);
      }
    }
    if (pair==='dates') {
      assert.equal(change[byId.get(left).field],change.effective_on);
      assert.equal(byId.get(right).field,'accepted_on');
    }
    if (pair.startsWith('batch-')) {
      const batch=h.batch_acceptance.batches.find(b=>b.index===Number(pair.slice(6)));
      assert.ok(batch.records.includes(byId.get(right).unit || byId.get(right).doc));
    }
  }
  if (defaultPair) await evaluate($('[data-pair="'+defaultPair+'"]')+'.click()');
  else { await selectFact(0,facts[0].id); await selectFact(1,facts[1].id); }
  await wait('document.querySelectorAll(".compare-scan canvas").length===2','two archived page images');
  const initial=await ids();
  for (const [i,id] of initial.entries()) {
    const fact=byId.get(id);
    assert.ok((await opens())[i].includes(fact.label));
  }
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    const boxes=await evaluate('[...document.querySelectorAll(".compare-leaf,.compare-original,.compare-scan canvas")].map(n=>n.getBoundingClientRect().toJSON())');
    assert.ok(boxes.every(r=>r.width>0 && r.left>=0 && r.right<=width+1),'comparison fits '+width);
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'page width '+width);
    const leaves=await evaluate('[...document.querySelectorAll(".compare-leaf")].map(n=>n.getBoundingClientRect().toJSON())');
    if (width>700) assert.equal(leaves[0].top,leaves[1].top);
    else assert.ok(leaves[1].top>=leaves[0].bottom);
    await picker(0);
    await search(initial[0]);
    assert.ok(await evaluate('Array.from(document.querySelectorAll(".finder-choice")).some(b=>b.dataset.ref==='+JSON.stringify(initial[0])+' && b.getBoundingClientRect().right<=innerWidth+1)'));
    await key('Escape',27);
    await wait('!document.querySelector(".citation-finder").open && document.activeElement===document.querySelector(".compare-pick")','filled search closed and focus restored at '+width);
    if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
      await evaluate('new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(done)))');
      const clip=await evaluate('(()=>{const r=document.querySelector(".trace-panel").getBoundingClientRect();return {x:r.left+scrollX,y:r.top+scrollY,width:r.width,height:r.height,scale:1}})()');
      const capture=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'compare-'+caseId+'-'+width+'.png'), Buffer.from(capture.data,'base64'));
    }
  }
  await evaluate('document.querySelectorAll(".compare-original")[1].focus()');
  await key('Enter',13);
  await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(initial[1]),'original focused on selected observation');
  await wait('document.querySelector("#page-dialog img")?.naturalWidth>0','full original decoded');
  await key('Escape',27);
  await wait('!document.querySelector("#page-dialog").open','original dismissed');
  assert.ok(await evaluate('document.activeElement===document.querySelectorAll(".compare-original")[1]'));
  const alternative=facts.find(f=>!initial.includes(f.id) && !f.source_line?.rects?.length) || facts.find(f=>!initial.includes(f.id));
  if (alternative) {
    await selectFact(0,alternative.id);
    await wait('!!document.querySelector(".compare-leaf .compare-scan canvas")','new first original loaded');
    assert.deepEqual(await ids(),[alternative.id,initial[1]]);
    assert.equal(await evaluate($('.compare-scan')+'.dataset.located'),String(Boolean(alternative.source_line?.rects?.length)));
    assert.equal(await evaluate($('.compare-quote blockquote')+'.textContent'),originalText(alternative));
  }
  await evaluate($('[data-mode="details"]')+'.click()');
  assert.ok(await evaluate('document.querySelector("#trace-compare").hidden && !document.querySelector("#trace-details").hidden'));
  assert.equal(await evaluate($('.trace-result p')+'.textContent'),h.detail);
  await evaluate($('[data-mode="compare"]')+'.click()');
  if (alternative) assert.equal((await ids())[0],alternative.id);
  if (h.batch_acceptance?.records.some(r=>r.standard)) {
    for (const batch of h.batch_acceptance.batches) {
      if (!pairs.includes('batch-'+batch.index)) continue;
      const phase=report.findings.find(f=>f.rule==='H04' && f.stage?.batch_index===batch.index);
      if (!phase) continue;
      await evaluate($('[data-tab="report"]')+'.click()');
      await evaluate($('[data-phase-choice="'+phase.id+'"]')+'.click()');
      await evaluate($('[data-phase-finding="'+phase.id+'"] .compare-jump')+'.click()');
      assert.equal(await evaluate('document.querySelector("[data-pair][aria-pressed=true]")?.dataset.pair'),'batch-'+batch.index);
      const record=h.batch_acceptance.records.find(r=>r.unit===batch.records[0]);
      assert.equal(await evaluate($('.compare-version')+'.dataset.state'),record.standard.state);
      if (record.standard.criterion_ref) assert.deepEqual(await ids(),[record.standard.criterion_ref,record.standard.reading_ref]);
    }
  }
  if (chain) {
    for (const phase of report.findings.filter(f=>f.rule==='H04' && f.stage)) {
      await evaluate($('[data-tab="report"]')+'.click()');
      await evaluate($('[data-phase-choice="'+phase.id+'"]')+'.click()');
      const link=$('[data-phase-finding="'+phase.id+'"] .compare-jump');
      const eligible=pairs.filter(key=>retestFields[key] && retestFields[key].every(([role,field])=>{
        const step=chain.steps.find(s=>s.role===role);
        return step?.evidence.some(ref=>phase.evidence.includes(ref) && byId.get(ref)?.field===field);
      }));
      assert.equal(await evaluate('!!'+link),eligible.length>0);
      if (!eligible.length) continue;
      await evaluate(link+'.click()');
      assert.ok(eligible.includes(await evaluate('document.querySelector("[data-pair][aria-pressed=true]").dataset.pair')));
    }
    await evaluate($('[data-tab="graph"]')+'.click()');
    for (const step of chain.steps.filter(s=>s.completion && s.completion.status!=='ok')) {
      const c=step.completion;
      for (const row of c.lines.filter(s=>['qualification','unreviewed'].includes(s.kind) || (!c.date && s.kind==='date'))) {
        const fact=byId.get(row.facts.find(id=>byId.get(id)?.quote===row.quote));
        const source=fact?.id || row.doc+'/p'+row.page+'/l'+row.line;
        const link=$('[data-repair-source="'+source+'"]');
        await evaluate('(()=>{const group='+link+'.closest("details");if(group) group.open=true})()');
        await evaluate(link+'.focus()'); await key('Enter',13);
        await wait('document.querySelector("#page-dialog").open && document.querySelector(".located blockquote")?.textContent==='+JSON.stringify(row.quote),'repair original and raw characters');
        const rects=report.graph.facts.find(f=>row.facts.includes(f.id) && f.source_line?.number===row.line && f.source_line.text===row.quote)?.source_line.rects || [];
        if (rects.length) assert.equal(await evaluate('document.querySelectorAll("#page-dialog svg rect").length'),rects.length);
        assert.ok(await evaluate('!!'+$('optgroup[label="整改状态与原行"]')));
        const navigator=$('.field-navigator .approval-switch');
        await evaluate($('button[aria-label="放大原页"]')+'.click()');
        const next=await evaluate(navigator+'.dataset.nextRef');
        await evaluate(navigator+'.focus()'); await key('Enter',13);
        assert.equal(await evaluate($('.field-navigator select')+'.value'),next);
        assert.equal(await evaluate($('.zoom-scale')+'.textContent'),'125%');
        await key('Escape',27);
        await wait('!document.querySelector("#page-dialog").open','repair page dismissed');
        assert.ok(await evaluate('document.activeElement==='+link));
        if (!row.line || !row.facts.length) continue;
        // Remove only this observation in the browser's copy. The archived native row still exists.
        function openUntranscribed(source) {
          const saved=state.bundle, graph=saved.report.graph, ledger=graph.repair_completion_sources;
          const lines=ledger.lines.map(s=>s.doc===source.doc && s.page===source.page && s.line===source.line ? {...s,facts:[]} : s);
          try {
            state.bundle={...saved,report:{...saved.report,graph:{...graph,facts:graph.facts.filter(f=>!source.facts.includes(f.id)),
              repair_completion_sources:{...ledger,lines}}}};
            openPage(source.doc,source.page,null,source.line);
          } finally { state.bundle=saved; }
        }
        await evaluate('('+openUntranscribed+')('+JSON.stringify(row)+')');
        assert.equal(await evaluate($('.located blockquote')+'.textContent'),row.quote);
        assert.equal(await evaluate($('.field-navigator select')+'.value'),'repair-line/'+row.line);
        assert.equal(await evaluate('document.querySelectorAll("#page-dialog svg rect").length'),0);
        await key('Escape',27);
        await wait('!document.querySelector("#page-dialog").open','untranscribed page dismissed');
      }
    }
  }
  const images=await evaluate('performance.getEntriesByType("resource").map(r=>r.name).filter(s=>s.includes("/documents/") && s.includes("/pages/"))');
  assert.ok(images.length && images.every(url=>url.startsWith(base+'/documents/') && new URL(url).searchParams.get('rev')===String(rev)));
  console.log('PASS · R'+rev+' · '+facts.length+' supported observations · '+pairs.join(', ')+' · pinned originals, keyboard and six widths');
}

export async function checkMandateCompare({root,call,evaluate,wait},cid) {
  const path=root+'/api/cases/'+cid;
  const task=await (await fetch(path)).json();
  assert.ok(task.title.startsWith('合成演练 · '));
  const {report}=await (await fetch(path+'/reports/'+task.rev)).json();
  const finding=report.findings.find(f=>f.rule==='H01');
  const witnesses=new Set(report.graph.edges.filter(e=>e.type==='supports_result' && e.to==='finding/'+finding.id).map(e=>e.from));
  const facts=new Map(report.graph.facts.filter(f=>finding.evidence.includes(f.id) && witnesses.has(f.id)).map(f=>[f.id,f]));
  const entry=finding.delegations[0];
  const limits=entry.limits || [];
  const adverse=limits.find(c=>c.comparison_ref && c.status==='risk');
  const dateRef=key=>[...facts.values()].find(f=>f.field===key).id;
  const expected=adverse?[adverse.field_ref,adverse.comparison_ref]:
    limits.length>=2?limits.slice(0,2).map(c=>c.field_ref):[dateRef('signed_on'),dateRef('grant_until')];
  const url=root+'/workpaper/'+cid+'?rev='+task.rev;
  await call('Page.navigate',{url:url+'&finding='+finding.id});
  await wait('document.querySelectorAll(".compare-scan canvas").length===2','authorized originals side by side');
  assert.deepEqual(await evaluate('[...document.querySelectorAll(".compare-leaf")].map(n=>n.dataset.fact)'),expected);
  const quotes=expected.map(ref=>facts.get(ref).source_line.text);
  assert.deepEqual(await evaluate('[...document.querySelectorAll(".compare-quote blockquote")].map(n=>n.textContent)'),quotes);
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    await evaluate('document.querySelector(".compare-bar").scrollIntoView({block:"start"})');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && [...document.querySelectorAll(".compare-original")].every(n=>{const r=n.getBoundingClientRect();return r.left>=0 && r.right<=innerWidth+1 && r.height>=44})'),'comparison width '+width);
    if ([390,1440].includes(width) && process.env.AUDIT_UI_SHOTS) {
      const shot=await call('Page.captureScreenshot',{format:'png'});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'mandate-'+cid+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
    }
  }
  await evaluate('document.querySelectorAll(".compare-original")[1].click()');
  await wait('document.querySelector("#page-dialog").open && !!document.querySelector(".located")','right original and coordinates');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await wait('!document.querySelector("#page-dialog").open','return from full original');
  await call('Page.navigate',{url});
  await wait('!!document.querySelector("[data-authority-pair]")','authorization shortcut from a payment phase');
  for (const phase of report.findings.filter(f=>f.rule==='H04' && f.stage)) {
    await evaluate('document.querySelector("[data-tab=report]").click()');
    await evaluate('document.querySelector("[data-phase-choice='+phase.id+']").click()');
    const button='document.querySelector("[data-phase-finding='+phase.id+'] [data-authority-pair]")';
    assert.ok(await evaluate(button+' && '+button+'.getClientRects().length'));
    await evaluate(button+'.click()');
    assert.equal(await evaluate('document.querySelector("#trace-select").value'),finding.id);
    const ids=await evaluate('[...document.querySelectorAll(".compare-leaf")].map(n=>n.dataset.fact)');
    assert.ok(ids.every(id=>phase.evidence.includes(id) && witnesses.has(id)));
    if (facts.get(ids[1]).field==='payment_stage') assert.equal(ids[1],phase.stage.clause_ref);
  }
  console.log('PASS · Signed mandate, source rows, six viewports and all affected installments · '+cid+' R'+task.rev);
}

export async function checkPhaseEvidence({root,call,evaluate,wait},cid) {
  const api=root+'/api/cases/'+cid, task=await (await fetch(api)).json();
  assert.ok(task.title.startsWith('合成演练 · '));
  const {report}=await (await fetch(api+'/reports/'+task.rev)).json();
  const phase=report.findings.find(f=>f.rule==='H04' && f.invoice_receipt);
  const payment=report.findings.find(f=>f.rule==='H05' && f.invoice_receipt);
  assert.ok(phase && payment);
  const gate=phase.invoice_receipt, facts=new Map(report.graph.facts.map(f=>[f.id,f]));
  const selector='[data-phase-finding="'+phase.id+'"] .phase-evidence';
  const node=s=>'document.querySelector('+JSON.stringify(s)+')';
  const get=key=>node(selector+' '+key);
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+task.rev});
  await wait(node(selector)+'?.children.length>0','issued phase evidence');
  if (payment.status==='risk' || phase.status!=='ok')
    assert.equal(await evaluate(node('.phase-choice[aria-selected=true]')+'.dataset.phaseChoice'),phase.id);
  await evaluate(node('[data-phase-choice="'+phase.id+'"]')+'.click()');
  if (payment.status==='risk') {
    assert.equal(await evaluate(node(selector)+'.dataset.mode'),'timeline');
    assert.equal(await evaluate(get('.proof-count')+'.textContent'),'付款早于收票 1 天');
  }
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    for (const mode of ['checks','timeline']) {
      await evaluate(get('[data-mode="'+mode+'"]')+'.click()');
      assert.equal(await evaluate(get('[aria-pressed=true]')+'.dataset.mode'),mode);
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && '+node(selector)+'.scrollWidth<='+node(selector)+'.clientWidth+1'),'fits '+width);
      if (mode==='checks') {
        for (const key of ['invoice','receipt'])
          assert.equal(await evaluate(get('[data-check="'+key+'"]')+'.dataset.state'),gate[key].status);
      } else {
        const dates=await evaluate('[...'+node(selector)+'.querySelectorAll(".proof-event time")].map(t=>t.dateTime)');
        assert.deepEqual(dates,[...dates].sort());
        assert.ok(dates.includes('2026-09-18') && dates.includes('2026-09-21'));
        if (process.env.AUDIT_UI_SHOTS && (width===1440 || width===390) && payment.status==='risk') {
          await evaluate(node(selector)+'.closest(".performance-panel").scrollIntoView({block:"center"})');
          await evaluate('document.fonts.ready.then(()=>true)');
          const clip=await evaluate('(()=>{const b='+node(selector)+'.closest(".performance-panel").getBoundingClientRect();return {x:b.x+scrollX,y:b.y+scrollY,width:b.width,height:b.height,scale:1}})()');
          const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
          await writeFile(join(process.env.AUDIT_UI_SHOTS,'receipt-timeline-'+width+'.png'),Buffer.from(shot.data,'base64'));
        }
      }
    }
  }
  await evaluate(get('[data-mode=checks]')+'.click()');
  if (gate.receipt.status==='ok') {
    await evaluate(get('[data-check=receipt]')+'.click()');
    await wait('document.querySelector("#page-dialog")?.open && document.querySelector(".located[data-fact]")?.dataset.fact==='+JSON.stringify(gate.receipt.seal_ref),'buyer seal on the receipt');
    await evaluate(node('#page-dialog [data-close]')+'.click()');
  } else {
    const status=await evaluate(get('[data-check=receipt] .tag')+'.textContent');
    assert.equal(status,gate.receipt.number_ref?'票号不符':'待补签收');
  }
  await evaluate(get('[data-mode=timeline]')+'.click()');
  await evaluate(get('[data-event=paid]')+'.focus()');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  const paid=payment.evidence.map(id=>facts.get(id)).find(f=>f?.field==='paid_on');
  await wait('document.querySelector("#page-dialog")?.open && document.querySelector(".located[data-fact]")?.dataset.fact==='+JSON.stringify(paid.id),'keyboard opens issued payment date');
  await wait('document.querySelector("#page-dialog .page-image")?.naturalWidth>0','verified original image loaded');
  assert.equal(await evaluate('new URL(document.querySelector("#page-dialog .source-tools a").href).searchParams.get("rev")'),String(task.rev));
  await evaluate(node('#page-dialog [data-close]')+'.click()');
  await evaluate(get('.proof-clauses summary')+'.click()');
  const clause=gate.clauses[0];
  assert.equal(await evaluate(get('.proof-line q')+'.textContent'),clause.quote);
  await evaluate(get('.proof-line button')+'.click()');
  await wait('document.querySelector("#page-dialog")?.open && [...document.querySelectorAll(".located blockquote")].some(q=>q.textContent==='+JSON.stringify(clause.quote)+')','printed rider or clause');
  await evaluate(node('#page-dialog [data-close]')+'.click()');
  for (const [key,expected] of [['receipt-number',[gate.invoice.number_ref,gate.receipt.number_ref]],
                               ['receipt-payment-date',[gate.receipt.date_ref,paid.id]]]) {
    if (expected.some(x=>!x)) {
      assert.equal(await evaluate(get('[data-pair="'+key+'"]')),null); continue;
    }
    await evaluate(get('[data-pair="'+key+'"]')+'.click()');
    await wait('document.querySelectorAll(".compare-leaf canvas").length===2','two original pages');
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".compare-leaf")].map(n=>n.dataset.fact)'),expected);
    await evaluate(node('#tabs [data-tab=report]')+'.click()');
    assert.equal(await evaluate(node('.phase-choice[aria-selected=true]')+'.dataset.phaseChoice'),phase.id);
    assert.equal(await evaluate(node(selector)+'.dataset.mode'),'timeline');
  }
  console.log('PASS · R'+task.rev+' · '+phase.status+'/'+payment.status+' · receipt checklist, chronological dates, original rows and paired pages at six widths');
}

export async function checkPaymentChange({root,call,evaluate,wait},cid,revision) {
  const api=root+'/api/cases/'+cid, task=await (await fetch(api)).json();
  assert.ok(task.title.startsWith('合成演练 · '));
  const rev=Number(revision || task.rev); assert.ok(Number.isSafeInteger(rev) && rev>0);
  const {report}=await (await fetch(api+'/reports/'+rev)).json();
  const node=s=>'document.querySelector('+JSON.stringify(s)+')';
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+rev});
  await wait(node('.performance-panel .phase-choice')+'!==null','issued workpaper');
  const phase=report.findings.find(f=>f.rule==='H04' && f.payment_change?.scope_clear);
  if (!phase) {
    assert.ok(!report.graph.quality_addenda?.payments);
    assert.equal(await evaluate(node('[data-payment-edition]')),null);
    console.log('PASS · R'+rev+' · historical payment presentation'); return;
  }
  const payment=report.findings.find(f=>f.rule==='H05' && f.payment_change);
  const edit=payment.payment_change, facts=new Map(report.graph.facts.map(f=>[f.id,f]));
  const section='[data-phase-finding="'+phase.id+'"] .phase-evidence';
  const within=s=>node(section+' '+s);
  const witnesses=new Set(report.graph.edges.filter(e=>e.type==='supports_result' && e.to==='finding/'+payment.id).map(e=>e.from));
  const selectPhase=()=>evaluate(node('[data-phase-choice="'+phase.id+'"]')+'.click()');
  await selectPhase();
  assert.equal(await evaluate(node(section)+'.dataset.mode'),'timeline');
  const strip=within('[data-payment-edition]'), button=within('.edition-source');
  assert.equal(await evaluate(strip+'.dataset.paymentEdition'),edit.applies);
  assert.equal(await evaluate(strip+'.querySelector("time")?.dateTime'),edit.paid_on);
  const label={original:'原合同',amended:'补充协议',same_day:'同日待核',pending:'生效待核'}[edit.applies];
  assert.equal(await evaluate(button+'.textContent'),label);
  const status=await evaluate(within('.proof-count')+'.textContent');
  if (edit.applies==='amended') assert.equal(status,'付款早于收票 1 天');
  else if (edit.applies==='same_day') assert.equal(status,'生效与实付同日 · 时分待核');
  else assert.ok(!status.includes('付款早于收票'));
  assert.equal(await evaluate(within('[data-event=amendment]')+'?.closest("[data-day]")?.dataset.day ?? null'),edit.effective_on);
  if (edit.applies==='same_day') {
    assert.ok(await evaluate(within('[data-event=amendment]')+'.closest("[role=group][data-day]")==='+within('[data-event=paid]')+'.closest("[role=group][data-day]")'));
    assert.equal(await evaluate(within('[data-event=paid]')+'.closest("[data-day]").querySelectorAll("time").length'),1);
  }
  const inspectRef={original:edit.original_ref,amended:edit.revised_ref,same_day:edit.timing_ref,pending:edit.effect_ref}[edit.applies];
  assert.ok(witnesses.has(inspectRef) && facts.has(inspectRef));
  const observed=await evaluate([
    '(() => {',
    'const report=state.bundle.report, graph=report.graph;',
    'const finding=report.findings.find(f=>f.id==='+JSON.stringify(payment.id)+'), ref='+JSON.stringify(inspectRef)+';',
    'const edges=graph.edges.filter(e=>!(e.type==="supports_result" && e.to==="finding/"+finding.id && e.from===ref));',
    'return [PhaseEvidence.amendmentFact(graph,finding,ref)?.id, PhaseEvidence.amendmentFact({...graph,edges},finding,ref)];',
    '})()'
  ].join('\n'));
  assert.deepEqual(observed,[inspectRef,null]);
  await evaluate(button+'.focus()');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await wait(node('#page-dialog')+'?.open && '+node('.located[data-fact]')+'?.dataset.fact==='+JSON.stringify(inspectRef),'keyboard opens the applicable original');
  await wait(node('#page-dialog .page-image')+'?.naturalWidth>0','original page image loaded');
  assert.equal(await evaluate('new URL('+node('#page-dialog .source-tools a')+'.href).searchParams.get("rev")'),String(rev));
  await evaluate(node('#page-dialog [data-close]')+'.click()');
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:940,deviceScaleFactor:1,mobile:width<600});
    const fit='document.documentElement.scrollWidth<=innerWidth+1 && '+node(section)+'.scrollWidth<='+node(section)+'.clientWidth+1';
    await evaluate(within('[data-mode=checks]')+'.click()');
    assert.equal(await evaluate(within('[data-check=amendment]')+'.dataset.state'),edit.effective_on?'ok':'missing');
    assert.ok(await evaluate(fit),'checklist fits '+width);
    await evaluate(within('[data-mode=timeline]')+'.click()');
    const dates=await evaluate('[...'+node(section)+'.querySelectorAll(".proof-rail time")].map(n=>n.dateTime)');
    assert.deepEqual(dates,[...dates].sort());
    assert.equal(new Set(dates).size,dates.length);
    assert.ok(await evaluate(fit),'timeline fits '+width);
    if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
      const panel=node(section)+'.closest(".performance-panel")';
      await evaluate('document.activeElement.blur();'+panel+'.scrollIntoView({block:"center"})'); await evaluate('document.fonts.ready.then(()=>true)');
      const clip=await evaluate('(()=>{const b='+panel+'.getBoundingClientRect();return {x:b.x+scrollX,y:b.y+scrollY,width:b.width,height:b.height,scale:1}})()');
      const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'payment-'+edit.applies+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
    }
  }
  const seal=edit.effective_on===edit.seller_on?edit.seller_date_ref:edit.buyer_date_ref;
  for (const [key,pair] of [['amendment-terms',[edit.original_ref,edit.revised_ref]],['amendment-payment-date',[edit.effective_on && seal,edit.paid_ref]]]) {
    const shortcut=within('[data-pair="'+key+'"]');
    if (pair.some(x=>!x)) { assert.equal(await evaluate(shortcut),null); continue; }
    assert.ok(pair.every(ref=>witnesses.has(ref) && facts.has(ref)));
    await evaluate(shortcut+'.click()');
    await wait('document.querySelectorAll(".compare-leaf canvas").length===2','two verified original pages');
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".compare-leaf")].map(n=>n.dataset.fact)'),pair);
    const mark=node('.compare-quote mark'), toggle=node('.compare-highlight input');
    if (key==='amendment-terms') {
      const printed=facts.get(edit.revised_ref).source_line.text;
      assert.equal(await evaluate(mark+'.textContent'),'且买方收到本合同对应的发票');
      const quote=node('.compare-leaf:nth-child(2) blockquote');
      assert.equal(await evaluate(quote+'.textContent'),printed);
      await evaluate(toggle+'.focus()');
      await call('Input.dispatchKeyEvent',{type:'keyDown',key:' ',code:'Space',windowsVirtualKeyCode:32});
      await call('Input.dispatchKeyEvent',{type:'keyUp',key:' ',code:'Space',windowsVirtualKeyCode:32});
      assert.equal(await evaluate(mark),null);
      assert.equal(await evaluate(quote+'.textContent'),printed);
      await evaluate(toggle+'.click()');
      assert.ok(await evaluate(mark+'!==null'));
      if (process.env.AUDIT_UI_SHOTS && edit.applies==='amended') {
        await call('Emulation.setDeviceMetricsOverride',{width:1440,height:940,deviceScaleFactor:1,mobile:false});
        const panel=node('.evidence-compare');
        await evaluate('document.activeElement.blur();'+panel+'.scrollIntoView({block:"center"})');
        const clip=await evaluate('(()=>{const b='+panel+'.getBoundingClientRect();return {x:b.x+scrollX,y:b.y+scrollY,width:b.width,height:b.height,scale:1}})()');
        const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
        await writeFile(join(process.env.AUDIT_UI_SHOTS,'payment-clause-diff.png'),Buffer.from(shot.data,'base64'));
      }
    } else assert.equal(await evaluate(mark),null);
    const ledger=node('details.payment-amendment-relations');
    await evaluate(ledger+'.querySelector("summary").click()');
    await wait(ledger+'.querySelectorAll("[data-reservation-source]").length>0','graph original lines');
    assert.ok(await evaluate(ledger+'.textContent.includes('+JSON.stringify(facts.get(edit.revised_ref).quote)+')'));
    await evaluate(node('#tabs [data-tab=report]')+'.click()');
    assert.equal(await evaluate(node('.phase-choice[aria-selected=true]')+'.dataset.phaseChoice'),phase.id);
  }
  for (const other of report.findings.filter(f=>f.rule==='H04' && !f.payment_change)) {
    await evaluate(node('[data-phase-choice="'+other.id+'"]')+'.click()');
    assert.equal(await evaluate(node('[data-phase-finding="'+other.id+'"] [data-payment-edition]')),null);
  }
  console.log('PASS · R'+rev+' · '+edit.applies+' · applicable clause, seal dates, transfer, originals, six viewport widths');
}
