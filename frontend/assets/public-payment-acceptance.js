// Each public source is a fixed excerpt from the watermarked sample shipped with the site.
const PublicPaymentAcceptance = (() => {
  let loading=false;
  async function open() {
    const slot=document.getElementById('payment-reference');
    if (loading || slot.querySelector('.payment-reference-card')) return;
    loading=true;
    try {
      const response=await fetch('/assets/batch-payment-reference.json');
      if (!response.ok) return;
      const sample=await response.json();
      function source(ref) {
        if (!ref) return null;
        const doc=sample.documents.find(d=>d.lines.some(l=>l.ref===ref)),row=doc?.lines.find(r=>r.ref===ref);
        if (!row) return null;
        return {value:row.value,label:row.label,url:doc.pdf,location:'第 '+doc.page+' 页 · 第 '+row.line+' 行',
          open:opener=>!document.dispatchEvent(new CustomEvent('inspect-sample-line',{cancelable:true,detail:{doc,ref,opener}})),
          excerpt:row.crop?async()=>{const image=new Image();image.alt='';image.src=row.crop;await image.decode();return image;}:null};
      }
      const items=sample.payments.map(item=>({...item,bank:source(item.bank),expected:source(item.expected),actual:source(item.actual),
        basis:item.basis.map(ref=>source(ref)).filter(Boolean)}));
      slot.replaceChildren(PaymentReferenceCard.render(items,'public-payment-acceptance','source'));
      slot.dataset.revision=sample.rev;
      if (!slot.hidden) document.getElementById('payment-version').textContent='合成案例 · R'+sample.rev;
    } catch { /* The watermarked PDF link remains available during a network failure. */ }
    finally {loading=false;}
  }
  return {open};
})();
