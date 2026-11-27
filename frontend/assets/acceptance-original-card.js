// A signed-off field transcription and the act of signing have separate sources.
const AcceptanceOriginalCard = (() => {
  const labels={acceptance_signer:'签认栏',measured_result:'实测',acceptance_result:'结论',defect_closure:'缺陷关闭'};
  function node(tag,cls,text) {
    const el=document.createElement(tag);if (cls) el.className=cls;if (text) el.textContent=text;return el;
  }
  function icon(name) {
    const el=node('i','ui-glyph ic-'+name);el.setAttribute('aria-hidden','true');return el;
  }
  function render(model,id) {
    const root=node('section','accept-original'), head=node('header'), file=node('a','accept-file',model.name);
    root.dataset.receiptOriginal=model.record;root.tabIndex=-1;root.setAttribute('aria-label',model.name+'签认凭证');
    file.prepend(icon('file-earmark-text'));file.href=model.original;file.download=model.name;
    head.append(file,node('span','accept-status','签认待核'));root.append(head);
    const body=node('div','accept-file-body'), sheet=node('div','accept-file-sheet'), inspector=node('div','accept-field-inspector');
    body.append(sheet,inspector);root.append(body);
    const tabs=node('div','accept-field-tabs'), panel=node('div','accept-field-panel');
    tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','核对验收原件');
    panel.id=id+'-field';panel.setAttribute('role','tabpanel');inspector.append(tabs,panel);
    let currentPage, browsing=false, generation=0;
    function showPage(number,browse=false) {
      if (currentPage===number && browsing===browse) return;
      currentPage=number;browsing=browse;
      const p=model.pages.find(row=>row.number===number),open=p.control();open.classList.add('accept-page');
      open.setAttribute('aria-label','查看'+model.name+'第 '+number+' 页整页');
      const thumb=node('span','accept-thumb');thumb.append(icon('file-earmark-text'));
      const label=node('span','accept-page-number','第 '+number+' 页');label.append(icon('arrows-angle-expand'));
      open.append(thumb,label);sheet.replaceChildren(open);
      p.thumbnail().then(canvas=>{if (canvas) {canvas.setAttribute('aria-hidden','true');thumb.replaceChildren(canvas);}}).catch(()=>{});
      if (browse && model.pages.length>1) {
        const select=node('select','accept-page-select');select.setAttribute('aria-label','选择验收单物理页');
        for (const pg of model.pages) select.add(new Option('第 '+pg.number+' 页',pg.number));
        select.value=String(number);select.addEventListener('change',()=>{showPage(Number(select.value),true);sheet.querySelector('select').focus();});sheet.append(select);
      }
    }
    const views=Object.keys(labels).filter(field=>model.lines.some(line=>line.field===field));
    if (model.notes.length) views.push('notes');
    if (views.length && model.pages.length>1) views.push('pages');
    function show(key) {
      const turn=++generation, buttons=[...tabs.children];
      for (const b of buttons) {
        const active=b.dataset.field===key;b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;
        if (active) panel.setAttribute('aria-labelledby',b.id);
      }
      panel.replaceChildren();panel.dataset.view=key;
      if (key==='pages') {
        showPage(currentPage || model.pages[0].number,true);
        panel.append(node('span','accept-locator',model.pages.length+' 页验收原件'));return;
      }
      const options=key==='notes'?model.notes:model.lines.filter(r=>r.field===key);
      const content=node('div','accept-source');
      function draw(entry) {
        if (key==='notes') {
          showPage(entry.location?.page || model.pages[0].number);
          content.replaceChildren(WordCommentCard.compare({name:model.name,original:model.original},entry));return;
        }
        showPage(entry.page);
        const open=entry.control();open.classList.add('accept-source-line');open.dataset.fact=entry.ref;
        const caption=node('span','accept-locator','第 '+entry.page+' 页 · 第 '+entry.line+' 行');caption.append(icon('arrows-angle-expand'));
        const quote=node('span','accept-source-quote',entry.quote), crop=node('span','accept-source-crop');
        open.setAttribute('aria-label',entry.quote+'，'+caption.textContent+'，查看原页');open.append(quote,crop,caption);content.replaceChildren(open);
        entry.excerpt().then(canvas=>{
          if (turn!==generation || content.firstChild!==open || !canvas) return;
          canvas.setAttribute('aria-hidden','true');crop.replaceChildren(canvas);quote.hidden=true;
        }).catch(()=>{});
      }
      if (options.length>1) {
        const choose=node('select','accept-field-select');
        choose.setAttribute('aria-label',key==='notes'?'选择验收批注':'选择'+labels[key]+'原行');
        for (const [i,row] of options.entries()) choose.add(new Option(key==='notes'?'批注 '+(i+1)+(row.author?' · '+row.author:''):'第 '+row.page+' 页 · 第 '+row.line+' 行',i));
        choose.addEventListener('change',()=>draw(options[choose.selectedIndex]));panel.append(choose);
      }
      panel.append(content);draw(options[0]);
    }
    for (const [i,field] of views.entries()) {
      const tab=node('button','',field==='notes'?'原批注':field==='pages'?'整页':labels[field]);
      tab.type='button';tab.id=id+'-'+field; tab.dataset.field=field;
      tab.setAttribute('role','tab');tab.setAttribute('aria-controls',panel.id);tab.addEventListener('click',()=>show(field));
      tab.addEventListener('keydown',e=>{
        const to={ArrowLeft:(i+views.length-1)%views.length,ArrowRight:(i+1)%views.length,Home:0,End:views.length-1}[e.key];
        if (to!==undefined) {e.preventDefault();tabs.children[to].focus();show(views[to]);}
      });tabs.append(tab);
    }
    if (views.length) show(views.includes(model.initial)?model.initial:views[0]);
    else {
      showPage(model.pages[0].number,true);
      inspector.replaceChildren(node('strong','',model.label),node('p','','打开整页核对签认人和签认范围。'));
    }
    if (views.length && (model.unplaced || model.partial)) {
      inspector.append(node('small','accept-review-limit',model.unplaced?model.unplaced+' 条批注的页面归属待核。':'Word 审阅记录的覆盖范围待核。'));
    }
    const footer=node('footer'), verify=node('details','accept-file-verify');
    verify.append(node('summary','','核验原件'),originalFileCheck(model.original,model.hash),node('code','',model.hash));
    footer.append(verify);if (model.permalink) footer.append(model.permalink());root.append(footer);
    return root;
  }
  return {render};
})();
