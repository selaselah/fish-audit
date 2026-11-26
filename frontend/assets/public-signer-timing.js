const PublicSignerTiming = (() => {
  const loading = new Set();
  async function open(clock=false) {
    const name=clock?'signer-clock':'signer-timing';
    const slot = document.getElementById('payment-'+name);
    if (loading.has(slot) || slot.querySelector('.signer-timeline')) return;
    loading.add(slot);
    try {
      const response = await fetch(clock?'/assets/signer-clock.json':'/assets/joint-signing.json');
      if (!response.ok) return;
      const sample = await response.json(), payment = sample.payment;
      function source(ref) {
        const doc = sample.documents.find(d=>d.lines.some(l=>l.ref===ref));
        const row = doc?.lines.find(l=>l.ref===ref);
        if (!row) return null;
        return {file:doc.title+'.pdf',place:'第 '+doc.page+' 页 · 第 '+row.line+' 行',quote:row.quote,url:doc.pdf,
          pageImage:doc.image,rects:row.rects,
          excerpt:row.crop?async()=>{const image=new Image();image.alt='';image.src=row.crop;await image.decode();return image;}:null,
          open:opener=>!document.dispatchEvent(new CustomEvent('inspect-sample-line',{cancelable:true,detail:{doc,ref,opener}}))};
      }
      const events=payment.events.map(e=>({...e,source:source(e.ref),daySource:source(e.dayRef),signature:source(e.signature)}));
      const pair=clock && payment.pair?.map(ref=>events.find(e=>e.ref===ref));
      const item = {...payment,clause:source(payment.clause),term:source(payment.term),events,
        pair:pair?.length===2 && pair.every(e=>e?.source)?pair:null};
      if (!item.clause || !item.term || !item.events.every(e=>e.source)) return;
      slot.replaceChildren(SignerTimeline.render([item],'public-'+name));
      slot.dataset.revision = sample.rev;
      if (!slot.hidden) document.getElementById('payment-version').textContent = '合成案例 · R'+sample.rev;
    } catch { /* The original watermarked transfer remains available in the HTML. */ }
    finally { loading.delete(slot); }
  }
  return {open};
})();
