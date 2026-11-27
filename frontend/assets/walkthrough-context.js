const screens = {home:'产品首页',desk:'审计工作台',case:'审计底稿',library:'证据检索',rules:'规则依据',team:'企业成员',account:'企业登录'};
const sections = {main:'',sample:'采购底稿演示',payments:'分期案例',workflow:'采购审计案例',start:'新建审计'};
const caseTabs = {report:'审计结论',evidence:'原件与引文',graph:'知识图谱',activity:'执行记录'};
const dialogs = {'page-dialog':'资料原页','sample-review':'演练原件','sample-compare':'原件对照','upload-dialog':'上传资料',
  'review-dialog':'人工验收','peer-dialog':'复核签收','amend-dialog':'补录原文','case-preview':'任务速览',
  'quick-dialog':'快速定位','case-finder':'查找案例'};
const homeKeys = ['scene','slip','copy','edition','batch','record','pdf','carrier'];
const caseKeys = ['view','stage','instrument','receipt','ticket','call','agreement','acceptance','finding','fact'];
const identifier = /^[a-zA-Z][a-zA-Z0-9_-]{0,95}$/;
const factID = /^d\d{2}\/p[1-9]\d*\/(?:[ft][1-9]\d*|h[a-f0-9]{12})$/;
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
      }
      if (owner?.id === 'page-dialog') {
        const page = document.querySelector('#page-content .page-view');
        if (page?.dataset.doc && +page.dataset.page > 0) {
          context.doc = page.dataset.doc; context.page = +page.dataset.page;
          if (+page.dataset.line > 0) context.line = +page.dataset.line;
          delete context.params;
          const cited = owner.querySelector('.located[data-fact]')?.dataset.fact;
          if (context.rev && factID.test(cited || '')) context.params = {fact:cited};
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
    const sourceLabel = file && control ? file+' · '+control : element.closest('.source-plane,#sample-review canvas') ? '原件页图' :
      element.closest('.evidence-row,.sample-records [data-ref]') ? '证据引文' :
      element.closest('.release-entry')?.querySelector('small')?.textContent;
    const text = sourceLabel || element.getAttribute('aria-label') || fieldLabel?.textContent ||
      (element.matches('button,a,summary,label,h1,h2,h3,h4,[role=tab]') && element.textContent) || element.title;
    const label = text && text.replace(/\s+/g,' ').trim();
    context.target = label && label.length <= 96 ? label : '所选位置';
    const named = element.closest('[id]');
    if (named && identifier.test(named.id) && !['content','case-panel','main'].includes(named.id)) context.anchor = named.id;
  }
  return context;
}
export function describeContext(c) {
  const screen = c.screen==='case' ? screens.case+' '+c.case_id.slice(0,8) : screens[c.screen];
  return [screen, c.example || sections[c.section], c.rev && 'R'+c.rev, caseTabs[c.tab], dialogs[c.dialog],
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
  }
  return base+'case/'+c.case_id+(query.size?'?'+query:'');
}
