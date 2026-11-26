const PerformanceIndex = (() => {
  const scopes = [
    {id:'contract', label:'签署与生效', icon:'journal-text', rules:['H01']},
    {id:'acceptance', label:'交付验收', icon:'clipboard-check', rules:['H02']},
    {id:'payment', label:'分期与付款', icon:'receipt', rules:['H03','H04','H05','H06']},
  ];
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
    const label=item.execution_basis?'扣款凭证':item.title;
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
  // Only offer a direct original when the issued finding, observation and physical page agree.
  function originals(item,graph) {
    const index=graphIndex(graph), node=index.nodes.get('finding/'+item.id);
    if (node?.type!=='finding' || node.status!==item.status || node.detail!==item.detail) return [];
    const links=index.fieldLinks ??= new Set(graph.edges.filter(e=>e.evidence?.length===1 &&
      ((e.type==='records' && e.evidence[0]===e.to) || (e.type==='supports_result' && e.evidence[0]===e.from)))
      .map(e=>e.from+' '+e.to));
    const sources=[];
    for (const ref of new Set(traceReferences(graph,item))) {
      const fact=index.facts.get(ref), observation=index.nodes.get(ref);
      if (!fact || observation?.type!=='observation' || observation.status!==fact.status ||
          typeof fact.quote!=='string' || !fact.quote || !links.has(ref+' '+node.id)) continue;
      const doc=index.documents.get(fact.doc), pageId=fact.doc+'/p'+fact.page, page=index.nodes.get(pageId);
      if (!doc?.sha256 || doc.sha256!==fact.source_sha256 || index.nodes.get(doc.id)?.sha256!==doc.sha256 ||
        page?.type!=='page' || !page.sha256 || fact.page_sha256!==page.sha256 || !links.has(pageId+' '+ref)) continue;
      const loc=fact.source_line;
      const exact=['anchored','confirmed'].includes(fact.status) && Number.isSafeInteger(loc?.number) && loc.number>0 &&
        typeof loc.text==='string' && loc.text.normalize('NFKC').includes(fact.quote.normalize('NFKC')) &&
        Array.isArray(loc.rects) && loc.rects.length && loc.rects.every(rect=>Array.isArray(rect) &&
          rect.length===4 && rect.every(n=>Number.isFinite(n) && n>=0 && n<=1) && rect[0]<rect[2] && rect[1]<rect[3]);
      sources.push({fact,doc,line:exact?loc.number:null});
    }
    return sources;
  }
  function sourceView(item, graph) {
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
      quality.replaceChildren(el('span',line?'原行':'提取引文'),tag(fact.status));
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
    if (item.execution_basis && target('payment-proof')) return PaymentProof.jump(item);
    if (item.signer_timing && target('signer-timing')) return SignerEvidence.jump(item);
    if (item.payment_acceptance && target('payment-acceptance')) return PaymentAcceptance.jump(item);
    const areas=[
      [item.rule==='H01' && item.effect_review?.pdf_execution,'pdf-signatures','核对 PDF 签署凭证'],
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
  function pairedLines(item,report) {
    if (item.execution_basis) {
      const [entry]=PaymentProof.entries(report,[item]);
      if (!entry || !['conflict','limited','application'].includes(entry.state)) return null;
      const rows=[[entry.leftLabel,entry.left],[entry.rightLabel,entry.right]].flatMap(([label,group])=>
        group.filter(r=>r.clear && r.rects.length).map(r=>({...r,label})));
      return rows.length?{title:rows[0].file,rows}:null;
    }
    if (item.rule!=='H02' || item.status!=='issue') return null;
    const graph=report.graph, refs=originals(item,graph), kinds=graph.documents_by_kind || {};
    function only(field,kind) {
      const candidates=refs.filter(r=>r.line && r.fact.field===field && kinds[kind]?.includes(r.fact.unit || r.fact.doc));
      return candidates.length===1?candidates[0]:null;
    }
    const contract=only('acceptance_criteria','contract'), acceptance=only('measured_result','acceptance');
    if (!contract || !acceptance) return null;
    // This is the issued quantitative finding. Other procedures may cite the same fields as context.
    const findingText='合同要求“'+contract.fact.value+'”，验收原页记载“'+acceptance.fact.value+'”，实测值超出约定限值。';
    if (!item.detail.normalize('NFKC').includes(findingText.normalize('NFKC'))) return null;
    const rows=[contract,acceptance].map(({doc,fact,line})=>({
      label:doc.name,place:'第 '+fact.page+' 页 · 第 '+line+' 行',line,quote:fact.source_line.text,
      excerpt:()=>EvidenceCompare.lineExcerpt(fact,graphIndex(graph)),open:()=>openPage(doc.id,fact.page,fact.id),
    }));
    return {title:'合同标准与验收实测',rows};
  }
  function pairView(item,report) {
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
    section.append(lazyFold('其他字段引文',()=>[sourceView(item,report.graph)]));
    return section;
  }
  function overview(findings,graph,rev) {
    const groupsHere=groups(findings);
    const summary=box('performance-statuses scope-cards'), dialog=el('dialog','','scope-dialog');
    dialog.id='performance-index'; dialog.setAttribute('aria-labelledby','scope-title');
    const title=el('h2'); title.id='scope-title';
    const close=action('',()=>dialog.close(),'icon-button');
    close.append(glyph('x-lg')); close.setAttribute('aria-label','关闭履约检查');
    const filters=box('scope-filters'), checks=box('scope-checks'), detail=el('section','','scope-detail'), mobile=el('select');
    filters.setAttribute('role','group'); filters.setAttribute('aria-label','筛选本组检查');
    checks.setAttribute('role','group'); checks.setAttribute('aria-label','本组检查');
    mobile.className='scope-check-select'; mobile.setAttribute('aria-label','选择检查项');
    detail.setAttribute('aria-labelledby','scope-check-title');
    dialog.append(box('scope-head',box('',el('small','合同履约审查 · R'+rev),title),close),filters,mobile,box('scope-body',checks,detail));
    let shown=[],group,selected;
    function select(item) {
      selected=item.id; mobile.value=selected;
      for (const row of checks.children) row.setAttribute('aria-pressed',String(row.dataset.check===selected));
      const heading=el('h3',checkName(item)); heading.id='scope-check-title';
      const complete=action('完整检查',()=>{
        dialog.close(); revealPaperTarget(document.querySelector('[data-finding="'+CSS.escape(item.id)+'"]'));
      },'text-button');
      const jump=specialist(item);
      if (jump) jump.addEventListener('click',()=>dialog.close(),{capture:true});
      const actions=box('scope-actions',...(jump?[jump]:[]),complete);
      const paired=pairView(item,state.bundle.report);
      const roster=AcceptanceRoster.bind(item,state.bundle.report);
      detail.replaceChildren(box('scope-check-state',el('span',item.id,'mono'),tag(item.status)),heading);
      if (roster) {
        if (item.status==='issue' && item.detail) detail.append(el('p',item.detail.split('。')[0]+'。','scope-reason'));
        detail.append(AcceptanceRosterCard.render(roster,'scope-signers','page-dialog'));
        if (item.detail) detail.append(fold('本项检查结论',el('p',item.detail,'scope-reason')));
      } else if (!paired && item.detail) {
        const reason=el('p',item.detail,'scope-reason');
        detail.append(item.detail.length<=100?reason:fold('阅读本项结论',reason));
      }
      const fields=roster?lazyFold('其他字段引文',()=>[sourceView(item,graph)]):null;
      detail.append(paired || fields || sourceView(item,graph),actions);
    }
    function filter(pending) {
      shown=pending?priorityFindings(group.pending).concat(group.pending.filter(f=>!['risk','issue','missing'].includes(f.status))):group.items;
      [...filters.children].forEach((button,i)=>button.setAttribute('aria-pressed',String((i===0)===pending)));
      checks.replaceChildren(); mobile.replaceChildren();
      for (const item of shown) {
        const row=action('',()=>select(item),'scope-check'); row.dataset.check=item.id;
        row.append(el('small',item.id,'mono'),el('span',checkName(item)),tag(item.status));
        const option=el('option',item.id+' · '+checkName(item)+' · '+statusName(item.status)); option.value=item.id;
        checks.append(row); mobile.append(option);
      }
      select(shown.find(f=>f.id===selected) || shown[0]);
    }
    mobile.addEventListener('change',()=>select(shown.find(f=>f.id===mobile.value)));
    function open(scope) {
      group=scope; selected=null; title.textContent=scope.label;
      dialog.dataset.single=String(group.items.length===1);
      filters.hidden=!group.pending.length || group.pending.length===group.items.length;
      const pending=action('待核 '+group.pending.length,()=>filter(true));
      pending.disabled=!group.pending.length;
      filters.replaceChildren(pending,action('全部 '+group.items.length,()=>filter(false)));
      filter(Boolean(group.pending.length));
      dialog.showModal();
    }
    for (const scope of groupsHere) {
      const button=action('',()=>open(scope),'scope-card');
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
  return {groups,count,originals,overview};
})();
