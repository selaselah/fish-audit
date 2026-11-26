const PublicPdfSigning = (() => {
  const modes=['typeset','current','earlier'];
  const requested=new URL(location.href).searchParams.get('pdf');
  let samples, version=modes.includes(requested)?requested:'earlier', request;
  function show(mode, remember=false) {
    if (!modes.includes(mode)) return;
    version=mode;
    if (remember) {
      const url=new URL(location.href);
      url.searchParams.set('scene','pdf-signing'); url.searchParams.set('pdf',mode); url.hash='workflow';
      history.replaceState(history.state,'',url);
    }
    const scene=document.getElementById('signing-pdf'), record=samples?.[mode];
    const picker=scene.querySelector('.pdf-demo-choices');
    for (const button of picker.children) button.setAttribute('aria-pressed',String(button.dataset.pdfMode===mode));
    if (record && !scene.hidden) {
      const card=PdfSignatureCard.render({...record,id:'public-pdf-signatures',basis:samples.basis});
      scene.querySelector('.pdf-demo-view').replaceChildren(card);
      document.getElementById('signing-example-version').textContent='合成案例 · R'+record.revision;
    }
  }
  function open() {
    const scene=document.getElementById('signing-pdf');
    if (samples) {show(version);return;}
    if (request) return;
    request=fetch('/assets/pdf-signing-samples.json').then(response=>{
      if (!response.ok) throw new Error();
      return response.json();
    }).then(data=>{
      samples=data;
      for (const button of scene.querySelectorAll('[data-pdf-mode]')) button.addEventListener('click',()=>show(button.dataset.pdfMode,true));
      scene.querySelector('.pdf-demo-choices').hidden=false; show(version);
    }).catch(()=>{}).finally(()=>{request=null;}); // The original remains available through the fallback link.
  }
  return {open,selected:()=>version};
})();
