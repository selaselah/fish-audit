// Read-only browser regression against an explicitly pinned synthetic report.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {accessibility, browserInput, inspect, size} from './review-screen.mjs';

const fixtures = {
  '7e3e44b82d394ed4a9324a0d3be0f8b7': {name:'strict',old:14,states:['original','applied'],limit:2,basis:4,reading:3},
  '99691f53404647d28c625ce6f3390f19': {name:'relaxed',old:12,states:['original','applied'],limit:8,basis:8,reading:6},
  'd51a9a3c8856414fa1de558cc2fd49e4': {name:'same-day',old:15,states:['original','pending'],limit:8,basis:8,reading:6},
  '12d553b8578840c6b07149b3982f077b': {name:'broken-date',old:9,states:['pending','pending'],limit:8,basis:8,reading:6},
};
const q = s => 'document.querySelector(' + JSON.stringify(s) + ')';
const all = s => '[...document.querySelectorAll(' + JSON.stringify(s) + ')]';
const modal = '#performance-index', proof = modal+' .batch-phase-proof', card = proof+' .batch-standard';
const field = key => card+' [data-standard-field="'+key+'"]';
const mode = key => proof+' [data-source="'+key+'"]';
const printed = fact => fact.source_line.text.replace(/^[^:：]+[:：]\s*/u,'').trim();
const unit = fact => fact.unit || fact.doc;

function expected(report,phase) {
  const h2=report.findings.find(f=>f.rule==='H02'), ledger=h2.batch_acceptance;
  const batch=ledger.batches.find(b=>b.index===phase.stage.batch_index);
  assert.equal(batch.records.length,1);
  const row=ledger.records.find(r=>r.unit===batch.records[0] && r.index===batch.index);
  const st=row.standard, facts=report.graph.facts.filter(f=>st.evidence.includes(f.id));
  const pick=(kind,owner)=>facts.find(f=>f.field===kind && (!owner || unit(f)===owner));
  const byRef=id=>facts.find(f=>f.id===id);
  return {batch,row,st,original:pick('acceptance_criteria'),revised:pick('revised_criterion',h2.quality_change.units[0]),
    criterion:byRef(st.criterion_ref),basis:pick('inspection_basis',row.unit),reading:byRef(st.reading_ref),date:byRef(st.date_ref),
    buyer:pick('buyer_sealed_on'),seller:pick('seller_sealed_on')};
}

// Run each change on its own copy in Chrome. The original service receives only GETs.
function altered(phaseId) {
  const results={};
  for (const change of ['baseline','comparison-missing','comparison-owner','comparison-version','comparison-evidence',
    'criterion-ref','foreign-reading','foreign-basis','foreign-date','foreign-scope','duplicate-owner','stage-clause',
    'receipt-text','change-identity','criterion-node','typed-edge','h04-edge','h02-edge','page-edge','page-hash',
    'receipt-day','stamp-line','stamp-value','effective-day','unselected','permuted','duplicate','duplicate-list',
    'stamp-owner','stamp-page','stamp-rect','stamp-h04','stamp-h02','raw-target','legacy-h02','legacy-graph','joined-day',
    'h02-scope-shape','missing-type-index']) {
    const report=structuredClone(state.bundle.report), {graph,findings}=report;
    const phase=findings.find(f=>f.id===phaseId), h=findings.find(f=>f.rule==='H02'), ledger=h.batch_acceptance;
    const batch=ledger.batches.find(b=>b.index===phase.stage.batch_index), row=ledger.records.find(r=>r.unit===batch.records[0]);
    const other=ledger.records.find(r=>r.index!==row.index && r.standard), st=row.standard;
    const fact=(field,owner)=>graph.facts.find(f=>f.field===field && (f.unit || f.doc)===owner);
    const basis=fact('inspection_basis',row.unit), reading=fact('measured_result',row.unit);
    const amended=fact('revised_criterion',h.quality_change.units[0]);
    const stamp=fact('seller_sealed_on',h.quality_change.units[0]);
    const cmp=graph.edges.find(e=>e.type==='batch_quality_comparison' && e.to===reading.id);
    const typed=f=>graph.edges.find(e=>e.type===f.field && e.evidence.includes(f.id));
    function drop(edge) { graph.edges=graph.edges.filter(e=>e!==edge); }
    switch (change) {
      case 'comparison-missing': drop(cmp); break;
      case 'comparison-owner': if (cmp) cmp.batch=other.index; break;
      case 'comparison-version': if (cmp) cmp.version='pending'; break;
      case 'comparison-evidence': if (cmp) cmp.evidence=cmp.evidence.filter(id=>id!==basis.id); break;
      case 'permuted': if (cmp) cmp.evidence=[...cmp.evidence].reverse(); break;
      case 'duplicate': if (cmp) cmp.evidence=[...cmp.evidence.slice(0,-1),cmp.evidence[0]]; break;
      case 'duplicate-list': if (cmp) cmp.evidence=[...cmp.evidence,cmp.evidence[0]]; break;
      case 'criterion-ref': st.criterion_ref=other.standard.reading_ref; break;
      case 'foreign-reading': st.reading_ref=other.standard.reading_ref; break;
      case 'foreign-basis': st.evidence=st.evidence.map(id=>id===basis.id?fact('inspection_basis',other.unit).id:id); break;
      case 'foreign-date': st.date_ref=other.standard.date_ref; break;
      case 'foreign-scope': row.scope_ref=other.scope_ref; break;
      case 'duplicate-owner': ledger.batches.find(b=>b.index===other.index).records.push(row.unit); break;
      case 'stage-clause': phase.stage.clause_ref=ledger.batches.find(b=>b.index===other.index).clause_ref; break;
      case 'receipt-text': basis.source_line.text=basis.quote.replace(/[248]/u,'9'); break;
      case 'change-identity': drop(typed(fact('base_contract_ref',h.quality_change.units[0]))); break;
      case 'criterion-node': graph.nodes.find(n=>n.id===typed(amended).to).label='柜温不高于11℃'; break;
      case 'typed-edge': typed(reading).from=other.unit; break;
      case 'h04-edge': case 'h02-edge':
        drop(graph.edges.find(e=>e.type==='supports_result' && e.from===basis.id && e.to==='finding/'+(change==='h04-edge'?phase.id:h.id))); break;
      case 'page-edge': drop(graph.edges.find(e=>e.type==='records' && e.to===reading.id)); break;
      case 'page-hash': report.calls.pages.find(p=>p.doc===reading.doc && p.page===reading.page).page_sha256='stale'; break;
      case 'receipt-day': row.date='2026-01-01'; break;
      case 'stamp-line': stamp.source_line.text='乙方盖章日期：2026年9月1 2日'; break;
      case 'stamp-value': stamp.value='2026年9月1日'; break;
      case 'stamp-owner': typed(stamp).from=row.unit; break;
      case 'stamp-page': drop(graph.edges.find(e=>e.type==='contains' && e.to===stamp.doc+'/p'+stamp.page)); break;
      case 'stamp-rect': stamp.source_line.rects=[]; break;
      case 'stamp-h04': case 'stamp-h02':
        drop(graph.edges.find(e=>e.type==='supports_result' && e.from===stamp.id && e.to==='finding/'+(change==='stamp-h04'?phase.id:h.id))); break;
      case 'raw-target': typed(reading).to=reading.id; break;
      case 'h02-scope-shape': h.scope={}; break;
      case 'missing-type-index': delete graph.documents_by_kind; break;
      case 'legacy-graph': delete report.calls.pages; break;
      case 'legacy-h02': for (const r of ledger.records) delete r.standard; break;
      case 'joined-day':
        if (!stamp.source_line.text.includes('1 2')) continue;
        Object.assign(h.quality_change,{state:'by_batch',scope_clear:true,effective_on:'2026-09-12',seller_sealed_on:'2026-09-12'});
        Object.assign(st,{state:'applied',effective_on:'2026-09-12',criterion:amended.value,criterion_ref:amended.id});
        graph.edges.push({type:'batch_quality_comparison',from:amended.id,to:reading.id,batch:batch.index,version:'applied',evidence:[...st.evidence]});
        break;
      case 'effective-day': st.effective_on='2026-01-01'; break;
      case 'unselected': st.state='pending'; st.criterion_ref=amended.id; break;
    }
    const p=BatchPhase.resolve(phase,h,graph,report.calls.pages), m=p?.standard;
    const panel=BatchPhase.panel(p,phase.stage);
    const pairs=EvidenceCompare.presets(h,PerformanceIndex.originals(h,graph).map(s=>s.fact),graph,change==='legacy-graph'?undefined:report);
    const pair=pairs.find(s=>s.key==='batch-'+batch.index), raw=pairs.find(s=>s.key==='receipt-batch-'+batch.index);
    results[change]={chosen:m?.chosen?.id || null, fieldNames:[...panel.querySelectorAll('[data-standard-field]')].map(b=>b.dataset.standardField),
      pair:pair?.version || null, receipt:raw?[raw.left.id,raw.right.id]:null, status:p.status};
  }
  return results;
}

export async function checkBatchStandard(ctx,id,rev,compareRev) {
  const {root,call,wait,evaluate}=ctx, api=root+'/api/cases/'+id, fixture=fixtures[id];
  assert.ok(Number.isInteger(rev) && rev>0,'supply the issued --rev');
  const task=await (await fetch(api)).json();
  assert.match(task.title,/^合成演练/u);
  const {key,tap,pointAt}=browserInput(ctx), pageHashes=new Set();
  async function load(revision) {
    const response=await fetch(api+'/reports/'+revision);
    assert.equal(response.status,200);
    const bundle=await response.json();
    assert.equal(bundle.rev,revision);
    return bundle.report;
  }
  async function stage(phase,revision,navigate=true,hasStandard=true) {
    if (navigate) await call('Page.navigate',{url:root+'/workpaper/'+id+'?rev='+revision+'&view=payment-checks&stage='+phase.id});
    else {
      if (!await evaluate(q(modal)+'.open')) await evaluate(q('[data-audit-scope=payment]')+'.click()');
      if (!await evaluate(q('.scope-checks [data-check="'+phase.id+'"]')+'!==null'))
        await evaluate(q('.scope-filters button:last-child')+'.click()');
      await evaluate('(()=>{const s='+q('.scope-check-select')+';s.value='+JSON.stringify(phase.id)+';s.dispatchEvent(new Event("change"));})()');
    }
    await wait(q(modal)+'?.open && '+q('.scope-check-select')+'?.value==='+JSON.stringify(phase.id)+' && '+
      (hasStandard?q(card)+'?.checkVisibility()':q(proof)+'!==null'),'R'+revision+' '+phase.id+' batch');
  }
  async function widthFits(width,selector) {
    const dims=await evaluate('(()=>{const e='+q(selector)+',r=e.getBoundingClientRect();return [document.documentElement.scrollWidth,r.left,r.right,e.scrollWidth-e.clientWidth]})()');
    assert.ok(dims[0]<=width+1 && dims[1]>=-1 && dims[2]<=width+1 && dims[3]<=1,selector+' at '+width+'px '+JSON.stringify(dims));
  }
  async function activate(selector,how) {
    if (how==='keyboard') { await evaluate(q(selector)+'.focus()'); await key('Enter'); return; }
    if (how==='touch') return tap(q(selector));
    const p=await pointAt(q(selector));
    await call('Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',clickCount:1});
    await call('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button:'left',clickCount:1});
  }
  async function original(selector,f,revision,width,how='keyboard',raw=false,insideChecks=true) {
    await activate(selector,how);
    const url=api+'/documents/'+f.doc+'/pages/'+f.page+'?rev='+revision;
    const location=raw?'?.dataset.sourceRef==='+JSON.stringify(f.id+'/l'+f.source_line.number):'?.dataset.fact==='+JSON.stringify(f.id);
    await wait(q('#page-dialog')+'.open && '+q('.evidence-row.located')+location+
      ' && '+q('.source-tools > a')+'?.href==='+JSON.stringify(url)+' && '+q('.page-image')+'?.naturalWidth>0','fixed original '+f.id+' R'+revision);
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+revision);
    assert.equal(await evaluate(q('.evidence-row.located blockquote')+'.textContent'),raw?f.source_line.text:f.quote);
    if (raw) {
      assert.match(await evaluate(q('.evidence-row.located h4')+'.textContent'),/待核.*第 14 行/u);
      assert.equal(await evaluate(q('.evidence-row.located')+'.dataset.gapLine'),String(f.source_line.number));
      const rects=await evaluate(all('.source-plane > svg:first-of-type > rect')+'.map(r=>["x","y","width","height"].map(k=>Number(r.getAttribute(k))))');
      assert.deepEqual(rects,f.source_line.rects.map(([l,t,r,b])=>[l*1000,t*1000,(r-l)*1000,(b-t)*1000]));
      if (fixture?.name==='broken-date' && revision===fixture.old && width===390)
        await inspect(ctx,width,'#page-dialog .evidence-row.located','broken-date-r'+rev+'-printed');
    }
    if (!pageHashes.has(url)) {
      assert.equal(createHash('sha256').update(Buffer.from(await (await fetch(url)).arrayBuffer())).digest('hex'),f.page_sha256);
      pageHashes.add(url);
    }
    await widthFits(width,'#page-dialog');
    await key('Escape');
    await wait((insideChecks?q(modal)+'.open && ':'')+'!'+q('#page-dialog')+'.open && document.activeElement==='+q(selector),'focus back on '+selector);
  }
  function assertIssued(report,phase,e,revision) {
    if (!fixture || ![fixture.old,fixture.old+1].includes(revision)) return;
    const {batch,st}=e, second=batch.index===2, current=revision===fixture.old+1;
    assert.equal(st.state,current?'pending':fixture.states[batch.index-1]);
    const degrees=f=>Number(printed(f).match(/\d+/u)?.[0]);
    assert.deepEqual([e.original,e.revised,e.basis,e.reading].map(degrees),[4,fixture.limit,second?fixture.basis:4,second?fixture.reading:3]);
    if (current) {
      assert.equal(st.criterion_ref,null);
      assert.equal(report.findings.find(f=>f.rule==='H02').quality_change.effective_on,null);
      assert.equal(phase.status,'missing');
      assert.deepEqual(report.findings.filter(f=>f.rule==='H04').map(f=>f.status),Array(4).fill('missing'));
    }
    if (!current && second && fixture.name==='strict') {
      assert.equal(batch.date,null);
      assert.deepEqual([e.criterion,e.basis,e.reading,e.date].map(f=>[f.id,f.source_line.number]),
        [['d05/p1/f9',10],['d02/p1/f10',11],['d02/p1/f11',12],['d02/p1/f6',7]]);
    }
  }
  async function checkCard(e) {
    const state=e.st.state;
    assert.equal(await evaluate(q(card)+'.dataset.version'),state);
    assert.equal(await evaluate(q(mode('standard'))+'.getAttribute("aria-pressed")'),'true');
    assert.equal(await evaluate(q(proof+' .tag')+'.dataset.state'),e.batch.status);
    const expectedKeys=state==='pending'?['original','revised','basis','reading']:['criterion','basis','reading'];
    const fields=await evaluate(all(card+' [data-standard-field]')+'.filter(b=>b.checkVisibility()).map(b=>[b.dataset.standardField,b.dataset.fact,b.querySelector("strong").textContent,b.querySelector("span").textContent,b.getBoundingClientRect().height])');
    assert.deepEqual(fields.map(f=>f[0]),expectedKeys);
    for (const [key,id,text,place,height] of fields) {
      const f=e[key];
      assert.equal(id,f.id); assert.equal(text,printed(f));
      assert.equal(place,'第 '+f.page+' 页 · 第 '+f.source_line.number+' 行');
      assert.ok(height>=44,key+' target height '+height);
    }
    assert.equal(await evaluate(q(field('criterion'))+'!==null'),state!=='pending');
    const labels=await evaluate(all(card+' em')+'.filter(e=>e.checkVisibility()).map(e=>e.textContent)');
    assert.deepEqual(labels,fixture?.name==='strict' && state==='applied'?['仍引原标准','超出限值']:[]);
    return expectedKeys;
  }
  async function graphPair(phase,e) {
    await key('Escape'); await wait('!'+q(modal)+'.open','close payment checks');
    const tab=q('[data-phase-choice="'+phase.id+'"]');
    await evaluate('revealPaperTarget('+tab+');'+tab+'.click()');
    const row='[data-phase-finding="'+phase.id+'"]';
    const sameDay=e.st.state==='pending' && e.st.effective_on!==null && e.st.effective_on===e.row.date;
    const jump=row+' .compare-jump', left=sameDay?e.seller:e.criterion || e.original;
    assert.equal(await evaluate(q(jump)+'.textContent'),e.criterion?'对照本批标准与实测':sameDay?'对照同日原件':'对照候选标准');
    await activate(jump,'keyboard');
    await wait(q('#trace-compare')+'?.hidden===false && '+q('[data-pair="batch-'+e.batch.index+'"]')+'?.getAttribute("aria-pressed")==="true"','exact comparison '+phase.id);
    assert.equal(await evaluate('document.activeElement.dataset.pair'),'batch-'+e.batch.index);
    assert.deepEqual(await evaluate(all('.compare-leaf')+'.map(n=>n.dataset.fact)'),[left.id,(sameDay?e.date:e.criterion?e.reading:e.revised).id]);
    assert.equal(await evaluate(q('.compare-version')+'.dataset.state'),e.st.state);
  }
  const report=await load(rev), phasesOf=r=>r.findings.filter(f=>f.rule==='H04' && f.stage?.batch_index);
  const phases=phasesOf(report).sort((a,b)=>a.stage.batch_index-b.stage.batch_index);
  assert.equal(phases.length,2);
  for (const width of [390,1440,320,360,768,1024]) {
    const full=width===390 || width===1440;
    await size(ctx,width);
    for (const [index,phase] of phases.entries()) {
      await stage(phase,rev,index===0);
      const e=expected(report,phase); assertIssued(report,phase,e,rev);
      await widthFits(width,modal); await widthFits(width,card);
      const keys=await checkCard(e);
      if (index===1) {
        const shot=fixture && (rev===fixture.old && width===({strict:390,relaxed:1440,'same-day':390,'broken-date':1440})[fixture.name] ||
          fixture.name==='strict' && rev===fixture.old+1 && width===390);
        if (shot) await inspect(ctx,width,modal+' .scope-head',fixture.name+'-r'+rev);
        else await accessibility(ctx,'standard '+id.slice(0,6)+' R'+rev+' at '+width);
      }
      if (full) {
        await evaluate(q(mode('standard'))+'.focus()');
        await key('Home'); assert.equal(await evaluate('document.activeElement.dataset.source'),'contract');
        await key('ArrowRight'); assert.equal(await evaluate('document.activeElement.dataset.source'),'receipt');
        await key('End'); assert.equal(await evaluate('document.activeElement.dataset.source'),'standard');
        await key('Tab'); assert.equal(await evaluate('document.activeElement.dataset.standardField'),keys[0]);
      }
      for (const [i,k] of keys.entries())
        await original(field(k),e[k],rev,width,i || !full?width<600?'touch':'mouse':'keyboard');
      if (full) {
        await activate(card+' summary','keyboard');
        const more=await evaluate(all(card+' details [data-standard-field]')+'.map(b=>b.dataset.standardField)');
        assert.ok(more.includes('date'));
        if (fixture?.name==='broken-date') {
          assert.ok(!more.includes('seller') && more.includes('seller-raw'));
          const source=field('seller-raw');
          assert.equal(await evaluate(q(source+' strong')+'.textContent'),'2026年9月1 2日');
          assert.equal(await evaluate(q(source+' em')+'.textContent'),'待核');
          assert.equal(e.st.effective_on,null);
          if (index===1) await accessibility(ctx,'expanded dates R'+rev+' at '+width);
        }
        if (fixture?.name==='same-day' && rev===fixture.old && index===1)
          assert.match(await evaluate(q(card+' .batch-standard-heading')+'.textContent'),/同日，时分待核/u);
        for (const k of more) await original(field(k),e[k.replace(/-raw$/u,'')],rev,width,'keyboard',k.endsWith('-raw'));
        await widthFits(width,card);
        await activate(card+' summary','keyboard');
      }
      if (index===1 && full) await graphPair(phase,e);
    }
  }
  const phase=phases.at(-1), e=expected(report,phase);
  const probes=await evaluate('('+altered.toString()+')('+JSON.stringify(phase.id)+')');
  assert.equal(probes.baseline.chosen,e.criterion?.id || null);
  assert.deepEqual(probes.permuted,probes.baseline,'unordered unique comparison evidence');
  for (const [change,p] of Object.entries(probes)) {
    if (['baseline','permuted'].includes(change)) continue;
    assert.equal(p.chosen,null,change+' selected an edition');
    assert.ok(!p.fieldNames.includes('criterion') && !['applied','original'].includes(p.pair),change+' left a positive shortcut');
    assert.notEqual(p.status,'ok',change+' retained a passing batch');
  }
  for (const [change,k] of [['typed-edge','reading'],['foreign-reading','reading'],['foreign-basis','basis'],['receipt-text','basis'],
    ['change-identity','revised'],['criterion-node','revised'],['foreign-date','date'],['receipt-day','date'],['stamp-line','seller'],['stamp-value','seller']])
    assert.ok(!probes[change].fieldNames.includes(k),change+' retained '+k);
  for (const change of ['h02-edge','h04-edge','foreign-scope','stage-clause','duplicate-owner']) assert.equal(probes[change].pair,null,change);
  for (const change of ['stamp-owner','stamp-page','stamp-rect','stamp-h04','stamp-h02','change-identity'])
    assert.ok(!probes[change].fieldNames.includes('seller-raw'),change+' retained doubtful stamp');
  for (const change of ['legacy-h02','legacy-graph','h04-edge','stage-clause']) assert.deepEqual(probes[change].receipt,[e.basis.id,e.reading.id],change);
  for (const change of ['foreign-scope','duplicate-owner','h02-edge','raw-target','page-hash','h02-scope-shape','missing-type-index'])
    assert.equal(probes[change].receipt,null,change);
  // Open a raw original using each legacy entry point, with the version protocol removed in this tab only.
  await size(ctx,390); await stage(phase,rev); await key('Escape');
  await evaluate('(()=>{state.bundle=structuredClone(state.bundle);const h=state.bundle.report.findings.find(f=>f.rule==="H02");'+
    'for (const r of h.batch_acceptance.records) delete r.standard;state.tab="report";renderCase(true)})()');
  await stage(phase,rev,false,false);
  assert.equal(await evaluate(q(card)),null);
  const other=all(modal+' .scope-detail summary')+'.find(s=>s.textContent==="其他字段引文")';
  await evaluate(other+'.click()');
  const general=modal+' .scope-source .scope-open-original';
  await wait(q(general)+'?.dataset.fact','ordinary original picker');
  const generalId=await evaluate(q(general)+'.dataset.fact');
  await original(general,report.graph.facts.find(f=>f.id===generalId),rev,390);
  await key('Escape');
  const h2=report.findings.find(f=>f.rule==='H02'), finding='[data-finding="'+h2.id+'"]';
  const record=finding+' [data-delivery-index="'+e.batch.index+'"]';
  await evaluate('revealPaperTarget('+q(finding)+');'+all(record+' summary')+'.find(s=>s.textContent==="核对标准、实测与签认原文").click()');
  const stated=record+' [data-batch-fact="'+e.basis.id+'"] button', measured=record+' [data-batch-fact="'+e.reading.id+'"] button';
  await wait(q(stated)+'?.checkVisibility() && '+q(measured)+'?.checkVisibility()','H02 physical receipt');
  assert.equal(await evaluate(q(record+' [data-batch-fact="'+e.revised.id+'"]')),null);
  await original(measured,e.reading,rev,390,'keyboard',false,false);
  await activate('.performance-heading .compare-jump','keyboard');
  const raw='[data-pair="receipt-batch-'+e.batch.index+'"]';
  await wait(q(raw)+'?.checkVisibility()','H02 raw report comparison'); await activate(raw,'keyboard');
  assert.equal(await evaluate(q('[data-pair="batch-'+e.batch.index+'"]')),null);
  assert.equal(await evaluate(q('.compare-version')+'.dataset.state'),'pending');
  assert.deepEqual(await evaluate(all('.compare-leaf')+'.map(n=>n.dataset.fact)'),[e.basis.id,e.reading.id]);
  await original('.compare-leaf[data-fact="'+e.basis.id+'"] .compare-original',e.basis,rev,390,'keyboard',false,false);
  if (Number.isSafeInteger(compareRev) && compareRev>0) {
    assert.notEqual(compareRev,rev);
    await size(ctx,390);
    await stage(phase,rev);
    for (const revision of [compareRev,rev]) {
      await key('Escape');
      await evaluate('(()=>{const select='+q('#version')+';select.value='+revision+';select.dispatchEvent(new Event("change"));})()');
      await wait('state.bundle.rev==='+revision+' && '+q('#version')+'.value===String('+revision+')','switch to R'+revision);
      const next=await load(revision), second=phasesOf(next).find(f=>f.stage.batch_index===2), item=expected(next,second);
      await stage(second,revision,false); assertIssued(next,second,item,revision); await checkCard(item);
      const k=item.criterion?'criterion':'revised';
      await original(field(k),item[k],revision,390);
      await original(field('reading'),item.reading,revision,390,'touch');
    }
  }
  console.log('Batch standards '+id.slice(0,6)+' R'+rev+' · '+phases.map(p=>expected(report,p).st.state).join('/')+
    ' · 6 widths · '+(Object.keys(probes).length-1)+' altered reports · '+pageHashes.size+' original page hashes'+
    (process.env.AUDIT_AXE_FILE?' · axe at all six widths':'')+(compareRev?' · R'+rev+' → R'+compareRev+' → R'+rev:''));
}
