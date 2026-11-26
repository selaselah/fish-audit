import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';

const widths=[1440,1024,820,768,390,320];
const q=selector=>'document.querySelector('+JSON.stringify(selector)+')';
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');

async function layout(ctx,width) {
  await ctx.call('Emulation.setDeviceMetricsOverride',{width,height:width<=390?844:950,deviceScaleFactor:1,mobile:width<600});
  await ctx.evaluate('document.fonts.ready.then(()=>true)');
  assert.ok(await ctx.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'horizontal overflow at '+width);
}

async function capture(ctx,name,width,selector) {
  if (!process.env.AUDIT_UI_SHOTS || ![390,1440].includes(width)) return;
  await ctx.evaluate(q(selector)+'.scrollIntoView({block:"center"})');
  const shot=await ctx.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  await writeFile(join(process.env.AUDIT_UI_SHOTS,'signatures-'+name+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
}

async function accessible(ctx,name,width) {
  if (!process.env.AUDIT_AXE_FILE || ![390,1440].includes(width)) return;
  await ctx.evaluate('document.fonts.ready.then(()=>true)');
  await ctx.evaluate('Promise.all(document.getAnimations().filter(a=>a.effect.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{}))).then(()=>true)');
  const source=await readFile(process.env.AUDIT_AXE_FILE,'utf8');
  await ctx.evaluate(source+'\n;void 0');
  const failures=await ctx.evaluate('axe.run(document,{runOnly:{type:"tag",values:["wcag2a","wcag2aa","wcag21a","wcag21aa"]}}).then(r=>r.violations.map(v=>[v.id,v.nodes.map(n=>[n.target,n.failureSummary])]))');
  assert.deepEqual(failures,[],name+' at '+width);console.log(name,width,'axe clear');
}

export async function checkPdfCase(ctx,id,revision) {
  const {root,call,evaluate,wait}=ctx;
  const task=await (await fetch(root+'/api/cases/'+id)).json();
  const rev=revision || task.rev;
  const report=(await (await fetch(root+'/api/cases/'+id+'/reports/'+rev)).json()).report;
  const effect=report.findings.find(f=>f.rule==='H01'), check=effect.effect_review.pdf_execution;
  const record=report.graph.pdf_execution_sources.documents.find(r=>r.id===check.source);
  const rows=report.graph.contract_effect_sources.signing_rows.filter(r=>check.rows.includes(r.id));
  const rootId='#pdf-signatures', tab=n=>q(rootId+'-tab-'+n);
  await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev='+rev+'&view=signatures'});
  await wait(q(rootId)+'?.getClientRects().length && state.bundle?.rev==='+rev,'PDF signature source');
  const url=await evaluate(q(rootId+' .pdf-signature-head a')+'.href');
  assert.ok(url.endsWith('/'+record.doc+'/original?rev='+rev));
  assert.equal(hash(Buffer.from(await (await fetch(url)).arrayBuffer())),record.original_sha256);
  for (const width of widths) {
    await layout(ctx,width);
    await evaluate(tab(1)+'.click()');
    assert.match(await evaluate(q(rootId+' .pdf-timeline')+'.textContent'),record.signatures.length?/PDF 修订/u:/未检出/u);
    await accessible(ctx,'签名覆盖 '+check.state,width);
    await capture(ctx,check.state,width,rootId);
    await evaluate(q(rootId+' .pdf-technical summary')+'.click()');
    assert.ok(await evaluate(q(rootId+' .pdf-facts')+'.innerText.includes('+JSON.stringify(record.original_sha256)+')'));
    await accessible(ctx,'签名明细 '+check.state,width);
    await evaluate(tab(1)+'.focus()');
    await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'End',windowsVirtualKeyCode:35});
    assert.equal(await evaluate('document.activeElement.id'),'pdf-signatures-tab-2');
    assert.equal(await evaluate(q(rootId+' .pdf-basis')+'.href'),report.policy.sources['electronic-signature'].url);
    if (await evaluate('Boolean('+q(rootId+' .pdf-authority button')+')')) {
      const requirement=await evaluate(q('.pdf-authority p')+'.textContent');
      await evaluate(q('.pdf-authority button')+'.click()');
      await wait(q('#review-dialog')+'.open','supplement draft');
      assert.equal(await evaluate(q('#review-note')+'.value'),requirement);
      await accessible(ctx,'补件草稿 '+check.state,width);
      await evaluate(q('#review-dialog [data-close]')+'.click()');
    }
    await evaluate(tab(0)+'.click()');
    assert.equal(await evaluate('document.querySelectorAll("#pdf-signatures .pdf-original-lines button").length'),rows.length);
    if (rows.length) {
      const anchored=rows.some(row=>report.graph.facts.some(f=>row.facts.includes(f.id) && f.source_line?.text===row.quote && f.source_line?.rects?.length));
      if (anchored) await wait(q('#pdf-signatures .pdf-line-quote canvas')+'?.width>0','verified page pixels');
      await evaluate(q('.pdf-original-lines button')+'.click()');
      await wait(q('#page-dialog')+'.open && '+q('#page-dialog .page-image')+'?.naturalWidth>0','original');
      assert.ok(await evaluate(q('#page-dialog')+'.textContent.includes('+JSON.stringify(rows[0].quote)+')'));
      await accessible(ctx,'签署原页 '+check.state,width);
      await evaluate(q('#page-dialog [data-close]')+'.click()');
    }
    const linked=await evaluate('[...document.querySelectorAll("[data-pdf-phase]")].map(b=>b.dataset.pdfPhase)');
    assert.deepEqual(linked,report.findings.filter(f=>['H04','H05'].includes(f.rule) && f.stage && f.evidence.includes(record.id)).map(f=>f.id));
    if (linked.length) {
      await evaluate(q('[data-pdf-phase]')+'.click()');
      assert.equal(await evaluate('document.activeElement.dataset.finding'),linked[0]);
    }
  }
  await evaluate(q('#quick-open')+'.click()');
  await wait(q('#quick-dialog')+'.open','workpaper command palette');
  await evaluate(q('#quick-query')+'.value="签署凭证";'+q('#quick-query')+'.dispatchEvent(new Event("input"))');
  await call('Input.dispatchKeyEvent',{type:'rawKeyDown',key:'Enter',windowsVirtualKeyCode:13});
  await wait('!'+q('#quick-dialog')+'.open && document.activeElement.id==="pdf-signatures"','signature command');
  const detached=await evaluate('(()=>{const r=structuredClone(state.bundle.report),f=r.findings.find(f=>f.rule==="H01");r.graph.pdf_execution_sources.documents[0].original_sha256="bad";return PdfSignatures.panel(f,r.graph,r.findings,r.calls.pages)===null})()');
  assert.ok(detached);
  const after=await (await fetch(root+'/api/cases/'+id)).json();assert.deepEqual(after.decisions,task.decisions);
  assert.equal(after.rev,task.rev);
}

export async function checkPublicPdf(ctx) {
  const {root,call,evaluate,wait}=ctx;
  const samples=await (await fetch(root+'/assets/pdf-signing-samples.json')).json();
  await call('Page.navigate',{url:root+'/?scene=pdf-signing#workflow'});
  await wait(q('#public-pdf-signatures')+'?.dataset.state==="earlier"','public signed revision');
  for (const mode of ['typeset','current','earlier']) {
    const sample=samples[mode];
    const contents=await (await fetch(root+sample.original)).arrayBuffer();
    assert.equal(hash(Buffer.from(contents)),sample.record.original_sha256);
    for (const width of widths) {
      await layout(ctx,width);
      await evaluate(q('[data-pdf-mode="'+mode+'"]')+'.click()');
      assert.equal(await evaluate(q('#public-pdf-signatures')+'.dataset.state'),mode);
      assert.equal(await evaluate('new URL(location.href).searchParams.get("pdf")'),mode);
      assert.equal(await evaluate(q('#signing-example-version')+'.textContent'),'合成案例 · R'+sample.revision);
      await evaluate(q('#public-pdf-signatures-tab-1')+'.click()');
      await accessible(ctx,'首页 PDF '+mode,width);
      if (mode==='earlier') await capture(ctx,'public',width,'#signing-pdf');
      await evaluate(q('#public-pdf-signatures-tab-0')+'.click()');
      await wait(q('.pdf-line-quote img')+'?.naturalWidth>0','archived source crop');
      if (mode==='typeset') await capture(ctx,'public-lines',width,'#signing-pdf');
      assert.deepEqual(await evaluate('[...document.querySelectorAll(".pdf-original-lines a .pdf-line-literal")].map(a=>a.textContent)'),sample.rows.map(r=>r.quote));
    }
  }
  await call('Page.navigate',{url:root+'/?scene=pdf-signing&pdf=current#workflow'});
  await wait(q('#public-pdf-signatures')+'?.dataset.state==="current"','shared public version');
  await evaluate(q('#tab-contract')+'.click()');
  assert.match(await evaluate(q('#sheet-contract .evidence-note')+'.textContent'),/签署凭证待核/);
  assert.match(await evaluate(q('#sample-phase-1')+'.textContent'),/签署待核/);
}
