// Each selectable device and its readings belong to the originals cited by one H02 finding.
const InspectionCoverage = (() => {
  const format = 'inspection-coverage-v1';
  const labels = {
    covered:'检测范围相符', short:'检测台数不足', records:'单机记录待补', repeated:'同台重复',
    count_conflict:'台数记载冲突', out_of_limit:'单机超限', scope:'范围待核', identity:'归属待核',
    source:'原页待核', terms:'抽检约定待核', population:'设备清单待核', count:'实测台数待核',
    criterion:'限值待核', reading:'读数待核', unknown:'检验依据待核'
  };
  const statuses = {covered:'ok',short:'risk',records:'missing',repeated:'risk',count_conflict:'risk',out_of_limit:'issue'};
  const compareText = s => s.replaceAll('℃','°C').replaceAll('，',',').replaceAll('：',':');
  const value = row => row?.quote.split(/[:：]/u).slice(1).join('：').trim() || '';
  const unique = (rows,kind) => {
    const selected = rows.filter(r => r.kind===kind);
    return selected.length===1 ? selected[0] : null;
  };
  function sources(graph) {
    const ledger = graph?.inspection_coverage_sources;
    if (ledger?.format!==format || !Array.isArray(ledger.rows) || !Array.isArray(ledger.pages)) return [];
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
    if (!(check?.state in statuses) || check.status!==statuses[check.state] || !check.limit ||
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
    const {declared,required,tested}=check;
    let state='covered';
    if (check.measurements.some(m=>!m.within && counts.get(m.serial)===1)) state='out_of_limit';
    else if ([...counts.values()].some(n=>n>1)) state='repeated';
    else if (declared!=null && declared<tested) state='count_conflict';
    else if (declared!=null && declared<required) state='short';
    else if (tested<required || declared!=null && declared!==tested) state='records';
    return state===check.state;
  }

  function element(tag,text,cls) {
    const node=document.createElement(tag);
    if (text) node.textContent=text;
    if (cls) node.className=cls;
    return node;
  }
  function deviceView(check,rows,makeSource,{expanded=false,publicSample=false}={}) {
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
    function source(parent,row,label) {
      if (!row) return;
      const button=makeSource(row,label);
      if (!button) return;
      button.classList.add('inspection-source');
      button.dataset.inspectionSource=row.id;
      const icon=element('i',null,'ui-glyph ic-arrows-angle-expand');
      icon.setAttribute('aria-hidden','true');
      button.append(icon);
      parent.append(button);
    }
    if (!numeric) {
      const links=element('div',null,'inspection-links');
      source(links,terms,'检测约定'); source(links,list,'设备清单');
      if (links.childElementCount) body.append(links);
      return panel;
    }
    const metric=element('div',null,'inspection-metric');
    metric.append(element('span','有读数'),element('strong',String(check.tested)),element('span','台'),
      element('span','合同应检 '+(check.mode==='sample'?'至少 ':'')+check.required+' 台','inspection-required'));
    if (check.declared!=null && (check.declared!==check.tested || check.state==='short')) {
      source(metric,unique(rows,'tested_quantity'),'验收单记载 '+check.declared+' 台');
    }
    body.append(metric);
    const byDevice=new Map(check.equipment.map(code=>[code,[]]));
    for (const m of check.measurements) byDevice.get(m.serial).push(m);
    const devices=check.equipment;
    const stateOf = records => records.length>1?'repeat':!records.length?'empty':records[0].within?'read':'over';
    const describe = records => records.length>1?records.length+' 条读数':!records.length?'未列读数':records[0].value+' ℃';
    let selected=devices.find(id=>stateOf(byDevice.get(id))==='over') || devices.find(id=>stateOf(byDevice.get(id))==='repeat') ||
      (check.mode==='all' && devices.find(id=>!byDevice.get(id).length)) || devices.find(id=>byDevice.get(id).length) || devices[0];
    const prefix=(publicSample?'sample':'workpaper')+'-inspection';
    const controls=element('div',null,'inspection-devices'), detail=element('div',null,'inspection-selection');
    const useSelect=devices.length>6;
    let picker;
    if (useSelect) {
      picker=element('select');
      picker.setAttribute('aria-label','选择验收设备');
      for (const id of devices) picker.add(new Option(id+' · '+describe(byDevice.get(id)),id));
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
    function select(id) {
      selected=id; panel.dataset.selectedDevice=id;
      if (useSelect) picker.value=id;
      else for (const b of controls.children) {
        const active=b.dataset.device===id;
        b.setAttribute('aria-selected',String(active)); b.tabIndex=active?0:-1;
        if (active) detail.setAttribute('aria-labelledby',b.id);
      }
      detail.replaceChildren();
      const readings=byDevice.get(id), links=element('div',null,'inspection-links');
      const label=readings.length>1?'同台有 '+readings.length+' 条读数':readings.length?'单机记录':'验收清单内，未列单机读数';
      detail.append(element('span',id+' · '+label,'inspection-selection-label'),links);
      for (const m of readings) source(links,rows.find(r=>r.id===m.row),'实测 '+m.value+' ℃');
      if (!readings.length) source(links,list,'设备清单');
      if (readings.length) source(links,limit,'合同 '+check.limit.operator+' '+check.limit.value+' ℃');
      source(links,terms,'检测约定');
    }
    body.append(controls,detail); select(selected);
    return panel;
  }
  function panel(finding,graph) {
    const check=finding?.inspection_coverage;
    if (finding?.rule!=='H02' || check?.format!==format) return null;
    const index=graphIndex(graph), supports=index.supports.get('finding/'+finding.id);
    const ledger=graph.inspection_coverage_sources;
    const rows=sources(graph).filter(r=>[r.id,r.doc+'/p'+r.page,...r.facts].every(ref=>
      supports?.has(ref) && finding.evidence.includes(ref) && check.evidence?.includes(ref)) && finding.scope.includes(r.unit));
    const roles=new Map((Array.isArray(ledger?.pages)?ledger.pages:[]).map(p=>[p.unit,p.role]));
    const bound=rows.length>0 && rows.length===ledger?.rows?.length &&
      check.evidence.every(ref=>finding.evidence.includes(ref) && supports?.has(ref)) &&
      [...roles.keys()].every(unit=>finding.scope.includes(unit) && check.scope?.includes(unit));
    let display=check;
    if (!bound || check.state in statuses && (!quantities(check,rows,roles) || ledger.pages.some(p=>!p.native || !p.text_only))) {
      display={state:'unknown',mode:null,tested:null};
    }
    const card=deviceView(display,rows,(r,label)=>action(label,()=>open(r,graph)),{expanded:display.state!=='covered'});
    if (display.state==='unknown' && !card.querySelector('.inspection-source')) {
      const jump=action('查看交付验收检查',()=>revealPaperTarget(document.querySelector('[data-finding="'+CSS.escape(finding.id)+'"]')),'inspection-source');
      card.querySelector('.inspection-body').append(jump);
    }
    return card;
  }
  return {panel,sources,observation,open,deviceView,quantities};
})();
