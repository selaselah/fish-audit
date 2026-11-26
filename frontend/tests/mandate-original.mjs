import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {browserInput,inspect,size} from './review-screen.mjs';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';
const all=s=>'[...document.querySelectorAll('+JSON.stringify(s)+')]';
const checks='#performance-index', reader='#page-dialog', opener='[data-audit-scope="contract"]';
const states={
  word_text:'Word 打印页仅见排印文字，签发待核',word_visual:'Word 打印页需核图，签章痕迹待核',
  word_review:'Word 审阅记录及签发依据待核',photo:'照片原件，授权方签章待核',review:'委托书原件的签发依据待核'
};

// Exercise the same binding used by the card and every finding citation with a fresh report per change.
function brokenSources(findingId,id) {
  const issued=state.bundle.report;
  function load() {
    const report=structuredClone(issued), g=report.graph, ledger=g.mandate_original_sources;
    const h=report.findings.find(f=>f.id===findingId), entry=h.delegations.find(e=>e.mandate_originals?.includes(id));
    const r=ledger.records.find(r=>r.id===id), word=ledger.documents.find(w=>w.id===r.review);
    const note=word?.notes.find(n=>r.notes.includes(n.id)), source=g.edges.find(e=>e.type==='mandate_original_source' && e.to===id);
    return {report,g,ledger,h,entry,r,word,note,source};
  }
  const {r,word,note}=load();
  const refList=[id,r.doc,...r.pages.map(p=>p.ref),...r.fields,...(word?[word.id]:[]),...r.notes,...(note?.location?.facts || [])];
  const edits={
    marker:b=>delete b.report.policy.mandate_originals, ledger:b=>b.ledger.format='unknown',
    declaration:b=>delete b.entry.mandate_originals, scope:b=>b.h.scope=b.h.scope.filter(u=>u!==r.unit),
    side:b=>b.entry.side='other', role:b=>b.g.documents_by_kind.power_of_attorney=[],
    entryStatus:b=>b.entry.status='ok', findingStatus:b=>{b.h.status=b.g.nodes.find(n=>n.id==='finding/'+findingId).status='ok';},
    unit:b=>b.entry.units=[], duplicate:b=>b.ledger.records.push({...b.r}),
    kind:b=>b.r.kind='pdf', original:b=>b.r.original_sha256='0'.repeat(64),
    node:b=>b.g.nodes.find(n=>n.id===id).state='other', page:b=>b.r.pages[0].sha256='0'.repeat(64),
    layer:b=>b.r.pages[0].layer='other', layout:b=>b.r.pages[0].text_only=!b.r.pages[0].text_only,
    call:b=>b.report.calls.pages.find(p=>r.pages.some(s=>s.ref===p.doc+'/p'+p.page)).page_sha256='other',
    source:b=>b.source.from='other', sourceOrder:b=>b.source.evidence.reverse(),
    notes:b=>b.r.notes.push('another note'), unplaced:b=>b.r.unplaced++,
  };
  for (const ref of new Set(refList)) {
    edits['entry '+ref]=b=>b.entry.evidence=b.entry.evidence.filter(x=>x!==ref);
    edits['finding '+ref]=b=>b.h.evidence=b.h.evidence.filter(x=>x!==ref);
    edits['support '+ref]=b=>b.g.edges.find(e=>e.type==='supports_result' && e.from===ref && e.to==='finding/'+findingId).evidence=[];
  }
  if (r.fields.length) {
    edits.field=b=>b.g.facts.find(f=>f.id===r.fields[0]).unit='other';
    edits.fieldEdge=b=>b.g.edges=b.g.edges.filter(e=>e.type!=='records' || e.to!==r.fields[0]);
    edits.fieldList=b=>{b.r.fields=[]; b.source.evidence=b.source.evidence.filter(x=>!r.fields.includes(x));};
  }
  if (word) {
    edits.word=b=>b.r.review='mandate-word/other';
    edits.wordSource=b=>b.g.edges=b.g.edges.filter(e=>e.type!=='mandate_word_review_source');
    edits.wordUnit=b=>b.word.units=['another unit'];
    edits.wordLink=b=>b.g.edges.find(e=>e.type==='mandate_original_word' && e.to===id).from='other';
    edits.wordDigest=b=>b.word.original_sha256='0'.repeat(64);
    edits.coverage=b=>b.word.coverage='unknown';
    if (r.state==='word_text') edits.emptyText=b=>{
      for (const p of b.r.pages) b.g.nodes.find(n=>n.id===p.ref).text_sha256='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';
    };
    if (r.state==='word_text' && r.fields.some(id=>issued.graph.facts.find(f=>f.id===id)?.source_line?.rects?.length)) {
      edits.falseVisual=b=>b.r.state=b.g.nodes.find(n=>n.id===id).state='word_visual';
    }
  }
  if (r.unit!==r.doc) edits.section=b=>b.g.edges=b.g.edges.filter(e=>e.type!=='section_page' || e.from!==r.unit);
  if (load().entry.signature_field) edits.crossedSide=b=>b.entry.side=b.entry.side==='buyer'?'seller':'buyer';
  if (note) {
    const owner=b=>b.g.edges.find(e=>e.to===note.id && e.type==='mandate_original_comment');
    edits.noOwner=b=>b.g.edges=b.g.edges.filter(e=>e!==owner(b));
    edits.crossedOwner=b=>owner(b).from='mandate-original/another-unit';
    edits.ownerEvidence=b=>owner(b).evidence=owner(b).evidence.slice(1);
    edits.duplicateOwner=b=>b.g.edges.push({...owner(b),from:'mandate-original/another-unit'});
    edits.reviewComment=b=>b.g.edges.find(e=>e.to===note.id && e.type==='mandate_word_review_comment').from='other';
    edits.part=b=>b.word.part_sha256='';
    edits.omitNote=b=>b.r.notes=b.r.notes.filter(ref=>ref!==note.id);
    if (note.anchor) edits.selection=b=>b.note.anchor.selected+='其他';
    if (note.location) {
      edits.noteUnit=b=>b.note.location.unit='other';
      edits.textDigest=b=>b.note.location.text_sha256='0'.repeat(64);
      edits.anchorEdge=b=>b.g.edges.find(e=>e.type==='mandate_word_review_anchor' && e.to===note.id).evidence=[];
      edits.ownerPage=b=>owner(b).evidence[2]='other/p1';
      if (note.location.facts.length) {
        edits.line=b=>b.note.location.line++;
        edits.ownerField=b=>owner(b).evidence.pop();
      }
    }
  }
  const failed=[];
  for (const [name,change] of Object.entries(edits)) {
    const b=load(); change(b);
    if (PerformanceIndex.mandateEvidence(b.h,b.report).some(m=>m.proofs.some(p=>p.record.id===id)) ||
        [id,...r.notes].some(ref=>PerformanceIndex.mandateCitation(b.report,ref,b.h).matches('button,a'))) failed.push(name);
  }
  return {failed,count:Object.keys(edits).length};
}

// The archive remains read-only. Render ambiguous Word ownership and photo-only fallbacks in this tab.
function localVariants(findingId,id) {
  const saved=state.bundle, outcomes={};
  function change(edit) {
    const bundle=structuredClone(saved), g=bundle.report.graph, ledger=g.mandate_original_sources;
    const h=bundle.report.findings.find(f=>f.id===findingId), r=ledger.records.find(r=>r.id===id);
    const entry=h.delegations.find(e=>e.mandate_originals?.includes(id)), word=ledger.documents.find(w=>w.id===r.review);
    edit({g,r,h,entry,word});
    document.querySelector('#performance-index').close(); state.bundle=bundle; renderCase(true);
    const opener=document.querySelector('[data-audit-scope="contract"]'); opener.focus(); opener.click();
    return document.querySelector('#performance-index');
  }
  const r=saved.report.graph.mandate_original_sources.records.find(r=>r.id===id);
  try {
    if (r.state==='word_text') {
      const visual=change(({g,r})=>{
        r.state=g.nodes.find(n=>n.id===id).state='word_visual';
        for (const p of r.pages) {p.text_only=false; g.nodes.find(n=>n.id===p.ref).clause_text_only=false;}
      });
      outcomes.wordVisual=Boolean(visual.querySelector('[data-state="word_visual"] [data-mandate-original]'));
      const partial=change(({g,r,word})=>{
        r.state=g.nodes.find(n=>n.id===id).state='word_review'; word.coverage='partial'; word.limitations=['tracked'];
      });
      const review=partial.querySelector('[data-mandate-review]'); if (review) review.open=true;
      outcomes.partialReview=Boolean(review?.textContent.includes('审阅范围待核') && !review.querySelector('blockquote,mark'));
    }
    if (r.state==='word_review' && r.notes.length) {
      for (const mode of ['missing','crossed']) {
        const dialog=change(({g})=>{
          const owner=g.edges.find(e=>e.type==='mandate_original_comment' && e.from===id);
          if (mode==='missing') g.edges=g.edges.filter(e=>e!==owner);
          else owner.from='mandate-original/another-unit';
        });
        const related=state.bundle.report.findings.filter(f=>['H01','H04','H05'].includes(f.rule) && f.evidence.includes(r.notes[0]));
        outcomes[mode]=!dialog.querySelector('[data-mandate-original="'+id+'"], [data-mandate-note]') &&
          related.every(f=>!citation(r.notes[0],f).matches('a,button'));
      }
      if (r.unit===r.doc) {
        const dialog=change(({g,r,word})=>{
          for (const note of word.notes.filter(n=>r.notes.includes(n.id))) {
            note.location=null;
            g.edges=g.edges.filter(e=>e.type!=='mandate_word_review_anchor' || e.to!==note.id);
            g.edges.find(e=>e.type==='mandate_original_comment' && e.from===id && e.to===note.id).evidence=[r.doc,word.id];
          }
        });
        const review=dialog.querySelector('[data-mandate-review]'); if (review) review.open=true;
        outcomes.documentNote=Boolean(review?.querySelector('blockquote') && !review.querySelector('.word-page-jump'));
      }
      if (r.unit===r.doc && r.pages.length===1) {
        const dialog=change(({g,r,h,entry,word})=>{
          const unit='unit/'+r.doc+'/p1', split='mandate-original/'+unit;
          g.audit_documents=(g.audit_documents || g.documents).map(d=>d.id===r.doc?{...d,id:unit,source:r.doc,page:1}:d);
          g.documents_by_kind.power_of_attorney=g.documents_by_kind.power_of_attorney.map(u=>u===r.unit?unit:u);
          g.nodes.push({id:unit,type:'document_section',source:r.doc,page:1});
          g.edges.push({from:r.doc,to:unit,type:'contains_section',evidence:[r.doc+'/p1']},
            {from:unit,to:r.doc+'/p1',type:'section_page',evidence:[r.doc+'/p1']});
          for (const f of g.facts.filter(f=>f.doc===r.doc)) f.unit=unit;
          g.nodes.find(n=>n.id===id).id=split;
          const omitted=new Set(r.notes);
          g.edges=g.edges.filter(e=>!(omitted.has(e.to) && ['mandate_original_comment','mandate_word_review_anchor'].includes(e.type)));
          for (const e of g.edges) {
            if (e.type==='mandate_original_source' && e.to===id) e.from=unit;
            if (e.to===id) e.to=split;
            if (e.from===id) e.from=split;
            e.evidence=e.evidence.map(x=>x===id?split:x);
          }
          h.scope=h.scope.map(x=>x===r.unit?unit:x); entry.units=entry.units.map(x=>x===r.unit?unit:x);
          entry.mandate_originals=entry.mandate_originals.map(x=>x===id?split:x);
          for (const holder of [entry,h]) holder.evidence=holder.evidence.filter(x=>!omitted.has(x)).map(x=>x===id?split:x);
          word.units=word.units.map(x=>x===r.unit?unit:x);
          for (const n of word.notes) if (omitted.has(n.id)) n.location=null;
          r.id=split; r.unit=unit; r.unplaced=word.notes.filter(n=>!n.location).length; r.notes=[];
        });
        const review=dialog.querySelector('[data-mandate-review]'); if (review) review.open=true;
        outcomes.unplaced=Boolean(review?.textContent.includes('单元归属待核') && !review.querySelector('blockquote,mark') &&
          !citation(r.notes[0]).matches('button,a') && dialog.querySelector('[data-mandate-original]'));
      }
    }
    if (r.kind==='image') {
      if (r.fields.length) {
        const dialog=change(({g,r})=>{
          const f=g.facts.find(f=>f.id===r.fields[0]); f.source_line={number:88,text:f.quote,rects:[[0,0,.7,.7]]};
        });
        dialog.querySelector('[data-mandate-original]').click();
        const page=document.querySelector('#page-dialog');
        outcomes.photoCoordinates=page.querySelector('.located')?.dataset.fact===r.fields[0] &&
          !page.querySelector('.source-plane svg rect') && !page.querySelector('.located').textContent.includes('文字层第');
        page.close();
      }
      const dialog=change(({g,r})=>{
        const fields=new Set(r.fields);
        g.facts=g.facts.filter(f=>!fields.has(f.id)); g.nodes=g.nodes.filter(n=>!fields.has(n.id));
        g.edges=g.edges.filter(e=>!fields.has(e.from) && !fields.has(e.to));
        g.edges.find(e=>e.type==='mandate_original_source' && e.to===id).evidence=[r.doc,...r.pages.map(p=>p.ref)];
        r.fields=[];
      });
      dialog.querySelector('[data-mandate-original]').click();
      const page=document.querySelector('#page-dialog');
      outcomes.wholePage=page.open && !page.querySelector('.located,.source-plane svg rect');
      page.close();
      const pending=change(({g,r})=>{r.state=g.nodes.find(n=>n.id===id).state='review';});
      outcomes.review=Boolean(pending.querySelector('[data-state="review"] [data-mandate-original]'));
    }
  } finally {
    document.querySelector('#performance-index').close(); state.bundle=saved; renderCase(true);
    const open=document.querySelector('[data-audit-scope="contract"]'); open.focus(); open.click();
  }
  return outcomes;
}

export async function checkMandateOriginal(ctx,id,requested,expected) {
  const {root,call,evaluate,wait}=ctx, api=root+'/api/cases/'+id;
  const task=await (await fetch(api)).json();
  assert.match(task.title,/^合成演练/u);
  const rev=Number(requested ?? task.rev), legacy=expected==='legacy';
  assert.ok(Number.isSafeInteger(rev) && rev>0 && (!expected || legacy || Object.hasOwn(states,expected)));
  const response=await fetch(api+'/reports/'+rev); assert.equal(response.status,200);
  const bundle=await response.json(), {graph,findings,policy}=bundle.report;
  assert.equal(bundle.rev,rev);
  const h=findings.find(f=>f.rule==='H01' && f.delegations?.length); assert.ok(h);
  const ledger=graph.mandate_original_sources;
  const records=h.delegations.flatMap(e=>(e.mandate_originals || []).map(id=>ledger.records.find(r=>r.id===id)));
  if (legacy) {
    assert.equal(policy.mandate_originals,undefined); assert.equal(records.length,0);
  } else {
    assert.equal(policy.mandate_originals,'mandate-original-execution-v1');
    assert.ok(records.length && (!expected || records.some(r=>r.state===expected)),'requested issued original');
  }
  const prefix=id+'-r'+rev+'-'+(legacy?'legacy':records.map(r=>r.state).join('-'));
  const {key,pointAt,tap}=browserInput(ctx), verified=new Set();
  async function bytes(url,hash) {
    if (verified.has(url)) return;
    const response=await fetch(url); assert.equal(response.status,200);
    assert.equal(createHash('sha256').update(Buffer.from(await response.arrayBuffer())).digest('hex'),hash);
    verified.add(url);
  }
  async function press(control,width,keyboard=false) {
    const p=await pointAt(control);
    assert.ok(await evaluate(control+'.checkVisibility() && '+control+'.contains(document.elementFromPoint('+p.x+','+p.y+'))'),'reachable '+control+' at '+width);
    if (keyboard) {await evaluate(control+'.focus()'); await key('Enter');}
    else if (width<600) await tap(control);
    else for (const type of ['mousePressed','mouseReleased']) await call('Input.dispatchMouseEvent',{type,...p,button:'left',clickCount:1});
  }
  async function openPage(control,width,{doc,page,field,photo},shot) {
    await press(control,width,width===1440);
    const url=api+'/documents/'+doc+'/pages/'+page+'?rev='+rev;
    await wait(q(reader)+'?.open && '+q(reader+' .source-tools a')+'?.href==='+JSON.stringify(url)+' && '+q(reader+' .page-image')+'?.naturalWidth>0','pinned original '+doc+' p'+page);
    assert.equal(await evaluate(q('#reader-revision')+'.textContent'),'R'+rev);
    assert.equal(await evaluate(q(reader+' .located')+'?.dataset.fact || null'),field || null);
    const fact=graph.facts.find(f=>f.id===field);
    if (photo || fact?.source_line?.rects) {
      const rects=await evaluate(all(reader+' .source-plane > svg:first-of-type rect')+'.map(r=>["x","y","width","height"].map(k=>Number(r.getAttribute(k))))');
      assert.deepEqual(rects,photo?[]:fact.source_line.rects.map(([l,t,r,b])=>[1000*l,1000*t,1000*(r-l),1000*(b-t)]));
    }
    if (photo) assert.ok(!/文字层第\s*\d+\s*行/u.test(await evaluate(q(reader+' .viewer-facts')+'.innerText')));
    await bytes(url,graph.nodes.find(n=>n.id===doc+'/p'+page).sha256);
    await bytes(api+'/documents/'+doc+'/original?rev='+rev,graph.documents.find(d=>d.id===doc).sha256);
    if (shot) await inspect(ctx,width,reader,prefix+'-'+shot);
    await key('Escape');
    await wait('!'+q(reader)+'.open && document.activeElement==='+control,'focus returned to the source');
  }
  async function oldPath(width) {
    const pick=q(checks+' .scope-source-head select'), open=q(checks+' .scope-open-original');
    if (!await evaluate(open+'?.checkVisibility()')) await evaluate(all(checks+' .scope-detail > details > summary')+'.find(s=>s.textContent==="其他字段引文").click()');
    await wait(open+'?.checkVisibility()','field originals available');
    const fields=await evaluate('PerformanceIndex.originals(state.bundle.report.findings.find(f=>f.id==='+JSON.stringify(h.id)+'),state.bundle.report.graph).map(r=>r.fact.id)');
    const fact=graph.facts.find(f=>f.field==='grant_signature' && fields.includes(f.id)) || graph.facts.find(f=>fields.includes(f.id) && h.delegations.some(e=>e.units.includes(f.unit || f.doc)));
    assert.ok(fact);
    if (await evaluate(pick+'!==null')) await evaluate(pick+'.value='+JSON.stringify(String(fields.indexOf(fact.id)))+';'+pick+'.dispatchEvent(new Event("change"))');
    assert.equal(await evaluate(open+'.dataset.fact'),fact.id);
    await openPage(open,width,{doc:fact.doc,page:fact.page,field:fact.id},legacy?'original':null);
  }
  const navigate=()=>call('Page.navigate',{url:root+'/workpaper/'+id+'?rev='+rev+'&view=contract-checks'});
  await navigate();
  await wait(q(checks)+'?.open && state.bundle.rev==='+rev+' && '+q('#scope-title')+'.textContent==="签署与生效"','pinned H01');
  assert.equal(await evaluate(q(checks+' .scope-check-state .tag')+'.dataset.state'),h.status);
  assert.equal(await evaluate(q('.conclusion-panel')+'.dataset.verdict'),bundle.report.result.verdict);
  if (task.status==='ready' && task.rev===rev) {
    assert.ok(await evaluate(all('button.primary')+'.some(b=>b.textContent==="填写验收意见")'),'manual acceptance remains available');
  }
  const full=[390,1440];
  for (const width of (legacy?full:[...full,320,360,768,1024])) {
    await size(ctx,width); await call('Emulation.setTouchEmulationEnabled',{enabled:width<600});
    await evaluate(q(checks)+'.scrollTop=0');
    assert.deepEqual(await evaluate(all(checks+' .scope-mandate-record:has([data-mandate-original])')+'.map(el=>el.dataset.state)'),records.map(r=>r.state));
    assert.ok(await evaluate(all(checks+', '+checks+' .scope-mandate-proof, '+checks+' .scope-mandate-record')+'.every(el=>el.scrollWidth<=el.clientWidth+1)'),'original card fits at '+width);
    if (full.includes(width)) await inspect(ctx,width,checks,prefix+'-checks');
    if (legacy) await oldPath(width);
    for (const [index,r] of records.entries()) {
      const buttons=all(checks+' [data-mandate-original="'+r.id+'"]'), row=buttons+'[0].closest(".scope-mandate-record")';
      assert.equal(await evaluate(row+'.querySelector("strong").textContent'),states[r.state]);
      const entry=h.delegations.find(e=>e.mandate_originals?.includes(r.id));
      assert.equal(await evaluate(row+'.closest(".scope-mandate-proof").querySelector(".tag").dataset.state'),entry.status);
      const photo=r.kind==='image', locations=r.fields.map(id=>{
        const f=graph.facts.find(f=>f.id===id); return {doc:r.doc,page:f.page,field:id,photo};
      });
      for (const p of r.pages) {
        const page=Number(p.ref.split('/p').at(-1));
        if (!locations.some(l=>l.page===page)) locations.push({doc:r.doc,page,photo});
      }
      assert.equal(await evaluate(buttons+'.length'),locations.length);
      for (const [i,loc] of locations.entries()) {
        const control=buttons+'['+i+']';
        assert.ok(await evaluate(control+'.getBoundingClientRect().height>=44'));
        if (!i && !index) {
          assert.ok(await evaluate(control+'.getBoundingClientRect().bottom<='+q(checks)+'.getBoundingClientRect().bottom'),'first source visible at '+width);
          if (full.includes(width)) {
            await evaluate(q(checks+' .scope-head button:last-child')+'.focus()');
            for (let tries=0;tries<30 && !await evaluate('document.activeElement==='+control);tries++) await key('Tab');
            assert.ok(await evaluate('document.activeElement==='+control),'Tab reaches signing source');
          }
        }
        if (photo) {
          assert.ok(!(await evaluate(control+'.innerText')).includes(' 行'));
          assert.match(await evaluate(control+'.innerText'),/核对整页照片/u);
        }
        await openPage(control,width,loc,full.includes(width) && !i?'original-'+index:null);
      }
      const word=ledger.documents.find(w=>w.id===r.review);
      if (word) {
        const file=row+'.querySelector(".scope-mandate-file")';
        assert.equal(await evaluate(file+'.href'),api+'/documents/'+r.doc+'/original?rev='+rev);
        assert.equal(await evaluate(file+'.download'),graph.documents.find(d=>d.id===r.doc).name);
        const details=row+'.querySelector("details[data-mandate-review]")', summary=details+'.querySelector("summary")';
        if (!r.notes.length && !r.unplaced && word.coverage==='complete') {assert.equal(await evaluate(details),null); continue;}
        await press(summary,width,width===1440);
        await wait(details+'.open','review expands');
        assert.ok(await evaluate(row+'.scrollWidth<='+row+'.clientWidth+1'),'review fits at '+width);
        for (const [i,ref] of r.notes.entries()) {
          const n=word.notes.find(n=>n.id===ref), body=details+'.querySelector(".scope-mandate-comment")';
          if (i) await evaluate(details+'.querySelector("select").selectedIndex='+i+';'+details+'.querySelector("select").dispatchEvent(new Event("change"))');
          assert.equal(await evaluate(body+'.dataset.mandateNote'),ref);
          assert.equal(await evaluate(body+'.querySelector("blockquote").textContent'),(n.text || '未提取到批注文字')+(n.shortened?'…':''));
          assert.equal(await evaluate(body+'.querySelector("mark")?.textContent || null'),n.anchor?.selected || null);
          assert.equal(await evaluate(body+'.querySelector(".word-credit small").textContent'),'采纳待核');
          if (full.includes(width) && i===0) await inspect(ctx,width,checks+' [data-mandate-note="'+ref+'"]',prefix+'-comment-'+index);
          const original=body+'.querySelector(".word-page-jump")';
          if (n.location?.facts.length) {
            assert.equal(await evaluate(original+'.innerText'),'第 '+n.location.page+' 页 · 第 '+n.location.line+' 行');
            await openPage(original,width,{doc:r.doc,page:n.location.page,field:n.location.facts[0]},full.includes(width)?'comment-line-'+index:null);
          } else if (n.location) {
            assert.match(await evaluate(original+'.innerText'),/核对整页/u);
            await openPage(original,width,{doc:r.doc,page:n.location.page});
          } else assert.equal(await evaluate(original),null);
        }
        await press(summary,width,width===1440); await wait('!'+details+'.open','review collapses');
      }
    }
    await key('Escape');
    await wait('!'+q(checks)+'.open && document.activeElement==='+q(opener),'Escape restores signing checks entry');
    await key('Enter'); await wait(q(checks)+'.open','keyboard reopens signing checks');
  }
  let changes=0, variants=0, phaseLinks=0;
  await size(ctx,1440); await call('Emulation.setTouchEmulationEnabled',{enabled:false});
  for (const r of records) {
    const result=await evaluate('('+brokenSources.toString()+')('+JSON.stringify(h.id)+','+JSON.stringify(r.id)+')');
    assert.deepEqual(result.failed,[]); changes+=result.count;
    const scenarios=await evaluate('('+localVariants.toString()+')('+JSON.stringify(h.id)+','+JSON.stringify(r.id)+')');
    for (const [name,passed] of Object.entries(scenarios)) {assert.ok(passed,name); variants++;}
    for (const rule of ['H04','H05']) {
      const phase=findings.find(f=>f.rule===rule && f.evidence.includes(r.id));
      if (!phase) continue;
      const row='[data-finding="'+phase.id+'"]';
      await evaluate(q(checks)+'.close();revealPaperTarget('+q(row)+');'+all(row+' summary')+'.find(s=>s.textContent.startsWith("查看本项全部引文")).parentElement.open=true');
      const control=q(row+' [data-mandate-original="'+r.id+'"]');
      await wait(control+'?.checkVisibility()','issued '+rule+' original citation');
      const field=graph.facts.find(f=>f.id===r.fields[0]);
      await openPage(control,1440,{doc:r.doc,page:field?.page || Number(r.pages[0].ref.split('/p').at(-1)),field:field?.id,photo:r.kind==='image'});
      if (r.notes.length && phase.evidence.includes(r.notes[0])) {
        const ref=r.notes[0], button=q(row+' [data-mandate-note-ref="'+ref+'"]');
        await press(button,1440,true);
        await wait(q(checks)+'?.open && '+q(checks+' [data-mandate-note="'+ref+'"]')+'?.checkVisibility() && document.activeElement.matches("[data-mandate-review] summary")','phase opens its Word note');
        await key('Escape'); await wait('!'+q(checks)+'.open && document.activeElement==='+button,'return to phase note citation');
      }
      const bound=await evaluate('(()=>{const p=structuredClone(state.bundle.report),f=p.findings.find(f=>f.id==='+JSON.stringify(phase.id)+'),id='+JSON.stringify(r.id)+';'+
        'p.graph.edges=p.graph.edges.filter(e=>!(e.type==="supports_result" && e.to==="finding/"+f.id && e.from===id));'+
        'return !PerformanceIndex.mandateCitation(p,id,f).matches("a,button") && PerformanceIndex.mandateCitation(p,id).matches("button");})()');
      assert.ok(bound,'payment support is local to the cited finding'); phaseLinks++;
      await evaluate(q(opener)+'.focus()'); await key('Enter'); await wait(q(checks)+'.open','return to signing checks');
    }
  }
  if (!legacy) {
    await evaluate(q(checks)+'.close();state.bundle=structuredClone(state.bundle);state.bundle.report.graph.edges=state.bundle.report.graph.edges.filter(e=>e.type!=="mandate_original_source");renderCase(true);'+q(opener)+'.focus();'+q(opener)+'.click()');
    assert.equal(await evaluate(q(checks+' [data-mandate-original]')),null);
    await oldPath(1440);
  }
  console.log('Mandate originals R'+rev+' '+(expected || records.map(r=>r.state))+' · widths '+(legacy?full:[320,360,390,768,1024,1440]).join('/')+' · '+changes+' binding changes · '+variants+' fallback views · '+phaseLinks+' payment checks');
}
