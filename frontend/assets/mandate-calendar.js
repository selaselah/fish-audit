// Read the dates and document relationships cited by this issued signing finding.
const MandateCalendar = (() => {
  const fields=[
    ['signed_on','signed_on','合同签约',['签约日期','签订日期','签署日期']],
    ['granted_on','issued_on','委托书出具',['授权出具日期','委托书出具日期']],
    ['grant_from','valid_from','授权起始',['授权起始日','授权起始日期','授权开始日期']],
    ['grant_until','valid_until','授权截止',['授权截止日','授权截止日期','授权终止日期']]
  ];
  const identityLabels={
    contract_id:['合同编号','合同号'],subject:['采购标的','合同标的','项目名称','标的名称','货物名称'],
    buyer:['采购方','购方','购买方','甲方','买方','需方','采购单位'],seller:['供应方','销方','销售方','乙方','卖方','供方','供应商','供货单位'],
    grant_principal:['委托单位','授权单位','委托人'],grant_counterparty:['交易相对方','授权交易相对方'],
    grant_number:['委托书编号','授权委托书编号'],buyer_grant_ref:['甲方委托书编号','采购方委托书编号'],
    seller_grant_ref:['乙方委托书编号','供应方委托书编号'],grant_agent:['受托人','受托人姓名','代理人姓名']
  };
  function completeNumber(value) {
    return /^[a-z\d\u3400-\u9fff][a-z\d\u3400-\u9fff._-]{0,79}$/iu.test(value) &&
      !/^(?:无|未编号|未填写|待定)$|尾号|[后末][零一二两三四五六七八九十\d]+位|脱敏|隐去|遮盖|\.{2,}|\dxx+(?=\d|$)/iu.test(value) &&
      !value.split(/[-_.]/u).some(s=>/^[\dx]*xx[\dx]*$/iu.test(s));
  }
  const plain=value=>String(value || '').normalize('NFKC').trim();
  function printed(fact) {
    const line=fact?.source_line;
    if (!line?.rects?.length || !['anchored','confirmed'].includes(fact.status)) return null;
    const raw=plain(line.text), colon=raw.indexOf(':');
    if (colon<1 || raw!==plain(fact.quote)) return null;
    const value=raw.slice(colon+1).trim();
    return [raw,value].includes(plain(fact.value))?{label:raw.slice(0,colon).trim(),value}:null;
  }
  function readDay(fact,labels,issued) {
    const p=printed(fact);
    if (!p || !labels.includes(p.label) || /\d\s+\d/u.test(p.value)) return null;
    const m=p.value.replace(/\s+/gu,'').match(/^(\d{4})(?:年(\d{1,2})月(\d{1,2})日|([-/.])(\d{1,2})\4(\d{1,2}))$/u);
    if (!m) return null;
    const iso=m[1]+'-'+(m[2] || m[5]).padStart(2,'0')+'-'+(m[3] || m[6]).padStart(2,'0');
    const time=Date.parse(iso+'T00:00:00Z');
    return iso===issued && Number.isFinite(time) && new Date(time).toISOString().slice(0,10)===iso?iso:null;
  }
  function evidence(finding,entry,graph) {
    const idx=graphIndex(graph), kinds=graph.documents_by_kind, refs=idx.supports.get('finding/'+finding.id);
    const contracts=kinds.contract?.filter(id=>finding.scope.includes(id)) || [];
    const contract=contracts.length===1?contracts[0]:null;
    const grant=entry.units.length===1 && kinds.power_of_attorney?.includes(entry.units[0]) && finding.scope.includes(entry.units[0])?entry.units[0]:null;
    function record(unit,field) {
      if (!unit) return null;
      const candidates=graph.facts.filter(f=>(f.unit || f.doc)===unit && f.field===field);
      if (candidates.length!==1) return null;
      const [f]=candidates;
      return refs?.has(f.id) && finding.evidence.includes(f.id) && entry.evidence.includes(f.id) &&
        graph.edges.some(e=>e.from===unit && e.type===field && e.evidence.includes(f.id))?f:null;
    }
    const rows=fields.map(([field,key,label,labels])=>{
      const fact=record(field==='signed_on'?contract:grant,field);
      return {field,label,fact,day:readDay(fact,labels,entry[key])};
    });
    function value(unit,field) {
      const row=printed(record(unit,field));
      return row && (!identityLabels[field] || identityLabels[field].includes(row.label))?row.value:null;
    }
    const counterparty=entry.side==='buyer'?'seller':'buyer';
    const links=[['contract_id','contract_id'],['subject','subject'],[entry.side,'grant_principal'],[counterparty,'grant_counterparty']];
    const mandateRef=entry.side+'_grant_ref';
    if (graph.facts.some(f=>(f.unit || f.doc)===contract && f.field===mandateRef)) links.push([mandateRef,'grant_number']);
    let bound=Boolean(contract && grant && ['buyer','seller'].includes(entry.side) && links.every(([left,right])=>{
      const a=value(contract,left);
      return a && a===value(grant,right) && (!(left==='contract_id' || left===mandateRef) || completeNumber(a));
    }));
    if (bound && graph.delegation_coverage?.format==='written-contract-mandate-v5' && rows[0].day && rows[1].day) {
      const [signed,issued]=rows, order=entry.issuance_order;
      const expected=signed.day===issued.day?'same_day':signed.day<issued.day?'before':'after';
      bound=order?.state===expected && order.signed_refs?.length===1 && order.signed_refs[0]===signed.fact.id &&
        order.issued_refs?.length===1 && order.issued_refs[0]===issued.fact.id;
    }
    const grantName=value(grant,'grant_agent'), signature=value(contract,entry.signature_field);
    const named=bound && entry.agent_kind==='named' && grantName===plain(entry.agent) &&
      [grantName+'(已签字)',grantName+'(已签名)'].includes(signature)?entry.agent:'';
    const image=(graph.delegation_coverage?.pages || []).some(p=>entry.units.includes(p.unit) && (!p.native || p.text_only===false));
    return {rows,bound,named,image,scope:record(grant,'grant_scope')};
  }
  function relation(entry,rows,bound,image) {
    const [signed,issued,start,end]=rows.map(r=>r.day), span=(a,b)=>Math.round((Date.parse(a)-Date.parse(b))/86400000);
    const note=(label,tone,field)=>({label,tone,field});
    if (image) return note('委托书影像待核','missing','granted_on');
    if (!bound) return note('原件归属待核','missing');
    if (start && end && start>end) return note('起止日期待核','missing','grant_until');
    if (signed && issued && signed<issued) return note('签约早于出具 '+span(issued,signed)+' 天','risk','granted_on');
    if (signed && end && signed>end) return note('签约超过截止日 '+span(signed,end)+' 天','risk','grant_until');
    if (signed && start && signed<start) return note('签约早于起始日 '+span(start,signed)+' 天','risk','grant_from');
    if (signed && issued && signed===issued) return note(entry.issuance_order?.state==='same_day'?'出具与签约同日 · 时分待核':'出具与签约同日','missing','granted_on');
    const missing=rows.filter(r=>!r.day);
    if (missing.length) return note(missing.length===1?missing[0].label+'日待核':'日期待核','missing',missing[0].field);
    if (signed===end) return note('签约在授权截止日','neutral','grant_until');
    if (signed===start) return note('签约在授权起始日','neutral','grant_from');
    return note('签约日在所列期间','neutral','grant_until');
  }
  function panel(finding,entry,graph,expandIssue=true) {
    const {rows,bound,named,image,scope}=evidence(finding,entry,graph), index=graphIndex(graph);
    if (!rows.some(r=>r.fact)) return null;
    const status=relation(entry,rows,bound,image), sides={buyer:'甲方',seller:'乙方',unassigned:'待归属'};
    const root=el('details','','mandate-calendar'), summary=el('summary');
    const otherLimit=status.tone==='neutral' && entry.status!=='ok';
    root.dataset.side=entry.side; root.dataset.dateStatus=status.tone;root.dataset.authorityStatus=entry.status;
    const title=box('mandate-calendar-title',glyph('clock-history'),el('strong',(sides[entry.side] || '')+'签约授权'));
    if (named) title.append(el('span',named,'mandate-agent'));
    const caption=otherLimit?'所列期间内 · '+(entry.status==='risk'?'签约权限有风险':'签约权限待核'):status.label;
    summary.append(title,el('span',caption,'mandate-date-caption'),glyph('chevron-down')); root.append(summary);
    const days=rows.map(r=>r.day).filter(Boolean).sort(), months=days.map(d=>d.slice(0,7));
    const views=index.mandateCalendars ??= new Map(), key=finding.id+'/'+entry.side;
    const first=rows.find(r=>r.field===status.field && !r.day && r.fact) || rows.find(r=>r.field==='signed_on' && r.day) || rows.find(r=>r.day) || rows.find(r=>r.fact);
    const view=views.get(key) || {selected:first.field,month:(first.day || rows[0].day || days[0])?.slice(0,7),open:expandIssue && status.tone!=='neutral'};
    views.set(key,view); root.open=view.open;
    let built=false;
    function build() {
      if (built) return;
      built=true;
      const body=box('mandate-calendar-body'), cal=box('mandate-month'), aside=box('mandate-reading');
      const selector=box('mandate-date-choices'), source=box('mandate-original'), buttons=new Map();
      selector.setAttribute('role','group'); selector.setAttribute('aria-label','选择要核查的日期原件');
      source.setAttribute('aria-live','polite');
      const heading=el('strong'), cells=box('mandate-days');
      cells.setAttribute('role','group'); cells.setAttribute('aria-label','有原件记载的日期');
      const turn=(direction)=>{
        const d=new Date(view.month+'-01T00:00:00Z');d.setUTCMonth(d.getUTCMonth()+direction);
        view.month=d.toISOString().slice(0,7); draw();
      };
      const back=action('',()=>turn(-1),'month-arrow'), next=action('',()=>turn(1),'month-arrow');
      back.append(glyph('chevron-down'));next.append(glyph('chevron-down'));
      back.setAttribute('aria-label','上个月'); next.setAttribute('aria-label','下个月');
      heading.setAttribute('aria-live','polite');
      const week=box('mandate-week');
      week.setAttribute('aria-hidden','true');
      for (const day of '一二三四五六日') week.append(el('span',day));
      const monthBar=box('mandate-month-heading',heading,box('month-navigation',back,next));
      const range=bound && !image && rows[2].day && rows[3].day && rows[2].day<=rows[3].day;
      cal.append(monthBar,week,cells);
      if (range) cal.append(box('mandate-range-key',el('i'),el('span','委托书所列期间')));
      function draw() {
        if (!view.month) return;
        cal.dataset.month=view.month;
        heading.textContent=view.month.slice(0,4)+' 年 '+Number(view.month.slice(5))+' 月';
        back.disabled=view.month<=months[0]; next.disabled=view.month>=months.at(-1);
        const firstOfMonth=new Date(view.month+'-01T00:00:00Z'), cursor=new Date(firstOfMonth);
        cursor.setUTCDate(1-(cursor.getUTCDay()+6)%7);
        const grid=document.createDocumentFragment();
        do {
          for (let i=0;i<7;i++) {
            const day=cursor.toISOString().slice(0,10), records=rows.filter(r=>r.day===day);
            const selected=records.some(r=>r.field===view.selected);
            const button=records.length?action(String(cursor.getUTCDate()),()=>choose((records.find(r=>r.field===view.selected) || records[0]).field,{focusDay:true}),'mandate-day'):el('span',String(cursor.getUTCDate()),'mandate-day');
            button.dataset.date=day;
            if (day.slice(0,7)!==view.month) {
              button.classList.add('outside-month');
              if (records.length) button.textContent=(cursor.getUTCMonth()+1)+'/'+cursor.getUTCDate();
            }
            if (range && day>=rows[2].day && day<=rows[3].day) button.classList.add('in-range');
            if (records.length) {
              button.setAttribute('aria-label',button.textContent+' 日，'+day+'，'+records.map(r=>r.label).join('、'));
              button.setAttribute('aria-pressed',String(selected));
              button.dataset.count=String(records.length);
              if (day===rows[0].day) button.classList.add('signing-day');
            } else button.setAttribute('aria-hidden','true');
            grid.append(button);cursor.setUTCDate(cursor.getUTCDate()+1);
          }
        } while (cursor.toISOString().slice(0,7)===view.month);
        cells.replaceChildren(grid);
      }
      function choose(field,{focusDay=false,alignMonth=true}={}) {
        const row=rows.find(r=>r.field===field); view.selected=field;
        if (row.day && alignMonth) view.month=row.day.slice(0,7);
        for (const [id,btn] of buttons) {
          btn.setAttribute('aria-pressed',String(id===field)); btn.tabIndex=id===field?0:-1;
        }
        if (view.month) draw();
        if (focusDay) cells.querySelector('button[aria-pressed=true]')?.focus();
        source.replaceChildren();
        const f=row.fact;
        if (!f) {source.append(el('span','本项缺少可定位的日期记录','mandate-no-source')); return;}
        const raw=f.source_line, quote=raw?.text || f.quote;
        const open=action('',()=>openPage(f.doc,f.page,f.id),'mandate-source-button');
        const label=(index.documents.get(f.doc)?.name || '原件')+' · 第 '+f.page+' 页'+(raw?.number?' · 第 '+raw.number+' 行':' · 核对影像');
        open.setAttribute('aria-label','查看'+row.label+'原件，'+quote+'，'+label);
        const strip=el('span','','mandate-ink'), text=el('q',quote);
        strip.append(text);open.append(strip,box('mandate-source-label',glyph('file-earmark-text'),el('span',label),glyph('arrows-angle-expand')));
        open.dataset.fact=f.id;source.append(open);
        strip.dataset.preview=raw?.rects?.length?'loading':'text';
        if (raw?.rects?.length) EvidenceCompare.lineExcerpt(f,index).then(canvas=>{
          if (!canvas || !open.isConnected) {strip.dataset.preview='text';return;}
          canvas.setAttribute('aria-hidden','true');strip.append(canvas);text.classList.add('visually-hidden');
          strip.dataset.preview='image';
        }).catch(()=>{strip.dataset.preview='text';});
      }
      for (const [i,row] of rows.entries()) {
        const btn=action('',()=>choose(row.field),'mandate-date-choice');
        btn.dataset.field=row.field;
        btn.append(el('span',row.label),el('strong',row.day || (row.fact && !row.fact.source_line?.rects?.length?'核对原图':'日期待核')));
        btn.addEventListener('keydown',e=>{
          const n={ArrowDown:(i+1)%4,ArrowRight:(i+1)%4,ArrowUp:(i+3)%4,ArrowLeft:(i+3)%4,Home:0,End:3}[e.key];
          if (n===undefined) return;
          e.preventDefault();choose(rows[n].field);buttons.get(rows[n].field).focus();
        });
        buttons.set(row.field,btn);selector.append(btn);
      }
      aside.append(selector,source);
      if (bound) {
        const cited=traceReferences(graph,finding).map(id=>index.facts.get(id)).filter(Boolean);
        const pairs=EvidenceCompare.presets(finding,cited,graph), tools=box('mandate-calendar-tools');
        const prefix='mandate-'+entry.side+'-';
        const limit=otherLimit && pairs.find(p=>p.key.startsWith(prefix) && p.status && (entry.limits || []).some(l=>l.field_ref===p.left.id));
        const scopeReading=otherLimit && !limit && printed(scope);
        const second=limit || (!scopeReading && pairs.find(p=>p.key===prefix+status.field));
        for (const pair of [pairs.find(p=>p.key===prefix+'signer'),second]) {
          if (!pair || !pair.left.source_line?.rects?.length || !pair.right.source_line?.rects?.length) continue;
          const btn=action('对照'+pair.label,()=>showFindingPath(finding,true,pair.key),'proof-pair');
          btn.dataset.pair=pair.key;btn.prepend(glyph('layout-sidebar-inset-reverse'));tools.append(btn);
        }
        if (scopeReading) {
          const btn=action('查看授权范围',()=>openPage(scope.doc,scope.page,scope.id),'proof-pair');
          btn.dataset.scopeRef=scope.id;btn.prepend(glyph('file-earmark-text'));tools.append(btn);
        }
        if (tools.childElementCount) aside.append(tools);
      }
      if (months.length) body.append(cal);
      else body.classList.add('without-month');
      body.append(aside);root.append(body);choose(view.selected,{alignMonth:false});
    }
    root.addEventListener('toggle',()=>{view.open=root.open;if (root.open) build();});
    if (root.open) requestAnimationFrame(()=>{if (root.isConnected && root.open) build();});
    return root;
  }
  return {panel,evidence};
})();
