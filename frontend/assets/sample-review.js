// Each public sample pairs a watermarked original with the locations from its fixed workpaper.
(() => {
  const dialog=document.querySelector('#sample-review');
  if (!dialog?.showModal) return;
  const rows=[...dialog.querySelectorAll('[data-ref]')];
  const describe = r => ({...r.dataset, label:r.querySelector('span').textContent, value:r.querySelector('strong').textContent});
  const samples = {
    acceptance:{title:'验收报告',version:'合成采购 · R7',image:'/assets/showcase-acceptance-page.png',pdf:'/showcase/acceptance.pdf',lines:rows.map(describe)},
    signing:{title:'采购合同',version:'合成采购 · R9',image:'/assets/showcase-signing-page.jpg',pdf:'/showcase/signing-contract.pdf',
      lines:[...document.querySelectorAll('.public-signing-lines [data-ref]')].map(describe)}
  };
  const modes=[...dialog.querySelectorAll('[data-scale]')];
  const canvas=dialog.querySelector('canvas'), status=dialog.querySelector('[role=status]');
  const context=canvas.getContext('2d');
  if (!context) return;
  let page, sample, start, end;
  const rectangles=new Map();
  let opener, row=rows.find(r=>r.getAttribute('aria-pressed')==='true'), mode='line';
  function draw() {
    if (!dialog.open || !page?.naturalWidth) return;
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
    canvas.setAttribute('aria-label',sample.title+location+'，'+row.querySelector('span').textContent+'，'+row.querySelector('strong').textContent);
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
  function load(next) {
    sample=next;
    dialog.querySelector('h2').textContent=sample.title;
    dialog.querySelector('.sample-review-head span').textContent=sample.version;
    dialog.querySelector('form button').setAttribute('aria-label','关闭'+sample.title);
    dialog.querySelector('.sample-records').setAttribute('aria-label','选择'+sample.title+'原行');
    dialog.querySelector('.sample-records a').href=sample.pdf;
    for (const [i,button] of rows.entries()) {
      const line=sample.lines[i];
      for (const key of ['ref','line','rect']) button.dataset[key]=line[key];
      button.querySelector('span').textContent=line.label;
      button.querySelector('strong').textContent=line.value;
      rectangles.set(button,line.rect.split(',').map(Number));
    }
    const bounds=[...rectangles.values()];
    start=Math.min(...bounds.map(r=>r[0])); end=Math.max(...bounds.map(r=>r[2]));
    if (page?.getAttribute('src')===sample.image) return;
    // Changing width resets the pixels, so a delayed load cannot show the previous case.
    canvas.width=canvas.width; delete canvas.dataset.fact;
    status.textContent='正在载入原页…'; status.hidden=false;
    const requested=new Image(); page=requested;
    requested.onload=()=>{if (page===requested) draw();};
    requested.onerror=()=>{
      if (page!==requested) return;
      page=null; status.hidden=false; status.textContent='页图未能载入，可打开原始 PDF。';
    };
    requested.src=sample.image;
  }
  new ResizeObserver(draw).observe(canvas.parentElement);
  function present(doc,ref,trigger) {
    opener=trigger;
    trigger.focus({preventScroll:true});
    load(doc); dialog.showModal();
    select(rows.find(r=>r.dataset.ref===ref) || rows[2],'line');
    row.focus({preventScroll:true});
  }
  document.addEventListener('inspect-sample-line',event=>{
    const {doc,ref,opener}=event.detail;
    if (!doc.lines.some(l=>l.ref===ref) || doc.lines.length!==rows.length) return;
    event.preventDefault(); present(doc,ref,opener);
  });
  for (const link of document.querySelectorAll('.open-sample-review')) {
    link.setAttribute('aria-haspopup','dialog'); link.setAttribute('aria-controls',dialog.id);
    link.addEventListener('click',event=>{
      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      event.preventDefault(); present(samples[link.dataset.sample || 'acceptance'],link.dataset.ref,link);
    });
  }
  dialog.addEventListener('close',()=>{
    if (!dialog.open && (document.activeElement===document.body || dialog.contains(document.activeElement)))
      opener?.focus({preventScroll:true});
  });
})();
