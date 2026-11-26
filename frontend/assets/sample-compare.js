// Read the same two fixed page images at four synchronized scales.
(() => {
  const triggers=document.querySelectorAll('#compare-sample,#compare-inspection'), dialog=document.querySelector('#sample-compare');
  if (!triggers.length || !dialog?.showModal) return;
  let opener;
  const zoom=dialog.querySelector('input[type=range]'), caption=dialog.querySelector('output');
  const levels=['整页','页宽','放大','原行'];
  const sheets=[...dialog.querySelectorAll('figure')].map(figure=>{
    const canvas=figure.querySelector('canvas');
    return {figure,canvas,context:canvas.getContext('2d'),rect:figure.dataset.rect.split(',').map(Number),image:null};
  });
  if (sheets.some(s=>!s.context)) return;
  function draw() {
    const level=Number(zoom.value);
    caption.value=levels[level]; zoom.setAttribute('aria-valuetext',levels[level]);
    for (const step of dialog.querySelectorAll('[data-step]')) step.disabled=level+Number(step.dataset.step)<0 || level+Number(step.dataset.step)>=levels.length;
    if (!dialog.open) return;
    for (const {figure,canvas,context,rect,image} of sheets) {
      if (!image?.naturalWidth) continue;
      const width=canvas.clientWidth,height=canvas.clientHeight;
      if (!width || !height) continue;
      const density=Math.min(devicePixelRatio||1,2);
      canvas.width=Math.round(width*density);canvas.height=Math.round(height*density);
      context.setTransform(canvas.width/width,0,0,canvas.height/height,0,0);
      const w=image.naturalWidth,h=image.naturalHeight,[left,top,right,bottom]=rect;
      // Use the wider contract line for both documents so the lettering stays comparable.
      const scale=[Math.min(width/w,height/h),width/w,1.68*width/w,2.52*width/w][level];
      function origin(view,extent,center) {
        return extent<=view?(view-extent)/2:Math.min(0,Math.max(view-extent,view/2-center));
      }
      const x=origin(width,w*scale,(left+right)*w*scale/2), y=origin(height,h*scale,(top+bottom)*h*scale/2);
      context.fillStyle='#edf0f5';context.fillRect(0,0,width,height);
      context.drawImage(image,x,y,w*scale,h*scale);
      const bounds=[x+left*w*scale,y+top*h*scale,(right-left)*w*scale,(bottom-top)*h*scale];
      context.fillStyle='rgba(243,178,55,.24)';context.fillRect(...bounds);
      context.strokeStyle='#8a510b';context.lineWidth=1.5;context.strokeRect(...bounds);
      canvas.dataset.fact=figure.dataset.fact;canvas.dataset.scale=String(level);
      figure.querySelector('[role=status]').hidden=true;
    }
  }
  function open(event) {
    opener=event.currentTarget; opener.focus({preventScroll:true});dialog.showModal();zoom.value='2';
    for (const sheet of sheets) {
      if (sheet.image) continue;
      const image=new Image();sheet.image=image;
      image.onload=draw;
      image.onerror=()=>{sheet.image=null;const status=sheet.figure.querySelector('[role=status]');status.textContent='页图载入失败，可打开原始 PDF。';status.hidden=false;};
      image.src=sheet.figure.dataset.image;
    }
    draw();
  }
  for (const trigger of triggers) {trigger.hidden=false; trigger.addEventListener('click',open);}
  zoom.addEventListener('input',draw);
  for (const button of dialog.querySelectorAll('[data-step]')) button.addEventListener('click',()=>{
    zoom.value=String(Number(zoom.value)+Number(button.dataset.step));draw();
  });
  const observer=new ResizeObserver(draw);
  for (const {canvas} of sheets) observer.observe(canvas);
  dialog.addEventListener('close',()=>{
    if (!document.querySelector('dialog[open]') && (document.activeElement===document.body || dialog.contains(document.activeElement)))
      opener?.focus({preventScroll:true});
  });
})();
