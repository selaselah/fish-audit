// Public pages and line coordinates come from the same watermarked R8 workpaper.
(() => {
  function bind(slot, doc) {
    const link=slot.querySelector('a'), thumb=link.querySelector('img'), marker=link.querySelector('.purchase-sheet i');
    if (doc?.pdf!==link.pathname || doc.thumb!==thumb.getAttribute('src') || doc.page!==1 ||
        !Array.isArray(doc.lines) || !doc.lines.length || !doc.lines.every(l=>Number.isSafeInteger(l.line) && l.line>0 &&
          l.rects?.length===1 && l.rects[0].length===4 && l.rects[0].every(n=>Number.isFinite(n) && n>=0 && n<=1) &&
          l.rects[0][0]<l.rects[0][2] && l.rects[0][1]<l.rects[0][3])) return;
    const select=document.createElement('select');
    select.setAttribute('aria-label','选择'+doc.title+'的原行');
    for (const line of doc.lines) select.add(new Option(line.label+' · 第 '+line.line+' 行',line.ref));
    const frame=document.createElement('span'); frame.className='purchase-line-frame';
    slot.append(frame,select);
    function current() { return doc.lines[select.selectedIndex]; }
    function draw() {
      const line=current(), [x,y,right,bottom]=line.rects[0];
      Object.assign(marker.style,{left:x*100+'%',top:y*100+'%',width:(right-x)*100+'%',height:(bottom-y)*100+'%'});
      marker.hidden=false;
      link.dataset.fact=line.ref;
      link.setAttribute('aria-label','看原页，'+doc.title+'第 '+doc.page+' 页第 '+line.line+' 行，'+line.label);
      frame.replaceChildren();
      if (line.pixels?.length!==4 || !line.crop?.startsWith('/assets/purchase-')) return;
      const img=new Image(); img.className='purchase-line'; img.alt=line.label+'：'+line.value; img.dataset.fact=line.ref;
      img.onload=()=>{
        const [l,t,r,b]=line.pixels;
        if (current()===line && img.naturalWidth===r-l && img.naturalHeight===b-t) frame.replaceChildren(img);
      };
      img.src=line.crop;
    }
    select.addEventListener('change',draw);
    link.addEventListener('click',event=>{
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const request=new CustomEvent('inspect-sample-line',{cancelable:true,detail:{doc,ref:current().ref,opener:link,scale:'page'}});
      if (!document.dispatchEvent(request)) event.preventDefault();
    });
    if (typeof document.querySelector('#sample-review')?.showModal==='function') {
      link.setAttribute('aria-haspopup','dialog'); link.setAttribute('aria-controls','sample-review');
    }
    draw();
  }
  async function load() {
    const reply=await fetch('/assets/purchase-preview.json');
    if (!reply.ok) return;
    const record=await reply.json();
    if (record.revision!==8) return;
    for (const slot of document.querySelectorAll('.purchase-locator')) bind(slot,record.documents[slot.dataset.document]);
  }
  load().catch(()=>{}); // Each thumbnail links directly to its public PDF before enhancement.

})();
