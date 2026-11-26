import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {inspect,size} from './review-screen.mjs';

const q=selector=>'document.querySelector('+JSON.stringify(selector)+')';
const all=selector=>'[...document.querySelectorAll('+JSON.stringify(selector)+')]';
const dialog='#performance-index', pageDialog='#page-dialog', opener='[data-audit-scope="contract"]';
const labels={
  typeset:'仅见排印文字，未检出嵌入式电子签名',visual:'含影像、图形或批注，签章痕迹待核',
  current:'电子签名覆盖本版，签署人身份及权限待核',earlier:'电子签名仅覆盖较早版本',
  mismatch:'电子签名与所签内容校验不符',review:'委托书签章凭证待核'
};

// Each change is made to a fresh browser-local copy of the issued report.
function brokenBindings(findingId,id) {
  const changes={
    policy:b=>delete b.report.policy.mandate_pdf,
    ledger:b=>b.graph.mandate_pdf_sources.format='other',
    declaration:b=>delete b.entry.mandate_execution,
    entryOk:b=>b.entry.status='ok',
    findingOk:b=>{b.finding.status='ok'; b.graph.nodes.find(n=>n.id==='finding/'+findingId).status='ok';},
    unit:b=>b.entry.units=[],
    scope:b=>b.finding.scope=b.finding.scope.filter(u=>u!==b.record.unit),
    role:b=>b.graph.documents_by_kind.power_of_attorney=[],
    record:b=>b.graph.mandate_pdf_sources.records.push({...b.record}),
    state:b=>b.node.state='unknown',
    digest:b=>b.record.original_sha256='stale',
    page:b=>b.record.pages[0].sha256='stale',
    layer:b=>b.record.pages[0].typeset=null,
    signatures:b=>b.record.signatures=[{state:'current'}],
    physicalPage:b=>b.graph.nodes.find(n=>n.id===b.record.pages[0].ref).sha256='stale',
    issuedPage:b=>b.report.calls.pages.find(p=>p.doc===b.record.doc && b.record.doc+'/p'+p.page===b.record.pages[0].ref).page_sha256='stale',
    source:b=>b.edge.from='another unit',
    sourceEvidence:b=>b.edge.evidence=b.edge.evidence.slice(1),
    findingNode:b=>b.graph.nodes.find(n=>n.id==='finding/'+findingId).detail='another finding',
  };
  const issued=state.bundle.report, original=issued.graph.mandate_pdf_sources.records.find(r=>r.id===id);
  for (const ref of [id,original.doc,...original.pages.map(p=>p.ref),...original.fields]) {
    changes['entry '+ref]=b=>b.entry.evidence=b.entry.evidence.filter(r=>r!==ref);
    changes['finding '+ref]=b=>b.finding.evidence=b.finding.evidence.filter(r=>r!==ref);
    changes['support '+ref]=b=>b.graph.edges.find(e=>e.type==='supports_result' && e.to==='finding/'+findingId && e.from===ref).evidence=[];
  }
  if (original.fields.length) {
    changes.field=b=>b.graph.facts.find(f=>f.id===original.fields[0]).field='buyer_signature';
    changes.fieldPage=b=>b.graph.facts.find(f=>f.id===original.fields[0]).page_sha256='stale';
    changes.fieldLink=b=>b.graph.edges=b.graph.edges.filter(e=>!(e.type==='records' && e.to===original.fields[0]));
    changes.omittedFields=b=>{b.record.fields=[]; b.edge.evidence=b.edge.evidence.filter(r=>!original.fields.includes(r));};
  }
  if (['current','earlier','mismatch'].includes(original.state)) {
    const signed=b=>b.record.signatures.find(s=>s.state===original.state);
    changes.certificate=b=>delete signed(b).certificate_sha256;
    changes.byteRange=b=>signed(b).ends_at=0;
    changes.coverage=b=>signed(b).coverage='PARTIAL';
  }
  const failures=[];
  for (const [name,change] of Object.entries(changes)) {
    const report=structuredClone(issued), graph=report.graph;
    const finding=report.findings.find(f=>f.id===findingId), entry=finding.delegations.find(e=>e.mandate_execution?.includes(id));
    const record=graph.mandate_pdf_sources.records.find(r=>r.id===id), node=graph.nodes.find(n=>n.id===id);
    const edge=graph.edges.find(e=>e.type==='mandate_pdf_source' && e.to===id);
    change({report,graph,finding,entry,record,node,edge});
    if (PerformanceIndex.mandateEvidence(finding,report).some(m=>m.proofs.some(p=>p.record.id===id)) ||
        PerformanceIndex.mandateCitation(report,id).matches('button')) failures.push(name);
  }
  return {count:Object.keys(changes).length,failures};
}

function mismatchStatuses(findingId,id) {
  const report=structuredClone(state.bundle.report), graph=report.graph;
  const finding=report.findings.find(f=>f.id===findingId), entry=finding.delegations.find(e=>e.mandate_execution?.includes(id));
  const record=graph.mandate_pdf_sources.records.find(r=>r.id===id);
  const signature=record.signatures.find(s=>s.state===record.state);
  signature.state=record.state=graph.nodes.find(n=>n.id===id).state='mismatch';
  const accepted=[], node=graph.nodes.find(n=>n.id==='finding/'+findingId);
  for (const parent of ['ok','missing','risk','issue']) {
    finding.status=node.status=parent;
    for (const child of ['ok','missing','risk','issue']) {
      entry.status=child;
      if (PerformanceIndex.mandateCitation(report,id).matches('button')) accepted.push([parent,child]);
    }
  }
  return accepted;
}

function brokenScopeLinks(findingId,ref) {
  const issued=state.bundle, failures=[];
  function show(bundle) {
    document.querySelector('#performance-index').close();
    state.bundle=bundle; renderCase(true);
    const opener=document.querySelector('[data-audit-scope="contract"]'); opener.focus(); opener.click();
  }
  const changes={
    'permission edge':b=>b.graph.edges=b.graph.edges.filter(e=>e!==b.edge),
    'crossed unit':b=>b.fact.unit=b.graph.documents_by_kind.contract[0],
    'crossed edge':b=>b.edge.from=b.graph.documents_by_kind.contract[0],
    'uncited scope':b=>b.entry.evidence=b.entry.evidence.filter(r=>r!==ref),
    'finding citation':b=>b.finding.evidence=b.finding.evidence.filter(r=>r!==ref),
    'result edge':b=>b.graph.edges.find(e=>e.type==='supports_result' && e.from===ref && e.to==='finding/'+findingId).evidence=[],
    'field location':b=>b.fact.source_line.rects=[],
    'different permission':b=>b.graph.nodes.find(n=>n.id===b.edge.to).label='可以签约',
  };
  try {
    for (const [name,change] of Object.entries(changes)) {
      const bundle=structuredClone(issued), {report}=bundle, graph=report.graph;
      const finding=report.findings.find(f=>f.id===findingId), entry=finding.delegations.find(e=>e.evidence.includes(ref));
      const fact=graph.facts.find(f=>f.id===ref), edge=graph.edges.find(e=>e.type==='grant_scope' && e.evidence.includes(ref));
      change({fact,edge,graph,entry,finding});
      const model=PerformanceIndex.mandateEvidence(finding,report).find(m=>m.entry===entry);
      if (!model || model.scope) failures.push(name);
      if (name==='permission edge' || name==='crossed unit') {
        show(bundle);
        const panel=document.querySelector('#performance-index');
        if (panel.querySelector('[data-mandate-scope]') || !panel.querySelector('[data-pdf-mandate]')) failures.push(name+' in dialog');
      }
    }
  } finally {show(issued);}
  return failures;
}

export async function checkMandatePdf(ctx,id,requested,expected) {
  const {root,call,evaluate,wait}=ctx, api=root+'/api/cases/'+id;
  const task=await (await fetch(api)).json();
  assert.match(task.title,/^合成演练/u);
  const rev=Number(requested ?? task.rev), legacy=expected==='legacy';
  assert.ok(Number.isSafeInteger(rev) && rev>0);
  assert.ok(!expected || legacy || Object.hasOwn(labels,expected),'--expect must name an issued PDF state or legacy');
  const response=await fetch(api+'/reports/'+rev);
  assert.equal(response.status,200);
  const bundle=await response.json(), {report}=bundle, {graph}=report;
  assert.equal(bundle.rev,rev);
  const finding=report.findings.find(f=>f.rule==='H01' && f.delegations?.length);
  assert.ok(finding,'a delegation in the pinned H01');
  const proofs=finding.delegations.flatMap(entry=>(entry.mandate_execution || []).map(ref=>{
    const record=graph.mandate_pdf_sources?.records.find(r=>r.id===ref);
    assert.ok(record && Object.hasOwn(labels,record.state));
    return {entry,record};
  }));
  if (legacy) {
    assert.equal(report.policy.mandate_pdf,undefined); assert.equal(proofs.length,0);
  } else {
    assert.equal(report.policy.mandate_pdf,'pdf-mandate-execution-v1');
    assert.ok(proofs.length && (!expected || proofs.some(p=>p.record.state===expected)),'expected an issued '+(expected || 'mandate')+' proof');
  }
  const prefix='mandate-'+id+'-r'+rev+'-'+(legacy?'legacy':proofs.map(p=>p.record.state).join('-'));
  const key=async name=>{
    const codes={Escape:27,Enter:13,Tab:9,Space:32};
    for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key:name==='Space'?' ':name,
      code:name,windowsVirtualKeyCode:codes[name],...(type==='keyDown' && name==='Enter'?{text:'\r'}:{})});
  };
  async function pointAt(control) {
    return evaluate('(()=>{const el='+control+';el.scrollIntoView({block:"nearest",behavior:"instant"});'+
      'const r=el.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()');
  }
  async function tap(control) {
    const point=await pointAt(control);
    await call('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[point]});
    await call('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  }
  const checked=new Set();
  async function verifyBytes(url,sha) {
    if (checked.has(url)) return;
    const result=await fetch(url);
    assert.equal(result.status,200);
    assert.equal(createHash('sha256').update(Buffer.from(await result.arrayBuffer())).digest('hex'),sha);
    checked.add(url);
  }
  async function openOriginal(trigger,doc,page,field,width,shot) {
    if (width===390) await tap(trigger);
    else {await evaluate(trigger+'.focus()'); await key('Enter');}
    await wait(q(pageDialog)+'?.open && '+q('.source-tools a')+'?.pathname.endsWith('+JSON.stringify('/documents/'+doc+'/pages/'+page)+')','correct physical mandate page');
    await wait(q('#page-dialog .page-image')+'?.naturalWidth>0','original image decoded');
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    if (field) {
      assert.equal(await evaluate(q('#page-dialog .located')+'?.dataset.fact'),field);
      const rects=graph.facts.find(f=>f.id===field).source_line?.rects;
      if (rects?.length) {
        const marked=await evaluate(all('#page-dialog .source-plane > svg:first-of-type rect')+'.map(r=>["x","y","width","height"].map(k=>Number(r.getAttribute(k))))');
        assert.deepEqual(marked,rects.map(([l,t,r,b])=>[l*1000,t*1000,(r-l)*1000,(b-t)*1000]));
      }
    }
    const href=await evaluate(q('.source-tools a')+'.href');
    assert.equal(href,api+'/documents/'+doc+'/pages/'+page+'?rev='+rev);
    await verifyBytes(href,graph.nodes.find(n=>n.id===doc+'/p'+page).sha256);
    await verifyBytes(api+'/documents/'+doc+'/original?rev='+rev,graph.documents.find(d=>d.id===doc).sha256);
    if (shot) await inspect(ctx,width,pageDialog,prefix+'-'+(shot===true?'original':shot));
    await key('Escape');
    await wait('!'+q(pageDialog)+'.open && '+q(dialog)+'.open && document.activeElement==='+trigger,'Escape restores the same source button');
  }
  const grantUnits=new Set(finding.delegations.flatMap(entry=>entry.units));
  const oldFields=graph.facts.filter(f=>grantUnits.has(f.unit || f.doc) && finding.evidence.includes(f.id));
  const oldField=oldFields.find(f=>f.field==='grant_signature') || oldFields[0];
  const locationsFor=record=>record.fields.length?record.fields.map(ref=>graph.facts.find(f=>f.id===ref)):
    record.pages.map(p=>({doc:record.doc,page:Number(p.ref.split('/p').pop())}));
  async function oldOriginal(width,shot) {
    assert.ok(oldField,'the older field citation is available');
    const select=q(dialog+' .scope-source-head select'), button=q(dialog+' .scope-open-original');
    if (!await evaluate(button+'?.checkVisibility()')) {
      await evaluate(all(dialog+' .scope-detail > details > summary')+'.find(s=>s.textContent==="其他字段引文").click()');
    }
    await wait(button+'?.checkVisibility()','original field chooser');
    if (await evaluate(select+'!=null')) {
      const option=await evaluate('PerformanceIndex.originals(state.bundle.report.findings.find(f=>f.id==='+JSON.stringify(finding.id)+'),state.bundle.report.graph).findIndex(r=>r.fact.id==='+JSON.stringify(oldField.id)+')');
      assert.ok(option>=0);
      await evaluate(select+'.value='+JSON.stringify(String(option))+';'+select+'.dispatchEvent(new Event("change"))');
    }
    assert.equal(await evaluate(button+'.dataset.fact'),oldField.id);
    await openOriginal(button,oldField.doc,oldField.page,oldField.id,width,shot);
  }
  const visibleProofs=dialog+' .scope-mandate-record', records=all(visibleProofs);
  await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev='+rev+'&view=contract-checks'});
  await wait(q(dialog)+'?.open && state.bundle.rev==='+rev+' && '+q('#scope-title')+'.textContent==="签署与生效"','pinned signing checks');
  assert.equal(await evaluate(q('.scope-check-select')+'.value'),finding.id);
  let degraded=0;
  const scopeRefs=new Set();
  for (const width of [390,1440]) {
    await size(ctx,width);
    await call('Emulation.setTouchEmulationEnabled',{enabled:width===390});
    assert.equal(await evaluate(q('.scope-check-state .tag')+'.dataset.state'),finding.status);
    assert.deepEqual(await evaluate(records+'.map(r=>r.dataset.state)'),proofs.map(p=>p.record.state));
    await inspect(ctx,width,dialog,prefix+'-checks');
    if (legacy) await oldOriginal(width,true);
    for (const [index,{entry,record}] of proofs.entries()) {
      const row=records+'['+index+']', card=row+'.closest(".scope-mandate-proof")';
      assert.equal(await evaluate(row+'.querySelector("strong").innerText'),labels[record.state]);
      assert.equal(await evaluate(card+'.querySelector(".tag").dataset.state'),entry.status);
      const note=await evaluate(card+'.querySelector(".scope-mandate-note > span")?.innerText');
      assert.ok(!note || entry.detail.includes(note),'verbatim issued authorization reason');
      assert.ok(await evaluate(card+'.querySelectorAll(".scope-mandate-note").length<=1'));
      if (entry.detail.startsWith('委托书 PDF 仅见排印内容')) {
        assert.equal(note,'请核对被代理人签名或盖章的原件或对应签署记录。');
      } else if (entry.detail.includes('还有待核的限制')) {
        assert.match(note,/还有待核的限制/u);
      }
      if (entry.detail.includes('仅限收货验收')) {
        assert.equal(entry.status,'risk'); assert.match(note,/仅限收货验收/u);
      }
      const locations=locationsFor(record);
      const buttons=row+'.querySelectorAll("[data-pdf-mandate]")';
      assert.equal(await evaluate(buttons+'.length'),locations.length);
      for (const [i,location] of locations.entries()) {
        const button=buttons+'['+i+']';
        assert.equal(await evaluate(button+'.dataset.pdfMandate'),record.id);
        assert.ok(await evaluate(button+'.getBoundingClientRect().height>=44 && '+card+'.scrollWidth<='+card+'.clientWidth+1'));
        if (!index && !i) {
          assert.ok(await evaluate(button+'.getBoundingClientRect().bottom<='+q(dialog)+'.getBoundingClientRect().bottom'),'first source in view at '+width);
          await evaluate(q(dialog+' .scope-head .icon-button')+'.focus()');
          for (let n=0;n<40 && !await evaluate('document.activeElement==='+button);n++) await key('Tab');
          assert.ok(await evaluate('document.activeElement==='+button),'source reachable with Tab');
        }
        await openOriginal(button,record.doc,location.page,location.id,width,!index && !i);
      }
      const scope=card+'.querySelector("[data-mandate-scope]")';
      const conflict=/权限不足以支持代理签约|需另核签约授权/u.test(entry.detail);
      const field=graph.facts.find(f=>f.field==='grant_scope' && (f.unit || f.doc)===record.unit && entry.evidence.includes(f.id) && f.source_line?.rects?.length);
      if (conflict && field && ['risk','issue'].includes(entry.status)) {
        assert.equal(await evaluate(scope+'?.dataset.mandateScope'),field.id);
        assert.equal(await evaluate(scope+'.textContent'),'查看权限原行');
        if (id==='47967684163c47b094313f8632ec397a' && rev===6) {
          assert.deepEqual([field.id,field.source_line.number,locations[0].id,locations[0].source_line.number],['d01/p1/f9',10,'d01/p1/f13',14]);
        }
        assert.ok((await evaluate(scope+'.title')).endsWith('第 '+field.source_line.number+' 行'));
        await openOriginal(scope,field.doc,field.page,field.id,width,'scope-line'); scopeRefs.add(field.id);
      } else {
        assert.equal(await evaluate(scope),null);
      }
      if (['current','earlier','mismatch'].includes(record.state)) {
        const summary=row+'.querySelector("summary")';
        if (width===390) await tap(summary);
        else {await evaluate(summary+'.focus()'); await key('Space');}
        await wait(row+'.querySelector(".pdf-timeline")?.dataset.state==='+JSON.stringify(record.state),'issued signature range');
        await inspect(ctx,width,dialog,prefix+'-range');
        await evaluate(row+'.querySelector(".pdf-technical summary").click()');
        const signature=record.signatures.find(s=>s.state===record.state);
        const technical=await evaluate(row+'.querySelector(".pdf-technical").innerText');
        assert.ok(technical.includes(record.original_sha256) && technical.includes(signature.certificate_sha256));
        if (record.state==='earlier') assert.match(await evaluate(row+'.innerText'),/签后追加 [\d,]+ 字节/u);
        assert.ok(await evaluate(card+'.scrollWidth<='+card+'.clientWidth+1'),'expanded detail at '+width);
        await evaluate(row+'.querySelector(".pdf-technical summary").click();'+summary+'.focus()'); await key('Enter');
      }
    }
    await key('Escape');
    await wait('!'+q(dialog)+'.open && document.activeElement==='+q(opener),'Escape returns to the signing check');
    await key('Enter'); await wait(q(dialog)+'.open','reopen with the keyboard');
  }
  if (proofs.length) {
    const targets=proofs.flatMap(({record})=>locationsFor(record)).map((location,i)=>({
      location,control:all(dialog+' [data-pdf-mandate]')+'['+i+']'
    }));
    for (const ref of scopeRefs) targets.push({location:graph.facts.find(f=>f.id===ref),control:q(dialog+' [data-mandate-scope="'+ref+'"]')});
    for (const width of [320,360,768,1024]) {
      await size(ctx,width);
      await call('Emulation.setTouchEmulationEnabled',{enabled:width<600});
      await evaluate(q(dialog)+'.scrollTop=0');
      assert.ok(await evaluate(all(dialog+', '+dialog+' .scope-mandate-proof, '+dialog+' .scope-mandate-record')+
        '.every(el=>el.scrollWidth<=el.clientWidth+1)'),'card overflow at '+width);
      assert.ok(await evaluate(targets[0].control+'.getBoundingClientRect().bottom<='+q(dialog)+'.getBoundingClientRect().bottom'));
      for (const {control,location} of targets) {
        const point=await pointAt(control);
        assert.ok(await evaluate(control+'.checkVisibility() && '+control+'.getBoundingClientRect().height>=44 && '+
          control+'.contains(document.elementFromPoint('+point.x+','+point.y+'))'),'source hit target at '+width);
        if (width<600) await tap(control);
        else for (const type of ['mousePressed','mouseReleased']) await call('Input.dispatchMouseEvent',{type,...point,button:'left',clickCount:1});
        const href=api+'/documents/'+location.doc+'/pages/'+location.page+'?rev='+rev;
        await wait(q(pageDialog)+'?.open && '+q('.source-tools a')+'?.href==='+JSON.stringify(href),'source opens at '+width);
        if (location.id) assert.equal(await evaluate(q('#page-dialog .located')+'?.dataset.fact'),location.id);
        await evaluate(q('#page-dialog [data-close]')+'.click()');
      }
    }
  }
  for (const {record} of proofs) {
    const result=await evaluate('('+brokenBindings.toString()+')('+JSON.stringify(finding.id)+','+JSON.stringify(record.id)+')');
    assert.deepEqual(result.failures,[]); degraded+=result.count;
    if (['current','earlier','mismatch'].includes(record.state)) {
      const combinations=await evaluate('('+mismatchStatuses.toString()+')('+JSON.stringify(finding.id)+','+JSON.stringify(record.id)+')');
      assert.deepEqual(combinations,[['risk','risk'],['risk','issue'],['issue','risk'],['issue','issue']]);
    }
  }
  for (const ref of scopeRefs) {
    assert.deepEqual(await evaluate('('+brokenScopeLinks.toString()+')('+JSON.stringify(finding.id)+','+JSON.stringify(ref)+')'),[]);
  }
  const contractJump=q(dialog+' [aria-controls="pdf-signatures"]');
  if (await evaluate(q('#pdf-signatures')+'!==null')) {
    assert.equal(await evaluate(contractJump+'?.textContent'),'查看合同签署凭证');
    await evaluate(contractJump+'.focus()'); await key('Enter');
    await wait('!'+q(dialog)+'.open && document.activeElement==='+q('#pdf-signatures'),'open the contract signature evidence');
    await evaluate(q(opener)+'.focus()'); await key('Enter');
  }
  if (!legacy) {
    // Re-render through the workpaper with the inspection edge removed, then exercise the old path.
    await evaluate(q(dialog)+'.close();state.bundle=structuredClone(state.bundle);'+
      'state.bundle.report.graph.edges=state.bundle.report.graph.edges.filter(e=>e.type!=="mandate_pdf_source");'+
      'renderCase(true);'+q(opener)+'.focus();'+q(opener)+'.click()');
    assert.equal(await evaluate(records+'.length'),0);
    if (oldField) await oldOriginal(1440,false);
    else assert.ok(await evaluate(q(dialog+' .scope-open-original')+'?.checkVisibility()'));
  }
  console.log('PASS · '+id+' R'+rev+' · '+(legacy?'legacy':proofs.map(p=>p.record.state).join('/'))+
    ' · H01 '+finding.status+' · 390/1440 · pinned originals, keyboard, Escape · '+degraded+' broken bindings'+
    (proofs.length?' · layout and hit tests at 320/360/768/1024':'')+(scopeRefs.size?' · grant scope and 8 broken scope links':''));
}
