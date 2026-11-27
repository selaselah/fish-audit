import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {browserInput,inspect,size} from './review-screen.mjs';

export async function checkPublicRelease(ctx) {
  const {root,call,evaluate,wait}=ctx,{key,tap}=browserInput(ctx);
  const q=s=>'document.querySelector('+JSON.stringify(s)+')',card='#payment-release .release-card';
  const url=root+'/?scene=payment-release&slip=late#workflow';
  const {editions}=await (await fetch(root+'/assets/release-examples.json')).json();
  const published=new Map(editions.flatMap(s=>Object.values(s.docs)).flatMap(d=>[[d.pdf || d.original,d.source_sha256],[d.image,d.page_sha256]]));
  for (const [path,expected] of published) {
    const reply=await fetch(root+path);assert.ok(reply.ok,path);
    assert.equal(createHash('sha256').update(Buffer.from(await reply.arrayBuffer())).digest('hex'),expected);
  }
  await call('Page.navigate',{url});await wait(q(card)+'?.dataset.releaseState==="signature_pending"','public release inspector');
  for (const width of [1440,1024,820,768,390,320]) {
    await size(ctx,width);
    await call('Emulation.setTouchEmulationEnabled',{enabled:width<600});
    for (const sample of editions) {
      const pick=q('#release-example'),pane=q(card+' .release-pane'),active=q(card+' [aria-selected=true]');
      await evaluate(pick+'.value='+JSON.stringify(sample.key)+';'+pick+'.dispatchEvent(new Event("change"))');
      assert.equal(await evaluate(q(card)+'.dataset.releaseRecord'),sample.record.id);
      assert.equal(await evaluate('new URL(location.href).searchParams.get("slip")'),sample.key);
      assert.equal(await evaluate(q('#payment-version')+'.textContent'),'合成演练 · R'+sample.rev);
      if (sample.timing==='before') {
        assert.equal(await evaluate(q(card+' .release-flag[data-risk=true]')+'.textContent'),'提前付款风险');
        assert.equal(await evaluate(q(card+' .release-span')+'.textContent'),'间隔 1 天');
        assert.ok(await evaluate(q(card+' .release-dates button:first-child')+'.textContent.includes("回单付款日")'));
        if (width===1440 || width===390) await inspect(ctx,width,card,'public-release-dates');
      }
      await evaluate(active+'.focus()');await key('Home');
      if (sample.key==='earlier') {
        assert.match(await evaluate(q(card+' .pdf-byte-delta')+'.textContent'),/追加 349 字节/);
        if (width===1440 || width===390) await inspect(ctx,width,card,'public-release-version');
      }
      if (sample.key==='comment') {
        assert.equal(await evaluate(q(card+' blockquote')+'.textContent'),sample.notes[0].text);
        const btn=card+' .release-note button';await evaluate(q(btn)+'.click()');
        await wait(q('#sample-review')+'.open && '+q('#sample-location')+'.textContent.includes("第 8 行")','original comment anchor');
        await key('Escape');assert.equal(await evaluate('document.activeElement==='+q(btn)),true);
      }
      await evaluate(active+'.focus()');await key('ArrowRight');assert.equal(await evaluate(pane+'.dataset.releaseView'),'authority');
      if (sample.key==='late') assert.equal(await evaluate(q(card+' .release-flag')+'.textContent'),'签署身份待核');
      await evaluate(q(card+' [role=switch]')+'.click()');
      await wait(q(card+' .release-pair .release-crop canvas')+'?.width>0','real line from the contract');
      assert.equal(await evaluate(q(card+' .release-pair button:nth-child(2)')+'.querySelectorAll(".release-crop").length'),sample.key==='scan'?0:1);
      if (sample.key==='comment') {
        const raw=q(card+' .release-pane > .release-entry .release-transcribed');
        await wait(raw+'?.textContent==='+JSON.stringify(sample.rows.hold.value),'verbatim opinion is read aloud once its image is displayed');
        assert.equal(await evaluate('getComputedStyle('+raw+').width'),'1px');
      }
      if (sample.key==='comment' && (width===1440 || width===390)) await inspect(ctx,width,card,'public-release-authority');
      if (sample.key==='scan' && [390,1440].includes(width)) {
        const preview=card+' .release-sheet';
        if (width<600) await tap(q(preview));else await evaluate(q(preview)+'.click()');
        await wait(q('#sample-review')+'.open && '+q('#sample-location')+'.textContent.includes("整页")','whole watermarked scan');
        await key('Escape');assert.equal(await evaluate('document.activeElement==='+q(preview)),true);
      }
      assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && '+q(card)+'.scrollWidth<='+q(card)+'.clientWidth+1'),true);
    }
  }
  await evaluate(q(card+' .agreement-check button')+'.click()');await wait(q(card+' .agreement-check')+'.dataset.state==="match"','public sample hash matches');
  const privateRequests=await evaluate('performance.getEntriesByType("resource").map(r=>new URL(r.name).pathname).filter(p=>p.startsWith("/api/cases"))');
  assert.deepEqual(privateRequests,[]);
  await call('Page.reload',{ignoreCache:true});await wait(q('#release-example')+'?.value==="scan"','fixed edition survives reload');
  await evaluate(q('#find-case')+'.click()');
  const input=q('#case-finder input');await evaluate(input+'.value="签后追加";'+input+'.dispatchEvent(new Event("input"))');
  await key('Enter');await wait(q('#release-example')+'.value==="earlier" && location.search.includes("slip=earlier")','case finder selects the actual signed revision');
  await call('Network.enable');await call('Network.setCacheDisabled',{cacheDisabled:true});
  await call('Network.setBlockedURLs',{urls:['*release-examples.json*']});
  await call('Page.navigate',{url:root+'/?scene=payment-release&slip=comment#workflow'});
  const retry=q('#payment-release .standard-retry');
  await wait(retry+'?.getClientRects().length','retry when the fixed source index is unavailable');
  const fallback=q('#payment-release > a[data-slip]:not([hidden])');
  assert.equal(await evaluate(fallback+'.getAttribute("href")'),editions.find(e=>e.key==='comment').docs.d01.original);
  await call('Network.setBlockedURLs',{urls:[]});await evaluate(retry+'.click()');
  await wait(q('#release-example')+'?.value==="comment"','recover the requested Word revision');
  console.log('PASS · five pinned public release reviews, original-line switch, dates, scan, keyboard and six widths');
}

async function checkExecution(ctx,report,phase,rev) {
  const {evaluate,wait}=ctx,{key}=browserInput(ctx);
  const q=s=>'document.querySelector('+JSON.stringify(s)+')';
  const option=phase.payment_opinion.release,ident=option.signature_records[0];
  const record=[...report.graph.release_pdf_sources.records,...report.graph.release_original_sources.records].find(r=>r.id===ident);
  const section='[data-phase-finding="'+phase.id+'"] .phase-evidence',card=section+' .release-card';
  await evaluate(q('[data-phase-choice="'+phase.id+'"]')+'.click()');
  await evaluate(q(section+' [data-mode=opinion]')+'.click()');
  await wait(q(card)+'?.dataset.releaseRecord==='+JSON.stringify(ident),'signed instrument bound to the selected installment');
  const tabs=card+' .release-tabs',selected=q(tabs+' [aria-selected=true]');
  for (const width of [1440,1024,820,768,390,320]) {
    await size(ctx,width);
    await evaluate(selected+'.focus()');await key('Home');
    assert.equal(await evaluate(q(card+' .release-pane')+'.dataset.releaseView'),'version');
    if (record.state==='earlier') assert.match(await evaluate(q(card+' .pdf-byte-delta')+'.textContent'),/追加/);
    if (record.notes?.length) assert.equal(await evaluate(q(card+' blockquote')+'.textContent'),report.graph.release_original_sources.documents[0].notes[0].text);
    if (width===1440 || width===390) await inspect(ctx,width,card,'release-'+record.state);
    await key('ArrowRight');assert.equal(await evaluate(q(card+' .release-pane')+'.dataset.releaseView'),'authority');
    assert.ok(await evaluate(q(card+' .release-pane')+'.textContent.includes('+JSON.stringify(option.required)+')'));
    const crops=q(card+' [role=switch]');
    await evaluate(crops+'.click()');
    await wait(q(card+' .release-pair .release-crop canvas')+'?.width>0','private, revision-specific contract line');
    await evaluate(crops+'.click()');
    let src=q(card+' .release-pair button');
    await evaluate(src+'.click()');await wait(q('#page-dialog .page-image')+'?.naturalWidth>0','contract page loads');
    assert.ok(await evaluate(q('#page-dialog .located')+'?.textContent.includes("放行约定")'));
    const version=new URL(await evaluate(q('#page-dialog .source-tools a')+'.href'));assert.equal(version.searchParams.get('rev'),String(rev));
    await evaluate(q('#page-dialog [data-close]')+'.click()');
    await evaluate(selected+'.focus()');await key('End');
    assert.equal(await evaluate(q(card+' .release-pane')+'.dataset.releaseView'),record.state==='photo'?'authority':'dates');
    if (option.sources.some(s=>s.role==='approval_date') && !option.sources.some(s=>s.role==='date')) {
      const body=await evaluate(q(card+' .release-pane')+'.textContent');
      assert.match(body,/单上所列签字日日期待核/);assert.match(body,/单上审批日期/);
    }
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && '+q(card)+'.scrollWidth<='+q(card)+'.clientWidth+1'));
  }
  await evaluate(q(card+' .agreement-check button')+'.click()');
  await wait(q(card+' .agreement-check')+'.dataset.state==="match"','cryptographic match on the revision-specific original');
  const failed=await evaluate(`(() => {
    const r=state.bundle.report, f=r.findings.find(f=>f.id===${JSON.stringify(phase.id)}), id=${JSON.stringify(ident)};
    return ['file','edge','program','call'].map(change=>{
      const report=structuredClone(r), graph=report.graph, record=[...graph.release_original_sources.records,...graph.release_pdf_sources.records].find(r=>r.id===id);
      if(change==='file') record.original_sha256='0'.repeat(64);
      if(change==='edge') graph.edges=graph.edges.filter(e=>!(e.type==='supports_result' && e.from===id && e.to==='finding/'+f.id));
      if(change==='program') delete report.policy.code_sha256['release_execution.py'];
      if(change==='call') report.calls.pages=report.calls.pages.filter(c=>c.doc!==record.doc);
      return PerformanceIndex.releaseProofs(f,report).length;
    });
  })()`);
  assert.deepEqual(failed,[0,0,0,0]);
  const address=await evaluate(q(card+' [aria-label="本版付款放行单核对固定链接"]')+'.href');
  assert.equal(new URL(address).searchParams.get('stage'),phase.id);
  await ctx.call('Page.navigate',{url:address});
  await wait('document.activeElement?.matches(".release-tab[aria-selected=true]") && document.activeElement.closest(".release-card")?.dataset.releaseRecord==='+JSON.stringify(ident),'direct link selects the issued phase and focuses its release');
  const bank=report.findings.find(f=>f.rule==='H05' && f.payment_opinion?.release?.signature_records?.includes(ident));
  if (bank && bank.payment_opinion.release.paid_ref) {
    const bankLink=new URL(address);bankLink.searchParams.set('stage',bank.id);
    await ctx.call('Page.navigate',{url:bankLink.href});await wait('document.activeElement?.dataset.view==="dates"','payment link selects its date comparison');
    if (bank.status==='risk' && bank.payment_opinion.release.written_timing==='before') {
      assert.equal(await evaluate(q(card+' .release-flag[data-risk=true]')+'.textContent'),'提前付款风险');
    }
  }
  console.log('PASS · R'+rev+' · '+record.state+' · release tabs, original, keyboard, evidence binding and six widths');
}

async function checkComparison(ctx,report,phase,rev) {
  const {root,call,evaluate,wait}=ctx, release=phase.payment_opinion.release;
  const bank=report.findings.find(f=>f.rule==='H05' && f.stage?.clause_ref===phase.stage.clause_ref);
  const base=root+'/workpaper/'+report.case_id+'?rev='+rev+'&view=payment-release&stage='+bank.id;
  const q=s=>'document.querySelector('+JSON.stringify(s)+')', group='[data-release-set="'+phase.id+'"]';
  const [first,second]=release.instruments, unit=group+' [data-instrument="'+second.unit+'"]', selector=unit+' .release-decision-line';
  await call('Page.navigate',{url:base+'&instrument='+encodeURIComponent(second.unit)});
  await wait(q(unit)+'?.getClientRects().length && '+q(unit)+'===document.activeElement','second approval in the issued installment');
  for (const width of [1440,1024,820,768,390,320]) {
    await size(ctx,width);
    assert.equal(await evaluate(q(group)+'.querySelectorAll("[data-instrument]").length'),release.instruments.length);
    assert.equal(await evaluate(q(group+' .release-flag')+'.dataset.risk'),String(release.state==='decision_conflict'));
    assert.ok(await evaluate(q(group)+'.scrollWidth<='+q(group)+'.clientWidth+1'));
    if (release.state==='decision_conflict') await inspect(ctx,width,group,'release-comparison');
  }
  for (const item of [first,second]) {
    const row=release.sources.find(r=>r.unit===item.unit && r.role==='decision' && r.line);
    const prefix=group+' [data-instrument="'+item.unit+'"]';
    assert.ok(await evaluate(q(prefix+' .release-decision-line')+'.textContent.includes('+JSON.stringify(row.quote)+')'));
    await evaluate(q(prefix+' .release-decision-line')+'.click()');
    await wait(q('#page-dialog .page-view')+'?.dataset.doc==='+JSON.stringify(row.doc)+' && '+q('#page-dialog .located')+'?.textContent.includes('+JSON.stringify(row.quote)+')','decision cites its own physical original');
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    await evaluate(q('#page-dialog [data-close]')+'.click()');
  }
  const field=release.instruments[1].receipt_ref;
  await evaluate(q(unit+' .release-compare-field button')+'.click()');
  await wait(q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(field),'second receipt reference');
  await evaluate(q('#page-dialog [data-close]')+'.click()');
  await evaluate(q('#walk-launch')+'.click()');
  await wait(q('#walk-dialog')+'?.open && !'+q('#walk-pick')+'.disabled','walkthrough can point at the second opinion');
  await evaluate(q('#walk-pick')+'.click()');await evaluate(q(selector)+'.click()');
  const printed=report.graph.documents.find(d=>d.id===release.sources.find(r=>r.unit===second.unit).doc).name;
  await wait(q('#walk-dialog')+'.open && '+q('#walk-location')+'.textContent.includes('+JSON.stringify(printed)+')','selected approval named in feedback');
  await evaluate(q('#walk-close')+'.click()');
  const saved=await evaluate("import('/assets/walkthrough-context.js').then(m=>{const c=m.captureContext(null,"+q(selector)+");return {c,url:m.returnUrl(c,null)}})");
  assert.deepEqual(saved.c.params,{view:'payment-release',stage:phase.id,instrument:second.unit});
  assert.equal(saved.c.rev,rev);
  await call('Page.navigate',{url:root+saved.url});
  await wait(q(selector)+'?.getClientRects().length && '+q(selector)+'.classList.contains("walk-mark")','reopened walkthrough highlights the original decision');
  await call('Page.navigate',{url:base+'&instrument=d99'});
  await wait(q('#case-panel > [role=status]')+'?.textContent.includes("尚无可定位")','other documents cannot open this comparison');
  console.log('PASS · R'+rev+' · both printed decisions and receipts, six widths and the recorded control return');
}

export async function checkRelease({root,call,evaluate,wait},cid,revision) {
  const api=root+'/api/cases/'+cid, task=await (await fetch(api)).json();
  assert.ok(task.title.startsWith('合成演练 · '));
  const rev=Number(revision || task.rev), {report}=await (await fetch(api+'/reports/'+rev)).json();
  const node=s=>'document.querySelector('+JSON.stringify(s)+')';
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+rev});
  await wait(node('.phase-choice'),'issued phases');
  const phase=report.findings.filter(f=>f.rule==='H04')[1], bank=report.findings.find(f=>f.rule==='H05');
  const r=phase.payment_opinion?.release;
  if (r?.instruments) return checkComparison({root,call,evaluate,wait},report,phase,rev);
  if (r?.signature_records?.length) return checkExecution({root,call,evaluate,wait},report,phase,rev);
  if (!r) {
    assert.ok(!report.graph.payment_release_sources);
    assert.equal(await evaluate(node('[data-release-state]')),null);
    console.log('PASS · R'+rev+' · historical workpaper before signed releases'); return;
  }
  const timing=bank.payment_opinion.release.timing;
  const section='[data-phase-finding="'+phase.id+'"] .phase-evidence', inside=s=>node(section+' '+s);
  await evaluate(node('[data-phase-choice="'+phase.id+'"]')+'.click()');
  assert.equal(await evaluate(node(section)+'.dataset.mode'),['before','same_day'].includes(timing)?'timeline':'opinion');
  const choices=inside('.opinion-record .opinion-choices');
  const mode=k=>evaluate(inside('button[data-mode="'+k+'"]')+'.click()');
  const text=()=>evaluate(inside('.opinion-record q')+'.textContent');
  await mode('opinion');assert.equal(await evaluate(inside('.proof-opinion')+'.dataset.releaseState'),r.state);
  const note=phase.payment_opinion.notes[0], authority=r.sources.find(s=>s.role==='authority');
  const entryKind={signer_mismatch:'signature',reference_mismatch:'receipt',pending:'approval_date'}[r.state] || 'decision';
  const entry=r.sources.find(s=>s.role===entryKind);
  assert.ok(entry && authority); assert.equal(await text(),entry.quote);
  const press=async key=>{
    await call('Input.dispatchKeyEvent',{type:'keyDown',key,code:key});
    await call('Input.dispatchKeyEvent',{type:'keyUp',key,code:key});
  };
  await evaluate(choices+'.querySelector("[aria-pressed=true]").focus()');
  for (const [key,row] of [['Home',note],['ArrowRight',authority],['End',entry]]) {
    await press(key); assert.equal(await text(),row.quote);
    await evaluate(inside('.opinion-record .ref')+'.click()');
    await wait(node('#page-dialog .located')+'?.textContent.includes('+JSON.stringify(row.quote)+')','the selected original row');
    await wait(node('#page-dialog .page-image')+'?.naturalWidth>0','issued page image');
    const url=new URL(await evaluate(node('#page-dialog .source-tools a')+'.href'));
    assert.ok(url.pathname.endsWith('/documents/'+row.doc+'/pages/'+row.page));assert.equal(url.searchParams.get('rev'),String(rev));
    await evaluate(node('#page-dialog [data-close]')+'.click()');
    await evaluate(choices+'.querySelector("[aria-pressed=true]").focus()');
  }
  const fallback=await evaluate(`(() => {
    const {graph,findings}=state.bundle.report;
    const finding=findings.find(f=>f.id===${JSON.stringify(phase.id)});
    const mandate=ReleaseEvidence.one(ReleaseEvidence.sources(graph,finding),'authority');
    const page=mandate.doc+'/p'+mandate.page;
    const without=skip=>({...graph,edges:graph.edges.filter(edge=>!skip(edge))});
    const supports=edge=>edge.type==='supports_result' && edge.to==='finding/'+finding.id;
    const copy=without(edge=>supports(edge) && mandate.facts.includes(edge.from));
    const row=ReleaseEvidence.one(ReleaseEvidence.sources(copy,finding),'authority');
    const roleIn=g=>ReleaseEvidence.sources(g,finding).some(s=>s.role==='authority');
    AcceptanceOpinion.source(row,copy).querySelector('button').click();
    return {
      facts:row.facts,
      pageMissing:roleIn(without(edge=>supports(edge) && edge.from===page)),
      lineMissing:roleIn(without(edge=>edge.type==='payment_release_basis' && edge.from===row.unit && edge.to===page && edge.line===row.line))
    };
  })()`);
  assert.deepEqual(fallback,{facts:[],pageMissing:false,lineMissing:false});
  const located=node('#page-dialog .evidence-row.located');
  await wait(located+'?.dataset.sourceRef==='+JSON.stringify('release-line/'+authority.line),'unboxed mandate on its printed line');
  assert.ok(await evaluate(located+'.textContent.includes('+JSON.stringify(authority.quote)+')'));
  assert.equal(await evaluate(node('#page-dialog .image-sheet svg rect')),null);
  assert.equal(new URL(await evaluate(node('#page-dialog .source-tools a')+'.href')).searchParams.get('rev'),String(rev));
  await evaluate(node('#page-dialog [data-close]')+'.click()');
  const state={matched:'已核具名放行',signer_mismatch:'签发人不符',reference_mismatch:'原验收单号不符',pending:'缺放行签字日'}[r.state];
  assert.equal(await evaluate(inside('.proof-count')+'.textContent'),state);
  async function capture(selector,name) {
    const panel=node(selector);
    await evaluate('document.activeElement.blur();'+panel+'.scrollIntoView({block:"center"});document.fonts.ready.then(()=>true)');
    const clip=await evaluate('(()=>{const b='+panel+'.getBoundingClientRect();return {x:b.x+scrollX,y:b.y+scrollY,width:b.width,height:b.height,scale:1}})()');
    const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
    await writeFile(join(process.env.AUDIT_UI_SHOTS,name+'.png'),Buffer.from(shot.data,'base64'));
  }
  for (const width of [1440,1024,820,768,390,320]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:940,deviceScaleFactor:1,mobile:width<600});
    for (const k of ['checks','opinion','timeline']) {
      await mode(k);
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && '+node(section)+'.scrollWidth<='+node(section)+'.clientWidth+1'),k+' fits '+width);
      if (k==='checks') assert.equal(await evaluate(inside('[data-check=release]')+'.dataset.state'),r.state==='matched'?'ok':'missing');
      if (process.env.AUDIT_UI_SHOTS && (width===390 || width===1440) &&
        (k==='opinion' && r.state==='signer_mismatch' || k==='timeline' && timing==='before'))
        await capture('.performance-panel','release-'+(k==='timeline'?'dates':'signer')+'-'+width);
    }
    const event=inside('[data-event=release]');
    assert.equal(await evaluate(event+'?.closest("[data-day]")?.dataset.day ?? null'),r.state==='matched'?r.signed_on:null);
    const hold=inside('[data-event=hold]');
    assert.equal(await evaluate(hold+'?.closest("[data-day]")?.dataset.day ?? null'),r.held_on);
    if (r.held_on) assert.ok(await evaluate(hold+'.closest("[data-day]")==='+inside('[data-event=acceptance]')+'.closest("[data-day]")'));
    const count=await evaluate(inside('.proof-count')+'.textContent');
    if (timing==='before') assert.equal(count,'实付早于放行 1 天');
    if (timing==='same_day') {
      assert.equal(count,'放行与实付同日 · 时分待核');
      assert.ok(await evaluate(event+'.closest("[data-day]")==='+inside('[data-event=paid]')+'.closest("[data-day]")'));
    }
  }
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:940,deviceScaleFactor:1,mobile:false});
  if (r.held_on) {
    await evaluate(inside('[data-event=hold]')+'.click()');
    await wait(node('#page-dialog .located')+'?.textContent.includes('+JSON.stringify(note.quote)+')','hold event opens the original hold instruction');
    const url=new URL(await evaluate(node('#page-dialog .source-tools a')+'.href'));
    assert.ok(url.pathname.endsWith('/documents/'+note.doc+'/pages/'+note.page));assert.equal(url.searchParams.get('rev'),String(rev));
    await evaluate(node('#page-dialog [data-close]')+'.click()');
  }
  await mode('opinion');
  const party=authority.facts.find(id=>report.graph.facts.some(f=>f.id===id && f.source_line?.text===authority.quote && f.source_line?.rects.length));
  const pairs=[['release-authority',[party,r.signature_ref]],['release-receipt',[r.original_ref,r.receipt_ref]],
    ['release-transfer',[r.date_ref,bank.payment_opinion.release.paid_ref]]];
  for (const [key,ids] of pairs) {
    const target=inside('[data-pair="'+key+'"]');
    const needed=ids.every(Boolean) && (key!=='release-receipt' || r.state==='reference_mismatch') && (key!=='release-transfer' || r.state==='matched');
    assert.equal(await evaluate('Boolean('+target+')'),needed,key);
    if (!needed) continue;
    await evaluate(target+'.click()');await wait('document.querySelectorAll(".compare-leaf canvas").length===2','two original lines');
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".compare-leaf")].map(n=>n.dataset.fact)'),ids);
    const fold=node('.release-relations');
    if (!(await evaluate(fold+'.open'))) await evaluate(fold+'.querySelector("summary").click()');
    await wait(fold+'.querySelectorAll(".reservation-note").length>1','related original lines');
    await evaluate(node('#tabs [data-tab=report]')+'.click()');
    assert.equal(await evaluate(node('.phase-choice[aria-selected=true]')+'.dataset.phaseChoice'),phase.id);
  }
  console.log('PASS · R'+rev+' · '+r.state+' / '+timing+' · six widths, originals, signer, receipt number and dated release');
}
