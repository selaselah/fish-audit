import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

export async function checkPaymentQuality(ctx,cid) {
  const {root,call,evaluate,wait}=ctx, isolated=process.env.AUDIT_ISOLATED_QUALITY_ORIGIN;
  const json=async path=>{const r=await fetch(root+path);assert.equal(r.status,200);return r.json();};
  const base='/api/cases/'+cid, task=await json(base);assert.match(task.title,/^合成演练 · /u);
  const {report,rev}=await json(base+'/reports/'+(process.env.AUDIT_QUALITY_REV || task.rev));
  const findings=report.findings.filter(f=>['H04','H05'].includes(f.rule)), quality=findings.filter(f=>f.payment_quality);
  const h02=report.findings.find(f=>f.rule==='H02' && f.quality_comparison);
  const current=quality.find(f=>f.rule==='H05') || quality[0], fixed=root+'/workpaper/'+cid+'?rev='+rev;
  const q=s=>'document.querySelector('+JSON.stringify(s)+')', visible=s=>q(s)+'?.getClientRects().length';
  const click=s=>evaluate(q(s)+'.click()'), go=url=>call('Page.navigate',{url});
  async function open(id) {
    await go(fixed+'&view=payment-checks&stage='+id);
    await wait(q('#performance-index')+'?.open && '+q('.scope-check-select')+'?.value==='+JSON.stringify(id),'specific issued installment '+id);
  }
  async function original(id,key) {
    const f=report.findings.find(x=>x.id===id),data=f.quality_comparison || f.payment_quality;
    const ref=data.fields[key],fact=report.graph.facts.find(x=>x.id===ref),limits=f.rule==='H02';
    const button=(limits?'#limits-':'#quality-')+id+'-'+key;
    assert.equal(await evaluate(q(button)+'.dataset.source'),ref);
    await click(button);
    await wait(q('#page-dialog')+'?.open && '+q('#page-content .located')+'?.dataset.fact==='+JSON.stringify(ref)+' && '+q('#page-content img')+'?.naturalWidth>0','source for '+key);
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    assert.equal(await evaluate(q('#page-content .page-view')+'.dataset.doc'),fact.doc);
    assert.equal(await evaluate(q('#page-content .located')+'.dataset.fact'),fact.id);
    await evaluate(q('#page-dialog')+'.close()');
    assert.ok(await evaluate(limits?visible(button):q('#performance-index')+'.open'));
  }
  // The real report and its installment picker expose the same control, including unknown-designation receipts.
  await open((current || findings.at(-1)).id);
  for (const f of findings) {
    if (!await evaluate('[...'+q('.scope-check-select')+'.options].some(o=>o.value==='+JSON.stringify(f.id)+')')) {
      await click('#performance-index .scope-filters button:last-child');
    }
    await evaluate('(()=>{const s='+q('.scope-check-select')+';s.value='+JSON.stringify(f.id)+';s.dispatchEvent(new Event("change"));})()');
    const card='#quality-'+f.id, data=f.payment_quality;
    assert.equal(await evaluate(q('[data-quality-finding]')+'?.id || null'),data?card.slice(1):null,f.id);
    if (!data) continue;
    assert.equal(await evaluate(q(card)+'?.dataset.rev'),String(rev));
    const observed=data.comparison?.observed || {value:data.measure.observed,unit:data.measure.unit};
    assert.equal(await evaluate(q(card+' .measured strong')+'.textContent'),observed.value+' '+observed.unit);
    if (data.comparison) {
      for (const [role,key] of [['contract','acceptance_criteria'],['inspection','inspection_basis']]) {
        const result=data.comparison.limits[role].result;
        assert.ok(await evaluate(visible(card+'-'+key+' .quality-evaluation.'+result)));
      }
      await original(f.id,'inspection_basis');
    }
    if (data.payment) {
      const days=data.payment.days;
      assert.equal(await evaluate(q(card+' .quality-order')+'.textContent'),days?'回单'+(days<0?'早 ':'晚 ')+Math.abs(days)+' 天':'同日，先后待核');
      await original(f.id,'paid_on');
    }
  }
  if (h02) {
    const card='#limits-'+h02.id, selector='[data-finding="'+h02.id+'"] .finding-disclosure > summary';
    await go(fixed);await wait(visible(selector),'acceptance in the ordinary findings ledger');
    await click(selector);await wait(visible(card),'limits on the ordinary acceptance finding');
    const picked=await evaluate('import("/assets/walkthrough-context.js").then(m=>m.captureContext(null,'+q(card+'-inspection_basis')+'))');
    assert.deepEqual(picked.params,{view:'acceptance-limits'});assert.equal(picked.anchor,card.slice(1)+'-inspection_basis');
    await go(fixed+'&view=acceptance-limits');
    await wait(visible(card),'issued acceptance limits');
    for (const key of ['measured_result','acceptance_criteria','inspection_basis','acceptance_result']) await original(h02.id,key);
    for (const width of [320,390,768,820,1024,1440]) {
      await size(ctx,width);
      assert.ok(await evaluate('[...'+q(card)+'.querySelectorAll("button")].every(b=>{const r=b.getBoundingClientRect();return r.width>=44 && r.height>=44 && r.left>=-1 && r.right<=innerWidth+1})'),'acceptance controls at '+width);
      await inspect(ctx,width,card,'limits-'+cid.slice(0,8));
    }
  } else {
    await go(fixed+'&view=acceptance-limits');
    await wait(q('#case-panel')+'?.textContent.includes("本版未出具合同与验收单的双限值对照")','no dual comparison on this edition');
    assert.equal(await evaluate(q('[data-limit-finding]')+'===null'),true);
  }
  if (!current) {console.log('PASS · R'+rev+' · scoped findings retain their ordinary sources');return;}
  const id=current.id, card='#quality-'+id, data=current.payment_quality;
  await go(fixed);
  const summary='[data-finding="'+id+'"] .finding-disclosure > summary';
  await wait(q(summary)+'?.textContent','installment in the ordinary findings ledger');
  await click(summary);
  const jump='[data-finding="'+id+'"] a[href*="view=payment-checks"][href*="stage='+id+'"]';
  await wait(q(jump)+'?.href','quality comparison on the ordinary finding');
  await click(jump);await wait(visible(card)+' && '+q('#performance-index')+'.open','ordinary finding to comparison');
  for (const key of ['acceptance_criteria','measured_result',...(data.accepted_on?['accepted_on']:[])]) await original(id,key);
  const folded=data.payment?'transfer_status':'acceptance_scope';
  await click(card+' summary');
  const basis=report.graph.facts.find(f=>f.id===data.fields.inspection_basis).source_line.text;
  if (!data.comparison) assert.equal(await evaluate(q(card+'-inspection_basis strong')+'.textContent'),basis.slice(basis.search(/[:：]/u)+1));
  await original(id,folded);await click(card+' summary');
  for (const width of [320,390,768,820,1024,1440]) {
    await size(ctx,width);
    assert.ok(await evaluate('[...'+q(card)+'.querySelectorAll("summary,button")].filter(n=>n.getClientRects().length).every(n=>{const r=n.getBoundingClientRect();return r.width>=44 && r.height>=44 && r.left>=-1 && r.right<=innerWidth+1})'),'controls at '+width);
    await inspect(ctx,width,card,'quality-'+cid.slice(0,8));
  }
  const corrupted=await evaluate('(()=>{const checks=[];for(const fault of ["edge","line","amount","method","date"]){const p=structuredClone(state.bundle.report);const i=p.findings.find(f=>f.id==='+JSON.stringify(id)+');const v=i.payment_quality;if(fault==="edge")p.graph.edges=p.graph.edges.filter(e=>e.type!=="acceptance_reading_for_payment");if(fault==="line")p.graph.payment_quality_sources.rows.find(r=>r.facts.includes(v.fields.measured_result)).line++;if(fault==="amount"){if(v.comparison)v.comparison.observed.value="1";else v.measure.observed="1"}if(fault==="method")delete p.policy.code_sha256["payment_quality.py"];if(fault==="date")v.accepted_on="1900-02-01";checks.push(PaymentQuality.bind(i,p)===null)}return checks})()');
  assert.deepEqual(corrupted,[true,true,true,true,true]);
  if (h02) {
    for (const fault of ['stage-inspection','h02-contract','h02-edge','h02-field']) {
      assert.equal(await evaluate('(()=>{const p=structuredClone(state.bundle.report),h=p.findings.find(f=>f.quality_comparison),i=p.findings.find(f=>f.id==='+JSON.stringify(id)+');'+
        ({'stage-inspection':'i.payment_quality.comparison.limits.inspection.result="altered";','h02-contract':'h.quality_comparison.limits.contract.limit="999";',
          'h02-edge':'p.graph.edges=p.graph.edges.filter(e=>e.type!=="measured_against_inspection_limits");',
          'h02-field':'h.quality_comparison.fields.inspection_basis=h.quality_comparison.fields.acceptance_criteria;'}[fault])+
        'return PaymentQuality.bind(i,p)===null})()'),true,fault);
    }
  }
  if (isolated) {
    assert.equal(root,isolated);assert.ok(!['8000','8010'].includes(new URL(root).port));
    assert.deepEqual((await json('/api/walkthrough')).notes,[]);
    // Pick a recorded field while the payment modal is open. Its own stage can differ from the route's initial selection.
    const last=quality.at(-1), fid=last.id, target='#quality-'+fid+'-measured_result';
    await open(id);await size(ctx,390);
    if (id!==fid) await evaluate('(()=>{const s='+q('.scope-check-select')+';s.value='+JSON.stringify(fid)+';s.dispatchEvent(new Event("change"));})()');
    await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','start a note');
    const general='希望这笔付款的审批记录也能在此核对。';
    await evaluate(q('#walk-text')+'.value='+JSON.stringify(general)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
    await click('#walk-save');await wait('!'+q('#walk-dialog')+'.open','save a note without selecting a control');
    const [ordinary]=(await json('/api/walkthrough')).notes;
    assert.deepEqual(ordinary.context.params,{view:'payment-checks',stage:fid});
    assert.equal(ordinary.context.anchor,'quality-'+fid);assert.equal(ordinary.text,general);
    await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','start a field note');
    const opinion='希望在终验实测旁也显示检验依据。';
    await evaluate(q('#walk-text')+'.value='+JSON.stringify(opinion)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
    await click('#walk-pick');await browserInput(ctx).tap(q(target));
    await wait(q('#walk-dialog')+'.open && '+q(target)+'.classList.contains("walk-selected")','pin the measured result');
    await inspect(ctx,390,'#walk-dialog','quality-feedback');
    await click('#walk-save');await wait('!'+q('#walk-dialog')+'.open','save the walkthrough note');
    const [note]= (await json('/api/walkthrough')).notes;
    assert.deepEqual(note.context.params,{view:'payment-checks',stage:fid});
    assert.equal(note.context.anchor,target.slice(1));assert.match(note.context.target,/终验实测.*第 1 页.*行/u);
    assert.equal(note.context.case_id,cid);assert.equal(note.context.rev,rev);
    const stage=quality.find(f=>f.rule==='H04').id;
    for (const [context,status] of [[{...note.context,rev:rev-1},404],
      [{...note.context,anchor:'quality-'+stage+'-paid_on',params:{view:'payment-checks',stage}},404],
      [{...note.context,params:{view:'payment-checks',stage}},400]]) {
      const res=await fetch(root+'/api/walkthrough',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({id:'e'.repeat(32),text:opinion,context})});
      assert.equal(res.status,status);
    }
    assert.equal((await json('/api/walkthrough')).notes.length,2);
    await go(root+'/app#desk');
    await wait(visible('#desk')+' && '+visible('body > #walk-launch'),'desk recorder after removing the open workpaper dialog');
    await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-saved')+'.disabled','notebook');
    await click('#walk-saved');await wait(visible('#walk-history li a'),'saved version and original');
    await evaluate('Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:async text=>{window.qualityHandoff=text}});true');
    await browserInput(ctx).tap(q('#walk-copy'));await wait('typeof window.qualityHandoff==="string"','copy to Codex');
    const dest=await evaluate(q('#walk-history li a')+'.href'), handoff=await evaluate('window.qualityHandoff');
    assert.ok(handoff.includes(dest) && handoff.includes(opinion) && handoff.includes(general) && handoff.includes(note.context.target));
    await click('#walk-history li a');
    await wait(q(target)+'?.classList.contains("walk-mark") && '+visible(target),'return to same case, revision and receipt');
    await original(fid,'measured_result');
    // A field nested in a collapsed disclosure is restored even if the issued paper takes over six seconds to load.
    const deferred='#quality-'+fid+'-'+folded;
    await click('#quality-'+fid+' summary');
    const back=await evaluate('import("/assets/walkthrough-context.js").then(m=>m.returnUrl(m.captureContext('+q('#performance-index')+','+q(deferred)+')))');
    const delay=await call('Page.addScriptToEvaluateOnNewDocument',{source:'const normal=window.fetch;window.fetch=async(...args)=>{const r=await normal(...args);if(String(args[0]).includes("/reports/'+rev+'"))await new Promise(done=>setTimeout(done,6500));return r;};'});
    await go(root+back);
    await wait(q(deferred)+'?.classList.contains("walk-mark") && '+visible(deferred),'late report expands and pins the same source field',30000);
    await call('Page.removeScriptToEvaluateOnNewDocument',{identifier:delay.identifier});
    await original(fid,folded);
    if (h02) {
      await go(fixed+'&view=acceptance-limits');
      const button='#limits-'+h02.id+'-inspection_basis';
      await wait(visible(button),'acceptance control');
      await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','record a note on the acceptance finding');
      await evaluate(q('#walk-text')+'.value="想在这项验收核对上加一个补件入口。";'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
      await click('#walk-save');await wait('!'+q('#walk-dialog')+'.open','store a note on the visible acceptance comparison');
      const [generalLimit]=(await json('/api/walkthrough')).notes;
      assert.equal(generalLimit.context.anchor,'limits-'+h02.id);
      assert.deepEqual(generalLimit.context.params,{view:'acceptance-limits'});
      await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','record a note on an individual limit');
      const opinion='请核对这份验收单采用的限值。';
      await evaluate(q('#walk-text')+'.value='+JSON.stringify(opinion)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
      await click('#walk-pick');await browserInput(ctx).tap(q(button));
      await wait(q('#walk-dialog')+'.open && '+q(button)+'.classList.contains("walk-selected")','selected inspection limit');
      await inspect(ctx,390,'#walk-dialog','limits-feedback');
      await click('#walk-save');await wait('!'+q('#walk-dialog')+'.open','store a limit-specific walkthrough opinion');
      const [entry]=(await json('/api/walkthrough')).notes;
      assert.deepEqual(entry.context.params,{view:'acceptance-limits'});assert.equal(entry.context.anchor,button.slice(1));
      assert.match(entry.context.target,/检验依据.*第 1 页.*行/u);assert.equal(entry.context.rev,rev);
      for (const [context,status] of [[{...entry.context,rev:rev-1},404],[{...entry.context,params:{finding:h02.id}},400]]) {
        const res=await fetch(root+'/api/walkthrough',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({id:'c'.repeat(32),text:opinion,context})});assert.equal(res.status,status);
      }
      await go(root+'/app#desk');await wait(visible('#desk'),'desk before opening the limits note');
      await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-saved')+'.disabled','notebook');
      await click('#walk-saved');await wait(visible('#walk-history li a'),'recorded limit note');
      await click('#walk-history li a');await wait(q(button)+'?.classList.contains("walk-mark") && '+visible(button),'return to the recorded inspection limit');
      await original(h02.id,'inspection_basis');
    }
    const end=await json(base);assert.deepEqual([end.status,end.rev,end.decisions],[task.status,task.rev,task.decisions]);
  }
  console.log('PASS · R'+rev+' · '+quality.length+' installment and receipt comparisons, original lines, six widths'+(isolated?', note and Codex handoff':''));
}
