const PublicSignerTiming = (() => {
  let loading = false;
  async function open() {
    const slot = document.getElementById('payment-signer-timing');
    if (loading || slot.querySelector('.signer-timeline')) return;
    loading = true;
    try {
      const response = await fetch('/assets/joint-signing.json');
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
      const item = {...payment,clause:source(payment.clause),term:source(payment.term),
        events:payment.events.map(e=>({...e,source:source(e.ref)}))};
      if (!item.clause || !item.term || !item.events.every(e=>e.source)) return;
      slot.replaceChildren(SignerTimeline.render([item],'public-signer-timing'));
      slot.dataset.revision = sample.rev;
      if (!slot.hidden) document.getElementById('payment-version').textContent = '合成案例 · R'+sample.rev;
    } catch { /* The original watermarked transfer remains available in the HTML. */ }
    finally { loading = false; }
  }
  return {open};
})();
