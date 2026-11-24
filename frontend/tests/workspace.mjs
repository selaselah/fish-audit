// Exercise the real registration, invitation and workspace navigation in an isolated browser and database.
import assert from 'node:assert/strict';
import {spawn, execFileSync} from 'node:child_process';
import {mkdtemp, readFile, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {createServer} from 'node:net';
import {createHash} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';
import {once} from 'node:events';

const scratch = await mkdtemp(join(tmpdir(), 'fish-ui-'));
const socket = createServer().listen(0, '127.0.0.1');
await once(socket, 'listening');
const port = socket.address().port;
await new Promise(resolve => socket.close(resolve));
const sampleDesk = process.argv.includes('--sample-desk');
function caseArgument(name) {
  const index = process.argv.indexOf(name);
  if (index < 0) return null;
  const id = process.argv[index+1];
  assert.match(id || '',/^[a-f0-9]{32}$/);
  return id;
}
const paymentCase = caseArgument('--payment-case');
const supplementCase = caseArgument('--supplement-case');
const peerCase = caseArgument('--peer-case');
const seeded = sampleDesk || paymentCase || supplementCase || peerCase;
const root = 'http://127.0.0.1:' + (seeded ? 8000 : port);
const children = [];
const faults = [];
function start(binary, args, env = process.env) {
  const child = spawn(binary, args, {stdio:'ignore', env});
  child.on('error', error => faults.push(error.message)); children.push(child);
  return child;
}
async function until(read, label, timeout = 15000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (faults.length) throw new Error(faults.join('\n'));
    const result = await read().catch(() => null);
    if (result) return result;
    await delay(100);
  }
  throw new Error('Timed out waiting for ' + label);
}
let ws;
try {
  if (!seeded) start(process.env.AUDIT_PYTHON || 'server/.venv/bin/python', ['server/main.py'], {...process.env,
    PORT:String(port), AUDIT_BIND:'127.0.0.1', AUDIT_ACCESS_MODE:'saas', AUDIT_PUBLIC_ORIGIN:root,
    AUDIT_DATA_DIR:join(scratch, 'data')});
  await until(async () => (await fetch(root+'/api/health')).ok,'service');
  const chrome = process.env.CHROME_BIN || (process.platform === 'darwin'
    ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : 'google-chrome');
  start(chrome,['--headless=new','--no-first-run','--disable-extensions','--disable-background-networking',
    '--remote-debugging-port=0','--user-data-dir='+join(scratch,'browser'),'about:blank']);
  const debugPort = await until(async () => (await readFile(join(scratch,'browser','DevToolsActivePort'),'utf8')).split('\n')[0], 'Chrome');
  const targets = await (await fetch('http://127.0.0.1:'+debugPort+'/json/list')).json();
  ws = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
  await new Promise(resolve => ws.addEventListener('open', resolve, {once:true}));
  const pending = new Map();
  let sequence = 0;
  ws.addEventListener('message', ({data}) => {
    const msg = JSON.parse(data);
    if (pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
    if (msg.method === 'Runtime.exceptionThrown') faults.push(msg.params.exceptionDetails.exception?.description || 'Browser exception');
  });
  async function call(method, params={}) {
    const id = ++sequence;
    const result = new Promise(resolve => pending.set(id, resolve));
    ws.send(JSON.stringify({id,method,params}));
    const msg = await result;
    if (msg.error) throw new Error(msg.error.message);
    return msg.result;
  }
  const evaluate = async expression => {
    const reply = await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if (reply.exceptionDetails) throw new Error(reply.exceptionDetails.exception?.description);
    return reply.result.value;
  };
  const wait = (expr,label,ms) => until(()=>evaluate(expr),label,ms);
  const entry = async (values) => {
    await evaluate('Object.entries('+JSON.stringify(values)+').forEach(([k,v]) => document.querySelector("#account-panel input[name="+k+"]").value = v)');
    await evaluate('document.querySelector("#account-panel input[name=password]").form.requestSubmit()');
  };
  const click = (label, container='document') => evaluate('[...'+container+'.querySelectorAll("button,a")].find(b=>b.textContent==='+JSON.stringify(label)+' && b.getClientRects().length).click()');
  await call('Runtime.enable');
  await call('Page.navigate',{url:root});
  if (peerCase) {
    const base = root+'/api/cases/'+peerCase;
    const detail = await (await fetch(base)).json();
    assert.ok(detail.title.startsWith('合成演练 · '));
    const bundle = await (await fetch(base+'/reports/'+detail.rev)).json();
    const peer = bundle.report.peer_review;
    assert.ok(peer?.findings?.length);
    const originalUrl = root+'/workpaper/'+peerCase+'?rev='+peer.source_rev;
    await call('Page.navigate',{url:originalUrl});
    const next = await wait('document.querySelector(".peer-panel a.source-jump")?.href','immutable referral and resolution link');
    assert.equal(new URL(next).searchParams.get('rev'),String(bundle.rev));
    await call('Page.navigate',{url:next});
    await wait('!!document.querySelector(".peer-panel a[href*=finding]")','cited original finding');
    const selected = await evaluate('document.querySelector(".peer-panel a[href*=finding]").href');
    const target = new URL(selected);
    assert.equal(target.searchParams.get('rev'),String(peer.source_rev));
    assert.ok(peer.findings.includes(target.searchParams.get('finding')));
    if (peer.resolution.decision==='return') assert.ok(await evaluate('document.querySelector("#supplement-family").textContent.includes("提交补件")'));
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'peer workpaper at '+width);
    }
    await call('Page.navigate',{url:selected});
    await wait('document.querySelector("#trace-select")?.value==='+JSON.stringify(target.searchParams.get('finding')),'frozen review evidence');
    console.log('PASS · Signed referral, peer decision, original finding, return intake and six viewport widths');
  } else if (supplementCase) {
    const base = root+'/api/cases/';
    const child = await (await fetch(base+supplementCase)).json();
    assert.ok(child.title.startsWith('合成演练 · '));
    const current = (await (await fetch(base+supplementCase+'/reports/'+child.rev)).json()).report;
    const origin = current.supplement;
    const parent = await (await fetch(base+origin.parent)).json();
    assert.ok(parent.title.startsWith('合成演练 · '));
    const old = (await (await fetch(base+origin.parent+'/reports/'+origin.rev)).json()).report;
    const group = origin.comparisons.find(g=>g.rule==='B01') || origin.comparisons[0];
    const previousId = group.before[0].id;
    await call('Page.navigate',{url:root+'/workpaper/'+supplementCase});
    await wait('!!document.querySelector(".return-comparison")','returned workpaper comparison');
    const otherRisk = current.findings.find(f=>f.status!=='ok' && !origin.comparisons.some(g=>g.rule===f.rule));
    if (otherRisk) {
      await evaluate('[...document.querySelectorAll(".return-comparison details")].find(d=>d.querySelector("summary").textContent.startsWith("本次其他风险与缺口")).open=true');
      const url = await wait('[...document.querySelectorAll(".return-comparison a")].find(a=>a.textContent.startsWith('+JSON.stringify(otherRisk.rule+' ')+'))?.href','additional finding on new material');
      assert.equal(new URL(url).searchParams.get('finding'),otherRisk.id);
      await call('Page.navigate',{url});
      await wait('document.querySelector("#trace-select")?.value==='+JSON.stringify(otherRisk.id),'new risk evidence path');
      await call('Page.navigate',{url:root+'/workpaper/'+supplementCase});
      await wait('!!document.querySelector(".return-comparison")','comparison reopened');
    }
    await evaluate('[...document.querySelectorAll(".return-comparison details")].find(d=>d.querySelector("summary").textContent.startsWith('+JSON.stringify(group.rule+' ')+')).open=true');
    const before = await wait('document.querySelector(".return-comparison a[href*=finding]")?.href','signed parent finding link');
    assert.equal(new URL(before).pathname,'/workpaper/'+origin.parent);
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'supplement comparison at '+width);
    }
    await call('Page.navigate',{url:before});
    if (old.graph.nodes.some(n=>n.id==='finding/'+previousId))
      await wait('document.querySelector("#trace-select")?.value==='+JSON.stringify(previousId),'signed parent evidence path');
    else await wait('document.activeElement?.dataset.finding==='+JSON.stringify(previousId),'legacy finding focused on original workpaper');
    await click('提交补件','document.querySelector("#supplement-family")');
    await wait('document.querySelector("#upload-dialog")?.open && document.querySelector("#upload-profile").disabled','returned intake');
    assert.equal(await evaluate('document.querySelectorAll("#retain-files input:checked").length'),parent.documents.length);
    await evaluate('document.querySelectorAll("#retain-files input:checked").forEach(c=>c.click());document.querySelector("#upload-form").requestSubmit()');
    await wait('document.querySelector("#upload-error").textContent.includes("请选择")','empty supplement validation');
    await evaluate('document.querySelector("#retain-files input").click()');
    if (process.argv.includes('--live')) {
      assert.match(parent.title,/^合成演练 · 缺银行回单 · [A-F0-9]{8}$/);
      const code = parent.title.slice(-8);
      const title = '合成演练 · 手机补交回单 · '+code;
      let id = parent.supplements.find(c=>c.title===title)?.id;
      if (!id) {
        const file = resolve('docs/samples/generated/11-退回补交银行回单',code,'银行付款回单.pdf');
        assert.equal(createHash('sha256').update(await readFile(file)).digest('hex'),
          child.documents.find(d=>d.name==='银行付款回单.pdf').sha256);
        const {root:dom} = await call('DOM.getDocument');
        const {nodeId} = await call('DOM.querySelector',{nodeId:dom.nodeId,selector:'#upload-files'});
        await call('DOM.setFileInputFiles',{nodeId,files:[file]});
        await evaluate('document.querySelector("#upload-title").value='+JSON.stringify(title)+';document.querySelector("#supplement-note").value="手机端演练补交原回单";document.querySelector("#upload-form").requestSubmit()');
        await wait('!document.querySelector("#upload-dialog").open && document.querySelector("#case-title").textContent==='+JSON.stringify(title),'new mobile submission');
        id = await evaluate('location.hash.split("/").pop()');
      } else await call('Page.navigate',{url:root+'/workpaper/'+id});
      await wait('!!document.querySelector(".return-comparison")','live supplemental audit',540000);
      const saved = (await (await fetch(base+id+'/reports/1')).json()).report;
      assert.equal(saved.supplement.parent,origin.parent);
      assert.deepEqual(saved.supplement.retained,origin.retained);
      assert.equal(saved.supplement.reason,parent.decisions.at(-1).note);
      console.log('Live mobile supplement '+id+' · '+saved.result.verdict);
    }
    console.log('PASS · Signed return, versioned finding link, retained originals and mobile supplemental intake at six widths');
  } else if (paymentCase) {
    const base = root+'/api/cases/'+paymentCase;
    const detail = await (await fetch(base)).json();
    assert.ok(detail.title.startsWith('合成演练 · '),'use a marked training task');
    const report = (await (await fetch(base+'/reports/'+detail.rev)).json()).report;
    const match = report.graph.payment_history.matches[0];
    const citation = match.evidence.find(f=>f.field==='transfer_ref');
    const rule = match.kind === 'same' ? 'B06' : 'B07';
    await call('Page.navigate',{url:root+'/workpaper/'+paymentCase});
    await wait('!!document.querySelector(".finding")','payment finding');
    await evaluate('(()=>{const target=[...document.querySelectorAll(".finding")].find(f=>f.querySelector(".mono")?.textContent==='+JSON.stringify(rule)+'); [...target.querySelectorAll("button")].find(b=>b.textContent==="查看证据路径").click()})()');
    await wait('document.querySelector("#trace-select")?.value.startsWith('+JSON.stringify(rule+'-')+')','payment evidence path');
    await evaluate('for(const d of document.querySelectorAll(".trace-sources > details")) d.open=true');
    const historical = await wait('[...document.querySelectorAll(".trace-sources a")].find(a=>a.textContent.endsWith("交易流水号"))?.href','archived transfer link');
    assert.equal(new URL(historical).pathname,'/workpaper/'+match.case_id);
    assert.equal(new URL(historical).searchParams.get('fact'),citation.fact);
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'payment trace layout at '+width);
    }
    await evaluate('[...document.querySelectorAll(".trace-sources a")].find(a=>a.textContent.endsWith("交易流水号")).click()');
    const located = 'document.querySelector("#page-dialog")?.open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(citation.fact);
    await wait(located,'historical fact opened in app');
    assert.ok(await evaluate('document.querySelector(".located").textContent.includes('+JSON.stringify(citation.value)+')'));
    await call('Page.navigate',{url:historical});
    await wait(located,'archived revision reopened from independent URL');
    assert.ok(await evaluate('document.querySelector("#case-title").textContent==='+JSON.stringify(match.title)));
    console.log('PASS · '+rule+' links a signed payment to its exact historical revision and printed transfer reference across six viewport widths');
  } else if (sampleDesk) {
    await wait('!!document.querySelector(".case-link")','seeded workbench');
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
      const layout = await evaluate('({width:innerWidth,content:document.documentElement.scrollWidth,brand:document.querySelector(".brand").getBoundingClientRect().right,rail:document.querySelector(".bar").getBoundingClientRect().right})');
      assert.ok(layout.content<=layout.width+1 && layout.brand<=layout.rail+1,'workbench layout at '+width);
    }
    await evaluate('const search=document.querySelector("#case-search");search.value="收款账户变更与超付";search.dispatchEvent(new Event("input"))');
    await wait('document.querySelectorAll(".case-link").length===1 && document.querySelector(".case-link").textContent.includes("超付")','case search');
    const permanent = await evaluate('document.querySelector(".case-link").href');
    await call('Page.navigate',{url:permanent});
    await wait('document.querySelector("#case-title")?.textContent.includes("超付") && !!document.querySelector(".formula")','direct paper URL');
    await evaluate('const amount=document.querySelector(".formula .ref");for(let p=amount;p;p=p.parentElement) if(p.tagName==="DETAILS") p.open=true; amount.click()');
    await wait('document.querySelector("#page-dialog").open && !!document.querySelector(".located")','mobile operand source');
    await evaluate('document.querySelector("#page-dialog").close();const accountFinding=[...document.querySelectorAll(".finding")].find(f=>f.querySelector(".mono")?.textContent==="B03");[...accountFinding.querySelectorAll("button")].find(b=>b.textContent==="查看证据路径").click()');
    await wait('document.querySelector("#trace-select")?.value.startsWith("B03-") && document.querySelector(".trace-result").textContent.includes("0092")','selected finding path');
    await evaluate('for(const d of document.querySelectorAll(".trace-sources > details")) d.open=true');
    await wait('[...document.querySelectorAll(".trace-quote button")].some(b=>b.textContent.includes("实际收款账号"))','account operand path');
    await evaluate('[...document.querySelectorAll(".trace-quote button")].find(b=>b.textContent.includes("实际收款账号")).click()');
    await wait('document.querySelector("#page-dialog").open && document.querySelector(".located").textContent.includes("000000000000000092")','matching printed account');
    await evaluate('document.querySelector("#page-dialog").close();document.querySelector("#nav-library").click()');
    await wait('!document.querySelector("#library").hidden','evidence search');
    await evaluate('document.querySelector("#library-query").value="YL-BANK-092";document.querySelector("#library-form").requestSubmit()');
    await wait('!!document.querySelector("#library-results .source-jump")','evidence hit');
    const cited = await evaluate('document.querySelector("#library-results .source-jump").href');
    await call('Page.navigate',{url:cited});
    await wait('document.querySelector("#page-dialog")?.open && !!document.querySelector(".located")','permanent revision and fact URL');
    console.log('PASS · Six viewports, inbox search, finding-to-account provenance and permanent revision/source links');
  } else {
    await wait('document.querySelector("#account input[name=password]") !== null', 'login');
    await click('创建企业账号');
    const password = 'synthetic-ui-only-123';
    await entry({workspace:'合成演练 · 青岚商贸', name:'林审计', login:'ui.owner',password});
    await wait('!!document.querySelector("#nav-team")?.getClientRects().length && location.hash.endsWith("/desk")','admin workspace');
    const first = await evaluate('location.hash');
    await click('企业成员');
    await wait('!!document.querySelector("#team form select")','team');
    await click('生成邀请链接');
    const invite = await wait('document.querySelector("#team input[readonly]")?.value','invitation');
    await evaluate('document.querySelector("#nav-account").click()');
    await wait('document.querySelector("#account-panel details") !== null','account switcher');
    await evaluate('document.querySelector("#account-panel details").open=true; const org=document.querySelector("#account-panel input[name=name]"); org.value="合成演练 · 乙企业"; org.form.requestSubmit()');
    await wait('location.hash.endsWith("/desk") && location.hash!=='+JSON.stringify(first),'second enterprise');
    await evaluate('document.querySelector("#nav-account").click()');
    await wait('document.querySelectorAll("#account-panel .line a").length===2','two companies');
    await click('退出登录');
    await wait('!!document.querySelector("#account-panel input[name=password]")','logout');
    await call('Page.navigate',{url:invite});
    await wait('document.querySelector("#account-title")?.textContent==="加入企业"','invited account');
    if (!await evaluate('!!document.querySelector("#account input[name=name]")')) await click('创建账号并接受邀请');
    await entry({name:'余经办',login:'ui.employee',password});
    await wait('location.hash==='+JSON.stringify(first)+' && !document.querySelector("#desk").hidden && document.querySelector("#nav-team").hidden','employee workspace');
    await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
    await evaluate('document.querySelector("#new-case").click()');
    await wait('document.querySelector("#upload-dialog").open && document.querySelector("#upload-files").multiple','mobile intake');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'), 'mobile overflow');
    console.log('PASS · Admin registration, enterprise switching, one-use invitation, employee login and mobile intake');
    if (process.argv.includes('--live')) {
      const file = resolve('docs/samples/generated/07-采购三单合订/采购业务合订件.pdf');
      const {root:dom} = await call('DOM.getDocument');
      const {nodeId} = await call('DOM.querySelector',{nodeId:dom.nodeId,selector:'#upload-files'});
      await call('DOM.setFileInputFiles',{nodeId,files:[file]});
      await evaluate('document.querySelector("#upload-title").value="合成演练 · 三单合订"; document.querySelector("#upload-form").requestSubmit()');
      await wait('location.hash.includes("/case/") && !!document.querySelector("#progress-panel progress")','submitted');
      await wait('document.querySelector("#checkpoint-totals")?.textContent.includes("已分页 3 页") && !!document.querySelector(".checkpoint-active")','saved pagination and active model page',120000);
      await evaluate('window.trainingProgressRow=document.querySelector(".checkpoint-document");window.trainingProgressRow.open=true');
      const range = await evaluate('fetch(document.querySelector(".checkpoint-pages a").href,{headers:{Range:"bytes=0-7"}}).then(async r=>[r.status,(await r.arrayBuffer()).byteLength,!!r.headers.get("ETag")])');
      assert.deepEqual(range,[206,8,true]);
      await wait('[...document.querySelectorAll(".checkpoint-pages span")].some(s=>s.textContent.includes("已记录视觉复检"))','stored visual check',240000);
      await wait('document.querySelector("#case-status")?.textContent==="待验收"','multimodal audit', 540000);
      assert.ok(await evaluate('window.trainingProgressRow===document.querySelector(".checkpoint-document") && window.trainingProgressRow.open'));
      assert.ok(await evaluate('document.querySelector("#checkpoint-totals").textContent.includes("已提取 3 页") && !document.querySelector(".checkpoint-active")'));
      for (const width of [1440,1024,820,768,320,390]) {
        await call('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:width<600});
        assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'expanded employee progress at '+width);
      }
      console.log('PASS · Saved per-page extraction and visual checks, verified live preview and preserved expanded document');
      assert.ok(await evaluate('document.querySelector("#report-tools").hidden'),'employee scope');
      const detail = await evaluate('location.hash');
      await evaluate('document.querySelector("#nav-account").click()');
      await wait('!!document.querySelector("#account-panel details")','account');
      await click('退出登录');
      await wait('!!document.querySelector("#account-panel input[name=password]")','sign in');
      if (await evaluate('!!document.querySelector("#account input[name=name]")')) await click('已有账号，去登录');
      await entry({login:'ui.owner',password});
      await wait('location.hash.endsWith("/desk")','reviewer login');
      await evaluate('location.hash='+JSON.stringify(detail));
      await wait('!document.querySelector("#report-tools").hidden && !!document.querySelector("#case-panel .panel")','reviewer report');
      const path = await evaluate('location.hash.slice(1).split("/")');
      const report = await evaluate('fetch("/api/w/'+path[1]+'/cases/'+path[3]+'/reports/1").then(r=>r.json())');
      console.log(JSON.stringify({verdict:report.report.result.verdict,pages:report.report.graph.nodes.filter(n=>n.type==='page').length,
        findings:report.report.findings.length, calculations:report.report.findings.flatMap(f=>f.calculations||[]).length}));
      const needsReview = report.report.result.verdict === 'review';
      if (needsReview) {
        console.log(JSON.stringify({gaps:report.report.graph.gaps, pending:report.report.graph.facts.filter(f=>!['anchored','confirmed'].includes(f.status)).map(f=>[f.page,f.field,f.status]), rules:report.report.findings.filter(f=>f.status!=='ok').map(f=>[f.rule,f.detail])}));
        assert.ok(report.report.graph.gaps.some(g=>g.doc==='d01' && g.page===1 && g.field==='payment_term' &&
          g.quote?.endsWith('验收后一次性全额结算')),'review links to the printed contract clause');
        assert.ok(report.report.findings.some(f=>f.rule==='M02' && f.status==='missing'),'unverified payment terms block the full-settlement calculation');
        assert.ok(report.report.findings.filter(f=>f.status!=='ok').every(f=>['E01','C01','M02','X01'].includes(f.rule)),'only the evidenced contract clause needs review');
      } else assert.equal(report.report.result.verdict,'pass','golden procurement result');
      const calcCount = report.report.findings.flatMap(f=>f.calculations || []).length;
      assert.ok(calcCount >= (needsReview ? 1 : 3), 'operand-linked audit');
      await evaluate('const detailEl = document.querySelector("#case-panel .formula .ref"); for (let a=detailEl.parentElement; a; a=a.parentElement) if(a.tagName==="DETAILS") a.open=true; detailEl.click()');
      await wait('document.querySelector("#page-dialog").open && !!document.querySelector(".evidence-row.located")','operand citation');
      const sourceUrl = await wait('document.querySelector("#page-dialog img")?.naturalWidth && document.querySelector("#page-dialog .image-sheet + a").href','verified source image loaded');
      assert.equal(new URL(sourceUrl).searchParams.get('rev'),'1');
      const page = /\/documents\/(d[0-9]+)\/pages\/([0-9]+)$/.exec(new URL(sourceUrl).pathname);
      assert.ok(page);
      const temporaryPage = join(scratch,'data','cases',path[3],page[1],page[2]+'.jpg');
      const savedPage = await readFile(temporaryPage);
      await evaluate('document.querySelector("#page-dialog").close()');
      try {
        await writeFile(temporaryPage,Buffer.from('changed local test fixture'));
        await evaluate('detailEl.click()');
        await wait('document.querySelector("#page-dialog [role=alert]")?.textContent.includes("原页加载失败")','changed test image refused');
        assert.ok(await evaluate('!document.querySelector("#page-dialog input:enabled")'));
      } finally {
        await writeFile(temporaryPage,savedPage);
        await evaluate('if(document.querySelector("#page-dialog").open) document.querySelector("#page-dialog").close()');
      }
      await evaluate('detailEl.click()');
      await wait('!!document.querySelector("#page-dialog input:enabled")','verified bytes restored for review');
      await evaluate('document.querySelector("#page-dialog").close()');
      let revision = 1;
      let referForReview = needsReview;
      if (process.argv.includes('--dispute') && !needsReview) {
        const term = report.report.graph.facts.find(f=>f.field==='payment_term' && f.doc==='d01' && f.page===1);
        assert.ok(term);
        await evaluate('location.hash='+JSON.stringify(detail+'?rev=1&fact='+encodeURIComponent(term.id)));
        await wait('document.querySelector("#page-dialog")?.open && !!document.querySelector(".located input:enabled")','printed payment term');
        await evaluate('document.querySelector(".located input").click()');
        await click('记录所选引文的核图意见','document.querySelector("#page-dialog")');
        await evaluate('document.querySelector("#review-decision").value="dispute";document.querySelector("#review-note").value="合成演练，审计员对该合同结算条款的取值提出异议。";document.querySelector("#review-form").requestSubmit()');
        revision = 2;
        await wait('document.querySelector("#version").value==="2" && document.querySelector("#case-status").textContent==="待验收"','recalculated workpaper after dispute',240000);
        const revised = await evaluate('fetch("/api/w/'+path[1]+'/cases/'+path[3]+'/reports/2").then(r=>r.json()).then(b=>b.report)');
        assert.equal(revised.graph.facts.find(f=>f.id===term.id)?.status,'disputed');
        assert.equal(revised.findings.find(f=>f.rule==='M02')?.status,'missing');
        assert.equal(revised.result.verdict,'review');
        referForReview = true;
      }
      await click('填写验收意见');
      let decision = referForReview ? 'escalate' : 'approve';
      const note = referForReview ? '合成演练：合同结算条款尚待核实，提交复核。' : '已核合成演练三份原页及金额复算。';
      await evaluate('document.querySelector("#review-decision").value='+JSON.stringify(decision)+';document.querySelector("#review-note").value='+JSON.stringify(note)+';document.querySelector("#review-form").requestSubmit()');
      await wait('document.querySelector("#case-status").textContent==='+JSON.stringify(referForReview?'待复核':'已归档'),'auditor signoff');
      assert.equal(await evaluate('fetch("/api/w/'+path[1]+'/cases/'+path[3]+'").then(r=>r.json()).then(c=>c.decisions.at(-1).decision)'),decision);
      const usageUrl = '/api/workspaces/'+path[1]+'/team';
      const usageAtSignoff = await evaluate('fetch('+JSON.stringify(usageUrl)+').then(r=>r.json()).then(d=>d.usage)');
      if (referForReview) {
        assert.ok(await evaluate('document.querySelector(".peer-panel").textContent.includes("等待同企业另一位")'));
        await evaluate('document.querySelector("#nav-team").click()');
        await wait('!!document.querySelector("#team select[name=role]")','auditor invitation form');
        await evaluate('document.querySelector("#team select[name=role]").value="auditor"');
        await click('生成邀请链接');
        const auditorInvite = await wait('document.querySelector("#team input[readonly]")?.value','peer invitation');
        await evaluate('document.querySelector("#nav-account").click()');
        await wait('!!document.querySelector("#account-panel details")','owner account options');
        await click('退出登录');
        await wait('!!document.querySelector("#account input[name=password]")','owner logged out');
        await call('Page.navigate',{url:auditorInvite});
        await wait('document.querySelector("#account-title")?.textContent==="加入企业"','auditor invited');
        if (!await evaluate('!!document.querySelector("#account input[name=name]")')) await click('创建账号并接受邀请');
        await entry({name:'陆复核',login:'ui.second.auditor',password});
        await wait('document.querySelector("[data-metric=in_review] strong")?.textContent==="1" && !document.querySelector("#desk").hidden','peer inbox');
        await evaluate('document.querySelector("[data-metric=in_review]").click()');
        await wait('document.querySelector("[data-filter=in_review]").getAttribute("aria-pressed")==="true" && document.querySelectorAll(".case-link").length===1','filtered review queue');
        await evaluate('document.querySelector(".case-link").click()');
        await wait('!!document.querySelector(".peer-panel button")','independent reviewer can sign');
        await click('填写复核意见');
        await wait('document.querySelector("#peer-dialog").open','peer decision form');
        assert.deepEqual(await evaluate('[document.querySelector("#peer-reviewer").value,document.querySelector("#peer-reviewer").readOnly]'),['陆复核',true]);
        await evaluate('document.querySelector("#peer-note").value="合成演练，结算条款存在异议，请补交载明付款条件的资料。";document.querySelector("#peer-decision").value="return";document.querySelector("#peer-form").requestSubmit()');
        await wait('document.querySelector("#peer-error").textContent.includes("勾选")','actual findings required');
        const selected = await evaluate('(()=>{const row=[...document.querySelectorAll(".peer-finding")].find(r=>r.textContent.includes("M02"));row.querySelector("input").click();return [row.querySelector("input").value,row.querySelector("a").href]})()');
        assert.equal(new URL(selected[1]).searchParams.get('rev'),String(revision));
        assert.equal(new URL(selected[1]).searchParams.get('finding'),selected[0]);
        for (const width of [1440,1024,820,768,390,320]) {
          await call('Emulation.setDeviceMetricsOverride',{width,height:850,deviceScaleFactor:1,mobile:width<600});
          assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && document.querySelector("#peer-dialog").scrollWidth<=document.querySelector("#peer-dialog").clientWidth+1'),'peer form at '+width);
        }
        await evaluate('document.querySelector("#peer-form").requestSubmit()');
        decision = 'return'; revision++;
        await wait('!document.querySelector("#peer-dialog").open && document.querySelector("#case-status").textContent==="已归档" && document.querySelector("#version").value==='+JSON.stringify(String(revision)),'independent peer signed');
        const history = await evaluate('fetch("/api/w/'+path[1]+'/cases/'+path[3]+'").then(r=>r.json()).then(c=>c.decisions)');
        assert.deepEqual(history.map(s=>s.decision),['escalate','return']);
        assert.notEqual(history[0].actor,history[1].actor);
        await evaluate('document.querySelector(".peer-panel a[href*=finding]").click()');
        await wait('document.querySelector("#trace-select")?.value==='+JSON.stringify(selected[0]),'peer citation opened the disputed finding on its original revision');
        assert.ok(await evaluate('location.hash.includes("rev='+(revision-1)+'")'));
      }
      const bundleUrl = '/api/w/'+path[1]+'/cases/'+path[3]+'/reports/'+revision+'/bundle';
      const b64 = await evaluate('fetch('+JSON.stringify(bundleUrl)+').then(r=>r.blob()).then(b=>new Promise(res=>{const f=new FileReader(); f.onload=()=>res(f.result.split(",")[1]);f.readAsDataURL(b)}))');
      const zip = join(scratch,'signed.zip');
      await writeFile(zip,Buffer.from(b64,'base64'));
      console.log(execFileSync(process.env.AUDIT_PYTHON || 'server/.venv/bin/python',['server/verify.py','--rules',zip],{encoding:'utf8'}).trim());
      await evaluate('document.querySelector("#nav-library").click()');
      await wait('!document.querySelector("#library").hidden','evidence library');
      await evaluate('document.querySelector("#library-query").value="YL-FP-071";document.querySelector("#library-form").requestSubmit()');
      const indexed = await wait('document.querySelector("#library-results .source-jump")?.href','indexed invoice number');
      assert.equal(new URL(indexed).searchParams.get('rev'),String(revision));
      await evaluate('document.querySelector("#library-results .source-jump").click()');
      await wait('document.querySelector("#page-dialog").open && !!document.querySelector(".evidence-row.located") && location.hash.includes("rev='+revision+'")','source opened on its indexed revision');
      await evaluate('document.querySelector("#page-dialog").close()');
      if (referForReview) {
        await evaluate('document.querySelector("#nav-account").click()');
        await wait('!!document.querySelector("#account-panel details")','peer account');
        await click('退出登录');
        await wait('!!document.querySelector("#account-panel input[name=password]")','peer logged out');
        if (await evaluate('!!document.querySelector("#account input[name=name]")')) await click('已有账号，去登录');
        await entry({login:'ui.owner',password});
        await wait('location.hash.endsWith("/desk") && !document.querySelector("#nav-team").hidden','owner returns');
      }
      await evaluate('document.querySelector("#nav-team").click()');
      await wait('document.querySelector(".usage-list")','workspace usage');
      const usage = await evaluate('fetch("/api/workspaces/'+path[1]+'/team").then(r=>r.json()).then(d=>d.usage)');
      assert.ok(usage.requests >= 4 && usage.input_tokens > 0 && usage.output_tokens > 0,'provider usage recorded');
      for (const key of ['requests','input_tokens','output_tokens']) assert.equal(usage[key],usageAtSignoff[key],'human review adds no model calls or tokens');
      console.log(JSON.stringify({requests:usage.requests,input_tokens:usage.input_tokens,output_tokens:usage.output_tokens}));
      console.log('Signed '+decision+' on R'+revision);
      console.log('PASS · Employee upload, live audit, operand citation, signoff, offline replay and cross-case source retrieval');
    }
  }
  assert.deepEqual(faults,[]);
} finally {
  ws?.close();
  for (const child of children.reverse()) {
    if (child.exitCode === null && child.signalCode === null) {
      child.kill(); await Promise.race([once(child,'exit').catch(()=>{}),delay(2000)]);
    }
  }
  await rm(scratch,{recursive:true,force:true,maxRetries:4});
}
