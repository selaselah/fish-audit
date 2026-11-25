import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {join} from 'node:path';
import {writeFile} from 'node:fs/promises';

export async function checkSigningImages({call,evaluate,wait,q},report,rev) {
  const finding=report.findings.find(f=>f.rule==='H01');
  const pages=report.graph.contract_effect_sources?.format==='contract-effect-sources-v5' ?
    finding?.effect_review?.mixed_pages.filter(p=>p.kind!=='board_approval') || [] : [];
  const rail=q('.seal-pages'), inspector=q('.seal-inspector');
  assert.equal(await evaluate(rail+'!==null'),Boolean(pages.length));
  if (!pages.length) return 0;
  const entries=finding.effect_review.party_seals || [];
  const side=entries.find(r=>r.status==='risk') || entries.find(r=>r.status!=='ok') || entries[0];
  function citedPages(record) {
    const selected=report.graph.contract_effect_sources.signing_rows.filter(r=>record?.evidence.includes(r.id));
    for (const role of ['imprint','signature','party']) {
      const matches=pages.filter(p=>selected.some(r=>r.role===role && r.doc===p.doc && r.page===p.page));
      if (matches.length) return matches;
    }
    return [];
  }
  const initial=citedPages(side)[0] || pages[0];
  const initialIndex=pages.indexOf(initial), picker=q('.seal-page-picker');
  assert.equal(await evaluate(rail+'.dataset.page'),initial.doc+'/p'+initial.page);
  for (const p of pages) {
    const i=pages.indexOf(p);
    if (pages.length>1) await evaluate(picker+'.selectedIndex='+i+';'+picker+'.dispatchEvent(new Event("change"))');
    await wait(rail+'.dataset.preview==="image" && '+q('.seal-thumb img')+'.naturalWidth>0','archived contract thumbnail');
    assert.equal(await evaluate(rail+'.dataset.page'),p.doc+'/p'+p.page);
    const thumb=q('.seal-preview-link');
    await evaluate(thumb+'.focus()');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    const dialog=q('#page-dialog');
    await wait(dialog+'.open && '+q('#page-dialog .page-image')+'?.naturalWidth>0','open entire contract page');
    const url=await evaluate(q('#page-dialog .source-tools a')+'.href');
    assert.equal(new URL(url).searchParams.get('rev'),String(rev));
    assert.ok(new URL(url).pathname.endsWith('/documents/'+p.doc+'/pages/'+p.page));
    const bytes=Buffer.from(await (await fetch(url)).arrayBuffer());
    assert.equal(createHash('sha256').update(bytes).digest('hex'),report.graph.nodes.find(n=>n.id===p.doc+'/p'+p.page).sha256);
    assert.equal(await evaluate('document.querySelectorAll("#page-dialog svg rect").length'),0);
    await evaluate(dialog+'.close()');
    assert.ok(await evaluate('document.activeElement==='+thumb));
  }
  if (pages.length>1) {
    for (const record of entries) {
      await evaluate(q('.seal-side[data-side="'+record.side+'"]')+'.click()');
      const own=citedPages(record);
      if (own.length) assert.ok(own.map(p=>p.doc+'/p'+p.page).includes(await evaluate(rail+'.dataset.page')));
    }
    if (side) await evaluate(q('.seal-side[data-side="'+side.side+'"]')+'.click()');
    await evaluate(picker+'.selectedIndex='+initialIndex+';'+picker+'.dispatchEvent(new Event("change"))');
    await wait(rail+'.dataset.preview==="image"','return to signing page');
  }
  for (const width of [320,390,600,768,1024,1440]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
    assert.ok(await evaluate('['+rail+','+inspector+','+q('.seal-preview-link')+'].every(n=>n.scrollWidth<=n.clientWidth+1)'),'contract source fits '+width);
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'workpaper fits '+width);
    assert.ok(await evaluate('(()=>{const frame=document.querySelector(".seal-thumb").getBoundingClientRect(),image=document.querySelector(".seal-thumb img").getBoundingClientRect(),label=document.querySelector(".seal-open-label").getBoundingClientRect();return image.top>=frame.top-1 && image.bottom<=frame.bottom+1 && (image.right<=label.left+1 || image.bottom<=label.top+1)})()'),'thumbnail and action stay separate at '+width);
    if (width===390) {
      await evaluate(q('.seal-preview-link')+'.click()');
      await wait(q('#page-dialog .page-image')+'?.naturalWidth>0','mobile original');
      await evaluate(q('#page-dialog [aria-label="放大原页"]')+'.click()');
      assert.equal(await evaluate(q('#page-dialog .zoom-scale')+'.textContent'),'125%');
      await evaluate(q('#page-dialog .zoom-fit')+'.click();'+q('#page-dialog')+'.close()');
    }
    if (!entries.length && process.env.AUDIT_UI_SHOTS && [390,1440].includes(width)) {
      await evaluate(inspector+'.scrollIntoView({block:"center"})');
      const clip=await evaluate('(()=>{const r='+inspector+'.getBoundingClientRect();return {x:r.left+scrollX,y:r.top+scrollY,width:r.width,height:r.height,scale:1}})()');
      const image=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'source-'+report.case_id+'-R'+rev+'-'+width+'.png'),Buffer.from(image.data,'base64'));
    }
  }
  for (const record of entries.filter(r=>r.comparison.length)) {
    const row=record.field_sources.find(s=>['image','mixed'].includes(s.kind) && record.comparison.includes(s.row));
    if (!row) continue;
    for (const variant of ['receipt','digest','owner','origin',...(row.kind==='image'?['geometry']:[])]) {
      const status=await evaluate(`(()=>{
        const report=structuredClone(state.bundle.report),graph=report.graph,finding=report.findings.find(f=>f.rule==='H01');
        const side=finding.effect_review.party_seals.find(r=>r.side===${JSON.stringify(record.side)});
        const origin=side.field_sources.find(s=>s.row===${JSON.stringify(row.row)}),fact=graph.facts.find(f=>f.id===origin.fact);
        switch (${JSON.stringify(variant)}) {
          case 'receipt': fact.attestation.source_check.report_hash='0'.repeat(64); break;
          case 'digest': fact.page_sha256='0'.repeat(64); break;
          case 'owner': graph.edges=graph.edges.filter(e=>!(e.from===side.unit && e.type===fact.field && e.evidence.includes(fact.id))); break;
          case 'origin': origin.receipt_rev=99; break;
          case 'geometry': fact.source_line={number:1,text:fact.quote,rects:[[.1,.2,.7,.3]]}; break;
        }
        const panel=SigningParties.panel(finding,graph,[]);
        panel.querySelector('.seal-side[data-side="'+side.side+'"]').click();
        return [panel.dataset.status,Boolean(panel.querySelector('.seal-compare')),SigningParties.pagePairs(finding,graph).some(p=>p.key==='signing-'+side.side)];
      })()`);
      assert.deepEqual(status,['missing',false,false],variant);
    }
  }
  const disconnected=await evaluate(`(()=>{
    const report=structuredClone(state.bundle.report),graph=report.graph,finding=report.findings.find(f=>f.rule==='H01');
    const ids=new Set(finding.effect_review.mixed_pages.map(p=>p.doc+'/p'+p.page));
    graph.edges=graph.edges.filter(e=>e.type!=='supports_result' || !ids.has(e.from) || e.to!=='finding/'+finding.id);
    return Boolean(SigningParties.panel(finding,graph,[])?.querySelector('.seal-pages'));
  })()`);
  assert.equal(disconnected,false,'detached pages cannot become evidence shortcuts');
  for (const record of entries) {
    await evaluate(q('.seal-side[data-side="'+record.side+'"]')+'.click()');
    const endpoints=record.comparison.map(ref=>record.field_sources.find(s=>s.row===ref));
    const facts=endpoints.map(s=>report.graph.facts.find(f=>f.id===s.fact));
    const compare=q('.seal-compare');
    const cross=facts.length===2 && facts.every(Boolean) && (facts[0].doc!==facts[1].doc || facts[0].page!==facts[1].page) &&
      endpoints.some(s=>['image','mixed'].includes(s.kind));
    assert.equal(await evaluate(compare+'!==null'),cross);
    if (!cross) continue;
    await evaluate(compare+'.click()');
    await wait('document.querySelectorAll(".compare-original canvas").length===2','both original sources');
    assert.equal(await evaluate('document.activeElement.dataset.pair'),'signing-'+record.side);
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".compare-leaf")].map(n=>n.dataset.fact)'),facts.map(f=>f.id));
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".compare-quote blockquote")].map(n=>n.textContent)'),facts.map(f=>f.quote));
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".compare-scan")].map(n=>n.dataset.located)'),facts.map(f=>String(Boolean(f.source_line?.rects?.length))));
    if (record.state==='different') assert.ok(await evaluate(q('.compare-quote mark')+'?.textContent.length>0'));
    for (const width of [390,1440]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
      const fits=await evaluate('[...document.querySelectorAll(".compare-scan canvas")].every(canvas=>{const image=canvas.getBoundingClientRect(),frame=canvas.parentElement.getBoundingClientRect();return image.bottom<=frame.bottom+1 && image.top>=frame.top-1 && image.right<=frame.right+1})');
      assert.ok(fits,'both evidence images fit at '+width);
      if (process.env.AUDIT_UI_SHOTS && record.state==='different' && width===1440) {
        const spread=q('.compare-spread');await evaluate(spread+'.scrollIntoView({block:"center"})');
        const clip=await evaluate('(()=>{const r='+spread+'.getBoundingClientRect();return {x:r.left+scrollX,y:r.top+scrollY,width:r.width,height:r.height,scale:1}})()');
        const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
        await writeFile(join(process.env.AUDIT_UI_SHOTS,'spread-'+report.case_id+'-R'+rev+'.png'),Buffer.from(shot.data,'base64'));
      }
    }
    await evaluate('document.querySelectorAll(".compare-original")[1].click()');
    await wait(q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(facts[1].id),'compared field opens its original');
    await evaluate(q('#page-dialog')+'.close();'+q('#tabs [data-tab=report]')+'.click()');
    await wait(inspector,'return to contract');
  }
  if (side) await evaluate(q('.seal-side[data-side="'+side.side+'"]')+'.click()');
  if (!entries.length) {
    const source=await evaluate('new URL(workpaperSource('+JSON.stringify(initial.doc)+',"pages/'+initial.page+'"),location.href).href');
    await call('Network.enable'); await call('Network.setBlockedURLs',{urls:[source]});
    await call('Page.reload',{ignoreCache:true});
    await wait(rail+'?.dataset.preview==="error"','unavailable contract source');
    await call('Network.setBlockedURLs',{urls:[]});
    const retry=q('.seal-retry'); await evaluate(retry+'.focus()');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    await wait(rail+'.dataset.preview==="image" && document.activeElement.matches(".seal-preview-link")','keyboard retry restores source');
  }
  return pages.length;
}
