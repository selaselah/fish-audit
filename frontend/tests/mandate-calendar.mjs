import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {browserInput,inspect,size} from './review-screen.mjs';

async function checkPaymentDates(ctx,report,url) {
  const {call,evaluate,wait}=ctx, q=s=>'document.querySelector('+JSON.stringify(s)+')';
  const effect=report.findings.find(f=>f.rule==='H01'), [entry]=effect.delegations;
  const order=entry.issuance_order;
  for (const payment of report.findings.filter(f=>['H04','H05'].includes(f.rule))) {
    await call('Page.navigate',{url:url+'&view=payment-checks&stage='+payment.id});
    const pane='#performance-index[open]', card=pane+' [data-mandate-payment="'+payment.id+'"]';
    await wait(q(pane+' .scope-check[aria-pressed=true]')+'?.dataset.check==='+JSON.stringify(payment.id),'selected installment');
    const available=payment.stage && ['same_day','before'].includes(order?.state) &&
      [...order.issued_refs,...order.signed_refs].every(ref=>payment.evidence.includes(ref));
    if (!available) {assert.equal(await evaluate(q(card)+'===null'),true);continue;}
    await wait(q(card)+'?.getClientRects().length','two issued dates on the payment');
    const sources=await evaluate('[...'+q(card)+'.querySelectorAll("[data-mandate-date]")].map(b=>b.dataset.fact)');
    assert.deepEqual(sources,[...order.signed_refs,...order.issued_refs]);
    const gap=Math.round((Date.parse(entry.issued_on)-Date.parse(entry.signed_on))/86400000);
    assert.equal(await evaluate(q(card+' .mandate-payment-head span')+'.textContent'),gap?'签约早于出具 '+gap+' 天':'同日 · 时分待核');
    if (payment.rule==='H04' && payment.stage.name!=='第一期') continue;
    for (const width of [1440,1024,768,390,360,320]) {
      await size(ctx,width);
      assert.ok(await evaluate(q(card)+'.scrollWidth<='+q(card)+'.clientWidth+1'),'authority dates fit at '+width);
      if (payment.rule==='H05') await inspect(ctx,width,card,'mandate-payment-'+order.state);
      if (![390,1440].includes(width)) continue;
      for (const ref of sources) {
        const button=q(card+' [data-fact="'+ref+'"]');
        await evaluate(button+'.focus();'+button+'.click()');
        await wait(q('#page-dialog')+'.open && '+q('#page-content .located')+'?.dataset.fact==='+JSON.stringify(ref),'correct physical date row');
        await wait(q('.source-plane svg rect')+'!=null','marked original');
        await evaluate(q('#page-dialog [data-close]')+'.click()');
        await wait('document.activeElement==='+button,'focus on the payment date source');
      }
    }
    for (const change of ["f.evidence=f.evidence.filter(id=>id!==ref)","r.graph.edges=r.graph.edges.filter(e=>!(e.from===ref && e.to==='finding/'+f.id))",
      "r.graph.facts.find(x=>x.id===ref).source_line.rects=[]","r.graph.edges=r.graph.edges.filter(e=>!(e.type==='records' && e.to===ref))",
      "r.calls.pages.find(p=>p.doc===ref.split('/')[0]).check=null",
      "const p=r.calls.pages.find(p=>p.doc===ref.split('/')[0]);p.check.response_id=p.response_id",
      "r.calls.pages.push(r.calls.pages.find(p=>p.doc===ref.split('/')[0]))",
      "r.calls.expert.input.procedures.find(p=>p.rule==='H01').delegations=[]"]) {
      assert.equal(await evaluate('(()=>{const r=structuredClone(state.bundle.report),f=r.findings.find(x=>x.id==='+JSON.stringify(payment.id)+'),ref='+JSON.stringify(sources[1])+';'+change+';return Boolean(MandateCalendar.paymentPanel(f,r,state.bundle.rev))})()'),false);
    }
    if (payment.rule==='H05') {
      const field=q(card+' [data-mandate-date=granted_on]'), {click}=browserInput(ctx);
      await click(q('#walk-launch'));
      await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'?.disabled','recorder on this payment');
      await click(q('#walk-pick'));
      await click(field);
      assert.equal(await evaluate(q('#walk-location')+'.textContent'),await evaluate(field+'.dataset.originalLabel'));
      const link=await evaluate(`(async()=>{
        const {captureContext,returnUrl}=await import('/assets/walkthrough-context.js');
        return returnUrl(captureContext(document.getElementById('performance-index'),${field}),null);
      })()`);
      await call('Page.navigate',{url:new URL(link,ctx.root).href});
      await wait(field+'?.classList.contains("walk-mark")','return to the selected source within the saved edition and installment');
    }
  }
}

export async function checkMandateCalendar({root,call,evaluate,wait},cid,revision) {
  const api=root+'/api/cases/'+cid, task=await (await fetch(api)).json();
  assert.ok(task.title.startsWith('合成演练 · '));
  const rev=Number(revision || task.rev), {report}=await (await fetch(api+'/reports/'+rev)).json();
  const finding=report.findings.find(f=>f.rule==='H01'), [entry]=finding.delegations;
  const expected=new Map([
    ['代理人在授权最后一天签约','签约在授权截止日'],['代理人在授权开始前一天签约','签约早于起始日 1 天'],
    ['签约次日才出具委托书','签约早于出具 1 天'],['出具委托书与代理签约同日',entry.issuance_order?'出具与签约同日 · 时分待核':'出具与签约同日'],
    ['签约时书面授权已到期','签约超过截止日 1 天'],['委托书截止日期的日数断字','授权截止日待核'],
    ['委托代理人在授权期内签约','签约日在所列期间'],['受托人仅获授权收货验收','所列期间内 · 签约权限有风险'],
    ['委托书限制预付款并要求书面批准','所列期间内 · 签约权限有风险'],['扫描委托书的签约附加条件','委托书影像待核']
  ]);
  const title=task.title.replace('合成演练 · ','');
  assert.ok(expected.has(title),title);
  const selector='.performance-overview .mandate-calendar[data-side="'+entry.side+'"]';
  const node=s=>'document.querySelector('+JSON.stringify(s)+')';
  const panel=node(selector), part=s=>node(selector+' '+s);
  const url=root+'/workpaper/'+cid+'?rev='+rev;
  if (title==='签约次日才出具委托书' && rev===task.rev) {
    await call('Page.navigate',{url:root+'/app'});
    await wait(node('#case-search')+'?.getClientRects().length','work queue search');
    await evaluate(node('#case-search')+'.value='+JSON.stringify(title)+';'+node('#case-search')+'.dispatchEvent(new Event("input",{bubbles:true}))');
    const card=node('.audit-card a[href="'+new URL(url).pathname+'?rev='+rev+'"]');
    await wait(card+'?.getClientRects().length','dated review card in the audit queue');
    await evaluate(card+'.click()');
  } else await call('Page.navigate',{url});
  await wait(panel,'mandate at the workpaper overview');
  assert.equal(await evaluate(part('.mandate-date-caption')+'.textContent'),expected.get(title));
  if (!await evaluate(panel+'.open')) await evaluate(part('summary')+'.click()');
  await wait(part('.mandate-month')+'?.dataset.month','calendar month');
  const graph=report.graph, fields=['signed_on','granted_on','grant_from','grant_until'];
  const contract=graph.documents_by_kind.contract[0];
  const facts=fields.map((field,i)=>graph.facts.find(f=>(f.unit || f.doc)===(i?entry.units[0]:contract) && f.field===field && entry.evidence.includes(f.id)));
  assert.ok(facts.every(Boolean));
  const prop=['signed_on','issued_on','valid_from','valid_until'];
  const scan=title.startsWith('扫描委托书');
  const days=prop.map((key,i)=>!facts[i].source_line || title.includes('断字') && i===3?null:entry[key]);
  const selected=part('.mandate-date-choice[aria-pressed=true]'), right=part('.mandate-source-button');
  const choose=async i=>evaluate(part('[data-field="'+fields[i]+'"]')+'.click()');
  for (const [i,f] of facts.entries()) {
    await choose(i);
    assert.equal(await evaluate(selected+'.textContent.endsWith('+JSON.stringify(days[i] || (f.source_line?'日期待核':'核对原图'))+')'),true);
    if (days[i]) {
      assert.equal(await evaluate(part('button.mandate-day[aria-pressed=true]')+'.dataset.date'),days[i]);
      assert.equal(await evaluate(part('.mandate-month')+'.dataset.month'),days[i].slice(0,7));
    } else assert.equal(await evaluate(part('button.mandate-day[aria-pressed=true]')),null);
    await wait(right+'?.dataset.fact==='+JSON.stringify(f.id),'corresponding date source');
    assert.equal(await evaluate(right+'.querySelector("q").textContent'),f.source_line?.text || f.quote);
    await evaluate(right+'.click()');
    await wait(node('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(f.id),'source fact is located');
    await wait(node('#page-dialog .page-image')+'?.naturalWidth>0','immutable original page');
    const source=new URL(await evaluate(node('#page-dialog .source-tools a')+'.href'));
    assert.ok(source.pathname.endsWith('/documents/'+f.doc+'/pages/'+f.page));assert.equal(source.searchParams.get('rev'),String(rev));
    if (!f.source_line) assert.equal(await evaluate(node('#page-dialog .image-sheet svg rect')),null);
    await evaluate(node('#page-dialog [data-close]')+'.click()');
  }
  await evaluate(selected+'.focus()');
  for (const [key,field] of [['Home','signed_on'],['ArrowDown','granted_on'],['End','grant_until'],['ArrowRight','signed_on']]) {
    await call('Input.dispatchKeyEvent',{type:'keyDown',key,code:key});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key,code:key});
    assert.equal(await evaluate('document.activeElement.dataset.field'),field);
    assert.equal(await evaluate(selected+'.dataset.field'),field);
  }
  if (entry.issued_on===entry.signed_on) {
    assert.equal(await evaluate(part('[data-date="'+entry.signed_on+'"]')+'.getAttribute("aria-label")'),Number(entry.signed_on.slice(8))+' 日，'+entry.signed_on+'，合同签约、委托书出具');
    const count=await evaluate(panel+'.querySelectorAll('+JSON.stringify('button[data-date="'+entry.signed_on+'"]')+').length');
    assert.equal(count,1);
  }
  const months=days.filter(Boolean).map(s=>s.slice(0,7)).sort();
  const next=part('[aria-label=下个月]'), previous=part('[aria-label=上个月]');
  if (months[0]!==months.at(-1)) {
    await choose(days.findIndex(d=>d?.startsWith(months[0])));
    assert.equal(await evaluate(previous+'.disabled'),true);
    await evaluate(next+'.click()');
    assert.ok(await evaluate(part('.mandate-month')+'.dataset.month')>months[0]);
    await choose(days.findIndex(d=>d?.startsWith(months.at(-1))));
    assert.equal(await evaluate(next+'.disabled'),true);
  }
  await choose(0);
  if (title==='签约时书面授权已到期') {
    const previousEnd=part('button[data-date="'+entry.valid_until+'"]');
    assert.equal(await evaluate(previousEnd+'.textContent'),'8/31');
  }
  const selectedDate=part('button[data-date="'+days[0]+'"]');
  await evaluate(selectedDate+'.click()');
  assert.equal(await evaluate('document.activeElement.dataset.date'),days[0]);
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:950,deviceScaleFactor:1,mobile:width<600});
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && ['+panel+','+part('.mandate-days')+','+part('.mandate-reading')+'].every(e=>e.scrollWidth<=e.clientWidth+1)'),'layout at '+width);
    const shown=await evaluate('[...'+panel+'.querySelectorAll(".mandate-day.in-range")].map(e=>e.dataset.date)');
    if (days[2] && days[3]) {
      assert.equal(shown.length,await evaluate('[...'+panel+'.querySelectorAll("[data-date]")].filter(e=>e.dataset.date>='+JSON.stringify(days[2])+' && e.dataset.date<='+JSON.stringify(days[3])+').length'));
    } else assert.equal(shown.length,0);
    if (process.env.AUDIT_UI_SHOTS && [390,1440].includes(width)) {
      await wait(right+'?.querySelector("canvas")','original date excerpt');
      await evaluate('document.activeElement.blur();'+panel+'.scrollIntoView({block:"center"});document.fonts.ready.then(()=>true)');
      const clip=await evaluate('(()=>{const b='+panel+'.getBoundingClientRect();return {x:b.x+scrollX,y:b.y+scrollY,width:b.width,height:b.height,scale:1}})()');
      const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'mandate-calendar-'+cid+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
    }
  }
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  const keys=await evaluate('[...'+panel+'.querySelectorAll("[data-pair]")].map(b=>b.dataset.pair)');
  if (scan) assert.deepEqual(keys,[]);
  else {
    assert.ok(keys.includes('mandate-'+entry.side+'-signer'));
    if (days[0]===days[1]) assert.ok(keys.includes('mandate-'+entry.side+'-granted_on'));
  }
  for (const key of keys) {
    const pair=part('[data-pair="'+key+'"]');
    await evaluate(pair+'.click()');
    await wait('document.querySelectorAll(".compare-leaf canvas").length===2','both original lines of each comparison');
    const ids=await evaluate('[...document.querySelectorAll(".compare-leaf")].map(e=>e.dataset.fact)');
    const field=key.slice(('mandate-'+entry.side+'-').length);
    const limit=entry.limits?.find(l=>l.field_ref===ids[0] && l.comparison_ref===ids[1]);
    if (limit) assert.equal(limit.status,'risk');
    else assert.deepEqual(ids.map(id=>graph.facts.find(f=>f.id===id).field),field==='signer'?[entry.signature_field,'grant_agent']:['signed_on',field]);
    await evaluate(node('#tabs [data-tab=report]')+'.click()');
    await wait(right+'?.dataset.fact==='+JSON.stringify(facts[0].id),'return to expanded calendar and selected source');
  }
  if (title==='受托人仅获授权收货验收') {
    await evaluate(part('[data-scope-ref]')+'.click()');
    await wait(node('#page-dialog .located')+'?.textContent.includes("仅限收货验收")','limited authority on the mandate');
    await evaluate(node('#page-dialog [data-close]')+'.click()');
  }
  const check=await evaluate(`(() => {
    const {graph,findings}=state.bundle.report, finding=findings.find(f=>f.rule==='H01'), entry=finding.delegations[0];
    const src=MandateCalendar.evidence(finding,entry,graph), date=src.rows[1].fact;
    const edge=e=>e.type==='supports_result' && e.to==='finding/'+finding.id;
    const cut={...graph,edges:graph.edges.filter(e=>!(edge(e) && e.from===date.id))};
    const shuffled={...entry,units:graph.documents_by_kind.contract};
    const order=entry.issuance_order || {};
    const broken={...entry,issuance_order:{state:order.state,issued_refs:order.signed_refs,signed_refs:order.issued_refs}};
    const copy={...graph,facts:graph.facts.map(f=>f.id===date.id?{...f,source_line:null}:f)};
    const masked={...graph,facts:graph.facts.map(f=>f.field==='contract_id' && f.source_line
      ? {...f,value:'尾号001',quote:'合同编号：尾号001',source_line:{...f.source_line,text:'合同编号：尾号001'}}:f)};
    return {withdrawn:MandateCalendar.evidence(finding,entry,cut).rows[1].fact,
      wrong:MandateCalendar.evidence(finding,shuffled,graph).bound,
      imageOnly:MandateCalendar.evidence(finding,entry,copy).rows[1].day,masked:MandateCalendar.evidence(finding,entry,masked).bound,
      invalidOrder:MandateCalendar.evidence(finding,broken,graph).bound};
  })()`);
  assert.equal(check.withdrawn,null);assert.equal(check.imageOnly,null);assert.equal(check.wrong,false);assert.equal(check.masked,false);
  if (entry.issuance_order) assert.equal(check.invalidOrder,false);
  if (entry.issuance_order?.state==='same_day') {
    await call('Network.enable'); await call('Network.setBlockedURLs',{urls:['*'+cid+'/documents/*/pages/*']});
    await call('Page.reload',{ignoreCache:true});
    await wait(part('.mandate-ink[data-preview=text] q:not(.visually-hidden)'),'archived date when the image is unavailable');
    assert.equal(await evaluate(right+'.querySelector("q").textContent'),facts[0].source_line.text);
    assert.equal(await evaluate(right+'.querySelector("canvas")'),null);
    await call('Network.setBlockedURLs',{urls:[]});await choose(0);
    await wait(part('.mandate-ink[data-preview=image] canvas'),'original date excerpt recovered');
  }
  console.log('PASS · R'+rev+' · '+expected.get(title)+' · calendar, four cited rows, keyboard, original comparison and six widths');
  if (['签约次日才出具委托书','出具委托书与代理签约同日'].includes(title)) {
    await checkPaymentDates({root,call,evaluate,wait},report,url);
    console.log('PASS · 第一期、第二期、第三期及回单逐项核对授权日期证据');
  }
}
