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
let jumpObserver, jumpTimer;
function returnToControl() {
  jumpObserver?.disconnect();
  clearTimeout(jumpTimer);
  for (const old of document.querySelectorAll('.walk-mark')) old.classList.remove('walk-mark');
  const url=new URL(location.href), anchor=url.searchParams.get('walkat');
  if (!anchor || !/^[a-zA-Z][a-zA-Z0-9_-]{0,95}$/.test(anchor)) return;
  const [path,query]=url.hash.split('?'), params=new URLSearchParams(query);
  const comparison=anchor.startsWith('revision-') && params.get('view')==='revision-comparison'
    ? document.getElementById('revision-comparison') : null;
  const board=params.get('view')==='board-decision' && anchor.startsWith('board-');
  const receipt=params.get('view')==='payment-checks' && /^(?:quality|retest|inspection-use)-/.test(anchor);
  url.searchParams.delete('walkat');
  history.replaceState(history.state,'',url);
  function locate() {
    if (comparison && (url.hash!==location.hash || comparison.dataset.caseId!==path.split('/').at(-1) ||
        comparison.dataset.rev!==params.get('rev') || comparison.dataset.prior!==params.get('prior') ||
        (params.has('entry') && comparison.dataset.entry!==params.get('entry')))) return false;
    const el = document.getElementById(anchor);
    if (receipt) {
      const card=el?.closest('#performance-index[open] :is([data-quality-finding],[data-retest-finding],[data-use-finding])');
      if (!card || url.hash!==location.hash || card.dataset.caseId!==path.split('/').at(-1) ||
          card.dataset.rev!==params.get('rev') || (card.dataset.useFinding || card.dataset.qualityFinding || card.dataset.retestFinding)!==params.get('stage')) return false;
    }
    if (board) {
      const card=el?.closest('#board-decision,#board-unavailable');
      if (!card || url.hash!==location.hash || card.dataset.caseId!==path.split('/').at(-1) || card.dataset.rev!==params.get('rev') ||
          (params.has('filing') && card.dataset.boardFiling!==params.get('filing')) ||
          (params.has('part') && card.dataset.boardPart!==params.get('part'))) return false;
    }
    if (el?.closest('#revision-comparison:not([hidden]),#board-decision,[data-quality-finding],[data-retest-finding],[data-use-finding]')) {
      for (let parent=el.parentElement;parent && parent.id!=='revision-comparison';parent=parent.parentElement)
        if (parent.tagName==='DETAILS') parent.open=true;
    }
    if (!el?.getClientRects().length) return false;
    el.scrollIntoView({block:'center'});
    el.classList.add('walk-mark');
    setTimeout(() => el.classList.remove('walk-mark'), 2400);
    jumpObserver?.disconnect();
    return true;
  }
  if (!locate()) {
    jumpObserver = new MutationObserver(locate);
    jumpObserver.observe(comparison || document.body, {subtree:true, childList:true, attributes:true, attributeFilter:['hidden','open']});
    if (!comparison && !board && !receipt) jumpTimer = setTimeout(() => jumpObserver.disconnect(), 6000);
  }
}
addEventListener('hashchange', returnToControl);
addEventListener('walkthrough-return', returnToControl);
returnToControl();
