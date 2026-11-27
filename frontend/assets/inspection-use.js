// A payment restriction can be present on the original even when neither reader transcribed it as a field.
const InspectionUse = (() => {
  const firstFormat='cited-inspection-payment-use-v1', crossFormat='cited-inspection-payment-use-v2', approvalFormat='cited-inspection-payment-use-v3', clockFormat='cited-inspection-payment-use-v4';
  const labels={ban:'与回单用途冲突',approval:'另行审批待核',conditional:'签字条件待核',unclear:'适用范围待核',
    other_document:'附注来自另一份单据',other_stage:'附注属于其他期次'};
  const same=(left,right)=>Array.isArray(left) && Array.isArray(right) && left.length===right.length && left.every((v,i)=>v===right[i]);
  const validRect=r=>Array.isArray(r) && r.length===4 && r.every(v=>Number.isFinite(v) && v>=0 && v<=1) && r[0]<r[2] && r[1]<r[3];

  function receipt(item,report) {
    const r=item.retest_reference;
    if (r && ['original','final'].includes(r.state) && RetestReference.bind(item,report)) {
      return {bank:r.bank,cited:r.units[r.state],number:r.number,citation:r.fields.citation,
        own:r.fields[r.state+'_acceptance_number'],units:[r.units.original,r.units.final]};
    }
    const b=item.payment_acceptance;
    if (b && ['matched','other_batch'].includes(b.state) && PaymentAcceptance.itemsFor(report).some(p=>p.key===item.id && p.state===b.state)) {
      const [cited]=b.cited;
      return {bank:b.bank,cited,number:b.number,citation:b.citations[0],
        own:b.register.find(x=>x.unit===cited).number_row,units:b.register.map(x=>x.unit)};
    }
    return null;
  }

  function original(r,report,evidence) {
    const prefix=r.id.split('/')[0], kind={'payment-approval':'payment_approval','inspection-use':'inspection_use','payment-clock':'payment_clock','contract-approver':'contract_approver','approval-change':'approval_change'}[prefix];
    if (!kind) return null;
    const g=report.graph, idx=graphIndex(g);
    const pageId=r.doc+'/p'+r.page, node=idx.nodes.get(r.id), page=idx.nodes.get(pageId);
    const calls=report.calls?.pages?.filter(p=>p.doc===r.doc && p.page===r.page);
    const doc=calls?.length===1 && issuedPageDocument(g,calls[0]);
    const source=g.edges.filter(e=>e.type===kind+'_source' && e.to===r.id);
    const owner=g.audit_documents?.find(d=>d.source===r.doc && d.page===r.page)?.id || r.doc;
    if (!doc || owner!==r.unit || !Number.isSafeInteger(r.line) || r.line<1 ||
        r.id!==prefix+'/'+pageId+'/l'+r.line || node?.type!==kind+'_line' || node.doc!==r.doc ||
        node.page!==r.page || node.line!==r.line || node.label!==r.quote || !r.quote || page?.layer!=='text' ||
        !page.text_sha256 || page.sha256!==r.page_sha256 || !Array.isArray(r.rects) || !r.rects.every(validRect) ||
        JSON.stringify(calls[0].inspection_use_rects?.[r.line] || [])!==JSON.stringify(r.rects) || !Array.isArray(r.facts) ||
        ![r.id,pageId,...r.facts].every(id=>evidence.includes(id)) || source.length!==1 || source[0].from!==pageId ||
        !same(source[0].evidence,[pageId,...r.facts]) || !r.facts.every(id=>{
          const f=idx.facts.get(id);
          return f?.doc===doc.id && f.page===r.page && f.page_sha256===r.page_sha256 && f.source_sha256===doc.sha256 &&
            f.source_line?.number===r.line && f.source_line.text===r.quote;
        })) return null;
    return doc;
  }

  function bind(item,report) {
    const c=item.inspection_use;
    if (!c || item.rule!=='H05' || item.execution_basis || !Object.hasOwn(labels,c.state) || !([firstFormat,crossFormat,approvalFormat,clockFormat].includes(c.format) || ApprovalNames.supports(c.format)) ||
        report.policy.inspection_use!==c.format || !/^[a-f0-9]{64}$/u.test(report.policy.code_sha256?.['inspection_use.py'])) return null;
    const g=report.graph, idx=graphIndex(g), ledger=g.inspection_use_sources, link=receipt(item,report);
    const node=idx.nodes.get('finding/'+item.id), supported=new Set(traceReferences(g,item));
    if (!link || c.cited!==link.cited || c.number!==link.number || c.bank!==link.bank || c.citation!==link.citation ||
        c.number_ref!==link.own || !item.stage?.clause_ref || node?.detail!==item.detail || node.status!==item.status ||
        ledger?.format!==c.format || !Array.isArray(ledger.rows) || !Array.isArray(c.notes) || !c.notes.length ||
        !Array.isArray(c.evidence) || !c.evidence.every(ref=>supported.has(ref)) ||
        ![c.citation,c.number_ref,item.stage.clause_ref].every(ref=>c.evidence.includes(ref))) return null;
    const rows=ledger.rows.filter(r=>link.units.includes(r.unit));
    if (!same(rows.map(r=>r.id),c.notes.map(n=>n.row))) return null;
    const edges=g.edges.filter(e=>e.type==='cites_inspection_use' && e.from===c.citation);
    const expected=c.notes.filter(n=>n.scope==='cited').map(n=>n.row);
    if (!same(edges.map(e=>e.to),expected) || edges.some(e=>!same(e.evidence,[c.citation,c.number_ref,e.to]))) return null;
    const stage=/^第([\d零一二两三四五六七八九十]+)期$/u.exec(item.stage.name);
    const bound=[], active=[];
    for (const [i,r] of rows.entries()) {
      const doc=item.scope.includes(r.unit) && r.id.startsWith('inspection-use/') && original(r,report,c.evidence);
      if (!doc) return null;
      let scope='cited';
      const review=g.acceptance_word_reviews?.documents?.some(d=>d.units.includes(r.unit) && (d.notes.length || d.coverage!=='complete'));
      const applies=stage && (r.index==null || (c.format===approvalFormat || ApprovalClock.supports(c.format) ? BatchPhase.ordinal(stage[1])===r.index :
        BatchPhase.sameOrdinal(stage[1],r.index) || /^\d+$/u.test(stage[1]) && Number(stage[1])===r.index));
      if (r.unit!==c.cited) {
        const foreignTitle=r.unit===item.retest_reference?.units?.original && /本复验(?:单|报告)/u.test(r.quote);
        const local=c.format===firstFormat ? r.kind!=='approval' || /本(?:单|报告|复验单|复验报告|验收单|验收报告)/u.test(r.quote) :
          ['ban','conditional'].includes(r.kind) && r.rects.length && !(r.disputed || foreignTitle || review);
        scope=local?'other_document':'unresolved';
      }
      else if (r.disputed || !r.rects.length || review) scope='unresolved';
      else if (stage && r.index && !applies) scope='other_stage';
      else if (!stage || !['ban','approval','conditional'].includes(r.kind) || (r.role!=null && r.role!=='验收款')) scope='unresolved';
      if (c.notes[i].scope!==scope) return null;
      if (scope==='cited' || scope==='unresolved') active.push(scope==='cited'?r.kind:'unclear');
      bound.push({row:r,doc,scope});
    }
    const outcome=active.length===1?active[0]:active.length?'unclear':bound.every(b=>b.scope==='other_document')?'other_document':'other_stage';
    if (outcome!==c.state) return null;
    const requiresComparison=(c.format===approvalFormat || ApprovalClock.supports(c.format)) && outcome==='approval' && ledger.approvals?.length>0;
    if (Boolean(c.approval)!==Boolean(requiresComparison)) return null;
    if (requiresComparison) {
      const request=bound.find(b=>b.scope==='cited' && b.row.kind==='approval')?.row;
      const entries=InstallmentApproval.bind(item,report,request,r=>original(r,report,c.evidence));
      if (!entries || c.status!==c.approval.status) return null;
      bound.push(...entries);
    } else if (c.status!==(outcome==='ban'?'risk':active.length?'missing':'ok')) return null;
    return bound;
  }

  function source(row) {
    const label=row.id.startsWith('approval-change/')?'签批变更协议原行':row.id.startsWith('contract-approver/')?'合同签批约定原行':row.id.startsWith('payment-clock/')?'银行时刻原行':row.id.startsWith('payment-approval/')?'付款审批原行':'付款用途原行';
    return {ref:row.id,quote:row.quote,rects:row.rects,label,option:label+' · 第 '+row.line+' 行',
      rawLine:row.line,quality:'inspection_use_source'};
  }
  function pageReferences(paper,doc,page) {
    const ledger=paper?.graph.inspection_use_sources;
    if (!ledger?.rows?.some(r=>r.doc===doc && r.page===page) && !['approvals','bank_clocks','approver_terms','approver_changes'].some(k=>ledger?.[k]?.some(p=>p.doc===doc && p.page===page))) return [];
    const refs=new Map();
    for (const item of paper.findings) {
      for (const {row} of [...(bind(item,paper) || []),...conditions(item,paper),...(ApprovalChange.bind(item,paper) || []),...ApprovalChange.scopeEntries(item,paper)]) {
        if (row.doc===doc && row.page===page && row.rects.length) refs.set(row.id,source(row));
      }
    }
    return [...refs.values()];
  }

  function open({row,doc},report) {
    if (state.bundle?.report!==report) return;
    const options=row.rects.length?{lineHint:row.line,rawRef:row.id,printedSource:source(row)}:{};
    OriginalReader.open(doc,row.page,options);
  }
  function conditions(item,report) {
    if (!ApprovalNames.supports(report.policy.inspection_use) || !['H03','H04','H05'].includes(item.rule) || item.inspection_use?.approval?.names) return [];
    const ledger=report.graph.inspection_use_sources;
    if (ledger?.format!==report.policy.inspection_use || !ApprovalNames.archived(report)) return [];
    const refs=traceReferences(report.graph,item);
    return (ledger.approver_terms || []).flatMap(p=>p.rows.filter(r=>item.evidence.includes(r.id) && refs.includes(r.id) &&
      r.field==='named_clause' && p.complete && r.doc===p.doc && r.page===p.page && r.unit===p.unit).map(row=>({row,doc:original(row,report,item.evidence)})).filter(e=>e.doc));
  }
  function citation(ref,finding,report) {
    if (!report || (finding?.id && !traceReferences(report.graph,finding).includes(ref))) return null;
    const candidates=finding?.id?[finding]:report.findings.filter(f=>f.evidence.includes(ref));
    for (const item of candidates) {
      const entry=(bind(item,report) || []).find(b=>b.row.id===ref) || conditions(item,report).find(b=>b.row.id===ref) ||
        (ApprovalChange.bind(item,report) || []).find(b=>b.row.id===ref) || ApprovalChange.scopeEntries(item,report).find(b=>b.row.id===ref);
      if (entry) {
        const {row,doc}=entry;
        const button=action((row.id.startsWith('approval-change/')?'签批变更':row.id.startsWith('contract-approver/')?'合同签批':row.id.startsWith('payment-clock/')?'银行时刻':row.field?'付款审批':'付款用途')+' · '+doc.name+' · 第 '+row.page+' 页'+(row.rects.length?' · 第 '+row.line+' 行':''),()=>open(entry,report),'ref');
        button.dataset.useRef=ref;button.title=row.quote;
        return button;
      }
    }
    return null;
  }
  function panel(item,report,rev) {
    const bound=bind(item,report);
    if (!bound) return item.inspection_use?.approval ? el('p','付款审批的原件定位待核。','muted') : null;
    const c=item.inspection_use, root=el('section','','inspection-use');
    root.id='inspection-use-'+item.id;root.setAttribute('aria-label','验收单的付款用途');
    Object.assign(root.dataset,{useFinding:item.id,caseId:report.case_id,rev:String(rev),status:c.status});
    if (c.approval) root.dataset.approval=c.approval.state;
    const cross=c.state==='unclear' && bound.some(b=>b.scope==='unresolved' && b.row.unit!==c.cited);
    root.append(box('inspection-use-heading',el('h4','验收单的付款用途'),el('span',c.approval?'要求另行审批':cross?'附注所指范围待核':labels[c.state])));
    function originalButton(entry) {
      const {row,doc,scope}=entry;
      const place=doc.name+' · 第 '+row.page+' 页'+(row.rects.length?' · 第 '+row.line+' 行':'');
      const button=action('',()=>open(entry,report),'inspection-use-row');
      button.id=(scope==='contract_term'?'contract-approver-'+item.id:scope==='bank_time'?'payment-clock-'+item.id:row.field?'payment-approval-'+item.id:root.id)+'-'+row.doc+'-p'+row.page+'-l'+row.line;
      const subject=row.field ? row.quote.split(/[:：]/u,1)[0].trim() : '付款用途';
      button.dataset.source=row.id;button.dataset.scope=scope;button.dataset.originalLabel=subject+' · '+place;
      button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-controls','page-dialog');
      const compact=row.field && c.approval.fields && c.approval.documents.length===1;
      button.title=place;
      const time=c.approval?.clock && (scope==='bank_time' || row.id===c.approval.clock.signed);
      const names=c.approval?.names;
      const named=names && (scope==='contract_term' || row.id===names.signed_by);
      if (named) {
        const who=scope==='contract_term'?names.required:names.listed;
        button.setAttribute('aria-description',doc.name);
        button.append(el('span',scope==='contract_term'?'合同约定':'审批单具名栏','time-label'),
          el('strong',who?.length?who.join('、'):row.quote),el('small','第 '+row.page+' 页 · 第 '+row.line+' 行'),glyph('arrows-angle-expand'));
      } else if (time) {
        const sep=row.quote.search(/[:：]/u);
        button.append(el('span',subject,'time-label'),el('strong',sep<0?row.quote:row.quote.slice(sep+1).trim()),
          el('small',place),glyph('arrows-angle-expand'));
      } else button.append(el('strong',row.quote),el('small',compact?'原件第 '+row.line+' 行':place),glyph('arrows-angle-expand'));
      return button;
    }
    root.append(...bound.filter(b=>!b.row.field).map(originalButton));
    if (c.approval) root.append(InstallmentApproval.panel(c.approval,bound.filter(b=>b.row.field),originalButton,item.id));
    return root;
  }
  return {bind,panel,pageReferences,citation,original,open};
})();
