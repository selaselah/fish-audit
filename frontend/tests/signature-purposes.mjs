import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

export async function checkSignaturePurposes(ctx,cid,requested) {
  const {root,call,evaluate,wait}=ctx,{click,key}=browserInput(ctx);
  const base=root+'/api/cases/'+cid, task=await (await fetch(base)).json();
  assert.ok(task.title.startsWith('合成演练') && task.title.includes('到货数量'));
  const rev=Number(requested || task.rev), {report}=await (await fetch(base+'/reports/'+rev)).json();
  const row=report.graph.signature_purposes?.rows[0];
  const q=s=>'document.querySelector('+JSON.stringify(s)+')';
  const path=root+'/workpaper/'+cid+'?rev='+rev;
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
