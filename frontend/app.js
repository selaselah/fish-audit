const $ = selector => document.querySelector(selector);
const state = {cases: [], filter: 'all', detail: null, bundle: null, tab: 'report', pinned: 0,
  timer: null, epoch: 0, key: null, review: null};
const labels = {
  queued: '排队中', running: '处理中', ready: '待验收', closed: '已归档', failed: '已中断',
  prepare: '资料分页', extract: '多模态解析', graph: '证据建图', controls: '规则执行', expert: '专家复核',
  attestation: '人工核图', pass: '建议通过', review: '需要人工校验', reject: '建议不通过',
  ok: '相符', issue: '问题', risk: '风险', missing: '证据不足', anchored: '已匹配文字层',
  visual: '待核原图', confirmed: '人工已确认', disputed: '人工有异议', unsupported: '引用不支持取值',
  approve: '通过', return: '退回补件', escalate: '提交复核', top: '上部', middle: '中部', bottom: '下部',
};
const tabs = {report: '审计结论', evidence: '原件与引文', graph: '知识图谱', activity: '执行记录'};
const travelProfile = 'cn-travel-reimbursement/v1';
const bankProfile = 'cn-bank-contract-payment/v1';
const profileName = profile => ({[travelProfile]:'差旅报销',[bankProfile]:'付款回单核对','cn-procurement-full-settlement/v1':'采购与付款'}[profile] || profile);
const tone = {ready: 'risk', closed: 'ok', failed: 'issue', pass: 'ok', review: 'risk', reject: 'issue',
  visual: 'risk', unsupported: 'issue', disputed: 'issue', confirmed: 'ok', anchored: 'ok'};
const statusName = value => labels[value] || value;
const base = () => Team.cases() + '/' + state.detail.id;
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
    problem.status = response.status; throw problem;
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
function openPage(docId, pageNumber, highlight) {
  const item = state.detail.documents.find(doc => doc.id === docId);
  if (!item) return;
  const pageUrl = base() + '/documents/' + docId + '/pages/' + pageNumber;
  const image = el('img', '', 'page-image');
  image.src = pageUrl; image.alt = item.name + ' 第 ' + pageNumber + ' 页';
  const enlarged = link('单独打开页图', pageUrl); enlarged.target = '_blank'; enlarged.rel = 'noopener';
  const overlay = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  overlay.setAttribute('viewBox', '0 0 1000 1000');
  overlay.setAttribute('preserveAspectRatio', 'none');
  overlay.setAttribute('aria-hidden', 'true');
  const left = box('', box('image-sheet', image, overlay), enlarged);
  const right = box('', el('h3', '本页引文'));
  const pageFacts = (state.bundle?.report.graph.facts || []).filter(fact => fact.doc === docId && fact.page === pageNumber);
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
    if (fact.origin === 'verified_printed_heading') row.append(el('small','标题来自可定位文字层，经模型对照页图复检。','small'));
    if (fact.visual_check) row.append(el('small', '模型二次读图 · ' +
      ({clear:'可辨认', conflict:'存在差异', unreadable:'无法核实'}[fact.visual_check] || fact.visual_check), 'small'));
    if (fact.source_line?.rects?.length) row.append(action('定位原文', () => locate(fact), 'ref'));
    if (fact.attestation) row.append(el('p', fact.attestation.reviewer + ' · ' + fact.attestation.note, 'muted'));
    if (fact.amendment) {
      const previous = fact.original_candidate;
      row.append(fold('人工' + (previous ? '更正' : '补录') + '来源', el('p', fact.amendment.reviewer + ' · ' +
        fact.amendment.note), el('p', previous ? '原模型引文：' + previous.quote + '（' + previous.value + '）' : '此字段由审计人员据图补录。')));
    }
    if (editable) row.append(action('更正字段', () => openAmend(docId, pageNumber, fact), 'ref'));
    if (fact.id === highlight) focusRow = row;
    right.append(row);
  }
  const gaps = (state.bundle?.report.graph.gaps || []).filter(g => g.doc === docId && g.page === pageNumber && g.quote);
  for (const gap of gaps) {
    const section = box('evidence-row',el('h4','待核的原文字层 · 第 '+gap.line+' 行'),el('blockquote',gap.quote));
    const field = gap.field || gap.title_hint;
    if (editable && field) {
      const candidates = pageFacts.filter(f => f.field===field && !['anchored','confirmed'].includes(f.status));
      if (candidates.length <= 1) section.append(action(candidates.length ? '据此行更正候选' : '据此行补录',
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
  $('#page-title').textContent = item.name + ' · 第 ' + pageNumber + ' 页';
  $('#page-content').replaceChildren(box('page-view', left, right));
  $('#page-dialog').showModal();
  if (focusRow) {
    locate(pageFacts.find(fact => fact.id === highlight));
    focusRow.scrollIntoView({block: 'nearest'});
  }
}
function citation(ref) {
  const index = state.bundle && graphIndex(state.bundle.report.graph);
  const prior = index?.prior.get(ref);
  if (prior) {
    const target = Team.cases() + '/' + prior.case_id + '/documents/' + prior.doc + '/pages/' + prior.page;
    const source = link('已归档 · ' + prior.title + ' · R' + prior.rev + ' p.' + prior.page, target, 'button ref');
    source.target = '_blank'; source.rel = 'noopener';
    return source;
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
    const download = link('下载原件', base() + '/documents/' + item.id + '/original');
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
function finding(item) {
  const node = box('finding', box('flow', tag(item.status), el('h3', item.title), el('span', item.rule, 'mono')),
    el('p', item.detail), el('p', '执行依据 · ' + item.basis, 'muted'));
  if (item.scope.length) node.append(el('small', '检查范围 · ' + item.scope.map(id =>
    state.bundle.report.graph.audit_documents?.find(doc => doc.id === id)?.name ||
    state.detail.documents.find(doc => doc.id === id)?.name || id).join('、'), 'small'));
  if (item.calculations?.length) node.append(fold('查看金额算式与取数依据',
    ...item.calculations.map(calculationPanel)));
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
  const passed = report.findings.filter(item => item.status === 'ok');
  const exceptions = report.findings.filter(item => item.status !== 'ok');
  const conclusion = box('panel', box('panel-head', el('h2', '审计建议'), tag(report.result.verdict)),
    el('p', '专项人工校验：' + (report.result.human_required ? '需要' : '无待核项') + ' · 最终决定由审计人员验收。'),
    el('p', report.result.counts.issue + ' 项问题 · ' + report.result.counts.risk + ' 项风险 · ' +
      report.result.counts.missing + ' 项证据不足', 'muted'));
  const findings = box('panel', el('h2', '风险与问题'));
  if (exceptions.length) findings.append(...exceptions.map(finding));
  else findings.append(el('p', '本次已执行的检查程序均相符。'));
  if (passed.length) findings.append(fold('展开相符的检查程序（' + passed.length + '）', ...passed.map(finding)));
  const human = box('panel', el('h2', '审计人员验收'));
  const decision = state.detail.decisions.find(item => item.rev === state.bundle.rev);
  if (decision) {
    human.append(el('h3', statusName(decision.decision)), el('p', decision.note),
      el('small', decision.reviewer + ' · ' + time(decision.time), 'small'));
  } else if (state.detail.status === 'ready' && state.detail.rev === state.bundle.rev) {
    human.append(el('p', '查看原页与引用后，记录验收决定及依据。', 'muted'),
      action('填写验收意见', () => openReview(null), 'primary'));
  } else human.append(el('p', '此为历史底稿，保留当时的审计建议。', 'muted'));
  const working = box('panel', el('h3', '底稿留存'), el('p', 'R' + state.bundle.rev + ' · ' + time(state.bundle.created), 'muted'),
    link('下载底稿及证据包', base() + '/reports/' + state.bundle.rev + '/bundle', 'button'),
    fold('底稿 SHA-256', el('code', state.bundle.sha256)));
  return box('grid', box('', conclusion, findings), box('', human, working));
}
function graphPanel() {
  const graph = state.bundle.report.graph;
  const {nodes,facts} = graphIndex(graph);
  const docIds = new Set((graph.audit_documents || graph.documents).map(doc => doc.id));
  const relations = graph.edges.filter(edge => docIds.has(edge.from) && !['contains','section_page'].includes(edge.type));
  const panel = box('panel', el('h2', '本案证据关系'), el('p', graph.nodes.length + ' 个节点 · ' +
    graph.edges.length + ' 条关系 · ' + graph.facts.length + ' 条提取记录', 'muted'));
  const grouped = new Map();
  if (graph.audit_documents) panel.append(fold('合订资料的原页归属', ...graph.audit_documents.filter(doc => doc.source)
    .map(doc => box('line', el('strong', doc.name), citation(doc.source + '/p' + doc.page)))));
  for (const edge of relations) {
    if (!grouped.has(edge.to)) grouped.set(edge.to, []);
    grouped.get(edge.to).push(edge);
  }
  const groups = [...grouped].sort((left, right) => right[1].length - left[1].length);
  if (groups.length) panel.append(lazyFold('查看实体与单据关联（'+groups.length+'）',()=>groups.map(([target, edges])=>
    lazyFold(nodes.get(target).label+' · '+edges.length+' 条关联',()=>edges.map(edge=>box('line',
      el('strong',nodes.get(edge.from).label),el('span','记载'+(facts.get(edge.evidence[0])?.label || edge.type)),
      box('chips',...edge.evidence.map(citation))))))));
  if (!groups.length) panel.append(el('p', '请在原件与引文中核对待确认记录，核图后系统会重建关系。'));
  if (graph.prior_invoices?.length) panel.append(fold('跨案同号记录', ...graph.prior_invoices.map(row =>
    box('line', link(row.title, Team.hash('case/' + row.case_id)), el('p', '历史人工决定 · ' + statusName(row.decision) + ' · ' +
      (row.document_kind === 'unclassified' ? '原资料类型待核' : '发票')),
      el('blockquote', row.quote), citation(row.id), el('small', '历史底稿 SHA-256 · ' + row.report_hash, 'small')))));
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
  return box('', panel, log);
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
      if (rev && (bundle?.rev !== rev || bundle.report.case_id !== data.id))
        bundle = await api(Team.cases() + '/' + data.id + '/reports/' + rev);
      if (epoch !== state.epoch) return;
      state.detail = data; state.bundle = rev ? bundle : null;
      renderCase();
      const target = route.params.get('fact');
      if (target && state.openedCitation !== location.hash && state.bundle) {
        const fact = state.bundle.report.graph.facts.find(f => f.id === target);
        if (fact) { state.openedCitation = location.hash; openPage(fact.doc,fact.page,fact.id); }
      }
      if (['queued','running'].includes(data.status)) interval = 1600;
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
        Team.session=null;
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
function openReview(facts) {
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
    $('#amend-image').src = base() + '/documents/' + doc + '/pages/' + page;
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
  } catch (error) { alertText(error); }
}
$('#amend-form').addEventListener('submit', async event => {
  event.preventDefault();
  const {id, ...source} = state.amend;
  const button = $('#amend-submit'); button.disabled = true;
  try {
    await post(Team.cases() + '/' + id + '/amend', {...source, field:$('#amend-field').value,
      quote:$('#amend-quote').value, value:$('#amend-value').value, region:$('#amend-region').value,
      reviewer:$('#amend-reviewer').value, note:$('#amend-note').value});
    $('#amend-dialog').close(); chooseRevision(); await refresh();
  } catch (error) { $('#amend-error').textContent = error.message; }
  finally { button.disabled = false; }
});
$('#review-form').addEventListener('submit', async event => {
  event.preventDefault();
  const pending = state.review; if (!pending) return;
  const button = $('#submit-review'); button.disabled = true;
  try {
    await post(Team.cases() + '/' + pending.id + (pending.facts ? '/attest' : '/signoff'), {rev: pending.rev,
      reviewer: $('#reviewer').value, note: $('#review-note').value, decision: $('#review-decision').value,
      facts: pending.facts});
    $('#review-dialog').close(); chooseRevision(); await refresh();
  } catch (error) { $('#review-error').textContent = error.message; }
  finally { button.disabled = false; }
});
$('#new-case').addEventListener('click', () => $('#upload-dialog').showModal());
$('#upload-files').addEventListener('change', () => {
  state.key = null; $('#upload-error').textContent = '';
  $('#chosen-files').replaceChildren(...[...$('#upload-files').files].map(file => el('li', file.name)));
});
$('#upload-title').addEventListener('input', () => { state.key = null; });
function profileChanged() {
  state.key = null;
  if ($('#upload-profile').value === bankProfile) {
    $('#profile-note').textContent = '按一份合同及一张银行回单核对付款主体、收款账号、流水状态和单笔全额差额。';
    return;
  }
  $('#profile-note').textContent = $('#upload-profile').value === travelProfile ?
    '按一份差旅报销单和所附具名发票勾稽，检查票号、实际发生日期和申请金额。' : '按单合同、一次全额结算核对。';
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
    if (files.length > 12 || files.some(file => file.size > 16*1024**2) || files.reduce((sum,file) => sum + file.size, 0) > 48*1024**2)
      throw new Error('所选资料超出文件数或大小限制。');
    for (const file of files) data.append('files', file);
    state.key ||= crypto.randomUUID();
    const {id} = await api(Team.cases(), {method:'POST', headers:{'Idempotency-Key':state.key}, body:data});
    if (workspace !== Team.current?.id) return;
    $('#upload-dialog').close(); $('#upload-form').reset(); $('#chosen-files').replaceChildren();
    profileChanged(); $('#upload-error').textContent = ''; location.hash = Team.hash('case/' + id);
  } catch (error) { $('#upload-error').textContent = error.message; }
  finally { button.disabled = false; button.textContent = '提交并开始审计'; }
});
for (const button of document.querySelectorAll('[data-close]')) button.addEventListener('click', () => button.closest('dialog').close());
Desk.bind();
$('#version').addEventListener('change', () => { chooseRevision(Number($('#version').value)); refresh(); });
window.addEventListener('hashchange', () => {
  state.openedCitation=null; state.traceId=null; state.traceKey=null; state.bundle = null; state.detail = null; state.pinned = 0; state.tab = 'report';
  if ((Team.current?.id || null) !== Team.route().id) {
    Desk.reset(); state.key=null; state.cases=[]; $('#case-list').replaceChildren(); $('#team-panel').replaceChildren();
    $('#upload-form').reset(); $('#chosen-files').replaceChildren(); profileChanged();
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
