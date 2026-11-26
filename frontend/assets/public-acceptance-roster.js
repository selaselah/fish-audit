const PublicAcceptanceRoster = (() => {
  let loading=false;
  async function open() {
    const slot=document.getElementById('inspection-signers');
    if (loading || slot.querySelector('.acceptance-roster')) return;
    loading=true;
    try {
      const reply=await fetch('/assets/acceptance-roster.json');
      if (!reply.ok) return;
      const sample=await reply.json(), roster=sample.roster;
      async function loadImage(url) {
        const image=new Image(); image.alt=''; image.src=url; await image.decode(); return image;
      }
      function source(ref) {
        const doc=sample.documents.find(d=>d.lines.some(l=>l.ref===ref));
        const row=doc.lines.find(l=>l.ref===ref);
        return {...row,file:doc.title+'.pdf',page:doc.page,url:doc.pdf,
          excerpt:row.crop?()=>loadImage(row.crop):null,thumbnail:row.crop?()=>loadImage(doc.thumb):null,
          open:opener=>!document.dispatchEvent(new CustomEvent('inspect-sample-line',{cancelable:true,detail:{doc,ref,opener}}))};
      }
      const records=roster.records.map(r=>({...r,signed:r.signed.map(s=>({...s,source:source(s.ref)})),
        phases:r.phases.map(p=>({...p,source:source(p.ref)}))}));
      const card=AcceptanceRosterCard.render({...roster,contract:source(roster.contract),records},'sample-signers','sample-review','h3');
      slot.replaceChildren(card);
      slot.dataset.revision=sample.rev;
      if (!slot.hidden) document.getElementById('inspection-version').textContent='合成案例 · R'+sample.rev;
    } catch { /* Keep the link to the watermarked acceptance report. */ }
    finally { loading=false; }
  }
  return {open};
})();
