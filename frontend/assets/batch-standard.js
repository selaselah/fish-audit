// A changed standard belongs to a single receipt and installment of the issued revision.
const BatchStandard = (() => {
  const labels={
    acceptance_criteria:['约定验收标准','合同验收标准'],previous_criterion:['原验收标准'],
    revised_criterion:['变更后验收标准','新验收标准'],inspection_basis:['检验依据','实测验收标准','实际验收标准'],
    measured_result:['实测结果','检测结果','实测数据'],accepted_on:['验收日期','验收时间'],
    buyer_sealed_on:['甲方盖章日期'],seller_sealed_on:['乙方盖章日期'],
    contract_id:['合同编号','合同号'],base_contract_ref:['原合同编号','原采购合同编号'],
    signed_on:['签约日期','签订日期','签署日期'],effect_on:['实际生效日期','生效确认日期'],valid_until:['合同有效期至','合同有效截止日']
  };
  const normalize=s=>typeof s==='string'?s.normalize('NFKC').trim():'';
  const unit=f=>f.unit || f.doc;
  const body=f=>normalize(f?.source_line?.text).replace(/^[^:]+:\s*/u,'');
  function equalRefs(a,b) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length!==b.length) return false;
    const ids=new Set(a);
    return ids.size===a.length && new Set(b).size===b.length && b.every(id=>ids.has(id));
  }
  const names={original:'按原合同',applied:'按补充协议',pending:'适用版本待核'};
  // The observation can locate a printed row even when its transcribed value cannot be used.
  function printedTarget(f,graph,pages) {
    if (!f) return null;
    const index=graphIndex(graph), pageId=f.doc+'/p'+f.page, owner=unit(f);
    const text=normalize(f.source_line?.text), colon=text.indexOf(':');
    if (colon<1 || !body(f) || labels[f.field] && !labels[f.field].includes(text.slice(0,colon)) ||
        !f.id.startsWith(pageId+'/') || index.documents.get(f.doc)?.name!==f.name ||
        index.nodes.get(pageId)?.layer!=='text' || pages!=null &&
          (!Array.isArray(pages) || !pages.some(p=>p.doc===f.doc && p.page===f.page && p.page_sha256===f.page_sha256)) ||
        !graph.edges.some(e=>e.type==='contains' && e.from===f.doc && e.to===pageId && equalRefs(e.evidence,[pageId]))) return null;
    if (owner!==f.doc) {
      const section=index.nodes.get(owner);
      if (section?.type!=='document_section' || section.source!==f.doc || section.page!==f.page) return null;
    }
    const edges=graph.edges.filter(e=>e.type===f.field && e.evidence?.includes(f.id)), [edge]=edges;
    if (edges.length!==1 || edge.from!==owner || !equalRefs(edge.evidence,[f.id])) return null;
    const target=index.nodes.get(edge.to);
    if (f.field==='delivery_batch' && edge.to===f.id) return target?.type==='observation' && target.label===f.label?target:null;
    const type={contract_id:'contract_number',base_contract_ref:'contract_number',buyer:'party',seller:'party'}[f.field] || f.field;
    return target?.type===type?target:null;
  }
  function readField(f,graph,pages) {
    const target=printedTarget(f,graph,pages);
    if (!target) return null;
    const text=normalize(f.source_line.text), value=body(f);
    return normalize(f.quote)===text && [value,text].includes(normalize(f.value)) && !/[-+.\d]\s+(?=[.\d])/u.test(value) &&
      (target.id===f.id || normalize(target.label)===normalize(f.value))?f:null;
  }
  function resolve({phase,acceptance,graph,pages,batch,row,clause,allocation,stages,accepted,stageRows,acceptedRows}) {
    const st=row.standard, change=acceptance.quality_change, index=graphIndex(graph);
    if (!st || !['original','applied','pending'].includes(st.state) || !change || change.quantity ||
        !Array.isArray(change.units) || !Array.isArray(change.evidence) || !Array.isArray(st.evidence) ||
        !Array.isArray(row.evidence) || new Set(st.evidence).size!==st.evidence.length ||
        !st.evidence.every(ref=>row.evidence.includes(ref) && batch.evidence.includes(ref)) ||
        row.scope_unclear!==false || !st.evidence.includes(row.scope_ref) || !Array.isArray(pages)) return null;
    const contract=unit(clause), receipt=row.unit;
    if (st.evidence.some(ref=>{
      const f=index.facts.get(ref);
      return f && ![contract,receipt,...change.units].includes(unit(f));
    })) return null;
    const owns=u=>[phase.scope,acceptance.scope,batch.scope].every(scope=>Array.isArray(scope) && scope.includes(u));
    if (!owns(contract) || !owns(receipt)) return null;
    function field(f) {
      return f && stages.has(f.id) && accepted.has(f.id)?readField(f,graph,pages):null;
    }
    if (!field(clause) || !field(allocation) || !field(stages.get(row.scope_ref))) return null;
    const refs=new Set(st.evidence);
    function candidate(key,u) {
      const candidates=graph.facts.filter(f=>f.field===key && unit(f)===u && refs.has(f.id));
      if (candidates.length!==1 || (u!==receipt && !change.evidence.includes(candidates[0].id))) return null;
      return candidates[0];
    }
    const one=(key,u)=>field(candidate(key,u));
    function referenced(key,ref) {
      const f=one(key,receipt);
      return f && f.id===ref?f:null;
    }
    const basis=one('inspection_basis',receipt), reading=referenced('measured_result',st.reading_ref);
    const dated=referenced('accepted_on',st.date_ref), day=PhaseEvidence.dateOn(dated);
    const date=day && day===row.date?dated:null;
    const original=one('acceptance_criteria',contract);
    const amendment=change.units.length===1 && change.units[0];
    const related=amendment && owns(amendment) && graph.documents_by_kind?.contract_addendum?.includes(amendment) &&
      [['contract_id','base_contract_ref'],['buyer','buyer'],['seller','seller'],['subject','subject']].every(([a,b])=>{
        const left=one(a,contract), right=one(b,amendment);
        return left && right && body(left)===body(right);
      });
    const revised=related?one('revised_criterion',amendment):null;
    function seal(key) {
      const f=related && one(key,amendment), day=PhaseEvidence.dateOn(f);
      return day && day===change[key]?f:null;
    }
    const buyer=seal('buyer_sealed_on'), seller=seal('seller_sealed_on');
    function stampLine(key,usable) {
      if (usable || !related) return null;
      const f=candidate(key,amendment);
      return f && [stageRows,acceptedRows].every(rows=>rows.some(s=>s.fact===f && s.printedLine)) &&
        printedTarget(f,graph,pages)?f:null;
    }
    const later=buyer && seller && (change.buyer_sealed_on>change.seller_sealed_on?buyer:seller);
    const effective=later && PhaseEvidence.dateOn(later)===st.effective_on && st.effective_on===change.effective_on?st.effective_on:null;
    const sameDay=Boolean(date && effective===day);
    const dateHint=sameDay?'验收与盖章同日，时分待核':!date?'本批单据日期待核':!effective && related?
      (!buyer && seller?'甲方盖章日期待核':buyer && !seller?'乙方盖章日期待核':'协议生效日待核'):'';
    const model={state:'pending',original,revised,basis,reading,date,buyer,seller,sameDay,dateHint,
      buyerLine:stampLine('buyer_sealed_on',buyer),sellerLine:stampLine('seller_sealed_on',seller)};
    if (st.state==='pending' || !original || !revised || !basis || !reading || !date || !effective || day===effective ||
        change.state!=='by_batch' || change.scope_clear!==true || st.state!==(day<effective?'original':'applied')) return model;
    const chosen=st.state==='original'?original:revised, previous=one('previous_criterion',amendment);
    const signed=PhaseEvidence.dateOn(one('signed_on',contract)), begins=PhaseEvidence.dateOn(one('effect_on',contract));
    const expires=one('valid_until',contract), end=PhaseEvidence.dateOn(expires);
    if (!signed || !begins || day<=begins || [change.buyer_sealed_on,change.seller_sealed_on].some(s=>s<signed || s<begins) ||
        graph.facts.some(f=>unit(f)===contract && f.field==='valid_until') && (!end || effective>end || day>end) ||
        !previous || body(previous)!==body(original) || body(original)!==normalize(change.original_criterion) ||
        body(revised)!==normalize(change.revised_criterion) || chosen.id!==st.criterion_ref || body(chosen)!==normalize(st.criterion)) return model;
    const edges=graph.edges.filter(e=>e.type==='batch_quality_comparison' && (e.batch===batch.index || e.to===reading.id)), [edge]=edges;
    if (edges.length!==1 || edge.batch!==batch.index || edge.from!==chosen.id || edge.to!==reading.id ||
        edge.version!==st.state || !equalRefs(edge.evidence,st.evidence)) return model;
    const exceeded=row.status==='issue' && batch.status==='issue' && [row.detail,batch.detail,phase.detail].every(d=>
      typeof d==='string' && PerformanceIndex.issuedLimitBreach(d,chosen,reading));
    return {...model,state:st.state,chosen,exceeded,oldBasis:st.state==='applied' && body(basis)===body(original) && body(original)!==body(revised)};
  }
  // A legacy H02 may credit a batch receipt without a corresponding H04 version decision.
  function receipt(acceptance,batch,graph,pages) {
    const ledger=acceptance.batch_acceptance;
    if (!Number.isSafeInteger(batch.index) || batch.index<1 || batch.index>99 || batch.records?.length!==1 ||
        ledger.batches.filter(b=>b.index===batch.index).length!==1) return null;
    const [owner]=batch.records, matches=ledger.records.filter(r=>r.unit===owner), [row]=matches;
    const kinds=graph.documents_by_kind || {};
    if (matches.length!==1 || row.index!==batch.index || row.scope_unclear!=null && row.scope_unclear!==false ||
        ledger.batches.filter(b=>b.records?.includes(owner)).length!==1 ||
        ![kinds.acceptance,kinds.reinspection].some(group=>Array.isArray(group) && group.includes(owner)) ||
        ![acceptance.scope,batch.scope].every(scope=>Array.isArray(scope) && scope.includes(owner))) return null;
    const rows=PerformanceIndex.originals(acceptance,graph).filter(s=>s.line && unit(s.fact)===owner &&
      batch.evidence?.includes(s.fact.id) && row.evidence?.includes(s.fact.id));
    function line(key) {
      const matches=rows.filter(s=>s.fact.field===key);
      return matches.length===1?readField(matches[0].fact,graph,pages):null;
    }
    const scope=line('acceptance_scope');
    if (!scope || scope.id!==row.scope_ref || !BatchPhase.batchPrefix(body(scope),batch.index)) return null;
    return {basis:line('inspection_basis'),reading:line('measured_result'),date:line('accepted_on'),
      fields:new Set(rows.map(s=>s.fact.id))};
  }
  function openPrintedDate(fact) {
    const index=graphIndex(state.bundle.report.graph);
    if (index.facts.get(fact.id)!==fact) return;
    const line=fact.source_line, label=line.text.split(/[:：]/u,1)[0]+'待核';
    const raw={ref:fact.id+'/l'+line.number,label,option:label+' · 第 '+line.number+' 行',quality:'batch_stamp_source',
      rawLine:line.number,quote:line.text,rects:line.rects};
    OriginalReader.open(index.documents.get(fact.doc),fact.page,{lineHint:line.number,rawRef:raw.ref,printedSource:raw});
  }
  function pair(model,index) {
    if (!model) return null;
    let left,right,label;
    if (model.chosen) {left=model.chosen; right=model.reading; label='实测';}
    else if (model.sameDay) {
      left=PhaseEvidence.dateOn(model.buyer)===PhaseEvidence.dateOn(model.date)?model.buyer:model.seller;
      right=model.date; label='同日原件';
    } else {left=model.original; right=model.revised; label='候选标准';}
    return left && right?{key:'batch-'+index,label:'第'+index+'批'+label,left,right,version:model.state}:null;
  }
  function panel(model,source) {
    const view=box('batch-standard');
    view.dataset.version=model.state;
    const heading=box('batch-standard-heading',glyph('layers'),el('strong',names[model.state]));
    if (!model.chosen && model.dateHint) heading.append(el('small',model.dateHint));
    view.append(heading);
    function add(parent,title,f,key,note,open) {
      if (!f) return;
      const button=source(title,f,note,open); button.dataset.standardField=key; parent.append(button);
    }
    add(view,'本批适用标准',model.chosen,'criterion');
    if (!model.chosen && (model.original || model.revised)) {
      const candidates=box('batch-standard-candidates');
      add(candidates,'原合同候选',model.original,'original');
      add(candidates,'补充协议候选',model.revised,'revised');
      view.append(candidates);
    }
    const different=model.basis && model.chosen && body(model.chosen)!==body(model.basis);
    add(view,'报告检验依据',model.basis,'basis',different && (model.oldBasis?'仍引原标准':'与适用标准不符'));
    add(view,'本批实测',model.reading,'reading',model.exceeded && '超出限值');
    const details=fold(model.chosen?'核对版本依据':'核对日期原行');
    for (const [name,label] of [['original','原合同标准'],['revised','协议所列标准'],['date','本批单据日期'],['buyer','甲方盖章日期'],['seller','乙方盖章日期']]) {
      if (model[name]!==model.chosen && (model.chosen || !['original','revised'].includes(name))) add(details,label,model[name],name);
      const raw=model[name+'Line'];
      if (raw) add(details,label,raw,name+'-raw','待核',()=>openPrintedDate(raw));
    }
    if (details.children.length>1) view.append(details);
    return view;
  }
  return {resolve,receipt,pair,panel};
})();
