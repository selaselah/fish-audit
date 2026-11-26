// One payment document at a time. The workpaper and the public specimen supply their own original-page openers.
const PaymentProofCard = (() => {
  const outcomes = {conflict:'状态与受理说明冲突', application:'仅见付款申请', limited:'回单载有限定',
    review:'凭证范围待核', unverified:'原行依据待核'};
  const labels = {title:'凭证名称', request:'申请单据', status:'交易状态', pending_status:'办理状态',
    limit:'凭证说明', wrapped_limit:'凭证说明', request_time:'申请时间', purpose:'款项用途'};
  const success=quote=>/^(交易|转账)状态\s*:\s*(交易成功|转账成功|付款成功|支付成功|成功|已完成|已记账|已入账)$/u.test(quote.normalize('NFKC').trim());
  function make(tag, cls, text) {
    const e=document.createElement(tag);
    if (cls) e.className=cls;
    if (text) e.textContent=text;
    return e;
  }
  function openButton(row, label) {
    const button=make(row.url?'a':'button','debit-open',label);
    if (row.url) {button.href=row.url;button.target='_blank';button.rel='noopener';}
    else button.type='button';
    button.setAttribute('aria-haspopup','dialog');
    button.setAttribute('aria-label',label+'，'+row.file+'，'+row.place);
    button.addEventListener('click',e=>{
      if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
      if (row.open(button)!==false) e.preventDefault();
    });
    return button;
  }
  function render(items,id) {
    const panel=make('section','payment-proof');panel.id=id;panel.tabIndex=-1;
    const heading=make('h3','','扣款凭证核对');heading.id=id+'-title';
    panel.setAttribute('aria-labelledby',heading.id);
    const header=make('div','debit-head'), result=make('strong','debit-state');
    result.setAttribute('aria-live','polite');
    const map=make('div','debit-map'), identity=make('div','debit-identity'), file=make('span','debit-file');
    const choose=make('select','debit-picker');choose.setAttribute('aria-label','选择待核付款凭证');
    for (const item of items) {const option=make('option','',item.name);option.value=item.key;choose.append(option);}
    const modes=make('div','debit-modes');modes.setAttribute('role','group');modes.setAttribute('aria-label','原行显示方式');
    const pair=make('div','debit-pair'), extra=make('details','debit-extra');
    const note=make('div','debit-empty');note.hidden=true;note.setAttribute('role','status');
    identity.append(heading,items.length>1?choose:file);
    const controls=make('div','debit-controls');controls.append(result,modes);
    header.append(map,identity,controls);panel.append(header,pair,extra,note);
    let active, mode='image';
    function locate(selected) {
      if (!selected?.pageImage || !selected.rects?.length) {map.replaceChildren();map.hidden=true;return;}
      if (map.dataset.row===selected.id && !map.hidden) return;
      map.hidden=false;map.dataset.row=selected.id;
      const opener=openButton(selected,'查看原页');opener.title=selected.file+' · '+selected.place;
      const image=new Image();image.alt='';image.src=selected.pageImage;opener.replaceChildren(image);
      const imageError=()=>{if (map.dataset.row===selected.id) map.hidden=true;};
      image.addEventListener('error',imageError,{once:true});
      for (const row of [...active.left,...active.right]) {
        if (row.pageImage!==selected.pageImage) continue;
        for (const [left,top,right,bottom] of row.rects || []) {
          const mark=make('i','debit-mark');mark.setAttribute('aria-hidden','true');
          mark.dataset.active=String(row.id===selected.id);
          Object.assign(mark.style,{left:left*100+'%',top:top*100+'%',width:(right-left)*100+'%',height:(bottom-top)*100+'%'});
          opener.append(mark);
        }
      }
      map.replaceChildren(opener);
    }
    function display(next) {
      mode=next;panel.dataset.mode=mode;
      for (const b of modes.children) b.setAttribute('aria-pressed',String(b.dataset.mode===mode));
    }
    for (const [key,label] of [['image','原件'],['text','文字']]) {
      const b=make('button','',label);b.type='button';b.dataset.mode=key;
      b.addEventListener('click',()=>display(key));modes.append(b);
    }
    function leaf(pairLabel,rows) {
      const section=make('section','debit-side'), title=make('h4','',pairLabel);
      section.append(title);
      if (!rows.length) section.append(make('p','debit-unknown','待补原件'));
      for (const row of rows) {
        const line=make('div','debit-line'), quote=make('blockquote','debit-quote',row.quote);
        const location=openButton(row,row.place+' ↗');
        location.addEventListener('focus',()=>locate(row));
        location.addEventListener('pointerenter',()=>locate(row));
        line.append(quote);section.append(line,location);
        if (row.excerpt) row.excerpt().then(crop=>{
          if (!crop || !pair.contains(section)) return;
          const strip=make('div','debit-strip');
          crop.setAttribute('aria-hidden','true');strip.append(crop);line.append(strip);line.classList.add('with-crop');
        }).catch(()=>{ /* The exact transcript stays visible if the original cannot be loaded. */ });
      }
      return section;
    }
    function paint(item,announce=false) {
      if (!item) return;
      delete panel.dataset.invalidReceipt;
      active=item;panel.dataset.selected=item.key;panel.dataset.clause=item.clause || '';
      panel.dataset.state=item.state;panel.dataset.outOfStage='false';note.hidden=true;
      choose.value=item.key;file.textContent=item.name;result.textContent=outcomes[item.state];
      modes.hidden=![...item.left,...item.right].some(r=>r.excerpt);
      pair.replaceChildren(leaf(item.leftLabel,item.left),leaf(item.rightLabel,item.right));
      const used=new Set([...item.left,...item.right].map(r=>r.id));
      const remaining=item.rows.filter(r=>!used.has(r.id));
      extra.hidden=!remaining.length;extra.open=false;extra.replaceChildren();
      if (remaining.length) {
        extra.append(make('summary','','其他原行（'+remaining.length+'）'));
        for (const row of remaining) extra.append(openButton(row,row.quote));
      }
      locate(item.right.find(r=>r.rects?.length) || item.left.find(r=>r.rects?.length));
      display(mode);
      if (announce) panel.dispatchEvent(new CustomEvent('select-contract-phase',{detail:item.clause}));
    }
    choose.addEventListener('change',()=>paint(items.find(i=>i.key===choose.value),true));
    panel.addEventListener('select-proof',e=>{
      const selected=items.find(i=>i.key===e.detail);
      if (selected) paint(selected,true);
      else {
        panel.dataset.invalidReceipt='true';panel.dataset.outOfStage='true';note.replaceChildren(make('span','','本版未收录所选凭证。'));
        const reset=make('button','debit-open','查看本版凭证');reset.type='button';
        reset.onclick=()=>paint(items[0],true);note.append(reset);note.hidden=false;
      }
    });
    panel.addEventListener('inspect-payment-stage',e=>{
      if (panel.dataset.invalidReceipt) return;
      if (!active.clause || active.clause===e.detail.clause_ref) {
        panel.dataset.outOfStage='false';note.hidden=true;return;
      }
      const target=items.find(i=>i.clause===e.detail.clause_ref);
      if (target) {paint(target);return;}
      panel.dataset.outOfStage='true';note.replaceChildren(make('span','','本期未关联这份凭证。'));
      const back=make('button','debit-open','查看'+active.stage+'凭证');back.type='button';back.onclick=()=>paint(active,true);
      note.append(back);note.hidden=false;
    });
    panel.addEventListener('reveal-evidence',()=>{if (!panel.dataset.invalidReceipt && panel.dataset.outOfStage==='true' && active.clause) {
      panel.dispatchEvent(new CustomEvent('select-contract-phase',{detail:active.clause}));
    }});
    paint(items.find(i=>i.state==='conflict') || items[0]);return panel;
  }
  function pairs(rows,state) {
    const preferred=rows.filter(r=>r.line && r.rects?.length && !r.disputed);
    const ordered=[...new Set([...preferred,...rows])];
    const samePage=(a,b)=>a && b && a.pageImage===b.pageImage;
    const statuses=ordered.filter(r=>r.kind==='status' || r.kind==='pending_status');
    const request=ordered.find(r=>r.kind==='request');
    const restrictions=ordered.filter(r=>['limit','wrapped_limit'].includes(r.kind));
    if (state==='conflict') {
      const positive=preferred.filter(r=>r.clear && r.kind==='status' && success(r.quote));
      const restriction=preferred.find(r=>r.explicit && positive.some(s=>samePage(s,r)));
      const status=positive.find(s=>samePage(s,restriction));
      if (restriction && status) return {leftLabel:'状态栏',left:[status],rightLabel:labels[restriction.kind],right:[restriction]};
    }
    if (restrictions.length) {
      const first=restrictions[0];
      const second=first.kind==='wrapped_limit' && restrictions.find(r=>r.kind===first.kind && samePage(r,first) && r.line===first.line+1);
      const status=statuses.find(r=>samePage(r,first));
      const left=status || ordered.find(r=>r.kind==='title' && samePage(r,first));
      return {leftLabel:status?'状态栏':'单据名称',left:left?[left]:[],rightLabel:'凭证说明',right:second?[first,second]:[first]};
    }
    const status=statuses.find(r=>samePage(r,request)) || ordered.find(r=>r.kind==='request_time' && samePage(r,request));
    return {leftLabel:'单据名称',left:request?[request]:[],rightLabel:'申请记录',right:status?[status]:[]};
  }
  return {render,pairs,labels,success};
})();
