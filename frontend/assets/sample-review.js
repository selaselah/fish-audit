// The image and three rectangles are from the same public, watermarked R7 page.
(() => {
  const dialog=document.querySelector('#sample-review');
  if (!dialog?.showModal) return;
  const rows=[...dialog.querySelectorAll('[data-ref]')];
  const rectangles=new Map(rows.map(r=>[r,r.dataset.rect.split(',').map(Number)]));
  const bounds=[...rectangles.values()];
  const start=Math.min(...bounds.map(r=>r[0])), end=Math.max(...bounds.map(r=>r[2]));
  const modes=[...dialog.querySelectorAll('[data-scale]')];
  const canvas=dialog.querySelector('canvas'), status=dialog.querySelector('[role=status]');
  const context=canvas.getContext('2d');
  if (!context) return;
  const page=new Image();
  let opener, row=rows.find(r=>r.getAttribute('aria-pressed')==='true'), mode='line';
  function draw() {
    if (!dialog.open || !page.naturalWidth) return;
    const width=canvas.clientWidth, height=canvas.clientHeight;
    if (!width || !height) return;
    const density=Math.min(devicePixelRatio || 1,2);
    canvas.width=Math.round(width*density); canvas.height=Math.round(height*density);
    context.setTransform(canvas.width/width,0,0,canvas.height/height,0,0);
    const w=page.naturalWidth, h=page.naturalHeight;
    const [left,top,right,bottom]=rectangles.get(row);
    const lineWidth=(right-left)*w, lineHeight=(bottom-top)*h;
    const viewWidth=Math.min(w,Math.max((end-start)*w+100,Math.min(810,width*1.45)));
    const scale=mode==='page'?Math.min(width/w,height/h):width/viewWidth;
    function origin(view,extent,center) {
      if (view>=extent) return (view-extent)/2;
      return Math.max(view-extent,Math.min(0,view/2-center));
    }
    const x=origin(width,w*scale,(start+end)*w*scale/2);
    const y=origin(height,h*scale,(top+bottom)*h*scale/2);
    context.fillStyle='#e9edf3'; context.fillRect(0,0,width,height);
    context.drawImage(page,x,y,w*scale,h*scale);
    const highlight=[x+left*w*scale,y+top*h*scale,lineWidth*scale,lineHeight*scale];
    context.fillStyle='rgba(255,196,49,.25)'; context.fillRect(...highlight);
    context.strokeStyle='#935d10'; context.lineWidth=1.5; context.strokeRect(...highlight);
    canvas.dataset.fact=row.dataset.ref; status.hidden=true;
  }
  function select(next,scale) {
    row=next; mode=scale;
    for (const r of rows) r.setAttribute('aria-pressed',String(r===row));
    for (const m of modes) m.setAttribute('aria-pressed',String(m.dataset.scale===mode));
    const location='第 1 页 · 第 '+row.dataset.line+' 行';
    dialog.querySelector('output').textContent=location;
    canvas.setAttribute('aria-label','验收报告'+location+'，'+row.querySelector('span').textContent+'，'+row.querySelector('strong').textContent);
    draw();
  }
  for (const [index,button] of rows.entries()) {
    button.addEventListener('click',()=>select(button,mode));
    button.addEventListener('keydown',event=>{
      const k={ArrowUp:(index+rows.length-1)%rows.length,ArrowDown:(index+1)%rows.length,Home:0,End:rows.length-1}[event.key];
      if (k===undefined) return;
      event.preventDefault(); select(rows[k],mode); rows[k].focus();
    });
  }
  for (const button of modes) button.addEventListener('click',()=>select(row,button.dataset.scale));
  page.onload=draw;
  page.onerror=()=>{
    page.removeAttribute('src'); status.hidden=false; status.textContent='页图未能载入，可打开原始 PDF。';
  };
  new ResizeObserver(draw).observe(canvas.parentElement);
  for (const link of document.querySelectorAll('.open-sample-review')) {
    link.setAttribute('aria-haspopup','dialog'); link.setAttribute('aria-controls',dialog.id);
    link.addEventListener('click',event=>{
      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      event.preventDefault(); opener=link; dialog.showModal();
      if (!page.hasAttribute('src')) {
        status.textContent='正在载入原页…'; status.hidden=false;
        page.src='/assets/showcase-acceptance-page.png';
      }
      select(rows[2],'line'); row.focus({preventScroll:true});
    });
  }
  dialog.addEventListener('close',()=>opener?.focus({preventScroll:true}));
})();
