// Decode only the published image bytes named in the fixed sample's index.
const VerifiedSamplePage = (() => {
  const pages = new Map();
  function load(doc) {
    const key = doc.image+' '+doc.page_sha256;
    if (pages.has(key)) return pages.get(key);
    if (!/^[a-f0-9]{64}$/.test(doc.page_sha256)) return Promise.reject(new Error('Missing page digest'));
    const digest = Uint8Array.from(doc.page_sha256.match(/../g),hex=>parseInt(hex,16));
    const integrity = 'sha256-'+btoa(String.fromCharCode(...digest));
    const request = fetch(doc.image,{integrity}).then(async response=>{
      if (!response.ok) throw new Error('Page unavailable');
      const url = URL.createObjectURL(await response.blob()), img = new Image();
      try { img.src = url; await img.decode(); return img; } finally { URL.revokeObjectURL(url); }
    });
    pages.set(key,request); request.catch(()=>pages.delete(key));
    return request;
  }
  function crop(img, bounds, canvas=document.createElement('canvas')) {
    const w=img.naturalWidth,h=img.naturalHeight,[l,t,r,b]=bounds;
    const x=Math.max(0,Math.floor(l*w)-4), y=Math.max(0,Math.floor(t*h)-4);
    canvas.width=Math.min(w-x,Math.ceil(r*w)+4-x); canvas.height=Math.min(h-y,Math.ceil(b*h)+4-y);
    canvas.getContext('2d').drawImage(img,x,y,canvas.width,canvas.height,0,0,canvas.width,canvas.height);
    return canvas;
  }
  function link(row) {
    const anchor=document.createElement('a');
    anchor.href=row.doc.original || row.doc.pdf; anchor.target='_blank'; anchor.rel='noopener';
    anchor.setAttribute('aria-haspopup','dialog'); anchor.setAttribute('aria-controls','sample-review');
    anchor.addEventListener('click',event=>{
      if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const inspect=new CustomEvent('inspect-sample-line',{cancelable:true,detail:{
        doc:row.doc,ref:row.ref,opener:anchor,loadPage:()=>load(row.doc)}});
      if (!document.dispatchEvent(inspect)) event.preventDefault();
    });
    return anchor;
  }
  return {load,crop,link};
})();
