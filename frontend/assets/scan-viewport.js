// Inspect an unlocated scan at its original pixel resolution. All coordinates below are view coordinates.
export function createScanViewport(canvas, tools, describeView) {
  const pane=canvas.parentElement, context=canvas.getContext('2d');
  const levels=[1,1.5,2,3,4];
  const buttons=Object.fromEntries([...tools.querySelectorAll('[data-scan]')].map(b=>[b.dataset.scan,b]));
  const map=tools.querySelector('.scan-map'), miniature=map.querySelector('canvas'), frame=map.querySelector('i');
  const state=tools.querySelector('output');
  let original=null, zoom=0, turns=0, painted=-1, drag=null;
  const clamp=n=>Math.max(0,Math.min(1,n));

  function visibleArea() {
    const paper=canvas.getBoundingClientRect(), view=pane.getBoundingClientRect();
    return {
      left:clamp((view.left-paper.left)/paper.width), right:clamp((view.left+pane.clientWidth-paper.left)/paper.width),
      top:clamp((view.top-paper.top)/paper.height), bottom:clamp((view.top+pane.clientHeight-paper.top)/paper.height),
    };
  }
  function mark() {
    if (!original || map.hidden || !pane.clientWidth) return;
    const {left,right,top,bottom}=visibleArea();
    Object.assign(frame.style,{left:100*left+'%',top:100*top+'%',width:100*(right-left)+'%',height:100*(bottom-top)+'%'});
  }
  function center(x,y) {
    const paper=canvas.getBoundingClientRect(), view=pane.getBoundingClientRect();
    pane.scrollLeft+=paper.left+clamp(x)*paper.width-view.left-pane.clientWidth/2;
    pane.scrollTop+=paper.top+clamp(y)*paper.height-view.top-pane.clientHeight/2;
    mark();
  }
  function paint() {
    const w=original.naturalWidth, h=original.naturalHeight, sideways=turns%2===1;
    canvas.width=sideways?h:w;canvas.height=sideways?w:h;
    context.translate(canvas.width/2,canvas.height/2);
    context.rotate(turns*Math.PI/2);
    context.drawImage(original,-w/2,-h/2);
    const previewScale=Math.min(52/canvas.width,38/canvas.height);
    const mw=Math.max(1,Math.round(canvas.width*previewScale)), mh=Math.max(1,Math.round(canvas.height*previewScale));
    miniature.width=mw*2;miniature.height=mh*2;
    miniature.style.width=mw+'px';miniature.style.height=mh+'px';
    miniature.getContext('2d').drawImage(canvas,0,0,miniature.width,miniature.height);
    painted=turns;
  }
  function size() {
    const scale=Math.min(pane.clientWidth/canvas.width,pane.clientHeight/canvas.height)*levels[zoom];
    canvas.style.width=Math.max(1,Math.floor(canvas.width*scale))+'px';
    canvas.style.height=Math.max(1,Math.floor(canvas.height*scale))+'px';
    buttons.out.disabled=zoom===0;buttons.in.disabled=zoom===levels.length-1;
    map.hidden=zoom===0;pane.dataset.pannable=String(zoom>0);
    const label=levels[zoom]+'×'+(turns?' · '+turns*90+'°':'');
    if (state.textContent!==label) state.textContent=label;
    describeView(zoom>0);
    mark();
  }
  function change(next,rotate=false) {
    if (!original) return;
    const area=visibleArea(), x=(area.left+area.right)/2, y=(area.top+area.bottom)/2;
    zoom=Math.max(0,Math.min(levels.length-1,next));
    if (rotate) {turns=(turns+1)%4;paint();}
    size();center(rotate?1-y:x,rotate?x:y);
  }
  buttons.in.addEventListener('click',()=>change(zoom+1));
  buttons.out.addEventListener('click',()=>change(zoom-1));
  buttons.fit.addEventListener('click',()=>change(0));
  buttons.rotate.addEventListener('click',()=>change(zoom,true));
  pane.addEventListener('scroll',mark,{passive:true});
  function panKey(e) {
    if (!original || !zoom) return;
    const step={ArrowRight:[1,0],ArrowLeft:[-1,0],ArrowDown:[0,1],ArrowUp:[0,-1]}[e.key];
    if (!step) return;
    e.preventDefault();
    pane.scrollBy({left:step[0]*pane.clientWidth/3,top:step[1]*pane.clientHeight/3,behavior:'instant'});mark();
  }
  pane.addEventListener('keydown',panKey);map.addEventListener('keydown',panKey);
  pane.addEventListener('pointerdown',e=>{
    if (!original || !zoom || e.pointerType!=='mouse' || e.button!==0) return;
    drag={id:e.pointerId,x:e.clientX,y:e.clientY,left:pane.scrollLeft,top:pane.scrollTop};
    pane.setPointerCapture(e.pointerId);pane.dataset.dragging='true';
  });
  pane.addEventListener('pointermove',e=>{
    if (drag?.id!==e.pointerId) return;
    pane.scrollLeft=drag.left+drag.x-e.clientX;pane.scrollTop=drag.top+drag.y-e.clientY;
  });
  pane.addEventListener('lostpointercapture',()=>{drag=null;delete pane.dataset.dragging;});
  function locate(e) {
    const r=miniature.getBoundingClientRect();
    center((e.clientX-r.left)/r.width,(e.clientY-r.top)/r.height);
  }
  map.addEventListener('pointerdown',e=>{
    if (e.button!==0 || !e.isPrimary) return;
    map.setPointerCapture(e.pointerId);locate(e);
  });
  map.addEventListener('pointermove',e=>{if (map.hasPointerCapture(e.pointerId)) locate(e);});
  map.addEventListener('click',e=>{if (e.detail===0) center(.5,.5);});

  function reset() {
    if (drag && pane.hasPointerCapture(drag.id)) pane.releasePointerCapture(drag.id);
    original=null;zoom=0;turns=0;painted=-1;drag=null;
    tools.hidden=true;map.hidden=true;
    pane.classList.remove('scan-viewport');delete pane.dataset.pannable;delete pane.dataset.dragging;
    for (const name of ['tabindex','role','aria-label']) pane.removeAttribute(name);
    canvas.style.removeProperty('width');canvas.style.removeProperty('height');
    pane.scrollLeft=0;pane.scrollTop=0;
  }
  function show(image) {
    if (original!==image) {
      original=image;painted=-1;tools.hidden=false;
      pane.classList.add('scan-viewport');pane.tabIndex=0;pane.setAttribute('role','region');
      pane.setAttribute('aria-label','扫描原页，放大后可用方向键或拖动查看');
    }
    if (painted!==turns) paint();
    size();
  }
  return {show,reset};
}
