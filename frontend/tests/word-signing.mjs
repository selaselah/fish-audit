import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {createHash} from 'node:crypto';

export async function checkWordSigning({root,call,evaluate,wait},id,version) {
  const get=async path=>(await fetch(root+'/api/cases/'+id+path)).json();
  const detail=await get(''), rev=version || detail.rev, {report}=await get('/reports/'+rev);
  assert.ok(detail.title.startsWith('合成演练 · '));
  const finding=report.findings.find(f=>f.rule==='H01');
  const q=s=>'document.querySelector('+JSON.stringify(s)+')';
  await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev='+rev+'&view=signatures'});
  await wait(q('.performance-overview')+'?.offsetWidth>0','performance workpaper');
  const check=finding.effect_review?.word_signatures;
  if (!check) {
    assert.equal(await evaluate('!!'+q('#word-signatures')),false);
    console.log('PASS · Historical workpaper preserved'); return;
  }
  await wait(q('#word-signatures')+'?.open','signature disclosure opened from fixed link');
  const rows=check.rows.map(s=>({...s,source:report.graph.contract_effect_sources.signing_rows.find(r=>r.id===s.row)}));
  const tab=i=>q('#word-signing-tab-'+i);
  for (const width of [1440,1024,768,390,360,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
    await evaluate(tab(0)+'.click();'+tab(0)+'.focus()');
    for (const [i,s] of rows.entries()) {
      if (i) {
        await evaluate(tab(i-1)+'.focus()');
        await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'ArrowRight',windowsVirtualKeyCode:39});
        await call('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',windowsVirtualKeyCode:39});
        assert.equal(await evaluate('document.activeElement.id'),'word-signing-tab-'+i);
      }
      await wait(q('.word-reading')+'?.dataset.row==='+JSON.stringify(s.row),'party source selected');
      await wait('!!'+q('.word-line canvas'),'actual cropped page');
      assert.equal(await evaluate(tab(i)+'.getAttribute("aria-selected")'),'true');
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'));
      assert.ok(await evaluate(q('.word-excerpt')+'.getAttribute("aria-label")').then(t=>t.includes(s.source.quote)));
      const edit=s.state==='field' && rev===detail.rev;
      if (process.env.AUDIT_UI_SHOTS && i===0 && [390,1440].includes(width)) {
        const rect=await evaluate('(()=>{const b='+q('#word-signatures')+'.getBoundingClientRect();return {x:b.x+scrollX,y:b.y+scrollY,width:b.width,height:b.height,scale:1};})()');
        const shot=await call('Page.captureScreenshot',{format:'png',clip:rect,captureBeyondViewport:true});
        await writeFile(join(process.env.AUDIT_UI_SHOTS,'sign-'+id.slice(0,5)+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
      }
      await evaluate(q('.word-excerpt')+'.click()');
      await wait(q('#page-dialog')+'.open && '+q('.source-plane img')+'?.naturalWidth>0 && !!'+q('.source-plane svg rect')+' && '+q('.located')+'?.dataset.gapLine==='+JSON.stringify(String(s.source.line)),'actual line in original');
      assert.equal(await evaluate(q('.located blockquote')+'.textContent'),s.source.quote);
      const original=await evaluate(q('#page-dialog .source-tools a')+'.href');
      assert.ok(original.endsWith('/pages/'+s.source.page+'?rev='+rev));
      if (width===1440) {
        const bytes=await (await fetch(original)).arrayBuffer();
        const page=report.graph.nodes.find(n=>n.id===s.source.doc+'/p'+s.source.page);
        assert.equal(createHash('sha256').update(Buffer.from(bytes)).digest('hex'),page.sha256);
      }
      if (edit) {
        const change=q('.located [data-word-edit]');
        assert.equal(await evaluate(change+'.dataset.wordEdit'),s.row);
        await evaluate(change+'.click()');
        await wait(q('#amend-dialog')+'.open && !'+q('#amend-submit')+'.disabled','source ready to correct');
        assert.equal(await evaluate(q('#amend-field')+'.value'),s.source.field);
        assert.equal(await evaluate(q('#amend-quote')+'.value'),s.source.quote);
        const coordinates=report.graph.facts.find(f=>f.id===s.fact).source_line.rects.map(([l,t,r,b])=>
          [l,t,r-l,b-t].map(n=>String(n*1000)));
        assert.deepEqual(await evaluate('[...document.querySelectorAll("#amend-marks rect")].map(r=>["x","y","width","height"].map(k=>r.getAttribute(k)))'),coordinates);
        assert.equal(await evaluate(q('#amend-original')+'.tabIndex'),0);
        assert.equal(await evaluate(q('#amend-value')+'.value'),'');
        assert.equal(await evaluate('state.amend.target'),s.fact);
        await evaluate(q('#amend-dialog [data-close]')+'.click()');
      } else {
        if (rev!==detail.rev) assert.equal(await evaluate('!!'+q('#word-signatures [data-word-edit]')),false);
        await evaluate(q('#page-dialog [data-close]')+'.click()');
      }
      const expected=report.findings.filter(f=>['H04','H05'].includes(f.rule) && f.evidence.includes(s.row)).map(f=>f.id);
      assert.deepEqual(await evaluate('[...document.querySelectorAll("[data-word-phase]")].map(b=>b.dataset.wordPhase)'),expected);
      if (expected.length && i===0) {
        await evaluate(q('[data-word-phase]')+'.click()');
        assert.equal(await evaluate('document.activeElement.dataset.finding'),expected[0]);
      }
    }
    if (detail.rev===rev) {
      await evaluate(q('.word-draft')+'.click()');
      assert.equal(await evaluate(q('#review-decision input:checked')+'.value'),'return');
      assert.ok((await evaluate(q('#review-note')+'.value')).includes(detail.documents.find(d=>d.id===check.pages[0].split('/')[0]).name));
      await evaluate(q('#review-dialog [data-close]')+'.click()');
    } else assert.equal(await evaluate('!!'+q('.word-draft')),false);
  }
  assert.deepEqual((await get('')).decisions,detail.decisions);
  for (const corrupt of ['page','extraPage','edge','classification','receipt']) {
    const visible=await evaluate('(()=>{const r=structuredClone(state.bundle.report), f=r.findings.find(x=>x.rule==="H01"), w=f.effect_review.word_signatures, s=w.rows[0];'+
      ({page:'r.calls.pages.find(x=>x.doc==="d01" && x.page===1).clause_text_only=false;',
        extraPage:'w.pages.push("d01/p2");',
        edge:'r.graph.edges=r.graph.edges.filter(e=>!(e.from===s.row && e.to==="finding/"+f.id));',
        classification:'s.state="unknown";',receipt:'s.receipt_rev=10000;'})[corrupt]+
      'return !!WordSigning.panel(f,r.graph,r.findings,r.calls.pages);})()');
    assert.equal(visible,false,corrupt);
  }
  console.log('PASS · '+rows.map(r=>r.state).join('/')+' · both original lines, linked payment findings and fixed revision at six widths');
}

export async function checkPublicWordSigning({root,call,evaluate,wait}) {
  const page='/assets/showcase-word-signing-page.jpg', original='/showcase/signing-text.docx';
  for (const [path,sha] of [[page,'b22afb14f83e9a80fc635518e167bbb9465df63a0939572197c2cf2bd6789a70'],
                            [original,'1902b237402d810010cc477e6327368dba4e32d50da4f610d3188180ef78b184']]) {
    const res=await fetch(root+path); assert.equal(res.status,200);
    if (path===original) {
      assert.match(res.headers.get('content-type'),/wordprocessingml\.document/u);
      assert.match(res.headers.get('content-disposition'),/^attachment/u);
    }
    assert.equal(createHash('sha256').update(Buffer.from(await res.arrayBuffer())).digest('hex'),sha);
  }
  assert.equal((await fetch(root+'/showcase/other.docx')).status,404);
  const q=s=>'document.querySelector('+JSON.stringify(s)+')';
  await call('Page.navigate',{url:root+'/?scene=word-signing#workflow'});
  await wait(q('#signing-example')+'?.value==="word" && !'+q('#scene-signing')+'?.hidden','public Word sample');
  assert.equal(await evaluate('performance.getEntriesByType("resource").some(r=>r.name.endsWith('+JSON.stringify(page)+'))'),false);
  for (const width of [320,390,600,768,1024,1440]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
    assert.ok(await evaluate(q('#scene-signing')+'.scrollWidth<='+q('#scene-signing')+'.clientWidth+1'));
    assert.match(await evaluate(q('#signing-example-version')+'.textContent'),/R6/u);
    await evaluate(q('.word-sample-thumbnail')+'.click()');
    await wait(q('#sample-review canvas')+'?.dataset.fact==="d01/p1/f10"','thumbnail opens the physical signing page');
    assert.equal(await evaluate(q('#sample-review [data-scale="page"]')+'.getAttribute("aria-pressed")'),'true');
    await evaluate(q('#sample-review form button')+'.click()');
    for (const [suffix,line] of [[9,10],[10,11],[11,12]]) {
      const ref='d01/p1/f'+suffix, anchor=q('#signing-word .public-signing-lines [data-ref="'+ref+'"]');
      await evaluate(anchor+'.click()');
      await wait(q('#sample-review canvas')+'?.dataset.fact==='+JSON.stringify(ref),'original Word line');
      assert.equal(await evaluate(q('#sample-review output')+'.textContent'),'第 1 页 · 第 '+line+' 行');
      assert.equal(await evaluate(q('#sample-review [data-scale="line"]')+'.getAttribute("aria-pressed")'),'true');
      const source=q('#sample-review .sample-records a');
      assert.equal(await evaluate(source+'.pathname'),original);
      assert.equal(await evaluate(q('#sample-review .sample-file-kind')+'.textContent'),'下载 Word 原件');
      await evaluate(q('#sample-review [data-scale="page"]')+'.click()');
      await evaluate(q('#sample-review form button')+'.click()');
      assert.equal(await evaluate('document.activeElement.dataset.ref'),ref);
    }
    await evaluate(q('#signing-example')+'.value="company";'+q('#signing-example')+'.dispatchEvent(new Event("change"))');
    assert.equal(await evaluate('new URL(location.href).searchParams.get("scene")'),'signing');
    await evaluate(q('#signing-company [data-ref]')+'.click()');
    await wait(q('#sample-review canvas')+'?.dataset.fact==="d02/p1/f3"','separate company comparison');
    assert.equal(await evaluate(q('#sample-review .sample-file-kind')+'.textContent'),'原始 PDF');
    await evaluate(q('#sample-review form button')+'.click()');
    await evaluate(q('#signing-example')+'.value="word";'+q('#signing-example')+'.dispatchEvent(new Event("change"))');
    assert.equal(await evaluate('new URL(location.href).searchParams.get("scene")'),'word-signing');
  }
}
