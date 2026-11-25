const EntityBrowser = (() => {
  const types = {
    contract_number:['单号','合同编号',['contract_id','base_contract_ref']],
    invoice_number:['单号','发票号码',['invoice_id','claim_ref']],
    transfer_ref:['单号','银行流水号',['transfer_ref']],
    acceptance_reference:['单号','验收单号',['acceptance_number','original_acceptance']],
    repair_number:['单号','整改记录号',['repair_number']],
    defect_number:['单号','缺陷编号',['defect_number']],
    addendum_number:['单号','补充协议号',['addendum_number']],
    party:['往来单位','单位名称',['buyer','seller','payer','payee']],
    subject:['标的','标的名称',['subject']],
  };
  const same=(a,b)=>typeof a==='string' && typeof b==='string' && a.normalize('NFKC').trim()===b.normalize('NFKC').trim();
  function fullNumber(f) {
    const raw=(f.source_line?.text || f.quote).normalize('NFKC').trim(), value=f.value.normalize('NFKC').trim();
    const colon=raw.indexOf(':'), body=colon<0?raw:raw.slice(colon+1).trim();
    return body===value && !/[\s*•●■□×…]|\.{2,}|尾号|后[零一二三四五六七八九十0-9]+位/.test(value) &&
      !/(?:尾号|仅显示|仅保留|遮挡|掩码)/.test(raw) && !/^[0-9Xx]*[Xx]{2,}[0-9Xx]*$/.test(value);
  }

  function items(graph) {
    const index=graphIndex(graph);
    if (index.entityItems) return index.entityItems;
    const objects=new Map(), records=new Map(), pages=new Map();
    for (const e of graph.edges) {
      if (e.evidence?.length!==1) continue;
      if (e.type==='records' && e.evidence[0]===e.to) records.set(e.to,e.from);
      if (['contains','section_page'].includes(e.type) && e.evidence[0]===e.to) {
        if (!pages.has(e.from)) pages.set(e.from,new Set());
        pages.get(e.from).add(e.to);
      }
    }
    for (const e of graph.edges) {
      const entity=index.nodes.get(e.to), rule=entity && types[entity.type];
      if (!rule || !rule[2].includes(e.type) || e.evidence?.length!==1) continue;
      const f=index.facts.get(e.evidence[0]), doc=index.nodes.get(e.from);
      if (!f || f.field!==e.type || !['anchored','confirmed'].includes(f.status) ||
          !['document','document_section'].includes(doc?.type) || (f.unit || f.doc)!==doc.id ||
          !same(f.value,entity.label) || index.nodes.get(f.id)?.type!=='observation' || index.nodes.get(f.id).status!==f.status ||
          (rule[0]==='单号' && !fullNumber(f))) continue;
      const ref=f.doc+'/p'+f.page, page=index.nodes.get(ref);
      if (page?.type!=='page' || !page.sha256 || page.sha256!==f.page_sha256 ||
          index.documents.get(f.doc)?.sha256!==f.source_sha256 || index.nodes.get(f.doc)?.sha256!==f.source_sha256 || !f.source_sha256 ||
          !pages.get(doc.id)?.has(ref) || records.get(f.id)!==ref ||
          (doc.source || doc.id)!==f.doc || (doc.source && doc.page!==f.page)) continue;
      if (!objects.has(entity.id)) objects.set(entity.id,{node:entity,category:rule[0],label:rule[1],docs:new Map()});
      const docs=objects.get(entity.id).docs;
      if (!docs.has(doc.id)) docs.set(doc.id,{node:doc,facts:[]});
      const facts=docs.get(doc.id).facts;
      if (!facts.some(existing=>existing.id===f.id)) facts.push(f);
    }
    index.entityItems=[...objects.values()].sort((a,b)=>b.docs.size-a.docs.size || a.node.label.localeCompare(b.node.label,'zh-CN'));
    return index.entityItems;
  }

  function panel(graph) {
    const data=items(graph);
    const panel=el('section','','entity-browser'), title=el('h2','按对象查原件');
    panel.id='case-entity-browser'; panel.tabIndex=-1; title.id='entity-browser-title';
    panel.setAttribute('aria-labelledby',title.id);
    if (!data.length) {
      panel.dataset.empty='true';
      panel.append(title,el('p','本版缺少可逐项关联的完整单号、往来单位或标的。','muted'),
        action('查看原件与引文',()=>document.querySelector('#tabs [data-tab=evidence]')?.click(),'ref'));
      return panel;
    }
    const segments=box('entity-segments'), objects=el('select'), documents=el('select'), excerpt=box('entity-excerpt');
    segments.setAttribute('role','group'); segments.setAttribute('aria-label','业务对象类型');
    objects.id='entity-object'; documents.id='entity-document';
    const picker=(id,caption,select)=>{
      const label=el('label',caption); label.htmlFor=id;
      return box('entity-picker',label,select);
    };
    const connector=el('span','→','entity-connector'); connector.setAttribute('aria-hidden','true');
    const count=el('span','','entity-count');
    const place=el('small'), quote=el('blockquote'), crop=box('entity-crop');
    crop.id='entity-page-crop'; crop.hidden=true; crop.setAttribute('aria-live','polite');
    let drawRequest=0;
    const links=el('select'); links.setAttribute('aria-label','所选单据的相关引文');
    const original=action('打开原页',()=>{
      const f=selectedFact();
      if (f) openPage(f.doc,f.page,f.id);
    },'entity-open');
    original.prepend(glyph('file-earmark-text'));
    const index=graphIndex(graph);
    const selection=index.entitySelection || {preview:true};
    index.entitySelection=selection;
    const selectedItem=()=>data.find(item=>item.node.id===objects.value);
    const selectedFacts=()=>selectedItem()?.docs.get(documents.value)?.facts || [];
    const selectedFact=()=>selectedFacts().find(f=>f.id===links.value);
    const preview=action('对照原行',()=>{selection.preview=!selection.preview; renderQuote();},'entity-preview');
    preview.setAttribute('aria-controls',crop.id);
    const previous=action('',()=>stepDocument(-1),'entity-step entity-back'), next=action('',()=>stepDocument(1),'entity-step');
    for (const [button,title] of [[previous,'上一份关联单据'],[next,'下一份关联单据']]) {
      button.setAttribute('aria-label',title); button.title=title; button.append(glyph('chevron-down'));
    }
    function stepDocument(offset) {
      const position=documents.selectedIndex+offset;
      if (position<0 || position>=documents.options.length) return;
      documents.selectedIndex=position; renderDocument();
      if (document.activeElement?.disabled) documents.focus();
    }
    function renderQuote() {
      const f=selectedFact();
      if (!f) return;
      selection.fact=f.id;
      const loc=f.source_line, physical=loc?.number && loc.rects?.length;
      place.textContent=f.label+' · 第 '+f.page+' 页'+(physical?' '+loc.number+' 行':' · 影像引文');
      quote.textContent=physical?loc.text:f.quote;
      original.dataset.entityFact=f.id;
      const request=++drawRequest, show=Boolean(physical && selection.preview);
      preview.hidden=!physical; preview.setAttribute('aria-pressed',String(show));
      crop.hidden=!show; crop.replaceChildren(); delete crop.dataset.fact;
      if (!show) return;
      crop.textContent='正在读取原页…';
      EvidenceCompare.lineExcerpt(f,index).then(canvas=>{
        if (request!==drawRequest) return;
        if (!canvas) { crop.textContent='原页位置待核'; return; }
        crop.dataset.fact=f.id; crop.replaceChildren(canvas);
      }).catch(()=>{
        if (request===drawRequest) crop.replaceChildren(el('span','页图加载失败'),action('重新载入',renderQuote,'ref'));
      });
    }
    function renderDocument() {
      selection.unit=documents.value;
      const facts=selectedFacts();
      links.replaceChildren(...facts.map(f=>new Option(f.label+' · 第 '+f.page+' 页'+(f.source_line?.number?' '+f.source_line.number+' 行':''),f.id)));
      if (facts.some(f=>f.id===selection.fact)) links.value=selection.fact;
      links.hidden=facts.length<=1; renderQuote();
      count.textContent=(documents.selectedIndex+1)+' / '+documents.length+' 份';
      previous.disabled=documents.selectedIndex===0; next.disabled=documents.selectedIndex===documents.length-1;
      previous.hidden=next.hidden=documents.length===1;
      documents.parentElement.classList.toggle('one-document',documents.length===1);
    }
    function renderObject() {
      const item=selectedItem(); selection.target=item.node.id;
      documents.replaceChildren(...[...item.docs.values()].map(d=>new Option(d.node.label,d.node.id)));
      if (item.docs.has(selection.unit)) documents.value=selection.unit;
      renderDocument();
    }
    function category(name) {
      selection.category=name;
      for (const button of segments.children) {
        const selected=button.textContent===name;
        button.setAttribute('aria-pressed',String(selected)); button.tabIndex=selected?0:-1;
      }
      const matching=data.filter(item=>item.category===name);
      objects.replaceChildren(...matching.map(item=>new Option(item.label+' · '+item.node.label,item.node.id)));
      if (matching.some(item=>item.node.id===selection.target)) objects.value=selection.target;
      renderObject();
    }
    const categories=['单号','往来单位','标的'].filter(name=>data.some(item=>item.category===name));
    for (const [i,name] of categories.entries()) {
      const button=action(name,()=>category(name));
      button.addEventListener('keydown',event=>{
        const n=categories.length, j={ArrowRight:(i+1)%n,ArrowLeft:(i+n-1)%n,Home:0,End:n-1}[event.key];
        if (j===undefined) return;
        event.preventDefault(); category(categories[j]); segments.children[j].focus();
      });
      segments.append(button);
    }
    objects.addEventListener('change',renderObject); documents.addEventListener('change',renderDocument);
    links.addEventListener('change',renderQuote);
    const target=picker(objects.id,'业务对象',objects), source=picker(documents.id,'关联单据',documents);
    source.firstChild.append(count);
    source.append(box('entity-pager',previous,documents,next));
    const documentLabel=el('div','','entity-location'); documentLabel.append(place,links);
    excerpt.append(box('entity-proof',documentLabel,quote),box('entity-actions',preview,original),crop);
    panel.append(box('entity-head',title,segments),box('entity-path',target,connector,source),excerpt);
    category(categories.includes(selection.category)?selection.category:categories[0]);
    return panel;
  }
  function views(report,buildRelations) {
    const graph=report.graph, index=graphIndex(graph);
    const nav=box('graph-directions'), content=box('graph-direction-content');
    const more=lazyFold('查看关系明细',()=>[buildRelations(report)]);
    nav.setAttribute('role','group'); nav.setAttribute('aria-label','知识图谱查看方式');
    content.id='graph-direction-content'; more.className='graph-relations';
    const forms=new Map(), programs=new Set(graph.edges.filter(e=>e.type==='procedure_result').map(e=>e.to));
    if (report.findings.some(f=>programs.has('finding/'+f.id))) forms.set('findings',['按审计发现',()=>provenancePanel(report)]);
    forms.set('entities',['按业务对象',()=>panel(graph)]);
    const built=new Map();
    function show(mode) {
      index.graphBrowseMode=mode;
      for (const b of nav.children) b.setAttribute('aria-pressed',String(b.dataset.direction===mode));
      if (!built.has(mode)) built.set(mode,forms.get(mode)[1]());
      content.replaceChildren(built.get(mode)); more.open=mode==='findings';
    }
    for (const [mode,[caption]] of forms) {
      const choice=action(caption,()=>show(mode));
      choice.dataset.direction=mode; choice.setAttribute('aria-controls',content.id); nav.append(choice);
    }
    nav.hidden=forms.size<2;
    show(forms.has(index.graphBrowseMode)?index.graphBrowseMode:forms.keys().next().value);
    return box('graph-stack',nav,content,more);
  }
  return {items,panel,views};
})();
