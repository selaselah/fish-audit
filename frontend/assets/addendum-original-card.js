const AddendumOriginalCard = (() => {
  function element(tag,text,cls) {
    const node=document.createElement(tag);
    if (text) node.textContent=text;
    if (cls) node.className=cls;
    return node;
  }
  function inspector(id,views,first) {
    const root=element('div','','agreement-inspector'), tabs=element('div','','agreement-inspector-tabs');
    tabs.setAttribute('role','tablist'); tabs.setAttribute('aria-label','协议核对项目');
    root.append(tabs);
    function select(key) {
      for (const [i,view] of views.entries()) {
        const active=key===view.key, tab=tabs.children[i];
        tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1; view.panel.hidden=!active;
      }
    }
    for (const [i,view] of views.entries()) {
      const tab=element('button',view.name);
      if (view.count) tab.append(element('span',String(view.count),'agreement-tab-count'));
      tab.type='button';tab.id=id+'-tab-'+view.key;tab.dataset.agreementView=view.key;
      view.panel.id=id+'-view-'+view.key;view.panel.tabIndex=0;view.panel.setAttribute('role','tabpanel');
      view.panel.setAttribute('aria-labelledby',tab.id);tab.setAttribute('role','tab');tab.setAttribute('aria-controls',view.panel.id);
      tab.addEventListener('click',()=>select(view.key));
      tab.addEventListener('keydown',event=>{
        const to={ArrowLeft:(i+views.length-1)%views.length,ArrowRight:(i+1)%views.length,Home:0,End:views.length-1}[event.key];
        if (to!==undefined) {event.preventDefault();select(views[to].key);tabs.children[to].focus();}
      });
      tabs.append(tab);root.append(view.panel);
    }
    select(views.some(v=>v.key===first)?first:views[0].key);
    return root;
  }
  function render(model,terms,id) {
    const {record,filename,original,pages,rows,notes}=model;
    const root=element('section','','agreement-original');
    root.dataset.state=record.state;
    root.setAttribute('aria-label','补充协议原件签署凭证');
    const sheet=element('div','','agreement-original-sheet'), info=element('div','','agreement-original-info');
    const pageBox=element('div','','agreement-proof-strip');
    const title=element('header'), filenameLink=element('a',filename,'agreement-file-link');
    const fileIcon=element('i','','ui-glyph ic-'+(record.kind==='word'?'file-earmark-text':'eye'));
    fileIcon.setAttribute('aria-hidden','true'); filenameLink.prepend(fileIcon);
    filenameLink.href=original; filenameLink.download=filename; filenameLink.title='下载'+filename;
    title.append(filenameLink,element('span','需人工校验','agreement-review-status'));root.append(title);
    function show(page) {
      const control=page.control();control.classList.add('agreement-sheet-open');
      control.setAttribute('aria-label','第 '+page.number+' 页，查看'+filename);
      const thumbnail=element('span','','agreement-thumbnail'), icon=element('i','','ui-glyph ic-arrows-angle-expand');
      icon.setAttribute('aria-hidden','true');
      thumbnail.append(element('i','','ui-glyph ic-file-earmark-text'));
      if (page.load) page.load().then(img=>{
        const preview=element('canvas');preview.width=180;preview.height=Math.round(180*img.naturalHeight/img.naturalWidth);
        preview.getContext('2d').drawImage(img,0,0,preview.width,preview.height);
        preview.setAttribute('aria-hidden','true');thumbnail.replaceChildren(preview);
      }).catch(()=>{});
      else {
        const image=new Image();image.alt='';image.decoding='async';
        image.addEventListener('load',()=>thumbnail.replaceChildren(image),{once:true});image.src=page.image;
      }
      control.append(thumbnail,element('span','第 '+page.number+' 页'),icon);sheet.replaceChildren(control);
    }
    show(pages.find(p=>p.number===model.page) || pages[0]);
    if (pages.length>1) {
      const pick=element('select'); pick.setAttribute('aria-label','选择协议物理页');
      for (const p of pages) pick.add(new Option('第 '+p.number+' 页',p.number));
      pick.value=String(model.page);pick.addEventListener('change',()=>show(pages[pick.selectedIndex]));info.append(pick);
    }
    info.prepend(element('h3',model.label));
    if (model.sharedPage) info.append(element('p','与排印版的打印页相同，原件含 '+notes.length+' 条批注。'));
    else if (record.state==='word_text') info.append(element('p','核对双方签署的定稿或签署记录。'));
    else if (record.kind==='image') info.append(element('p','对照原图核实双方签章和版本。'));
    else if (record.state==='word_visual') info.append(element('p','核对图形所在的签章栏及签署版本。'));
    pageBox.append(sheet,info);root.append(pageBox);
    const views=[];
    if (terms.length) views.push({key:'terms',name:'条款对照',panel:AddendumCard.termPanel(terms,true)});
    if (notes.length || record.unplaced || model.word?.coverage && model.word.coverage!=='complete') {
      const details=element('div','','agreement-notes'), body=element('div');
      if (notes.length) {
        const pick=element('select');pick.setAttribute('aria-label','选择协议批注');
        for (const [i,n] of notes.entries()) pick.add(new Option('批注 '+(i+1)+(n.author?' · '+n.author:''),String(i)));
        function display() {
          const note=notes[pick.selectedIndex];body.dataset.note=note.id;
          body.replaceChildren(WordCommentCard.compare({name:filename,original},note));
        }
        details.addEventListener('select-agreement-note',event=>{
          const i=notes.findIndex(n=>n.id===event.detail);
          if (i>=0) {pick.selectedIndex=i;display();}
        });
        if (notes.length>1) details.append(pick);
        pick.addEventListener('change',display); display(); details.append(body);
      }
      if (record.unplaced) details.append(element('p',record.unplaced+' 条批注的页面归属待核。'));
      if (model.word?.coverage!=='complete') {
        details.append(element('p',model.word?.limitations?.includes('tracked')?'原件含修订记录，请核对双方采用的定稿。':'原件的审阅范围待核。'));
      }
      views.push({key:'notes',name:notes.length?'原批注':'审阅范围',count:notes.length,panel:details});
    }
    if (rows.length) {
      const panel=element('div','','agreement-signature-lines');
      for (const r of rows) {
        const control=r.control();control.classList.add('agreement-signature-line');
        control.append(element('small',r.side),element('span',r.quote),element('small','第 '+r.line+' 行'));
        panel.append(control);
      }
      views.push({key:'signatures',name:'签章栏',count:rows.length,panel});
    }
    if (views.length) root.append(inspector(id,views,record.state==='word_review'?'notes':'terms'));
    const footer=element('footer','','agreement-proof-actions');
    const verify=element('details','','agreement-verification');
    verify.append(element('summary','查看原件校验值'));
    const hashes=element('dl');
    for (const [name,value] of [['上传原件',model.sourceHash],...pages.map(p=>['第 '+p.number+' 页页图',p.hash]),
      [model.word?.part,model.word?.part_sha256]]) {
      if (name && value) hashes.append(element('dt',name),element('dd',value));
    }
    verify.append(originalFileCheck(original,model.sourceHash),hashes);footer.append(verify);
    if (model.request) {
      const ask=element('button','起草补件要求','agreement-request');
      ask.type='button';ask.addEventListener('click',model.request);footer.append(ask);
    }
    root.append(footer);
    return root;
  }
  return {render};
})();
