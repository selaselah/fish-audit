import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

export async function checkContractSigningForm(ctx,cid) {
  const {root,call,evaluate,wait}=ctx;
  const isolated=process.env.AUDIT_ISOLATED_FORM_ORIGIN;
  if (isolated) {
    assert.equal(isolated,root);
    assert.ok(!['8000','8010'].includes(new URL(root).port));
  }
  async function get(path) {
    const response=await fetch(root+path);
    assert.equal(response.status,200); return response.json();
  }
  const base='/api/cases/'+cid, task=await get(base);
  assert.match(task.title,/^合成演练 · /u);
  const {report,rev}=await get(base+'/reports/'+(process.env.AUDIT_FORM_REV || task.rev));
  const signed=report.findings.find(f=>f.rule==='H01');
  const accepted=report.findings.find(f=>f.rule==='H02'), pay=report.findings.find(f=>f.rule==='H05');
  const terms=report.findings.find(f=>f.rule==='H04' && f.stage?.name===pay.stage.name);
  assert.ok(terms);
  const rows=signed.effect_review.conditions.filter(r=>r.kind==='signing_form');
  const format=report.policy.contract_effect;
  const sharedClause=format==='contract-effect-sources-v9' && /合同与验收报告均须|验收报告与合同均须/u.test(task.title);
  const shared=sharedClause && report.policy.version!=='2026.11.28.13';
  const expected=sharedClause || ['contract-effect-sources-v8','contract-effect-sources-v9'].includes(format) && /合同另须|董事会已列/u.test(task.title);
  assert.equal(rows.length,expected?1:0);
  assert.deepEqual(accepted.acceptance_signing_requirements || [],shared?[rows[0].id]:[]);
  const [row]=rows, fixed=root+'/workpaper/'+cid+'?rev='+rev;
  const go=url=>call('Page.navigate',{url});
  const q=s=>'document.querySelector('+JSON.stringify(s)+')';
  const click=s=>evaluate(q(s)+'.click()');
  const active=s=>q(s)+'?.getClientRects().length';
  const input=browserInput(ctx);
  const selector=f=>'#form-'+f.id+'-'+row.doc+'-p'+row.page+'-l'+row.line;
  async function phase(f) {
    await go(fixed+'&view=payment-checks&stage='+f.id);
    await wait(q('#performance-index')+'?.open && '+q('.scope-check-select')+'?.value==='+JSON.stringify(f.id),'open original installment '+f.id);
  }
  async function acceptance() {
    await go(fixed+'&view=acceptance-checks');
    await wait(q('#performance-index')+'?.open && '+q('.scope-check-select')+'?.value==='+JSON.stringify(accepted.id),'open delivery acceptance');
  }
  async function checkOriginal() {
    await wait(q('#page-dialog')+'?.open && '+q('#page-content .located')+'?.dataset.sourceRef==='+JSON.stringify(row.id)+' && '+q('#page-content img')+'?.naturalWidth>0','cited contract line');
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    assert.equal(await evaluate(q('#page-content .located blockquote')+'.textContent'),row.quote);
    const filed=report.calls.pages.find(p=>p.doc===row.doc && p.page===row.page).contract_signing_form_rects[row.line];
    const marks=await evaluate('[...document.querySelectorAll("#page-content .source-plane svg rect")].map(r=>["x","y","width","height"].map(k=>Number(r.getAttribute(k))))');
    assert.ok(filed.length);
    assert.deepEqual(marks,filed.map(([l,t,r,b])=>[l,t,r-l,b-t].map(v=>1000*v)));
  }
  async function save(text,target,{docked=false,mobile=false,acceptancePin=false}={}) {
    await click('#walk-launch');
    await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','open recorder');
    if (docked) {
      await input.click(q('#walk-dock'));
      await wait(q('#walk-rail')+'?.matches(":popover-open")','write beside this payment');
    }
    await evaluate(q('#walk-text')+'.value='+JSON.stringify(text)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
    if (target) {
      await click('#walk-pick'); await wait(q('#walk-launch')+'.dataset.picking==="true"','select a control');
      await input.click(q(target)); await wait(q(target)+'.classList.contains("walk-selected")','pin the selected control');
    }
    if (mobile) {
      assert.ok((await evaluate(q('#walk-origin')+'.textContent')).includes('R'+rev));
      assert.equal(await evaluate(q('#walk-location')+'.textContent'),'采购合同.pdf · 第 '+row.page+' 页 · 第 '+row.line+' 行');
      await inspect(ctx,390,'#walk-dialog','signing-form-feedback');
    }
    if (acceptancePin) await inspect(ctx,390,'#walk-dialog','shared-signing-feedback');
    if (docked) await inspect(ctx,1440,'#walk-rail','signing-form-sidebar');
    await click('#walk-save');
    if (docked) {
      await wait(q('#walk-status')+'.textContent==="意见已保存。"','saved while auditing');
      await click('#walk-close');
    } else {
      await wait('!'+q('#walk-dialog')+'.open','save feedback');
    }
    const note=(await get('/api/walkthrough')).notes.find(n=>n.text===text);
    assert.equal(note.context.rev,rev); return note.context;
  }
  async function reopenNote(text,description,copy=false) {
    await go(root+'/app#desk');
    await wait(active('#desk')+' && '+active('#walk-launch'),'open the notebook from the workspace');
    await click('#walk-launch'); await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','open notes');
    await click('#walk-saved');
    const link='[...document.querySelectorAll("#walk-history li")].find(li=>li.querySelector("p")?.textContent==='+JSON.stringify(text)+')?.querySelector("a")';
    await wait(link+'?.getClientRects().length','locate the saved note');
    assert.ok((await evaluate(link+'.textContent')).includes(description));
    const url=await evaluate(link+'.href');
    assert.ok(url.includes(cid) && url.includes('rev='+rev));
    if (copy) {
      await evaluate('Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:async t=>{window.copiedNote=t}});true');
      await input.click(q('#walk-copy'));
      await wait('window.copiedNote?.includes('+JSON.stringify(url)+')','handoff includes a fixed-revision link');
      assert.ok((await evaluate('window.copiedNote')).includes(text));
    }
    await input.click(link);
  }
  for (const width of [320,390,768,820,1024,1440]) {
    await size(ctx,width); await acceptance();
    if (shared) {
      const id=selector(accepted);
      await wait(active(id),'common clause cited by acceptance');
      assert.equal(await evaluate(q(id+' strong')+'.textContent'),row.quote);
      await inspect(ctx,width,id,'shared-signing-acceptance');
      await input.click(q(id)); await checkOriginal();
    } else {
      assert.equal(await evaluate(q('#performance-index [data-form-finding]')+'===null'),true);
    }
    await phase(pay);
    assert.equal(await evaluate(q('#scope-source-field-'+pay.id)+'.labels[0].textContent'),'字段引文');
    if (!expected) {
      assert.equal(await evaluate(q('#performance-index [data-form-finding]')+'===null'),true);
      continue;
    }
    const id=selector(pay);
    await wait(active(id),'printed execution condition on the selected payment');
    assert.equal(await evaluate(q(id+' strong')+'.textContent'),row.quote);
    assert.ok(await evaluate(q(id)+'.getBoundingClientRect().height>=44'));
    await inspect(ctx,width,id,'signing-form-payment');
    await input.click(q(id)); await checkOriginal();
    await inspect(ctx,width,'#page-content .located','signing-form-original');
    await evaluate(q('#page-dialog')+'.close()');
  }
  if (expected) {
    await phase(terms);
    await click(selector(terms)); await checkOriginal();
    await go(fixed+'&view=contract-signing-form');
    await wait(active(selector(signed)),'signature clause in the full workpaper');
    await evaluate(q(selector(signed))+'.focus()'); await input.key('Enter'); await checkOriginal();
    if (isolated) {
      const originalNote='签署原件希望能和代表身份材料并排核对。';
      await size(ctx,390);
      const original=await save(originalNote,null,{mobile:true});
      assert.equal(original.raw_ref,row.id); assert.equal(original.line,row.line);
      await reopenNote(originalNote,'合同签署原行'); await checkOriginal();
      if (shared) {
        await acceptance();
        const note='在验收签署条件旁也要能核对实际签认材料。';
        const pinned=await save(note,selector(accepted),{acceptancePin:true});
        assert.equal(pinned.anchor,selector(accepted).slice(1));
        assert.deepEqual(pinned.params,{view:'acceptance-checks'});
        await reopenNote(note,'验收签署条件',true);
        await wait(q('#performance-index')+'?.open && '+q(selector(accepted))+'?.classList.contains("walk-mark")','restore the acceptance clause');
        const bindings=await evaluate(`(()=>{
          const results=[];
          for(const change of ['node','ledger','accepted','evidence']) {
            const p=structuredClone(state.bundle.report), h=p.findings.find(f=>f.rule==='H02');
            const ref=h.acceptance_signing_requirements[0];
            if(change==='node') delete p.graph.nodes.find(n=>n.id===ref).applies_to;
            if(change==='ledger') delete p.graph.contract_effect_sources.conditions.find(r=>r.id===ref).applies_to;
            if(change==='accepted') h.acceptance_signing_requirements=[];
            if(change==='evidence') h.evidence=h.evidence.filter(s=>s!==ref);
            results.push(contractSigningSources(p,h).length);
          } return results;
        })()`);
        assert.deepEqual(bindings,[0,0,0,0]);
      }
      await size(ctx,1440);
      await go(fixed+'&view=contract-signing-form'); await wait(active(selector(signed)),'open the contract original control');
      const contractNote='请在合同签署条件旁保留页行。';
      const onContract=await save(contractNote,selector(signed));
      assert.deepEqual(onContract.params,{view:'contract-signing-form'});
      await reopenNote(contractNote,'合同签署条件');
      await wait(q(selector(signed))+'?.classList.contains("walk-mark") && '+active(selector(signed)),'restore the original contract control');
      await phase(pay);
      const paymentNote='希望在'+pay.stage.name+'付款这里看到签署人的授权范围。';
      const control=await save(paymentNote,selector(pay),{docked:true});
      assert.equal(control.anchor,selector(pay).slice(1));
      assert.deepEqual(control.params,{view:'payment-checks',stage:pay.id});
      await reopenNote(paymentNote,'实付回单 '+pay.id,true);
      await wait(q('#performance-index')+'?.open && '+q(selector(pay))+'?.classList.contains("walk-mark")','return to the payment control');
      for (const invalid of [{...control,anchor:control.anchor+'0'}, {...original,line:row.line+1,raw_ref:row.id.replace(/l[0-9]+$/u,'l'+(row.line+1))}]) {
        const response=await fetch(root+'/api/walkthrough',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({id:'d'.repeat(32),text:'水印定位核验',context:invalid})});
        assert.equal(response.status,404);
      }
    }
  }
  const after=await get(base);
  assert.deepEqual([after.rev,after.status,after.decisions],[task.rev,task.status,task.decisions]);
  console.log('PASS · R'+rev+' · '+(shared?'contract, acceptance and payment cite the same issued line':expected?'contract and payment trace to signed-form original':'no cumulative contract citation')+' · six widths');
}
