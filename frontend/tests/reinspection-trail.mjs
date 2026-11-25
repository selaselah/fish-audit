import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

const selector = s=>'document.querySelector('+JSON.stringify(s)+')';
const trail = '.reinspection-trail';

export async function checkReinspectionTrail({root,call,evaluate,wait},cid,requestedRev) {
  const api=root+'/api/cases/'+cid;
  const task=await (await fetch(api)).json();
  assert.ok(task.title.startsWith('合成演练 · ') && task.profile==='cn-contract-performance/v1');
  const rev=requestedRev || task.rev;
  const {report}=await (await fetch(api+'/reports/'+rev)).json();
  const finding=report.findings.find(f=>f.rule==='H02');
  const chain=finding.reinspection;
  assert.ok(chain?.steps.length);
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+rev+'&view=reinspection'});
  await wait(selector(trail)+'?.dataset.disposition==='+JSON.stringify(chain.state),'published reinspection trail');
  assert.equal(await evaluate('document.activeElement?.id'),'equipment-reinspection-trail');
  assert.ok(await evaluate(selector(trail)+'.open'));
  assert.equal(await evaluate('document.querySelectorAll('+JSON.stringify(trail)+').length'),1);
  assert.ok(await evaluate(selector(trail)+'.closest(".performance-overview")!==null'));
  const active='.trail-tab[aria-selected=true]';
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
    await evaluate(selector('#trail-tab-final')+'.click()');
    assert.equal(await evaluate('document.querySelectorAll(".trail-view:not([hidden])").length'),1);
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth && [...document.querySelectorAll(".trail-tab")].every(t=>t.offsetHeight>=44 && t.offsetWidth>=44)'));
    assert.ok(await evaluate('[...document.querySelectorAll(".trail-view:not([hidden]) .trail-source")].filter(c=>!c.closest("details:not([open])") && c.getClientRects().length).length<=2'));
    for (const [key,code,role] of [['Home',36,'original'],['ArrowRight',39,'repair'],['End',35,'final']]) {
      await evaluate(selector(active)+'.focus()');
      for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key,code:key,windowsVirtualKeyCode:code});
      assert.equal(await evaluate('document.activeElement?.id'),'trail-tab-'+role);
      assert.equal(await evaluate(selector(active)+'.getAttribute("aria-controls")'),'trail-view-'+role);
      const st=chain.steps.find(s=>s.role===role);
      if (!st) continue;
      assert.ok(await evaluate('['+selector('#trail-view-'+role)+','+selector('#trail-tab-'+role)+'].some(n=>n.innerText.includes('+JSON.stringify(st.date || '日期待核')+'))'));
      const card=selector('#trail-view-'+role+' .trail-source[data-cited-fact]');
      const factId=await evaluate(card+'?.dataset.citedFact');
      const fact=report.graph.facts.find(f=>f.id===factId);
      assert.ok(fact && st.evidence.includes(factId));
      await evaluate(card+'.click()');
      await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(factId),'pinned original '+role);
      await evaluate(selector('#page-dialog [data-close]')+'.click()');
      const hold=st.completion?.status!=='ok' && st.completion?.lines.find(s=>['qualification','unreviewed'].includes(s.kind) || s.kind==='date' && !st.completion.date);
      if (hold) {
        const note=selector('#trail-view-repair [data-repair-note="'+hold.kind+'"]');
        assert.equal(await evaluate(note+'?.title'),hold.quote);
        await evaluate(note+'.click()');
        await wait(selector('#page-dialog .located blockquote')+'?.textContent==='+JSON.stringify(hold.quote),'repair remark from original');
        await evaluate(selector('#page-dialog [data-close]')+'.click()');
      }
    }
    const compare=selector('#trail-view-final .trail-compare');
    const held=(chain.register?.lines || []).find(r=>r.line && !['clear','matched'].includes(r.kind));
    if (held) {
      assert.ok(await evaluate(compare));
      await evaluate(compare+'.click()');
      const controls='#page-dialog .trail-reader-pair button';
      await wait('document.querySelectorAll('+JSON.stringify(controls)+').length===2 && document.querySelector("#page-dialog .page-image")?.naturalWidth>0','same-page original');
      const outcome=report.graph.facts.find(f=>f.field==='acceptance_result' && f.doc===held.doc && f.page===held.page);
      assert.equal(await evaluate(selector(controls+'[aria-pressed=true]')+'.dataset.pairRef'),outcome.id);
      const input=os=>evaluate('document.querySelectorAll('+JSON.stringify(controls)+')['+os+'].click()');
      await input(1);
      await wait(selector('#page-dialog .located[data-gap-line] blockquote')+'?.textContent==='+JSON.stringify(held.quote),'same-page qualification');
      assert.ok(await evaluate(selector(controls+':last-of-type')+'.getAttribute("aria-pressed")==="true"'));
      if (width===1440 && process.env.AUDIT_UI_SHOTS) {
        await evaluate('document.fonts.ready.then(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))');
        const {data}=await call('Page.captureScreenshot',{format:'png'});
        await writeFile(join(process.env.AUDIT_UI_SHOTS,'reinspection-reader.png'),Buffer.from(data,'base64'));
      }
      await input(0);
      await wait(selector('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(outcome.id),'same-page signed conclusion');
      await evaluate(selector('#page-dialog [data-close]')+'.click()');
    } else assert.equal(await evaluate('Boolean('+compare+')'),false);
    if ((width===1440 || width===390) && process.env.AUDIT_UI_SHOTS) {
      await evaluate('document.activeElement?.blur()');
      await evaluate(selector(trail)+'.scrollIntoView({block:"center"})');
      await evaluate('document.fonts.ready.then(()=>Promise.all(document.getAnimations().filter(a=>a.effect?.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})))).then(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))');
      const clip=await evaluate('(()=>{const r='+selector(trail)+'.getBoundingClientRect();return {x:r.x+scrollX-4,y:r.y+scrollY-4,width:r.width+8,height:r.height+8,scale:1}})()');
      const {data}=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'reinspection-'+width+'.png'),Buffer.from(data,'base64'));
    }
  }
  await evaluate(selector('#trail-tab-final')+'.click()');
  await evaluate('document.querySelectorAll("#trail-view-final details").forEach(d=>d.open=true)');
  const sourceRows=chain.register?.lines || [];
  for (const row of sourceRows.filter(r=>r.line)) {
    const card=selector('#trail-view-final [data-register-line="'+row.line+'"][data-register-kind="'+row.kind+'"]');
    assert.equal(await evaluate(card+'?.title'),row.quote);
    await evaluate(card+'.click()');
    await wait('document.querySelector("#page-dialog").open && document.querySelector(".located[data-gap-line] blockquote")?.textContent==='+JSON.stringify(row.quote),'register note '+row.line);
    const href=await evaluate(selector('#page-dialog a[href*="/pages/"]')+'.href');
    assert.equal(href,api+'/documents/'+row.doc+'/pages/'+row.page+'?rev='+rev);
    const response=await fetch(href);
    assert.equal(response.status,200);
    assert.equal(createHash('sha256').update(Buffer.from(await response.arrayBuffer())).digest('hex'),
      report.graph.nodes.find(n=>n.id===row.doc+'/p'+row.page).sha256);
    if (row.facts.some(id=>report.graph.facts.find(f=>f.id===id)?.source_line?.number===row.line)) {
      assert.ok(await evaluate('document.querySelectorAll("#page-dialog svg rect").length>0'));
    }
    await evaluate(selector('#page-dialog [data-close]')+'.click()');
  }
  const held=sourceRows.filter(r=>!['clear','matched'].includes(r.kind));
  if (held.length===1) {
    const note=held[0];
    const phases=report.findings.filter(f=>f.rule==='H04' && f.stage);
    for (const phase of phases) {
      const applicable=phase.status!=='ok' && phase.scope.includes(note.unit) && phase.evidence.includes(note.doc+'/p'+note.page);
      const entry=selector('[data-register-phase="'+phase.id+'"]');
      assert.equal(await evaluate('Boolean('+entry+')'),applicable);
      if (!applicable) continue;
      await evaluate(selector('#phase-choice-'+phase.id)+'.click()');
      await evaluate(entry+'.click()');
      await wait(selector('#page-dialog .located blockquote')+'?.textContent==='+JSON.stringify(note.quote),'phase-specific register evidence');
      await evaluate(selector('#page-dialog [data-close]')+'.click()');
    }
  }
  if (!chain.register) assert.equal(await evaluate('document.querySelectorAll("[data-register-kind]").length'),0);
  await call('Page.navigate',{url:'about:blank'});
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+rev});
  await wait(selector(trail)+'?.dataset.disposition==='+JSON.stringify(chain.state),'ordinary report entry');
  assert.equal(await evaluate(selector(trail)+'.open'),chain.state!=='closed' || finding.status!=='ok');
  if (sourceRows.length) {
    assert.ok(await evaluate(`(()=>{
      const f=state.bundle.report.findings.find(f=>f.rule==='H02');
      const g=structuredClone(state.bundle.report.graph);
      g.edges=g.edges.filter(e=>e.type!=='reinspection_register_line');
      const p=ReinspectionTrail.panel(f,g);
      return p.dataset.disposition==='unverified' && !p.querySelector('[data-register-kind],.trail-compare') && p.textContent.includes('原件关系待核');
    })()`));
  }
  console.log('PASS · '+task.title+' R'+rev+' · 3 stages, 6 viewport widths, '+sourceRows.length+' register lines, keyboard and revision-scoped originals');
}
