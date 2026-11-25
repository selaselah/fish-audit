import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';

const q=s=>'document.querySelector('+JSON.stringify(s)+')';

export async function checkEntityBrowser({root,call,evaluate,wait},cid) {
  const api=root+'/api/cases/'+cid, task=await (await fetch(api)).json();
  assert.ok(task.title.startsWith('合成演练'));
  const {report}=await (await fetch(api+'/reports/'+task.rev)).json(), g=report.graph;
  await call('Page.navigate',{url:root+'/workpaper/'+cid+'?rev='+task.rev+'&view=entities'});
  const panel=q('#case-entity-browser'), combo=q('#entity-object'), docs=q('#entity-document'), original=q('.entity-open');
  await wait(panel+' && document.activeElement.id==="case-entity-browser"','entity view');
  if (await evaluate(panel+'.dataset.empty==="true"')) {
    assert.ok(g.number_masks?.facts?.length,'synthetic masked invoice case');
    assert.equal(await evaluate('EntityBrowser.items(state.bundle.report.graph).length'),0);
    assert.equal(await evaluate('Boolean('+original+')'),false);
    await evaluate(panel+'.querySelector("button").click()');
    assert.equal(await evaluate(q('#tabs [data-tab=evidence]')+'.getAttribute("aria-pressed")'),'true');
    console.log('PASS · '+task.title+' R'+task.rev+' · masked references withheld, originals reachable'); return;
  }
  assert.ok(await evaluate('!document.querySelector("#trace-select") && !document.querySelector(".graph-relations").open && !document.querySelector(".graph-relations .panel")'));
  const select=(selector,value)=>evaluate(selector+'.value='+JSON.stringify(value)+';'+selector+'.dispatchEvent(new Event("change"))');
  const units=new Set();
  for (const width of [320,390,768,820,1024,1440]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:false});
    const buttons='.entity-segments button';
    const categories=await evaluate('[...document.querySelectorAll('+JSON.stringify(buttons)+')].map(b=>b.textContent)');
    for (const [i,label] of categories.entries()) {
      await evaluate(q(buttons+'[aria-pressed=true]')+'.focus()');
      const key=i?'ArrowRight':'Home';
      for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key,code:key,windowsVirtualKeyCode:i?39:36});
      assert.equal(await evaluate('document.activeElement.textContent'),label);
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'page overflow at '+width);
      assert.deepEqual(await evaluate('[...'+panel+'.querySelectorAll("button:not([hidden]),select:not([hidden])")].filter(b=>b.offsetWidth<44 || b.offsetHeight<44).map(b=>[b.outerHTML.slice(0,100),b.offsetWidth,b.offsetHeight])'),[]);
      let options=await evaluate('Array.from('+combo+'.options,o=>o.value)');
      // Inspect every printed reference in the desktop view, and one entity per category at other widths.
      if (width!==1440) options=options.slice(0,1);
      for (const id of options) {
        await select(combo,id);
        const choices=await evaluate('Array.from('+docs+'.options,o=>o.value)');
        assert.ok(choices.length);
        assert.ok((await evaluate(q('.entity-count')+'.textContent')).endsWith(' / '+choices.length+' 份'));
        for (const unit of (width===1440?choices:choices.slice(0,1))) {
          await select(docs,unit); units.add(unit);
          const picker=q('.entity-location select');
          const facts=await evaluate('Array.from('+picker+'.options,o=>o.value)');
          for (const factId of facts) {
            await select(picker,factId);
            const f=g.facts.find(f=>f.id===factId), doc=g.documents.find(d=>d.id===f.doc);
            assert.equal(f.unit || f.doc, unit);
            assert.ok(g.edges.some(e=>e.from===unit && e.to===id && e.type===f.field && e.evidence.length===1 && e.evidence[0]===f.id));
            assert.equal(await evaluate(q('.entity-proof blockquote')+'.textContent'),f.source_line?.rects?.length?f.source_line.text:f.quote);
            assert.equal(await evaluate(original+'.dataset.entityFact'),f.id);
            assert.ok(doc && ['confirmed','anchored'].includes(f.status));
          }
        }
        if (id===options[0]) {
          const fid=await evaluate(original+'.dataset.entityFact'), f=g.facts.find(f=>f.id===fid);
          await evaluate(original+'.click()');
          await wait(q('#page-dialog .located')+'?.dataset.fact==='+JSON.stringify(fid)+' && '+q('#page-dialog .page-image')+'?.naturalWidth>0','entity to original');
          const link=new URL(await evaluate(q('#page-dialog a[target=_blank]')+'.href'));
          assert.ok(link.pathname.endsWith('/'+f.doc+'/pages/'+f.page)); assert.equal(link.searchParams.get('rev'),String(task.rev));
          if (width===1440) assert.equal(createHash('sha256').update(Buffer.from(await (await fetch(link)).arrayBuffer())).digest('hex'),f.page_sha256);
          await evaluate(q('#page-dialog [data-close]')+'.click()');
        }
      }
    }
    if ((width===1440 || width===390) && process.env.AUDIT_UI_SHOTS) {
      await evaluate(q('.entity-segments button')+'.click()');
      const defect=g.nodes.find(n=>n.type==='defect_number');
      const ids=await evaluate('Array.from('+combo+'.options,o=>o.value)');
      await select(combo,ids.includes(defect?.id)?defect.id:ids[0]);
      await evaluate(docs+'.selectedIndex=Math.floor('+docs+'.length/2);'+docs+'.dispatchEvent(new Event("change"))');
      if (await evaluate('!'+q('.entity-preview')+'.hidden && '+q('.entity-preview')+'.getAttribute("aria-pressed")!=="true"')) await evaluate(q('.entity-preview')+'.click()');
      if (await evaluate('!'+q('.entity-preview')+'.hidden')) await wait(q('.entity-crop canvas'),'printed crop');
      await evaluate(panel+'.scrollIntoView({block:"center"});document.activeElement?.blur();document.fonts.ready.then(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))');
      const clip=await evaluate('(()=>{const r='+panel+'.getBoundingClientRect();return {x:r.x+scrollX-4,y:r.y+scrollY-4,width:r.width+8,height:r.height+8,scale:1}})()');
      const {data}=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
      await writeFile(join(process.env.AUDIT_UI_SHOTS,'entities-'+cid.slice(0,5)+'-'+width+'.png'),Buffer.from(data,'base64'));
    }
  }
  if (g.audit_documents?.some(d=>d.source)) assert.ok([...units].some(id=>id.startsWith('unit/')));
  await evaluate(q('.entity-segments button')+'.click();'+combo+'.selectedIndex=0;'+combo+'.dispatchEvent(new Event("change"));'+docs+'.selectedIndex=0;'+docs+'.dispatchEvent(new Event("change"))');
  if (await evaluate(docs+'.length>1 && !'+q('.entity-preview')+'.hidden')) {
    if (await evaluate(q('.entity-preview')+'.getAttribute("aria-pressed")!=="true"')) await evaluate(q('.entity-preview')+'.click()');
    for (const direction of ['下一份关联单据','上一份关联单据']) {
      await evaluate(q('button[aria-label="'+direction+'"]')+'.click()');
      const at=await evaluate(docs+'.selectedIndex');
      assert.equal(at,direction.startsWith('下')?1:0);
      const ref=await evaluate(original+'.dataset.entityFact');
      if (await evaluate('!'+q('.entity-preview')+'.hidden')) {
        await wait(q('.entity-crop')+'.dataset.fact==='+JSON.stringify(ref)+' && '+q('.entity-crop canvas')+'?.width>0','original crop follows selected document');
      }
    }
    await evaluate(q('.entity-preview')+'.click()');
    assert.ok(await evaluate(q('.entity-crop')+'.hidden'));
    const late=await evaluate(`(async()=>{
      const pane=document.querySelector('.entity-browser'), select=pane.querySelector('#entity-document');
      const toggle=pane.querySelector('.entity-preview'), crop=pane.querySelector('.entity-crop');
      const actual=EvidenceCompare.lineExcerpt, first=pane.querySelector('.entity-open').dataset.entityFact;
      let release,firstStarted;
      const held=new Promise(resolve=>{firstStarted=resolve;});
      EvidenceCompare.lineExcerpt=async(f,i)=>{
        const canvas=await actual(f,i);
        if(f.id===first) await new Promise(resolve=>{release=resolve;firstStarted();});
        return canvas;
      };
      try {
        toggle.click(); await held;
        select.selectedIndex=1; select.dispatchEvent(new Event('change'));
        const next=pane.querySelector('.entity-open').dataset.entityFact;
        const imageVisible=!toggle.hidden;
        if(imageVisible) await new Promise((resolve,reject)=>{
          if(crop.dataset.fact===next) return resolve();
          const watch=new MutationObserver(()=>{if(crop.dataset.fact===next){clearTimeout(timer);watch.disconnect();resolve();}});
          const timer=setTimeout(()=>{watch.disconnect();reject(new Error('new document crop missing'));},4000);
          watch.observe(crop,{attributes:true,childList:true});
        });
        release(); await new Promise(resolve=>setTimeout(resolve,0));
        return next!==first && (imageVisible?crop.dataset.fact===next:crop.hidden && !crop.dataset.fact);
      } finally { release?.(); EvidenceCompare.lineExcerpt=actual; }
    })()`);
    assert.ok(late,'an older image completed after switching to a different document');
  }
  assert.ok(await evaluate(`(()=>{
    const current=state.bundle.report.graph;
    const masked=new Set((current.number_masks?.facts || []).map(m=>m.fact));
    if (EntityBrowser.items(current).some(i=>[...i.docs.values()].some(d=>d.facts.some(f=>masked.has(f.id))))) return false;
    const g=structuredClone(current); g.edges=g.edges.filter(e=>e.type!=='records'); if(EntityBrowser.panel(g).dataset.empty!=='true') return false;
    const x=structuredClone(current), f=x.facts.find(f=>f.field==='contract_id' && f.source_line);
    if(!f) return true;
    const visible=graph=>EntityBrowser.items(graph).some(i=>[...i.docs.values()].some(d=>d.facts.some(item=>item.id===f.id)));
    const b=structuredClone(x); b.facts.find(a=>a.id===f.id).status='disputed';
    const c=structuredClone(x); c.facts.find(a=>a.id===f.id).page_sha256='wrong';
    const e=structuredClone(x); e.facts.find(a=>a.id===f.id).source_line.text+='（尾号）';
    return !visible(b) && !visible(c) && !visible(e);
  })()`));
  if (await evaluate('Boolean('+q('[data-direction=findings]')+')')) {
    await evaluate(q('[data-direction=findings]')+'.click()');
    assert.ok(await evaluate('document.querySelector("#trace-select") && !document.querySelector("#case-entity-browser")'));
    await evaluate(q('[data-direction=entities]')+'.click()');
    assert.ok(await evaluate('!document.querySelector("#trace-select") && document.querySelector("#case-entity-browser")'));
  }
  await evaluate(q('#tabs [data-tab=report]')+'.click();'+q('#quick-open')+'.click()');
  await evaluate(q('#quick-query')+'.value="按对象查原件";'+q('#quick-query')+'.dispatchEvent(new Event("input"))');
  for (const type of ['keyDown','keyUp']) await call('Input.dispatchKeyEvent',{type,key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await wait(panel+' && document.activeElement.id==="case-entity-browser"','command palette returns to linked objects');
  console.log('PASS · '+task.title+' R'+task.rev+' · 6 widths, '+units.size+' document units, original bytes, keyboard and palette');
}
