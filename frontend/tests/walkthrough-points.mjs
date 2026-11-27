import assert from 'node:assert/strict';
import {browserInput,inspect,size} from './review-screen.mjs';

// Writes personal product notes only in the disposable walkthrough server.
export async function checkPagePoints(ctx,cid,workspace=null) {
  const {root,call,evaluate,wait}=ctx;
  assert.match(root,/^http:\/\/127\.0\.0\.1:\d+$/u);
  assert.ok(!['8000','8010'].includes(new URL(root).port));
  const q=s=>'document.querySelector('+JSON.stringify(s)+')';
  const input=browserInput(ctx), mouse=s=>input.click(q(s)), tap=s=>input.tap(q(s));
  const go=url=>call('Page.navigate',{url});
  const prefix=workspace?'/api/w/'+workspace:'/api', route=workspace?'w/'+workspace+'/':'';
  async function json(path) {
    const address=prefix+path;
    if (workspace) return evaluate('fetch('+JSON.stringify(address)+').then(r=>{if(!r.ok)throw Error(r.status);return r.json()})');
    const response=await fetch(root+address);assert.equal(response.status,200);return response.json();
  }
  const api='/cases/'+cid, task=await json(api);
  assert.match(task.title,/^合成演练/u);
  const rev=Number(process.env.AUDIT_POINT_REV || task.rev), doc=process.env.AUDIT_POINT_DOC || 'd01', page=Number(process.env.AUDIT_POINT_PAGE || 1);
  const filed=await json(api+'/reports/'+rev), node=filed.report.graph.nodes.find(n=>n.id===doc+'/p'+page && n.type==='page');
  const given=(process.env.AUDIT_POINT_XY || '3350,4300').split(',').map(Number);
  const note=process.env.AUDIT_POINT_NOTE || '希望在这个位置旁显示需要核对的原文。';
  const view='#page-dialog[open] .page-view', plane=view+' .source-plane', canvas=view+' .source-scroll';
  const ready=q(view)+'?.dataset.pageSha256==='+JSON.stringify(node.sha256);
  const url=root+'/app#'+route+'case/'+cid+'?rev='+rev+'&walktab=evidence&walkdoc='+doc+'&walkpage='+page;
  const count=(await json('/walkthrough')).notes.length;
  const opened=q('#walk-dialog')+'?.open && !'+q('#walk-point')+'.hidden && !'+q('#walk-point')+'.disabled';
  const docked=q('#walk-rail')+'?.matches(":popover-open")';
  const type=s=>evaluate(q('#walk-text')+'.value='+JSON.stringify(s)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
  async function hit(x,y,touch=false) {
    const pt=await evaluate('(()=>{const c='+q(canvas)+',s='+q(plane+' > svg')+';'+
      'const p=()=>new DOMPoint('+x+'/10,'+y+'/10).matrixTransform(s.getScreenCTM());'+
      'c.scrollIntoView({block:"nearest",behavior:"instant"});const r=c.getBoundingClientRect();'+
      'c.scrollBy({left:p().x-(r.left+r.right)/2,top:p().y-(r.top+r.bottom)/2,behavior:"instant"});'+
      'const t=p();return {x:t.x,y:t.y,ok:'+q(plane)+'.contains(document.elementFromPoint(t.x,t.y))};})()');
    assert.ok(pt.ok,'chosen source pixel is visible');
    if (touch) {
      await call('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:pt.x,y:pt.y}]});
      await call('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    } else for (const type of ['mousePressed','mouseReleased']) await call('Input.dispatchMouseEvent',{type,x:pt.x,y:pt.y,button:'left',clickCount:1});
  }
  await go('about:blank');await call('Emulation.setTouchEmulationEnabled',{enabled:false});
  await size(ctx,1440);await go(url);await wait(ready+' && '+q('#page-dialog #walk-launch')+'?.isConnected','issued original image');
  await mouse('#walk-launch');await wait(opened,'image feedback action');
  await mouse('#walk-dock');await wait(docked,'beside the original');await type(note);
  await mouse('#walk-point');await wait(q('.walk-point-cursor')+'?.isConnected','keyboard cursor');
  assert.equal(await evaluate(q('#walk-save')+'.disabled'),true);
  await input.key('ArrowRight');await input.key('Escape');
  assert.equal(await evaluate(q('.walk-point-cursor')),null);
  assert.equal(await evaluate(q('#walk-text')+'.value'),note);
  await mouse('button[aria-label="放大原页"]');
  for (let turn=1;turn<=4;turn++) {
    await mouse('button[aria-label="向右旋转 90°"]');await mouse('#walk-point');
    await wait(q('.walk-point-cursor')+'?.isConnected','choose a rotated and zoomed source pixel');
    await hit(...given);
    await wait(q('.walk-point-draft')+'?.isConnected && !'+q('.walk-point-cursor'),'rotate coordinates back to the filed page');
    const actual=await evaluate('['+q('.walk-point-draft')+'.style.left,'+q('.walk-point-draft')+'.style.top].map(s=>Math.round(parseFloat(s)*100))');
    assert.ok(given.every((v,i)=>Math.abs(actual[i]-v)<30),'physical point after turn '+turn);
  }
  await mouse('.zoom-fit');
  await inspect(ctx,1440,'#walk-rail','page-point-'+cid.slice(0,8)+'-side');
  await mouse('#walk-save');await wait(q('#walk-status')+'.textContent.includes("已保存")','save the pinned draft');
  const notes=(await json('/walkthrough')).notes;assert.equal(notes.length,count+1);
  const ctx1=notes[0].context,point=ctx1.page_point;
  assert.equal(notes[0].text,note);
  assert.deepEqual([ctx1.case_id,ctx1.rev,ctx1.doc,ctx1.page,point.page_sha256],[cid,rev,doc,page,node.sha256]);
  assert.ok(!ctx1.params && !ctx1.line && !ctx1.anchor);
  assert.ok(Math.abs(point.x-given[0])<30 && Math.abs(point.y-given[1])<30,'rotated source point');
  await mouse('#walk-saved');await wait(q('#walk-history a[href*="walkpoint="]')+'?.getClientRects().length','saved point');
  const link=q('#walk-history a[href*="walkpoint="]'), dest=await evaluate(link+'.href');
  assert.ok(new URL(dest).hash.startsWith('#'+route+'case/'+cid+'?'));
  await evaluate('Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:async text=>{window.pointCopy=text}})');
  await mouse('#walk-copy');await wait('window.pointCopy?.includes('+JSON.stringify(dest)+')','copy the point link');
  assert.ok(await evaluate('window.pointCopy.includes('+JSON.stringify(note)+')'));
  await evaluate(link+'.click()');
  const saved=plane+' .walk-point-saved';
  await wait(ready+' && '+q(saved)+'?.isConnected && !'+q('.walk-point-draft'),'return to the original mark');
  const savedAt=()=>evaluate('['+q(saved)+'.style.left,'+q(saved)+'.style.top].map(s=>Math.round(parseFloat(s)*100))');
  assert.deepEqual(await savedAt(),[point.x,point.y]);
  const docPages=filed.report.graph.documents.find(d=>d.id===doc).pages;
  if (docPages>1) {
    const step=page>1?-1:1;
    await mouse('.reader-step[data-step="'+step+'"]');
    await wait(q(view)+'?.dataset.page==='+JSON.stringify(String(page+step))+' && '+q(view)+'?.dataset.pageSha256','next original has loaded');
    assert.equal(await evaluate(q(saved)),null);
    await mouse('.reader-step[data-step="'+(-step)+'"]');await wait(ready+' && '+q(saved)+'?.isConnected','return to saved page');
    for (const width of [320,390,768,820,1024,1440]) {
      await size(ctx,width);
      await wait(q('.reader-bar')+'?.parentElement.matches('+JSON.stringify(width>=761?'.dialog-head':'#reader-navigation')+')','pager layout at '+width);
      const clear=await evaluate('(()=>{const a='+q('.reader-pager')+'.getBoundingClientRect(),b='+q('#walk-launch')+
        '.getBoundingClientRect(); return a.left>=0 && a.right<=innerWidth && (a.right<=b.left || b.right<=a.left || a.top>=b.bottom || b.top>=a.bottom)})()');
      assert.ok(clear,'page controls and feedback action at '+width);
    }
  }
  await size(ctx,390);await call('Emulation.setTouchEmulationEnabled',{enabled:true});
  await call('Page.reload',{ignoreCache:true});
  await wait(ready+' && '+q(saved)+'?.isConnected','saved location after a mobile reload');
  if (await evaluate(q(plane+' img')+'.naturalWidth>=3*'+q(canvas)+'.clientWidth')) {
    assert.equal(await evaluate(q('.zoom-scale')+'.textContent'),'300%');
  }
  await tap('.walk-point-locate');await inspect(ctx,390,'#page-dialog','page-point-'+cid.slice(0,8)+'-mobile','start');
  await tap('#walk-launch');await wait(opened,'mobile mark');
  await tap('#walk-point');await wait(q('.walk-point-cursor')+'?.isConnected','tap on the actual page');
  await hit(6450,4850,true);await wait(opened+' && '+q('.walk-point-draft')+'?.isConnected','mobile returns to the pinned editor');
  const touchAt=await evaluate('['+q('.walk-point-draft')+'.style.left,'+q('.walk-point-draft')+'.style.top].map(s=>Math.round(parseFloat(s)*100))');
  assert.ok(Math.abs(touchAt[0]-6450)<60 && Math.abs(touchAt[1]-4850)<60,'mobile tap');
  await tap('#walk-close');await call('Page.reload',{ignoreCache:true});await wait(ready,'reloaded page');
  await tap('#walk-launch');await wait(opened+' && '+q('.walk-point-draft')+'?.isConnected','restore the mobile draft');
  assert.equal(await evaluate(q('#walk-text')+'.value'),'');
  await type('手机原页定位。');
  await tap('#walk-point');await wait('document.activeElement==='+q(canvas),'accessible point movement');
  await input.key('ArrowDown');await input.key('Enter');await wait(opened,'confirm a keyboard adjustment');
  await tap('#walk-save');await wait('!'+q('#walk-dialog')+'.open','save mobile adjustment');
  const last=(await json('/walkthrough')).notes;
  assert.equal(last.length,count+2);const p2=last[0].context.page_point;
  assert.ok(Math.abs(p2.x-touchAt[0])<=1 && p2.y>touchAt[1] && p2.y-touchAt[1]<200,'keyboard adjustment after a mobile tap');
  await go(dest.replace(point.page_sha256,'a'.repeat(64)));
  await wait(ready+' && '+q('.source-tools')+'?.textContent.includes("与这版页图不符")','mismatched page digest');
  assert.equal(await evaluate(q(saved)),null);
  await call('Network.enable');
  await call('Network.setBlockedURLs',{urls:['*/documents/'+doc+'/pages/'+page+'?rev='+rev]});
  await go(dest);
  await wait(q(view+' .source-error button')+'?.getClientRects().length','unavailable source image');
  assert.equal(await evaluate(q(saved)),null);
  await tap('#walk-launch');await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','ordinary feedback remains available');
  assert.equal(await evaluate(q('#walk-point')+'.hidden'),true);
  await tap('#walk-close');await call('Network.setBlockedURLs',{urls:[]});await tap(view+' .source-error button');
  await wait(ready+' && '+q(saved)+'?.isConnected','retry the verified original and restore its marker');
  const after=await json(api);assert.deepEqual([after.rev,after.status,after.decisions,after.referrals],[task.rev,task.status,task.decisions,task.referrals]);
  assert.deepEqual(await json(api+'/reports/'+rev),filed);
  if (workspace) assert.equal((await fetch(root+prefix+'/walkthrough')).status,401);
  console.log('PASS · '+cid+' R'+rev+' '+doc+'/p'+page+' · rotated source, keyboard and touch, pinned draft, copied location, original report intact · '+point.x+','+point.y);
}
