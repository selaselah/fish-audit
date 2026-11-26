// Show the dates and original lines used by this revision of the warranty check.
const WarrantyTimeline = (() => {
  const dayMs=86400000;
  const plain=value=>String(value ?? '').normalize('NFKC').trim();
  function day(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/u.test(value || '')) return null;
    const n=Date.parse(value+'T00:00:00Z');
    return Number.isFinite(n) && new Date(n).toISOString().slice(0,10)===value ? n/dayMs : null;
  }
  function panel(phase,payments,graph) {
    const entry=phase.warranty_check, snapshot=entry?.at_submission;
    if (!['contract-warranty-release-v2','contract-warranty-release-v3','contract-warranty-release-v4','contract-warranty-release-v5'].includes(graph.warranty_sources?.format) || !snapshot ||
        snapshot.as_of!==graph.warranty_as_of || day(snapshot.as_of)===null) return null;
    const cutoff=day(snapshot.as_of);
    const index=graphIndex(graph), ledger=graph.warranty_sources;
    function source(finding,id,field,kinds,role) {
      const f=index.facts.get(id), line=f?.source_line;
      if (!line?.rects?.length || !['anchored','confirmed'].includes(f.status) || !finding.evidence.includes(id) ||
          !index.supports.get('finding/'+finding.id)?.has(id) || !kinds.some(k=>graph.documents_by_kind[k]?.includes(f.unit || f.doc)) ||
          !finding.scope.includes(f.unit || f.doc) || plain(f.quote)!==plain(line.text) || f.field!==field) return null;
      const raw=plain(line.text), sep=raw.indexOf(':');
      if (sep<1 || ![raw,raw.slice(sep+1).trim()].includes(plain(f.value))) return null;
      if (role && !ledger.lines.some(s=>s.kind===role && s.unit===(f.unit || f.doc) && s.doc===f.doc && s.page===f.page &&
          s.line===line.number && s.quote===line.text && s.facts.includes(id))) return null;
      return f;
    }
    const starts=snapshot.start_refs.map(id=>source(phase,id,'accepted_on',['acceptance','reinspection']))
      .filter(f=>f && PhaseEvidence.dateOn(f)===entry.accepted_on);
    const term=source(phase,entry.term_ref,'warranty_period',['contract'],'warranty_period');
    const confirmation=source(phase,entry.confirmation_ref,'warranty_release',['warranty'],'warranty_release');
    const defect=source(phase,entry.defect_ref,'warranty_defects',['warranty'],'warranty_defects');
    const inline=entry.condition_ref===phase.stage.clause_ref;
    const condition=source(phase,entry.condition_ref,inline?'payment_stage':'warranty_condition',['contract'],inline?'inline_condition':'warranty_condition');
    const startDate=starts.length ? entry.accepted_on : null;
    const endDate=term && (entry.period?.fixed || startDate) ? entry.calendar_end : null;
    const certificateDate=confirmation && PhaseEvidence.dateOn(confirmation)===entry.confirmed_on ? entry.confirmed_on : null;
    const selectedSources=(items,label)=>items.map(f=>[label,f]);
    const rows=[
      {key:'start',label:'终验 / 复验',value:startDate,refs:selectedSources(starts,'起算原件')},
      {key:'end',label:'推算末日',value:endDate,refs:[...selectedSources(entry.period?.fixed?[]:starts,'起算原件'),['期限条款',term]]},
      {key:'confirmation',label:'期满确认',value:certificateDate,refs:[['确认原件',confirmation]]}
    ];
    for (const payment of payments) {
      const record=payment.warranty_payment;
      if (!record || payment.warranty_check?.at_submission?.as_of!==snapshot.as_of) continue;
      const refs=record.date_refs.map(id=>source(payment,id,'paid_on',['bank_receipt'])).filter(f=>f && PhaseEvidence.dateOn(f)===record.paid_on);
      rows.push({key:payment.id,label:payments.length>1?'回单 '+(rows.length-2):'回单落款',value:refs.length?record.paid_on:null,
        refs:selectedSources(refs,'付款回单'),payment});
    }
    for (const item of rows) {
      item.when=day(item.value);
      item.refs=item.refs.filter(([,f])=>f);
    }
    const bankRows=rows.filter(r=>r.payment), futureBank=bankRows.find(r=>r.when!==null && r.when>cutoff);
    const [start,end,cert]=rows;
    const early=bankRows.find(r=>r.when!==null && cert.when!==null && r.when<cert.when);
    const shared=bankRows.find(r=>r.when!==null && r.when===cert.when);
    let focus=end, title='质保依据待核';
    if (start.when!==null && start.when>cutoff) { focus=start; title='终验日期晚于提交 '+(start.when-cutoff)+' 天'; }
    else if (end.when!==null && end.when>cutoff) title='距质保末日还有 '+(end.when-cutoff)+' 天';
    else if (cert.when!==null && cert.when>cutoff) { focus=cert; title='期满确认晚于提交 '+(cert.when-cutoff)+' 天'; }
    else if (futureBank) { focus=futureBank; title='回单晚于提交 '+(focus.when-cutoff)+' 天'; }
    else if (defect && snapshot.defects==='listed_open') { focus=cert; title='确认单仍列有未结缺陷'; }
    else if (early) { focus=early; title='回单早于期满确认 '+(cert.when-early.when)+' 天'; }
    else if (shared) { focus=shared; title='确认与付款同日'; }
    else if (cert.when!==null && end.when!==null && cert.when<end.when) { focus=cert; title='确认早于质保末日 '+(end.when-cert.when)+' 天'; }
    else if (cert.when!==null && cert.when===end.when) { focus=cert; title='确认与质保末日同日'; }
    else if (entry.status==='ok' && cert.when!==null) { focus=cert; title='已取得期满确认'; }

    const root=el('section','','warranty-timeline');
    root.setAttribute('aria-label','质保时点');
    const stamp=el('time',snapshot.as_of.replaceAll('-','.')); stamp.dateTime=snapshot.as_of;
    const stampLabel=box('warranty-cutoff',el('i'),el('span','提交日'),stamp);
    stampLabel.firstChild.setAttribute('aria-hidden','true');
    root.append(box('warranty-heading',el('h4',title),stampLabel));
    const plot=box('warranty-plot'), choice=box('warranty-tracks');
    choice.setAttribute('role','radiogroup'); choice.setAttribute('aria-label','选择时点核对原件');
    const guide=el('span','','warranty-axis');
    const bounds=box('warranty-axis-dates');
    guide.append(bounds);
    const zoom=box('warranty-zoom');
    zoom.setAttribute('role','group'); zoom.setAttribute('aria-label','时轴范围');
    const axis=box('warranty-axis-row',el('span'),guide,zoom);
    plot.append(choice,axis); root.append(plot);
    const detail=box('warranty-selected');
    detail.setAttribute('role','region'); detail.setAttribute('aria-label','所选时点的依据');
    function preview() {
      if (!root.getClientRects().length) return;
      for (const ink of detail.querySelectorAll('.warranty-ink[data-preview="idle"]')) {
        ink.dataset.preview='loading';
        EvidenceCompare.lineExcerpt(index.facts.get(ink.parentElement.dataset.source),index).then(canvas=>{
          if (!canvas || !ink.isConnected) return;
          ink.append(canvas); ink.dataset.preview='image';
        }).catch(()=>{ ink.dataset.preview='text'; });
      }
    }
    root.addEventListener('show-warranty',()=>requestAnimationFrame(preview));
    if (defect || condition || entry.requires_defect_clearance) {
      const strip=box('warranty-defects',glyph('shield-check'),el('span','确认单'));
      strip.dataset.record=defect?snapshot.defects:'unverified';
      const labels={listed_open:'列有未结缺陷',stated_clear:'载明无未结缺陷',unverified:'缺陷记录待核'};
      if (defect) {
        const btn=action(labels[snapshot.defects],()=>openPage(defect.doc,defect.page,defect.id),'warranty-defect-source');
        btn.dataset.source=defect.id; btn.append(glyph('arrows-angle-expand')); strip.append(btn);
      } else strip.append(el('strong',labels.unverified));
      if (condition) {
        const btn=action('返还条件',()=>openPage(condition.doc,condition.page,condition.id),'warranty-condition');
        btn.dataset.source=condition.id; strip.append(btn);
      }
      root.append(detail,strip);
    } else root.append(detail);
    const points=[cutoff,...rows.map(r=>r.when).filter(n=>n!==null)];
    const low=Math.min(...points), high=Math.max(...points);
    let near=Boolean(low<cutoff-7 || high>cutoff+7) && (futureBank || (end.when!==null && end.when>cutoff));
    function scale(close) {
      near=Boolean(close);
      root.dataset.scale=near?'week':'all';
      const min=near?cutoff-7:low-1, max=near?cutoff+7:high+1;
      const percent=n=>(3+94*Math.max(0,Math.min(1,(n-min)/(max-min))))+'%';
      root.style.setProperty('--cut-at',percent(cutoff));
      bounds.replaceChildren(...[min,max].map(n=>{
        const t=new Date(n*dayMs).toISOString().slice(0,10);
        const label=el('time',(t.startsWith(snapshot.as_of.slice(0,4))?t.slice(5):t).replaceAll('-','.'));
        label.dateTime=t; return label;
      }));
      for (const item of rows) {
        item.btn.dataset.range=item.when===null?'unknown':item.when<min?'before':item.when>max?'after':'inside';
        if (item.when!==null) item.btn.style.setProperty('--mark-at',percent(item.when));
      }
      for (const btn of zoom.children) btn.setAttribute('aria-pressed',String((btn.dataset.scale==='week')===near));
    }
    function select(item) {
      detail.dataset.event=item.key;
      detail.replaceChildren();
      for (const row of rows) {
        row.btn.tabIndex=row===item?0:-1;
        row.btn.setAttribute('aria-checked',String(row===item));
      }
      if (item.key==='end' && item.value && entry.period && !entry.period.fixed) {
        const p=entry.period, unit={月:'个月',日:'天',年:'年'}[p.unit];
        detail.append(box('warranty-formula',glyph('layers'),el('span','终验 / 复验 + '+p.count+' '+unit),
          el('strong','= '+item.value.replaceAll('-','.'))));
      }
      for (const [label,f] of item.refs) {
        const btn=action('',()=>openPage(f.doc,f.page,f.id),'warranty-cite');
        btn.dataset.source=f.id;
        const ink=el('span','','warranty-ink'); ink.append(el('q',f.source_line.text)); ink.dataset.preview='idle';
        btn.append(el('span',label),ink,el('small',f.page+' 页 · '+f.source_line.number+' 行'),glyph('arrows-angle-expand'));
        btn.append(el('span','，打开'+f.name+'原件','visually-hidden'));
        detail.append(btn);
      }
      if (!item.refs.length) detail.append(el('span','本版缺少可定位的'+item.label+'依据。','small'));
      requestAnimationFrame(preview);
    }
    for (const [i,item] of rows.entries()) {
      const btn=action('',()=>select(item),'warranty-event');
      btn.dataset.event=item.key; btn.dataset.future=String(item.when!==null && item.when>cutoff);
      const track=el('span','','warranty-track'); track.setAttribute('aria-hidden','true'); track.append(el('i'));
      const date=item.when===null?el('span','待核','warranty-value'):el('time',item.value.replaceAll('-','.'),'warranty-value');
      if (item.when!==null) date.dateTime=item.value;
      const value=el('span','','warranty-event-date'); value.append(date);
      if (item.when!==null && item.when>cutoff) value.append(el('small','提交后 '+(item.when-cutoff)+' 天','warranty-offset'));
      btn.append(el('span',item.label,'warranty-event-name'),track,value);
      btn.setAttribute('role','radio');
      btn.append(el('span','，查看时点依据','visually-hidden'));
      btn.addEventListener('keydown',e=>{
        const key=e.key;
        if (!['ArrowUp','ArrowLeft','ArrowDown','ArrowRight','Home','End'].includes(key)) return;
        e.preventDefault(); e.stopPropagation();
        const n=key==='Home'?0:key==='End'?rows.length-1:(i+(['ArrowUp','ArrowLeft'].includes(key)?-1:1)+rows.length)%rows.length;
        select(rows[n]); rows[n].btn.focus();
      });
      item.btn=btn; choice.append(btn);
    }
    if (low<cutoff-7 || high>cutoff+7) {
      for (const [key,label,desc] of [['all','全程','查看全部日期'],['week','±7 天','查看提交日前后各 7 天']]) {
        const btn=action(label,()=>scale(key==='week')); btn.dataset.scale=key; btn.setAttribute('aria-label',label+'，'+desc); zoom.append(btn);
      }
    }
    scale(near); select(focus);
    return root;
  }
  return {panel};
})();
