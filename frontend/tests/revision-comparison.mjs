import assert from 'node:assert/strict';
import {inspect,size} from './review-screen.mjs';

export async function checkRevisionComparison(ctx,cid) {
  const {root,call,evaluate,wait}=ctx, api=root+'/api/cases/'+cid;
  const json=async url=>{const r=await fetch(url);assert.equal(r.status,200);return r.json();};
  const task=await json(api), rev=Number(process.env.AUDIT_COMPARISON_REV || task.rev);
  assert.match(task.title,/演练|合成/);
  const versions=task.revisions.filter(v=>v.rev<rev), nearest=versions[0].rev;
  const prior=Number(process.env.AUDIT_COMPARISON_PRIOR || nearest);
  const data=await json(api+'/reports/'+rev+'/comparison/'+prior);
  const entry=process.env.AUDIT_COMPARISON_ENTRY || data.rows.find(r=>r.changes.includes('status'))?.id ||
    data.rows.find(r=>r.changes.length)?.id || data.rows[0].id;
  const row=data.rows.find(r=>r.id===entry);assert.ok(row);
  const q=s=>'document.querySelector('+JSON.stringify(s)+')', click=s=>evaluate(q(s)+'.click()');
  const visible=s=>q(s)+'?.getClientRects().length';
  const navigate=url=>call('Page.navigate',{url});
  const paper=root+'/workpaper/'+cid+'?rev='+rev;
  const pinned=paper+'&view=revision-comparison&prior='+prior+'&entry='+entry;
  const select=(s,v)=>evaluate('(()=>{const n='+q(s)+';n.value='+JSON.stringify(v)+';n.dispatchEvent(new Event("change",{bubbles:true}))})()');
  await navigate(paper);
  await wait(visible('#revision-launch a'),'compare from the ordinary report');
  assert.equal(await evaluate('performance.getEntriesByType("resource").filter(e=>e.name.includes("/comparison/")).length'),0);
  await click('#revision-launch a');await wait(visible('#revision-entry'),'issued findings loaded');
  if (prior!==nearest) await select('#revision-prior',String(prior));
  await wait(visible('#revision-entry')+' && '+q('#revision-comparison')+'.dataset.prior==='+JSON.stringify(String(prior)),'selected earlier workpaper');
  const choices=await evaluate('[...'+q('#revision-entry')+'.options].map(o=>o.value)');
  assert.deepEqual([...choices].sort(),data.rows.map(r=>r.id).sort());
  await select('#revision-entry',entry);
  assert.equal(await evaluate(q('#revision-comparison')+'.dataset.entry'),entry);
  for (const [side,meta] of [['earlier',data.earlier],['later',data.later]]) {
    const s='#revision-comparison [data-side='+side+']';
    assert.equal(await evaluate(q(s+' h3')+'.textContent'),'R'+meta.rev);
    if (row[side]) {
      assert.equal(await evaluate(q(s+' .tag')+'.dataset.state'),row[side].status);
      const shown=await evaluate(q(s+' blockquote')+'.textContent');assert.ok(shown && row[side].detail.includes(shown));
      if (row[side].basis) assert.equal(await evaluate(q(s+' .revision-basis')+'.textContent'),row[side].basis);
    } else assert.match(await evaluate(q(s)+'.textContent'),/缺少可唯一对应/);
  }
  for (const width of [320,390,768,1024,1440]) {
    await size(ctx,width);
    assert.ok(await evaluate('[...'+q('#revision-comparison')+'.querySelectorAll("select,a,summary")].filter(n=>n.getClientRects().length).every(n=>n.getBoundingClientRect().right<=innerWidth+1)'));
    await inspect(ctx,width,'#revision-comparison','revision-'+cid.slice(0,8)+'-'+entry);
  }
  for (const [side,meta] of [['earlier',data.earlier],['later',data.later]]) {
    const item=row[side], source=item?.sources[0];if (!source) continue;
    const area='#revision-comparison [data-side='+side+']', target=area+' .revision-sources a';
    await evaluate(q(target)+'.closest("details").open=true');
    const feedback=await evaluate('import("/assets/walkthrough-context.js").then(m=>{const c=m.captureContext(null,'+q(target)+');return {c,label:m.describeContext(c),url:m.returnUrl(c)}})');
    assert.deepEqual(feedback.c.params,{view:'revision-comparison',prior:String(prior),entry});
    assert.equal(feedback.c.rev,rev);
    assert.ok(feedback.label.includes('履约对照 R'+prior+' / R'+rev));
    assert.ok(feedback.c.target.startsWith('R'+meta.rev+' · '+source.name));
    await click(target);
    await wait(q('#page-dialog')+'.open && '+q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(source.ref)+' && '+q('#page-dialog img')+'?.naturalWidth>0','selected side original');
    assert.deepEqual(await evaluate('['+q('#reader-revision')+'.textContent,'+q('#page-content .page-view')+'.dataset.doc]'),['R'+meta.rev,source.doc]);
    let delayScript;
    if (side==='earlier' && process.env.AUDIT_COMPARISON_RESILIENCE) {
      delayScript=await call('Page.addScriptToEvaluateOnNewDocument',{source:`
        const nativeComparisonFetch=window.fetch;
        window.fetch=async (...args)=>{
          const result=await nativeComparisonFetch(...args);
          if (String(args[0]).includes('/comparison/')) await new Promise(resolve=>setTimeout(resolve,6600));
          return result;
        };`});
    }
    await navigate(root+feedback.url);
    await wait(q(target)+'?.classList.contains("walk-mark") && '+visible(target),'returned to original expanded source link');
    if (delayScript) await call('Page.removeScriptToEvaluateOnNewDocument',{identifier:delayScript.identifier});
    await click(area+' .revision-links a');
    await wait('state.bundle?.rev==='+meta.rev+' && state.traceId==='+JSON.stringify(item.id),'versioned finding in the graph');
    await navigate(pinned);await wait(q('#revision-comparison')+'?.dataset.entry==='+JSON.stringify(entry),'fixed comparison');
    const board=area+' .revision-links a[id$="-board"]';
    if (item.board_decision) {
      await click(board);
      await wait('state.bundle?.rev==='+meta.rev+' && '+q('#board-decision')+'?.dataset.boardFiling','board filing from the selected revision');
      await navigate(pinned);await wait(q('#revision-comparison')+'?.dataset.entry==='+JSON.stringify(entry),'fixed comparison after board filing');
    } else assert.equal(await evaluate(q(board)),null);
    const quality=area+' .revision-links a[id$="-quality"]';
    if (item.payment_quality) {
      await click(quality);
      await wait('state.bundle?.rev==='+meta.rev+' && '+q('#performance-index[open] [data-quality-finding]')+
        '?.dataset.qualityFinding==='+JSON.stringify(item.id),'quality comparison for this receipt and issued revision');
      await navigate(pinned);await wait(q('#revision-comparison')+'?.dataset.entry==='+JSON.stringify(entry),'back from quality comparison');
    } else assert.equal(await evaluate(q(quality)),null);
  }
  if (process.env.AUDIT_COMPARISON_RESILIENCE && versions.length>1) {
    const alternate=versions.find(v=>v.rev!==prior).rev;
    await evaluate(`window.ordinaryFetch=window.fetch;
      window.fetch=(url,options)=>{
        if (!String(url).includes('/comparison/')) return window.ordinaryFetch(url,options);
        window.fetch=window.ordinaryFetch;
        return Promise.resolve(new Response(JSON.stringify({error:'演练读取中断'}),{status:503}));
      };`);
    await select('#revision-prior',String(alternate));
    await wait(q('#revision-comparison')+'.textContent.includes("演练读取中断")','read failure');
    assert.equal(await evaluate(q('.revision-side')),null);
    await click('#revision-comparison button');
    await wait(visible('#revision-entry')+' && '+q('#revision-prior')+'.value==='+JSON.stringify(String(alternate)),'retry of the same pair');
    await evaluate(`window.fetch=async (url,options)=>{
      if (!String(url).includes('/comparison/')) return window.ordinaryFetch(url,options);
      window.fetch=window.ordinaryFetch;
      const response=await window.ordinaryFetch(url,options);
      const saved=new Response(await response.text(),{status:response.status});
      return new Promise(resolve=>{window.releaseComparison=()=>resolve(saved);});
    };`);
    await select('#revision-prior',String(prior));
    await wait('typeof window.releaseComparison==="function"','prior response held');
    await evaluate('location.hash=Team.hash('+JSON.stringify('case/'+cid+'?rev='+rev+'&view=revision-comparison&prior='+alternate)+')');
    await wait(visible('#revision-entry')+' && '+q('#revision-prior')+'.value==='+JSON.stringify(String(alternate)),'different pair opened');
    await evaluate('window.releaseComparison();new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(done)))');
    assert.equal(await evaluate(q('#revision-comparison [data-side=earlier] h3')+'.textContent'),'R'+alternate);
    await navigate(pinned);await wait(q('#revision-comparison')+'?.dataset.entry==='+JSON.stringify(entry),'restored requested pair');
  }
  if (process.env.AUDIT_ISOLATED_COMPARISON_ORIGIN) {
    assert.deepEqual((await json(root+'/api/walkthrough')).notes,[]);
    await size(ctx,390);
    for (const [side,edition,note] of [['earlier',prior,'希望在这里同时看到原合同约定的付款条件。'],['later',rev,'请把期满单和回单的两行日期并排显示。']]) {
      const target='#revision-comparison [data-side='+side+'] .revision-sources a';
      const anchor=await evaluate(q(target)+'.id');
      await evaluate(q(target)+'.closest("details").open=true');
      await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','recorder');
      await evaluate(q('#walk-text')+'.value='+JSON.stringify(note)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
      await click('#walk-pick');await click(target);
      await wait(q('#walk-dialog')+'.open && '+q(target)+'.classList.contains("walk-selected")','source selected in the comparison');
      if (side==='later') await inspect(ctx,390,'#walk-dialog','revision-feedback');
      await click('#walk-save');await wait('!'+q('#walk-dialog')+'.open','opinion written');
      await navigate(root+'/app#desk');await wait(visible('#case-list')+' && '+visible('#walk-launch'),'queue');
      await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-saved')+'.disabled','open review history');
      const history='#walk-history li a[href*="walkat='+anchor+'"]';
      await click('#walk-saved');await wait(visible(history),'saved opinion');
      assert.ok((await evaluate(q(history)+'.textContent')).includes('履约对照 R'+prior+' / R'+rev));
      await click(history);await wait(q(target)+'?.classList.contains("walk-mark") && '+visible(target),'saved opinion restored both versions and source');
      const saved=(await json(root+'/api/walkthrough')).notes.find(n=>n.text===note);
      assert.deepEqual(saved.context.params,{view:'revision-comparison',prior:String(prior),entry});
      assert.equal(saved.context.anchor,anchor);
      assert.ok(saved.context.target.startsWith('R'+edition+' · '));
    }
    const end=await json(api);assert.deepEqual([end.rev,end.status,end.decisions],[task.rev,task.status,task.decisions]);
  }
  if (row.earlier && row.later) {
    const earlierId='old-'+row.earlier.id;
    await navigate(paper+'&view=revision-comparison&prior='+prior+'&entry='+earlierId);
    await wait(q('#revision-comparison')+'?.dataset.entry==='+JSON.stringify(earlierId),'link by the earlier issued finding');
    assert.equal(await evaluate(q('#revision-entry')+'.value'),row.id);
    assert.equal(new URL(await evaluate(q('#revision-comparison [data-side=later] .revision-links a')+'.href')).searchParams.get('finding'),row.later.id);
  }
  await navigate(paper+'&view=revision-comparison&prior='+prior+'&entry=new-H05-99999');
  await wait(q('.revision-body')+'?.textContent.includes("没有所选位置")','unknown entry stays unresolved');
  assert.equal(await evaluate(q('.revision-side')),null);
  await navigate(root+'/workpaper/'+cid+'?rev=1');await wait('state.bundle?.rev===1','initial revision');
  assert.equal(await evaluate(q('#revision-launch')+'.hidden'),true);
  console.log('PASS · R'+prior+' / R'+rev+' · '+entry+' · five widths, version-specific findings, original pages and pinned feedback');
}
