const launcher = document.createElement('button');
launcher.type = 'button';
launcher.className = 'walk-launch';
launcher.id = 'walk-launch';
launcher.title = '记录产品走查意见';
launcher.setAttribute('aria-haspopup', 'dialog');
launcher.innerHTML = '<i class="ui-glyph ic-journal-text" aria-hidden="true"></i><span>提意见</span>';
document.body.append(launcher);

let owner;
const openModals = [];
function placeLauncher() {
  for (let i=openModals.length-1;i>=0;i--) {
    if (!openModals[i].open || !openModals[i].isConnected) openModals.splice(i,1);
  }
  const top = openModals.at(-1);
  if (top === owner && launcher.isConnected && (top ? top.contains(launcher) : launcher.parentElement === document.body)) return;
  owner = top;
  if (!top) document.body.append(launcher);
  else {
    const close = top.querySelector('[data-close], button[aria-label^="关闭"], button[value="close"]');
    if (close) (close.closest('form[method="dialog"]') || close).before(launcher);
    else top.prepend(launcher);
  }
  launcher.dispatchEvent(new Event('walkthrough-owner-change'));
}
document.addEventListener('toggle', event => {
  const panel = event.target;
  if (!(panel instanceof HTMLDialogElement) || panel.id === 'walk-dialog') return;
  const i = openModals.indexOf(panel);
  if (i >= 0) openModals.splice(i, 1);
  if (panel.open) openModals.push(panel);
  placeLauncher();
}, true);
for (const panel of document.querySelectorAll('dialog[open]')) openModals.push(panel);
placeLauncher();
// Navigation can remove an open workpaper dialog without dispatching its close or toggle event.
new MutationObserver(() => {
  if (!launcher.isConnected || owner && !owner.isConnected) placeLauncher();
}).observe(document.body,{childList:true,subtree:true});

let loading = false;
launcher.addEventListener('click', async () => {
  if (loading) return;
  loading = true;
  try {
    const recorder = await import('./walkthrough.js');
    await recorder.openRecorder(owner);
  } catch {
    launcher.querySelector('span').textContent = '重试提意见';
    launcher.title = '走查面板未载入，点击重试';
  } finally { loading = false; }
});

// A saved link can point to an element that is rendered after the workpaper loads.
let stopJump, jumpRoute;
function returnToControl() {
  const url=new URL(location.href), anchor=url.searchParams.get('walkat');
  const route=url.pathname+url.hash;
  if (!anchor && jumpRoute===route) return;
  stopJump?.();
  for (const old of document.querySelectorAll('.walk-mark')) old.classList.remove('walk-mark');
  jumpRoute=null;
  if (!anchor || !/^[a-zA-Z][a-zA-Z0-9_-]{0,95}$/.test(anchor)) return;
  jumpRoute=route;
  const [path,query]=url.hash.split('?'), params=new URLSearchParams(query);
  const comparison=anchor.startsWith('revision-') && params.get('view')==='revision-comparison'
    ? document.getElementById('revision-comparison') : null;
  const board=params.get('view')==='board-decision' && anchor.startsWith('board-');
  const receipt=params.get('view')==='payment-checks' && /^(?:quality|retest|inspection-use|payment-approval|payment-clock|contract-approver|approver-change|installment-count)-/.test(anchor);
  const party=anchor.startsWith('party-reading-');
  const limits=params.get('view')==='acceptance-limits' && anchor.startsWith('limits-H02-');
  const form=/^(?:form|number|serial)-(H0[1245]-[1-9][0-9]*)-d[0-9]+-p[1-9][0-9]*-l[1-9][0-9]*$/.exec(anchor);
  const formView=form && ({H01:'contract-signing-form',H02:'acceptance-checks'}[form[1].slice(0,3)] || 'payment-checks');
  url.searchParams.delete('walkat');
  history.replaceState(history.state,'',url);
  let marked, fallbackTimer;
  const interaction=new AbortController(), observer=new MutationObserver(locate);
  function release() {
    observer.disconnect();
    clearTimeout(fallbackTimer);
    interaction.abort();
    marked?.classList.remove('walk-mark');
    stopJump=null;
  }
  stopJump=release;
  // Keep the selected position through late rendering, until the reader acts or leaves this route.
  for (const event of ['pointerdown','keydown'])
    document.addEventListener(event,release,{capture:true,signal:interaction.signal});
  function locate() {
    if (comparison && (url.hash!==location.hash || comparison.dataset.caseId!==path.split('/').at(-1) ||
        comparison.dataset.rev!==params.get('rev') || comparison.dataset.prior!==params.get('prior') ||
        (params.has('entry') && comparison.dataset.entry!==params.get('entry')))) return false;
    const el = document.getElementById(anchor);
    if (form && (!el || url.hash!==location.hash || (el.dataset.formFinding || el.dataset.numberFinding || el.dataset.serialFinding)!==form[1] ||
        el.dataset.caseId!==path.split('/').at(-1) || el.dataset.rev!==params.get('rev') ||
        params.get('view')!==formView || formView!=='contract-signing-form' && !el.closest('#performance-index[open]') ||
        formView==='payment-checks' && params.get('stage')!==form[1])) return false;
    if (limits) {
      const card=el?.closest('[data-limit-finding]');
      if (!card || url.hash!==location.hash || card.dataset.caseId!==path.split('/').at(-1) ||
          card.dataset.rev!==params.get('rev') || (anchor!==card.id && !anchor.startsWith(card.id+'-'))) return false;
    }
    if (party && (!el?.matches('#page-dialog[open] .located [data-party-reading]') || url.hash!==location.hash ||
        el.dataset.caseId!==path.split('/').at(-1) || el.dataset.rev!==params.get('rev') ||
        el.closest('.evidence-row')?.dataset.fact!==params.get('fact'))) return false;
    if (receipt) {
      const card=el?.closest('#performance-index[open] :is([data-quality-finding],[data-retest-finding],[data-use-finding],[data-count-finding])');
      if (!card || url.hash!==location.hash || card.dataset.caseId!==path.split('/').at(-1) ||
          card.dataset.rev!==params.get('rev') || (card.dataset.countFinding || card.dataset.useFinding || card.dataset.qualityFinding || card.dataset.retestFinding)!==params.get('stage')) return false;
    }
    if (board) {
      const card=el?.closest('#board-decision,#board-unavailable');
      if (!card || url.hash!==location.hash || card.dataset.caseId!==path.split('/').at(-1) || card.dataset.rev!==params.get('rev') ||
          (params.has('filing') && card.dataset.boardFiling!==params.get('filing')) ||
          (params.has('part') && card.dataset.boardPart!==params.get('part'))) return false;
    }
    if (el?.closest('#revision-comparison:not([hidden]),#board-decision,[data-limit-finding],[data-quality-finding],[data-retest-finding],[data-use-finding],[data-count-finding],[data-form-finding],[data-number-finding],[data-serial-finding]')) {
      for (let parent=el.parentElement;parent && parent.id!=='revision-comparison';parent=parent.parentElement)
        if (parent.tagName==='DETAILS' && !parent.open) parent.open=true;
    }
    if (!el?.getClientRects().length) return false;
    if (marked===el) return true;
    const focusTarget=!marked || document.activeElement===marked || document.activeElement===document.body;
    marked?.classList.remove('walk-mark');
    marked=el;
    el.scrollIntoView({block:'center'});
    if (focusTarget && el.matches('button,a[href],input,select,textarea,summary,[tabindex]')) el.focus({preventScroll:true});
    el.classList.add('walk-mark');
    clearTimeout(fallbackTimer);
    return true;
  }
  observer.observe(document.body, {subtree:true, childList:true, attributes:true, attributeFilter:['hidden','open']});
  if (!locate() && !comparison && !board && !receipt && !party && !limits && !form)
    fallbackTimer = setTimeout(release,6000);
}
addEventListener('hashchange', returnToControl);
addEventListener('walkthrough-return', returnToControl);
returnToControl();
