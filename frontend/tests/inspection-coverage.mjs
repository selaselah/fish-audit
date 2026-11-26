import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {inspect} from './review-screen.mjs';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const widths=[320,390,600,768,1024,1440];
async function screenshot({call,evaluate},selector,name) {
  if (!process.env.AUDIT_UI_SHOTS) return;
  await evaluate(q(selector)+'.scrollIntoView({block:"center"});document.activeElement.blur()');
  const clip=await evaluate('(()=>{const r='+q(selector)+'.getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}})()');
  const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
  await writeFile(join(process.env.AUDIT_UI_SHOTS,name+'.png'),Buffer.from(shot.data,'base64'));
}
async function hash(url) {
  const res=await fetch(url); assert.equal(res.status,200);
  return createHash('sha256').update(Buffer.from(await res.arrayBuffer())).digest('hex');
}

export async function checkInspectionCoverage(driver,cid,fixed) {
  const {root,call,evaluate,wait}=driver;
  const api=root+'/api/cases/'+cid, detail=await (await fetch(api)).json();
  assert.match(detail.title,/^合成演练 · /);
  const rev=Number(fixed || detail.rev);
  const {report,sha256}=await (await fetch(api+'/reports/'+rev)).json();
  const accepted=report.findings.find(f=>f.rule==='H02');
  const proof=accepted.inspection_coverage;
  const panel=q('.inspection-panel');
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+rev});
  await wait(q('.performance-overview')+' && state.bundle.rev==='+rev,'fixed workpaper');
  const pending=report.findings.filter(f=>f.status!=='ok');
  assert.deepEqual(await evaluate('[...document.querySelectorAll(".findings-ledger .finding:not([hidden])")].map(e=>e.dataset.finding)'),
    (pending.length?pending:report.findings).map(f=>f.id));
  const experts=report.findings.filter(f=>f.rule==='X01');
  if (experts.length>1) {
    const group=q('.expert-group');
    assert.equal(await evaluate(group+'.open'),false);
    assert.equal(await evaluate(group+'.querySelector(".expert-count").textContent'),experts.length+' 项');
    const row=q('[data-finding="'+experts[0].id+'"]');
    await evaluate(q('[data-finding-filter=ok]')+'.click();revealPaperTarget('+row+')');
    assert.ok(await evaluate(group+'.open && document.activeElement==='+row+' && !'+row+'.hidden'));
    await evaluate(group+'.open=false;'+row+'.querySelector("details").open=false;'+q('[data-finding-filter=pending]')+'.click()');
  }
  if (!proof) {
    assert.equal(await evaluate(panel+'===null'),true);
    console.log('PASS · archived R'+rev+' before unit-level inspections'); return;
  }
  assert.equal(await evaluate(panel+'.dataset.inspectionState'),proof.state);
  assert.equal(await evaluate(panel+'.open'),proof.state!=='covered');
  if (proof.named) {
    const view='/workpaper/'+cid+'?rev='+rev+'&view=inspection';
    if (detail.rev===rev) {
      await call('Page.navigate',{url:root+'/app#desk'});
      const search=q('#case-search'), peek=q('[data-preview-case="'+cid+'"]');
      await wait(search+'?.getClientRects().length && Desk.fingerprint','workspace search');
      await evaluate(search+'.value='+JSON.stringify(detail.title)+';'+search+'.dispatchEvent(new Event("input",{bubbles:true}))');
      await wait(peek+'!=null','synthetic case in the workspace'); await evaluate(peek+'.click()');
      const inspect=q('#case-preview .preview-check[href="'+view+'"]');
      await wait(inspect+'?.getClientRects().length','receipt review from the preview'); await evaluate(inspect+'.click()');
    } else await call('Page.navigate',{url:root+view});
    await wait(q('#inspection-coverage')+'?.open && document.activeElement==='+panel,'direct link to the device review');
    assert.ok(await evaluate(panel+'.checkVisibility()'));
  } else await evaluate('revealPaperTarget('+panel+')');
  if (proof.named) {
    const quick=q('#quick-query');
    await evaluate(q('#quick-open')+'.click();'+quick+'.value="核对验收设备";'+quick+'.dispatchEvent(new Event("input"))');
    await wait(q('#quick-results [role=option]')+'?.textContent.includes("核对验收设备")','device review in quick navigation');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter'});
    await wait('!'+q('#quick-dialog')+'.open && document.activeElement==='+panel,'return from quick navigation');
  }
  const read=report.graph.inspection_coverage_sources.rows;
  const chosen=await evaluate(panel+'.dataset.selectedDevice');
  if (proof.named) {
    const expected=proof.named.equipment.length-proof.named.missing.length;
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".inspection-total meter")].map(m=>[m.value,m.max])'),
      [[Math.min(proof.tested,proof.required),proof.required],[expected,proof.named.equipment.length]]);
    assert.equal(await evaluate(q('.inspection-filter [aria-pressed=true]')+'.dataset.scope'),proof.named.equipment.includes(chosen)?'named':'all');
    await wait(q('.inspection-proof-pair .inspection-strip canvas')+'?.width>0','original pixels from the fixed workpaper');
    const linked=report.findings.filter(f=>['H04','H05'].includes(f.rule) && f.evidence.includes(proof.named.row));
    const active=q('.phase-choice[aria-selected=true]');
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".inspection-payments [data-jump-finding]")].map(b=>b.dataset.jumpFinding).sort()'),
      linked.map(f=>f.id).sort());
    const payment=linked.find(f=>f.rule==='H05');
    if (payment) {
      assert.equal(await evaluate(active+'.dataset.phaseChoice'),linked.find(f=>f.rule==='H04' && f.stage.clause_ref===payment.stage.clause_ref).id);
      await evaluate(q('.inspection-payments')+'.open=true;'+q('.inspection-payments [data-jump-finding="'+payment.id+'"]')+'.click()');
      assert.equal(await evaluate('document.activeElement.dataset.finding'),payment.id);
      const last=linked.filter(f=>f.rule==='H04').at(-1);
      await evaluate(q('.inspection-payments [data-jump-finding="'+last.id+'"]')+'.click()');
      assert.equal(await evaluate(active+'.dataset.phaseChoice'),last.id);
      await evaluate(q('.inspection-payments [data-jump-finding="'+payment.id+'"]')+'.click()');
      await evaluate('revealPaperTarget('+panel+');'+q('.inspection-payments')+'.open=false');
    }
    await evaluate(q('.inspection-filter [data-scope=all]')+'.click()');
  }
  if (proof.tested!=null) {
    assert.equal(await evaluate(q('.inspection-metric strong')+'.innerText'),String(proof.tested));
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".inspection-devices [data-device]")].map(b=>b.dataset.device)'),proof.equipment);
    assert.equal(await evaluate(q('.inspection-required')+'.innerText.includes('+JSON.stringify(String(proof.required))+')'),true);
  }
  const ids=proof.tested==null?['']:proof.equipment;
  const opened=new Set();
  for (const id of ids) {
    if (id) {
      await evaluate(q('[data-device="'+id+'"]')+'.click()');
      assert.equal(await evaluate(panel+'.dataset.selectedDevice'),id);
      const measured=proof.measurements.filter(m=>m.serial===id).map(m=>m.row);
      const links=await evaluate('[...document.querySelectorAll(".inspection-source")].map(n=>n.dataset.inspectionSource)');
      assert.ok(measured.every(ref=>links.includes(ref)));
    }
    for (const ref of await evaluate('[...document.querySelectorAll(".inspection-source")].map(n=>n.dataset.inspectionSource)')) {
      if (opened.has(ref)) continue;
      opened.add(ref);
      const row=read.find(r=>r.id===ref);
      const button=q('[data-inspection-source="'+ref+'"]');
      await evaluate(button+'.focus();'+button+'.click()');
      await wait(q('#page-dialog')+'.open && '+q('#page-dialog img.page-image')+'?.naturalWidth>0 && '+q('#page-dialog .located'),'cited observation or native line');
      const endpoint=await evaluate(q('#page-dialog .source-tools a')+'.href');
      assert.equal(new URL(endpoint).searchParams.get('rev'),String(rev));
      assert.ok(new URL(endpoint).pathname.endsWith('/documents/'+row.doc+'/pages/'+row.page));
      assert.equal(await hash(endpoint),report.graph.nodes.find(n=>n.id===row.doc+'/p'+row.page).sha256);
      const location=await evaluate('({...'+q('#page-dialog .located')+'.dataset})');
      if (location.fact) {
        assert.ok(row.facts.includes(location.fact));
        const fact=report.graph.facts.find(f=>f.id===location.fact);
        assert.equal(fact.source_line.number,row.line); assert.equal(fact.source_line.text,row.quote);
      } else assert.equal(location.gapLine,String(row.line));
      await evaluate(q('#page-dialog')+'.close()');
    }
  }
  if (chosen) {
    const tab=q('[data-device="'+ids[0]+'"]');
    await evaluate(tab+'.focus()');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'End',code:'End'});
    assert.equal(await evaluate('document.activeElement.dataset.device'),ids.at(-1));
    await evaluate(q('[data-device="'+chosen+'"]')+'.click()');
    for (const corrupt of ['edge','reading','support','page','quantity','parent','record','missing_list',...(proof.named?['named','clause','gap','omitted']:[])]) {
      const result=await evaluate('(()=>{const g=structuredClone(state.bundle.report.graph),f=structuredClone(state.bundle.report.findings.find(f=>f.rule==="H02")),c=f.inspection_coverage;'+
        ({edge:'g.edges=g.edges.filter(e=>e.type!=="inspection_coverage_source");',
          reading:'g.inspection_coverage_sources.rows[0].quote+="?";',
          support:'g.edges=g.edges.filter(e=>!(e.type==="supports_result" && e.from===g.inspection_coverage_sources.rows[0].id));',
          page:'g.inspection_coverage_sources.pages[0].text_only=false;',
          parent:'g.edges=g.edges.filter(e=>e.type!=="contains");',
          record:'g.edges=g.edges.filter(e=>e.type!=="records");',
          missing_list:'delete c.equipment;',
          named:'c.named.equipment.reverse();',
          clause:'c.named.row=c.measurements[0].row;',
          gap:'c.named.missing.push("QC-99");',
          omitted:'delete c.named;',
          quantity:'c.tested++;'}[corrupt])+
        'const p=InspectionCoverage.panel(f,g);return [p.dataset.inspectionState,!!p.querySelector(".inspection-metric")];})()');
      assert.deepEqual(result,['unknown',false],corrupt);
    }
    const large=await evaluate('(()=>{const c=structuredClone(state.bundle.report.findings.find(f=>f.rule==="H02").inspection_coverage);'+
      'c.equipment.push("EX-05","EX-06","EX-07");const p=InspectionCoverage.deviceView(c,[],()=>null);p.querySelector("[data-scope=all]")?.click();const s=p.querySelector("select");'+
      's.value="EX-07";s.dispatchEvent(new Event("change"));return [s.options.length,p.dataset.selectedDevice];})()');
    assert.deepEqual(large,[proof.equipment.length+3,'EX-07']);
    if (proof.measurements.length) {
      const ref=proof.measurements[0].row, raw=read.find(r=>r.id===ref);
      // The original text can contain a reading the extractor did not index. Exercise that path in memory.
      await evaluate('(()=>{window.originalInspectionGraph=state.bundle.report.graph;const g=structuredClone(window.originalInspectionGraph);'+
        'const r=g.inspection_coverage_sources.rows.find(r=>r.id==='+JSON.stringify(ref)+');r.facts=[];'+
        'const e=g.edges.find(e=>e.type==="inspection_coverage_source" && e.to===r.id);e.evidence=[e.from];'+
        'state.bundle.report.graph=g;InspectionCoverage.open(r,g);})()');
      await wait(q('#page-dialog .located')+'?.dataset.gapLine==='+JSON.stringify(String(raw.line)),'native source without a field candidate');
      assert.ok(await evaluate(q('#page-dialog .located')+'.textContent.includes('+JSON.stringify(raw.quote)+')'));
      assert.equal(await evaluate('document.querySelectorAll("#page-dialog svg rect").length'),0);
      await evaluate(q('#page-dialog')+'.close();state.bundle.report.graph=window.originalInspectionGraph;delete window.originalInspectionGraph');
    }
  }
  if (proof.named) {
    await evaluate(q('.inspection-filter [data-scope=named]')+'.click();'+q('[data-device="'+chosen+'"]')+'?.click()');
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".inspection-devices [role=tab]")].map(b=>b.dataset.device)'),proof.named.equipment);
  }
  for (const width of widths) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && '+panel+'.scrollWidth<='+panel+'.clientWidth+1'));
    if ([390,1440].includes(width)) {
      if (proof.named) await inspect(driver,width,'.inspection-panel','device-workpaper-'+proof.state);
      await screenshot(driver,'.inspection-panel','inspection-'+(proof.mode || 'unknown')+'-'+proof.state+'-'+width);
      if (proof.state==='short' && width===1440) await screenshot(driver,'.findings-ledger','inspection-findings-'+width);
    }
  }
  if (proof.state==='short' && cid==='08fdfa388dce4718a4cd46dada1385d8') await checkPublicInspection(driver,report);
  if (proof.named && proof.state==='named_records') {
    const published=await (await fetch(root+'/assets/named-inspection.json')).json();
    if (published.case_id===cid && published.rev===rev) {
      assert.equal(published.report_sha256,sha256);
      await checkPublicInspection(driver,report,true);
    }
  }
  console.log('PASS · R'+rev+' · '+proof.state+' · '+opened.size+' verified source actions · six widths');
}

export async function checkPublicInspection(driver,report,named=false) {
  const {root,call,evaluate,wait}=driver;
  const slug=named?'named-inspection':'inspection';
  const container=named?'#named-inspection-demo':'#inspection-demo';
  const sample=await (await fetch(root+'/assets/'+(named?'named-inspection':'showcase-inspection')+'.json')).json();
  if (report) {
    const proof=report.findings.find(f=>f.rule==='H02').inspection_coverage;
    assert.deepEqual(sample.check.measurements,proof.measurements);
    if (named) {
      assert.equal(sample.case_id,report.case_id);
      assert.deepEqual(sample.check,Object.fromEntries(Object.entries(proof).filter(([k])=>!['detail','evidence','scope'].includes(k))));
      const keys=['id','doc','unit','page','line','kind','quote'];
      assert.deepEqual(sample.rows,report.graph.inspection_coverage_sources.rows.map(r=>Object.fromEntries(keys.map(k=>[k,r[k]]))));
    }
  }
  for (const [id,doc] of Object.entries(sample.documents)) {
    assert.equal(await hash(root+doc.pdf),doc.source_sha256);
    assert.equal(await hash(root+doc.image),doc.page_sha256);
    if (report) {
      assert.equal(doc.source_sha256,report.graph.documents.find(d=>d.id===id).sha256);
      assert.equal(doc.page_sha256,report.graph.nodes.find(n=>n.id===id+'/p1').sha256);
      if (named) for (const line of doc.lines) {
        const row=report.graph.inspection_coverage_sources.rows.find(r=>r.id===line.ref);
        assert.equal(row.doc,id); assert.equal(row.line,line.line);
        assert.equal(line.label+'：'+line.value,row.quote);
        const fact=report.graph.facts.find(f=>row.facts.includes(f.id) && f.source_line?.number===line.line && f.source_line.text===row.quote);
        assert.deepEqual(line.rects,fact.source_line.rects);
      }
    }
  }
  await call('Page.navigate',{url:root+'/?scene='+slug+'#workflow'});
  await wait(q(container+' .inspection-panel')+'?.dataset.inspectionState==='+JSON.stringify(sample.check.state),'interactive public sample');
  if (named) await wait('[...document.querySelectorAll("'+container+' .inspection-strip img")].filter(i=>i.naturalWidth>0).length===2','two original source excerpts');
  assert.equal(await evaluate('performance.getEntriesByType("resource").filter(e=>/showcase-inspection-.+jpg/.test(e.name)).length'),0);
  for (const width of widths) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    await evaluate(q(container+' [data-device="'+(named?'QC-02':'QC-01')+'"]')+'.click()');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'));
    const tabs=await evaluate('[...document.querySelectorAll(".file-tabs button")].map(b=>{const r=new Range();r.selectNodeContents(b.lastChild);return [b.innerText,r.getClientRects().length,b.getBoundingClientRect().height]})');
    assert.ok(tabs.every(([,lines,height])=>lines===1 && height>=44),'file tab labels fit at '+width+' '+JSON.stringify(tabs));
    if ([768,1024].includes(width)) {
      assert.ok(await evaluate('(()=>{const h=document.querySelector("#hero-title");return h.clientHeight<=2*parseFloat(getComputedStyle(h).lineHeight)+2})()'),'two-line heading at '+width);
    }
    if ([390,1440].includes(width)) {
      if (named) await inspect(driver,width,container,'public-named-inspection');
      await screenshot(driver,'.workflow-demo','landing-'+slug+'-'+width);
    }
  }
  if (named) {
    assert.equal(await evaluate(q(container+' .inspection-panel')+'.dataset.selectedDevice'),'QC-02');
    const all=q(container+' [data-scope=all]');
    await evaluate(q(container+' [data-scope=named]')+'.focus()');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight'});
    assert.equal(await evaluate(all+'.getAttribute("aria-pressed")'),'true');
    assert.ok(await evaluate('document.activeElement==='+all));
    assert.deepEqual(await evaluate('[...document.querySelectorAll("'+container+' [data-device][data-required=true]")].map(b=>b.dataset.device)'),sample.check.named.equipment);
  }
  for (const id of named?sample.check.equipment:['QC-01','QC-02']) {
    await evaluate(q(container+' [data-device="'+id+'"]')+'.click()');
    for (const ref of await evaluate('[...document.querySelectorAll("'+container+' .inspection-source")].map(a=>a.dataset.inspectionSource)')) {
      const row=sample.rows.find(r=>r.id===ref), opener=q(container+' [data-inspection-source="'+ref+'"]');
      await evaluate(opener+'.click()');
      await wait(q('#sample-review')+'.open && '+q('#sample-review canvas')+'.dataset.fact==='+JSON.stringify(ref),'public original line');
      assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),sample.documents[row.doc].pdf);
      assert.equal(await evaluate(q('#sample-review output')+'.textContent'),'第 1 页 · 第 '+row.line+' 行');
      await evaluate(q('#sample-review')+'.close()');
      await wait('document.activeElement==='+opener,'return to evidence source button');
    }
  }
}
