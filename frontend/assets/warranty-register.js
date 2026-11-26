// The same register presents issued workpaper evidence and the fixed public sample.
const WarrantyRegister = (() => {
  function make(tag, cls, text) {
    const item = document.createElement(tag);
    if (cls) item.className = cls;
    if (text) item.textContent = text;
    return item;
  }
  function icon(name) {
    const item = make('i','ui-glyph ic-'+name);
    item.setAttribute('aria-hidden','true');
    return item;
  }
  function button(label, cls) {
    const item = make('button',cls,label);
    item.type = 'button';
    return item;
  }
  function source(control, row, label, preview) {
    control.className = preview ? 'wr-source' : 'wr-reference';
    control.dataset.source = row.ref;
    control.setAttribute('aria-description','第 '+row.page+' 页第 '+row.line+' 行，'+row.quote);
    if (!preview) {
      control.append(make('span','',label),make('span','wr-reference-value',row.value),icon('arrows-angle-expand'));
      return control;
    }
    const place = make('span','wr-location',row.page+' 页 · '+row.line+' 行');
    const head = make('span','wr-source-head'); head.append(make('strong','',label),place,icon('arrows-angle-expand'));
    const paper = make('span','wr-paper'), quote = make('span','wr-quote',row.quote);
    paper.append(quote); control.append(head,paper);
    preview().then(canvas=>{
      if (!canvas) return;
      canvas.setAttribute('aria-hidden','true'); paper.append(canvas); quote.classList.add('wr-transcribed');
      control.dataset.printed = 'true';
    }).catch(()=>{ /* The verbatim line and the link to its page remain accessible. */ });
    return control;
  }
  const statuses = {ok:'相符', missing:'依据待核', risk:'有风险', issue:'有问题'};
  function render(model, id, sourceControl, headingLevel, compare, permalink) {
    const root = make('section','warranty-register');
    root.setAttribute('aria-label','质保工单与返还依据');
    const header = make('div','wr-heading'), tools = make('div','wr-filters');
    const list = make('div','wr-list'), detail = make('div','wr-detail');
    list.setAttribute('role','tablist'); list.setAttribute('aria-label','选择维修工单');
    list.setAttribute('aria-orientation','vertical');
    detail.id = id+'-detail'; detail.setAttribute('role','tabpanel');
    const changes = model.tickets.filter(ticket=>ticket.difference);
    const all = button('全部 '+model.tickets.length), only = button('有差异 '+changes.length);
    tools.setAttribute('role','group'); tools.setAttribute('aria-label','筛选工单');
    tools.append(all,only);
    const title = make(headingLevel,'','质保工单');
    header.append(title);
    if (changes.length && changes.length<model.tickets.length) header.append(tools);
    root.append(header,list,detail);
    let selected;
    const tabs = new Map();
    function select(ticket) {
      selected = ticket;
      const active = tabs.get(ticket);
      for (const tab of tabs.values()) {
        tab.setAttribute('aria-selected',String(tab===active));
        tab.tabIndex = tab===active ? 0 : -1;
      }
      root.dataset.ticket = ticket.key;
      detail.setAttribute('aria-labelledby',active.id);
      const head = make('div','wr-detail-heading'), pair = make('div','wr-pair');
      head.append(icon(ticket.difference?'exclamation-diamond':'file-earmark-text'),
        make('strong','',ticket.difference?'两份单据记载有差异':ticket.review?'差异依据待核':'工单原文'));
      if (ticket.difference && compare) head.append(compare(ticket));
      if (permalink) head.append(permalink(ticket));
      head.dataset.difference = String(ticket.difference);
      const show = (row,label) => { if (row) pair.append(sourceControl(row,label,true)); };
      if (ticket.difference) {
        show(model.certificate,'期满确认单'); show(ticket.state,'维修工单');
      } else if (ticket.closed && ticket.signer) {
        show(ticket.closed,'工单关闭日期'); show(ticket.signer,'采购方签认栏');
      } else {
        show(ticket.state,'工单状态'); show(ticket.reported,'报修日期');
      }
      const extras = make('details','wr-extra');
      const more = make('summary','','查看其他原行');
      more.append(icon('chevron-down')); extras.append(more);
      for (const [label,row] of [['工单编号',ticket.number],['报修事项',ticket.fault],['报修日期',ticket.reported],
        ['工单状态',ticket.state],['关闭日期',ticket.closed],['采购方签认',ticket.signer],['期满确认日期',model.confirmed]]) {
        if (row && !pair.querySelector('[data-source="'+CSS.escape(row.ref)+'"]')) extras.append(sourceControl(row,label,false));
      }
      detail.replaceChildren(head,pair);
      if (extras.children.length>1) detail.append(extras);
    }
    for (const [i,ticket] of model.tickets.entries()) {
      const tab = button('','wr-row'), main = make('span','wr-row-identity');
      const name = ticket.fault?.value || '报修事项待核';
      main.append(make('strong','',name),make('small','',ticket.number?.value || '工单编号待核'));
      tab.id = id+'-ticket-'+i; tab.dataset.ticket = ticket.key;
      if (ticket.finding) tab.dataset.differenceFinding = ticket.finding;
      tab.setAttribute('role','tab'); tab.setAttribute('aria-controls',detail.id);
      tab.dataset.difference = String(ticket.difference);
      const status = make('span','wr-state',ticket.state?.value || '状态待核');
      tab.append(icon(ticket.difference?'exclamation-diamond':'file-earmark-text'),main,status,icon('chevron-down'));
      tab.addEventListener('click',()=>select(ticket));
      tab.addEventListener('keydown',event=>{
        if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
        const visible = model.tickets.filter(item=>!tabs.get(item).hidden), at = visible.indexOf(ticket), count = visible.length;
        const next = {ArrowUp:(at+count-1)%count,ArrowDown:(at+1)%count,Home:0,End:count-1}[event.key];
        if (next===undefined) return;
        event.preventDefault(); select(visible[next]); tabs.get(visible[next]).focus();
      });
      list.append(tab); tabs.set(ticket,tab);
    }
    function filter(filtered) {
      for (const [ticket,tab] of tabs) tab.hidden = filtered && !ticket.difference;
      all.setAttribute('aria-pressed',String(!filtered)); only.setAttribute('aria-pressed',String(filtered));
      if (!selected || tabs.get(selected).hidden) select(changes[0] || model.tickets[0]);
    }
    all.addEventListener('click',()=>filter(false)); only.addEventListener('click',()=>filter(true)); filter(false);
    const footer = make('div','wr-basis');
    for (const [label,status,row] of [[model.phaseName+'返还条件',model.phaseStatus,model.condition],
      ['回单付款依据',model.paymentStatus,model.paid]]) {
      if (!status) continue;
      const part = make('div','wr-basis-item');
      part.dataset.basis = row && row===model.paid ? 'payment' : 'condition';
      part.append(make('span','',label),make('strong','',statuses[status] || '待核'));
      if (row) part.append(sourceControl(row,row===model.paid?'付款日':'合同条款',false));
      footer.append(part);
    }
    if (footer.childElementCount) root.append(footer);
    return root;
  }
  return {render,source};
})();
