const screens = {home:'产品首页',desk:'审计工作台',case:'审计底稿',library:'证据检索',rules:'规则依据',team:'企业成员',account:'企业登录'};
const sections = {main:'',sample:'采购底稿演示',payments:'分期案例',workflow:'采购审计案例',start:'新建审计'};
const caseTabs = {report:'审计结论',evidence:'原件与引文',graph:'知识图谱',activity:'执行记录'};
const dialogs = {'page-dialog':'资料原页','sample-review':'演练原件','sample-compare':'原件对照','upload-dialog':'上传资料',
  'review-dialog':'人工验收','peer-dialog':'复核签收','amend-dialog':'补录原文','case-preview':'任务速览',
  'quick-dialog':'快速定位','case-finder':'查找案例'};
const homeKeys = ['scene','slip','copy','edition','batch','record','pdf','carrier'];
const caseKeys = ['view','stage','instrument','receipt','ticket','call','agreement','acceptance','finding','fact','prior','entry','filing','part'];
const identifier = /^[a-zA-Z][a-zA-Z0-9_-]{0,95}$/;
const factID = /^d\d{2}\/p[1-9]\d*\/(?:[ft][1-9]\d*|h[a-f0-9]{12})$/;
function printedRef(context, ref) {
  const address=context.doc+'/p'+context.page+'/l'+context.line;
  return context.rev && ['inspection-use/','payment-approval/','payment-clock/','contract-approver/','approval-change/'].some(prefix=>ref===prefix+address);
}
function knownParams(search, keys) {
  const out = {};
  for (const key of keys) {
    const value = search.get(key);
    if (value && /^[A-Za-z0-9][A-Za-z0-9_/-]{0,79}$/.test(value)) out[key] = value;
  }
  return out;
}
export function captureContext(owner, element) {
  let context;
  if (location.pathname === '/') {
    const near = element || document.elementFromPoint(Math.floor(innerWidth / 2), Math.floor(innerHeight * .4));
    const fragment = location.hash.slice(1);
    const region = near?.closest('#workflow,#payments,#start,#sample,.hero');
    const section = region ? region.id || 'main' : Object.hasOwn(sections,fragment) ? fragment : 'main';
    context = {screen:'home', section};
    if (section === 'workflow') {
      context.params = knownParams(new URLSearchParams(location.search), homeKeys);
      const sample = document.querySelector('#workflow .workflow-demo > [role=tabpanel]:not([hidden]) .signing-sample-header select');
      const slip = document.getElementById('release-example');
      const example = [sample,slip].filter(select=>select?.getClientRects().length).map(select=>select.selectedOptions[0]?.textContent).filter(Boolean).join(' · ');
      if (example) context.example=example;
    }
  } else {
    const route = Team.route();
    const screen = ['case','desk','library','rules','team','account'].find(id => !document.getElementById(id).hidden) || 'desk';
    context = {screen};
    if (screen==='desk' && owner?.id==='upload-dialog') {
      const profile=IntakeProfiles.find(p=>p.id===document.getElementById('upload-profile').value);
      if (profile) context.intake=profile.key;
    }
    if (screen === 'case') {
      const cid = /^case\/([a-f0-9]{32})$/.exec(route.page)?.[1];
      if (!cid || state.detail?.id !== cid) return {screen:'desk'};
      context.case_id = cid;
      if (state.bundle?.report.case_id === cid) {
        context.rev = state.bundle.rev;
        context.tab = state.tab;
        context.params = knownParams(route.params, caseKeys);
        const view=context.params.view;
        const viewTab=view==='entities'?'graph':['execution','replay'].includes(view)?'activity':'report';
        if (context.params.fact || (view && viewTab!==state.tab) || (context.params.finding && state.traceId!==context.params.finding)) context.params={};
        const finding = element?.closest('[data-finding]')?.dataset.finding;
        if (finding && /^[A-Z]\d{2}-[1-9]\d*$/.test(finding)) context.params = {finding};
        const stage = element?.closest('.release-card')?.closest('[data-phase-finding]')?.dataset.phaseFinding;
        if (stage && /^H04-[1-9]\d*$/.test(stage)) context.params = {view:'payment-release',stage};
        const instrument=element?.closest('[data-release-set] [data-instrument]');
        if (instrument) context.params={view:'payment-release',stage:instrument.parentElement.dataset.releaseSet,instrument:instrument.dataset.instrument};
        const receiptSelector='[data-quality-finding],[data-retest-finding],[data-use-finding]';
        const receiptCard=element?.closest(receiptSelector) || (!element && owner?.id==='performance-index' && owner.querySelector(receiptSelector));
        const certificate=element?.closest('.warranty-certificate')?.closest('[data-phase-finding]')?.dataset.phaseFinding;
        if (certificate) {
          const payment=element.closest('[data-warranty-payment]')?.dataset.warrantyPayment;
          context.params={view:'warranty-certificate',stage:/^H05-[1-9]\d*$/.test(payment || '')?payment:certificate};
        }
        const board=element ? element.closest('#board-decision') : view==='board-decision' ? document.getElementById('board-decision') : null;
        if (board?.dataset.boardFiling) context.params={view:'board-decision',filing:board.dataset.boardFiling,part:board.dataset.boardPart};
        else if (view==='board-decision' && document.getElementById('board-unavailable')) context.params={view:'board-decision'};
        const comparison=element?element.closest('#revision-comparison'):document.getElementById('revision-comparison');
        if (comparison && !comparison.hidden && comparison.dataset.entry)
          context.params={view:'revision-comparison',prior:comparison.dataset.prior,entry:comparison.dataset.entry};
        if (receiptCard) {
          context.params={view:'payment-checks',stage:receiptCard.dataset.useFinding || receiptCard.dataset.qualityFinding || receiptCard.dataset.retestFinding};
          if (!element) {context.anchor=receiptCard.id;context.target=receiptCard.getAttribute('aria-label');}
        }
      }
      if (owner?.id === 'page-dialog') {
        const page = document.querySelector('#page-content .page-view');
        if (page?.dataset.doc && +page.dataset.page > 0) {
          context.doc = page.dataset.doc; context.page = +page.dataset.page;
          delete context.params;
          const files=context.rev?state.bundle.report.graph.documents:state.detail.documents;
          const name=files?.find(file=>file.id===context.doc)?.name;
          if (!element && name && !/[\p{C}\p{Z}]/u.test(name.replaceAll(' ',''))) {
            const chars=[...name];
            context.target=chars.length<=96?name:chars.slice(0,65).join('')+'…'+chars.slice(-30).join('');
          }
          const row=element?.closest('.evidence-row') || owner.querySelector('.evidence-row.located');
          const cited=row?.dataset.fact;
          const fact=context.rev && factID.test(cited || '') && graphIndex(state.bundle.report.graph).facts.get(cited);
          if (fact && fact.doc===context.doc && fact.page===context.page) {
            context.params={fact:cited};
            if (fact.source_line?.number>0) context.line=fact.source_line.number;
            const card=element ? element.closest('[data-party-reading]') : row.querySelector('[data-party-reading]');
            const proof=card && PartyReadings.bind(state.bundle.report,card.dataset.partyReading);
            if (proof?.model.id===cited && card.dataset.rev===String(context.rev) && card.dataset.caseId===context.case_id) {
              context.line=proof.row.line; context.anchor=card.id; context.target=card.dataset.originalLabel;
            }
          } else if (+row?.dataset.gapLine>0) {
            context.line=+row.dataset.gapLine;
            if (printedRef(context,row.dataset.sourceRef)) context.raw_ref=row.dataset.sourceRef;
          }
        }
      }
    }
  }
  if (Object.hasOwn(dialogs, owner?.id)) context.dialog = owner.id;
  if (element) {
    const fieldLabel=element.labels?.[0]?.cloneNode(true);
    fieldLabel?.querySelectorAll('input,select,textarea').forEach(control=>control.remove());
    const item=element.closest('.release-instrument'), file=item?.querySelector('.release-instrument-name')?.textContent;
    const control=element.closest('.release-decision-line') ? '放行决定' : element.closest('.release-compare-field')?.querySelector('small')?.textContent;
    const note=element.closest('[data-warranty-note]');
    const boardNote=element.closest('[data-board-note]');
    const boardFile=boardNote?.closest('#board-decision')?.querySelector('.warranty-file')?.textContent;
    const boardRow=element.closest('[data-board-row]');
    const date=element.closest('.warranty-date-source'), order=element.closest('[data-warranty-order]');
    const sourceLabel = element.closest('[data-original-label]')?.dataset.originalLabel ||
      (element.closest('.quality-order') ? '两单日期 · '+element.closest('.quality-order').textContent : null) ||
      (element.id==='board-unavailable' ? element.textContent :
      boardRow ? [boardRow.querySelector('small').textContent,boardRow.querySelector('button').textContent].join(' · ') :
      boardNote ? [boardFile,'原批注',boardNote.querySelector('button')?.textContent].filter(Boolean).join(' · ') :
      date ? ['small','time','.warranty-date-place span'].map(s=>date.querySelector(s).textContent).join(' · ') :
      order ? '两单日期 · '+order.textContent : note?'期满确认单批注'+(note.querySelector('button')?' · '+note.querySelector('button').textContent:''):
      file && control ? file+' · '+control : element.closest('.source-plane,#sample-review canvas') ? '原件页图' :
      element.closest('.evidence-row,.sample-records [data-ref]') ? '证据引文' :
      element.closest('.release-entry')?.querySelector('small')?.textContent);
    const text = sourceLabel || element.getAttribute('aria-label') || fieldLabel?.textContent ||
      (element.matches('button,a,summary,label,h1,h2,h3,h4,[role=tab]') && element.textContent) || element.title;
    const label = text && text.replace(/\s+/g,' ').trim();
    const side=element.closest('#revision-comparison .revision-side')?.querySelector('h3')?.textContent;
    const target=label && (side?side+' · '+label:label);
    context.target = target && target.length <= 96 ? target : '所选位置';
    const named = element.closest('[id]');
    if (named && identifier.test(named.id) && !['content','case-panel','main'].includes(named.id)) context.anchor = named.id;
  }
  return context;
}
export function describeContext(c) {
  const screen = c.screen==='case' ? screens.case+' '+c.case_id.slice(0,8) : screens[c.screen];
  const edition=c.params?.view==='revision-comparison' ? '履约对照 R'+c.params.prior+' / R'+c.rev : c.rev && 'R'+c.rev;
  const board=c.params?.view==='board-decision' && ({decision:'董事会决议原文',signing:'董事会签发版本',payments:'董事会决议关联期款'}[c.params.part] || '董事会审批原件');
  const receipt=c.params?.view==='payment-checks' && (c.anchor?.startsWith('payment-approval-')?'付款审批单 '+c.params.stage:
    c.anchor?.startsWith('contract-approver-')?'合同签批人 '+c.params.stage:
    c.anchor?.startsWith('payment-clock-')?'银行回单时刻 '+c.params.stage:
    c.anchor?.startsWith('inspection-use-')?'验收单付款用途 '+c.params.stage:
    c.anchor?.startsWith('retest-')?'复验回单核对 '+c.params.stage:
    c.anchor?.startsWith('quality-') && '验收款核对 '+c.params.stage);
  return [screen, c.example || sections[c.section], edition, caseTabs[c.tab], board, receipt, dialogs[c.dialog],
    c.doc && (c.doc+' · 第 '+c.page+' 页'), c.line && '第 '+c.line+' 行', c.target].filter(Boolean).join(' › ');
}
export function returnUrl(c, workspace) {
  const route = new URLSearchParams();
  if (c.anchor && identifier.test(c.anchor)) route.set('walkat',c.anchor);
  if (c.screen === 'home') {
    for (const [key,value] of Object.entries(knownParams(new URLSearchParams(c.params),homeKeys))) route.set(key,value);
    const search = route.toString();
    return '/' + (search ? '?'+search : '') + (c.section && c.section !== 'main' ? '#'+c.section : '');
  }
  if (c.screen==='desk' && c.dialog==='upload-dialog' && ['contract','purchase','travel','payment'].includes(c.intake)) route.set('new',c.intake);
  const base = '/app'+(route.size?'?'+route:'')+'#' + (workspace ? 'w/'+workspace+'/' : '');
  if (c.screen !== 'case') return base+c.screen;
  const query = new URLSearchParams(knownParams(new URLSearchParams(c.params), caseKeys));
  if (c.rev) query.set('rev', c.rev);
  if (c.tab) query.set('walktab', c.tab);
  if (c.doc && !query.has('fact')) {
    query.set('walkdoc', c.doc); query.set('walkpage', c.page);
    if (c.line) query.set('walkline', c.line);
    if (printedRef(c,c.raw_ref)) query.set('walkraw',c.raw_ref);
  }
  return base+'case/'+c.case_id+(query.size?'?'+query:'');
}
