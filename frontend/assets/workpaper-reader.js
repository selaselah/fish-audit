function workpaperEvidence(sections, graph) {
  const available = sections.filter(s=>s.content);
  if (!available.length) return document.createDocumentFragment();
  if (available.length===1 && available[0].key!=='contract-dates') return available[0].content;
  const reader=el('section','','paper-reader');
  reader.setAttribute('aria-label','原件核对');
  if (available.length===1) {
    reader.classList.add('single');
    reader.append(el('h3',available[0].label),available[0].content); return reader;
  }
  const index=graphIndex(graph);
  const rail=box('paper-reader-rail'), holder=box('paper-reader-body');
  rail.setAttribute('role','tablist'); rail.setAttribute('aria-label','原件核对项目'); rail.setAttribute('aria-orientation','vertical');
  const mobile=el('select'); mobile.setAttribute('aria-label','选择原件核对项目');
  const chooser=box('paper-reader-mobile',glyph('layers'),mobile,glyph('chevron-down'));
  function select(i) {
    index.readerSection=available[i].key;
    mobile.selectedIndex=i;
    [...rail.children].forEach((button,n)=>{
      button.tabIndex=n===i?0:-1; button.setAttribute('aria-selected',String(n===i));
      holder.children[n].hidden=n!==i;
    });
  }
  available.forEach(({key,label,icon,content},i)=>{
    const option=el('option',label); option.value=key; mobile.append(option);
    const button=action('',()=>select(i),'paper-reader-tab');
    const pane=el('div','','paper-reader-pane');
    pane.id='reader-view-'+key; pane.setAttribute('role','tabpanel');
    button.id='reader-tab-'+key; button.setAttribute('role','tab');
    button.setAttribute('aria-controls',pane.id); pane.setAttribute('aria-labelledby',button.id);
    button.append(glyph(icon),el('span',label));
    button.addEventListener('keydown',event=>{
      const to={ArrowDown:(i+1)%available.length,ArrowUp:(i+available.length-1)%available.length,Home:0,End:available.length-1}[event.key];
      if (to!==undefined) {event.preventDefault();select(to);rail.children[to].focus();}
    });
    pane.addEventListener('reveal-evidence',()=>select(i));
    rail.append(button); pane.append(content); holder.append(pane);
  });
  mobile.addEventListener('change',()=>select(mobile.selectedIndex));
  reader.append(chooser,rail,holder);
  const remembered=available.findIndex(s=>s.key===index.readerSection);
  select(remembered>=0?remembered:Math.max(0,available.findIndex(s=>s.priority)));
  return reader;
}

function priorityQueue(items) {
  const queue=box('priority-findings findings-queue');
  const label=el('strong','优先核对');
  const destination=box('queue-destination'), position=el('output','','queue-position');
  let selected=0;
  const previous=action('‹',()=>show(selected-1),'queue-step'), next=action('›',()=>show(selected+1),'queue-step');
  previous.setAttribute('aria-label','上一条待核事项'); next.setAttribute('aria-label','下一条待核事项');
  function show(i) {
    selected=i;
    const finding=items[i], title=finding.stage ? finding.stage.name+' · '+finding.title : finding.title;
    if (finding.execution_basis) {
      const jump=PaymentProof.jump(finding,(finding.stage?finding.stage.name+' · ':'')+'核对扣款凭证');
      jump.classList.add('performance-jump');jump.append(tag(finding.status));destination.replaceChildren(jump);
    } else destination.replaceChildren(performanceJump(finding,title));
    position.value=(i+1)+' / '+items.length;
    position.setAttribute('aria-label','第 '+(i+1)+' 项，共 '+items.length+' 项');
    const focused=document.activeElement;
    previous.disabled=i===0; next.disabled=i===items.length-1;
    if (focused===previous && previous.disabled) next.focus();
    if (focused===next && next.disabled) previous.focus();
  }
  queue.append(label,destination);
  if (items.length>1) queue.append(box('queue-controls',previous,position,next));
  show(0);
  return queue;
}
