const PublicAcceptanceComments = (() => {
  let pending=false;
  async function open() {
    const slot=document.getElementById('inspection-comments');
    if (pending || slot.querySelector('.word-review-card')) return;
    pending=true;
    try {
      const response=await fetch('/assets/acceptance-comment-sample.json');
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
      slot.replaceChildren(WordCommentCard.render({id:'public-acceptance-comments',status:sample.status,documents:[{...doc,notes}]}));
    } catch {
      const anchor=slot.querySelector('a');
      if (anchor) anchor.textContent='查看水印 Word 原件';
    } finally {pending=false;}
  }
  return {open};
})();
