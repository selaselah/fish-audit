// Each public sample pairs a watermarked original with the locations from its fixed workpaper.
(() => {
  const dialog=document.querySelector('#sample-review');
  if (!dialog?.showModal) return;
  const rows=[...dialog.querySelectorAll('[data-ref]')];
  const template=rows[0].cloneNode(true);
  const records=dialog.querySelector('.sample-records');
  const describe = r => ({...r.dataset, label:r.querySelector('span').textContent, value:r.querySelector('strong').textContent});
  const samples = {
    acceptance:{title:'验收报告',version:'合成采购 · R8',image:'/assets/showcase-acceptance-page.png',pdf:'/showcase/acceptance.pdf',lines:rows.map(describe)},
    signing:{title:'采购合同',version:'合成采购 · R9',image:'/assets/showcase-signing-page.jpg',pdf:'/showcase/signing-contract.pdf',
      lines:[...document.querySelectorAll('#signing-company [data-ref]')].map(describe)},
    word:{title:'演练采购合同',version:'合成采购 · R6',image:'/assets/showcase-word-signing-page.jpg',original:'/showcase/signing-text.docx',
      lines:[...document.querySelectorAll('#signing-word .public-signing-lines [data-ref]')].map(describe)},
    calendar:{title:'采购合同',version:'合成采购 · R6',image:'/assets/showcase-calendar-page.jpg',pdf:'/showcase/calendar-contract.pdf',
      lines:[...document.querySelectorAll('#signing-calendar .public-calendar-dates [data-ref], #signing-calendar .public-signing-lines [data-ref]')].map(describe)}
  };
  const standard=document.querySelector('#sample-compare figure[data-fact="d02/p1/f13"]');
  samples.standard={title:'采购合同',version:'合成采购 · R8',image:standard.dataset.image,pdf:'/showcase/contract.pdf',
    lines:[{ref:standard.dataset.fact,line:'14',rect:standard.dataset.rect,label:'约定验收标准',value:'柜温不高于4℃'}]};
  const strips=[...document.querySelectorAll('.temperature-line')];
  const widest=Math.max(...strips.map(strip=>Number(strip.getAttribute('width'))));
  for (const strip of strips) strip.style.setProperty('--relative-width',100*Number(strip.getAttribute('width'))/widest+'%');
  for (const source of document.querySelectorAll('.temperature-originals [data-ref]')) {
    const documentSample=samples[source.dataset.sample || 'acceptance'];
    const line=documentSample.lines.find(l=>l.ref===source.dataset.ref);
    if (!line || new URL(source.href).pathname!==documentSample.pdf) continue;
    const [left,top,right,bottom]=line.rect.split(',').map(Number), mark=source.querySelector('.temperature-sheet i');
    Object.assign(mark.style,{left:left*100+'%',top:top*100+'%',width:(right-left)*100+'%',height:(bottom-top)*100+'%'});
    mark.hidden=false;
  }
  const modes=[...dialog.querySelectorAll('[data-scale]')];
  const canvas=dialog.querySelector('canvas'), status=dialog.querySelector('[role=status]');
  const context=canvas.getContext('2d');
  if (!context) return;
  let page, sample, start, end, pageView, pointer;
  const pickHint=dialog.querySelector('.page-pick-hint');
  const rectangles=new Map();
  let opener, row=rows.find(r=>r.getAttribute('aria-pressed')==='true'), mode='line';
  function draw() {
    pageView=null;
    pickHint.hidden=true;
    if (!dialog.open || !page?.naturalWidth) { updateHover(); return; }
    const width=canvas.clientWidth, height=canvas.clientHeight;
    if (!width || !height) { updateHover(); return; }
    const density=Math.min(devicePixelRatio || 1,2);
    canvas.width=Math.round(width*density); canvas.height=Math.round(height*density);
    context.setTransform(canvas.width/width,0,0,canvas.height/height,0,0);
    const w=page.naturalWidth, h=page.naturalHeight;
    const spans=rectangles.get(row) || [];
    const top=spans.length?Math.min(...spans.map(r=>r[1])):0, bottom=spans.length?Math.max(...spans.map(r=>r[3])):1;
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
    if (mode==='page') {
      pageView={x,y,width:w*scale,height:h*scale};
      context.strokeStyle='#3659a3'; context.lineWidth=1.25; context.setLineDash([3,2]);
      for (const [button,areas] of rectangles) {
        if (button===row) continue;
        for (const [l,t,r,b] of areas)
          context.strokeRect(x+l*pageView.width,y+t*pageView.height,(r-l)*pageView.width,(b-t)*pageView.height);
      }
      context.setLineDash([]);
      pickHint.hidden=rectangles.size===0;
    }
    context.fillStyle='rgba(255,196,49,.25)'; context.strokeStyle='#935d10'; context.lineWidth=1.5;
    for (const [l,t,r,b] of spans) {
      const area=[x+l*w*scale,y+t*h*scale,(r-l)*w*scale,(b-t)*h*scale];
      context.fillRect(...area); context.strokeRect(...area);
    }
    if (row) canvas.dataset.fact=row.dataset.ref;
    else delete canvas.dataset.fact;
    canvas.dataset.page=String(sample.page || 1); status.hidden=true;
    updateHover();
  }
  function select(next,scale) {
    row=next; mode=row?scale:'page';
    for (const r of rows) r.setAttribute('aria-pressed',String(r===row));
    for (const m of modes) m.setAttribute('aria-pressed',String(m.dataset.scale===mode));
    const location='第 '+(sample.page || 1)+' 页'+(row?' · 第 '+row.dataset.line+' 行':' · 整页');
    dialog.querySelector('output').textContent=location;
    canvas.setAttribute('aria-label',sample.title+location+(row?'，'+row.querySelector('span').textContent+'，'+row.querySelector('strong').textContent:''));
    draw();
  }
  function markedRow(event) {
    if (!pageView) return;
    const screen=canvas.getBoundingClientRect();
    const x=(event.clientX-screen.left-pageView.x)/pageView.width, y=(event.clientY-screen.top-pageView.y)/pageView.height;
    const dx=2/pageView.width, dy=2/pageView.height;
    let hit;
    for (const [button,areas] of rectangles) {
      if (areas.some(([l,t,r,b])=>x>=l-dx && x<=r+dx && y>=t-dy && y<=b+dy)) {
        if (hit) return; // Overlapping citations can be selected unambiguously in the field list.
        hit=button;
      }
    }
    return hit;
  }
  function updateHover() {
    const hit=pointer && markedRow(pointer);
    canvas.style.cursor=hit?'zoom-in':'';
    if (hit) canvas.title=hit.querySelector('span').textContent+' · 第 '+hit.dataset.line+' 行';
    else canvas.removeAttribute('title');
  }
  canvas.addEventListener('pointermove',event=>{
    pointer={clientX:event.clientX,clientY:event.clientY};
    updateHover();
  });
  canvas.addEventListener('pointerleave',()=>{ pointer=null; updateHover(); });
  canvas.addEventListener('click',event=>{
    const hit=markedRow(event);
    if (hit) { select(hit,'line'); hit.focus({preventScroll:true}); }
  });
  records.addEventListener('click',event=>{
    const button=event.target.closest('button[data-ref]');
    if (button) select(button,mode);
  });
  records.addEventListener('keydown',event=>{
    const index=rows.indexOf(event.target.closest('button[data-ref]'));
    if (index<0) return;
    const k={ArrowUp:(index+rows.length-1)%rows.length,ArrowDown:(index+1)%rows.length,Home:0,End:rows.length-1}[event.key];
    if (k===undefined) return;
    event.preventDefault(); select(rows[k],mode); rows[k].focus();
  });
  for (const button of modes) button.addEventListener('click',()=>select(row,button.dataset.scale));
  function load(next,loadPage) {
    sample=next; pointer=null; updateHover();
    dialog.querySelector('h2').textContent=sample.title;
    dialog.querySelector('.sample-review-head span').textContent=sample.version;
    dialog.querySelector('form button').setAttribute('aria-label','关闭'+sample.title);
    records.setAttribute('aria-label','选择'+sample.title+'原行');
    const original=records.querySelector('a');
    original.href=sample.original || sample.pdf;
    original.querySelector('.sample-file-kind').textContent=sample.media==='image'?'扫描原件':sample.original?'下载 Word 原件':'原始 PDF';
    original.querySelector('.sr-only').textContent=sample.original?'，合成演练资料':'，在新标签页打开';
    while (rows.length>sample.lines.length) rows.pop().remove();
    while (rows.length<sample.lines.length) {
      const button=template.cloneNode(true);
      original.before(button); rows.push(button);
    }
    rectangles.clear();
    for (const [i,button] of rows.entries()) {
      const line=sample.lines[i];
      for (const key of ['ref','line','rect']) button.dataset[key]=line[key];
      button.querySelector('span').textContent=line.label;
      button.querySelector('strong').textContent=line.value;
      rectangles.set(button,line.rects || [line.rect.split(',').map(Number)]);
    }
    const bounds=[...rectangles.values()].flat();
    start=bounds.length?Math.min(...bounds.map(r=>r[0])):0; end=bounds.length?Math.max(...bounds.map(r=>r[2])):1;
    modes[0].parentElement.hidden=!bounds.length;
    if (!loadPage && page?.getAttribute('src')===sample.image) return;
    // Changing width resets the pixels, so a delayed load cannot show the previous case.
    canvas.width=canvas.width; delete canvas.dataset.fact; delete canvas.dataset.page;
    status.textContent='正在载入原页…'; status.hidden=false;
    if (loadPage) {
      page=null;
      loadPage().then(img=>{if (sample===next) { page=img; draw(); }}).catch(()=>{
        if (sample!==next) return;
        status.hidden=false; status.textContent='页图未通过载入校验，可打开演练原件。';
      });
      return;
    }
    const requested=new Image(); page=requested;
    requested.onload=()=>{if (page===requested) draw();};
    requested.onerror=()=>{
      if (page!==requested) return;
      page=null; status.hidden=false; status.textContent='页图未能载入，可打开演练原件。';
    };
    requested.src=sample.image;
  }
  new ResizeObserver(draw).observe(canvas.parentElement);
  function present(doc,ref,trigger,scale='line',loadPage) {
    opener=trigger;
    trigger.focus({preventScroll:true});
    load(doc,loadPage); dialog.showModal();
    select(rows.find(r=>r.dataset.ref===ref) || rows[Math.min(2,rows.length-1)],scale);
    (row || dialog.querySelector('form button')).focus({preventScroll:true});
  }
  document.addEventListener('inspect-sample-line',event=>{
    const {doc,ref,opener,scale,loadPage}=event.detail;
    if (!doc.lines.some(l=>l.ref===ref) || !doc.lines.every(line=>{
      const bounds=line.rects || (line.rect && [line.rect.split(',').map(Number)]);
      return bounds?.length && bounds.every(r=>Array.isArray(r) && r.length===4 && r.every(n=>Number.isFinite(n) && n>=0 && n<=1) &&
        r[2]>r[0] && r[3]>r[1]);
    })) return;
    event.preventDefault(); present(doc,ref,opener,scale==='page'?'page':'line',loadPage);
  });
  document.addEventListener('inspect-sample-page',event=>{
    const {doc,opener,loadPage}=event.detail;
    if (!Array.isArray(doc.lines) || doc.lines.length || !opener?.isConnected || typeof loadPage!=='function') return;
    event.preventDefault(); present(doc,null,opener,'page',loadPage);
  });
  for (const link of document.querySelectorAll('.open-sample-review')) {
    link.setAttribute('aria-haspopup','dialog'); link.setAttribute('aria-controls',dialog.id);
    link.addEventListener('click',event=>{
      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      event.preventDefault(); present(samples[link.dataset.sample || 'acceptance'],link.dataset.ref,link,link.dataset.scale==='page'?'page':'line');
    });
  }
  dialog.addEventListener('close',()=>{
    if (!document.querySelector('dialog[open]') && (document.activeElement===document.body || dialog.contains(document.activeElement)))
      opener?.focus({preventScroll:true});
  });
})();
