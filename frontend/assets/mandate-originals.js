const MandateOriginals = (() => {
  const format='mandate-original-execution-v1';
  const images=new Set(['.png','.jpg','.jpeg','.webp','.tif','.tiff','.heic','.heif']);
  const labels={
    word_text:'Word 打印页仅见排印文字，签发待核',
    word_visual:'Word 打印页需核图，签章痕迹待核',
    word_review:'Word 审阅记录及签发依据待核',
    photo:'照片原件，授权方签章待核',
    review:'委托书原件的签发依据待核'
  };
  const families={
    board:{kinds:['contract_approval'],labels:{
      word_text:'Word 排印件',word_visual:'Word 含图形',word_review:'Word 审阅版',photo:'扫描或拍照原件',review:'决议签署凭证待核'
    }},
    warranty:{kinds:['warranty'],labels:{
      word_text:'Word 排印件',word_visual:'Word 含图形',word_review:'Word 审阅版',photo:'扫描或拍照原件',review:'期满单签署凭证待核'
    }},
    release:{kinds:['payment_release'],labels:{
      word_text:'Word 排印件',word_visual:'Word 含图形',word_review:'Word 审阅版',photo:'扫描或拍照原件',review:'签署凭证待核'
    }},
    mandate:{kinds:['power_of_attorney'],labels},
    addendum:{kinds:['contract_addendum'],labels:{
      word_text:'Word 排印原件',word_visual:'Word 签章页待核图',word_review:'Word 定稿待核',
      photo:'补充协议影像',review:'原件签署依据待核'
    }},
    acceptance:{kinds:['acceptance','reinspection'],labels:{
      word_text:'Word 排印件',word_visual:'Word 含图形',word_review:'Word 审阅版',
      photo:'扫描或拍照原件',review:'签认原件待核'
    }}
  };
  const digest=value=>typeof value==='string' && /^[a-f0-9]{64}$/.test(value);
  const same=(a,b)=>Array.isArray(a) && a.length===b.length && a.every((v,i)=>v===b[i]);
  function edge(graph,from,to,type,evidence) {
    const edges=graph.edges.filter(e=>e.type===type && e.to===to);
    return edges.length===1 && edges[0].from===from && same(edges[0].evidence,evidence);
  }
  function wordReview(graph,source,rows,role) {
    const {record,doc}=source, index=graphIndex(graph), ledger=role==='acceptance'?graph.acceptance_word_reviews:graph[role+'_original_sources'];
    const relation=role==='acceptance'?'word_review':role+'_word_review';
    const documents=ledger.documents.filter(d=>d?.doc===doc.id || d?.id===record.review), [word]=documents;
    const units=(graph.audit_documents || graph.documents).filter(u=>(u.source || u.id)===doc.id);
    const assigned=units.filter(u=>families[role].kinds.some(k=>graph.documents_by_kind[k]?.includes(u.id)) ||
      role==='release' && ReleaseEvidence.filedUnit(graph,u.id));
    if (documents.length!==1 || word.id!==record.review || word.id!==role+'-word/'+doc.id || word.doc!==doc.id ||
        word.original_sha256!==doc.sha256 || !same(word.units,assigned.map(u=>u.id)) ||
        index.nodes.get(word.id)?.type!==role+'_word_review' || index.nodes.get(word.id).doc!==doc.id ||
        !edge(graph,doc.id,word.id,relation+'_source',[doc.id]) ||
        !edge(graph,word.id,record.id,role+'_original_word',[doc.id,word.id])) return null;
    if (!['complete','partial','unreadable'].includes(word.coverage) || !Array.isArray(word.limitations) ||
        !Array.isArray(word.notes) || (word.coverage==='complete')!==!word.limitations.length ||
        (word.coverage==='unreadable' ? word.count!==null || word.notes.length :
          !digest(word.body_sha256) || !Number.isSafeInteger(word.count) || word.count<word.notes.length ||
          word.coverage==='complete' && word.count!==word.notes.length) ||
        word.notes.length && (!digest(word.part_sha256) || typeof word.part!=='string' || !word.part)) return null;
    const notes=[], refs=[word.id];
    let unplaced=0;
    for (const [i,n] of word.notes.entries()) {
      if (n?.id!==word.id+'/n'+(i+1) || index.nodes.get(n.id)?.type!==role+'_word_comment' ||
          index.nodes.get(n.id).doc!==doc.id || !edge(graph,word.id,n.id,relation+'_comment',[doc.id,word.id]) ||
          typeof n.text!=='string' || typeof n.author!=='string' || typeof n.shortened!=='boolean' ||
          !AcceptanceComments.validAnchor(n.anchor)) return null;
      const loc=n.location;
      let fact;
      if (loc===null) {
        if (graph.edges.some(e=>e.to===n.id && e.type===relation+'_anchor')) return null;
        if (record.unit!==doc.id) { unplaced++; continue; }
      } else {
        if (!loc || !n.anchor || !Number.isSafeInteger(loc.page) || loc.page<1 || loc.page>doc.pages ||
            !Number.isSafeInteger(loc.line) || loc.line<1 || !Array.isArray(loc.facts) ||
            new Set(loc.facts).size!==loc.facts.length) return null;
        const pageId=doc.id+'/p'+loc.page, page=index.nodes.get(pageId);
        const split=units.filter(u=>u.source && u.page===loc.page);
        if (split.length>1 || loc.unit!==(split[0]?.id || doc.id) || page?.type!=='page' || page.layer!=='text' ||
            !digest(loc.page_sha256) || page.sha256!==loc.page_sha256 || !digest(loc.text_sha256) ||
            page.text_sha256!==loc.text_sha256 || !edge(graph,pageId,n.id,relation+'_anchor',[pageId,...loc.facts])) return null;
        if (loc.unit!==record.unit) continue;
        const printed=loc.printed ?? n.anchor.quote;
        if (!record.pages.some(p=>p.ref===pageId) || typeof printed!=='string' || role==='acceptance' && printed!==n.anchor.quote ||
            AcceptanceComments.printedKey(printed)!==AcceptanceComments.printedKey(n.anchor.quote) ||
            !loc.facts.every(id=>{
              const row=rows.get(id), f=row?.fact;
              return row?.line===loc.line && f.doc===doc.id && (f.unit || f.doc)===loc.unit &&
                f.page===loc.page && f.source_line.text===printed && AcceptanceComments.printedKey(f.quote)===AcceptanceComments.printedKey(printed);
            })) return null;
        fact=loc.facts[0];
        refs.push(pageId,...loc.facts);
      }
      const evidence=[doc.id,word.id];
      if (loc) evidence.push(doc.id+'/p'+loc.page,...loc.facts);
      if (!edge(graph,record.id,n.id,role+'_original_comment',evidence)) return null;
      refs.push(n.id);
      notes.push({...n,open:fact?()=>openPage(doc.id,loc.page,fact):null,openPage:loc && !fact?()=>openPage(doc.id,loc.page):null});
    }
    const owned=graph.edges.filter(e=>e.from===record.id && e.type===role+'_original_comment');
    if (!same(record.notes,notes.map(n=>n.id)) || record.unplaced!==unplaced ||
        owned.length!==notes.length || !owned.every(e=>record.notes.includes(e.to))) return null;
    return {word:{id:word.id,coverage:word.coverage,limitations:word.limitations,part:word.part,part_sha256:word.part_sha256},notes,refs};
  }
  function bind(graph,source,rows,role='mandate') {
    const ledger=role==='acceptance'?graph.acceptance_word_reviews:graph[role+'_original_sources'];
    if (!source || !Array.isArray(ledger?.documents)) return null;
    const {record,doc}=source, index=graphIndex(graph);
    if (!Object.hasOwn(families[role].labels,record.state) || !Array.isArray(record.notes) ||
        !Number.isSafeInteger(record.unplaced) || record.unplaced<0 || record.pages.some(p=>{
          const page=index.nodes.get(p.ref);
          return p.layer!==page.layer || p.text_only!==(page.clause_text_only===true) ||
            p.text_only && p.layer!=='text' || !digest(page.text_sha256);
        })) return null;
    if (record.unit!==doc.id) {
      const section=index.nodes.get(record.unit), ref=record.pages[0].ref;
      if (section?.type!=='document_section' || section.source!==doc.id || ref!==doc.id+'/p'+section.page ||
          !edge(graph,doc.id,record.unit,'contains_section',[ref]) || !edge(graph,record.unit,ref,'section_page',[ref])) return null;
    }
    const proof={...source,label:families[role].labels[record.state]};
    if (record.kind==='image') {
      if (!images.has(doc.ext) || !['photo','review'].includes(record.state) || record.review!==null || record.notes.length || record.unplaced ||
          ledger.documents.some(d=>d?.doc===doc.id) ||
          graph.edges.some(e=>e.to===record.id && e.type===role+'_original_word' ||
            e.from===record.id && e.type===role+'_original_comment') ||
          record.state==='photo' && !record.pages.every(p=>p.layer==='image' && !p.text_only)) return null;
      return proof;
    }
    if (record.kind!=='word' || !['.doc','.docx'].includes(doc.ext) || record.state==='photo') return null;
    const review=wordReview(graph,source,rows,role);
    if (!review) return null;
    const pending=Boolean(review.notes.length || record.unplaced || review.word.coverage!=='complete');
    if (record.state!=='review' && (record.state==='word_review')!==pending) return null;
    const textOnly=record.pages.every(p=>p.text_only);
    const emptyText='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';
    if (record.state==='word_text' && (!textOnly || record.pages.every(p=>index.nodes.get(p.ref).text_sha256===emptyText))) return null;
    if (record.state==='word_visual' && !record.pages.some(p=>p.layer==='image_overlay' || p.layer==='text' && !p.text_only)) return null;
    return {...proof,word:review.word,notes:review.notes,refs:[...new Set([...proof.refs,...review.refs])]};
  }
  function wordFile(proof) {
    const a=link('下载 Word 原件',workpaperSource(proof.doc.id,'original'),'scope-mandate-file');
    a.download=proof.doc.name;
    return a;
  }
  function wordTools(proof) {
    const {word,doc,notes,record}=proof;
    const tools=box('scope-mandate-word-tools');
    if (notes.length || record.unplaced || word.coverage!=='complete') {
      const details=fold(notes.length?'查看原批注 · '+notes.length:'查看审阅范围');
      details.dataset.mandateReview=record.id;
      if (notes.length) {
        const body=box('scope-mandate-comment'), choose=el('select');
        choose.setAttribute('aria-label','选择本单元的 Word 批注');
        for (const [i,n] of notes.entries()) choose.add(new Option('批注 '+(i+1)+(n.author?' · '+n.author:''),n.id));
        function show(id) {
          const note=notes.find(n=>n.id===id);
          if (!note) return;
          choose.value=note.id; body.dataset.mandateNote=note.id;
          body.replaceChildren(WordCommentCard.compare(doc,note));
          if (note.anchor) body.querySelector('.word-caption').append(el('span','，选中“'+note.anchor.selected+'”','visually-hidden'));
          body.querySelector('.word-credit').append(el('small','采纳待核'));
        }
        if (notes.length>1) details.append(choose);
        choose.addEventListener('change',()=>show(choose.value));
        details.addEventListener('select-mandate-note',event=>show(event.detail));
        show(notes[0].id); details.append(body);
      }
      if (record.unplaced) details.append(el('p',record.unplaced+' 条批注的单元归属待核。','scope-mandate-advice'));
      if (word.coverage!=='complete') details.append(el('p','审阅范围待核，请对照 Word 原件。','scope-mandate-advice'));
      tools.append(details);
    }
    tools.append(wordFile(proof));
    return tools;
  }
  return {format,images,bind,wordFile,wordTools};
})();
