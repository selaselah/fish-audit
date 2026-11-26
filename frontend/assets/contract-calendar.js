const ContractCalendar = (() => {
  const names = {signed_on:'签订日',effect_on:'生效日',valid_until:'有效截止日'};
  const labels = {signed_on:['签约日期','签订日期','签署日期'],effect_on:['实际生效日期','生效确认日期'],
    valid_until:['合同有效期至','合同有效截止日']};
  const states = {exact:'原行一致',spacing:'排版空格已核',notation:'写法待核',invalid:'日历日期无效',unread:'原行待核',
    multiple:'多条待核',different:'读数有差异',unverified:'转录待核',conflict:'日期冲突'};
  const readable = state => state==='exact' || state==='spacing';
  const papers = new WeakMap();
  const parts = value => /^([^:：]+)([:：])(.*)$/u.exec(value);

  function literal(value) {
    const text=value.replace(/^ +| +$/gu,'');
    const cn=/^([0-9]{4}) *年 *([0-9]{1,2}) *月 *([0-9]{1,2}) *日$/u.exec(text);
    const num=/^([0-9]{4}) *([-./]) *([0-9]{1,2}) *\2 *([0-9]{1,2})$/u.exec(text);
    if (!cn && !num) return null;
    const [year,month,day] = cn ? cn.slice(1) : [num[1],num[3],num[4]];
    const date=new Date(0);
    date.setUTCFullYear(+year,+month-1,+day);
    if (+year===0 || date.getUTCFullYear()!==+year || date.getUTCMonth()!==+month-1 || date.getUTCDate()!==+day) return null;
    return {tokens:[cn?'年月日':num[2],year,month,day].join('|'),iso:[year,month.padStart(2,'0'),day.padStart(2,'0')].join('-')};
  }

  function backed(row, fact, call, doc, page) {
    const raw=parts(row.quote), quote=parts(fact?.quote || '');
    if (!raw || !quote || !labels[row.field].includes(raw[1]) || raw[1]!==quote[1] || raw[2]!==quote[2] ||
        !['anchored','confirmed'].includes(fact.status) || fact.field!==row.field || !fact.source_line?.rects?.length) return false;
    const value=quote && fact.value===fact.quote ? quote[3] : fact.value;
    const original=literal(raw[3]);
    if (!original || original.iso!==row.date || [value,quote[3]].some(v=>literal(v)?.tokens!==original.tokens)) return false;
    const exact=fact.quote===row.quote && raw[3].replace(/^ +| +$/gu,'')===value;
    if (row.state==='exact') return exact && row.witness==='native_line';
    return !exact && (row.witness==='visual_check' && FolioTranscriptions.visuallyRead(fact,call) ||
      row.witness==='field_receipt' && Boolean(fieldReceiptOperation(fact,doc,page)));
  }

  function resolve(finding,graph,calls) {
    const ledger=graph.contract_effect_sources, events=finding.effect_review.calendar;
    const index=graphIndex(graph), cited=new Set(traceReferences(graph,finding));
    const unit=graph.documents_by_kind.contract?.find(id=>finding.scope.includes(id));
    const all=ledger.date_rows?.filter(r=>r.unit===unit);
    if (!unit || !all?.length || new Set(events.map(e=>e.field)).size!==events.length ||
        new Set(all.map(r=>r.field)).size!==events.length || new Set(all.map(r=>r.id)).size!==all.length) return null;
    const groups=[];
    for (const event of events) {
      const rows=all.filter(r=>r.field===event.field);
      if (!names[event.field] || !states[event.state] || !rows.length ||
          JSON.stringify(rows.map(r=>r.id))!==JSON.stringify(event.rows)) return null;
      const readings=[];
      for (const row of rows) {
        const pg=row.doc+'/p'+row.page, page=index.nodes.get(pg), source=index.nodes.get(row.id), doc=index.documents.get(row.doc);
        const edge=graph.edges.find(e=>e.type==='contract_date_source' && e.from===pg && e.to===row.id);
        const call=calls?.find(p=>p.doc===row.doc && p.page===row.page);
        if (!states[row.state] || !Number.isInteger(row.line) || row.line<1 || row.id!=='contract-date/'+pg+'/l'+row.line ||
            !ledger.pages.some(p=>p.unit===unit && p.doc===row.doc && p.page===row.page && p.native) ||
            !row.original_sha256 || row.original_sha256!==doc?.sha256 || page?.layer!=='text' || row.page_sha256!==page.sha256 ||
            call?.page_sha256!==page.sha256 || source?.type!=='contract_date_line' || source.label!==row.quote ||
            source.doc!==row.doc || source.page!==row.page || source.line!==row.line ||
            !edge || JSON.stringify(edge.evidence)!==JSON.stringify([pg,...row.facts]) || ![row.id,...edge.evidence].every(id=>cited.has(id))) return null;
        const facts=row.facts.map(id=>index.facts.get(id));
        if (!facts.every(f=>f && f.doc===row.doc && f.page===row.page && (f.unit || f.doc)===unit &&
          f.page_sha256===page.sha256 && f.source_sha256===doc.sha256 && f.source_line?.text===row.quote && f.source_line.number===row.line)) return null;
        if (readable(row.state) ? facts.length!==1 || !backed(row,facts[0],call,doc,page) : row.date!==null || row.witness!==null) return null;
        readings.push({row,facts,doc});
      }
      const distinct=new Set(rows.map(r=>literal(parts(r.quote)?.[3] || '')?.iso).filter(Boolean));
      if (readable(event.state) ? rows.length!==1 || rows[0].state!==event.state || rows[0].date!==event.date :
        event.date!==null || finding.status==='ok' || (event.state==='conflict')!==(distinct.size>1) ||
        rows.length>1 && !['conflict','multiple'].includes(event.state) ||
        rows.length===1 && event.state!==rows[0].state && !(readable(rows[0].state) && event.state==='unverified')) return null;
      groups.push({...event,readings});
    }
    return groups;
  }

  function currentRows() {
    const report=state.bundle?.report;
    if (!report) return [];
    if (!papers.has(report)) {
      const h01=report.findings.find(f=>f.rule==='H01');
      const groups=h01?.effect_review?.calendar && report.graph.contract_effect_sources?.format==='contract-effect-sources-v7'
        ? resolve(h01,report.graph,report.calls.pages) : null;
      papers.set(report,(groups || []).flatMap(g=>g.readings));
    }
    return papers.get(report);
  }
  function open(row) {
    openPage(row.doc,row.page,null,row.line,null,row.id);
  }
  function pageReferences(doc,page) {
    return currentRows().filter(({row})=>row.doc===doc && row.page===page).map(({row,facts})=>({
      ref:row.id,label:names[row.field]+'原行',option:names[row.field]+' · 第 '+row.line+' 行',
      rawLine:row.line,quote:row.quote,quality:'contract_date_reference',rects:facts[0]?.source_line?.rects || [],
    }));
  }
  function citation(ref) {
    const source=currentRows().find(({row})=>row.id===ref);
    return source ? action(source.row.quote,()=>open(source.row),'ref') : el('span','合同日期原行待核','small');
  }

  function panel(finding,graph,findings,calls) {
    if (!finding?.effect_review?.calendar?.length || graph.contract_effect_sources?.format!=='contract-effect-sources-v7') return null;
    const groups=resolve(finding,graph,calls);
    if (!groups) return el('p','合同日期依据待核','small');
    const index=graphIndex(graph);
    const root=el('section','','calendar-workpaper');
    root.id='contract-calendar'; root.tabIndex=-1; root.setAttribute('aria-label','合同原件日期');
    const picker=box('calendar-events'), body=box('calendar-body');
    picker.setAttribute('role','tablist'); picker.setAttribute('aria-label','合同日期栏');
    body.setAttribute('role','tabpanel'); body.id='calendar-readout';
    let selected, lineIndex, serial=0;
    function paintRow() {
      const group=groups[selected], {row,facts,doc}=group.readings[lineIndex];
      const fact=facts.length===1?facts[0]:null, request=++serial;
      body.dataset.calendarRow=row.id;
      const line=el('span',row.quote,'calendar-paper-line');
      const location='第 '+row.page+' 页 · 第 '+row.line+' 行';
      const original=action('',()=>open(row),'calendar-original');
      original.append(box('calendar-file',glyph('file-earmark-text'),el('span',doc.name),el('small',location),glyph('arrows-angle-expand')),line);
      original.setAttribute('aria-label','打开'+doc.name+'，'+location+'，'+row.quote);
      if (fact?.source_line?.rects?.length) EvidenceCompare.lineExcerpt(fact,index).then(canvas=>{
        if (canvas && request===serial) {canvas.setAttribute('aria-hidden','true'); line.replaceChildren(canvas);}
      }).catch(()=>{});
      const meta=box('calendar-reading',el('small','提取读数'),el('strong',fact?.value || (facts.length?'多条观察':'未提取')),
        el('span',fact && fact.field!==group.field?'归入「'+fact.label+'」':
          ({visual_check:'排版空格已核 · 独立读图',field_receipt:'排版空格已核 · 核图回执',native_line:'与原行逐字相符'})[row.witness] || states[row.state]));
      const related=findings.filter(f=>['H04','H05'].includes(f.rule) && f.stage && traceReferences(graph,f).includes(row.id));
      const jumps=box('calendar-related');
      if (related.length) {
        jumps.append(el('small','引用此行'));
        for (const f of related) {
          const button=action(f.stage.name+(f.rule==='H05'?'实付':''),()=>revealPaperTarget(document.querySelector('[data-finding="'+CSS.escape(f.id)+'"]')));
          button.setAttribute('aria-label',button.textContent+'，'+statusName(f.status)+'，查看审计依据');
          button.dataset.calendarPhase=f.id; jumps.append(button);
        }
      }
      if (!readable(group.state) && canReviewCurrentPaper()) {
        jumps.append(action('拟补件意见',()=>{
          const examples=[group.readings[lineIndex]];
          if (group.state==='conflict') {
            const dateOf=r=>literal(parts(r.row.quote)?.[3] || '')?.iso;
            const first=group.readings.find(r=>dateOf(r));
            const second=group.readings.find(r=>dateOf(r) && dateOf(r)!==dateOf(first));
            examples.splice(0,1,first,second);
          }
          const places=examples.map(({row:r,doc:d})=>{
            const location='《'+d.name+'》第 '+r.page+' 页第 '+r.line+' 行';
            return group.state==='conflict' ? location+'载有「'+r.quote+'」' : location;
          });
          draftSupplement(places.join('，')+'。请补充可确认合同'+names[group.field]+'的原件，并注明所依据的合同版本。');
        },'calendar-draft'));
      }
      const content=box('calendar-source',original,meta);
      body.replaceChildren();
      if (group.readings.length>1) {
        const picks=box('calendar-lines'); picks.setAttribute('role','group'); picks.setAttribute('aria-label','同一日期栏的原行');
        for (const [i,{row:r}] of group.readings.entries()) {
          const label='第 '+r.page+' 页 · '+r.line+' 行';
          const button=action('',()=>{lineIndex=i;paintRow();body.querySelector('[aria-pressed="true"]').focus();});
          button.append(el('strong',parts(r.quote)?.[3].trim() || r.quote),el('small',label));
          button.setAttribute('aria-pressed',String(i===lineIndex)); picks.append(button);
        }
        body.append(picks);
      }
      body.append(content);
      if (jumps.childElementCount) body.append(jumps);
    }
    function select(i) {
      selected=i; lineIndex=0;
      [...picker.children].forEach((tab,n)=>{tab.tabIndex=n===i?0:-1; tab.setAttribute('aria-selected',String(n===i));});
      body.setAttribute('aria-labelledby',picker.children[i].id);
      paintRow();
    }
    for (const [i,group] of groups.entries()) {
      const tab=action('',()=>select(i),'calendar-event');
      tab.id='calendar-'+group.field; tab.dataset.state=group.state;
      tab.setAttribute('role','tab'); tab.setAttribute('aria-controls',body.id);
      tab.append(el('small',names[group.field]),el('strong',group.date || states[group.state]));
      tab.addEventListener('keydown',event=>{
        const to={ArrowRight:(i+1)%groups.length,ArrowLeft:(i+groups.length-1)%groups.length,Home:0,End:groups.length-1}[event.key];
        if (to!==undefined) {event.preventDefault();select(to);picker.children[to].focus();}
      });
      picker.append(tab);
    }
    root.append(picker,body);
    const focus=groups.findIndex(g=>!readable(g.state));
    select(focus>=0 ? focus : Math.max(0,groups.findIndex(g=>g.field==='effect_on')));
    return root;
  }
  return {panel,pageReferences,citation,available:()=>currentRows().length>0};
})();
