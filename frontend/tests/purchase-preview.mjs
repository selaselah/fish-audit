import assert from 'node:assert/strict';
import {createHash,randomUUID} from 'node:crypto';
import {inspect} from './review-screen.mjs';

const q=selector=>'document.querySelector('+JSON.stringify(selector)+')';
const profiles={
  contract:['cn-contract-performance/v1','合同履约与分期','合同','各期付款条件'],
  purchase:['cn-procurement-full-settlement/v1','采购与付款','发票','全额结算勾稽'],
  travel:['cn-travel-reimbursement/v1','差旅报销','具名发票','行程及发生日期'],
  payment:['cn-bank-contract-payment/v1','付款回单核对','一张银行回单','收款账户']
};
async function key(ctx,name) {
  const code=name==='Escape'?27:name==='Enter'?13:0;
  for (const type of ['keyDown','keyUp'])
    await ctx.call('Input.dispatchKeyEvent',{type,key:name,code:name,windowsVirtualKeyCode:code});
}
async function home(ctx,suffix='') {
  await ctx.call('Page.navigate',{url:ctx.root+'/'+suffix});
  await ctx.wait(q('.start-preview')+' && !'+q('.start-preview')+'.hidden','public intake controls');
}
async function choose(ctx,alias) {
  const [,title,document,check]=profiles[alias];
  await ctx.evaluate(q('.start-options input[value="'+alias+'"]')+'.click()');
  assert.equal(await ctx.evaluate(q('.start-preview h3')+'.textContent'),title);
  for (const [selector,text] of [['.start-materials',document],['.start-checks',check]])
    assert.ok(await ctx.evaluate(q(selector)+'.textContent.includes('+JSON.stringify(text)+')'),text);
}
async function start(ctx,alias) {
  await choose(ctx,alias);
  await ctx.evaluate(q('.audit-start button[type=submit]')+'.click()');
  await ctx.wait('location.pathname==="/app"','public form enters workspace');
}
async function upload(ctx,alias,company) {
  const [id]=profiles[alias], dialog=q('#upload-dialog');
  await ctx.wait(dialog+'?.open && '+q('#intake-scopes input:checked')+'?.value==='+JSON.stringify(id),alias+' intake');
  assert.deepEqual(await ctx.evaluate('['+q('#upload-profile')+'.value,'+q('#intake-workspace')+'.textContent,'+
    q('#upload-files')+'.files.length,new URLSearchParams(location.search).has("new")]'),[id,company,0,false]);
}
async function guest(ctx,alias) {
  await ctx.wait(q('#account-panel .auth-card')+'?.textContent.includes('+JSON.stringify(profiles[alias][1])+')','guest sees selected scope');
  assert.ok(await ctx.evaluate('!'+q('#upload-dialog')+'.open && new URLSearchParams(location.search).get("new")==='+JSON.stringify(alias)));
}
async function noTenantRequests(ctx) {
  assert.equal(await ctx.evaluate('performance.getEntriesByType("resource").filter(e=>new URL(e.name).pathname.startsWith("/api/")).length'),0);
}
async function pickOnPaper(ctx,doc,width) {
  const canvas=q('#sample-review canvas'),target=doc.lines[1];
  const box=await ctx.evaluate(canvas+'.getBoundingClientRect().toJSON()');
  const [pw,ph]=doc.size, scale=Math.min(box.width/pw,box.height/ph), [l,t,r,b]=target.rects[0];
  const point={x:box.x+(box.width-pw*scale)/2+(l+r)/2*pw*scale,y:box.y+(box.height-ph*scale)/2+(t+b)/2*ph*scale};
  await ctx.call('Input.dispatchMouseEvent',{type:'mousePressed',x:box.x+3,y:box.y+3,button:'left',clickCount:1});
  await ctx.call('Input.dispatchMouseEvent',{type:'mouseReleased',x:box.x+3,y:box.y+3,button:'left',clickCount:1});
  assert.equal(await ctx.evaluate(canvas+'.dataset.fact'),doc.lines[0].ref);
  if (width<600) {
    await ctx.call('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:1});
    await ctx.call('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[point]});
    await ctx.call('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  } else {
    await ctx.call('Input.dispatchMouseEvent',{type:'mouseMoved',...point});
    assert.equal(await ctx.evaluate(canvas+'.style.cursor'),'zoom-in');
    await ctx.call('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});
    await ctx.call('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});
  }
  await ctx.wait(canvas+'.dataset.fact==='+JSON.stringify(target.ref)+' && '+q('#sample-review [data-scale=line]')+'.getAttribute("aria-pressed")==="true"','paper selects physical row');
  assert.equal(await ctx.evaluate('document.activeElement.dataset.ref'),target.ref);
  if (width<600) await ctx.call('Emulation.setTouchEmulationEnabled',{enabled:false});
}
export async function checkPurchasePreview(ctx) {
  const {root,call,wait,evaluate}=ctx;
  const record=await (await fetch(root+'/assets/purchase-preview.json')).json();
  const {mode}=await (await fetch(root+'/api/session')).json();
  assert.equal(record.revision,8);
  assert.deepEqual(Object.keys(record.documents).sort(),['acceptance','contract','transfer']);
  for (const doc of Object.values(record.documents)) {
    for (const [path,sha] of [[doc.pdf,doc.source_sha256],[doc.image,doc.page_sha256]]) {
      const response=await fetch(root+path);
      assert.equal(response.status,200);
      assert.equal(createHash('sha256').update(Buffer.from(await response.arrayBuffer())).digest('hex'),sha,path);
    }
  }
  for (const width of [320,360,390,768,1024,1440]) {
    await call('Emulation.setDeviceMetricsOverride',{width,height:width<600?844:900,deviceScaleFactor:1,mobile:width<600});
    await home(ctx,'?width='+width);
    await wait(q('#sheet-acceptance .purchase-line')+'?.naturalWidth>0','real source crop rendered');
    const imagePaths=Object.values(record.documents).map(d=>d.image);
    assert.ok(await evaluate('!performance.getEntriesByType("resource").some(e=>'+JSON.stringify(imagePaths)+'.includes(new URL(e.name).pathname))'),'full pages load on demand');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'home fits '+width);
    if ([390,1440].includes(width)) await inspect(ctx,width,'#hero-title','purchase-home');
    for (const [slug,doc] of Object.entries(record.documents)) {
      await evaluate(q('#tab-'+slug)+'.click()');
      const slot='#sheet-'+slug+' .purchase-locator',select=q(slot+' select'),link=q(slot+' a');
      assert.equal(await evaluate(select+'.options.length'),3);
      assert.equal(await evaluate(link+'.pathname'),doc.pdf);
      for (const line of doc.lines) {
        const ref=JSON.stringify(line.ref), marker=q(slot+' .purchase-sheet i');
        await evaluate(select+'.value='+ref+';'+select+'.dispatchEvent(new Event("change"))');
        await wait(q(slot+' .purchase-line')+'?.dataset.fact==='+ref,'correct physical crop');
        const position=await evaluate('['+marker+'.style.left,'+marker+'.style.top,'+marker+'.style.width,'+marker+'.style.height].map(x=>parseFloat(x)/100)');
        const [x,y,r,b]=line.rects[0];
        assert.ok(position.every((n,i)=>Math.abs(n-[x,y,r-x,b-y][i])<1e-6),'highlight matches archived coordinates');
        await evaluate(link+'.focus()'); await key(ctx,'Enter');
        await wait(q('#sample-review')+'.open && '+q('#sample-review canvas')+'.dataset.fact==='+ref,'original opens at '+line.ref);
        assert.equal(await evaluate(q('#sample-review output')+'.textContent'),'第 1 页 · 第 '+line.line+' 行');
        assert.equal(await evaluate(q('#sample-review [data-scale=page]')+'.getAttribute("aria-pressed")'),'true');
        assert.equal(await evaluate(q('#sample-review .sample-records a')+'.pathname'),doc.pdf);
        if (line===doc.lines[0] && [390,1440].includes(width)) {
          if (slug==='acceptance') await inspect(ctx,width,'#sample-review canvas','purchase-marks');
          await pickOnPaper(ctx,doc,width);
        }
        await key(ctx,'Escape'); await wait('document.activeElement==='+link,'return to same original');
      }
    }
    await evaluate(q('.ledger-switch [aria-controls=sample-dates]')+'.click()');
    await evaluate(q('#sheet-transfer .phase-jump')+'.click()');
    await wait('location.hash==="#sample-phase-2" && '+q('#sample-phase-2')+'.open && !'+q('#sample-installments')+'.hidden','receipt links to installment terms');
    const clause=q('#sample-phase-2 .phase-original-clause');
    await wait(clause+'?.getClientRects().length','second installment contract line');
    await evaluate(clause+'.click()');
    await wait(q('#sample-review canvas')+'.dataset.fact==="d02/p1/f16"','60% contract clause');
    assert.equal(await evaluate(q('#sample-review output')+'.textContent'),'第 1 页 · 第 17 行');
    await key(ctx,'Escape'); await wait('document.activeElement==='+clause,'return to second installment');
    const compare=q('#sample-phase-2 .phase-temperature');
    await evaluate(compare+'.focus()'); await key(ctx,'Enter');
    await wait(q('#sample-compare')+'.open && [...document.querySelectorAll("#sample-compare canvas")].every(c=>c.dataset.scale==="2")','contract and acceptance readings at payment decision');
    assert.deepEqual(await evaluate('[...document.querySelectorAll("#sample-compare canvas")].map(c=>c.dataset.fact)'),['d02/p1/f13','d04/p1/f11']);
    await key(ctx,'Escape'); await wait('document.activeElement==='+compare,'return to the same payment condition');
    for (const alias of Object.keys(profiles)) await choose(ctx,alias);
    if ([390,1440].includes(width)) await inspect(ctx,width,'#start','purchase-start');
    await noTenantRequests(ctx);
  }
  await call('Network.enable');
  await call('Network.setBlockedURLs',{urls:['*/assets/purchase-preview.json']});
  await home(ctx,'?preview=unavailable');
  for (const slug of Object.keys(record.documents)) {
    await evaluate(q('#tab-'+slug)+'.click()');
    assert.equal(await evaluate(q('#sheet-'+slug+' .purchase-locator a')+'.pathname'),record.documents[slug].pdf);
    assert.equal(await evaluate(q('#sheet-'+slug+' .purchase-locator select')),null);
  }
  await noTenantRequests(ctx);
  await call('Network.setBlockedURLs',{urls:[]});
  for (const alias of Object.keys(profiles)) {
    await home(ctx); await start(ctx,alias);
    if (mode==='saas') await guest(ctx,alias); else await upload(ctx,alias,'本机工作区');
  }
  console.log('PASS · R8 三份原件九处字段、第二期条款、六种屏宽、原始 PDF 回退、四种审计入口 · '+mode);
}

export async function checkIntakeEntry(ctx) {
  const {call,root,evaluate,wait,entry,click}=ctx;
  const first='合成演练 · 青禾采购',second='合成演练 · 云桥服务';
  const login='intake.demo',password=randomUUID();
  await home(ctx,'#start'); await start(ctx,'travel'); await guest(ctx,'travel');
  await click('创建企业账号');
  await entry({workspace:first,name:'林审计',login,password});
  await upload(ctx,'travel',first);
  const firstId=await evaluate('Team.current.id');
  await evaluate(q('#upload-dialog [data-close]')+'.click()');
  const secondId=await evaluate('post("/api/workspaces",{name:'+JSON.stringify(second)+'}).then(info=>info.selected)');
  assert.match(secondId,/^[a-f0-9]{32}$/); assert.notEqual(firstId,secondId);
  async function chooseCompany(alias,id,name) {
    const panel=q('#account-panel');
    await wait(panel+'?.textContent.includes("选择本次审计所属企业") && '+panel+'.textContent.includes('+JSON.stringify(profiles[alias][1])+')','explicit workspace selection');
    assert.ok(await evaluate('!'+q('#upload-dialog')+'.open'));
    assert.equal(await evaluate('performance.getEntriesByType("resource").filter(e=>/\\/api\\/w\\//.test(new URL(e.name).pathname)).length'),0);
    await evaluate(q('#account-panel a[href="#w/'+id+'/desk"]')+'.click()');
    await upload(ctx,alias,name);
    assert.equal(await evaluate('Team.current.id'),id);
  }
  await home(ctx,'#start'); await start(ctx,'payment');
  await chooseCompany('payment',secondId,second);
  await call('Page.navigate',{url:root+'/app?new=contract#w/'+firstId+'/desk'});
  await upload(ctx,'contract',first);
  await call('Page.navigate',{url:root+'/app#account'}); await wait(q('#account-panel')+'?.textContent.includes("退出登录")','signed account');
  await click('退出登录'); await wait(q('#account-panel input[name=password]'),'guest after logout');
  await home(ctx,'#start'); await start(ctx,'purchase'); await guest(ctx,'purchase');
  await entry({login,password});
  await chooseCompany('purchase',firstId,first);
  await call('Page.navigate',{url:root+'/app?new=travel'});
  await wait(q('#account-panel a[href="/app#account"]'),'can cancel pending multi-company intake');
  await evaluate(q('#account-panel a[href="/app#account"]')+'.click()');
  await wait(q('#account-panel')+'?.textContent.includes("我的企业") && !location.search','cancel returns to account');
  assert.ok(await evaluate('!'+q('#upload-dialog')+'.open'));
  console.log('PASS · 隔离企业注册、单企业直达、多企业选择、显式企业链接、重新登录和取消新建');
}
