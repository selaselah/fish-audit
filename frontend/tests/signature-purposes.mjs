import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

async function checkRevisionPair(ctx,report,path,rev,title) {
  const {call,evaluate,wait}=ctx, {click,key}=browserInput(ctx);
  const q=s=>'document.querySelector('+JSON.stringify(s)+')';
  const rows=report.graph.signature_purposes.rows;
  const fields=title.includes('数量签认在后')?['QualityReview','SyntheticApproval']:['SyntheticApproval','QualityReview'];
  assert.deepEqual(rows.map(r=>[r.field,r.revision,r.coverage]),[
    [fields[0],2,'ENTIRE_REVISION'],[fields[1],3,'ENTIRE_FILE']]);
  assert.notEqual(rows[0].certificate_sha256,rows[1].certificate_sha256);
  for (const f of report.findings.filter(f=>['H01','H02','H04','H05'].includes(f.rule))) {
    const view=f.rule==='H01'?'contract-checks':f.rule==='H02'?'acceptance-checks':'payment-checks&stage='+f.id;
    await call('Page.navigate',{url:path+'&view='+view});
    await wait(q('#performance-index[open] .scope-check[aria-pressed=true]')+'?.dataset.check==='+JSON.stringify(f.id),'selected '+f.id);
    const expected=f.rule==='H02' || ['H04','H05'].includes(f.rule) && ['第二期','第三期'].includes(f.stage.name);
    assert.deepEqual(await evaluate('[...document.querySelectorAll(".purpose-series q")].map(e=>e.textContent)'),expected?rows.map(r=>r.reason):[]);
    if (f.rule!=='H05') continue;
    const doc=report.graph.documents.find(d=>d.id===rows[0].doc);
    const source=row=>'#signature-purpose-'+f.id+'-'+row.doc+'-r'+row.revision;
    for (const width of [1440,1024,768,390,360,320]) {
      await size(ctx,width);
      for (const row of rows) assert.ok(await evaluate(q(source(row))+'.scrollWidth<='+q(source(row))+'.clientWidth+1'));
      if (![1440,390].includes(width)) continue;
      await inspect(ctx,width,'.purpose-series','signed-revisions');
      for (const row of rows) {
        const summary=q(source(row)),detail=summary+'.parentElement';
        await evaluate(summary+'.focus()');await key('Enter');await wait(detail+'.open','signed edition expanded');
        assert.deepEqual(await evaluate('[...'+detail+'.querySelectorAll("dd")].map(e=>e.textContent)'),[row.field,
          '文件修订 '+row.revision+' · '+(row.coverage==='ENTIRE_FILE'?'整份提交件':'较早修订'),row.certificate_sha256,row.signed_sha256]);
        const link=detail+'.querySelector("a")';
        const response=await fetch(await evaluate(link+'.href'));
        assert.equal(response.status,200);assert.equal(response.headers.get('etag'),'"'+row.signed_sha256+'"');
        const bytes=Buffer.from(await response.arrayBuffer());
        assert.equal(bytes.length,row.ends_at);assert.equal(Buffer.from(await crypto.subtle.digest('SHA-256',bytes)).toString('hex'),row.signed_sha256);
        await inspect(ctx,width,'.purpose-series details[open]','signed-revision-'+row.revision);
        await key('Enter');await wait('!'+detail+'.open','fold signed attributes');
      }
    }
    for (const row of rows) {
      const control=q(source(row));
      await click(q('#walk-launch'));await wait(q('#walk-dialog[open]')+' && !'+q('#walk-save')+'.disabled','recorder ready');
      await click(q('#walk-pick'));await click(control);
      await wait(q('#walk-excerpt blockquote')+'?.textContent==='+JSON.stringify(row.reason),'selected revision quote');
      const place=await evaluate(q('#walk-location')+'.textContent');
      assert.ok(place.includes(doc.name) && place.includes('修订 '+row.revision));assert.doesNotMatch(place,/第\s*\d+\s*(页|行)/u);
      await click(q('#walk-close'));
      await size(ctx,1024);await click(q('#performance-index .scope-actions > button:last-child'));
      const finding='.finding[data-finding="'+f.id+'"]';
      const refs='[...'+q(finding)+'.querySelectorAll(".finding-body details > summary")].find(n=>n.textContent.startsWith("查看本项全部引文"))';
      await wait(refs+'?.getClientRects().length','finding citations');
      if (!await evaluate(refs+'.parentElement.open')) await click(refs);
      const citation=q(finding+' a[href*="walkat='+source(row).slice(1)+'"]');
      await wait(citation+'?.getClientRects().length','exact revision link');await click(citation);
      await wait(control+'?.matches("#performance-index[open] .walk-mark")','revision restored from finding');
    }
    const invalid=await evaluate('(()=>{const r=structuredClone(state.bundle.report),p=r.graph.signature_purposes.rows;'+
      'p[0].ends_at=p[1].ends_at;return SignaturePurposes.bind(r,r.findings.find(f=>f.id==='+JSON.stringify(f.id)+'),p[0].id)})()');
    assert.equal(invalid,null);
  }
  console.log('PASS R'+rev,'both signed PDF revisions, exact downloads, role, installments, citations and individual feedback');
}

async function checkReportReference(ctx,report,path) {
  const {call,evaluate,wait}=ctx, {click,key}=browserInput(ctx);
  const q=s=>'document.querySelector('+JSON.stringify(s)+')';
  const row=report.graph.signature_purposes.rows.find(r=>r.report_reference), ref=row.report_reference;
  const scope=ref.coverage, scopeLabels={sample:'样机台数待核',short:'报告台数不足',count_only:'台数相符 · 逐台记录待核',review:'检测口径待核'};
  const label=scope?'已定位报告 · '+scopeLabels[scope.state]
    : {unlocated:'待查报告原件',different:'报告编号不同',matched:'已定位报告 · 终验待核'}[ref.state];
  assert.ok(label);
  for (const f of report.findings.filter(f=>['H01','H02','H04','H05'].includes(f.rule))) {
    const view=f.rule==='H01'?'contract-checks':f.rule==='H02'?'acceptance-checks':'payment-checks&stage='+f.id;
    await call('Page.navigate',{url:path+'&view='+view});
    await wait(q('#performance-index[open] .scope-check[aria-pressed=true]')+'?.dataset.check==='+JSON.stringify(f.id),'selected '+f.id);
    const summary='#signature-purpose-'+f.id+'-'+row.doc+(row.coverage?'-r'+row.revision:'');
    const selected=f.rule==='H02' || ['第二期','第三期'].includes(f.stage?.name);
    const display=await evaluate('[...document.querySelectorAll(".purpose-report-state")].map(s=>[s.parentElement.id,s.textContent])');
    assert.deepEqual(display,selected?[[summary.slice(1),label]]:[]);
    if (f.rule!=='H05') continue;
    const detail=q(summary)+'.parentElement';
    await evaluate(q(summary)+'.focus()'); await key('Enter'); await wait(detail+'.open','report disclosure');
    const values=await evaluate('[...document.querySelectorAll(".report-scope-value strong")].map(n=>n.textContent)');
    const count=n=>n==null?'待核':n+' 台';
    assert.deepEqual(values,scope?[count(scope.received),count(scope.reported)]:[]);
    for (const width of [1440,1024,768,390,360,320]) {
      await size(ctx,width);
      assert.ok(await evaluate(detail+'.scrollWidth<='+detail+'.clientWidth+1'));
      await inspect(ctx,width,scope?'.report-scope':'.purpose-report','inspection-'+(scope?.state || ref.state));
    }
    for (const candidate of ref.candidates) {
      const pdf=await fetch(await evaluate(q('.purpose-report-file a')+'.href'));
      assert.ok(pdf.ok);
      assert.equal(Buffer.from(await crypto.subtle.digest('SHA-256',await pdf.arrayBuffer())).toString('hex'),candidate.original_sha256);
      await size(ctx,1440);
      for (const item of [candidate.number,scope?.report_rows.count].filter(Boolean)) {
        const source='inspection-report-line/'+candidate.doc+'/p1/l'+item.line;
        await evaluate(q('[data-inspection-line="'+source+'"]')+'.focus()');await key('Enter');
        await wait(q('#page-dialog[open] .located[data-source-ref="'+source+'"] blockquote')+
          '?.textContent==='+JSON.stringify(item.quote),'keyboard opens the printed report row');
        await key('Escape');await wait('!'+q('#page-dialog')+'.open','keyboard returns to installment');
      }
      for (const item of [candidate.number,candidate.conclusion,scope?.report_rows.count].filter(Boolean)) {
        await size(ctx,390);
        const source='inspection-report-line/'+candidate.doc+'/p1/l'+item.line, control=q('[data-inspection-line="'+source+'"]');
        assert.equal(await evaluate(control+'.title'),item.quote);
        await wait(q('#performance-index[open] #walk-launch')+'?.getClientRects().length','recorder returned to payment check');
        await click(q('#walk-launch'));await wait(q('#walk-dialog[open]')+' && !'+q('#walk-save')+'.disabled','recorder ready');
        await click(q('#walk-pick'));await click(control);
        await wait(q('#walk-excerpt blockquote')+'?.textContent==='+JSON.stringify(item.quote),'attachment quote from panel');
        await click(q('#walk-close'));await click(control);
        const located='#page-dialog[open] .located[data-source-ref="'+source+'"]';
        await wait(q(located+' blockquote')+'?.textContent==='+JSON.stringify(item.quote),'actual report row in reader');
        await wait(q('#page-dialog .source-plane svg rect')+' && '+q('#page-dialog .page-image')+'?.naturalWidth','marked original image');
        await wait(q('#page-dialog #walk-launch')+'?.getClientRects().length','recorder in the original reader');
        await click(q('#walk-launch'));
        await wait(q('#walk-dialog[open]')+' && !'+q('#walk-save')+'.disabled && '+q('#walk-excerpt blockquote')+'?.textContent==='+JSON.stringify(item.quote),'feedback from actual original');
        await click(q('#walk-close'));await click(q('#page-dialog [data-close]'));
      }
    }
    for (const field of ['clause','ordered','accepted','acceptance_scope']) {
      const basis=scope?.basis[field];
      if (!basis) continue;
      const control=q('[data-inspection-basis="'+basis.fact+'"]');
      await wait(q('#performance-index[open] #walk-launch')+'?.getClientRects().length','back at installment');
      await click(q('#walk-launch'));await wait(q('#walk-dialog[open]')+' && !'+q('#walk-save')+'.disabled','recorder ready');
      await click(q('#walk-pick'));await click(control);
      await wait(q('#walk-excerpt blockquote')+'?.textContent==='+JSON.stringify(basis.quote),'selected contract or receipt field');
      await click(q('#walk-close'));await evaluate(control+'.focus()');await key('Enter');
      await wait(q('#page-dialog[open] .located[data-fact="'+basis.fact+'"] blockquote')+'?.textContent==='+JSON.stringify(basis.quote),'original field');
      await key('Escape');await wait('!'+q('#page-dialog')+'.open','return from the cited field');
    }
    const scopeEdits=scope?["delete r.policy.code_sha256['inspection_report_scope.py']",
      "r.graph.edges=r.graph.edges.filter(e=>e.type!=='inspection_scope_basis')"]:[];
    for (const edit of ["r.graph.edges=r.graph.edges.filter(e=>e.type!=='requires_inspection_report')",
      "delete r.policy.code_sha256['inspection_reports.py']", "r.calls.expert.input.procedures=[]", ...scopeEdits]) {
      const invalid=await evaluate('(()=>{const r=structuredClone(state.bundle.report);'+edit+
        ';return SignaturePurposes.bind(r,r.findings.find(f=>f.id==='+JSON.stringify(f.id)+'),'+JSON.stringify(row.id)+')})()');
      assert.equal(invalid,null);
    }
  }
  console.log('PASS',ref.state,row.id,'scope, original attachment, line selection and feedback');
}

export async function checkSignaturePurposes(ctx,cid,requested) {
  const {root,call,evaluate,wait}=ctx,{click,key}=browserInput(ctx);
  const base=root+'/api/cases/'+cid, task=await (await fetch(base)).json();
  assert.ok(task.title.startsWith('合成演练') && /到货数量|两次签名|签名所引检测报告|四台逐台测温合同/u.test(task.title));
  const rev=Number(requested || task.rev), {report}=await (await fetch(base+'/reports/'+rev)).json();
  const row=report.graph.signature_purposes?.rows[0];
  const q=s=>'document.querySelector('+JSON.stringify(s)+')';
  const path=root+'/workpaper/'+cid+'?rev='+rev;
  if (report.graph.signature_purposes?.rows.some(r=>r.report_reference)) return checkReportReference(ctx,report,path);
  if (task.title.includes('两次签名') && row) return checkRevisionPair(ctx,report,path,rev,task.title);
  const stage=f=>f.rule==='H01'?'contract-checks':f.rule==='H02'?'acceptance-checks':'payment-checks&stage='+f.id;
  for (const f of report.findings.filter(f=>['H01','H02','H04','H05'].includes(f.rule))) {
    await call('Page.navigate',{url:path+'&view='+stage(f)});
    await wait(q('#performance-index[open] .scope-check[aria-pressed=true]')+'?.dataset.check==='+JSON.stringify(f.id),'chosen check '+f.id);
    const summary=q('.signature-purpose > summary');
    assert.equal(await evaluate('Boolean('+summary+')'),Boolean(f.signature_purposes));
    if (!f.signature_purposes) continue;
    assert.deepEqual(f.signature_purposes,[row.id]);
    assert.equal(await evaluate(q('.signature-purpose q')+'.textContent'),row.reason);
    assert.ok((await evaluate(summary+'.textContent')).includes(row.role==='contract'?'合同签名原因':'验收报告签名原因'));
    if (f.rule!=='H05') continue;
    const doc=report.graph.documents.find(d=>d.id===row.doc);
    for (const width of [1440,1024,768,390,360,320]) {
      await size(ctx,width);
      assert.ok(await evaluate(summary+'.scrollWidth<='+summary+'.clientWidth+1'));
      if (![1440,390].includes(width)) continue;
      await inspect(ctx,width,'.signature-purpose','signature-purpose-'+row.role);
      await evaluate(summary+'.focus()');await key('Enter');
      await wait(q('.signature-purpose[open] a')+'?.getClientRects().length','signed file attributes');
      assert.deepEqual(await evaluate('[...document.querySelectorAll(".purpose-attributes dd")].map(n=>n.textContent)'),
        [row.field,'文件修订 '+row.revision+' · 整份提交件',row.certificate_sha256]);
      const a=q('.purpose-attributes a');
      assert.equal(await evaluate(a+'.download'),doc.name);
      const digest=await evaluate('(async()=>{const r=await fetch('+a+'.href);if(!r.ok)throw Error(r.status);const h=await crypto.subtle.digest("SHA-256",await r.arrayBuffer());return [...new Uint8Array(h)].map(x=>x.toString(16).padStart(2,"0")).join("")})()');
      assert.equal(digest,row.original_sha256);
      await inspect(ctx,width,'.signature-purpose','signature-attributes-'+row.role);
      await key('Enter');await wait('!'+q('.signature-purpose')+'.open','fold attributes');
    }
    await click(q('#walk-launch'));await wait(q('#walk-dialog[open]')+' && !'+q('#walk-save')+'.disabled','walkthrough ready');
    await click(q('#walk-pick'));await click(summary);
    await wait(q('#walk-excerpt blockquote')+'?.textContent==='+JSON.stringify(row.reason),'exact PDF attribute');
    assert.ok((await evaluate(q('#walk-location')+'.textContent')).includes(doc.name));
    assert.doesNotMatch(await evaluate(q('#walk-location')+'.textContent'),/第\s*\d+\s*(页|行)/u);
    await click(q('#walk-close'));
    for (const change of ["r.graph.edges=r.graph.edges.filter(e=>e.type!=='declares_signature_purpose')",
      "r.graph.signature_purposes.rows[0].certificate_sha256='x'","r.calls.expert.input.procedures=[]"]) {
      const bound=await evaluate('(()=>{const r=structuredClone(state.bundle.report),f=r.findings.find(f=>f.id==='+JSON.stringify(f.id)+');'+change+
        ';return Boolean(SignaturePurposes.bind(r,f,'+JSON.stringify(row.id)+'))})()');
      assert.equal(bound,false);
    }
    await size(ctx,1024);
    await click(q('#performance-index .scope-actions > button:last-child'));
    const finding='.finding[data-finding="'+f.id+'"]';
    const refs='[...'+q(finding)+'.querySelectorAll(".finding-body details > summary")].find(n=>n.textContent.startsWith("查看本项全部引文"))';
    await wait(refs+'?.getClientRects().length','full finding citations');
    await click(refs);
    const anchor='signature-purpose-'+f.id+'-'+doc.id, citation=q(finding+' a[href*="walkat='+anchor+'"]');
    await wait(citation+'?.getClientRects().length','signed attribute in evidence list');
    await click(citation);
    await wait(q('#'+anchor)+'?.matches("#performance-index[open] .walk-mark")','citation returns to the same signed attribute');
  }
  console.log('PASS R'+rev,row?.role || 'historical','signed PDF purpose, owner and installment coverage');
}
