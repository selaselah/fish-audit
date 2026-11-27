import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {inspect,size} from './review-screen.mjs';

async function checkCertificate(ctx,report,rev,phase,bank) {
  const {root,call,evaluate,wait}=ctx, graph=report.graph, cert=phase.warranty_check.certificate;
  const records=[...graph.warranty_pdf_sources.records,...graph.warranty_original_sources.records].filter(r=>cert.records.includes(r.id));
  assert.equal(records.length,1);
  const [record]=records, source=graph.documents.find(d=>d.id===record.doc);
  const url=root+'/workpaper/'+report.case_id+'?rev='+rev+'&view=warranty-certificate&stage=';
  const card='[data-certificate="'+record.id+'"]', query=s=>'document.querySelector('+JSON.stringify(s)+')';
  const click=s=>evaluate(query(s)+'.click()'), visible=s=>query(s)+'?.getClientRects().length';
  const original=card+' .warranty-file', note=graph.warranty_original_sources.documents.find(d=>d.doc===record.doc)?.notes[0];
  for (const f of [phase,bank].filter(Boolean)) {
    await call('Page.navigate',{url:url+f.id});
    await wait(visible(card),'signed warranty certificate from '+f.id);
    assert.equal(await evaluate(query(card)+'.dataset.state'),record.state);
    assert.equal(await evaluate(query(card)+'.closest("[data-phase-finding]").dataset.phaseFinding'),phase.id);
  }
  const row='[data-phase-finding="'+phase.id+'"] .warranty-event[data-event=confirmation]';
  assert.equal(await evaluate(query(row)+'.querySelector("time")?.dateTime || null'),phase.warranty_check.stated_on);
  assert.equal(phase.warranty_check.confirmed_on,null);
  assert.equal(await evaluate(query(card+' a[download]')+'.download'),source.name);
  assert.equal(await evaluate('fetch('+query(card+' a[download]')+'.href).then(r=>r.arrayBuffer()).then(b=>crypto.subtle.digest("SHA-256",b)).then(b=>Array.from(new Uint8Array(b),n=>n.toString(16).padStart(2,"0")).join(""))'),source.sha256);
  await click(card+' .agreement-check button');
  await wait(query(card+' .agreement-check')+'?.dataset.state==="match"','file hash');
  if (record.signatures?.length) assert.equal(await evaluate(query(card+' .pdf-timeline')+'.dataset.state'),record.state);
  if (note) assert.equal(await evaluate(query(card+' blockquote')+'.textContent'),note.text);
  await click(note?.location?card+' .warranty-original-note button':original);
  await wait(query('#page-dialog')+'.open && '+query('#page-dialog img')+'?.naturalWidth>0','physical page');
  assert.equal(await evaluate(query('#page-content .page-view')+'.dataset.doc'),record.doc);
  if (note?.location) assert.equal(await evaluate(query('#page-content .page-view')+'.dataset.line'),String(note.location.line));
  await click('#page-dialog [data-close]');
  for (const width of [320,390,768,820,1024,1440]) {
    await size(ctx,width);
    assert.ok(await evaluate(query(card)+'.getBoundingClientRect().right<=innerWidth+1'));
    await inspect(ctx,width,card,'warranty-certificate-'+record.state);
  }
  const target=note?.location?card+' .warranty-original-note button':original;
  const feedback=await evaluate('import("/assets/walkthrough-context.js").then(m=>{const c=m.captureContext(null,'+query(target)+');return {c,url:m.returnUrl(c)}})');
  assert.deepEqual(feedback.c.params,{view:'warranty-certificate',stage:phase.id});
  assert.equal(feedback.c.rev,rev);
  await call('Page.navigate',{url:root+feedback.url});
  await wait(visible(card)+' && '+query(target)+'?.classList.contains("walk-mark")','walkthrough returned to original control');
  if (process.env.AUDIT_ISOLATED_WARRANTY_ORIGIN && note?.location) {
    assert.deepEqual((await (await fetch(root+'/api/walkthrough')).json()).notes,[]);
    await click('#walk-launch');
    await wait(query('#walk-dialog')+'?.open && !'+query('#walk-save')+'.disabled','write in the active workpaper');
    const opinion='请在这条批注旁保留维修工单入口。';
    await evaluate(query('#walk-text')+'.value='+JSON.stringify(opinion)+';'+query('#walk-text')+'.dispatchEvent(new Event("input"))');
    await click('#walk-pick');
    await click(card+' blockquote');
    await wait(query('#walk-dialog')+'.open && '+query('#walk-location')+'.textContent.includes("第 9 行")','comment location selected');
    await click('#walk-save');
    await wait('!'+query('#walk-dialog')+'.open','opinion saved');
    await call('Page.navigate',{url:root+'/app#desk'});
    await wait(visible('#case-list')+' && '+visible('#walk-launch'),'queue feedback');
    await click('#walk-launch'); await wait(query('#walk-dialog')+'?.open && !'+query('#walk-saved')+'.disabled','feedback history');
    await click('#walk-saved'); await wait(visible('#walk-history li a'),'saved comment');
    assert.equal(await evaluate(query('#walk-history li p')+'.textContent'),opinion);
    await click('#walk-history li a');
    await wait(visible(card)+' && '+query(card+' [data-warranty-note]')+'?.classList.contains("walk-mark")','reopen saved comment');
    const [saved]=(await (await fetch(root+'/api/walkthrough')).json()).notes;
    assert.deepEqual(saved.context.params,{view:'warranty-certificate',stage:phase.id});
    assert.equal(saved.context.rev,rev);
    const detail=await (await fetch(root+'/api/cases/'+report.case_id)).json();
    assert.deepEqual([detail.rev,detail.status,detail.decisions.length],[rev,'ready',0]);
  }
  const altered=await evaluate(`(()=>{const p=structuredClone(state.bundle.report), f=p.findings.find(v=>v.id===${JSON.stringify(phase.id)});
    p.graph.edges=p.graph.edges.filter(e=>!(e.type==='supports_result' && e.to==='finding/'+f.id && e.from===${JSON.stringify(record.id)}));
    return PerformanceIndex.warrantyProofs(f,p).length;})()`);
  assert.equal(altered,0);
  const unrelated=report.findings.find(f=>f.rule==='H04' && !f.warranty_check);
  await call('Page.navigate',{url:url+unrelated.id});
  await wait(query('#case-panel > [role=status]')+'?.textContent.includes("未附")','other installments cannot reopen this proof');
  const difference=report.findings.find(f=>f.rule==='H07')?.warranty_difference;
  if (difference) {
    await call('Page.navigate',{url:root+'/workpaper/'+report.case_id+'?rev='+rev+'&view=warranty-register&ticket='+difference.ticket_unit});
    await wait(query('.wr-row[aria-selected=true]')+'?.dataset.ticket==='+JSON.stringify(difference.ticket_unit),'printed certificate and open warranty ticket');
    assert.ok(await evaluate(query('.warranty-register')+'.textContent.includes("'+difference.printed_state+'")'));
  }
  console.log('PASS · R'+rev+' · '+record.state+' · file, signature or original page, six widths and pinned feedback');
}

export async function checkWarrantyTimeline({root,call,evaluate,wait},cid,revision) {
  const api=root+'/api/cases/'+cid, task=await (await fetch(api)).json();
  assert.ok(task.title.startsWith('合成演练 · '));
  const rev=Number(revision || task.rev), {report}=await (await fetch(api+'/reports/'+rev)).json();
  const phase=report.findings.find(f=>f.rule==='H04' && f.warranty_check), entry=phase.warranty_check;
  const bank=report.findings.find(f=>f.rule==='H05' && f.warranty_payment), node=s=>'document.querySelector('+JSON.stringify(s)+')';
  if (entry.certificate) return checkCertificate({root,call,evaluate,wait},report,rev,phase,bank);
  const section='[data-phase-finding="'+phase.id+'"] .phase-evidence';
  const area=node(section), inside=s=>node(section+' '+s), part=s=>inside('.warranty-timeline '+s);
  const stage=node('[data-phase-choice="'+phase.id+'"]'), url=root+'/workpaper/'+cid+'?rev='+rev;
  if (bank?.warranty_payment.after_submission && !entry.at_submission.future.length && rev===task.rev) {
    await call('Page.navigate',{url:root+'/app'});
    await wait(node('#case-search')+'?.getClientRects().length','audit queue');
    const name=task.title.replace('合成演练 · ','');
    await evaluate(node('#case-search')+'.value='+JSON.stringify(name)+';'+node('#case-search')+'.dispatchEvent(new Event("input",{bubbles:true}))');
    const card=node('.audit-card a[href="'+new URL(url).pathname+'?rev='+rev+'"]');
    await wait(card+'?.getClientRects().length','frozen workpaper link in search results');
    await evaluate(card+'.click()');
  } else await call('Page.navigate',{url});
  await wait(stage,'warranty payment phase');
  await evaluate(stage+'.click()');
  if (!entry.at_submission) {
    assert.equal(await evaluate(inside('.warranty-timeline')),null);
    assert.equal(await evaluate(inside('button[data-mode="warranty"]')),null);
    console.log('PASS · R'+rev+' · historical warranty program retained'); return;
  }
  const visible=inside('.warranty-timeline');
  assert.equal(await evaluate(area+'.dataset.mode'),'warranty');
  assert.equal(await evaluate(part('.warranty-cutoff time')+'.dateTime'),entry.at_submission.as_of);
  const rows=await evaluate('[...'+visible+'.querySelectorAll(".warranty-event")].map(b=>[b.dataset.event,b.querySelector("time")?.dateTime || null,b.dataset.future])');
  const dates=[entry.accepted_on,entry.calendar_end,entry.confirmed_on,...(bank?[bank.warranty_payment.paid_on]:[])];
  assert.deepEqual(rows.map(r=>r[1]),dates);
  assert.deepEqual(rows.map(r=>r[2]),dates.map(d=>String(Boolean(d && d>entry.at_submission.as_of))));
  const title=task.title.replace('合成演练 · ','');
  const expected=new Map([
    ['提交时质保期未满但确认单及回单均记载已履行','距质保末日还有 3 天'],
    ['质保已到期但成功回单落款在提交日之后','回单晚于提交 3 天'],
    ['质保金回单日期等于资料提交日',entry.status==='ok'?'已取得期满确认':'质保依据待核'],
    ['确认单记载温控故障未修复仍有质保金回单','确认单仍列有未结缺陷'],
    ['合同要求清结缺陷但确认单缺少记录','质保依据待核']
  ]);
  if (bank && entry.confirmed_on) assert.equal(await evaluate(part('h4')+'.textContent'),expected.get(title));
  const initial=await evaluate(part('.warranty-selected')+'.dataset.event');
  if (entry.calendar_end && entry.confirmed_on && bank && entry.term_ref) {
    const detached=await evaluate(`(()=>{
      const r=structuredClone(state.bundle.report), g=r.graph;
      const phase=r.findings.find(f=>f.id===${JSON.stringify(phase.id)}), bank=r.findings.find(f=>f.id===${JSON.stringify(bank.id)});
      const w=phase.warranty_check;
      g.edges=g.edges.filter(e=>!(e.type==='supports_result' && e.to==='finding/'+phase.id && e.from===w.term_ref));
      w.confirmed_on='2079-04-15';
      const sample=WarrantyTimeline.panel(phase,[bank],g);
      const time=k=>sample.querySelector('.warranty-event[data-event="'+k+'"] time')?.dateTime || null;
      const dates=[time('end'),time('confirmation'),time(bank.id)];
      g.warranty_as_of='2079-04-15';
      return [dates,WarrantyTimeline.panel(phase,[bank],g)===null];
    })()`);
    assert.deepEqual(detached,[[null,null,bank.warranty_payment.paid_on],true]);
  }
  const open=async (s,id)=>{
    assert.equal(await evaluate(s+'.dataset.source'),id);
    await evaluate(s+'.click()');
    await wait(node('#page-dialog')+'.open && '+node('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(id)+' && '+node('#page-dialog img')+'?.naturalWidth>0','original page and line '+id);
    await evaluate(node('#page-dialog [data-close]')+'.click()');
  };
  const event=k=>part('button.warranty-event[data-event="'+k+'"]');
  const key=async name=>{
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:name});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:name});
  };
  await evaluate(event(rows.at(-1)[0])+'.focus()'); await key('Home');
  assert.equal(await evaluate('document.activeElement.dataset.event'),'start');
  await key('ArrowDown'); assert.equal(await evaluate('document.activeElement.dataset.event'),'end');
  assert.equal(await evaluate(part('.warranty-selected')+'.dataset.event'),'end');
  const expectedEnd=[...(entry.period?.fixed?[]:entry.at_submission.start_refs),entry.term_ref].filter(Boolean);
  assert.deepEqual(await evaluate('[...'+part('.warranty-selected')+'.querySelectorAll("[data-source]")].map(b=>b.dataset.source)'),expectedEnd);
  for (const id of expectedEnd) await open(part('.warranty-cite[data-source="'+id+'"]'),id);
  if (entry.calendar_end && expectedEnd.length) {
    await wait(part('.warranty-selected')+'.querySelectorAll("canvas").length==='+expectedEnd.length,'original date and term crops');
  }
  for (const [k,ids] of [['confirmation',[entry.confirmation_ref]],...(bank?[[bank.id,bank.warranty_payment.date_refs]]:[])]) {
    await evaluate(event(k)+'.click()');
    for (const id of ids.filter(Boolean)) await open(part('.warranty-cite[data-source="'+id+'"]'),id);
  }
  if (entry.defect_ref) await open(part('.warranty-defect-source'),entry.defect_ref);
  else assert.equal(await evaluate(part('.warranty-defect-source')),null);
  if (entry.condition_ref) await open(part('.warranty-condition'),entry.condition_ref);
  assert.equal(await evaluate(part('.warranty-defects')+'?.dataset.record'),entry.at_submission.defects);
  await evaluate(event(initial)+'.click()');
  const zoom=part('button[data-scale="week"]');
  if (await evaluate(zoom)) {
    await evaluate(zoom+'.click()');
    assert.equal(await evaluate(event('start')+'.dataset.range'),entry.accepted_on && entry.accepted_on<entry.at_submission.as_of && Date.parse(entry.at_submission.as_of)-Date.parse(entry.accepted_on)>7*86400000?'before':entry.accepted_on?'inside':'unknown');
    assert.equal(await evaluate(zoom+'.getAttribute("aria-pressed")'),'true');
    await evaluate(part('button[data-scale="all"]')+'.click()');
    assert.equal(await evaluate(event('start')+'.dataset.range'),entry.accepted_on?'inside':'unknown');
    if (entry.at_submission.future.length || bank?.warranty_payment.after_submission) await evaluate(zoom+'.click()');
  }
  await evaluate(inside('button[data-mode="checks"]')+'.click()');
  await evaluate(inside('button[data-check="warranty"]')+'.click()');
  assert.equal(await evaluate(area+'.dataset.mode'),'warranty');
  if (bank) {
    await evaluate(inside('button[data-mode="timeline"]')+'.click()');
    assert.ok((await evaluate(inside('[data-event="paid"]')+'.textContent')).includes('回单落款'));
    await evaluate(inside('button[data-mode="warranty"]')+'.click()');
  }
  for (const width of [320,390,600,768,1024,1440]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
    await evaluate('document.activeElement.blur();'+area+'.scrollIntoView({block:"center"});document.fonts.ready.then(()=>true)');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width+' page overflow');
    assert.ok(await evaluate('[...'+visible+'.querySelectorAll("button,time")].filter(n=>n.getClientRects().length).every(n=>n.getBoundingClientRect().right<='+visible+'.getBoundingClientRect().right+1)'),width+' control overflow');
    if (process.env.AUDIT_UI_SHOTS && [390,1440].includes(width)) {
      const clip=await evaluate('(()=>{const b='+area+'.getBoundingClientRect();return {x:b.x+scrollX,y:b.y+scrollY,width:b.width,height:b.height,scale:1}})()');
      const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'warranty-'+cid+'-R'+rev+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
    }
  }
  console.log('PASS · R'+rev+' · '+title+' · six widths, submission date, sources and keyboard selection');
}
