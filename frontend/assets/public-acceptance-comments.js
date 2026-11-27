const PublicAcceptanceComments = (() => {
  const pending=new Set();
  async function open(role='acceptance',target) {
    const contract=role==='contract', slot=target || document.getElementById(contract?'payment-comments':'inspection-comments');
    if (!contract && !target) return PublicAcceptanceOriginals.open(slot,legacy=>open(role,legacy));
    if (pending.has(role) || slot.dataset.revision) return;
    pending.add(role);
    try {
      const response=await fetch('/assets/'+role+'-comment-sample.json');
      if (!response.ok) throw new Error('演练案例暂时无法载入');
      const sample=await response.json(), doc=sample.document, source=sample.sources[doc.doc];
      if (doc.original_sha256!==source.source_sha256) throw new Error('原件未对应');
      function inspect(src,ref) {
        return opener=>document.dispatchEvent(new CustomEvent('inspect-sample-line',{cancelable:true,detail:{doc:src,ref,opener}}));
      }
      const statusNames={ok:'相符',risk:'风险',missing:'证据不足',issue:'问题'};
      const notes=doc.notes.map(note=>{
        const line=source.lines.find(l=>l.ref===note.ref);
        if (!line || line.line!==note.location.line || source.page_sha256!==note.location.page_sha256) throw new Error('原行未对应');
        return {...note,rects:line.rects,open:inspect(source,note.ref),thumbnail:source.image,
          related:note.related.map(f=>({...f,statusName:statusNames[f.status],open:inspect(sample.sources[f.doc],f.ref)}))};
      });
      const stages=contract && sample.stages.map(s=>{
        const line=source.lines.find(l=>l.ref===s.ref);
        if (!line || line.line!==s.line || s.quote!==line.label+'：'+line.value) throw new Error('期款原行未对应');
        return {...s,open:inspect(source,s.ref)};
      });
      slot.replaceChildren(WordCommentCard.panel({id:'public-'+role+'-comments',role,stages,status:sample.status,documents:[{...doc,notes}]}));
      slot.dataset.revision=String(sample.revision);
      if (contract && !slot.hidden) document.getElementById('payment-version').textContent='合成案例 · R'+sample.revision;
    } catch {
      const anchor=slot.querySelector('a');
      if (anchor) anchor.textContent='查看水印 Word 原件';
    } finally {pending.delete(role);}
  }
  return {open};
})();
