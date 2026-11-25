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
import {checkProduct, checkReviewDesign} from './product.mjs';
import {checkEvidenceCompare,checkMandateCompare,checkPhaseEvidence,checkPaymentChange} from './evidence-compare.mjs';
import {checkPaymentOpinions} from './payment-opinions.mjs';
import {checkRelease} from './payment-release.mjs';
import {checkMandateCalendar} from './mandate-calendar.mjs';
import {checkWarrantyTimeline} from './warranty-timeline.mjs';
import {checkWarrantyTickets} from './warranty-tickets.mjs';
import {checkWarrantyPhotos} from './warranty-photos.mjs';
import {checkNavigation,checkPrior} from './prior-installment.mjs';
import {checkInspectionCoverage} from './inspection-coverage.mjs';
import {checkSigningParties} from './signing-parties.mjs';
import {checkReinspectionTrail} from './reinspection-trail.mjs';
import {checkReinspectionTiming} from './reinspection-timing.mjs';
import {checkEntityBrowser} from './entity-browser.mjs';

const scratch = await mkdtemp(join(tmpdir(), 'fish-ui-'));
const socket = createServer().listen(0, '127.0.0.1');
await once(socket, 'listening');
const port = socket.address().port;
await new Promise(resolve => socket.close(resolve));
const sampleDesk = process.argv.includes('--sample-desk');
const product = process.argv.includes('--product');
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
const fieldCase = caseArgument('--field-case');
const installmentCase = caseArgument('--installment-case');
const replayCase = caseArgument('--replay-case');
const recoveringCase = caseArgument('--recovering-case');
const invoiceConflict = caseArgument('--invoice-conflict-case');
const invoiceSource = caseArgument('--invoice-source-case');
const invoiceApproval = caseArgument('--invoice-approval-case');
const claimPairCase = caseArgument('--claim-pair-case');
const invoiceCodeHistory = caseArgument('--invoice-code-case');
const maskedInvoice = caseArgument('--masked-invoice-case');
const legacyMask = caseArgument('--legacy-mask-case');
const legacyTransfer = caseArgument('--legacy-transfer-case');
const partialTransfer = caseArgument('--partial-transfer-case');
const visibilityCase = caseArgument('--visibility-case');
const accountReview = caseArgument('--account-review-case');
const performanceCase = caseArgument('--performance-case');
const designCase = caseArgument('--design-case');
const compareCase = caseArgument('--compare-case');
const mandateCase = caseArgument('--mandate-case');
const mandateCalendarCase = caseArgument('--mandate-calendar-case');
const warrantyCase = caseArgument('--warranty-case');
const ticketCase = caseArgument('--ticket-case');
const photoCase = caseArgument('--warranty-photo-case');
const inspectionCase = caseArgument('--inspection-case');
const signingCase = caseArgument('--signing-party-case');
const priorCase=caseArgument('--prior-installment-case');
const trailCase=caseArgument('--reinspection-trail-case');
const timingCase=caseArgument('--reinspection-time-case');
const entityCase=caseArgument('--entity-case');
const navCase=caseArgument('--navigation-case');
const phaseEvidenceCase = caseArgument('--phase-evidence-case');
const paymentChangeCase = caseArgument('--payment-change-case');
const paymentOpinionCase = caseArgument('--payment-opinion-case');
const releaseCase = caseArgument('--release-case');
const qualityImageCase = caseArgument('--quality-image-case');
const reinspectionGap = caseArgument('--reinspection-gap-case');
const brokenPayment = caseArgument('--payment-source-case');
const waitingCase = caseArgument('--waiting-case');
const seeded = [priorCase,trailCase,timingCase,entityCase,navCase,product,designCase,compareCase,mandateCase,mandateCalendarCase,warrantyCase,ticketCase,photoCase,signingCase,inspectionCase,phaseEvidenceCase,paymentChangeCase,paymentOpinionCase,releaseCase,sampleDesk,paymentCase,supplementCase,peerCase,fieldCase,installmentCase,replayCase,recoveringCase,
                invoiceConflict,invoiceSource,invoiceApproval,claimPairCase,invoiceCodeHistory,maskedInvoice,legacyMask,legacyTransfer,partialTransfer,visibilityCase,accountReview,performanceCase,qualityImageCase,reinspectionGap,brokenPayment,waitingCase].some(Boolean);
const legacyCase = legacyMask || legacyTransfer;
const root = product ? process.env.AUDIT_PRODUCT_ORIGIN || 'http://127.0.0.1:8000' : brokenPayment ? process.env.SYNTHETIC_PAYMENT_ORIGIN : legacyCase ? process.env.SYNTHETIC_LEGACY_ORIGIN : waitingCase ? process.env.SYNTHETIC_WRITER_ORIGIN :
  recoveringCase ? process.env.SYNTHETIC_RECOVERY_ORIGIN : 'http://127.0.0.1:' + (seeded ? 8000 : port);
if (product || recoveringCase || waitingCase || legacyCase || brokenPayment) assert.match(root || '',/^http:\/\/127\.0\.0\.1:\d+$/);
if (legacyCase || brokenPayment) assert.ok(!['8000','8010'].includes(new URL(root).port));
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
  await call('Page.navigate',{url:product ? root : root+'/app'});
  if (product) {
    await checkProduct({root,call,evaluate,wait});
  } else if (entityCase) {
    await checkEntityBrowser({root,call,evaluate,wait},entityCase);
  } else if (timingCase) {
    await checkReinspectionTiming({root,call,evaluate,wait},timingCase,Number(process.env.AUDIT_TIMING_REV));
  } else if (trailCase) {
    await checkReinspectionTrail({root,call,evaluate,wait},trailCase,Number(process.env.AUDIT_TRAIL_REV));
  } else if (priorCase) {
    await checkPrior({root,call,evaluate,wait},priorCase,process.env.AUDIT_PRIOR_REV);
  } else if (navCase) {
    await checkNavigation({root,call,evaluate,wait},navCase);
  } else if (designCase) {
    await checkReviewDesign({root,call,evaluate,wait},designCase);
  } else if (phaseEvidenceCase) {
    await checkPhaseEvidence({root,call,evaluate,wait},phaseEvidenceCase);
  } else if (paymentChangeCase) {
    await checkPaymentChange({root,call,evaluate,wait},paymentChangeCase,process.env.AUDIT_CHANGE_REV);
  } else if (paymentOpinionCase) {
    await checkPaymentOpinions({root,call,evaluate,wait},paymentOpinionCase,process.env.AUDIT_OPINION_REV);
  } else if (releaseCase) {
    await checkRelease({root,call,evaluate,wait},releaseCase,process.env.AUDIT_RELEASE_REV);
  } else if (mandateCalendarCase) {
    await checkMandateCalendar({root,call,evaluate,wait},mandateCalendarCase,process.env.AUDIT_MANDATE_REV);
  } else if (warrantyCase) {
    await checkWarrantyTimeline({root,call,evaluate,wait},warrantyCase,process.env.AUDIT_WARRANTY_REV);
  } else if (ticketCase) {
    await checkWarrantyTickets({root,call,evaluate,wait},ticketCase,process.env.AUDIT_TICKET_REV);
  } else if (photoCase) {
    await checkWarrantyPhotos({root,call,evaluate,wait},photoCase,process.env.AUDIT_PHOTO_REV);
  } else if (inspectionCase) {
    await checkInspectionCoverage({root,call,evaluate,wait},inspectionCase,process.env.AUDIT_INSPECTION_REV);
  } else if (signingCase) {
    await checkSigningParties({root,call,evaluate,wait},signingCase,process.env.AUDIT_SIGNING_REV);
  } else if (mandateCase) {
    await checkMandateCompare({root,call,evaluate,wait},mandateCase);
  } else if (compareCase) {
    const arg=process.argv.indexOf('--compare-rev');
    const rev=arg===-1 ? null : Number(process.argv[arg+1]);
    assert.ok(rev===null || Number.isSafeInteger(rev) && rev>0);
    await checkEvidenceCompare({root,call,evaluate,wait},compareCase,rev);
  } else if (reinspectionGap) {
    const api=root+'/api/cases/'+reinspectionGap;
    const task=await (await fetch(api)).json();
    assert.ok(task.title.startsWith('合成演练 · ') && task.profile==='cn-contract-performance/v1');
    const {report}=await (await fetch(api+'/reports/1')).json();
    const gap=report.graph.gaps.find(g=>g.quality==='uncovered_title' && g.title_hint==='reinspection');
    assert.ok(gap);
    await call('Page.navigate',{url:root+'/workpaper/'+reinspectionGap+'?rev=1'});
    await wait('document.querySelector(".reinspection-trail")?.textContent.includes('+JSON.stringify(gap.quote)+')','unassigned reinspection page');
    await evaluate('document.querySelector("#trail-tab-final").click()');
    await click('核对原页第 '+gap.line+' 行','document.querySelector(".reinspection-trail")');
    await wait('document.querySelector("#page-dialog").open && document.querySelector(".located[data-gap-line] blockquote")?.textContent==='+JSON.stringify(gap.quote),'missing heading line');
    assert.equal(await evaluate('document.querySelector(".located[data-gap-line]").dataset.gapLine'),String(gap.line));
    console.log('PASS · Unverified reinspection heading links to the original native line');
  } else if (qualityImageCase) {
    const api = root+'/api/cases/'+qualityImageCase;
    const task = await (await fetch(api)).json();
    assert.ok(task.title.startsWith('合成演练 · 缺陷尾号说明'));
    const {report} = await (await fetch(api+'/reports/'+task.rev)).json();
    const [hold] = report.graph.quality_references.holds;
    const [note] = hold.observations;
    assert.equal(note.quote, '缺陷编号展示说明：本单仅列尾号');
    assert.equal(hold.lines.length, 0);
    await call('Page.navigate',{url:root+'/workpaper/'+qualityImageCase+'?rev='+task.rev});
    await wait('!!document.querySelector(".performance-overview")','overview of incomplete material');
    assert.equal(await evaluate('document.querySelectorAll(".phase-summary li").length'),0);
    const missingPlan=report.findings.find(f=>f.rule==='H03');
    assert.equal(missingPlan.status,'missing');
    const planButton='.performance-statuses [data-jump-finding="'+missingPlan.id+'"]';
    assert.ok(await evaluate('document.querySelector('+JSON.stringify(planButton)+').textContent.includes("证据不足")'));
    for (const width of [1280, 320]) {
      await call('Emulation.setDeviceMetricsOverride', {width, height:900, deviceScaleFactor:1, mobile:false});
      await call('Page.navigate', {url:root+'/workpaper/'+qualityImageCase+'?'+new URLSearchParams({rev:task.rev,fact:hold.fact})});
      const card = 'document.querySelector(".located .quality-number-hold")';
      await wait('document.querySelector("#page-dialog img")?.naturalWidth && '+card+'?.querySelector("button:enabled") && '+card+'.innerText.includes('+JSON.stringify(note.quote)+')',
        'visible number and page image');
      await click('定位同页展示说明', card);
      await wait('document.activeElement?.dataset.fact==='+JSON.stringify(note.fact)+' && document.querySelector(".located").dataset.fact==='+JSON.stringify(note.fact),
        'qualified image observation');
      assert.ok(await evaluate('document.querySelector(".located").textContent.includes('+JSON.stringify(note.quote)+')'));
    }
    console.log('PASS · Same-page image note is traceable from the confirmed defect digits on desktop and mobile');
  } else if (performanceCase) {
    const api = root+'/api/cases/'+performanceCase;
    const task = await (await fetch(api)).json();
    assert.ok(task.title.startsWith('合成演练 · ') && task.profile==='cn-contract-performance/v1');
    const requestedRev=process.argv.indexOf('--performance-rev');
    if (requestedRev>=0) {
      const rev=Number(process.argv[requestedRev+1]);
      assert.ok(Number.isSafeInteger(rev) && rev>0 && rev<=task.rev);
      task.rev=rev;
    }
    const {report} = await (await fetch(api+'/reports/'+task.rev)).json();
    const phaseChecks=report.findings.filter(f=>f.rule==='H04');
    const phases=phaseChecks.filter(f=>f.stage);
    const batches=report.findings.find(f=>f.rule==='H02')?.batch_acceptance;
    const plan=report.findings.find(f=>f.rule==='H03');
    if (plan.status==='ok') {
      assert.ok(phases.length && phases.every(f=>Number(f.stage.share)>0));
      assert.ok(Math.abs(phases.reduce((sum,f)=>sum+Number(f.stage.share),0)-100)<1e-8);
    }
    if (!phases.length) assert.ok(phaseChecks.length && phaseChecks.every(f=>f.status==='missing'));
    await wait('!!document.querySelector("#new-case")','new audit');
    await evaluate('document.querySelector("#new-case").click()');
    await evaluate('const p=document.querySelector("#upload-profile");p.value="cn-contract-performance/v1";p.dispatchEvent(new Event("change"));');
    assert.ok(await evaluate('document.querySelector("#profile-note").textContent.includes("质保期满确认单")'));
    await call('Page.navigate',{url:root+'/workpaper/'+performanceCase+'?rev='+task.rev});
    await wait('!!document.querySelector(".performance-panel .performance-overview")','contract performance report');
    const summary='document.querySelector(".performance-overview")';
    const jump = async (container,item) => {
      const selector='[data-jump-finding="'+item.id+'"]';
      const button=container+'.querySelector('+JSON.stringify(selector)+')';
      assert.ok(await evaluate(button+'.querySelector(".tag").classList.contains('+JSON.stringify(item.status)+')'));
      await evaluate(button+'.click()');
      assert.equal(await evaluate('document.activeElement.dataset.finding'),item.id);
    };
    for (const f of report.findings.filter(f=>['H01','H02','H03'].includes(f.rule))) await jump(summary,f);
    const planHeading=plan.status!=='ok'?'付款期次待核':phases.length===1?'单期全额付款':'分 '+phases.length+' 期付款';
    assert.equal(await evaluate(summary+'.querySelector('+JSON.stringify('[data-jump-finding="'+plan.id+'"] span')+').textContent'),planHeading);
    assert.equal(await evaluate(summary+'.querySelectorAll(".phase-summary li").length'),phases.length);
    for (const phase of phases) {
      const row=summary+'.querySelector('+JSON.stringify('[data-phase-finding="'+phase.id+'"]')+')';
      await evaluate(summary+'.querySelector('+JSON.stringify('[data-phase-choice="'+phase.id+'"]')+').click()');
      assert.ok(await evaluate('!'+row+'.hidden'));
      assert.equal(await evaluate(row+'.querySelector(".phase-source").textContent'),
        phase.stage.name+(phase.stage.share?' · '+phase.stage.share+'%':''));
      assert.equal(await evaluate(row+'.querySelector("q").textContent'),phase.stage.clause);
      await evaluate(row+'.querySelector(".phase-source").click()');
      await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(phase.stage.clause_ref),'phase contract original from overview');
      await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      await jump(row,phase);
      const matched=report.findings.filter(f=>f.rule==='H05' && f.stage && ['name','clause','share','clause_ref'].every(k=>f.stage[k]===phase.stage[k]));
      assert.equal(await evaluate(row+'.querySelectorAll(".phase-unlinked").length'),matched.length ? 0 : 1);
      for (const payment of matched) await jump(row,payment);
    }
    await evaluate('for(const d of document.querySelectorAll(".finding-disclosure:not([open])")) d.querySelector("summary").click()');
    for (const payment of report.findings.filter(f=>f.rule==='H05' && !f.stage)) {
      await jump(summary,payment);
      const panel='document.querySelector('+JSON.stringify('[data-finding="'+payment.id+'"] .performance-comparison')+')';
      const originals=report.graph.facts.filter(f=>payment.evidence.includes(f.id) && ['paid_on','transfer_amount','payment_designation'].includes(f.field));
      for (const fact of originals) {
        const row=panel+'.querySelector('+JSON.stringify('[data-source-fact="'+fact.id+'"]')+')';
        await wait(panel+'?.open && '+row+'?.querySelector("blockquote").textContent==='+JSON.stringify(fact.quote),'unassigned receipt source');
        await evaluate(row+'.querySelector("button").click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(fact.id),'original unassigned payment');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
    }
    if (phases.length>=2) {
      const sharedClause = await evaluate(`(() => {
        const {findings,graph}=state.bundle.report;
        const [first,second]=findings.filter(f=>f.rule==='H04' && f.stage);
        const sameLine={...second,stage:{...second.stage,clause_ref:first.stage.clause_ref}};
        const receipt={...sameLine,id:'H05-99',rule:'H05'};
        const preview=performanceOverview([first,sameLine,receipt],graph);
        return [...preview.querySelectorAll('li')].map(row=>row.querySelectorAll('[data-jump-finding="H05-99"]').length);
      })()`);
      assert.deepEqual(sharedClause,[0,1],'a receipt belongs only to its named phase when two phases share one contract line');
    }
    const chain=report.findings.find(f=>f.rule==='H02')?.reinspection;
    for (const finding of report.findings.filter(f=>f.date_checks)) {
      const panel='document.querySelector('+JSON.stringify('[data-finding="'+finding.id+'"] .contract-date-evidence')+')';
      const dates=new Set(finding.date_checks.flatMap(c=>c.evidence));
      const relevant=report.graph.facts.filter(f=>dates.has(f.id) && ['signed_on','effect_on','valid_until','approved_on','accepted_on','paid_on','warranty_release','buyer_sealed_on','seller_sealed_on'].includes(f.field));
      assert.equal(await evaluate(panel+'.querySelectorAll("[data-date-fact]").length'),relevant.length);
      for (const check of finding.date_checks.filter(c=>!finding.detail.includes(c.detail)))
        assert.ok(await evaluate(panel+'.textContent.includes('+JSON.stringify(check.detail)+')'));
      for (const fact of relevant) {
        const row=panel+'.querySelector('+JSON.stringify('[data-date-fact="'+fact.id+'"]')+')';
        assert.equal(await evaluate(row+'.querySelector("q").textContent'),fact.source_line?.text || fact.quote);
        await evaluate(row+'.querySelector("button").click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(fact.id)+' && document.querySelector("#page-dialog img")?.naturalWidth>0','chronology source');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
    }
    const change=report.findings.find(f=>f.rule==='H02')?.quality_change;
    const authority=report.findings.find(f=>f.rule==='H02')?.acceptance_authority;
    const effect=report.findings.find(f=>f.rule==='H01')?.effect_review;
    const warranty=phases.find(f=>f.warranty_check);
    const inspection=report.findings.find(f=>f.rule==='H02');
    const reservations=inspection?.acceptance_reservations;
    const hasRemarks=Boolean(reservations && (reservations.lines.length || reservations.mixed_pages.length));
    const verifyRemarks=async (panel,lines)=>{
      for (const line of lines) {
        const fact=line.facts.map(id=>report.graph.facts.find(f=>f.id===id)).find(f=>f?.quote===line.quote);
        const ref=fact?.id || line.doc+'/p'+line.page+'/l'+line.line;
        const row=panel+'.querySelector('+JSON.stringify('[data-reservation-source="'+ref+'"]')+')';
        await wait(row+'?.querySelector("q").textContent==='+JSON.stringify(line.quote),'acceptance remark transcription');
        await evaluate(row+'.querySelector("button").click()');
        const position=fact?'document.querySelector(".located")?.dataset.fact==='+JSON.stringify(fact.id):
          'document.querySelector(".located[data-gap-line] blockquote")?.textContent==='+JSON.stringify(line.quote);
        await wait('document.querySelector("#page-dialog").open && '+position+' && document.querySelector("#page-dialog img")?.naturalWidth>0','inspection remark on original');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
    };
    if (batches && report.graph.delivery_batch_sources?.remarks?.length) {
      for (const phase of phases) {
        const stage=phase.stage;
        const records=batches.records.filter(r=>stage.batch_index ? r.index===stage.batch_index : /验收|质保|保修/u.test(stage.clause));
        const sources=[...(batches.payment_holds || []),...records.flatMap(r=>r.inspection_notes || [])]
          .filter(s=>phase.evidence.includes(s.doc+'/p'+s.page));
        await evaluate('document.querySelector('+JSON.stringify('[data-phase-choice="'+phase.id+'"]')+').click()');
        const row='document.querySelector('+JSON.stringify('[data-phase-finding="'+phase.id+'"]')+')';
        const group=row+'.querySelector(".phase-remarks")';
        assert.equal(await evaluate('Boolean('+group+')'),Boolean(sources.length));
        if (!sources.length) continue;
        await evaluate(group+'.querySelector("summary").click()');
        assert.equal(await evaluate(group+'.querySelectorAll("q").length'),sources.length);
        if (process.env.AUDIT_UI_SHOTS && stage.batch_index && sources.some(s=>s.kind==='limited_inspection') && sources.some(s=>s.kind==='payment_hold')) {
          await call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
          const clip=await evaluate('(()=>{const rect=document.querySelector(".performance-overview").getBoundingClientRect();return {x:rect.x+scrollX,y:rect.y+scrollY,width:rect.width,height:rect.height,scale:1}})()');
          const shot=await call('Page.captureScreenshot',{format:'png',clip,captureBeyondViewport:true});
          await writeFile(join(process.env.AUDIT_UI_SHOTS,'batch-payment-remarks-'+performanceCase+'.png'),Buffer.from(shot.data,'base64'));
          await call('Emulation.clearDeviceMetricsOverride');
        }
        await verifyRemarks(group,sources);
        await evaluate(group+'.querySelector("summary").click()');
        const paper='document.querySelector('+JSON.stringify('[data-finding="'+phase.id+'"] .phase-remarks')+')';
        assert.equal(await evaluate(paper+'.querySelectorAll("q").length'),sources.length);
      }
    }
    const packets=report.graph.receipt_packet_sources?.packets || [];
    const equipment=inspection?.equipment_models;
    const modelLines=report.graph.equipment_model_sources?.lines || [];
    const keepEvidenceOpen=async panel=>{
      const retained=await evaluate(`(async()=>{
        const evidence=${panel};
        evidence.open=true;
        const summary=evidence.querySelector('summary');
        summary.focus();
        await refresh();
        return evidence.isConnected && evidence.open && document.activeElement===summary;
      })()`);
      assert.ok(retained,'a progress refresh must keep the open evidence and its keyboard focus');
    };
    if (equipment) {
      const panel='document.getElementById("equipment-models")';
      assert.equal(await evaluate(panel+'.dataset.modelStatus'),equipment.status);
      assert.equal(await evaluate(panel+'.open'),equipment.status!=='ok');
      await keepEvidenceOpen(panel);
      await verifyRemarks(panel,modelLines);
      const holds=report.graph.equipment_model_sources.review_holds || [];
      assert.equal(await evaluate(panel+'.querySelectorAll("[data-model-review]").length'),holds.length);
      for (const hold of holds) {
        const fact=report.graph.facts.find(f=>f.id===hold.facts[0]);
        const review=panel+'.querySelector('+JSON.stringify('[data-model-review="'+fact.id+'"]')+')';
        assert.ok(await evaluate(review+'.textContent.includes('+JSON.stringify(fact.attestation.note)+')'));
        await evaluate(review+'.querySelector("button").click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+
          JSON.stringify(fact.id)+' && document.querySelector("#page-dialog img")?.naturalWidth>0','disputed model on its original page');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
      if (equipment.exchange) {
        const view='document.querySelector(".equipment-exchange")';
        const source=report.graph.equipment_model_sources.exchange;
        assert.equal(await evaluate(view+'.dataset.exchangeStatus'),equipment.exchange.status);
        const pending=equipment.exchange.checks.filter(c=>c.status!=='ok');
        assert.equal(await evaluate(view+'.querySelectorAll(".exchange-pending button").length'),pending.length);
        if (pending.length) {
          await evaluate(view+'.querySelector(".exchange-pending button").click()');
          await wait('document.activeElement?.id==='+JSON.stringify('exchange-check-'+pending[0].key),'first outstanding exchange check');
        }
        const inspectedUnits=equipment.records.filter(r=>r.inspection_role).map(r=>r.unit);
        const inventories=source.pages.filter(p=>p.form || inspectedUnits.includes(p.unit)).flatMap(p=>p.rows)
          .filter(r=>['delivered_serials','exchange_old_serials','exchange_new_serials'].includes(r.kind));
        await verifyRemarks(view,inventories);
        for (const check of equipment.exchange.checks) {
          const selector=['returned','received'].includes(check.key)?'data-exchange-list':'data-exchange-check';
          const part=view+'.querySelector('+JSON.stringify('['+selector+'="'+check.key+'"]')+')';
          if (selector==='data-exchange-check') await evaluate(part+'.open=true');
          await wait(part+'?.textContent.includes('+JSON.stringify(check.detail)+')','individual exchange result');
          assert.ok(await evaluate(part+'.querySelector(".tag").classList.contains('+JSON.stringify(check.status)+')'));
          if (check.key==='signatures') await verifyRemarks(part,source.pages.filter(p=>p.form).flatMap(p=>p.rows)
            .filter(row=>['buyer_signature','seller_signature'].includes(row.kind)));
          if (selector==='data-exchange-check') await evaluate(part+'.open=false');
        }
        for (const item of report.findings.filter(f=>f.stage && ['H04','H05'].includes(f.rule))) {
          const box='document.querySelector('+JSON.stringify('[data-finding="'+item.id+'"] .exchange-payment-proof')+')';
          const forms=source.pages.filter(p=>p.form && item.scope.includes(p.unit));
          const cited=forms.some(p=>item.evidence.some(ref=>ref===p.doc+'/p'+p.page || ref.startsWith(p.doc+'/p'+p.page+'/')));
          if (/^合同生效/.test(item.stage.clause) && !pending.some(c=>c.key==='scope')) {
            assert.equal(await evaluate('!!'+box),false,'an independent prepayment does not depend on an equipment exchange');
          } else if (cited) {
            const target=await evaluate(box+'.querySelector("button").getAttribute("aria-controls")');
            if (/^合同生效/.test(item.stage.clause)) assert.equal(target,'exchange-check-scope');
            if (!pending.length) assert.equal(target,'equipment-exchange');
            if (pending.length===1) assert.ok(await evaluate(box+'.textContent.includes('+JSON.stringify(pending[0].detail)+')'));
            await evaluate(panel+'.open=false;'+box+'.querySelector("button").click()');
            await wait(panel+'.open && document.activeElement?.id==='+JSON.stringify(target),'payment phase opens the specific exchange evidence');
          }
        }
      }
      if (equipment.sequence) {
        assert.equal(await evaluate(panel+'.querySelector("[data-model-sequence]").dataset.modelSequence'),equipment.sequence.outcome);
        await evaluate(panel+'.querySelector("[aria-controls=equipment-reinspection-trail]").click()');
        await wait('document.activeElement?.id==="equipment-reinspection-trail"','original defect and reinspection for model comparison');
        const roles=await evaluate('[...'+panel+'.querySelectorAll(".equipment-original h4")].map(e=>e.textContent)');
        if (['original','final'].every(role=>equipment.records.some(r=>r.inspection_role===role)))
          assert.ok(roles.indexOf('初验实收')>0 && roles.indexOf('初验实收')<roles.indexOf('复验实收'));
      }
      for (const record of equipment.records) {
        const section='document.getElementById('+JSON.stringify('equipment-model-'+record.unit)+')';
        assert.equal(await evaluate(section+'.querySelector(".model-code").textContent'),record.received?.value || '型号待核');
        const identity=record.identity.receipt.find(ref=>report.graph.facts.find(f=>f.id===ref)?.field==='contract_id');
        if (identity) {
          await evaluate(section+'.querySelector("details").open=true');
          const source=section+'.querySelector('+JSON.stringify('[data-model-identity="'+identity+'"]')+')';
          await wait(source,'equipment contract reference');
          await evaluate(source+'.querySelector("button").click()');
          await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(identity),'received equipment linked to the original contract number');
          await evaluate('document.querySelector("#page-dialog [data-close]").click()');
          await evaluate(section+'.querySelector("details").open=false');
        }
      }
      for (const stage of phases) {
        const button='document.querySelector('+JSON.stringify('[data-finding="'+stage.id+'"] [aria-controls^="equipment-model"]')+')';
        if (/^合同生效/.test(stage.stage.clause)) assert.equal(await evaluate('!!'+button),false);
        if (/验收|质保/.test(stage.stage.clause) && equipment.records.some(r=>stage.scope.includes(r.unit))) {
          await evaluate(panel+'.open=false');
          const target=await evaluate(button+'.getAttribute("aria-controls")');
          await evaluate(button+'.click()');
          await wait(panel+'.open && document.activeElement?.id==='+JSON.stringify(target),'jump from installment to open model source');
        }
      }
    }
    const settlements=report.findings.filter(f=>f.stage_payments);
    for (const f of settlements) {
      await jump(summary,f);
      const item=f.stage_payments;
      const panel='document.querySelector('+JSON.stringify('[data-finding="'+f.id+'"] .stage-payments')+')';
      assert.equal(await evaluate(panel+'.dataset.stageBalance'),item.state);
      const displayed=await evaluate('[...'+panel+'.querySelectorAll("dd")].map(e=>e.textContent.replaceAll(",",""))');
      assert.deepEqual(displayed,[item.expected,item.seen,item.difference?.replace(/^-/,'')].map(v=>v==null?'待核':v+' 元'));
      if (item.base.total && item.expected!=null) {
        await evaluate(panel+'.querySelector("details").open=true');
        const formula=item.base.total.value+' × '+f.stage.share+'% = '+item.expected+' 元';
        await wait(panel+'.querySelector("details p")?.textContent.replaceAll(",","")==='+JSON.stringify(formula.replaceAll(',','')),'printed gross times stage share');
        await evaluate(panel+'.querySelector("details").open=false');
      }
      assert.equal(await evaluate(panel+'.querySelectorAll(".stage-transfer").length'),item.records.length);
      const phase=phases.find(p=>p.stage.clause_ref===f.stage?.clause_ref && p.stage.name===f.stage?.name);
      if (phase) await jump(panel,phase);
      if (!phase || phase.status==='ok') assert.equal(await evaluate(panel+'.querySelectorAll(".stage-prerequisite").length'),0);
      else {
        for (const upstream of report.findings.filter(h=>['H01','H02'].includes(h.rule) && h.status!=='ok')) {
          const field=upstream.rule==='H01'?'effect_clause':'acceptance';
          const shared=report.graph.facts.some(fact=>fact.field===field && phase.evidence.includes(fact.id) && upstream.evidence.includes(fact.id));
          if (shared) {
            assert.ok(await evaluate(panel+'.textContent.includes('+JSON.stringify(upstream.detail)+')'),'original contract or quality finding on the relevant installment');
            await jump(panel,upstream);
          }
        }
      }
      for (const r of item.records) {
        const row=panel+'.querySelector('+JSON.stringify('[data-transfer-unit="'+r.unit+'"]')+')';
        for (const value of [r.inputs.transfer_amount,r.inputs.transfer_ref].filter(Boolean)) {
          const proof=row+'.querySelector('+JSON.stringify('[data-stage-operand="'+value.ref+'"]')+')';
          await evaluate(proof+'.querySelector("button").click()');
          await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(value.ref)
            +' && document.querySelector("#page-dialog img")?.naturalWidth>0','specific transfer field on original');
          await evaluate('document.querySelector("#page-dialog [data-close]").click()');
        }
        const timing=item.timing.find(t=>t.unit===r.unit);
        const payment=report.findings.find(p=>p.rule==='H05' && p.evidence.includes(timing.receipt_ref));
        if (payment) await jump(row,payment);
      }
      await verifyRemarks(panel,report.graph.stage_payment_sources.notes);
    }
    assert.equal(await evaluate('document.querySelectorAll(".packet-file").length'),packets.length);
    for (const packet of packets) {
      for (const page of packet.pages) {
        const ref=page.doc+'/p'+page.page;
        const group='document.querySelector('+JSON.stringify('[data-packet-page="'+ref+'"]')+')';
        assert.equal(await evaluate(group+'.closest(".packet-file").dataset.packetStatus'),packet.status);
        for (const reason of page.reasons) assert.ok(await evaluate(group+'.textContent.includes('+JSON.stringify(reason)+')'));
        await evaluate(group+'.querySelector("button").click()');
        const original=report.graph.documents.find(d=>d.id===page.doc).name+' · 第 '+page.page+' 页';
        await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-title").textContent==='+JSON.stringify(original)
          +' && document.querySelector("#page-dialog img")?.naturalWidth>0','original acceptance page in shared PDF');
        const scope=page.rows.find(r=>r.field==='acceptance_scope');
        if (scope?.facts.length) assert.equal(await evaluate('document.querySelector(".located")?.dataset.fact'),scope.facts[0]);
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
        if (page.reasons.length) {
          const jump='document.querySelector('+JSON.stringify('[data-packet-issue="'+ref+'"]')+')';
          await evaluate(jump+'.click()');
          await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-title").textContent==='+JSON.stringify(original),'unresolved receipt page');
          await evaluate('document.querySelector("#page-dialog [data-close]").click()');
        }
        const detail=page.rows.filter(r=>['acceptance','contract_id','accepted_on'].includes(r.field));
        if (detail.length) await evaluate(group+'.querySelector("details").open=true');
        await verifyRemarks(group,page.rows.filter(r=>r.field!=='acceptance_scope'));
      }
    }
    const supplier=reservations?.supplier;
    if (supplier) {
      const panel='document.querySelector(".supplier-review")';
      assert.equal(await evaluate(panel+'.open'),supplier.status!=='ok');
      await evaluate(panel+'.open=true');
      await verifyRemarks(panel,supplier.lines);
      const note=supplier.lines.find(s=>s.kind==='delivery_note' && s.line);
      if (note) {
        await evaluate('reservationSource('+JSON.stringify({...note,facts:[]})+',state.bundle.report.graph).querySelector("button").click()');
        await wait('document.querySelector(".located[data-gap-line] blockquote")?.textContent==='+JSON.stringify(note.quote),'original delivery note without an extracted fact');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
      for (const page of supplier.pages.filter(p=>!supplier.names[p.unit] || !p.native || !p.text_only)) {
        const button=panel+'.querySelector('+JSON.stringify('[data-supplier-page="'+page.doc+'/p'+page.page+'"]')+')';
        await evaluate(button+'.click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth>0','supplier original page');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
    }
    assert.equal(await evaluate('!!document.querySelector(".reservation-review")'),hasRemarks);
    if (hasRemarks) {
      const panel='document.querySelector(".reservation-review")';
      await verifyRemarks(panel,reservations.lines);
      for (const fact of report.graph.facts.filter(f=>inspection.evidence.includes(f.id) && ['acceptance_result','acceptance_scope'].includes(f.field))) {
        const row=panel+'.querySelector('+JSON.stringify('[data-reservation-fact="'+fact.id+'"]')+')';
        assert.equal(await evaluate(row+'.querySelector("q").textContent'),fact.source_line?.text || fact.quote);
        await evaluate(row+'.querySelector("button").click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(fact.id),'inspection conclusion box');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
      for (const page of reservations.mixed_pages) {
        const button=panel+'.querySelector('+JSON.stringify('[data-reservation-page="'+page.doc+'/p'+page.page+'"]')+')';
        await evaluate(button+'.click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth>0','inspection page with annotations');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
    }
    const windows=report.findings.filter(f=>f.payment_window);
    const windowPanel=f=>'document.querySelector('+JSON.stringify('[data-finding="'+f.id+'"] .payment-window')+')';
    for (const finding of windows) {
      const w=finding.payment_window, panel=windowPanel(finding);
      const dates=[w.trigger_on,w.calendar_end];
      if (finding.rule==='H05') dates.push(w.paid_on);
      assert.deepEqual(await evaluate('[...'+panel+'.querySelectorAll("dd")].map(e=>e.textContent)'),dates.map(d=>d || '待核'));
      assert.equal(await evaluate(panel+'.dataset.windowState'),w.outcome || w.state);
      const citations=new Map();
      for (const item of w.lines) {
        const fact=item.facts.map(id=>report.graph.facts.find(f=>f.id===id)).find(f=>f?.quote===item.quote);
        citations.set(fact?.id || item.doc+'/p'+item.page+'/l'+item.line,{quote:item.quote,fact:fact?.id,line:item.line});
      }
      for (const id of [w.trigger_ref,w.paid_ref].filter(Boolean)) {
        const fact=report.graph.facts.find(f=>f.id===id);
        if (!citations.has(id)) citations.set(id,{quote:fact.source_line?.text || fact.quote,fact:id});
      }
      for (const [ref,original] of citations) {
        const row=panel+'.querySelector('+JSON.stringify('[data-window-source="'+ref+'"]')+')';
        assert.equal(await evaluate(row+'.querySelector("q").textContent'),original.quote);
        await evaluate(row+'.querySelector("button").click()');
        const locator=original.fact?'document.querySelector(".located")?.dataset.fact==='+JSON.stringify(original.fact):
          'document.querySelector(".located[data-gap-line] blockquote")?.textContent==='+JSON.stringify(original.quote);
        await wait('document.querySelector("#page-dialog").open && '+locator+' && document.querySelector("#page-dialog img")?.naturalWidth>0','original payment-window evidence');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
      for (const page of w.mixed_pages) {
        const button=panel+'.querySelector('+JSON.stringify('[data-window-page="'+page.doc+'/p'+page.page+'"]')+')';
        await evaluate(button+'.click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth>0','whole payment-window page');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
      if (w.calendar_source) {
        assert.equal(await evaluate(panel+'.querySelector("[data-workday-source]").href'),report.policy.sources[w.calendar_source].url);
        if (w.days.length) {
          await evaluate(panel+'.querySelector(".workday-trace").open=true');
          await wait(panel+'.querySelectorAll(".workday-table tbody tr").length==='+w.days.length,'full workday calculation');
          assert.deepEqual(await evaluate('[...'+panel+'.querySelectorAll("tbody tr")].map(r=>[...Array.from(r.cells,c=>c.textContent),r.classList.contains("workday-counted")])'),
            w.days.map(d=>[d.date,d.kind,String(d.total),d.counted]));
          await evaluate(panel+'.querySelector(".workday-trace").open=false');
        }
      }
    }
    if (warranty) {
      const entry=warranty.warranty_check;
      const panel='document.querySelector(".warranty-review")';
      assert.deepEqual(await evaluate('[...'+panel+'.querySelectorAll("dd")].map(d=>d.textContent)'),
        [entry.accepted_on,entry.calendar_end,entry.confirmed_on].map(d=>d || '待核'));
      assert.equal(await evaluate(panel+'.querySelectorAll(".warranty-conflict").length'),entry.identity_conflicts.length);
      for (const source of report.graph.warranty_sources.lines.filter(s=>entry.scope.includes(s.unit))) {
        const fact=report.graph.facts.find(f=>source.facts.includes(f.id) && f.quote===source.quote);
        const ref=fact?.id || source.doc+'/p'+source.page+'/l'+source.line;
        const row=panel+'.querySelector('+JSON.stringify('[data-warranty-source="'+ref+'"]')+')';
        assert.equal(await evaluate(row+'.querySelector("q").textContent'),source.quote);
        await evaluate(row+'.querySelector("button").click()');
        const where=fact?'document.querySelector(".located")?.dataset.fact==='+JSON.stringify(fact.id):
          'document.querySelector(".located")?.dataset.gapLine==='+JSON.stringify(String(source.line));
        await wait('document.querySelector("#page-dialog").open && '+where+' && document.querySelector("#page-dialog img")?.naturalWidth>0','warranty original line');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
      for (const p of report.graph.warranty_sources.pages.filter(p=>entry.scope.includes(p.unit) && (!p.native || !p.text_only))) {
        const button=panel+'.querySelector('+JSON.stringify('[data-warranty-page="'+p.doc+'/p'+p.page+'"]')+')';
        await evaluate(button+'.click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth>0','warranty full page');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
      for (const finding of report.findings.filter(f=>f.rule==='H05' && f.warranty_check)) {
        const payment='document.querySelector('+JSON.stringify('[data-finding="'+finding.id+'"] .warranty-review')+')';
        const bank=report.graph.facts.find(f=>f.field==='paid_on' && finding.evidence.includes(f.id));
        assert.equal(await evaluate(payment+'.querySelector(".warranty-date:last-child dd").textContent'),bank.source_line.text.split(/[:：]/u).at(-1).trim());
      }
    }
    if (effect) {
      const panel='document.querySelector(".effect-review")';
      assert.equal(await evaluate('!!'+panel),Boolean(effect.conditions.length || effect.mixed_pages.length || effect.approval_pages?.length));
      for (const p of effect.approval_pages || []) {
        const pageId=p.doc+'/p'+p.page;
        const decision=report.graph.facts.find(f=>f.doc===p.doc && f.page===p.page && f.field==='approval_result');
        await evaluate(panel+'.querySelector('+JSON.stringify('[data-approval-page="'+pageId+'"]')+').click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector(".page-image")?.naturalWidth>0','original board resolution');
        if (decision) assert.equal(await evaluate('document.querySelector(".located")?.dataset.fact'),decision.id);
        const notes = effect.conditions.filter(row => row.kind==='approval_note' && row.doc===p.doc && row.page===p.page);
        const control = 'document.querySelector(".approval-switch")';
        if (!notes.length) assert.equal(await evaluate('Boolean('+control+')'),false);
        if (decision && notes.length===1) {
          const note = notes[0];
          const fact = report.graph.facts.find(f => note.facts.includes(f.id) && f.quote===note.quote);
          const ref = fact?.id || 'line/'+note.line;
          if (ref!==decision.id) {
            await evaluate('document.querySelector("[aria-label=放大原页]").click()');
            for (const width of [1440,390,320]) {
              await call('Emulation.setDeviceMetricsOverride',{width,height:width===1440?900:844,deviceScaleFactor:1,mobile:width<600});
              assert.equal(await evaluate(control+'.dataset.nextRef'),ref);
              await evaluate(control+'.focus()');
              assert.ok(await evaluate('document.activeElement==='+control+' && !'+control+'.disabled'));
              await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r',unmodifiedText:'\r'});
              await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
              assert.equal(await evaluate('document.querySelector(".field-navigator select").value'),ref);
              assert.equal(await evaluate('document.querySelector(".located blockquote").textContent'),note.quote);
              assert.equal(await evaluate('document.querySelectorAll(".image-sheet rect").length'),fact?.source_line?.rects.length || 0);
              assert.equal(await evaluate('document.querySelector(".zoom-scale").textContent'),'125%');
              assert.ok(await evaluate('document.activeElement==='+control+' && '+control+'.offsetHeight>=44 && document.querySelector("#page-dialog").scrollWidth<=innerWidth'));
              if (process.env.AUDIT_UI_SHOTS && width===1440) {
                const shot=await call('Page.captureScreenshot',{format:'png'});
                await writeFile(join(process.env.AUDIT_UI_SHOTS,'board-'+performanceCase+'.png'),Buffer.from(shot.data,'base64'));
              }
              await evaluate(control+'.click()');
              assert.equal(await evaluate('document.querySelector(".located").dataset.fact'),decision.id);
            }
            await call('Emulation.clearDeviceMetricsOverride');
            if (fact && note.line) {
              // Exercise a missed transcription in this browser's in-memory copy of a watermarked case.
              const viewWithoutObservation = (omitted, doc, page, decisionId) => {
                const original = state.bundle;
                const graph = original.report.graph;
                const ledger = graph.contract_effect_sources;
                const conditions = ledger.conditions.map(row => ({...row,facts:row.facts.filter(id => id!==omitted)}));
                try {
                  state.bundle = {...original,report:{...original.report,graph:{...graph,
                    facts:graph.facts.filter(f => f.id!==omitted),contract_effect_sources:{...ledger,conditions}}}};
                  openPage(doc,page,decisionId);
                } finally {
                  state.bundle = original;
                }
              };
              await evaluate('('+viewWithoutObservation+')(...'+JSON.stringify([fact.id,p.doc,p.page,decision.id])+')');
              await wait('document.querySelector(".page-image")?.naturalWidth>0','original with an untranscribed line');
              await evaluate(control+'.click()');
              assert.equal(await evaluate('document.querySelector(".located").dataset.gapLine'),String(note.line));
              assert.equal(await evaluate('document.querySelector(".located blockquote").textContent'),note.quote);
              assert.equal(await evaluate('document.querySelectorAll(".image-sheet rect").length'),0);
              await evaluate(control+'.click()');
              assert.equal(await evaluate('document.querySelector(".located").dataset.fact'),decision.id);
            }
          }
        }
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
        for (const f of report.findings.filter(f=>f.stage && ['H04','H05'].includes(f.rule) && f.evidence.includes(pageId))) {
          await evaluate('document.querySelector('+JSON.stringify('[data-finding="'+f.id+'"] [aria-controls="board-approval-evidence"]')+').click()');
          assert.equal(await evaluate('document.activeElement.id'),'board-approval-evidence');
        }
      }
      if (effect.seals) {
        assert.deepEqual(await evaluate('[...'+panel+'.querySelectorAll("dd")].map(e=>e.textContent)'),
          [effect.seals.dates.buyer_sealed_on,effect.seals.dates.seller_sealed_on,effect.seals.declared_on].map(d=>d || '待核'));
        assert.equal(await evaluate(panel+'.querySelector("h4").textContent'),effect.approval_pages?.length?'董事会决议与合同生效':'双方盖章与合同生效日');
      }
      for (const item of effect.conditions) {
        const fact=report.graph.facts.find(f=>item.facts.includes(f.id) && f.quote===item.quote);
        const ref=fact?.id || item.doc+'/p'+item.page+'/l'+item.line;
        const row=panel+'.querySelector('+JSON.stringify('[data-effect-source="'+ref+'"]')+')';
        assert.equal(await evaluate(row+'.querySelector("q").textContent'),item.quote);
        assert.equal(await evaluate(row+'.querySelector("small").textContent'),item.line?'原页文字层第 '+item.line+' 行':'影像读图引文');
        if (!item.line && fact) {
          const label={visual:'待核原图',confirmed:'人工已确认',disputed:'人工有异议',unsupported:'引用不支持取值',anchored:'已匹配文字层'}[fact.status];
          assert.equal(await evaluate(row+'.querySelector(".tag").textContent'),label);
        }
        await evaluate(row+'.querySelector("button").click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth>0','contract condition on original');
        if (fact) assert.equal(await evaluate('document.querySelector(".located").dataset.fact'),fact.id);
        else assert.equal(await evaluate('document.querySelector(".located[data-gap-line] blockquote").textContent'),item.quote);
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
      for (const p of effect.mixed_pages) {
        const button=panel+'.querySelector('+JSON.stringify('[data-effect-page="'+p.doc+'/p'+p.page+'"]')+')';
        await evaluate(button+'.click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth>0','whole mixed contract page');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
    }
    if (batches) {
      const panel='document.querySelector(".delivery-batches")';
      const ledger=report.graph.delivery_batch_sources;
      const openFact=async (container,id) => {
        const row=container+'.querySelector('+JSON.stringify('[data-batch-fact="'+id+'"]')+')';
        const fact=report.graph.facts.find(f=>f.id===id);
        await wait(row+'?.querySelector("q").textContent==='+JSON.stringify(fact.source_line?.text || fact.quote),'exact batch quote');
        await evaluate(row+'.querySelector("button").click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth>0 && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(id),'batch fact on the original');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      };
      const checkSigning=async (group,key,section,stages) => {
        const authority=section+'.querySelector(".batch-signing")';
        await openFact(authority,group.signing_requirement.clause_ref);
        for (const name of group.signing_requirement.required) assert.ok(await evaluate(authority+'.innerText.includes('+JSON.stringify(name)+')'));
        for (const item of stages) {
          const locator='[data-finding="'+item.id+'"] [aria-controls="batch-signing-'+key+'"]';
          await evaluate('document.querySelector('+JSON.stringify(locator)+').click()');
          assert.equal(await evaluate('document.activeElement.dataset.batchSigning'),String(key));
        }
        const matched=batches.records.filter(r=>group.records.includes(r.unit) && r.signing);
        assert.equal(await evaluate(authority+'.querySelectorAll("[data-signing-record]").length'),matched.length);
        for (const record of matched) {
          const proof=authority+'.querySelector('+JSON.stringify('[data-signing-record="'+record.unit+'"]')+')';
          await verifyRemarks(proof,record.signing.signed.map(s=>s.native && !s.fact?{...s,facts:[]}:s));
          const native=record.signing.signed.find(s=>s.line && s.native);
          if (native) {
            await evaluate('reservationSource('+JSON.stringify({...native,fact:null,facts:[]})+',state.bundle.report.graph).querySelector("button").click()');
            await wait('document.querySelector(".located[data-gap-line] blockquote")?.textContent==='+JSON.stringify(native.quote),'signature original without a model observation');
            await evaluate('document.querySelector("#page-dialog [data-close]").click()');
          }
          for (const value of [...record.signing.missing_names,...record.signing.other_names])
            assert.ok(await evaluate(proof+'.innerText.includes('+JSON.stringify(value)+')'));
        }
      };
      if (batches.rule_ref) await openFact(panel,batches.rule_ref);
      if (batches.separate_final) {
        const final=batches.separate_final;
        const section='document.getElementById("batch-final-acceptance")';
        assert.equal(await evaluate(section+'.dataset.status'),final.status);
        assert.ok(await evaluate(section+'.innerText.includes('+JSON.stringify(final.detail)+')'));
        if (final.signing_requirement) await checkSigning(final,'final',section,report.findings.filter(f=>f.warranty_check));
        if (batches.completion_on) assert.ok(await evaluate(section+'.querySelector(".final-date").innerText.includes('+JSON.stringify(batches.completion_on)+')'));
        for (const f of report.findings.filter(f=>f.warranty_check)) {
          const locator='[data-finding="'+f.id+'"] [aria-controls="batch-final-acceptance"]';
          await evaluate('document.querySelector('+JSON.stringify(locator)+').click()');
          assert.equal(await evaluate('document.activeElement.id'),'batch-final-acceptance');
        }
        for (const b of final.basis.filter(b=>b.number_ref)) await openFact(section,b.number_ref);
        for (const r of batches.records.filter(r=>final.records.includes(r.unit))) {
          if (r.refs_ref) await openFact(section,r.refs_ref);
          for (const p of ledger.pages.filter(p=>p.unit===r.unit && !p.text_only)) {
            const selector='[data-batch-page="'+p.doc+'/p'+p.page+'"]';
            assert.ok(await evaluate(section+'.querySelector('+JSON.stringify(selector)+')!=null'));
          }
          for (const note of ledger.visual_notes.filter(n=>n.unit===r.unit)) await openFact(section,note.fact);
          const fields=['accepted_on','measured_result','delivered_serials','acceptance_signer'];
          await evaluate(section+'.querySelectorAll("details").forEach(d=>d.open=true)');
          for (const fact of report.graph.facts.filter(f=>r.evidence.includes(f.id) && fields.includes(f.field))) await openFact(section,fact.id);
          await evaluate(section+'.querySelectorAll("details").forEach(d=>d.open=false)');
        }
      }
      for (const b of batches.batches) {
        const section=panel+'.querySelector('+JSON.stringify('[data-delivery-index="'+b.index+'"]')+')';
        assert.ok(await evaluate(section+'.innerText.includes('+JSON.stringify(b.detail)+') && '+section+'.querySelector(".tag").classList.contains('+JSON.stringify(b.status)+')'));
        await openFact(section,b.clause_ref);
        if (b.signing_requirement) await checkSigning(b,b.index,section,report.findings.filter(f=>f.stage?.batch_index===b.index));
        for (const item of batches.records.filter(r=>b.records.includes(r.unit))) {
          for (const val of [item.number,item.date,...item.serials].filter(Boolean))
            assert.ok(await evaluate(section+'.innerText.includes('+JSON.stringify(val)+')'));
        }
        await evaluate(section+'.querySelector("details").open=true');
        for (const fact of report.graph.facts.filter(f=>b.evidence.includes(f.id) && ['measured_result','acceptance_criteria','delivered_serials'].includes(f.field)))
          await openFact(section,fact.id);
        await evaluate(section+'.querySelector("details").open=false');
      }
      for (const page of ledger.pages.filter(p=>!p.text_only)) {
        const button=panel+'.querySelector('+JSON.stringify('[data-batch-page="'+page.doc+'/p'+page.page+'"]')+')';
        await evaluate(button+'.click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth>0','batch image annotation');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
      for (const note of ledger.visual_notes) await openFact(panel,note.fact);
      for (const page of ledger.pages) for (const line of page.uncovered) {
        const row=panel+'.querySelector('+JSON.stringify('[data-batch-line="'+page.doc+'/p'+page.page+'/l'+line.line+'"]')+')';
        await evaluate(row+'.querySelector("button").click()');
        await wait('document.querySelector(".located[data-gap-line] blockquote")?.textContent==='+JSON.stringify(line.quote),'batch rider on original');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
    }
    if (authority) {
      const panel='document.querySelector(".acceptance-authority")';
      const ledger=report.graph.acceptance_authority_sources;
      assert.equal(await evaluate(panel+'.dataset.authorityStatus'),authority.status);
      assert.equal(await evaluate(panel+'.querySelector(".signer-names").textContent'),authority.required.join('、'));
      for (const record of authority.records) {
        const section=panel+'.querySelector('+JSON.stringify('[data-signer-record="'+record.unit+'"]')+')';
        const visible=await evaluate(section+'.innerText');
        for (const label of [record.date, ...record.missing_names, ...record.other_names].filter(Boolean)) assert.ok(visible.includes(label));
        assert.equal(await evaluate(section+'.querySelectorAll(".signer-source").length'),record.signed.length);
        assert.ok(await evaluate(section+'.querySelector(".tag").classList.contains('+JSON.stringify(record.status)+')'));
      }
      const sources=[...ledger.clauses,...authority.records.flatMap(r=>r.signed),...ledger.visual_notes,
                     ...ledger.pages.flatMap(p=>p.uncovered.map(l=>({...l,doc:p.doc,page:p.page})))];
      for (const item of sources) {
        const fact=report.graph.facts.find(f=>f.id===(item.fact || (!item.line && item.facts?.[0])));
        const ref=fact && (!item.line || fact.quote===item.quote) ? fact.id : null;
        const id=ref || item.doc+'/p'+item.page+'/l'+item.line;
        const row=panel+'.querySelector('+JSON.stringify('[data-signer-source="'+id+'"]')+')';
        if (!ref && !await evaluate('!!'+row) && sources.some(s=>s!==item && s.doc===item.doc && s.page===item.page && s.line===item.line && s.fact)) continue;
        assert.equal(await evaluate(row+'.querySelector("q").textContent'),item.quote);
        assert.equal(await evaluate('getComputedStyle('+row+'.querySelector("q")).whiteSpace'),'pre-wrap');
        await evaluate(row+'.querySelector("button").click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth>0','image of signature record');
        if (ref) assert.equal(await evaluate('document.querySelector(".located").dataset.fact'),ref);
        else assert.equal(await evaluate('document.querySelector(".located[data-gap-line] blockquote").textContent'),item.quote);
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
      for (const page of ledger.pages.filter(p=>!p.text_only)) {
        const locator=panel+'.querySelector('+JSON.stringify('[data-signer-page="'+page.doc+'/p'+page.page+'"]')+')';
        await evaluate(locator+'.click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth>0','full signature page');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
    }
    if (change) {
      const panel='document.querySelector(".quality-change")';
      assert.equal(await evaluate(panel+'.dataset.qualityChange'),change.state);
      assert.equal(await evaluate(panel+'.querySelector(".quality-standard")?.textContent || null'),change.applied_criterion);
      assert.deepEqual(await evaluate('[...'+panel+'.querySelectorAll(".mandate-dates dd > span")].map(e=>e.textContent)'),
        [change.buyer_sealed_on,change.seller_sealed_on,change.effective_on,...(change.state==='by_batch'?[]:[change.accepted_on])].map(d=>d || '待核'));
      if (change.quantity) {
        const quantity=change.quantity;
        const expected=quantity.difference===null?'数量差额待核':quantity.difference===0?'数量相符':
          (quantity.difference<0?'少 ':'多 ')+Math.abs(quantity.difference)+quantity.applicable.unit;
        assert.ok(await evaluate(panel+'.querySelector(".quantity-result").textContent.endsWith('+JSON.stringify(expected)+')'));
        await verifyRemarks(panel,quantity.lines);
        const nativeNote=quantity.lines.find(line=>line.field==='quantity_note') || quantity.lines.find(line=>line.field==='revised_quantity');
        if (nativeNote) {
          await evaluate('reservationSource('+JSON.stringify({...nativeNote,facts:[]})+',state.bundle.report.graph).querySelector("button").click()');
          await wait('document.querySelector(".located[data-gap-line] blockquote")?.textContent==='+JSON.stringify(nativeNote.quote),'quantity from the original row without a model observation');
          await evaluate('document.querySelector("#page-dialog [data-close]").click()');
        }
        for (const page of quantity.pages.filter(p=>!p.native || !p.text_only)) {
          const locator=panel+'.querySelector('+JSON.stringify('[data-quantity-page="'+page.doc+'/p'+page.page+'"]')+')';
          await evaluate(locator+'.click()');
          await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth>0','full page with quantities');
          await evaluate('document.querySelector("#page-dialog [data-close]").click()');
          const readings=report.graph.facts.filter(f=>f.doc===page.doc && f.page===page.page && !f.source_line && !change.units.includes(page.unit));
          if (readings.length) {
            const list=panel+'.querySelector('+JSON.stringify('[data-quantity-image="'+page.doc+'/p'+page.page+'"]')+')';
            await evaluate(list+'.open=true');
            for (const fact of readings) {
              const row=list+'.querySelector('+JSON.stringify('[data-change-fact="'+fact.id+'"]')+')';
              await wait(row+'?.querySelector("q").textContent==='+JSON.stringify(fact.quote),'image quantity reading');
              await evaluate(row+'.querySelector("button").click()');
              await wait('document.querySelector(".located")?.dataset.fact==='+JSON.stringify(fact.id),'image quantity original');
              await evaluate('document.querySelector("#page-dialog [data-close]").click()');
            }
          }
        }
      }
      await evaluate(panel+'.querySelectorAll("details").forEach(d=>d.open=true)');
      const fields=['change_scope','change_timing','change_effect_clause','buyer_signature','seller_signature'];
      if (!change.quantity) fields.push('acceptance_criteria','revised_criterion','inspection_basis','measured_result');
      const refs=report.graph.facts.filter(f=>fields.includes(f.field) && change.evidence.includes(f.id) &&
        (!['buyer_signature','seller_signature'].includes(f.field) || change.units.includes(f.unit || f.doc)));
      for (const fact of refs) {
        const row=panel+'.querySelector('+JSON.stringify('[data-change-fact="'+fact.id+'"]')+')';
        await wait(row+'?.textContent.includes('+JSON.stringify(fact.quote)+')','visible amendment evidence');
        await evaluate(row+'.querySelector("button").click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(fact.id),'source of '+fact.field);
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
      for (const page of report.graph.quality_addenda.pages) {
        if (!page.text_only) {
          await click('查看第 '+page.page+' 页',panel);
          await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth>0','visible mixed-layout page');
          await evaluate('document.querySelector("#page-dialog [data-close]").click()');
          const notes=report.graph.facts.filter(f=>f.doc===page.doc && f.page===page.page && !f.source_line && f.field!=='contract_addendum' && change.evidence.includes(f.id));
          const list=panel+'.querySelector('+JSON.stringify('[data-change-image="'+page.doc+'/p'+page.page+'"]')+')';
          if (notes.length) await evaluate(list+'.open=true');
          for (const note of notes) {
            const line=list+'.querySelector('+JSON.stringify('[data-change-fact="'+note.id+'"]')+')';
            await wait(line+'?.textContent.includes('+JSON.stringify(note.quote)+')','transcribed visual rider');
            await evaluate(line+'.querySelector("button").click()');
            await wait('document.querySelector(".located")?.dataset.fact==='+JSON.stringify(note.id),'visual rider source');
            await evaluate('document.querySelector("#page-dialog [data-close]").click()');
          }
        }
        for (const line of page.uncovered) {
          await click('定位第 '+line.line+' 行',panel);
          await wait('document.querySelector(".located[data-gap-line] blockquote")?.textContent==='+JSON.stringify(line.quote),'unread addendum clause');
          await evaluate('document.querySelector("#page-dialog [data-close]").click()');
        }
      }
    }
    if (chain) {
      assert.equal(await evaluate('document.querySelector(".reinspection-trail").dataset.disposition'),chain.state);
      await evaluate('document.querySelector(".reinspection-trail").open=true');
      for (const role of ['original','repair','final']) {
        const step=chain.steps.find(s=>s.role===role);
        assert.ok(step);
        const row='document.querySelector('+JSON.stringify('[data-reinspection-role="'+role+'"]')+')';
        await evaluate('document.querySelector("#trail-tab-'+role+'").click()');
        assert.ok(await evaluate('['+row+',document.querySelector("#trail-tab-'+role+'")].some(n=>n.textContent.includes('+JSON.stringify(step.date)+'))'));
        const factId=await evaluate(row+'.querySelector("[data-cited-fact]").dataset.citedFact');
        assert.ok(step.evidence.includes(factId));
        const fact=report.graph.facts.find(f=>f.id===factId);
        await evaluate(row+'.querySelector("[data-cited-fact]").click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.textContent.includes('+JSON.stringify(fact.quote)+')','reinspection source '+role);
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
    }
    for (const phase of phases) {
      const selector='[data-finding="'+phase.id+'"]';
      const node='document.querySelector('+JSON.stringify(selector)+')';
      assert.ok(await evaluate(node+'.innerText.includes('+JSON.stringify(phase.detail)+')'));
      assert.ok(await evaluate(node+'.querySelector(".procedure-title").innerText.includes('+JSON.stringify(phase.stage.share+'%')+')'));
      await evaluate(node+'.querySelector(".clause-source button").click()');
      const fact=report.graph.facts.find(f=>f.id===phase.stage.clause_ref);
      await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.textContent.includes('+JSON.stringify(fact.quote)+')','pinned contract clause');
      await evaluate('document.querySelector("#page-dialog [data-close]").click()');
    }
    for (const entry of report.findings.find(f => f.rule==='H01').delegations || []) {
      const panel='document.querySelector('+JSON.stringify('[data-mandate-side="'+entry.side+'"]')+')';
      if (entry.agent_kind) assert.equal(await evaluate(panel+'.dataset.agentKind'),entry.agent_kind);
      assert.deepEqual(await evaluate('[...'+panel+'.querySelectorAll("dd > span")].map(s=>s.textContent)'),
        [entry.signed_on,entry.issued_on,entry.valid_from,entry.valid_until].map(d=>d || '待核'));
      for (const fact of report.graph.facts.filter(f => entry.evidence.includes(f.id) && [entry.signature_field,'grant_agent','grant_scope','grant_signature'].includes(f.field))) {
        const row=panel+'.querySelector('+JSON.stringify('[data-mandate-fact="'+fact.id+'"]')+')';
        assert.ok(await evaluate(row+'.textContent.includes('+JSON.stringify(fact.quote)+')'));
        await evaluate(row+'.querySelector("button").click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(fact.id),'delegated signature or authority');
        const ledger=report.graph.delegation_coverage;
        const held=[...(ledger.agent_holds || []),...(ledger.signer_holds || [])].find(h=>h.fact===fact.id && h.lines?.length);
        if (held) {
          const native='document.querySelector(".located .mandate-name-source")';
          assert.equal(await evaluate(native+'.dataset.mandateKind'),held.kind);
          assert.deepEqual(await evaluate('[...'+native+'.querySelectorAll("blockquote")].map(q=>q.textContent)'),held.lines.map(l=>l.quote));
          assert.equal(await evaluate('getComputedStyle('+native+'.querySelector("blockquote")).whiteSpace'),'pre-wrap');
        }
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
      for (const page of report.graph.delegation_coverage.pages.filter(p=>entry.units.includes(p.unit))) {
        if (!page.native) {
          assert.ok(await evaluate(panel+'.textContent.includes("需通读完整授权范围")'));
          const notes=report.graph.facts.filter(f=>f.doc===page.doc && f.page===page.page && f.field==='other');
          const group=panel+'.querySelector('+JSON.stringify('[data-mandate-image="'+page.doc+'/p'+page.page+'"]')+')';
          if (notes.length) await evaluate(group+'.open=true');
          for (const fact of notes) {
            const row=group+'.querySelector('+JSON.stringify('[data-mandate-note="'+fact.id+'"]')+')';
            await wait(row+'?.textContent.includes('+JSON.stringify(fact.quote)+')','image note transcription');
            await evaluate(row+'.querySelector("button").click()');
            await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(fact.id),'image note original');
            await evaluate('document.querySelector("#page-dialog [data-close]").click()');
          }
        }
        for (const line of page.uncovered) {
          await click('核对委托书第 '+line.line+' 行', panel);
          await wait('document.querySelector(".located[data-gap-line] blockquote")?.textContent==='+JSON.stringify(line.quote),'unreviewed authority condition');
          await evaluate('document.querySelector("#page-dialog [data-close]").click()');
        }
      }
    }
    for (const rule of ['H01','H02']) {
      const f=report.findings.find(row=>row.rule===rule);
      const node='document.querySelector('+JSON.stringify('[data-finding="'+f.id+'"] .performance-comparison')+')';
      await evaluate(node+'.open=true');
      const selected=rule==='H01'?['effect_clause','approval_result']:['measured_result','acceptance_result'];
      for (const source of report.graph.facts.filter(v=>selected.includes(v.field) && f.evidence.includes(v.id))) {
        const row='document.querySelector('+JSON.stringify('[data-source-fact="'+source.id+'"]')+')';
        await wait(row+'?.textContent.includes('+JSON.stringify(source.quote)+')','original '+source.field);
        await evaluate(row+'.querySelector("button").click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.textContent.includes('+JSON.stringify(source.quote)+')','cited '+source.field);
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
    }
    for (const fact of report.graph.facts.filter(f => f.origin === 'printed_quality_number')) {
      const query = new URLSearchParams({rev: String(task.rev), fact: fact.id});
      await call('Page.navigate', {url: root+'/workpaper/'+performanceCase+'?'+query});
      const card = 'document.querySelector(".located .quality-number-check")';
      await wait('document.querySelector("#page-dialog").open && '+card+' && document.querySelector(".located").dataset.fact==='+JSON.stringify(fact.id),
        'classification on the cited page');
      await evaluate(card+'.querySelector("summary").click()');
      const trace = report.calls.pages.find(p => p.doc === fact.doc && p.page === fact.page);
      const indices = [fact.id.split('/f').pop(), fact.classification_index];
      const labels = indices.map(i => trace.check.input.find(row => row.index === i).field);
      assert.deepEqual(await evaluate('[...'+card+'.querySelectorAll("p")].map(p=>p.textContent)'),
        [labels[0]+' · 与原页冲突', labels[1]+' · 与原页相符']);
      assert.deepEqual(await evaluate('[...'+card+'.querySelectorAll("blockquote")].map(b=>b.textContent)'),
        [fact.quote, fact.quote]);
      await evaluate('document.querySelector("#page-dialog [data-close]").click()');
    }
    for (const hold of report.graph.quality_references?.holds || []) {
      const query = new URLSearchParams({rev: String(task.rev), fact: hold.fact});
      await call('Page.navigate', {url: root+'/workpaper/'+performanceCase+'?'+query});
      const card = 'document.querySelector(".located .quality-number-hold")';
      await wait('document.querySelector("#page-dialog").open && '+card+' && document.querySelector(".located").dataset.fact==='+JSON.stringify(hold.fact),
        'qualified identifier on the original page');
      const lines = [...hold.lines.map(l => '本页第 '+l.number+' 行 · '+l.quote),
        ...hold.observations.map(o => '本页读图引文 · '+o.quote)];
      assert.deepEqual(await evaluate('[...'+card+'.querySelectorAll("blockquote")].map(b=>b.textContent)'), lines);
      assert.equal(await evaluate(card+'.querySelector("strong").textContent'), '需核对完整编号');
      await call('Emulation.setDeviceMetricsOverride',{width:320,height:880,deviceScaleFactor:1,mobile:false});
      assert.ok(await evaluate(card+'.clientWidth>0 && '+card+'.scrollWidth<='+card+'.clientWidth+1'));
      await evaluate('document.querySelector("#page-dialog [data-close]").click()');
    }
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:880,deviceScaleFactor:1,mobile:false});
      if (equipment) {
        await evaluate('document.getElementById("equipment-models").open=true');
        if (equipment.exchange) {
          assert.ok(await evaluate('[...document.querySelectorAll(".equipment-exchange,.exchange-list")].every(e=>e.clientWidth && e.scrollWidth<=e.clientWidth+1)'));
          if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
            await evaluate('document.querySelector(".equipment-exchange").scrollIntoView({block:"start"})');
            const capture=await call('Page.captureScreenshot',{format:'png'});
            await writeFile(join(process.env.AUDIT_UI_SHOTS,'exchange-'+performanceCase+'-'+width+'.png'),Buffer.from(capture.data,'base64'));
          }
        }
        assert.ok(await evaluate('[...document.querySelectorAll(".equipment-originals,.equipment-original")].every(e=>e.scrollWidth<=e.clientWidth+1)'),'equipment records fit at '+width);
        if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
          await evaluate('document.getElementById("equipment-models").scrollIntoView({block:"start"})');
          const capture=await call('Page.captureScreenshot',{format:'png'});
          await writeFile(join(process.env.AUDIT_UI_SHOTS,'equipment-'+performanceCase+'-'+width+'.png'),Buffer.from(capture.data,'base64'));
        }
      }
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'workpaper viewport at '+width);
      const overflow = await evaluate('[...document.querySelectorAll(".phase-summary li,.phase-results,.clause-source,.mandate-dates,.mandate-side,.quality-change,.change-comparison,.change-source,.acceptance-authority,.signature-record,.signer-source,.contract-date-evidence,.delivery-batches,.batch-source,.batch-record,.batch-receipt,.receipt-packets,.packet-file,.packet-page")].filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>[e.className,e.clientWidth,e.scrollWidth])');
      assert.deepEqual(overflow,[],'performance layout at '+width);
      if (settlements.length) {
        assert.ok(await evaluate('[...document.querySelectorAll(".stage-payments,.stage-balances,.stage-transfer")].every(e=>e.scrollWidth<=e.clientWidth+1)'),'stage payment totals at '+width);
        if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
          await evaluate('document.querySelector(".stage-payments").scrollIntoView({block:"start"});window.scrollBy(0,-48)');
          const shot=await call('Page.captureScreenshot',{format:'png'});
          await writeFile(join(process.env.AUDIT_UI_SHOTS,'stage-transfers-'+performanceCase+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
        }
      }
      if (packets.length && process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
        await evaluate('document.querySelectorAll(".packet-page details").forEach(d=>d.open=false);document.querySelector(".receipt-packets").scrollIntoView({block:"start"});window.scrollBy(0,-40)');
        const shot=await call('Page.captureScreenshot',{format:'png'});
        await writeFile(join(process.env.AUDIT_UI_SHOTS,'receipt-pages-'+performanceCase+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
      }
      if (batches && process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
        await evaluate('document.querySelector(".delivery-batches").scrollIntoView({block:"start"});window.scrollBy(0,-40)');
        const capture=await call('Page.captureScreenshot',{format:'png'});
        await writeFile(join(process.env.AUDIT_UI_SHOTS,'batches-'+performanceCase+'-'+width+'.png'),Buffer.from(capture.data,'base64'));
        if (batches.separate_final) {
          await evaluate('document.querySelector(".separate-final").scrollIntoView({block:"start"});window.scrollBy(0,-36)');
          assert.ok(await evaluate('[...document.querySelectorAll(".separate-final,.final-originals li,.separate-final .batch-source")].every(e=>e.scrollWidth<=e.clientWidth+1)'));
          const shot=await call('Page.captureScreenshot',{format:'png'});
          await writeFile(join(process.env.AUDIT_UI_SHOTS,'final-'+performanceCase+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
          if (batches.separate_final.signing_requirement) {
            await evaluate('document.getElementById("batch-signing-final").scrollIntoView({block:"start"});window.scrollBy(0,-40)');
            assert.ok(await evaluate('[...document.querySelectorAll("#batch-signing-final,#batch-signing-final .batch-signed-record")].every(e=>e.scrollWidth<=e.clientWidth+1)'));
            const signatures=await call('Page.captureScreenshot',{format:'png'});
            await writeFile(join(process.env.AUDIT_UI_SHOTS,'final-signers-'+performanceCase+'-'+width+'.png'),Buffer.from(signatures.data,'base64'));
          }
        }
        if (batches.batches.some(b=>b.signing_requirement)) {
          assert.ok(await evaluate('[...document.querySelectorAll(".batch-signing,.batch-signed-record")].every(e=>e.scrollWidth<=e.clientWidth+1)'));
          await evaluate('(document.querySelector(".batch-signing[data-status=risk],.batch-signing[data-status=missing]") || document.querySelector(".batch-signing")).closest(".batch-record").scrollIntoView({block:"start"});window.scrollBy(0,-30)');
          const shot=await call('Page.captureScreenshot',{format:'png'});
          await writeFile(join(process.env.AUDIT_UI_SHOTS,'signing-'+performanceCase+'-'+width+'.png'),Buffer.from(shot.data,'base64'));
        }
      }
      if (warranty) {
        const panel='document.querySelector(".warranty-review")';
        assert.ok(await evaluate(panel+'.clientWidth>0 && '+panel+'.scrollWidth<='+panel+'.clientWidth+1'));
        if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
          await evaluate(panel+'.scrollIntoView({block:"start"});window.scrollBy(0,-50)');
          const capture=await call('Page.captureScreenshot',{format:'png'});
          await writeFile(join(process.env.AUDIT_UI_SHOTS,'warranty-'+performanceCase+'-'+width+'.png'),Buffer.from(capture.data,'base64'));
        }
      }
      if (windows.length) {
        const panel=windowPanel(windows.find(f=>f.rule==='H05') || windows[0]);
        await evaluate(panel+'.querySelector(".workday-trace")?.setAttribute("open","")');
        assert.ok(await evaluate('[...document.querySelectorAll(".payment-window,details[open] .workday-table")].every(e=>e.clientWidth>0 && e.scrollWidth<=e.clientWidth+1)'),'payment window at '+width);
        if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
          await evaluate(panel+'.scrollIntoView({block:"start"});window.scrollBy(0,-54)');
          const capture=await call('Page.captureScreenshot',{format:'png'});
          await writeFile(join(process.env.AUDIT_UI_SHOTS,'payment-window-'+performanceCase+'-'+width+'.png'),Buffer.from(capture.data,'base64'));
        }
      }
      if (supplier) {
        const panel='document.querySelector(".supplier-review")';
        assert.ok(await evaluate(panel+'.clientWidth>0 && '+panel+'.scrollWidth<='+panel+'.clientWidth+1'),'supplier panel at '+width);
        if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
          await evaluate(panel+'.open=true;'+panel+'.scrollIntoView({block:"start"});window.scrollBy(0,-100)');
          const capture=await call('Page.captureScreenshot',{format:'png'});
          await writeFile(join(process.env.AUDIT_UI_SHOTS,'supplier-'+performanceCase+'-'+width+'.png'),Buffer.from(capture.data,'base64'));
        }
      }
      if (hasRemarks) {
        const panel='document.querySelector(".reservation-review")';
        assert.ok(await evaluate(panel+'.clientWidth>0 && '+panel+'.scrollWidth<='+panel+'.clientWidth+1'),'inspection remarks at '+width);
        if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
          await evaluate(panel+'.scrollIntoView({block:"start"});window.scrollBy(0,-85)');
          const capture=await call('Page.captureScreenshot',{format:'png'});
          await writeFile(join(process.env.AUDIT_UI_SHOTS,'reservations-'+performanceCase+'-'+width+'.png'),Buffer.from(capture.data,'base64'));
        }
      }
      if (effect && (effect.conditions.length || effect.mixed_pages.length) && process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
        await evaluate('document.querySelector(".effect-review").scrollIntoView({block:"start"});window.scrollBy(0,-45)');
        assert.ok(await evaluate('document.querySelector(".effect-review").scrollWidth<=document.querySelector(".effect-review").clientWidth+1'));
        const capture=await call('Page.captureScreenshot',{format:'png'});
        await writeFile(join(process.env.AUDIT_UI_SHOTS,'effect-'+performanceCase+'-'+width+'.png'),Buffer.from(capture.data,'base64'));
      }
      if (report.findings.some(f=>f.date_checks) && process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
        await evaluate('document.querySelector(".contract-date-evidence").scrollIntoView({block:"start"});window.scrollBy(0,-140)');
        const capture=await call('Page.captureScreenshot',{format:'png'});
        await writeFile(join(process.env.AUDIT_UI_SHOTS,'contract-dates-'+performanceCase+'-'+width+'.png'),Buffer.from(capture.data,'base64'));
      }
      if (authority && process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
        await evaluate('document.querySelector(".acceptance-authority").scrollIntoView({block:"start"});window.scrollBy(0,-54)');
        const capture=await call('Page.captureScreenshot',{format:'png'});
        await writeFile(join(process.env.AUDIT_UI_SHOTS,'signers-'+performanceCase+'-'+width+'.png'),Buffer.from(capture.data,'base64'));
      }
      if (change && process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
        await evaluate('document.querySelector(".quality-change").scrollIntoView({block:"start"});window.scrollBy(0,-54)');
        const capture=await call('Page.captureScreenshot',{format:'png'});
        const name=change.quantity?'quantity-'+performanceCase:'amendment-'+change.state;
        await writeFile(join(process.env.AUDIT_UI_SHOTS,name+'-'+width+'.png'),Buffer.from(capture.data,'base64'));
      }
    }
    const target=report.findings.find(f=>f.rule==='H02');
    await click('查看证据路径','document.querySelector('+JSON.stringify('[data-finding="'+target.id+'"]')+')');
    await wait('document.querySelector("#trace-select")?.value==='+JSON.stringify(target.id),'acceptance evidence graph');
    const allRemarks=report.graph.acceptance_reservation_sources?.lines || [];
    if (modelLines.length) {
      const panel='document.querySelector(".equipment-model-relations")';
      await keepEvidenceOpen(panel);
      await verifyRemarks(panel,modelLines);
      assert.equal(await evaluate(panel+'.querySelectorAll("[data-model-relation]").length'),
        report.graph.edges.filter(e=>e.type==='equipment_model_comparison').length);
    }
    const quantities=report.graph.quality_addenda?.quantities?.lines || [];
    if (equipment?.exchange) {
      const view='document.querySelector(".equipment-exchange-relations")';
      await keepEvidenceOpen(view);
      await wait(view+'.querySelector(".exchange-list")','exchange inventory evidence');
      const links=report.graph.edges.filter(e=>e.type.startsWith('equipment_exchange_'));
      assert.equal(await evaluate(view+'.querySelectorAll("[data-exchange-relation]").length'),links.length);
      const printed=report.graph.equipment_model_sources.exchange.pages.flatMap(p=>p.rows).filter(
        r=>['exchange_old_serials','exchange_new_serials'].includes(r.kind));
      await verifyRemarks(view,printed);
    }
    if (quantities.length) {
      const panel='document.querySelector(".quantity-relations")';
      await evaluate(panel+'.open=true');
      await verifyRemarks(panel,quantities);
    }
    const supplierRows=report.graph.acceptance_reservation_sources?.supplier_rows || [];
    if (supplierRows.length) {
      const panel='document.querySelector(".supplier-relations")';
      await evaluate(panel+'.open=true');
      await verifyRemarks(panel,supplierRows);
    }
    assert.equal(await evaluate('!!document.querySelector(".reservation-relations")'),Boolean(allRemarks.length));
    if (allRemarks.length) {
      const panel='document.querySelector(".reservation-relations")';
      await evaluate(panel+'.open=true');
      await verifyRemarks(panel,allRemarks);
    }
    if (windows.length) {
      const links=report.graph.edges.filter(e=>e.type==='payment_window_comparison');
      assert.equal(await evaluate('!!document.querySelector(".payment-window-relations")'),!!links.length);
      if (links.length) await evaluate('document.querySelector(".payment-window-relations").open=true');
      for (const edge of links) {
        const row='document.querySelector('+JSON.stringify('[data-window-witness="'+edge.from+'>'+edge.to+'"]')+')';
        await wait(row+'?.querySelectorAll("button").length===2','payment term and bank receipt');
        for (const [index,id] of [edge.from,edge.to].entries()) {
          await evaluate(row+'.querySelectorAll("button")['+index+'].click()');
          await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(id),'payment-window graph citation');
          await evaluate('document.querySelector("#page-dialog [data-close]").click()');
        }
      }
    }
    if (warranty) {
      const links=report.graph.edges.filter(e=>e.type==='warranty_release_basis');
      assert.equal(await evaluate('!!document.querySelector(".warranty-relations")'),!!links.length);
      if (links.length) await evaluate('document.querySelector(".warranty-relations").open=true');
      for (const edge of links) {
        const row='document.querySelector('+JSON.stringify('[data-warranty-witness="'+edge.from+'>'+edge.to+'"]')+')';
        await wait(row+'?.querySelectorAll("button").length===2','warranty clause and dated confirmation');
        for (const [index,id] of [edge.from,edge.to].entries()) {
          await evaluate(row+'.querySelectorAll("button")['+index+'].click()');
          await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(id),'warranty graph citation');
          await evaluate('document.querySelector("#page-dialog [data-close]").click()');
        }
      }
    }
    const pageIdentities=report.graph.edges.filter(e=>e.type==='acceptance_page_identity');
    const transferOperands=report.graph.edges.filter(e=>e.type==='stage_transfer_operand');
    assert.equal(await evaluate('!!document.querySelector(".stage-transfer-relations")'),Boolean(transferOperands.length));
    if (transferOperands.length) await evaluate('document.querySelector(".stage-transfer-relations").open=true');
    for (const edge of transferOperands) {
      const row='document.querySelector('+JSON.stringify('[data-stage-transfer="'+edge.to+'"]')+')';
      await wait(row+'?.querySelectorAll("button").length===4','contract and transfer operands');
      for (const [i,ref] of edge.evidence.entries()) {
        await evaluate(row+'.querySelectorAll("button")['+i+'].click()');
        await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(ref),'contract share and counted transfer');
        await evaluate('document.querySelector("#page-dialog [data-close]").click()');
      }
    }
    assert.equal(await evaluate('!!document.querySelector(".packet-relations")'),Boolean(pageIdentities.length));
    if (pageIdentities.length) await evaluate('document.querySelector(".packet-relations").open=true');
    for (const edge of pageIdentities) {
      const row='document.querySelector('+JSON.stringify('[data-packet-witness="'+edge.to+'"]')+')';
      await wait(row+'?.querySelector("button")','acceptance page identity in graph');
      await evaluate(row+'.querySelector("button").click()');
      await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(edge.to),'printed receipt identity');
      await evaluate('document.querySelector("#page-dialog [data-close]").click()');
    }
    if (batches) {
      const edges=report.graph.edges.filter(e=>['delivery_batch_acceptance','batch_payment_basis','batch_named_signature','batch_final_basis','final_named_signature'].includes(e.type));
      assert.equal(await evaluate('!!document.querySelector(".batch-relations")'),!!edges.length);
      if (edges.length) await evaluate('document.querySelector(".batch-relations").open=true');
      for (const edge of edges) {
        const row='document.querySelector('+JSON.stringify('[data-batch-witness="'+edge.from+'>'+edge.to+'"]')+')';
        await wait(row+'?.querySelectorAll("button").length===2','batch and receipt pair');
        for (const [i,id] of [edge.from,edge.to].entries()) {
          await evaluate(row+'.querySelectorAll("button")['+i+'].click()');
          await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(id),'linked batch original');
          await evaluate('document.querySelector("#page-dialog [data-close]").click()');
        }
      }
      const remarkEdges=report.graph.edges.filter(e=>['batch_inspection_note','batch_payment_hold'].includes(e.type));
      assert.equal(await evaluate('Boolean(document.querySelector(".batch-remark-relations"))'),Boolean(remarkEdges.length));
      if (remarkEdges.length) {
        await evaluate('document.querySelector(".batch-remark-relations").open=true');
        await wait('document.querySelectorAll("[data-batch-remark]").length==='+remarkEdges.length,'remark links from each clause');
        for (const [i,edge] of remarkEdges.entries()) {
          const row='document.querySelectorAll("[data-batch-remark]")['+i+']';
          const note=report.graph.delivery_batch_sources.remarks.find(r=>r.doc+'/p'+r.page===edge.to && r.line===edge.line && r.facts.every(id=>edge.evidence.includes(id)));
          await evaluate(row+'.querySelector("button").click()');
          await wait('document.querySelector(".located")?.dataset.fact==='+JSON.stringify(edge.from),'contract clause of restricted payment or batch');
          await evaluate('document.querySelector("#page-dialog [data-close]").click()');
          await verifyRemarks(row,[note]);
        }
      }
    }
    if (authority) {
      const edges=report.graph.edges.filter(e=>e.type==='named_acceptance_signature');
      assert.equal(await evaluate('!!document.querySelector(".signature-relations")'),!!edges.length);
      if (edges.length) await evaluate('document.querySelector(".signature-relations").open=true');
      for (const edge of edges) {
        const row='document.querySelector('+JSON.stringify('[data-signer-witness="'+edge.to+'"]')+')';
        await wait(row+'?.querySelectorAll("button").length===2','source pair on the graph');
        for (const [i,id] of [edge.from,edge.to].entries()) {
          await evaluate(row+'.querySelectorAll("button")['+i+'].click()');
          await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(id),'graph to original');
          await evaluate('document.querySelector("#page-dialog [data-close]").click()');
        }
      }
    }
    console.log('PASS · Contract scope, '+phases.length+' phase decisions, original clauses and evidence path at six widths');
  } else if (claimPairCase) {
    const api=root+'/api/cases/'+claimPairCase;
    const task=await (await fetch(api)).json();
    assert.ok(task.title.startsWith('合成演练 · 八位同号异代码双票'));
    const paper=(await (await fetch(api+'/reports/'+task.rev)).json()).report;
    const pairs=paper.graph.facts.filter(f=>f.origin==='printed_claim_pair');
    assert.equal(pairs.length,2);
    for (const fact of pairs) {
      await call('Page.navigate',{url:root+'/workpaper/'+claimPairCase+'?rev='+task.rev+'&fact='+encodeURIComponent(fact.id)});
      await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.textContent.includes('+JSON.stringify(fact.quote)+')','original claim line');
      assert.ok(await evaluate('document.querySelector(".located").textContent.includes("模型原列为随附票号")'));
      assert.ok(await evaluate('document.querySelector(".located").textContent.includes("文字层第 '+fact.source_line.number+' 行")'));
    }
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:880,deviceScaleFactor:1,mobile:false});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && document.querySelector(".located").scrollWidth<=document.querySelector(".located").clientWidth+1'),'printed pair at '+width);
    }
    console.log('PASS · Printed claim pairs, exact labelled lines, visible model classification and six widths');
  } else if (legacyCase) {
    const api=root+'/api/cases/'+legacyCase;
    const get=async suffix=>(await fetch(api+suffix)).json();
    const task=await get(''),original=await get('/reports/1');
    assert.ok(task.title.startsWith(legacyTransfer?'合成演练 · 流水':'合成演练 · 遮盖票号的费用申请') && task.rev===1 && task.status==='ready');
    const {graph,findings}=original.report;
    if (legacyTransfer) assert.ok(!graph.transfer_references && findings.some(f=>f.rule==='B06' && f.status==='ok'));
    else assert.ok(!graph.number_masks && original.report.result.verdict==='pass');
    const fields=graph.facts.filter(f=>legacyTransfer ? f.field==='transfer_ref' && ['anchored','confirmed'].includes(f.status)
      : ['invoice_id','claim_ref'].includes(f.field) && f.value.includes('****'));
    assert.ok(fields.length>0);
    await call('Page.navigate',{url:root+'/workpaper/'+legacyCase+'?rev=1'});
    await wait('[...document.querySelectorAll("button")].some(b=>b.textContent==="填写验收意见")','legacy review available');
    await click('填写验收意见');
    await evaluate('document.querySelector("#reviewer").value="演练核验员";document.querySelector("#review-decision").value="approve";document.querySelector("#review-note").value="已核对本次演练的旧底稿。";document.querySelector("#review-form").requestSubmit()');
    await wait('document.querySelectorAll("#review-error a").length==='+fields.length,'original masked references');
    const links=await evaluate('[...document.querySelectorAll("#review-error a")].map(a=>a.href)');
    assert.deepEqual(links.map(url=>new URL(url).searchParams.get('fact')).sort(),fields.map(f=>f.id).sort());
    assert.ok(await evaluate('document.querySelector("#review-decision option[value=approve]").disabled && document.querySelector("#review-note").value==="已核对本次演练的旧底稿。"'));
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:860,deviceScaleFactor:1,mobile:false});
      assert.ok(await evaluate('document.querySelector("#review-dialog").scrollWidth<=document.querySelector("#review-dialog").clientWidth+1'),'legacy approval at '+width);
    }
    await click('保留 R1 并重新审计','document.querySelector("#review-error")');
    const next=await until(async()=>{const item=await get('');return item.rev===2 && item.status==='ready' && item;},'reassessed masked case',120000);
    assert.equal(next.decisions.length,0);
    assert.equal((await get('/reports/2')).report.result.verdict,'review');
    assert.equal((await get('/reports/1')).sha256,original.sha256);
    console.log('PASS · Legacy decision withheld, original citations, preserved note, six widths and reviewed R2');
  } else if (brokenPayment) {
    const api=root+'/api/cases/'+brokenPayment;
    const get=async suffix=>(await fetch(api+suffix)).json();
    const task=await get('');
    assert.ok(task.title.startsWith('合成演练 · 同合同另一笔全额付款') && task.status==='ready');
    const {report}=await get('/reports/'+task.rev);
    const prior=report.graph.payment_history.matches.find(m=>m.kind==='full');
    const ref=prior.evidence.find(f=>f.field==='transfer_ref');
    await call('Page.navigate',{url:root+'/workpaper/'+brokenPayment+'?rev='+task.rev});
    await wait('[...document.querySelectorAll("button")].some(b=>b.textContent==="填写验收意见")','initial review');
    await click('填写验收意见');
    await evaluate('document.querySelector("#reviewer").value="回单演练员";document.querySelector("#review-decision").value="approve";document.querySelector("#review-note").value="复核前案成功流水。";document.querySelector("#review-form").requestSubmit()');
    await wait('document.querySelector("#review-error a") && document.querySelector("#review-error").textContent.includes("原件核验失败")','missing original with its pinned reference');
    const link=new URL(await evaluate('document.querySelector("#review-error a").href'));
    assert.equal(link.pathname,'/workpaper/'+prior.case_id);
    assert.equal(link.searchParams.get('rev'),String(prior.rev));
    assert.equal(link.searchParams.get('fact'),ref.fact);
    assert.ok(await evaluate('document.querySelector("#review-dialog").open && document.querySelector("#review-note").value==="复核前案成功流水。"'));
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:860,deviceScaleFactor:1,mobile:false});
      assert.ok(await evaluate('document.querySelector("#review-dialog").scrollWidth<=document.querySelector("#review-dialog").clientWidth+1'),'missing payment source at '+width);
    }
    assert.equal((await get('')).decisions.length,0);
    await call('Page.navigate',{url:link.href});
    await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.textContent.includes('+JSON.stringify(ref.quote)+')','prior preserved page and cited reference');
    console.log('PASS · Unavailable original blocked approval, preserved note and linked pinned receipt at six widths');
  } else if (accountReview) {
    const api=root+'/api/cases/'+accountReview;
    const task=await (await fetch(api)).json();
    assert.ok(task.title.startsWith('合成演练 · '));
    const arg=process.argv.indexOf('--account-revision');
    const rev=arg<0?task.rev:Number(process.argv[arg+1]);
    assert.ok(Number.isInteger(rev) && rev>0 && rev<=task.rev);
    const {report}=await (await fetch(api+'/reports/'+rev)).json();
    const item=report.findings.find(f=>f.rule==='B03');
    const graph=report.graph;
    const fields=item.evidence.map(id=>graph.facts.find(f=>f.id===id)).filter(f=>['contract_account','payee_account'].includes(f?.field));
    assert.equal(fields.length,2);
    const normalized=fields.map(f=>f.value.normalize('NFKC').replace(/\s/gu,''));
    const comparable=normalized.every(v=>/^[0-9]{8,32}$/.test(v));
    await call('Page.navigate',{url:root+'/workpaper/'+accountReview+'?'+new URLSearchParams({rev,finding:item.id})});
    await wait('!!document.querySelector(".account-comparison summary")','account comparison on B03');
    assert.ok(await evaluate('!document.querySelector(".account-image")'));
    await evaluate('const d=document.querySelector(".account-comparison");for(let a=d.parentElement;a;a=a.parentElement){if(a.tagName==="DETAILS")a.open=true;}d.querySelector("summary").click()');
    await wait('document.querySelectorAll(".account-image img,.account-image canvas").length===2','two original receipt previews');
    const marks=[];
    for (const [i,f] of fields.entries()) {
      const sel='.account-observation[data-account-fact="'+f.id+'"]';
      const view=await evaluate('(()=>{const e=document.querySelector('+JSON.stringify(sel)+');return {digits:e.querySelector("code").textContent,quote:e.querySelector("blockquote").textContent,marked:[...e.querySelectorAll("mark")].map(m=>m.textContent).join(""),native:e.querySelector(".account-native")?.textContent || "",crop:!!e.querySelector("canvas"),original:e.querySelector("img")?.naturalWidth || 0};})()');
      assert.equal(view.digits,/^[0-9]{8,32}$/.test(normalized[i])?normalized[i]:f.value);
      assert.equal(view.quote,f.quote);
      const page=graph.nodes.find(n=>n.id===f.doc+'/p'+f.page);
      const crop=page.layer==='text' && !!f.source_line?.rects?.length;
      assert.equal(view.crop,crop);
      if (crop) {
        assert.ok(await evaluate('(()=>{const c=document.querySelector('+JSON.stringify(sel+' canvas')+');return c.width>8 && c.height>3 && c.getContext("2d").getImageData(0,0,c.width,c.height).data.some((v,i)=>i%4===0 && v<150);})()'));
      } else assert.ok(view.original>0);
      const gap=graph.gaps.find(g=>g.field===f.field && g.doc===f.doc && g.page===f.page && g.quality==='uncovered');
      if (gap) {
        assert.ok(view.native.includes(gap.quote));
        const printed=/^[^:0-9]+:([0-9]{8,32})$/.exec(gap.quote.normalize('NFKC').replace(/\s/gu,''));
        if (printed) assert.ok(view.native.includes(printed[1].length+' 位数字'));
      }
      marks.push(view.marked);
      await evaluate('document.querySelector('+JSON.stringify(sel+' button')+').click()');
      await wait('document.querySelector("#page-dialog").open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(f.id)+' && document.querySelector("#page-dialog img")?.naturalWidth','same-version original account observation');
      await evaluate('document.querySelector("#page-dialog [data-close]").click()');
    }
    for (const [i,value] of normalized.entries())
      assert.equal(marks[i],comparable?Array.from(value).filter((digit,k)=>digit!==normalized[1-i][k]).join(''):'');
    const difference=await evaluate('document.querySelector(".account-difference").textContent');
    if (!comparable) {
      assert.ok(difference.includes('核实完整账号') && !difference.includes('逐位相同'));
      const observations=['contract_account','payee_account'].flatMap((field,side)=>['00000001','00000002'].map((value,i)=>({
        field,value,doc:'d0'+(side+1),page:1,id:'d0'+(side+1)+'/p1/f'+(i+1),quote:'演练账号：'+value,status:'visual'
      })));
      for (const facts of [observations,observations.filter(f=>f.field==='payee_account')]) {
        const sample={facts,nodes:[],gaps:[],documents:[],documents_by_kind:{contract:['d01'],bank_receipt:['d02']}};
        const check=await evaluate('(()=>{const g='+JSON.stringify(sample)+';const d=accountComparison({evidence:g.facts.map(f=>f.id)},g);d.open=true;d.dispatchEvent(new Event("toggle"));return {observations:d.querySelectorAll(".account-observation").length,marks:d.querySelectorAll("mark").length,previews:d.querySelectorAll(".account-preview").length,summary:d.querySelector(".account-difference").textContent};})()');
        assert.equal(check.observations,facts.length);
        assert.equal(check.marks,0);
        assert.equal(check.previews,0);
        assert.ok(check.summary.includes('2 条候选引文') && !check.summary.includes('逐位相同'));
        if (facts.length===2) assert.ok(check.summary.includes('缺少引文'));
      }
    }
    else if (normalized[0]===normalized[1]) assert.ok(difference.includes('逐位相同'));
    else {
      let position=0;
      while (normalized[0][position]===normalized[1][position]) position++;
      assert.ok(difference.includes('第 '+(position+1)+' 位'));
    }
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:860,deviceScaleFactor:1,mobile:false});
      const overflow=await evaluate('Array.from(document.querySelectorAll("body *")).filter(e=>{const r=e.getBoundingClientRect();return r.width && (r.right>innerWidth+1 || (e.classList.contains("account-observation") && e.scrollWidth>e.clientWidth+1));}).slice(0,8).map(e=>[e.tagName,e.id,e.className,Math.ceil(e.getBoundingClientRect().right)])');
      assert.deepEqual(overflow,[],'account evidence at '+width+' · '+JSON.stringify(overflow));
    }
    const first=fields[0];
    const blocked=api+'/documents/'+first.doc+'/pages/'+first.page+'?rev='+rev;
    await call('Network.enable');
    await call('Network.setBlockedURLs',{urls:[blocked]});
    await call('Page.navigate',{url:root+'/workpaper/'+accountReview+'?rev='+rev});
    await wait('!!document.querySelector("[data-finding] .account-comparison")','account comparison in the audit findings');
    await evaluate('const d=document.querySelector(".account-comparison");for(let a=d.parentElement;a;a=a.parentElement){if(a.tagName==="DETAILS")a.open=true;}d.querySelector("summary").click()');
    const card='.account-observation[data-account-fact="'+first.id+'"]';
    await wait('document.querySelector('+JSON.stringify(card)+')?.textContent.includes("原页读取失败")','explicit unavailable source');
    assert.equal(await evaluate('document.querySelector('+JSON.stringify(card+' blockquote')+').textContent'),first.quote);
    await call('Network.setBlockedURLs',{urls:[]});
    await evaluate('document.querySelector('+JSON.stringify(card+' button')+').click()');
    await wait('document.querySelector(".located")?.dataset.fact==='+JSON.stringify(first.id)+' && document.querySelector("#page-dialog img")?.naturalWidth','retry original after a failed preview');
    console.log('PASS · Exact digits, source image crops or whole pages, source links and six widths · '+item.status);
  } else if (visibilityCase) {
    const api=root+'/api/cases/'+visibilityCase;
    const get=async suffix=>(await fetch(api+suffix)).json();
    const task=await get('');
    const sample=/^合成演练 · 流水整页核图 · ([0-9A-F]{4,8})$/.exec(task.title);
    assert.ok(sample && ['ready','closed'].includes(task.status));
    const bytes=await readFile(resolve('docs/samples/generated/流水整页核图-'+sample[1]+'/银行回单照片.jpg'));
    const checksum=createHash('sha256').update(bytes).digest('hex');
    let {report}=await get('/reports/'+task.rev);
    const source=report.graph.facts.find(f=>f.field==='transfer_ref' && f.source_sha256===checksum);
    assert.ok(source && source.value==='0042' && source.quote.replace(/[:：\s]/g,'')==='交易流水号0042');
    const original=source.attestation.source_check.reference_visibility;
    const rev=original ? source.attestation.source_check.rev : task.rev;
    const before=await get('/reports/'+rev);
    assert.equal(before.report.graph.transfer_references.facts.find(f=>f.fact===source.id)?.state,'visibility_unchecked');
    assert.equal(before.report.findings.find(f=>f.rule==='B06').status,'missing');
    const page=rev=>root+'/workpaper/'+visibilityCase+'?'+new URLSearchParams({rev,fact:source.id});
    await call('Page.navigate',{url:page(rev)});
    await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth && document.querySelector(".located")?.textContent.includes("待核整页展示范围")','unassessed reference on its source image');
    if (!original) {
      assert.equal(task.status,'ready');
      await wait('[...document.querySelectorAll(".located button:enabled")].some(b=>b.textContent==="记录流水展示范围")','loaded source enables whole-page review');
      await evaluate('[...document.querySelectorAll(".located button")].find(b=>b.textContent==="记录流水展示范围").click()');
      await wait('document.querySelector("#review-dialog").open && !document.querySelector("#review-visibility").hidden','individual reference scope');
      assert.equal(await evaluate('document.querySelector("#review-visibility select").value'),'');
      assert.ok(await evaluate('document.querySelector("#review-visibility a").href.endsWith("?rev='+rev+'")'));
      for (const width of [1440,1024,820,768,390,320]) {
        await call('Emulation.setDeviceMetricsOverride',{width,height:860,deviceScaleFactor:1,mobile:false});
        assert.ok(await evaluate('document.querySelector("#review-dialog").scrollWidth<=document.querySelector("#review-dialog").clientWidth+1'),'whole-page review at '+width);
      }
      await evaluate('document.querySelector("#review-visibility select").value="complete";document.querySelector("#reviewer").value="水印样本校验";document.querySelector("#review-note").value="对照生成的水印原件和整页图片，流水栏完整显示 0042。";document.querySelector("#review-form").requestSubmit()');
      await until(async()=>{const c=await get('');return c.rev===rev+1 && c.status==='ready';},'new version with whole-page evidence',180000);
    }
    ({report}=await get('/reports/'+(rev+1)));
    const checked=report.graph.facts.find(f=>f.id===source.id).attestation.source_check;
    assert.equal(checked.report_hash,before.sha256);
    assert.equal(checked.original_sha256,checksum);
    assert.equal(checked.reference_visibility.opinion,'complete');
    assert.equal((await get('/reports/'+rev)).sha256,before.sha256);
    assert.ok(['ok','risk'].includes(report.findings.find(f=>f.rule==='B06').status));
    await call('Page.navigate',{url:page(rev+1)});
    await wait('document.querySelector(".located")?.textContent.includes("整页核图已确认流水完整显示")','archived whole-page declaration');
    assert.ok(await evaluate('document.querySelector(".located .field-source-check").textContent.includes('+JSON.stringify(before.sha256)+')'));
    console.log('PASS · Checked marked original, explicit full-reference decision, pinned prior revision and resumed comparison');
  } else if (partialTransfer) {
    const api=root+'/api/cases/'+partialTransfer;
    const task=await (await fetch(api)).json();
    assert.ok(task.title.startsWith('合成演练 · 流水'));
    const {report}=await (await fetch(api+'/reports/'+task.rev)).json();
    const [field]=report.graph.transfer_references.facts;
    const source=report.graph.facts.find(f=>f.id===field.fact);
    await call('Page.navigate',{url:root+'/workpaper/'+partialTransfer+'?'+new URLSearchParams({rev:task.rev,fact:field.fact})});
    const pending=field.state==='pending_note';
    await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth && document.querySelector(".located")?.textContent.includes('+JSON.stringify(pending?'流水展示说明待核图':'流水号待补全')+')','visible partial reference on its original page');
    const shown=await evaluate('document.querySelector(".located").textContent');
    assert.ok(shown.includes(source.quote));
    for (const line of field.lines) assert.ok(shown.includes(line.text));
    if (field.notes?.length) {
      const [note]=field.notes;
      assert.ok(shown.includes(note.quote));
      await evaluate('[...document.querySelectorAll(".located button")].find(b=>b.textContent==="定位同页展示说明").click()');
      assert.equal(await evaluate('document.activeElement.dataset.fact'),note.fact);
      assert.ok(await evaluate('document.querySelector(".located").textContent.includes('+JSON.stringify(note.quote)+')'));
      for (const width of [1440,1024,820,768,390,320]) {
        await call('Emulation.setDeviceMetricsOverride',{width,height:860,deviceScaleFactor:1,mobile:false});
        assert.ok(await evaluate('document.querySelector("#page-dialog").scrollWidth<=document.querySelector("#page-dialog").clientWidth+1'),'photo reference dialog at '+width);
      }
    }
    await call('Page.navigate',{url:root+'/workpaper/'+partialTransfer+'?rev='+task.rev});
    for (const rule of ['B05','B06','B08']) {
      const finding=report.findings.find(f=>f.rule===rule);
      assert.equal(finding.status,'missing');
      assert.ok(finding.evidence.includes(field.fact));
      for (const note of field.notes || []) assert.ok(finding.evidence.includes(note.fact));
      await wait('document.querySelector('+JSON.stringify('[data-finding="'+finding.id+'"]')+')?.textContent.includes('+JSON.stringify(finding.detail)+')',rule+' visible review finding');
    }
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:860,deviceScaleFactor:1,mobile:false});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'partial receipt at '+width);
    }
    console.log('PASS · Original receipt, printed qualification, withheld payment controls and six widths');
  } else if (maskedInvoice) {
    const api=root+'/api/cases/'+maskedInvoice;
    const task=await (await fetch(api)).json();
    assert.ok(task.title.startsWith('合成演练 · 遮盖票号'));
    const {report}=await (await fetch(api+'/reports/'+task.rev)).json();
    const masks=report.graph.number_masks.facts;
    assert.ok(masks.some(f=>f.field==='invoice_id') && masks.some(f=>f.field==='claim_ref'));
    for (const field of masks) {
      await call('Page.navigate',{url:root+'/workpaper/'+maskedInvoice+'?rev='+task.rev+'&fact='+encodeURIComponent(field.fact)});
      await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth && document.querySelector(".located")?.textContent.includes("原文含遮盖位")','incomplete invoice on its original page');
      assert.ok(await evaluate('document.querySelector(".located").textContent.includes('+JSON.stringify(field.value)+')'));
    }
    await call('Page.navigate',{url:root+'/workpaper/'+maskedInvoice+'?rev='+task.rev});
    const selectRule=rule=>'[data-finding="'+report.findings.find(f=>f.rule===rule).id+'"]';
    await wait('document.querySelector('+JSON.stringify(selectRule('I02'))+')?.textContent.includes("无法用这些引文")','withheld cross-case search');
    assert.ok(await evaluate('document.querySelector('+JSON.stringify(selectRule('T02'))+').textContent.includes("暂缓关联")'));
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:860,deviceScaleFactor:1,mobile:false});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'incomplete invoice at '+width);
    }
    console.log('PASS · Withheld invoice identity, original marked fields and six widths');
  } else if (invoiceCodeHistory) {
    const api=root+'/api/cases/'+invoiceCodeHistory;
    const task=await (await fetch(api)).json();
    assert.ok(task.title.startsWith('合成演练 · 跨案同号异代码'));
    const {report,invoice_approval:approval}=await (await fetch(api+'/reports/'+task.rev)).json();
    const finding=report.findings.find(f=>f.rule==='I02');
    const parent=approval ? '.invoice-approval' : '[data-finding="'+finding.id+'"]';
    const candidates=approval ? approval.screened : report.graph.prior_invoices;
    assert.ok(candidates.some(c=>c.comparison==='different'));
    await call('Page.navigate',{url:root+'/workpaper/'+invoiceCodeHistory+'?rev='+task.rev});
    await wait('!!document.querySelector('+JSON.stringify(parent)+')','signed receipt or I02 finding');
    if (approval) await evaluate('document.querySelector(".invoice-approval > summary").click()');
    const foldTitle=approval?'查看签收时的同号候选':'核对前案签收依据';
    await evaluate('[...document.querySelector('+JSON.stringify(parent)+').querySelectorAll("summary")].find(s=>s.textContent.startsWith('+JSON.stringify(foldTitle)+')).click()');
    const cards=JSON.stringify(parent+' .invoice-source');
    await wait('document.querySelectorAll('+cards+').length==='+candidates.length,'all same-number candidates');
    const urls=[];
    for (const [i,row] of candidates.entries()) {
      const card='document.querySelectorAll('+cards+')['+i+']';
      const contents=await evaluate(card+'.innerText');
      const code=row.code_evidence[0];
      assert.ok(contents.includes(row.quote) && contents.includes(code.quote) && contents.includes('第 '+code.line+' 行'));
      assert.ok(contents.includes({same:'完整标识相同',different:'同号异代码，已排除'}[row.comparison]));
      const href=await evaluate('[...'+card+'.querySelectorAll("a")].find(a=>a.textContent==="查看代码原文").href');
      assert.equal(new URL(href).searchParams.get('fact'),code.fact);
      assert.equal(new URL(href).searchParams.get('rev'),String(row.rev));
      assert.equal(new URL(href).pathname.split('/').at(-1),row.case_id);
      urls.push([href,code.quote]);
    }
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:860,deviceScaleFactor:1,mobile:false});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && [...document.querySelectorAll('+cards+')].every(e=>e.scrollWidth<=e.clientWidth+1)'),'signed codes at '+width);
    }
    for (const [url,quote] of urls) {
      await call('Page.navigate',{url});
      await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth && document.querySelector(".located")?.textContent.includes('+JSON.stringify(quote)+')','prior signed code at the exact page and row');
    }
    console.log('PASS · Signed code comparisons, historical code links and six widths');
  } else if (invoiceConflict) {
    const path=root+'/api/cases/'+invoiceConflict;
    const get=async suffix=>(await fetch(path+suffix)).json();
    const task=await get('');
    assert.ok(task.title.startsWith('合成演练 · 同票签收乙 · ') && task.status==='ready' && task.rev===1);
    const list=await (await fetch(root+'/api/cases')).json();
    const peer=list.cases.find(c=>c.title===task.title.replace('同票签收乙','同票签收甲'));
    assert.ok(peer && peer.status==='closed' && peer.rev===1);
    const signed=await (await fetch(root+'/api/cases/'+peer.id)).json();
    assert.equal(signed.decisions[0].decision,'approve');
    assert.deepEqual(signed.documents.map(d=>d.sha256).sort(),task.documents.map(d=>d.sha256).sort());
    const saved=await get('/reports/1');
    await call('Page.navigate',{url:root+'/workpaper/'+invoiceConflict+'?rev=1'});
    await wait('!![...document.querySelectorAll("button")].find(b=>b.textContent==="填写验收意见")','workpaper ready for signoff');
    await click('填写验收意见');
    await evaluate('document.querySelector("#reviewer").value="网页演练审计员";document.querySelector("#review-note").value="复核同票签收保护。";document.querySelector("#review-decision").value="approve";document.querySelector("#review-form").requestSubmit()');
    const jump=await wait('document.querySelector("#review-error .invoice-changes a")?.href','newly signed invoice citation');
    assert.ok(await evaluate('document.querySelector("#review-dialog").open && document.querySelector("#review-note").value==="复核同票签收保护。"'));
    assert.ok(await evaluate('document.querySelector("#review-decision option[value=approve]").disabled && !document.querySelector("#review-decision option[value=return]").disabled'));
    const link=new URL(jump),prior=link.pathname.split('/').at(-1);
    assert.equal(prior,peer.id);
    const original=await (await fetch(root+'/api/cases/'+prior+'/reports/'+link.searchParams.get('rev'))).json();
    const fact=original.report.graph.facts.find(f=>f.id===link.searchParams.get('fact'));
    assert.equal(fact.field,'invoice_id');
    assert.ok(await evaluate('document.querySelector("#review-error").textContent.includes('+JSON.stringify(fact.quote)+')'));
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
      assert.ok(await evaluate('document.querySelector("#review-dialog").scrollWidth<=document.querySelector("#review-dialog").clientWidth+1'),'signoff change at '+width);
    }
    assert.deepEqual((await get('')).decisions,[]);
    if (process.argv.includes('--live')) {
      await click('保留 R1 并重新审计','document.querySelector("#review-error")');
      await wait('document.querySelector("#version").value==="2" && document.querySelector("#case-status").textContent==="待验收"','recalculated I02',240000);
      const next=await get('/reports/2');
      assert.ok(next.report.findings.some(f=>f.rule==='I02' && f.status==='risk'));
      assert.equal(next.report.graph.prior_invoices[0].case_id,prior);
      assert.equal((await get('/reports/1')).sha256,saved.sha256);
      assert.deepEqual((await get('')).decisions,[]);
    }
    await call('Page.navigate',{url:jump});
    await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth && document.querySelector(".located")?.textContent.includes('+JSON.stringify(fact.quote)+')','signed invoice on its original page');
    console.log('PASS · Stale invoice approval, preserved draft note, six widths, exact original'+(process.argv.includes('--live')?' and manually initiated rerun':''));
  } else if (invoiceSource) {
    const base=root+'/api/cases/'+invoiceSource;
    const task=await (await fetch(base)).json();
    assert.ok(task.title.startsWith('合成演练 · '));
    const {report}=await (await fetch(base+'/reports/'+task.rev)).json();
    const finding=report.findings.find(f=>f.rule==='I02' && f.status==='risk');
    const prior=report.graph.prior_invoices.find(m=>finding.evidence.includes(m.id) && m.source?.basis==='native_line');
    assert.ok(prior);
    await call('Page.navigate',{url:root+'/workpaper/'+invoiceSource+'?rev='+task.rev+'&finding='+finding.id});
    await wait('document.querySelector("#trace-select")?.value==='+JSON.stringify(finding.id),'pinned I02 evidence path');
    await evaluate('[...document.querySelectorAll(".trace-sources summary")].find(s=>s.textContent.startsWith('+JSON.stringify(prior.title)+')).click()');
    await wait('document.querySelector(".trace-sources .invoice-source")?.textContent.includes('+JSON.stringify(prior.quote)+')','historical field in the evidence path');
    await click('审计结论');
    const selector='[data-finding="'+finding.id+'"]';
    await wait('!!document.querySelector('+JSON.stringify(selector)+')','I02 finding');
    await evaluate('[...document.querySelector('+JSON.stringify(selector)+').querySelectorAll("summary")].find(s=>s.textContent.startsWith("核对前案签收依据")).click()');
    const sel=JSON.stringify(selector+' .invoice-source');
    await wait('document.querySelector('+sel+')?.textContent.includes('+JSON.stringify(prior.quote)+')','signed original invoice citation');
    assert.ok(await evaluate('document.querySelector('+sel+').textContent.includes("第 '+prior.source.line+' 行")'));
    await evaluate('document.querySelector('+sel+').querySelector("summary").click()');
    await wait('document.querySelector('+sel+').textContent.includes('+JSON.stringify(prior.signoff_hash)+')','signed opinion digest');
    const urls=await evaluate('[...document.querySelector('+sel+').querySelectorAll("a")].map(a=>a.href)');
    assert.equal(new URL(urls[0]).searchParams.get('fact'),prior.fact);
    assert.equal(new URL(urls[0]).searchParams.get('rev'),String(prior.rev));
    assert.equal(new URL(urls[1]).pathname,'/api/cases/'+prior.case_id+'/documents/'+prior.doc+'/original');
    assert.equal(new URL(urls[1]).searchParams.get('rev'),String(prior.rev));
    const original=await fetch(urls[1]);
    assert.equal(original.status,200);
    assert.equal(createHash('sha256').update(Buffer.from(await original.arrayBuffer())).digest('hex'),prior.source_hash);
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:880,deviceScaleFactor:1,mobile:false});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && document.querySelector('+sel+').scrollWidth<=document.querySelector('+sel+').clientWidth+1'),'invoice proof at '+width);
      if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
        await evaluate('document.querySelector('+sel+').scrollIntoView({block:"center"})');
        const capture=await call('Page.captureScreenshot',{format:'png'});
        await writeFile(join(process.env.AUDIT_UI_SHOTS,'invoice-source-'+width+'.png'),Buffer.from(capture.data,'base64'));
      }
    }
    await call('Page.navigate',{url:urls[0]});
    await wait('document.querySelector("#page-dialog").open && document.querySelector("#page-dialog img")?.naturalWidth && document.querySelector(".located")?.textContent.includes('+JSON.stringify(prior.quote)+')','signed native invoice opened at its original quote');
    console.log('PASS · I02 signed source, original bytes, exact line, both revisions and six responsive widths');
  } else if (invoiceApproval) {
    const base=root+'/api/cases/'+invoiceApproval;
    const get=async suffix=>(await fetch(base+suffix)).json();
    const task=await get('');
    assert.ok(task.title.startsWith('合成演练 · '));
    await call('Page.navigate',{url:root+'/workpaper/'+invoiceApproval});
    if (process.argv.includes('--live') && task.title.startsWith('合成演练 · 单笔差旅签收 · ')) {
      assert.ok(task.status==='ready' && task.rev===1);
      const {report}=await get('/reports/1');
      assert.equal(report.result.verdict,'pass');
      assert.equal(report.graph.prior_invoices.length,0);
      const code=task.title.split(' · ').at(-1);
      assert.ok(report.graph.facts.some(f=>f.field==='invoice_id' && f.status==='anchored' && f.value==='YL-LV-'+code));
      await wait('[...document.querySelectorAll("button")].some(b=>b.textContent==="填写验收意见")','single claim pending signature');
      await click('填写验收意见');
      await evaluate('document.querySelector("#reviewer").value="演练初审陆平";document.querySelector("#review-decision").value="approve";document.querySelector("#review-note").value="已对照水印住宿发票和差旅报销单，金额均为 636 元。";document.querySelector("#review-form").requestSubmit()');
    } else if (process.argv.includes('--live')) {
      assert.ok(task.title.startsWith('合成演练 · 补齐差旅报销单 · ') && task.status==='in_review' && task.rev===1);
      const {report}=await get('/reports/1');
      const prior=report.graph.prior_invoices;
      assert.equal(prior.length,1);
      assert.equal(prior[0].case_id,task.supplement_of.id);
      assert.equal(prior[0].decision,'return');
      const parent=await (await fetch(root+'/api/cases/'+prior[0].case_id)).json();
      assert.ok(parent.title.startsWith('合成演练 · 差旅缺报销单 · ') && parent.decisions.at(-1).decision==='return');
      assert.ok(task.documents.some(d=>d.sha256===parent.documents[0].sha256));
      const finding=report.findings.find(f=>f.rule==='I02' && f.status==='risk');
      assert.ok(report.findings.some(f=>f.rule==='T03' && f.status==='ok'));
      await wait('[...document.querySelectorAll("button")].some(b=>b.textContent==="填写复核意见")','corrected claim pending peer signature');
      await click('填写复核意见');
      await evaluate('document.querySelector("#peer-reviewer").value="演练复核沈禾";document.querySelector("#peer-decision").value="approve";document.querySelector("#peer-note").value="已核前案退回、沿用的水印发票和补交的 636 元差旅报销单，本次演练只签收一次。";[...document.querySelectorAll("#peer-findings input")].find(i=>i.value==='+JSON.stringify(finding.id)+').checked=true;document.querySelector("#peer-form").requestSubmit()');
    }
    await wait('!!document.querySelector(".invoice-approval")','invoice receipt on signed workpaper');
    const current=await get('');
    const saved=await get('/reports/'+current.rev);
    const record=saved.invoice_approval;
    assert.ok(record);
    await evaluate('document.querySelector(".invoice-approval > summary").click()');
    const body=await evaluate('document.querySelector(".invoice-approval").innerText');
    assert.ok(body.includes('R'+record.source_rev) && body.includes('R'+record.signed_rev));
    for (const entry of record.numbers) assert.ok(body.includes(entry.value));
    assert.ok(body.includes({matched:'命中 ',no_match:'未命中已签收任务',no_usable_number:'缺少可查的已核票号',
      incomplete_number:'无法完整查重',insufficient_identity:'同页代码待核',possible_match:'需核对代码或单据归属'}[record.outcome]));
    await evaluate('document.querySelector(".invoice-approval details summary").click()');
    const pin=current.decisions.find(d=>d.rev===current.rev).invoice_check_hash;
    await wait('document.querySelector(".invoice-approval").textContent.includes('+JSON.stringify(pin)+')','approval check digest');
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:860,deviceScaleFactor:1,mobile:false});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'approval receipt at '+width);
      if (process.env.AUDIT_UI_SHOTS && [1440,390].includes(width)) {
        await evaluate('document.querySelector(".invoice-approval").scrollIntoView({block:"center"})');
        const capture=await call('Page.captureScreenshot',{format:'png'});
        await writeFile(join(process.env.AUDIT_UI_SHOTS,'invoice-approval-'+width+'.png'),Buffer.from(capture.data,'base64'));
      }
    }
    if (record.matches.length) {
      const href=await evaluate('document.querySelector(".invoice-approval > a").href');
      assert.equal(new URL(href).pathname,'/workpaper/'+record.matches[0].case_id);
      assert.equal(new URL(href).searchParams.get('fact'),record.matches[0].fact);
      await call('Page.navigate',{url:href});
      await wait('document.querySelector("#page-dialog").open && !!document.querySelector(".located")','pinned historical invoice from signoff');
    }
    console.log('PASS · Human approval, original search scope, pinned invoice evidence and six viewport widths');
  } else if (waitingCase) {
    const path=root+'/api/cases/'+waitingCase;
    const task=await (await fetch(path)).json();
    assert.equal(task.title,'合成演练 · 写锁释放后继续');
    await call('Page.navigate',{url:root+'/workpaper/'+waitingCase});
    await wait('document.querySelector("#progress-panel").textContent.includes("后台任务正在等待数据库写入")','worker waiting for a database writer',30000);
    for (const width of [1440,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:820,deviceScaleFactor:1,mobile:false});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'database wait at '+width);
    }
    await writeFile(process.env.SYNTHETIC_WRITER_OBSERVED,'visible');
    await wait('document.querySelector("#version").value==="1" && document.querySelector("#case-status").textContent==="待验收"','same job completed after the writer released',30000);
    assert.ok(await evaluate('!document.querySelector("#progress-panel").textContent.includes("等待数据库写入")'));
    console.log('PASS · Desktop and mobile showed the storage wait and resumed at the first completed workpaper');
  } else if (recoveringCase) {
    const workspace=process.env.SYNTHETIC_RECOVERY_WORKSPACE;
    assert.match(workspace || '',/^[0-9a-f]{32}$/);
    const cookie=await call('Network.setCookie',{name:'fish_session',value:process.env.SYNTHETIC_RECOVERY_SESSION,
      url:root,httpOnly:true,sameSite:'Lax'});
    assert.ok(cookie.success);
    await call('Page.navigate',{url:root+'/w/'+workspace+'/workpaper/'+recoveringCase});
    await wait('document.querySelector("#checkpoint-totals")?.textContent.includes("R1 专家响应已保存")','persisted expert checkpoint');
    assert.ok(await evaluate('document.querySelector("#progress-panel progress").value===96 && document.querySelector("#report-tools").hidden'));
    await evaluate('document.querySelector("#checkpoint-files details").open=true');
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && !!document.querySelector("#checkpoint-files a")'),'saved expert response at '+width);
    }
    await call('Page.reload');
    await wait('document.querySelector("#checkpoint-totals")?.textContent.includes("R1 专家响应已保存")','checkpoint after reload');
    console.log('PASS · persisted expert checkpoint before publication, reload and six widths');
  } else if (replayCase) {
    const base=root+'/api/cases/'+replayCase;
    const original=await (await fetch(base)).json();
    assert.ok(original.title.startsWith('合成演练 · '));
    const index=process.argv.indexOf('--revision');
    const rev=index<0 ? original.rev : Number(process.argv[index+1]);
    assert.ok(Number.isSafeInteger(rev) && rev>0);
    const saved=await (await fetch(base+'/reports/'+rev)).json();
    const expected=process.argv.includes('--expect-unavailable') ? 'unavailable' : 'verified';
    await call('Page.navigate',{url:root+'/workpaper/'+replayCase+'?rev='+rev+'&view=replay'});
    await wait('document.querySelector("#case-title")?.textContent==='+JSON.stringify(original.title),'pinned replay case');
    await wait('document.querySelector(".rule-replay button")===document.activeElement','pinned replay action');
    await click('复算本版规则','document.querySelector(".rule-replay")');
    await wait('document.querySelector(".rule-replay .replay-status")?.textContent.includes('+JSON.stringify(expected==='verified'?'复算一致':'无法复算')+')','pinned rule replay',60000);
    await evaluate('document.querySelector(".rule-replay details").open=true');
    const result=await evaluate('document.querySelector(".rule-replay").textContent');
    assert.ok(result.includes(saved.sha256));
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'replay receipt at '+width);
    }
    await call('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:scratch});
    await click('下载复算记录','document.querySelector(".rule-replay")');
    const filename=join(scratch,'复算记录-'+replayCase+'-R'+rev+'.json');
    const receipt=await until(async()=>JSON.parse(await readFile(filename,'utf8')),'downloaded JSON receipt');
    assert.deepEqual([receipt.state,receipt.report_sha256,receipt.rev,receipt.case_id],[expected,saved.sha256,rev,replayCase]);
    if (expected==='verified') {
      assert.ok(result.includes(receipt.findings_sha256) && result.includes(receipt.result_sha256));
      const zip=join(scratch,'workpaper.zip');
      await writeFile(zip,Buffer.from(await (await fetch(base+'/reports/'+rev+'/bundle')).arrayBuffer()));
      const proof=execFileSync(process.env.AUDIT_PYTHON || 'server/.venv/bin/python',['server/verify.py',zip,'--replay-receipt',filename],{encoding:'utf8'});
      assert.ok(proof.includes(receipt.commit) && proof.includes('校验成功'));
      assert.equal(receipt.finding_count,saved.report.findings.length);
    } else assert.ok(!receipt.commit && receipt.message);
    const after=await (await fetch(base)).json();
    for (const key of ['decisions','revisions','events','status']) assert.deepEqual(after[key],original[key]);
    console.log('PASS · '+expected+' rule replay, downloaded version receipt and six widths');
  } else if (installmentCase) {
    const base = root+'/api/cases/'+installmentCase;
    const detail = await (await fetch(base)).json();
    assert.ok(detail.title.startsWith('合成演练 · '));
    const {report} = await (await fetch(base+'/reports/'+detail.rev)).json();
    const f = report.findings.find(f=>f.rule==='B08');
    const window = report.graph.payment_history.installments;
    const calc = window.calculation;
    assert.equal(calc.state,'calculated');
    const url = root+'/workpaper/'+installmentCase+'?'+new URLSearchParams({rev:detail.rev,finding:f.id});
    await call('Page.navigate',{url});
    const article = 'document.querySelector(".trace-grid")';
    await wait('document.querySelector("#trace-select")?.value==='+JSON.stringify(f.id),'cumulative finding');
    await evaluate('[...'+article+'.querySelectorAll("summary")].find(s=>s.textContent==="逐笔复算分期付款").click()');
    await wait(article+'.querySelector(".installment-ledger")','receipt ledger');
    const ledger = article+'.querySelector(".installment-ledger")';
    assert.equal(await evaluate(ledger+'.querySelectorAll(".installment-row").length'),calc.payments.length);
    const shown=(await evaluate(ledger+'.textContent')).replaceAll(',','');
    for (const amount of [calc.paid_total,calc.contract_total,calc.difference]) assert.ok(shown.includes(amount+' 元'));
    for (const p of calc.payments) assert.ok((await evaluate(ledger+'.textContent')).includes(p.reference));
    await evaluate(ledger+'.querySelectorAll(".installment-row details").forEach(d=>d.open=true)');
    await wait(ledger+'.querySelector(".installment-row a")','prior receipt amount link, including duplicate copy');
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && '+ledger+'.scrollWidth<='+ledger+'.clientWidth+1'),'installment ledger at '+width);
    }
    const historic=await evaluate(ledger+'.querySelector(".installment-row a").href');
    const target=new URL(historic);
    const source=window.matches.find(m=>target.pathname.endsWith('/'+m.case_id));
    assert.equal(target.searchParams.get('rev'),String(source.rev));
    assert.ok(source.evidence.some(e=>e.fact===target.searchParams.get('fact') && e.field==='transfer_amount'));
    await click('审计结论');
    await wait('[...document.querySelectorAll("[data-finding]")].some(row=>row.dataset.finding==='+JSON.stringify(f.id)+' && row.textContent.includes("逐笔复算分期付款"))','ledger available in audit conclusions');
    await call('Page.navigate',{url:historic});
    await wait('document.querySelector("#page-dialog")?.open && document.querySelector(".located")?.dataset.fact==='+JSON.stringify(target.searchParams.get('fact')),'archived receipt amount on pinned original');
    console.log('PASS · Installment totals, unique receipts, historical amount on its original page and six widths');
  } else if (fieldCase) {
    const base = root+'/api/cases/'+fieldCase;
    const current = await (await fetch(base)).json();
    assert.ok(current.title.startsWith('合成演练 · '));
    const bundle = await (await fetch(base+'/reports/'+current.rev)).json();
    const field = bundle.report.graph.facts.find(f=>f.attestation?.source_check);
    assert.ok(field);
    const receipt = field.attestation.source_check;
    const params = new URLSearchParams({rev:String(current.rev),fact:field.id});
    await call('Page.navigate',{url:root+'/workpaper/'+fieldCase+'?'+params});
    await wait('document.querySelector("#page-dialog")?.open && !!document.querySelector(".located .field-source-check")','checked field on its original page');
    await evaluate('document.querySelector(".located .field-source-check").open=true');
    const visible = await evaluate('document.querySelector(".located .field-source-check").textContent');
    for (const hash of [receipt.report_hash,receipt.original_sha256,receipt.page_sha256]) assert.ok(visible.includes(hash));
    const links = await evaluate('[...document.querySelectorAll(".located .field-source-check a")].map(link=>link.href)');
    const [pageUrl,paperUrl,originalUrl] = links.map(url=>new URL(url));
    for (const url of [pageUrl,paperUrl,originalUrl]) assert.equal(url.searchParams.get('rev'),String(receipt.rev));
    assert.equal(paperUrl.pathname,'/workpaper/'+fieldCase);
    assert.equal(paperUrl.searchParams.get('fact'),receipt.operation==='add' ? null : field.id);
    for (const [url,expected] of [[pageUrl,receipt.page_sha256],[originalUrl,receipt.original_sha256]]) {
      const file = await fetch(url);
      assert.equal(file.status,200);
      assert.equal(createHash('sha256').update(Buffer.from(await file.arrayBuffer())).digest('hex'),expected);
    }
    const prior = await (await fetch(base+'/reports/'+receipt.rev)).json();
    assert.equal(prior.sha256,receipt.report_hash);
    for (const width of [1440,1024,820,768,390,320]) {
      await call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<600});
      assert.ok(await evaluate('document.querySelector("#page-dialog").scrollWidth<=document.querySelector("#page-dialog").clientWidth+1'),'field receipt at '+width);
    }
    console.log('PASS · Signed field, pinned workpaper, original and page hashes across six widths');
  } else if (peerCase) {
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
      const activePath = await evaluate('Team.cases()+"/"+state.detail.id');
      await evaluate('document.querySelector("#nav-desk").click()');
      await wait('!document.querySelector("#desk").hidden && !!document.querySelector("[data-preview-case]")','active task queue');
      await evaluate('performance.clearResourceTimings();document.querySelector("[data-preview-case]").click()');
      await wait('document.querySelector("#case-preview").open && !!document.querySelector("#preview-body progress")','active job in preview');
      await wait('performance.getEntriesByType("resource").filter(r=>new URL(r.name).pathname==='+JSON.stringify(activePath)+').length>=2','automatic progress refresh');
      await evaluate('document.querySelector(".preview-open").click()');
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
      await evaluate('document.querySelector("#quick-open").click()');
      await wait('document.querySelector("#quick-dialog").open','employee commands');
      const employeeCommands=await evaluate('document.querySelector("#quick-results").innerText');
      assert.ok(employeeCommands.includes('逐份资料进度'));
      assert.ok(!/本版原件|待核发现|知识图谱|证据检索|企业成员/.test(employeeCommands));
      await evaluate('document.querySelector("#quick-close").click()');
      const detail = await evaluate('location.hash');
      await evaluate('document.querySelector("#nav-desk").click()');
      await wait('!document.querySelector("#desk").hidden && !!document.querySelector("[data-preview-case]")','employee task queue');
      await evaluate('performance.clearResourceTimings();document.querySelector("[data-preview-case]").click()');
      await wait('document.querySelector("#case-preview").open && !!document.querySelector(".preview-open")','employee task preview');
      assert.equal(await evaluate('document.querySelector(".preview-open").textContent'),'打开任务');
      assert.ok(await evaluate('!document.querySelector(".preview-finding") && !performance.getEntriesByType("resource").some(r=>new URL(r.name).pathname.includes("/reports/"))'));
      await evaluate('document.querySelector("#case-preview [data-close]").click()');
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
      const printedTerm = row => row.doc==='d01' && row.page===1 && row.field==='payment_term' &&
        row.quote?.endsWith('验收后一次性全额结算');
      const term = report.report.graph.facts.find(printedTerm);
      const termVerified = term && ['anchored','confirmed'].includes(term.status);
      assert.equal(report.report.result.verdict,'review','the packet has no contract signatures or signed final acceptance');
      console.log(JSON.stringify({gaps:report.report.graph.gaps, pending:report.report.graph.facts.filter(f=>!['anchored','confirmed'].includes(f.status)).map(f=>[f.page,f.field,f.status]), rules:report.report.findings.filter(f=>f.status!=='ok').map(f=>[f.rule,f.detail])}));
      assert.ok(term || report.report.graph.gaps.some(printedTerm),'the printed payment term is cited or marked as an extraction gap');
      const status = rule => report.report.findings.find(f=>f.rule===rule)?.status;
      assert.equal(status('M02'),termVerified?'ok':'missing','the amount comparison depends on the verified full-settlement term');
      assert.ok(['missing','risk'].includes(status('H01')),'the unsigned contract has outstanding effectiveness evidence');
      assert.ok(['missing','risk'].includes(status('H02')),'the delivery form lacks signed evidence of final acceptance');
      assert.equal(status('H04'),'missing','payment still needs the contract and final acceptance');
      const calcCount = report.report.findings.flatMap(f=>f.calculations || []).length;
      assert.ok(calcCount >= (termVerified ? 3 : 1), 'operand-linked audit');
      await evaluate('const detailEl = document.querySelector("#case-panel .formula .ref"); for (let a=detailEl.parentElement; a; a=a.parentElement) if(a.tagName==="DETAILS") a.open=true; detailEl.click()');
      await wait('document.querySelector("#page-dialog").open && !!document.querySelector(".evidence-row.located")','operand citation');
      const sourceUrl = await wait('document.querySelector("#page-dialog img")?.naturalWidth && document.querySelector("#page-dialog .source-tools > a").href','verified source image loaded');
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
      if (process.argv.includes('--confirm-source')) {
        const bill = report.report.graph.facts.find(f=>f.field==='invoice_id' && f.value==='YL-FP-071');
        assert.ok(bill?.doc==='d01' && bill.page===2);
        await evaluate('location.hash='+JSON.stringify(detail+'?rev=1&fact='+encodeURIComponent(bill.id)));
        await wait('document.querySelector("#page-dialog")?.open && !!document.querySelector(".located input:enabled")','invoice to confirm');
        await evaluate('document.querySelector(".located input").click()');
        await click('记录所选引文的核图意见','document.querySelector("#page-dialog")');
        await evaluate('document.querySelector("#review-decision").value="confirm";document.querySelector("#review-note").value="合成演练，已核对第二页所列发票号码。";');
        const originalFile = join(scratch,'data','cases',path[3],'d01','original.pdf');
        const bytes = await readFile(originalFile);
        assert.equal(createHash('sha256').update(bytes).digest('hex'),bill.source_sha256);
        try {
          await writeFile(originalFile,Buffer.from('changed synthetic upload after opening the page'));
          await evaluate('document.querySelector("#review-form").requestSubmit()');
          await wait('document.querySelector("#review-error").textContent.includes("摘要不符") && !document.querySelector("#submit-review").disabled','confirmation refused after original changed');
        } finally { await writeFile(originalFile,bytes); }
        await evaluate('document.querySelector("#review-form").requestSubmit()');
        revision++;
        await wait('document.querySelector("#version").value==="2" && document.querySelector("#case-status").textContent==="待验收"','confirmed report rebuilt',240000);
        await evaluate('location.hash='+JSON.stringify(detail+'?rev=2&fact='+encodeURIComponent(bill.id)));
        await wait('document.querySelector("#page-dialog").open && !!document.querySelector(".located .field-source-check")','field source receipt in the workpaper');
        const certificate = await evaluate('(()=>{const d=document.querySelector(".located .field-source-check");d.open=true;return [d.textContent,d.querySelector("a").href]})()');
        for (const sha of [bill.source_sha256,bill.page_sha256,report.sha256]) assert.ok(certificate[0].includes(sha));
        assert.equal(new URL(certificate[1]).searchParams.get('rev'),'1');
        await evaluate('document.querySelector("#page-dialog").close()');
        console.log('PASS · Refused a changed original after preview; restored source, confirmed bill number and pinned its three hashes');
      }
      const disputeTerm = process.argv.includes('--dispute') && termVerified;
      if (disputeTerm) {
        await evaluate('location.hash='+JSON.stringify(detail+'?rev='+revision+'&fact='+encodeURIComponent(term.id)));
        await wait('document.querySelector("#page-dialog")?.open && !!document.querySelector(".located input:enabled")','printed payment term');
        await evaluate('document.querySelector(".located input").click()');
        await click('记录所选引文的核图意见','document.querySelector("#page-dialog")');
        await evaluate('document.querySelector("#review-decision").value="dispute";document.querySelector("#review-note").value="合成演练，审计员对该合同结算条款的取值提出异议。";document.querySelector("#review-form").requestSubmit()');
        revision++;
        await wait('document.querySelector("#version").value==='+JSON.stringify(String(revision))+' && document.querySelector("#case-status").textContent==="待验收"','recalculated workpaper after dispute',240000);
        const revised = await evaluate('fetch("/api/w/'+path[1]+'/cases/'+path[3]+'/reports/'+revision+'").then(r=>r.json()).then(b=>b.report)');
        assert.equal(revised.graph.facts.find(f=>f.id===term.id)?.status,'disputed');
        assert.equal(revised.findings.find(f=>f.rule==='M02')?.status,'missing');
        assert.equal(revised.result.verdict,'review');
      }
      await click('填写验收意见');
      const note = disputeTerm ? '合成演练，对结算条款取值有异议，请复核。' : '合成演练，请复核合同生效与终验签认的依据。';
      await evaluate('document.querySelector("#review-decision").value="escalate";document.querySelector("#review-note").value='+JSON.stringify(note)+';document.querySelector("#review-form").requestSubmit()');
      await wait('document.querySelector("#case-status").textContent==="待复核"','auditor referral');
      assert.equal(await evaluate('fetch("/api/w/'+path[1]+'/cases/'+path[3]+'").then(r=>r.json()).then(c=>c.decisions.at(-1).decision)'),'escalate');
      const usageUrl = '/api/workspaces/'+path[1]+'/team';
      const usageAtSignoff = await evaluate('fetch('+JSON.stringify(usageUrl)+').then(r=>r.json()).then(d=>d.usage)');
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
      const peerNote = disputeTerm ? '合成演练，请补交载明结算条款的资料。' : '合成演练，请补交双方签署的合同和已签认的终验资料。';
      await evaluate('document.querySelector("#peer-note").value='+JSON.stringify(peerNote)+';document.querySelector("#peer-decision").value="return";document.querySelector("#peer-form").requestSubmit()');
      await wait('document.querySelector("#peer-error").textContent.includes("勾选")','actual findings required');
      const peerRule = disputeTerm ? 'M02' : 'H01';
      const selected = await evaluate('(()=>{const row=[...document.querySelectorAll(".peer-finding")].find(r=>r.textContent.includes('+JSON.stringify(peerRule)+'));row.querySelector("input").click();return [row.querySelector("input").value,row.querySelector("a").href]})()');
      assert.equal(new URL(selected[1]).searchParams.get('rev'),String(revision));
      assert.equal(new URL(selected[1]).searchParams.get('finding'),selected[0]);
      for (const width of [1440,1024,820,768,390,320]) {
        await call('Emulation.setDeviceMetricsOverride',{width,height:850,deviceScaleFactor:1,mobile:width<600});
        assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1 && document.querySelector("#peer-dialog").scrollWidth<=document.querySelector("#peer-dialog").clientWidth+1'),'peer form at '+width);
      }
      await evaluate('document.querySelector("#peer-form").requestSubmit()');
      revision++;
      await wait('!document.querySelector("#peer-dialog").open && document.querySelector("#case-status").textContent==="已归档" && document.querySelector("#version").value==='+JSON.stringify(String(revision)),'independent peer signed');
      const history = await evaluate('fetch("/api/w/'+path[1]+'/cases/'+path[3]+'").then(r=>r.json()).then(c=>c.decisions)');
      assert.deepEqual(history.map(s=>s.decision),['escalate','return']);
      assert.notEqual(history[0].actor,history[1].actor);
      await evaluate('document.querySelector(".peer-panel a[href*=finding]").click()');
      await wait('document.querySelector("#trace-select")?.value==='+JSON.stringify(selected[0]),'peer citation opened the disputed finding on its original revision');
      assert.ok(await evaluate('location.hash.includes("rev='+(revision-1)+'")'));
      const bundleUrl = '/api/w/'+path[1]+'/cases/'+path[3]+'/reports/'+revision+'/bundle';
      const b64 = await evaluate('fetch('+JSON.stringify(bundleUrl)+').then(r=>r.blob()).then(b=>new Promise(res=>{const f=new FileReader(); f.onload=()=>res(f.result.split(",")[1]);f.readAsDataURL(b)}))');
      const zip = join(scratch,'signed.zip');
      await writeFile(zip,Buffer.from(b64,'base64'));
      console.log(execFileSync(process.env.AUDIT_PYTHON || 'server/.venv/bin/python',['server/verify.py','--rules',zip],{encoding:'utf8'}).trim());
      await evaluate('document.querySelector("#nav-library").click()');
      await wait('!document.querySelector("#library").hidden','evidence library');
      const signedFacts=await evaluate('fetch('+JSON.stringify('/api/w/'+path[1]+'/cases/'+path[3]+'/reports/'+revision)+').then(r=>r.json()).then(b=>b.report.graph.facts)');
      const invoiceNumber='YL-FP-071';
      const verified=f=>['anchored','confirmed'].includes(f.status);
      const numbers=signedFacts.filter(f=>[f.quote,f.value].some(t=>t.normalize('NFKC').includes(invoiceNumber)));
      const searchLibrary=(query,group)=>evaluate('document.querySelector("#library-query").value='+JSON.stringify(query)+
        ';document.querySelector("#library-status").value='+JSON.stringify(group)+';document.querySelector("#library-form").requestSubmit()');
      await searchLibrary(invoiceNumber,'verified');
      let candidates=numbers.filter(verified);
      if (!candidates.length) {
        await wait('document.querySelector("#library-results").textContent.includes("没有匹配引文")','unverified invoice excluded from verified results');
        candidates=numbers.length?numbers:signedFacts.filter(f=>f.field==='contract_id' && verified(f));
        assert.ok(candidates.length,'the signed fixture contains an indexed source');
        await searchLibrary(numbers.length?invoiceNumber:candidates[0].value,numbers.length?'pending':'verified');
      }
      const allowed=candidates.map(f=>f.id);
      const indexed = await wait('Array.from(document.querySelectorAll("#library-results .source-jump"),a=>a.href).find(url=>'+JSON.stringify(allowed)+'.includes(new URL(url).searchParams.get("fact")))','source indexed with its signed evidence status');
      assert.equal(new URL(indexed).searchParams.get('rev'),String(revision));
      await evaluate('Array.from(document.querySelectorAll("#library-results .source-jump")).find(a=>a.href==='+JSON.stringify(indexed)+').click()');
      await wait('document.querySelector("#page-dialog").open && !!document.querySelector(".evidence-row.located") && location.hash.includes("rev='+revision+'")','source opened on its indexed revision');
      await evaluate('document.querySelector("#page-dialog").close()');
      await evaluate('document.querySelector("#nav-account").click()');
      await wait('!!document.querySelector("#account-panel details")','peer account');
      await click('退出登录');
      await wait('!!document.querySelector("#account-panel input[name=password]")','peer logged out');
      if (await evaluate('!!document.querySelector("#account input[name=name]")')) await click('已有账号，去登录');
      await entry({login:'ui.owner',password});
      await wait('location.hash.endsWith("/desk") && !document.querySelector("#nav-team").hidden','owner returns');
      await evaluate('document.querySelector("#nav-team").click()');
      await wait('document.querySelector(".usage-list")','workspace usage');
      const usage = await evaluate('fetch("/api/workspaces/'+path[1]+'/team").then(r=>r.json()).then(d=>d.usage)');
      assert.ok(usage.requests >= 4 && usage.input_tokens > 0 && usage.output_tokens > 0,'provider usage recorded');
      for (const key of ['requests','input_tokens','output_tokens']) assert.equal(usage[key],usageAtSignoff[key],'human review adds no model calls or tokens');
      console.log(JSON.stringify({requests:usage.requests,input_tokens:usage.input_tokens,output_tokens:usage.output_tokens}));
      console.log('Signed return on R'+revision);
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
