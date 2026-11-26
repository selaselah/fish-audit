import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {size,inspect} from './review-screen.mjs';

const q = s=>'document.querySelector('+JSON.stringify(s)+')';
const all = s=>'[...document.querySelectorAll('+JSON.stringify(s)+')]';

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
