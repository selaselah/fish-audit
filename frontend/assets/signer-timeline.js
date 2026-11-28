// The public example and signed workpapers share the same calendar controls.
const SignerTimeline = (() => {
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }
  function original(source, label) {
    const button = element(source.url ? 'a' : 'button', 'signer-original', label);
    if (source.url) {
      button.href = source.url; button.target = '_blank'; button.rel = 'noopener';
    } else button.type = 'button';
    button.setAttribute('aria-haspopup','dialog');
    button.addEventListener('click', event => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (source.open(button) !== false) event.preventDefault();
    });
    return button;
  }
  function outcome(item) {
    if (item.state==='same_day') {
      if (item.clockState==='missing') {
        const bank=item.events.find(e=>e.kind==='payment');
        if (bank && !bank.at && item.events.some(e=>e.day===bank.day && e.at)) return '扣款时刻待核';
        return bank?.at?'签认时刻待核':'同日 · 时分待核';
      }
      const label={before:'扣款早于签认',after:'签认后扣款',overlap:'时刻重叠 · 先后待核',zone:'时区待核',unverified:'时刻证据待核'}[item.clockState];
      if (label) return label;
    }
    if (item.clockState==='conflict') return '时间记载有冲突';
    if (item.state === 'before') return '付款早 ' + Math.abs(item.days) + ' 天';
    if (item.state === 'after') return '付款晚 ' + item.days + ' 天';
    return {same_day:'同日 · 时分待核', incomplete:'签认日期待核', scope:'单据归属待核', unverified:'证据待核'}[item.state] || '时序待核';
  }
  function documentPreview(holder,source) {
    const quote=element('blockquote','signer-quote',source.quote);
    const meta=element('div','signer-meta'), documentLink=original(source,'查看原件');
    meta.append(element('span','signer-source-label',source.file),element('small','signer-location',source.place));
    const thumb=thumbnail(source);
    if (thumb) {documentLink.prepend(thumb);documentLink.classList.add('signer-document-link');}
    holder.append(meta,quote,documentLink);
    if (source.excerpt) source.excerpt().then(image=>{
      if (!image || !holder.contains(quote)) return;
      const strip=element('div','signer-strip');
      image.setAttribute('aria-hidden','true'); strip.append(image); quote.after(strip);
      quote.classList.add('signer-transcript');
    }).catch(()=>{ /* The printed transcript is available when the page image fails to load. */ });
  }
  function thumbnail(source) {
    if (!source.pageImage) return null;
    const frame=element('span','signer-thumbnail'), image=new Image();
    frame.setAttribute('aria-hidden','true');
    image.alt=''; image.loading='lazy'; image.decoding='async';
    image.addEventListener('error',()=>frame.remove(),{once:true});
    image.src=source.pageImage; frame.append(image);
    const rects=(source.rects || []).filter(r=>Array.isArray(r) && r.length===4 &&
      r.every(n=>Number.isFinite(n) && n>=0 && n<=1) && r[2]>r[0] && r[3]>r[1]);
    for (const [x,y,right,bottom] of rects) {
      const mark=element('i','signer-thumbnail-mark');
      mark.style.left=x*100+'%'; mark.style.top=y*100+'%';
      mark.style.width=(right-x)*100+'%'; mark.style.height=(bottom-y)*100+'%'; frame.append(mark);
    }
    return frame;
  }
  function render(items, id) {
    const card = element('section','signer-timeline');
    card.id = id; card.tabIndex = -1;
    const heading = element('div','signer-head');
    const title = element('h3','', '共同签认与付款');
    title.id = id + '-title'; card.setAttribute('aria-labelledby',title.id);
    const status = element('span','signer-outcome'); status.setAttribute('role','status');
    heading.append(title,status);
    const picker = items.length > 1 ? element('select','signer-payment-picker') : null;
    if (picker) {
      picker.setAttribute('aria-label','选择付款回单');
      items.forEach(item => picker.add(new Option(item.choice,item.key)));
    }
    const body = element('div','signer-body');
    const schedule = element('div','signer-schedule'), preview = element('div','signer-preview');
    const stage = element('div','signer-stage'), list = element('div','signer-events');
    list.setAttribute('role','group'); list.setAttribute('aria-label','选择时序原件');
    preview.setAttribute('aria-live','polite');
    const basis = element('div','signer-basis');
    const tabs=element('div','signer-view-switch'), paired=element('div','signer-paired');
    tabs.hidden=true; paired.hidden=true;
    tabs.setAttribute('role','group'); tabs.setAttribute('aria-label','签认与付款视图');
    body.id=id+'-events'; paired.id=id+'-originals';
    const timelineButton=element('button','','时序'), pairButton=element('button','','原行对照');
    for (const [button,target] of [[timelineButton,body],[pairButton,paired]]) {
      button.type='button'; button.setAttribute('aria-controls',target.id); tabs.append(button);
    }
    let pairTitle;
    function showPair(active) {
      body.hidden=active; paired.hidden=!active;
      title.textContent=active?pairTitle:'共同签认与付款';
      pairButton.setAttribute('aria-pressed',String(active)); timelineButton.setAttribute('aria-pressed',String(!active));
    }
    timelineButton.addEventListener('click',()=>showPair(false));
    pairButton.addEventListener('click',()=>showPair(true));
    schedule.append(stage,list); body.append(schedule,preview);
    card.append(heading); if (picker) card.append(picker); card.append(tabs,body,paired,basis);
    function choose(item) {
      if (!item) return;
      if (picker) picker.value = item.key;
      card.dataset.findingKey = item.key; card.dataset.state = item.state;
      if (item.clockState) card.dataset.clockState=item.clockState; else delete card.dataset.clockState;
      if (item.stageRef) card.dataset.clause = item.stageRef;
      status.textContent = outcome(item);
      const first=item.pair?.[0], sameDate=first?.day && item.pair.every(e=>e.day===first.day);
      pairTitle=[sameDate?first.day.replaceAll('-','/'):'原件时刻',item.pair?.every(e=>e.zone==='+08:00')?'北京时间':''].filter(Boolean).join(' · ');
      tabs.hidden=!item.pair; showPair(false); paired.replaceChildren();
      if (item.pair) {
        for (const event of item.pair) {
          const side=element('section','signer-pair-side');
          const head=element('header','signer-pair-head'), time=element('time','signer-pair-time',event.at);
          time.dateTime=event.day?event.day+'T'+event.at+(event.zone || ''):event.at;
          head.append(element('h4','',event.label),time);
          const doc=element('div','signer-preview');
          documentPreview(doc,event.source);
          side.append(head,doc); paired.append(side);
        }
      }
      const year = [...new Set(item.events.filter(e => e.day).map(e => e.day.slice(0,4)))];
      stage.textContent = [item.stage,year.length === 1 ? year[0] + ' 年' : null].filter(Boolean).join(' · ');
      const ordered=['before','after'].includes(item.clockState);
      const events = [...item.events].sort((a,b) => (a.day || '9999').localeCompare(b.day || '9999') ||
        (ordered && a.at && b.at?a.at.localeCompare(b.at):0));
      const controls = [];
      list.replaceChildren();
      function select(index,chosen=false) {
        const event = events[index];
        controls.forEach((button,i) => {
          button.setAttribute('aria-pressed',String(i===index));
          button.toggleAttribute('data-walk-selected',chosen && i===index && Boolean(button.dataset.timingRef));
        });
        preview.replaceChildren();
        const source = event.source;
        if (source) {
          documentPreview(preview,source);
        } else {
          const bank=event.kind==='payment';
          preview.append(element('span','signer-source-label',event.label),
            element('strong','signer-pending',bank?'回单日期待核':'签认日期待核'),
            element('small','signer-location',bank?'需核对本笔付款的原回单。':'需取得可定位的具名日期原行。'));
        }
        if (event.daySource) preview.append(original(event.daySource,'查看日期栏'));
        if (event.signature) preview.append(original(event.signature,'查看签字栏'));
      }
      const dayGroups=new Map();
      for (const [i,event] of events.entries()) {
        const button = element('button','signer-event'); button.type = 'button';
        const row=/^(signer-date|joint-clock)\/(d\d+)\/p(\d+)\/l(\d+)$/.exec(event.source?.ref || '');
        if (id==='signer-timing' && row && event.source.rects?.length) {
          button.id='timing-'+item.key+'-'+row[1]+'-'+row[2]+'-p'+row[3]+'-l'+row[4];
          button.dataset.timingRef=event.source.ref;
          button.dataset.originalLabel=event.source.file+' · '+event.source.place+' · '+event.source.quote;
        }
        button.dataset.kind = event.kind;
        const stamp = element(event.day?'time':'span','signer-stamp',event.day?(year.length===1?event.day.slice(5):event.day).replaceAll('-','/'):'待核');
        if (event.day) stamp.dateTime = event.day;
        const pin = element('span','signer-pin'); pin.setAttribute('aria-hidden','true');
        button.append(stamp,pin,element('span','signer-event-name',event.label));
        if (event.at) {
          const at=element('time','signer-clock',event.at);
          at.dateTime=event.day?event.day+'T'+event.at+(event.zone || ''):event.at;
          button.append(at);
        }
        button.addEventListener('click',()=>select(i,true));
        button.addEventListener('keydown',e=>{
          const next = {ArrowDown:i+1,ArrowUp:i-1,Home:0,End:events.length-1}[e.key];
          if (next==null) return;
          e.preventDefault();
          const j=Math.max(0,Math.min(next,events.length-1)); controls[j].focus(); select(j,true);
        });
        controls.push(button);
        const groupKey=event.day || '';
        if (!event.day || events.filter(e=>e.day===event.day).length>1) {
          if (!dayGroups.has(groupKey)) {
            const group=element('div','signer-day-group');
            const clocks=events.filter(e=>e.day===event.day && e.at);
            const zone=clocks.length && clocks.every(e=>e.zone==='+08:00')?' · 北京时间':'';
            const label=event.day ? stamp.textContent+' · 同日记录'+zone : '日期待核';
            group.setAttribute('role','group'); group.setAttribute('aria-label',label);
            group.append(element('span','signer-group-label',label)); list.append(group); dayGroups.set(groupKey,group);
          }
          dayGroups.get(groupKey).append(button);
        } else list.append(button);
      }
      basis.replaceChildren();
      for (const [source,label] of [[item.clause,'共同签认约定'],[item.term,'本期付款条款']]) {
        if (source) basis.append(original(source,label));
      }
      for (const group of item.joined || []) {
        const details=element('details','signer-candidates');
        details.append(element('summary','','模型合并抄录 · '+group.sources.length+' 行'),element('blockquote','signer-quote',group.quote));
        for (const source of group.sources) details.append(original(source,source.quote));
        basis.append(details);
      }
      if (item.candidates?.length) {
        const details=element('details','signer-candidates');
        details.append(element('summary','','待核原行 · '+item.candidates.length));
        for (const s of item.candidates) details.append(original(s,s.quote));
        basis.append(details);
      }
      basis.hidden = !basis.childElementCount;
      const initial = item.state === 'incomplete' ? events.findIndex(e=>!e.day) : -1;
      select(initial >= 0 ? initial : Math.max(0,events.findIndex(e=>e.kind==='payment')));
      card.dispatchEvent(new CustomEvent('signer-payment-changed',{detail:item.key}));
    }
    picker?.addEventListener('change',()=>choose(items.find(i=>i.key===picker.value)));
    card.addEventListener('select-signer-payment',event=>choose(items.find(i=>i.key===event.detail)));
    choose(items.find(i=>i.state==='before' || i.clockState==='before') || items[0]);
    return card;
  }
  return {render};
})();
