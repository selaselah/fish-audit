import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

// Runs in the page. Each variation gets a fresh copy of the issued report and graph indexes.
function bindingFailures(id) {
  const issued=state.bundle.report, receipt=issued.findings.find(f=>f.id===id).retest_reference, failures=[];
  function check(label,change,expected=false) {
    const report=structuredClone(issued), item=report.findings.find(f=>f.id===id), c=item.retest_reference;
    const graph=report.graph, plan=report.findings.find(f=>f.rule==='H03');
    change({report,item,c,graph,plan,review:c.schedule_review,ledger:graph.retest_reference_sources});
    if (Boolean(RetestReference.bind(item,report))!==expected) failures.push(label);
  }
  check('policy format',({report})=>{report.policy.retest_reference='other';});
  check('graph format',({ledger})=>{ledger.format='other';});
  check('receipt format',({c})=>{c.format='other';});
  check('issued rule version',({report,item,c})=>{
    item.version=report.policy.version=c.format.endsWith('-v1')?'2026.11.28.7':'2026.11.28.6';
  });
  check('method',({report})=>{delete report.policy.code_sha256['retest_reference.py'];});
  check('receipt status',({c})=>{c.status=c.status==='risk'?'missing':'risk';});
  if (receipt.state!=='unresolved') {
    check('number',({c})=>{c.number+='-1';});
    check('state',({c})=>{c.state=c.state==='original'?'final':'original';});
    check('date',({c})=>{c.final_on='2000-09-20';});
    check('date difference',({c})=>{c.days_from_final=(c.days_from_final || 0)+1;});
    check('unit',({c})=>{c.units.original=c.units.final;});
    check('final line',({c,ledger})=>{ledger.rows.find(r=>r.facts.includes(c.fields.final_acceptance_number)).line++;});
    check('receipt edge',({c,graph})=>{
      const edge=graph.edges.find(e=>e.type==='receipt_names_inspection' && e.from===c.fields.citation);
      if (edge) edge.to=c.fields.paid_on;
      else graph.edges.push({type:'receipt_names_inspection',from:c.fields.citation,to:c.fields.final_acceptance_number,evidence:c.evidence});
    });
    if (receipt.format==='reinspection-receipt-reference-v2') {
      for (const agrees of [true,false]) check(agrees?'equivalent printed repair dates':'different repair dates',({report,c,graph,ledger})=>{
        const step=report.findings.find(f=>f.rule==='H02').reinspection.steps.find(s=>s.role==='repair');
        const [year,month,day]=step.date.split('-'), fact=graph.facts.find(f=>f.id===c.fields.repair_repaired_on);
        const row=ledger.rows.find(r=>r.unit===step.unit && r.field==='repaired_on');
        const fullWidth=s=>s.replace(/[0-9]/gu,d=>String.fromCharCode(d.charCodeAt(0)+0xfee0));
        row.quote=fact.source_line.text='整改完成日期：'+fullWidth(year+'年　'+month+'月'+day+'日');
        fact.quote='整改完成日期: '+year+' 年 '+month+' 月 '+day+' 日';
        fact.value=year+'年'+month+'月'+(agrees?day:day==='01'?'02':'01')+'日';
      },agrees);
    }
  }
  if (receipt.schedule_review) {
    check('omitted hold',({c})=>{delete c.schedule_review;});
    check('unresolved hold',({c})=>{c.state='unresolved';});
    check('partial marked ok',({c})=>{c.status='ok';});
    check('missing page marker',({ledger})=>{delete ledger.schedule_page;});
    check('other page marker',({ledger,c})=>{ledger.schedule_page=c.bank+'/p1';});
    check('H03 status',({plan,graph})=>{plan.status=graph.nodes.find(n=>n.id==='finding/'+plan.id).status='ok';});
    check('H03 graph witness',({plan,graph})=>{graph.nodes.find(n=>n.id==='finding/'+plan.id).detail+='?';});
    check('H03 procedure',({plan,graph})=>{graph.edges=graph.edges.filter(e=>e.type!=='procedure_result' || e.to!=='finding/'+plan.id);});
    check('declared count',({review})=>{review.declared++;});
    check('listed count',({review})=>{review.listed++;});
    check('total share',({review})=>{review.share_total=String(Number(review.share_total)+1);});
    check('header ref',({review})=>{review.header=review.clauses[0];});
    check('header line',({ledger,graph})=>{ledger.rows.find(r=>r.unit===graph.documents_by_kind.contract[0] && r.field==='payment_term').line++;});
    check('H03 header citation',({plan,review})=>{plan.evidence=plan.evidence.filter(ref=>ref!==review.header);});
    check('H05 clause witness',({graph,item,review})=>{
      graph.edges=graph.edges.filter(e=>!(e.type==='supports_result' && e.to==='finding/'+item.id && e.from===review.clauses[0]));
    });
    check('clause list',({review})=>{review.clauses.pop();});
    if (receipt.schedule_review.listed>1) check('printed stage order',({review})=>{review.clauses.reverse();});
    check('printed clause',({graph,review})=>{graph.facts.find(f=>f.id===review.clauses[0]).source_line.text+=' 待核';});
    check('unlisted stage observation',({graph,review})=>{graph.facts.push({...graph.facts.find(f=>f.id===review.clauses[0]),id:'extra-stage'});});
    check('H04 share',({report,review})=>{report.findings.find(f=>f.rule==='H04' && f.stage?.clause_ref===review.clauses[0]).stage.share='0';});
    check('own installment',({item})=>{item.stage.name='第99期';});
    check('own share',({item})=>{item.stage.share='0';});
    check('repair chronology',({report})=>{report.findings.find(f=>f.rule==='H02').reinspection.steps.find(s=>s.role==='repair').date='2000-01-01';});
    if (receipt.schedule_review.header.startsWith('installment-count/')) {
      check('raw header graph witness',({graph,review})=>{graph.edges=graph.edges.filter(e=>e.type!=='locates_installment_count' || e.to!==review.header);});
    }
  } else {
    check('unissued hold',({c})=>{c.schedule_review={declared:4,listed:3,share_total:'100',header:c.fields.clause,clauses:[]};});
    check('no marker required without a hold',({ledger})=>{delete ledger.schedule_page;},true);
  }
  return failures;
}

export async function checkRetestReference(ctx,cid) {
  const {root,call,evaluate,wait}=ctx, base='/api/cases/'+cid;
  async function json(path) {
    const response=await fetch(root+path);assert.equal(response.status,200);return response.json();
  }
  const task=await json(base);assert.match(task.title,/^合成演练 · /u);
  const {report,rev}=await json(base+'/reports/'+(process.env.AUDIT_RETEST_REV || task.rev));
  const item=report.findings.find(f=>f.retest_reference) ||
    report.findings.find(f=>f.payment_acceptance) || report.findings.find(f=>f.rule==='H05' && f.stage);
  const {id,retest_reference:c}=item, fixed=root+'/workpaper/'+cid+'?rev='+rev, card='#retest-'+id;
  const review=c?.schedule_review, plan=report.findings.find(f=>f.rule==='H03'), schedule=card+'-schedule';
  const payment=fixed+'&view=payment-checks&stage='+id;
  if (process.env.AUDIT_RETEST_EXPECT_SCHEDULE) {
    assert.equal(review?[review.declared,review.listed,review.share_total].join('/'):'none',process.env.AUDIT_RETEST_EXPECT_SCHEDULE);
  }
  const q=s=>'document.querySelector('+JSON.stringify(s)+')', click=s=>evaluate(q(s)+'.click()');
  const visible=s=>q(s)+'?.getClientRects().length', go=url=>call('Page.navigate',{url});
  const facts=new Map(report.graph.facts.map(f=>[f.id,f]));
  async function original(key,whileOpen) {
    const fact=facts.get(c.fields[key]), button=card+'-'+key;
    assert.equal(await evaluate(q(button)+'.dataset.source'),fact.id);
    assert.match(await evaluate(q(button)+'.title'),new RegExp('第 '+fact.page+' 页 · 第 '+fact.source_line.number+' 行'));
    await click(button);
    await wait(q('#page-dialog')+'?.open && '+q('#page-content .located')+'?.dataset.fact==='+JSON.stringify(fact.id)+
      ' && '+q('#page-content img')+'?.naturalWidth>0','filed original for '+key);
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    assert.equal(await evaluate(q('#page-content .page-view')+'.dataset.doc'),fact.doc);
    assert.equal(await evaluate(q('#reader-citation-picker')+'.value'),fact.id);
    if (whileOpen) await whileOpen(fact);
    await evaluate(q('#page-dialog')+'.close()');
  }
  if (!c) {
    await go(payment);
    await wait(q('#performance-index')+'?.open && '+q('.scope-check-select')+'?.value==='+JSON.stringify(id),'historical finding');
    assert.equal(await evaluate(q('[data-retest-finding]')),null);
    console.log('PASS · R'+rev+' historical finding retains its issued evidence');return;
  }
  await go(fixed);
  const section='[data-finding="'+id+'"]', summary=section+' .finding-disclosure > summary';
  await wait(visible(summary),'receipt in the findings ledger');await click(summary);
  const jump=section+' a[href*="view=payment-checks"][href*="stage='+id+'"]';
  await wait(visible(jump),'receipt citation on the ordinary workpaper');await click(jump);
  await wait(q('#performance-index')+'?.open && '+visible(card),'matching receipt, revision and installment');
  assert.equal(await evaluate(q(card)+'.dataset.caseId'),cid);assert.equal(await evaluate(q(card)+'.dataset.rev'),String(rev));
  assert.deepEqual(await evaluate('('+bindingFailures.toString()+')('+JSON.stringify(id)+')'),[]);
  if (review) {
    assert.equal(c.format,'reinspection-receipt-reference-v2');
    assert.equal(report.graph.retest_reference_sources.schedule_page,report.graph.documents_by_kind.contract[0]+'/p1');
    assert.equal(plan.status,'missing');assert.notEqual(c.status,'ok');
    const hold=await evaluate(q(schedule)+'.innerText');
    for (const part of ['付款安排待核','约定 '+review.declared+' 期','列出 '+review.listed+' 期','合计 '+review.share_total+'%','R'+rev,'H03']) assert.ok(hold.includes(part),part);
    assert.equal(await evaluate(q(schedule)+'.href'),fixed+'&finding='+plan.id);
    assert.equal((await evaluate(q(card+' .quality-heading > span')+'.textContent')).includes('风险'),c.status==='risk');
  } else assert.equal(await evaluate(q(schedule)),null);
  const cited=card+'-citation';
  if (c.number) {assert.equal(await evaluate(q(cited+' strong')+'.textContent'),c.number);await original('citation');}
  if (c.state==='unresolved') {
    for (const key of ['-terms','-final_acceptance_number','-original_acceptance_number','-order'])
      assert.equal(await evaluate(q(card+key)),null);
  } else {
    for (const role of ['original','final']) {
      const key=role+'_acceptance_number', button=card+'-'+key;
      assert.equal(await evaluate(q(button+' strong')+'.textContent'),c[role+'_number']);
      assert.equal(await evaluate(q(button)+'.classList.contains("retest-match")'),c.state===role);
      await original(key);
    }
    for (const key of ['paid_on','final_accepted_on']) await original(key);
    const order=await evaluate(q(card+'-order')+'?.textContent || null'), days=c.days_from_final;
    assert.equal(order,c.state==='final'?(days?'回单'+(days<0?'早 ':'晚 ')+Math.abs(days)+' 天':'同日，先后待核'):null);
    await click(card+'-terms');
    for (const key of ['clause','repair_repair_number','repair_repaired_on','final_defect_closure']) await original(key);
    await click(card+'-terms');
  }
  for (const width of [320,390,768,820,1024,1440]) {
    await size(ctx,width);
    assert.ok(await evaluate('[...'+q(card)+'.querySelectorAll("button,summary,a")].filter(e=>e.getClientRects().length).every(e=>{const r=e.getBoundingClientRect();return r.width>=44 && r.height>=44 && r.left>=-1 && r.right<=innerWidth+1})'),'controls at '+width);
    await inspect(ctx,width,card,'retest-'+cid.slice(0,8)+'-R'+rev);
  }
  const pointer=browserInput(ctx), mouse=s=>pointer.click(q(s));
  async function openScheduleHeader() {
    await wait(q('#trace-select')+'?.value==='+JSON.stringify(plan.id)+' && state.bundle?.rev==='+rev,'same-revision H03 evidence');
    assert.equal(await evaluate(q('#trace-details .trace-result p')+'.textContent'),plan.detail);
    const details='.trace-modes [data-mode="details"]';
    if (await evaluate(visible(details))) await mouse(details);
    const header=facts.get(review.header);
    if (header) {
      const doc=report.graph.documents.find(d=>d.id===header.doc);
      const fold='[...document.querySelectorAll("#trace-details .trace-sources > details > summary")].find(s=>s.textContent.startsWith('+JSON.stringify(doc.name+' ·')+'))';
      await pointer.click(fold);
      const source='[...document.querySelectorAll("#trace-details .trace-quote")].find(s=>s.querySelector("blockquote")?.textContent==='+JSON.stringify(header.quote)+')?.querySelector("button")';
      await wait(source+'?.getClientRects().length','contract header in the H03 trace');await pointer.click(source);
    } else await mouse('#trace-details [data-count-ref="'+review.header+'"]');
    await wait(q('#page-dialog')+'?.open && '+q('#reader-citation-picker')+'?.value==='+JSON.stringify(review.header)+
      ' && '+q('#page-content img')+'?.naturalWidth>0','H03 opens its cited header');
    assert.equal(await evaluate(q('#page-content .located')+'.dataset.'+(header?'fact':'sourceRef')),review.header);
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
  }
  if (review) {
    await evaluate(q(schedule)+'.focus()');await pointer.key('Enter');
    await openScheduleHeader();
    const picker=q('#reader-citation-picker'), located=q('#page-content .located');
    for (const ref of review.clauses) {
      const fact=facts.get(ref);
      await evaluate(picker+'.value='+JSON.stringify(ref)+';'+picker+'.dispatchEvent(new Event("change"))');
      await wait(located+'?.dataset.fact==='+JSON.stringify(ref),'line picker selects '+ref);
      assert.equal(await evaluate(q('#page-content .page-view')+'.dataset.doc'),fact.doc);
      assert.equal(await evaluate('document.querySelectorAll("#page-content .source-plane svg rect").length'),fact.source_line.rects.length);
    }
    await evaluate(q('#page-dialog')+'.close()');
    await go(payment);await wait(q('#performance-index')+'?.open && '+visible(schedule),'return to the issued receipt');
  }
  const isolated=process.env.AUDIT_ISOLATED_RETEST_ORIGIN && process.env.AUDIT_RETEST_READ_ONLY!=='1';
  if (isolated && c.state!=='unresolved') {
    assert.equal(root,process.env.AUDIT_ISOLATED_RETEST_ORIGIN);assert.ok(!['8000','8010'].includes(new URL(root).port));
    assert.match(root,/^http:\/\/127\.0\.0\.1:\d+$/u);
    assert.deepEqual((await json('/api/walkthrough')).notes,[]);
    await size(ctx,390);
    const folded='final_original_acceptance', target=review?schedule:card+'-'+folded;
    const general='希望在本期付款旁补充审批记录入口。';
    const opinion=review?'查看付款安排依据时，希望能对照回单引用的单号。':'这张复验单引用哪张初验单，希望同时看到初验结论。';
    async function walkSchedule(text) {
      await size(ctx,1440);
      const docked=owner=>q(owner+' #walk-rail')+'?.matches(":popover-open")';
      const label=await evaluate(q(schedule)+'.dataset.originalLabel');
      await mouse('#walk-dock');await wait(docked('#performance-index'),'dock the recorder beside H05');
      await mouse('#walk-pick');await mouse(schedule);
      await wait(q(schedule)+'.classList.contains("walk-selected") && '+q('#walk-location')+'.textContent==='+JSON.stringify(label),'pin the schedule hold at 1440px');
      await mouse(schedule);await openScheduleHeader();
      await wait(docked('#page-dialog'),'keep the recorder beside the cited contract page');
      assert.equal(await evaluate(q('#walk-location')+'.textContent'),label);
      assert.equal(await evaluate(q('#walk-text')+'.value'),text);
      assert.ok(await evaluate('(()=>{const page='+q('#page-dialog')+'.getBoundingClientRect(),rail='+q('#walk-rail')+
        '.getBoundingClientRect();return page.width>0 && rail.width>0 && page.right<=rail.left && rail.right<=innerWidth+1})()'),'contract and recorder occupy separate columns');
      await inspect(ctx,1440,'#walk-rail','retest-walkthrough');
      await size(ctx,390);await wait(q('#walk-dialog')+'?.matches(":modal")','same pinned note after undocking');
    }
    async function write(text,pick) {
      await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','start a note');
      await evaluate(q('#walk-text')+'.value='+JSON.stringify(text)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
      if (pick) {
        await click('#walk-pick');await browserInput(ctx).tap(q(pick));
        await wait(q('#walk-dialog')+'.open && '+q(pick)+'.classList.contains("walk-selected")','pin a source control');
        await inspect(ctx,390,'#walk-dialog','retest-feedback');
        if (pick===schedule) await walkSchedule(text);
      }
      await click('#walk-save');await wait('!'+q('#walk-dialog')+'.open','save the note');
      if (pick===schedule) {
        await go(payment);await wait(q('#performance-index')+'?.open && '+visible(schedule),'back to the pinned installment');
      }
    }
    await write(general);
    if (!review) await click(card+'-terms');
    await write(opinion,target);
    assert.ok(await evaluate('!Object.keys(sessionStorage).some(k=>k.startsWith("fish-walk-draft:"))'),'successful save clears the pinned draft and its submission id');
    const notes=(await json('/api/walkthrough')).notes, note=notes.find(n=>n.text===opinion), ordinary=notes.find(n=>n.text===general);
    assert.equal(notes.length,2);
    assert.equal(ordinary.text,general);assert.equal(ordinary.context.anchor,card.slice(1));assert.equal(note.text,opinion);
    for (const row of [note,ordinary]) {
      assert.equal(row.context.case_id,cid);assert.equal(row.context.rev,rev);
      assert.deepEqual(row.context.params,{view:'payment-checks',stage:id});
    }
    assert.equal(note.context.anchor,target.slice(1));
    if (review) assert.equal(note.context.target,await evaluate(q(schedule)+'.dataset.originalLabel'));
    else assert.match(note.context.target,/复验所引初验单.*第 1 页.*行/u);
    const rejected=[[{...note.context,rev:task.rev+1},404],[{...note.context,params:{view:'payment-checks',stage:'H05-300'}},400]];
    if (c.state!=='final') rejected.push([{...note.context,anchor:card.slice(1)+'-order'},404]);
    if (rev>1) {
      const prior=(await json(base+'/reports/'+(rev-1))).report.findings.find(f=>f.id===id)?.retest_reference;
      if (review?!prior?.schedule_review:!prior?.fields[folded]) rejected.push([{...note.context,rev:rev-1},404]);
    }
    for (const [context,status] of rejected) {
      const response=await fetch(root+'/api/walkthrough',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({id:'4'.repeat(32),text:opinion,context})});assert.equal(response.status,status);
    }
    await go(root+'/app#desk');await wait(visible('#desk')+' && '+visible('body > #walk-launch'),'desk');
    await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-saved')+'.disabled','open saved notes');
    await click('#walk-saved');await wait(visible('#walk-history li a'),'recorded locations');
    await evaluate('Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:async t=>{window.copiedWalkthrough=t}});true');
    await browserInput(ctx).tap(q('#walk-copy'));await wait('typeof window.copiedWalkthrough==="string"','copy to Codex');
    const saved='#walk-history a[href*="walkat='+target.slice(1)+'"]';
    const dest=await evaluate(q(saved)+'.href'), handoff=await evaluate('window.copiedWalkthrough');
    assert.ok([dest,opinion,general,note.context.target].every(x=>handoff.includes(x)));
    await click(saved);
    await wait(visible(target)+' && '+q(target)+'.classList.contains("walk-mark")','return to the pinned receipt control');
    if (review) {
      assert.equal(await evaluate(q(target)+'.href'),fixed+'&finding='+plan.id);
      await click(card+'-terms');
    }
    await original(folded,async fact=>{
      await write('复验报告里这一行原单号也应出现在审批旁。');
      const [pageNote]=(await json('/api/walkthrough')).notes;
      assert.equal(pageNote.context.target,report.graph.documents.find(d=>d.id===fact.doc).name);
      assert.deepEqual([pageNote.context.rev,pageNote.context.doc,pageNote.context.page,pageNote.context.line,pageNote.context.params.fact],
        [rev,fact.doc,fact.page,fact.source_line.number,fact.id]);
    });
    const end=await json(base);
    assert.deepEqual([end.status,end.rev,end.decisions,end.referrals],[task.status,task.rev,task.decisions,task.referrals]);
  }
  console.log('PASS · R'+rev+' · '+c.state+' · source lines, receipt and six viewport widths'+(review?', H03 schedule hold':'')+
    (isolated && c.state!=='unresolved'?', saved control and copied handoff':''));
}
