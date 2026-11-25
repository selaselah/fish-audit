import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

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
  const findingInks = new Set();
  for (const [name,expected] of Object.entries(digests)) {
    await evaluate(select('#tab-'+name)+'.click()');
    const panel = select('#sheet-'+name);
    assert.ok(await evaluate(panel+'.getClientRects().length>0'));
    assert.equal(await evaluate('document.querySelectorAll(".evidence-paper:not([hidden])").length'),1);
    const marked='#sheet-'+name+' .marked';
    findingInks.add((await checkTextContrast(evaluate,marked+' dd',marked)).ink);
    await checkTextContrast(evaluate,'#tab-'+name);
    const source = await evaluate(panel+'.querySelector("a").href');
    const pdf = await fetch(source);
    assert.equal(pdf.status,200); assert.match(pdf.headers.get('content-type'),/application\/pdf/);
    assert.equal(createHash('sha256').update(Buffer.from(await pdf.arrayBuffer())).digest('hex'),expected);
  }
  assert.equal(findingInks.size,3,'confirmed, exceeded and pending evidence must read differently');
  await evaluate(select('#tab-contract')+'.focus()');
  await call('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight'});
  assert.equal(await evaluate('document.activeElement.id'),'tab-acceptance');
  assert.equal(await evaluate(select('#tab-acceptance')+'.getAttribute("aria-selected")'),'true');
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
  }
  assert.equal(await evaluate('location.pathname'),'/app');
  await call('Page.navigate',{url:root+'/#rules'});
  await wait('location.pathname==="/app" && !document.querySelector("#rules").hidden','legacy rules bookmark');
  await evaluate(select('.fish-wordmark')+'.click()');
  await wait('location.pathname==="/" && !!document.querySelector("#hero-title")','return to product site');
  console.log('PASS · public demo, three original PDFs, keyboard, six viewports, workspace entry and legacy bookmark ('+mode+')');
}

export async function checkReviewDesign({root,call,evaluate,wait}, caseId) {
  const report = (await (await fetch(root+'/api/cases/'+caseId+'/reports/7')).json()).report;
  const doc = report.graph.documents.find(d => d.sha256===digests.acceptance);
  assert.ok(doc,'the showcase must use the published watermarked acceptance sheet');
  const fact = report.graph.facts.find(f => f.doc===doc.id && f.field==='measured_result');
  assert.ok(fact.source_line.rects.length);
  await wait('!!document.querySelector(".case-link")','local desk');
  await evaluate('document.querySelector("#case-search").value="合成演练";document.querySelector("#case-search").dispatchEvent(new Event("input"))');
  const subset = await (await fetch(root+'/api/inbox?'+new URLSearchParams({q:'合成演练',status:'all'}))).json();
  await wait('document.querySelector("[data-metric=all] strong").textContent==='+JSON.stringify(subset.total.toLocaleString('zh-CN')),'synthetic-only queue');
  assert.ok(await evaluate('[...document.querySelectorAll(".case-link")].every(a=>a.getAttribute("aria-label")?.startsWith("合成演练 · "))'));
  await evaluate('Promise.all(document.getAnimations().filter(a=>a.effect.getTiming().iterations!==Infinity).map(a=>a.finished.catch(()=>{}))).then(()=>true)');
  for (const width of [1440,390]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width===390?844:900,deviceScaleFactor:1,mobile:width<600});
    await evaluate('scrollTo(0,0)');
    await capture(call,'desk-'+width);
  }
  await evaluate('document.querySelector("[data-metric=attention]").click()');
  await wait('document.querySelector("#queue-title").textContent==="有疑点待验收" && document.querySelector("[data-metric=attention]").getAttribute("aria-pressed")==="true"','scoped attention queue');
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
  }
  console.log('PASS · synthetic queue, actual counts, desktop source alignment and mobile evidence navigation');
}
