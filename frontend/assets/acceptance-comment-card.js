// Word stores the selected text and the comment independently of the printable page.
const WordCommentCard = (() => {
  function element(tag, text, cls) {
    const node=document.createElement(tag);
    if (text) node.textContent=text;
    if (cls) node.className=cls;
    return node;
  }
  function icon(name) {
    const node=element('i','','ui-glyph ic-'+name);
    node.setAttribute('aria-hidden','true');
    return node;
  }
  function button(text,click,cls) {
    const node=element('button',text,cls);
    node.type='button';
    node.addEventListener('click',click);
    return node;
  }
  function fromFile(text,doc) {
    const link=element('a',text,'word-file');
    link.href=doc.original;
    link.download=doc.name;
    link.prepend(icon('file-earmark-text'));
    return link;
  }
  function sourceButton(doc,note) {
    const {anchor,location}=note;
    const content=element('div','','word-source');
    const title=element('span','正文选区','word-caption');
    content.append(title);
    if (anchor) {
      const letters=Array.from(anchor.quote);
      const line=element('p','','word-quote');
      line.append(letters.slice(0,anchor.start).join(''),element('mark',anchor.selected),letters.slice(anchor.end).join(''));
      content.append(line);
      if (!note.open && !note.openPage) content.append(element('span','打印页位置待核','word-caption'));
    } else content.append(element('p','批注位置需在 Word 中核对。','word-unknown'));
    const open=note.open || note.openPage;
    if (!open || !location) return content;
    const place='第 '+location.page+' 页'+(note.open?' · 第 '+location.line+' 行':' · 核对整页');
    const jump=button('',event=>open(event.currentTarget),'word-page-jump');
    jump.setAttribute('aria-label',doc.name+' · 第 '+location.page+' 页'+(note.open?'第 '+location.line+' 行':'')+'，打开原页');
    jump.setAttribute('aria-haspopup','dialog');
    jump.append(icon('eye'),element('span',place),icon('arrows-angle-expand'));
    content.append(jump);
    if (!note.thumbnail) return content;
    const miniature=button('',event=>note.open(event.currentTarget),'word-mini');
    miniature.setAttribute('aria-label','放大'+doc.name+'，定位批注所指原行');
    miniature.setAttribute('aria-haspopup','dialog');
    const paper=element('span','','word-mini-page'), img=element('img');
    img.alt=''; img.loading='lazy'; img.src=note.thumbnail;
    paper.append(img);
    for (const [l,t,r,b] of note.rects || []) {
      const mark=element('i');
      mark.style.left=l*100+'%'; mark.style.top=t*100+'%';
      mark.style.width=(r-l)*100+'%'; mark.style.height=(b-t)*100+'%';
      paper.append(mark);
    }
    miniature.append(paper);
    const paired=element('div','','word-source-pair');
    paired.append(miniature,content);
    return paired;
  }
  function compare(doc,note) {
    if (!note) {
      const empty=element('div','','word-empty');
      const clear=doc.coverage==='complete' && doc.count===0;
      empty.append(icon(clear?'journal-text':'eye'),element('strong',clear?'此原件未检出标准审阅批注':'审阅记录需人工核对'));
      if (!clear) empty.append(fromFile('查看 Word 原件',doc));
      return empty;
    }
    const pair=element('div','','word-pair'), margin=element('div','','word-margin');
    const credit=element('div','','word-credit');
    credit.append(icon('journal-text'),element('strong',note.author || '未记载批注署名'));
    if (note.author) credit.querySelector('strong').setAttribute('aria-label','批注署名：'+note.author);
    margin.append(credit,element('blockquote',(note.text || '未提取到批注文字')+(note.shortened?'…':'')));
    pair.append(sourceButton(doc,note),margin);
    return pair;
  }
  function payments(items) {
    const list=element('div','','word-impacts');
    if (!items.length) list.append(element('p','本版底稿没有引用此记录的期款。','word-unknown'));
    for (const item of items) {
      const row=item.open?button('',event=>item.open(event.currentTarget),'word-impact'):element('div','','word-impact');
      row.dataset.findingId=item.id;
      const value=element('strong',item.kind==='payment'?'回单':item.kind==='total'?'合计':item.share?item.share+'%':'款项','word-share');
      const name=element('span','','word-phase');
      name.append(element('strong',item.name),element('small',item.kind==='payment'?'实付时点':item.kind==='total'?'回单汇总':'付款条件'));
      const status=element('span',item.statusName,'word-outcome');
      status.dataset.state=item.status;
      row.append(value,name,status);
      if (item.open) row.append(icon('arrows-angle-expand'));
      list.append(row);
    }
    return list;
  }
  function render(model) {
    const root=element('section','','word-review-card');
    root.id=model.id; root.tabIndex=-1; root.dataset.state=model.status;
    root.setAttribute('aria-label',model.role==='contract'?'合同付款条款批注':'Word 验收批注');
    const choices=model.documents.flatMap(doc=>doc.notes.length?doc.notes.map(note=>({doc,note})):[{doc,note:null}]);
    let selected=choices.findIndex(c=>c.note || c.doc.coverage!=='complete');
    if (selected<0) selected=0;
    function draw(which=0) {
      const {doc,note}=choices[selected];
      const header=element('div','','word-review-head');
      const file=element('span','','word-review-title');
      file.append(icon('file-earmark-text'),element('strong',doc.name));
      const count=element('small',doc.count===null?'审阅层待核':'原件 '+doc.count+' 条批注','word-count');
      header.append(file,count);
      if (choices.length>1) {
        const choice=element('select');
        choice.setAttribute('aria-label','选择文件及批注');
        choices.forEach(({doc,note},i)=>{
          const label=doc.name+(note?' · 批注 '+(doc.notes.indexOf(note)+1):'');
          const option=element('option',label); option.value=String(i); choice.append(option);
        });
        choice.value=String(selected);
        choice.addEventListener('change',()=>{selected=choice.selectedIndex;draw();root.querySelector('select').focus();});
        header.append(choice);
      }
      const panes=element('div','','word-panes'), nav=element('div','','word-view-switch');
      nav.setAttribute('role','tablist'); nav.setAttribute('aria-label','批注核对视图');
      const refs=note?.related || doc.related || [];
      const hasTabs=Boolean(note || refs.length);
      const parts=[['正文与批注',compare(doc,note)],['关联款项',payments(refs)]];
      function select(i) {
        [...nav.children].forEach((tab,n)=>{
          tab.tabIndex=n===i?0:-1;
          tab.setAttribute('aria-selected',String(n===i)); panes.children[n].hidden=n!==i;
        });
      }
      parts.forEach(([name,body],i)=>{
        const panel=element('div','','word-review-pane'), tab=button(name,()=>select(i));
        panel.id=model.id+'-pane-'+i; tab.id=model.id+'-tab-'+i;
        panel.append(body);
        if (hasTabs) {
          panel.setAttribute('role','tabpanel'); panel.setAttribute('aria-labelledby',tab.id);
          tab.setAttribute('role','tab'); tab.setAttribute('aria-controls',panel.id);
          tab.addEventListener('keydown',event=>{
            const target={ArrowLeft:1-i,ArrowRight:1-i,Home:0,End:1}[event.key];
            if (target!==undefined) {event.preventDefault();select(target);nav.children[target].focus();}
          });
        }
        nav.append(tab); panes.append(panel);
      });
      const footer=element('div','','word-review-tools');
      const proof=element('details','','word-proof');
      proof.append(element('summary','核验记录'));
      const list=element('dl');
      for (const [label,value] of [['Word 段落',note?.anchor?.paragraph],['审阅部件',doc.part],
        ['原件 SHA-256',doc.original_sha256],['批注部件 SHA-256',doc.part_sha256],['页图 SHA-256',note?.location?.page_sha256]]) {
        if (value) list.append(element('dt',label),element('dd',String(value)));
      }
      proof.append(list);
      footer.append(fromFile('下载原件',doc));
      if (model.request && (note || doc.coverage!=='complete')) footer.append(button('起草补件意见',()=>model.request(doc,note),'word-request'));
      root.replaceChildren(header);
      if (hasTabs) root.append(nav);
      root.append(panes);
      if (doc.coverage!=='complete') root.append(element('p','此文件的审阅层需结合 Word 原件复核。','word-coverage'));
      root.append(footer,proof);
      select(which);
    }
    root.addEventListener('word-review-select',event=>{
      const i=choices.findIndex(({doc,note})=>note?.id===event.detail || doc.id===event.detail);
      if (i>=0) {selected=i;draw();}
    });
    draw(); return root;
  }
  function panel(model) {
    if (!model.stages?.length) return render(model);
    const doc=model.documents[0], stages=model.stages;
    const root=element('section','','contract-review');
    root.id=model.id; root.tabIndex=-1; root.dataset.state=model.status;
    root.setAttribute('aria-label','按期次核对合同批注');
    const top=element('div','','contract-index-head');
    top.append(element('strong','合同期款'),element('span','正文比例'));
    const tabs=element('div','','contract-index'), body=element('div','','contract-index-body');
    tabs.setAttribute('role','tablist'); tabs.setAttribute('aria-label','选择合同期次');
    body.id=model.id+'-selection'; body.setAttribute('role',model.externalStages?'group':'tabpanel');
    const choices=[];
    function select(i,noteRef) {
      const stage=stages[i];
      choices.forEach((tab,j)=>{
        tab.setAttribute('aria-selected',String(i===j)); tab.tabIndex=i===j?0:-1;
      });
      if (model.externalStages) body.setAttribute('aria-label',stage.name+'合同原文及批注');
      else body.setAttribute('aria-labelledby',choices[i].id);
      const notes=doc.notes.filter(n=>stage.notes.includes(n.id));
      if (notes.length) {
        const card=render({...model,id:model.id+'-source',documents:[{...doc,notes}]});
        body.replaceChildren(card);
        if (noteRef) card.dispatchEvent(new CustomEvent('word-review-select',{detail:noteRef}));
        return;
      }
      const line=element('div','','contract-printed-clause'), lead=element('div','','contract-clause-label');
      lead.append(icon('journal-text'),element('span','合同原文'),element('small','本期未关联批注'));
      const jump=button('第 '+stage.page+' 页 · 第 '+stage.line+' 行',event=>stage.open(event.currentTarget),'word-page-jump');
      jump.append(icon('arrows-angle-expand'));
      line.append(lead,element('p',stage.quote),jump,fromFile('下载原件',doc)); body.replaceChildren(line);
    }
    if (!model.externalStages) stages.forEach((stage,i)=>{
      const tab=button('',()=>select(i),'contract-stage');
      tab.id=model.id+'-stage-'+i;
      tab.setAttribute('role','tab'); tab.setAttribute('aria-controls',body.id);
      tab.dataset.noted=String(stage.notes.length>0);
      const name=element('span',stage.name), number=element('strong',stage.share?stage.share+'%':'待核');
      tab.append(name,number);
      if (stage.notes.length) {
        const count=element('span',String(stage.notes.length),'contract-note-count');
        count.prepend(icon('journal-text')); count.setAttribute('aria-hidden','true'); tab.append(count);
      }
      tab.append(element('span','，'+stage.notes.length+' 条关联批注','contract-sr-only'));
      tab.addEventListener('keydown',event=>{
        const next={ArrowRight:(i+1)%stages.length,ArrowLeft:(i+stages.length-1)%stages.length,Home:0,End:stages.length-1}[event.key];
        if (next===undefined) return;
        event.preventDefault();select(next);choices[next].focus();
      });
      choices.push(tab);tabs.append(tab);
    });
    root.addEventListener('word-review-select',event=>{
      const i=stages.findIndex(s=>s.notes.includes(event.detail));
      const target=i>=0?i:event.detail===doc.id?Math.max(0,stages.findIndex(s=>s.notes.length)):-1;
      if (target<0) return;
      if (model.externalStages) root.dispatchEvent(new CustomEvent('select-contract-phase',{detail:stages[target].ref}));
      select(target,event.detail);
    });
    if (model.externalStages) root.addEventListener('contract-stage-change',event=>{
      const i=stages.findIndex(s=>s.ref===event.detail);
      if (i>=0) select(i);
    });
    else root.append(top,tabs);
    root.append(body);
    select(Math.max(0,stages.findIndex(s=>s.notes.length)));
    return root;
  }
  return {render,panel,compare};
})();
