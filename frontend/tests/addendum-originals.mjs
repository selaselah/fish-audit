import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {browserInput,inspect,size} from './review-screen.mjs';

const q=selector=>'document.querySelector('+JSON.stringify(selector)+')';
const all=selector=>'[...document.querySelectorAll('+JSON.stringify(selector)+')]';
const digest=(raw,format='hex')=>createHash('sha256').update(Buffer.from(raw)).digest(format);
const words={word_text:'printed',word_review:'commented',photo:'scan'};
const widths=[320,390,768,820,1024,1440];
const fixed=(root,e)=>root+'/workpaper/'+e.case_id+'?rev='+e.rev+'&view=addendum-signing&agreement='+e.doc.id;

async function directory(root) {
  const response=await fetch(root+'/assets/addendum-originals-sample.json');assert.equal(response.status,200);
  const bytes=await response.arrayBuffer();
  return {hash:'sha256-'+digest(bytes,'base64'),editions:JSON.parse(Buffer.from(bytes)).editions};
}

async function checkControl(ctx,selector,e) {
  const {evaluate}=ctx,card=q(selector);
  assert.equal(await evaluate(card+'.querySelector(".agreement-original").dataset.state'),e.key);
  assert.equal(await evaluate(card+'.querySelector(".agreement-file-link").download'),e.doc.name);
  assert.ok(!(await evaluate(card+'.querySelector(".pdf-switches,.pdf-technical")')));
  assert.equal(await evaluate(card+'.querySelector(".agreement-verification").open'),false);
  const values=await evaluate(all(selector+' .agreement-verification dd')+'.map(n=>n.textContent)');
  assert.deepEqual(values,[e.doc.source_sha256,e.doc.page_sha256,...(e.review?.part_sha256?[e.review.part_sha256]:[])]);
  const labels=await evaluate(all(selector+' .addendum-term strong')+'.map(n=>n.textContent)');
  assert.deepEqual(labels,e.doc.lines.slice(0,2).map(l=>l.value));
  const notes=await evaluate(all(selector+' .agreement-notes blockquote')+'.map(n=>n.textContent)');
  assert.deepEqual(notes,e.notes.map(n=>n.text));
  const highlighted=await evaluate(all(selector+' .agreement-notes mark')+'.map(n=>n.textContent)');
  assert.deepEqual(highlighted,e.notes.map(n=>n.anchor.selected));
  const views=await evaluate(all(selector+' .agreement-inspector [role=tabpanel]')+'.filter(p=>p.getClientRects().length).map(p=>p.id)');
  assert.equal(views.length,e.key==='photo'?0:1);
  if (views.length) assert.ok(views[0].endsWith(e.notes.length?'view-notes':'view-terms'));
  assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),true);
}

async function checkOriginalBytes(ctx,selector,alternate) {
  const {evaluate,wait}=ctx,{key}=browserInput(ctx);
  const details=q(selector+' .agreement-verification'),summary=q(selector+' .agreement-verification summary');
  const button=q(selector+' .agreement-check button'),row=q(selector+' .agreement-check'),link=q(selector+' .agreement-file-link');
  await evaluate(summary+'.focus()');await key('Enter');await wait(details+'.open','open checksum controls');
  await evaluate(button+'.focus()');
  for (const expected of (alternate?['match','mismatch','unavailable','match']:['match'])) {
    if (expected==='mismatch' || expected==='unavailable') {
      // Substitute the response in this browser only. Both Word files print the same physical page.
      await evaluate(`(()=>{
        const original=${link}.href, previous=window.fetch;
        window.fetch=(url,init)=>{
          if (new URL(url,location.href).href!==original) return previous(url,init);
          window.fetch=previous;
          return ${expected==='mismatch'?'previous('+JSON.stringify(alternate)+',init)':'Promise.resolve(new Response(null,{status:503}))'};
        };
      })()`);
    }
    await key('Enter');
    await wait(row+'.dataset.state==='+JSON.stringify(expected)+' && !'+button+'.hasAttribute("aria-disabled")','original byte comparison '+expected);
    assert.equal(await evaluate('document.activeElement==='+button),true);
  }
  await evaluate(summary+'.focus()');await key('Enter');await wait('!'+details+'.open','close checksum controls');
}

export async function checkNativeAgreements(ctx,privatePaper) {
  const {root,call,evaluate,wait}=ctx, {key,tap}=browserInput(ctx),{editions,hash}=await directory(root);
  const selector=privatePaper?'#addendum-signing':'#public-native-agreement';
  const card=q(selector),reader=q(privatePaper?'#page-dialog':'#sample-review');
  for (const e of editions) {
    const response=await fetch(root+e.doc.original);assert.equal(response.status,200);assert.equal(digest(await response.arrayBuffer()),e.doc.source_sha256);
    assert.equal(digest(await (await fetch(root+e.doc.image)).arrayBuffer()),e.doc.page_sha256);
  }
  const publicUrl=root+'/?scene=addendum-invoice&carrier=';
  for (const width of widths) {
    await size(ctx,width);await call('Emulation.setTouchEmulationEnabled',{enabled:width<600});
    for (const e of editions) {
      await call('Page.navigate',{url:privatePaper?fixed(root,e):publicUrl+words[e.key]+'#workflow'});
      await wait(card+'?.getClientRects().length && '+card+'.querySelector(".agreement-original")?.dataset.state==='+JSON.stringify(e.key),'filed agreement '+e.key);
      await checkControl(ctx,selector,e);
      if (privatePaper) {
        await wait('document.activeElement==='+card,'fixed private unit');
        const binding=await evaluate('PerformanceIndex.addendumEvidence(state.bundle.report).map(p=>({id:p.record.id,owners:p.bindings.map(b=>b.owner.id),rows:p.lines.map(r=>r.fact.id)}))');
        assert.equal(binding.length,1);assert.equal(binding[0].id,e.record_id);assert.ok(binding[0].owners.includes(e.finding));
        assert.ok(e.doc.lines.every(l=>binding[0].rows.includes(l.ref)));
        assert.equal(await evaluate(card+'.querySelector(".addendum-permalink").href'),fixed(root,e));
        assert.equal(digest(await (await fetch(await evaluate(card+'.querySelector(".agreement-file-link").href'))).arrayBuffer()),e.doc.source_sha256);
      } else {
        assert.equal(await evaluate(q('#payment-addendum-invoice')+'.dataset.carrierIntegrity'),hash);
        assert.equal(await evaluate(q('#payment-version')+'.textContent'),e.doc.version);
        assert.ok(await evaluate(all('.agreement-carriers button')+'.every(b=>b.scrollWidth<=b.clientWidth+1 && b.getBoundingClientRect().height>=40)'),'carrier labels fit '+width);
        await wait(card+'.querySelector(".agreement-thumbnail canvas")?.height>0','verified page preview');
      }
      if ([390,1440].includes(width)) {
        if (e.key!=='word_text') await inspect(ctx,width,privatePaper?selector:width===390?'#scene-folios':'.workflow .section-inner',
          (privatePaper?'workpaper':'public')+'-agreement-'+words[e.key],width===390?'start':'center');
        if (width===1440 && e.notes.length) await checkOriginalBytes(ctx,selector,editions[0].doc.original);
        if (width===390 && e.key==='photo') await checkOriginalBytes(ctx,selector);
        if (width===390 && e.notes.length) {
          const signatures=q(selector+' [data-agreement-view=signatures]'),note=q(selector+' [data-agreement-view=notes]');
          await tap(signatures);await wait(signatures+'.getAttribute("aria-selected")==="true"','touch selects signature references');
          const sign=q(selector+' .agreement-signature-line');
          await tap(sign);await wait(reader+'.open','touch opens real signature row');
          const found=privatePaper?q('#page-dialog .located')+'?.dataset.fact':q('#sample-review canvas')+'.dataset.fact';
          await wait(found+'==='+JSON.stringify(e.doc.lines[2].ref),'touch locates filed buyer signature line');
          await key('Escape');await wait('!'+reader+'.open','close signature reference');await tap(note);
        }
        const open=e.notes.length?q(selector+' .word-page-jump'):q(selector+' .agreement-sheet-open');
        await evaluate(open+'.focus();'+open+'.click()');await wait(reader+'.open','original page dialog');
        if (!privatePaper) {
          await wait(q('#sample-review canvas')+'?.dataset.page==="1"','verified original pixels');
          assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),e.doc.original);
          if (e.key==='photo') {
            assert.equal(await evaluate(q('#sample-location')+'.textContent'),'第 1 页 · 整页');
            assert.equal(await evaluate(q('#sample-review canvas')+'.dataset.fact || null'),null);
            assert.equal(await evaluate(all('#sample-review .sample-records button[data-ref]')+'.length'),0);
          } else if (e.notes.length) {
            assert.equal(await evaluate(q('#sample-review canvas')+'.dataset.fact'),e.notes[0].location.facts[0]);
          }
        } else if (e.notes.length) {
          await wait(q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(e.notes[0].location.facts[0]),'filed comment opens exact clause');
        }
        await key('Escape');await wait('!'+reader+'.open && document.activeElement==='+open,'original restores focus');
        if (e.key==='word_review') {
          await evaluate(q(selector+' [data-agreement-view=terms]')+'.click()');
          const toggle=q(selector+' .addendum-original-mode');
          await evaluate(toggle+'.click()');
          await wait(all(selector+' .addendum-excerpt canvas')+'.length===2','actual before and after crops');
        }
      }
    }
  }
  const noted=editions.find(e=>e.key==='word_review');
  if (privatePaper) {
    await call('Page.navigate',{url:fixed(root,{...noted,rev:1})});
    await wait(card+'?.dataset.agreement==='+JSON.stringify(noted.record_id)+' && state.bundle.rev===1','unamended historical Word agreement');
    assert.equal(await evaluate('!!'+q(selector+' .agreement-request')),false);
    const oldNote=await evaluate('PerformanceIndex.addendumEvidence(state.bundle.report)[0].notes[0].location');
    assert.deepEqual(oldNote.facts,[]);assert.equal(oldNote.page,1);
    assert.ok((await evaluate(q(selector+' .word-page-jump')+'.textContent')).includes('核对整页'));
    await call('Page.navigate',{url:fixed(root,noted)});
    await wait(card+'?.dataset.agreement==='+JSON.stringify(noted.record_id),'returned to pinned noted agreement');
    const selectedNote=noted.notes[0].id, finding=q('[data-finding="'+noted.finding+'"]');
    await evaluate('revealPaperTarget('+finding+')');
    await evaluate('[...'+finding+'.querySelectorAll("summary")].find(s=>s.textContent.includes("查看本项全部引文")).click()');
    const citation=q('[data-finding="'+noted.finding+'"] [data-agreement-note="'+selectedNote+'"]');
    await wait(citation+'?.getClientRects().length','issued finding cites a specific Word comment');
    await evaluate(citation+'.click()');
    await wait('document.activeElement?.classList.contains("agreement-notes") && '+q(selector+' [data-note]')+'.dataset.note==='+JSON.stringify(selectedNote),'finding opens its own selected Word comment');
    const broken=await evaluate(`(()=>{
      const mutations=[
        r=>{delete r.policy.code_sha256['original_records.py'];},
        r=>{r.graph.addendum_original_sources.records[0].original_sha256='0'.repeat(64);},
        r=>{r.graph.addendum_original_sources.documents[0].notes[0].location.page=2;},
        r=>{r.graph.edges=r.graph.edges.filter(e=>e.type!=='addendum_original_comment');},
        r=>{r.calls.pages.find(c=>c.doc==='d04').check.response_id=null;},
        r=>{r.graph.edges=r.graph.edges.filter(e=>!(e.type==='supports_result' && e.from==='addendum-original/d04'));},
        r=>{for(const f of r.findings) for(const c of [f.payment_change,f.quality_change]) if(c) c.original_execution=['addendum-original/d03'];}
      ];
      return mutations.map(change=>{const r=structuredClone(state.bundle.report);change(r);return PerformanceIndex.addendumEvidence(r).length;});
    })()`);
    assert.deepEqual(broken,Array(7).fill(0));
    const tabs=selector+' .agreement-inspector-tabs', current=q(tabs+' [data-agreement-view=notes]');
    await evaluate(current+'.focus()');await key('End');
    await wait(q(tabs+' [data-agreement-view=signatures]')+'.getAttribute("aria-selected")==="true"','keyboard opens signature rows');
    const signature=q(selector+' .agreement-signature-line');
    await evaluate(signature+'.focus()');await key('Enter');
    await wait(q('#page-dialog')+'.open && '+q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(noted.doc.lines[2].ref),'printed buyer field opens on its own line');
    await key('Escape');await wait('document.activeElement==='+signature,'signature row focus returns');
    const ask=q(selector+' .agreement-request');await evaluate(ask+'.focus();'+ask+'.click()');
    await wait(q('#review-dialog')+'.open && '+q('#review-note')+'.value.includes("补充协议定稿")','draft for the selected original');
    await key('Escape');
    const detail=await (await fetch(root+'/api/cases/'+noted.case_id)).json();
    assert.equal(detail.rev,noted.rev);assert.deepEqual(detail.decisions,[]);
  } else {
    await call('Page.navigate',{url:publicUrl+'scan#workflow'});
    await wait(card+'?.querySelector(".agreement-original")?.dataset.state==="photo"','scan tab');
    await evaluate(q(selector+' .agreement-sheet-open')+'.click()');await wait(q('#sample-review')+'.open && !'+q('#sample-review .sample-records [data-ref]'),'whole scan without fictitious line marks');
    await key('Escape');await evaluate(q('#carrier-scan')+'.focus()');await key('ArrowLeft');
    await wait(card+'?.querySelector(".agreement-notes mark") && new URL(location.href).searchParams.get("carrier")==="commented"','keyboard carrier navigation');
    const row=q(selector+' .word-page-jump');await evaluate(row+'.focus();'+row+'.click()');
    await wait(q('#sample-review canvas')+'.dataset.fact==='+JSON.stringify(noted.notes[0].location.facts[0]),'Word line navigation after viewing an image-only page');
    await key('Escape');await evaluate(q('#carrier-commented')+'.focus()');
    await key('Home');await wait(q('#public-addendum-invoice')+'?.getClientRects().length && !new URL(location.href).searchParams.has("carrier")','historical PDF case');
    for (const [query,carrier] of [['补充协议 批注','commented'],['补充协议 扫描','scan']]) {
      await evaluate(q('#find-case')+'.click()');await wait('document.activeElement==='+q('#finder-query'),'case finder search');
      await call('Input.insertText',{text:query});await wait(all('#finder-results [role=option]')+'.length===1','exact agreement carrier in finder');
      await key('Enter');await wait(q('#carrier-'+carrier)+'.getAttribute("aria-selected")==="true" && new URL(location.href).searchParams.get("carrier")==='+JSON.stringify(carrier),'open searched carrier');
    }
    await call('Network.enable');await call('Network.setBlockedURLs',{urls:['*addendum-originals-sample.json*']});
    await call('Page.navigate',{url:publicUrl+'commented&trial=offline#workflow'});
    const retry=q('#public-agreement-carrier .standard-retry');
    await wait(retry+'?.getClientRects().length','original stays available when native index is missing');
    assert.equal(await evaluate(q('#public-agreement-carrier [role=status] + a')+'.pathname'),noted.doc.original);
    await call('Network.setBlockedURLs',{urls:[]});await evaluate(retry+'.focus()');await key('Enter');
    await wait('document.activeElement==='+card,'retry focus');
    await call('Network.setBlockedURLs',{urls:['*addendum-original-word.jpg*']});
    await call('Page.navigate',{url:publicUrl+'commented&trial=image#workflow'});
    await wait(row+'?.getClientRects().length','file still opens with an unavailable page image');
    await evaluate(row+'.click()');await wait(q('#sample-review [role=status]')+'.textContent.includes("页图未通过载入校验")','no stale page when source pixels are unavailable');
    assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),noted.doc.original);
    await key('Escape');await call('Network.setBlockedURLs',{urls:[]});await evaluate(row+'.click()');
    await wait(q('#sample-review canvas')+'.dataset.fact==='+JSON.stringify(noted.notes[0].location.facts[0]),'same source loads with verified pixels after recovery');
  }
  console.log((privatePaper?'Private':'Public')+' Word and scan agreements: three fixed originals, six widths, archived evidence, keyboard and source checks passed.');
}
