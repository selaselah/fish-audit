const PerformanceIndex = (() => {
  const scopes = [
    {id:'contract', label:'签署与生效', icon:'journal-text', rules:['H01']},
    {id:'acceptance', label:'交付验收', icon:'clipboard-check', rules:['H02']},
    {id:'payment', label:'分期与付款', icon:'receipt', rules:['H03','H04','H05','H06','H07']},
  ];
  const includes = finding => scopes.some(scope=>scope.rules.includes(finding.rule));
  function groups(findings) {
    return scopes.map(scope=>{
      const items=findings.filter(f=>scope.rules.includes(f.rule));
      const pending=items.filter(f=>f.status!=='ok');
      return {...scope,items,pending};
    }).filter(group=>group.items.length);
  }
  function count(group) {
    if (!group.pending.length) return group.items.length+' 项相符';
    if (group.pending.length===group.items.length) return group.items.length+' 项待核';
    return group.pending.length+' / '+group.items.length+' 项待核';
  }
  function checkName(item) {
    let label=item.title;
    if (item.execution_basis) label='扣款凭证';
    else if (item.advance_guarantee?.period) label=item.rule==='H05'?'付款日与保函期间':'保函期间约定';
    else if (item.advance_guarantee) label=item.rule==='H05'?'签收与付款日':'预付款收函条件';
    if (item.stage) return item.stage.name+' · '+label;
    if (item.rule==='H05' || item.stage_payments) return '期次待核 · '+label;
    return label;
  }
  function paymentTitle(items,graph) {
    const plan=items.find(f=>f.rule==='H03');
    if (plan?.status!=='ok') return '付款安排';
    const cited=new Set(originals(plan,graph).filter(({fact})=>fact.field==='payment_stage' &&
      ['anchored','confirmed'].includes(fact.status)).map(({fact})=>fact.id));
    const phases=items.filter(f=>f.rule==='H04');
    const refs=phases.map(f=>f.stage?.clause_ref);
    if (!phases.length || new Set(refs).size!==phases.length || cited.size!==phases.length ||
        !phases.every((f,i)=>cited.has(refs[i]) && traceReferences(graph,f).includes(refs[i]))) return '分期与付款';
    if (phases.length>1) return '分 '+phases.length+' 期付款';
    return Number(phases[0].stage.share)===100?'单期付款':'付款安排';
  }
  function fieldLinks(graph) {
    return graphIndex(graph).fieldLinks ??= new Set(graph.edges.filter(e=>e.evidence?.length===1 &&
      ((e.type==='records' && e.evidence[0]===e.to) || (e.type==='supports_result' && e.evidence[0]===e.from)))
      .map(e=>e.from+' '+e.to));
  }
  // Only offer a direct original when the issued finding, observation and physical page agree.
  function originals(item,graph) {
    const index=graphIndex(graph), node=index.nodes.get('finding/'+item.id);
    if (node?.type!=='finding' || node.status!==item.status || node.detail!==item.detail) return [];
    const links=fieldLinks(graph);
    const sources=[];
    for (const ref of new Set(traceReferences(graph,item))) {
      const fact=index.facts.get(ref), observation=index.nodes.get(ref);
      if (!fact || observation?.type!=='observation' || observation.status!==fact.status ||
          typeof fact.quote!=='string' || !fact.quote || !links.has(ref+' '+node.id)) continue;
      const doc=index.documents.get(fact.doc), pageId=fact.doc+'/p'+fact.page, page=index.nodes.get(pageId);
      if (!doc?.sha256 || doc.sha256!==fact.source_sha256 || index.nodes.get(doc.id)?.sha256!==doc.sha256 ||
        page?.type!=='page' || !page.sha256 || fact.page_sha256!==page.sha256 || !links.has(pageId+' '+ref)) continue;
      const loc=fact.source_line;
      const printed=page.layer!=='image' && !MandateOriginals.images.has(doc.ext) && ['anchored','confirmed'].includes(fact.status) &&
        Number.isSafeInteger(loc?.number) && loc.number>0 &&
        typeof loc.text==='string' && loc.text.trim() &&
        Array.isArray(loc.rects) && loc.rects.length && loc.rects.every(rect=>Array.isArray(rect) &&
          rect.length===4 && rect.every(n=>Number.isFinite(n) && n>=0 && n<=1) && rect[0]<rect[2] && rect[1]<rect[3]);
      const exact=printed && loc.text.normalize('NFKC').includes(fact.quote.normalize('NFKC'));
      sources.push({fact,doc,line:exact?loc.number:null,printedLine:printed?loc.number:null});
    }
    return sources;
  }
  function matchesPrintedField(source,report,ledgerRows,unit,field) {
    if (!source?.printedLine) return false;
    const f=source.fact, clause=field==='clause';
    if ((f.unit || f.doc)!==unit || (clause?!['payment_stage','payment_term'].includes(f.field):f.field!==field)) return false;
    const heading=s=>s.split(/[:：]/u,1)[0].trim();
    const matches=ledgerRows.filter(r=>r.unit===unit && r.field===f.field &&
      (!clause || typeof r.quote==='string' && heading(r.quote)===heading(f.source_line.text)));
    const [row]=matches;
    if (matches.length!==1 || row.facts?.length!==1 || row.facts[0]!==f.id || row.doc!==f.doc ||
        row.page!==f.page || row.line!==source.printedLine || row.quote!==f.source_line.text) return false;
    const calls=report.calls?.pages?.filter(p=>p.doc===f.doc && p.page===f.page);
    if (calls?.length!==1) return false;
    const [page]=calls;
    return Boolean(page.response_id && page.check?.response_id && page.page_sha256===f.page_sha256 &&
      issuedPageDocument(report.graph,page)===source.doc);
  }
  function originalButton(id,{fact,doc,printedLine},label,display,cls) {
    const place='第 '+fact.page+' 页 · 第 '+printedLine+' 行';
    const button=action('',()=>openPage(fact.doc,fact.page,fact.id),cls);
    button.id=id;
    button.dataset.source=fact.id;
    button.dataset.originalLabel=[label,doc.name,place].join(' · ');
    button.setAttribute('aria-haspopup','dialog');
    button.setAttribute('aria-controls','page-dialog');
    button.title=doc.name+' · '+place;
    button.append(el('small',label),el('strong',display),glyph('arrows-angle-expand'),el('span',button.title,'visually-hidden'));
    return button;
  }
  function sourceView(item, graph, pdfProofs=[]) {
    const rows=originals(item,graph);
    if (!rows.length) return el('p','本版没有可从此项直接打开的字段引文。','scope-empty');
    const pick=el('select'), fileGroups=new Map();
    pick.setAttribute('aria-label','选择此项检查所引的字段');
    for (const [i,row] of rows.entries()) {
      if (!fileGroups.has(row.doc.id)) {
        const group=el('optgroup'); group.label=row.doc.name; fileGroups.set(row.doc.id,group); pick.append(group);
      }
      const option=el('option',row.fact.label+' · 第 '+row.fact.page+' 页'+(row.line?' '+row.line+' 行':''));
      option.value=String(i); fileGroups.get(row.doc.id).append(option);
    }
    const preferred={
      H01:['effect_clause','buyer_signature','seller_signature'], H02:['acceptance_result','acceptance_scope','acceptance_criteria'],
      H03:['payment_stage','payment_term'], H05:['payment_designation','transfer_status','paid_on'],
    }[item.rule] || [];
    let initial=rows.findIndex(row=>row.fact.id===item.stage?.clause_ref && item.rule==='H04');
    if (item.rule==='H02' && pdfProofs.length &&
        (item.status==='missing' || pdfProofs.some(r=>r.record.state==='mismatch'))) {
      const refs=new Set(pdfProofs.flatMap(r=>r.record.fields));
      initial=rows.findIndex(({fact})=>refs.has(fact.id));
    }
    const authority=item.rule==='H02' && item.acceptance_authority;
    if (authority && item.status!=='ok') {
      const ledger=graph.acceptance_authority_sources;
      const clues=[...(ledger?.clauses || []).filter(s=>!s.native && s.facts?.some(id=>authority.clause_evidence?.includes(id))),
        ...(ledger?.signatures || []).filter(s=>!s.confirmed && authority.records.some(r=>r.unit===s.unit))];
      for (const clue of clues) {
        const hit=rows.findIndex(({fact})=>clue.facts?.includes(fact.id) && fact.doc===clue.doc &&
          fact.page===clue.page && (fact.unit || fact.doc)===clue.unit && fact.quote===clue.quote);
        if (hit>=0) { initial=hit; break; }
      }
    }
    const first=preferred.map(field=>rows.findIndex(row=>row.fact.field===field)).find(i=>i>=0);
    pick.value=String(initial>=0?initial:first??0);
    const quote=el('blockquote'), place=el('span'), quality=box('scope-source-quality'), crop=box('scope-source-crop');
    let preferImage=true, sequence=0;
    const mode=action('',()=>{preferImage=!preferImage; showExcerpt();},'text-button scope-source-mode');
    function showExcerpt() {
      const hasImage=crop.childElementCount>0;
      crop.hidden=!hasImage || !preferImage; quote.classList.toggle('visually-hidden',!crop.hidden);
      mode.hidden=!hasImage; mode.textContent=preferImage?'看文字':'看原行';
    }
    const open=action('',()=>{
      const {fact}=rows[Number(pick.value)]; openPage(fact.doc,fact.page,fact.id);
    },'scope-open-original');
    open.append(glyph('arrows-angle-expand'),el('span','打开原页'));
    open.setAttribute('aria-haspopup','dialog'); open.setAttribute('aria-controls','page-dialog');
    function draw() {
      const request=++sequence;
      const {fact,doc,line}=rows[Number(pick.value)];
      quote.textContent=line?fact.source_line.text:fact.quote;
      place.textContent=doc.name+' · 第 '+fact.page+' 页'+(line?' '+line+' 行':'');
      const status=tag(fact.status);
      const proof=pdfProofs.find(r=>r.record.fields.includes(fact.id));
      if (fact.status==='confirmed' && proof) status.textContent=proof.record.kind==='image'?'图像观察已复核':'栏中文字已核';
      quality.replaceChildren(el('span',line?'原行':'提取引文'),status);
      open.dataset.fact=fact.id;
      crop.replaceChildren(); showExcerpt();
      if (line) EvidenceCompare.lineExcerpt(fact,graphIndex(graph)).then(canvas=>{
        if (canvas && request===sequence && crop.isConnected) {
          crop.replaceChildren(canvas); showExcerpt();
        }
      }).catch(()=>{}); // The archived text and full-page link remain available.
    }
    draw(); pick.addEventListener('change',draw);
    const field=rows.length===1?el('span',rows[0].fact.label,'small'):pick;
    return box('scope-source',box('scope-source-head',el('h4','字段引文'),field),box('scope-excerpt-head',quality,mode),crop,quote,
      box('scope-source-footer',place,open));
  }
  function specialist(item) {
    const target=id=>document.getElementById(id);
    if (item.effect_review?.board_decision && boardProofs(item,state.bundle.report)?.proofs.length) {
      return Team.paperLink('核对董事会审批原件',state.bundle.report.case_id,'text-button',
        new URLSearchParams({rev:state.bundle.rev,view:'board-decision'}));
    }
    if (item.warranty_check?.certificate && warrantyProofs(item,state.bundle.report).length) {
      const bundle=state.bundle;
      return action('核对期满确认单',()=>{if (state.bundle===bundle) WarrantyTimeline.reveal(target('case-panel'),item,bundle.report);},'text-button');
    }
    if (item.payment_opinion?.release?.signature_records?.length &&
        releaseProofs(item,state.bundle.report).length===(item.payment_opinion.release.instruments?.length || 1)) {
      const bundle=state.bundle;
      return action('核对放行原件',()=>{if (state.bundle===bundle) ReleaseEvidence.reveal(target('case-panel'),item,bundle.report);},'text-button');
    }
    if (item.warranty_difference) return WarrantyRegisterEvidence.jump(item);
    if (item.execution_basis && target('payment-proof')) return PaymentProof.jump(item);
    if (item.signer_timing && target('signer-timing')) return SignerEvidence.jump(item);
    if (item.payment_acceptance && target('payment-acceptance')) return PaymentAcceptance.jump(item);
    const areas=[
      [item.rule==='H01' && item.effect_review?.pdf_execution,'pdf-signatures','查看合同签署凭证'],
      [item.rule==='H01' && item.effect_review?.word_signatures,'word-signatures','核对 Word 签章区'],
      [item.acceptance_comments,'acceptance-comments','核对验收批注'],
      [item.inspection_coverage,'inspection-coverage','核对验收范围'],
      [item.reinspection,'equipment-reinspection-trail','核对整改与复验'],
      [item.contract_comments,'contract-comments','核对付款批注'],
      [item.rule==='H03' && item.contract_folios,'contract-pages','核对分期条款原页'],
    ];
    const selected=areas.find(([applies,id])=>applies && target(id));
    return selected?evidenceJump(selected[2],selected[1]):null;
  }
  const pdfSources={
    board:{kinds:['contract_approval'],field:'approval_signer',format:'board-decision-execution-v1',labels:ReleaseCard.states},
    warranty:{kinds:['warranty'],field:'acceptance_signer',format:'warranty-certificate-execution-v1',labels:ReleaseCard.states},
    release:{kinds:['payment_release'],field:'approval_signer',format:'payment-release-execution-v1',labels:ReleaseCard.states},
    addendum:{kinds:['contract_addendum'],field:['buyer_signature','seller_signature'],labels:{
      typeset:'仅见排印文字',visual:'签章影像待核',current:'签名覆盖本版',earlier:'签名覆盖较早版',
      mismatch:'签名校验不符',review:'签署凭证待核'}},
    acceptance:{kinds:['acceptance','reinspection'],field:'acceptance_signer',labels:{
      typeset:'仅见排印文字',visual:'签认图像待核',current:'本版有电子签名，身份待核',
      earlier:'签名覆盖较早版',mismatch:'签名校验不符',review:'签署凭证待核'}},
    mandate:{kinds:['power_of_attorney'],field:'grant_signature',labels:{
      typeset:'仅见排印文字，未检出嵌入式电子签名',visual:'含影像、图形或批注，签章痕迹待核',
      current:'电子签名覆盖本版，签署人身份及权限待核',earlier:'电子签名仅覆盖较早版本',
      mismatch:'电子签名与所签内容校验不符',review:'委托书签章凭证待核'}}
  };
  function unitSource(graph,id,family,kinds,field) {
    const ledger=graph[family+'_sources'], index=graphIndex(graph);
    if (!Array.isArray(ledger?.records)) return null;
    const records=ledger.records.filter(r=>r?.id===id), [record]=records, node=index.nodes.get(id);
    if (records.length!==1 || node?.type!==family+'_inspection' || node.doc!==record.doc || node.state!==record.state ||
        id!==family.replace('_','-')+'/'+record.unit ||
        !Array.isArray(record.pages) || !record.pages.length || !Array.isArray(record.fields)) return null;
    const doc=index.documents.get(record.doc);
    if (!doc || !/^[a-f0-9]{64}$/.test(doc.sha256) || doc.sha256!==record.original_sha256 ||
        doc.sha256!==node.sha256 || index.nodes.get(doc.id)?.type!=='document' || index.nodes.get(doc.id).sha256!==doc.sha256) return null;
    const unit=(graph.audit_documents || graph.documents).find(u=>u.id===record.unit);
    if (!unit || (unit.source || unit.id)!==doc.id || !(kinds.some(k=>graph.documents_by_kind?.[k]?.includes(unit.id)) ||
        kinds.includes('payment_release') && ReleaseEvidence.filedUnit(graph,unit.id))) return null;
    if (!Number.isSafeInteger(doc.pages) || doc.pages<1 || !Number.isSafeInteger(doc.size) || doc.size<1 ||
        record.pages.length!==(unit.source?1:doc.pages) ||
        unit.source && (!Number.isSafeInteger(unit.page) || unit.page<1 || unit.page>doc.pages)) return null;
    if (record.pages.some((p,i)=>!p || p.ref!==doc.id+'/p'+(unit.source?unit.page:i+1))) return null;
    const refs=[doc.id,...record.pages.map(p=>p.ref),...record.fields];
    const edges=graph.edges.filter(e=>e.type===family+'_source' && e.to===id);
    if (new Set(refs).size!==refs.length || edges.length!==1 || edges[0].from!==record.unit ||
        !Array.isArray(edges[0].evidence) || edges[0].evidence.length!==refs.length || !edges[0].evidence.every((ref,i)=>ref===refs[i])) return null;
    if (record.pages.some(p=>index.nodes.get(p.ref)?.type!=='page' || !p.ref.startsWith(doc.id+'/p') ||
        !/^[a-f0-9]{64}$/.test(p.sha256) || index.nodes.get(p.ref).sha256!==p.sha256)) return null;
    const fields=record.fields.map(ref=>index.facts.get(ref));
    const allowed=Array.isArray(field)?field:[field];
    if (fields.some(f=>!f || f.doc!==doc.id || (f.unit || f.doc)!==record.unit || !allowed.includes(f.field) || !Number.isSafeInteger(f.page) ||
        f.source_sha256!==doc.sha256 || !record.pages.some(p=>p.ref===f.doc+'/p'+f.page && p.sha256===f.page_sha256))) return null;
    const first=fields[0], page=first?.page || Number(record.pages[0].ref.split('/p').pop());
    return {record,doc,page,field:first?.id,refs};
  }
  function unitPdfOriginal(graph,id,kind) {
    const family=kind+'_pdf', {kinds,field,labels}=pdfSources[kind];
    if (graph[family+'_sources']?.format!==(pdfSources[kind].format || 'pdf-'+kind+'-execution-v1')) return null;
    const inspected=graphIndex(graph).unitPdfOriginals ??= new Map();
    if (inspected.has(id)) return inspected.get(id);
    const source=unitSource(graph,id,family,kinds,field);
    if (!source || source.doc.ext!=='.pdf') return null;
    const {record,doc}=source;
    if (!Object.hasOwn(labels,record.state) || record.pages.some(p=>
        !['text','image_overlay','unknown'].includes(p.layer) || typeof p.has_text!=='boolean' ||
        typeof p.typeset!=='boolean' || p.typeset && p.layer!=='text')) return null;
    const unsigned=['typeset','visual'].includes(record.state);
    if (unsigned && record.pages.some(p=>p.layer==='unknown') ||
        record.state==='typeset' && (!record.pages.every(p=>p.typeset) || !record.pages.some(p=>p.has_text)) ||
        record.state==='visual' && record.pages.every(p=>p.typeset)) return null;
    const signature={state:unsigned?'unsigned':record.state,size:doc.size,
      original_sha256:doc.sha256,signatures:record.signatures};
    if (!PdfSignatures.validSignatures(signature)) return null;
    const proof={...source,signature,label:labels[record.state]};
    inspected.set(id,proof);
    return proof;
  }
  function receiptButton({record,doc,page,field,label}) {
    const button=action('',()=>openPage(doc.id,page,field),'scope-pdf-receipt');
    button.setAttribute('aria-haspopup','dialog'); button.setAttribute('aria-controls','page-dialog');
    button.append(glyph('file-earmark-text'),el('strong',label),el('small',doc.name+' · 第 '+page+' 页'),glyph('arrows-angle-expand'));
    button.dataset.pdfAcceptance=record.id;
    return button;
  }
  function receiptCitation(graph,id) {
    const proof=unitPdfOriginal(graph,id,'acceptance');
    return proof && receiptButton(proof);
  }
  function issuedReferences(item,graph) {
    const index=graphIndex(graph), finding=index.nodes.get('finding/'+item.id);
    if (finding?.type!=='finding' || finding.status!==item.status || finding.detail!==item.detail || !Array.isArray(item.evidence)) return new Set();
    const supports=index.resultLinks ??= new Set(graph.edges.filter(e=>e.type==='supports_result' &&
      e.evidence?.length===1 && e.evidence[0]===e.from).map(e=>e.from+' '+e.to));
    return new Set(item.evidence.filter(ref=>supports.has(ref+' '+finding.id)));
  }
  function issuedSource(proof,cited,calls) {
    return proof && cited.has(proof.record.id) && proof.refs.every(ref=>cited.has(ref)) && Array.isArray(calls) &&
      proof.record.pages.every(p=>calls.some(c=>c.doc===proof.doc.id && proof.doc.id+'/p'+c.page===p.ref && c.page_sha256===p.sha256));
  }
  function nativeAddendum(graph,id,rows) {
    const fields=['buyer_signature','seller_signature'];
    const source=unitSource(graph,id,'addendum_original',['contract_addendum'],fields);
    if (!source) return null;
    const filed=graph.facts.filter(f=>f.doc===source.doc.id && (f.unit || f.doc)===source.record.unit && fields.includes(f.field));
    if (filed.length!==source.record.fields.length || filed.some((f,i)=>f.id!==source.record.fields[i])) return null;
    return MandateOriginals.bind(graph,source,rows,'addendum');
  }
  function addendumEvidence(report) {
    const {graph,policy}=report;
    const hashed=name=>/^[a-f0-9]{64}$/.test(policy?.code_sha256?.[name]);
    const pdf=policy?.addendum_pdf==='pdf-addendum-execution-v1' && graph.addendum_pdf_sources?.records?.length && hashed('addendum_execution.py');
    const native=policy?.addendum_originals==='addendum-original-execution-v1' && graph.addendum_original_sources?.format===policy.addendum_originals &&
      graph.addendum_original_sources.records?.length && hashed('addendum_originals.py') && hashed('original_records.py');
    if (!pdf && !native) return [];
    const index=graphIndex(graph);
    if (index.addendumEvidence) return index.addendumEvidence;
    const proofs=new Map(), procedures=new Map(), calls=report.calls?.pages || [];
    for (const edge of graph.edges) {
      if (edge.type!=='procedure_result') continue;
      // A second procedure for the same finding makes that binding ambiguous.
      procedures.set(edge.to,procedures.has(edge.to)?null:edge);
    }
    const issued=report.findings.filter(f=>{
      const control=index.nodes.get('control/'+f.rule), edge=procedures.get('finding/'+f.id);
      return f.rule.startsWith('H') && control?.type==='control' && control.version===f.version && Array.isArray(f.evidence) &&
        edge?.from===control.id && edge.evidence?.length===f.evidence.length && edge.evidence.every((ref,i)=>ref===f.evidence[i]);
    });
    for (const owner of issued) for (const change of [owner.quality_change,owner.payment_change]) {
      if (!['H02','H03','H04','H05'].includes(owner.rule) || !change ||
          (change.state || change.applies)!=='pending' || change.effective_on!==null) continue;
      const cited=issuedReferences(owner,graph), rows=new Map(originals(owner,graph).map(r=>[r.fact.id,r]));
      const ids=[];
      for (const [enabled,list,prefix] of [[pdf,change.execution,'addendum-pdf/'],[native,change.original_execution,'addendum-original/']]) {
        if (enabled && Array.isArray(list) && new Set(list).size===list.length &&
            list.every(id=>typeof id==='string' && id.startsWith(prefix))) ids.push(...list);
      }
      for (const id of ids) {
        const proof=id.startsWith('addendum-original/')?nativeAddendum(graph,id,rows):unitPdfOriginal(graph,id,'addendum');
        if (!issuedSource(proof,cited,calls) || !owner.scope?.includes(proof.record.unit) || !change.units?.includes(proof.record.unit) ||
            ![id,...proof.refs].every(ref=>change.evidence?.includes(ref)) ||
            !proof.record.pages.every(p=>{
              const pageCalls=calls.filter(c=>c.doc===proof.doc.id && c.doc+'/p'+c.page===p.ref);
              return pageCalls.length===1 && pageCalls[0].response_id && pageCalls[0].check?.response_id && issuedPageDocument(graph,pageCalls[0]);
            })) continue;
        if (!proofs.has(id)) {
          const related=issued.filter(f=>f.scope?.includes(proof.record.unit) && issuedSource(proof,issuedReferences(f,graph),calls));
          proofs.set(id,{...proof,related,bindings:[],lines:[]});
        }
        const record=proofs.get(id);
        const lines=[...rows.values()].filter(r=>r.line && r.fact.doc===proof.doc.id &&
          (r.fact.unit || r.fact.doc)===proof.record.unit && change.evidence.includes(r.fact.id));
        record.bindings.push({owner,change,lines});
        for (const row of lines) if (!record.lines.some(r=>r.fact.id===row.fact.id)) record.lines.push(row);
      }
    }
    index.addendumEvidence=[...proofs.values()]; return index.addendumEvidence;
  }
  function pdfReceiptEvidence(item,report) {
    const {graph,policy}=report;
    if (policy.acceptance_pdf!=='pdf-acceptance-execution-v1' || !['H02','H04','H05','H06'].includes(item.rule) || item.status==='ok') return [];
    const index=graphIndex(graph), cited=issuedReferences(item,graph);
    let ids=[...cited].filter(ref=>index.nodes.get(ref)?.type==='acceptance_pdf_inspection');
    if (item.rule==='H02') {
      if (Array.isArray(item.acceptance_execution)) ids=ids.filter(id=>item.acceptance_execution.includes(id));
      else if (Object.hasOwn(item,'acceptance_execution') || policy.version!=='2026.11.26.27' ||
        policy.code_sha256?.['controls.py']!=='eeff68cc20371bace1b158ebf70cc33885603b3913d8896f7b95236be19cd8a6') return [];
    }
    return ids.map(id=>unitPdfOriginal(graph,id,'acceptance')).filter(proof=>issuedSource(proof,cited,report.calls?.pages));
  }
  function nativeReceiptEvidence(item,report) {
    const {graph,policy}=report, format='acceptance-original-execution-v1';
    const ledger=graph.acceptance_original_sources, reviews=graph.acceptance_word_reviews;
    if (!['H02','H04','H05','H06'].includes(item.rule) || ledger?.format!==format || policy?.acceptance_originals!==format ||
        reviews?.format!=='word-acceptance-comments-v1' || policy.acceptance_word_reviews!==reviews.format ||
        !Array.isArray(ledger.records) || !Array.isArray(reviews.documents) ||
        !['acceptance_originals.py','original_records.py','acceptance_comments.py'].every(file=>/^[a-f0-9]{64}$/.test(policy.code_sha256?.[file]))) return [];
    const owners=report.findings.filter(f=>f.rule==='H02'), [owner]=owners;
    if (owners.length!==1 || !Array.isArray(owner.acceptance_originals) || !owner.acceptance_originals.length ||
        new Set(owner.acceptance_originals).size!==owner.acceptance_originals.length) return [];
    const cited=issuedReferences(item,graph), held=issuedReferences(owner,graph);
    const basis=new Map(originals(owner,graph).map(row=>[row.fact.id,row]));
    const allowed=new Set(['acceptance_signer','acceptance_result','measured_result','defect_closure']);
    const proofs=[];
    for (const id of owner.acceptance_originals) {
      if (!cited.has(id) || !held.has(id)) continue;
      const source=unitSource(graph,id,'acceptance_original',['acceptance','reinspection'],'acceptance_signer');
      if (!source || !owner.scope.includes(source.record.unit) || !item.scope.includes(source.record.unit)) continue;
      const signers=graph.facts.filter(f=>f.doc===source.doc.id && (f.unit || f.doc)===source.record.unit && f.field==='acceptance_signer');
      if (signers.length!==source.record.fields.length || signers.some((f,i)=>f.id!==source.record.fields[i])) continue;
      const proof=MandateOriginals.bind(graph,source,basis,'acceptance');
      if (!issuedSource(proof,held,report.calls?.pages) || !issuedSource(proof,cited,report.calls.pages)) continue;
      const lines=[];
      for (const row of basis.values()) {
        const {fact}=row;
        if (!row.printedLine || !allowed.has(fact.field) || !cited.has(fact.id) || (fact.unit || fact.doc)!==proof.record.unit ||
            fact.doc!==proof.doc.id || !proof.record.pages.some(p=>p.ref===fact.doc+'/p'+fact.page && p.sha256===fact.page_sha256)) continue;
        const text=fact.source_line.text;
        if (text!==fact.quote) {
          if (fact.field!=='measured_result' || !/^实测结果[：:]柜温 -?[0-9]+(?:\.[0-9]+)?(?:℃|°C)$/u.test(text) ||
              text.replace('柜温 ','柜温')!==fact.quote) continue;
          const page=graphIndex(graph).nodes.get(fact.doc+'/p'+fact.page),call=report.calls.pages.find(c=>c.doc===fact.doc && c.page===fact.page);
          if (!FolioTranscriptions.visuallyRead(fact,call) && !fieldReceiptOperation(fact,proof.doc,page)) continue;
        }
        lines.push({...row,line:row.printedLine});
      }
      let initial='acceptance_signer';
      const reading=lines.find(row=>row.fact.field==='measured_result');
      if (owner.status==='issue' && owner.reinspection?.state==='open' &&
          owner.reinspection.steps?.some(s=>s.role==='final' && s.unit===proof.record.unit)) initial='defect_closure';
      else if (owner.status==='issue' && reading && [...basis.values()].some(r=>r.line && r.fact.field==='acceptance_criteria' &&
          graph.documents_by_kind.contract?.includes(r.fact.unit || r.fact.doc) && issuedLimitBreach(owner.detail,r.fact,reading.fact))) initial='measured_result';
      else if (owner.status==='risk' && proof.notes?.some(n=>n.location)) initial='notes';
      proofs.push({...proof,lines,initial});
    }
    return proofs;
  }
  function receiptEvidence(item,report) {
    return [...pdfReceiptEvidence(item,report),...nativeReceiptEvidence(item,report)];
  }
  function nativeReceiptCitation(report,id,finding) {
    const owner=finding || report.findings.find(f=>f.rule==='H02');
    const proof=owner && nativeReceiptEvidence(owner,report).find(p=>p.record.id===id);
    if (!proof) return el('span','验收签认来源待核','small');
    const open=action(proof.doc.name+' · 签认原件',()=>{
      document.querySelector('[data-audit-scope="acceptance"]')?.dispatchEvent(new CustomEvent('open-acceptance-source',{detail:proof.record.unit}));
    },'ref');
    open.dataset.acceptanceCitation=id;open.setAttribute('aria-haspopup','dialog');open.setAttribute('aria-controls','performance-index');
    return open;
  }
  function releaseProofs(item,report) {
    const {graph,policy}=report,release=item.payment_opinion?.release,format='payment-release-execution-v1';
    if (!['H04','H05'].includes(item.rule) || policy?.release_execution!==format ||
        graph.release_pdf_sources?.format!==format || graph.release_original_sources?.format!==format ||
        !['release_execution.py','pdf_execution.py','original_records.py','acceptance_comments.py'].every(f=>/^[a-f0-9]{64}$/.test(policy.code_sha256?.[f])) ||
        !release?.signature_records?.length || new Set(release.signature_records).size!==release.signature_records.length) return [];
    const cited=issuedReferences(item,graph), rows=new Map(originals(item,graph).map(r=>[r.fact.id,r])),proofs=[];
    // A Word comment can anchor to a native line whose model field category is still under review.
    for (const printed of ReleaseEvidence.sources(graph,item)) {
      if (!printed.line || !printed.native) continue;
      for (const ref of printed.facts) {
        const row=rows.get(ref),f=row?.fact,loc=f?.source_line;
        if (row && !row.line && f.status==='visual' && loc?.rects?.length && loc.number===printed.line &&
            loc.text===printed.quote && f.quote===printed.quote && f.doc===printed.doc && f.page===printed.page) {
          rows.set(ref,{...row,line:printed.line});
        }
      }
    }
    for (const id of release.signature_records) {
      const source=id.startsWith('release-pdf/')?unitPdfOriginal(graph,id,'release'):
        MandateOriginals.bind(graph,unitSource(graph,id,'release_original',['payment_release'],'approval_signer'),rows,'release');
      if (!issuedSource(source,cited,report.calls?.pages) || !release.units.includes(source.record.unit) ||
          ![id,...source.refs].every(ref=>release.evidence.includes(ref)) ||
          !graph.payment_release_sources.pages.some(p=>p.role==='release' && p.unit===source.record.unit && p.doc===source.doc.id)) return [];
      const fields=graph.facts.filter(f=>f.doc===source.doc.id && (f.unit || f.doc)===source.record.unit && f.field==='approval_signer');
      if (fields.length!==source.record.fields.length || fields.some((f,i)=>source.record.fields[i]!==f.id)) return [];
      proofs.push(source);
    }
    return proofs;
  }
  function boardProofs(item,report) {
    const {graph,policy}=report, check=item.effect_review?.board_decision, format=pdfSources.board.format;
    if (item.rule!=='H01' || policy.board_decision!==format || !check?.records?.length ||
        typeof check.linked!=='boolean' || !Array.isArray(check.evidence) ||
        !['board_execution.py','pdf_execution.py','original_records.py','acceptance_comments.py'].every(k=>/^[a-f0-9]{64}$/.test(policy.code_sha256?.[k])) ||
        ![graph.board_pdf_sources,graph.board_original_sources].every(l=>l?.format===format && Array.isArray(l.records))) return null;
    const records=[...graph.board_pdf_sources.records,...graph.board_original_sources.records].filter(r=>item.scope.includes(r.unit));
    const units=item.scope.filter(u=>graph.documents_by_kind.contract_approval?.includes(u));
    if (records.length!==check.records.length || new Set(check.records).size!==records.length ||
        records.some((r,i)=>r.id!==check.records[i]) || check.state!==(records.length===1 && units.length===1?records[0].state:'multiple')) return null;
    const rows=new Map(originals(item,graph).map(r=>[r.fact.id,r])), cited=issuedReferences(item,graph);
    if (!check.evidence.every(ref=>cited.has(ref))) return null;
    const proofs=[];
    for (const record of records) {
      const source=record.id.startsWith('board-pdf/')?unitPdfOriginal(graph,record.id,'board'):
        MandateOriginals.bind(graph,unitSource(graph,record.id,'board_original',['contract_approval'],'approval_signer'),rows,'board');
      if (!issuedSource(source,cited,report.calls?.pages) || ![record.id,...source.refs].every(ref=>check.evidence.includes(ref))) return null;
      const fields=graph.facts.filter(f=>(f.unit || f.doc)===record.unit && f.doc===record.doc && f.field==='approval_signer');
      if (fields.length!==record.fields.length || fields.some((f,i)=>f.id!==record.fields[i])) return null;
      proofs.push(source);
    }
    const fields={};
    for (const [kind,ref] of Object.entries(check.fields || {})) {
      let row=rows.get(ref);
      const f=row?.fact;
      if (kind==='approved_on' && !row?.line && row?.printedLine) {
        // Word can insert spaces around 年/月/日. Keep every digit group and the printed line.
        const date=s=>s.normalize('NFKC').trim().match(/^(审批日期|批准日期|决定日期)\s*:\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日$/u)?.slice(1).join('/');
        const printed=date(f.source_line.text);
        if (printed && printed===date(f.quote)) row={...row,line:row.printedLine};
      }
      const scope=kind==='effect_clause'?graph.documents_by_kind.contract:units;
      if (!row?.line || f.field!==kind || !check.evidence.includes(ref) || !scope?.includes(f.unit || f.doc)) return null;
      fields[kind]=row;
    }
    return {proofs,fields};
  }
  function warrantyProofs(item,report) {
    const {graph,policy}=report, cert=item.warranty_check?.certificate, format=pdfSources.warranty.format;
    if (!['H04','H05'].includes(item.rule) || !cert?.records?.length || !Array.isArray(cert.evidence) ||
        typeof cert.linked!=='boolean' || policy?.warranty_execution!==format ||
        !['warranty_execution.py','original_records.py','pdf_execution.py','acceptance_comments.py'].every(f=>/^[a-f0-9]{64}$/.test(policy.code_sha256?.[f])) ||
        ![graph.warranty_original_sources,graph.warranty_pdf_sources].every(l=>l?.format===format && Array.isArray(l.records))) return [];
    const records=[...graph.warranty_pdf_sources.records,...graph.warranty_original_sources.records].filter(r=>item.scope.includes(r.unit));
    if (records.length!==cert.records.length || new Set(cert.records).size!==records.length ||
        records.some((r,i)=>r.id!==cert.records[i]) || (cert.linked ? records.length!==1 || cert.state!==records[0].state : cert.state!=='scope_pending')) return [];
    const rows=new Map(originals(item,graph).map(r=>[r.fact.id,r]));
    for (const line of graph.warranty_sources.lines) {
      if (!line.line || !records.some(r=>r.unit===line.unit && r.doc===line.doc)) continue;
      for (const id of line.facts) {
        const row=rows.get(id), f=row?.fact, loc=f?.source_line;
        if (f?.status==='visual' && f.page===line.page && f.doc===line.doc && loc?.number===line.line &&
            loc.rects?.length && loc.text===line.quote && f.quote===line.quote) rows.set(id,{...row,line:line.line});
      }
    }
    const cited=issuedReferences(item,graph), proofs=[];
    for (const record of records) {
      const source=record.id.startsWith('warranty-pdf/')?unitPdfOriginal(graph,record.id,'warranty'):
        MandateOriginals.bind(graph,unitSource(graph,record.id,'warranty_original',['warranty'],'acceptance_signer'),rows,'warranty');
      if (!issuedSource(source,cited,report.calls?.pages) || ![record.id,...source.refs].every(ref=>cert.evidence.includes(ref)) ||
          !graph.warranty_sources.pages.some(p=>p.unit===record.unit && p.doc===record.doc)) return [];
      const fields=graph.facts.filter(f=>f.doc===record.doc && (f.unit || f.doc)===record.unit && f.field==='acceptance_signer');
      if (fields.length!==record.fields.length || fields.some((f,i)=>f.id!==record.fields[i])) return [];
      proofs.push(source);
    }
    return proofs;
  }
  const mandateSides={buyer:'甲方授权',seller:'乙方授权',unassigned:'委托书归属待核'};
  const mandatePending=['missing','risk','issue'];
  function mandateScope(item,entry,proofs,rows,cited,graph) {
    if ([entry.status,item.status].includes('missing') || entry.side==='unassigned' || entry.units.length!==1 ||
        proofs.length!==1 || typeof entry.detail!=='string' || typeof item.detail!=='string') return null;
    const {record,doc}=proofs[0], index=graphIndex(graph);
    const fields=graph.facts.filter(f=>f.field==='grant_scope' && (f.unit || f.doc)===record.unit);
    if (fields.length!==1) return null;
    const [fact]=fields, row=rows.get(fact.id), source=MandateCalendar.printed(fact), pageId=fact.doc+'/p'+fact.page;
    if (!row?.line || !source?.value || !['授权权限','代理权限','授权范围'].includes(source.label) ||
        fact.doc!==doc.id || !entry.evidence.includes(fact.id) || !cited.has(fact.id) ||
        index.nodes.get(pageId)?.layer!=='text' || !record.pages.some(p=>p.ref===pageId && p.layer==='text' && p.sha256===fact.page_sha256)) return null;
    const edges=graph.edges.filter(e=>e.type==='grant_scope' && e.evidence?.includes(fact.id)), [edge]=edges;
    if (edges.length!==1 || edge.from!==record.unit || !Array.isArray(edge.evidence) || edge.evidence.length!==1) return null;
    const target=index.nodes.get(edge.to);
    if (target?.type!=='grant_scope' || typeof target.label!=='string' || target.label.normalize('NFKC').trim()!==source.value) return null;
    // Link the conflict the issued decision actually cites, even if other limitations share the page.
    const reason=entry.detail.match(/[^。]+。?/gu)?.map(s=>s.trim()).find(s=>s.includes('“'+source.value+'”') &&
      /权限不足以支持代理签约|需另核签约授权/u.test(s));
    return reason && item.detail.includes(reason)?{fact,line:row.line,doc,reason}:null;
  }
  function delegationProofs(item,entry,report,rows,cited,native) {
    const {graph,policy}=report;
    const format=native?MandateOriginals.format:'pdf-mandate-execution-v1';
    const ledger=native?graph.mandate_original_sources:graph.mandate_pdf_sources;
    const ids=native?entry.mandate_originals:entry.mandate_execution;
    if ((native?policy?.mandate_originals:policy?.mandate_pdf)!==format || ledger?.format!==format ||
        !Array.isArray(ledger.records) || !Array.isArray(ids) || !ids.length || new Set(ids).size!==ids.length) return [];
    if (native && entry.signature_field && ![entry.side+'_signature',entry.side+'_agent_signature'].includes(entry.signature_field)) return [];
    const records=ledger.records.filter(r=>r && entry.units.includes(r.unit));
    if (records.length!==ids.length || !records.every(r=>ids.includes(r.id))) return [];
    const proofs=[];
    for (const id of ids) {
      const proof=native?MandateOriginals.bind(graph,unitSource(graph,id,'mandate_original',['power_of_attorney'],'grant_signature'),rows):
        unitPdfOriginal(graph,id,'mandate');
      if (!issuedSource(proof,cited,report.calls?.pages) || ![id,...proof.refs].every(ref=>entry.evidence.includes(ref))) return [];
      const {record,doc}=proof;
      if (!item.scope.includes(record.unit) || !native && record.pages.some(p=>p.layer==='unknown' && (record.state!=='review' || p.has_text))) return [];
      if (native && item.delegations.some(e=>e?.side!==entry.side && e?.units?.includes(record.unit))) return [];
      if (record.state==='mismatch' && [entry.status,item.status].includes('missing')) return [];
      // An empty field list is valid only when this unit really has no signing observation.
      const fields=graph.facts.filter(f=>f.field==='grant_signature' && (f.unit || f.doc)===record.unit);
      if (fields.length!==record.fields.length || !fields.every(f=>record.fields.includes(f.id) && rows.has(f.id))) return [];
      const locations=record.fields.map(field=>{
        const {fact,line}=rows.get(field);
        const printed=!native || record.kind==='word' && record.pages.some(p=>p.ref===doc.id+'/p'+fact.page && p.layer==='text');
        return {page:fact.page,field,line:printed?line:null};
      });
      if (!locations.length || native) {
        for (const p of record.pages) {
          const page=Number(p.ref.slice(doc.id.length+2));
          if (!locations.some(l=>l.page===page)) locations.push({page});
        }
      }
      proofs.push({...proof,locations});
    }
    return proofs;
  }
  function mandateEvidence(item,report) {
    const {graph}=report;
    if (item.rule!=='H01' || !mandatePending.includes(item.status) || !Array.isArray(item.delegations) || !Array.isArray(item.scope)) return [];
    const cited=issuedReferences(item,graph);
    if (!cited.size) return [];
    const rows=new Map(originals(item,graph).map(row=>[row.fact.id,row]));
    return item.delegations.flatMap(entry=>{
      if (!Array.isArray(entry?.units) || !Array.isArray(entry.evidence) || !Object.hasOwn(mandateSides,entry.side) ||
          !mandatePending.includes(entry.status)) return [];
      const proofs=[...delegationProofs(item,entry,report,rows,cited,false),...delegationProofs(item,entry,report,rows,cited,true)];
      return proofs.length?[{entry,proofs,scope:mandateScope(item,entry,proofs,rows,cited,graph)}]:[];
    });
  }
  function mandatePage(proof,location) {
    const {doc,record}=proof, {page,field,line}=location;
    const button=action('',()=>openPage(doc.id,page,field),'scope-mandate-page');
    if (record.kind) button.dataset.mandateOriginal=record.id;
    else button.dataset.pdfMandate=record.id;
    button.setAttribute('aria-haspopup','dialog'); button.setAttribute('aria-controls','page-dialog');
    const place=doc.name+' · 第 '+page+' 页'+(line?' · 第 '+line+' 行':'');
    const open=el('span',record.kind==='image'?'核对整页照片':field?'查看签章页':'查看原页','scope-mandate-open');
    open.append(glyph('arrows-angle-expand')); button.append(el('span',place),open);
    return button;
  }
  function mandatePanel({entry,proofs,scope}) {
    const panel=el('section','','scope-mandate-proof');
    panel.setAttribute('aria-label',mandateSides[entry.side]+' · 授权方签章凭证');
    panel.append(box('scope-mandate-heading',el('h4','授权方签章凭证'),el('span',mandateSides[entry.side]),tag(entry.status)));
    for (const proof of proofs) {
      const record=box('scope-mandate-record',el('strong',proof.label));
      record.dataset.state=proof.record.state;
      for (const location of proof.locations) record.append(mandatePage(proof,location));
      if (proof.word) record.append(MandateOriginals.wordTools(proof));
      if (['current','earlier','mismatch'].includes(proof.record.state)) {
        record.append(lazyFold('签名覆盖范围',()=>[PdfSignatureCard.digital(proof.signature)]));
      }
      panel.append(record);
    }
    const [reason='',next='']=typeof entry.detail==='string'?entry.detail.trim().match(/[^。]+。?/gu) || []:[];
    const note=scope?.reason || (/^(?:委托书 (?:PDF|Word)|委托书为上传的影像|委托书原件的签发|电子签名)/u.test(reason)?(reason+next).match(/[，。]\s*(请[^。]*。?)/u)?.[1]:reason);
    if (note) {
      const paragraph=el('p','','scope-mandate-note'); paragraph.append(el('span',note));
      if (scope) {
        const {fact,doc,line}=scope;
        const open=action('查看权限原行',()=>openPage(doc.id,fact.page,fact.id),'text-button scope-mandate-scope');
        open.dataset.mandateScope=fact.id; open.title=doc.name+' · 第 '+fact.page+' 页 · 第 '+line+' 行';
        open.setAttribute('aria-haspopup','dialog'); open.setAttribute('aria-controls','page-dialog');
        paragraph.append(' ',open);
      }
      panel.append(paragraph);
    }
    return panel;
  }
  function mandateCitation(report,id,finding) {
    const cites=finding?.rule && issuedReferences(finding,report.graph);
    for (const item of report.findings.filter(f=>f.rule==='H01')) {
      for (const {proofs} of mandateEvidence(item,report)) {
        for (const proof of proofs) {
          const note=proof.notes?.find(n=>n.id===id);
          if (proof.record.id!==id && proof.word?.id!==id && !note) continue;
          if (cites && (!cites.has(id) || !issuedSource(proof,cites,report.calls?.pages))) continue;
          if (proof.record.id===id) return mandatePage(proof,proof.locations[0]);
          if (!note) return MandateOriginals.wordFile(proof);
          const button=action(proof.doc.name+' · 原批注',()=>{
            document.querySelector('[data-audit-scope="contract"]')?.dispatchEvent(new CustomEvent('open-mandate-note',
              {detail:{item,record:proof.record.id,note:id}}));
          },'ref');
          button.dataset.mandateNoteRef=id;
          button.setAttribute('aria-haspopup','dialog'); button.setAttribute('aria-controls','performance-index');
          return button;
        }
      }
    }
    return el('span','委托书签章凭证来源待核','small');
  }
  function receiptPanel(receipt,item,related,graph,openPayment) {
    const tools=box('scope-proof-tools'), panel=box('scope-proof-detail');
    panel.id='receipt-detail-'+item.id+'-'+encodeURIComponent(receipt.record.id);
    panel.hidden=true;
    function control(label,build) {
      const button=action(label,()=>{
        const expand=button.getAttribute('aria-expanded')==='false';
        for (const b of tools.children) b.setAttribute('aria-expanded',String(expand && b===button));
        panel.replaceChildren(...(expand?[build()]:[])); panel.hidden=!expand;
      });
      button.setAttribute('aria-expanded','false'); button.setAttribute('aria-controls',panel.id);
      tools.append(button);
      return button;
    }
    const native=Boolean(receipt.record.kind);
    if (!native) control('签名覆盖范围',()=>PdfSignatureCard.digital(receipt.signature)).dataset.receiptRange=receipt.record.id;
    if (related.length) {
      control('付款检查 · '+related.length+' 项',()=>{
        const list=box('scope-receipt-links');
        for (const f of related) {
          const original=originals(f,graph).find(r=>r.fact.id===f.stage.clause_ref && ['anchored','confirmed'].includes(r.fact.status));
          const shares=original?.fact.value.normalize('NFKC').match(/\d+(?:\.\d+)?%/g) || [];
          const share=shares.length===1 && Number(shares[0].slice(0,-1))===Number(f.stage.share)?' · '+shares[0]:'';
          const label={H04:'付款条件',H05:'实付时点',H06:'回单合计'}[f.rule];
          const button=action('',()=>openPayment(f,receipt.record.id),'scope-receipt-phase');
          button.dataset.receiptPhase=f.id;
          button.append(el('strong',f.stage.name+share),el('span',label),tag(f.status),glyph('chevron-down'));
          list.append(button);
        }
        return list;
      }).dataset.receiptPayments=receipt.record.id;
    }
    if (!native) return box('scope-receipt-proof',receiptButton(receipt),tools,panel);
    const {doc,record}=receipt, index=graphIndex(graph), bundle=state.bundle, route=Team.route();
    const original=workpaperSource(doc.id,'original');
    const current=()=>state.bundle===bundle && Team.route().id===route.id && Team.route().page===route.page;
    const pageControl=(number,fact)=>()=>{
      const b=action('',()=>{if (current()) openPage(doc.id,number,fact);});
      b.setAttribute('aria-haspopup','dialog');b.setAttribute('aria-controls','page-dialog');return b;
    };
    const model={
      record:record.id,name:doc.name,original,hash:doc.sha256,label:receipt.label,unplaced:record.unplaced,
      initial:receipt.initial,partial:receipt.word && receipt.word.coverage!=='complete',notes:receipt.notes || [],
      pages:record.pages.map(p=>{const number=Number(p.ref.split('/p').pop());
        return {number,control:pageControl(number),thumbnail:async()=>current() && EvidenceCompare.pageThumbnail({doc:doc.id,page:number},index)};
      }),
      lines:receipt.lines.map(({fact,line})=>({ref:fact.id,field:fact.field,page:fact.page,line,quote:fact.source_line.text,
        control:pageControl(fact.page,fact.id),excerpt:async()=>current() && EvidenceCompare.lineExcerpt(fact,index)})),
      permalink:()=>Team.paperLink('固定链接',bundle.report.case_id,'accept-original-link',new URLSearchParams({
        rev:String(bundle.rev),view:'acceptance-checks',acceptance:record.unit})),
    };
    const card=AcceptanceOriginalCard.render(model,'accept-'+item.id+'-'+encodeURIComponent(record.id));
    return box('scope-receipt-proof',card,...(tools.children.length?[tools,panel]:[]));
  }
  function issuedLimitBreach(detail,criterion,reading) {
    const statement='合同要求“'+criterion.value+'”，验收原页记载“'+reading.value+'”，实测值超出约定限值。';
    return detail.normalize('NFKC').includes(statement.normalize('NFKC'));
  }
  function pairedLines(item,report) {
    const graph=report.graph;
    function fromFacts(title, entries) {
      const rows=entries.map(([label,fact])=>({
        label,place:'第 '+fact.page+' 页 · 第 '+fact.source_line.number+' 行',line:fact.source_line.number,quote:fact.source_line.text,
        excerpt:()=>EvidenceCompare.lineExcerpt(fact,graphIndex(graph)),open:()=>openPage(fact.doc,fact.page,fact.id),
      }));
      return {title,rows};
    }
    if (item.rule==='H07') {
      const pair=WarrantyRegisterEvidence.pair(item,report);
      return pair && fromFacts(pair.label,[['期满确认单',pair.left],['维修工单',pair.right]]);
    }
    if (item.execution_basis) {
      const [entry]=PaymentProof.entries(report,[item]);
      if (!entry || !['conflict','limited','application'].includes(entry.state)) return null;
      const rows=[[entry.leftLabel,entry.left],[entry.rightLabel,entry.right]].flatMap(([label,group])=>
        group.filter(r=>r.clear && r.rects.length).map(r=>({...r,label})));
      return rows.length?{title:rows[0].file,rows}:null;
    }
    if (item.rule!=='H02' || item.status!=='issue') return null;
    const refs=originals(item,graph), kinds=graph.documents_by_kind || {};
    function only(field,kind) {
      const candidates=refs.filter(r=>r.line && r.fact.field===field && kinds[kind]?.includes(r.fact.unit || r.fact.doc));
      return candidates.length===1?candidates[0]:null;
    }
    const contract=only('acceptance_criteria','contract'), acceptance=only('measured_result','acceptance');
    if (!contract || !acceptance) return null;
    // This is the issued quantitative finding. Other procedures may cite the same fields as context.
    if (!issuedLimitBreach(item.detail,contract.fact,acceptance.fact)) return null;
    return fromFacts('合同标准与验收实测',[contract,acceptance].map(({doc,fact})=>[doc.name,fact]));
  }
  function pairView(item,report,receipts) {
    const pair=pairedLines(item,report);
    if (!pair) return null;
    const section=box('scope-originals');
    let print=true;
    const mode=action('',()=>{print=!print; draw();},'text-button scope-source-mode');
    const clips=[];
    function draw() {
      mode.hidden=!clips.some(({crop})=>crop.childElementCount);
      mode.textContent=print?'看文字':'看原行';
      for (const {crop,quote} of clips) {
        crop.hidden=!print || !crop.childElementCount; quote.classList.toggle('visually-hidden',!crop.hidden);
      }
    }
    section.append(box('scope-excerpt-head',el('h4',pair.title),mode));
    for (const row of pair.rows) {
      const open=action('',row.open,'scope-original-line'), crop=box('scope-source-crop'), quote=el('q',row.quote);
      open.setAttribute('aria-haspopup','dialog'); open.setAttribute('aria-controls','page-dialog');
      open.dataset.sourceLine=String(row.line);
      open.append(box('scope-row-head',el('strong',row.label),el('span',row.place),glyph('arrows-angle-expand')),crop,quote);
      section.append(open); clips.push({crop,quote});
      row.excerpt?.().then(canvas=>{if (canvas && crop.isConnected) {crop.replaceChildren(canvas);draw();}}).catch(()=>{});
    }
    draw();
    section.append(lazyFold('其他字段引文',()=>[sourceView(item,report.graph,receipts)]));
    return section;
  }
  function overview(findings,graph,rev) {
    const groupsHere=groups(findings);
    const guaranteePayments=findings.filter(f=>f.rule==='H05' && f.advance_guarantee);
    const checkLabel=item=>guaranteePayments.length>1 && guaranteePayments.includes(item)?
      checkName(item)+' · '+AdvanceGuarantee.receiptName(item,state.bundle.report):checkName(item);
    const summary=box('performance-statuses scope-cards'), dialog=el('dialog','','scope-dialog');
    dialog.id='performance-index'; dialog.setAttribute('aria-labelledby','scope-title');
    const title=el('h2'); title.id='scope-title';
    let previous;
    const back=action('返回交付验收',()=>{
      const source=previous;
      previous=null; back.hidden=true;
      showGroup(source.group,source.item);
      const toggle=detail.querySelector('[data-receipt-payments="'+CSS.escape(source.proof)+'"]');
      if (!toggle) return;
      toggle.click();
      toggle.closest('.scope-receipt-proof').querySelector('[data-receipt-phase="'+CSS.escape(source.phase)+'"]')?.focus();
    },'text-button scope-back');
    back.hidden=true;
    const close=action('',()=>dialog.close(),'icon-button');
    close.append(glyph('x-lg')); close.setAttribute('aria-label','关闭履约检查');
    const filters=box('scope-filters'), checks=box('scope-checks'), detail=el('section','','scope-detail'), mobile=el('select');
    filters.setAttribute('role','group'); filters.setAttribute('aria-label','筛选本组检查');
    checks.setAttribute('role','group'); checks.setAttribute('aria-label','本组检查');
    mobile.className='scope-check-select'; mobile.setAttribute('aria-label','选择检查项');
    detail.setAttribute('aria-labelledby','scope-check-title');
    dialog.append(box('scope-head',box('',box('scope-context',back,el('small','合同履约审查 · R'+rev)),title),close),filters,mobile,box('scope-body',checks,detail));
    let shown=[],group,selected;
    const shownReceipts=new Map();
    function select(item) {
      selected=item.id; mobile.value=selected;
      for (const row of checks.children) row.setAttribute('aria-pressed',String(row.dataset.check===selected));
      const heading=el('h3',checkLabel(item)); heading.id='scope-check-title';
      const complete=action('完整检查',()=>{
        dialog.close(); revealPaperTarget(document.querySelector('[data-finding="'+CSS.escape(item.id)+'"]'));
      },'text-button');
      const jump=specialist(item);
      if (jump) jump.addEventListener('click',()=>dialog.close(),{capture:true});
      const actions=box('scope-actions',...(jump?[jump]:[]),complete);
      const receipts=receiptEvidence(item,state.bundle.report);
      const mandates=mandateEvidence(item,state.bundle.report);
      const paired=pairView(item,state.bundle.report,receipts);
      const roster=AcceptanceRoster.bind(item,state.bundle.report);
      const batch=BatchPhase.resolve(item,findings.find(f=>f.rule==='H02'),graph,state.bundle.report.calls?.pages);
      const guarantee=AdvanceGuarantee.panel(item,state.bundle.report);
      const quality=PaymentQuality.panel(item,state.bundle.report,rev);
      const retest=RetestReference.panel(item,state.bundle.report,rev);
      detail.dataset.batch=String(Boolean(batch));
      detail.dataset.guarantee=String(Boolean(guarantee));
      detail.dataset.quality=String(Boolean(quality));
      detail.replaceChildren(box('scope-check-state',el('span',item.id,'mono'),tag(item.status)),heading);
      if (quality) detail.append(quality);
      else if (item.payment_quality) detail.append(el('p','验收款质量对照的原行待核。','scope-empty'));
      if (retest) detail.append(retest);
      else if (item.retest_reference) detail.append(el('p','请在字段引文中核对回单所引的验收原件。','scope-empty'));
      for (const proof of addendumEvidence(state.bundle.report).filter(p=>p.related.includes(item))) {
        const control=AddendumSigning.jump(proof);
        control.addEventListener('click',()=>dialog.close(),{capture:true});
        detail.append(control);
      }
      for (const mandate of mandates) detail.append(mandatePanel(mandate));
      let detailText=item.detail || '';
      if (guarantee) detail.append(guarantee);
      if (batch) detail.append(BatchPhase.panel(batch,item.stage));
      if (paired) detail.append(paired);
      else if (!guarantee && !retest && detailText && (receipts.length && ['issue','risk'].includes(item.status) || roster && item.status==='issue')) {
        const end=detailText.indexOf('。')+1 || detailText.length;
        detail.append(el('p',detailText.slice(0,end),'scope-reason')); detailText=detailText.slice(end).trimStart();
      }
      const payments=groupsHere.find(g=>g.id==='payment');
      const byProof=new Map(receipts.map(r=>[r.record.id,[]]));
      if (receipts.length && item.rule==='H02' && payments) {
        for (const phase of payments.items.filter(f=>f.stage)) {
          for (const r of receiptEvidence(phase,state.bundle.report)) byProof.get(r.record.id)?.push(phase);
        }
      }
      function makeReceipt(receipt) {
        return receiptPanel(receipt,item,byProof.get(receipt.record.id),graph,(phase,proof)=>{
          previous={group,item,proof,phase:phase.id}; back.hidden=false;
          showGroup(payments,phase); back.focus();
        });
      }
      if (receipts.length>1 && receipts.some(p=>p.record.kind)) {
        const picker=el('select','','accept-proof-picker'),slot=box('accept-picked-proof');
        picker.setAttribute('aria-label','选择本项所据验收原件');
        for (const p of receipts) picker.add(new Option(p.doc.name+' · 第 '+p.page+' 页',p.record.id));
        const selectedProof=receipts.find(p=>p.record.id===shownReceipts.get(item.id)) || receipts.find(p=>p.record.kind);
        function choose(id) {
          picker.value=id;shownReceipts.set(item.id,id);slot.replaceChildren(makeReceipt(receipts.find(p=>p.record.id===id)));
        }
        picker.addEventListener('change',()=>choose(picker.value));choose(selectedProof.record.id);
        detail.append(picker,slot);
      } else {
        for (const receipt of receipts) detail.append(makeReceipt(receipt));
      }
      if (roster) {
        detail.append(AcceptanceRosterCard.render(roster,'scope-signers','page-dialog'));
        if (detailText) detail.append(fold('本项检查结论',el('p',detailText,'scope-reason')));
      } else if (!paired && detailText) {
        const reason=el('p',detailText,'scope-reason');
        detail.append(detailText.length<=100 && !receipts.length && !batch && !guarantee && !quality && !retest?reason:fold('阅读本项结论',reason));
      }
      if (!paired) {
        const sources=()=>sourceView(item,graph,[...receipts,...mandates.flatMap(m=>m.proofs)]);
        detail.append(roster || batch || guarantee || quality || retest || mandates.length || receipts.some(p=>p.record.kind)?lazyFold('其他字段引文',()=>[sources()]):sources());
      }
      detail.append(actions);
      detail.scrollTop=0;
    }
    function filter(pending,unavailable=false) {
      shown=pending?priorityFindings(group.pending).concat(group.pending.filter(f=>!['risk','issue','missing'].includes(f.status))):group.items;
      [...filters.children].forEach((button,i)=>button.setAttribute('aria-pressed',String((i===0)===pending)));
      checks.replaceChildren(); mobile.replaceChildren();
      for (const item of shown) {
        const row=action('',()=>select(item),'scope-check'); row.dataset.check=item.id;
        const label=checkLabel(item);
        row.append(el('small',item.id,'mono'),el('span',label),tag(item.status));
        const option=el('option',item.id+' · '+label+' · '+statusName(item.status)); option.value=item.id;
        checks.append(row); mobile.append(option);
      }
      if (unavailable) {
        selected=null; detail.dataset.batch='false'; detail.dataset.guarantee='false'; detail.dataset.quality='false';
        for (const row of checks.children) row.setAttribute('aria-pressed','false');
        const placeholder=new Option('选择本版检查项','',true,true); placeholder.disabled=true;
        mobile.prepend(placeholder); mobile.value='';
        const note=el('p','所选期次未收录于本版底稿，请从本组检查中选择。','scope-empty');
        note.id='scope-check-title'; note.setAttribute('role','status'); detail.replaceChildren(note);
        return;
      }
      select(shown.find(f=>f.id===selected) || shown[0]);
    }
    mobile.addEventListener('change',()=>select(shown.find(f=>f.id===mobile.value)));
    function showGroup(scope,item,unavailable=false) {
      group=scope; selected=item?.id; title.textContent=scope.label;
      dialog.dataset.single=String(group.items.length===1 && !unavailable);
      filters.hidden=!group.pending.length || group.pending.length===group.items.length;
      const pending=action('待核 '+group.pending.length,()=>filter(true));
      pending.disabled=!group.pending.length;
      filters.replaceChildren(pending,action('全部 '+group.items.length,()=>filter(false)));
      filter(Boolean(group.pending.length) && item?.status!=='ok',unavailable);
    }
    function open(scope, stage) {
      previous=null; back.hidden=true;
      const item=stage && scope.items.find(f=>['H04','H05'].includes(f.rule) && f.id===stage);
      showGroup(scope,item,Boolean(stage && !item));
      dialog.showModal();
      dialog.scrollTop=0;
    }
    for (const scope of groupsHere) {
      const button=action('',()=>open(scope),'scope-card');
      if (scope.id==='acceptance') button.addEventListener('open-acceptance-source',event=>{
        const owner=scope.items.find(f=>f.rule==='H02');
        const proof=owner && nativeReceiptEvidence(owner,state.bundle.report).find(p=>p.record.unit===event.detail);
        previous=null;back.hidden=true;
        if (proof) shownReceipts.set(owner.id,proof.record.id);
        showGroup(scope,owner);
        if (!dialog.open) dialog.showModal();
        if (proof) detail.querySelector('[data-receipt-original="'+CSS.escape(proof.record.id)+'"]')?.focus();
        else {
          const note=el('p','本版未收录所选验收签认原件。','scope-empty'); note.setAttribute('role','status');note.tabIndex=-1;
          detail.replaceChildren(note);note.focus();
        }
      });
      if (scope.id==='contract') button.addEventListener('open-mandate-note',event=>{
        const {item,record,note}=event.detail;
        previous=null; back.hidden=true;
        showGroup(scope,item);
        if (!dialog.open) dialog.showModal();
        const review=detail.querySelector('[data-mandate-review="'+CSS.escape(record)+'"]');
        if (!review) return;
        review.open=true;
        review.dispatchEvent(new CustomEvent('select-mandate-note',{detail:note}));
        review.querySelector('summary').focus();
      });
      if (scope.id==='payment') button.addEventListener('open-payment-stage',event=>open(scope,event.detail));
      button.dataset.auditScope=scope.id;
      button.setAttribute('aria-haspopup','dialog'); button.setAttribute('aria-controls',dialog.id);
      const status=PhaseEvidence.combined(scope.items);
      const name=scope.id==='payment'?paymentTitle(scope.items,graph):scope.label;
      button.append(box('scope-card-head',glyph(scope.icon),el('strong',name)),
        box('scope-card-count',el('span',count(scope)),scope.pending.length?tag(status):glyph('chevron-down')));
      button.dataset.status=status;
      summary.append(button);
    }
    summary.append(dialog);
    return summary;
  }
  return {includes,groups,count,originals,originalButton,matchesPrintedField,fieldLinks,issuedLimitBreach,receiptCitation,receiptEvidence,nativeReceiptCitation,mandateCitation,mandateEvidence,addendumEvidence,releaseProofs,warrantyProofs,boardProofs,overview};
})();
