import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

export async function checkWarrantyPhotos({root,call,evaluate,wait},cid,revision) {
  const api=root+'/api/cases/'+cid, task=await (await fetch(api)).json(), rev=Number(revision || task.rev);
  assert.ok(task.title.startsWith('合成演练 · '));
  const scan=task.title.includes('两页扫描'), file=scan?'售后附件扫描件.pdf':'报修附件.jpg', num=scan?2:1;
  const doc=task.documents.find(d=>d.name===file), {report}=await (await fetch(api+'/reports/'+rev)).json(),g=report.graph;
  const phase=report.findings.find(f=>f.rule==='H04' && f.warranty_check);
  const url=root+'/workpaper/'+cid+'?rev='+rev, q=s=>'document.querySelector('+JSON.stringify(s)+')';
  const panel='[data-phase-finding="'+phase.id+'"] .ticket-image-review', area=q(panel), locate=s=>q(panel+' '+s);
  const dialog=q('#page-dialog'), sheet=q('#page-dialog .image-sheet'), original=q('#page-dialog .page-image');
  const left=q('[aria-label="向左旋转 90°"]'), right=q('[aria-label="向右旋转 90°"]');
  const click=expr=>evaluate(expr+'.click()'), close=()=>click(q('#page-dialog [data-close]'));
  const width=async w=>call('Emulation.setDeviceMetricsOverride',{width:w,height:900,deviceScaleFactor:1,mobile:false});
  async function shot(name,element) {
    if (!process.env.AUDIT_UI_SHOTS) return;
    const clip=await evaluate('(()=>{const b='+element+'.getBoundingClientRect();return{x:b.x+scrollX,y:b.y+scrollY,width:b.width,height:b.height,scale:1}})()');
    const result=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
    await writeFile(join(process.env.AUDIT_UI_SHOTS,(scan?'scan':'photo')+'-R'+rev+'-'+name+'.png'),Buffer.from(result.data,'base64'));
  }
  const byteHash=async path=>createHash('sha256').update(Buffer.from(await (await fetch(path)).arrayBuffer())).digest('hex');
  const pageUrl=(n)=>api+'/documents/'+doc.id+'/pages/'+n+'?rev='+rev;
  const pageNode=n=>g.nodes.find(node=>node.id===doc.id+'/p'+n);
  await call('Page.navigate',{url});
  const stage=q('[data-phase-choice="'+phase.id+'"]');
  await wait(stage,'issued workpaper'); await click(stage);
  if (!phase.warranty_check.tickets?.length) {
    assert.ok(scan && report.policy.warranty_checks==='contract-warranty-release-v3');
    assert.equal(await evaluate(area),null);
    console.log('PASS · old scan has no work-order finding · R'+rev); return;
  }
  assert.equal(phase.status,'missing');
  assert.ok(!g.edges.some(e=>e.type==='warranty_release_basis' || e.type==='warranty_ticket_comparison'));
  const unit=phase.warranty_check.tickets.find(t=>t.evidence.includes(doc.id+'/p'+num)); assert.equal(unit.state,'scope');
  const key=doc.id+'/p'+num;
  await wait(area+'?.dataset.preview==="image"','work-order page thumbnail');
  assert.equal(await evaluate(area+'.dataset.page'),key);
  const facts=g.facts.filter(f=>f.doc===doc.id && f.page===num);
  const stateFact=facts.find(f=>f.field==='warranty_ticket_state');
  const stateButton=locate('[data-scan-fact="'+stateFact.id+'"]');
  assert.equal(await evaluate(stateButton+'.querySelector("strong").textContent'),stateFact.value);
  assert.equal(await evaluate(stateButton+'.querySelector(".scan-receipt").textContent'),stateFact.status==='confirmed'?'已核图':'待核图');
  if (scan) {
    assert.ok(await evaluate(locate('[data-scan-gap=warranty_closed_by]')));
    const picker=locate('.scan-page-picker'); assert.equal(await evaluate(picker+'.selectedIndex'),1);
    await evaluate(picker+'.selectedIndex=0;'+picker+'.dispatchEvent(new Event("change"))');
    await wait(area+'.dataset.preview==="image" && '+area+'.dataset.page.endsWith("/p1")','cover thumbnail');
    assert.equal(await evaluate(locate('[data-scan-fact]')),null);
    await click(locate('.scan-open-page'));
    await wait(dialog+'.open && '+original+'?.naturalWidth>0 && '+q('#page-title')+'.textContent.endsWith("第 1 页")','cover original');
    await close();
    await evaluate(picker+'.selectedIndex=1;'+picker+'.dispatchEvent(new Event("change"))');
    await wait(area+'.dataset.preview==="image" && '+area+'.dataset.page.endsWith("/p2")','body original');
  }
  const disclosure=q('[data-phase-finding="'+phase.id+'"] .ticket-disclosure');
  assert.equal(await evaluate(locate('.scan-field-details')+'.getClientRects().length'),0);
  await click(disclosure);
  const buttons=await evaluate('[...'+area+'.querySelectorAll("[data-scan-fact]")].map(b=>b.dataset.scanFact)');
  for (const id of buttons) {
    assert.ok(unit.evidence.includes(id) && phase.evidence.includes(id));
    assert.ok(await evaluate(locate('[data-scan-fact="'+id+'"]')+'.getClientRects().length'));
    await click(locate('[data-scan-fact="'+id+'"]'));
    await wait(dialog+'.open && '+original+'?.naturalWidth>0 && '+q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(id),'exact image observation');
    assert.equal(await evaluate(q('#page-dialog svg rect')),null);
    await close();
  }
  await click(disclosure);
  if (stateFact.status==='confirmed') {
    for (const hash of ['page_sha256','original_sha256','report_hash']) {
      const stale=await evaluate(`(()=>{
        const r=structuredClone(state.bundle.report),p=r.findings.find(f=>f.id===${JSON.stringify(phase.id)}),t=p.warranty_check.tickets[0];
        const f=r.graph.facts.find(f=>f.id===${JSON.stringify(stateFact.id)});
        f.attestation.source_check[${JSON.stringify(hash)}]='0'.repeat(64);
        const panel=WarrantyImages.panel(p,t,r.graph.warranty_sources,graphIndex(r.graph));
        return panel.querySelector('[data-scan-fact="'+f.id+'"] .scan-receipt').textContent;
      })()`);
      assert.equal(stale,'待核图',hash);
    }
  }
  const detached=await evaluate(`(()=>{
    const r=structuredClone(state.bundle.report),p=r.findings.find(f=>f.id===${JSON.stringify(phase.id)}),t=p.warranty_check.tickets[0];
    const ref=${JSON.stringify(stateFact.id)};
    r.graph.edges=r.graph.edges.filter(e=>!(e.from===ref && e.type==='supports_result' && e.to==='finding/'+p.id));
    const panel=WarrantyImages.panel(p,t,r.graph.warranty_sources,graphIndex(r.graph));
    return Boolean(panel?.querySelector('[data-scan-fact="'+ref+'"]'));
  })()`);
  assert.equal(detached,false);
  for (const w of [320,390,600,768,1024,1440]) {
    await width(w); await evaluate(area+'.scrollIntoView({block:"center"})');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),w);
    assert.ok(await evaluate('[...'+area+'.querySelectorAll("button,select")].every(n=>n.getBoundingClientRect().right<='+area+'.getBoundingClientRect().right+1)'),w);
    if ([390,1440].includes(w)) await shot('panel-'+w,area+'.closest(".phase-evidence")');
    await click(stateButton); await wait(sheet+'?.dataset.turn==="0"','original orientation');
    await click(left);
    assert.equal(await evaluate(sheet+'.dataset.turn'),'3');
    const size=await evaluate('(()=>{const b='+sheet+'.getBoundingClientRect();return [b.width/b.height,'+original+'.naturalHeight/'+original+'.naturalWidth]})()');
    assert.ok(Math.abs(size[0]-size[1])<.015,w);
    await click(q('[aria-label="放大原页"]'));
    await click(right);
    assert.equal(await evaluate(q('.zoom-scale')+'.textContent'),'125%');
    for (let n=0;n<4;n++) await click(q('[aria-label="放大原页"]'));
    assert.equal(await evaluate(q('.zoom-scale')+'.textContent'),'400%');
    await click(q('.zoom-fit')); await click(left);
    assert.equal(await evaluate(q('#page-dialog svg rect')),null);
    if (!scan && w===390) await shot('oriented-mobile',q('.viewer-original'));
    await close();
  }
  // The versioned page route and the archived source agree before and after display transforms.
  for (let n=1;n<=num;n++) assert.equal(await byteHash(pageUrl(n)),pageNode(n).sha256);
  assert.equal(await byteHash(api+'/documents/'+doc.id+'/original?rev='+rev),doc.sha256);
  await call('Network.enable');
  await call('Network.setBlockedURLs',{urls:[pageUrl(num)]});
  await call('Page.navigate',{url});
  await wait(stage,'report with unavailable thumbnail'); await click(stage);
  await wait(area+'?.dataset.preview==="error"','thumbnail error on the indicated page');
  assert.equal(await evaluate(area+'.dataset.page'),key);
  await click(stateButton);
  await wait(q('#page-dialog .source-error')+'?.getClientRects().length','recoverable page error');
  assert.ok(await evaluate(left+'.disabled && '+right+'.disabled'));
  assert.equal(await evaluate('[...document.querySelectorAll("#page-dialog .evidence-row input")].filter(n=>!n.disabled).length'),0);
  await call('Network.setBlockedURLs',{urls:[]});
  const enter=async button=>{
    await evaluate(button+'.focus()');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  };
  await enter(q('#page-dialog .source-error button'));
  await wait(sheet+'.dataset.turn==="0" && '+original+'.naturalWidth>0 && !'+left+'.disabled','retry the same fixed page');
  assert.equal(await evaluate(q('#page-dialog .located')+'.dataset.fact'),stateFact.id);
  assert.equal(await evaluate('document.activeElement.matches(".source-scroll")'),true);
  await close();
  await enter(locate('.scan-image-source .ref'));
  await wait(area+'.dataset.preview==="image" && '+locate('.scan-thumb img')+'.naturalWidth>0','thumbnail retry after connection restored');
  assert.equal(await evaluate('document.activeElement.matches(".scan-open-page")'),true);
  const anchored=g.facts.find(f=>f.source_line?.rects?.length && f.doc!==doc.id);
  await call('Page.navigate',{url:url+'&fact='+encodeURIComponent(anchored.id)});
  await wait(dialog+'.open && '+sheet+'?.dataset.turn==="0" && '+q('.image-sheet rect'),'native printed line before rotation');
  let [x0,y0,x1,y1]=anchored.source_line.rects[0];
  for (let n=0;n<4;n++) {
    await click(right);
    [x0,y0,x1,y1]=[1-y1,x0,1-y0,x1];
    const coords=await evaluate('(()=>{const p='+sheet+'.getBoundingClientRect(),b='+q('.image-sheet rect')+'.getBoundingClientRect();return [(b.left-p.left)/p.width,(b.top-p.top)/p.height,(b.right-p.left)/p.width,(b.bottom-p.top)/p.height]})()');
    for (const [i,v] of [x0,y0,x1,y1].entries()) assert.ok(Math.abs(coords[i]-v)<.008,[coords,v]);
  }
  await close();
  assert.deepEqual((await (await fetch(api)).json()).decisions,[]);
  console.log('PASS · '+(scan?'scan':'photo')+' R'+rev+' · page '+num+' · '+stateFact.status+' · six widths, rotation, receipts and retry');
}
