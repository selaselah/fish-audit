import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

export async function checkWarrantyTickets({root,call,evaluate,wait},cid,revision) {
  const api=root+'/api/cases/'+cid, task=await (await fetch(api)).json(), rev=Number(revision || task.rev);
  assert.ok(task.title.startsWith('合成演练 · '));
  const {report}=await (await fetch(api+'/reports/'+rev)).json(), g=report.graph;
  const phase=report.findings.find(f=>f.rule==='H04' && f.warranty_check), w=phase?.warranty_check;
  const url=root+'/workpaper/'+cid+'?rev='+rev, node=s=>'document.querySelector('+JSON.stringify(s)+')';
  if (task.title.includes('付款后才由采购方关闭') && rev===task.rev && w.tickets?.some(t=>t.state==='late')) {
    await call('Page.navigate',{url:root+'/app'}); await wait(node('#case-search')+'?.getClientRects().length','review queue');
    await evaluate(node('#case-search')+'.value='+JSON.stringify(task.title.replace('合成演练 · ',''))+';'+node('#case-search')+'.dispatchEvent(new Event("input",{bubbles:true}))');
    const link=node('.audit-card a[href="'+new URL(url).pathname+'?rev='+rev+'"]');
    await wait(link+'?.getClientRects().length','warranty case from queue'); await evaluate(link+'.click()');
  } else await call('Page.navigate',{url});
  await wait(node('.performance-overview'),'issued workpaper');
  if (!w?.tickets) {
    assert.equal(await evaluate(node('.ticket-review')),null);
    console.log('PASS · R'+rev+' · no work-order view in this archive'); return;
  }
  const stage=node('[data-phase-choice="'+phase.id+'"]');
  const section='[data-phase-finding="'+phase.id+'"] .phase-evidence', area=node(section), part=s=>node(section+' .ticket-review '+s);
  const rootNode=node(section+' .ticket-review'), picker=part('.ticket-picker');
  await evaluate(stage+'.click()'); await wait(rootNode+'?.getClientRects().length','work-order panel');
  assert.equal(await evaluate(area+'.dataset.mode'),'tickets');
  const priority=w.tickets.find(t=>t.status==='risk') || w.tickets.find(t=>t.status==='missing') || w.tickets[0];
  assert.equal(await evaluate(rootNode+'.dataset.unit'),priority.unit);
  const bank=report.findings.find(f=>f.rule==='H05' && f.warranty_payment);
  const pick=async i=>{
    if (w.tickets.length<=1) return;
    await evaluate(picker+'.selectedIndex='+i+';'+picker+'.dispatchEvent(new Event("change"))');
  };
  if (w.tickets.length>1) {
    const i=await evaluate(picker+'.selectedIndex');
    await evaluate(picker+'.focus()'); const key=i?'ArrowUp':'ArrowDown';
    const event={key,code:key,windowsVirtualKeyCode:i?38:40};
    await call('Input.dispatchKeyEvent',{type:'keyDown',...event}); await call('Input.dispatchKeyEvent',{type:'keyUp',...event});
    assert.notEqual(await evaluate(rootNode+'.dataset.unit'),priority.unit);
    for (const [key,index] of [['Home',0],['End',w.tickets.length-1]]) {
      await call('Input.dispatchKeyEvent',{type:'keyDown',code:key,key});
      assert.equal(await evaluate(rootNode+'.dataset.unit'),w.tickets[index].unit);
    }
  } else assert.equal(await evaluate(picker),null);
  for (const [i,t] of w.tickets.entries()) {
    await pick(i);
    assert.equal(await evaluate(rootNode+'.dataset.unit'),t.unit);
    assert.equal(await evaluate(rootNode+'.dataset.ticketState'),t.state);
    const title=await evaluate(part('h4')+'.textContent');
    if (t.state==='open') assert.ok(title.includes(t.printed_state));
    if (t.state==='late' && bank?.warranty_payment.paid_on<t.closed_on) assert.equal(title,'回单早于工单关闭 '+(Date.parse(t.closed_on)-Date.parse(bank.warranty_payment.paid_on))/86400000+' 天');
    if (t.state==='same_day') assert.ok(title.includes('先后待核'));
    if (t.state==='closed') assert.ok(title.includes('早于期满确认'));
    const refs=await evaluate('[...'+rootNode+'.querySelectorAll("[data-source]")].map(b=>b.dataset.source)');
    const expected=t.identity_conflicts.length?t.identity_conflicts.flatMap(p=>[p.contract_ref,p.ticket_ref]):
      [w.defect_ref,t.refs.warranty_ticket_state];
    for (const id of expected.filter(Boolean)) assert.ok(refs.includes(id),id);
    if (t.closed_by) assert.ok(refs.includes(t.refs.warranty_closed_by));
    const anchors=await evaluate('[...'+rootNode+'.querySelectorAll(".ticket-source")].map(b=>[b.dataset.source,b.querySelector("q").textContent])');
    for (const [id,quote] of anchors) assert.equal(g.facts.find(f=>f.id===id).source_line.text,quote);
    if (anchors.length) await wait(rootNode+'.querySelectorAll(".ticket-ink canvas").length==='+anchors.length,'both original line crops');
    const more=part('.ticket-disclosure');
    if (await evaluate(more)) {
      assert.equal(await evaluate(more+'.getAttribute("aria-expanded")'),'false');
      await evaluate(more+'.click()');
      assert.ok(await evaluate(part('.ticket-fields')+'.getClientRects().length'));
    }
    for (const id of new Set(refs)) {
      assert.ok([phase,...(bank?[bank]:[])].some(f=>f.evidence.includes(id) && g.edges.some(e=>e.type==='supports_result' && e.to==='finding/'+f.id && e.from===id)));
      const link=part('[data-source="'+id+'"]');
      assert.ok(await evaluate(link+'.getClientRects().length'));
      await evaluate(link+'.click()');
      await wait(node('#page-dialog')+'.open && '+node('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(id)+' && '+node('#page-dialog img')+'?.naturalWidth>0','exact work-order evidence '+id);
      await evaluate(node('#page-dialog [data-close]')+'.click()');
    }
    if (await evaluate(more)) await evaluate(more+'.click()');
    const jump=part('.ticket-compare');
    if (await evaluate(jump)) {
      const key=await evaluate(jump+'.dataset.ticketPair');
      const dest=key.includes('warranty-payment')?bank:phase;
      const pair=await evaluate('WarrantyTickets.pairs(state.bundle.report.findings.find(f=>f.id==='+JSON.stringify(dest.id)+'),state.bundle.report.graph).find(p=>p.key==='+JSON.stringify(key)+')');
      assert.deepEqual(anchors.slice(0,2).map(([id])=>id),[pair.left.id,pair.right.id]);
      await evaluate(jump+'.click()');
      await wait('document.querySelectorAll(".compare-leaf canvas").length===2','side-by-side rendered originals');
      assert.equal(await evaluate(node('.compare-presets [aria-pressed=true]')+'.dataset.pair'),key);
      assert.deepEqual(await evaluate('[...document.querySelectorAll(".compare-leaf")].map(n=>n.dataset.fact)'),[pair.left.id,pair.right.id]);
      await evaluate(node('#tabs [data-tab=report]')+'.click()');
      await evaluate(stage+'.click()');
    }
  }
  await pick(w.tickets.indexOf(priority));
  if (['open','late','same_day','closed'].includes(priority.state)) {
    for (const missing of ['relation','condition','printedValue']) {
      const incomplete=await evaluate(`(()=>{
        const r=structuredClone(state.bundle.report), g=r.graph, p=r.findings.find(f=>f.id===${JSON.stringify(phase.id)});
        const w=p.warranty_check, t=w.tickets.find(t=>t.unit===${JSON.stringify(priority.unit)});
        const stateRef=t.refs.warranty_ticket_state, edges=g.edges.filter(e=>e.type==='warranty_ticket_comparison' && e.to===stateRef);
        switch (${JSON.stringify(missing)}) {
          case 'relation': g.edges=g.edges.filter(e=>!edges.includes(e)); break;
          case 'condition': edges.forEach(e=>e.evidence=e.evidence.filter(id=>id!==w.condition_ref)); break;
          case 'printedValue': g.facts.find(f=>f.id===stateRef).value='未见于工单的状态'; break;
        }
        const panel=WarrantyTickets.panel(p,r.findings.filter(f=>f.rule==='H05'),g);
        const paired=WarrantyTickets.pairs(p,g).some(pair=>pair.unit===t.unit);
        return [panel.dataset.ticketState,panel.querySelector('.ticket-compare')===null,paired];
      })()`);
      assert.deepEqual(incomplete,['pending',true,false],missing);
    }
  }
  for (const width of [320,390,600,768,1024,1440]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
    await evaluate('document.activeElement.blur();'+area+'.scrollIntoView({block:"center"});document.fonts.ready.then(()=>true)');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width+' page overflow');
    assert.ok(await evaluate('[...'+rootNode+'.querySelectorAll("button,select")].every(n=>n.getBoundingClientRect().right<='+rootNode+'.getBoundingClientRect().right+1)'),width+' control overflow');
    if (process.env.AUDIT_UI_SHOTS && [390,1440].includes(width)) {
      const clip=await evaluate('(()=>{const b='+area+'.getBoundingClientRect();return {x:b.x+scrollX,y:b.y+scrollY,width:b.width,height:b.height,scale:1}})()');
      const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'ticket-'+cid+'-R'+rev+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
    }
  }
  console.log('PASS · R'+rev+' · '+task.title+' · '+w.tickets.map(t=>t.state).join('/')+' · six widths and exact originals');
}
