import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';

// These are the three public, watermarked originals of the equipment-quality exercise, R7.
const digests = {
  contract:'546d0efde4b8a9bc2bc501c866dedaf60a3ac20ef46cc1af63194aa75e4e1af2',
  acceptance:'587d052e348bf67e32399f0daafc1a065d061a13f669f08396ce75875b4153cf',
  transfer:'8b0087142d831b111eea4cf1c77913b8df67a96a26a1da1a288a9875744df586',
};

async function capture(call, name, clip) {
  if (!process.env.AUDIT_UI_SHOTS) return;
  const {data} = await call('Page.captureScreenshot',{format:'png',...(clip ? {clip} : {})});
  await writeFile(join(process.env.AUDIT_UI_SHOTS,name+'.png'),Buffer.from(data,'base64'));
}

async function checkTextContrast(evaluate, textSelector, surfaceSelector = textSelector) {
  const style = selector => 'getComputedStyle(document.querySelector('+JSON.stringify(selector)+'))';
  const [ink, surface] = await evaluate('['+style(textSelector)+'.color,'+style(surfaceSelector)+'.backgroundColor]');
  function luminance(color) {
    const rgb = /^rgb\((\d+), (\d+), (\d+)\)$/.exec(color);
    assert.ok(rgb,'Expected an opaque sRGB color for '+textSelector+' on '+surfaceSelector+', got '+color);
    const [r,g,b] = rgb.slice(1).map(value => {
      const channel = Number(value)/255;
      return channel<=0.04045 ? channel/12.92 : ((channel+0.055)/1.055)**2.4;
    });
    return 0.2126*r+0.7152*g+0.0722*b;
  }
  const a=luminance(ink), b=luminance(surface);
  const ratio=(Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
  assert.ok(ratio>=4.5,textSelector+' on '+surfaceSelector+' has contrast '+ratio.toFixed(2));
  return {ink,surface};
}

export async function checkProduct({root,call,evaluate,wait}) {
  const select = selector => 'document.querySelector('+JSON.stringify(selector)+')';
  const mode = (await (await fetch(root+'/api/ready')).json()).mode;
  await wait('document.querySelector("#hero-title") && document.readyState==="complete"','public product page');
  await evaluate('document.fonts.ready.then(()=>true)');
  await evaluate('Promise.all(document.getAnimations().filter(a=>a.effect.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{}))).then(()=>true)');
  assert.equal(await evaluate('performance.getEntriesByType("resource").some(r=>new URL(r.name).pathname.startsWith("/api/"))'),false);
  assert.equal((await fetch(root+'/showcase/other.pdf')).status,404);
  const primary = await checkTextContrast(evaluate,'.hero-actions .button');
  const readingSwitch = '.reading-switch';
  assert.ok(await evaluate('!document.querySelector(".reading-switch").hidden && !document.querySelector("#temperature-readings").hidden'));
  assert.deepEqual(await evaluate('[...document.querySelectorAll("#temperature-readings dd a")].map(a=>[a.textContent.trim(),a.pathname])'),
    [['≤ 4 ℃','/showcase/contract.pdf'],['8 ℃','/showcase/acceptance.pdf']]);
  await evaluate(select(readingSwitch+' [aria-controls=acceptance-excerpt]')+'.click()');
  assert.ok(await evaluate('!document.querySelector("#acceptance-excerpt").hidden && document.querySelector("#temperature-readings").hidden'));
  assert.equal(await evaluate(select(readingSwitch+' [aria-controls=acceptance-excerpt]')+'.getAttribute("aria-pressed")'),'true');
  const findingInks = new Set();
  for (const [name,expected] of Object.entries(digests)) {
    await evaluate(select('#tab-'+name)+'.click()');
    const panel = select('#sheet-'+name);
    assert.ok(await evaluate(panel+'.getClientRects().length>0'));
    assert.equal(await evaluate('document.querySelectorAll(".evidence-paper:not([hidden])").length'),1);
    const marked='#sheet-'+name+' .marked';
    findingInks.add((await checkTextContrast(evaluate,marked+' dd',marked)).ink);
    await checkTextContrast(evaluate,'#tab-'+name);
    const source = await evaluate(panel+'.querySelector(".evidence-note a").href');
    const pdf = await fetch(source);
    assert.equal(pdf.status,200); assert.match(pdf.headers.get('content-type'),/application\/pdf/);
    assert.equal(createHash('sha256').update(Buffer.from(await pdf.arrayBuffer())).digest('hex'),expected);
  }
  assert.equal(findingInks.size,3,'confirmed, exceeded and pending evidence must read differently');
  await evaluate(select('#tab-contract')+'.focus()');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight'});
  assert.equal(await evaluate('document.activeElement.id'),'tab-acceptance');
  assert.equal(await evaluate(select('#tab-acceptance')+'.getAttribute("aria-selected")'),'true');
  assert.ok(await evaluate('!document.querySelector("#acceptance-excerpt").hidden'),'changing documents preserves the excerpt view');
  await evaluate(select(readingSwitch+' [aria-controls=temperature-readings]')+'.click()');
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight'});
  await call('Emulation.setEmulatedMedia',{features:[{name:'forced-colors',value:'active'}]});
  assert.equal(await evaluate('getComputedStyle(document.activeElement).textDecorationStyle'),'double');
  await call('Emulation.setEmulatedMedia',{features:[]});
  await evaluate('document.activeElement.blur()');
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    await evaluate('scrollTo({top:0,behavior:"instant"})');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'product width '+width);
    for (const selector of ['#hero-title','.file-tabs','.evidence-note a','.button']) {
      const bounds = await evaluate(select(selector)+'.getBoundingClientRect().toJSON()');
      assert.ok(bounds.width>0 && bounds.left>=0 && bounds.right<=width+1,selector+' at '+width);
      if (width<=390 && selector==='.evidence-note a')
        assert.ok(bounds.height>=44 && bounds.bottom<=844,'mobile original-PDF link at '+width);
    }
    if (width===1440 || width===390) await capture(call,'product-'+width);
  }
  await evaluate(select('.mobile-menu summary')+'.click()');
  await evaluate(select('.mobile-menu a[href="#workflow"]')+'.click()');
  await wait('location.hash==="#workflow" && !document.querySelector(".mobile-menu").open','mobile section navigation');
  await evaluate('document.querySelector(".mobile-menu summary").click()');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape'});
  assert.equal(await evaluate('document.querySelector(".mobile-menu").open'),false);
  for (const index of [0,1,2]) {
    await evaluate('document.querySelectorAll(".phase summary")['+index+'].click()');
    assert.equal(await evaluate('document.querySelectorAll(".phase[open]").length'),1);
    assert.ok(await evaluate('!!document.querySelector(".phase[open] .phase-detail a").getClientRects().length'));
  }
  await evaluate(select('.hero-actions a')+'.click()');
  if (mode==='saas') {
    await wait('!!document.querySelector("#account-panel input[name=password]")','enterprise login');
    assert.deepEqual(await checkTextContrast(evaluate,'#account-panel button.primary'),primary);
  } else {
    await wait('!!document.querySelector("#desk:not([hidden]) #new-case")','local workbench');
    assert.deepEqual(await checkTextContrast(evaluate,'#new-case'),primary);
    await checkTextContrast(evaluate,'.queue-total strong','.queue-total');
    await evaluate(select('#new-case')+'.click()');
    await wait('document.querySelector("#upload-dialog").open','upload dialog');
    for (const name of ['contract.pdf','receipt.pdf']) {
      await evaluate('(()=>{const data=new DataTransfer();data.items.add(new File(["fixture"],'+JSON.stringify(name)+',{type:"application/pdf"}));document.querySelector(".upload-zone").dispatchEvent(new DragEvent("drop",{dataTransfer:data,bubbles:true}));})()');
    }
    assert.deepEqual(await evaluate('[...document.querySelector("#upload-files").files].map(f=>f.name)'),['contract.pdf','receipt.pdf']);
    await evaluate(select('#chosen-files button')+'.click()');
    assert.deepEqual(await evaluate('[...document.querySelector("#upload-files").files].map(f=>f.name)'),['receipt.pdf']);
    const {root:dom}=await call('DOM.getDocument');
    const {nodeId}=await call('DOM.querySelector',{nodeId:dom.nodeId,selector:'#upload-files'});
    for (const name of ['contract','acceptance']) await call('DOM.setFileInputFiles',{nodeId,files:[resolve('frontend/showcase/'+name+'.pdf')]});
    assert.deepEqual(await evaluate('Array.from(document.querySelector("#upload-files").files,f=>f.name)'),['receipt.pdf','contract.pdf','acceptance.pdf']);
    assert.ok(await evaluate('document.querySelector("#intake-count").textContent.includes("3 / 12")'));
    assert.ok(await evaluate('document.querySelector(".intake-footer").innerText.includes("OpenAI") && !document.querySelector(".intake-requirements").open'));
    for (const width of [1440,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
      assert.ok(await evaluate('document.querySelector("#upload-dialog").scrollWidth<=document.querySelector("#upload-dialog").clientWidth+1'));
      if (width!==320) {
        const clip=await evaluate('(()=>{const r=document.querySelector("#upload-dialog").getBoundingClientRect(); return {x:r.left+scrollX,y:r.top+scrollY,width:r.width,height:r.height,scale:1}})()');
        await capture(call,'intake-'+width,clip);
      }
    }
    await evaluate('(()=>{const data=new DataTransfer(); for(let i=0;i<10;i++) data.items.add(new File(["演练"],"额外"+i+".pdf"));document.querySelector(".upload-zone").dispatchEvent(new DragEvent("drop",{dataTransfer:data,bubbles:true}));})()');
    assert.ok(await evaluate('document.querySelector("#intake-count").textContent.includes("13 / 12") && document.querySelector("#upload-error").textContent.includes("超过 12")'));
    await evaluate('document.querySelector("#chosen-files li:last-child button").click()');
    assert.equal(await evaluate('document.querySelector("#upload-error").textContent'),'');
  }
  assert.equal(await evaluate('location.pathname'),'/app');
  await call('Page.navigate',{url:root+'/#rules'});
  await wait('location.pathname==="/app" && !document.querySelector("#rules").hidden','legacy rules bookmark');
  await evaluate(select('.fish-wordmark')+'.click()');
  await wait('location.pathname==="/" && !!document.querySelector("#hero-title")','return to product site');
  console.log('PASS · public demo, three original PDFs, keyboard, six viewports, workspace entry and legacy bookmark ('+mode+')');
}

export async function checkReviewDesign({root,call,evaluate,wait}, caseId) {
  const endpoint = root+'/api/cases/'+caseId;
  const task = await (await fetch(endpoint)).json();
  const report = (await (await fetch(endpoint+'/reports/7')).json()).report;
  const doc = report.graph.documents.find(d => d.sha256===digests.acceptance);
  assert.ok(doc,'the showcase must use the published watermarked acceptance sheet');
  const fact = report.graph.facts.find(f => f.doc===doc.id && f.field==='measured_result');
  assert.ok(fact.source_line.rects.length);
  await wait('!!document.querySelector(".case-link")','local desk');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'/',code:'Slash'});
  assert.equal(await evaluate('document.activeElement.id'),'case-search');
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'/',code:'Slash'});
  await evaluate('document.querySelector("#desk-filters summary").click();document.querySelector("#desk-sort").value="created";document.querySelector("#desk-sort").dispatchEvent(new Event("change"))');
  assert.equal(await evaluate('document.querySelector("#filter-count").innerText'),'1');
  await evaluate('document.querySelector("#reset-filters").click()');
  assert.ok(await evaluate('document.querySelector("#filter-count").hidden && !document.querySelector("#desk-filters").open && document.querySelector("#desk-sort").value==="updated"'));
  await evaluate('document.querySelector("#case-search").value="合成演练";document.querySelector("#case-search").dispatchEvent(new Event("input"))');
  const subset = await (await fetch(root+'/api/inbox?'+new URLSearchParams({q:'合成演练',status:'all'}))).json();
  await wait('document.querySelector("[data-metric=all] strong").textContent==='+JSON.stringify(subset.total.toLocaleString('zh-CN')),'synthetic-only queue');
  assert.ok(await evaluate('[...document.querySelectorAll(".case-link")].every(a=>a.getAttribute("aria-label")?.startsWith("合成演练 · "))'));
  await evaluate('document.activeElement.blur()');
  await evaluate('Promise.all(document.getAnimations().filter(a=>a.effect.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{}))).then(()=>true)');
  for (const width of [1440,390]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width===390?844:900,deviceScaleFactor:1,mobile:width<600});
    await evaluate('scrollTo(0,0)');
    await capture(call,'desk-'+width);
  }
  await evaluate('document.querySelector("[data-metric=attention]").click()');
  await wait('document.querySelector("#queue-title").textContent==="有疑点待验收" && document.querySelector("[data-metric=attention]").getAttribute("aria-pressed")==="true"','scoped attention queue');
  await evaluate('document.querySelector("[data-metric=all]").click();document.querySelector("#case-search").value='+JSON.stringify(task.title)+';document.querySelector("#case-search").dispatchEvent(new Event("input"))');
  const peek = 'document.querySelector('+JSON.stringify('[data-preview-case="'+caseId+'"]')+')';
  await wait('document.querySelectorAll("[data-preview-case]").length===1 && '+peek,'exact case in inbox');
  await evaluate(peek+'.focus();'+peek+'.click()');
  await wait('document.querySelector("#case-preview").open && !!document.querySelector(".preview-finding")','pinned findings in preview');
  assert.equal(await evaluate('document.querySelector("#preview-title").textContent'),task.title);
  assert.deepEqual(await evaluate('[...document.querySelectorAll(".preview-files li span")].map(n=>n.textContent)'),task.documents.map(d=>d.name));
  assert.equal(await evaluate('new URL(document.querySelector(".preview-open").href).searchParams.get("rev")'),String(task.rev));
  const latest = task.rev===7 ? report : (await (await fetch(endpoint+'/reports/'+task.rev)).json()).report;
  assert.equal(await evaluate('document.querySelector(".preview-verdict .tag").dataset.state'),latest.result.verdict);
  assert.equal(await evaluate('document.querySelector(".preview-verdict .small").textContent'),latest.result.human_required?'需人工校验':'无专项待核项');
  const priority = ['issue','risk','missing'].flatMap(s=>latest.findings.filter(f=>f.status===s)).slice(0,3);
  assert.deepEqual(await evaluate('[...document.querySelectorAll(".preview-finding")].map(a=>Array.from(new URL(a.href).searchParams.values()))'),
    priority.map(f=>[String(task.rev),f.id]));
  if (process.env.AUDIT_UI_SHOTS) {
    await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
    await evaluate('Promise.all(document.getAnimations().filter(a=>a.effect.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{}))).then(()=>true)');
    await capture(call,'preview-drawer-1440');
    await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  }
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await wait('!document.querySelector("#case-preview").open && !document.querySelector("#preview-body").childElementCount','dismiss and clear preview');
  assert.equal(await evaluate('document.activeElement.dataset.previewCase'),caseId);
  await evaluate(peek+'.click()');
  await wait('!!document.querySelector(".preview-finding")','reopen preview');
  await evaluate('document.querySelector(".preview-finding").click()');
  await wait('!document.querySelector("#case-preview").open && !document.querySelector("#case").hidden && !!document.querySelector("#trace-select")','preview to evidence trail');
  assert.equal(await evaluate('document.querySelector("#trace-select").value'),priority[0].id);
  await call('Page.navigate',{url:root+'/workpaper/'+caseId+'?rev=7'});
  await wait('!!document.querySelector(".finding-disclosure")','condensed R7 workpaper');
  assert.equal(await evaluate('document.querySelectorAll(".finding-disclosure[open]").length'),0);
  for (const key of ['all','issue','risk','missing','ok']) {
    const filtered = key==='all' ? report.findings : report.findings.filter(f=>f.status===key);
    const control = 'document.querySelector('+JSON.stringify('[data-finding-filter="'+key+'"]')+')';
    assert.equal(await evaluate(control+'.querySelector("strong").textContent'),String(filtered.length));
    if (!filtered.length) { assert.equal(await evaluate(control+'.disabled'),true); continue; }
    await evaluate(control+'.click()');
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".finding:not([hidden])")].map(r=>r.dataset.finding)'),filtered.map(f=>f.id));
  }
  const issue = report.findings.find(f=>f.status==='issue');
  await evaluate('document.querySelector(".priority-findings button").click()');
  assert.equal(await evaluate('document.activeElement.dataset.finding'),issue.id);
  assert.equal(await evaluate('document.activeElement.querySelector(".finding-disclosure[open] .finding-detail").innerText'),issue.detail);
  assert.equal(await evaluate('document.querySelector("[data-finding-filter=all]").getAttribute("aria-pressed")'),'true');
  const phases = report.findings.filter(f=>f.rule==='H04' && f.stage);
  assert.deepEqual(await evaluate('[...document.querySelectorAll(".share-strip span")].map(s=>Number(getComputedStyle(s).flexGrow))'),phases.map(f=>Number(f.stage.share)));
  assert.equal(await evaluate('document.querySelector(".phase-choice[aria-selected=true]").dataset.phaseChoice'),phases.find(f=>f.status!=='ok').id);
  await evaluate('document.querySelector(".phase-choice[aria-selected=true]").focus()');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'End',code:'End'});
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'End',code:'End'});
  assert.equal(await evaluate('document.activeElement.dataset.phaseChoice'),phases.at(-1).id);
  assert.deepEqual(await evaluate('[...document.querySelectorAll(".phase-summary li:not([hidden])")].map(row=>row.dataset.phaseFinding)'),[phases.at(-1).id]);
  await evaluate('document.querySelector(".phase-summary li:not([hidden]) .phase-source").click()');
  await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(phases.at(-1).stage.clause_ref),'original for selected phase');
  const target = '/workpaper/'+caseId+'?'+new URLSearchParams({rev:7,fact:fact.id});
  for (const width of [1440,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    await call('Page.navigate',{url:root+target});
    await wait('document.querySelector("#page-dialog")?.open && !!document.querySelector(".page-image")?.naturalWidth && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(fact.id),'cited measurement');
    await checkTextContrast(evaluate,'.located .tag');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'));
    if (width===1440) {
      await evaluate('const row=document.querySelector(".located");row.scrollIntoView({block:"center"})');
      const clip = await evaluate('const r=document.querySelector("#page-dialog").getBoundingClientRect();({x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1})');
      await capture(call,'viewer-desktop',clip);
      assert.ok(await evaluate('const mark=document.querySelector(".image-sheet rect").getBoundingClientRect(), pane=document.querySelector(".viewer-original").getBoundingClientRect();mark.top>=pane.top && mark.bottom<=pane.bottom'));
    } else {
      await evaluate('document.querySelector(".viewer-nav [aria-controls=viewer-original]").click()');
      assert.equal(await evaluate('document.activeElement.id'),'viewer-original');
      await evaluate('document.querySelector(".viewer-nav [aria-controls=viewer-facts]").click()');
      assert.equal(await evaluate('document.activeElement.id'),'viewer-facts');
      if (width===390) await capture(call,'viewer-mobile');
    }
    const other = report.graph.facts.find(f=>f.id!==fact.id && f.doc===doc.id && f.page===fact.page && f.source_line?.rects.length);
    await evaluate('document.querySelector("[aria-label=放大原页]").click();document.querySelector("[aria-label=放大原页]").click()');
    assert.equal(await evaluate('document.querySelector(".zoom-scale").textContent'),'150%');
    assert.ok(await evaluate('const canvas=document.querySelector(".source-scroll");Math.abs(canvas.scrollWidth/canvas.clientWidth-1.5)<.02'),'original zoom width at '+width);
    await evaluate('const picker=document.querySelector("[aria-label=定位本页引文]");picker.value='+JSON.stringify(other.id)+';picker.dispatchEvent(new Event("change"))');
    assert.equal(await evaluate('document.activeElement.dataset.fact'),other.id);
    assert.equal(await evaluate('document.querySelectorAll(".evidence-row.located").length'),1);
    assert.equal(await evaluate('document.querySelectorAll(".evidence-row[data-fact]:not([hidden])").length'),1);
    assert.equal(await evaluate('document.querySelectorAll(".image-sheet rect").length'),other.source_line.rects.length);
    await evaluate('picker.value="";picker.dispatchEvent(new Event("change"))');
    assert.equal(await evaluate('document.querySelectorAll(".evidence-row[data-fact]:not([hidden])").length'),
      report.graph.facts.filter(f=>f.doc===doc.id && f.page===fact.page).length);
    await evaluate('document.querySelector(".zoom-fit").click()');
    assert.equal(await evaluate('document.querySelector(".zoom-scale").textContent'),'100%');
    assert.equal(await evaluate('document.querySelector("[aria-label=缩小原页]").disabled'),true);
  }
  console.log('PASS · scoped drawer and exact revision, procedure filters, keyboard-selected installments, original-image zoom and cited fact navigation');
}
