// Earlier releases used fragments at the site root for workpapers and invitations.
function restoreWorkspaceLink() {
  if (/^#(?:w\/|case\/|invite\/|(?:desk|account|team|rules|library)(?:\?|$))/.test(location.hash)) {
    location.replace('/app' + location.search + location.hash);
    return true;
  }
  return false;
}
if (!restoreWorkspaceLink()) {
  window.addEventListener('hashchange', restoreWorkspaceLink);
  const menu = document.querySelector('.mobile-menu');
  menu.addEventListener('click', event => {
    if (event.target.closest('a')) menu.open = false;
  });
  document.addEventListener('click', event => {
    if (menu.open && !menu.contains(event.target)) menu.open = false;
  });
  document.addEventListener('keydown', event => {
    if (menu.open && event.key === 'Escape') {
      menu.open = false;
      menu.querySelector('summary').focus();
    }
  });
  const tabs = [...document.querySelectorAll('.file-tabs [role="tab"]')];
  function selectTab(tab) {
    for (const item of tabs) {
      const selected = item === tab;
      item.setAttribute('aria-selected', String(selected));
      item.tabIndex = selected ? 0 : -1;
      document.getElementById(item.getAttribute('aria-controls')).hidden = !selected;
    }
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectTab(tab));
    tab.addEventListener('keydown', event => {
      const positions = {ArrowLeft: (index + tabs.length - 1) % tabs.length, ArrowRight: (index + 1) % tabs.length, Home: 0, End: tabs.length - 1};
      if (!(event.key in positions)) return;
      event.preventDefault();
      const next = tabs[positions[event.key]];
      selectTab(next);
      next.focus();
    });
  });
  const readingSwitch = document.querySelector('.reading-switch');
  const readings = [...readingSwitch.querySelectorAll('button')];
  function selectReading(button) {
    for (const option of readings) {
      const selected = option === button;
      option.setAttribute('aria-pressed', String(selected));
      document.getElementById(option.getAttribute('aria-controls')).hidden = !selected;
    }
  }
  for (const button of readings) button.addEventListener('click', () => selectReading(button));
  selectReading(readings[0]);
  readingSwitch.hidden = false;
}
