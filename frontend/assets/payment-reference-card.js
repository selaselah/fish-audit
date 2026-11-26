// Shared presentation for the issued workpaper and its fixed, watermarked public example.
const PaymentReferenceCard = (() => {
  const titles = {other_batch:'引用了其他批次',matched:'本期单号相符',unlocated:'所引原件待补',
    scope:'期次归属待核',reference:'引用编号待核',source:'回单原文待核',records:'验收单归属待核',unverified:'来源待核'};
  function node(tag,cls,text) {
    const e=document.createElement(tag);
    if (cls) e.className=cls;
    if (text) e.textContent=text;
    return e;
  }
  function icon(name) {
    const i=node('i','ui-glyph ic-'+name);i.setAttribute('aria-hidden','true');return i;
  }
  function link(source,cls) {
    const button=node(source.url?'a':'button',cls);
    if (source.url) {button.href=source.url;button.target='_blank';button.rel='noopener';}
    else button.type='button';
    button.setAttribute('aria-haspopup','dialog');
    button.addEventListener('click',event=>{
      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      if (source.open(button)!==false) event.preventDefault();
    });
    return button;
  }
  function difference(value,other,show) {
    const out=node('b','payment-reference-number');
    if (!show || !other || !value || value===other) {out.textContent=value || '待核原件';return out;}
    let start=0,end=0;
    while (start<value.length && value[start]===other[start]) start++;
    while (end<Math.min(value.length,other.length)-start && value[value.length-1-end]===other[other.length-1-end]) end++;
    out.append(value.slice(0,start),node('mark','',value.slice(start,value.length-end)),value.slice(value.length-end));
    return out;
  }
  function render(items,id,initialMode='number') {
    const card=node('section','payment-reference-card');
    card.id=id;card.tabIndex=-1;card.setAttribute('aria-label','回单与验收单核对');
    const chooser=node('div','payment-reference-picker'),body=node('div','payment-reference-body');
    const label=node('span','payment-reference-kicker',items.length+' 笔回单');
    const tabs=node(items.length>4?'select':'div','payment-reference-tabs');
    const menu=tabs.tagName==='SELECT';
    tabs.setAttribute('aria-label','选择要核对的回单');
    if (!menu) tabs.setAttribute('role','tablist');
    body.id=id+'-payment'; if (!menu && items.length>1) body.setAttribute('role','tabpanel');
    chooser.append(label,tabs); if (items.length>1) card.append(chooser);
    card.append(body);
    let selected=0,showDiff=true,mode=initialMode;
    function paint() {
      const item=items[selected],state=item.state;
      card.dataset.referenceState=state;card.dataset.payment=item.key;
      card.dataset.clause=item.clauseRef || '';
      body.replaceChildren();
      const header=node('div','payment-reference-heading');
      const heading=node('h3','',item.stage || '期次待核');
      if (item.batch) heading.append(node('small','','第 '+item.batch+' 批验收'));
      const status=node('span','payment-reference-verdict',titles[state] || titles.unverified);
      status.prepend(icon(state==='matched'?'clipboard-check':state==='other_batch'?'exclamation-diamond':'eye'));
      header.append(heading,status);body.append(header);
      const grid=node('div','payment-reference-pair');
      const canRead=[item.bank,item.expected].some(s=>s?.excerpt);
      const readMode=mode==='source' && canRead;
      card.dataset.readMode=readMode?'source':'number';
      if (canRead) {
        const views=node('div','payment-reference-modes');views.setAttribute('role','group');views.setAttribute('aria-label','凭证显示方式');
        for (const [key,title] of [['number','核对单号'],['source','对照原行']]) {
          const b=node('button','',title);b.type='button';b.dataset.mode=key;
          b.prepend(icon(key==='number'?'card-checklist':'file-earmark-text'));
          b.setAttribute('aria-pressed',String(readMode===(key==='source')));
          b.addEventListener('click',()=>{mode=key;paint();body.querySelector('[data-mode="'+key+'"]').focus();});
          views.append(b);
        }
        body.append(views);
      }
      function side(title,source,peer) {
        const wrap=source?link(source,'payment-reference-source'):node('div','payment-reference-source empty');
        const cap=node('span','payment-reference-caption',title);
        cap.prepend(icon(title==='回单所引'?'receipt':'clipboard-check'));
        const val=difference(source?.value,peer?.value,showDiff && state==='other_batch');
        wrap.append(cap,val);
        if (readMode) {
          if (source?.excerpt) {
            const strip=node('span','payment-reference-strip','正在载入原行…');
            source.excerpt().then(image=>{
              if (!image) {strip.textContent='原行图像待核';return;}
              image.setAttribute('aria-hidden','true');strip.replaceChildren(image);
            }).catch(()=>{strip.textContent='原行图像未载入，可打开原页';});
            wrap.append(strip);val.classList.add('payment-reference-readout');
          } else if (source) wrap.append(node('span','payment-reference-strip','可打开原页核读'));
        }
        if (source) {
          const meta=node('span','payment-reference-location',source.location);meta.append(icon('arrows-angle-expand'));
          wrap.append(meta);
          wrap.setAttribute('aria-label',title+'，'+source.value+'，'+source.location+'，打开原件');
        }
        grid.append(wrap);
      }
      side('回单所引',item.bank,item.expected);side('本期应据',item.expected,item.bank);
      body.append(grid);
      const tools=node('div','payment-reference-actions');
      if (item.actual && state==='other_batch') {
        const original=link(item.actual,'payment-reference-origin');
        original.append(icon('layers'),document.createTextNode('查看第 '+item.actualBatch+' 批验收单'),icon('arrows-angle-expand'));tools.append(original);
      }
      if (state==='other_batch' && !readMode) {
        const toggle=node('label','payment-reference-toggle'),input=node('input');
        input.type='checkbox';input.setAttribute('role','switch');input.checked=showDiff;
        const apply=()=>{const values=[item.bank,item.expected];grid.querySelectorAll('.payment-reference-number').forEach((e,i)=>e.replaceWith(difference(values[i]?.value,values[1-i]?.value,showDiff)));};
        input.addEventListener('change',()=>{showDiff=input.checked;apply();});
        toggle.append(input,node('span','','标出差异'));tools.append(toggle);
      }
      if (tools.childElementCount) body.append(tools);
      if (item.total) {
        const total=node('div','payment-reference-total');
        const amount=item.total.replace(/\B(?=(\d{3})+\.)/gu,',');
        total.append(node('span','','本期所见合计'),node('strong','',amount+' 元'),node('span','','与约定相符'));body.append(total);
      }
      const fold=node('details','payment-reference-basis');
      const summary=node('summary','','核对依据');fold.append(summary,node('p','',item.detail));
      for (const source of item.basis || []) {
        const a=link(source,'payment-reference-basis-link');a.append(source.label,icon('arrows-angle-expand'));fold.append(a);
      }
      body.append(fold);
      card.dispatchEvent(new CustomEvent('change-reference',{detail:item}));
    }
    function select(n) {
      selected=n;
      if (menu) tabs.selectedIndex=n;
      else if (items.length>1) {
        [...tabs.children].forEach((tab,i)=>{tab.tabIndex=i===n?0:-1;tab.setAttribute('aria-selected',String(i===n));});
        body.setAttribute('aria-labelledby',tabs.children[n].id);
      }
      paint();
    }
    if (items.length>1) items.forEach((item,i)=>{
      const button=node(menu?'option':'button','','');
      if (menu) button.textContent=[item.choice,item.amount].filter(Boolean).join(' · ');
      else {
        button.append(node('span','',item.choice));
        if (item.amount) button.append(node('b','',item.amount));
      }
      if (!menu) {
        button.type='button';button.id=id+'-transfer-'+i;button.setAttribute('role','tab');button.setAttribute('aria-controls',body.id);
        button.addEventListener('click',()=>select(i));
        button.addEventListener('keydown',event=>{
          const n={ArrowRight:(i+1)%items.length,ArrowLeft:(i+items.length-1)%items.length,Home:0,End:items.length-1}[event.key];
          if (n!==undefined) {event.preventDefault();select(n);tabs.children[n].focus();}
        });
      }
      tabs.append(button);
    });
    if (menu) tabs.addEventListener('change',()=>select(tabs.selectedIndex));
    card.addEventListener('select-reference',event=>{const n=items.findIndex(i=>i.key===event.detail);if(n>=0) select(n);});
    const risk=items.findIndex(i=>i.state==='other_batch');
    select(risk>=0?risk:Math.max(0,items.findIndex(i=>i.state!=='matched')));
    return card;
  }
  return {render};
})();
