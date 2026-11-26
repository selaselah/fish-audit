import assert from 'node:assert/strict';
import {size,inspect} from './review-screen.mjs';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const all=s=>'[...document.querySelectorAll('+JSON.stringify(s)+')]';
const widths=[320,360,390,768,1024,1440];

function alteredFieldLinks() {
  const {graph,findings}=state.bundle.report, finding=findings.find(f=>f.rule==='H02');
  const [row]=PerformanceIndex.originals(finding,graph);
  if (!row) return null;
  const id=row.fact.id, target='finding/'+finding.id;
  const supports=e=>e.type==='supports_result' && e.from===id && e.to===target;
  return ['original','support','crossed','record','hash','finding','geometry'].map(change=>{
    const g=structuredClone(graph);
    if (change==='support') g.edges=g.edges.filter(e=>!supports(e));
    if (change==='crossed') g.edges.find(supports).evidence=['a different observation'];
    if (change==='record') g.edges=g.edges.filter(e=>!(e.type==='records' && e.to===id));
    if (change==='hash') g.facts.find(f=>f.id===id).page_sha256='stale';
    if (change==='finding') g.nodes.find(n=>n.id===target).status='disputed';
    if (change==='geometry') g.facts.find(f=>f.id===id).source_line={number:1,text:row.fact.quote,rects:[[0,0,9,1]]};
    const source=PerformanceIndex.originals(finding,g).find(s=>s.fact.id===id);
    return change==='geometry'?source?.line:Boolean(source);
  });
}

export async function checkPerformanceIndex(ctx,id,requested) {
  const {root,call,evaluate,wait}=ctx, base=root+'/api/cases/'+id;
  const task=await (await fetch(base)).json();
  assert.ok(task.title.startsWith('合成演练'));
  const rev=requested || task.rev;
  const {report}=await (await fetch(base+'/reports/'+rev)).json();
  const groups={contract:['H01'],acceptance:['H02'],payment:['H03','H04','H05','H06']};
  const dialog='#performance-index', page='#page-dialog';
  const card=scope=>'[data-audit-scope="'+scope+'"]';
  const checkPick=q('.scope-check-select');
  const key=async name=>{
    for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key:name,code:name,windowsVirtualKeyCode:{Escape:27,Enter:13}[name],
      ...(type==='keyDown' && name==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});
  };
  await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev='+rev+'&view=payment-checks'});
  await wait(q(dialog)+'?.open','pinned payment checks');
  assert.equal(await evaluate(q('#scope-title')+'.textContent'),'分期与付款');
  await key('Escape');
  await wait('!'+q(dialog)+'.open && document.activeElement==='+q(card('payment')),'return to the addressed scope');
  for (const width of widths) {
    await size(ctx,width);
    for (const [scope,rules] of Object.entries(groups)) {
      const items=report.findings.filter(f=>rules.includes(f.rule));
      const pending=items.filter(f=>f.status!=='ok');
      const opener=q(card(scope));
      assert.equal(await evaluate(opener+'.querySelector(".scope-card-count span").textContent'),
        pending.length===0?items.length+' 项相符':pending.length===items.length?items.length+' 项待核':pending.length+' / '+items.length+' 项待核');
      if (scope==='payment') {
        const title=await evaluate(opener+'.querySelector("strong").textContent');
        if (items.find(f=>f.rule==='H03')?.status!=='ok') assert.equal(title,'付款安排');
        else if (items.some(f=>f.execution_basis?.state==='conflict')) {
          const phases=items.filter(f=>f.rule==='H04');
          if (phases.length>1) assert.equal(title,'分 '+phases.length+' 期付款');
        }
      }
      await evaluate(opener+'.focus()'); await key('Enter');
      await wait(q(dialog)+'.open','audit scope from keyboard');
      assert.equal(await evaluate(checkPick+'.checkVisibility()'),width<=650 && items.length>1);
      assert.equal(await evaluate(q('.scope-filters')+'.checkVisibility()'),pending.length>0 && pending.length<items.length);
      const list=()=>evaluate(all('.scope-check')+'.map(b=>b.dataset.check)');
      assert.deepEqual((await list()).sort(),(pending.length?pending:items).map(f=>f.id).sort());
      assert.equal(await evaluate(q('.scope-filters button')+'.disabled'),!pending.length);
      if (pending.length>0 && pending.length<items.length) await evaluate(q('.scope-filters button:last-child')+'.click()');
      assert.deepEqual((await list()).sort(),items.map(f=>f.id).sort());
      const focus=items.find(f=>f.execution_basis?.state==='conflict') || items.find(f=>f.execution_basis) || items[0];
      if (items.length>1) {
        if (width<=650) await evaluate(checkPick+'.value='+JSON.stringify(focus.id)+';'+checkPick+'.dispatchEvent(new Event("change"))');
        else await evaluate(q('.scope-check[data-check="'+focus.id+'"]')+'.click()');
      }
      assert.equal(await evaluate(q('.scope-check-state .tag')+'.dataset.state'),focus.status);
      if (scope==='payment') {
        assert.ok(await evaluate(q(dialog)+'.scrollWidth<='+q(dialog)+'.clientWidth+1'));
        if (focus.execution_basis) await inspect(ctx,width,dialog,'scope-'+focus.execution_basis.state);
      }
      const raw=await evaluate(all('.scope-original-line')+'.map(b=>[Number(b.dataset.sourceLine),b.querySelector("q").textContent])');
      if (focus.execution_basis?.state==='conflict') assert.equal(raw.length,2);
      if (raw.length) {
        const sources=focus.execution_basis ?
          report.graph.payment_execution_sources.rows.filter(row=>focus.execution_basis.rows.includes(row.id)) :
          report.graph.facts.filter(f=>focus.evidence.includes(f.id) && f.source_line).map(f=>({line:f.source_line.number,quote:f.source_line.text,fact:f.id}));
        await wait(all('.scope-original-line canvas')+'.length==='+raw.length,'both physical crops loaded');
        if (scope==='acceptance') await inspect(ctx,width,dialog,'scope-acceptance');
        await evaluate(q('.scope-excerpt-head .scope-source-mode')+'.click()');
        assert.ok(await evaluate(all('.scope-original-line .scope-source-crop')+'.every(c=>c.hidden)'));
        for (const [i,[line,quote]] of raw.entries()) {
          const source=sources.find(row=>row.line===line && row.quote===quote);
          assert.ok(source);
          const trigger=all('.scope-original-line')+'['+i+']';
          await evaluate(trigger+'.focus();'+trigger+'.click()');
          await wait(q(page)+'.open && '+q('.located')+(source.fact?'?.dataset.fact==='+JSON.stringify(source.fact):'?.dataset.gapLine==='+JSON.stringify(String(line))),'cited physical line');
          assert.ok(await evaluate(q('.located')+'.textContent.normalize("NFKC").includes('+JSON.stringify(quote.normalize('NFKC'))+')'));
          await wait(q('#page-dialog .source-plane svg rect')+'!=null','physical receipt rectangle');
          assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
          await key('Escape');
          await wait('!'+q(page)+'.open','close the original');
          assert.ok(await evaluate(q(dialog)+'.open && document.activeElement==='+trigger),'original to its receipt row at '+width+' on line '+line);
        }
      } else {
        const trigger=q('.scope-open-original'), factId=await evaluate(trigger+'?.dataset.fact');
        if (factId) {
          const fact=report.graph.facts.find(f=>f.id===factId);
          assert.ok(focus.evidence.includes(fact.id));
          if (await evaluate(q('.scope-source-quality > span')+'.textContent==="原行"')) {
            await wait(q('.scope-source-crop canvas')+'?.width>0','actual page crop for field');
            await evaluate(q('.scope-source-mode')+'.click()');
            assert.ok(await evaluate(q('.scope-source-crop')+'.hidden && '+q('.scope-source blockquote')+'.textContent==='+JSON.stringify(fact.source_line.text)));
            await evaluate(q('.scope-source-mode')+'.click()');
          }
          await evaluate(trigger+'.focus();'+trigger+'.click()');
          await wait(q(page)+'.open && '+q('.located')+'?.dataset.fact==='+JSON.stringify(fact.id),'selected check fact on original');
          assert.ok(await evaluate(q('.source-tools a')+'.href.endsWith("?rev='+rev+'")'));
          await key('Escape');
          await wait(q(dialog)+'.open && document.activeElement==='+trigger,'return to field evidence');
        }
      }
      await evaluate(q('.scope-actions button:last-child')+'.click()');
      await wait('!'+q(dialog)+'.open && document.activeElement?.dataset.finding==='+JSON.stringify(focus.id),'complete archived check');
    }
  }
  const negative=await evaluate('('+alteredFieldLinks.toString()+')()');
  if (negative) assert.deepEqual(negative,[true,false,false,false,false,false,null]);
  const scan=await evaluate('(()=>{const r=state.bundle.report,f=r.findings.find(f=>f.rule==="H01"),rows=PerformanceIndex.originals(f,r.graph),i=rows.findIndex(x=>!x.fact.source_line && ["confirmed","visual"].includes(x.fact.status));return i>=0?{i,id:rows[i].fact.id,status:rows[i].fact.status}:null;})()');
  if (scan) {
    await evaluate(q(card('contract'))+'.click()');
    const picker=q('.scope-source-head select');
    await evaluate(picker+'.value='+scan.i+';'+picker+'.dispatchEvent(new Event("change"))');
    assert.equal(await evaluate(q('.scope-source-quality > span')+'.textContent'),'提取引文');
    assert.equal(await evaluate(q('.scope-source-quality .tag')+'.dataset.state'),scan.status);
    assert.equal(await evaluate(q('.scope-source-crop')+'.childElementCount'),0);
    await evaluate(q('.scope-open-original')+'.click()');
    await wait(q('.located')+'?.dataset.fact==='+JSON.stringify(scan.id),'scan opens on its own physical page');
    await key('Escape'); await evaluate(q(dialog)+'.close()');
  }
  if (rev===task.rev) {
    await call('Page.navigate',{url:root+'/app#desk'});
    const search=q('#case-search'), peek=q('[data-preview-case="'+id+'"]'), link=q('#case-preview .scope-preview-link');
    await wait(search+'?.checkVisibility() && Desk.fingerprint','case search');
    await evaluate(search+'.value='+JSON.stringify(task.title)+';'+search+'.dispatchEvent(new Event("input",{bubbles:true}))');
    await wait(peek+'!=null','synthetic task in queue'); await evaluate(peek+'.click()');
    await wait(link+'?.checkVisibility()','scope entry from the queue preview');
    assert.equal(await evaluate(link+'.getAttribute("href")'),'/workpaper/'+id+'?rev='+rev+'&view=payment-checks');
    await evaluate(link+'.click()');
    await wait(q(dialog)+'?.open && '+q('#scope-title')+'.textContent==="分期与付款"','same revision from task preview');
    assert.equal(await evaluate('state.bundle.rev'),rev);
  }
  console.log('PASS · R'+rev+' three review scopes, individually issued results, pinned original and return focus · '+widths.join('/'));
}

export async function checkPublicTopics(ctx) {
  const {root,call,evaluate,wait}=ctx;
  const routes=[
    ['signing',['signing','word-signing','contract-dates','pdf-signing'],'signing-example',['company','word','calendar','pdf']],
    ['inspection',['acceptance','inspection','named-inspection','suppliers','word-comments'],'inspection-example',['readings','equipment','named','supplier','comments']],
    ['folios',['contract-comments','payment-proof','signer-clock','signer-timing','payment-acceptance','folios'],'payment-example',['comments','proof','clock','timing','reference','folios']],
  ];
  for (const [tab,scenes,pick,values] of routes) {
    for (const [i,scene] of scenes.entries()) {
      await call('Page.navigate',{url:root+'/?scene='+scene+'#workflow'});
      await wait(q('.scene-tabs')+'?.hidden===false && '+q('#scene-tab-'+tab)+'.getAttribute("aria-selected")==="true" && '+q('#'+pick)+'.value==='+JSON.stringify(values[i]),'public bookmark '+scene);
      const count=await evaluate(q('#scene-tab-'+tab+' small')+'.textContent');
      assert.equal(count,scenes.length+' 个场景');
      assert.equal(await evaluate(all('.workflow-demo > [role=tabpanel]')+'.filter(p=>!p.hidden).length'),1);
    }
  }
  for (const width of widths) {
    await size(ctx,width);
    await evaluate(q('#scene-tab-inspection')+'.click()');
    const control=q('#inspection-example');
    await evaluate(control+'.value="readings";'+control+'.dispatchEvent(new Event("change"))');
    assert.ok(await evaluate('location.search.includes("scene=acceptance")'));
    assert.equal(await evaluate(q('#inspection-version')+'.textContent'),'合成案例 · R8');
    await inspect(ctx,width,'.workflow .section-inner','public-audit-topics');
    const scales=await evaluate(all('.temperature-line')+'.map(img=>img.getBoundingClientRect().width/Number(img.getAttribute("width")))');
    assert.ok(Math.abs(scales[0]-scales[1])<.007,'originals share the same print scale at '+width);
    for (const [ref,line,file] of [['d02/p1/f13',14,'contract'],['d04/p1/f11',12,'acceptance']]) {
      const anchor=q('#inspection-readings [data-ref="'+ref+'"]');
      await wait(anchor+'.querySelector(".temperature-sheet img").naturalWidth===320','physical page miniature');
      const rect=await evaluate(q('#sample-compare figure[data-fact="'+ref+'"]')+'.dataset.rect.split(",").map(Number)');
      const top=await evaluate('parseFloat('+anchor+'.querySelector(".temperature-sheet i").style.top)');
      assert.ok(Math.abs(top-rect[1]*100)<.0001);
      await evaluate(anchor+'.focus();'+anchor+'.click()');
      await wait(q('#sample-review')+'.open && '+q('#sample-review canvas')+'?.dataset.fact==='+JSON.stringify(ref),'open temperature source');
      assert.equal(await evaluate(q('#sample-location')+'.textContent'),'第 1 页 · 第 '+line+' 行');
      assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),'/showcase/'+file+'.pdf');
      await evaluate(q('#sample-review form button')+'.click()');
      await wait('document.activeElement==='+anchor,'back to selected '+file+' original at '+width);
    }
    await evaluate(q('#compare-inspection')+'.click()');
    await wait(q('#sample-compare')+'.open && '+all('#sample-compare canvas')+'.every(c=>c.dataset.scale==="2")','two original pages in comparison');
    assert.deepEqual(await evaluate(all('#sample-compare canvas')+'.map(c=>c.dataset.fact)'),['d02/p1/f13','d04/p1/f11']);
    await evaluate(q('#sample-compare form button')+'.click()');
    await wait('document.activeElement==='+q('#compare-inspection'),'back to comparison button');
    assert.equal(await evaluate('performance.getEntriesByType("resource").some(r=>new URL(r.name).pathname.startsWith("/api/"))'),false);
  }
  console.log('PASS · 15 public scenario addresses in three topics, watermarked original and revision, responsive and keyboard focus');
}
