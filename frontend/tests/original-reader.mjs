import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {size,inspect} from './review-screen.mjs';

const q = s=>'document.querySelector('+JSON.stringify(s)+')';
const all = s=>'[...document.querySelectorAll('+JSON.stringify(s)+')]';

export async function checkCitedOriginal(ctx,id) {
  const {root,call,evaluate,wait}=ctx, api=root+'/api/cases/'+id;
  const detail=await (await fetch(api)).json();
  assert.ok(detail.title.startsWith('合成演练 · '));
  const {report}=await (await fetch(api+'/reports/8')).json();
  const ref='d04/p1/f11',accepted='d04/p1/f8', source=report.graph.facts.find(f=>f.id===ref);
  assert.equal(source?.source_line.text,'实测结果：柜温8℃');
  const ids=report.findings.filter(f=>f.evidence.includes(ref)).map(f=>f.id);
  assert.deepEqual(ids,['H02-3','H04-6','H04-7','H05-8']);
  const digest=createHash('sha256').update(Buffer.from(await (await fetch(api+'/documents/d04/pages/1?rev=8')).arrayBuffer())).digest('hex');
  assert.equal(digest,source.page_sha256);
  const open=root+'/workpaper/'+id+'?rev=8&fact='+accepted;
  const toggle=q('.reader-citation-toggle'), picker=q('#reader-citation-picker');
  const rect=q('.reader-citation-marks g[data-fact="'+ref+'"] rect');
  const summary=q('#reader-citation-detail summary');
  for (const width of [320,360,390,768,1024,1440]) {
    await size(ctx,width);
    await call('Page.navigate',{url:open});
    await wait(toggle+'?.getClientRects().length && '+picker+'.value==='+JSON.stringify(accepted),'original and initial field');
    assert.equal(await evaluate(q('.reader-citation-marks')),null);
    await evaluate(toggle+'.click()');
    await wait(rect+'?.getClientRects().length','citation overlays');
    if ([390,1440].includes(width)) {
      await evaluate(q('[aria-label="放大原页"]')+'.click()');
      await evaluate(q('[aria-label="向右旋转 90°"]')+'.click()');
    }
    await evaluate(rect+'.scrollIntoView({block:"center",inline:"center",behavior:"instant"})');
    const point=await evaluate('(()=>{const r='+rect+'.getBoundingClientRect(); return {x:r.left+r.width/2,y:r.top+r.height/2}})()');
    if (width===390) {
      await call('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:1});
      await call('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[point]});
      await call('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    } else {
      await call('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});
      await call('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});
    }
    await wait(picker+'.value==='+JSON.stringify(ref)+' && '+summary+'.textContent.includes("4 项")','pointer chooses archived measurement at '+width);
    if (width===390) await call('Emulation.setTouchEmulationEnabled',{enabled:false});
    assert.equal(await evaluate(q('.viewer-facts .located')+'.dataset.fact'),ref);
    await evaluate(summary+'.click()');
    assert.deepEqual(await evaluate(all('#reader-citation-detail a')+'.map(a=>[new URL(a.href).searchParams.get("rev"),new URL(a.href).searchParams.get("finding")])'),ids.map(i=>['8',i]));
    assert.ok(await evaluate(q('#reader-citation-detail a[href*="H04-6"]')+'.textContent.includes("第二期")'));
    if ([390,1440].includes(width)) {
      await evaluate(q('[aria-label="向左旋转 90°"]')+'.click()');
      await inspect(ctx,width,'#reader-citation-detail','issued-page-citations');
    }
    if ([320,1440].includes(width)) {
      const heading=q('.reader-citation-marks g[data-fact="d04/p1/f1"] rect');
      await evaluate(heading+'.scrollIntoView({block:"center",inline:"center",behavior:"instant"})');
      const spot=await evaluate('(()=>{const r='+heading+'.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()');
      for (const type of ['mousePressed','mouseReleased']) await call('Input.dispatchMouseEvent',{type,...spot,button:'left',clickCount:1});
      const choice=q('#reader-citation-detail select');
      await wait(choice+'?.options.length===3','coincident title facts require a choice');
      assert.equal(await evaluate(picker+'.value'),ref);
      assert.deepEqual(await evaluate('[...'+choice+'.options].slice(1).map(o=>o.value).sort()'),['d04/p1/f1','d04/p1/t2']);
      assert.ok(await evaluate('[...'+choice+'.options].slice(1).every(o=>o.text.includes(o.value))'));
      assert.ok(await evaluate(q('#page-dialog')+'.scrollWidth<='+q('#page-dialog')+'.clientWidth+1'),'overlap selector fits');
      await evaluate(choice+'.value="d04/p1/t2";'+choice+'.dispatchEvent(new Event("change"))');
      assert.equal(await evaluate(picker+'.value'),'d04/p1/t2');
    }
    await evaluate(toggle+'.click()');
    assert.equal(await evaluate(q('.reader-citation-marks')),null);
    await evaluate(toggle+'.click()');
    await evaluate('(()=>{const p='+picker+',i=[...p.options].findIndex(o=>o.value==='+JSON.stringify(accepted)+');p.selectedIndex=i-1;p.focus()})()');
    for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key:'ArrowDown',code:'ArrowDown',windowsVirtualKeyCode:40});
    assert.equal(await evaluate('document.activeElement.id'),'reader-citation-picker');
    assert.equal(await evaluate(picker+'.value'),accepted);
    assert.ok(await evaluate(q('#reader-citation-detail strong')+'.textContent.includes("第 9 行")'));
    await evaluate(summary+'.click();'+q('#reader-citation-detail a[href*="H04-6"]')+'.click()');
    await wait('location.hash.includes("rev=8&finding=H04-6") && !'+q('#page-dialog')+'.open','same archived payment check');
  }
  await wait('state.bundle?.rev===8','pinned report after following finding');
  const rejected=await evaluate(`(()=>{
    function result(change) {
      const p=structuredClone(state.bundle.report),f=p.graph.facts.find(f=>f.id==="d04/p1/f11");
      change(p,f);
      return OriginalReader.citedFields(p,'d04',1).find(row=>row.fact.id===f.id)?.checks.map(c=>c.id) || [];
    }
    return [
      result((p,f)=>f.source_sha256='wrong'),result((p,f)=>f.page_sha256='other-page'),
      result((p,f)=>f.source_line.rects=[[.5,.1,.2,.3]]),
      result(p=>p.graph.nodes.find(n=>n.id==='d04/p1').layer='image'),
      result((p,f)=>p.graph.edges=p.graph.edges.filter(e=>!(e.type==='records' && e.to===f.id))),
      result((p,f)=>p.graph.edges=p.graph.edges.filter(e=>!(e.type==='supports_result' && e.from===f.id && e.to==='finding/H04-6')))
    ];
  })()`);
  assert.deepEqual(rejected,[[],[],[],[],[],ids.filter(id=>id!=='H04-6')]);
  await call('Network.enable'); await call('Network.setBlockedURLs',{urls:['*/documents/d04/pages/1?rev=8']});
  await call('Page.navigate',{url:open});
  await wait(q('.source-error')+'?.getClientRects().length','failed archived page');
  assert.ok(await evaluate(toggle+'.hidden && !'+q('.reader-citation-marks')));
  await call('Network.setBlockedURLs',{urls:[]});
  await evaluate(q('.source-error button')+'.click()');
  await wait(toggle+'?.getClientRects().length && '+q('.page-image')+'.naturalWidth>0','verified page available after retry');
  console.log('PASS · 已出具 R8 页图反查四项检查，六种屏宽、触摸、缩放旋转、键盘选栏及六种证据缺口');
}

async function pendingPages(ctx,task,base) {
  const {root,call,evaluate,wait} = ctx;
  const doc = task.documents.find(d=>d.pages>=20);
  assert.ok(doc);
  await size(ctx,390);
  await call('Page.navigate',{url:root+'/app#case/'+task.id});
  await wait(q('.archive-open')+'?.getClientRects().length','prepared source');
  await evaluate(q('.archive-info')+'.click();window.examinedFile='+q('.archive-open'));
  await evaluate('refresh()');
  assert.ok(await evaluate('examinedFile.isConnected && !document.querySelector(".archive-hash").hidden'));
  await evaluate('examinedFile.focus();examinedFile.click()');
  await wait(q('.page-image')+'?.naturalWidth>0','prepared original before a report');
  assert.ok(await evaluate(q('#reader-revision')+'.hidden && !document.querySelector(".review-selection")'));
  await evaluate(q('.reader-map')+'.click()');
  await wait(q('.reader-thumb img')+'?.naturalWidth>0','first visible thumbnail');
  const loaded = await evaluate(all('.reader-thumb img[src]')+'.length');
  assert.ok(loaded>0 && loaded<doc.pages,'only visible thumbnails requested');
  const jump = q('.reader-jump select');
  await evaluate(jump+'.value='+doc.pages+';'+jump+'.dispatchEvent(new Event("change"))');
  await wait(q('.source-tools a')+'?.href==='+JSON.stringify(base+'/documents/'+doc.id+'/pages/'+doc.pages)+' && '+q('.page-image')+'?.naturalWidth>0','jump to last physical page');
  await wait(q('.reader-thumb[aria-current] img')+'?.naturalWidth>0','selected thumbnail');
  assert.ok(await evaluate(q('.reader-step[data-step="1"]')+'.disabled'));
  assert.equal(await evaluate(q('.reader-thumb[aria-current]')+'.dataset.page'),String(doc.pages));
  const counted = await evaluate(all('.reader-thumb img[src]')+'.length');
  assert.ok(counted<doc.pages,'jumping avoids fetching the pages in between');
  await evaluate(q('#page-dialog [data-close]')+'.click()');
  assert.ok(await evaluate('document.activeElement===examinedFile'));
  console.log('PASS · '+doc.pages+' 页水印资料，处理中的原件、分页直达、按需读取和焦点保留');
}

export async function checkOriginalReader(ctx,id,revision) {
  const {root,call,evaluate,wait} = ctx;
  const base = root+'/api/cases/'+id;
  const task = await (await fetch(base)).json();
  assert.ok(task.title.startsWith('合成演练 · '));
  if (!task.rev) return pendingPages(ctx,task,base);
  const rev = revision || task.rev;
  const {report} = await (await fetch(base+'/reports/'+rev)).json();
  const doc = report.graph.documents.find(d=>d.pages>1);
  const pages = report.graph.nodes.filter(n=>n.type==='page' && n.id.startsWith(doc.id+'/p'));
  const scope = report.graph.facts.filter(f=>f.doc===doc.id && f.page===1 && f.source_line?.rects?.length);
  const anchor = scope.find(f=>['payment_stage','acceptance_result'].includes(f.field)) || scope[0];
  const checklist = rev===task.rev && task.status==='ready';
  const expected = page=>base+'/documents/'+doc.id+'/pages/'+page+'?rev='+rev;
  for (const node of pages) {
    const page = Number(node.id.split('/p')[1]), response = await fetch(expected(page));
    assert.ok(response.ok);
    assert.equal(createHash('sha256').update(Buffer.from(await response.arrayBuffer())).digest('hex'),node.sha256);
  }
  const entry = root+'/workpaper/'+id+'?'+new URLSearchParams({rev,fact:anchor.id});
  const dialog = q('#page-dialog'), picker = q('.field-navigator select');
  const press = s=>evaluate(q(s)+'.click()');
  const next = '.reader-step[data-step="1"]';
  const firstFact = q('.evidence-row[data-fact="'+anchor.id+'"]');
  async function pageLoaded(n) {
    await wait(q('.source-tools > a')+'?.href==='+JSON.stringify(expected(n))+' && '+q('.page-image')+'?.naturalWidth>0','full original '+n);
  }
  await call('Network.enable');
  for (const width of [1440,1024,768,390,360,320]) {
    await size(ctx,width);
    await call('Page.navigate',{url:entry});
    await wait(dialog+'?.open && '+firstFact+'?.classList.contains("located")','original cited row');
    await pageLoaded(1);
    assert.equal(await evaluate(picker+'.value'),anchor.id);
    assert.equal(await evaluate('performance.getEntriesByType("resource").filter(r=>r.name.includes("/thumbnail?")).length'),0);
    if (checklist) await evaluate(firstFact+'.querySelector("input").click()');
    await press('.reader-map');
    await wait(all('.reader-thumb img')+'.every(i=>i.naturalWidth>0)','actual thumbnails');
    const thumbs = await evaluate(all('.reader-thumb img')+'.map(i=>[i.src,i.naturalWidth,i.naturalHeight])');
    assert.deepEqual(thumbs.map(r=>r[0]),pages.map((_,i)=>expected(i+1).replace('?','/thumbnail?')));
    assert.ok(thumbs.every(([,w,h])=>w<=180 && h<=224));
    await press(next); await pageLoaded(2);
    assert.equal(await evaluate(q('.reader-return')+'.hidden'),false);
    assert.equal(await evaluate(all('.evidence-row input:checked')+'.length'),0);
    assert.equal(await evaluate(all('.quote-index .evidence-row[data-fact] > blockquote')+'.filter(n=>n.getClientRects().length).length'),0);
    const currentFact = report.graph.facts.find(f=>f.doc===doc.id && f.page===2);
    if (currentFact) {
      await press('.evidence-row[data-fact="'+currentFact.id+'"] .reader-quote');
      assert.equal(await evaluate(q('.evidence-row.located blockquote')+'.textContent'),currentFact.quote);
      await evaluate(picker+'.value="";'+picker+'.dispatchEvent(new Event("change"))');
      assert.equal(await evaluate(all('.source-plane rect')+'.length'),0);
    }
    if (width===1440 || width===390) {
      const ext=doc.ext.slice(1);
      await inspect(ctx,width,'#reader-navigation','original-'+ext+'-'+doc.pages+'p');
    }
    const geometry = await evaluate(dialog+'.scrollWidth<='+dialog+'.clientWidth+1 && document.documentElement.scrollWidth<=innerWidth+1');
    assert.ok(geometry,'reader fits '+width);
    await evaluate(q('.reader-thumb[aria-current]')+'.focus()');
    for (const [key,number] of [['End',doc.pages],['Home',1]]) {
      await call('Input.dispatchKeyEvent',{type:'keyDown',key,code:key});
      await call('Input.dispatchKeyEvent',{type:'keyUp',key,code:key});
      await pageLoaded(number);
      assert.equal(await evaluate('document.activeElement.dataset.page'),String(number));
    }
    await press(next); await pageLoaded(2);
    await press('.reader-return'); await pageLoaded(1);
    assert.equal(await evaluate(picker+'.value'),anchor.id);
    assert.equal(await evaluate('document.querySelectorAll(".source-plane rect").length'),anchor.source_line.rects.length);
    assert.equal(await evaluate(firstFact+'.querySelector("input")?.checked===true'),checklist);
    await press('#page-dialog [data-close]');
    await press('#tabs [data-tab="evidence"]');
    const tile=all('.archive-file')+'.find(n=>n.querySelector(".archive-name strong").textContent==='+JSON.stringify(doc.name)+')';
    assert.equal(await evaluate(all('.archive-file')+'.length'),report.graph.documents.length);
    if (doc.pages===3) await inspect(ctx,width,'.source-library','original-file-list');
    await evaluate(tile+'.querySelector(".archive-info").click()');
    assert.equal(await evaluate(tile+'.querySelector(".archive-hash:not([hidden]) code").textContent'),doc.sha256);
    assert.equal(await evaluate(tile+'.querySelector(".archive-download").href'),base+'/documents/'+doc.id+'/original?rev='+rev);
    await evaluate(tile+'.querySelector(".archive-open").click()'); await pageLoaded(1);
    assert.equal(await evaluate(all('.evidence-row input:checked')+'.length'),0);
    assert.equal(await evaluate(picker+'.value'),'');
    if (width===1024) {
      await evaluate(q(next)+'.click();'+q('.reader-step[data-step="-1"]')+'.click();'+q(next)+'.click()');
      await pageLoaded(2);
      assert.equal(await evaluate(q('#page-title')+'.textContent'),doc.name+' · 第 2 页');
      assert.equal(await evaluate(all('.evidence-row input:checked')+'.length'),0);
    }
    if (width===390) {
      await call('Network.setBlockedURLs',{urls:[expected(2)]});
      await press(next);
      await wait(q('.source-error')+'?.getClientRects().length','missing original');
      assert.ok(await evaluate(q('.image-sheet')+'.hidden && !document.querySelector(".evidence-row input:enabled, .review-selection button:enabled")'));
      await call('Network.setBlockedURLs',{urls:[]});
      await press('.source-error button'); await pageLoaded(2);
      assert.equal(await evaluate('!!document.querySelector(".source-error")'),false);
    }
    await press('#page-dialog [data-close]');
    const single = report.graph.documents.find(d=>d.pages===1);
    if (single && width===1440) {
      await evaluate(all('.archive-file')+'.find(n=>n.querySelector("strong").textContent==='+JSON.stringify(single.name)+').querySelector(".archive-open").click()');
      await wait(dialog+'.open && '+q('.page-image')+'?.naturalWidth>0','one-page original');
      assert.ok(await evaluate(q('#reader-navigation')+'.hidden && !document.querySelector(".reader-return")'));
      await press('#page-dialog [data-close]');
    }
  }
  console.log('PASS · '+doc.name+' · R'+rev+' · '+doc.pages+' 页 · 六种宽度、原页摘要、页内引文、核图选择隔离及重试');
}
