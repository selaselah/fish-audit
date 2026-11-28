import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

export async function checkDeliveryRegister(ctx,cid) {
  const {root,call,evaluate,wait}=ctx, input=browserInput(ctx), base='/api/cases/'+cid;
  const q=s=>'document.querySelector('+JSON.stringify(s)+')';
  const click=s=>input.click(q(s));
  const get=async path=>{const r=await fetch(root+path);assert.equal(r.status,200);return r.json();};
  const task=await get(base);
  assert.match(task.title,/^合成演练 · (同型冷藏柜|四台冷藏柜|同一批四台冷藏柜|冷藏柜验收清单|合同约定经书面批准可以代用|终验注明冷藏柜代用|末台冷藏柜另附待签|冷藏柜合同点名禁止|冷藏柜保养条款|终验前所记|验收款付款当天所记|验收款付款后所记|补充协议批准的是另一台|一份待签草案)/u);
  const {report,rev}=await get(base+'/reports/'+(process.env.AUDIT_REGISTER_REV || task.rev));
  const accepted=report.findings.find(f=>f.rule==='H02'), paid=report.findings.find(f=>f.rule==='H05');
  const term=report.findings.find(f=>f.rule==='H04' && f.stage?.name===paid.stage.name);
  const register=accepted.inspection_coverage;
  const rows=(report.graph.inspection_coverage_sources?.rows || []).filter(r=>accepted.delivery_register?.includes(r.id));
  const format=report.policy.inspection_coverage, expected=['inspection-coverage-v3','inspection-coverage-v4','inspection-coverage-v5'].includes(format);
  const datedPacket=/所记的设备代用决定|补充协议批准的是另一台/u.test(task.title);
  const later=task.title.includes('付款后所记'), same=task.title.includes('当天所记'), before=task.title.includes('终验前所记');
  const compared=format==='inspection-coverage-v5' && (later || same || before);
  const qualification=rows.find(r=>r.kind==='substitution' && report.graph.documents_by_kind.contract_addendum?.includes(r.unit)) || rows.find(r=>r.kind==='substitution');
  if (['inspection-coverage-v4','inspection-coverage-v5'].includes(format)) {
    const noteCase=datedPacket || /约定经书面批准可以代用|终验注明冷藏柜代用|末台冷藏柜另附待签|点名禁止/u.test(task.title);
    assert.equal(Boolean(qualification),noteCase);
    if (noteCase) assert.equal(register.state,task.title.includes('点名禁止')?'register_prohibited':'register_substitution');
  }
  assert.equal(rows.filter(r=>r.line).length,expected?(datedPacket?4:qualification?3:2):0);
  for (const f of [accepted,term,paid]) assert.equal(Boolean(f.substitution_dates),compared);
  const pin=(f,r)=>'#serial-'+f.id+'-'+r.doc+'-p'+r.page+'-l'+r.line;
  async function open(f) {
    const view=f===accepted?'acceptance-checks':'payment-checks&stage='+f.id;
    await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+rev+'&view='+view});
    await wait(q('#performance-index')+'?.open && '+q('.scope-check-select')+'?.value==='+JSON.stringify(f.id),'open '+f.id);
  }
  async function original(r) {
    await wait(q('#page-dialog')+'?.open && '+q('#page-content .located')+'?.dataset.sourceRef==='+JSON.stringify(r.id)+
      ' && '+q('#page-content img')+'?.naturalWidth>0','register original');
    assert.equal(await evaluate(q('#page-content .located blockquote')+'.textContent'),r.quote);
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    const saved=report.calls.pages.find(c=>c.doc===r.doc && c.page===r.page).delivery_register_rects[r.line];
    const svg=await evaluate('[...document.querySelectorAll("#page-content .source-plane svg rect")].map(r=>["x","y","width","height"].map(k=>Number(r.getAttribute(k))))');
    assert.ok(saved.length);assert.deepEqual(svg,saved.map(([a,b,c,d])=>[a,b,c-a,d-b].map(n=>1000*n)));
  }
  for (const width of [320,390,768,820,1024,1440]) {
    await size(ctx,width);
    for (const f of [accepted,paid]) {
      await open(f);
      const group='#performance-index .delivery-register-lines';
      if (!expected) {assert.equal(await evaluate(q(group)+'===null'),true);continue;}
      await wait(q(group)+'?.getClientRects().length','register pair');
      const marks=await evaluate('[...document.querySelectorAll('+JSON.stringify(group+' mark')+')].map(n=>n.textContent)');
      const wanted=datedPacket?(task.title.includes('另一台')?['FA-0101','FA-0104','FA-0101','FA-0109','FA-0109','FA-0104','FA-0101']:
        rows.some(r=>!r.line)?['FA-0109','FA-0109','FA-0109']:['FA-0104','FA-0109','FA-0109','FA-0104','FA-0109','FA-0104']):
        ['register_prohibited','register_substitution'].includes(register.state)?['FA-0104','FA-0109','FA-0109','FA-0104']:
        register.state==='register_difference'?['FA-0104','FA-0109']:
        register.state==='register_duplicate'?['FA-0103','FA-0103']:[];
      assert.deepEqual(marks,wanted);
      if (qualification) {
        const endings=rows.filter(r=>wanted.includes(r.quote.match(/([A-Za-z0-9._*＊?-]+)。$/u)?.[1]));
        const paired=await evaluate(`[...document.querySelectorAll('#performance-index .register-code')].filter(n=>
          n.firstElementChild?.matches('mark') && n.textContent.endsWith('。')).map(n=>{
          const range=document.createRange();
          range.selectNodeContents(n.firstElementChild); const code=range.getBoundingClientRect();
          range.selectNodeContents(n.lastChild); const stop=range.getBoundingClientRect();
          return code.top<stop.bottom && stop.top<code.bottom;
        })`);
        assert.deepEqual(paired,endings.map(()=>true),'the terminal punctuation stays with its equipment number');
      }
      if (compared) {
        const event=f===paid?'实付':'终验', days=(f===paid?21:20)-(later?22:same?21:19);
        const label=days?event+'比协议所记批准日'+(days<0?'早 ':'晚 ')+Math.abs(days)+' 天':event+'与所记批准同日，时刻待核';
        assert.equal(await evaluate(q(group+' .register-outcome')+'.textContent'),label);
        assert.equal(await evaluate(q(group)+'.dataset.dateRef'),f.substitution_dates.date_ref);
        const summary='#serial-'+f.id+'-order';
        assert.equal(await evaluate(q(group)+'.open && '+q(summary)+'.dataset.originalLabel'),label);
        if (width===390) {
          await evaluate(q(summary)+'.focus()');await input.key('Enter');
          await wait('!'+q(group)+'.open','collapse the four source rows');
          await input.key('Enter');await wait(q(group)+'.open','restore the source rows');
        }
      } else assert.equal(await evaluate(q(group)+'.dataset.dateRef || null'),null);
      if (qualification && f===paid && width<=390) {
        const widths=await evaluate('[...document.querySelectorAll(".proof-checkpoints")].filter(g=>g.offsetWidth && g.childElementCount).map(g=>g.getBoundingClientRect().right-g.lastElementChild.getBoundingClientRect().right)');
        assert.ok(widths.length && widths.every(gap=>Math.abs(gap)<=1),'the last checkpoint fills its row');
      }
      await inspect(ctx,width,group,'delivery-register-'+f.rule);
      for (const row of rows.filter(r=>r.line)) {
        const target=pin(f,row);
        assert.equal(await evaluate(q(target+' strong')+'.textContent'),row.quote);
        assert.ok(await evaluate(q(target)+'.getBoundingClientRect().height>=44'));
        await click(target);await original(row);
        if (width===390 && f===paid && (qualification?row===qualification:row.kind==='population')) await inspect(ctx,width,'#page-content .located','delivery-register-original');
        await input.key('Escape');await wait('!'+q('#page-dialog')+'.open','return to check');
      }
    }
  }
  if (expected) {
    await open(paid);
    const fieldTitle=qualification?'回单付款日 2026-09-21':'其他字段引文';
    const otherFields='[...document.querySelectorAll("#performance-index summary")].find(s=>s.textContent==='+JSON.stringify(fieldTitle)+')';
    assert.equal(await evaluate(otherFields+'?.parentElement.open'),false);
    await evaluate(`(()=>{
      const read=EvidenceCompare.lineExcerpt, delay=new Promise(resolve=>{window.releaseDateCrop=resolve});
      EvidenceCompare.lineExcerpt=async (fact,index)=>{
        if (fact.field==='paid_on') {await delay;EvidenceCompare.lineExcerpt=read;}
        return read(fact,index);
      };
      return true;
    })()`);
    await input.click(otherFields);
    const select=q('#scope-source-field-'+paid.id), receipt=report.graph.documents.find(d=>d.name==='银行付款回单.pdf');
    const date=report.graph.facts.find(f=>f.doc===receipt.id && f.field==='paid_on' && paid.evidence.includes(f.id));
    await wait(select+'?.options.length>0','bank receipt fields');
    if (qualification) {
      assert.equal(await evaluate(q('#performance-index .scope-open-original')+'.dataset.fact'),date.id);
      const unverified=await evaluate(`['ambiguous','outside','date','receipt'].map(fault=>{
        const report=structuredClone(state.bundle.report), graph=report.graph, f=report.findings.find(f=>f.id===${JSON.stringify(paid.id)});
        const date=graph.facts.find(o=>o.id===${JSON.stringify(date.id)});
        if (fault==='ambiguous') graph.facts.push({...date,id:date.id+'-second'});
        if (fault==='outside') f.scope=f.scope.filter(u=>u!==(date.unit || date.doc));
        if (fault==='date') date.value='2026年9月22日';
        if (fault==='receipt') report.calls.pages.find(p=>p.doc===date.doc && p.page===date.page).check.response_id='';
        return WarrantyDates.receiptDate(f,report);
      })`);
      assert.deepEqual(unverified,[null,null,null,null]);
    } else {
      await evaluate('(()=>{const s='+select+', option=[...s.options].find(o=>o.parentElement.label==='+JSON.stringify(receipt.name)+
        ' && o.textContent.startsWith('+JSON.stringify(date.label+' · ')+'));s.value=option.value;s.dispatchEvent(new Event("change"));return true})()');
    }
    const place=receipt.name+' · 第 '+date.page+' 页'+(date.source_line?' '+date.source_line.number+' 行':'');
    assert.equal(await evaluate(q('#performance-index .scope-source-footer span')+'.textContent'),place);
    const buttonOffset=q('#performance-index .scope-open-original')+'.getBoundingClientRect().top-'+q('#performance-index .scope-source')+'.getBoundingClientRect().top';
    const beforeCrop=await evaluate(buttonOffset);
    await evaluate('window.releaseDateCrop();true');
    await wait(q('#performance-index .scope-source-crop canvas')+'?.width>0','visible archive excerpt');
    assert.ok(Math.abs(await evaluate(buttonOffset)-beforeCrop)<=1,'original link stays in place as the source image loads');
    await click('#performance-index .scope-open-original');
    await wait(q('#page-dialog')+'?.open && '+q('#page-content .evidence-row.located')+'?.dataset.fact==='+JSON.stringify(date.id),'open the payment date in the archived receipt');
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    if (qualification && report.graph.documents_by_kind.contract_addendum?.includes(qualification.unit)) {
      await open(paid);
      const selector='#performance-index .addendum-jump', record='addendum-pdf/'+qualification.unit;
      assert.equal(await evaluate(q(selector)+'.dataset.proof'),record);
      await click(selector);
      await wait(q('#addendum-signing')+'?.dataset.agreement==='+JSON.stringify(record)+' && document.activeElement==='+q('#addendum-signing'),'the signing evidence belongs to the same addendum');
    }
    await open(term);
    if (compared) {
      const summary='[...document.querySelectorAll("#performance-index summary")].find(s=>s.textContent==="终验日期 2026-09-20")';
      await input.click(summary);
      await wait(q('#performance-index .scope-open-original')+'?.dataset.fact==='+JSON.stringify(term.substitution_dates.date_ref),'installment links the dated acceptance');
      await click('#performance-index .scope-open-original');
      await wait(q('#page-content .located')+'?.dataset.fact==='+JSON.stringify(term.substitution_dates.date_ref),'original acceptance date');
      await input.key('Escape');await wait('!'+q('#page-dialog')+'.open','return to the installment');
      const guarded=await evaluate(`['edge','scope','date','pair','fields','draft','issuer','qualification'].map(fault=>{
        const p=structuredClone(state.bundle.report), f=p.findings.find(x=>x.rule==='H05'), proof=f.substitution_dates;
        const form=p.graph.inspection_coverage_sources.pages.find(page=>page.unit===proof.unit);
        if(fault==='edge') p.graph.edges=p.graph.edges.filter(e=>e.type!=='dates_equipment_substitution');
        if(fault==='scope') f.scope=f.scope.filter(u=>u!==proof.unit);
        if(fault==='date') proof.event_on='2026-10-01';
        if(fault==='pair') proof.original='FA-0110';
        if(fault==='fields') p.graph.inspection_coverage_sources.decision_fields=[];
        if(fault==='draft') form.substitution_decision.change_state.quote='补充协议状态：待双方签署';
        if(fault==='issuer') form.substitution_decision.buyer_signature.quote='甲方签章：另一家采购中心（已盖章）';
        if(fault==='qualification') form.substitution_qualification=true;
        return InspectionCoverage.registerControls(p,f)?.dataset.dateRef || null;
      })`);
      assert.ok(guarded.every(ref=>ref===null));
    }
    const row=qualification || rows.find(r=>r.kind==='population');
    await evaluate(q(pin(term,row))+'.focus()');await input.key('Enter');await original(row);
    const altered=await evaluate(`(()=>{
      return ['scope','quote','rect','edge','register'].map(fault=>{
        const p=structuredClone(state.bundle.report), f=p.findings.find(f=>f.rule==='H05'), id=f.delivery_register.at(-1);
        const r=p.graph.inspection_coverage_sources.rows.find(r=>r.id===id);
        if(fault==='scope') f.scope=f.scope.filter(u=>u!==r.unit);
        if(fault==='quote') p.graph.nodes.find(n=>n.id===id).label='另一份清单';
        if(fault==='rect') p.calls.pages.find(c=>c.doc===r.doc && c.page===r.page).delivery_register_rects[r.line]=[[.7,.2,.3,.4]];
        if(fault==='edge') p.graph.edges=p.graph.edges.filter(e=>!(e.from===id && e.to==='finding/'+f.id));
        if(fault==='register') f.delivery_register=f.delivery_register.slice(1);
        return InspectionCoverage.registerSources(p,f).length;
      });
    })()`);
    assert.deepEqual(altered,[0,0,0,0,0]);
    const isolated=process.env.AUDIT_ISOLATED_REGISTER_ORIGIN;
    async function compose(text,target,shot='delivery-register-feedback') {
      await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','walkthrough');
      await evaluate(q('#walk-text')+'.value='+JSON.stringify(text)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
      if (target) {
        await click('#walk-pick');await wait(q('#walk-launch')+'.dataset.picking==="true"','select');
        await click(target);await wait(q(target)+'.classList.contains("walk-selected")','source control');
        await inspect(ctx,390,'#walk-dialog',shot);
      }
    }
    async function saveAndReopen(text) {
      assert.equal(isolated,root);assert.ok(!['8000','8010'].includes(new URL(root).port));
      await click('#walk-save');await wait('!'+q('#walk-dialog')+'.open','saved');
      const note=(await get('/api/walkthrough')).notes.find(n=>n.text===text);
      assert.equal(note.context.rev,rev);
      await call('Page.navigate',{url:root+'/app#desk'});await wait(q('#desk')+'?.getClientRects().length','desk');
      await click('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','clear history panel');
      await click('#walk-saved');
      const link='[...document.querySelectorAll("#walk-history li")].find(n=>n.querySelector("p")?.textContent==='+JSON.stringify(text)+')?.querySelector("a")';
      await wait(link+'?.getClientRects().length','reopen this note');
      const url=await evaluate(link+'.href');assert.ok(url.includes(cid) && url.includes('rev='+rev));
      await evaluate('Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:async t=>{window.copied=t}});true');
      await click('#walk-copy');await wait('window.copied?.includes('+JSON.stringify(url)+')','exported fixed address');
      await input.click(link);
      await wait('location.hash==='+JSON.stringify(new URL(url).hash),'returned to the recorded revision and view');
      return note.context;
    }
    if (isolated) {
      const text=qualification?'请在这条代用原文旁增加批准原件的入口。':'请在终验原件这里增加核对送货单的入口。';
      await compose(text);const context=await saveAndReopen(text);await original(row);assert.equal(context.raw_ref,row.id);
    }
    if (isolated || process.env.AUDIT_UI_SHOTS) {
      const before=await get('/api/walkthrough'), text=compared?'希望在所记批准日旁补上当时收到原件的时间。':
        qualification?'希望在这笔验收款旁看到批准人和当时生效的文件。':'希望从这笔验收款直接查看相应的设备铭牌。';
      await size(ctx,390);await open(paid);await compose(text,pin(paid,row));
      if (isolated) {
        const context=await saveAndReopen(text);
        assert.equal(context.anchor,pin(paid,row).slice(1));assert.deepEqual(context.params,{view:'payment-checks',stage:paid.id});
        await wait(q(pin(paid,row))+'?.classList.contains("walk-mark")','restored payment control');
        // A delayed refresh must still restore the control when the reviewer is reading.
        const target=q(pin(paid,row));
        await new Promise(resolve=>setTimeout(resolve,2700));
        await evaluate('(()=>{const old='+target+', fresh=old.cloneNode(true);fresh.classList.remove("walk-mark");'+
          'old.replaceWith(fresh);window.dispatchEvent(new HashChangeEvent("hashchange"));return true})()');
        await wait(target+'?.classList.contains("walk-mark")','retained selection after the control was rendered again');
        await input.key('Tab');
        await wait(target+' && !'+target+'.classList.contains("walk-mark")','released selection on the next keyboard action');
      } else assert.deepEqual(await get('/api/walkthrough'),before);
      if (compared) {
        const claim='#serial-'+paid.id+'-order', label=await evaluate(q(claim)+'.textContent');
        const note='希望在这个日期结论旁注明收到批准文件的时间。';
        if (!isolated) {await click('#walk-close');await wait('!'+q('#walk-dialog')+'.open','close previous draft');}
        await open(paid);await compose(note,claim,'delivery-register-order-feedback');
        if (isolated) {
          const context=await saveAndReopen(note);
          assert.deepEqual(context.params,{view:'payment-checks',stage:paid.id});
          assert.equal(context.anchor,claim.slice(1));assert.equal(context.target,label);
          await wait(q(claim)+'?.classList.contains("walk-mark") && document.activeElement==='+q(claim),'return to dated finding');
        } else assert.deepEqual(await get('/api/walkthrough'),before);
      }
    }
  }
  const after=await get(base);
  assert.deepEqual([after.rev,after.status,after.decisions],[task.rev,task.status,task.decisions]);
  console.log('PASS R'+rev+', '+(register?.state || 'prior edition')+', '+rows.length+' original lines, six widths');
}
