import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

export async function checkInspectionUse(ctx,cid) {
  const {call,evaluate,wait,root}=ctx, api='/api/cases/'+cid;
  const json=async path=>{const r=await fetch(root+path);assert.equal(r.status,200);return r.json();};
  const task=await json(api);assert.match(task.title,/^合成演练 · /u);
  const {report,rev}=await json(api+'/reports/'+(process.env.AUDIT_USE_REV || task.rev));
  const item=report.findings.find(f=>f.inspection_use) || report.findings.find(f=>f.rule==='H05' && f.stage);
  const c=item.inspection_use, {id}=item, card='#inspection-use-'+id;
  const q=s=>'document.querySelector('+JSON.stringify(s)+')', click=s=>evaluate(q(s)+'.click()');
  const visible=s=>q(s)+'?.getClientRects().length', go=url=>call('Page.navigate',{url});
  const fixed=root+'/workpaper/'+cid+'?rev='+rev;
  if (!c) {
    await go(fixed+'&view=payment-checks&stage='+id);
    await wait(q('#performance-index')+'?.open && '+q('.scope-check-select')+'?.value==='+JSON.stringify(id),'issued installment');
    assert.equal(await evaluate(q('[data-use-finding]')),null);
    console.log('PASS · R'+rev+' retains the issued receipt without a payment-use statement');return;
  }
  await go(fixed);
  const section='[data-finding="'+id+'"]', summary=section+' .finding-disclosure > summary';
  await wait(visible(summary),'ordinary workpaper');await click(summary);
  const jump=section+' a[href*="view=payment-checks"][href*="stage='+id+'"]';
  await wait(visible(jump),'payment-use finding');await click(jump);
  await wait(q('#performance-index')+'?.open && '+visible(card),'issued payment-use statement');
  assert.equal(await evaluate(q(card)+'.dataset.status'),c.status);
  const proof=c.notes[0], a=c.approval, approvalCard='#payment-approval-'+id;
  const approvalRows=report.graph.inspection_use_sources.approvals?.flatMap(p=>p.rows) || [];
  const bankRows=report.graph.inspection_use_sources.bank_clocks?.flatMap(p=>p.rows) || [];
  const clock=a?.clock, time=bankRows.find(r=>clock?.rows.includes(r.id));
  const names=a?.names, term=report.graph.inspection_use_sources.approver_terms?.flatMap(p=>p.rows).find(r=>names?.rows.includes(r.id));
  const row=term || time || (a?.fields ? approvalRows.find(r=>r.id===a.fields.date) : report.graph.inspection_use_sources.rows.find(r=>r.id===proof.row));
  const base=term?'#contract-approver-'+id:time?'#payment-clock-'+id:row.field?approvalCard:card, doc=report.graph.documents.find(d=>d.id===row.doc);
  const control=base+'-'+row.doc+'-p'+row.page+'-l'+row.line;
  assert.equal(await evaluate(q(control)+'.dataset.scope'),term?'contract_term':time?'bank_time':row.field?'approval_sheet':proof.scope);
  assert.equal(await evaluate(q(control+' strong')+'.textContent'),term?(names.required?.join('、') || row.quote):time?row.quote.slice(row.quote.search(/[:：]/u)+1).trim():row.quote);
  const label=await evaluate(q(control)+'.dataset.originalLabel');
  assert.ok(label.includes(doc.name) && label.includes('第 '+row.line+' 行'));
  async function located(fromHistory=false,printed=row) {
    const sel='#page-content .evidence-row.located';
    const route=fromHistory?'state.openedCitation===location.hash && Team.route().params.get("walkraw")==='+JSON.stringify(printed.id)+' && ':'';
    await wait(route+q('#page-dialog')+'?.open && '+q(sel)+'?.dataset.sourceRef==='+JSON.stringify(printed.id)+' && '+q('#page-content img')+'?.naturalWidth>0','printed line and original page image');
    assert.equal(await evaluate(q(sel+' blockquote')+'.textContent'),printed.quote);
    assert.equal(await evaluate(q('#page-content .page-view')+'.dataset.doc'),printed.doc);
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    assert.equal(await evaluate(q('#reader-citation-picker')+'.value'),printed.id);
    assert.equal(await evaluate('document.querySelectorAll("#page-content .source-plane svg rect").length'),printed.rects.length);
  }
  await click(control);await located();await evaluate(q('#page-dialog')+'.close()');
  const checks=await evaluate('(()=>{return ["coords","source","support","status","scope","method","doc"].map(mode=>{'+
    'const p=structuredClone(state.bundle.report),i=p.findings.find(x=>x.id==='+JSON.stringify(id)+'),c=i.inspection_use,'+
    'r=p.graph.inspection_use_sources.rows.find(r=>r.id===c.notes[0].row);'+
    'if(mode==="coords")p.calls.pages.find(v=>v.doc===r.doc && v.page===r.page).inspection_use_rects[r.line]=[];'+
    'if(mode==="source")p.graph.edges=p.graph.edges.filter(e=>e.type!=="inspection_use_source");'+
    'if(mode==="support")p.graph.edges=p.graph.edges.filter(e=>!(e.type==="supports_result" && e.from===r.id));'+
    'if(mode==="status")c.state=c.state==="ban"?"other_stage":"ban";'+
    'if(mode==="scope")c.notes[0].scope=c.notes[0].scope==="cited"?"other_document":"cited";'+
    'if(mode==="method")delete p.policy.code_sha256["inspection_use.py"];if(mode==="doc")c.cited="d99";'+
    'return InspectionUse.bind(i,p)===null})})()');
  assert.deepEqual(checks,Array(7).fill(true));
  const approvalControl=r=>approvalCard+'-'+r.doc+'-p'+r.page+'-l'+r.line;
  if (a?.fields) {
    assert.equal(await evaluate(q(approvalCard)+'.dataset.approvalState'),a.state);
    if (term) await click(approvalCard+' > details > summary');
    for (const key of ['stage','inspection','decision','date']) {
      const raw=approvalRows.find(r=>r.id===a.fields[key]);
      await click(approvalControl(raw));await located(false,raw);await evaluate(q('#page-dialog')+'.close()');
    }
    if (term) await click(approvalCard+' > details > summary');
    const failed=await evaluate('["state","coordinates","link","decision","paid","method","omitted"].map(mode=>{'+
      'const p=structuredClone(state.bundle.report),i=p.findings.find(f=>f.id==='+JSON.stringify(id)+'),c=i.inspection_use,a=c.approval;'+
      'const r=p.graph.inspection_use_sources.approvals.flatMap(s=>s.rows).find(r=>r.id===a.fields.decision);'+
      'if(mode==="state")a.state=a.state==="later"?"earlier":"later";if(mode==="paid")a.paid_on="2001-01-01";'+
      'if(mode==="coordinates")p.calls.pages.find(v=>v.doc===r.doc && v.page===r.page).inspection_use_rects[r.line]=[];'+
      'if(mode==="link")p.graph.edges=p.graph.edges.filter(e=>!(e.type==="compares_payment_approval"&&e.to===r.id));'+
      'if(mode==="decision")a.fields.decision=a.fields.stage;if(mode==="method")delete p.policy.code_sha256["installment_approval.py"];'+
      'if(mode==="omitted")delete c.approval;return InspectionUse.bind(i,p)===null})');
    assert.deepEqual(failed,Array(7).fill(true));
  }
  if (time) {
    assert.equal(await evaluate(q(approvalCard)+'.dataset.clock'),clock.state);
    const signature=approvalRows.find(r=>r.id===clock.signed);
    if (signature) {await click(approvalControl(signature));await located(false,signature);await evaluate(q('#page-dialog')+'.close()');}
    const invalid=await evaluate('["status","method","event","source","precision","timezone","omitted","notes","citation","relationship"].map(mode=>{'+
      'const p=structuredClone(state.bundle.report),i=p.findings.find(f=>f.id==='+JSON.stringify(id)+'),a=i.inspection_use.approval,v=a.clock,'+
      'r=p.graph.inspection_use_sources.bank_clocks.flatMap(b=>b.rows).find(r=>v.rows.includes(r.id));'+
      'if(mode==="status")v.state=v.state==="debit_first"?"approval_first":"debit_first";'+
      'if(mode==="method")delete p.policy.code_sha256["approval_clock.py"];if(mode==="event")r.field=r.field==="debit_time"?"bank_event":"debit_time";'+
      'if(mode==="source")p.graph.edges=p.graph.edges.filter(e=>e.type!=="payment_clock_source");'+
      'if(mode==="precision")v.debited_at="00:34:00";if(mode==="timezone")v.zone="+00:00";if(mode==="omitted")delete a.clock;'+
      'if(mode==="notes")delete i.retest_reference.timing_notes;if(mode==="citation")i.retest_reference.citations.push(r.id);'+
      'if(mode==="relationship"){const es=p.graph.edges,link=es.find(e=>e.type==="compares_debit_time");'+
      'if(link)link.to=v.signed;else es.push({type:"compares_debit_time",from:v.signed,to:r.id,evidence:[a.request,i.inspection_use.citation,v.signed,r.id]})}'+
      'return InspectionUse.bind(i,p)===null})');
    assert.deepEqual(invalid,Array(10).fill(true));
  }
  if (term) {
    assert.equal(await evaluate(q(base)+'.dataset.nameState'),names.state);
    const signer=approvalRows.find(r=>r.id===names.signed_by);
    if (signer) {
      const button=approvalControl(signer);
      assert.equal(await evaluate(q(button+' strong')+'.textContent'),names.listed?.join('、') || signer.quote);
      await click(button);await located(false,signer);await evaluate(q('#page-dialog')+'.close()');
    }
    const invalid=await evaluate('["method","scope","raw","who","range","source","link","coords","required","listed","status","omitted"].map(mode=>{'+
      'const p=structuredClone(state.bundle.report),i=p.findings.find(f=>f.id==='+JSON.stringify(id)+'),a=i.inspection_use.approval,x=a.names,'+
      'r=p.graph.inspection_use_sources.approver_terms.flatMap(v=>v.rows).find(r=>x.rows.includes(r.id));'+
      'if(mode==="method")delete p.policy.code_sha256["approval_names.py"];if(mode==="scope")x.state=x.state==="listed"?"different":"listed";'+
      'if(mode==="who")x.signed_by=a.fields.authority;if(mode==="range")x.contract_fields.buyer=x.contract_fields.seller;'+
      'if(mode==="source")p.graph.edges=p.graph.edges.filter(e=>e.type!=="contract_approver_source");'+
      'if(mode==="link"){const es=p.graph.edges;if(es.some(e=>e.type==="compares_approval_names"))p.graph.edges=es.filter(e=>e.type!=="compares_approval_names");'+
      'else es.push({type:"compares_approval_names",from:r.id,to:x.signed_by,evidence:[i.inspection_use.citation]})}'+
      'if(mode==="raw")r.quote=r.quote.replace("第二期","第三期");if(mode==="coords")r.rects=[];'+
      'if(mode==="required")x.required=["周湘"];if(mode==="listed")x.listed=["周湘"];'+
      'if(mode==="status")a.status=a.status==="risk"?"missing":"risk";if(mode==="omitted")delete a.names;'+
      'return InspectionUse.bind(i,p)===null})');
    assert.deepEqual(invalid,Array(12).fill(true));
  }
  for (const width of [320,390,768,820,1024,1440]) {
    await size(ctx,width);
    assert.ok(await evaluate('(()=>{const b='+q(control)+'.getBoundingClientRect();return b.width>=44 && b.height>=44 && b.left>=-1 && b.right<=innerWidth+1})()'));
    await inspect(ctx,width,card,'inspection-use-'+cid.slice(0,8)+'-R'+rev);
  }
  if (process.env.AUDIT_ISOLATED_USE_ORIGIN) {
    assert.equal(root,process.env.AUDIT_ISOLATED_USE_ORIGIN);
    assert.ok(!['8000','8010'].includes(new URL(root).port));assert.deepEqual((await json('/api/walkthrough')).notes,[]);
    await size(ctx,390);
    const cardNote=term?'建议把合同点名的人和审批单列的人并排呈现。':time?'希望这两个时刻同时注明各自来自哪张单据。':row.field?'建议在审批日期旁显示银行扣款日。':'建议付款检查并排显示这句用途限制和实际审批依据。';
    const pageNote=term?'希望在这条共同签批约定旁能看到本期审批单。':time?'建议从银行回单的这一行直接跳到签批原件。':'希望从原件这一行也能回看付款审批。';
    async function compose(text,pick) {
      await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','compose on site');
      await evaluate(q('#walk-text')+'.value='+JSON.stringify(text)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
      if (pick) {
        await click('#walk-pick');await browserInput(ctx).tap(q(pick));
        await wait(q('#walk-dialog')+'?.open && '+q(pick)+'.classList.contains("walk-selected")','select printed condition');
        await inspect(ctx,390,'#walk-dialog','inspection-use-feedback');
      }
      await click('#walk-save');await wait('!'+q('#walk-dialog')+'.open','persist feedback');
    }
    const notebook=async()=>{
      await go(root+'/app#desk');await wait(visible('#desk')+' && '+visible('body > #walk-launch'),'workbench');
      await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-saved')+'.disabled','notebook');
      await click('#walk-saved');await wait(visible('#walk-history li a'),'saved links');
    };
    await compose(cardNote,control);await click(control);await located();await compose(pageNote);
    const notes=(await json('/api/walkthrough')).notes;assert.equal(notes.length,2);
    const a=notes.find(n=>n.text===cardNote).context, b=notes.find(n=>n.text===pageNote).context;
    assert.deepEqual([a.case_id,a.rev,a.anchor,a.target,a.params],[cid,rev,control.slice(1),label,{view:'payment-checks',stage:id}]);
    assert.deepEqual([b.case_id,b.rev,b.doc,b.page,b.line,b.raw_ref],[cid,rev,row.doc,row.page,row.line,row.id]);
    const prior=rev>1 && (await json(api+'/reports/'+(rev-1))).report.findings.find(f=>f.id===id);
    const filed=prior?.inspection_use;
    const absent=prior && !filed?.notes.some(n=>n.row===row.id) && !filed?.approval?.rows.includes(row.id) &&
      !filed?.approval?.clock?.rows.includes(row.id) && !filed?.approval?.names?.rows.includes(row.id) ? rev-1 : task.rev+1;
    for (const [context,status] of [[{...a,rev:absent},404],[{...a,anchor:base.slice(1)+'-'+row.doc+'-p1-l1'},404],
      [{...a,params:{view:'payment-checks',stage:'H05-999'}},400],[{...b,line:1},400],[{...b,rev:absent},404]]) {
      const r=await fetch(root+'/api/walkthrough',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({id:'3'.repeat(32),context,text:cardNote})});assert.equal(r.status,status);
    }
    await notebook();
    await evaluate('Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:async t=>{window.copiedNotes=t}});true');
    await browserInput(ctx).tap(q('#walk-copy'));await wait('typeof window.copiedNotes==="string"','copy to Codex');
    const copy=await evaluate('window.copiedNotes');
    for (const text of [cardNote,pageNote,label,'walkline','walkraw']) assert.ok(copy.includes(text));
    await click('#walk-history a[href*="walkat='+base.slice(1)+'"]');
    await wait(visible(control)+' && '+q(control)+'.classList.contains("walk-mark")','same archived control');
    await notebook();await click('#walk-history a[href*="walkraw="]');await located(true);
    await size(ctx,1440);await go(fixed+'&view=payment-checks&stage='+id);
    await wait(visible(control)+' && '+visible('#performance-index #walk-launch'),'filed clause');
    const mouse=s=>browserInput(ctx).click(q(s));
    const fill=msg=>evaluate(q('#walk-text')+'.focus();'+q('#walk-text')+'.value='+JSON.stringify(msg)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
    const docked=owner=>q(owner+' #walk-rail')+'?.matches(":popover-open")';
    await mouse('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-dock')+'.disabled','compose on the installment');
    await mouse('#walk-dock');await wait(docked('#performance-index'),'side-by-side installment');
    await mouse('#walk-pick');await mouse(control);
    await wait(q(control)+'.classList.contains("walk-selected") && '+q('#walk-location')+'.textContent.includes('+JSON.stringify(label)+')','pin the filed clause');
    const alongside=term?'核对签批人时，希望能直接看到两份原件的人名。':time?'希望一眼看出这笔钱是在签批前还是签批后扣除。':row.field?'希望直接看到审批日期和付款日期相差几天。':'希望在这个付款条件旁直接对照审批单上的期次。';
    await fill(alongside);await mouse(control);await located();
    await wait(docked('#page-dialog'),'continue writing beside the open original');
    assert.ok(await evaluate(q('#page-dialog')+'.getBoundingClientRect().right<='+q('#walk-rail')+'.getBoundingClientRect().left'),'original page fits to the left of the recorder');
    assert.equal(await evaluate(q('#walk-text')+'.value'),alongside);
    assert.ok((await evaluate(q('#walk-location')+'.textContent')).includes(label));
    await inspect(ctx,1440,'#walk-rail','walkthrough-approval-side-by-side');
    await mouse('#walk-save');await wait(q('#walk-status')+'.textContent.includes("已保存")','first opinion filed, next one points to the open page');
    assert.match(await evaluate(q('#walk-location')+'.textContent'),new RegExp('第 '+row.line+' 行'));
    const sourceNote='这行审批说明需要对照银行回单。';
    await fill(sourceNote);await mouse('#walk-save');await wait(q('#walk-saved span')+'.textContent==="4"','second opinion filed without closing the side panel');
    const sideNotes=(await json('/api/walkthrough')).notes;
    assert.deepEqual(sideNotes.find(n=>n.text===alongside).context,a);
    assert.deepEqual(sideNotes.find(n=>n.text===sourceNote).context,b);
    const draft='回到审批说明再确认一次。';
    await fill(draft);await mouse('#page-dialog [data-close]');await wait(docked('#performance-index'),'close only the PDF');
    assert.equal(await evaluate(q('#walk-text')+'.value'),draft);
    await mouse(control);await located();await wait(docked('#page-dialog'),'open the same original again');
    await size(ctx,820);await wait(q('#walk-dialog')+'.matches(":modal")','resize the draft on the original');
    await browserInput(ctx).key('Escape');await wait('!'+q('#walk-dialog')+'.open && '+q('#page-dialog')+'.open','dismiss feedback alone');
    await mouse('#walk-launch');await wait(q('#walk-dialog')+'.open && '+q('#walk-text')+'.value==='+JSON.stringify(draft),'draft remains bound to this PDF line');
    await mouse('#walk-saved');await mouse('#walk-history a[href*="walkraw="]');await located(true);
    if (term && names.signed_by) {
      const signer=approvalRows.find(r=>r.id===names.signed_by), field=approvalControl(signer);
      await size(ctx,390);await go(fixed+'&view=payment-checks&stage='+id);
      await wait(visible(field),'approval sheet signer on the other side of the comparison');
      const fieldNote='审批单具名栏这里，希望能直接核对实际签批记录。', lineNote='请在具名栏原行旁显示本版合同所列的签批人。';
      await compose(fieldNote,field);await click(field);await located(false,signer);await compose(lineNote);
      const notes=(await json('/api/walkthrough')).notes;
      assert.equal(notes.find(n=>n.text===fieldNote).context.anchor,field.slice(1));
      assert.equal(notes.find(n=>n.text===lineNote).context.raw_ref,signer.id);
      await notebook();await click('#walk-history a[href*="walkat='+field.slice(1)+'"]');
      await wait(q(field)+'?.classList.contains("walk-mark")','back on the issued signer field');
      await notebook();await click('#walk-history a[href*="walkline='+signer.line+'"][href*="walkraw="]');await located(true,signer);
    }
    const after=await json(api);assert.deepEqual([after.status,after.rev,after.decisions,after.referrals],[task.status,task.rev,task.decisions,task.referrals]);
  }
  await go(fixed+'&finding='+id);
  await wait(q('#trace-select')+'?.value==='+JSON.stringify(id),'payment finding in the evidence graph');
  const details='.trace-modes [data-mode="details"]';
  if (await evaluate(visible(details))) await click(details);
  const trace='#trace-details [data-use-ref="'+row.id+'"]';
  await wait(visible(trace),'original payment-use row in the finding trace');
  await click(trace);await located();
  if (term) {
    await evaluate(q('#page-dialog')+'.close()');
    const stage=report.findings.find(f=>f.rule==='H04' && f.stage_approvers?.includes(term.id));
    await go(fixed+'&finding='+stage.id);
    await wait(q('#trace-select')+'?.value==='+JSON.stringify(stage.id),'contract names on the relevant payment condition');
    if (await evaluate(visible(details))) await click(details);
    await wait(visible(trace),'contract name clause on the scheduled installment');await click(trace);await located(false,term);
  }
  console.log('PASS · R'+rev+' · '+c.state+' · original PDF line '+row.line+' · six widths'+(process.env.AUDIT_ISOLATED_USE_ORIGIN?' · recorded, exported and reopened both positions':''));
}
