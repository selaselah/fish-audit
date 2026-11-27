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
  const top = openModals.filter(d => d.open && d.isConnected).at(-1);
  if (top === owner) return;
  owner = top;
  if (!top) { document.body.append(launcher); return; }
  const close = top.querySelector('[data-close], button[aria-label^="关闭"], button[value="close"]');
  if (close) (close.closest('form[method="dialog"]') || close).before(launcher);
  else top.prepend(launcher);
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
  url.searchParams.delete('walkat');
  history.replaceState(history.state,'',url);
  function locate() {
    const el = document.getElementById(anchor);
    if (!el?.getClientRects().length) return false;
    el.scrollIntoView({block:'center'});
    el.classList.add('walk-mark');
    setTimeout(() => el.classList.remove('walk-mark'), 2400);
    jumpObserver?.disconnect();
    return true;
  }
  if (!locate()) {
    jumpObserver = new MutationObserver(locate);
    jumpObserver.observe(document.body, {subtree:true, childList:true, attributes:true, attributeFilter:['hidden','open']});
    jumpTimer = setTimeout(() => jumpObserver.disconnect(), 6000);
  }
}
addEventListener('hashchange', returnToControl);
addEventListener('walkthrough-return', returnToControl);
returnToControl();
