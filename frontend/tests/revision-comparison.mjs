import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

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
  const input=browserInput(ctx);
  const expand=selector=>evaluate('(()=>{for(let n='+q(selector)+';n;n=n.parentElement) if(n.tagName==="DETAILS") n.open=true;return true;})()');
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
  const change=await evaluate(q('.revision-change')+'.textContent');
  assert.equal(change.includes('三处所引原文一致'),row.shared_approval_lines?.recorded_in.length===1);
  for (const [side,meta] of [['earlier',data.earlier],['later',data.later]]) {
    const s='#revision-comparison [data-side='+side+']';
    assert.equal(await evaluate(q(s+' h3')+'.textContent'),'R'+meta.rev);
    if (row[side]) {
      assert.equal(await evaluate(q(s+' .tag')+'.dataset.state'),row[side].status);
      const shown=await evaluate(q(s+' blockquote')+'.textContent');assert.ok(shown && row[side].detail.includes(shown));
      if (row[side].basis) assert.equal(await evaluate(q(s+' .revision-basis')+'.textContent'),row[side].basis);
    } else assert.match(await evaluate(q(s)+'.textContent'),/缺少可唯一对应/);
  }
  for (const width of [320,390,768,820,1024,1440]) {
    await size(ctx,width);
    assert.ok(await evaluate('[...'+q('#revision-comparison')+'.querySelectorAll("select,a,summary")].filter(n=>n.getClientRects().length).every(n=>n.getBoundingClientRect().right<=innerWidth+1)'));
    if (width<=650) {
      await wait(visible('.revision-actions > #walk-launch'),'mobile comparison actions');
      await evaluate(q('.revision-columns')+'.scrollIntoView({block:"start",behavior:"instant"})');
      const bar=await evaluate(`(()=>{
        const nav=document.querySelector('.revision-actions'), r=nav.getBoundingClientRect();
        return {width:r.width,left:r.left,bottom:innerHeight-r.bottom,targets:[...nav.children].map(el=>{
          const b=el.getBoundingClientRect();
          return [b.height,el.contains(document.elementFromPoint(b.left+b.width/2,b.top+b.height/2))];
        })};
      })()`);
      assert.equal(bar.left,0);assert.equal(bar.width,width);assert.ok(Math.abs(bar.bottom)<=1);
      assert.equal(bar.targets.length,2);assert.ok(bar.targets.every(([height,reachable])=>height>=44 && reachable));
    } else await wait(visible('body > #walk-launch'),'wide-screen feedback launcher');
    if (row.shared_approval_lines && [390,1440].includes(width)) {
      const folds='[...document.querySelectorAll("#revision-comparison .revision-approval-fold")]';
      const head='#revision-comparison [data-side=later] .revision-approval-fold > summary';
      await evaluate(q(head)+'.focus()');await input.key('Enter');
      await wait(folds+'.map(d=>Number(d.open)).join("")==='+JSON.stringify(width===390?'01':'11'),'expand the matching original lines');
      if (width===1440) {
        const ys=await evaluate(folds+'.map(d=>d.querySelector("a").getBoundingClientRect().top)');
        assert.ok(Math.abs(ys[0]-ys[1])<=1,'the two sides align at the cited lines');
      }
      await input.key('Enter');await wait(folds+'.every(d=>!d.open)','collapse the original lines');
    }
    await inspect(ctx,width,'#revision-comparison','revision-'+cid.slice(0,8)+'-'+entry);
  }
  for (const [side,meta] of [['earlier',data.earlier],['later',data.later]]) {
    const item=row[side], source=item?.sources[0];if (!source) continue;
    const area='#revision-comparison [data-side='+side+']', target=area+' .revision-sources:not(.revision-approval-sources) a';
    await expand(target);
    const feedback=await evaluate('import("/assets/walkthrough-context.js").then(m=>{const c=m.captureContext(null,'+q(target)+');return {c,label:m.describeContext(c),url:m.returnUrl(c)}})');
    assert.deepEqual(feedback.c.params,{view:'revision-comparison',prior:String(prior),entry});
    assert.equal(feedback.c.rev,rev);
    assert.ok(feedback.label.includes('履约对照 R'+prior+' / R'+rev));
    assert.ok(feedback.c.target.startsWith('R'+meta.rev+' · '+source.name));
    await size(ctx,390);
    await click(target);
    await wait(q('#page-dialog')+'.open && '+q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(source.ref)+' && '+q('#page-dialog img')+'?.naturalWidth>0','selected side original');
    await wait(visible('#page-dialog #walk-launch'),'feedback available directly on the original');
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
    const approval=item.approval_dates, dates=area+' .revision-approval-sources';
    assert.equal(await evaluate('Boolean('+q(dates)+')'),Boolean(approval));
    if (approval) {
      const {report}=await json(api+'/reports/'+meta.rev);
      const mark=report.findings.find(f=>f.id===item.id).substitution_dates;
      assert.equal(approval.recorded,Boolean(mark));
      for (const slot of ['condition','decision','event']) {
        const s=approval.sources[slot], original=dates+' a[id$="-date-'+slot+'"]';
        await expand(original);
        assert.equal(await evaluate(q(original+' q')+'.textContent'),s.text);
        assert.ok(await evaluate(q(original)+'.getBoundingClientRect().height>=44'));
        if (slot==='decision' && side==='later') {
          await size(ctx,390);await inspect(ctx,390,original,'revision-approval-lines');
          await size(ctx,1440);
          if (row.shared_approval_lines) await wait('document.querySelectorAll(".revision-shared-lines .revision-approval-fold[open]").length===2','both originals stay open in the wider layout');
          await inspect(ctx,1440,area,'revision-approval-lines');
        }
        await input.click(q(original));
        const selected=slot==='event'?'fact':'sourceRef';
        await wait(q('#page-dialog')+'?.open && '+q('#page-content .located')+'?.dataset.'+selected+'==='+JSON.stringify(s.ref)+' && '+q('#page-content img')+'?.naturalWidth>0','the selected revision and line');
        assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+meta.rev);
        const saved=slot==='event'?report.graph.facts.find(f=>f.id===s.ref).source_line.rects:
          report.calls.pages.find(p=>p.doc===s.doc && p.page===s.page).delivery_register_rects[s.line];
        const rects=await evaluate('[...document.querySelectorAll("#page-content .source-plane svg rect")].map(r=>["x","y","width","height"].map(k=>Number(r.getAttribute(k))))');
        assert.deepEqual(rects,saved.map(([a,b,c,d])=>[a,b,c-a,d-b].map(v=>v*1000)));
        await navigate(pinned);await wait(q('#revision-comparison')+'?.dataset.entry==='+JSON.stringify(entry),'back to this item');
      }
      const jump=area+' .revision-links a[id$="-date-check"]';
      assert.equal(await evaluate('Boolean('+q(jump)+')'),approval.recorded);
      if (approval.recorded) {
        await input.click(q(jump));
        await wait('state.bundle?.rev==='+meta.rev+' && '+q('#serial-'+item.id+'-order')+'?.getClientRects().length','open the date comparison in its own revision');
        await navigate(pinned);await wait(q('#revision-comparison')+'?.dataset.entry==='+JSON.stringify(entry),'return after the dated conclusion');
      }
    }
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
    const retest=area+' .revision-links a[id$="-retest"]';
    if (item.retest_reference || item.inspection_use) {
      await click(retest);
      if (item.retest_reference) await wait('state.bundle?.rev==='+meta.rev+' && '+q('#performance-index[open] [data-retest-finding]')+
        '?.dataset.retestFinding==='+JSON.stringify(item.id),'receipt citation in the selected report revision');
      if (item.inspection_use) await wait('state.bundle?.rev==='+meta.rev+' && '+q('#performance-index[open] [data-use-finding]')+
        '?.dataset.useFinding==='+JSON.stringify(item.id),'payment-use statement from this side of the comparison');
      await navigate(pinned);await wait(q('#revision-comparison')+'?.dataset.entry==='+JSON.stringify(entry),'back from receipt citation');
    } else assert.equal(await evaluate(q(retest)),null);
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
    for (const [side,edition] of [['earlier',prior],['later',rev]]) {
      const approval=row[side]?.approval_dates;
      const note=approval?(side==='later'?'请在本版显示批准文件的收件时间。':'希望保留前版引用的这行批准决定。'):
        side==='earlier'?'希望在这里同时看到原合同约定的付款条件。':'请把本次检查所引的两行原文并排显示。';
      const target='#revision-comparison [data-side='+side+'] '+(approval?'a[id$="-date-decision"]':'.revision-sources a');
      const anchor=await evaluate(q(target)+'.id');
      await expand(target);
      await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','recorder');
      await evaluate(q('#walk-text')+'.value='+JSON.stringify(note)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
      await click('#walk-pick');await input.click(q(target));
      await wait(q('#walk-dialog')+'.open && '+q(target)+'.classList.contains("walk-selected")','source selected in the comparison');
      if (approval) assert.ok(await evaluate(q(target)+'.getBoundingClientRect().bottom<='+q('#walk-dialog')+'.getBoundingClientRect().top'),'selected original stays visible above the opinion');
      assert.equal(await evaluate(q('#walk-origin')+'.textContent'),'底稿 '+cid.slice(0,8)+' · R'+prior+' / R'+rev);
      assert.ok((await evaluate(q('#walk-location')+'.textContent')).startsWith('R'+edition+' · '));
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
  await size(ctx,390);await wait(visible('.revision-actions > #walk-launch'),'comparison footer');
  await input.click(q('.revision-actions > a'));
  await wait(visible('#revision-launch a')+' && '+visible('body > #walk-launch'),'collapse comparison and return feedback to the workpaper');
  await navigate(paper+'&view=revision-comparison&prior='+prior+'&entry=new-H05-99999');
  await wait(q('.revision-body')+'?.textContent.includes("没有所选位置")','unknown entry stays unresolved');
  assert.equal(await evaluate(q('.revision-side')),null);
  await navigate(root+'/workpaper/'+cid+'?rev=1');await wait('state.bundle?.rev===1','initial revision');
  assert.equal(await evaluate(q('#revision-launch')+'.hidden'),true);
  console.log('PASS · R'+prior+' / R'+rev+' · '+entry+' · six widths, version-specific findings, original pages and pinned feedback');
}
