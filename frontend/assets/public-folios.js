(() => {
  const panel=document.getElementById('scene-folios'), toggle=panel.querySelector('input');
  const choices=[...panel.querySelectorAll('.public-folio-rows a')];
  let loading=false;
  async function load() {
    if (panel.hidden || loading) return;
    loading=true;
    try {
      const response=await fetch('/assets/showcase-payment-folios.json');
      if (!response.ok) throw new Error('样本未能载入');
      const {pages}=await response.json();
      const numbers=pages.map(p=>p.lines.find(r=>r.ref===p.focus)?.value);
      if (pages.length!==choices.length || !choices.every((a,i)=>a.querySelector('strong').textContent===numbers[i] &&
          a.getAttribute('href')===pages[i].pdf && pages[i].page===i+1)) return;
      function paint() {
        choices.forEach((a,i)=>{
          a.querySelector('strong').replaceChildren(toggle.checked ? printedNumberDifference(numbers[i],numbers[1-i]) : numbers[i]);
        });
      }
      choices.forEach((a,i)=>{
        const doc=pages[i], source=doc.lines.find(r=>r.ref===doc.focus);
        const highlight=a.querySelector('.public-folio-thumb i');
        const [left,top,right,bottom]=source.rect.split(',').map(Number);
        highlight.style.left=left*100+'%'; highlight.style.top=top*100+'%';
        highlight.style.width=(right-left)*100+'%'; highlight.style.height=(bottom-top)*100+'%';
        a.setAttribute('aria-haspopup','dialog'); a.setAttribute('aria-controls','sample-review');
        a.addEventListener('click',event=>{
          if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
          const request=new CustomEvent('inspect-sample-line',{cancelable:true,detail:{doc,ref:doc.focus,opener:a}});
          if (!document.dispatchEvent(request)) event.preventDefault();
        });
      });
      toggle.addEventListener('change',paint); toggle.parentElement.hidden=false; paint();
      observer.disconnect();
    } catch { loading=false; }
  }
  const observer=new MutationObserver(load);
  observer.observe(panel,{attributes:true,attributeFilter:['hidden']});
  load();
})();
