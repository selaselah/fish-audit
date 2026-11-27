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
  const proof=c.notes[0], row=report.graph.inspection_use_sources.rows.find(r=>r.id===proof.row);
  const doc=report.graph.documents.find(d=>d.id===row.doc), control=card+'-'+row.doc+'-p'+row.page+'-l'+row.line;
  assert.equal(await evaluate(q(control)+'.dataset.scope'),proof.scope);
  assert.equal(await evaluate(q(control+' strong')+'.textContent'),row.quote);
  const label=await evaluate(q(control)+'.dataset.originalLabel');
  assert.ok(label.includes(doc.name) && label.includes('第 '+row.line+' 行'));
  async function located(fromHistory=false) {
    const sel='#page-content .evidence-row.located';
    const route=fromHistory?'state.openedCitation===location.hash && Team.route().params.get("walkraw")==='+JSON.stringify(row.id)+' && ':'';
    await wait(route+q('#page-dialog')+'?.open && '+q(sel)+'?.dataset.sourceRef==='+JSON.stringify(row.id)+' && '+q('#page-content img')+'?.naturalWidth>0','original payment-use row and page image');
    assert.equal(await evaluate(q(sel+' blockquote')+'.textContent'),row.quote);
    assert.equal(await evaluate(q('#page-content .page-view')+'.dataset.doc'),row.doc);
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    assert.equal(await evaluate(q('#reader-citation-picker')+'.value'),row.id);
    assert.equal(await evaluate('document.querySelectorAll("#page-content .source-plane svg rect").length'),row.rects.length);
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
  for (const width of [320,390,768,820,1024,1440]) {
    await size(ctx,width);
    assert.ok(await evaluate('(()=>{const b='+q(control)+'.getBoundingClientRect();return b.width>=44 && b.height>=44 && b.left>=-1 && b.right<=innerWidth+1})()'));
    await inspect(ctx,width,card,'inspection-use-'+cid.slice(0,8)+'-R'+rev);
  }
  if (process.env.AUDIT_ISOLATED_USE_ORIGIN) {
    assert.equal(root,process.env.AUDIT_ISOLATED_USE_ORIGIN);
    assert.ok(!['8000','8010'].includes(new URL(root).port));assert.deepEqual((await json('/api/walkthrough')).notes,[]);
    await size(ctx,390);
    const cardNote='建议付款检查并排显示这句用途限制和实际审批依据。', pageNote='希望从原件这一行也能回看付款审批。';
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
    const absent=prior && !prior.inspection_use?.notes.some(n=>n.row===row.id) ? rev-1 : task.rev+1;
    for (const [context,status] of [[{...a,rev:absent},404],[{...a,anchor:card.slice(1)+'-'+row.doc+'-p1-l1'},404],
      [{...a,params:{view:'payment-checks',stage:'H05-999'}},400],[{...b,line:1},400],[{...b,rev:absent},404]]) {
      const r=await fetch(root+'/api/walkthrough',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({id:'3'.repeat(32),context,text:cardNote})});assert.equal(r.status,status);
    }
    await notebook();
    await evaluate('Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:async t=>{window.copiedNotes=t}});true');
    await browserInput(ctx).tap(q('#walk-copy'));await wait('typeof window.copiedNotes==="string"','copy to Codex');
    const copy=await evaluate('window.copiedNotes');
    for (const text of [cardNote,pageNote,label,'walkline','walkraw']) assert.ok(copy.includes(text));
    await click('#walk-history a[href*="walkat=inspection-use-"]');
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
    const alongside='希望在这个付款条件旁直接对照审批单上的期次。';
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
    const after=await json(api);assert.deepEqual([after.status,after.rev,after.decisions,after.referrals],[task.status,task.rev,task.decisions,task.referrals]);
  }
  await go(fixed+'&finding='+id);
  await wait(q('#trace-select')+'?.value==='+JSON.stringify(id),'payment finding in the evidence graph');
  const details='.trace-modes [data-mode="details"]';
  if (await evaluate(visible(details))) await click(details);
  const trace='#trace-details [data-use-ref="'+row.id+'"]';
  await wait(visible(trace),'original payment-use row in the finding trace');
  await click(trace);await located();
  console.log('PASS · R'+rev+' · '+c.state+' · original PDF line '+row.line+' · six widths'+(process.env.AUDIT_ISOLATED_USE_ORIGIN?' · recorded, exported and reopened both positions':''));
}
