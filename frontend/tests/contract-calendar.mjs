import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

export async function checkCalendar({root,call,evaluate,wait},id,version) {
  const detail=await (await fetch(root+'/api/cases/'+id)).json(), rev=version || detail.rev;
  const report=(await (await fetch(root+'/api/cases/'+id+'/reports/'+rev)).json()).report;
  const h01=report.findings.find(f=>f.rule==='H01'), groups=h01.effect_review.calendar;
  const rows=report.graph.contract_effect_sources.date_rows, doc=report.graph.documents[0];
  const q=selector=>'document.querySelector('+JSON.stringify(selector)+')';
  await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev='+rev+'&view=calendar'});
  await wait(q('#contract-calendar')+'?.getClientRects().length && state.bundle?.rev==='+rev,'fixed-revision calendar');
  const effective=groups.find(g=>g.field==='effect_on');
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
    await evaluate(q('#calendar-effect_on')+'.click()');
    for (const [i,id] of effective.rows.entries()) {
      const row=rows.find(r=>r.id===id);
      if (i) await evaluate('document.querySelectorAll(".calendar-lines button")['+i+'].click()');
      await wait(q('.calendar-body')+'?.dataset.calendarRow==='+JSON.stringify(id),'selected physical line');
      const fact=report.graph.facts.find(f=>f.id===row.facts[0]);
      if (row.facts.length===1 && fact?.source_line?.rects?.length) await wait('!!'+q('.calendar-paper-line canvas'),'original excerpt');
      assert.equal(await evaluate(q('#calendar-effect_on')+'.dataset.state'),effective.state);
      const overflow=await evaluate('document.documentElement.scrollWidth>innerWidth+1 || '+
        '[...document.querySelectorAll(".paper-reader button,.calendar-reading,.calendar-paper-line canvas")].some(e=>e.getClientRects().length && e.getBoundingClientRect().right>innerWidth+1)');
      assert.equal(overflow,false,'viewport '+width);
      if (process.env.AUDIT_UI_SHOTS && !i && [1440,390].includes(width)) {
        const clip=await evaluate('(()=>{const r='+q('.paper-reader')+'.getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1};})()');
        const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
        await writeFile(join(process.env.AUDIT_UI_SHOTS,'calendar-'+id.split('/')[1]+'-'+effective.state+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
      }
      await evaluate(q('.calendar-original')+'.click()');
      await wait(q('#page-dialog')+'.open && '+q('.source-plane img')+'?.naturalWidth && '+q('.located')+'?.dataset.gapLine==='+JSON.stringify(String(row.line)),'original page and line');
      assert.equal(await evaluate(q('.located blockquote')+'.textContent'),row.quote);
      const url=await evaluate(q('#page-dialog .source-tools a')+'.href');
      assert.ok(url.endsWith('/pages/'+row.page+'?rev='+rev));
      if (width===1440) {
        const bytes=Buffer.from(await (await fetch(url)).arrayBuffer());
        assert.equal(createHash('sha256').update(bytes).digest('hex'),row.page_sha256);
        assert.equal(row.original_sha256,doc.sha256);
      }
      await evaluate(q('#page-dialog [data-close]')+'.click()');
    }
    await evaluate(q('#calendar-effect_on')+'.focus()');
    await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Home',windowsVirtualKeyCode:36});
    assert.equal(await evaluate('document.activeElement.id'),'calendar-'+groups[0].field);
    await evaluate(q('#calendar-effect_on')+'.click()');
    const linked=await evaluate('[...document.querySelectorAll("[data-calendar-phase]")].map(e=>e.dataset.calendarPhase)');
    assert.deepEqual(linked,report.findings.filter(f=>['H04','H05'].includes(f.rule) && f.stage && f.evidence.includes(effective.rows[0])).map(f=>f.id));
    if (linked.length) {
      await evaluate(q('[data-calendar-phase]')+'.click()');
      assert.equal(await evaluate('document.activeElement.dataset.finding'),linked[0]);
    }
    if (await evaluate('!!'+q('.paper-reader-mobile select'))) {
      if (width<=760) {
        await evaluate('(()=>{const s='+q('.paper-reader-mobile select')+';s.selectedIndex=[...s.options].findIndex(o=>o.value!=="contract-dates");s.dispatchEvent(new Event("change"));})()');
      } else {
        await evaluate(q('#reader-tab-contract-dates')+'.focus()');
        await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'ArrowDown',windowsVirtualKeyCode:40});
      }
      assert.equal(await evaluate(q('#contract-calendar')+'.getClientRects().length'),0);
      await evaluate('revealPaperTarget('+q('#contract-calendar')+')');
      assert.equal(await evaluate(q('.paper-reader-mobile select')+'.value'),'contract-dates');
      assert.equal(await evaluate('document.querySelectorAll(".paper-reader-pane:not([hidden])").length'),1);
    }
  }
  const pending=report.findings.filter(f=>['issue','risk','missing'].includes(f.status));
  if (!['exact','spacing'].includes(effective.state) && rev===detail.rev) {
    await evaluate(q('#calendar-effect_on')+'.click();'+q('.calendar-draft')+'.click()');
    assert.equal(await evaluate(q('#review-decision input:checked')+'.value'),'return');
    const draft=await evaluate(q('#review-note')+'.value');
    for (const ref of effective.rows) {
      const r=rows.find(r=>r.id===ref);
      assert.ok(draft.includes('第 '+r.line+' 行'));
      if (effective.state==='conflict') assert.ok(draft.includes(r.quote));
    }
    await evaluate(q('#review-dialog [data-close]')+'.click()');
  } else assert.equal(await evaluate('!!'+q('.calendar-draft')),false);
  if (pending.length>1) {
    await evaluate(q('.queue-controls [aria-label="下一条待核事项"]')+'.click()');
    assert.equal(await evaluate(q('.queue-position')+'.value'),'2 / '+pending.length);
    await evaluate(q('.queue-controls [aria-label="上一条待核事项"]')+'.click()');
    assert.equal(await evaluate(q('.queue-position')+'.value'),'1 / '+pending.length);
  }
  await evaluate(q('#quick-open')+'.click();'+q('#quick-query')+'.value="核对合同日期";'+q('#quick-query')+'.dispatchEvent(new Event("input"))');
  await evaluate(q('#quick-results [role="option"]')+'.click()');
  assert.equal(await evaluate('document.activeElement.id'),'contract-calendar');
  for (const mutation of ['hash','quote','edge','date','location',...(effective.state==='spacing'?['call']:[])]) {
    const fallback=await evaluate('(()=>{const r=structuredClone(state.bundle.report), f=r.findings.find(f=>f.rule==="H01"), '+
      'group=f.effect_review.calendar.find(x=>x.field==="effect_on"), row=r.graph.contract_effect_sources.date_rows.find(x=>x.id===group.rows[0]);'+
      ({hash:'row.original_sha256="different";',quote:'row.quote+="改";',edge:'r.graph.edges=r.graph.edges.filter(e=>!(e.from===row.id && e.to==="finding/"+f.id));',
        date:'group.date="1999-06-05";',location:'row.line=200;',call:'r.calls.pages.find(p=>p.doc===row.doc && p.page===row.page).check.response_id="different";'})[mutation]+
      'return ContractCalendar.panel(f,r.graph,r.findings,r.calls.pages).textContent;})()');
    assert.equal(fallback,'合同日期依据待核',mutation);
  }
  const after=await (await fetch(root+'/api/cases/'+id)).json();
  assert.deepEqual(after.decisions,detail.decisions);
  console.log('PASS · '+effective.state+' · '+effective.rows.length+' native lines · 6 widths, original pages, payments and evidence picker');
}

export async function checkPublicCalendar({root,call,evaluate,wait}) {
  const file='/showcase/calendar-contract.pdf', image='/assets/showcase-calendar-page.jpg';
  for (const [path,digest] of [[file,'c9751b24f4902a8f18e963b86b3f2c6b1eeaf5562483814be397165e9a0eb741'],
    [image,'63e7a392710a1adde85eafb3816b43e4abe70bf8a0e2eaf17a6ca0891b45d79c']]) {
    const response=await fetch(root+path);
    assert.ok(response.ok);
    assert.equal(createHash('sha256').update(Buffer.from(await response.arrayBuffer())).digest('hex'),digest);
  }
  const q=selector=>'document.querySelector('+JSON.stringify(selector)+')';
  await call('Page.navigate',{url:root+'/?scene=contract-dates#workflow'});
  await wait(q('#signing-example')+'?.value==="calendar" && !'+q('#signing-calendar')+'?.hidden','public conflicting dates');
  for (const [preference,animation] of [['reduce','none'],['no-preference','settle']]) {
    await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:preference}]});
    assert.equal(await evaluate('getComputedStyle('+q('.hero-copy')+').animationName'),animation);
  }
  await call('Emulation.setEmulatedMedia',{features:[]});
  assert.equal(await evaluate('performance.getEntriesByType("resource").some(r=>r.name.endsWith('+JSON.stringify(image)+'))'),false);
  for (const width of [320,390,768,1024,1440]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
    assert.equal(await evaluate(q('#scene-signing')+'.scrollWidth<='+q('#scene-signing')+'.clientWidth+1'),true);
    if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
      const clip=await evaluate('(()=>{const r='+q('#scene-signing')+'.getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1};})()');
      const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'home-calendar-'+width+'.png'),Buffer.from(shot.data,'base64'));
    }
    await evaluate(q('.calendar-thumbnail')+'.click()');
    await wait(q('#sample-review canvas')+'?.dataset.fact==="d01/p1/f7"','thumbnail opens the full source');
    assert.equal(await evaluate(q('#sample-review [data-scale="page"]')+'.getAttribute("aria-pressed")'),'true');
    await evaluate(q('#sample-review form button')+'.click()');
    for (const [ref,line] of [['d01/p1/f7',9],['d01/p1/f8',10],['d01/p1/f6',8]]) {
      await evaluate(q('#signing-calendar a[data-line][data-ref="'+ref+'"]')+'.click()');
      await wait(q('#sample-review canvas')+'?.dataset.fact==='+JSON.stringify(ref),'public source line');
      assert.equal(await evaluate(q('#sample-review output')+'.textContent'),'第 1 页 · 第 '+line+' 行');
      assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),file);
      await evaluate(q('#sample-review [data-scale="page"]')+'.click()');
      await evaluate(q('#sample-review form button')+'.click()');
      assert.equal(await evaluate('document.activeElement.dataset.ref'),ref);
    }
    for (const key of ['company','word','calendar']) {
      await evaluate(q('#signing-example')+'.value='+JSON.stringify(key)+';'+q('#signing-example')+'.dispatchEvent(new Event("change"))');
      assert.equal(await evaluate('new URL(location.href).searchParams.get("scene")'),{company:'signing',word:'word-signing',calendar:'contract-dates'}[key]);
      assert.equal(await evaluate(q('#signing-'+key)+'.hidden'),false);
    }
  }
  console.log('PASS · public calendar source and archived page, 3 physical lines at 5 widths');
}
