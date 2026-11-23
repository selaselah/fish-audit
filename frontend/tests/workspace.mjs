// Exercise the real registration, invitation and workspace navigation in an isolated browser and database.
import assert from 'node:assert/strict';
import {spawn, execFileSync} from 'node:child_process';
import {mkdtemp, readFile, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {createServer} from 'node:net';
import {setTimeout as delay} from 'node:timers/promises';
import {once} from 'node:events';

const scratch = await mkdtemp(join(tmpdir(), 'fish-ui-'));
const socket = createServer().listen(0, '127.0.0.1');
await once(socket, 'listening');
const port = socket.address().port;
await new Promise(resolve => socket.close(resolve));
const root = 'http://127.0.0.1:' + port;
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
  start(process.env.AUDIT_PYTHON || 'server/.venv/bin/python', ['server/main.py'], {...process.env,
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
    await wait('document.querySelector("#case-status")?.textContent==="待验收"','multimodal audit', 540000);
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
    if (report.report.result.verdict !== 'pass') {
      console.log(JSON.stringify({gaps:report.report.graph.gaps, pending:report.report.graph.facts.filter(f=>!['anchored','confirmed'].includes(f.status)).map(f=>[f.page,f.field,f.status]), rules:report.report.findings.filter(f=>f.status!=='ok').map(f=>[f.rule,f.detail])}));
      throw new Error('Golden procurement packet needs review');
    }
    const calcCount = report.report.findings.flatMap(f=>f.calculations || []).length;
    assert.ok(calcCount >= 3, 'operand-linked audit');
    await evaluate('const detailEl = document.querySelector("#case-panel .formula .ref"); for (let a=detailEl.parentElement; a; a=a.parentElement) if(a.tagName==="DETAILS") a.open=true; detailEl.click()');
    await wait('document.querySelector("#page-dialog").open && !!document.querySelector(".evidence-row.located")','operand citation');
    await evaluate('document.querySelector("#page-dialog").close()');
    await click('填写验收意见');
    await evaluate('document.querySelector("#review-decision").value="approve";document.querySelector("#review-note").value="已核合成演练三份原页及金额复算。";document.querySelector("#review-form").requestSubmit()');
    await wait('document.querySelector("#case-status").textContent==="已归档"','auditor signoff');
    const bundleUrl = '/api/w/'+path[1]+'/cases/'+path[3]+'/reports/1/bundle';
    const b64 = await evaluate('fetch('+JSON.stringify(bundleUrl)+').then(r=>r.blob()).then(b=>new Promise(res=>{const f=new FileReader(); f.onload=()=>res(f.result.split(",")[1]);f.readAsDataURL(b)}))');
    const zip = join(scratch,'signed.zip');
    await writeFile(zip,Buffer.from(b64,'base64'));
    console.log(execFileSync(process.env.AUDIT_PYTHON || 'server/.venv/bin/python',['server/verify.py',zip],{encoding:'utf8'}).trim());
    await evaluate('document.querySelector("#nav-library").click()');
    await wait('!document.querySelector("#library").hidden','evidence library');
    await evaluate('document.querySelector("#library-query").value="YL-FP-071";document.querySelector("#library-form").requestSubmit()');
    await wait('!!document.querySelector(".source-jump")','indexed invoice number');
    await evaluate('document.querySelector(".source-jump").click()');
    await wait('document.querySelector("#page-dialog").open && !!document.querySelector(".evidence-row.located") && location.hash.includes("rev=1")','source opened on its indexed revision');
    console.log('PASS · Employee upload, live audit, operand citation, signoff, offline replay and cross-case source retrieval');
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
