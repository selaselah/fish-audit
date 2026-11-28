import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

export async function checkMeasurementSpacing(ctx,cid) {
  const {root,call,evaluate,wait}=ctx, input=browserInput(ctx);
  const get=async path=>{
    const r=await fetch(root+path); assert.equal(r.status,200); return r.json();
  };
  const base='/api/cases/'+cid, task=await get(base);
  assert.match(task.title,/^合成演练 · (终验柜温读数|合同柜温上限|验收单所引上限|柜温数值完整)/u);
  const {report,rev}=await get(base+'/reports/'+(process.env.AUDIT_NUMBER_REV || task.rev));
  const current=report.policy.version.localeCompare('2026.11.28.15','en',{numeric:true})>=0;
  const expected=current && !task.title.includes('柜温数值完整');
  const rows=report.graph.measurement_number_sources?.rows || [];
  assert.equal(Boolean(rows.length),expected);
  const row=rows.find(r=>r.line && r.origin==='original');
  const accepted=report.findings.find(f=>f.rule==='H02'), paid=report.findings.find(f=>f.rule==='H05');
  const term=report.findings.find(f=>f.rule==='H04' && f.stage?.name===paid.stage.name);
  const q=s=>'document.querySelector('+JSON.stringify(s)+')';
  const click=s=>input.click(q(s));
  const selector=f=>'#number-'+f.id+'-'+row.doc+'-p'+row.page+'-l'+row.line;
  const visit=url=>call('Page.navigate',{url});
  async function open(f) {
    const view=f.rule==='H02'?'acceptance-checks':'payment-checks&stage='+f.id;
    await visit(root+'/workpaper/'+cid+'?rev='+rev+'&view='+view);
    await wait(q('#performance-index')+'?.open && '+q('.scope-check-select')+'?.value==='+JSON.stringify(f.id),'open '+f.id);
  }
  async function original() {
    await wait(q('#page-dialog')+'?.open && '+q('#page-content .located')+'?.dataset.sourceRef==='+JSON.stringify(row.id)+
      ' && '+q('#page-content img')+'?.naturalWidth>0','original number line');
    assert.equal(await evaluate(q('#page-content .located blockquote')+'.textContent'),row.quote);
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    const rects=report.calls.pages.find(p=>p.doc===row.doc && p.page===row.page).measurement_number_rects[row.line];
    const shown=await evaluate('[...document.querySelectorAll("#page-content .source-plane svg rect")].map(r=>["x","y","width","height"].map(k=>Number(r.getAttribute(k))))');
    assert.ok(rects.length);
    assert.deepEqual(shown,rects.map(([l,t,r,b])=>[l,t,r-l,b-t].map(n=>1000*n)));
  }
  async function compose(note,target) {
    await click('#walk-launch'); await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','ready to write');
    await evaluate(q('#walk-text')+'.value='+JSON.stringify(note)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
    if (target) {
      await click('#walk-pick'); await wait(q('#walk-launch')+'.dataset.picking==="true"','pick a paper control');
      await click(target); await wait(q(target)+'.classList.contains("walk-selected")','mark this control');
      await inspect(ctx,390,'#walk-dialog','measurement-spacing-feedback');
    }
  }
  for (const width of [320,390,768,820,1024,1440]) {
    await size(ctx,width);
    for (const f of [accepted,paid]) {
      await open(f);
      if (!expected) {
        assert.equal(await evaluate(q('#performance-index [data-number-finding]')+'===null'),true);
        continue;
      }
      const id=selector(f);
      await wait(q(id)+'?.getClientRects().length','numeric evidence');
      assert.equal(await evaluate(q(id+' strong')+'.textContent'),row.quote);
      if (row.facts.length===1) {
        const fact=report.graph.facts.find(f=>f.id===row.facts[0]);
        assert.ok((await evaluate(q(id+' .number-copy')+'.textContent')).endsWith(' · '+fact.value));
      }
      assert.ok(await evaluate(q(id)+'.getBoundingClientRect().height>=44'));
      await inspect(ctx,width,id,'measurement-spacing-'+f.rule);
      await click(id); await original();
      if (f===accepted) await inspect(ctx,width,'#page-content .located','measurement-spacing-original');
    }
  }
  if (expected) {
    const corrupted=await evaluate(`(()=>{
      return ['node','scope','evidence','edge','geometry'].map(fault=>{
        const p=structuredClone(state.bundle.report), f=p.findings.find(f=>f.rule==='H05');
        const r=p.graph.measurement_number_sources.rows.find(r=>r.line);
        if(fault==='node') p.graph.nodes.find(n=>n.id===r.id).label='缺少原行';
        if(fault==='scope') f.scope=f.scope.filter(u=>u!==r.unit);
        if(fault==='evidence') f.evidence=f.evidence.filter(ref=>ref!==r.id);
        if(fault==='edge') p.graph.edges=p.graph.edges.filter(e=>e.from!==r.id || e.to!=='finding/'+f.id);
        if(fault==='geometry') p.calls.pages.find(c=>c.doc===r.doc && c.page===r.page).measurement_number_rects[r.line]=[[0,.8,.5,.3]];
        return measurementNumberSources(p,f).some(s=>s.ref===r.id);
      });
    })()`);
    assert.deepEqual(corrupted,[false,false,false,false,false]);
    await open(term); await evaluate(q(selector(term))+'.focus()'); await input.key('Enter'); await original();
    const payNote='核对这笔验收款时，想同屏查看原始检测记录。';
    if (process.env.AUDIT_ISOLATED_NUMBER_ORIGIN) {
      assert.equal(root,process.env.AUDIT_ISOLATED_NUMBER_ORIGIN);
      assert.ok(!['8000','8010'].includes(new URL(root).port));
      async function save(note,target) {
        await compose(note,target);
        await click('#walk-save'); await wait('!'+q('#walk-dialog')+'.open','save');
        const saved=(await get('/api/walkthrough')).notes.find(n=>n.text===note);
        assert.equal(saved.context.rev,rev);return saved.context;
      }
      async function restore(note) {
        await visit(root+'/app#desk');await wait(q('#desk')+'?.getClientRects().length','return to desk');
        await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','open notes');
        await click('#walk-saved');
        const a='[...document.querySelectorAll("#walk-history li")].find(li=>li.querySelector("p")?.textContent==='+JSON.stringify(note)+')?.querySelector("a")';
        await wait(a+'?.getClientRects().length','reload the note');
        const url=await evaluate(a+'.href');assert.ok(url.includes(cid) && url.includes('rev='+rev));
        await evaluate('Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:async t=>{window.exported=t}});true');
        await click('#walk-copy');await wait('window.exported?.includes('+JSON.stringify(url)+')','copied fixed address');
        await input.click(a);
      }
      const onPage='请在检测数值旁保留原件中的间距。';
      const raw=await save(onPage);
      assert.equal(raw.raw_ref,row.id);await restore(onPage);await original();
      await size(ctx,390);await open(paid);
      const pinned=await save(payNote,selector(paid));
      assert.equal(pinned.anchor,selector(paid).slice(1));
      assert.deepEqual(pinned.params,{view:'payment-checks',stage:paid.id});
      await restore(payNote);
      await wait(q('#performance-index')+'?.open && '+q(selector(paid))+'?.classList.contains("walk-mark")','restore the selected payment');
      const stale=await fetch(root+'/api/walkthrough',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({id:'d'.repeat(32),text:'旧版定位演练',context:{...raw,rev:rev-1}})});
      assert.equal(stale.status,404);
    } else if (process.env.AUDIT_UI_SHOTS) {
      const before=await get('/api/walkthrough');
      await size(ctx,390);await open(paid);await compose(payNote,selector(paid));
      assert.deepEqual(await get('/api/walkthrough'),before);
    }
  }
  const after=await get(base);
  assert.deepEqual([after.rev,after.status,after.decisions],[task.rev,task.status,task.decisions]);
  console.log('PASS measurement spacing, R'+rev+', '+(expected?'filed lines and installment':'comparison control')+', six widths');
}
