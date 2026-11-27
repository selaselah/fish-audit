import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

export async function checkBoardDecision(ctx,cid) {
  const {root,call,evaluate,wait}=ctx;
  const json=async path=>{const r=await fetch(root+path);assert.equal(r.status,200);return r.json();};
  const base='/api/cases/'+cid, task=await json(base);assert.match(task.title,/合成演练/);
  const {report,rev}=await json(base+'/reports/'+(process.env.AUDIT_BOARD_REV || task.rev));
  const h=report.findings.find(f=>f.rule==='H01'),b=h.effect_review?.board_decision, fixed=root+'/workpaper/'+cid+'?rev='+rev+'&view=board-decision';
  const q=s=>'document.querySelector('+JSON.stringify(s)+')';
  const click=s=>evaluate(q(s)+'.click()'),visible=s=>q(s)+'?.getClientRects().length';
  const go=url=>call('Page.navigate',{url});
  if (b) {
    await go(root+'/workpaper/'+cid+'?rev='+rev);
    await wait(visible('[data-audit-scope=contract]'),'ordinary contract review');
    await click('[data-audit-scope=contract]');
    const jump='#performance-index .scope-actions a';
    await wait(visible(jump),'board filing link in contract review');
    assert.equal(new URL(await evaluate(q(jump)+'.href')).searchParams.get('view'),'board-decision');
    await click(jump);
    await wait(q('#board-decision')+'?.dataset.rev==='+JSON.stringify(String(rev))+' && !'+q('#performance-index')+'.open','board from ordinary review');
  } else await go(fixed);
  if (!b) {
    await wait(visible('#board-unavailable'),'board decision missing in the selected revision');
    assert.equal(await evaluate(q('#board-decision')),null);
    const missing=await evaluate('import("/assets/walkthrough-context.js").then(m=>{const c=m.captureContext(null,'+q('#board-unavailable')+');return {c,url:m.returnUrl(c)}})');
    assert.deepEqual(missing.c.params,{view:'board-decision'});assert.equal(missing.c.rev,rev);
    await go(root+missing.url);await wait(q('#board-unavailable')+'?.classList.contains("walk-mark")','returned to the missing evidence message');
    console.log('PASS · absent R'+rev);return;
  }
  const records=[...report.graph.board_pdf_sources.records,...report.graph.board_original_sources.records].filter(r=>b.records.includes(r.id));
  assert.ok(records.length);
  const record=records[0],file=fixed+'&filing='+encodeURIComponent(record.unit);
  await wait(q('#board-decision')+'?.dataset.boardFiling==='+JSON.stringify(record.unit),'bound board filing');
  assert.equal(await evaluate(q('#board-decision')+'.dataset.state'),record.state);
  assert.ok(await evaluate(visible('#board-decision')));
  if (b.fields.approval_result) {
    const fact=report.graph.facts.find(f=>f.id===b.fields.approval_result), button='#board-decision [data-board-field=approval_result]';
    assert.equal(await evaluate(q(button)+'.previousElementSibling.textContent'),fact.source_line.text);
    await click(button);await wait(q('#page-dialog')+'.open && '+q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(fact.id),'approval original line');
    await evaluate(q('#page-dialog')+'.close()');
  }
  await click('#board-tab-signing');
  const card='#board-decision', tab=q(card)+'.dataset.boardPart';
  assert.equal(await evaluate(tab),'signing');
  const note=report.graph.board_original_sources.documents.flatMap(d=>d.notes).find(n=>record.notes?.includes(n.id));
  if (note) {
    assert.equal(await evaluate(q('[data-board-note] blockquote')+'.textContent'),note.text);
    if (note.location) {
      await click('[data-board-note] button');await wait(q('#page-dialog')+'.open && '+q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(note.location.facts[0]),'Word comment original');
      await evaluate(q('#page-dialog')+'.close()');
    }
  }
  if (record.signatures?.length) assert.equal(await evaluate(q('#board-decision .pdf-timeline')+'.dataset.state'),record.signatures[0].state);
  const footer=await evaluate(q('#board-decision .release-file-actions a:last-child')+'.href');
  assert.ok(footer.includes('rev='+rev) && footer.includes('part=signing'));
  await click('#board-decision .agreement-check button');
  await wait(q('#board-decision .agreement-check')+'?.dataset.state==="match"','original file agrees with the archived SHA-256');
  const target=note?'[data-board-note] button':'#board-decision .warranty-file';
  const feedback=await evaluate('import("/assets/walkthrough-context.js").then(m=>{const c=m.captureContext(null,'+q(target)+');return {c,url:m.returnUrl(c)}})');
  assert.deepEqual(feedback.c.params,{view:'board-decision',filing:record.unit,part:'signing'});
  assert.equal(feedback.c.rev,rev);
  for (const width of [320,390,768,1024,1440]) {
    await size(ctx,width);
    assert.ok(await evaluate('[...'+q(card)+'.querySelectorAll("button,a,select,summary")].filter(n=>n.getClientRects().length).every(n=>n.getBoundingClientRect().right<=innerWidth+1)'));
    await inspect(ctx,width,card,'board-'+cid.slice(0,8)+'-'+record.state);
  }
  let delayed;
  if (process.env.AUDIT_BOARD_RESILIENCE) {
    delayed=await call('Page.addScriptToEvaluateOnNewDocument',{source:`
      const ordinary=window.fetch;
      window.fetch=async (...args)=>{
        const response=await ordinary(...args);
        if (String(args[0]).includes('/reports/'+${rev})) await new Promise(done=>setTimeout(done,6500));
        return response;
      };`});
  }
  await go(root+feedback.url);
  await wait(q(target)+'?.classList.contains("walk-mark") && '+visible(target),'return to the same filing and control');
  if (delayed) await call('Page.removeScriptToEvaluateOnNewDocument',{identifier:delayed.identifier});
  if (process.env.AUDIT_ISOLATED_BOARD_ORIGIN) {
    assert.ok(note?.location);
    assert.deepEqual((await json('/api/walkthrough')).notes,[]);
    await size(ctx,390);
    await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','open recorder');
    await evaluate(q('#walk-text')+'.value="希望在审批决定旁也能看到这条另行表决的批注。";'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
    await click('#walk-pick');await click(target);
    await wait(q('#walk-dialog')+'.open && '+q(target)+'.classList.contains("walk-selected")','pick the board comment link');
    await inspect(ctx,390,'#walk-dialog','board-feedback');
    await click('#walk-save');await wait('!'+q('#walk-dialog')+'.open','saved');
    await go(root+'/app#desk');await wait(visible('#case-list')+' && '+visible('#walk-launch'),'desk');
    await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-saved')+'.disabled','review history');
    await click('#walk-saved');await wait(visible('#walk-history li a'),'saved note');
    const label=await evaluate(q('#walk-history li a')+'.textContent');
    const filename=report.graph.documents.find(d=>d.id===record.doc).name;
    assert.ok(['董事会签发版本',filename,'原批注','第 '+note.location.line+' 行'].every(text=>label.includes(text)));
    await click('#walk-history li a');await wait(q(target)+'?.classList.contains("walk-mark") && '+visible(target),'reopened from desk');
    assert.equal(await evaluate(tab),'signing');
    const [saved]=(await json('/api/walkthrough')).notes;
    assert.deepEqual(saved.context.params,feedback.c.params);assert.equal(saved.context.anchor,feedback.c.anchor);
    await click(target);await wait(q('#page-dialog')+'.open && '+q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(note.location.facts[0]),'saved note to decision row');
    await evaluate(q('#page-dialog')+'.close()');
    await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','recorder for the comment text');
    await evaluate(q('#walk-text')+'.value="希望能在正文旁展开这条批注。";'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
    await click('#walk-pick');await click('[data-board-note] blockquote');
    await wait(q('[data-board-note]')+'.classList.contains("walk-selected")','point to the original comment text');
    await click('#walk-save');await wait('!'+q('#walk-dialog')+'.open','saved the comment text as a target');
    const notes=(await json('/api/walkthrough')).notes;
    assert.equal(notes.length,2);assert.equal(notes[0].context.anchor,await evaluate(q('[data-board-note]')+'.id'));
    assert.ok(notes[0].context.target.includes(filename) && notes[0].context.target.includes('原批注'));
    await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-saved')+'.disabled','review both recorded opinions');
    await click('#walk-saved');await wait(visible('#walk-copy'),'copy list');
    await evaluate('Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:async content=>{window.boardClipboard=content}});true');
    await browserInput(ctx).tap(q('#walk-copy'));
    await wait('typeof window.boardClipboard==="string"','Codex handoff');
    const copy=await evaluate('window.boardClipboard');
    for (const n of notes) {
      assert.ok(copy.includes(n.text) && copy.includes(n.context.anchor) && copy.includes(n.context.target));
    }
    await click('#walk-close');
    const end=await json(base);assert.deepEqual([end.rev,end.status,end.decisions],[task.rev,task.status,task.decisions]);
  }
  await click('#board-tab-payments');assert.equal(await evaluate(tab),'payments');
  const phases=report.findings.filter(f=>['H04','H05'].includes(f.rule) && f.scope.includes(record.unit) && f.evidence.includes(record.id));
  assert.deepEqual(await evaluate('[...'+q(card)+'.querySelectorAll(".board-payment a")].map(n=>new URL(n.href).searchParams.get("finding"))'),phases.map(f=>f.id));
  if (phases.length) {
    await click('#board-decision .board-payment a');await wait('state.traceId==='+JSON.stringify(phases[0].id)+' && state.bundle?.rev==='+rev,'related issued installment');
  }
  await go(file+'&part=decision');await wait(q(card)+'?.dataset.boardPart==="decision"','fixed decision');
  await click('#board-decision .warranty-file');await wait(q('#page-dialog')+'.open && '+q('#page-dialog img')+'?.naturalWidth>0 && '+q('#page-content .page-view')+'?.dataset.doc==='+JSON.stringify(record.doc),'archived filing page');
  assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
  await go(fixed+'&filing=d99&part=signing');await wait(q(card)+'?.textContent.includes("本版没有所选")','unknown filing stays unresolved');
  assert.equal(await evaluate(q('#board-decision')+'.dataset.boardFiling'),undefined);
  console.log('PASS · R'+rev+' · '+record.state+' · originals, installments, fixed feedback, five widths');
}
