import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {browserInput,inspect,size} from './review-screen.mjs';

const widths=[320,360,390,768,1024,1440];
const q=selector=>'document.querySelector('+JSON.stringify(selector)+')';
const all=selector=>'[...document.querySelectorAll('+JSON.stringify(selector)+')]';
const sha=(data,format='hex')=>createHash('sha256').update(Buffer.from(data)).digest(format);
const privateCard='#addendum-signing',publicCard='#public-addendum-signing';
const fixed=(root,e,view='addendum-signing')=>root+'/workpaper/'+e.case_id+'?rev='+e.rev+'&view='+view;

async function controls(ctx,selector,edition,width) {
  const {evaluate,wait}=ctx;
  const card=q(selector+' .pdf-signature-card');
  await wait(card+'?.dataset.state==='+JSON.stringify(edition.key),'signed PDF state '+edition.key);
  assert.equal(await evaluate(all(selector+' .pdf-switches button')+'.length'),3);
  assert.deepEqual(await evaluate(all(selector+' .addendum-term strong')+'.map(n=>n.textContent)'),['柜温不高于4℃','柜温不高于2℃']);
  assert.ok(await evaluate(q(selector+' .addendum-terms-head')+'.textContent.includes("生效日待核")'));
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width+'px overflow');
  if (width<=768) {
    const heights=await evaluate(all(selector+' .addendum-term,'+selector+' .pdf-switches button')+'.map(n=>n.getBoundingClientRect().height)');
    assert.ok(heights.every(h=>h>=43.9),'touch targets '+width+'px '+heights);
  }
}

async function verifyDigital(ctx,selector,edition) {
  const {evaluate}=ctx;
  await evaluate(q(selector+' .pdf-switches button:nth-child(2)')+'.click()');
  const details=q(selector+' .pdf-technical'); await evaluate(details+'.open=true');
  assert.ok(await evaluate(details+'.textContent.includes('+JSON.stringify(edition.doc.source_sha256)+')'));
  if (edition.key!=='typeset') {
    const [signature]=edition.signatures;
    assert.ok(await evaluate(details+'.textContent.includes('+JSON.stringify(signature.certificate_sha256)+')'));
    const delta=q(selector+' .pdf-byte-delta');
    if (edition.key==='earlier') assert.match(await evaluate(delta+'.textContent'),/349/);
    else assert.equal(await evaluate('!!'+delta),false);
  }
}

async function compareRows(ctx,selector,edition) {
  const {evaluate,wait}=ctx, {key}=browserInput(ctx);
  const toggle=q(selector+' .addendum-original-mode');
  const terms=all(selector+' .addendum-term'), visible=terms+'.filter(el=>el.getClientRects().length)';
  assert.deepEqual(await evaluate(terms+'.map(el=>el.querySelector("mark").textContent)'),['4','2']);
  await evaluate(toggle+'.focus()'); await key('Space');
  await wait(toggle+'.getAttribute("aria-checked")==="true" && '+visible+'.every(el=>el.querySelector("canvas")?.width>0)','both archived original crops');
  const fields=edition.doc.lines.filter(row=>['previous_criterion','revised_criterion'].includes(row.field));
  for (const [i,row] of fields.entries()) {
    const source=terms+'['+i+']';
    assert.equal(await evaluate(source+'.querySelector(".addendum-line-position").textContent'),'第 1 页 · 第 '+row.line+' 行');
    assert.equal(await evaluate(source+'.querySelector(".addendum-literal").textContent'),row.quote);
    if (selector===publicCard) {
      const equal=await evaluate('(async()=>{const img=await VerifiedSamplePage.load('+JSON.stringify(edition.doc)+');'+
        'const w=img.naturalWidth,h=img.naturalHeight,[l,t,r,b]='+JSON.stringify(row.rect)+';'+
        'const x=Math.max(0,Math.floor(l*w)-4),y=Math.max(0,Math.floor(t*h)-4),crop=document.createElement("canvas");'+
        'crop.width=Math.min(w-x,Math.ceil(r*w)+4-x);crop.height=Math.min(h-y,Math.ceil(b*h)+4-y);'+
        'crop.getContext("2d").drawImage(img,x,y,crop.width,crop.height,0,0,crop.width,crop.height);'+
        'return crop.toDataURL()==='+source+'.querySelector("canvas").toDataURL()})()');
      assert.ok(equal,'exact original pixels '+row.ref);
    }
  }
}

async function publicInvoice(ctx) {
  const {root,call,evaluate,wait}=ctx,{key}=browserInput(ctx),card='#public-addendum-invoice';
  const bytes=await (await fetch(root+'/assets/addendum-invoice-sample.json')).arrayBuffer();
  const sample=JSON.parse(Buffer.from(bytes)), {agreement,bank}=sample.documents;
  const url=root+'/?scene=addendum-invoice#workflow';
  for (const doc of [agreement,bank]) {
    for (const [path,hash] of [[doc.pdf,doc.source_sha256],[doc.image,doc.page_sha256]]) {
      const res=await fetch(root+path);assert.equal(res.status,200);assert.equal(sha(await res.arrayBuffer()),hash);
    }
  }
  for (const width of widths) {
    await size(ctx,width);await call('Page.navigate',{url:url.replace('#','&width='+width+'#')});
    await wait(q(card)+'?.getClientRects().length && '+q('#scene-tab-folios')+'.getAttribute("aria-selected")==="true"','payment condition public entry');
    assert.equal(await evaluate(q('#payment-addendum-invoice')+'.dataset.integrity'),'sha256-'+sha(bytes,'base64'));
    assert.equal(await evaluate(q(card+' .addendum-term mark')+'.textContent'),'且买方收到本合同对应的发票');
    assert.deepEqual(await evaluate(all(card+' time')+'.map(t=>t.dateTime)'),['2026-09-16','2026-09-21','2026-09-22']);
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'));
    if (width<600) assert.ok(await evaluate(all(card+' .addendum-dates a')+'.every(a=>a.getBoundingClientRect().height>=44)'));
    if (![390,1440].includes(width)) continue;
    await inspect(ctx,width,width<600?'#scene-folios':'.workflow .section-inner','public-addendum-invoice',width<600?'start':'center');
    const refs=await evaluate(all(card+' [data-source]')+'.map(el=>el.dataset.source)');
    assert.equal(new Set(refs).size,5);
    for (const ref of refs) {
      const doc=ref.startsWith(bank.id+'/')?bank:agreement, row=doc.lines.find(line=>line.ref===ref);
      const anchor=q(card+' [data-source="'+ref+'"]');
      await evaluate(anchor+'.focus()');await key('Enter');
      await wait(q('#sample-review')+'.open && '+q('#sample-review canvas')+'.dataset.fact==='+JSON.stringify(ref),'dated evidence '+ref);
      assert.equal(await evaluate(q('#sample-location')+'.textContent'),'第 1 页 · 第 '+row.line+' 行');
      assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),doc.pdf);
      await key('Escape');await wait('document.activeElement==='+anchor,'dated evidence restores focus');
    }
  }
  await call('Network.enable');await call('Network.setBlockedURLs',{urls:['*addendum-invoice-sample.json*']});
  await call('Page.navigate',{url:url.replace('#','&offline=1#')});
  const retry=q('#payment-addendum-invoice .standard-retry');
  await wait(retry+'?.getClientRects().length','available fixed PDFs after an invoice-index failure');
  assert.equal(await evaluate(all('#payment-addendum-invoice a')+'.length'),2);
  await call('Network.setBlockedURLs',{urls:[]});await evaluate(retry+'.focus()');await key('Enter');
  await wait('document.activeElement==='+q(card),'invoice retry restores keyboard focus');
  for (const [query,scene] of [['签后修订','addendum-signing'],['收票','addendum-invoice']]) {
    await evaluate(q('#find-case')+'.click()');
    const input=q('#finder-query');
    await wait('document.activeElement==='+input,'case finder focus');
    await call('Input.insertText',{text:query});await wait(all('#finder-results [role=option]')+'.length===1','find by '+query);
    await key('Enter');await wait('!'+q('#case-finder')+'.open && new URL(location.href).searchParams.get("scene")==='+JSON.stringify(scene),'open '+scene+' from the case finder');
  }
}

export async function checkPublicAddendumSigning(ctx) {
  const {root,call,evaluate,wait}=ctx,{key,tap}=browserInput(ctx);
  const bytes=await (await fetch(root+'/assets/addendum-signing-sample.json')).arrayBuffer();
  const {editions}=JSON.parse(Buffer.from(bytes)), url=root+'/?scene=addendum-signing&copy=';
  for (const e of editions) {
    for (const [path,digest] of [[e.doc.pdf,e.doc.source_sha256],[e.doc.image,e.doc.page_sha256]]) {
      const res=await fetch(root+path); assert.equal(res.status,200);assert.equal(sha(await res.arrayBuffer()),digest);
    }
  }
  for (const width of widths) {
    await size(ctx,width); await call('Emulation.setTouchEmulationEnabled',{enabled:width<600});
    await call('Page.navigate',{url:url+'earlier&width='+width+'#workflow'});
    await wait(q(publicCard)+'?.dataset.agreement==="earlier"','cold signed revision');
    assert.equal(await evaluate(q('#signing-addendum')+'.dataset.integrity'),'sha256-'+sha(bytes,'base64'));
    for (const e of [editions[2],editions[1],editions[0]]) {
      const pick=q(publicCard+' button[data-agreement="'+e.key+'"]');
      if (width===390) await tap(pick); else await evaluate(pick+'.click()');
      await controls(ctx,publicCard,e,width);
      assert.equal(await evaluate('new URL(location.href).searchParams.get("copy")'),e.key);
      assert.equal(await evaluate(q('#signing-example-version')+'.textContent'),e.doc.version);
      assert.equal(await evaluate(q(publicCard+' .pdf-signature-head a')+'.pathname'),e.doc.pdf);
      if ([390,1440].includes(width) && e.key==='earlier') {
        await compareRows(ctx,publicCard,e);
        await inspect(ctx,width,width<600?'#scene-signing':'.workflow .section-inner','public-addendum-signing',width<600?'start':'center');
      }
      await verifyDigital(ctx,publicCard,e);
      if (![390,1440].includes(width)) continue;
      const tabs=all(publicCard+' [role=tab]');await evaluate(tabs+'[1].focus()');
      await key('Home'); await wait(tabs+'[0].getAttribute("aria-selected")==="true"','keyboard signature page');
      for (const row of e.doc.lines) {
        const link=q(publicCard+' [data-source="'+row.ref+'"]');
        await evaluate(link+'.focus()'); await key('Enter');
        await wait(q('#sample-review')+'.open && '+q('#sample-review canvas')+'.dataset.fact==='+JSON.stringify(row.ref),'public row '+row.ref);
        assert.equal(await evaluate(q('#sample-location')+'.textContent'),'第 1 页 · 第 '+row.line+' 行');
        assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),e.doc.pdf);
        await key('Escape'); await wait('document.activeElement==='+link,'return to same public row');
      }
    }
  }
  await call('Network.enable'); await call('Network.setBlockedURLs',{urls:['*addendum-signing-sample.json*']});
  await call('Page.navigate',{url:url+'current&network=offline#workflow'});
  await wait(q('#signing-addendum .standard-retry')+'?.getClientRects().length','three original files survive index failure');
  assert.equal(await evaluate(all('#signing-addendum a')+'.length'),3);
  await call('Network.setBlockedURLs',{urls:[]}); await evaluate(q('#signing-addendum .standard-retry')+'.focus()'); await key('Enter');
  await wait(q(publicCard)+'?.dataset.agreement==="current" && document.activeElement.dataset.agreement==="current"','retry restores requested copy and focus');
  await evaluate(q('#scene-tab-inspection')+'.click()');
  assert.ok(await evaluate('!new URL(location.href).searchParams.has("copy")'));
  await call('Network.setCacheDisabled',{cacheDisabled:true});
  await call('Network.setBlockedURLs',{urls:['*batch-version-addendum.jpg*']});
  await call('Page.navigate',{url:url+'earlier&image=offline#workflow'});
  await wait(q(publicCard)+'?.dataset.agreement==="earlier"','index still available');
  await evaluate(q(publicCard+' .addendum-original-mode')+'.click()');
  await wait(all(publicCard+' .addendum-line-position')+'.every(n=>n.textContent.includes("页图暂不可用"))','exact printed text remains available after page failure');
  assert.deepEqual(await evaluate(all(publicCard+' .addendum-literal')+'.map(n=>n.textContent)'),['原验收标准：柜温不高于4℃','变更后验收标准：柜温不高于2℃']);
  await call('Network.setBlockedURLs',{urls:[]}); await call('Network.setCacheDisabled',{cacheDisabled:false});
  await publicInvoice(ctx);
  console.log('Public supplementary agreement: signed revisions and second-instalment invoice prerequisite, five PDF digests, dated source entries, six widths, original pixels, keyboard, retry.');
}

export async function checkPrivateAddendumSigning(ctx) {
  const {root,call,evaluate,wait}=ctx,{key}=browserInput(ctx);
  const {editions}=await (await fetch(root+'/assets/addendum-signing-sample.json')).json();
  for (const [i,width] of widths.entries()) {
    const e=editions[i%3];
    await size(ctx,width); await call('Emulation.setTouchEmulationEnabled',{enabled:width<600});
    await call('Page.navigate',{url:fixed(root,e)});
    await wait(q(privateCard)+'?.getClientRects().length && document.activeElement==='+q(privateCard),'pinned supplementary agreement '+e.key);
    await controls(ctx,privateCard,e,width);
    const resolution=await evaluate('PerformanceIndex.addendumEvidence(state.bundle.report).map(p=>({id:p.record.id,owners:p.bindings.map(b=>b.owner.id),related:p.related.map(f=>f.id),refs:p.lines.map(r=>r.fact.id)}))');
    assert.equal(resolution.length,1);assert.ok(resolution[0].owners.includes(e.finding));
    assert.ok(e.doc.lines.every(row=>resolution[0].refs.includes(row.ref)));
    const href=await evaluate(q(privateCard+' .pdf-signature-head a')+'.href');
    assert.equal(sha(await (await fetch(href)).arrayBuffer()),e.doc.source_sha256);
    assert.equal(await evaluate(q(privateCard+' .addendum-permalink')+'.href'),fixed(root,e)+'&agreement='+e.doc.id);
    if ([390,1440].includes(width)) {
      await compareRows(ctx,privateCard,e);
      await inspect(ctx,width,privateCard,'workpaper-addendum-signing');
    }
    await verifyDigital(ctx,privateCard,e);
    const open=q(privateCard+' .addendum-term:last-child');
    const ref=e.doc.lines.find(row=>row.field==='revised_criterion').ref;
    await evaluate(open+'.focus();'+open+'.click()');
    await wait(q('#page-dialog')+'.open && '+q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(ref),'private revised term and source');
    await key('Escape');await wait('document.activeElement==='+open,'private original restores focus');
  }
  const e=editions[0]; await call('Page.navigate',{url:fixed(root,e,'acceptance-checks')});
  const jump=q('#performance-index .addendum-jump');
  await wait(jump+'?.dataset.proof=== "addendum-pdf/d05" && '+jump+'.getClientRects().length','scoped H02 cites agreement');
  await evaluate(jump+'.click()');
  await wait('!'+q('#performance-index')+'.open && document.activeElement==='+q(privateCard),'H02 exact agreement detail');
  const payment=q(privateCard+' [data-finding-ref]'); const phase=await evaluate(payment+'.dataset.findingRef');
  await evaluate(payment+'.click()');await wait(q('#performance-index')+'.open && '+q('.scope-check-select')+'.value==='+JSON.stringify(phase),'linked payment condition');
  await key('Escape');
  const substitutions=await evaluate(`(()=>{
    const replacements=[
      r=>r.policy.addendum_pdf='older',
      r=>r.graph.addendum_pdf_sources.records[0].original_sha256='0'.repeat(64),
      r=>r.graph.edges=r.graph.edges.filter(e=>e.type!=='addendum_pdf_source'),
      r=>r.graph.nodes.find(n=>n.id==='d05/p1').sha256='0'.repeat(64),
      r=>r.calls.pages.find(p=>p.doc==='d05').check.response_id='',
      r=>r.calls.pages.push({...r.calls.pages.find(p=>p.doc==='d05')}),
      r=>r.graph.edges=r.graph.edges.filter(e=>e.from!=='addendum-pdf/d05'),
      r=>r.graph.addendum_pdf_sources.records[0].fields.push('d04/p1/f1'),
      r=>r.graph.edges=r.graph.edges.filter(e=>e.type!=='procedure_result'),
      r=>r.graph.edges.filter(e=>e.type==='procedure_result').forEach(e=>e.from='control/U01'),
    ];return replacements.map(change=>{const r=structuredClone(state.bundle.report);change(r);return PerformanceIndex.addendumEvidence(r).length;});
  })()`);
  assert.deepEqual(substitutions,Array(10).fill(0));
  await call('Page.navigate',{url:root+'/app#case/'+e.case_id+'?rev=16&rev=15&view=addendum-signing'});
  await wait('document.activeElement.textContent==="请选择一个明确的底稿版本。"','ambiguous hash does not select an original');
  assert.equal(await evaluate(q(privateCard)+'.getClientRects().length'),0);
  await call('Page.navigate',{url:fixed(root,e)+'&agreement=d99'});
  await wait('document.activeElement.textContent==="本版没有所选补充协议的签署凭证。"','unknown agreement in this report');
  assert.equal(await evaluate(q(privateCard)+'.getClientRects().length'),0);
  await call('Page.navigate',{url:fixed(root,e)+'&agreement=d05'});
  await wait(q(privateCard)+'?.dataset.agreement==="addendum-pdf/d05" && document.activeElement==='+q(privateCard),'pinned agreement restores correct original');
  await evaluate(q(privateCard+' .pdf-switches button:last-child')+'.click()');
  const draft=q(privateCard+' .pdf-authority button');
  await evaluate(draft+'.focus();'+draft+'.click()');
  await wait(q('#review-dialog')+'.open && '+q('#review-note')+'.value.includes("采购合同补充协议.pdf") && '+q('#review-decision input:checked')+'.value==="return"','editable human review draft');
  await key('Escape');
  const detail=await (await fetch(root+'/api/cases/'+e.case_id)).json();
  assert.equal(detail.rev,e.rev);assert.deepEqual(detail.decisions,[]);assert.deepEqual(detail.referrals,[]);
  for (const rev of [14,15]) {
    await call('Page.navigate',{url:fixed(root,{...e,rev})});
    await wait('document.activeElement.textContent==="本版未收录补充协议 PDF 签署凭证。"','old revision without substituted evidence');
    assert.equal(await evaluate('!!'+q(privateCard)),false);
  }
  const invoice={case_id:'8c2a157237cf4712856f64225466ee2c',rev:10};
  for (const width of [390,1440]) {
    await size(ctx,width);await call('Page.navigate',{url:fixed(root,invoice)+'&agreement=d04'});
    await wait(q(privateCard)+'?.dataset.agreement==="addendum-pdf/d04" && document.activeElement==='+q(privateCard),'payment amendment original');
    const clauses=await evaluate(all(privateCard+' .addendum-term strong')+'.map(n=>n.textContent)');
    assert.deepEqual(clauses,['第二期：最终验收合格后支付60%','第二期：最终验收合格且买方收到本合同对应的发票后支付60%']);
    assert.equal(await evaluate(q(privateCard+' .addendum-term[data-side=after] mark')+'.textContent'),'且买方收到本合同对应的发票');
    assert.equal(await evaluate('Boolean('+q(privateCard+' .addendum-term[data-side=before] mark')+')'),false);
    const phases=await evaluate(all(privateCard+' [data-finding-ref]')+'.map(b=>[b.dataset.findingRef,b.textContent])');
    assert.deepEqual(phases,[['H04-6','第二期条件'],['H05-8','第二期实付']]);
    await inspect(ctx,width,privateCard,'addendum-invoice-condition');
    for (const [ref] of phases) {
      const link=q(privateCard+' [data-finding-ref="'+ref+'"]');
      await evaluate(link+'.focus();'+link+'.click()');
      await wait(q('#performance-index')+'.open && '+q('.scope-check-select')+'.value==='+JSON.stringify(ref),'second instalment '+ref);
      assert.ok(await evaluate(q('#performance-index .addendum-jump')+'.dataset.proof==="addendum-pdf/d04"'));
      await key('Escape');
    }
  }
  console.log('Private supplementary agreement: four issued workpapers, original-line compare, fixed unit links, six widths, second instalment invoice prerequisite and payment, ten substitutions, historical R14/R15.');
}
