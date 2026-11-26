import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';

const widths=[1440,1024,820,768,390,320];
const q=selector=>'document.querySelector('+JSON.stringify(selector)+')';
const hash=bytes=>createHash('sha256').update(Buffer.from(bytes)).digest('hex');
async function size({call,evaluate},width) {
  await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:950,deviceScaleFactor:1,mobile:width<600});
  await evaluate('document.fonts.ready.then(()=>true)');
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'overflow at '+width);
}
async function inspect(ctx,width,label,focus,screenshot=false) {
  if (![390,1440].includes(width)) return;
  await ctx.evaluate('document.fonts.ready.then(()=>Promise.all(document.getAnimations().filter(a=>a.effect.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{})))).then(()=>true)');
  if (process.env.AUDIT_AXE_FILE) {
    await ctx.evaluate(await readFile(process.env.AUDIT_AXE_FILE,'utf8')+'\n;void 0');
    const violations=await ctx.evaluate('axe.run(document,{runOnly:{type:"tag",values:["wcag2a","wcag2aa","wcag21a","wcag21aa"]}}).then(r=>r.violations.map(v=>[v.id,v.nodes.map(n=>[n.target,n.failureSummary])]))');
    assert.deepEqual(violations,[],label+' '+width);console.log('axe',label,width);
  }
  if (screenshot && process.env.AUDIT_UI_SHOTS) {
    await ctx.evaluate(q(focus)+'.scrollIntoView({block:"center"})');
    const result=await ctx.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(process.env.AUDIT_UI_SHOTS,'supplier-'+label+'-'+width+'.png'),Buffer.from(result.data,'base64'));
  }
}

export async function checkSupplierPages(ctx,id,revision) {
  const {root,call,evaluate,wait}=ctx;
  const task=await (await fetch(root+'/api/cases/'+id)).json();
  const rev=revision || task.rev;
  const url=root+'/workpaper/'+id+'?rev='+rev+'&view=suppliers';
  const report=(await (await fetch(root+'/api/cases/'+id+'/reports/'+rev)).json()).report;
  const finding=report.findings.find(f=>f.rule==='H02'), check=finding.acceptance_reservations.supplier;
  const pages=report.graph.supplier_page_sources.pages.filter(p=>check.page_inspections.includes(p.id));
  const page=pages[0], label=page.annotations.some(a=>a.kind==='signature_reason')?'reason':check.status==='risk'?'different':page.state;
  await call('Page.navigate',{url});
  await wait(q('#supplier-pages')+'?.getClientRects().length && state.bundle?.rev==='+rev,'current supplier evidence');
  const tab=i=>q('#supplier-pages-tab-'+i);
  assert.equal(await evaluate(q('#supplier-pages')+'.dataset.state'),check.status);
  assert.equal(await evaluate('Boolean('+q('.supplier-legacy')+')'),report.policy.supplier_page_inspection==='pdf-supplier-pages-v1');
  const first=check.status==='missing' && pages.some(p=>p.state==='annotations')?1:0;
  assert.equal(await evaluate(tab(first)+'.getAttribute("aria-selected")'),'true');
  for (const width of widths) {
    await size(ctx,width);
    await evaluate(tab(1)+'.click()');
    assert.deepEqual(await evaluate('[...document.querySelectorAll("#supplier-pages .supplier-note blockquote")].map(n=>n.textContent)'),
      pages.flatMap(p=>p.annotations.flatMap(a=>[a.signing_reason && a.signing_reason+(a.reason_shortened?'…':''),a.note && a.note+(a.shortened?'…':'')].filter(Boolean))));
    await inspect(ctx,width,label+'-notes','#supplier-pages',true);
    const file=await evaluate(q('#supplier-pages .supplier-record-head a.supplier-file')+'.href');
    assert.ok(file.endsWith('/'+page.doc+'/original?rev='+rev));
    assert.equal(await evaluate(q('#supplier-pages .supplier-file[download]')+'.download'),report.graph.documents.find(d=>d.id===page.doc).name);
    if (width===1440) assert.equal(hash(await (await fetch(file)).arrayBuffer()),page.original_sha256);
    await wait(q('#supplier-pages .supplier-thumbnail img')+'?.naturalWidth>0','bound page thumbnail');
    await evaluate(q('#supplier-pages .supplier-thumbnail')+'.click()');
    await wait(q('#page-dialog')+'.open && '+q('#page-dialog .page-image')+'?.naturalWidth>0','full page');
    await evaluate(q('#page-dialog [data-close]')+'.click()');
    await evaluate(q('#supplier-pages .supplier-proof summary')+'.click()');
    assert.ok(await evaluate(q('#supplier-pages .supplier-proof dl')+'.innerText.includes('+JSON.stringify(page.page_sha256)+')'));
    if (page.state==='same_print') assert.ok(await evaluate(q('.supplier-proof dl')+'.innerText.includes('+JSON.stringify(page.comparison.original_sha256)+')'));
    const linked=report.findings.filter(f=>f.rule==='H01' ? f.effect_review?.pdf_execution?.source===page.signature_source && f.evidence.includes(page.signature_source) :
      ['H04','H05'].includes(f.rule) && f.stage && f.scope.includes(page.unit) && f.evidence.includes(page.id));
    assert.deepEqual(await evaluate('[...document.querySelectorAll("[data-supplier-related]")].map(b=>b.dataset.supplierRelated)'),linked.map(f=>f.id));
    if (width===1440 && linked.some(f=>f.rule==='H04')) {
      const phase=linked.find(f=>f.rule==='H04');
      await evaluate(q('.supplier-related summary')+'.click()');
      await evaluate(q('[data-supplier-related="'+phase.id+'"]')+'.click()');
      assert.equal(await evaluate('document.activeElement.dataset.finding'),phase.id);
      await evaluate('revealPaperTarget('+q('#supplier-pages')+')');
    }
    await evaluate(tab(1)+'.focus()');
    await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Home',windowsVirtualKeyCode:36});
    assert.equal(await evaluate('document.activeElement.id'),'supplier-pages-tab-0');
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".supplier-name")].map(n=>n.textContent)'),
      [...new Set(check.pages.map(p=>p.unit))].map(unit=>check.names[unit] || '名称待核'));
    await wait('document.querySelectorAll("#supplier-pages .supplier-strip canvas").length==='+check.lines.length,'cropped supplier lines');
    if (check.status==='risk' && Object.keys(check.names).length===2) {
      const toggle=q('#supplier-pages [role=switch]');
      assert.ok(await evaluate(toggle+'.checked && Boolean(document.querySelector(".supplier-name mark"))'));
      const names=await evaluate('[...document.querySelectorAll(".supplier-name")].map(n=>n.textContent)');
      await evaluate(toggle+'.click()');
      assert.ok(await evaluate('!document.querySelector(".supplier-name mark")'));
      assert.deepEqual(await evaluate('[...document.querySelectorAll(".supplier-name")].map(n=>n.textContent)'),names);
      await evaluate(toggle+'.click()');
    }
    await inspect(ctx,width,label+'-names','#supplier-pages',true);
    const buttons=await evaluate('document.querySelectorAll("#supplier-pages .supplier-location").length');
    for (let i=0;i<buttons;i++) {
      await evaluate('document.querySelectorAll("#supplier-pages .supplier-location")['+i+'].click()');
      await wait(q('#page-dialog')+'.open && '+q('#page-dialog .page-image')+'?.naturalWidth>0','fixed page');
      const row=check.lines[i], fact=report.graph.facts.find(f=>row.facts.includes(f.id) && f.quote===row.quote);
      assert.ok(await evaluate(q('#page-dialog')+'.textContent.includes('+JSON.stringify(row.quote)+')'));
      if (fact?.source_line?.rects?.length) {
        assert.equal(await evaluate(q('#page-dialog .evidence-row.located')+'.dataset.fact'),fact.id);
        const marks=await evaluate('[...document.querySelectorAll("#page-dialog .source-plane rect")].map(rect=>["x","y","width","height"].map(key=>Number(rect.getAttribute(key))))');
        assert.deepEqual(marks,fact.source_line.rects.map(([l,t,r,b])=>[1000*l,1000*t,1000*(r-l),1000*(b-t)]));
      }
      if (!i) await inspect(ctx,width,label+'-page','#page-dialog');
      await evaluate(q('#page-dialog [data-close]')+'.click()');
    }
    const draft=q('#supplier-pages .supplier-card-head button');
    const canDraft=rev===task.rev && task.status==='ready' && check.status!=='ok';
    assert.equal(await evaluate('Boolean('+draft+')'),canDraft);
    if (canDraft) {
      await evaluate(draft+'.click()');
      await wait(q('#review-dialog')+'.open','supplement draft');
      assert.equal(await evaluate(q('#review-decision')+'.value'),'return');
      assert.match(await evaluate(q('#review-note')+'.value'),check.status==='risk'?/委托交付/:label==='reason'?/签署原因/:/批注/);
      await inspect(ctx,width,label+'-draft','#review-dialog');
      await evaluate(q('#review-dialog [data-close]')+'.click()');
    }
  }
  await evaluate(q('#quick-open')+'.click()');
  await wait(q('#quick-dialog')+'.open','quick switcher');
  await evaluate(q('#quick-query')+'.value="核对供货主体";'+q('#quick-query')+'.dispatchEvent(new Event("input"))');
  await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Enter',windowsVirtualKeyCode:13});
  await wait('!'+q('#quick-dialog')+'.open && document.activeElement.id==="supplier-pages"','quick supplier command');
  const invalid=await evaluate('(()=>{const edits=[r=>r.graph.supplier_page_sources.pages[0].original_sha256="bad",r=>r.graph.supplier_page_sources.pages[0].unit="other",r=>r.calls.pages[0].page_sha256="bad",r=>r.graph.edges=r.graph.edges.filter(e=>e.type!=="supplier_page_source"),r=>r.graph.edges=r.graph.edges.filter(e=>e.type!=="supplier_identity_basis"),r=>r.policy.supplier_page_inspection="other"];return edits.every(edit=>{const r=structuredClone(state.bundle.report);edit(r);return SupplierPages.current(r)===null})})()');
  assert.ok(invalid,'evidence must belong to this version and unit');
  const after=await (await fetch(root+'/api/cases/'+id)).json();
  assert.equal(after.rev,task.rev);assert.deepEqual(after.decisions,task.decisions);
  console.log('checked supplier workpaper',label,'R'+rev,widths.join('/'));
}

export async function checkPublicSuppliers(ctx) {
  const {root,call,evaluate,wait}=ctx;
  const sample=await (await fetch(root+'/assets/supplier-sample.json')).json();
  for (const unit of sample.units) {
    const original=await fetch(root+unit.source.pdf);
    assert.equal(original.headers.get('content-type'),'application/pdf');
    assert.equal(hash(await original.arrayBuffer()),unit.source.source_sha256);
    assert.equal(hash(await (await fetch(root+unit.source.image)).arrayBuffer()),unit.source.page_sha256);
  }
  await call('Page.navigate',{url:root+'/?scene=suppliers#workflow'});
  await wait(q('#public-suppliers')+'?.getClientRects().length','public evidence');
  for (const width of widths) {
    await size(ctx,width);
    await evaluate(q('#public-suppliers-tab-1')+'.click()');
    assert.equal(await evaluate(q('#public-suppliers blockquote')+'.textContent'),sample.pages[0].annotations[0].signing_reason);
    await evaluate(q('#public-suppliers .supplier-thumbnail')+'.click()');
    await wait(q('#sample-review')+'.open && '+q('#sample-review [data-scale=page]')+'.getAttribute("aria-pressed")==="true"','public original page preview');
    await evaluate(q('#sample-review form button')+'.click()');
    await inspect(ctx,width,'public-notes','#scene-inspection',true);
    await evaluate(q('#public-suppliers-tab-0')+'.click()');
    await wait('document.querySelectorAll("#public-suppliers .supplier-strip img").length===2','two public source crops');
    await inspect(ctx,width,'public-names','#scene-inspection',true);
    for (const [i,u] of sample.units.entries()) {
      const opener='document.querySelectorAll("#public-suppliers .supplier-location")['+i+']';
      await evaluate(opener+'.click()');
      await wait(q('#sample-review')+'.open && '+q('#sample-review canvas')+'?.dataset.fact==='+JSON.stringify(u.rows[0].ref),'public cited line');
      assert.equal(await evaluate(q('#sample-review [data-ref][aria-pressed=true]')+'.dataset.rect'),u.source.lines.find(l=>l.ref===u.rows[0].ref).rect);
      assert.equal(await evaluate(q('#sample-review .sample-records a')+'.getAttribute("href")'),u.source.pdf);
      if (!i) await inspect(ctx,width,'public-source','#sample-review');
      await evaluate(q('#sample-review form button')+'.click()');
      assert.ok(await evaluate('document.activeElement==='+opener));
    }
    await evaluate(q('#inspection-example')+'.value="equipment";'+q('#inspection-example')+'.dispatchEvent(new Event("change"))');
    await wait(q('#inspection-demo .inspection-panel')+'?.getClientRects().length','device sample');
    assert.equal(await evaluate('new URL(location.href).searchParams.get("scene")'),'inspection');
    await evaluate(q('#inspection-example')+'.value="supplier";'+q('#inspection-example')+'.dispatchEvent(new Event("change"))');
    assert.equal(await evaluate('new URL(location.href).searchParams.get("scene")'),'suppliers');
  }
  console.log('checked public supplier cases',root,widths.join('/'));
}
