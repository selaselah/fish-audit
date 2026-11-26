// Read fixed synthetic reports through the same routes, controls and original reader as an auditor.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {browserInput, inspect, size} from './review-screen.mjs';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const all=s=>'[...document.querySelectorAll('+JSON.stringify(s)+')]';
const modal='#performance-index', panel=modal+' .advance-guarantee';
const tab=name=>panel+' [role=tab][id$="-'+name+'"]';
const source=ref=>panel+' button[data-source="'+ref+'"]';
const moneyPaid='2026-09-05', dayIssued='2026-09-02';
const cases=[
  ['未附采购方签收单','only','missing','签收依据待补',null],
  ['支付后签收','late','before_receipt','付款早于签收3天','2026-09-08'],
  ['支付前签收','early','after_receipt','付款晚于签收2天','2026-09-03'],
  ['受益人与合同','beneficiary','mismatch','受益人与约定不符','2026-09-03']
];

function changed(findingId,change) {
  const report=structuredClone(state.bundle.report), graph=report.graph;
  const f=report.findings.find(row=>row.id===findingId), p=f.advance_guarantee;
  const row=p.sources.find(s=>s.role==='guarantee' && s.field==='issued_on');
  switch (change) {
    case 'page-hash': graph.nodes.find(n=>n.id===row.doc+'/p'+row.page).sha256='unrelated'; break;
    case 'coordinates': report.calls.pages.find(c=>c.doc===row.doc && c.page===row.page).advance_guarantee_rects[row.line]=[]; break;
    case 'support': graph.edges=graph.edges.filter(e=>!(e.from===row.id && e.to==='finding/'+f.id)); break;
    case 'source': graph.edges.find(e=>e.type==='advance_guarantee_source' && e.to===row.id).from='unrelated'; break;
    case 'duplicate': p.sources.push(row); break;
    case 'unit': row.unit='foreign'; break;
    case 'quote': row.quote='开立日期：2025年9月2日'; break;
    case 'operands': p.evidence=p.evidence.filter(ref=>ref!==row.id); break;
    case 'stage': graph.edges=graph.edges.filter(e=>!(e.type==='payment_stage' && e.evidence.includes(f.stage.clause_ref))); break;
    case 'order': p.state='same_day'; break;
    case 'legacy': delete report.policy.advance_guarantee; break;
  }
  const view=AdvanceGuarantee.panel(f,report);
  return {outcome:view?.dataset.state || null,readable:Boolean(AdvanceGuarantee.citation(row.id,f,report))};
}

export async function checkAdvanceGuarantee(ctx,id,revision,previous) {
  const {root,call,wait,evaluate}=ctx, api=root+'/api/cases/'+id;
  const task=await (await fetch(api)).json(), rev=revision || task.rev;
  const scenario=cases.find(c=>task.title?.startsWith('合成演练') && task.title.includes(c[0]));
  assert.ok(scenario && Number.isInteger(rev) && rev>0,'select a fixed guarantee exercise');
  const [,name,outcome,label,ackDay]=scenario;
  const bundle=await (await fetch(api+'/reports/'+rev)).json();
  assert.equal(bundle.rev,rev);
  const report=bundle.report, phase=report.findings.find(f=>f.rule==='H04' && f.advance_guarantee);
  const payment=report.findings.find(f=>f.rule==='H05' && f.advance_guarantee);
  assert.ok(phase && payment);
  assert.equal(payment.advance_guarantee.state,outcome);
  const later=report.findings.find(f=>f.rule==='H04' && f.stage?.name==='第二期');
  const {key,tap}=browserInput(ctx), hashes=new Set();
  const url=r=>root+'/workpaper/'+id+'?rev='+r+'&view=payment-checks&stage=';

  async function load(r,item,expectProof=true) {
    await call('Page.navigate',{url:url(r)+item});
    await wait(q(modal)+'?.open && '+q('.scope-check-select')+'?.value==='+JSON.stringify(item)+' && state.bundle?.rev==='+r,'R'+r+' '+item);
    assert.equal(await evaluate(q(panel)+'!==null'),expectProof);
  }
  async function original(row,width) {
    const selector=source(row.id), address=api+'/documents/'+row.doc+'/pages/'+row.page+'?rev='+rev;
    if (width<600) await tap(q(selector));
    else { await evaluate(q(selector)+'.focus()'); await key('Enter'); }
    const located='#page-dialog .evidence-row.located';
    await wait(q('#page-dialog')+'.open && '+q(located)+'?.dataset.sourceRef==='+JSON.stringify(row.id)+
      ' && '+q('.source-tools > a')+'?.href==='+JSON.stringify(address)+' && '+q('.page-image')+'?.naturalWidth>0','issued row '+row.id);
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    assert.equal(await evaluate(q(located+' blockquote')+'.textContent'),row.quote);
    assert.equal(await evaluate(q(located)+'.dataset.gapLine'),String(row.line));
    const rects=await evaluate(all('.source-plane > svg:first-of-type > rect')+'.map(r=>["x","y","width","height"].map(k=>Number(r.getAttribute(k))))');
    assert.deepEqual(rects,row.rects.map(([l,t,r,b])=>[l*1000,t*1000,(r-l)*1000,(b-t)*1000]));
    if (!hashes.has(address)) {
      assert.equal(createHash('sha256').update(Buffer.from(await (await fetch(address)).arrayBuffer())).digest('hex'),row.page_sha256);
      hashes.add(address);
    }
    await key('Escape');
    await wait(q(modal)+'.open && !'+q('#page-dialog')+'.open && document.activeElement==='+q(selector),'return to original control');
  }

  for (const width of [320,360,390,768,1024,1440]) {
    await size(ctx,width);
    await call('Emulation.setTouchEmulationEnabled',{enabled:width<600});
    await load(rev,payment.id);
    assert.equal(await evaluate(q(panel)+'.dataset.state'),outcome);
    assert.equal(await evaluate(q(panel+' .guarantee-status')+'.textContent'),label);
    assert.equal(await evaluate(q(panel+' .guarantee-followup')+'?.textContent || null'),name==='early'?'待人工核验保函真伪、效力及付款授权':null);
    assert.equal(await evaluate(q(panel+' [role=tabpanel]')+'.dataset.tab'),name==='beneficiary'?'parties':'dates');
    await inspect(ctx,width,panel,'advance-'+name);
    if ([390,1440].includes(width)) {
      const switcher=q(panel+' [role=switch]');
      await evaluate(switcher+'.click()');
      await wait(all(panel+' .guarantee-strip canvas')+'.length>=2','original image excerpts');
      await inspect(ctx,width,panel,'advance-'+name+'-originals');
      await evaluate(switcher+'.focus()'); await key('Space');
      assert.equal(await evaluate(all(panel+' .guarantee-strip')+'.length'),0);
    }
    if (name==='beneficiary') {
      const b=payment.advance_guarantee.sources.find(r=>r.field==='beneficiary');
      assert.equal(await evaluate(q(source(b.id))+'.dataset.discrepancy'),'true');
      await original(b,width);
    }
    await evaluate(q(tab('dates'))+'.click()');
    const dates=await evaluate(all(panel+' .guarantee-dates time')+'.map(t=>t.dateTime)');
    assert.deepEqual(dates,[dayIssued,moneyPaid,...(ackDay?[ackDay]:[])].sort());
    assert.equal(await evaluate(all(panel+' .guarantee-undated')+'.length'),ackDay?0:1);
    for (const row of payment.advance_guarantee.sources.filter(r=>['issued_on','received_on','paid_on'].includes(r.field)))
      await original(row,width);
    await evaluate(q(tab('dates'))+'.focus()'); await key('ArrowRight');
    assert.equal(await evaluate(q(tab('parties'))+'.getAttribute("aria-selected")'),'true');
    if (width>=651) {
      const pinned=await evaluate('(()=>{const d=document.querySelector(".scope-detail"),h=document.querySelector(".scope-head"),'+
        'nav=document.querySelector(".scope-checks"),details=d.querySelector(".guarantee-lines details");'+
        'details.open=true;const before=h.getBoundingClientRect().top,left=nav.getBoundingClientRect().top;d.scrollTop=d.scrollHeight;'+
        'const result=[d.scrollTop,h.getBoundingClientRect().top-before,nav.getBoundingClientRect().top-left];d.scrollTop=0;details.open=false;return result;})()');
      assert.ok(pinned[0]>0,'expanded sources scroll inside the reading pane');
      assert.deepEqual(pinned.slice(1),[0,0],'heading and installment list stay in place');
    }
    await key('End');
    assert.equal(await evaluate(q(tab('clause'))+'.getAttribute("aria-selected")'),'true');
    const term=payment.advance_guarantee.sources.find(r=>r.role==='clause' && r.line);
    await original(term,width);
    assert.ok(await evaluate(q(panel)+'.scrollWidth<='+q(panel)+'.clientWidth+1'));
    await load(rev,phase.id);
    assert.equal(await evaluate(q(panel)+'.dataset.state'),phase.advance_guarantee.state);
    assert.equal(await evaluate(q(panel+' .guarantee-followup')+'!==null'),phase.advance_guarantee.state==='recorded');
    assert.equal(await evaluate(all(panel+' [data-event=paid]')+'.length'),0);
  }
  await load(rev,payment.id);
  for (const change of ['page-hash','coordinates','support','source','duplicate','unit','quote','operands','stage','legacy',
    ...(['early','late'].includes(name)?['order']:[])]) {
    const result=await evaluate('('+changed.toString()+')('+JSON.stringify(payment.id)+','+JSON.stringify(change)+')');
    assert.equal(result.outcome,change==='legacy'?null:'unverified',change);
    if (['page-hash','coordinates','support','source','unit','quote','legacy'].includes(change)) assert.equal(result.readable,false,change);
  }
  const desk=await evaluate('(()=>{const p=contractPreview(state.bundle.report,state.detail);p.querySelector(".preview-phase-tab")?.click();return [...p.querySelectorAll("a")].map(a=>[a.textContent,a.getAttribute("href")]);})()');
  for (const [f,title] of [[phase,'预付款保函'],[payment,'签收与付款日']])
    assert.equal(desk.find(row=>row[0].includes(title))?.[1],'/workpaper/'+id+'?rev='+rev+'&view=payment-checks&stage='+f.id);
  await key('Escape');
  await evaluate(q('#quick-open')+'.click()');
  await wait(q('#quick-dialog')+'.open','quick navigation');
  await evaluate(q('#quick-query')+'.value="预付款保函";'+q('#quick-query')+'.dispatchEvent(new Event("input"))');
  await wait(all('#quick-results .quick-label')+'.some(s=>s.textContent==="核对预付款保函")','guarantee command');
  await evaluate(all('#quick-results .quick-label')+'.find(s=>s.textContent==="核对预付款保函").closest("[role=option]").click()');
  await wait(q(modal)+'.open && '+q('.scope-check-select')+'.value==='+JSON.stringify(payment.id),'payment workpaper via quick navigation');
  await load(rev,later.id,false);
  if (previous) {
    await load(previous,payment.id,false);
    await load(rev,payment.id);
  }
  if (name==='late') {
    await call('Network.enable');
    await call('Network.setBlockedURLs',{urls:['*/api/cases/'+id+'/documents/*/pages/*']});
    try {
      await load(rev,payment.id);
      await evaluate(q(panel+' [role=switch]')+'.click()');
      await wait(all(panel+' .guarantee-strip')+'.length===3 && graphIndex(state.bundle.report.graph).images?.size===0','quote fallback after failed images');
      const printed=await evaluate(all(panel+' .guarantee-strip')+'.map(s=>s.querySelector("span").textContent)');
      const rows=payment.advance_guarantee.sources.filter(r=>['issued_on','received_on','paid_on'].includes(r.field));
      assert.deepEqual(printed.sort(),rows.map(r=>r.quote).sort());
      assert.equal(await evaluate(all(panel+' .guarantee-strip canvas')+'.length'),0);
    } finally {
      await call('Network.setBlockedURLs',{urls:[]});
    }
    await evaluate(q(panel+' [role=switch]')+'.click();'+q(panel+' [role=switch]')+'.click()');
    await wait(all(panel+' .guarantee-strip canvas')+'.length===3','excerpts after network recovery');
  }
  await call('Page.navigate',{url:url(rev)+'H05-999'});
  await wait(q(modal)+'?.open && '+q(modal+' .scope-detail .scope-empty')+'?.textContent.includes("所选期次")','unavailable installment');
  assert.equal(await evaluate(q(panel)+'!==null'),false);
  console.log('PASS · '+name+' R'+rev+', six widths, fixed original quotes, rectangles, revision, focus and evidence boundaries');
}
