import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {browserInput,inspect,size} from './review-screen.mjs';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const all=s=>'[...document.querySelectorAll('+JSON.stringify(s)+')]';
const digest=(b,encoding='hex')=>createHash('sha256').update(Buffer.from(b)).digest(encoding);
const fixed=(root,s)=>root+'/workpaper/'+s.case_id+'?rev='+s.rev+'&view=acceptance-checks&acceptance='+s.doc.id;

export async function checkAcceptanceOriginals(ctx,privatePaper) {
  const {root,call,evaluate,wait}=ctx,{key,tap}=browserInput(ctx);
  const data=await (await fetch(root+'/assets/acceptance-original-samples.json')).arrayBuffer();
  const {editions}=JSON.parse(Buffer.from(data));
  const url=root+'/?scene=word-comments&record=';
  const source=privatePaper?'#performance-index .accept-original':'#inspection-comments .accept-original',card=q(source);
  const dialog=q(privatePaper?'#page-dialog':'#sample-review');
  for (const s of editions) {
    assert.equal(digest(await (await fetch(root+s.doc.original)).arrayBuffer()),s.doc.source_sha256);
    assert.equal(digest(await (await fetch(root+s.doc.image)).arrayBuffer()),s.doc.page_sha256);
  }
  for (const width of [320,390,768,820,1024,1440]) {
    await size(ctx,width);await call('Emulation.setTouchEmulationEnabled',{enabled:width<600});
    for (const s of editions) {
      await call('Page.navigate',{url:privatePaper?fixed(root,s):url+s.key+'#workflow'});
      await wait(card+'?.dataset.receiptOriginal==='+JSON.stringify(s.id),'filed acceptance '+s.key+' at '+width);
      const active=await evaluate(all(source+' [role=tab]')+'.filter(b=>b.getAttribute("aria-selected")==="true").map(b=>b.dataset.field)');
      assert.deepEqual(active,s.key==='scan'?[]:[{limited:'notes',hot:'measured_result',retest:'defect_closure'}[s.key] || 'acceptance_signer']);
      assert.equal(await evaluate(q(source+' .accept-file')+'.download'),s.doc.name);
      await wait(q(source+' .accept-thumb canvas')+'?.width>0','real page thumbnail');
      assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),true);
      assert.ok(await evaluate(all(source+' [role=tab]')+'.every(b=>b.scrollWidth<=b.clientWidth+1 && b.getBoundingClientRect().height>=43.9)'),'field controls fit');
      if (privatePaper) {
        assert.equal(await evaluate('state.bundle.rev'),s.rev);
        assert.equal(await evaluate(q(source+' .accept-original-link')+'.href'),fixed(root,s));
      } else {
        assert.equal(await evaluate(q('#inspection-version')+'.textContent'),s.doc.version);
        assert.equal(await evaluate(q('.accept-example-tools output')+'.dataset.state'),s.status);
        assert.equal(await evaluate(q('#inspection-comments')+'.dataset.integrity'),'sha256-'+digest(data,'base64'));
      }
      if (![390,1440].includes(width)) continue;
      if (['limited','scan','retest'].includes(s.key)) await inspect(ctx,width,privatePaper?source:'#scene-inspection',
        (privatePaper?'workpaper':'public')+'-accept-original-'+s.key,'center');
      if (s.key==='scan') {
        assert.equal(await evaluate(all(source+' .accept-source-line')+'.length'),0);
        const page=q(source+' .accept-page');
        if (width===390) await tap(page); else await evaluate(page+'.focus();'+page+'.click()');
        await wait(dialog+'.open','whole scanned acceptance');
        if (!privatePaper) {
          await wait(q('#sample-review canvas')+'.dataset.page==="1"','archived scan');
          assert.equal(await evaluate(all('#sample-review .sample-records button[data-ref]')+'.length'),0);
        }
        await key('Escape');await wait('!'+dialog+'.open','close scan');
      } else {
        for (const row of s.doc.lines) {
          const tab=q(source+' [data-field="'+row.field+'"]');
          assert.ok(await evaluate(tab+'!==null'),'cited field '+s.key+' '+row.field);
          if (width===390) await tap(tab); else await evaluate(tab+'.focus();'+tab+'.click()');
          const open=q(source+' .accept-source-line');
          await wait(open+'.dataset.fact==='+JSON.stringify(row.ref)+' && '+open+'.querySelector("canvas")','archived field pixels '+s.key+' '+row.field);
          assert.equal(await evaluate(q(source+' .accept-source-quote')+'.textContent'),row.quote);
          if (row.field==='acceptance_signer' || row.field==='defect_closure') {
            await evaluate(open+'.focus();'+open+'.click()');await wait(dialog+'.open','open selected physical row');
            const located=privatePaper?q('#page-dialog .located')+'?.dataset.fact':q('#sample-review canvas')+'.dataset.fact';
            await wait(located+'==='+JSON.stringify(row.ref),'exact archived row');
            await key('Escape');await wait('!'+dialog+'.open && document.activeElement==='+open,'return focus to source');
          }
        }
        if (s.notes.length) {
          const first=q(source+' [data-field=acceptance_signer]');
          await evaluate(first+'.focus()');await key('End');
          assert.equal(await evaluate(q(source+' .accept-field-panel')+'.dataset.view'),'notes');
          assert.equal(await evaluate(q(source+' blockquote')+'.textContent'),s.notes[0].text);
          assert.equal(await evaluate(q(source+' mark')+'.textContent'),s.notes[0].anchor.selected);
          const jump=q(source+' .word-page-jump');await evaluate(jump+'.focus();'+jump+'.click()');
          await wait(dialog+'.open','open selected note anchor');
          const located=privatePaper?q('#page-dialog .located')+'?.dataset.fact':q('#sample-review canvas')+'.dataset.fact';
          await wait(located+'==='+JSON.stringify(s.notes[0].location.facts[0]),'note opens the issued result line');await key('Escape');
        }
      }
      if (s.key==='clean' && width===1440) {
        await evaluate(q(source+' .accept-file-verify summary')+'.click()');const check=q(source+' .agreement-check button');
        await evaluate(check+'.focus()');await key('Enter');await wait(q(source+' .agreement-check')+'.dataset.state==="match"','fresh original matches this filing');
      }
    }
  }
  const s=editions.find(e=>e.key==='limited');
  if (privatePaper) {
    const pageSelections=await evaluate(`(()=>{
      const blank=async()=>null, control=()=>document.createElement('button');
      const view=AcceptanceOriginalCard.render({record:'test-only',name:'两页验收单',original:'#',hash:'0'.repeat(64),notes:[],
        pages:[1,2].map(number=>({number,control,thumbnail:blank})),
        lines:[1,2].map(page=>({ref:'page'+page,field:'acceptance_signer',page,line:5,quote:'签认栏',control,excerpt:blank}))},'two-page-test');
      const select=(query,value)=>{const el=view.querySelector(query);el.value=value;el.dispatchEvent(new Event('change'));};
      select('.accept-field-select','1');
      const bound=view.querySelector('.accept-page').getAttribute('aria-label'), independent=!!view.querySelector('.accept-page-select');
      view.querySelector('[data-field=pages]').click();select('.accept-page-select','1');
      const free=view.querySelector('.accept-page').getAttribute('aria-label');
      view.querySelector('[data-field=acceptance_signer]').click();
      return [bound,independent,free,view.querySelector('.accept-source-line').dataset.fact,!!view.querySelector('.accept-page-select')];
    })()`);
    assert.deepEqual(pageSelections,['查看两页验收单第 2 页整页',false,'查看两页验收单第 1 页整页','page1',false]);
    await call('Page.navigate',{url:fixed(root,s)});await wait(card+'?.getClientRects().length','issued Word original');
    const toggle=q('[data-receipt-payments="'+s.id+'"]');
    await evaluate(toggle+'.click()');
    const buttons=await evaluate(all('.scope-receipt-phase')+'.map(b=>b.dataset.receiptPhase)');
    const issued=await evaluate('state.bundle.report.findings.filter(f=>f.stage && f.evidence.includes('+JSON.stringify(s.id)+')).map(f=>f.id)');
    assert.deepEqual(buttons,issued);
    const forward=q('[data-receipt-phase="'+buttons[0]+'"]');await evaluate(forward+'.focus()');await key('Enter');
    await wait(q('.scope-check-select')+'.value==='+JSON.stringify(buttons[0])+' && '+card+'?.getClientRects().length','payment check carries the same receipt');
    await evaluate(q('.scope-back')+'.click()');await wait('document.activeElement==='+forward,'return to the same linked payment');
    const broken=await evaluate(`(()=>{
      const actions=[
        r=>delete r.policy.code_sha256['acceptance_originals.py'],
        r=>r.graph.acceptance_original_sources.records[0].original_sha256='0'.repeat(64),
        r=>r.graph.edges=r.graph.edges.filter(e=>e.type!=='acceptance_original_word'),
        r=>r.graph.edges=r.graph.edges.filter(e=>e.type!=='word_review_anchor'),
        r=>r.graph.edges=r.graph.edges.filter(e=>e.type!=='supports_result'||!e.from.startsWith('acceptance-original/')),
        r=>r.calls.pages.find(c=>c.doc==='d02').page_sha256='0'.repeat(64),
        r=>r.findings.find(f=>f.rule==='H02').acceptance_originals=[]
      ];
      return actions.map(m=>{const r=structuredClone(state.bundle.report);m(r);return PerformanceIndex.receiptEvidence(r.findings.find(f=>f.rule==='H02'),r).filter(p=>p.record.kind).length;});
    })()`);
    assert.deepEqual(broken,Array(7).fill(0));
    for (const invalid of [fixed(root,{...s,rev:s.rev-1}),fixed(root,s).replace('acceptance=d02','acceptance=d03')]) {
      await call('Page.navigate',{url:invalid});await wait(q('#performance-index .scope-empty[role=status]')+'?.textContent.includes("未收录")','historical or unrelated source');
      assert.equal(await evaluate('!!'+card),false);
    }
    const duplicate=await fetch(fixed(root,s)+'&acceptance=d01');assert.equal(duplicate.status,400);
  } else {
    await call('Network.enable');await call('Network.setCacheDisabled',{cacheDisabled:true});
    await call('Network.setBlockedURLs',{urls:['*acceptance-original-samples.json*']});
    await call('Page.navigate',{url:url+'clean#workflow'});
    const retry=q('.accept-source-retry');await wait(retry+'?.getClientRects().length','source index fallback');
    assert.equal(await evaluate(q('.public-accept-file > a')+'.pathname'),editions[0].doc.original);
    await call('Network.setBlockedURLs',{urls:[]});await evaluate(retry+'.focus()');await key('Enter');
    await wait('document.activeElement==='+card,'retry restores focus');
    await evaluate(q('#acceptance-record')+'.value="history";'+q('#acceptance-record')+'.dispatchEvent(new Event("change"))');
    await wait(q('#public-acceptance-comments')+'?.getClientRects().length && !new URL(location.href).searchParams.has("record")','R7 review remains available');
    assert.equal(await evaluate('performance.getEntriesByType("resource").filter(e=>new URL(e.name).pathname.startsWith("/api/")).length'),0);
  }
  console.log((privatePaper?'Private':'Public')+' acceptance originals: five pinned cases, six widths, physical readings, signature rows, Word comments, scanning and independent payment evidence.');
}
