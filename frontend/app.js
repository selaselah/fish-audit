const $ = selector => document.querySelector(selector);
const state = {cases: [], filter: 'all', detail: null, bundle: null, tab: 'report', pinned: 0,
  timer: null, epoch: 0, key: null, review: null};
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
function tag(value) { return el('span', statusName(value), 'tag ' + (tone[value] || value)); }
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
  catch {
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
function renderList() {
  const list = $('#case-list');
  const visible = state.cases;
  const header = box('ledger-header ledger-row', ...['任务名称','处理状态','审计建议', $('#desk-sort').value === 'updated' ? '最近更新' : '提交时间'].map(label => el('span', label)));
  list.replaceChildren(header);
  for (const row of visible) {
    const title = Team.paperLink(row.title, row.id, 'case-link');
    const metadata = el('span', profileName(row.profile) + ' · ' + row.files + ' 份资料' + (row.rev ? ' · 底稿 R' + row.rev : ''), 'small');
    const status = box('', tag(row.status));
    if (row.status === 'running') status.append(el('small', row.progress + '%', 'small'));
    const result = row.decision ? '人工' + statusName(row.decision) :
      (row.verdict ? statusName(row.verdict) : '等待结果');
    list.append(box('ledger-row', box('case-name',el('span','',row.profile===travelProfile?'doc-icon travel':'doc-icon'),box('',title,metadata)), status,
      box('row-result',el('span',result), ...(row.issues || row.risks ? [el('small',[(row.issues ? row.issues+' 项问题' : ''),(row.risks ? row.risks+' 项风险' : '')].filter(Boolean).join(' · '),'small')] : [])),
      el('span', time($('#desk-sort').value==='updated' ? row.updated : row.created), 'small row-date')));
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
function openPage(docId, pageNumber, highlight, lineHint) {
  const item = state.detail.documents.find(doc => doc.id === docId);
  if (!item) return;
  const pageUrl = workpaperSource(docId,'pages/'+pageNumber);
  const image = el('img', '', 'page-image');
  image.alt = item.name + ' 第 ' + pageNumber + ' 页';
  const enlarged = link('单独打开页图', pageUrl); enlarged.target = '_blank'; enlarged.rel = 'noopener';
  const overlay = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  overlay.setAttribute('viewBox', '0 0 1000 1000');
  overlay.setAttribute('preserveAspectRatio', 'none');
  overlay.setAttribute('aria-hidden', 'true');
  const left = box('', box('image-sheet', image, overlay), enlarged);
  const right = box('', el('h3', '本页引文'));
  const pageFacts = (state.bundle?.report.graph.facts || []).filter(fact => fact.doc === docId && fact.page === pageNumber);
  const coverage = state.bundle?.report.graph.delegation_coverage;
  const nameHolds = new Map([...(coverage?.agent_holds || []),...(coverage?.signer_holds || [])]
    .filter(h=>h.doc===docId && h.page===pageNumber && h.lines?.length).map(h=>[h.fact,h]));
  const editable = state.bundle?.rev === state.detail.rev && state.detail.status === 'ready';
  const selected = new Set();
  let focusRow;
  function locate(fact) {
    overlay.replaceChildren();
    for (const [left, top, right, bottom] of fact.source_line?.rects || []) {
      const rect = document.createElementNS('http://www.w3.org/2000/svg','rect');
      for (const [name, value] of Object.entries({x:left,y:top,width:right-left,height:bottom-top}))
        rect.setAttribute(name,String(1000*value));
      overlay.append(rect);
    }
    for (const row of right.querySelectorAll('[data-fact]')) row.classList.toggle('located', row.dataset.fact === fact.id);
  }
  function focusObservation(source) {
    locate(source);
    const target = right.querySelector('.located');
    target.tabIndex = -1;
    target.focus({preventScroll:true});
    target.scrollIntoView({block:'nearest'});
  }
  for (const fact of pageFacts) {
    const row = box('evidence-row');
    row.dataset.fact = fact.id;
    const label = el('label', '', 'check-label');
    if (editable) {
      const check = el('input'); check.type = 'checkbox'; check.value = fact.id;
      check.addEventListener('change', () => {
        if (check.checked) selected.add(fact.id); else selected.delete(fact.id);
        submit.disabled = selected.size === 0;
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
    const note = [...addenda.signals,...addenda.limited_numbers].find(s=>s.doc===docId && s.page===pageNumber && s.line===lineHint);
    if (note) gaps.push({...note,quality:'addendum_reference'});
  }
  const signers = state.bundle?.report.graph.acceptance_authority_sources;
  if (signers && lineHint && !gaps.some(g=>g.line===lineHint)) {
    const source = [...signers.clauses,...signers.signatures].find(s=>s.doc===docId && s.page===pageNumber && s.line===lineHint);
    if (source) gaps.push({...source,quality:'signer_reference'});
  }
  for (const gap of gaps) {
    const label = {addendum_reference:'补充协议所据原文',signer_reference:'验收签认所据原文'}[gap.quality] || '待核的原文字层';
    const section = box('evidence-row',el('h4',label+' · 第 '+gap.line+' 行'),el('blockquote',gap.quote));
    section.dataset.gapLine = String(gap.line);
    if (gap.line===lineHint) {
      section.classList.add('located');
      focusRow=section;
    }
    const field = ['mandate_clause','addendum_clause','acceptance_authority_clause'].includes(gap.quality) ? null : gap.field || gap.title_hint;
    if (editable && field) {
      const unresolved=pageFacts.filter(f=>['visual','unsupported'].includes(f.status));
      const matching=unresolved.filter(f=>f.source_line?.number===gap.line && f.source_line.text===gap.quote);
      const candidates=matching.length?matching:unresolved.filter(f=>f.field===field && !f.source_line);
      const label=candidates.length && candidates[0].field!==field?'据原文更正字段类别':'据此行更正候选';
      if (candidates.length <= 1) section.append(action(candidates.length ? label : '据此行补录',
        ()=>openAmend(docId,pageNumber,candidates[0],{field,quote:gap.quote}),'ref'));
    }
    right.append(section);
  }
  if (!pageFacts.length) right.append(el('p', '本页尚无可展示的提取记录。', 'muted'));
  const submit = action('记录所选引文的核图意见', () => {
    $('#page-dialog').close(); openReview([...selected]);
  }, 'primary');
  submit.disabled = true;
  if (editable && pageFacts.length) right.append(submit);
  if (editable) right.append(action('补录本页字段', () => openAmend(docId, pageNumber, null)));
  const controls = editable ? [...right.querySelectorAll('button:enabled,input:enabled')] : [];
  for (const control of controls) control.disabled = true;
  loadReviewImage(image,pageUrl).then(()=>{
    for (const control of controls) control.disabled=false;
  },()=>{
    image.hidden=true; overlay.setAttribute('hidden','');
    const notice=el('p','原页加载失败，可单独打开页图查看原因。','note');
    notice.setAttribute('role','alert'); left.prepend(notice);
  });
  $('#page-title').textContent = item.name + ' · 第 ' + pageNumber + ' 页';
  $('#page-content').replaceChildren(box('page-view', left, right));
  $('#page-dialog').showModal();
  if (focusRow) {
    const fact=pageFacts.find(f=>f.id===highlight);
    if (fact) locate(fact);
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

function finding(item) {
  const heading = item.stage ? item.stage.name + (item.stage.share ? ' · ' + item.stage.share + '%' : '') +
    (item.rule === 'H05' ? ' 实付时点' : ' 付款条件') : item.title;
  const node = box('finding', box('flow', tag(item.status), el('h3', heading), el('span', item.rule, 'mono')),
    el('p', item.detail), el('p', '执行依据 · ' + item.basis, 'muted'));
  node.dataset.finding = item.id;
  node.tabIndex = -1;
  if (item.stage) node.insertBefore(box('clause-source',el('q',item.stage.clause), citation(item.stage.clause_ref)),node.children[1]);
  if (item.reinspection) node.append(reinspectionTrail(item.reinspection,state.bundle.report.graph));
  if (item.delegations) node.append(mandatePanel(item.delegations, state.bundle.report.graph));
  if (item.quality_change) node.append(qualityChangePanel(item.quality_change, state.bundle.report.graph));
  if (item.acceptance_authority) node.append(acceptanceAuthorityPanel(item.acceptance_authority, state.bundle.report.graph));
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
  if (graphIndex(state.bundle.report.graph).nodes.has('finding/'+item.id)) node.append(action('查看证据路径',()=>{
    state.traceKey=state.detail.id+'@'+state.bundle.rev; state.traceId=item.id;
    state.tab='graph'; renderCase(); $('#trace-select')?.focus();
  },'text-button'));
  const policy = state.bundle.report.policy;
  const refs = policy.rule_sources?.[item.rule] || [];
  if (refs.length) node.append(fold('核对制度出处与适用范围', ...refs.map(id => sourceEntry(policy.sources[id]))));
  return node;
}
function reportPanel() {
  const report = state.bundle.report;
  const performance = report.findings.filter(item => /^H0[1-5]$/.test(item.rule));
  const other = report.findings.filter(item => !performance.includes(item));
  const passed = other.filter(item => item.status === 'ok');
  const exceptions = other.filter(item => item.status !== 'ok');
  const conclusion = box('panel', box('panel-head', el('h2', '审计建议'), tag(report.result.verdict)),
    el('p', '专项人工校验：' + (report.result.human_required ? '需要' : '无待核项') + ' · 最终决定由审计人员验收。'),
    el('p', report.result.counts.issue + ' 项问题 · ' + report.result.counts.risk + ' 项风险 · ' +
      report.result.counts.missing + ' 项证据不足', 'muted'));
  const findings = box('panel', el('h2', performance.length ? '其他检查程序' : '风险与问题'));
  if (exceptions.length) findings.append(...exceptions.map(finding));
  else if (!performance.length) findings.append(el('p', '本次已执行的检查程序均相符。'));
  if (passed.length) findings.append(fold('展开相符的检查程序（' + passed.length + '）', ...passed.map(finding)));
  const human = box('panel', el('h2', report.peer_review ? '复核签收决定' : '审计人员验收'));
  const decision = state.detail.decisions.find(item => item.rev === state.bundle.rev);
  if (decision) {
    human.append(el('h3', statusName(decision.decision)), el('p', decision.note),
      el('small', decision.reviewer + ' · ' + time(decision.time), 'small'));
    if (state.bundle.invoice_approval && decision.invoice_check_hash)
      human.append(invoiceApproval(state.bundle.invoice_approval,decision.invoice_check_hash));
  } else if (state.detail.status === 'ready' && state.detail.rev === state.bundle.rev) {
    human.append(el('p', '查看原页与引用后，记录验收决定及依据。', 'muted'),
      action('填写验收意见', () => openReview(null), 'primary'));
  } else human.append(el('p', '此为历史底稿，保留当时的审计建议。', 'muted'));
  const working = box('panel', el('h3', '底稿留存'), el('p', 'R' + state.bundle.rev + ' · ' + time(state.bundle.created), 'muted'),
    link('下载底稿及证据包', base() + '/reports/' + state.bundle.rev + '/bundle', 'button'),
    fold('底稿 SHA-256', el('code', state.bundle.sha256)));
  const review = box('', conclusion);
  if (report.supplement) review.append(returnComparison(report,state.bundle.rev));
  if (performance.length) {
    const conditions = box('panel performance-panel',el('h2','合同履约审查'));
    conditions.append(performanceOverview(performance,report.graph));
    for (const entry of performance) conditions.append(finding(entry));
    review.append(conditions);
  }
  review.append(findings);
  const side = box('', human);
  const peer = PeerReview.panel(state.detail,state.bundle);
  if (peer) side.append(peer);
  side.append(working);
  return box('grid', review, side);
}
function graphPanel() {
  const graph = state.bundle.report.graph;
  const {nodes,facts} = graphIndex(graph);
  const docIds = new Set((graph.audit_documents || graph.documents).map(doc => doc.id));
  const relations = graph.edges.filter(edge => docIds.has(edge.from) && !['contains','section_page'].includes(edge.type));
  const panel = box('panel', el('h2', '本案证据关系'), el('p', graph.nodes.length + ' 个节点 · ' +
    graph.edges.length + ' 条关系 · ' + graph.facts.length + ' 条提取记录', 'muted'));
  const grouped = new Map();
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
    const comparison = (rule,kind,label) => state.bundle.report.findings.find(f=>f.rule===rule)?.status==='missing'
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
    box('line', el('span', item.quality === 'uncovered_title' ? '页首标题尚待核图补录' : item.quote ? '文字层第 ' + item.line + ' 行尚缺完整取值' :
      (item.quality === 'section_unresolved' ? '本页的单据归属待核对' : '页图存在辨读或提取缺口')),
      el('blockquote', item.quote || '请查看原件或补传清晰资料。'), citation(item.id)))));
  panel.append(lazyFold('资料、页与观察记录的溯源关系', ()=>graph.edges.filter(edge => ['contains','records'].includes(edge.type))
    .map(edge => box('line', el('code', edge.from + ' → ' + edge.to), box('chips', ...edge.evidence.map(citation))))));
  const path = provenancePanel(state.bundle.report);
  return path ? box('graph-stack',path,panel) : panel;
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
function renderCase() {
  const data = state.detail;
  $('#case-title').textContent = data.title;
  $('#case-meta').textContent = profileName(data.profile) + ' · ' + time(data.created) + ' 提交';
  $('#case-status').replaceChildren(tag(data.status));
  const progress = $('#progress-panel');
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
    const content = [sourceList(), activityPanel()];
    const decision = data.decisions?.at(-1);
    if (decision) content.unshift(box('panel',el('h2','验收决定'),tag(decision.decision),el('p',decision.note)));
    $('#case-panel').replaceChildren(...content); return;
  }
  const nav = $('#tabs'); nav.replaceChildren();
  for (const [id, label] of Object.entries(tabs)) {
    const button = action(label, () => { state.tab = id; renderCase(); });
    button.setAttribute('aria-pressed', String(state.tab === id)); nav.append(button);
  }
  const versions = $('#version'); versions.replaceChildren();
  for (const row of data.revisions) versions.add(new Option('R' + row.rev, row.rev, false, row.rev === bundle.rev));
  const panel = {report: reportPanel, evidence: sourceList, graph: graphPanel, activity: activityPanel}[state.tab]();
  $('#case-panel').replaceChildren(panel);
}
function clearCaseView() {
  state.detail = null; state.bundle = null;
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
        state.tab=traced?'graph':'report'; focusFinding=traced?'#trace-select':'[data-finding="'+requestedFinding+'"]';
      } else if (route.params.get('view')==='replay' && state.openedCitation!==location.hash && state.bundle) {
        state.openedCitation=location.hash; state.tab='activity'; focusFinding='.rule-replay button';
      }
      renderCase();
      if (focusFinding) {
        const target = $(focusFinding);
        for (let p=target?.parentElement;p;p=p.parentElement) if (p.tagName==='DETAILS') p.open=true;
        target?.focus();
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
    $('#amend-context').textContent = item.name + ' · 第 ' + page + ' 页 · 底稿 R' + state.bundle.rev;
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
      if (image.isConnected) submit.disabled = false;
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
$('#supplement-fields').addEventListener('input',()=>{state.key=null;});
$('#upload-files').addEventListener('change', () => {
  state.key = null; $('#upload-error').textContent = '';
  $('#chosen-files').replaceChildren(...[...$('#upload-files').files].map(file => el('li', file.name)));
});
$('#upload-title').addEventListener('input', () => { state.key = null; });
function profileChanged() {
  state.key = null;
  if ($('#upload-profile').value === performanceProfile) {
    $('#profile-note').textContent = '上传合同及本次要核对的履约资料。代理人签约可附授权委托书，另可提交审批单、验收单、整改复验记录、质保期满确认单及分期回单。';
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
    const bytes = retained.reduce((sum,input)=>sum+Number(input.dataset.bytes),0);
    if (!(files.length+retained.length)) throw new Error('请选择沿用原件或添加资料。');
    if (files.length+retained.length > 12 || files.some(file => file.size > 16*1024**2) || bytes+files.reduce((sum,file) => sum + file.size, 0) > 48*1024**2)
      throw new Error('所选资料超出文件数或大小限制。');
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
