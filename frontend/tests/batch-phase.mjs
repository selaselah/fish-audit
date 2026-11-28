// Read a fixed, watermarked workpaper through both audit entry points.
import assert from 'node:assert/strict';
import {size, inspect} from './review-screen.mjs';

const q = selector => 'document.querySelector(' + JSON.stringify(selector) + ')';
const all = selector => '[...document.querySelectorAll(' + JSON.stringify(selector) + ')]';

// Run each alteration on a fresh in-memory report. The service never receives the copies.
function alteredBatch(id) {
  const results = {};
  for (const change of ['original', 'batch-link', 'payment-link', 'page', 'support', 'other-batch', 'combined-scope',
    'clause', 'ledger-unit', 'duplicate', 'date-hash', 'criterion-link', 'bad-index', 'missing-index']) {
    const {findings, graph, calls} = structuredClone(state.bundle.report);
    const phase = findings.find(f => f.id === id), acceptance = findings.find(f => f.rule === 'H02');
    const ledger = acceptance.batch_acceptance, batch = ledger.batches.find(b => b.index === phase.stage.batch_index);
    const record = ledger.records.find(r => batch.records.includes(r.unit));
    const scope = graph.facts.find(f => f.id === record.scope_ref);
    const drop = keep => { graph.edges = graph.edges.filter(keep); };
    if (change === 'batch-link') drop(e => !(e.type === 'delivery_batch_acceptance' && e.to === scope.id));
    if (change === 'payment-link') drop(e => !(e.type === 'batch_payment_basis' && e.from === phase.stage.clause_ref));
    if (change === 'page') drop(e => !(e.type === 'records' && e.to === scope.id));
    if (change === 'support') drop(e => !(e.type === 'supports_result' && e.from === scope.id && e.to === 'finding/' + phase.id));
    if (change === 'other-batch') scope.source_line.text = scope.source_line.text.replace(/第.+?批/u, '第九批');
    if (change === 'combined-scope') scope.source_line.text += '及第九批';
    if (change === 'clause') phase.stage.clause_ref = ledger.batches.find(b => b.index !== batch.index).clause_ref;
    if (change === 'ledger-unit') record.unit = 'unrelated-document';
    if (change === 'duplicate') ledger.records.push({...record});
    if (change === 'date-hash') graph.facts.find(f => (f.unit || f.doc) === record.unit && f.field === 'accepted_on').page_sha256 = 'stale';
    if (change === 'criterion-link') {
      const witness = graph.facts.find(f => batch.evidence.includes(f.id) && f.field === 'acceptance_criteria');
      drop(e => !(e.type === 'supports_result' && e.from === witness.id && e.to === 'finding/' + acceptance.id));
    }
    if (change === 'bad-index') phase.stage.batch_index = '2';
    if (change === 'missing-index') delete phase.stage.batch_index;
    const proof = BatchPhase.resolve(phase, acceptance, graph, calls?.pages), ui = BatchPhase.panel(proof, phase.stage);
    results[change] = [proof.verified, proof.status, ui.querySelectorAll('[data-fact]').length];
  }
  return results;
}
async function checkScopedFinal(ctx,report,url) {
  const {call,evaluate,wait}=ctx;
  const cases=report.findings.filter(f=>f.final_signature_condition);
  assert.ok(cases.some(f=>f.rule==='H04') && cases.some(f=>f.rule==='H05'));
  const h=report.findings.find(f=>f.rule==='H02'), final=h.batch_acceptance.separate_final;
  const proof=final.signatures_on_batches[0];
  const fact=report.graph.facts.find(f=>f.id===proof.signature_ref);
  const visited=new Set();
  for (const f of cases) {
    const panel='#performance-index [data-roster-finding="'+f.id+'"]';
    await call('Page.navigate',{url:url+'&view=payment-checks&stage='+f.id});
    await wait(q('#performance-index')+'?.open && '+q(panel)+'?.getClientRects().length','warranty condition in the selected installment');
    assert.ok((await evaluate(q(panel+' summary')+'.textContent')).includes(proof.name));
    const picker=q('#performance-index .accept-proof-picker');
    const finalFile=report.graph.documents.find(d=>d.id===f.final_signature_condition.receipt);
    assert.equal(await evaluate(picker+'.labels[0].textContent'),'验收原件');
    assert.ok((await evaluate(picker+'.selectedOptions[0].textContent')).includes(finalFile.name));
    const receipts=await evaluate('Array.from('+picker+'.options,o=>o.textContent)');
    assert.ok(receipts.length>1);
    for (const index of [1,0]) {
      await evaluate(picker+'.selectedIndex='+index+';'+picker+'.dispatchEvent(new Event("change"))');
      assert.equal(await evaluate(all('#performance-index .scope-receipt-proof')+'.length'),1);
      assert.ok((await evaluate(q('#performance-index .scope-receipt-proof')+'.textContent')).includes(receipts[index].split(' · ')[0]));
    }
    for (const change of ["delete r.findings.find(p=>p.rule==='H02').batch_acceptance.separate_final.records",
      "r.graph.edges=r.graph.edges.filter(e=>e.type!=='final_name_on_batch_record')",
      "f.final_signature_condition.batch_signatures=[]","r.graph.facts.find(p=>p.id===ref).source_line.rects=[]",
      "r.calls.expert.input.procedures.find(p=>p.rule==='H02').batch_acceptance.separate_final.signatures_on_batches=[]"]) {
      const available=await evaluate('(()=>{const r=structuredClone(state.bundle.report),f=r.findings.find(x=>x.id==='+JSON.stringify(f.id)+'),ref='+JSON.stringify(proof.signature_ref)+';'+
        change+';return Boolean(batchSignatureEvidence(r,f))})()');
      assert.equal(available,false);
    }
    await evaluate(q(panel+' summary')+'.click()');
    const links=await evaluate(all(panel+' button')+'.map(b=>b.dataset.batchRosterSource)');
    assert.ok(links.includes(proof.signature_ref) && links.includes(final.signing_requirement.clause_ref) && links.includes(f.final_signature_condition.term_ref));
    for (const width of [1440,1024,768,390,360,320]) {
      await size(ctx,width);
      await inspect(ctx,width,panel,'scoped-final-'+f.rule);
      for (const ref of links) {
        const key=f.rule+'/'+ref+'/'+(width<600?'phone':'desk');
        if (visited.has(key)) continue;
        const button=q(panel+' [data-batch-roster-source="'+ref+'"]');
        await evaluate(button+'.focus();'+button+'.click()');
        await wait(q('#page-dialog')+'.open && '+q('#page-content .evidence-row.located')+'?.dataset.fact==='+JSON.stringify(ref),'linked physical row');
        await wait(q('.source-plane svg rect')+'!=null','line highlight');
        if (ref===proof.signature_ref) {
          assert.ok((await evaluate(q('#page-content .evidence-row.located')+'.textContent')).includes(fact.source_line.text));
          if (f.rule==='H05') {
            await evaluate(q('#page-dialog #walk-launch')+'.click()');
            await wait(q('#walk-dialog')+'?.open && !'+q('#walk-excerpt')+'?.hidden','walkthrough at the original');
            assert.equal(await evaluate(q('#walk-excerpt blockquote')+'.textContent'),fact.source_line.text);
            assert.ok((await evaluate(q('#walk-origin')+'.textContent')).includes('R'+new URL(url).searchParams.get('rev')));
            const binding=await evaluate('(async()=>{'+
              'const {captureContext,originalLine}=await import("/assets/walkthrough-context.js");'+
              'const c=captureContext(document.getElementById("page-dialog")), b=structuredClone(state.bundle);'+
              'const invalid=[{rev:c.rev+1},{case_id:"other"},{line:c.line+1},{doc:"d99"}];'+
              'const allMissing=invalid.every(v=>!originalLine({...c,...v},b));'+
              'b.report.graph.facts.find(x=>x.id===c.params.fact).source_line.rects=[];'+
              'return allMissing && !originalLine(c,b)})()');
            assert.equal(binding,true);
            await evaluate(q('#walk-close')+'.click()');
          }
        }
        await evaluate(q('#page-dialog [data-close]')+'.click()');
        await wait('document.activeElement==='+button,'return to source link');
        visited.add(key);
      }
    }
    const prior=report.findings.find(x=>x.rule==='H04' && x.stage?.batch_index && !x.final_signature_condition);
    await evaluate(q('.scope-check-select')+'.value='+JSON.stringify(prior.id)+';'+q('.scope-check-select')+'.dispatchEvent(new Event("change"))');
    await wait(q('#performance-index .batch-roster-proof')+'===null','independent batch installment');
  }
  console.log('PASS · 分批签认原行、另行终验缺签与质保金 · 两个付款入口、六种宽度');
}

export async function checkBatchPhase(ctx, id, revision) {
  const {root, call, wait, evaluate} = ctx, base = root + '/api/cases/' + id;
  const task = await (await fetch(base)).json();
  assert.ok(task.title.startsWith('合成演练'));
  const rev = Number(revision || task.rev);
  const {report} = await (await fetch(base + '/reports/' + rev)).json();
  const h2 = report.findings.find(f => f.rule === 'H02'), ledger = h2.batch_acceptance;
  if (report.findings.some(f=>f.final_signature_condition))
    return checkScopedFinal(ctx,report,root+'/workpaper/'+id+'?rev='+rev);
  const phases = report.findings.filter(f => f.rule === 'H04' && f.stage?.batch_index);
  const url = root + '/workpaper/' + id + '?rev=' + rev, scope = '#performance-index';
  const evidence = scope + ' .batch-phase-proof', facts = report.graph.facts;
  async function key(key) {
    for (const type of ['keyDown', 'keyUp']) await call('Input.dispatchKeyEvent', {
      type, key, code: key, windowsVirtualKeyCode: {Escape:27, Enter:13, Home:36, End:35}[key],
      ...(type === 'keyDown' && key === 'Enter' ? {text:'\r', unmodifiedText:'\r'} : {}),
    });
  }
  async function openStage(phase) {
    await call('Page.navigate', {url: url + '&view=payment-checks&stage=' + phase.id});
    await wait(q(scope) + '?.open && ' + q(evidence) + '?.dataset.batch===' + JSON.stringify(String(phase.stage.batch_index)), 'fixed payment stage');
    assert.equal(await evaluate(q('.scope-check-select') + '.value'), phase.id);
  }
  if (!phases.length) {
    await call('Page.navigate', {url});
    await wait(q('[data-phase-finding] .phase-evidence') + '!==null', 'ordinary installment plan');
    assert.equal(await evaluate(all('.batch-phase-proof') + '.length'), 0);
    return;
  }
  const covered = new Set();
  let drafted = false;
  for (const width of [320, 360, 390, 768, 1024, 1440]) {
    await size(ctx, width);
    for (const phase of phases) {
      await openStage(phase);
      const batch = ledger.batches.find(b => b.index === phase.stage.batch_index);
      const recordUnits = batch.records, name = String(batch.index);
      const versioned = ledger.records.some(r=>r.standard && recordUnits.includes(r.unit));
      const compared = !versioned && batch.status === 'issue' && batch.detail.includes('实测值超出约定限值。') ?
        ['acceptance_criteria', 'measured_result'].map(field => facts.find(f => f.field === field && batch.evidence.includes(f.id))) : [];
      assert.equal(await evaluate(q(evidence) + '.dataset.verified'), 'true', phase.id + ' at R' + rev);
      assert.equal(await evaluate(q(evidence + ' .tag') + '.dataset.state'), batch.status);
      if (versioned) assert.equal(await evaluate(q(evidence+' [data-source=standard]')+'.getAttribute("aria-pressed")'),'true');
      if (compared.length) assert.ok(await evaluate(q(evidence + ' [data-source=quality]') + '?.getAttribute("aria-pressed")==="true"'));
      assert.ok(await evaluate(q(scope) + '.scrollWidth<=' + q(scope) + '.clientWidth+1'));
      if (phase === phases.at(-1)) await inspect(ctx, width, evidence, 'batch-' + id.slice(0, 6));
      if (width === 390) {
        await evaluate(q(evidence + ' [data-source=receipt]') + '.focus()'); await key('Home');
        assert.equal(await evaluate('document.activeElement.dataset.source'), 'contract');
        await key('End');
        assert.equal(await evaluate('document.activeElement.dataset.source'), versioned ? 'standard' : compared.length ? 'quality' : 'receipt');
      }
      for (const mode of ['receipt', 'contract', ...(compared.length ? ['quality'] : [])]) {
        const switcher = q(evidence + ' [data-source="' + mode + '"]');
        await evaluate(switcher + '.click()');
        const links = await evaluate(all(evidence + ' [data-fact]') + '.filter(b=>b.checkVisibility()).map(b=>b.dataset.fact)');
        if (mode === 'contract') assert.deepEqual(links, [phase.stage.clause_ref, batch.clause_ref]);
        else if (mode === 'quality') assert.deepEqual(links, compared.map(f => f.id));
        else {
          assert.deepEqual(links.map(ref => facts.find(f => f.id === ref)).filter(f => f.field === 'acceptance_scope').map(f => f.unit || f.doc), recordUnits);
          const bank = new Set(report.graph.documents_by_kind.transfer || []);
          for (const ref of links) {
            const f = facts.find(f => f.id === ref);
            assert.ok(recordUnits.includes(f.unit || f.doc) && !bank.has(f.unit || f.doc));
          }
        }
        for (const ref of links) {
          if (covered.has(width < 600 ? 'touch/' + ref : ref)) continue;
          const source = q(evidence + ' [data-fact="' + ref + '"]');
          await evaluate(source + '.focus()'); await key('Enter');
          const f = facts.find(f => f.id === ref), expected = base + '/documents/' + f.doc + '/pages/' + f.page + '?rev=' + rev;
          await wait(q('#page-dialog') + '.open && ' + q('.evidence-row.located') + '?.dataset.fact===' + JSON.stringify(ref) +
            ' && ' + q('.source-tools > a') + '?.href===' + JSON.stringify(expected) + ' && ' + q('.page-image') + '?.naturalWidth>0', 'physical line ' + ref);
          assert.equal(await evaluate(q('.evidence-row.located blockquote') + '.textContent'), f.quote);
          await key('Escape'); await wait(q(scope) + '.open && document.activeElement===' + source, 'return to source button');
          covered.add(width < 600 ? 'touch/' + ref : ref);
        }
      }
      await evaluate(q(evidence + ' [data-source=receipt]') + '.click()');
      const draft = q(evidence + ' .batch-phase-empty button'), canDraft = await evaluate('!!' + draft);
      const receipts = [...(report.graph.documents_by_kind.acceptance || []), ...(report.graph.documents_by_kind.reinspection || [])];
      const unresolved = receipts.some(unit => !ledger.records.some(r => r.unit === unit && (r.index || r.role === 'final')));
      if (unresolved || rev !== task.rev || recordUnits.length) assert.equal(canDraft, false);
      if (!drafted && !recordUnits.length && !unresolved && task.status === 'ready' && rev === task.rev && batch.detail.includes('缺少对应本批的验收原件')) {
        assert.ok(canDraft);
        await evaluate(draft + '.focus()'); await key('Enter');
        await wait(q('#review-dialog') + '.open && document.activeElement===' + q('#review-note'), 'draft supplement');
        const note = await evaluate(q('#review-note') + '.value');
        assert.ok(note.includes(phase.stage.clause) && note.includes('第 ' + name + ' 批') && note.includes(phase.stage.name));
        assert.equal(await evaluate(q('#review-decision input:checked') + '.value'), 'return');
        await key('Escape'); await wait(q(scope) + '.open && document.activeElement===' + draft, 'cancel unsent supplement');
        drafted = true;
      }
      await key('Escape'); await wait('!' + q(scope) + '.open', 'close stage inspector');
      const group = '[data-phase-finding="' + phase.id + '"]', choice = q('[data-phase-choice="' + phase.id + '"]');
      await evaluate('revealPaperTarget(' + choice + ');' + choice + '.click()');
      const step = q(group + ' [data-check=acceptance]');
      assert.equal(await evaluate(step + '.dataset.state'), batch.status);
      await evaluate(step + '.click()');
      assert.equal(await evaluate(q(group + ' .phase-evidence') + '.dataset.mode'), 'batch');
      assert.equal(await evaluate('document.activeElement.dataset.mode'), 'batch');
      const dates = await evaluate(all(group + ' [data-event=acceptance]') + '.map(e=>[e.closest("[data-day]").dataset.day,e.textContent])');
      for (const [date, caption] of dates) {
        assert.ok(ledger.records.some(r => recordUnits.includes(r.unit) && date === r.date));
        assert.ok(caption.includes('第 ' + name + ' 批验收单据日期'));
      }
      if (!recordUnits.length) assert.equal(dates.length, 0);
      if (batch.status === 'ok') assert.equal(dates.length, 1);
    }
  }
  const positive = phases.find(f => f.status === 'ok' && ledger.batches.find(b => b.index === f.stage.batch_index)?.status === 'ok');
  if (positive) {
    const probes = await evaluate('(' + alteredBatch.toString() + ')(' + JSON.stringify(positive.id) + ')');
    assert.equal(probes.original[0], true);
    for (const [name, result] of Object.entries(probes)) if (name !== 'original')
      assert.deepEqual(result, [false, 'missing', 0], name);
  }
  for (const phase of phases) {
    const probe = await evaluate('(' + function (id) {
      const {findings, graph, calls} = structuredClone(state.bundle.report);
      const phase = findings.find(f => f.id === id), h2 = findings.find(f => f.rule === 'H02');
      const proof = BatchPhase.resolve(phase, h2, graph, calls?.pages);
      if (proof.missingReceipt) {
        graph.documents.push({id:'unclassified', name:'待辨附件'});
        return BatchPhase.resolve(phase, h2, graph, calls?.pages).missingReceipt;
      }
      if (proof.quality) {
        const reloaded = structuredClone(graph);
        reloaded.facts.find(f => f.id === proof.quality.reading.id).source_line.rects = [];
        return Boolean(BatchPhase.resolve(phase, h2, reloaded, calls?.pages).quality);
      }
      return false;
    }.toString() + ')(' + JSON.stringify(phase.id) + ')');
    assert.equal(probe, false, 'unallocated attachment or unlocated measurement');
  }
  if (h2.batch_acceptance.separate_final && h2.status !== 'ok') {
    const final = report.findings.find(f => f.rule === 'H04' && !f.stage.batch_index && f.warranty_check);
    if (final) {
      const row = '[data-phase-finding="' + final.id + '"]';
      const citesReceipt = facts.some(f => h2.evidence.includes(f.id) && final.evidence.includes(f.id) &&
        ['acceptance_scope','acceptance_result','accepted_on'].includes(f.field));
      assert.equal(await evaluate(q(row + ' [data-check=acceptance]') + '?.dataset.state'), citesReceipt ? h2.status : undefined);
      assert.equal(await evaluate(q(row + ' [data-mode=batch]')), null);
    }
  }
  await call('Page.navigate', {url:url + '&view=payment-checks&stage=H04-999'});
  await wait(q(scope) + '?.open && ' + q(scope + ' [role=status]') + '?.textContent.includes("未收录")', 'unavailable fixed stage');
  assert.equal(await evaluate(q('.scope-check-select') + '.value'), '');
  assert.equal(await evaluate(all('.scope-detail [data-fact], .scope-check[aria-pressed=true]') + '.length'), 0);
  await evaluate(q('.scope-check') + '.click()');
  assert.notEqual(await evaluate(q('.scope-check-select') + '.value'), '');
  console.log('Batch acceptance R' + rev + ' · ' + phases.length + ' installments · six widths · ' + (drafted ? 'unsent supplement' : 'read-only'));
}
