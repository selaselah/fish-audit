import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {checkSigningImages} from './signing-images.mjs';

export async function checkSigningParties({root,call,evaluate,wait}, cid, fixed) {
  const base = root+'/api/cases/'+cid;
  const detail = await (await fetch(base)).json();
  assert.match(detail.title,/^合成演练 · /);
  const rev = Number(fixed || detail.rev);
  const {report} = await (await fetch(base+'/reports/'+rev)).json();
  const signed = report.findings.find(f=>f.rule==='H01');
  const q = s=>'document.querySelector('+JSON.stringify(s)+')';
  const panel = q('.seal-inspector'), dialog = q('#page-dialog');
  const key = k=>call('Input.dispatchKeyEvent',{type:'keyDown',key:k,code:k});
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+rev});
  await wait(q('.performance-overview')+' && state.bundle.rev==='+rev,'fixed contract workpaper');
  const images=await checkSigningImages({call,evaluate,wait,q},report,rev);
  const entries = signed?.effect_review?.party_seals;
  if (!entries?.length) {
    assert.equal(await evaluate(panel+'!==null'),Boolean(images));
    console.log('PASS · R'+rev+' · no signing comparison issued · '+images+' review pages'); return;
  }
  const primary=entries.find(r=>r.status==='risk') || entries.find(r=>r.status!=='ok') || entries[0];
  assert.equal(await evaluate(panel+'.dataset.side'),primary.side);
  assert.equal(await evaluate(panel+'.open'),Boolean(images) || entries.some(r=>r.status!=='ok'));
  await evaluate(panel+'.open=true');
  const sections=report.graph.contract_effect_sources.signing_rows;
  const facts=new Map(report.graph.facts.map(f=>[f.id,f]));
  for (const [i,record] of entries.entries()) {
    const tab=q('.seal-side[data-side="'+record.side+'"]');
    await evaluate(tab+'.focus()'); await key(i?'End':'Home');
    assert.equal(await evaluate('document.activeElement.dataset.side'),record.side);
    assert.equal(await evaluate(panel+'.dataset.state'),record.state);
    for (const id of Object.values(record.rows).flat()) {
      const row=sections.find(r=>r.id===id);
      const button=q('[data-signing-row="'+id+'"]');
      assert.equal(await evaluate(button+'.title'),row.quote);
      const origin=record.field_sources?.find(s=>s.row===id);
      if (origin && (images || origin.kind!=='text')) {
        const badge=button+'.querySelector(".seal-origin")';
        assert.equal(await evaluate(badge+'.dataset.kind'),origin.kind);
        if (['image','mixed'].includes(origin.kind)) {
          assert.equal(await evaluate(badge+'.dataset.usable'),String(Boolean(origin.receipt_rev) && !origin.disputed));
          assert.ok(await evaluate(badge+'.innerText.endsWith("P'+row.page+'")'));
        }
      }
      await evaluate(button+'.click()');
      const observed=row.facts.map(id=>facts.get(id)).filter(f=>f.field===row.field && f.quote===row.quote &&
        (row.line==null || f.source_line?.number===row.line && f.source_line.text===row.quote && f.source_line.rects.length));
      const fact=observed.length===1 ? observed[0] : null;
      const selected=q('#page-dialog .located');
      await wait(dialog+'.open && '+q('#page-dialog .page-image')+'?.naturalWidth>0','archived contract page');
      if (fact || row.line) {
        await wait(selected,'cited field or printed line');
        assert.ok(await evaluate(selected+'.textContent.includes('+JSON.stringify(row.quote)+')'));
      }
      const src=await evaluate(q('#page-dialog .source-tools a')+'.href');
      assert.equal(new URL(src).searchParams.get('rev'),String(rev));
      assert.match(new URL(src).pathname,new RegExp('/documents/'+row.doc+'/pages/'+row.page+'$'));
      const pageHash=createHash('sha256').update(Buffer.from(await (await fetch(src)).arrayBuffer())).digest('hex');
      assert.equal(pageHash,report.graph.nodes.find(n=>n.id===row.doc+'/p'+row.page).sha256);
      if (fact) {
        assert.equal(await evaluate(selected+'.dataset.fact'),fact.id);
        if (origin?.kind==='image') assert.equal(await evaluate('document.querySelectorAll("#page-dialog svg rect").length'),0);
      }
      else if (row.line) {
        assert.equal(await evaluate(selected+'.dataset.gapLine'),String(row.line));
        const expected=facts.get(row.facts[0])?.source_line;
        const rects=expected?.text===row.quote && expected.number===row.line ? expected.rects : [];
        assert.equal(await evaluate('document.querySelectorAll("#page-dialog svg rect").length'),rects.length);
      } else assert.equal(await evaluate('document.querySelectorAll("#page-dialog svg rect").length'),0);
      await evaluate(dialog+'.close()');
    }
  }
  await evaluate(q('.seal-side[data-side="'+primary.side+'"]')+'.click()');
  if (primary.state==='different') assert.ok(await evaluate(q('.seal-body mark')+'?.textContent.length>0'));
  if (entries.length>1) {
    await evaluate(q('.seal-side')+'.focus()'); await key('ArrowRight');
    assert.equal(await evaluate('document.activeElement.dataset.side'),entries[1].side);
    await key('ArrowLeft'); assert.equal(await evaluate('document.activeElement.dataset.side'),entries[0].side);
  }
  await evaluate(q('.seal-side[data-side="'+primary.side+'"]')+'.click()');
  for (const width of [320,390,600,768,1024,1440]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    assert.ok(await evaluate(panel+'.scrollWidth<='+panel+'.clientWidth+1'),'panel fits '+width);
    assert.ok(await evaluate('[...'+panel+'.querySelectorAll(".seal-row")].every(b=>b.scrollWidth<=b.clientWidth+1)'));
    if (process.env.AUDIT_UI_SHOTS && [390,1440].includes(width)) {
      await evaluate(panel+'.scrollIntoView({block:"center"});document.activeElement.blur()');
      const clip=await evaluate('(()=>{const r='+panel+'.getBoundingClientRect(); return {x:r.left+scrollX,y:r.top+scrollY,width:r.width,height:r.height,scale:1}})()');
      const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'party-'+cid+'-R'+rev+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
    }
  }
  const jump=q('.seal-payments');
  if (await evaluate(jump+'!==null')) {
    await evaluate(jump+'.click()');
    assert.ok(await evaluate('Boolean(document.activeElement.dataset.phaseChoice)'));
  }
  // Keep textual evidence available when a scope, relationship, receipt or graph node is detached.
  for (const record of entries.filter(r=>r.comparison.length)) {
    const mutations = ['edge','row','party',...(record.state==='match'?['receipt']:[])];
    for (const mutation of mutations) {
      const result=await evaluate(`(()=>{
        const report=structuredClone(state.bundle.report), graph=report.graph, finding=report.findings.find(f=>f.rule==='H01');
        const record=finding.effect_review.party_seals.find(r=>r.side===${JSON.stringify(record.side)});
        const [left,right]=record.comparison;
        if (${JSON.stringify(mutation)}==='edge') graph.edges=graph.edges.filter(e=>e.type!=='contract_seal_name_comparison' || e.to!==right);
        if (${JSON.stringify(mutation)}==='row') graph.nodes.find(n=>n.id===left).label+='异';
        if (${JSON.stringify(mutation)}==='party') graph.edges=graph.edges.filter(e=>e.from!==record.unit || e.type!==record.side);
        if (${JSON.stringify(mutation)}==='receipt'){
          const line=graph.contract_effect_sources.signing_rows.find(s=>s.id===record.rows.signature[0]);
          graph.facts.find(f=>line.facts.includes(f.id) && f.field===line.field).attestation.source_check.report_hash='0'.repeat(64);
        }
        const view=SigningParties.panel(finding,graph,[]);
        view.querySelector('.seal-side[data-side="'+record.side+'"]').click();
        return [view.dataset.state,view.dataset.status];
      })()`);
      assert.deepEqual(result,['pending','missing'],mutation);
    }
  }
  await evaluate(q('#tabs [data-tab=graph]')+'.click()');
  const paired=entries.filter(r=>r.comparison.length);
  if (paired.length) {
    const group=q('.signing-relations');
    await wait(group,'graph comparison');
    await evaluate(group+'.querySelector("summary").click()');
    await wait(q('.seal-pair'),'two original endpoints');
    for (const r of paired) {
      const pair=q('.seal-pair[data-side="'+r.side+'"]');
      const labels=await evaluate('[...'+pair+'.querySelectorAll("button")].map(b=>b.textContent)');
      assert.deepEqual(labels,r.comparison.map(id=>sections.find(s=>s.id===id).quote));
    }
    await evaluate(q('.seal-pair button:last-child')+'.click()');
    await wait(dialog+'.open && '+q('#page-dialog .located'),'graph link opens original');
  } else assert.equal(await evaluate(q('.signing-relations')),null);
  console.log('PASS · R'+rev+' · '+entries.map(r=>r.side+' '+r.state).join(' / ')+' · six widths, keyboard and original citations');
}
