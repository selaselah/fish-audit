import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {checkPublicCompare} from './prior-installment.mjs';
import {checkPublicInspection} from './inspection-coverage.mjs';
import {checkPublicWordSigning} from './word-signing.mjs';
import {checkPublicCalendar} from './contract-calendar.mjs';

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

async function checkSampleReader({root,call,evaluate,wait}) {
  const dialog='document.querySelector("#sample-review")';
  const inside=s=>dialog+'.querySelector('+JSON.stringify(s)+')';
  const imagePath='/assets/showcase-acceptance-page.png';
  const image=await fetch(root+imagePath);
  assert.equal(image.status,200);
  assert.equal(createHash('sha256').update(Buffer.from(await image.arrayBuffer())).digest('hex'),
    'fb4799101ab7c9ee46baa4705ed0712abeede3e50e22d8f0b8aebfb5a9ef27bd');
  assert.equal(await evaluate('performance.getEntriesByType("resource").some(r=>new URL(r.name).pathname==='+JSON.stringify(imagePath)+')'),false);
  const records=[['d04/p1/f8','9','合格'],['d04/p1/f10','11','柜温不高于4℃'],['d04/p1/f11','12','柜温8℃']];
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    const opener=width<600?'.workflow-image':'.evidence-note .open-sample-review';
    await evaluate('document.querySelector('+JSON.stringify(opener)+').click()');
    const canvas=inside('canvas');
    await wait(dialog+'.open && '+canvas+'.dataset.fact==="d04/p1/f11"','public archived page ready');
    assert.ok(await evaluate(dialog+'.scrollWidth<='+dialog+'.clientWidth+1'),'public reader fits '+width);
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Home',code:'Home'});
    for (const [i,[id,line,value]] of records.entries()) {
      if (i) await call('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowDown',code:'ArrowDown'});
      assert.equal(await evaluate('document.activeElement.dataset.ref'),id);
      assert.equal(await evaluate(canvas+'.dataset.fact'),id);
      assert.equal(await evaluate(inside('output')+'.textContent'),'第 1 页 · 第 '+line+' 行');
      assert.ok(await evaluate(canvas+'.getAttribute("aria-label").includes('+JSON.stringify(value)+')'));
    }
    const excerpt=await evaluate(canvas+'.toDataURL()');
    await evaluate(inside('[data-scale=page]')+'.click()');
    assert.equal(await evaluate(inside('[data-scale=page]')+'.getAttribute("aria-pressed")'),'true');
    assert.notEqual(await evaluate(canvas+'.toDataURL()'),excerpt);
    await evaluate(inside('[data-scale=line]')+'.click()');
    if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
      await evaluate('document.activeElement.blur()');
      const clip=await evaluate('(()=>{const r='+dialog+'.getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}})()');
      await capture(call,'landing-reader-'+width,clip);
    }
    assert.equal(await evaluate(inside('a')+'.pathname'),'/showcase/acceptance.pdf');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
    await wait('!'+dialog+'.open && document.activeElement.matches('+JSON.stringify(opener)+')','focus returns to reader opener');
  }
  assert.equal(await evaluate('performance.getEntriesByType("resource").some(r=>new URL(r.name).pathname.startsWith("/api/"))'),false);
}

async function checkSigningSample({root,call,evaluate,wait}) {
  const q = s=>'document.querySelector('+JSON.stringify(s)+')';
  const dialog = q('#sample-review'), canvas = q('#sample-review canvas');
  const signingTab = q('#scene-tab-signing'), acceptanceTab = q('#scene-tab-acceptance');
  for (const [path,hash] of [
    ['/assets/showcase-signing-page.jpg','5bcc03f483827ae679d14455dec8c3e8a85b04dd8b218c197417c2cfd57988fc'],
    ['/showcase/signing-contract.pdf','f5d63eb3c3630fe538e409a55df09b641ab4b9b9987136bdd19f3a2d3ff4390d']
  ]) {
    const response=await fetch(root+path);
    assert.equal(response.status,200);
    assert.equal(createHash('sha256').update(Buffer.from(await response.arrayBuffer())).digest('hex'),hash);
  }
  assert.equal(await evaluate('performance.getEntriesByType("resource").some(r=>r.name.endsWith("/showcase-signing-page.jpg"))'),false);
  for (const width of [320,390,600,768,1024,1440]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    await evaluate(acceptanceTab+'.focus()');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight'});
    assert.equal(await evaluate('document.activeElement.id'),'scene-tab-signing');
    assert.equal(await evaluate(signingTab+'.getAttribute("aria-selected")'),'true');
    assert.equal(await evaluate(q('#scene-signing mark')+'.textContent'),'杭州分公司');
    assert.ok(await evaluate(q('#scene-signing')+'.scrollWidth<='+q('#scene-signing')+'.clientWidth+1'));
    if (process.env.AUDIT_UI_SHOTS && [390,1440].includes(width)) {
      await evaluate(q('.workflow-demo')+'.scrollIntoView({block:"center"});document.activeElement.blur()');
      const clip=await evaluate('(()=>{const r='+q('.workflow-demo')+'.getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}})()');
      await capture(call,'landing-signing-'+width,clip);
    }
    for (const [id,line] of [['d02/p1/f3',4],['d02/p1/f10',11],['d02/p1/f18',19]]) {
      const source = q('#scene-signing [data-ref="'+id+'"]');
      await evaluate(source+'.click()');
      await wait(dialog+'.open && '+canvas+'.dataset.fact==='+JSON.stringify(id),'matching public contract line');
      assert.equal(await evaluate(q('#sample-review-title')+'.textContent'),'采购合同');
      assert.equal(await evaluate(q('#sample-location')+'.textContent'),'第 1 页 · 第 '+line+' 行');
      assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),'/showcase/signing-contract.pdf');
      await evaluate(q('#sample-review [data-scale=page]')+'.click()');
      await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
      await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
      await wait('!'+dialog+'.open && document.activeElement==='+source,'focus back on signed contract row');
    }
    await evaluate(signingTab+'.focus()'); await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Home',code:'Home'});
    await evaluate(q('.workflow-image')+'.click()');
    await wait(canvas+'.dataset.fact==="d04/p1/f11" && '+q('#sample-review-title')+'.textContent==="验收报告"','switch to other archived original');
    await evaluate(dialog+'.close()');
  }
}

export async function checkProduct({root,call,evaluate,wait}) {
  const select = selector => 'document.querySelector('+JSON.stringify(selector)+')';
  const mode = (await (await fetch(root+'/api/ready')).json()).mode;
  await wait('document.querySelector("#hero-title") && document.readyState==="complete"','public product page');
  await evaluate('document.fonts.ready.then(()=>true)');
  await evaluate('Promise.all(document.getAnimations().filter(a=>a.effect.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{}))).then(()=>true)');
  assert.equal(await evaluate('performance.getEntriesByType("resource").some(r=>new URL(r.name).pathname.startsWith("/api/"))'),false);
  assert.equal((await fetch(root+'/showcase/other.pdf')).status,404);
  await checkSampleReader({root,call,evaluate,wait});
  await checkSigningSample({root,call,evaluate,wait});
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  const primary = await checkTextContrast(evaluate,'.hero-actions .button');
  for (const [selector,surface] of [
    ['#temperature-readings dl > :first-child small','#sheet-acceptance'],
    ['#temperature-readings dl > :last-child small','#sheet-acceptance'],
    ['.total strong','.total'],['.dial-share','.dial-share'],['.dial-label','.dial-label']
  ]) await checkTextContrast(evaluate,selector,surface);
  const dates=select('.ledger-switch [aria-controls=sample-dates]');
  await evaluate(dates+'.focus();new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  assert.ok(await evaluate('document.activeElement==='+dates),'dismissing an original preserves subsequent keyboard navigation');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'End',code:'End'});
  await call('Input.dispatchKeyEvent',{type:'keyUp',key:'End',code:'End'});
  assert.ok(await evaluate('!document.querySelector("#sample-dates").hidden && document.querySelector("#sample-installments").hidden'));
  assert.deepEqual(await evaluate('[...document.querySelectorAll(".sample-dates a")].map(a=>[a.querySelector("time").dateTime,a.pathname])'),
    [['2026-09-01','/showcase/contract.pdf'],['2026-09-20','/showcase/acceptance.pdf'],['2026-09-21','/showcase/transfer.pdf']]);
  for (const width of [1440,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    assert.ok(await evaluate('document.querySelector("#sample-dates").scrollWidth<=document.querySelector("#sample-dates").clientWidth+1'));
    if (width!==320 && process.env.AUDIT_UI_SHOTS) {
      await evaluate('document.querySelector(".phase-ledger").scrollIntoView({block:"center",behavior:"instant"})');
      const clip=await evaluate('(()=>{const r=document.querySelector(".phase-ledger").getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}})()');
      await capture(call,'sample-dates-'+width,clip);
    }
  }
  for (const selector of ['.sample-dates time','.sample-dates .flagged span small'])
    await checkTextContrast(evaluate,selector,'.phase-ledger');
  await checkTextContrast(evaluate,'.ledger-switch [aria-pressed=true]');
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await evaluate(select('.ledger-switch [aria-controls=sample-installments]')+'.click()');
  assert.ok(await evaluate('document.querySelector("#sample-dates").hidden && !document.querySelector("#sample-installments").hidden'));
  const readingSwitch = '.reading-switch';
  assert.ok(await evaluate('!document.querySelector(".reading-switch").hidden && !document.querySelector("#temperature-readings").hidden'));
  assert.deepEqual(await evaluate('[...document.querySelectorAll("#temperature-readings dd a")].map(a=>[a.textContent.trim(),a.pathname])'),
    [['≤ 4 ℃','/showcase/contract.pdf'],['8 ℃','/showcase/acceptance.pdf']]);
  await evaluate(select(readingSwitch+' [aria-controls=acceptance-excerpt]')+'.click()');
  assert.ok(await evaluate('!document.querySelector("#acceptance-excerpt").hidden && document.querySelector("#temperature-readings").hidden'));
  assert.equal(await evaluate(select(readingSwitch+' [aria-controls=acceptance-excerpt]')+'.getAttribute("aria-pressed")'),'true');
  const findingInks = new Set();
  await evaluate(select(readingSwitch+' [aria-controls=source-strips]')+'.click()');
  await wait('Array.from(document.querySelectorAll("#source-strips img")).every(i=>i.naturalWidth>0)','both published original lines');
  const strips=await evaluate('Array.from(document.querySelectorAll("#source-strips a"),a=>[a.pathname,a.querySelector("img").src])');
  for (const [i,[path,image]] of strips.entries()) {
    assert.equal(path,'/showcase/'+['contract','acceptance'][i]+'.pdf');
    const digest=createHash('sha256').update(Buffer.from(await (await fetch(image)).arrayBuffer())).digest('hex');
    assert.equal(digest,['71ac6d8b21360c348a3ae65715115a14bc396f18205936a51629ff4d6b9c28a0','44a6d7766ddb789b087869c4b1b941ea90188962115fec193a3f2b4f934c4f47'][i]);
  }
  await evaluate(select(readingSwitch+' [aria-controls=acceptance-excerpt]')+'.click()');
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
    await evaluate(select(readingSwitch+' [aria-controls=source-strips]')+'.click()');
    const stripsFit=await evaluate('Array.from(document.querySelectorAll("#source-strips a"),n=>n.getBoundingClientRect()).every(r=>r.height>=44 && r.left>=0 && r.right<=innerWidth)');
    assert.ok(stripsFit,'published line links at '+width);
    await evaluate(select(readingSwitch+' [aria-controls=temperature-readings]')+'.click()');
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
    await wait('document.querySelector(".dial-share").textContent==='+JSON.stringify(['30%','60%','10%'][index]),'contract share follows selected installment');
  }
  await evaluate(select('.phase-dial')+'.focus()');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Home',code:'Home'});
  assert.equal(await evaluate('document.querySelector(".phase[open] .phase-name").textContent'),'生效预付款');
  await evaluate(select('.phase-dial')+'.click()');
  assert.equal(await evaluate('document.querySelector(".phase[open] .phase-name").textContent'),'终验款');
  if (process.env.AUDIT_UI_SHOTS) {
    await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
    await evaluate('document.querySelector("#payments").scrollIntoView()');
    await capture(call,'installment-dial-1440');
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
  await checkPublicInspection({root,call,evaluate,wait});
  await checkPublicCompare({root,call,evaluate,wait});
  await checkPublicWordSigning({root,call,evaluate,wait});
  await checkPublicCalendar({root,call,evaluate,wait});
  console.log('PASS · acceptance, signing and unit inspection, original PDFs and Word, keyboard, six viewports, workspace entry and legacy bookmark ('+mode+')');
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
  const board=await (await fetch(root+'/api/inbox?view=board&q='+encodeURIComponent('合成演练'))).json();
  await wait('performance.getEntriesByType("resource").some(r=>{const u=new URL(r.name);return u.pathname==="/api/inbox" && u.searchParams.get("q")==="合成演练" && u.searchParams.get("view")==="board"}) && !!document.querySelector(".verdict-board")','filtered board has finished loading');
  const buckets=Object.entries(board.lanes).filter(([id,lane])=>id!=='pending' || lane.total);
  for (const [id,lane] of buckets) {
    const selector=selectLane(id);
    assert.equal(await evaluate(selector+'.querySelector(".lane-heading strong").textContent'),lane.total.toLocaleString('zh-CN'));
    assert.deepEqual(await evaluate('[...'+selector+'.querySelectorAll("[data-case-id]")].map(x=>x.dataset.caseId)'),lane.cases.map(c=>c.id));
    assert.deepEqual(await evaluate('[...'+selector+'.querySelectorAll("[data-case-id]")].map(x=>new URL(x.href).searchParams.get("rev"))'),
      lane.cases.map(c=>c.rev>0?String(c.rev):null));
  }
  function selectLane(id) { return 'document.querySelector("#lane-'+id+'")'; }
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width===390?844:900,deviceScaleFactor:1,mobile:width<600});
    await evaluate('scrollTo(0,0)');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'verdict board at '+width);
    if (width<600) {
      for (const id of ['pass','review','reject']) {
        await evaluate('document.querySelector("[data-lane-choice='+id+']").click()');
        assert.equal(await evaluate('[...document.querySelectorAll(".verdict-lane")].filter(n=>n.getClientRects().length).map(n=>n.id).join()'),'lane-'+id);
      }
    }
    if (width===1440 || width===390) await capture(call,'desk-'+width);
  }
  const bucket=buckets.find(([,lane])=>lane.total>3);
  assert.ok(bucket);
  await evaluate('document.querySelector("[data-lane-choice='+bucket[0]+']").click();document.querySelector("[data-more-lane='+bucket[0]+']").click()');
  await wait('!!document.querySelector(".verdict-chip") && !!document.querySelector(".ledger-header")','board to filtered ledger');
  assert.equal(await evaluate('document.querySelector("#queue-count").textContent'),bucket[1].total.toLocaleString('zh-CN')+' 项');
  assert.deepEqual(await evaluate('[...document.querySelectorAll(".ledger-row [data-case-id]")].slice(0,3).map(n=>n.dataset.caseId)'),bucket[1].cases.map(c=>c.id));
  await evaluate('document.querySelector(".verdict-chip").click()');
  await wait('document.querySelector("#queue-count").textContent==='+JSON.stringify(board.total.toLocaleString('zh-CN')+' 项')+' && document.querySelector("#verdict-filter").hidden','remove recommendation filter');
  await call('Page.reload');
  await wait('!!document.querySelector(".ledger-header") && document.querySelector("[data-desk-view=list]").getAttribute("aria-pressed")==="true"','preferred view on reload');
  await evaluate('document.querySelector("[data-desk-view=board]").click()');
  await wait('!!document.querySelector(".verdict-board")','restore grouped view');
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
  const human=latest.result.verdict==='review' && latest.result.human_required===true ? null :
    latest.result.human_required===true?'需人工校验':latest.result.human_required===false?'无专项待核项':'人工校验要求待核';
  assert.equal(await evaluate('document.querySelector(".preview-verdict .small")?.textContent ?? null'),human);
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
