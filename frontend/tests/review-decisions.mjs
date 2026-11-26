import assert from 'node:assert/strict';
import {browserInput, inspect, size} from './review-screen.mjs';

const q = selector => 'document.querySelector('+JSON.stringify(selector)+')';
const button = (container, label) => '[...document.querySelectorAll('+JSON.stringify(container+' button')+')].find(b=>b.textContent==='+JSON.stringify(label)+')';

export async function checkReviewDecisions(ctx, id) {
  const {root,call,evaluate,wait}=ctx;
  const task = await (await fetch(root+'/api/cases/'+id)).json();
  assert.ok(task.title.startsWith('合成演练 · ') && task.status==='ready');
  const bundle = await (await fetch(root+'/api/cases/'+id+'/reports/'+task.rev)).json();
  const facts = bundle.report.graph.facts;
  const file = facts.find(f=>facts.filter(g=>g.doc===f.doc && g.page===f.page).length>=2);
  assert.ok(file);
  const pair = facts.filter(f=>f.doc===file.doc && f.page===file.page).slice(0,2);
  const url=root+'/workpaper/'+id+'?rev='+task.rev;
  const open=button('#content','填写验收意见');
  const selected=q('#review-form')+'.elements.decision.value';
  const decision=value=>q('#review-decision input[value='+value+']');
  const {key,tap}=browserInput(ctx);
  // Exercise the request body and the conflict UI without recording decisions on the shared sample.
  await call('Network.enable');
  await call('Network.setBlockedURLs',{urls:['*/signoff','*/attest']});
  const intercept = `(()=>{
    const read=window.fetch;
    window.reviewRequests=[];
    window.fetch=(url,init={})=>{
      if (!init.method || ['GET','HEAD'].includes(init.method)) return read(url,init);
      const decision=JSON.parse(init.body);
      window.reviewRequests.push({url:String(url),decision});
      return Promise.resolve(Response.json({error:'合成演练的版本冲突',invoice_history:{changes:[],count:0}},{status:409}));
    };
    return Array.isArray(window.reviewRequests);
  })()`;
  for (const width of [320,360,390,768,1024,1440]) {
    await call('Page.navigate',{url});
    await wait('Boolean('+open+')','ready watermarked workpaper');
    assert.ok(await evaluate(intercept));
    await size(ctx,width);
    await call('Emulation.setTouchEmulationEnabled',{enabled:width<600});
    await evaluate(open+'.focus();'+open+'.click()');
    await wait(q('#review-dialog')+'.open','signoff dialog');
    assert.equal(await evaluate(selected),'');
    assert.equal(await evaluate(q('#review-context .review-version')+'.textContent'),'R'+task.rev);
    assert.equal(await evaluate(q('#review-context [data-state]')+'.dataset.state'),bundle.report.result.verdict);
    assert.ok(await evaluate(q('#review-dialog')+'.scrollWidth<='+q('#review-dialog')+'.clientWidth+1'));
    await evaluate(q('#reviewer')+'.value="水印演练核验员";'+q('#review-note')+'.value="请补充委托方签发记录。";'+q('#review-form')+'.requestSubmit()');
    assert.equal(await evaluate('reviewRequests.length'),0);
    if (width===390) {
      await tap(q('#review-decision label:has(input[value=return])'));
    } else {
      await evaluate(decision('approve')+'.focus()');
      for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
    }
    assert.equal(await evaluate(selected),'return');
    assert.equal(await evaluate(q('#review-note-label')+'.textContent'),'需补资料与原因');
    assert.equal(await evaluate(q('#submit-review')+'.textContent'),'确认退回补件');
    await inspect(ctx,width,'#review-dialog','signoff-decisions');
    if (width===1440) {
      await evaluate(decision('approve')+'.click();'+q('#review-form')+'.requestSubmit()');
      await wait(decision('approve')+'.disabled','refused approval');
      assert.equal(await evaluate('reviewRequests[0].decision.rev'),task.rev);
      assert.equal(await evaluate('reviewRequests[0].decision.decision'),'approve');
      assert.equal(await evaluate(selected),'');
      assert.equal(await evaluate(q('#review-note')+'.value'),'请补充委托方签发记录。');
      await evaluate(decision('escalate')+'.click()');
      assert.equal(await evaluate(q('#submit-review')+'.textContent'),'确认提交复核');
    }
    await key('Escape');
    assert.ok(await evaluate('!'+q('#review-dialog')+'.open && document.activeElement==='+open));
    await call('Page.navigate',{url:url+'&fact='+encodeURIComponent(pair[0].id)});
    await wait(q('#page-dialog')+'?.open && !!'+q('#page-dialog input[type=checkbox]'),'source field');
    for (const f of pair) {
      const group=q('#page-dialog .evidence-row[data-fact="'+f.id+'"]');
      const picker=q('#reader-citation-picker');
      await evaluate(picker+'.value='+JSON.stringify(f.id)+';'+picker+'.dispatchEvent(new Event("change"))');
      const checkbox=group+'.querySelector("input")';
      await wait(checkbox+'?.getClientRects().length && !'+checkbox+'.disabled','visible source choice');
      if (!await evaluate(checkbox+'.checked')) {
        if (width===390) await tap(checkbox); else await evaluate(checkbox+'.click()');
      }
    }
    const record=button('#page-dialog','记录所选引文的核图意见');
    await evaluate(record+'.focus();'+record+'.click()');
    await wait(q('#review-dialog')+'.open','field decision');
    assert.equal(await evaluate(selected),'');
    assert.ok(await evaluate('!'+q('#review-context details')+'.open'));
    assert.equal(await evaluate(q('#review-context summary')+'.textContent'),'核对所选 2 条引文');
    await evaluate(q('#review-context summary')+'.click();'+decision('dispute')+'.click()');
    const links = await evaluate('[...document.querySelectorAll(".review-source-list a")].map(a=>[a.href,a.target])');
    assert.deepEqual(links,pair.map(f=>[url+'&fact='+encodeURIComponent(f.id),'_blank']));
    assert.equal(await evaluate(q('#review-note-label')+'.textContent'),'异议内容与依据');
    await inspect(ctx,width,'#review-dialog','field-decisions');
    await key('Escape');
    await wait('!'+q('#review-dialog')+'.open','dismiss field decision');
    const returned=await evaluate('['+q('#page-dialog')+'.open,document.activeElement==='+record+',document.activeElement?.textContent.slice(0,50)]');
    assert.deepEqual(returned.slice(0,2),[true,true],JSON.stringify(returned));
    assert.equal(await evaluate('document.querySelectorAll("#page-dialog .evidence-row input:checked").length'),2);
  }
  console.log('PASS · Six widths, explicit signoff, native keyboard and touch choices, refusal with preserved note, pinned field quotes');
}
