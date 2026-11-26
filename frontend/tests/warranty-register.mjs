import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {browserInput,inspect,size} from './review-screen.mjs';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const all=s=>'[...document.querySelectorAll('+JSON.stringify(s)+')]';
const id='920ea04963ef4f68905ff87533133fd4', rev=11, widths=[320,360,390,768,1024,1440];
const card='.warranty-register', slot='#payment-warranty-register';
const tab=doc=>q(card+' .wr-row[data-ticket="'+doc+'"]');
const selected=q(card+' .wr-row[aria-selected=true]');
const digest=(data,encoding='hex')=>createHash('sha256').update(Buffer.from(data)).digest(encoding);
const fixed=(root,version,ticket)=>root+'/workpaper/'+id+'?'+new URLSearchParams({rev:version,view:'warranty-register',...(ticket?{ticket}:{})});

async function controls(ctx,width) {
  const {evaluate,wait}=ctx,{key,tap}=browserInput(ctx);
  assert.deepEqual(await evaluate(all(card+' .wr-row-identity strong')+'.map(el=>el.textContent)'),['柜体风扇故障','温控探头故障']);
  assert.deepEqual(await evaluate(all(card+' .wr-state')+'.map(el=>el.textContent)'),['待维修','已关闭']);
  assert.deepEqual(await evaluate(all(card+' .wr-basis-item > strong')+'.map(el=>el.textContent)'),['依据待核','依据待核']);
  assert.equal(await evaluate(selected+'.dataset.ticket'),'d01');
  await evaluate(selected+'.focus()'); await key('ArrowDown');
  assert.equal(await evaluate('document.activeElement==='+tab('d03')),true);
  await key('ArrowUp'); assert.equal(await evaluate('document.activeElement==='+tab('d01')),true);
  await key('End');
  assert.equal(await evaluate('document.activeElement==='+tab('d03')),true);
  assert.deepEqual(await evaluate(all(card+' .wr-source')+'.map(el=>el.dataset.source)'),['d03/p1/f9','d03/p1/f10']);
  const filter=q(card+' .wr-filters button:last-child'), showAll=q(card+' .wr-filters button:first-child');
  if (width<600) await tap(filter); else await evaluate(filter+'.click()');
  await wait(selected+'.dataset.ticket==="d01" && '+tab('d03')+'.hidden','filter to the one documented difference');
  assert.equal(await evaluate(filter+'.getAttribute("aria-pressed")'),'true');
  await evaluate(showAll+'.click();'+tab('d03')+'.click()');
  await evaluate(selected+'.focus()'); await key('Home');
  assert.equal(await evaluate('document.activeElement==='+tab('d01')),true);
  assert.deepEqual(await evaluate(all(card+' .wr-source')+'.map(el=>el.dataset.source)'),['d02/p1/f7','d01/p1/f8']);
  await wait(all(card+' .wr-source[data-printed=true]')+'.length===2','both selected original line images');
  assert.ok(await evaluate(q(card)+'.scrollWidth<='+q(card)+'.clientWidth+1'),'work order register fits '+width);
}

async function crop(ctx,doc,row) {
  const selector=q(card+' .wr-source[data-source="'+row.ref+'"]');
  const same=await ctx.evaluate('(async()=>{const img=new Image();img.src='+JSON.stringify(doc.image)+';await img.decode();'+
    'const [l,t,r,b]='+JSON.stringify(row.rect)+',w=img.naturalWidth,h=img.naturalHeight,'+
    'x=Math.max(0,Math.floor(l*w)-4),y=Math.max(0,Math.floor(t*h)-4),c=document.createElement("canvas");'+
    'c.width=Math.min(w-x,Math.ceil(r*w)+4-x);c.height=Math.min(h-y,Math.ceil(b*h)+4-y);'+
    'c.getContext("2d").drawImage(img,x,y,c.width,c.height,0,0,c.width,c.height);return c.toDataURL()==='+selector+'.querySelector("canvas").toDataURL();})()');
  assert.ok(same,'physical watermarked image pixels '+row.ref);
}

export async function checkPublicWarrantyRegister(ctx) {
  const {root,call,evaluate,wait}=ctx, {key}=browserInput(ctx);
  const raw=await (await fetch(root+'/assets/warranty-register-sample.json')).arrayBuffer(), sample=JSON.parse(Buffer.from(raw));
  assert.equal(sample.case_id,id);
  for (const doc of Object.values(sample.documents)) {
    for (const [path,sha] of [[doc.pdf,doc.source_sha256],[doc.image,doc.page_sha256]]) {
      const response=await fetch(root+path); assert.equal(response.status,200); assert.equal(digest(await response.arrayBuffer()),sha);
    }
  }
  const url=root+'/?scene=warranty-register#workflow';
  for (const width of widths) {
    await size(ctx,width); await call('Emulation.setTouchEmulationEnabled',{enabled:width<600});
    await call('Page.navigate',{url:url.replace('#workflow','&width='+width+'#workflow')}); await wait(q(slot)+'?.dataset.revision==="11"','issued public register');
    assert.equal(await evaluate(q(slot)+'.dataset.integrity'),'sha256-'+digest(raw,'base64'));
    await controls(ctx,width);
    await inspect(ctx,width,width<600?'#scene-folios':'.workflow .section-inner','public-warranty-register',width<600?'start':'center');
    if ([390,1440].includes(width)) {
      for (const doc of [sample.documents.open,sample.documents.certificate]) {
        const row=doc.lines.find(line=>['warranty_ticket_state','warranty_defects'].includes(line.field));
        await crop(ctx,doc,row);
      }
      const visited=new Set();
      for (const unit of ['d01','d03']) {
        await evaluate(tab(unit)+'.click();'+q(card+' .wr-extra summary')+'.click()');
        const refs=await evaluate(all(card+' [data-source]')+'.map(el=>el.dataset.source)');
        for (const ref of refs) {
          if (visited.has(ref)) continue;
          visited.add(ref);
          const doc=Object.values(sample.documents).find(d=>d.lines.some(l=>l.ref===ref));
          const line=doc.lines.find(r=>r.ref===ref), link=q(card+' [data-source="'+ref+'"]');
          await evaluate(link+'.click()'); await wait(q('#sample-review')+'.open && '+q('#sample-review canvas')+'.dataset.fact==='+JSON.stringify(ref),'open public physical row '+ref);
          assert.equal(await evaluate(q('#sample-location')+'.textContent'),'第 1 页 · 第 '+line.line+' 行');
          assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),doc.pdf);
          await key('Escape'); await wait('document.activeElement==='+link,'return to public work order field');
        }
      }
      assert.ok(visited.size>=14);
    }
    assert.equal(await evaluate('performance.getEntriesByType("resource").some(e=>new URL(e.name).pathname.startsWith("/api/"))'),false);
  }
  await call('Network.enable'); await call('Network.setCacheDisabled',{cacheDisabled:true});
  await call('Network.setBlockedURLs',{urls:['*warranty-register-sample.json*']}); await call('Page.navigate',{url:url.replace('#workflow','&check=index#workflow')});
  const retry=q(slot+' .standard-retry'), host=q(slot);
  await wait(retry+' && '+host+'.getAttribute("aria-busy")==="false"','watermarked PDFs available offline');
  assert.equal(await evaluate(all(slot+' .period-fallback a')+'.length'),2);
  await call('Network.setBlockedURLs',{urls:[]});
  await evaluate(host+'.dataset.saved='+host+'.dataset.integrity;'+host+'.dataset.integrity="sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=";'+retry+'.click()');
  await wait(host+'.getAttribute("aria-busy")==="false"','digest rejection');
  assert.equal(await evaluate(q(card)),null);
  await evaluate(host+'.dataset.integrity='+host+'.dataset.saved;'+retry+'.focus();'+retry+'.click()');
  await wait('document.activeElement==='+tab('d01'),'restored verified sample focus');
  await call('Network.setBlockedURLs',{urls:['*warranty-register-open.jpg*']}); await call('Page.navigate',{url:url.replace('#workflow','&check=image#workflow')});
  const open=q(card+' .wr-source[data-source="d01/p1/f8"]');
  await wait(open+' && !'+open+'.querySelector(".wr-quote").classList.contains("wr-transcribed")','retain printed transcription after failed image');
  await evaluate(open+'.click()');
  await wait(q('#sample-review')+'.open && '+q('#sample-review [role=status]')+'.textContent.includes("校验")','failed image never shown as checked original');
  assert.equal(await evaluate(q('#sample-review canvas')+'.dataset.fact || null'),null);
  assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),sample.documents.open.pdf);
  await key('Escape'); await call('Network.setBlockedURLs',{urls:[]});
  await evaluate(tab('d03')+'.click();'+tab('d01')+'.click()'); await wait(open+'.dataset.printed==="true"','page restored');
  await call('Page.navigate',{url:root+'/#workflow'}); await wait(q('#find-case')+'?.hidden===false','search available');
  await evaluate(q('#find-case')+'.click();'+q('#finder-query')+'.value="质保 缺陷";'+q('#finder-query')+'.dispatchEvent(new Event("input"))');
  assert.equal(await evaluate(all('#finder-results [role=option]')+'.length'),1);
  await key('Enter'); await wait(q(slot)+'?.dataset.revision==="11" && '+q('#payment-example')+'.value==="warranty"','work order reached from homepage search');
  console.log('PASS · published warranty register · five original PDFs and images, source pixels, 14+ addressable original rows, failure recovery and six widths');
}

function broken(kind) {
  const report=structuredClone(state.bundle.report), graph=report.graph;
  const difference=report.findings.find(f=>f.rule==='H07'), phase=report.findings.find(f=>f.rule==='H04' && f.warranty_check);
  const obj=difference.warranty_difference, ref=obj.refs.ticket_state, f=graph.facts.find(f=>f.id===ref);
  const edge=graph.edges.find(e=>e.type==='warranty_record_difference'), sheet=graph.warranty_sources.register_pages.find(p=>p.doc===f.doc);
  switch (kind) {
    case 'method': delete report.policy.code_sha256['warranty_register.py']; break;
    case 'relation': graph.edges=graph.edges.filter(e=>e!==edge); break;
    case 'duplicate': graph.edges.push(structuredClone(edge)); break;
    case 'role': obj.ticket_unit='d03'; break;
    case 'scope': delete phase.scope; break;
    case 'releaseFields': delete graph.warranty_sources.register_pages.find(p=>p.role==='warranty').refs; break;
    case 'ticketFields': delete sheet.refs; break;
    case 'qualification': sheet.bounded=false; break;
    case 'sameDay': obj.reported_on=obj.confirmed_on; break;
    case 'procedure': graph.edges=graph.edges.filter(e=>e.type!=='procedure_result' || e.to!=='finding/'+difference.id); break;
    case 'support': graph.edges.find(e=>e.type==='supports_result' && e.from===ref && e.to==='finding/'+difference.id).evidence=[]; break;
    case 'docSha': graph.documents.find(d=>d.id===f.doc).sha256='a'.repeat(64); break;
    case 'pageSha': f.page_sha256='a'.repeat(64); break;
    case 'line': f.source_line.number++; break;
    case 'value': f.value='已关闭'; break;
    case 'geometry': f.source_line.rects[0]=[0,-1,1,2]; break;
    case 'identity': sheet.refs.buyer=sheet.refs.seller; break;
    case 'call': report.calls.pages.find(c=>c.doc===f.doc).check.response_id='another-call'; break;
    case 'signer': graph.facts.find(f=>f.id===graph.warranty_sources.register_pages.find(p=>p.role==='warranty').refs.acceptance_signer[0]).attestation.source_check.case_id='another'; break;
  }
  const model=WarrantyRegisterEvidence.resolve(report,phase,[]);
  return [model?.tickets.some(t=>t.difference) || false,Boolean(WarrantyRegisterEvidence.pair(difference,report))];
}

export async function checkPrivateWarrantyRegister(ctx) {
  const {root,call,evaluate,wait}=ctx, {key}=browserInput(ctx);
  const response=await fetch(root+'/api/cases/'+id+'/reports/'+rev), {report}=await response.json();
  assert.equal(report.result.human_required,true);
  const finding=report.findings.find(f=>f.rule==='H07'); assert.equal(finding.status,'risk');
  await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev=11'});
  const priority=q('.queue-destination button');
  await wait(priority+'?.textContent.includes("核对期满声明与维修工单")','record difference in priority queue');
  await evaluate(priority+'.click()'); await wait('document.activeElement==='+tab('d01'),'priority queue to original work order');
  await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev=11&view=payment-checks'}); await wait(q('#performance-index')+'?.open','normal payment checks');
  const picker=q('.scope-check-select');
  await evaluate(picker+'.value='+JSON.stringify(finding.id)+';'+picker+'.dispatchEvent(new Event("change"))');
  const jump='[...document.querySelectorAll("#performance-index .scope-actions button")].find(b=>b.textContent==="核对两份记载")';
  assert.equal(await evaluate(picker+'.value'),finding.id);
  assert.ok(await evaluate('Boolean('+jump+')'),'issued difference has a work-order action');
  const expected=[finding.warranty_difference.refs.defects,finding.warranty_difference.refs.ticket_state];
  const rows=all('#performance-index .scope-original-line');
  await wait(rows+'.filter(b=>b.querySelector("canvas")).length===2','two original lines in payment checks');
  for (const [index,ref] of expected.entries()) {
    const row=rows+'['+index+']', fact=report.graph.facts.find(f=>f.id===ref);
    assert.equal(await evaluate(row+'.querySelector("q").textContent'),fact.source_line.text);
    await evaluate(row+'.focus();'+row+'.click()');
    await wait(q('#page-dialog')+'.open && '+q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(ref),'payment-check original '+ref);
    await key('Escape'); await wait('document.activeElement==='+row,'return to payment-check original');
  }
  await evaluate(jump+'.click()');
  await wait('!'+q('#performance-index')+'.open && document.activeElement==='+tab('d01')+' && '+tab('d01')+'?.getClientRects().length','H07 leads to the matching third installment work order');
  for (const width of widths) {
    await size(ctx,width); await call('Emulation.setTouchEmulationEnabled',{enabled:width<600});
    await call('Page.navigate',{url:fixed(root,rev,'d01')});
    await wait('document.activeElement==='+tab('d01')+' && '+tab('d01')+'?.getClientRects().length','issued register address');
    await controls(ctx,width); await inspect(ctx,width,card,'workpaper-warranty-register','center');
    if ([390,1440].includes(width)) {
      for (const unit of ['d01','d03']) {
        await evaluate(tab(unit)+'.click()');
        assert.equal(await evaluate(q(card+' .wr-permalink')+'.href'),fixed(root,rev,unit));
        const refs=await evaluate(all(card+' .wr-source')+'.map(e=>e.dataset.source)');
        for (const ref of refs) {
          const opener=q(card+' .wr-source[data-source="'+ref+'"]');
          await evaluate(opener+'.focus();'+opener+'.click()');
          await wait(q('#page-dialog')+'.open && '+q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(ref),'workpaper original '+ref);
          await key('Escape'); await wait('document.activeElement==='+opener,'workpaper original return focus');
        }
      }
      await evaluate(tab('d01')+'.click();'+q(card+' .wr-compare')+'.click()');
      await wait(q('.compare-presets [aria-pressed=true]')+'?.dataset.pair==="warranty-record-d01" && '+all('.compare-leaf canvas')+'.length===2','exact comparison graph edge');
      assert.deepEqual(await evaluate(all('.compare-leaf')+'.map(n=>n.dataset.fact)'),[finding.warranty_difference.refs.defects,finding.warranty_difference.refs.ticket_state]);
      const relation=q('.warranty-difference-relations');
      await wait(relation+'?.getClientRects().length','published work-order relationship');
      await evaluate(relation+'.querySelector("summary").click()');
      const link=q('[data-warranty-difference="'+finding.id+'"]');
      await wait(link+'?.querySelector("button")','work order in relationship details');
      assert.deepEqual(await evaluate(link+' && Array.from('+link+'.querySelectorAll("q"),q=>q.textContent)'),expected.map(ref=>report.graph.facts.find(f=>f.id===ref).source_line.text));
      await evaluate(link+'.querySelector("button").click()');
      await wait(q('.compare-presets [aria-pressed=true]')+'?.dataset.pair==="warranty-record-d01" && '+all('.compare-leaf canvas')+'.length===2','graph relationship opens both original lines');
    }
  }
  await call('Page.navigate',{url:fixed(root,rev,'d03')});
  await wait('document.activeElement==='+tab('d03'),'fixed second work order');
  const mutations=['method','relation','duplicate','role','scope','releaseFields','ticketFields','qualification','sameDay',
    'procedure','support','docSha','pageSha','line','value','geometry','identity','call','signer'];
  for (const kind of mutations) {
    assert.deepEqual(await evaluate('('+broken.toString()+')('+JSON.stringify(kind)+')'),[false,false],kind);
  }
  for (const change of ['workspace','permission','revision','case']) {
    assert.ok(await evaluate('(()=>{const detail=state.detail,old=state.pinned;try{'+
      (change==='revision'?'state.pinned=9;':change==='permission'?'state.detail={...detail,can_review:false};':
        change==='workspace'?'state.detail={...detail,workspace:"other"};':'state.detail={...detail,id:"other"};')+
      q(card+' .wr-source')+'.click();return !'+q('#page-dialog')+'.open;}finally{state.detail=detail;state.pinned=old}})()'),change);
  }
  await call('Page.navigate',{url:fixed(root,rev,'d99')});
  await wait('document.activeElement.textContent==="本版没有所选工单。"','unknown unit explicitly identified');
  for (const version of [9,10]) {
    await call('Page.navigate',{url:fixed(root,version,'d01')});
    await wait('state.bundle?.rev==='+version+' && document.activeElement.textContent.includes("本版未收录")','earlier issued edition');
    assert.equal(await evaluate(q(card)),null);
  }
  console.log('PASS · R9/R10/R11 work-order evidence, phase vs payment, two pinned work orders, focus, dual originals, '+mutations.length+' evidence mutations and six widths');
}
