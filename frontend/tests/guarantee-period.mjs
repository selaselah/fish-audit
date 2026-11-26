// Trace the same calendar controls to immutable originals on a private workpaper and the public site.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {browserInput,inspect,size} from './review-screen.mjs';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const all=s=>'[...document.querySelectorAll('+JSON.stringify(s)+')]';
const widths=[320,360,390,768,1024,1440];
const modal='#performance-index', panel=modal+' .advance-guarantee', card=panel+' .period-card', slot='#payment-guarantee-period';
const paid='2026-09-05',start='2026-09-02';
const names={expired:'付款晚于止日 1 天',covered:'付款日在载明期间内',end_unspecified:'止日是否含当日待核',extension_review:'展期凭证待核'};
const fixtures={dcda3682a4994b1f94b35b29fd22dbe5:'expired',f8d801a40c9e4e24b5d93021295a6655:'covered',
  '27113ff7b88d4cbe995e48b4d93b8d28':'end_unspecified','56975f40714340899938573b4e83981d':'extension_review'};
const hash=buffer=>createHash('sha256').update(Buffer.from(buffer)).digest('hex');

function modified(id,kind) {
  const report=structuredClone(state.bundle.report), f=report.findings.find(f=>f.id===id), p=f.advance_guarantee.period;
  const end=p.sources.find(r=>r.field.startsWith('valid_until'));
  if (kind==='bank') p.paid_on='2026-09-01';
  if (kind==='start') p.valid_from='2026-09-01';
  if (kind==='boundary') p.end_inclusive=!p.end_inclusive;
  if (kind==='quote') end.quote='有效期已延期';
  if (kind==='role') end.role='payment';
  if (kind==='hash') report.graph.nodes.find(n=>n.id===end.doc+'/p'+end.page).sha256='';
  if (kind==='support') report.graph.edges=report.graph.edges.filter(e=>e.from!==end.id || e.to!=='finding/'+f.id);
  if (kind==='stage') report.graph.edges=report.graph.edges.filter(e=>e.type!=='payment_stage' || !e.evidence.includes(f.stage.clause_ref));
  if (kind==='renewed') p.state='renewed';
  if (kind==='claim') p.sources=p.sources.filter(s=>s.id!==end.id);
  if (kind==='method') delete report.policy.code_sha256['guarantee_period.py'];
  if (kind==='qualification') {
    const ex=p.sources.find(s=>s.field==='extension_note'); if (!ex) return null;
    p.sources=p.sources.filter(s=>s.id!==ex.id);
  }
  const section=AdvanceGuarantee.panel(f,report);
  return [section?.querySelector('.period-card')?.dataset.periodState,section?.querySelector('.guarantee-status')?.textContent];
}

async function calendar(ctx,selector,days,endDay,width) {
  const {evaluate}=ctx, {key}=browserInput(ctx);
  const tabs=selector+' .period-day', chosen=tabs+'[aria-selected=true]';
  assert.deepEqual(await evaluate(all(tabs)+'.map(t=>t.dataset.day)'),days);
  assert.equal(await evaluate(q(chosen)+'.dataset.day'),paid);
  assert.equal(await evaluate(q(chosen)+'.getAttribute("aria-controls")==='+q(selector+' .period-selected')+'.id'),true);
  const markers=await evaluate(all(selector+' .period-mark')+'.map(m=>[m.dataset.event,m.dataset.day,parseFloat(m.style.left)])');
  assert.deepEqual(markers.map(r=>r.slice(0,2)),endDay===paid?[['start',start],['end',paid],['paid',paid]]:[['start',start],['end',endDay],['paid',paid]]);
  assert.equal(markers[0][2],0); assert.equal(markers[2][2],100);
  assert.ok(Math.abs(markers[1][2]-(endDay===paid?100:200/3))<.001);
  await evaluate(q(chosen)+'.focus()'); await key('Home');
  assert.equal(await evaluate('document.activeElement.dataset.day'),start);
  await key('ArrowRight'); assert.equal(await evaluate(q(chosen)+'.dataset.day'),endDay);
  await key('End'); assert.equal(await evaluate(q(chosen)+'.dataset.day'),paid);
  await evaluate(q(selector+' .period-mark[data-event=end]')+'.click()');
  assert.equal(await evaluate(q(chosen)+'.dataset.day'),endDay);
  await evaluate(q(selector+' .period-mark[data-event=paid]')+'.click()');
  if (width<600) {
    await browserInput(ctx).tap(q(tabs+'[data-day="'+start+'"]'));
    assert.equal(await evaluate(q(chosen)+'.dataset.day'),start);
    await browserInput(ctx).tap(q(tabs+'[data-day="'+paid+'"]'));
  }
}

export async function checkGuaranteePeriod(ctx,id,rev,previous) {
  const {root,call,evaluate,wait}=ctx, api=root+'/api/cases/'+id, expected=fixtures[id], endDay=['covered','end_unspecified'].includes(expected)?paid:'2026-09-04';
  assert.ok(expected && rev===2 && previous===1);
  const doc=await (await fetch(api+'/reports/'+rev)).json(), report=doc.report;
  const payment=report.findings.find(f=>f.rule==='H05'), phase=report.findings.find(f=>f.rule==='H04');
  assert.equal(payment.advance_guarantee.period.state,expected); assert.equal(payment.stage.name,'第一期');
  const dates=[...new Set([start,endDay,paid])], hashes=new Set(), originals=payment.advance_guarantee.period.sources;
  async function load(r,f) {
    await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev='+r+'&view=payment-checks&stage='+f.id});
    await wait(q(modal)+'?.open && '+q('.scope-check-select')+'?.value==='+JSON.stringify(f.id)+' && state.bundle?.rev==='+r,'load '+f.id+' R'+r);
  }
  async function original(row,width) {
    const sel=q(card+' [data-source="'+row.id+'"]');
    if (width<600) await browserInput(ctx).tap(sel);
    else { await evaluate(sel+'.focus()'); await browserInput(ctx).key('Enter'); }
    const loc=q('#page-dialog .evidence-row.located'), url=api+'/documents/'+row.doc+'/pages/'+row.page+'?rev='+rev;
    await wait(q('#page-dialog')+'.open && '+loc+'?.dataset.sourceRef==='+JSON.stringify(row.id)+' && '+q('.page-image')+'?.naturalWidth>0','open issued date '+row.id);
    assert.deepEqual(await evaluate('['+loc+'.dataset.gapLine,'+loc+'.querySelector("blockquote").textContent,'+q('.source-tools > a')+'.href]'),
      [String(row.line),row.quote,url]);
    const rects=await evaluate(all('.source-plane > svg:first-of-type > rect')+'.map(r=>["x","y","width","height"].map(k=>Number(r.getAttribute(k))))');
    assert.deepEqual(rects,row.rects.map(([l,t,r,b])=>[l*1000,t*1000,(r-l)*1000,(b-t)*1000]));
    if (!hashes.has(url)) { assert.equal(hash(await (await fetch(url)).arrayBuffer()),row.page_sha256); hashes.add(url); }
    await browserInput(ctx).key('Escape');
    await wait('!'+q('#page-dialog')+'.open && document.activeElement==='+sel,'return to selected source');
  }
  for (const width of widths) {
    await size(ctx,width); await call('Emulation.setTouchEmulationEnabled',{enabled:width<600});
    await load(rev,payment);
    assert.equal(await evaluate(q(card)+'.dataset.periodState'),expected);
    assert.equal(await evaluate(q(panel+' .guarantee-status')+'.textContent'),names[expected]);
    assert.equal(await evaluate(q(panel+' .guarantee-panel')+'.dataset.tab'),'period');
    await calendar(ctx,card,dates,endDay,width);
    assert.equal(await evaluate(all(card+' .period-selected .guarantee-source')+'.length'),endDay===paid?2:1);
    if ([390,1440].includes(width)) await evaluate('for (const el of ['+q(modal)+',...'+q(modal)+'.querySelectorAll(".scope-detail,.scope-body,.scope-checks")]) el.scrollTop=0');
    await inspect(ctx,width,modal,'period-'+expected);
    if ([390,1440].includes(width)) {
      await evaluate(q(panel+' [role=switch]')+'.click()');
      await wait(q(card+' .period-selected .guarantee-strip canvas')+'!==null','pinned date excerpt');
      for (const [field,day] of [['valid_from',start],['end',endDay],['paid_on',paid]]) {
        const row=originals.find(r=>field==='end'?r.field.startsWith('valid_until'):r.field===field);
        await evaluate(q(card+' .period-day[data-day="'+day+'"]')+'.click()');
        await wait(q(card+' [data-source="'+row.id+'"] canvas')+'!==null','reload selected original strip');
        await original(row,width);
      }
      await evaluate(q(card+' .period-basis summary')+'.click()');
      await original(originals.find(r=>r.field==='period_clause'),width);
      if (expected==='extension_review') await original(originals.find(r=>r.field==='extension_note'),width);
      await evaluate(q(panel+' .guarantee-tabs button[id$="-dates"]')+'.click()');
      assert.equal(await evaluate(q(panel+' .guarantee-status')+'.textContent'),'付款晚于签收2天');
      const receipt=originals.find(r=>r.field==='received_on');
      assert.ok(await evaluate(q(panel+' [data-source="'+receipt.id+'"]')+'!==null'));
    }
    assert.ok(await evaluate(q(panel)+'.scrollWidth<='+q(panel)+'.clientWidth+1'));
  }
  await load(rev,phase);
  assert.equal(await evaluate(all(card+' [data-event=paid]')+'.length'),0);
  assert.equal(await evaluate(q(card)+'.dataset.periodState'),expected==='extension_review'?'extension_review':'stated');
  for (const other of report.findings.filter(f=>f.rule==='H04' && f.id!==phase.id)) {
    await load(rev,other); assert.equal(await evaluate(q(card)+'!==null'),false);
  }
  await load(previous,payment); assert.equal(await evaluate(q(card)+'!==null'),false);
  await load(rev,payment);
  for (const change of ['bank','start','boundary','quote','role','hash','support','stage','renewed','claim',...(expected==='extension_review'?['qualification']:[])]) {
    assert.deepEqual(await evaluate('('+modified.toString()+')('+JSON.stringify(payment.id)+','+JSON.stringify(change)+')'),['review','期间依据待核'],change);
  }
  assert.deepEqual(await evaluate('('+modified.toString()+')('+JSON.stringify(payment.id)+',"method")'),[null,null]);
  console.log('PASS · guarantee period '+expected+' · six widths, source images, version, keyboard and independent dates');
}

export async function checkPublicGuaranteePeriod(ctx) {
  const {root,call,evaluate,wait}=ctx, {key}=browserInput(ctx);
  const raw=await (await fetch(root+'/assets/guarantee-period-sample.json')).arrayBuffer(), sample=JSON.parse(Buffer.from(raw));
  const opened=new URL('/?scene=guarantee-period#workflow',root).href;
  for (const doc of Object.values(sample.documents)) {
    for (const [url,sha] of [[doc.pdf,doc.source_sha256],[doc.image,doc.page_sha256]]) {
      const r=await fetch(root+url); assert.equal(r.status,200); assert.equal(hash(await r.arrayBuffer()),sha);
    }
  }
  for (const width of widths) {
    await size(ctx,width); await call('Emulation.setTouchEmulationEnabled',{enabled:width<600}); await call('Page.navigate',{url:opened});
    await wait(q(slot)+'?.dataset.revision==="2"','published guarantee');
    assert.equal(await evaluate(q(slot)+'.dataset.integrity'),'sha256-'+createHash('sha256').update(Buffer.from(raw)).digest('base64'));
    assert.equal(await evaluate(q('#payment-example')+'.value'),'guarantee');
    assert.equal(await evaluate(q(slot+' .period-decision')+'.textContent'),names.expired);
    await calendar(ctx,slot,[start,'2026-09-04',paid],'2026-09-04',width);
    await wait(q(slot+' [data-key=paid]')+'?.dataset.printed==="true"','verified printed bank date');
    await evaluate(q(slot+' .period-basis')+'.open=false');
    await inspect(ctx,width,width<600?'#workflow-title':slot,'public-guarantee-period',width<600?'start':'center');
    if ([390,1440].includes(width)) {
      await evaluate('if (!'+q(slot+' .period-basis')+'.open) '+q(slot+' .period-basis summary')+'.click()');
      for (const doc of Object.values(sample.documents)) for (const row of doc.lines) {
        const day={start,end:'2026-09-04',paid}[row.key];
        if (day) await evaluate(q(slot+' .period-day[data-day="'+day+'"]')+'.click()');
        const loc=q(slot+' [data-source="'+row.ref+'"]');
        if (day) {
          await wait(loc+'?.dataset.printed==="true"','verified crop '+row.ref);
          const pixels=await evaluate('(async()=>{const img=new Image();img.src='+JSON.stringify(doc.image)+';await img.decode();'+
            'const [l,t,r,b]='+JSON.stringify(row.rect)+',w=img.naturalWidth,h=img.naturalHeight,'+
            'x=Math.max(0,Math.floor(l*w)-4),y=Math.max(0,Math.floor(t*h)-4),c=document.createElement("canvas");'+
            'c.width=Math.min(w-x,Math.ceil(r*w)+4-x);c.height=Math.min(h-y,Math.ceil(b*h)+4-y);'+
            'c.getContext("2d").drawImage(img,x,y,c.width,c.height,0,0,c.width,c.height);return c.toDataURL()==='+
              loc+'.querySelector(".period-print").toDataURL();})()');
          assert.ok(pixels,'exact pixels of '+row.key);
        }
        await evaluate(loc+'.click()');
        await wait(q('#sample-review')+'.open && '+q('#sample-review canvas')+'.dataset.fact==='+JSON.stringify(row.ref),'read public '+row.ref);
        assert.deepEqual(await evaluate('['+q('#sample-location')+'.textContent,'+q('#sample-review .sample-records a')+'.pathname,'+
          q('#sample-review [aria-pressed=true][data-ref]')+'.dataset.rect]'),['第 1 页 · 第 '+row.line+' 行',doc.pdf,row.rect.join(',')]);
        await key('Escape'); await wait('!'+q('#sample-review')+'.open && document.activeElement==='+loc,'return to '+row.key+' at '+width,3000).catch(async error=>{
          const snap=await evaluate('['+q('#sample-review')+'.open,document.activeElement.outerHTML.slice(0,220),'+loc+'.getClientRects().length,'+q(slot+' details')+'.open]');
          throw new Error(error.message+' '+JSON.stringify(snap));
        });
      }
    }
    assert.equal(await evaluate('performance.getEntriesByType("resource").some(e=>new URL(e.name).pathname.startsWith("/api/"))'),false);
  }
  await call('Page.navigate',{url:root+'/?scene=contract-comments#workflow'});
  await wait(q(slot)+' && typeof PublicGuaranteePeriod!=="undefined" && '+q('#payment-example')+'.value==="comments"','load recovery control');
  const el=q(slot), retry=q(slot+' .standard-retry'), select=q('#payment-example');
  await call('Network.enable'); await call('Network.setBlockedURLs',{urls:['*guarantee-period-sample.json*']});
  await evaluate(select+'.value="guarantee";'+select+'.dispatchEvent(new Event("change"))');
  await wait(retry+'!==null && '+el+'.getAttribute("aria-busy")==="false"','show original PDF links when sample cannot load');
  await call('Network.setBlockedURLs',{urls:[]});
  await evaluate(el+'.dataset.verified='+el+'.dataset.integrity;'+el+'.dataset.integrity="sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";'+retry+'.click()');
  await wait(retry+'!==null && '+el+'.getAttribute("aria-busy")==="false"','show original PDF links on invalid index');
  assert.equal(await evaluate(all(slot+' .period-fallback a')+'.length'),2);
  assert.equal(await evaluate(q(slot+' .period-card')+'!==null'),false);
  await evaluate(el+'.dataset.integrity='+el+'.dataset.verified;'+retry+'.focus();'+retry+'.click()');
  await wait(el+'.dataset.revision==="2"','recover verified dates');
  assert.equal(await evaluate('document.activeElement.dataset.day'),paid);
  await call('Network.setCacheDisabled',{cacheDisabled:true});
  await call('Network.setBlockedURLs',{urls:['*guarantee-period-bank.jpg*']});
  await call('Page.navigate',{url:opened.replace('#workflow','&verify=page#workflow')});
  const bank=q(slot+' [data-key=paid]');
  await wait(bank+' && '+el+'.dataset.revision==="2"','show printed transcription');
  assert.equal(await evaluate(bank+'.querySelector(".period-transcript").textContent'),sample.documents.bank.lines[0].quote);
  await evaluate(bank+'.click()');
  await wait(q('#sample-review')+'.open && '+q('#sample-review [role=status]')+'.textContent.includes("校验")','unavailable page status');
  assert.equal(await evaluate(q('#sample-review canvas')+'.dataset.fact || null'),null);
  assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),sample.documents.bank.pdf);
  await key('Escape'); await call('Network.setBlockedURLs',{urls:[]});
  await evaluate(q(slot+' .period-day[data-day="'+start+'"]')+'.click();'+q(slot+' .period-day[data-day="'+paid+'"]')+'.click()');
  await wait(bank+'.dataset.printed==="true"','restore verified page rendering');
  console.log('PASS · published guarantee, exact original bytes, dates, original links, recovery and six viewport widths');
}
