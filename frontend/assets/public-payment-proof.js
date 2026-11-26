const PublicPaymentProof = (() => {
  let pending=false;
  async function open() {
    const slot=document.getElementById('payment-execution');
    if (pending || slot.dataset.revision) return;
    pending=true;
    try {
      const reply=await fetch('/assets/payment-execution-notice.json');
      if (!reply.ok) return;
      const sample=await reply.json(), doc=sample.document;
      const rows=doc.lines.map(row=>({...row,id:row.ref,file:doc.title+'.pdf',url:doc.pdf,pageImage:doc.image,
        clear:true,explicit:row.kind==='limit',
        place:'第 '+doc.page+' 页 · 第 '+row.line+' 行',
        open:opener=>!document.dispatchEvent(new CustomEvent('inspect-sample-line',
          {cancelable:true,detail:{doc,ref:row.ref,opener}})),
        excerpt:row.crop?async()=>{const img=new Image();img.alt='';img.src=row.crop;await img.decode();return img;}:null}));
      const item={key:sample.finding,name:doc.title+'.pdf · '+sample.stage,state:sample.state,rows,...PaymentProofCard.pairs(rows,sample.state)};
      slot.replaceChildren(PaymentProofCard.render([item],'public-payment-proof'));slot.dataset.revision=sample.rev;
      if (!slot.hidden) document.getElementById('payment-version').textContent='合成案例 · R'+sample.rev;
    } catch { /* Keep the watermarked PDF link available when the interactive example cannot load. */ }
    finally {pending=false;}
  }
  return {open};
})();
