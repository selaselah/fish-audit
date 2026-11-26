import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

const q = selector => 'document.querySelector('+JSON.stringify(selector)+')';
export async function checkFolios({root,call,evaluate,wait},cid,revision) {
  const api=root+'/api/cases/'+cid, task=await (await fetch(api)).json(), rev=revision || task.rev;
  assert.ok(task.title.startsWith('合成演练 · '));
  const {report}=await (await fetch(api+'/reports/'+rev)).json();
  const finding=report.findings.find(f=>f.rule==='H03'), check=finding.contract_folios;
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+rev+'&view=contract-pages'});
  await wait(q('.performance-overview')+'?.offsetWidth>0','workpaper');
  if (!check) {
    assert.equal(await evaluate('Boolean('+q('#contract-pages')+')'),false);
    console.log('PASS · historical R'+rev+' has its original findings'); return;
  }
  const card=q('#contract-pages'), ledger=report.graph.contract_folio_sources, p1=check.pages[0], p2=check.pages[1];
  await wait(card+'?.dataset.folioState==='+JSON.stringify(check.state),'verified folio view '+check.state);
  const initial=check.state==='continued'?p2:check.pages.find(p=>p.state===check.state);
  assert.equal(await evaluate(q('.folio-reading')+'.dataset.folioPage'),String(initial.page));
  const buttonFor = p => q('.folio-page[data-folio-page="'+p.page+'"]');
  async function original(id,width,selector) {
    const row=ledger.lines.find(s=>s.id===id), btn=q(selector || '.folio-excerpt[data-folio-ref="'+id+'"]');
    await evaluate(btn+'.focus();'+btn+'.click()');
    await wait(q('#page-dialog .located blockquote')+'?.textContent==='+JSON.stringify(row.quote)+' && '+q('#page-dialog .page-image')+'?.naturalWidth>0','exact physical row '+id);
    const selected=await evaluate(q('#page-dialog .located')+'.dataset.gapLine');
    assert.equal(selected,String(row.line));
    const rects=report.calls.pages.find(c=>c.doc===row.doc && c.page===row.page).contract_folio_rects[row.line];
    assert.equal(await evaluate('document.querySelectorAll("#page-dialog .source-plane svg rect").length'),rects.length);
    const url=await evaluate(q('#page-dialog .source-tools a')+'.href');
    assert.equal(new URL(url).searchParams.get('rev'),String(rev));
    if (width===1440) assert.equal(createHash('sha256').update(Buffer.from(await (await fetch(url)).arrayBuffer())).digest('hex'),row.page_sha256);
    await evaluate(q('#page-dialog [data-close]')+'.click()');
  }
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:false});
    await evaluate(buttonFor(initial)+'.click();'+card+'.scrollIntoView({block:"center",behavior:"instant"})');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth && [...document.querySelectorAll(".folio-card,.folio-layout,.folio-reading,.folio-evidence")].every(el=>el.scrollWidth<=el.clientWidth+1)'));
    await wait('[...document.querySelectorAll(".folio-thumb img")].every(i=>i.naturalWidth>0)','physical page thumbnails');
    await wait(q('.folio-excerpt canvas')+'?.width>0','original printed crop');
    assert.ok(await evaluate('[...document.querySelectorAll(".folio-page,.folio-select,.folio-excerpt")].every(b=>b.offsetWidth>=44&&b.offsetHeight>=44)'));
    if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
      const bounds=await evaluate('(()=>{const r='+card+'.getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}})()');
      const shot=await call('Page.captureScreenshot',{format:'png',clip:bounds,captureBeyondViewport:true});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'folio-'+cid.slice(0,5)+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
    }
    for (const p of check.pages) {
      await evaluate(buttonFor(p)+'.click()');
      const id=await evaluate(q('.folio-select')+'.value');
      assert.equal(id,p.focus);
      if (p.state==='foreign') {
        assert.equal(await evaluate('document.querySelectorAll(".folio-excerpt").length'),2);
        await original(check.root_ref,width);
      }
      if (p.state==='foreign') {
        await evaluate(q('.folio-modes button:nth-child(2)')+'.click()');
        const values=await evaluate('[...document.querySelectorAll(".folio-number")].map(n=>[n.textContent,n.querySelector("mark").textContent])');
        const expected=[check.root_ref,id].map(ref=>ledger.lines.find(r=>r.id===ref).number);
        assert.deepEqual(values.map(v=>v[0]),expected); assert.notEqual(values[0][1],values[1][1]);
        await original(id,width);
        await evaluate(q('.folio-modes button')+'.click()');
      }
      if (id && ledger.lines.find(s=>s.id===id)?.line) await original(id,width);
      const stage=ledger.lines.find(s=>s.page===p.page && s.kind==='stage' && s.unit===check.unit);
      if (!stage) continue;
      await evaluate(q('.folio-select')+'.value='+JSON.stringify(stage.id)+';'+q('.folio-select')+'.dispatchEvent(new Event("change"))');
      await original(stage.id,width);
      const proofs=ledger.lines.filter(s=>s.unit===check.unit && s.page===p.page && s.transcription);
      if (proofs.length) {
        const details=q('.folio-transcripts'), choose=q('.folio-reading-top select'), toggle=q('.folio-spaces input');
        assert.equal(await evaluate(details+'.open'),false);
        await evaluate(details+'.querySelector("summary").focus()');
        await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',text:'\r',windowsVirtualKeyCode:13});
        await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
        await wait(details+'.open','keyboard opens transcript comparison');
        assert.equal(await evaluate(details+'.querySelector("summary small").textContent'),String(proofs.length));
        await evaluate(choose+'.value='+JSON.stringify(proofs[0].id)+';'+choose+'.dispatchEvent(new Event("change"))');
        for (const [index,row] of proofs.entries()) {
          if (index) await evaluate(q('.folio-transcript-step:last-child')+'.click()');
          assert.equal(await evaluate(details+'.dataset.folioTranscript'),row.id);
          assert.equal(await evaluate(choose+'.value'),row.id);
          assert.equal(await evaluate(q('.folio-evidence .folio-excerpt')+'.dataset.folioRef'),row.id);
          assert.equal(await evaluate(q('.folio-transcript-position')+'.textContent'),(index+1)+' / '+proofs.length);
          const expected=[row.quote,row.transcription.quote,row.transcription.value];
          const visible='[...document.querySelectorAll(".folio-literal")].map(el=>el.textContent)';
          assert.deepEqual(await evaluate(visible),expected);
          await evaluate(toggle+'.click()');
          assert.deepEqual(await evaluate(visible),expected.map(s=>s.replaceAll(' ','·')));
          if (row.transcription.form==='temperature' && process.env.AUDIT_UI_SHOTS && [390,1440].includes(width)) {
            const clip=await evaluate('(()=>{const r='+card+'.getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}})()');
            const image=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
            await writeFile(join(process.env.AUDIT_UI_SHOTS,'transcript-'+cid.slice(0,5)+'-'+width+'.png'),Buffer.from(image.data,'base64'));
          }
          await evaluate(toggle+'.click()');
          await original(row.id,width,'.folio-source-link');
          assert.equal(await evaluate('document.activeElement==='+q('.folio-source-link')),true);
        }
        assert.equal(await evaluate(q('.folio-transcript-step:last-child')+'.disabled'),true);
        if (proofs.length>1) {
          await evaluate(q('.folio-transcript-step:first-child')+'.click()');
          assert.equal(await evaluate(choose+'.value'),proofs.at(-2).id);
        }
        await evaluate(details+'.querySelector("summary").click()');
      }
    }
    await evaluate(buttonFor(p2 || p1)+'.focus()');
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Home',code:'Home',windowsVirtualKeyCode:36});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Home',code:'Home',windowsVirtualKeyCode:36});
    assert.equal(await evaluate('document.activeElement.dataset.folioPage'),String(p1.page));
  }
  if (check.state==='numeral') {
    const bad=ledger.lines.find(r=>r.ambiguous_body);
    const phase=report.findings.find(f=>f.rule==='H04' && f.stage?.name===bad.label);
    assert.equal(phase.stage.share,'');
    const tab=q('[data-phase-choice="'+phase.id+'"]');
    assert.equal(await evaluate(tab+'.querySelector("strong").textContent'),'比例待核');
    await evaluate(tab+'.click()');
    await original(bad.id,1440,'.installment-list [data-folio-numeral],li[data-phase-finding] [data-folio-numeral]');
  }
  if (check.standalone) {
    await evaluate(q('[data-folio-independent]')+'.click()');
    const authority=ledger.lines.find(s=>s.id===check.standalone.authority);
    await wait(q('#page-dialog .located blockquote')+'?.textContent==='+JSON.stringify(authority.quote),'express root prepayment');
    await evaluate(q('#page-dialog [data-close]')+'.click()');
  }
  const unknown = report.graph.facts.filter(f=>['bank_receipt','warranty'].includes(f.field) && f.status==='visual' && finding.scope.includes(f.doc));
  for (const f of unknown) {
    await evaluate(q('[data-folio-title="'+f.id+'"]')+'.click()');
    await wait(q('#page-dialog .page-image')+'?.naturalWidth>0 && '+q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(f.id),'unconfirmed image title');
    assert.equal(await evaluate(q('#page-dialog .located blockquote')+'.textContent'),f.quote);
    await evaluate(q('#page-dialog [data-close]')+'.click()');
  }
  const corrupt=['g.edges=g.edges.filter(e=>e.type!=="contract_folio_basis")','g.contract_folio_sources.lines[0].page_sha256+="x"',
                        'c.pages[0].contract_folio_rects={};c.pages.find(p=>p.doc===f.contract_folios.unit).contract_folio_rects={}',
                        'f.contract_folios.state="wrong"','delete f.contract_folios.pages[0].issues','g.contract_folio_sources.lines.find(r=>r.kind==="stage").label="第五期"'];
  const proof=ledger.lines.find(r=>r.transcription?.basis==='visual_check');
  if (proof) {
    const row='g.contract_folio_sources.lines.find(r=>r.id==='+JSON.stringify(proof.id)+')';
    const fact='g.facts.find(f=>f.id==='+JSON.stringify(proof.transcription.ref)+')';
    const call='c.pages.find(p=>p.doc==='+JSON.stringify(proof.doc)+' && p.page==='+proof.page+')';
    corrupt.push(row+'.transcription.form="other"',row+'.transcription.value+="1"',row+'.transcription.basis="field_receipt"',
      fact+'.check_response_id="x"',call+'.check.input=[]',call+'.check.output.checks=[]');
  }
  if (check.state==='numeral') corrupt.push('delete g.contract_folio_sources.lines.find(r=>r.ambiguous_body).ambiguous_body');
  for (const mutate of corrupt) {
    const state=await evaluate('(()=>{const g=structuredClone(state.bundle.report.graph),c=structuredClone(state.bundle.report.calls),'+
      'f=structuredClone(state.bundle.report.findings.find(f=>f.rule==="H03"));'+mutate+';'+
      'const card=ContractFolios.panel(f,g,c.pages);return [card.dataset.folioState,card.querySelectorAll(".folio-excerpt").length]})()');
    assert.deepEqual(state,['unverified',0]);
  }
  console.log('PASS · '+check.state+' R'+rev+' · six widths, keyboard, original hashes, raw line rectangles, altered links');
}

export async function checkPublicFolios({root,call,evaluate,wait}) {
  const sample=await (await fetch(root+'/assets/showcase-payment-folios.json')).json();
  assert.equal(sample.revision,10);
  assert.equal(sample.source_sha256,'053f0ca1aec9a45b5ddef9eacc7e5f8d85b0caa39b73b908bda0bb814aec9ad9');
  assert.deepEqual(sample.pages.map(p=>p.sha256),[
    'cbc975856a4d495ff284bc08ea87b17bc7dce175363949d3c9d5e39d8b785f16',
    '14c1c671cf8a7907825c7d62133f95d02703e0ae52fcb77984fe51f296a0c876',
  ]);
  for (const [path,sha] of [['/showcase/payment-folios.pdf',sample.source_sha256],...sample.pages.map(p=>[p.image,p.sha256])]) {
    const res=await fetch(root+path);
    assert.equal(res.status,200); assert.equal(createHash('sha256').update(Buffer.from(await res.arrayBuffer())).digest('hex'),sha);
  }
  await call('Page.navigate',{url:root+'/?scene=folios#workflow'});
  await wait(q('#scene-folios .folio-highlight')+'?.offsetWidth>0','public folio number comparison');
  assert.equal(await evaluate('performance.getEntriesByType("resource").some(r=>r.name.includes("showcase-payment-folio-")&&r.name.endsWith(".jpg"))'),false);
  const toggle=q('#scene-folios input');
  await wait('[...document.querySelectorAll(".public-folio-thumb img")].length===2 && [...document.querySelectorAll(".public-folio-thumb img")].every(i=>i.naturalWidth>0 && i.naturalWidth<=150)','verified page thumbnails');
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:false});
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth && [...document.querySelectorAll(".scene-tabs button")].every(n=>n.offsetWidth>=44 && n.offsetHeight>=44)'));
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".public-folio-rows mark")].map(m=>m.textContent)'),['LY','OTHER']);
    await evaluate(toggle+'.click()');
    assert.equal(await evaluate('document.querySelectorAll(".public-folio-rows mark").length'),0);
    await evaluate(toggle+'.click()');
    if (process.env.AUDIT_UI_SHOTS && [390,1440].includes(width)) {
      await evaluate(q('.workflow-demo')+'.scrollIntoView({block:"center",behavior:"instant"})');
      const bounds=await evaluate('(()=>{const r='+q('.workflow-demo')+'.getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}})()');
      const shot=await call('Page.captureScreenshot',{format:'png',clip:bounds,captureBeyondViewport:true});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'landing-folios-'+width+'.png'),Buffer.from(shot.data,'base64'));
    }
    for (const [i,p] of sample.pages.entries()) {
      const a=q('.public-folio-rows a:nth-child('+(i+1)+')');
      await evaluate(a+'.click()');
      await wait(q('#sample-review canvas')+'.dataset.fact==='+JSON.stringify(p.focus),'public numbered physical page '+p.page);
      const location=p.lines.find(l=>l.ref===p.focus);
      assert.equal(await evaluate(q('#sample-location')+'.textContent'),'第 '+p.page+' 页 · 第 '+location.line+' 行');
      assert.equal(await evaluate(q('#sample-review .sample-records a')+'.hash'),'#page='+p.page);
      await evaluate(q('#sample-review [data-scale=page]')+'.click()');
      await evaluate(q('#sample-review form button')+'.click()');
      assert.equal(await evaluate('document.activeElement==='+a),true);
    }
  }
  console.log('PASS · public contract R10 · 2 original pages, 6 widths, numbers, PDF and focus');
}
