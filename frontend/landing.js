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

  const phases=[...document.querySelectorAll('.phase-ledger .phase')];
  const shares=phases.map(p=>Number.parseFloat(p.querySelector('.phase-share').textContent));
  const dial=document.querySelector('.phase-dial');
  if (shares.every(n=>n>0) && shares.reduce((a,b)=>a+b,0)===100) {
    function selected() { return phases.findIndex(p=>p.open); }
    function draw() {
      const current=selected();
      const stops=[];
      let start=0;
      shares.forEach((n,i)=>{
        const end=start+n;
        const color=i===current?'var(--accent)':i%2?'#a0b2d3':'#cad5e8';
        stops.push(color+' '+start+'% '+(end-.6)+'%','white '+(end-.6)+'% '+end+'%'); start=end;
      });
      dial.style.setProperty('--installments','conic-gradient('+stops.join(',')+')');
      const share=current<0?'100%':shares[current]+'%';
      const basis=current<0?'合同合计':'约定占比';
      dial.querySelector('.dial-share').textContent=share;
      dial.querySelector('.dial-label').textContent=basis;
      const name=current<0?'合同合计':phases[current].querySelector('.phase-name').textContent;
      dial.setAttribute('aria-label',share+' '+basis+'，'+name+'，切换到下一期');
      dial.title='切换到下一期';
    }
    function choose(index) {
      phases[index].open=true;
      // Explicitly synchronize browsers that do not implement exclusive details groups.
      phases.forEach((p,i)=>{ if (i!==index) p.open=false; });
      draw();
    }
    phases.forEach((p,i)=>{
      p.id='sample-phase-'+(i+1);
      p.addEventListener('toggle',()=>{ if (p.open) choose(i); else draw(); });
    });
    dial.setAttribute('aria-controls',phases.map(p=>p.id).join(' '));
    dial.addEventListener('click',()=>choose((selected()+1)%phases.length));
    dial.addEventListener('keydown',event=>{
      const i=selected();
      const target={ArrowLeft:(i<=0?phases.length:i)-1,ArrowRight:(i+1)%phases.length,Home:0,End:phases.length-1}[event.key];
      if (target!==undefined) { event.preventDefault(); choose(target); }
    });
    draw(); dial.hidden=false;
  }
}
