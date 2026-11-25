import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';

export async function checkReinspectionTiming({root,call,evaluate,wait},cid,version) {
  const api=root+'/api/cases/'+cid, task=await (await fetch(api)).json();
  assert.ok(task.title.startsWith('合成演练 · ') && task.profile==='cn-contract-performance/v1');
  const rev=version || task.rev;
  const {report}=await (await fetch(api+'/reports/'+rev)).json();
  const h=report.findings.find(f=>f.rule==='H02'), timing=h.reinspection.timing;
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+rev+'&view=reinspection'});
  await wait(q('#equipment-reinspection-trail')+'?.open','published revision');
  if (!timing) {
    assert.equal(await evaluate('Boolean('+q('#reinspection-wait')+')'),false);
    console.log('PASS · 历史 R'+rev+' 按原底稿显示'); return;
  }
  const selector='#reinspection-wait', card=q(selector), source=q(selector+' .wait-open');
  const rows=report.graph.reinspection_wait_sources.lines;
  await evaluate(q('#trail-tab-final')+'.click()');
  await wait(card+'?.dataset.timingState==='+JSON.stringify(timing.state),'verified waiting condition');
  const hasStart=timing.start_ref!==null;
  assert.equal(await evaluate(q('.wait-switch button:last-child')+'.textContent'),hasStart?'复验开始':'复验单日期');
  assert.equal(await evaluate(q('.wait-metric strong')+'.textContent'),'≥ '+timing.required_hours+'小时');
  assert.equal(await evaluate(q('.wait-values')+'.children.length'),hasStart?2:1);
  const expected=new Map([['met','> 49小时14分< 49小时16分'],['early','> 46小时59分< 47小时1分'],
    ['boundary','> 24小时< 72小时'],['report_early','< 48小时'],['start_missing','< 120小时'],
    ['operation_pending','> 49小时14分< 49小时16分']]);
  assert.equal(await evaluate(q('.wait-values')+'.textContent'),expected.get(timing.state));
  if (!hasStart) assert.ok((await evaluate(q('.wait-metric:last-child > span')+'.textContent')).includes('复验单日期'));
  if (timing.state==='operation_pending') assert.ok((await evaluate(q('.wait-state')+'.textContent')).includes('试运行'));
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:false});
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth && [...document.querySelectorAll(".wait-switch button,.wait-open")].every(b=>b.offsetWidth>=44 && b.offsetHeight>=44)'));
    for (const [key,keyCode,ref] of [['Home',36,timing.term_ref],['ArrowRight',39,timing.repair_ref],['End',35,timing.start_ref || timing.report_ref]]) {
      await evaluate(q('.wait-switch button[aria-pressed=true]')+'.focus()');
      for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key,code:key,windowsVirtualKeyCode:keyCode});
      assert.ok(await evaluate('document.activeElement.matches(".wait-switch button[aria-pressed=true]")'));
      const row=rows.find(r=>r.id===ref);
      assert.equal(await evaluate(source+'.dataset.timingRef'),ref);
      assert.equal(await evaluate(source+'.querySelector("strong").textContent'),row.quote);
      assert.ok(await evaluate(source+'.getClientRects().length===1'));
      await evaluate(source+'.click()');
      await wait(q('#page-dialog .located blockquote')+'?.textContent==='+JSON.stringify(row.quote)+' && '+q('#page-dialog .page-image')+'?.naturalWidth>0','pinned evidence '+row.kind);
      assert.equal(await evaluate(q('#page-dialog .located')+'.dataset.gapLine'),String(row.line));
      const image=await evaluate(q('#page-dialog .page-image')+'.getAttribute("src")');
      const original=await evaluate(q('#page-dialog a[target=_blank]')+'.href');
      const url=new URL(original);
      assert.ok(url.pathname.endsWith('/'+row.doc+'/pages/'+row.page));
      assert.equal(url.searchParams.get('rev'),String(rev));
      if (width===1440) {
        const hash=createHash('sha256').update(Buffer.from(await (await fetch(original)).arrayBuffer())).digest('hex');
        assert.equal(hash,row.page_sha256);
      }
      const exact=row.facts.map(id=>report.graph.facts.find(f=>f.id===id)).find(f=>f?.source_line?.number===row.line && f.source_line.rects.length);
      if (exact) assert.ok(await evaluate('document.querySelectorAll("#page-dialog svg rect").length>0'));
      assert.ok(image);
      await evaluate(q('#page-dialog [data-close]')+'.click()');
    }
    if ((width===1440 || width===390) && process.env.AUDIT_UI_SHOTS) {
      await evaluate(q('.wait-switch button:first-child')+'.click()');
      await evaluate(card+'.scrollIntoView({block:"center"}); document.activeElement?.blur(); document.fonts.ready.then(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))');
      const clip=await evaluate('(()=>{const r='+q('#equipment-reinspection-trail')+'.getBoundingClientRect();return {x:r.x+scrollX-4,y:r.y+scrollY-4,width:r.width+8,height:r.height+8,scale:1}})()');
      const {data}=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'retest-'+timing.state+'-'+width+'.png'),Buffer.from(data,'base64'));
    }
  }
  const phaseRows=report.findings.filter(f=>f.rule==='H04');
  for (const phase of phaseRows) {
    const jump=q('[data-timing-phase="'+phase.id+'"]');
    const applies=phase.status!=='ok' && phase.evidence.includes(timing.term_ref);
    assert.equal(await evaluate('Boolean('+jump+')'),applies);
    if (applies) {
      await evaluate(q('#phase-choice-'+phase.id)+'.click()');
      await evaluate(jump+'.click()');
      assert.equal(await evaluate('document.activeElement.id'),'reinspection-wait');
      assert.equal(await evaluate(q('#trail-tab-final')+'.getAttribute("aria-selected")'),'true');
    }
  }
  assert.ok(await evaluate(`(()=>{
    const h=state.bundle.report.findings.find(f=>f.rule==='H02'), g=structuredClone(state.bundle.report.graph);
    const altered=structuredClone(h); altered.reinspection.timing.below_seconds+=60;
    if (ReinspectionTiming.panel(altered,g).dataset.timingState!=='unverified') return false;
    g.edges=g.edges.filter(e=>e.type!=='reinspection_time_basis');
    const p=ReinspectionTrail.panel(h,g);
    return p.dataset.disposition==='unverified' && p.querySelector('.wait-state').textContent==='证据关系待核'
      && !p.querySelector('.wait-metrics,.wait-open');
  })()`));
  console.log('PASS · '+task.title+' R'+rev+' · '+timing.state+' · 6 widths, keyboard, exact source pages and payment links');
}
