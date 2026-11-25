import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

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
  const {report}=await (await fetch(api+'/reports/'+rev)).json();
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
  await evaluate(panel+'.open=true');
  const read=report.graph.inspection_coverage_sources.rows;
  const chosen=await evaluate(panel+'.dataset.selectedDevice');
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
    for (const corrupt of ['edge','reading','support','page','quantity','parent','record','missing_list']) {
      const result=await evaluate('(()=>{const g=structuredClone(state.bundle.report.graph),f=structuredClone(state.bundle.report.findings.find(f=>f.rule==="H02")),c=f.inspection_coverage;'+
        ({edge:'g.edges=g.edges.filter(e=>e.type!=="inspection_coverage_source");',
          reading:'g.inspection_coverage_sources.rows[0].quote+="?";',
          support:'g.edges=g.edges.filter(e=>!(e.type==="supports_result" && e.from===g.inspection_coverage_sources.rows[0].id));',
          page:'g.inspection_coverage_sources.pages[0].text_only=false;',
          parent:'g.edges=g.edges.filter(e=>e.type!=="contains");',
          record:'g.edges=g.edges.filter(e=>e.type!=="records");',
          missing_list:'delete c.equipment;',
          quantity:'c.tested++;'}[corrupt])+
        'const p=InspectionCoverage.panel(f,g);return [p.dataset.inspectionState,!!p.querySelector(".inspection-metric")];})()');
      assert.deepEqual(result,['unknown',false],corrupt);
    }
    const large=await evaluate('(()=>{const c=structuredClone(state.bundle.report.findings.find(f=>f.rule==="H02").inspection_coverage);'+
      'c.equipment.push("EX-05","EX-06","EX-07");const p=InspectionCoverage.deviceView(c,[],()=>null),s=p.querySelector("select");'+
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
  for (const width of widths) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && '+panel+'.scrollWidth<='+panel+'.clientWidth+1'));
    if ([390,1440].includes(width)) {
      await screenshot(driver,'.inspection-panel','inspection-'+(proof.mode || 'unknown')+'-'+proof.state+'-'+width);
      if (proof.state==='short' && width===1440) await screenshot(driver,'.findings-ledger','inspection-findings-'+width);
    }
  }
  if (proof.state==='short' && cid==='08fdfa388dce4718a4cd46dada1385d8') await checkPublicInspection(driver,report);
  console.log('PASS · R'+rev+' · '+proof.state+' · '+opened.size+' verified source actions · six widths');
}

export async function checkPublicInspection(driver,report) {
  const {root,call,evaluate,wait}=driver;
  const sample=await (await fetch(root+'/assets/showcase-inspection.json')).json();
  if (report) {
    const proof=report.findings.find(f=>f.rule==='H02').inspection_coverage;
    assert.deepEqual(sample.check.measurements,proof.measurements);
  }
  for (const [id,doc] of Object.entries(sample.documents)) {
    assert.equal(await hash(root+doc.pdf),doc.source_sha256);
    assert.equal(await hash(root+doc.image),doc.page_sha256);
    if (report) {
      assert.equal(doc.source_sha256,report.graph.documents.find(d=>d.id===id).sha256);
      assert.equal(doc.page_sha256,report.graph.nodes.find(n=>n.id===id+'/p1').sha256);
    }
  }
  await call('Page.navigate',{url:root+'/?scene=inspection#workflow'});
  await wait(q('#scene-inspection .inspection-panel')+'?.dataset.inspectionState==="short"','interactive public sample');
  assert.equal(await evaluate('performance.getEntriesByType("resource").filter(e=>/showcase-inspection-.+jpg/.test(e.name)).length'),0);
  for (const width of widths) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    await evaluate(q('#scene-inspection [data-device="QC-01"]')+'.click()');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'));
    assert.ok(await evaluate('[...document.querySelectorAll(".file-tabs button")].every(b=>{const r=new Range();r.selectNodeContents(b.lastChild);return r.getClientRects().length===1 && b.getBoundingClientRect().height>=44})'),'file tab labels fit at '+width);
    if ([768,1024].includes(width)) {
      assert.ok(await evaluate('(()=>{const h=document.querySelector("#hero-title");return h.clientHeight<=2*parseFloat(getComputedStyle(h).lineHeight)+2})()'),'two-line heading at '+width);
    }
    if ([390,1440].includes(width)) await screenshot(driver,'.workflow-demo','landing-inspection-'+width);
  }
  for (const id of ['QC-01','QC-02']) {
    await evaluate(q('#scene-inspection [data-device="'+id+'"]')+'.click()');
    for (const ref of await evaluate('[...document.querySelectorAll("#inspection-demo .inspection-source")].map(a=>a.dataset.inspectionSource)')) {
      const row=sample.rows.find(r=>r.id===ref), opener=q('[data-inspection-source="'+ref+'"]');
      await evaluate(opener+'.click()');
      await wait(q('#sample-review')+'.open && '+q('#sample-review canvas')+'.dataset.fact==='+JSON.stringify(ref),'public original line');
      assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),sample.documents[row.doc].pdf);
      assert.equal(await evaluate(q('#sample-review output')+'.textContent'),'第 1 页 · 第 '+row.line+' 行');
      await evaluate(q('#sample-review')+'.close()');
      await wait('document.activeElement==='+opener,'return to evidence source button');
    }
  }
}
