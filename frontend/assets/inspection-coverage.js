// Each selectable device and its readings belong to the originals cited by one H02 finding.
const InspectionCoverage = (() => {
  const legacy = 'inspection-coverage-v1', current = 'inspection-coverage-v4';
  const registerFormats = new Set(['inspection-coverage-v3',current]);
  const formats = new Set([legacy,'inspection-coverage-v2',...registerFormats]);
  const registerStates={register_match:'两份清单的编号逐一相符',register_difference:'合同与终验编号不一致',
    register_duplicate:'编号重复',register_spelling:'编码口径待核',register_incomplete:'完整编号待核',
    register_scope:'适用范围待核',register_source:'原件待核',register_substitution:'代用批准依据待核',register_prohibited:'实收编号与禁止代用条款冲突'};
  const namedKind = 'inspection_required_serials';
  const labels = {
    covered:'检测范围相符', short:'检测台数不足', records:'单机记录待补', repeated:'同台重复',
    count_conflict:'台数记载冲突', out_of_limit:'单机超限', scope:'范围待核', identity:'归属待核',
    source:'原页待核', terms:'抽检约定待核', population:'设备清单待核', count:'实测台数待核',
    criterion:'限值待核', reading:'读数待核', named_scope:'指定范围待核', named_records:'必检读数待补', unknown:'检验依据待核'
  };
  const statuses = {covered:'ok',short:'risk',records:'missing',named_records:'missing',repeated:'risk',count_conflict:'risk',out_of_limit:'issue'};
  const compareText = s => s.replaceAll('℃','°C').replaceAll('，',',').replaceAll('：',':');
  const value = row => row?.quote.split(/[:：]/u).slice(1).join('：').trim() || '';
  const unique = (rows,kind) => {
    const selected = rows.filter(r => r.kind===kind);
    return selected.length===1 ? selected[0] : null;
  };
  function sources(graph) {
    const ledger = graph?.inspection_coverage_sources;
    if (!formats.has(ledger?.format) || !Array.isArray(ledger.rows) || !Array.isArray(ledger.pages)) return [];
    const index = graphIndex(graph);
    const links = new Map(graph.edges.filter(e => e.type==='inspection_coverage_source').map(e => [e.to,e]));
    const parents = new Map(graph.edges.filter(e => e.type==='contains' && e.evidence.includes(e.to)).map(e=>[e.to,e.from]));
    const records = new Map(graph.edges.filter(e => e.type==='records' && e.evidence.includes(e.to)).map(e=>[e.to,e.from]));
    const units = new Map((graph.audit_documents || graph.documents).map(d=>[d.id,d]));
    return ledger.rows.filter(row => {
      if (!row || !Array.isArray(row.facts) || typeof row.quote!=='string' || !Number.isInteger(row.page)) return false;
      const pageId=row.doc+'/p'+row.page, node=index.nodes.get(row.id), link=links.get(row.id);
      const page=index.nodes.get(pageId), doc=index.documents.get(row.doc);
      const unit=units.get(row.unit);
      const id=row.line==null && row.facts.length===1 ? 'inspection-line/'+row.facts[0] :
        'inspection-line/'+pageId+'/l'+row.line;
      if (!doc || !unit || (unit.source || unit.id)!==row.doc || unit.page!=null && unit.page!==row.page ||
          parents.get(pageId)!==row.doc || page?.type!=='page' || row.id!==id || node?.type!=='inspection_line' ||
          node.label!==row.quote || node.doc!==row.doc || node.page!==row.page || node.line!==row.line ||
          !ledger.pages.some(p => p.doc===row.doc && p.unit===row.unit && p.page===row.page &&
            graph.documents_by_kind[p.role]?.includes(row.unit) && p.native===(page.layer==='text') &&
            p.text_only===(page.clause_text_only===true)) || link?.from!==pageId || link.evidence[0]!==pageId ||
          link.evidence.length!==1+row.facts.length) return false;
      return row.facts.every((ref,i) => {
        const f=index.facts.get(ref);
        return records.get(ref)===pageId && link.evidence[i+1]===ref && f?.doc===row.doc && f.page===row.page && (f.unit || f.doc)===row.unit &&
          f.source_sha256===doc.sha256 && f.page_sha256===page.sha256;
      });
    });
  }
  function observation(row,graph) {
    const matches=row.facts.map(id=>graphIndex(graph).facts.get(id)).filter(f => f && typeof f.value==='string' && typeof f.quote==='string' &&
      compareText(f.quote)===compareText(row.quote) && [value(row),row.quote].some(s=>compareText(s)===compareText(f.value)) && (row.line==null ||
        f.source_line?.number===row.line && f.source_line.text===row.quote && f.source_line.rects?.length));
    return matches.length===1 ? matches[0] : null;
  }
  function open(row,graph) {
    const fact=observation(row,graph);
    openPage(row.doc,row.page,fact?.id,fact ? undefined : row.line);
  }

  function quantities(check,rows,roles) {
    if (!formats.has(check?.format) || !(check.state in statuses) || check.status!==statuses[check.state] || !check.limit ||
        !Array.isArray(check.measurements) || !Array.isArray(check.equipment) ||
        rows.some(r=>!r.line || r.disputed)) return false;
    const contract = rows.filter(r=>roles.get(r.unit)==='contract');
    const receipt = rows.filter(r=>roles.get(r.unit)==='acceptance');
    const term=value(unique(contract,'inspection_requirement'));
    const match=term.match(/^(?:至少|不少于)抽检([1-9]\d*)台测温$|^抽检不少于([1-9]\d*)台测温$/u);
    const numberOf = r => {
      const match=value(r).match(/^(0|[1-9]\d*)\s*台$/u);
      return match?Number(match[1]):null;
    };
    const order=numberOf(unique(contract,'ordered'));
    const all=['全部交付设备逐台测温','每台设备均须测温','逐台测温','全部设备逐台测温'].includes(term);
    if (!order || numberOf(unique(receipt,'received'))!==order ||
        check.mode!==(all?'all':match?'sample':null) || check.required!==(all?order:Number(match?.[1] || match?.[2])) ||
        check.required>order || check.declared!==numberOf(unique(receipt,'tested_quantity'))) return false;
    const equipment=value(unique(receipt,'population')).split(/[、，,]/u).map(s=>s.trim());
    if (equipment.length!==order || new Set(equipment).size!==order ||
        equipment.some((id,i)=>id!==check.equipment[i]) || check.equipment.length!==order) return false;
    const limitExp=/^柜温(不高于|不超过|至多|≤|不低于|不少于|至少|≥)(-?\d{1,3}(?:\.\d{1,4})?)\s*(?:℃|°C)$/u;
    const limit=value(unique(contract,'limit')).match(limitExp), basis=value(unique(receipt,'basis')).match(limitExp);
    const upper=op=>['不高于','不超过','至多','≤'].includes(op);
    if (!limit || !basis || upper(limit[1])!==upper(basis[1]) || Number(limit[2])!==Number(basis[2]) ||
        check.limit.value!==limit[2] || check.limit.unit!=='℃' || check.limit.metric!=='柜温' ||
        check.limit.operator!==(upper(limit[1])?'≤':'≥')) return false;
    const readings=receipt.filter(r=>r.kind==='unit_temperature');
    const counts=new Map();
    if (readings.length!==check.measurements.length) return false;
    for (const [i,row] of readings.entries()) {
      const m=check.measurements[i], original=value(row).match(/^([^，,]+)[，,]\s*柜温\s*(-?\d{1,3}(?:\.\d{1,4})?)\s*(?:℃|°C)$/u);
      if (!m || !original || m.row!==row.id || m.serial!==original[1].trim() || !equipment.includes(m.serial) ||
          m.value!==original[2] || m.within!==(upper(limit[1])?Number(m.value)<=Number(limit[2]):Number(m.value)>=Number(limit[2]))) return false;
      counts.set(m.serial,(counts.get(m.serial) || 0)+1);
    }
    if (counts.size!==check.tested) return false;
    if (check.format!==legacy) {
      const splitIds = row => value(row).split(/[、，,]/u).map(s=>s.trim());
      const ordered=contract.filter(r=>r.kind==='ordered_serials');
      const sameList = (a,b) => Array.isArray(b) && a.length===b.length && a.every((s,i)=>s===b[i]);
      if (ordered.length && (ordered.length!==1 || !sameList(splitIds(ordered[0]).sort(),[...equipment].sort()))) return false;
      const named=contract.filter(r=>r.kind===namedKind);
      const fromLabel=rows.filter(r=>/^(?:必检设备编号|指定抽检设备编号|必测设备编号)\s*[:：]/u.test(r.quote));
      if (rows.some(r=>r.kind==='note') || named.length!==fromLabel.length || named.length>1 ||
          rows.some(r=>r.kind===namedKind && !named.includes(r))) return false;
      if (named.length) {
        const row=named[0], expected=splitIds(row);
        if (row!==fromLabel[0] || check.named?.row!==row.id || new Set(expected).size!==expected.length ||
            expected.some(s=>!equipment.includes(s)) || !sameList(expected,check.named.equipment) ||
            !sameList(expected.filter(s=>!counts.has(s)),check.named.missing)) return false;
      } else if (check.named!==undefined) return false;
    } else if (check.named!==undefined) return false;
    const {declared,required,tested}=check;
    let state='covered';
    if (check.measurements.some(m=>!m.within && counts.get(m.serial)===1)) state='out_of_limit';
    else if ([...counts.values()].some(n=>n>1)) state='repeated';
    else if (declared!=null && declared<tested) state='count_conflict';
    else if (declared!=null && declared<required) state='short';
    else if (tested<required || declared!=null && declared!==tested) state='records';
    else if (check.named?.missing.length) state='named_records';
    return state===check.state;
  }

  function element(tag,text,cls) {
    const node=document.createElement(tag);
    if (text) node.textContent=text;
    if (cls) node.className=cls;
    return node;
  }
  function deviceView(check,rows,makeSource,{expanded=false,publicSample=false,excerpt}={}) {
    const panel=element('details',null,'inspection-panel');
    panel.open=expanded;
    panel.dataset.inspectionState=check.state;
    if (check.mode) panel.dataset.inspectionMode=check.mode;
    const head=element('summary'), icon=element('i',null,'ui-glyph ic-card-checklist');
    icon.setAttribute('aria-hidden','true');
    const title=check.mode==='all'?'逐台测温':check.mode==='sample'?'抽检测温':'设备检验';
    head.append(icon,element('strong',title),element('span',labels[check.state] || labels.unknown,'inspection-state'));
    panel.append(head);
    const body=element('div',null,'inspection-body');
    panel.append(body);
    const numeric=check.tested!=null && check.state in statuses;
    const terms=unique(rows,'inspection_requirement'), list=unique(rows,'population'), limit=unique(rows,'limit');
    const namedRows=rows.filter(r=>r.kind===namedKind);
    function source(parent,row,label,showLine=false) {
      if (!row) return;
      const button=makeSource(row,label);
      if (!button) return;
      button.classList.add('inspection-source');
      button.dataset.inspectionSource=row.id;
      const icon=element('i',null,'ui-glyph ic-arrows-angle-expand');
      icon.setAttribute('aria-hidden','true');
      button.append(icon);
      if (showLine) {
        button.classList.add('inspection-original');
        const location='第 '+row.page+' 页 · '+row.line+' 行';
        button.setAttribute('aria-label',label+'，'+location+'，'+row.quote);
        const strip=element('span',row.quote,'inspection-strip');
        button.append(element('small',location),strip);
        if (excerpt) Promise.resolve().then(()=>excerpt(row)).then(image=>{
          if (image) {image.setAttribute('aria-hidden','true'); strip.replaceChildren(image);}
        }).catch(()=>{});
      }
      parent.append(button);
    }
    if (!numeric) {
      const links=element('div',null,'inspection-links');
      for (const row of namedRows) source(links,row,namedRows.length===1?'必检原行':'必检原行 · 第 '+(row.line || '待核')+' 行');
      source(links,terms,'检测约定'); source(links,list,'设备清单');
      if (links.childElementCount) body.append(links);
      return panel;
    }
    const requiredIds=new Set(check.named?.equipment || []);
    const metric=element('div',null,'inspection-metric');
    if (check.named) {
      metric.classList.add('inspection-comparison');
      function total(label,actual,target,description,attention) {
        const group=element('div',null,'inspection-total');
        const numbers=element('div',null,'inspection-numbers');
        numbers.append(element('strong',String(actual)),element('span',description,'inspection-required'));
        const meter=element('meter');
        meter.min=0; meter.max=target; meter.value=Math.min(target,actual);
        meter.setAttribute('aria-label',label);
        meter.setAttribute('aria-valuetext',actual+' 台有读数，'+description);
        if (attention) group.dataset.attention='true';
        group.append(element('span',label),numbers,meter); metric.append(group);
      }
      total('实测设备',check.tested,check.required,(check.mode==='sample'?'至少 ':'应检 ')+check.required+' 台',check.tested<check.required);
      total('必检设备有读数',requiredIds.size-check.named.missing.length,requiredIds.size,'共 '+requiredIds.size+' 台',check.named.missing.length>0);
    } else {
      metric.append(element('span','有读数'),element('strong',String(check.tested)),element('span','台'),
        element('span','合同应检 '+(check.mode==='sample'?'至少 ':'')+check.required+' 台','inspection-required'));
    }
    if (check.declared!=null && (check.declared!==check.tested || check.state==='short')) {
      source(metric,unique(rows,'tested_quantity'),'验收单记载 '+check.declared+' 台');
    }
    body.append(metric);
    const byDevice=new Map(check.equipment.map(code=>[code,[]]));
    for (const m of check.measurements) byDevice.get(m.serial).push(m);
    const batch=check.equipment;
    const stateOf = records => records.length>1?'repeat':!records.length?'empty':records[0].within?'read':'over';
    const describe = records => records.length>1?records.length+' 条读数':!records.length?'未列读数':records[0].value+' ℃';
    let selected=batch.find(id=>stateOf(byDevice.get(id))==='over') || batch.find(id=>stateOf(byDevice.get(id))==='repeat') ||
      check.named?.missing[0] || (check.mode==='all' && batch.find(id=>!byDevice.get(id).length)) ||
      check.named?.equipment[0] || batch.find(id=>byDevice.get(id).length) || batch[0];
    const prefix=(publicSample?'sample':'workpaper')+(check.named?'-named':'')+'-inspection';
    const controls=element('div',null,'inspection-devices'), detail=element('div',null,'inspection-selection');
    const options=element('div',null,'inspection-filter');
    let picker=null;
    function showDevices(onlyNamed) {
      const devices=onlyNamed?check.named.equipment:batch;
      controls.replaceChildren(); picker=null;
      for (const b of options.children) {
        const active=(b.dataset.scope==='named')===onlyNamed;
        b.setAttribute('aria-pressed',String(active)); b.tabIndex=active?0:-1;
      }
      if (devices.length>6) {
        controls.removeAttribute('role'); controls.removeAttribute('aria-label');
        detail.removeAttribute('role'); detail.removeAttribute('aria-labelledby');
        picker=element('select');
        picker.setAttribute('aria-label','选择验收设备');
        for (const id of devices) picker.add(new Option(id+(requiredIds.has(id)?' · 必检':'')+' · '+describe(byDevice.get(id)),id));
        picker.addEventListener('change',()=>select(picker.value));
        controls.append(picker);
      } else {
        controls.setAttribute('role','tablist'); controls.setAttribute('aria-label','验收设备编号');
        detail.setAttribute('role','tabpanel'); detail.id=prefix+'-readings';
        devices.forEach((id,i)=>{
          const records=byDevice.get(id), button=element('button');
          button.type='button'; button.id=prefix+'-device-'+i; button.dataset.device=id;
          button.dataset.reading=stateOf(records); button.setAttribute('role','tab'); button.setAttribute('aria-controls',detail.id);
          button.append(element('strong',id),element('span',describe(records)));
          if (requiredIds.has(id)) {
            button.dataset.required='true';
            if (!onlyNamed) button.append(element('small','必检','inspection-named-mark'));
          }
          if (button.dataset.reading==='over') button.append(element('small','超限'));
          button.addEventListener('click',()=>select(id));
          button.addEventListener('keydown',event=>{
            const next={ArrowRight:(i+1)%devices.length,ArrowLeft:(i+devices.length-1)%devices.length,Home:0,End:devices.length-1}[event.key];
            if (next===undefined) return;
            event.preventDefault(); select(devices[next]); controls.children[next].focus();
          });
          controls.append(button);
        });
      }
      select(devices.includes(selected)?selected:devices[0]);
    }
    function select(id) {
      selected=id; panel.dataset.selectedDevice=id;
      if (picker) picker.value=id;
      else for (const b of controls.children) {
        const active=b.dataset.device===id;
        b.setAttribute('aria-selected',String(active)); b.tabIndex=active?0:-1;
        if (active) detail.setAttribute('aria-labelledby',b.id);
      }
      detail.replaceChildren();
      const readings=byDevice.get(id), links=element('div',null,'inspection-links');
      if (requiredIds.has(id)) {
        const pair=element('div',null,'inspection-proof-pair');
        source(pair,namedRows[0],'合同点名',true);
        if (readings.length) {
          for (const m of readings) source(pair,rows.find(r=>r.id===m.row),'验收读数',true);
          source(links,limit,'合同 '+check.limit.operator+' '+check.limit.value+' ℃');
        } else source(pair,list,'验收设备清单',true);
        detail.append(pair);
        if (links.childElementCount) detail.append(links);
        return;
      }
      const label=readings.length>1?'同台有 '+readings.length+' 条读数':readings.length?'单机记录':'验收清单内，未列单机读数';
      detail.append(element('span',id+' · '+label,'inspection-selection-label'),links);
      for (const m of readings) source(links,rows.find(r=>r.id===m.row),'实测 '+m.value+' ℃');
      if (!readings.length) source(links,list,'设备清单');
      if (readings.length) source(links,limit,'合同 '+check.limit.operator+' '+check.limit.value+' ℃');
      source(links,terms,'检测约定');
    }
    if (requiredIds.size && requiredIds.size<batch.length) {
      options.setAttribute('role','group'); options.setAttribute('aria-label','筛选验收设备');
      for (const [scope,label] of [['named','合同必检'],['all','全部设备']]) {
        const b=element('button',label); b.type='button'; b.dataset.scope=scope;
        b.append(element('span',String(scope==='named'?requiredIds.size:batch.length)));
        b.addEventListener('click',()=>showDevices(scope==='named')); options.append(b);
        b.addEventListener('keydown',event=>{
          const next={Home:'named',End:'all',ArrowLeft:scope==='named'?'all':'named',ArrowRight:scope==='named'?'all':'named'}[event.key];
          if (next===undefined) return;
          event.preventDefault(); showDevices(next==='named'); options.querySelector('[aria-pressed=true]').focus();
        });
      }
      body.append(options);
    }
    body.append(controls,detail); showDevices(requiredIds.has(selected));
    return panel;
  }
  function relatedPayments(graph,findings,proof) {
    const index=graphIndex(graph);
    const linked=findings.filter(f=>{
      if (!['H04','H05'].includes(f.rule) || !f.stage?.clause_ref) return false;
      const refs=traceReferences(graph,f);
      return index.facts.get(f.stage.clause_ref)?.field==='payment_stage' && refs.includes(f.stage.clause_ref) && refs.includes(proof.named.row);
    });
    const phases=linked.filter(f=>f.rule==='H04');
    if (!phases.length) return null;
    const fold=element('details',null,'inspection-payments');
    const header=element('summary','引用本项验收的期款');
    header.append(element('span',phases.length+' 期')); fold.append(header);
    for (const phase of phases) {
      const bank=linked.filter(f=>f.rule==='H05' && PhaseEvidence.sameStage(f.stage,phase.stage));
      const payments=element('div',null,'inspection-phase');
      payments.dataset.phaseId=phase.id;
      if (bank.length) payments.dataset.hasReceipt='true';
      payments.addEventListener('click',event=>{
        if (event.target.closest('[data-jump-finding]')) payments.dispatchEvent(
          new CustomEvent('select-contract-phase',{bubbles:true,detail:phase.stage.clause_ref}));
      });
      payments.append(performanceJump(phase,phase.stage.name+' · '+phase.stage.share+'%'));
      for (const item of bank) {
        const docs=graph.documents.filter(d=>item.scope.includes(d.id) && graph.documents_by_kind.bank_receipt?.includes(d.id));
        payments.append(performanceJump(item,bank.length>1 && docs.length===1?docs[0].name:'付款回单'));
      }
      fold.append(payments);
    }
    return fold;
  }
  function registerSources(report,finding=report?.findings.find(f=>f.rule==='H02')) {
    const graph=report?.graph, ledger=graph?.inspection_coverage_sources;
    const accepted=report?.findings.find(f=>f.rule==='H02'), check=accepted?.inspection_coverage;
    if (!finding?.delivery_register || !['H02','H04','H05'].includes(finding.rule) || check?.mode!=='delivery_register' ||
        ledger?.purpose!=='delivery_register' || !registerFormats.has(ledger.format) || check.format!==ledger.format ||
        report.policy.inspection_coverage!==ledger.format || !/^[a-f0-9]{64}$/u.test(report.policy.code_sha256?.['inspection_coverage.py'])) return [];
    const same=(a,b)=>Array.isArray(a) && Array.isArray(b) && a.length===b.length && a.every((x,i)=>x===b[i]);
    if (!same(check.register?.rows,accepted.delivery_register) || !same(finding.delivery_register,accepted.delivery_register)) return [];
    const index=graphIndex(graph), all=sources(graph);
    const rowById=new Map(all.map(r=>[r.id,r]));
    const checked=check.register.rows.map(id=>rowById.get(id)).filter(r=>r &&
      (['ordered_serials','population'].includes(r.kind) || ledger.format===current && r.kind==='substitution') &&
      check.scope.includes(r.unit) && [accepted,finding].every(f=>f.scope.includes(r.unit) &&
        [r.id,r.doc+'/p'+r.page,...r.facts].every(ref=>check.evidence.includes(ref) && f.evidence.includes(ref) &&
          index.supports.get('finding/'+f.id)?.has(ref))));
    if (checked.length!==check.register.rows.length || new Set(check.register.rows).size!==checked.length) return [];
    const codes=r=>value(r).split(/[、,，]/u).map(code=>code.trim());
    const left=unique(checked,'ordered_serials'), right=unique(checked,'population');
    const fromContract=left?codes(left):[], fromReceipt=right?codes(right):[];
    const onlyLeft=fromContract.filter(code=>!fromReceipt.includes(code)), onlyRight=fromReceipt.filter(code=>!fromContract.includes(code));
    const conflict=['register_difference','register_prohibited'].includes(check.state);
    const differences=conflict && same(onlyLeft,check.register.contract_only) && same(onlyRight,check.register.receipt_only);
    const notes=checked.filter(r=>r.kind==='substitution');
    const mentioned=new Set(notes.flatMap(r=>r.quote.match(/[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*/gu) || []));
    const citedCodes=[...new Set([...fromContract,...fromReceipt])].filter(code=>mentioned.has(code));
    if (check.state==='register_substitution' && (!notes.length || check.status!=='missing')) return [];
    if (check.state==='register_prohibited') {
      const clause=notes[0], equipment='([A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)';
      const ban=clause?.quote.match(new RegExp('^(?:供货约定|设备代用约定|交付约定)[:：]\\s*(?:不得|禁止|严禁)(?:以|用)\\s*'+equipment+'\\s*(?:代替|替代)\\s*'+equipment+'[。.]?\\s*$','u'));
      if (notes.length!==1 || clause?.unit!==left?.unit || check.status!=='issue' || !ban ||
          !same(onlyRight,[ban[1]]) || !same(onlyLeft,[ban[2]])) return [];
    }
    const compared=conflict || ['register_match','register_duplicate','register_spelling'].includes(check.state);
    if (compared) {
      const duplicate=[fromContract,fromReceipt].some(ids=>new Set(ids).size!==ids.length);
      const quantity=kind=>value(unique(all,kind)).match(/^([1-9][0-9]*)\s*台$/u)?.[1];
      if (!left || !right || ledger.pages.length!==2 || ledger.pages.some(p=>!p.native || !p.text_only) ||
          all.length!==ledger.rows.length || all.some(r=>!r.line || r.disputed || r.kind==='serial_note') ||
          Number(quantity('ordered'))!==fromContract.length || Number(quantity('received'))!==fromReceipt.length ||
          fromContract.length!==fromReceipt.length || (check.state==='register_duplicate')!==duplicate ||
          check.state==='register_match' && (onlyLeft.length || onlyRight.length) ||
          conflict && (!onlyLeft.length || !onlyRight.length || !differences)) return [];
    }
    const result=checked.map(row=>{
      const page=row.doc+'/p'+row.page, physical=index.nodes.get(page);
      const call=report.calls.pages.find(p=>p.doc===row.doc && p.page===row.page);
      const rects=call?.delivery_register_rects?.[row.line];
      const role=ledger.pages.find(p=>p.unit===row.unit && p.doc===row.doc && p.page===row.page)?.role;
      const note=row.kind==='substitution';
      if (!(note?['contract','acceptance','contract_addendum'].includes(role):role===(row.kind==='ordered_serials'?'contract':'acceptance')) ||
          !graph.documents_by_kind[role]?.includes(row.unit) || call?.page_sha256!==physical?.sha256 ||
          row.line!=null && (!Array.isArray(rects) || !rects.length || !rects.every(b=>Array.isArray(b) && b.length===4 &&
            b.every(n=>Number.isFinite(n) && n>=0 && n<=1) && b[0]<b[2] && b[1]<b[3]))) return null;
      const label=note?{contract:'合同代用约定',acceptance:'验收代用说明',contract_addendum:'补充协议条款'}[role]:role==='contract'?'合同约定编号':'终验实收编号';
      const tokens=codes(row);
      const marks=check.state==='register_substitution'?citedCodes:differences?(note?[...onlyLeft,...onlyRight]:role==='contract'?onlyLeft:onlyRight):
        check.state==='register_duplicate'?tokens.filter((code,i)=>tokens.indexOf(code)!==i):[];
      return {ref:row.id,doc:index.documents.get(row.doc),page:row.page,rawLine:row.line,quote:row.quote,
        rects:rects || [],fact:row.facts.length===1?row.facts[0]:null,label,marks,substitution:note,
        quality:'delivery_register_source',option:label+(row.line?' · 第 '+row.line+' 行':' · 页图')};
    });
    return result.includes(null)?[]:result;
  }
  function registerControls(report,finding,pin=true) {
    const lines=registerSources(report,finding);
    if (!lines.length) return null;
    const group=element('div',null,'delivery-register-lines');
    const check=report.findings.find(f=>f.rule==='H02').inspection_coverage;
    if (check.state==='register_substitution') group.classList.add('register-approval');
    group.setAttribute('role','group');group.setAttribute('aria-label',lines.some(s=>s.substitution)?'设备编号及代用原文':'合同与终验设备编号');
    if (pin) {
      group.append(element('strong',registerStates[check.state] || '设备清单待核','register-outcome'));
    }
    for (const line of lines) group.append(workpaperLineButton(line,finding,pin));
    return group;
  }
  function panel(finding,graph,findings=[]) {
    const check=finding?.inspection_coverage;
    if (finding?.rule!=='H02' || !formats.has(check?.format)) return null;
    const index=graphIndex(graph), supports=index.supports.get('finding/'+finding.id);
    const ledger=graph.inspection_coverage_sources;
    const rows=sources(graph).filter(r=>[r.id,r.doc+'/p'+r.page,...r.facts].every(ref=>
      supports?.has(ref) && finding.evidence.includes(ref) && check.evidence?.includes(ref)) && finding.scope.includes(r.unit));
    const roles=new Map((Array.isArray(ledger?.pages)?ledger.pages:[]).map(p=>[p.unit,p.role]));
    const bound=rows.length>0 && check.format===ledger?.format && rows.length===ledger.rows.length &&
      check.evidence.every(ref=>finding.evidence.includes(ref) && supports?.has(ref)) &&
      [...roles.keys()].every(unit=>finding.scope.includes(unit) && check.scope?.includes(unit));
    if (check.mode==='delivery_register') {
      const card=element('details',null,'inspection-panel');
      card.id='inspection-coverage';card.tabIndex=-1;card.open=check.state!=='register_match';
      const controls=bound && registerControls(state.bundle.report,finding,false);
      const head=element('summary');
      head.append(element('strong','合同与终验设备编号'),element('span',controls && registerStates[check.state] || '原件待核','inspection-state'));
      card.append(head);
      if (controls) {const body=element('div',null,'inspection-body');body.append(controls);card.append(body);}
      return card;
    }
    let display=check;
    if (!bound || check.state in statuses && (!quantities(check,rows,roles) || ledger.pages.some(p=>!p.native || !p.text_only))) {
      display={state:'unknown',mode:null,tested:null};
    }
    const card=deviceView(display,rows,(r,label)=>action(label,()=>open(r,graph)),{expanded:display.state!=='covered',
      excerpt:r=>{
        const fact=observation(r,graph);
        return fact?.source_line?.rects?.length?EvidenceCompare.lineExcerpt(fact,index):null;
      }});
    card.id='inspection-coverage'; card.tabIndex=-1;
    if (display.named) {
      const payments=relatedPayments(graph,findings,display);
      if (payments) card.querySelector('.inspection-body').append(payments);
    }
    if (display.state==='unknown' && !card.querySelector('.inspection-source')) {
      const jump=action('查看交付验收检查',()=>revealPaperTarget(document.querySelector('[data-finding="'+CSS.escape(finding.id)+'"]')),'inspection-source');
      card.querySelector('.inspection-body').append(jump);
    }
    return card;
  }
  return {panel,sources,observation,open,deviceView,quantities,registerSources,registerControls};
})();
