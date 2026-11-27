import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {browserInput,inspect,size} from './review-screen.mjs';

export async function checkWalkthrough(ctx,caseId,scratch) {
  const {root,call,evaluate,wait}=ctx;
  const q=s=>'document.querySelector('+JSON.stringify(s)+')';
  const press=s=>evaluate(q(s)+'.click()');
  const navigate=url=>call('Page.navigate',{url:root+url});
  const type=msg=>evaluate(q('#walk-text')+'.value='+JSON.stringify(msg)+';'+q('#walk-text')+'.dispatchEvent(new Event("input"))');
  async function open() {
    await wait(q('#walk-launch')+'?.getClientRects().length','walkthrough launcher');
    await press('#walk-launch');
    await wait(q('#walk-dialog')+'?.open && !'+q('#walk-save')+'.disabled','ready to write');
  }
  async function history(count) {
    await press('#walk-saved');
    await wait(q('#walk-saved span')+'.textContent==='+JSON.stringify(String(count)),'saved note count');
  }
  async function save() {await press('#walk-save');await wait('!'+q('#walk-dialog')+'.open','saved and returned to the site');}
  const url='/?scene=payment-release&slip=late&token=discard-this-token#workflow';
  await navigate(url); await wait(q('#payment-release .release-pane')+'?.dataset.releaseView==="dates"','public example');
  const width=caseId?390:1440;
  if (caseId) {
    await size(ctx,320);
    await call('Network.enable');await call('Network.setBlockedURLs',{urls:['*/api/session']});
    await press('#walk-launch');
    await wait(q('#walk-retry')+'?.getClientRects().length','initial connection can be retried in place');
    await type('重试前的草稿');
    assert.ok(await evaluate(q('#walk-dialog')+'.getBoundingClientRect().right<=innerWidth'));
    await call('Network.setBlockedURLs',{urls:[]});await press('#walk-retry');
    await wait('!'+q('#walk-save')+'.disabled','retry reconnects');
    assert.equal(await evaluate(q('#walk-text')+'.value'),'重试前的草稿');
    await type('');await press('#walk-close');
  }
  await size(ctx,width);
  await evaluate(q('#payment-release')+'.scrollIntoView({block:"center"})');
  await open();
  const opinion='希望在放行权限旁显示合同条款入口。';
  await type(opinion);await press('#walk-pick');
  const target='#payment-release .release-tab[data-view=authority]';
  if (width===390) {
    await call('Emulation.setTouchEmulationEnabled',{enabled:true});
    await browserInput(ctx).tap(q(target));
  } else await press(target);
  await wait(q('#walk-dialog')+'.open && '+q('#walk-location')+'.textContent.includes("放行权限")','point without activating the selected control');
  assert.equal(await evaluate(q('#payment-release .release-pane')+'.dataset.releaseView'),'dates');
  assert.equal(await evaluate(q('#walk-text')+'.value'),opinion);
  await inspect(ctx,width,'#walk-dialog','walkthrough-compose');
  if (caseId) {
    await call('Network.enable'); await call('Network.setBlockedURLs',{urls:['*/api/walkthrough']});
    await press('#walk-save');await wait(q('#walk-status')+'.textContent.includes("保存失败")','failed write stays editable');
    assert.equal(await evaluate(q('#walk-text')+'.value'),opinion);
    await call('Network.setBlockedURLs',{urls:[]});
  }
  await save();
  await call('Page.reload',{ignoreCache:true});await wait(q('#release-example')+'?.value==="late"','reload the selected example');
  await open();await history(1);
  const historyLink='#walk-history li a';
  const dest=new URL(await evaluate(q(historyLink)+'.href'));
  assert.equal(dest.searchParams.get('slip'),'late');assert.equal(dest.searchParams.get('token'),null);
  assert.equal(dest.searchParams.get('walkat'),await evaluate(q(target)+'.id'));
  // Capture the browser call without reading or replacing the operator's clipboard.
  await evaluate('Object.defineProperty(navigator.clipboard,"writeText",{configurable:true,value:async text=>{window.walkTestCopy=text}});true');
  await call('Page.bringToFront');
  const point=await browserInput(ctx).pointAt(q('#walk-copy'));
  for (const type of ['mousePressed','mouseReleased']) await call('Input.dispatchMouseEvent',{type,button:'left',clickCount:1,...point});
  await wait(q('#walk-status')+'.textContent.includes("已复制")','Codex clipboard handoff');
  const copied=await evaluate('window.walkTestCopy');
  assert.ok(copied.includes(opinion) && copied.includes(dest.href) && !copied.includes('discard-this-token'));
  await call('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:scratch});
  await press('#walk-download');
  let exported;
  for (let i=0;i<60 && !exported;i++) {
    try {exported=await readFile(join(scratch,'Fish-Audit-走查意见.md'),'utf8');} catch {await new Promise(r=>setTimeout(r,60));}
  }
  assert.equal(exported,copied);
  await inspect(ctx,width,'#walk-dialog','walkthrough-list');
  await press(historyLink);
  await wait('location.search.indexOf("token")<0 && '+q(target)+'?.classList.contains("walk-mark")','return to highlighted original control');
  if (caseId) {
    await navigate('/app#case/'+caseId+'?rev=1&walktab=evidence&walkdoc=d01&walkpage=1');
    await wait(q('#page-dialog')+'?.open && '+q('#page-dialog #walk-launch')+' && '+q('#page-dialog .page-image')+'?.naturalWidth','private original-page launcher');
    await open();
    assert.match(await evaluate(q('#walk-location')+'.textContent'),/R1.*d01.*第 1 页/);
    await type('希望这里保留原页页码。');await press('#walk-close');
    await wait('!'+q('#walk-dialog')+'.open && '+q('#page-dialog')+'.open','underlying original stays open');
    await open();assert.match(await evaluate(q('#walk-text')+'.value'),/原页页码/);await save();
    await navigate('/app#desk');await wait(q('#case-list'),'desk');await open();await history(2);
    await press(historyLink);
    await wait(q('#page-dialog')+'?.open && '+q('#page-dialog .page-view')+'?.dataset.doc==="d01" && '+q('#reader-revision')+'.textContent==="R1"','saved route reopens the exact issued original');
    const notes=(await (await fetch(root+'/api/walkthrough')).json()).notes;
    assert.equal(notes.length,2);assert.equal(notes[0].context.case_id,caseId);
    assert.equal(notes[0].context.rev,1);assert.equal(notes[0].context.page,1);
    await navigate('/app?new=payment#desk');await wait(q('#upload-dialog')+'?.open && '+q('#upload-dialog #walk-launch'),'intake has a feedback action');
    await open();await type('付款回单的上传入口');await save();
    await navigate('/app#desk');await open();await history(3);
    assert.equal(new URL(await evaluate(q(historyLink)+'.href')).searchParams.get('new'),'payment');
    await press(historyLink);await wait(q('#upload-dialog')+'?.open && '+q('#upload-profile')+'.value==="cn-bank-contract-payment/v1"','return to the chosen intake');
  } else {
    const wid=await evaluate(`fetch('/api/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({login:'weekend-walker',name:'演练员',password:'synthetic-password-17',workspace:'演练企业'})}).then(r=>r.json()).then(r=>r.selected)`);
    assert.match(wid,/^[0-9a-f]{32}$/);await navigate('/app#w/'+wid+'/desk');await wait('typeof Team!=="undefined" && Team.current?.id==='+JSON.stringify(wid),'private workspace');
    await open();await history(0);await press('#walk-compose');await type('这条意见属于企业走查。');await save();
    await open();await history(1);assert.equal(await evaluate(q('#walk-history li p')+'.textContent'),'这条意见属于企业走查。');
  }
  console.log('PASS · '+(caseId?'local workpaper and original revision':'public browser and private enterprise')+' · point, draft, save, reload, export and return');
}
