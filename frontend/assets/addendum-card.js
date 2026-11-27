const AddendumCard = (() => {
  function element(tag,text,cls) {
    const node=document.createElement(tag);
    if (text) node.textContent=text;
    if (cls) node.className=cls;
    return node;
  }
  function markedValue(value,other) {
    const label=element('strong'), chars=Array.from(value), compare=Array.from(other);
    let start=0, end=0;
    while (start<Math.min(chars.length,compare.length) && chars[start]===compare[start]) start++;
    while (end<Math.min(chars.length,compare.length)-start && chars.at(-1-end)===compare.at(-1-end)) end++;
    const change=chars.slice(start,chars.length-end).join('');
    if (change && start+end>0) label.append(chars.slice(0,start).join(''),element('mark',change),chars.slice(chars.length-end).join(''));
    else label.textContent=value;
    return label;
  }
  function termPanel(terms) {
    const change=element('section','','addendum-terms'), header=element('div','','addendum-terms-head');
    const title=element('div','','addendum-terms-title');
    title.append(element('strong','协议所列变更'),element('small','生效日待核'));
    const toggle=element('button','对照原行','addendum-original-mode');
    toggle.type='button';toggle.setAttribute('role','switch');toggle.setAttribute('aria-checked','false');
    const track=element('i');track.setAttribute('aria-hidden','true');toggle.prepend(track);
    header.append(title,toggle);change.append(header);
    const controls=terms.map((row,i)=>{
      const other=i%2===0?terms[i+1]:terms[i-1];
      const control=row.control(), label=markedValue(row.value,other.value);
      const place=element('span','第 '+row.page+' 页 · 第 '+row.line+' 行','addendum-line-position');
      const excerpt=element('span','','addendum-excerpt');
      const original=element('span',row.quote,'addendum-literal');
      const icon=element('i','','ui-glyph ic-arrows-angle-expand');icon.setAttribute('aria-hidden','true');
      control.classList.add('addendum-term');control.dataset.side=i%2?'after':'before';
      excerpt.append(original); place.hidden=excerpt.hidden=true;
      control.append(element('small',row.label),label,icon,place,excerpt);change.append(control);
      return {row,label,place,excerpt};
    });
    toggle.addEventListener('click',()=>{
      const enabled=toggle.getAttribute('aria-checked')==='false';
      toggle.setAttribute('aria-checked',String(enabled));change.classList.toggle('show-original',enabled);
      for (const {row,label,place,excerpt} of controls) {
        label.hidden=enabled;place.hidden=excerpt.hidden=!enabled;
        if (!enabled || excerpt.dataset.loading || excerpt.querySelector('canvas')) continue;
        excerpt.dataset.loading='true';
        row.excerpt().then(canvas=>{
          if (!canvas) throw new Error('原页不可用');
          if (!excerpt.isConnected) return;
          canvas.setAttribute('aria-hidden','true');excerpt.append(canvas);excerpt.classList.add('has-image');
          place.textContent='第 '+row.page+' 页 · 第 '+row.line+' 行';
        }).catch(()=>{place.textContent='第 '+row.page+' 页 · 第 '+row.line+' 行 · 页图暂不可用';})
          .finally(()=>delete excerpt.dataset.loading);
      }
    });
    return change;
  }
  function render(models,id,initial) {
    const root=element('section','','addendum-card'); root.id=id; root.tabIndex=-1;
    root.setAttribute('aria-label','补充协议签署');
    const switches=element('div','','addendum-choices'), body=element('div');
    switches.setAttribute('role','group'); switches.setAttribute('aria-label','选择补充协议原件');
    if (models.length>1) root.append(switches);
    root.append(body);
    function show(model) {
      root.dataset.agreement=model.key;
      for (const button of switches.children) button.setAttribute('aria-pressed',String(button.dataset.agreement===model.key));
      const card=PdfSignatureCard.render({...model.pdf,id:id+'-pdf'});
      body.replaceChildren(card);
      if (model.terms.length) body.append(termPanel(model.terms));
      if (model.related) body.append(model.related());
      if (model.permalink) body.append(model.permalink());
      model.onSelect?.();
    }
    for (const model of models) {
      const button=element('button',model.label);button.type='button';button.dataset.agreement=model.key;
      button.addEventListener('click',()=>show(model)); switches.append(button);
    }
    root.addEventListener('select-agreement',event=>{
      const model=models.find(m=>m.key===event.detail); if (model) show(model);
    });
    show(models.find(m=>m.key===initial) || models[0]);
    return root;
  }
  return {render,termPanel};
})();
