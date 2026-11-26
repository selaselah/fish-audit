// One published purchase, with two distinct issued workpapers over the same four source files.
const PublicBatchStandards = (() => {
  const slot=document.getElementById('inspection-standards');
  const indexPath='/assets/batch-standard-versions.json';
  const states={ok:'相符',missing:'证据不足',risk:'风险',issue:'问题'};
  const events=['1','change','2'];
  let view, loading=false;

  function element(tag,text='',className='') {
    const node=document.createElement(tag);
    if (className) node.className=className;
    node.textContent=text;
    return node;
  }
  function icon(name) {
    const mark=element('i','','ui-glyph ic-'+name);
    mark.setAttribute('aria-hidden','true');
    return mark;
  }
  function sourceLink(source,label,className) {
    const {doc,line}=source, anchor=element('a','',className);
    anchor.href=doc.pdf; anchor.target='_blank'; anchor.rel='noopener'; anchor.dataset.fact=line.ref;
    anchor.setAttribute('aria-description',label+'，'+doc.title+'第 '+doc.page+' 页第 '+line.line+' 行，'+line.quote);
    anchor.setAttribute('aria-haspopup','dialog'); anchor.setAttribute('aria-controls','sample-review');
    anchor.addEventListener('click',event=>{
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const documentVersion={...doc,version:'合成采购 · R'+view.version()};
      const open=new CustomEvent('inspect-sample-line',{cancelable:true,detail:{doc:documentVersion,ref:line.ref,opener:anchor}});
      if (!document.dispatchEvent(open)) event.preventDefault();
    });
    return anchor;
  }
  function temperature(source,limit) {
    const text=source.line.value.normalize('NFKC');
    const match=(limit?/^柜温不高于(-?\d+(?:\.\d+)?)°C$/u:/^柜温(-?\d+(?:\.\d+)?)°C$/u).exec(text);
    if (!match) throw new Error('Unrecognized temperature in the published sample');
    return {value:Number(match[1]),label:(limit?'≤ ':'')+match[1],source};
  }
  function dateOf(source) {
    const match=/^(\d{4})年(\d{1,2})月(\d{1,2})日$/u.exec(source.line.value);
    if (!match) throw new Error('Unrecognized date in the published sample');
    return [match[1],match[2].padStart(2,'0'),match[3].padStart(2,'0')].join('-');
  }
  function status(text,state) {
    const mark=element('span',text,'standard-status');
    mark.dataset.status=state;
    return mark;
  }
  function rowLink(title,source,value=source.line.value) {
    const a=sourceLink(source,title,'standard-source-row');
    a.append(element('span',title),element('strong',value),icon('arrows-angle-expand'));
    return a;
  }
  function readingPlot(original,revised,measured,applied) {
    const axis=element('div','','standard-axis');
    axis.setAttribute('role','group'); axis.setAttribute('aria-label','柜温实测和两份原件所列上限，单位为摄氏度');
    const low=Math.min(original.value,revised.value,measured.value);
    const high=Math.max(original.value,revised.value,measured.value);
    for (const [key,title,point] of [['original','原合同',original],['applied','补充协议',revised],['reading','本批实测',measured]]) {
      const a=sourceLink(point.source,title,'standard-tick');
      a.dataset.kind=key;
      a.classList.toggle('chosen-limit',key===applied);
      const position=high===low?50:19+62*(point.value-low)/(high-low);
      a.style.setProperty('--at',position+'%');
      const digits=element('strong',point.label);
      digits.append(element('small',' °C'));
      a.append(element('span',title),digits);
      axis.append(a);
    }
    return axis;
  }
  function reportBasis(source) {
    const a=sourceLink(source,'核对报告采用的检验依据','standard-printed');
    const title=element('span','','standard-printed-label');
    title.append(icon('file-earmark-text'),element('span','报告填写'));
    const quote=element('strong',source.line.quote,'standard-printed-quote');
    a.append(title,quote,icon('arrows-angle-expand'));
    if (source.line.crop) {
      const image=new Image();
      image.alt=source.line.quote;
      image.onload=()=>quote.replaceChildren(image);
      image.src=source.line.crop;
    }
    return a;
  }
  function build(sample) {
    const lines=new Map(sample.docs.flatMap(doc=>doc.lines.map(line=>[line.ref,{doc,line}])));
    function source(ref,field,unit) {
      const item=lines.get(typeof ref==='string'?ref:ref.ref);
      if (!item || item.line.field!==field || unit && item.doc.id!==unit ||
          typeof ref==='object' && item.line.value!==ref.value) throw new Error('Published source mismatch');
      return item;
    }
    const editions=new Map(sample.editions.map(e=>[String(e.rev),e]));
    const batches=new Map(sample.batches.map(b=>[String(b.index),b]));
    const change=sample.change;
    const original=temperature(source(change.original_ref,'acceptance_criteria'),true);
    const revised=temperature(source(change.revised_criterion,'revised_criterion'),true);
    const earlier=source(change.previous_criterion,'previous_criterion');
    const buyerDate=source(change.buyer_sealed_on,'buyer_sealed_on'), sellerDate=source(change.seller_sealed_on,'seller_sealed_on');
    const latest=String(sample.default_rev), params=new URLSearchParams(location.search);
    const requested=params.get('scene')==='batch-standards';
    let edition=editions.get(requested?params.get('edition'):null) || editions.get(latest);
    let current=requested && events.includes(params.get('batch'))?params.get('batch'):'2';
    const heading=element('div','','standard-heading');
    const select=element('select');
    select.id='standard-edition'; select.setAttribute('aria-label','对照合成底稿版本');
    for (const [id] of editions) select.add(new Option('合成 R'+id+' · '+(id===latest?'重审':'历史'),id));
    select.value=String(edition.rev);
    const readings=sample.batches.map(b=>temperature(source(b.measured_result,'measured_result',b.unit),false));
    const title=readings.length===2 && readings[0].value===readings[1].value?
      '两批柜温均为 '+readings[0].label+' °C':'分批柜温与约定上限';
    heading.append(element('h3',title),select);
    const tabs=element('div','','standard-events');
    tabs.setAttribute('role','tablist'); tabs.setAttribute('aria-label','核对批次或协议');
    const panel=element('div','','standard-body'); panel.id='standard-event-body'; panel.setAttribute('role','tabpanel');
    const announce=element('span','','sr-only'); announce.setAttribute('role','status');

    function decision(text,state,detail) {
      const button=element('button','','standard-decision'), badge=status(text,state);
      button.type='button'; badge.append(icon('chevron-down')); button.append(badge);
      button.setAttribute('aria-expanded','false'); button.setAttribute('aria-controls','standard-decision-detail');
      const reason=element('div','','standard-reason'), meta=element('div','','standard-method');
      const record=element('a','下载版本索引');
      record.href=indexPath; record.download='batch-standard-versions.json';
      meta.append(element('small','规则 '+edition.rule_version),record);
      reason.append(element('p',detail),meta);
      reason.id='standard-decision-detail'; reason.hidden=true;
      button.addEventListener('click',()=>{
        reason.hidden=!reason.hidden; button.setAttribute('aria-expanded',String(!reason.hidden));
      });
      return {button,reason};
    }
    function renderBatch(key) {
      const batch=batches.get(key), issued=edition.batches.find(r=>r.index===batch.index);
      const {standard,stage}=issued;
      const measured=temperature(source(batch.measured_result,'measured_result',batch.unit),false);
      const basis=source(batch.inspection_basis,'inspection_basis',batch.unit);
      const chosen={original:original.source.line.ref,applied:revised.source.line.ref,pending:null};
      if (chosen[standard.state]!==standard.criterion_ref || standard.reading_ref!==measured.source.line.ref ||
          standard.date_ref!==batch.accepted_on.ref || !states[stage.status]) throw new Error('Published edition mismatch');
      const summary=element('div','','standard-caption');
      const dateLink=sourceLink(source(batch.accepted_on,'accepted_on',batch.unit),'核对'+batch.label+'验收日期','standard-date');
      dateLink.append(element('strong','核对验收日期'),icon('arrows-angle-expand'));
      const stateButton=decision({original:'本版采用原合同',applied:'本版采用补充协议',pending:'适用标准待核'}[standard.state],
        standard.state==='pending'?'missing':'source',standard.state==='pending'?edition.quality_change.detail:issued.detail);
      summary.append(dateLink,stateButton.button);
      const footer=element('div','','standard-installment');
      const contract=source(stage.clause_ref,'payment_stage',original.source.doc.id);
      const jump=sourceLink(contract,'查看本期付款条款','standard-stage');
      jump.append(icon('receipt'),element('strong',stage.name+' · '+stage.share+'%'),icon('arrows-angle-expand'));
      footer.append(jump,status('付款条件 · '+states[stage.status],stage.status));
      return [summary,stateButton.reason,readingPlot(original,revised,measured,standard.state),reportBasis(basis),footer];
    }
    function renderAgreement() {
      const evidence=edition.quality_change;
      const summary=element('div','','standard-caption');
      const stateButton=decision(evidence.effective_on?'本版生效日 '+evidence.effective_on:'生效日期待核',
        evidence.effective_on?'source':'missing',evidence.detail);
      summary.append(element('strong','验收上限变更'),stateButton.button);
      const limits=element('div','','standard-amendment');
      for (const [title,value] of [['协议所列原上限',temperature(earlier,true)],['变更后上限',revised]]) {
        const link=sourceLink(value.source,title,'standard-limit');
        const digits=element('strong',value.label); digits.append(element('small',' °C'));
        link.append(element('span',title),digits,icon('arrows-angle-expand')); limits.append(link);
      }
      const scope=rowLink('适用约定',source(change.change_timing,'change_timing'));
      const more=element('details','','standard-details');
      more.append(element('summary','生效条款与双方盖章栏'),rowLink('生效条款',source(change.change_effect_clause,'change_effect_clause')),
        rowLink('甲方盖章栏',buyerDate),rowLink('乙方盖章栏',sellerDate));
      return [summary,stateButton.reason,limits,scope,more];
    }
    function address(url) {
      url.searchParams.set('edition',String(edition.rev));
      url.searchParams.set('batch',current);
    }
    function draw(updateURL=false) {
      const tab=tabs.querySelector('[data-event="'+current+'"]');
      for (const item of tabs.children) {
        const active=item===tab;
        item.setAttribute('aria-selected',String(active)); item.tabIndex=active?0:-1;
      }
      panel.setAttribute('aria-labelledby',tab.id); panel.dataset.event=current; panel.dataset.edition=edition.rev;
      panel.replaceChildren(...(current==='change'?renderAgreement():renderBatch(current)));
      if (updateURL) {
        const url=new URL(location.href); url.searchParams.set('scene','batch-standards'); address(url); url.hash='workflow';
        history.replaceState(history.state,'',url);
        announce.textContent='R'+edition.rev+'，'+tab.querySelector('span').textContent+'，'+panel.querySelector('.standard-decision').textContent;
      }
    }
    for (const [index,key] of events.entries()) {
      const batch=batches.get(key);
      const day=dateOf(batch?source(batch.accepted_on,'accepted_on',batch.unit):sellerDate);
      const name=batch?batch.label+'验收':'乙方落款';
      const tab=element('button'); tab.type='button'; tab.dataset.event=key; tab.id='standard-event-'+key;
      tab.setAttribute('role','tab'); tab.setAttribute('aria-controls',panel.id);
      tab.setAttribute('aria-description',(batch?name:'补充协议乙方盖章栏')+'，'+day);
      const time=element('time',day.slice(5).replace('-','.')); time.dateTime=day;
      tab.append(time,element('span',name));
      tab.addEventListener('click',()=>{current=key; draw(true);});
      tab.addEventListener('keydown',event=>{
        const next={ArrowLeft:(index+2)%3,ArrowRight:(index+1)%3,Home:0,End:2}[event.key];
        if (next===undefined) return;
        event.preventDefault(); current=events[next]; draw(true); tabs.children[next].focus();
      });
      tabs.append(tab);
    }
    select.addEventListener('change',()=>{edition=editions.get(select.value); draw(true);});
    draw();
    slot.replaceChildren(heading,tabs,panel,announce);
    if (requested && !slot.hidden && !slot.closest('[role="tabpanel"]').hidden) {
      const url=new URL(location.href);
      address(url); history.replaceState(history.state,'',url);
    }
    return {address,version:()=>edition.rev};
  }
  async function open() {
    if (view || loading) return;
    loading=true; slot.setAttribute('aria-busy','true');
    const retry=slot.querySelector('.standard-retry'), restoreFocus=retry && document.activeElement===retry;
    try {
      const response=await fetch(indexPath,{integrity:slot.dataset.integrity});
      if (!response.ok) throw new Error('Sample unavailable');
      view=build(await response.json());
      if (restoreFocus && !slot.hidden) slot.querySelector('select').focus({preventScroll:true});
    } catch {
      if (!slot.querySelector('button')) {
        const retry=element('button','重新载入对照','standard-retry'); retry.type='button';
        const notice=element('span','底稿对照暂未载入','standard-load-status'); notice.setAttribute('role','status');
        retry.addEventListener('click',open); slot.querySelector('.public-standard-fallback').append(notice,retry);
      }
    } finally { loading=false; slot.setAttribute('aria-busy','false'); }
  }
  return {open,address:url=>view?.address(url)};
})();
