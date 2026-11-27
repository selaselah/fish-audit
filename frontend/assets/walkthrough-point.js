// Coordinates are ten-thousandths of the upright, issued page image.
const extent=10000;
const bounded=value=>Math.min(extent,Math.max(0,Math.round(value)));

export function pointPage(owner) {
  return owner?.id==='page-dialog' && owner.open ? owner.querySelector('.page-view[data-page-sha256]') : null;
}

export function samePointPage(view,context) {
  return view && context?.page_point && view.dataset.caseId===context.case_id && view.dataset.rev===String(context.rev) &&
    view.dataset.doc===context.doc && view.dataset.page===String(context.page) &&
    view.dataset.pageSha256===context.page_point.page_sha256;
}

export function pointLabel(point) {
  return '原图标记 · 横向 '+(point.x/100)+'% · 纵向 '+(point.y/100)+'%';
}

function place(view,point,kind) {
  const plane=view.querySelector('.source-plane');
  let mark=plane.querySelector('.walk-point-'+kind);
  if (!mark) {
    mark=document.createElement('span'); mark.className='walk-page-point walk-point-'+kind;
    mark.setAttribute('role','img'); plane.append(mark);
  }
  mark.style.left=(point.x/100)+'%'; mark.style.top=(point.y/100)+'%';
  mark.setAttribute('aria-label',pointLabel(point));
  return mark;
}

export function showDraftPoint(view,context) {
  if (samePointPage(view,context)) place(view,context.page_point,'draft');
  else view?.querySelector('.walk-point-draft')?.remove();
}

export function restorePoint(view,token,adjustZoom) {
  const match=/^(0|[1-9]\d{0,4})\.(0|[1-9]\d{0,4})\.([a-f0-9]{64})$/u.exec(token);
  const tools=view.querySelector('.source-tools');
  if (!match || +match[1]>extent || +match[2]>extent || match[3]!==view.dataset.pageSha256) {
    const message=document.createElement('span'); message.className='small'; message.setAttribute('role','status');
    message.textContent='走查标记与这版页图不符。'; tools.append(message); return;
  }
  const mark=place(view,{x:+match[1],y:+match[2]},'saved');
  const canvas=view.querySelector('.source-scroll');
  function center() {
    const r=mark.getBoundingClientRect(), area=canvas.getBoundingClientRect();
    canvas.scrollBy({left:(r.left+r.right-area.left-area.right)/2,top:(r.top+r.bottom-area.top-area.bottom)/2,behavior:'instant'});
    const visible=mark.getBoundingClientRect(), owner=view.closest('dialog'), bounds=owner.getBoundingClientRect();
    const top=Math.max(0,bounds.top,owner.querySelector('.dialog-head').getBoundingClientRect().bottom,
      owner.querySelector('.viewer-nav').getBoundingClientRect().bottom);
    if (visible.top<top || visible.bottom>Math.min(innerHeight,bounds.bottom)) {
      mark.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});
    }
  }
  const button=document.createElement('button');
  button.type='button'; button.className='walk-point-locate'; button.textContent='定位走查标记';
  button.addEventListener('click',center);
  tools.append(button);
  adjustZoom(); center();
}

export function pickPoint(view,initial,signal,finish) {
  const plane=view.querySelector('.source-plane'), canvas=view.querySelector('.source-scroll');
  const layer=plane.querySelector('svg');
  function fromScreen(x,y) {
    const matrix=layer.getScreenCTM();
    if (!matrix) return null;
    const p=new DOMPoint(x,y).matrixTransform(matrix.inverse());
    return Number.isFinite(p.x) && Number.isFinite(p.y) ? {x:bounded(p.x*10),y:bounded(p.y*10)} : null;
  }
  const image=plane.getBoundingClientRect(), pane=canvas.getBoundingClientRect();
  const center=(low,high,start,end)=>(Math.max(low,start)+Math.min(high,end))/2;
  let point=initial || fromScreen(center(image.left,image.right,pane.left,pane.right),
    center(image.top,image.bottom,pane.top,pane.bottom)) || {x:5000,y:5000};
  const mark=place(view,point,'cursor');
  const instructions=document.createElement('div'), hint=document.createElement('span'), cancel=document.createElement('button');
  instructions.className='walk-point-instructions'; hint.id='walk-point-instruction';
  hint.textContent='点选原图，或用方向键移动后按 Enter。'; cancel.type='button'; cancel.textContent='取消';
  const location=document.createElement('output'); location.className='visually-hidden'; location.textContent=pointLabel(point);
  instructions.append(hint,location,cancel); canvas.before(instructions);
  const description=canvas.getAttribute('aria-describedby');
  canvas.setAttribute('aria-describedby',[description,hint.id].filter(Boolean).join(' '));
  canvas.focus({preventScroll:true});
  mark.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'});
  const options={signal,capture:true};
  const select=p=>finish(p && {...p,page_sha256:view.dataset.pageSha256});
  cancel.addEventListener('click',()=>select(null),{signal});
  plane.addEventListener('click',event=>{
    if (event.button!==0) return;
    event.preventDefault(); event.stopImmediatePropagation();
    const p=fromScreen(event.clientX,event.clientY);
    if (p) select(p);
  },options);
  document.addEventListener('keydown',event=>{
    if (event.isComposing || event.keyCode===229) return;
    if (event.key==='Escape') {
      event.preventDefault(); event.stopImmediatePropagation(); select(null); return;
    }
    if (event.target!==canvas) return;
    const step={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];
    if (!step && event.key!=='Enter' && event.key!==' ') return;
    event.preventDefault(); event.stopImmediatePropagation();
    if (!step) { select(point); return; }
    const r=mark.getBoundingClientRect(), distance=event.shiftKey?30:3;
    point=fromScreen((r.left+r.right)/2+step[0]*distance,(r.top+r.bottom)/2+step[1]*distance) || point;
    location.textContent=pointLabel(point);
    place(view,point,'cursor').scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'});
  },options);
  signal.addEventListener('abort',()=>{
    mark.remove(); instructions.remove();
    if (description) canvas.setAttribute('aria-describedby',description);
    else canvas.removeAttribute('aria-describedby');
  },{once:true});
}
