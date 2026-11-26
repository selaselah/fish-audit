// One calendar scale for the guarantee as printed and the payment as recorded by the bank.
const GuaranteePeriodCard = (() => {
  const labels={expired:'付款晚于止日',before_start:'付款早于起日',covered:'付款日在载明期间内',
    end_unspecified:'止日是否含当日待核',extension_review:'展期凭证待核',stated:'原函载明期间',review:'期间依据待核'};
  const dayMs=86_400_000;
  function iso(text) {
    const match=/^(\d{4})(?:年(\d{1,2})月(\d{1,2})日|-(\d{1,2})-(\d{1,2}))$/u.exec(text);
    if (!match || match[1]==='0000') return null;
    const y=match[1],m=match[2] || match[4],d=match[3] || match[5];
    const date=y+'-'+m.padStart(2,'0')+'-'+d.padStart(2,'0');
    const time=Date.parse(date+'T00:00:00Z');
    return Number.isFinite(time) && new Date(time).toISOString().slice(0,10)===date?date:null;
  }
  function element(tag,cls,value) {
    const node=document.createElement(tag);
    if (cls) node.className=cls;
    if (value) node.textContent=value;
    return node;
  }
  function describe(model) {
    const {state,start,end,paid}=model;
    if (state==='expired' || state==='before_start') {
      const bound=state==='expired'?end:start;
      const days=Math.round(Math.abs(Date.parse(paid)-Date.parse(bound))/dayMs);
      return {label:labels[state]+(Number.isFinite(days)?' '+days+' 天':''),tone:'risk'};
    }
    return {label:labels[state] || labels.review,tone:['covered','stated'].includes(state)?'documented':'review'};
  }
  const eventNames={start:'原函起日',end:'原函止日',paid:'银行付款'};
  function byDate(model) {
    const groups=new Map();
    for (const kind of Object.keys(eventNames)) {
      const day=model[kind];
      if (!iso(day) || !model.rows[kind]?.length) continue;
      if (!groups.has(day)) groups.set(day,[]);
      groups.get(day).push(kind);
    }
    return [...groups].sort(([a],[b])=>a.localeCompare(b));
  }
  function axis(model,days) {
    const frame=element('div','period-axis');
    frame.setAttribute('aria-hidden','true');
    const first=Date.parse(days[0][0]), last=Date.parse(days[days.length-1][0]);
    const position=day=>first===last?50:(Date.parse(day)-first)/(last-first)*100;
    const lanes=element('div','period-lanes'), captions=element('div','period-lane-labels');
    const bar=element('div','period-track'), payment=element('div','period-track');
    captions.append(element('span','','原函'),...(model.paid?[element('span','','付款')]:[]));
    if (model.start && model.end && model.start<=model.end) {
      const band=element('i','period-band');
      band.style.left=position(model.start)+'%';
      band.style.width=position(model.end)-position(model.start)+'%';
      bar.append(band);
    }
    for (const [day,kinds] of days) {
      for (const kind of kinds) {
        const marker=element('i','period-mark');
        marker.dataset.event=kind; marker.dataset.day=day; marker.style.left=position(day)+'%';
        if (kind==='end' && model.inclusive!==true) marker.dataset.boundary='open-question';
        (kind==='paid'?payment:bar).append(marker);
      }
    }
    const scale=element('div','period-scale');
    const sameYear=days[0][0].slice(0,4)===days.at(-1)[0].slice(0,4);
    for (const day of new Set([days[0][0],days.at(-1)[0]])) {
      const time=element('time','',(sameYear?day.slice(5):day).replaceAll('-','.')); time.dateTime=day; scale.append(time);
    }
    lanes.append(bar,...(model.paid?[payment]:[])); frame.append(scale,captions,lanes);
    return frame;
  }
  // sourceControl renders a button for a private report, or a watermarked PDF link for a public example.
  function render(model,key,sourceControl) {
    const card=element('div','period-card'), days=byDate(model);
    card.dataset.periodState=model.state;
    const selected=element('div','period-selected');
    selected.id=key+'-sources';
    if (days.length) {
      const rail=axis(model,days), tabs=element('div','period-days');
      tabs.setAttribute('role','tablist'); tabs.setAttribute('aria-label','选择保函或付款日期');
      const sameYear=days.every(([day])=>day.slice(0,4)===days[0][0].slice(0,4));
      rail.prepend(element('span','period-year',sameYear?days[0][0].slice(0,4)+' 年':'日期'));
      selected.setAttribute('role','tabpanel');
      function select(i) {
        const [day,kinds]=days[i], tab=tabs.children[i];
        for (const button of tabs.children) {
          const active=button===tab;
          button.tabIndex=active?0:-1; button.setAttribute('aria-selected',String(active));
        }
        for (const marker of rail.querySelectorAll('.period-mark')) marker.dataset.selected=String(marker.dataset.day===day);
        selected.setAttribute('aria-labelledby',tab.id);
        selected.replaceChildren(...kinds.flatMap(kind=>model.rows[kind].map(row=>sourceControl(row,
          kind==='end' && model.inclusive===true?'原函止日 · 含当日':eventNames[kind]))));
        card.dispatchEvent(new Event('guarantee-day-change',{bubbles:true}));
      }
      for (const [i,[day,kinds]] of days.entries()) {
        const tab=element('button','period-day'); tab.type='button'; tab.id=key+'-day-'+day; tab.dataset.day=day;
        tab.setAttribute('role','tab'); tab.setAttribute('aria-controls',selected.id);
        const [year,month,dayNumber]=day.split('-');
        tab.setAttribute('aria-description',year+'年'+Number(month)+'月'+Number(dayNumber)+'日，'+kinds.map(kind=>eventNames[kind]).join('、'));
        const time=element('time','', (sameYear?day.slice(5):day).replaceAll('-','.')); time.dateTime=day;
        tab.append(time,element('span','',kinds.map(kind=>({start:'起日',end:'止日',paid:'付款'})[kind]).join(' · ')));
        tab.addEventListener('click',()=>select(i));
        tab.addEventListener('keydown',event=>{
          const n=days.length, target={ArrowLeft:(i+n-1)%n,ArrowRight:(i+1)%n,Home:0,End:n-1}[event.key];
          if (target===undefined) return;
          event.preventDefault(); select(target); tabs.children[target].focus();
        });
        tabs.append(tab);
      }
      rail.addEventListener('click',event=>{
        const marker=event.target.closest('.period-mark');
        if (!marker) return;
        const i=days.findIndex(([day])=>day===marker.dataset.day);
        select(i); tabs.children[i].focus({preventScroll:true});
      });
      const preferred=days.findIndex(([day])=>day===(model.paid || model.end));
      select(Math.max(0,preferred)); card.append(rail,tabs);
    }
    card.append(selected);
    if (!days.length) card.append(element('p','period-hold','日期与本期的对应关系待核。'));
    const exceptions=model.rows.extension || [];
    for (const row of exceptions) card.append(sourceControl(row,'展期或补充依据'));
    const others=model.rows.unknown || [];
    const more=element('details','period-basis'), list=element('div','period-references');
    for (const row of model.rows.clause || []) list.append(sourceControl(row,'合同对首期保函的约定'));
    for (const row of model.rows.related || []) list.append(sourceControl(row,row.label));
    for (const row of others) list.append(sourceControl(row,'待核原件'));
    if (list.childElementCount) {
      more.append(element('summary','','核对合同与原件'),list); card.append(more);
    }
    return card;
  }
  return {iso,describe,render};
})();
