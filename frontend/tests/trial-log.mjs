import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const widths=[1440,1024,820,768,390,320];
async function screenshot(call,name,width) {
  if (!process.env.AUDIT_UI_SHOTS || ![390,1440].includes(width)) return;
  const shot=await call('Page.captureScreenshot',{format:'png'});
  await writeFile(join(process.env.AUDIT_UI_SHOTS,name+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
}

export async function checkTrialLog({root,call,wait,evaluate},cid,revision) {
  const api=root+'/api/cases/'+cid, task=await (await fetch(api)).json(), rev=revision || task.rev;
  assert.ok(task.title.startsWith('合成演练 · ') && task.profile==='cn-contract-performance/v1');
  const {report}=await (await fetch(api+'/reports/'+rev)).json();
  const f=report.findings.find(f=>f.rule==='H02'), t=f.reinspection.timing, op=t.operation, log=q('.run-log');
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+rev+'&view=trial'});
  await wait(q('#equipment-reinspection-trail')+'?.open','trial deep link');
  if (!op) {
    await evaluate(q('#trail-tab-final')+'.click()');
    assert.equal(await evaluate('Boolean('+log+')'),false);
    assert.equal(await evaluate(q('#reinspection-wait')+'.dataset.timingState'),t.state);
    console.log('PASS · historical R'+rev); return;
  }
  const expected={run_met:'normal',run_gap:'gap',run_fault:'fault'};
  const rows=report.graph.reinspection_wait_sources.lines;
  await wait(log+'?.dataset.runState==='+JSON.stringify(t.state),'verified signed log '+t.state);
  assert.notEqual(await evaluate(q('#equipment-reinspection-trail')+'.dataset.disposition'),'unverified');
  if (op.longest_seconds!==null) assert.equal(await evaluate(q('.run-inspector')+'.dataset.kind'),expected[t.state]);
  for (const width of widths) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:false});
    await evaluate(q('#reinspection-wait')+'.scrollIntoView({block:"center",behavior:"instant"})');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'));
    assert.ok(await evaluate('[...document.querySelectorAll(".retest-wait,.run-log,.run-inspector")].every(n=>n.scrollWidth<=n.clientWidth+1)'));
    if (op.longest_seconds!==null) {
      const focus=op.intervals.findIndex(s=>s.state==='fault');
      const slots=[...op.intervals,...op.gaps.map(s=>({...s,state:'gap'}))].sort((a,b)=>a.start.localeCompare(b.start));
      const lengths=await evaluate('[...document.querySelectorAll(".run-mark")].map(s=>s.getBoundingClientRect().width)');
      const total=slots.reduce((n,s)=>n+s.seconds,0), pixels=lengths.reduce((n,w)=>n+w,0);
      assert.ok(slots.every((s,i)=>Math.abs(lengths[i]-pixels*s.seconds/total)<1));
      const initial=t.state==='run_gap'?slots.findIndex(s=>s.state==='gap'):focus<0?0:focus;
      await evaluate(q('.run-select')+'.value='+JSON.stringify(String(initial))+';'+q('.run-select')+'.dispatchEvent(new Event("change"))');
      assert.equal(await evaluate(q('.run-inspector')+'.dataset.kind'),expected[t.state]);
      assert.equal(await evaluate(q('.run-mainvalue strong')+'.textContent'),op.longest_seconds===174600?'48小时30分':'24小时');
      assert.ok(await evaluate('[...document.querySelectorAll(".run-picker > *, .run-original")].every(n=>n.offsetWidth>=44 && n.offsetHeight>=44)'));
      await screenshot(call,t.state,width);
      for (let i=0;i<slots.length;i++) {
        await evaluate(q('.run-select')+'.value='+JSON.stringify(String(i))+';'+q('.run-select')+'.dispatchEvent(new Event("change"))');
        const slot=slots[i];
        assert.equal(await evaluate(q('.run-inspector')+'.dataset.kind'),slot.state);
        const refs=slot.state==='gap'?[slot.before_ref,slot.after_ref]:[slot.ref];
        assert.deepEqual(await evaluate('[...document.querySelectorAll(".run-inspector [data-run-ref]")].map(b=>b.dataset.runRef)'),refs);
        for (const ref of refs) {
          const row=rows.find(r=>r.id===ref);
          await evaluate(q('[data-run-ref="'+ref+'"]')+'.click()');
          await wait(q('#page-dialog .located blockquote')+'?.textContent==='+JSON.stringify(row.quote)+' && '+q('#page-dialog .page-image')+'?.naturalWidth>0','exact signed row');
          assert.equal(await evaluate(q('#page-dialog .located')+'.dataset.gapLine'),String(row.line));
          const page=await evaluate(q('#page-dialog a[target=_blank]')+'.href');
          assert.equal(new URL(page).searchParams.get('rev'),String(rev));
          if (width===1440) {
            assert.equal(createHash('sha256').update(Buffer.from(await (await fetch(page)).arrayBuffer())).digest('hex'),row.page_sha256);
          }
          await evaluate(q('#page-dialog [data-close]')+'.click()');
        }
      }
      await evaluate(q('.run-arrow')+'.click()');
      assert.equal(await evaluate(q('.run-select')+'.selectedIndex'),slots.length-2);
      await evaluate(q('.run-select')+'.focus()');
      await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Home',code:'Home',windowsVirtualKeyCode:36});
      await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Home',code:'Home',windowsVirtualKeyCode:36});
      assert.equal(await evaluate(q('.run-select')+'.selectedIndex'),0);
    } else {
      assert.equal(t.state,'run_device');
      assert.equal(await evaluate('Boolean('+q('.run-track')+')'),false);
      for (const [i,serial] of [op.serial,op.log_serial].entries()) {
        const b='.run-log > .run-original:nth-child('+(i+1)+')';
        assert.ok((await evaluate(q(b)+'.textContent')).includes(serial));
        await evaluate(q(b)+'.click()');
        await wait(q('#page-dialog .located blockquote')+'?.textContent.includes('+JSON.stringify(serial)+')','device original');
        await evaluate(q('#page-dialog [data-close]')+'.click()');
      }
      await screenshot(call,t.state,width);
    }
    assert.ok(await evaluate('!document.querySelector("#reinspection-wait > details").open'));
    await evaluate(q('#reinspection-wait > details > summary')+'.click()');
    await wait(q('.wait-source .wait-open')+'?.offsetWidth>0','disclosed contractual sources');
    await evaluate(q('#reinspection-wait > details > summary')+'.click()');
  }
  for (const kind of ['edge','duration','source','serial','verdict']) {
    const state=await evaluate('(()=>{const g=structuredClone(state.bundle.report.graph),f=structuredClone(state.bundle.report.findings.find(f=>f.rule==="H02"));'+
      'const c=f.reinspection.timing, op=c.operation, row=g.reinspection_wait_sources.lines.find(r=>r.kind==="run_segment");'+
      ({edge:'g.edges=g.edges.filter(e=>e.type!=="reinspection_time_basis"||e.to!==row.id);',
        duration:'op.longest_seconds=12345;',source:'row.page_sha256+="x";',serial:'op.serial+="x";',
        verdict:'c.state=c.state==="run_device"?"run_record":"run_device";c.status="missing";op.intervals=[];op.gaps=[];op.longest_seconds=null;'})[kind]+
      'const result=ReinspectionTiming.panel(f,g);return [result.dataset.timingState,Boolean(result.querySelector(".run-track"))]})()');
    assert.deepEqual(state,['unverified',false]);
  }
  console.log('PASS · '+t.state+' R'+rev+' · six widths, original page hashes, keyboard and altered evidence');
}

export async function checkIntakeScopes({root,call,wait,evaluate}) {
  await call('Page.navigate',{url:root+'/#workflow'});
  await wait(q('#workflow a[href="/app?new=contract"]')+'?.offsetWidth>0','contract intake on product home');
  await evaluate(q('#workflow a[href="/app?new=contract"]')+'.click()');
  await wait(q('#upload-dialog')+'?.open && '+q('#intake-scopes input')+'?.offsetWidth>0','native scope group');
  assert.equal(await evaluate(q('#intake-scopes input:checked')+'.value'),'cn-contract-performance/v1');
  assert.ok(await evaluate('!location.search && !document.querySelector("#upload-files").files.length'));
  for (const width of widths) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:false});
    const radios=await evaluate('[...document.querySelectorAll("#intake-scopes input")].map(r=>r.value)');
    assert.equal(radios.length,4);
    await evaluate(q('#intake-scopes input')+'.click();'+q('#intake-scopes input')+'.focus()');
    for (let i=0;i<4;i++) {
      assert.equal(await evaluate(q('#upload-profile')+'.value'),radios[i]);
      assert.equal(await evaluate(q('#intake-scopes input:checked')+'.value'),radios[i]);
      if (i===1) {
        await screenshot(call,'intake-scope',width);
        await evaluate(q('.intake-requirements > summary')+'.click()');
        assert.ok(await evaluate(q('#profile-note')+'.offsetWidth>0 && '+q('#profile-note')+'.textContent.includes("质保期满确认单")'));
        await evaluate(q('.intake-requirements > summary')+'.click()');
        await evaluate(q('#intake-scopes input:checked')+'.focus()');
      }
      for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
    }
    assert.equal(await evaluate(q('#upload-profile')+'.value'),radios[0]);
    assert.ok(await evaluate('[...document.querySelectorAll(".intake-scope")].every(n=>n.offsetWidth>=44&&n.offsetHeight>=44) && document.querySelector("#upload-dialog").scrollWidth<=document.querySelector("#upload-dialog").clientWidth'));
  }
  await evaluate(q('#upload-dialog [data-close]')+'.click()');
  await call('Page.reload',{ignoreCache:true});
  await wait(q('#new-case')+'?.offsetWidth>0','normal desk entry');
  assert.ok(await evaluate('!document.querySelector("#upload-dialog").open'));
  await evaluate(q('#new-case')+'.click()');
  assert.equal(await evaluate(q('#intake-scopes input:checked')+'.value'),'cn-procurement-full-settlement/v1');
  console.log('PASS · 首页预选履约审计，普通新建、四类范围、键盘与触控');
}
