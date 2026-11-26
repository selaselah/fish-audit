// Earlier releases used fragments at the site root for workpapers and invitations.
function restoreWorkspaceLink() {
  if (/^#(?:w\/|case\/|invite\/|(?:desk|account|team|rules|library)(?:\?|$))/.test(location.hash)) {
    location.replace('/app' + location.search + location.hash);
    return true;
  }
  return false;
}
if (!restoreWorkspaceLink()) {
  document.documentElement.classList.add('m-enter');
  window.addEventListener('hashchange', restoreWorkspaceLink);
  const startForm=document.querySelector('.audit-start'), startPreview=startForm.querySelector('.start-preview');
  function showStartProfile() {
    const choice=startForm.querySelector('input:checked'), profile=IntakeProfiles.find(p=>p.key===choice?.value);
    if (!profile) { startPreview.hidden=true; return; }
    startPreview.querySelector('h3').textContent=profile.label;
    for (const [selector,entries,icon] of [['.start-materials',profile.documents,'file-earmark-text'],['.start-checks',profile.checks,'clipboard-check']]) {
      startPreview.querySelector(selector+' ul').replaceChildren(...entries.map(entry=>{
        const row=document.createElement('li'), mark=document.createElement('i');
        mark.className='ui-glyph ic-'+icon; mark.setAttribute('aria-hidden','true');
        row.append(mark,entry); return row;
      }));
    }
    startPreview.hidden=false;
  }
  startForm.addEventListener('change',showStartProfile);
  window.addEventListener('pageshow',showStartProfile);
  showStartProfile();
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
  function enableTabs(tabs, changed) {
    function selectTab(tab, userAction=false) {
      for (const item of tabs) {
        const selected = item === tab;
        item.setAttribute('aria-selected', String(selected));
        item.tabIndex = selected ? 0 : -1;
        document.getElementById(item.getAttribute('aria-controls')).hidden = !selected;
      }
      if (userAction) changed?.(tab);
    }
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => selectTab(tab,true));
      tab.addEventListener('keydown', event => {
        const vertical=tab.parentElement.getAttribute('aria-orientation')==='vertical';
        const positions = {[vertical?'ArrowUp':'ArrowLeft']: (index + tabs.length - 1) % tabs.length, [vertical?'ArrowDown':'ArrowRight']: (index + 1) % tabs.length, Home: 0, End: tabs.length - 1};
        if (!(event.key in positions)) return;
        event.preventDefault();
        const next = tabs[positions[event.key]];
        selectTab(next,true);
        next.focus();
      });
    });
    return selectTab;
  }
  enableTabs([...document.querySelectorAll('.file-tabs [role="tab"]')]);
  const scenes = document.querySelector('.scene-tabs');
  const sceneTabs = [...scenes.querySelectorAll('[role="tab"]')];
  const contractExample=document.getElementById('signing-example');
  const inspectionExample=document.getElementById('inspection-example');
  const paymentExample=document.getElementById('payment-example');
  const desktopScenes=matchMedia('(min-width:961px)');
  const sceneOrientation=()=>scenes.setAttribute('aria-orientation',desktopScenes.matches?'vertical':'horizontal');
  sceneOrientation(); desktopScenes.addEventListener('change',sceneOrientation);
  for (const [i,select] of [contractExample,inspectionExample,paymentExample].entries()) {
    sceneTabs[i].querySelector('small').textContent=select.options.length+' 个场景';
  }
  const examples={company:{scene:'signing',revision:9},word:{scene:'word-signing',revision:6},calendar:{scene:'contract-dates',revision:6},pdf:{scene:'pdf-signing'}};
  const inspectionRoutes={readings:'acceptance',standards:'batch-standards',signers:'acceptance-signers',equipment:'inspection',named:'named-inspection',supplier:'suppliers',comments:'word-comments'};
  function sceneAddress(name) {
    const url=new URL(location.href);
    const scene=name==='inspection'?inspectionRoutes[inspectionExample.value]:name==='folios'?({comments:'contract-comments',reference:'payment-acceptance',timing:'signer-timing',clock:'signer-clock',proof:'payment-proof',folios:'folios'}[paymentExample.value]):name;
    url.searchParams.set('scene',name==='signing' ? examples[contractExample.value].scene : scene);
    if (url.searchParams.get('scene')==='pdf-signing') url.searchParams.set('pdf',PublicPdfSigning.selected());
    else url.searchParams.delete('pdf');
    if (scene==='batch-standards') PublicBatchStandards.address(url);
    else { url.searchParams.delete('edition'); url.searchParams.delete('batch'); }
    url.hash='workflow';
    history.replaceState(history.state,'',url);
  }
  const selectScene = enableTabs(sceneTabs,tab=>sceneAddress(tab.id.slice('scene-tab-'.length)));
  const requested=new URLSearchParams(location.search).get('scene');
  if (['signing','inspection','folios'].includes(requested)) selectScene(document.getElementById('scene-tab-'+requested));
  if (requested==='payment-acceptance') paymentExample.value='reference';
  if (requested==='signer-timing') paymentExample.value='timing';
  if (requested==='payment-proof') paymentExample.value='proof';
  if (requested==='signer-clock') paymentExample.value='clock';
  if (['contract-comments','payment-acceptance','signer-timing','signer-clock','payment-proof'].includes(requested)) selectScene(document.getElementById('scene-tab-folios'));
  if (requested==='folios') paymentExample.value='folios';
  const paymentsScene=document.getElementById('scene-folios');
  function showPayments() {
    const comments=paymentExample.value==='comments', slot=document.getElementById('payment-comments');
    const reference=paymentExample.value==='reference',demo=document.getElementById('payment-reference');
    const timing=document.getElementById('payment-signer-timing');
    const clock=document.getElementById('payment-signer-clock');
    const proof=document.getElementById('payment-execution');
    proof.hidden=paymentExample.value!=='proof';
    clock.hidden=paymentExample.value!=='clock';
    timing.hidden=paymentExample.value!=='timing';
    document.getElementById('payment-folios').hidden=paymentExample.value!=='folios';
    demo.hidden=!reference;
    slot.hidden=!comments;
    const edition=document.getElementById('payment-version');
    edition.textContent=comments?(slot.dataset.revision?'合成案例 · R'+slot.dataset.revision:'合成合同'):'合成案例 · R10';
    if (!proof.hidden) {
      edition.textContent=proof.dataset.revision?'合成案例 · R'+proof.dataset.revision:'合成案例';
      if (!paymentsScene.hidden) PublicPaymentProof.open();
    }
    if (reference) {
      edition.textContent=demo.dataset.revision?'合成案例 · R'+demo.dataset.revision:'合成案例';
      if (!paymentsScene.hidden) PublicPaymentAcceptance.open();
    }
    if (!timing.hidden || !clock.hidden) {
      const active=clock.hidden?timing:clock;
      edition.textContent=active.dataset.revision?'合成案例 · R'+active.dataset.revision:'合成案例';
      if (!paymentsScene.hidden) PublicSignerTiming.open(!clock.hidden);
    }
    if (comments && !paymentsScene.hidden) PublicAcceptanceComments.open('contract');
  }
  new MutationObserver(showPayments).observe(paymentsScene,{attributes:true,attributeFilter:['hidden']});
  paymentExample.addEventListener('change',()=>{showPayments();sceneAddress('folios');});
  document.getElementById('payment-example-choice').hidden=false;
  showPayments();
  function selectContractExample() {
    for (const key of Object.keys(examples)) document.getElementById('signing-'+key).hidden=key!==contractExample.value;
    const edition=document.getElementById('signing-example-version');
    if (contractExample.value==='pdf') {
      edition.textContent='合成合同'; PublicPdfSigning.open();
    } else edition.textContent='合成案例 · R'+examples[contractExample.value].revision;
  }
  const requestedExample=Object.keys(examples).find(key=>examples[key].scene===requested);
  if (requestedExample) {
    selectScene(document.getElementById('scene-tab-signing'));
    contractExample.value=requestedExample;
  }
  contractExample.addEventListener('change',()=>{ selectContractExample(); sceneAddress('signing'); });
  selectContractExample();
  document.getElementById('signing-example-choice').hidden=false;
  const inspectionScene=document.getElementById('scene-inspection');
  const selection=Object.keys(inspectionRoutes).find(key=>inspectionRoutes[key]===requested);
  if (selection) {
    inspectionExample.value=selection; selectScene(document.getElementById('scene-tab-inspection'));
  }
  const loadedInspections=new Set();
  const inspectionRevisions={readings:8,equipment:11,supplier:5,comments:7};
  async function showInspection() {
    const choice=inspectionExample.value;
    for (const key of Object.keys(inspectionRoutes)) document.getElementById('inspection-'+key).hidden=key!==choice;
    const version=document.getElementById('inspection-version');
    version.hidden=choice==='standards';
    version.textContent=inspectionRevisions[choice]?'合成案例 · R'+inspectionRevisions[choice]:'合成案例';
    if (inspectionScene.hidden || choice==='readings') return;
    if (choice==='standards') { PublicBatchStandards.open(); return; }
    if (choice==='supplier') {PublicSuppliers.open();return;}
    if (choice==='comments') {PublicAcceptanceComments.open();return;}
    if (choice==='signers') {
      const rev=document.getElementById('inspection-signers').dataset.revision;
      if (rev) version.textContent='合成案例 · R'+rev;
      PublicAcceptanceRoster.open(); return;
    }
    if (loadedInspections.has(choice)) return;
    loadedInspections.add(choice);
    const named=choice==='named';
    const target=document.getElementById(named?'named-inspection-demo':'inspection-demo');
    try {
      const response=await fetch(named?'/assets/named-inspection.json':'/assets/showcase-inspection.json');
      if (!response.ok) throw new Error('sample unavailable');
      const sample=await response.json(), docs=sample.documents;
      const roles=new Map(Object.entries(docs).map(([id,doc])=>[id,doc.role]));
      if (!InspectionCoverage.quantities(sample.check,sample.rows,roles)) throw new Error('sample evidence incomplete');
      inspectionRevisions[choice]=sample.rev;
      if (inspectionExample.value===choice) version.textContent='合成案例 · R'+sample.rev;
      target.replaceChildren(InspectionCoverage.deviceView(sample.check,sample.rows,(row,label)=>{
        const doc=docs[row.doc], anchor=document.createElement('a');
        anchor.href=doc.pdf; anchor.target='_blank'; anchor.rel='noopener'; anchor.textContent=label;
        if (doc.lines.some(l=>l.ref===row.id)) {
          anchor.setAttribute('aria-haspopup','dialog'); anchor.setAttribute('aria-controls','sample-review');
          anchor.addEventListener('click',event=>{
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            const request=new CustomEvent('inspect-sample-line',{cancelable:true,detail:{doc,ref:row.id,opener:anchor}});
            if (!document.dispatchEvent(request)) event.preventDefault();
          });
        }
        return anchor;
      },{expanded:true,publicSample:true,excerpt:async row=>{
        const line=docs[row.doc].lines.find(l=>l.ref===row.id);
        if (!line?.crop) return null;
        const img=new Image(); img.alt=''; img.src=line.crop; await img.decode(); return img;
      }}));
    } catch {
      loadedInspections.delete(choice);
    }
  }
  const observer=new MutationObserver(showInspection);
  observer.observe(inspectionScene,{attributes:true,attributeFilter:['hidden']});
  inspectionExample.addEventListener('change',()=>{ showInspection(); sceneAddress('inspection'); });
  document.getElementById('inspection-example-choice').hidden=false;
  showInspection();
  scenes.hidden = false;
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

  const ledgerSwitch=document.querySelector('.ledger-switch');
  const ledgerModes=[...ledgerSwitch.querySelectorAll('button')];
  function selectLedger(button) {
    for (const choice of ledgerModes) {
      const selected=choice===button;
      choice.setAttribute('aria-pressed',String(selected));
      document.getElementById(choice.getAttribute('aria-controls')).hidden=!selected;
    }
  }
  for (const [index,button] of ledgerModes.entries()) {
    button.addEventListener('click',()=>selectLedger(button));
    button.addEventListener('keydown',event=>{
      if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
      event.preventDefault();
      const next=ledgerModes[event.key==='Home'?0:event.key==='End'?ledgerModes.length-1:1-index];
      selectLedger(next); next.focus();
    });
  }
  ledgerSwitch.hidden=false;

  const phases=[...document.querySelectorAll('.phase-ledger .phase')];
  async function showPrintedTerms() {
    try {
      const response=await fetch('/assets/installment-originals.json');
      if (!response.ok) return;
      const doc=await response.json();
      for (const [i,phase] of phases.entries()) {
        const row=doc.lines[i], quote=phase.querySelector('.phase-detail q');
        if (!row || quote?.textContent!==row.value) continue;
        const link=document.createElement('a'); link.className='phase-original-clause';
        link.href=doc.pdf; link.target='_blank'; link.rel='noopener';
        link.setAttribute('aria-label',row.label+'，'+row.value+'，查看合同原行');
        link.setAttribute('aria-haspopup','dialog');
        const image=new Image(); image.alt=''; image.decoding='async';
        image.onload=()=>{link.append(image);quote.replaceWith(link);};
        link.addEventListener('click',event=>{
          if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
          const request=new CustomEvent('inspect-sample-line',{cancelable:true,detail:{doc,ref:row.ref,opener:link}});
          if (!document.dispatchEvent(request)) event.preventDefault();
        });
        image.src=row.crop;
      }
    } catch { /* The printed terms remain readable in the markup. */ }
  }
  const phaseObserver=new IntersectionObserver(records=>{
    if (records.some(r=>r.isIntersecting)) {phaseObserver.disconnect();showPrintedTerms();}
  },{rootMargin:'160px'});
  phaseObserver.observe(document.querySelector('.phase-ledger'));
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
      p.addEventListener('toggle',()=>{ if (p.open) choose(i); else draw(); });
    });
    function showLinkedPhase(hash) {
      const index=phases.findIndex(p=>'#'+p.id===hash);
      if (index<0) return;
      selectLedger(ledgerModes[0]); choose(index);
      phases[index].querySelector('summary').focus({preventScroll:true});
    }
    document.querySelector('.phase-jump').addEventListener('click',event=>{
      if (!event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) showLinkedPhase(event.currentTarget.hash);
    });
    window.addEventListener('hashchange',()=>showLinkedPhase(location.hash));
    showLinkedPhase(location.hash);
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
