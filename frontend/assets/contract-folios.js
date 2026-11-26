const ContractFolios = (() => {
  const states = {
    continued:'原页已对应', foreign:'合同号不一致', provisional:'条款待确认', attachment:'附表待确认',
    duplicate:'期次或标题重复', identity:'合同号待核', source:'原页待核', terms:'期次待归入', scope:'条款范围待核',
  };
  const priority = ['foreign','provisional','attachment','duplicate','source','identity','terms','scope'];
  const labels = {
    root_id:'正文合同号', related_id:'续页引用编号', stage:'付款期次', title:'合同标题', heading:'续页标题',
    provisional:'确认状态', qualification:'附加说明', unlocated:'待定位引文', attachment:'附件记载', independent:'首款独立约定',
  };
  const labelsFor = row => row.kind === 'stage' ? row.label : labels[row.kind];
  const bodyNumber = row => row?.quote.match(/^[^：:]+[:：](.*)$/u)?.[1].trim();
  const stateOf = issues => priority.find(s => issues.includes(s)) || 'continued';
  const rectValid = r => Array.isArray(r) && r.length === 4 && r.every(x => Number.isFinite(x) && x >= 0 && x <= 1) && r[2] > r[0] && r[3] > r[1];

  function resolve(finding, graph, calls) {
    const check = finding?.contract_folios, ledger = graph?.contract_folio_sources;
    if (!check || ledger?.format !== 'contract-payment-folios-v1' || !Array.isArray(ledger.pages) ||
        !Array.isArray(ledger.lines) || !Array.isArray(check.pages) || !Array.isArray(finding.evidence)) return null;
    const index = graphIndex(graph), cited = new Set(traceReferences(graph,finding)), unit = check.unit;
    const pages = ledger.pages.filter(p => p.unit === unit), rows = ledger.lines.filter(r => r.unit === unit);
    if (pages.length < 2 || pages.length !== check.pages.length || !index.documents.has(unit)) return null;
    const edges = new Map(graph.edges.filter(e=>e.type === 'contract_folio_basis').map(e=>[e.to,e]));
    const callsByPage = new Map((calls || []).filter(c=>c.doc === unit).map(c=>[c.page,c]));
    const table = new Map(), doc = index.documents.get(unit);
    for (const [i,p] of pages.entries()) {
      const v = check.pages[i], ref = unit+'/p'+p.page, node = index.nodes.get(ref), call = callsByPage.get(p.page);
      if (!v || !Array.isArray(v.lines) || !Array.isArray(v.issues) || !Array.isArray(v.stages) ||
          !node || p.doc !== unit || p.page !== v.page || v.ref !== ref || !cited.has(ref) || node.sha256 !== p.page_sha256 ||
          node.type !== 'page' || call?.page_sha256 !== p.page_sha256 || p.source_sha256 !== doc.sha256 ||
          p.native !== (node.layer === 'text') || p.text_only !== node.clause_text_only ||
          !graph.edges.some(e=>e.type==='contains' && e.from===unit && e.to===ref && e.evidence.includes(ref))) return null;
      const onPage = rows.filter(r=>r.page===p.page);
      if (v.lines.length !== onPage.length || !v.lines.every((s,i)=>s===onPage[i].id)) return null;
      for (const r of onPage) {
        const n = index.nodes.get(r.id), edge = edges.get(r.id);
        if (!labels[r.kind] || !Array.isArray(r.facts) || typeof r.quote!=='string' ||
            r.kind==='stage' && r.label!==r.quote.normalize('NFKC').split(/[:、]/u,1)[0] ||
            !cited.has(r.id) || n?.type !== 'contract_folio_line' || n.label !== r.quote ||
            n.doc !== unit || n.page !== p.page || n.line !== r.line || r.page_sha256 !== p.page_sha256 || r.source_sha256 !== doc.sha256 ||
            edge?.from !== ref || !Array.isArray(edge.evidence) || edge.evidence.length !== r.facts.length+1 || edge.evidence[0] !== ref ||
            r.supported && !(r.line && p.native && p.text_only)) return null;
        if (!r.facts.every((id,i)=>{
          const f = index.facts.get(id);
          return cited.has(id) && edge.evidence[i+1]===id && f?.doc===unit && (f.unit || f.doc)===unit && f.page===p.page &&
            f.page_sha256===p.page_sha256 && f.source_sha256===doc.sha256 && (!r.supported || f.status!=='disputed');
        })) return null;
        const rects = r.line === null ? [] : call.contract_folio_rects?.[r.line];
        if (!Array.isArray(rects) || !rects.every(rectValid)) return null;
        const anchored = r.facts.map(id=>index.facts.get(id)).filter(f=>f.source_line?.text===r.quote && f.source_line.number===r.line);
        if (anchored.some(f=>JSON.stringify(f.source_line.rects)!==JSON.stringify(rects))) return null;
        table.set(r.id,{...r,rects});
      }
      if (v.focus && !v.lines.includes(v.focus) || v.issues.some(issue=>!priority.includes(issue.state) || issue.ref && !v.lines.includes(issue.ref)) ||
          v.state !== stateOf(v.issues.map(s=>s.state)) || JSON.stringify(v.stages)!==JSON.stringify(onPage.filter(r=>r.kind==='stage').map(r=>r.label))) return null;
    }
    const root = table.get(check.root_ref), state = stateOf(check.pages.map(p=>p.state));
    const status = state === 'continued' ? 'ok' : state === 'foreign' ? 'risk' : 'missing';
    if (state !== check.state || status !== check.status || status !== 'ok' && finding.status === 'ok') return null;
    if (['continued','foreign'].includes(state) && (!root?.supported || !root.anchored || !root.number ||
        root.page!==1 || root.kind!=='root_id' || root.number!==bodyNumber(root))) return null;
    if (state==='foreign' && !rows.some(r=>r.page>1 && r.kind==='related_id' && r.supported && r.number &&
        r.number===bodyNumber(r) && r.number!==root.number && check.pages.some(p=>p.issues.some(s=>s.state==='foreign' && s.ref===r.id)))) return null;
    if (state==='continued' && (pages.some(p=>!p.native || !p.text_only) || rows.some(r=>!r.supported ||
        !['root_id','related_id','stage','heading','title','independent'].includes(r.kind) ||
        r.kind==='related_id' && (r.number!==root.number || r.number!==bodyNumber(r))))) return null;
    return {check,table,doc,root};
  }

  const verifiedReports=new WeakMap();
  function current() {
    const r=state.bundle?.report;
    if (!r) return null;
    if (!verifiedReports.has(r)) verifiedReports.set(r,resolve(r.findings.find(f=>f.rule==='H03'),r.graph,r.calls.pages));
    return verifiedReports.get(r);
  }
  function open(row) {
    openPage(row.doc,row.page,row.line ? null : row.facts[0],row.line,null,row.id);
  }
  function pageReferences(doc,page) {
    return [...(current()?.table.values() || [])].filter(r=>r.doc===doc && r.page===page && r.line).map(r=>({
      ref:r.id, label:labelsFor(r), option:'第 '+r.line+' 行 · '+labelsFor(r), rawLine:r.line, quote:r.quote,
      quality:'contract_folio_reference', rects:r.rects,
    }));
  }
  function citation(ref) {
    const row=current()?.table.get(ref);
    return row ? action(row.quote,()=>open(row),'ref') : el('span','合同付款原行待核','small');
  }

  function excerpt(r,index,label,otherNumber) {
    const button = action('',()=>open(r),'folio-excerpt');
    button.dataset.folioRef = r.id;
    const where = '第 '+r.page+' 页'+(r.line?' · 第 '+r.line+' 行':' · 影像引文');
    const frame = box('folio-strip',otherNumber ? printedNumberDifference(r.number,otherNumber) : el('span',r.quote));
    button.append(box('folio-line-head',el('strong',label || labelsFor(r)),el('span',where),glyph('arrows-angle-expand')),frame);
    if (otherNumber) button.append(el('span','，打开所据原页','visually-hidden'));
    else button.setAttribute('aria-label','打开'+(label || labelsFor(r))+'，'+where+'，'+r.quote);
    if (!otherNumber && r.rects.length) {
      EvidenceCompare.lineExcerpt({doc:r.doc,page:r.page,source_line:{rects:r.rects}},index).then(canvas=>{
        if (canvas) frame.replaceChildren(canvas);
      }).catch(()=>{ /* The literal quotation and original-page link remain available. */ });
    }
    return button;
  }

  function unassigned(finding,coverage,graph) {
    if (!coverage || finding.status==='ok') return null;
    const index=graphIndex(graph), cited=new Set(traceReferences(graph,coverage)), plan=traceReferences(graph,finding);
    const known=new Set(Object.values(graph.documents_by_kind).flat()), units=graph.audit_documents || graph.documents;
    const types=new Set(['contract','invoice','acceptance','claim','bank_receipt','warranty','contract_approval','remediation',
      'reinspection','power_of_attorney','contract_addendum','equipment_exchange','payment_release','warranty_ticket']);
    const group=box('folio-attachments'), list=box('folio-attachment-list');
    for (const unit of units.filter(u=>finding.scope.includes(u.id) && !known.has(u.id))) {
      const doc=unit.source || unit.id;
      const byPlan=plan.some(ref=>ref===unit.id || (index.facts.get(ref)?.unit || index.facts.get(ref)?.doc)===unit.id ||
        unit.page && ref===doc+'/p'+unit.page || !unit.page && /^d[0-9]+\/p[0-9]+$/u.test(ref) && ref.startsWith(doc+'/'));
      if (!byPlan) continue;
      const titles=graph.facts.filter(f=>(f.unit || f.doc)===unit.id && types.has(f.field) && cited.has(f.id) &&
        ['visual','disputed','unsupported'].includes(f.status) && f.quote.trim()===f.value.trim());
      for (const f of titles) {
        const ref=doc+'/p'+f.page, page=index.nodes.get(ref);
        if (page?.sha256!==f.page_sha256 || index.documents.get(doc)?.sha256!==f.source_sha256 ||
            !graph.edges.some(e=>e.type==='records' && e.from===ref && e.to===f.id && e.evidence.includes(f.id))) continue;
        const b=action('',()=>openPage(doc,f.page,f.id),'folio-attachment');
        b.dataset.folioTitle=f.id;
        b.append(glyph('file-earmark-text'),el('span',index.documents.get(doc).name),el('small','第 '+f.page+' 页'),glyph('arrows-angle-expand'));
        b.setAttribute('aria-label','核对待归属资料的标题，'+f.name+'，第 '+f.page+' 页，候选引文'+f.quote);
        list.append(b);
      }
    }
    if (!list.childElementCount) return null;
    group.append(el('h4','核对附件标题'),list);
    return group;
  }

  function panel(finding,graph,calls,coverage) {
    if (!finding?.contract_folios) return null;
    const data = resolve(finding,graph,calls), card=el('section','','folio-card');
    card.id='contract-pages'; card.tabIndex=-1; card.setAttribute('aria-label','合同付款续页');
    const title=el('h3','合同付款续页');
    if (!data) {
      card.dataset.folioState='unverified';
      card.append(box('folio-head',title,el('span','证据关系待核','folio-state'))); return card;
    }
    const {check,table,doc,root}=data, index=graphIndex(graph);
    card.dataset.folioState=check.state;
    card.append(box('folio-head',title,el('span',states[check.state],'folio-state')));
    const picker=box('folio-picker'), body=box('folio-reading'), file=box('folio-file',glyph('file-earmark-text'),el('span',doc.name));
    picker.setAttribute('role','group'); picker.setAttribute('aria-label','选择合同原页');
    const position = el('output','','visually-hidden'); position.setAttribute('aria-live','polite');
    const buttons=[], firstProblem=Math.max(0,check.pages.findIndex(p=>p.state===check.state && p.state!=='continued'));
    function select(i,takeFocus=false) {
      const page=check.pages[i], choices=page.lines.map(id=>table.get(id));
      buttons.forEach((b,j)=>{b.setAttribute('aria-pressed',String(i===j)); b.tabIndex=i===j?0:-1;});
      if (takeFocus) buttons[i].focus();
      body.replaceChildren(); body.dataset.folioPage=String(page.page); position.textContent='第 '+page.page+' 页，'+states[page.state];
      if (!choices.length) {
        body.append(action('查看第 '+page.page+' 页原件',()=>openPage(doc.id,page.page),'folio-excerpt')); return;
      }
      const source=box('folio-evidence'), choose=el('select','','folio-select'), modes=box('folio-modes');
      modes.setAttribute('role','group'); modes.setAttribute('aria-label','合同编号对照方式');
      let comparing=false;
      const modeButtons=['原图','比编号'].map((label,i)=>{
        const b=action(label,()=>{comparing=i===1;show(choose.value);}); modes.append(b); return b;
      });
      choose.setAttribute('aria-label','选择本页核对原行');
      choices.forEach(r=>choose.add(new Option(labelsFor(r)+(r.line?' · 第 '+r.line+' 行':''),r.id)));
      function show(id) {
        choose.value=id;
        const r=table.get(id);
        source.replaceChildren();
        const pair=r.kind==='related_id' && root?.supported && root.number===bodyNumber(root) &&
          r.supported && r.number && r.number===bodyNumber(r) && r.number!==root.number;
        modes.hidden=!pair;
        modeButtons.forEach((b,i)=>b.setAttribute('aria-pressed',String(i===(comparing?1:0))));
        if (r.kind==='related_id' && root?.id!==r.id && root) source.append(excerpt(root,index,null,pair && comparing ? r.number : null));
        source.append(excerpt(r,index,null,pair && comparing ? root.number : null));
      }
      choose.addEventListener('change',()=>show(choose.value));
      body.append(box('folio-reading-top',el('strong',i===0?'合同正文':'合同续页'),modes,choose),source);
      show(page.focus || choices[0].id);
    }
    check.pages.forEach((p,i)=>{
      const b=action('',()=>select(i),'folio-page'), pic=el('img');
      pic.alt=''; pic.loading='lazy'; pic.decoding='async'; pic.src=workpaperSource(doc.id,'pages/'+p.page);
      pic.addEventListener('error',()=>pic.replaceWith(glyph('file-earmark-text')),{once:true});
      const name='第 '+p.page+' 页', scope=p.stages.join('、') || (i===0?'合同正文':'补充记载');
      b.append(box('folio-thumb',pic),box('folio-page-copy',el('strong',name),el('small',scope)),el('i','','folio-dot'));
      b.dataset.folioPage=String(p.page); b.dataset.issue=String(p.state!=='continued');
      b.setAttribute('aria-label',name+'，'+scope+'，'+states[p.state]);
      b.addEventListener('keydown',event=>{
        const target={ArrowRight:(i+1)%buttons.length,ArrowDown:(i+1)%buttons.length,ArrowLeft:(i+buttons.length-1)%buttons.length,
          ArrowUp:(i+buttons.length-1)%buttons.length,Home:0,End:buttons.length-1}[event.key];
        if (target!==undefined) {event.preventDefault(); select(target,true);}
      });
      buttons.push(b); picker.append(b);
    });
    card.append(box('folio-layout',box('folio-rail',file,picker),body),position);
    const attachments=unassigned(finding,coverage,graph);
    if (attachments) card.append(attachments);
    select(check.state==='continued'?1:firstProblem);
    return card;
  }
  function independentLink(phase,graph) {
    const data=current(), proof=data?.check.standalone;
    if (!proof || proof.clause_ref!==phase.stage?.clause_ref) return null;
    const row=data.table.get(proof.authority);
    if (!row?.supported || row.kind!=='independent' || row.page!==1 || !traceReferences(graph,phase).includes(row.id)) return null;
    const b=action('首款独立约定',()=>open(row),'compare-jump');
    b.dataset.folioIndependent=row.id; return b;
  }
  return {panel,pageReferences,citation,independentLink};
})();
