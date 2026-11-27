// The printed rows, crops and normalized page positions belong to the same watermarked R8 workpaper.
(() => {
  function bind(slot, doc) {
    const link=slot.querySelector('a'), thumb=link.querySelector('img'), sheet=link.querySelector('.purchase-sheet');
    const marker=sheet.querySelector('i');
    if (doc?.pdf!==link.pathname || doc.thumb!==thumb.getAttribute('src') || doc.page!==1 ||
        !Array.isArray(doc.lines) || !doc.lines.length || new Set(doc.lines.map(l=>l.ref)).size!==doc.lines.length ||
        !doc.lines.every(l=>Number.isSafeInteger(l.line) && l.line>0 && l.rects?.length===1 && l.rects[0].length===4 &&
          l.rects[0].every(n=>Number.isFinite(n) && n>=0 && n<=1) && l.rects[0][0]<l.rects[0][2] && l.rects[0][1]<l.rects[0][3])) return;
    const lines=doc.lines.slice().sort((a,b)=>a.line-b.line);
    const select=document.createElement('select');
    select.setAttribute('aria-label','选择'+doc.title+'的原行');
    for (const line of lines) select.add(new Option(line.label+' · 第 '+line.line+' 行',line.ref));
    select.value=doc.lines[0].ref;
    const frame=document.createElement('span');frame.className='purchase-line-frame';
    const nav=document.createElement('div'), picker=document.createElement('div'), title=document.createElement('strong'), place=document.createElement('small');
    nav.className='purchase-evidence-nav';nav.setAttribute('role','group');nav.setAttribute('aria-label',doc.title+'证据导航');
    picker.className='purchase-line-picker';title.setAttribute('aria-hidden','true');place.setAttribute('aria-hidden','true');
    const live=document.createElement('span');live.className='sr-only';live.setAttribute('role','status');
    picker.append(title,place,select);
    function arrow(step) {
      const b=document.createElement('button');b.type='button';b.dataset.step=String(step);
      b.setAttribute('aria-label',(step<0?'上一条':'下一条')+doc.title+'原行');
      const glyph=document.createElement('i');glyph.className='ui-glyph ic-chevron-down';glyph.setAttribute('aria-hidden','true');b.append(glyph);
      b.addEventListener('click',()=>{
        const target=select.selectedIndex+step;
        if (target<0 || target>=lines.length) return;
        select.selectedIndex=target;draw(true);
      });
      return b;
    }
    const prev=arrow(-1), next=arrow(1);
    nav.append(prev,picker,next,live);slot.append(frame,nav);
    function position(node,[l,t,r,b]) {
      Object.assign(node.style,{left:l*100+'%',top:t*100+'%',width:(r-l)*100+'%',height:(b-t)*100+'%'});
    }
    for (const line of lines) {
      const area=document.createElement('span');area.className='purchase-citation';area.setAttribute('aria-hidden','true');
      area.dataset.previewRef=line.ref;position(area,line.rects[0]);sheet.append(area);
    }
    function current() { return lines[select.selectedIndex]; }
    function draw(announce=false) {
      const line=current();
      position(marker,line.rects[0]);marker.hidden=false;
      for (const area of sheet.querySelectorAll('.purchase-citation')) area.hidden=area.dataset.previewRef===line.ref;
      title.textContent=line.label;place.textContent='第 '+line.line+' 行';
      prev.setAttribute('aria-disabled',String(select.selectedIndex===0));next.setAttribute('aria-disabled',String(select.selectedIndex===lines.length-1));
      if (announce) live.textContent=line.label+'，第 '+line.line+' 行';
      link.dataset.fact=line.ref;link.setAttribute('aria-label','看原页，'+doc.title+'第 '+doc.page+' 页第 '+line.line+' 行，'+line.label);
      frame.replaceChildren();
      if (line.pixels?.length!==4 || !line.crop?.startsWith('/assets/purchase-')) return;
      const img=new Image();img.className='purchase-line';img.alt=line.label+'：'+line.value;img.dataset.fact=line.ref;
      img.onload=()=>{
        const [l,t,r,b]=line.pixels;
        if (current()===line && img.naturalWidth===r-l && img.naturalHeight===b-t) frame.replaceChildren(img);
      };
      img.src=line.crop;
    }
    function hitAt(event) {
      if (!event.detail || !matchMedia('(hover:hover) and (pointer:fine)').matches) return;
      const bounds=thumb.getBoundingClientRect();
      const x=(event.clientX-bounds.left)/bounds.width,y=(event.clientY-bounds.top)/bounds.height;
      const hits=lines.filter(line=>{const [l,t,r,b]=line.rects[0];return x>=l && x<=r && y>=t && y<=b;});
      return hits.length===1?hits[0]:null;
    }
    select.addEventListener('change',()=>draw());
    link.addEventListener('click',event=>{
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const hit=hitAt(event);
      if (hit && current()!==hit) {select.value=hit.ref;draw();}
      const request=new CustomEvent('inspect-sample-line',{cancelable:true,detail:{
        doc,ref:current().ref,opener:link,scale:hit?'line':'page',loadPage:()=>VerifiedSamplePage.load(doc)}});
      if (!document.dispatchEvent(request)) event.preventDefault();
    });
    if (typeof document.querySelector('#sample-review')?.showModal==='function') {
      link.setAttribute('aria-haspopup','dialog');link.setAttribute('aria-controls','sample-review');
    }
    draw();
  }
  async function load() {
    const integrity=document.getElementById('sample')?.dataset.evidenceIntegrity;
    if (!/^sha256-[A-Za-z0-9+/]{43}=$/.test(integrity)) return;
    const reply=await fetch('/assets/purchase-preview.json',{integrity});
    if (!reply.ok) return;
    const record=await reply.json();
    if (record.revision!==8) return;
    for (const slot of document.querySelectorAll('.purchase-locator')) bind(slot,record.documents[slot.dataset.document]);
  }
  load().catch(()=>{});
})();
