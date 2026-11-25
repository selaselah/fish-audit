const TrialLog = (() => {
  const labels = {
    run_subject: '采购标的', run_quantity: '设备数量', run_signer: '复验签认', run_equipment: '日志设备',
    run_clock: '区间口径', run_attestation: '签认范围', run_segment: '运行记录', run_qualification: '设备范围附注',
  };
  const states = {
    run_met: '满足试运行条款', run_gap: '日志有断档', run_fault: '曾故障停机', run_device: '设备范围待核',
    run_short: '记录时长不足', run_record: '记录或签认待核', run_window: '起止范围待核', run_overlap: '区间重叠',
  };
  const status = {normal:'无异常', gap:'无记录', fault:'故障停机'};
  const body = row => row?.quote.normalize('NFKC').replace(/^[^:]*:/,'').trim().replace(/。$/,'') || '';
  const seconds = stamp => Date.parse(stamp+'Z')/1000;
  const readable = stamp => stamp.slice(5,16).replace('T',' ');
  function duration(n) {
    const h=Math.floor(n/3600), m=Math.floor(n%3600/60);
    return (h ? h+'小时' : '')+(m ? m+'分' : '') || '0分';
  }
  function printed(row) {
    const match=body(row).match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s+至\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*\|\s*(连续无异常|故障停机)$/);
    if (!row.supported || !match) return null;
    const [start,end]=match.slice(1,3).map(t=>t.replace(' ','T')+':00');
    const diff=seconds(end)-seconds(start);
    if (!(diff>0) || [start,end].some(t=>new Date(seconds(t)*1000).toISOString().slice(0,19)!==t)) return null;
    return {ref:row.id,start,end,seconds:diff,state:match[3]==='连续无异常'?'normal':'fault'};
  }
  function equal(a,b,keys) {
    return a && b && keys.every(k=>a[k]===b[k]);
  }
  function checkSources(check, rows, chain, graph) {
    const op=check.operation, selected=rows.filter(r=>r.kind.startsWith('run_'));
    if (!op || !states[check.state] || graph?.reinspection_wait_sources?.format!=='contract-reinspection-wait-v2' ||
        !Array.isArray(op.sources) || selected.length!==op.sources.length || selected.some((r,i)=>r.id!==op.sources[i])) return false;
    const term=rows.find(r=>r.id===check.term_ref), contract=term?.unit;
    const promise=body(term).match(/^整改完成后须连续试运行\s*([1-9]\d{0,4})\s*小时无异常(?:方可|才能)开始复验$/);
    if (term?.kind!=='operation' || !promise || Number(promise[1])!==check.required_hours) return false;
    const step=role=>chain?.steps.filter(s=>s.role===role) || [];
    const final=step('final')[0]?.unit;
    function one(unit,kind) {
      const found=selected.filter(r=>r.unit===unit && r.kind===kind);
      return found.length===1 && found[0].supported ? found[0] : null;
    }
    const id=row=>{
      const code=body(row).match(/^[\p{L}\p{N}_ -]{1,60}\(序列号\s*([A-Za-z0-9._-]+)\)$/u)?.[1];
      return code && code===row.serial ? code : null;
    };
    const model=one(contract,'run_subject'), device=one(final,'run_equipment');
    if (op.serial!==id(model) || op.log_serial!==(device?.serial || null) ||
        (op.log_serial!==null && op.log_serial!==body(device))) return false;
    const pending=state=>check.state===state && check.status==='missing' && op.longest_seconds===null &&
      Array.isArray(op.intervals) && !op.intervals.length && Array.isArray(op.gaps) && !op.gaps.length;
    const units=['original','repair','final'].map(role=>step(role)[0]?.unit);
    const signer=one(final,'run_signer'), clock=one(final,'run_clock'), attestation=one(final,'run_attestation');
    const scoped=new Set([contract,...units]);
    if (!op.serial || op.serial!==op.log_serial || !/\d/.test(op.serial) || /XX|[*＊×□…]/i.test(op.serial) ||
        ['original','repair','final'].some(role=>step(role).length!==1) ||
        units.some(unit=>id(one(unit,'run_subject'))!==op.serial) ||
        graph.reinspection_wait_sources.pages.some(p=>scoped.has(p.unit) && !(p.native && p.text_only)) ||
        [contract,units[0],final].some(unit=>!/^1\s*台$/.test(body(one(unit,'run_quantity')))) ||
        selected.some(r=>r.kind==='run_qualification')) return pending('run_device');
    if (!signer || !clock || !attestation ||
        body(clock)!=='北京时间,区间含起不含止,边界为整分' || body(attestation)!=='本页复验签认涵盖全部试运行记录' ||
        signer.facts.map(ref=>graphIndex(graph).facts.get(ref)).filter(f=>f?.status==='confirmed' &&
          f.field==='acceptance_signer' && f.source_line?.text===signer.quote && f.source_line.number===signer.line).length!==1) return pending('run_record');
    const rowsOfLog=selected.filter(r=>r.kind==='run_segment');
    if (!rowsOfLog.length || [device,clock,attestation,...rowsOfLog].some(r=>r.doc!==signer.doc || r.page!==signer.page)) return pending('run_record');
    const intervals=rowsOfLog.map(printed);
    if (intervals.some(r=>!r?.seconds)) return pending('run_record');
    intervals.sort((a,b)=>a.start.localeCompare(b.start) || a.end.localeCompare(b.end) || a.ref.localeCompare(b.ref));
    if (op.intervals?.length!==intervals.length || intervals.some((s,i)=>
      !equal(s,op.intervals[i],['ref','start','end','state','seconds']))) return false;
    let longest=0, streak=0;
    const gaps=[];
    for (let i=0;i<intervals.length;i++) {
      const line=intervals[i], prev=intervals[i-1];
      if (prev && prev.end>line.start) return check.state==='run_overlap' && check.status==='missing' && op.longest_seconds===null && !op.gaps?.length;
      if (prev && prev.end<line.start) {
        gaps.push({start:prev.end,end:line.start,seconds:seconds(line.start)-seconds(prev.end),before_ref:prev.ref,after_ref:line.ref});
        streak=0;
      }
      streak=line.state==='normal'?streak+line.seconds:0;
      longest=Math.max(longest,streak);
    }
    const start=rows.find(r=>r.id===check.start_ref)?.stamp?.from, fixed=rows.find(r=>r.id===check.repair_ref)?.stamp?.before;
    if (!start || !fixed || intervals[0].start<fixed || intervals.at(-1).end>start) {
      return check.state==='run_window' && check.status==='missing' && op.longest_seconds===null && !op.gaps?.length;
    }
    const state=intervals.some(s=>s.state==='fault')?'run_fault':longest>=check.required_hours*3600?'run_met':gaps.length?'run_gap':'run_short';
    return check.state===state && check.status===(state==='run_met'?'ok':state==='run_fault'?'risk':'missing') &&
      op.longest_seconds===longest && op.gaps?.length===gaps.length && gaps.every((g,i)=>
        equal(g,op.gaps[i],['start','end','seconds','before_ref','after_ref']));
  }

  function sourceButton(row,label) {
    const ref=action('',()=>ReinspectionTiming.open(row),'run-original');
    ref.dataset.runRef=row.id;
    ref.append(glyph('journal-text'),el('span',label),el('small','第 '+row.page+' 页'+(row.line?' · '+row.line+' 行':'')),glyph('arrows-angle-expand'));
    ref.title=row.quote;
    return ref;
  }
  function panel(check,rows) {
    const op=check.operation, log=box('run-log'), ref=id=>rows.find(r=>r.id===id);
    log.dataset.runState=check.state;
    if (!Number.isSafeInteger(op.longest_seconds)) {
      const model=rows.find(r=>r.kind==='run_subject' && r.role==='contract' && r.supported);
      const device=rows.find(r=>r.kind==='run_equipment' && r.supported);
      if (model) log.append(sourceButton(model,'合同设备 · '+(op.serial || '范围待核')));
      if (device) log.append(sourceButton(device,'日志设备 · '+(op.log_serial || '范围待核')));
      const extra=rows.filter(r=>['run_clock','run_attestation','run_segment','run_qualification'].includes(r.kind));
      if (extra.length) log.append(fold('查看日志原行（'+extra.length+'）',box('run-sources',...extra.map(r=>sourceButton(r,labels[r.kind])))));
      return log;
    }
    const slots=[...op.intervals,...op.gaps.map(g=>({...g,state:'gap'}))].sort((a,b)=>a.start.localeCompare(b.start));
    const metric=box('run-measure',box('run-mainvalue',el('span','最长连续无异常'),el('strong',duration(op.longest_seconds))),
      box('run-target',el('span','合同要求'),el('strong','≥ '+duration(check.required_hours*3600))));
    const track=box('run-track'), swatches=[], pin=el('span','','run-pin');
    const origin=seconds(slots[0].start), extent=seconds(slots.at(-1).end)-origin;
    track.setAttribute('aria-hidden','true');
    const choices=el('select','','run-select'); choices.id='trial-log-period';
    for (const [i,s] of slots.entries()) {
      const mark=el('span','','run-mark'); mark.dataset.kind=s.state;
      mark.style.flexGrow=String(s.seconds); swatches.push(mark); track.append(mark);
      choices.add(new Option((i+1)+' / '+slots.length+'　'+status[s.state]+' · '+duration(s.seconds),String(i)));
    }
    track.append(pin);
    const earlier=action('',()=>select(active-1),'run-arrow'), later=action('',()=>select(active+1),'run-arrow');
    earlier.append(glyph('chevron-down')); later.append(glyph('chevron-down'));
    earlier.setAttribute('aria-label','上一时段'); later.setAttribute('aria-label','下一时段');
    const caption=el('label','运行时段','run-caption'); caption.htmlFor=choices.id;
    const time=el('span','','run-time'), sources=box('run-sources'), inspector=box('run-inspector',box('run-period',caption,time),sources);
    inspector.setAttribute('aria-live','polite');
    let active;
    function select(index) {
      active=index; const s=slots[index];
      choices.value=String(index); earlier.disabled=index===0; later.disabled=index===slots.length-1;
      for (const [i,mark] of swatches.entries()) mark.toggleAttribute('data-selected',i===index);
      pin.hidden=s.state==='normal';
      pin.dataset.kind=s.state;
      pin.textContent=s.state==='fault'?'!':'?';
      pin.style.left=(100*(seconds(s.start)+s.seconds/2-origin)/extent)+'%';
      time.textContent=readable(s.start)+' — '+readable(s.end);
      inspector.dataset.kind=s.state;
      if (s.state==='gap') sources.replaceChildren(sourceButton(ref(s.before_ref),'前段止点'),sourceButton(ref(s.after_ref),'后段起点'));
      else sources.replaceChildren(sourceButton(ref(s.ref),'核对运行记录'));
    }
    choices.addEventListener('change',()=>select(Number(choices.value)));
    choices.addEventListener('keydown',event=>{
      if (event.key!=='Home' && event.key!=='End') return;
      event.preventDefault(); select(event.key==='Home'?0:slots.length-1);
    });
    track.addEventListener('click',event=>{
      const index=swatches.indexOf(event.target.closest('.run-mark'));
      if (index>=0) select(index);
    });
    const nav=box('run-picker',earlier,choices,later);
    inspector.insertBefore(nav,sources);
    log.append(metric,box('run-label',el('strong',op.serial),el('small','北京时间')),
      track,box('run-axis',el('span',readable(slots[0].start)),el('span',readable(slots.at(-1).end))),inspector);
    if (['run_fault','run_gap'].includes(check.state)) {
      select(slots.findIndex(s=>s.state===(check.state==='run_fault'?'fault':'gap')));
    } else {
      let first=0, total=0;
      for (const [i,s] of slots.entries()) {
        if (s.state!=='normal') { first=i+1; total=0; continue; }
        total+=s.seconds;
        if (total===op.longest_seconds) break;
      }
      select(first);
    }
    return log;
  }
  return {labels,states,checkSources,panel};
})();
