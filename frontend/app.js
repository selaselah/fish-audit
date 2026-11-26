const $ = selector => document.querySelector(selector);
const state = {cases: [], filter: 'all', detail: null, bundle: null, tab: 'report', pinned: 0,
  timer: null, epoch: 0, key: null, review: null};
let displayedPaper = null;
const ruleChecks = new WeakMap();
const labels = {
  queued: '排队中', running: '处理中', ready: '待验收', in_review: '待复核', closed: '已归档', failed: '已中断',
  prepare: '资料分页', extract: '多模态解析', graph: '证据建图', controls: '规则执行', expert: '专家复核',
  attestation: '人工核图', pass: '建议通过', review: '需要人工校验', reject: '建议不通过',
  ok: '相符', issue: '问题', risk: '风险', missing: '证据不足', anchored: '已匹配文字层',
  visual: '待核原图', confirmed: '人工已确认', disputed: '人工有异议', unsupported: '引用不支持取值',
  approve: '通过', return: '退回补件', escalate: '提交复核', top: '上部', middle: '中部', bottom: '下部',
};
const tabs = {report: '审计结论', evidence: '原件与引文', graph: '知识图谱', activity: '执行记录'};
const travelProfile = 'cn-travel-reimbursement/v1';
const bankProfile = 'cn-bank-contract-payment/v1';
const performanceProfile = 'cn-contract-performance/v1';
const profileName = profile => ({[travelProfile]:'差旅报销',[bankProfile]:'付款回单核对',[performanceProfile]:'合同履约与分期','cn-procurement-full-settlement/v1':'采购与付款'}[profile] || profile);
const tone = {ready: 'risk', in_review: 'risk', closed: 'ok', failed: 'issue', pass: 'ok', review: 'risk', reject: 'issue',
  visual: 'risk', unsupported: 'issue', disputed: 'issue', confirmed: 'ok', anchored: 'ok'};
const statusName = value => labels[value] || value;
function appendHumanReview(row, result, className) {
  if (result.verdict==='review' && result.human_required===true) return;
  const label=result.human_required===true?'需人工校验':result.human_required===false?'无专项待核项':'人工校验要求待核';
  row.append(el('span',label,className));
}
function priorityFindings(findings) {
  return ['issue','risk','missing'].flatMap(status=>findings.filter(item=>item.status===status));
}
const base = () => Team.cases() + '/' + state.detail.id;
const workpaperSource = (doc,path) => base()+'/documents/'+doc+'/'+path+(state.bundle ? '?rev='+state.bundle.rev : '');
const time = value => new Date(value).toLocaleString('zh-CN', {hour12: false, month: '2-digit',
  day: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai'});

function el(tag, text = '', className = '') {
  const node = document.createElement(tag);
  if (text !== '') node.textContent = text;
  if (className) node.className = className;
  return node;
}
function box(className, ...children) {
  const node = el('div', '', className);
  node.append(...children);
  return node;
}
function glyph(name) {
  const icon = el('i', '', 'ui-glyph ic-' + name);
  icon.setAttribute('aria-hidden', 'true');
  return icon;
}
function tag(value) {
  const badge = el('span', statusName(value), 'tag ' + (tone[value] || value));
  badge.dataset.state = value;
  return badge;
}
function action(label, callback, className = '') {
  const node = el('button', label, className);
  node.type = 'button';
  node.addEventListener('click', callback);
  return node;
}
function link(label, target, className = '') {
  const node = el('a', label, className);
  node.href = target;
  return node;
}
function fold(title, ...children) {
  const block = el('details');
  block.append(el('summary', title), ...children);
  return block;
}
function alertText(error) {
  $('#network-error').textContent = error.message;
  $('#network-error').hidden = false;
}
async function api(url, options = {}) {
  let response;
  const headers = new Headers(options.headers || {});
  if (options.method && options.method !== 'GET' && Team.session?.csrf) headers.set('X-CSRF-Token', Team.session.csrf);
  try { response = await fetch(url, {cache: 'no-store', ...options, headers}); }
  catch (error) {
    if (options.signal?.aborted) throw error;
    $('#connection').textContent = '连接中断'; $('#connection').dataset.offline='true';
    throw new Error('暂时无法连接本机审计服务。服务恢复后可查看已提交任务。');
  }
  const data = await response.json();
  if (!response.ok) {
    const problem = new Error(data.error || '服务请求失败。');
    problem.status = response.status;
    problem.invoiceHistory = data.invoice_history;
    problem.incompleteNumbers = data.incomplete_numbers;
    problem.paymentSource = data.payment_source;
    throw problem;
  }
  return data;
}
function post(url, body) {
  return api(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
}
function caseName(row, pinRevision=false) {
  const prefix='合成演练 · ';
  const training=row.title.startsWith(prefix) && row.title.length>prefix.length;
  const params=pinRevision && row.rev>0 ? new URLSearchParams({rev:String(row.rev)}) : undefined;
  const title=Team.paperLink(training ? row.title.slice(prefix.length) : row.title,row.id,'case-link',params);
  title.dataset.caseId=row.id;
  if (training) title.setAttribute('aria-label',row.title);
  return {title,training};
}
function peekButton(row) {
  const button=action('',()=>Desk.peek(row),'icon-button case-peek');
  button.append(glyph('layout-sidebar-inset-reverse'));
  button.dataset.previewCase=row.id; button.title='速览任务';
  button.setAttribute('aria-label','速览 '+row.title); button.setAttribute('aria-haspopup','dialog');
  return button;
}
function renderList() {
  const list = $('#case-list');
  const visible = state.cases;
  const header = box('ledger-header ledger-row', ...['任务名称','处理状态','审计结果', $('#desk-sort').value === 'updated' ? '最近更新' : '提交时间',''].map(label => el('span', label)));
  list.replaceChildren(header);
  for (const row of visible) {
    const {title,training} = caseName(row);
    const metadata = el('span', [training ? '合成演练' : '', profileName(row.profile)].filter(Boolean).join(' · '), 'small case-meta');
    const status = box('', tag(row.status));
    if (row.status === 'running') status.append(el('small', row.progress + '%', 'small'));
    const result = row.decision ? '人工' + statusName(row.decision) :
      (row.verdict ? statusName(row.verdict) : '等待结果');
    const verdict = box('row-result', el('span',result));
    verdict.dataset.verdict = row.decision || row.verdict || '';
    if (row.issues || row.risks) verdict.append(el('small',
      [row.issues ? row.issues+' 项问题' : '', row.risks ? row.risks+' 项风险' : ''].filter(Boolean).join(' · '),'small'));
    const icon = box('case-glyph',glyph(row.profile===bankProfile || row.profile===travelProfile ? 'receipt' : 'journal-text'));
    list.append(box('ledger-row', box('case-name',icon,box('',title,metadata)), status, verdict,
      el('span', time($('#desk-sort').value==='updated' ? row.updated : row.created), 'small row-date'),peekButton(row)));
  }
  if (!visible.length) list.append(el('p', state.filter === 'all' && !$('#case-search').value && !$('#desk-profile').value ? '还没有任务，选择「新建审计」上传资料。' : '当前筛选条件下没有任务。', 'empty'));
  for (const button of document.querySelectorAll('[data-filter]')) {
    button.setAttribute('aria-pressed', String(button.dataset.filter === state.filter));
  }
}
function renderCatalog(data) {
  const panel = box('panel', el('h2', '资料检查程序'), el('p', Object.values(data.profiles).join('、')+' · 版本 ' + data.version, 'muted'));
  for (const rule of data.rules) {
    panel.append(box('line', el('strong', rule.id, 'mono'), el('strong', rule.name), el('p', rule.basis)));
  }
  const law = data.background;
  const url = link(law.title, law.url);
  url.target = '_blank'; url.rel = 'noopener noreferrer';
  const references = box('panel', el('h2', '制度与方法参考'));
  if (data.sources) {
    for (const source of Object.values(data.sources)) references.append(sourceEntry(source));
  } else references.append(el('p', law.scope), url);
  $('#catalog').replaceChildren(panel, references);
}
function sourceEntry(source) {
  const url = link(source.title, source.url); url.target = '_blank'; url.rel = 'noopener noreferrer';
  return box('line', url, el('p', source.locator + ' · ' + source.edition, 'small'),
    el('p', source.summary), el('p', source.scope, 'muted'));
}
async function loadReviewImage(image, source) {
  const response = await fetch(source, {cache:'no-store'});
  if (!response.ok) throw new Error('原页加载失败');
  const objectUrl = URL.createObjectURL(await response.blob());
  try {
    image.src = objectUrl;
    await image.decode();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}
function markPageRects(overlay, rects) {
  overlay.replaceChildren();
  for (const bounds of rects) {
    if (!Array.isArray(bounds) || bounds.length!==4 || !bounds.every(n=>Number.isFinite(n) && n>=0 && n<=1)) continue;
    const [left,top,right,bottom]=bounds;
    if (right<=left || bottom<=top) continue;
    const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');
    for (const [name,value] of Object.entries({x:left,y:top,width:right-left,height:bottom-top}))
      rect.setAttribute(name,String(1000*value));
    overlay.append(rect);
  }
}

function openPage(docId, pageNumber, highlight, lineHint, registerPair, rawRef) {
  const item = state.detail.documents.find(doc => doc.id === docId);
  if (!item) return;
  const pageUrl = workpaperSource(docId,'pages/'+pageNumber);
  const image = el('img', '', 'page-image');
  image.alt = item.name + ' 第 ' + pageNumber + ' 页';
  const enlarged = link('单独打开页图', pageUrl); enlarged.target = '_blank'; enlarged.rel = 'noopener';
  enlarged.prepend(glyph('arrows-angle-expand'));
  const overlay = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  overlay.setAttribute('viewBox', '0 0 1000 1000');
  overlay.setAttribute('preserveAspectRatio', 'none');
  overlay.setAttribute('aria-hidden', 'true');
  const plane = box('source-plane',image,overlay);
  const sheet = box('image-sheet',plane);
  const canvas = box('source-scroll',sheet);
  canvas.tabIndex=0; canvas.setAttribute('role','region'); canvas.setAttribute('aria-label','可滚动的原件页图');
  const levels = [100,125,150,200,300,400];
  let zoom = 0, turns = 0;
  const decrease = action('',()=>setZoom(zoom-1),'icon-button');
  const increase = action('',()=>setZoom(zoom+1),'icon-button');
  const fit = action('适宽',()=>setZoom(0),'zoom-fit');
  decrease.append(glyph('zoom-out')); increase.append(glyph('zoom-in'));
  decrease.setAttribute('aria-label','缩小原页'); increase.setAttribute('aria-label','放大原页');
  const scale = el('output','100%','zoom-scale'); scale.setAttribute('aria-label','相对适宽比例');
  const rotateLeft=action('',()=>rotate(-1),'turn-page'), rotateRight=action('',()=>rotate(1),'turn-page');
  rotateLeft.append(glyph('arrow-counterclockwise')); rotateRight.append(glyph('arrow-clockwise'));
  for (const [button,label] of [[rotateLeft,'向左旋转 90°'],[rotateRight,'向右旋转 90°']]) {
    button.setAttribute('aria-label',label); button.title=label; button.disabled=true;
  }
  const direction=el('output','','visually-hidden'); direction.setAttribute('aria-label','页图方向');
  const tools = box('source-tools',box('source-adjust',box('zoom-group',decrease,scale,increase,fit),
    box('zoom-group',rotateLeft,rotateRight,direction)),enlarged);
  const left = box('viewer-original',tools,canvas);
  const right = box('viewer-facts', el('h3', '本页引文'));
  left.id = 'viewer-original'; right.id = 'viewer-facts';
  left.tabIndex = right.tabIndex = -1;
  const pageFacts = (state.bundle?.report.graph.facts || []).filter(fact => fact.doc === docId && fact.page === pageNumber);
  const boardRefs = boardPageReferences(state.bundle?.report.graph, docId, pageNumber, pageFacts);
  const repairRefs = repairPageReferences(state.bundle?.report.graph, docId, pageNumber, pageFacts);
  const paper=state.bundle?.report;
  const word=WordSigning.resolve(paper?.findings.find(f=>f.rule==='H01'),paper?.graph,paper?.calls.pages);
  const registerRefs=ReinspectionTrail.pageReferences(paper?.findings.find(f=>f.rule==='H02'),paper?.graph,docId,pageNumber);
  const timingRows=ReinspectionTiming.pageReferences(paper?.findings.find(f=>f.rule==='H02'),paper?.graph,docId,pageNumber);
  const otherRefs = [...registerRefs, ...boardRefs, ...repairRefs, ...PhaseEvidence.pageReferences(paper?.graph,docId,pageNumber,pageFacts,lineHint)];
  const timingRefs=timingRows.filter(s=>!otherRefs.some(r=>r.rawLine===s.rawLine));
  const contractRefs=[...ContractFolios.pageReferences(docId,pageNumber),...ContractCalendar.pageReferences(docId,pageNumber)];
  const preferred=contractRefs.find(r=>r.ref===rawRef);
  const existingRefs=[...timingRefs,...otherRefs];
  const pageRefs=[...(preferred?[preferred]:[]),...existingRefs.filter(r=>!preferred || r.rawLine!==preferred.rawLine)];
  for (const row of contractRefs) {
    if (!pageRefs.some(r=>r.rawLine===row.rawLine)) pageRefs.push(row);
  }
  const comparedFact=registerPair && pageFacts.find(f=>f.id===registerPair.fact && f.field==='acceptance_result' && f.source_line?.rects?.length);
  const comparedNote=registerPair && registerRefs.find(s=>s.rawLine===registerPair.line && s.rawLine!==comparedFact?.source_line.number);
  const comparison=comparedFact && comparedNote ? box('trail-reader-pair') : null;
  if (comparison) {
    comparison.setAttribute('role','group'); comparison.setAttribute('aria-label','切换同页核对位置');
    const announce=el('output','','visually-hidden');
    for (const [ref,label,line,quote] of [[comparedFact.id,'复验结论',comparedFact.source_line.number,comparedFact.quote],
                                         [comparedNote.ref,'复验附注',comparedNote.rawLine,comparedNote.quote]]) {
      const control=action('',()=>{selectReference(ref,false); announce.textContent=quote;});
      control.dataset.pairRef=ref;
      control.append(el('strong',label),el('small','第 '+line+' 行'));
      comparison.append(control);
    }
    comparison.append(announce); left.insertBefore(comparison,canvas);
  }
  const rawLines = pageRefs.filter(source => source.rawLine);
  const initialRaw = rawLines.find(source => source.rawLine === lineHint);
  let showAllFacts = !initialRaw && !pageFacts.some(f=>f.id===highlight);
  const coverage = state.bundle?.report.graph.delegation_coverage;
  const nameHolds = new Map([...(coverage?.agent_holds || []),...(coverage?.signer_holds || [])]
    .filter(h=>h.doc===docId && h.page===pageNumber && h.lines?.length).map(h=>[h.fact,h]));
  const editable = state.bundle?.rev === state.detail.rev && state.detail.status === 'ready';
  const selected = new Set();
  let focusRow;
  function setZoom(index) {
    zoom = Math.max(0,Math.min(index,levels.length-1));
    sheet.style.width=levels[zoom]+'%';
    scale.textContent=levels[zoom]+'%';
    decrease.disabled=zoom===0;
    increase.disabled=zoom===levels.length-1;
    if (!zoom) canvas.scrollLeft=0;
    revealPageMark();
  }
  function orient() {
    const w=image.naturalWidth,h=image.naturalHeight;
    if (!w || !h) return;
    sheet.style.aspectRatio=turns%2?h+' / '+w:w+' / '+h;
    sheet.dataset.turn=String(turns);
    plane.style.width=(turns%2?100*w/h:100)+'%';
    plane.style.aspectRatio=w+' / '+h;
  }
  function rotate(step) {
    const before=sheet.getBoundingClientRect(), pane=canvas.getBoundingClientRect();
    if (!before.width || !before.height || !image.naturalWidth) return;
    const center=(a,b,start,end)=>(Math.max(a,start)+Math.min(b,end))/2;
    const x=(center(before.left,before.right,pane.left,pane.right)-before.left)/before.width;
    const y=(center(before.top,before.bottom,pane.top,pane.bottom)-before.top)/before.height;
    turns=(turns+step+4)%4; orient();
    const after=sheet.getBoundingClientRect();
    canvas.scrollLeft+=(after.left+(step===1?1-y:y)*after.width)-(pane.left+canvas.clientWidth/2);
    canvas.scrollTop+=(after.top+(step===1?x:1-x)*after.height)-(pane.top+canvas.clientHeight/2);
    direction.textContent=turns?'顺时针 '+(turns*90)+'°':'原始方向';
    revealPageMark();
  }
  decrease.disabled=increase.disabled=fit.disabled=true;
  function revealPageMark() {
    if (!left.isConnected || !image.naturalWidth) return;
    const rect = overlay.firstElementChild?.getBoundingClientRect();
    if (!rect) return;
    const pane = canvas.getBoundingClientRect();
    if (rect.top < pane.top + 8 || rect.bottom > pane.bottom - 8)
      canvas.scrollTop += (rect.top + rect.bottom - pane.top - pane.bottom) / 2;
    if (rect.left < pane.left + 8 || rect.right > pane.right - 8)
      canvas.scrollLeft += (rect.left + rect.right - pane.left - pane.right) / 2;
  }
  function locate(fact, raw) {
    const ref = fact?.id || raw?.ref || '';
    comparison?.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.pairRef===ref)));
    markPageRects(overlay,fact?.source_line?.rects || raw?.rects || []);
    for (const row of right.querySelectorAll('.evidence-row')) {
      const rowRef = row.dataset.fact || row.dataset.sourceRef;
      row.classList.toggle('located', Boolean(ref) && rowRef === ref);
      if (rowRef) row.hidden = !showAllFacts && rowRef !== ref;
    }
    if (fieldPicker) fieldPicker.value=showAllFacts ? '' : ref;
    if (compareButton) {
      const next = pageRefs[(pageRefs.findIndex(source => source.ref === ref) + 1) % pageRefs.length];
      compareButton.textContent = '对照' + next.label;
      compareButton.dataset.nextRef = next.ref;
    }
    revealPageMark();
  }
  function focusObservation(source, raw=null, moveFocus=true) {
    locate(source, raw);
    const target = right.querySelector('.located');
    if (!moveFocus || !target) return;
    target.tabIndex = -1;
    target.focus({preventScroll:true});
    target.scrollIntoView({block:'nearest'});
  }
  function selectReference(ref, moveFocus) {
    const fact = pageFacts.find(f => f.id === ref);
    const raw = rawLines.find(source => source.ref === ref);
    showAllFacts = !fact && !raw;
    if (showAllFacts) {
      comparison?.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed','false'));
      for (const row of right.querySelectorAll('[data-fact],[data-source-ref]')) row.hidden = false;
      return;
    }
    focusObservation(fact, raw, moveFocus);
  }
  let fieldPicker, compareButton;
  if (pageFacts.length || rawLines.length) {
    fieldPicker=el('select'); fieldPicker.setAttribute('aria-label','定位本页引文');
    fieldPicker.add(new Option('全部引文 · '+(pageFacts.length + rawLines.length)+' 项',''));
    for (const [label,refs] of [['复验间隔原行',timingRefs],['审批决定与待核原文',boardRefs],['整改状态与原行',repairRefs],['复验附注',registerRefs]]) {
      if (!refs.length) continue;
      const group = el('optgroup');
      group.label = label;
      for (const source of refs) group.append(new Option(source.option, source.ref));
      fieldPicker.append(group);
    }
    for (const fact of pageFacts) {
      if (!pageRefs.some(source => source.ref === fact.id)) fieldPicker.add(new Option(fact.label+' · '+fact.value,fact.id));
    }
    fieldPicker.addEventListener('change',() => selectReference(fieldPicker.value, true));
    const navigator = box('field-navigator',right.querySelector('h3'),fieldPicker);
    if (pageRefs.length > 1 && !comparison) {
      const announcement = el('output','','visually-hidden');
      compareButton = action('对照'+pageRefs[0].label,() => {
        const next = pageRefs.find(source => source.ref === compareButton.dataset.nextRef);
        selectReference(next.ref, false);
        announcement.textContent = next.label+' · '+next.quote;
      },'approval-switch');
      compareButton.dataset.nextRef = pageRefs[0].ref;
      fieldPicker.before(compareButton);
      navigator.append(announcement);
    }
    right.prepend(navigator);
  }
  const selectionCount = el('span','','small');
  for (const fact of pageFacts) {
    const row = box('evidence-row');
    row.dataset.fact = fact.id;
    const label = el('label', '', 'check-label');
    if (editable) {
      const check = el('input'); check.type = 'checkbox'; check.value = fact.id;
      check.addEventListener('change', () => {
        if (check.checked) selected.add(fact.id); else selected.delete(fact.id);
        submit.disabled = selected.size === 0;
        selectionCount.textContent = selected.size ? '已选 '+selected.size+' 项引文' : '';
      });
      label.append(check);
    }
    label.append(el('strong', fact.label + ' · ' + fact.value));
    row.append(label, tag(fact.status), el('blockquote', fact.quote),
      el('small', fact.id + ' · ' + (fact.source_line ? '文字层第 ' + fact.source_line.number + ' 行' :
        '模型定位：页' + statusName(fact.region)), 'small'));
    if (fact.source_line) row.append(fold('对照本机文字层', el('blockquote', fact.source_line.text)));
    const nameHold = nameHolds.get(fact.id);
    if (nameHold) {
      const native = box('mandate-name-source',el('strong','核对姓名栏原文'));
      native.dataset.mandateKind = nameHold.kind;
      for (const line of nameHold.lines) native.append(el('small','原页第 '+line.line+' 行','small'),el('blockquote',line.quote));
      row.append(native);
    }
    if (fact.origin === 'verified_printed_heading') row.append(el('small','标题来自可定位文字层，经模型对照页图复检。','small'));
    if (fact.origin === 'printed_quality_number') {
      const trace=state.bundle.report.calls.pages.find(t=>t.doc===docId && t.page===pageNumber);
      const check=trace?.check;
      const review=fold('核对编号字段的两项读图结果');
      review.classList.add('quality-number-check');
      for (const key of [fact.id.split('/f').pop(),fact.classification_index]) {
        const input=check?.input?.find(v=>v.index===key);
        const vote=check?.output?.checks?.find(v=>v.index===key);
        if (input && vote) review.append(el('p',input.field+' · '+({clear:'与原页相符',conflict:'与原页冲突',unreadable:'无法辨读'}[vote.support])),
          el('blockquote',input.quote));
      }
      row.append(review);
    }
    if (fact.origin === 'printed_claim_pair') row.append(el('small','模型原列为随附票号。原页同一行明列代码和号码，逐项读图复检已核对这段引文。','small'));
    const qualityHold = state.bundle.report.graph.quality_references?.holds.find(h => h.fact === fact.id);
    if (qualityHold) {
      const note = box('quality-number-hold');
      note.append(el('strong', '需核对完整编号'));
      for (const line of qualityHold.lines) {
        note.append(el('blockquote', '本页第 '+line.number+' 行 · '+line.quote));
        const source = pageFacts.find(f => f.id !== fact.id && f.source_line?.number === line.number && f.source_line.text === line.quote);
        if (source) note.append(action('定位同页展示说明', () => focusObservation(source), 'ref'));
      }
      for (const observation of qualityHold.observations) {
        note.append(el('blockquote', '本页读图引文 · '+observation.quote));
        const source = pageFacts.find(f => f.id === observation.fact);
        if (source) note.append(tag(source.status), action('定位同页展示说明', () => focusObservation(source), 'ref'));
      }
      row.append(note);
    }
    if (state.bundle.report.graph.number_masks?.facts.some(m=>m.fact===fact.id))
      row.append(el('small','原文含遮盖位或只列尾号。取得完整票号后可重新核对。','small'));
    const partialTransfer = state.bundle.report.graph.transfer_references?.facts.find(m=>m.fact===fact.id);
    if (partialTransfer) {
      const pending = partialTransfer.state==='pending_note';
      const unchecked = partialTransfer.state==='visibility_unchecked';
      row.append(el('strong',unchecked?'待核整页展示范围':pending?'流水展示说明待核图':'流水号待补全'));
      for (const line of partialTransfer.lines.filter(l=>l.number!==fact.source_line?.number))
        row.append(el('blockquote','本页第 '+line.number+' 行 · '+line.text));
      for (const note of partialTransfer.notes || []) {
        const source = pageFacts.find(f=>f.id===note.fact);
        if (source) row.append(el('blockquote',note.quote),tag(note.status),action('定位同页展示说明',()=>focusObservation(source),'ref'));
      }
      row.append(el('small',unchecked?'核对整张回单的流水栏、页脚和备注后，可在核图意见中记录展示范围。':
        pending?'核对这条说明后可重新审计。':'取得完整流水后可查找相同回单、复算累计付款。','small'));
      if (editable && unchecked) row.append(action('记录流水展示范围',()=>{
        $('#page-dialog').close();
        openReview([fact.id],true);
      },'ref'));
    }
    if (fact.visual_check) row.append(el('small', '模型二次读图 · ' +
      ({clear:'可辨认', conflict:'存在差异', unreadable:'无法核实'}[fact.visual_check] || fact.visual_check), 'small'));
    if (fact.source_line?.rects?.length) row.append(action('定位原文', () => locate(fact), 'ref'));
    if (fact.attestation) {
      row.append(el('p', fact.attestation.reviewer + ' · ' + fact.attestation.note, 'muted'));
      const scope=fact.attestation.source_check?.reference_visibility;
      if (scope) row.append(el('strong',scope.opinion==='complete'?'整页核图已确认流水完整显示':'整页核图已确认流水仅部分显示'));
    }
    if (fact.amendment) {
      const previous = fact.original_candidate;
      row.append(fold('人工' + (previous ? '更正' : '补录') + '来源', el('p', fact.amendment.reviewer + ' · ' +
        fact.amendment.note), el('p', previous ? '原模型引文：' + previous.quote + '（' + previous.value + '）' : '此字段由审计人员据图补录。')));
    }
    const checks = new Map();
    for (const record of [fact.amendment,fact.attestation]) {
      const check = record?.source_check;
      if (check) checks.set(check.rev+'@'+check.checked_at,check);
    }
    for (const check of checks.values()) {
      const anchor = link('打开核图时的第 '+check.page+' 页',base()+'/documents/'+check.doc+'/pages/'+check.page+'?rev='+check.rev,'source-jump');
      anchor.target = '_blank'; anchor.rel='noopener';
      const params = new URLSearchParams({rev:String(check.rev)});
      if (check.operation!=='add') params.set('fact',fact.id);
      const paper = Team.paperLink('查看核图时的底稿 R'+check.rev,state.detail.id,'source-jump',params);
      paper.target='_blank'; paper.rel='noopener';
      const download = link('下载当时的原件',base()+'/documents/'+check.doc+'/original?rev='+check.rev);
      const receipt = fold('核图时的原件与页图 · R'+check.rev,
        el('p',time(check.checked_at)+' · '+({confirm:'确认字段',correct:'更正字段',add:'补录字段'}[check.operation])),
        box('chips',anchor,paper,download),el('p','原件 SHA-256'),el('code',check.original_sha256),el('p','页图 SHA-256'),el('code',check.page_sha256),
        el('p','核图时的底稿 SHA-256'),el('code',check.report_hash));
      receipt.classList.add('field-source-check'); row.append(receipt);
    }
    if (editable) row.append(action('更正字段', () => openAmend(docId, pageNumber, fact), 'ref'));
    if (fact.id === highlight) focusRow = row;
    right.append(row);
  }
  const gaps = (state.bundle?.report.graph.gaps || []).filter(g => g.doc === docId && g.page === pageNumber && g.quote);
  const addenda = state.bundle?.report.graph.quality_addenda;
  if (addenda && lineHint && !gaps.some(g=>g.line===lineHint)) {
    const count = addenda.quantities?.lines.find(s=>s.doc===docId && s.page===pageNumber && s.line===lineHint);
    const payment=PhaseEvidence.amendmentLines(state.bundle.report.graph).find(s=>s.doc===docId && s.page===pageNumber && s.line===lineHint);
    const note = count || payment || [...addenda.signals,...addenda.limited_numbers].find(s=>s.doc===docId && s.page===pageNumber && s.line===lineHint);
    if (note) gaps.push({...note,field:note.field==='quantity_note'?'other':note.field,
      quality:count?'quantity_reference':payment?'payment_amendment_reference':'addendum_reference'});
  }
  const signers = state.bundle?.report.graph.acceptance_authority_sources;
  if (signers && lineHint && !gaps.some(g=>g.line===lineHint)) {
    const source = [...signers.clauses,...signers.signatures].find(s=>s.doc===docId && s.page===pageNumber && s.line===lineHint);
    if (source) gaps.push({...source,quality:'signer_reference'});
  }
  const batches=state.bundle?.report.graph.delivery_batch_sources;
  const batchNote = lineHint && batches?.remarks?.find(row => row.doc===docId && row.page===pageNumber && row.line===lineHint);
  if (batchNote && !gaps.some(g=>g.line===lineHint)) gaps.push({...batchNote,quality:'delivery_batch_clause'});
  const monetary=state.bundle?.report.graph.stage_payment_sources;
  const modelLines=state.bundle?.report.graph.equipment_model_sources?.lines;
  if (lineHint && modelLines && !gaps.some(g=>g.line===lineHint)) {
    const line=modelLines.find(r=>r.doc===docId && r.page===pageNumber && r.line===lineHint);
    if (line) gaps.push({...line,quality:'equipment_model_reference'});
  }
  if (monetary && lineHint && !gaps.some(g=>g.line===lineHint)) {
    const note=monetary.notes.find(r=>r.doc===docId && r.page===pageNumber && r.line===lineHint);
    const raw=monetary.pages.find(p=>p.doc===docId && p.page===pageNumber)?.uncovered.find(r=>r.line===lineHint);
    const row=note || raw;
    if (row) gaps.push({...row,quality:'stage_transfer_reference'});
  }
  const packets=state.bundle?.report.graph.receipt_packet_sources?.packets;
  if (packets && lineHint && !gaps.some(g=>g.line===lineHint)) {
    const page=packets.find(p=>p.doc===docId)?.pages.find(p=>p.page===pageNumber);
    const row=page?.rows.find(r=>r.line===lineHint);
    if (row) gaps.push({...row,quality:'receipt_page_reference',field:['continuation','partial_number'].includes(row.field)?null:row.field});
  }
  if (batches && lineHint && !gaps.some(g=>g.line===lineHint)) {
    const source=batches.signals.find(s=>s.doc===docId && s.page===pageNumber && s.line===lineHint);
    if (source) gaps.push({...source,quality:'delivery_batch_clause'});
  }
  const effect=state.bundle?.report.graph.contract_effect_sources;
  for (const source of rawLines) {
    if (!gaps.some(g => g.line === source.rawLine))
      gaps.push({line:source.rawLine,quote:source.quote,quality:source.quality || 'approval_reference'});
  }
  if (effect && lineHint && !gaps.some(g=>g.line===lineHint)) {
    const source=effect.conditions.find(s=>s.doc===docId && s.page===pageNumber && s.line===lineHint);
    if (source) gaps.push({...source,quality:source.kind==='approval_note'?'approval_reference':'effect_reference'});
  }
  const warranty=state.bundle?.report.graph.warranty_sources;
  if (warranty && lineHint && !gaps.some(g=>g.line===lineHint)) {
    const source=warranty.lines.find(s=>s.doc===docId && s.page===pageNumber && s.line===lineHint);
    if (source) gaps.push({...source,quality:'warranty_reference'});
  }
  const windows=state.bundle?.report.graph.payment_window_sources;
  if (windows && lineHint && !gaps.some(g=>g.line===lineHint)) {
    const source=windows.lines.find(s=>s.doc===docId && s.page===pageNumber && s.line===lineHint);
    if (source) gaps.push({...source,quality:'payment_window_reference'});
  }
  const reservations=state.bundle?.report.graph.acceptance_reservation_sources;
  if (reservations && lineHint && !gaps.some(g=>g.line===lineHint)) {
    const source=[...reservations.lines,...(reservations.supplier_rows || [])].find(s=>s.doc===docId && s.page===pageNumber && s.line===lineHint);
    if (source) gaps.push({...source,quality:['seller','delivery_note'].includes(source.kind)?'supplier_reference':'reservation_reference'});
  }
  for (const gap of gaps) {
    const label = {inspection_reference:'设备检验原行',contract_signing_reference:'合同签章原行',payment_release_reference:'放行依据原行',acceptance_opinion_reference:'付款意见原行',payment_amendment_reference:'付款变更所据原行',invoice_receipt_reference:'收票条件所据原行',repair_completion_reference:'整改记录原行',equipment_model_reference:'设备型号核对原行',stage_transfer_reference:'分笔付款所据原行',receipt_page_reference:'验收合订件原行',addendum_reference:'补充协议所据原文',quantity_reference:'交付数量核对原文',signer_reference:'验收签认所据原文',delivery_batch_clause:'分批交付待核原文',effect_reference:'合同生效所据原文',approval_reference:'董事会审批记录原文',warranty_reference:'质保金所据原文',payment_window_reference:'付款时限所据原文',reservation_reference:'验收附注原文',supplier_reference:'供应方核对原文'}[gap.quality] || '待核的原文字层';
    const timingRow=timingRefs.find(r=>r.rawLine===gap.line);
    const raw = rawLines.find(source => source.rawLine === gap.line);
    const heading=contractRefs.includes(raw)?raw.label:timingRow?.label || (gap.quality==='register_reference'?'复验附注':label);
    const section = box('evidence-row',el('h4',heading+' · 第 '+gap.line+' 行'),el('blockquote',gap.quote));
    section.dataset.gapLine = String(gap.line);
    if (raw) {
      section.dataset.sourceRef = raw.ref;
      if (boardRefs.includes(raw)) section.dataset.boardRef = raw.ref;
    }
    if (gap.line===lineHint) {
      section.classList.add('located');
      focusRow=section;
    }
    const field = ['mandate_clause','addendum_clause','acceptance_authority_clause','delivery_batch_clause'].includes(gap.quality) ? null : gap.field || gap.title_hint;
    const signing=word?.readings.find(r=>r.row.doc===docId && r.row.page===pageNumber &&
      r.row.line===gap.line && r.row.quote===gap.quote);
    if (signing) {
      const edit=WordSigning.editButton(signing);
      if (edit) section.append(edit);
    } else if (editable && field) {
      const unresolved=pageFacts.filter(f=>['visual','unsupported'].includes(f.status));
      const matching=unresolved.filter(f=>f.source_line?.number===gap.line && f.source_line.text===gap.quote);
      const candidates=matching.length?matching:unresolved.filter(f=>f.field===field && !f.source_line);
      const label=candidates.length && candidates[0].field!==field?'据原文更正字段类别':'据此行更正候选';
      if (candidates.length <= 1) section.append(action(candidates.length ? label : '据此行补录',
        ()=>openAmend(docId,pageNumber,candidates[0],{field,quote:gap.quote}),'ref'));
    }
    right.append(section);
  }
  if (!pageFacts.length && !rawLines.length) right.append(el('p', '本页尚无可展示的提取记录。', 'muted'));
  const submit = action('记录所选引文的核图意见', () => {
    $('#page-dialog').close(); openReview([...selected]);
  }, 'primary');
  submit.disabled = true;
  if (editable) {
    const reviewActions=box('review-selection');
    if (pageFacts.length) reviewActions.append(submit);
    reviewActions.append(action('补录本页字段', () => openAmend(docId, pageNumber, null)),selectionCount);
    right.append(reviewActions);
  }
  const controls = editable ? [...right.querySelectorAll('button:enabled,input:enabled')].filter(control => control !== compareButton) : [];
  for (const control of controls) control.disabled = true;
  const notice=box('source-error');
  const loadStatus=el('span','原页加载失败。');
  const retry=action('重新加载页图',load,'ref');
  notice.append(loadStatus,retry); notice.setAttribute('role','alert');
  async function load() {
    const returnFocus=document.activeElement===retry;
    retry.disabled=true;
    if (notice.isConnected) { loadStatus.textContent='正在重新载入原页…'; notice.setAttribute('aria-busy','true'); }
    try {
      await loadReviewImage(image,pageUrl);
      notice.remove();
      sheet.hidden=false; image.hidden=false; overlay.removeAttribute('hidden'); orient();
      rotateLeft.disabled=rotateRight.disabled=fit.disabled=false;
      setZoom(zoom);
      for (const control of controls) control.disabled=false;
      if (returnFocus && canvas.isConnected && $('#page-dialog').open) canvas.focus({preventScroll:true});
    } catch {
      sheet.hidden=true; image.hidden=true; overlay.setAttribute('hidden','');
      decrease.disabled=increase.disabled=fit.disabled=rotateLeft.disabled=rotateRight.disabled=true;
      loadStatus.textContent='原页加载失败。'; notice.removeAttribute('aria-busy'); retry.disabled=false;
      if (!notice.isConnected) left.prepend(notice);
      if (returnFocus && retry.isConnected && $('#page-dialog').open) retry.focus({preventScroll:true});
    }
  }
  load();
  $('#page-title').textContent = item.name + ' · 第 ' + pageNumber + ' 页';
  const jumpTo = (pane, target) => {
    pane.focus({preventScroll:true});
    (target || pane).scrollIntoView({block:'center'});
  };
  const originalButton = action('看原页', () => jumpTo(left,overlay.querySelector('rect')));
  const quotesButton = action('看引文', () => jumpTo(right,right.querySelector('.located')));
  originalButton.setAttribute('aria-controls',left.id); quotesButton.setAttribute('aria-controls',right.id);
  $('#page-content').replaceChildren(box('viewer-nav', originalButton, quotesButton), box('page-view', left, right));
  $('#page-dialog').showModal();
  if (focusRow) {
    const fact=pageFacts.find(f=>f.id===highlight);
    if (fact || initialRaw) locate(fact, initialRaw);
    focusRow.scrollIntoView({block: 'nearest'});
  }
}
function citation(ref) {
  const index = state.bundle && graphIndex(state.bundle.report.graph);
  const prior = index?.prior.get(ref);
  if (prior) {
    const label = prior.title+' · R'+prior.rev+' 第 '+prior.page+' 页 · '+(prior.label || '发票号码');
    return Team.paperLink(label,prior.case_id,'button ref',new URLSearchParams({rev:String(prior.rev),fact:prior.fact}));
  }
  const source = index?.nodes.get(ref);
  if (source?.type==='contract_date_line') return ContractCalendar.citation(ref);
  if (source?.type==='contract_folio_line') return ContractFolios.citation(ref);
  if (source?.type==='reinspection_time_line') {
    const report=state.bundle.report;
    const row=ReinspectionTiming.sources(report.graph,report.findings.find(f=>f.rule==='H02')).find(r=>r.id===ref);
    return row ? action(row.quote,()=>ReinspectionTiming.open(row),'ref') : el('span','复验间隔原行待核','small');
  }
  if (ref.startsWith('inspection-line/')) {
    const graph=state.bundle.report.graph;
    const row=InspectionCoverage.sources(graph).find(r=>r.id===ref);
    return row ? action(row.quote,()=>InspectionCoverage.open(row,graph),'ref') : el('span','设备检验原行待核','small');
  }
  if (source?.type==='prior_installment_term') {
    const graph=state.bundle.report.graph;
    const row=PriorInstallment.sources(graph).find(r=>r.id===ref);
    return row ? action(row.quote,()=>PriorInstallment.open(row,graph),'ref') : el('span','前款约定原行待核','small');
  }
  if (source?.type==='contract_signing_line') {
    const graph=state.bundle.report.graph;
    const row=SigningParties.sources(graph).find(r=>r.id===ref);
    return row ? action(row.quote,()=>SigningParties.open(row,graph),'ref') : el('span','签章原行待核','small');
  }
  if (source?.type==='method_reference') {
    const method=state.bundle.report.policy.sources?.[ref.slice('source/'.length)];
    if (!method || method.url!==source.url || !method.url.startsWith('https://')) return el('span','制度来源待核','small');
    const anchor=link(method.edition+' · '+method.title,method.url,'button ref');
    anchor.target='_blank'; anchor.rel='noopener noreferrer';
    return anchor;
  }
  if (source?.type === 'document' || source?.type === 'document_section') {
    const doc = source.source || ref;
    const page = source.page || 1;
    return action(source.label + ' · 查看原件', () => openPage(doc,page), 'ref');
  }
  const [doc, rawPage] = ref.split('/');
  const page = Number((rawPage || '').slice(1));
  const item = index?.documents.get(doc) || state.detail.documents.find(document => document.id === doc);
  const fact = index?.facts.get(ref);
  return action((item?.name || doc) + ' p.' + page + (fact ? ' · ' + fact.label : ''),
    () => openPage(doc, page, ref), 'ref');
}
$('.skip').addEventListener('click', event => {
  event.preventDefault();
  $('#content').focus();
});
function sourceList() {
  const panel = box('panel', el('h2', '提交资料'));
  for (const item of state.detail.documents) {
    const download = link('下载原件', workpaperSource(item.id,'original'));
    const pages = box('chips');
    for (let number = 1; number <= item.pages; number++) {
      pages.append(action('查看第 ' + number + ' 页', () => openPage(item.id, number), 'ref'));
    }
    const hash = fold('原件摘要 SHA-256', el('code', item.sha256));
    panel.append(box('source-doc', box('panel-head', el('h3', item.name), download),
      el('small', Math.ceil(item.size / 1024) + ' KiB · ' + item.pages + ' 页', 'small'), pages, hash));
  }
  return panel;
}
function calculationPanel(calculation) {
  const operands = calculation.operands.map(operand => {
    const refs = fold('币种与计量单位', citation(operand.currency_fact), citation(operand.unit_fact));
    return box('formula-operand', el('span', operand.sign < 0 ? '−' : '+', 'formula-sign'),
      box('', el('strong', operand.label), citation(operand.amount_fact), refs), el('span', operand.decimal, 'amount'));
  });
  return box('formula', el('h4', calculation.label), ...operands,
    box('formula-result', el('strong', '复算结果'), el('strong', calculation.result + ' 元', 'amount')));
}

function ruleReplayPanel(bundle) {
  const panel = box('panel rule-replay',el('h2','规则复算'),
    el('p','使用本版图谱与已保存的专家建议，逐项核对审计发现和整案建议。','muted'));
  const check = ruleChecks.get(bundle);
  const button = action(check?.state==='running'?'正在匹配版本并复算…':'复算本版规则',async()=>{
    ruleChecks.set(bundle,{state:'running'});
    panel.replaceWith(ruleReplayPanel(bundle));
    try {
      const result=await post(Team.cases()+'/'+bundle.report.case_id+'/reports/'+bundle.rev+'/replay',{});
      if (result.report_sha256!==bundle.sha256 || result.case_id!==bundle.report.case_id || result.rev!==bundle.rev)
        throw new Error('返回的复算记录与所选底稿摘要不符。');
      ruleChecks.set(bundle,result);
    } catch (error) {
      ruleChecks.set(bundle,{state:'error',message:error.message});
    }
    if (state.bundle===bundle) $('.rule-replay')?.replaceWith(ruleReplayPanel(bundle));
  });
  button.disabled=check?.state==='running';
  panel.append(button);
  if (!check) return panel;
  const status=el('p','','replay-status'); status.setAttribute('role','status');
  status.textContent=({running:'正在查找摘要匹配的规则源码。',
    verified:'复算一致 · '+check.finding_count+' 项发现 · 底稿建议「'+statusName(check.verdict)+'」',
    unavailable:'无法复算 · '+check.message,mismatch:'复算不一致 · '+check.message,error:check.message})[check.state];
  panel.append(status);
  if (check.checked_at) {
    const fields=[box('line',el('strong','底稿 SHA-256'),el('code',check.report_sha256))];
    if (check.commit) fields.push(box('line',el('strong','匹配规则的 Git 提交'),el('code',check.commit)));
    if (check.findings_sha256) fields.push(box('line',el('strong','审计发现 SHA-256'),el('code',check.findings_sha256)));
    if (check.result_sha256) fields.push(box('line',el('strong','整案建议 SHA-256'),el('code',check.result_sha256)));
    for (const [name,hash] of Object.entries(check.modules || {})) fields.push(box('line',el('strong',name),el('code',hash)));
    panel.append(fold('查看 '+time(check.checked_at)+' 的复算记录',...fields),
      action('下载复算记录',()=>{
        const url=URL.createObjectURL(new Blob([JSON.stringify(check,null,2)+'\n'],{type:'application/json'}));
        const save=link('',url);
        save.download='复算记录-'+check.case_id+'-R'+check.rev+'.json';
        document.body.append(save); save.click(); save.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
      },'text-button'));
  }
  return panel;
}

function installmentDetails(history) {
  const calc = history.calculation;
  if (calc.state!=='calculated') return lazyFold('核对累计范围',()=>[
    el('p',calc.reason),...history.matches.flatMap(m=>m.incomplete_references?.length
      ? m.incomplete_references.flatMap(field=>[
          Team.paperLink(m.title+' · R'+m.rev+' · 流水 '+field.value,m.case_id,'source-jump',new URLSearchParams({rev:m.rev,fact:field.fact})),
          ...(field.notes || []).map(note=>Team.paperLink('展示说明 · '+note.quote,m.case_id,'source-jump',
            new URLSearchParams({rev:m.rev,fact:note.fact})))])
      : [Team.paperLink(m.title+' · R'+m.rev,m.case_id,'source-jump',new URLSearchParams({rev:m.rev}))])]);
  return lazyFold('逐笔复算分期付款',()=>{
    const ledger = box('installment-ledger');
    const display = value=>value.replace(/\B(?=(\d{3})+\.)/g,',')+' 元';
    const positive = !calc.difference.startsWith('-') && calc.difference!=='0.00';
    const totals = box('installment-totals',
      box('',el('small','已见回单累计'),el('strong',display(calc.paid_total),'amount')),
      box('',el('small','合同总额'),el('strong',display(calc.contract_total),'amount'),citation(calc.contract_fact)),
      box(positive?'excess':'',el('small','累计减合同'),el('strong',(positive?'+':'')+display(calc.difference),'amount')));
    ledger.append(totals);
    for (const payment of calc.payments) {
      const row = box('installment-row',box('',el('small',payment.paid_on,'small'),el('strong',payment.reference,'mono')),
        el('strong',display(payment.amount),'amount'),citation(payment.amount_fact));
      if (payment.copies.length) row.append(lazyFold('同一流水的其他回单（'+payment.copies.length+'）',
        ()=>payment.copies.map(citation)));
      ledger.append(row);
    }
    return [ledger];
  });
}

function revealPaperTarget(target) {
  if (!target) return;
  target.dispatchEvent(new Event('reveal-evidence',{bubbles:true}));
  const entry = target.closest('[data-finding]');
  if (entry) {
    if (entry.hidden) entry.dispatchEvent(new Event('reveal-finding', {bubbles:true}));
    entry.querySelector('.finding-disclosure').open = true;
  }
  for (let fold = target.closest('details'); fold; fold = fold.parentElement?.closest('details')) fold.open = true;
  target.focus({preventScroll:true});
  target.scrollIntoView({block:'start'});
}
function evidenceJump(label, targetId) {
  const jump=action(label,()=>revealPaperTarget(document.getElementById(targetId)),'text-button');
  jump.setAttribute('aria-controls',targetId);
  return jump;
}

function showFindingPath(item, compare = false, pair = null) {
  state.traceKey=state.detail.id+'@'+state.bundle.rev; state.traceId=item.id;
  graphIndex(state.bundle.report.graph).graphBrowseMode='findings';
  state.tab='graph'; renderCase(true);
  if (compare) {
    const button=$('.trace-modes:not([hidden]) [data-mode="compare"]');
    if (button) {
      button.click();
      const shortcut=pair && $('.compare-presets [data-pair="'+CSS.escape(pair)+'"]');
      if (shortcut) { shortcut.click(); shortcut.focus(); } else button.focus();
      return;
    }
  }
  $('#trace-select')?.focus();
}

function finding(item) {
  const heading = item.stage ? item.stage.name + (item.stage.share ? ' · ' + item.stage.share + '%' : '') +
    (item.rule === 'H05' ? ' 实付时点' : item.rule==='H06'?' 回单合计':' 付款条件') : item.title;
  const node = box('finding-body',el('p', item.detail, 'finding-detail'),el('p', '执行依据 · ' + item.basis, 'muted'));
  if (item.stage) {
    const change=item.payment_change;
    const revised=change?.applies==='amended' && PhaseEvidence.amendmentFact(state.bundle.report.graph,item,change.revised_ref);
    const originalNumber=ContractFolios.numeralLink(item,state.bundle.report.graph);
    const clause=box('clause-source',el('q',revised?revised.quote:item.stage.clause),originalNumber || citation(revised?revised.id:item.stage.clause_ref));
    if (change && !revised) clause.prepend(el('small','原合同'));
    node.prepend(clause);
  }
  if (item.rule==='H03' && item.payment_change && !item.payment_change.scope_clear) {
    const graph=state.bundle.report.graph;
    const lines=PhaseEvidence.amendmentLines(graph);
    if (lines.length) node.append(lazyFold('核对付款变更原行',()=>lines.map(l=>reservationSource(l,graph))));
  }
  if (item.date_checks) {
    const dates = dateEvidencePanel(item,state.bundle.report.graph);
    if (dates) node.append(dates);
  }
  if (item.reinspection) node.append(evidenceJump('核对整改复验原件','equipment-reinspection-trail'));
  if (item.delegations) node.append(mandatePanel(item.delegations, state.bundle.report.graph));
  if (item.quality_change) node.append(qualityChangePanel(item.quality_change, state.bundle.report.graph));
  if (item.acceptance_authority) node.append(acceptanceAuthorityPanel(item.acceptance_authority, state.bundle.report.graph));
  if (item.effect_review) {
    const clauses=contractEffectPanel(item,state.bundle.report.graph);
    if (clauses) node.append(clauses);
  }
  if (item.warranty_check) {
    node.append(warrantyPanel(item,state.bundle.report.graph));
    const final=state.bundle.report.findings.find(f=>f.batch_acceptance?.separate_final)?.batch_acceptance.separate_final;
    if (final) {
      const links=box('flow',evidenceJump('核对质保起算的终验材料','batch-final-acceptance'));
      if (final.signing_requirement) links.append(evidenceJump('核对终验签字人','batch-signing-final'));
      node.append(links);
    }
  }
  if (item.payment_window) node.append(paymentWindowPanel(item,state.bundle.report.graph));
  if (item.payment_opinion) {
    const graph=state.bundle.report.graph, rows=AcceptanceOpinion.rows(graph,item);
    if (rows.length) node.append(lazyFold('核对付款意见原行',()=>rows.map(row=>AcceptanceOpinion.source(row,graph))));
    const release=ReleaseEvidence.sources(graph,item).filter(s=>!['title','identity'].includes(s.role));
    if (release.length) node.append(lazyFold('核对放行约定、签认及所引原单',()=>release.map(row=>AcceptanceOpinion.source(row,graph))));
  }
  if (item.stage && ['H04','H05'].includes(item.rule)) {
    const batch = state.bundle.report.findings.find(f => f.batch_acceptance)?.batch_acceptance;
    const remarks = phaseRemarks(item, batch, state.bundle.report.graph);
    if (remarks) node.append(remarks);
    const approvals=state.bundle.report.findings.find(f=>f.rule==='H01')?.effect_review?.approval_pages;
    if (approvals?.some(p=>item.evidence.includes(p.doc+'/p'+p.page)))
      node.append(evidenceJump('核对本期所据董事会决议','board-approval-evidence'));
  }
  if (item.acceptance_reservations?.lines.length || item.acceptance_reservations?.mixed_pages.length)
    node.append(reservationPanel(item,state.bundle.report.graph));
  if (item.acceptance_reservations?.supplier) node.append(supplierPanel(item.acceptance_reservations.supplier,state.bundle.report.graph));
  if (item.equipment_models) node.append(equipmentModelsPanel(item.equipment_models,state.bundle.report.graph));
  const exchangeEvidence=paymentExchangeEvidence(item,state.bundle.report);
  if (exchangeEvidence) node.append(exchangeEvidence);
  if (item.stage && /验收|质保|保修/.test(item.stage.clause)) {
    const models=state.bundle.report.findings.find(f=>f.equipment_models)?.equipment_models;
    if (models) {
      const records=models.records.filter(r=>item.scope.includes(r.unit) && r.identity.receipt.some(ref=>item.evidence.includes(ref)));
      if (records.length || !models.records.length) node.append(evidenceJump('核对本期所据的实收型号',
        records.length===1?'equipment-model-'+records[0].unit:'equipment-models'));
    }
  }
  const packets=state.bundle.report.graph.receipt_packet_sources?.packets;
  if (item.rule==='H02' && packets?.length) node.append(receiptPacketPanel(packets,state.bundle.report.graph));
  if (item.batch_acceptance) {
    const {graph,findings}=state.bundle.report;
    node.append(deliveryBatchPanel(item.batch_acceptance,graph,findings.filter(f=>f.rule==='H04')));
  }
  if (item.stage_payments) node.append(stagePaymentsPanel(item,state.bundle.report.graph,state.bundle.report.findings));
  if (item.stage?.batch_index && !item.stage_payments) {
    const {findings}=state.bundle.report;
    const batch=findings.find(f=>f.batch_acceptance)?.batch_acceptance;
    const record=batch?.batches.find(b=>b.index===item.stage.batch_index);
    const sources=(record?.records || []).map(unit=>batch.records.find(r=>r.unit===unit)?.scope_ref).filter(Boolean);
    const evidence=box('flow',el('strong','第'+item.stage.batch_index+'批验收'),el('span',item.stage.batch_date || '合格日期待核','small'));
    if (record) evidence.append(citation(record.clause_ref));
    for (const ref of sources) evidence.append(citation(ref));
    if (record?.signing_requirement) evidence.append(evidenceJump('核对'+record.label+'签认','batch-signing-'+record.index));
    node.append(evidence);
  }
  if (item.rule.startsWith('H')) {
    const comparison = performanceComparison(item,state.bundle.report.graph);
    if (comparison) node.append(comparison);
  }
  if (item.scope.length) node.append(el('small', '检查范围 · ' + item.scope.map(id =>
    state.bundle.report.graph.audit_documents?.find(doc => doc.id === id)?.name ||
    state.detail.documents.find(doc => doc.id === id)?.name || id).join('、'), 'small'));
  if (item.calculations?.length) node.append(fold('查看金额算式与取数依据',
    ...item.calculations.map(calculationPanel)));
  if (item.rule==='B03') {
    const comparison=accountComparison(item,state.bundle.report.graph);
    if (comparison) node.append(comparison);
  }
  if (item.rule==='B08' && state.bundle.report.graph.payment_history?.installments)
    node.append(installmentDetails(state.bundle.report.graph.payment_history.installments));
  if (item.rule==='I02') {
    const index=graphIndex(state.bundle.report.graph);
    const sources=item.evidence.map(id=>index.prior.get(id)).filter(row=>row?.source?.format==='signed-invoice-v1');
    if (sources.length) node.append(lazyFold('核对前案签收依据（'+sources.length+'）',()=>sources.map(row=>
      signedInvoiceSource(row,item.invoice_lookup?.candidates.find(c=>c.id===row.id)?.comparison))));
  }
  if (item.evidence.length) node.append(lazyFold('查看本项全部引文（'+item.evidence.length+'）',()=>[box('chips',...item.evidence.map(citation))]));
  if (graphIndex(state.bundle.report.graph).nodes.has('finding/'+item.id))
    node.append(action('查看证据路径',()=>showFindingPath(item),'text-button'));
  const policy = state.bundle.report.policy;
  const refs = policy.rule_sources?.[item.rule] || [];
  if (refs.length) node.append(fold('核对制度出处与适用范围', ...refs.map(id => sourceEntry(policy.sources[id]))));
  const row = box('finding');
  row.dataset.finding = item.id;
  row.dataset.findingStatus = item.status;
  row.tabIndex = -1;
  const foldout = el('details','','finding-disclosure');
  const summary = el('summary');
  const procedure=el('h3','','procedure-heading');
  procedure.append(el('span',item.rule,'mono procedure-code'), el('span',heading,'procedure-title'), tag(item.status), glyph('chevron-down'));
  summary.append(procedure);
  foldout.append(summary,node);
  row.append(foldout);
  return row;
}
function findingsLedger(report) {
  const panel = box('panel findings-ledger');
  const filters = box('finding-filters');
  filters.setAttribute('role','group'); filters.setAttribute('aria-label','按检查结果筛选');
  const rows = report.findings.map(finding);
  const firstExpert=report.findings.findIndex(f=>f.rule==='X01');
  const expertRows=firstExpert>=0 && report.findings.slice(firstExpert).every(f=>f.rule==='X01') ? rows.slice(firstExpert) : [];
  const group=el('details','','expert-group'), groupCount=el('span','','expert-count');
  if (expertRows.length>1) {
    const header=el('summary');
    header.append(glyph('clipboard-check'),el('strong','专家建议追加核对'),groupCount,glyph('chevron-down'));
    group.append(header,...expertRows);
    const index=graphIndex(report.graph);
    for (const [i,row] of expertRows.entries()) {
      const f=report.findings[firstExpert+i];
      const observation=traceReferences(report.graph,f).map(ref=>index.facts.get(ref)).find(Boolean);
      if (!observation) continue;
      const label=row.querySelector('.procedure-title'), line=observation.source_line?.number;
      label.textContent=observation.name+' · 第 '+observation.page+' 页'+(line?' · 第 '+line+' 行':'');
      label.title=observation.quote;
    }
  }
  const scopes=box('finding-scope');
  scopes.setAttribute('role','group'); scopes.setAttribute('aria-label','检查范围');
  const distribution=box('finding-distribution');
  distribution.setAttribute('aria-hidden','true');
  const countFor=key=>key==='all' ? rows.length : rows.filter(row=>matches(row,key)).length;
  function matches(row,key) {
    return key==='all' || (key==='pending' ? row.dataset.findingStatus!=='ok' : row.dataset.findingStatus===key);
  }
  function select(key) {
    panel.querySelectorAll('[data-finding-filter]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.findingFilter===key)));
    for (const row of rows) row.hidden = !matches(row,key);
    if (expertRows.length>1) {
      const count=expertRows.filter(row=>!row.hidden).length;
      group.hidden=!count;
      groupCount.textContent=count+' 项';
    }
  }
  for (const key of ['pending','all','issue','risk','missing','ok']) {
    const count = countFor(key);
    const label = key==='all' ? '全部' : key==='pending' ? '待处理' : statusName(key);
    const button = action('',()=>select(key));
    button.dataset.findingFilter = key;
    button.append(el('span',label),el('strong',String(count)));
    button.setAttribute('aria-label',label+'，'+count+' 项检查');
    button.disabled = !count;
    if (key==='all' || key==='pending') scopes.append(button);
    else {
      filters.append(button);
      if (count) {
        const segment=el('span');
        segment.dataset.status=key; segment.style.flexGrow=String(count); distribution.append(segment);
      }
    }
  }
  panel.addEventListener('reveal-finding',()=>select('all'));
  const entries=expertRows.length>1 ? [...rows.slice(0,firstExpert),group] : rows;
  panel.append(box('ledger-filter-head',el('h2','检查明细'),scopes),distribution,filters,...entries);
  select(countFor('pending')?'pending':'all');
  return panel;
}
function reportPanel() {
  const report = state.bundle.report;
  const performance = report.findings.filter(item => /^H0[1-6]$/.test(item.rule));
  const verdict = report.result.verdict;
  const mark = box('verdict-symbol',glyph(({pass:'shield-check',reject:'exclamation-diamond',review:'clipboard-check'})[verdict] || 'question-circle'));
  const verdictLine=box('verdict-line',mark,box('verdict-name',el('h2','审计建议'),el('strong',statusName(verdict))));
  appendHumanReview(verdictLine,report.result,'human-required');
  const conclusion = box('panel conclusion-panel',verdictLine);
  conclusion.dataset.verdict = report.result.verdict;
  const priorities = priorityFindings(report.findings);
  if (priorities.length) conclusion.append(priorityQueue(priorities));
  const human = box('panel', el('h2', report.peer_review ? '复核签收决定' : '审计人员验收'));
  const decision = state.detail.decisions.find(item => item.rev === state.bundle.rev);
  if (decision) {
    human.append(el('h3', statusName(decision.decision)), el('p', decision.note),
      el('small', decision.reviewer + ' · ' + time(decision.time), 'small'));
    if (state.bundle.invoice_approval && decision.invoice_check_hash)
      human.append(invoiceApproval(state.bundle.invoice_approval,decision.invoice_check_hash));
  } else if (state.detail.status === 'ready' && state.detail.rev === state.bundle.rev) {
    human.append(action('填写验收意见', () => openReview(null), 'primary'));
  } else human.append(el('p', '此为历史底稿，保留当时的审计建议。', 'muted'));
  const working = box('panel', el('h3', '底稿留存'), el('p', 'R' + state.bundle.rev + ' · ' + time(state.bundle.created), 'muted'),
    link('下载底稿及证据包', base() + '/reports/' + state.bundle.rev + '/bundle', 'button'),
    fold('底稿 SHA-256', el('code', state.bundle.sha256)));
  const review = box('', conclusion);
  if (report.supplement) review.append(returnComparison(report,state.bundle.rev));
  if (performance.length) {
    const heading=box('performance-heading',el('h2','合同履约审查'));
    const acceptance=performance.find(f=>f.rule==='H02');
    const index=graphIndex(report.graph);
    if (acceptance && index.nodes.has('finding/'+acceptance.id) &&
        traceReferences(report.graph,acceptance).filter(ref=>index.facts.has(ref)).length>=2) {
      const compare=action('对照验收原件',()=>showFindingPath(acceptance,true),'compare-jump');
      compare.prepend(glyph('layout-sidebar-inset-reverse')); heading.append(compare);
    }
    const conditions = box('panel performance-panel',heading);
    conditions.append(performanceOverview(performance,report.graph));
    review.append(conditions);
  }
  review.append(findingsLedger(report));
  const side = box('paper-side', human);
  const peer = PeerReview.panel(state.detail,state.bundle);
  if (peer) side.append(peer);
  side.append(working);
  return box('grid workpaper-grid', review, side);
}
function graphPanel() {
  return EntityBrowser.views(state.bundle.report, graphRelations);
}
function graphRelations(report) {
  const graph = report.graph;
  const {nodes,facts} = graphIndex(graph);
  const docIds = new Set((graph.audit_documents || graph.documents).map(doc => doc.id));
  const relations = graph.edges.filter(edge => docIds.has(edge.from) && !['contains','section_page','acceptance_reservation','acceptance_payment_opinion','payment_release_basis','supplier_identity_basis','delivery_quantity_basis','stage_invoice_clause','payment_amendment_basis'].includes(edge.type));
  const panel = box('panel', el('h2', '本案证据关系'), el('p', graph.nodes.length + ' 个节点 · ' +
    graph.edges.length + ' 条关系 · ' + graph.facts.length + ' 条提取记录', 'muted'));
  const grouped = new Map();
  const signing=SigningParties.relations(report.findings.find(f=>f.rule==='H01'),graph);
  if (signing) panel.append(signing);
  const opinions=AcceptanceOpinion.rows(graph);
  const released=ReleaseEvidence.sources(graph).filter(s=>!['title','identity'].includes(s.role));
  if (released.length) {
    const list=lazyFold('验收款暂缓与放行依据（'+released.length+'）',()=>released.map(s=>AcceptanceOpinion.source(s,graph)));
    list.classList.add('release-relations'); panel.append(list);
  }
  if (opinions.length) {
    const list=lazyFold('验收原件上的付款意见（'+opinions.length+'）',()=>opinions.map(row=>AcceptanceOpinion.source(row,graph)));
    list.classList.add('opinion-relations'); panel.append(list);
  }
  const changeTerms=PhaseEvidence.amendmentLines(graph);
  if (changeTerms.length) {
    const list=lazyFold('付款条款变更所据原行（'+changeTerms.length+'）',()=>changeTerms.map(row=>reservationSource(row,graph)));
    list.classList.add('payment-amendment-relations'); panel.append(list);
  }
  const receiptTerms=graph.invoice_receipt_sources?.lines.filter(row=>row.role==='clause');
  if (receiptTerms?.length) {
    const list=lazyFold('合同收票条款（'+receiptTerms.length+'）',()=>receiptTerms.map(row=>reservationSource(row,graph)));
    list.classList.add('invoice-clause-relations'); panel.append(list);
  }
  const reservations=graph.acceptance_reservation_sources?.lines;
  if (reservations?.length) {
    const list=lazyFold('验收保留意见与签收原页（'+reservations.length+'）',()=>reservations.map(line=>reservationSource(line,graph)));
    list.classList.add('reservation-relations');
    panel.append(list);
  }
  const supplierRows=graph.acceptance_reservation_sources?.supplier_rows;
  const modelLines=graph.equipment_model_sources?.lines;
  if (modelLines?.length) {
    const relations=graph.edges.filter(e=>e.type==='equipment_model_comparison');
    const list=lazyFold('设备型号与验收原行（'+modelLines.length+'）',()=>{
      const paired=new Set();
      const rows=relations.map(e=>{
        const row=box('line',box('flow',el('strong','约定与实收型号'),tag(e.status)));
        row.dataset.modelRelation=e.to;
        for (const [page,line] of [[e.from,e.ordered_line],[e.to,e.received_line]]) {
          const source=modelLines.find(s=>s.doc+'/p'+s.page===page && s.line===line);
          if (source) {
            paired.add(source);
            row.append(reservationSource(source,graph));
          }
        }
        return row;
      });
      return [...rows,...modelLines.filter(line=>!paired.has(line)).map(line=>reservationSource(line,graph))];
    });
    list.classList.add('equipment-model-relations');
    panel.append(list);
  }
  const exchangeCheck=report.findings.find(f=>f.equipment_models?.exchange)?.equipment_models;
  if (exchangeCheck) {
    const list=lazyFold('设备退回与换入的证据路径',()=>{
      const links=graph.edges.filter(e=>['equipment_exchange_returned','equipment_exchange_received'].includes(e.type));
      const rows=links.map(edge=>{
        const label=edge.type==='equipment_exchange_returned'?'初验清单与交接退回清单':'交接换入清单与复验清单';
        const row=box('line',box('flow',el('strong',label),tag(edge.status)),box('chips',citation(edge.from),citation(edge.to)));
        row.dataset.exchangeRelation=edge.type;
        return row;
      });
      if (!rows.length) rows.push(el('p','交接单的归属或所据单号待核。','muted'));
      return [...rows,exchangeSerialLists(exchangeCheck,graph)];
    });
    list.classList.add('equipment-exchange-relations');
    panel.append(list);
  }
  if (supplierRows?.length) {
    const list=lazyFold('供应方与交付原件（'+supplierRows.length+'）',()=>supplierRows.map(s=>reservationSource(s,graph)));
    list.classList.add('supplier-relations');
    panel.append(list);
  }
  const comparisons=graph.edges.filter(e=>e.type==='payment_window_comparison');
  const operands=graph.edges.filter(e=>e.type==='stage_transfer_operand');
  if (operands.length) {
    const list=lazyFold('本期约定与计入的流水（'+operands.length+'）',()=>operands.map(edge=>{
      const row=box('line');
      row.dataset.stageTransfer=edge.to;
      for (const ref of edge.evidence) row.append(box('batch-source',el('q',facts.get(ref).quote),citation(ref)));
      return row;
    }));
    list.classList.add('stage-transfer-relations');
    panel.append(list);
  }
  const countLines=graph.quality_addenda?.quantities?.lines;
  if (countLines?.length) {
    const list=lazyFold('交付数量变更与验收原行（'+countLines.length+'）',()=>countLines.map(line=>reservationSource(line,graph)));
    list.classList.add('quantity-relations');
    panel.append(list);
  }
  if (comparisons.length) {
    const list=lazyFold('付款期限与实付凭据（'+comparisons.length+'）',()=>comparisons.map(edge=>{
      const row=box('line',el('strong',({within:'期内付款',early:'早于起算日',late:'晚于付款末日',same_day:'同日待核时分',extension_unknown:'顺延口径待核'})[edge.outcome]));
      for (const id of [edge.from,edge.to]) row.append(box('batch-source',el('q',facts.get(id).quote),citation(id)));
      row.dataset.windowWitness=edge.from+'>'+edge.to;
      return row;
    }));
    list.classList.add('payment-window-relations');
    panel.append(list);
  }
  const warranties=graph.edges.filter(e=>e.type==='warranty_release_basis');
  if (warranties.length) {
    const links=lazyFold('质保金期次与期满确认（'+warranties.length+'）',()=>warranties.map(edge=>{
      const row=box('line');
      for (const id of [edge.from,edge.to]) row.append(box('batch-source',el('q',facts.get(id).quote),citation(id)));
      row.dataset.warrantyWitness=edge.from+'>'+edge.to;
      return row;
    }));
    links.classList.add('warranty-relations');
    panel.append(links);
  }
  const receiptEdges=graph.edges.filter(e=>e.type==='acceptance_page_identity');
  if (receiptEdges.length) {
    const nodes=graphIndex(graph).nodes;
    const list=lazyFold('验收单与原件页码（'+receiptEdges.length+'）',()=>receiptEdges.map(edge=>{
      const row=box('line',el('strong',nodes.get(edge.from).label),reservationSource({
        ...facts.get(edge.to),line:facts.get(edge.to).source_line.number,facts:[edge.to]},graph));
      row.dataset.packetWitness=edge.to;
      return row;
    }));
    list.classList.add('packet-relations');
    panel.append(list);
  }
  const batchLabels={delivery_batch_acceptance:'约定交付范围',batch_payment_basis:'本期付款条件',
    batch_named_signature:'本批指定人员与实际签认',batch_final_basis:'终验单引用的批次验收原件',
    final_named_signature:'合同指定的终验人与总单签字'};
  const batchEdges=graph.edges.filter(e=>Object.hasOwn(batchLabels,e.type));
  if (batchEdges.length) {
    const title=batchEdges.some(e=>e.type==='batch_final_basis')?'分批验收、终验与付款依据':'分批验收与付款依据';
    const list=lazyFold(title+'（'+batchEdges.length+'）',()=>batchEdges.map(edge=>{
      const row=box('line',el('strong',batchLabels[edge.type]),
        box('batch-source',el('q',facts.get(edge.from).quote),citation(edge.from)),
        box('batch-source',el('q',facts.get(edge.to).quote),citation(edge.to)));
      row.dataset.batchWitness=edge.from+'>'+edge.to;
      return row;
    }));
    list.classList.add('batch-relations');
    panel.append(list);
  }
  const remarkEdges=graph.edges.filter(e => ['batch_payment_hold','batch_inspection_note'].includes(e.type));
  if (remarkEdges.length) {
    const list=lazyFold('期款与验收备注（'+remarkEdges.length+'）',()=>remarkEdges.map(edge=>{
      const source=graph.delivery_batch_sources.remarks.find(r=>r.doc+'/p'+r.page===edge.to && r.line===edge.line && r.facts.every(ref=>edge.evidence.includes(ref)));
      const row=box('line',el('strong',edge.type==='batch_payment_hold'?'期款所据付款意见':'本批验收范围'),
        box('batch-source',el('q',facts.get(edge.from).quote),citation(edge.from)),reservationSource(source,graph));
      row.dataset.batchRemark=edge.from;
      return row;
    }));
    list.classList.add('batch-remark-relations');
    panel.append(list);
  }
  const signers = graph.edges.filter(edge=>edge.type==='named_acceptance_signature');
  if (signers.length) {
    const list=lazyFold('合同约定与签认关系（'+signers.length+'）',()=>signers.map(edge=>{
      const row=box('line',box('change-source',el('q',facts.get(edge.from).quote),citation(edge.from)),
        box('change-source',el('q',facts.get(edge.to).quote),citation(edge.to)));
      row.dataset.signerWitness=edge.to;
      return row;
    }));
    list.classList.add('signature-relations');
    panel.append(list);
  }
  if (graph.audit_documents) panel.append(fold('合订资料的原页归属', ...graph.audit_documents.filter(doc => doc.source)
    .map(doc => box('line', el('strong', doc.name), citation(doc.source + '/p' + doc.page)))));
  for (const edge of relations) {
    if (!grouped.has(edge.to)) grouped.set(edge.to, []);
    grouped.get(edge.to).push(edge);
  }
  const groups = [...grouped].sort((left, right) => right[1].length - left[1].length);
  if (groups.length) panel.append(lazyFold('查看实体与单据关联（'+groups.length+'）',()=>groups.map(([target, edges])=>
    lazyFold((edges[0].type.startsWith('incomplete_') ? facts.get(target).value+' · 号码待补全' : nodes.get(target).label)+' · '+edges.length+' 条关联',()=>edges.map(edge=>box('line',
      el('strong',nodes.get(edge.from).label),el('span','记载'+(facts.get(edge.evidence[0])?.label || edge.type)),
      box('chips',...edge.evidence.map(citation))))))));
  if (!groups.length) panel.append(el('p', '请在原件与引文中核对待确认记录，核图后系统会重建关系。'));
  if (graph.prior_invoices?.length) panel.append(lazyFold('跨案同号记录', ()=>graph.prior_invoices.map(row =>
    row.source?.format==='signed-invoice-v1' ? signedInvoiceSource(row) : box('line', Team.paperLink(row.title+' · R'+row.rev,row.case_id,'case-link',new URLSearchParams({rev:row.rev,fact:row.fact})), el('p', '历史人工决定 · ' + statusName(row.decision) + ' · ' +
      (row.document_kind === 'unclassified' ? '原资料类型待核' : '发票')),
      el('blockquote', row.quote), citation(row.id), el('small', '历史底稿 SHA-256 · ' + row.report_hash, 'small'),
      ...(row.signoff_hash ? [el('small','人工签收 SHA-256 · '+row.signoff_hash,'small')] : [])))));
  if (graph.payment_history) {
    const history = graph.payment_history;
    const comparison = (rule,kind,label) => report.findings.find(f=>f.rule===rule)?.status==='missing'
      ? label+'待补证' : label+'命中 '+history.counts[kind]+' 份';
    const matches = history.matches.map(match=>lazyFold(match.title+' · R'+match.rev,()=>[
      el('p',(match.kind==='same'?'相同付款户名与流水':'同合同的另一笔全额流水')+' · '+statusName(match.decision)+' · '+time(match.signed_at)+' 签收'),
      ...match.evidence.map(f=>box('trace-quote',citation(f.id),el('blockquote',f.quote))),
      el('small','历史底稿 SHA-256 · '+match.report_hash,'small')]));
    panel.append(fold('已签收付款底稿核查', el('p','截至 '+time(history.as_of)+'，'+comparison('B06','same','相同流水')+
      '，'+comparison('B07','full','同合同其他全额流水')+'。'),...matches));
  }
  if (graph.cautions?.length) panel.append(fold('原文中的结算及变更线索', ...graph.cautions.map(item =>
    box('line', el('blockquote', item.quote), el('span', '文字层第 ' + item.line + ' 行'), citation(item.page_id)))));
  if (graph.gaps.length) panel.append(fold('辨读与覆盖缺口', ...graph.gaps.map(item =>
    box('line', el('span', item.quality==='receipt_packet'?'验收单归属待核':item.quality === 'uncovered_title' ? '页首标题尚待核图补录' : item.quote ? '文字层第 ' + item.line + ' 行尚缺完整取值' :
      (item.quality === 'section_unresolved' ? '本页的单据归属待核对' : '页图存在辨读或提取缺口')),
      el('blockquote', item.quote || item.detail || '请查看原件或补传清晰资料。'), citation(item.id)))));
  panel.append(lazyFold('资料、页与观察记录的溯源关系', ()=>graph.edges.filter(edge => ['contains','records'].includes(edge.type))
    .map(edge => box('line', el('code', edge.from + ' → ' + edge.to), box('chips', ...edge.evidence.map(citation))))));
  return panel;
}
function activityPanel() {
  const log = box('panel', el('h2', '处理进度记录'));
  for (const entry of [...state.detail.events].reverse()) {
    log.append(box('line', el('strong', time(entry.time), 'mono'), el('span', entry.message)));
  }
  const bundle = state.bundle;
  if (!bundle) return log;
  const calls = bundle.report.calls;
  const panel = box('panel', el('h2', '本版模型调用'), el('p', '可检查模型、请求摘要、结构化输出与证据编号。', 'muted'));
  for (const trace of [...calls.pages, calls.expert]) {
    const title = trace.doc ? trace.doc + ' 第 ' + trace.page + ' 页' : '专家追加程序';
    panel.append(fold(title + ' · ' + trace.model, el('pre', JSON.stringify(trace, null, 2))));
  }
  const prompts = Object.entries(calls.instructions || {});
  if (prompts.length) panel.append(fold('查看本版留存的模型指令', ...prompts.map(([hash, prompt]) =>
    box('line', el('code', hash), el('pre', prompt)))));
  const policy = bundle.report.policy;
  const methods = Object.entries(policy.code_sha256 || {});
  if (methods.length) panel.append(fold('执行程序与版本摘要', ...methods.map(([name, hash]) => {
    let file = el('strong', name);
    if (policy.archived_methods) {
      file = link(name, base() + '/reports/' + bundle.rev + '/methods/' + encodeURIComponent(name));
      file.target = '_blank'; file.rel = 'noopener';
    }
    return box('line', file, el('code', hash, 'small'));
  })));
  panel.append(el('p', '规则集版本 ' + bundle.report.policy.version, 'small'));
  if (state.detail.status === 'ready' && state.detail.rev === bundle.rev) {
    panel.append(action('保留此版并重新审计', async event => {
      event.currentTarget.disabled = true;
      try { await post(base() + '/rerun', {rev: bundle.rev}); chooseRevision(); await refresh(); }
      catch (error) { alertText(error); await refresh(); }
    }));
  }
  return box('', ruleReplayPanel(bundle), panel, log);
}
function paperViewContext(data, rev) {
  const canReview = data.status === 'ready' && data.rev === rev;
  switch (state.tab) {
    case 'report':
      return JSON.stringify([canReview, data.decisions.find(row => row.rev === rev),
        data.referrals?.find(row => row.rev === rev), Team.current?.role, Team.session.user?.id]);
    case 'activity':
      return JSON.stringify([canReview, data.events.at(-1)?.seq]);
    case 'evidence':
      return JSON.stringify(data.documents);
    default:
      return '';
  }
}
function renderCase(forcePanel = false) {
  const data = state.detail;
  $('#case-title').textContent = data.title;
  $('#case-meta').textContent = profileName(data.profile) + ' · ' + time(data.created) + ' 提交';
  $('#case-status').replaceChildren(tag(data.status));
  const progress = $('#progress-panel');
  progress.hidden = !!state.bundle && ['ready','closed','in_review'].includes(data.status) && !data.error && !data.waiting_for_database;
  progress.replaceChildren(box('panel-head', el('strong', statusName(data.stage)), el('span', data.progress + '%', 'mono')));
  const meter = el('progress'); meter.max = 100; meter.value = data.progress; meter.setAttribute('aria-label','审计任务进度');
  progress.append(meter, el('p', data.message, 'muted'));
  if (data.waiting_for_database) progress.append(el('p','后台任务正在等待数据库写入，解除占用后会继续。','note'));
  if (data.status === 'queued' || data.status === 'running') {
    const steps = ['prepare','extract','graph','controls','expert'];
    const position = steps.indexOf(data.stage);
    const timeline = el('ol','','stage-track');
    timeline.setAttribute('aria-label','审计执行阶段');
    for (const [index,key] of steps.entries()) {
      const step = el('li', statusName(key), index < position ? 'done' : '');
      if (index === position) step.setAttribute('aria-current','step');
      timeline.append(step);
    }
    progress.append(timeline);
  }
  if (data.error) {
    progress.append(el('p', data.error));
    if (data.can_review !== false) progress.append(action('从检查点重试', async () => {
      try { await post(base() + '/retry', {}); await refresh(); } catch (error) { alertText(error); }
    }));
  }
  const bundle = state.bundle;
  PageProgress.render(data,bundle?.rev);
  renderSupplementFamily(data,bundle?.rev);
  $('#report-tools').hidden = !bundle;
  if (!bundle) {
    displayedPaper = null;
    const content = [sourceList(), activityPanel()];
    const decision = data.decisions?.at(-1);
    if (decision) content.unshift(box('panel',el('h2','验收决定'),tag(decision.decision),el('p',decision.note)));
    $('#case-panel').replaceChildren(...content); return;
  }
  const nav = $('#tabs');
  if (!nav.childElementCount) {
    const icons = {report:'card-checklist', evidence:'file-earmark-text', graph:'diagram-3', activity:'clock-history'};
    for (const [id, label] of Object.entries(tabs)) {
      const button = action(label, () => { state.tab = id; renderCase(); });
      button.prepend(glyph(icons[id]));
      button.dataset.tab = id; nav.append(button);
    }
  }
  for (const button of nav.children) button.setAttribute('aria-pressed', String(state.tab === button.dataset.tab));
  const versions = $('#version');
  if (versions.length !== data.revisions.length || data.revisions.some((row, i) => versions.options[i].value !== String(row.rev))) {
    versions.replaceChildren(...data.revisions.map(row => new Option('R' + row.rev, row.rev)));
  }
  if (versions.value !== String(bundle.rev)) versions.value = String(bundle.rev);
  const context = paperViewContext(data, bundle.rev);
  if (!forcePanel && displayedPaper?.bundle === bundle && displayedPaper.tab === state.tab && displayedPaper.context === context) return;
  const panel = {report: reportPanel, evidence: sourceList, graph: graphPanel, activity: activityPanel}[state.tab]();
  $('#case-panel').replaceChildren(panel);
  displayedPaper = {bundle, tab: state.tab, context};
}
function clearCaseView() {
  state.detail = null; state.bundle = null;
  displayedPaper = null;
  PageProgress.reset();
  $('#supplement-family').hidden = true; $('#supplement-family').replaceChildren();
  for (const id of ['case-panel','case-title','case-meta','case-status','progress-panel','page-content'])
    $('#'+id).replaceChildren();
  $('#report-tools').hidden = true;
}
async function refresh() {
  const epoch = ++state.epoch;
  clearTimeout(state.timer);
  const route = Team.route();
  let interval = 0;
  try {
    if (!Team.session) await Team.load();
    if (epoch !== state.epoch) return;
    const session = Team.session;
    Team.current = session.workspaces.find(w => w.id === route.id) || null;
    const match = /^case\/([a-f0-9]{32})$/.exec(route.page);
    const invite = /^invite\/([A-Za-z0-9_-]{20,128})$/.exec(route.page)?.[1];
    let view = match ? 'case' : (['rules','account','team','library'].includes(route.page) ? route.page : 'desk');
    if (invite) view = 'account';
    if (route.id && !Team.current) {
      if (!session.user) Team.returnTo = location.hash;
      view = 'account';
    } else if (!route.id && session.mode === 'saas' && view !== 'account' && (view !== 'rules' || session.user)) {
      if (session.workspaces.length) { location.replace(Team.hash('w/'+session.workspaces[0].id+'/'+route.page)); return; }
      view = 'account';
    }
    if (view === 'team' && Team.current?.role !== 'admin') view = 'account';
    if (view === 'library' && Team.current?.role === 'employee') view = 'desk';
    Team.syncNav();
    for (const id of ['desk','rules','case','account','team','library']) $('#'+id).hidden = id !== view;
    for (const id of ['desk','rules','team','account','library']) {
      const nav = $('#nav-' + id);
      if (id === (view === 'case' ? 'desk' : view)) nav.setAttribute('aria-current','page');
      else nav.removeAttribute('aria-current');
    }
    if (view === 'account') { Team.account(invite); $('#network-error').hidden=true; return; }
    if (view === 'library') { await Desk.library(epoch); if (epoch === state.epoch) $('#network-error').hidden=true; return; }
    if (view === 'team') { await Team.team(epoch); if (epoch === state.epoch) $('#network-error').hidden=true; return; }
    if (view === 'case') {
      const data = await api(Team.cases() + '/' + match[1]);
      if (epoch !== state.epoch) return;
      const requested = Number(route.params.get('rev'));
      const rev = data.can_review === false ? 0 : (state.pinned || (Number.isSafeInteger(requested) && requested>0 ? requested : data.rev));
      let bundle = state.bundle;
      const approved = data.decisions?.find(d=>d.rev===rev)?.invoice_check_hash;
      if (rev && (bundle?.rev !== rev || bundle.report.case_id !== data.id || (approved && !bundle.invoice_approval)))
        bundle = await api(Team.cases() + '/' + data.id + '/reports/' + rev);
      if (epoch !== state.epoch) return;
      state.detail = data; state.bundle = rev ? bundle : null;
      const requestedFinding = route.params.get('finding');
      let focusFinding;
      if (requestedFinding && state.openedCitation!==location.hash && state.bundle?.report.findings.some(f=>f.id===requestedFinding)) {
        state.openedCitation=location.hash; state.traceKey=data.id+'@'+rev; state.traceId=requestedFinding;
        const traced = graphIndex(bundle.report.graph).nodes.has('finding/'+requestedFinding);
        if (traced) graphIndex(bundle.report.graph).graphBrowseMode='findings';
        state.tab=traced?'graph':'report'; focusFinding=traced?'#trace-select':'[data-finding="'+requestedFinding+'"]';
      } else if (route.params.get('view')==='replay' && state.openedCitation!==location.hash && state.bundle) {
        state.openedCitation=location.hash; state.tab='activity'; focusFinding='.rule-replay button';
      } else if (['reinspection','trial'].includes(route.params.get('view')) && state.openedCitation!==location.hash &&
                 bundle?.report.findings.some(f=>f.rule==='H02' && f.reinspection)) {
        state.openedCitation=location.hash; state.tab='report'; focusFinding='#equipment-reinspection-trail';
      } else if (route.params.get('view')==='contract-pages' && state.openedCitation!==location.hash &&
                 bundle?.report.findings.some(f=>f.rule==='H03' && f.contract_folios)) {
        state.openedCitation=location.hash; state.tab='report'; focusFinding='#contract-pages';
      } else if (route.params.get('view')==='signatures' && state.openedCitation!==location.hash &&
                 bundle?.report.findings.some(f=>f.rule==='H01' && f.effect_review?.word_signatures)) {
        state.openedCitation=location.hash; state.tab='report'; focusFinding='#word-signatures';
      } else if (route.params.get('view')==='calendar' && state.openedCitation!==location.hash &&
                 bundle?.report.findings.some(f=>f.rule==='H01' && f.effect_review?.calendar?.length)) {
        state.openedCitation=location.hash; state.tab='report'; focusFinding='#contract-calendar';
      } else if (route.params.get('view')==='entities' && state.openedCitation!==location.hash && state.bundle) {
        state.openedCitation=location.hash; state.tab='graph';
        graphIndex(bundle.report.graph).graphBrowseMode='entities'; focusFinding='#case-entity-browser';
      }
      renderCase(Boolean(focusFinding));
      if (focusFinding) {
        const target = $(focusFinding);
        if (target?.id==='equipment-reinspection-trail' && route.params.get('view')==='trial' &&
            bundle.report.findings.some(f=>f.reinspection?.timing?.operation)) {
          target.open=true;
          $('#trail-tab-final')?.click();
          revealPaperTarget($('#reinspection-wait'));
        } else if (target?.dataset.finding || ['equipment-reinspection-trail','case-entity-browser','contract-pages','word-signatures','contract-calendar'].includes(target?.id)) revealPaperTarget(target);
        else target?.focus();
      }
      const target = route.params.get('fact');
      if (target && state.openedCitation !== location.hash && state.bundle) {
        const fact = state.bundle.report.graph.facts.find(f => f.id === target);
        if (fact) { state.openedCitation = location.hash; openPage(fact.doc,fact.page,fact.id); }
      }
      if (['queued','running'].includes(data.status)) interval = 1600;
      if (data.status === 'in_review') interval = 6000;
    } else if (view === 'rules') {
      const data = await api('/api/controls'); if (epoch !== state.epoch) return; renderCatalog(data);
    } else {
      await Desk.load(epoch); if (epoch !== state.epoch) return; interval = 5000;
      const entry=new URL(location.href);
      if (entry.searchParams.get('new')==='contract') {
        entry.searchParams.delete('new');
        history.replaceState(history.state,'',entry);
        openIntake();
        scopeSelect.value=performanceProfile;
        profileChanged();
      }
    }
    $('#network-error').hidden = true;
    if ($('#connection').textContent === '连接中断') checkConnection();
  } catch (error) {
    if (epoch !== state.epoch) return;
    if ([401,403,404].includes(error.status)) {
      clearCaseView(); Desk.reset(); state.cases=[];
      for (const id of ['case-panel','case-list','team-panel']) $('#'+id).replaceChildren();
      if (error.status === 401 || error.status === 403) {
        Team.session=null; resetIntake();
        for (const dialog of document.querySelectorAll('dialog[open]')) dialog.close();
      }
    }
    alertText(error); interval = 5000;
  }
  if (interval && epoch === state.epoch) state.timer = setTimeout(refresh, interval);
}
function chooseRevision(rev = 0) {
  state.pinned = rev;
  history.replaceState(null,'',Team.hash('case/'+state.detail.id+(rev ? '?rev='+rev : '')));
}
function showPaymentSourceError(container, problem) {
  const source=problem.paymentSource;
  const params=new URLSearchParams({rev:String(source.rev)});
  if (source.fact) params.set('fact',source.fact);
  const anchor=Team.paperLink('查看 R'+source.rev+' 所据底稿',source.case_id,'source-jump',params);
  anchor.target='_blank'; anchor.rel='noopener';
  container.replaceChildren(el('strong',problem.message),anchor);
}

function showInvoiceReviewConflict(container,problem,choice) {
  const history = problem.invoiceHistory;
  choice.querySelector('option[value="approve"]').disabled=true;
  choice.value='';
  const list = el('ul','','invoice-changes');
  const partial=problem.incompleteNumbers;
  if (partial) {
    for (const field of partial.facts) {
      const params=new URLSearchParams({rev:String(partial.rev),fact:field.fact});
      const anchor=Team.paperLink('查看 R'+partial.rev+' 第 '+field.page+' 页原文',partial.case_id,'source-jump',params);
      anchor.target='_blank'; anchor.rel='noopener';
      const row=el('li');
      row.append(el('strong',field.value),anchor);
      for (const line of field.lines || []) row.append(el('small','第 '+line.number+' 行 · '+line.text,'small'));
      for (const note of field.notes || []) {
        const source=Team.paperLink('展示说明 · '+note.quote,partial.case_id,'source-jump',new URLSearchParams({rev:partial.rev,fact:note.fact}));
        source.target='_blank'; source.rel='noopener';
        row.append(source,tag(note.status));
      }
      list.append(row);
    }
    container.replaceChildren(el('strong',problem.message),list);
    if (partial.count>partial.facts.length) container.append(el('p','本版共 '+partial.count+' 处号码待补全。','small'));
    return;
  }
  const source = (item,label)=>{
    const params = new URLSearchParams({rev:String(item.rev),fact:item.fact});
    const anchor = Team.paperLink(label+' · '+item.title+' R'+item.rev+' · '+statusName(item.decision),item.case_id,'source-jump',params);
    anchor.target='_blank'; anchor.rel='noopener';
    return anchor;
  };
  for (const {previous,current} of history.changes) {
    const row = el('li');
    row.append(el('strong',(current || previous).quote));
    if (previous) row.append(source(previous,'原引版本'));
    if (current) row.append(source(current,previous?'最新签收':'新增签收'));
    list.append(row);
  }
  container.replaceChildren(el('strong',problem.message),list);
  if (history.count>history.changes.length)
    container.append(el('p','显示 '+history.changes.length+' / '+history.count+' 处变化，重新审计可核对全部匹配。','small'));
}
function canReviewCurrentPaper() {
  return state.detail?.status==='ready' && state.detail.rev===state.bundle?.rev &&
    (!Team.current || ['admin','auditor'].includes(Team.current.role));
}
function draftSupplement(note) {
  if (!canReviewCurrentPaper()) return;
  openReview();
  const decision=$('#review-decision');
  decision.value='return'; decision.dispatchEvent(new Event('change'));
  $('#review-note').value=note;
  $('#review-note').focus();
}
function openReview(facts,reviewVisibility=false) {
  state.review = {id: state.detail.id, rev: state.bundle.rev, facts};
  $('#review-error').textContent = '';
  $('#review-title').textContent = facts ? '记录原图核验' : '人工验收';
  $('#review-context').textContent = state.detail.title + ' · R' + state.bundle.rev + ' · ' +
    (facts ? facts.join('、') : '系统' + statusName(state.bundle.report.result.verdict));
  const select = $('#review-decision'); select.replaceChildren();
  const choices = facts ? {confirm:'已对照原图，所选引文准确', dispute:'引文或字段有异议'} :
    {approve:'通过', return:'退回补件', escalate:'提交复核'};
  select.add(new Option('请选择决定', '', true, true)); select.required = true;
  for (const [value, label] of Object.entries(choices)) select.add(new Option(label, value));
  if (reviewVisibility) select.value='confirm';
  const visibility=$('#review-visibility');
  visibility.replaceChildren();
  const graph=state.bundle.report.graph;
  if (facts && graph.profile==='cn-bank-contract-payment/v1') {
    for (const fact of graph.facts.filter(f=>facts.includes(f.id) && f.field==='transfer_ref')) {
      const page=graph.nodes.find(n=>n.id===fact.doc+'/p'+fact.page);
      if (page?.layer==='text' && fact.source_line?.rects?.length) continue;
      const input=el('select');
      input.dataset.reference=fact.id;
      input.add(new Option('仅核对栏内字符',''));
      const limited=graph.transfer_references?.facts.find(m=>m.fact===fact.id);
      const whole=new Option('已核对整页，流水号完整显示','complete');
      whole.disabled=!!limited && (!['visibility_unchecked','reviewed_partial'].includes(limited.state) || !!limited.notes?.length || !!limited.lines?.length);
      input.add(whole);
      input.add(new Option('已核对整页，流水号仅部分显示','partial'));
      const label=el('label','流水 '+fact.value+' · 展示范围');
      label.append(input);
      const original=link('重新查看第 '+fact.page+' 页整张回单',workpaperSource(fact.doc,'pages/'+fact.page),'source-jump');
      original.target='_blank'; original.rel='noopener';
      visibility.append(label,original);
    }
  }
  const updateVisibility=()=>{visibility.hidden=!visibility.childElementCount || select.value!=='confirm';};
  select.onchange=updateVisibility;
  updateVisibility();
  $('#reviewer').value=Team.current ? Team.session.user.name : ''; $('#reviewer').readOnly=!!Team.current;
  $('#review-note').value = '';
  $('#review-dialog').showModal();
}
async function openAmend(doc, page, fact, printed) {
  try {
    state.fields ||= (await api('/api/controls')).fields;
    const current = state.detail;
    state.amend = {id:current.id, rev:state.bundle.rev, doc, page, target:fact?.id || null};
    $('#amend-form').reset();
    $('#amend-reviewer').value=Team.current ? Team.session.user.name : ''; $('#amend-reviewer').readOnly=!!Team.current;
    $('#amend-error').textContent = '';
    $('#amend-title').textContent = fact ? '核图更正字段' : '核图补录字段';
    const image = el('img','','page-image');
    image.id = 'amend-image'; image.alt = '本次核对的原页';
    $('#amend-image').replaceWith(image);
    const source = workpaperSource(doc,'pages/'+page);
    const submit = $('#amend-submit'); submit.disabled = true;
    const item = current.documents.find(item => item.id === doc);
    const line=fact?.doc===doc && fact.page===page && (!printed || printed.quote===fact.source_line?.text) ? fact.source_line : null;
    const marks=$('#amend-marks'), pane=$('#amend-original');
    markPageRects(marks,line?.rects || []);
    image.alt=item.name+' 第 '+page+' 页';
    $('#amend-context').textContent = item.name + ' · 第 ' + page + ' 页' + (marks.childElementCount?' · 第 '+line.number+' 行':'') + ' · 底稿 R' + state.bundle.rev;
    pane.setAttribute('aria-label',$('#amend-context').textContent+'，更正所据原页');
    const select = $('#amend-field'); select.replaceChildren(new Option('请选择字段', ''));
    for (const [key, label] of Object.entries(state.fields)) select.add(new Option(label, key));
    select.value = printed?.field || fact?.field || '';
    $('#amend-quote').value = printed?.quote || fact?.quote || '';
    $('#amend-value').value = printed ? '' : (fact?.value || '');
    $('#amend-region').value = fact?.region || 'top';
    $('#page-dialog').close();
    $('#amend-dialog').showModal();
    try {
      await loadReviewImage(image,source);
      if (image.isConnected) {
        submit.disabled = false;
        const mark=marks.firstElementChild?.getBoundingClientRect(), area=pane.getBoundingClientRect();
        if (mark && pane.scrollHeight>pane.clientHeight)
          pane.scrollTop+=(mark.top+mark.bottom-area.top-area.bottom)/2;
      }
    } catch {
      if (image.isConnected) $('#amend-error').textContent = '原页加载失败，请重新打开并核对原图。';
    }
  } catch (error) { alertText(error); }
}
$('#amend-form').addEventListener('submit', async event => {
  event.preventDefault();
  if ($('#amend-submit').disabled) return;
  const {id, ...source} = state.amend;
  const button = $('#amend-submit'); button.disabled = true;
  const label = button.textContent; button.textContent = '正在核对原件与页图…';
  try {
    await post(Team.cases() + '/' + id + '/amend', {...source, field:$('#amend-field').value,
      quote:$('#amend-quote').value, value:$('#amend-value').value, region:$('#amend-region').value,
      reviewer:$('#amend-reviewer').value, note:$('#amend-note').value});
    $('#amend-dialog').close(); chooseRevision(); await refresh();
  } catch (error) { $('#amend-error').textContent = error.message; }
  finally { button.disabled = false; button.textContent=label; }
});
$('#review-form').addEventListener('submit', async event => {
  event.preventDefault();
  const pending = state.review; if (!pending) return;
  const button = $('#submit-review'); button.disabled = true;
  const label = button.textContent;
  if (pending.facts && $('#review-decision').value==='confirm') button.textContent='正在核对原件与页图…';
  try {
    const visibility={};
    if (!$('#review-visibility').hidden)
      for (const input of $('#review-visibility').querySelectorAll('select')) if (input.value) visibility[input.dataset.reference]=input.value;
    await post(Team.cases() + '/' + pending.id + (pending.facts ? '/attest' : '/signoff'), {rev: pending.rev,
      reviewer: $('#reviewer').value, note: $('#review-note').value, decision: $('#review-decision').value,
      facts: pending.facts,...(Object.keys(visibility).length?{reference_visibility:visibility}:{})});
    $('#review-dialog').close(); chooseRevision(); await refresh();
  } catch (error) {
    const message = $('#review-error');
    if (error.paymentSource) {
      showPaymentSourceError(message,error);
      return;
    }
    if (error.invoiceHistory || error.incompleteNumbers) {
      showInvoiceReviewConflict(message,error,$('#review-decision'));
      message.append(action('保留 R'+pending.rev+' 并重新审计',async e=>{
        const rerun = e.currentTarget; rerun.disabled = true;
        try {
          await post(Team.cases()+'/'+pending.id+'/rerun',{rev:pending.rev});
          $('#review-dialog').close(); chooseRevision(); state.tab='report'; await refresh();
        } catch (problem) { message.append(el('p',problem.message)); rerun.disabled=false; }
      }));
      return;
    }
    message.textContent = error.message;
    if (error.status === 409) message.append(' ',action('查看最新执行记录',async()=>{
      $('#review-dialog').close(); chooseRevision(); state.tab='activity'; await refresh();
    },'text-button'));
  }
  finally { button.disabled = false; button.textContent=label; }
});
$('#new-case').addEventListener('click', () => openIntake());
$('#supplement-fields').addEventListener('input',()=>{state.key=null; renderIntakeLimits();});
const fileInput = $('#upload-files');
const canEditFileList = typeof DataTransfer === 'function';
let pendingFiles = [];
function fileSize(bytes) {
  if (!bytes) return '0 KiB';
  if (bytes<1024**2) return Math.ceil(bytes/1024)+' KiB';
  return (bytes/1024**2).toLocaleString('zh-CN',{maximumFractionDigits:2})+' MiB';
}
function fileProblem(file) {
  if (!file.size) return '空文件';
  if (file.size>16*1024**2) return '超过 16 MiB';
  const extension=file.name.match(/\.[^.]+$/)?.[0].toLowerCase();
  if (!fileInput.accept.split(',').includes(extension)) return '不支持此格式';
  return '';
}
function renderIntakeLimits() {
  const retained=[...$('#retain-files').querySelectorAll('input:checked')];
  const count=pendingFiles.length+retained.length;
  const bytes=pendingFiles.reduce((sum,f)=>sum+f.size,0)+retained.reduce((sum,f)=>sum+Number(f.dataset.bytes),0);
  const error=count>12?'整案超过 12 份，请移除多余文件。':bytes>48*1024**2?'整案超过 48 MiB，请缩减资料。':
    pendingFiles.some(fileProblem)?'请处理清单中标出的问题文件。':'';
  const capacity=$('#intake-capacity');
  capacity.hidden=!count; capacity.dataset.invalid=String(Boolean(error));
  capacity.querySelector('progress').value=count;
  $('#intake-count').textContent='已选 '+count+' / 12 份'+(retained.length?'，含沿用 '+retained.length+' 份':'');
  $('#intake-size').textContent=fileSize(bytes)+' / 48 MiB';
  $('#upload-error').textContent=error;
  return error;
}
function drawIntakeFiles(files) {
  pendingFiles=files;
  $('#chosen-files').replaceChildren(...files.map((file,index) => {
    const row = el('li');
    const problem=fileProblem(file);
    row.dataset.invalid=String(Boolean(problem));
    row.append(glyph('file-earmark-text'),el('span',file.name),el('small',problem || fileSize(file.size)));
    if (canEditFileList) {
      const remove = action('移除',() => {
        if ($('#submit-files').disabled) return;
        replaceFiles(files.filter((_,i)=>i!==index));
        const next = $('#chosen-files').children[index] || $('#chosen-files').lastElementChild;
        (next?.querySelector('button') || fileInput).focus();
      },'plain');
      remove.setAttribute('aria-label','移除 '+file.name);
      row.append(remove);
    }
    return row;
  }));
  renderIntakeLimits();
}
function replaceFiles(files) {
  const selection = new DataTransfer();
  for (const file of files) selection.items.add(file);
  fileInput.files = selection.files;
  state.key=null; drawIntakeFiles([...fileInput.files]);
}
fileInput.addEventListener('change', () => {
  // A second trip through the native picker replaces FileList. Keep earlier attachments in the case.
  if (canEditFileList) replaceFiles([...pendingFiles,...fileInput.files]);
  else { state.key=null; drawIntakeFiles([...fileInput.files]); }
});
if (canEditFileList) {
  const zone = fileInput.closest('label');
  $('#drop-hint').hidden = false;
  zone.addEventListener('dragover', event => {
    if (!Array.from(event.dataTransfer.types).includes('Files')) return;
    event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; zone.classList.add('drag-over');
  });
  zone.addEventListener('dragleave', event => {
    if (!zone.contains(event.relatedTarget)) zone.classList.remove('drag-over');
  });
  zone.addEventListener('drop', event => {
    event.preventDefault(); zone.classList.remove('drag-over');
    if ($('#submit-files').disabled || !event.dataTransfer.files.length) return;
    replaceFiles([...fileInput.files,...event.dataTransfer.files]);
  });
}
$('#upload-title').addEventListener('input', () => { state.key = null; });
const scopeSelect=$('#upload-profile'), scopeGroup=$('#intake-scopes');
for (const option of scopeSelect.options) {
  const label=el('label','','intake-scope'), radio=el('input');
  radio.type='radio'; radio.name='intake-scope'; radio.value=option.value;
  radio.defaultChecked=option.defaultSelected || option.index===0;
  radio.addEventListener('change',()=>{
    if (radio.checked && !scopeSelect.disabled) {
      scopeSelect.value=radio.value;
      scopeSelect.dispatchEvent(new Event('change'));
    }
  });
  label.append(glyph(option.dataset.icon),box('scope-text',el('strong',option.text),el('small',option.dataset.scope)),radio);
  scopeGroup.append(label);
}
scopeSelect.parentElement.hidden=true;
scopeGroup.closest('fieldset').hidden=false;
scopeSelect.closest('.intake-fields').classList.add('with-scopes');
function profileChanged() {
  state.key = null;
  scopeGroup.closest('fieldset').disabled=scopeSelect.disabled;
  for (const radio of scopeGroup.querySelectorAll('input')) radio.checked=radio.value===scopeSelect.value;
  if ($('#upload-profile').value === performanceProfile) {
    $('#profile-note').textContent = '上传合同、验收单及注明期次的付款回单。分批交付时请附各批验收单。涉及代理、审批、整改或质保时，可附授权委托书、审批记录、复验报告及质保期满确认单。';
    return;
  }
  if ($('#upload-profile').value === bankProfile) {
    $('#profile-note').textContent = '每个任务上传一份合同和一张银行回单。可核对收款账户、重复流水及全额差额，分期付款可与本企业已签收的回单累计比较。';
    return;
  }
  $('#profile-note').textContent = $('#upload-profile').value === travelProfile ?
    '按一份差旅报销单和所附具名发票勾稽，检查票号、实际发生日期和申请金额。' : '核对合同签署、交付验收与付款约定，并勾稽发票及全额结算资料。';
}
$('#upload-profile').addEventListener('change', profileChanged);
$('#upload-form').addEventListener('submit', async event => {
  event.preventDefault();
  const workspace=Team.current?.id;
  const files = [...$('#upload-files').files]; const data = new FormData();
  data.append('title', $('#upload-title').value);
  data.append('profile', $('#upload-profile').value);
  const button = $('#submit-files'); button.disabled = true; button.textContent = '正在提交…';
  try {
    const parent = state.intakeParent;
    const retained = parent ? [...$('#retain-files').querySelectorAll('input:checked')] : [];
    if (!(files.length+retained.length)) throw new Error('请选择沿用原件或添加资料。');
    const problem = renderIntakeLimits();
    if (problem) throw new Error(problem);
    for (const file of files) data.append('files', file);
    if (parent) {
      data.append('rev',String(parent.rev)); data.append('note',$('#supplement-note').value);
      for (const input of retained) data.append('retain',input.value);
    }
    state.key ||= crypto.randomUUID();
    const url = Team.cases()+(parent?'/'+parent.id+'/supplements':'');
    const {id} = await api(url, {method:'POST', headers:{'Idempotency-Key':state.key}, body:data});
    if (workspace !== Team.current?.id) return;
    $('#upload-dialog').close(); resetIntake(); location.hash = Team.hash('case/' + id);
  } catch (error) { $('#upload-error').textContent = error.message; }
  finally { button.disabled = false; button.textContent = '提交并开始审计'; }
});
for (const button of document.querySelectorAll('[data-close]')) button.addEventListener('click', () => button.closest('dialog').close());
Desk.bind();
PeerReview.bind();
$('#version').addEventListener('change', () => { chooseRevision(Number($('#version').value)); refresh(); });
window.addEventListener('hashchange', () => {
  state.openedCitation=null; state.traceId=null; state.traceKey=null; state.bundle = null; state.detail = null; state.pinned = 0; state.tab = 'report';
  if ((Team.current?.id || null) !== Team.route().id) {
    Desk.reset(); state.key=null; state.cases=[]; $('#case-list').replaceChildren(); $('#team-panel').replaceChildren();
    resetIntake();
  }
  for (const dialog of document.querySelectorAll('dialog[open]')) dialog.close();
  clearCaseView();
  refresh();
});
async function checkConnection() {
  try {
    const data = await api('/api/health');
    $('#connection').dataset.offline=String(!data.audit.configured);
    $('#connection').textContent = data.audit.configured ? (Team.current ? '服务已连接' : '服务在线') : '模型密钥待配置';
  } catch { $('#connection').textContent = '连接中断'; $('#connection').dataset.offline='true'; }
}
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    checkConnection();
    if (!document.querySelector('dialog[open]')) refresh();
  }
});
window.addEventListener('online', () => {
  checkConnection();
  if (!document.querySelector('dialog[open]')) refresh();
});
checkConnection();
refresh();
