const graphIndexes = new WeakMap();

function graphIndex(graph) {
  let index = graphIndexes.get(graph);
  if (!index) {
    const prior = new Map((graph.prior_invoices || []).map(row=>[row.id,row]));
    for (const row of graph.prior_invoices || []) {
      for (const code of row.code_evidence || []) {
        prior.set(code.id,{...code,label:'发票代码',case_id:row.case_id,rev:row.rev,title:row.title,decision:row.decision});
      }
    }
    const history = graph.payment_history;
    for (const match of [...(history?.matches || []),...(history?.installments?.matches || [])]) {
      for (const fact of match.evidence) {
        prior.set(fact.id,{...fact,case_id:match.case_id,rev:match.rev,title:match.title,decision:match.decision});
      }
    }
    index = {
      facts:new Map(graph.facts.map(f=>[f.id,f])),
      documents:new Map(graph.documents.map(d=>[d.id,d])),
      prior,
      nodes:new Map(graph.nodes.map(n=>[n.id,n])),
    };
    graphIndexes.set(graph,index);
  }
  return index;
}

function lazyFold(title, build) {
  const details = fold(title);
  const expand = () => {
    if (!details.open) return;
    details.removeEventListener('toggle',expand);
    details.append(...build());
  };
  details.addEventListener('toggle',expand);
  return details;
}

function performanceComparison(finding, graph) {
  const comparisons = {
    H01: ['对照生效条件与签署依据',['effect_clause','buyer_signature','seller_signature','contract_state','approval_authority','approval_result','approved_on','approval_signer']],
    H02: ['对照验收范围、标准与结果',['acceptance_scope','quantity_agreed','quantity_accepted','acceptance_criteria','inspection_basis','measured_result','acceptance_result','acceptance_exception','acceptance_signer']],
    H05: ['对照付款和履约日期',['payment_designation','paid_on','effect_on','approved_on','accepted_on','warranty_release']],
  };
  const spec = comparisons[finding.rule];
  if (!spec) return null;
  const [title,fields] = spec;
  const index = graphIndex(graph);
  const citations = finding.evidence.map(ref=>index.facts.get(ref)).filter(f=>f && fields.includes(f.field));
  citations.sort((a,b)=>fields.indexOf(a.field)-fields.indexOf(b.field));
  if (!citations.length) return null;
  const details = lazyFold(title,()=>citations.map(fact=>{
    const row = box('performance-source',el('blockquote',fact.quote),box('flow',tag(fact.status),citation(fact.id)));
    row.dataset.sourceFact = fact.id;
    return row;
  }));
  details.classList.add('performance-comparison');
  details.open = ['risk','issue'].includes(finding.status);
  return details;
}

function accountPreview(fact, page) {
  const figure=el('figure','','account-preview');
  const caption=el('figcaption',fact.name+' · 第 '+fact.page+' 页');
  const surface=box('account-image',el('small','正在读取原页…','muted'));
  figure.append(surface,caption);
  const img=el('img');
  const title=fact.name+' 第 '+fact.page+' 页';
  img.alt=title+'整页图像';
  const rects=page?.layer==='text' ? fact.source_line?.rects || [] : [];
  const valid=rects.length && rects.every(r=>Array.isArray(r) && r.length===4 && r.every(n=>Number.isFinite(n) && n>=0 && n<=1) && r[0]<r[2] && r[1]<r[3]);
  loadReviewImage(img,workpaperSource(fact.doc,'pages/'+fact.page)).then(()=>{
    if (!valid) {
      surface.replaceChildren(img);
      return;
    }
    const width=img.naturalWidth,height=img.naturalHeight;
    const x=Math.max(0,Math.floor(Math.min(...rects.map(r=>r[0]))*width)-10);
    const y=Math.max(0,Math.floor(Math.min(...rects.map(r=>r[1]))*height)-8);
    const right=Math.min(width,Math.ceil(Math.max(...rects.map(r=>r[2]))*width)+10);
    const bottom=Math.min(height,Math.ceil(Math.max(...rects.map(r=>r[3]))*height)+8);
    const crop=el('canvas');
    crop.width=right-x; crop.height=bottom-y;
    const ctx=crop.getContext('2d');
    if (!ctx) { surface.replaceChildren(img); return; }
    ctx.drawImage(img,x,y,crop.width,crop.height,0,0,crop.width,crop.height);
    crop.setAttribute('role','img');
    crop.setAttribute('aria-label',title+'第 '+fact.source_line.number+' 行原图');
    surface.replaceChildren(crop);
    caption.textContent+=' · 原图第 '+fact.source_line.number+' 行';
  }).catch(()=>surface.replaceChildren(el('p','原页读取失败，可打开原页重试。','small')));
  return figure;
}

function accountComparison(item,graph) {
  const index=graphIndex(graph);
  const cited=[...new Set(item.evidence)].map(id=>index.facts.get(id)).filter(Boolean);
  const sides=[
    {kind:'contract',field:'contract_account',label:'合同约定收款账号'},
    {kind:'bank_receipt',field:'payee_account',label:'回单收款账号'}
  ].map(side=>({...side,facts:cited.filter(f=>f.field===side.field && graph.documents_by_kind[side.kind]?.includes(f.unit || f.doc))}));
  if (!sides.some(s=>s.facts.length)) return null;
  const details=lazyFold('逐位核对收款账号',()=>{
    const digits=f=>f.value.normalize('NFKC').replace(/\s/gu,'');
    const pair=sides.map(s=>s.facts.length===1 ? digits(s.facts[0]) : '');
    const completeDigits=/^[0-9]{8,32}$/;
    const gaps=sides.flatMap((s,i)=>{
      if (!s.facts.length) return [s.label+'缺少引文'];
      if (s.facts.length>1) return [s.label+'有 '+s.facts.length+' 条候选引文'];
      if (completeDigits.test(pair[i])) return [];
      return [s.label+(/[*•●…×]|^[0-9Xx]*[Xx]{2,}[0-9Xx]*$/.test(pair[i])?'含遮盖字符':'的字符或位数待核')];
    });
    const comparable=!gaps.length;
    const longer=pair[0].length>=pair[1].length ? pair[0] : pair[1];
    const first=Array.from(longer).findIndex((_,i)=>pair[0][i]!==pair[1][i]);
    const columns=box('account-evidence-grid');
    for (const [i,side] of sides.entries()) {
      const column=box('account-evidence-side',el('h4',side.label));
      if (!side.facts.length) column.append(el('p','本项尚缺该侧账号引文。','muted'));
      for (const f of side.facts) {
        const card=box('account-observation');
        card.dataset.accountFact=f.id;
        const number=digits(f);
        const isDigits=completeDigits.test(number);
        card.append(tag(f.status));
        if (isDigits) {
          const display=el('code','','account-digits');
          display.setAttribute('aria-label','抄录账号 '+number.split('').join(' '));
          for (let j=0;j<number.length;j+=4) {
            const group=el('span');
            for (let k=j;k<Math.min(number.length,j+4);k++) {
              if (comparable && number[k]!==pair[1-i][k]) group.append(el('mark',number[k]));
              else group.append(number[k]);
            }
            display.append(group);
          }
          card.append(display,el('small',number.length+' 位 · '+number.match(/^0*/)[0].length+' 个前导零','small'));
        } else {
          card.append(el('code',f.value,'account-digits'));
        }
        card.append(el('blockquote',f.quote));
        const uncovered=graph.gaps.filter(g=>g.quality==='uncovered' && g.doc===f.doc && g.page===f.page && g.field===f.field && g.quote);
        for (const gap of uncovered) {
          const printed=/^[^:0-9]+:([0-9]{8,32})$/.exec(gap.quote.normalize('NFKC').replace(/\s/gu,''));
          const length=printed?' · '+printed[1].length+' 位数字':'';
          card.append(box('account-native',el('small','待核文字层 · 第 '+gap.line+' 行'+length,'small'),el('blockquote',gap.quote)));
        }
        const preview=()=>accountPreview(f,index.nodes.get(f.doc+'/p'+f.page));
        card.append(side.facts.length===1 ? preview() : lazyFold('预览这处引文的原页',()=>[preview()]),
          action('打开原页核对引文',()=>openPage(f.doc,f.page,f.id),'ref'));
        column.append(card);
      }
      columns.append(column);
    }
    const detail=comparable ? (first<0?'两处抄录逐位相同。':'两处抄录从左数第 '+(first+1)+' 位开始不同。')
      : gaps.join('，')+'，请对照原页核实完整账号。';
    return [el('p',detail,'account-difference'),columns];
  });
  details.classList.add('account-comparison');
  return details;
}

const invoiceMatchLabel = {same:'完整标识相同',uncertain:'资料不足，需核对',different:'同号异代码，已排除'};

function signedInvoiceSource(row, comparison=row.comparison) {
  const source = row.source;
  const basis = {native_line:'原生文字层匹配',field_check:'审计人员已核对原件与页图',
    historical_record:'历史底稿记载的票号',historical_confirmation:'历史人工确认记录'}[source.basis];
  const origin = Team.paperLink('查看签收版原页',row.case_id,'source-jump',new URLSearchParams({rev:row.rev,fact:row.fact}));
  origin.target='_blank'; origin.rel='noopener';
  const original = link('下载前案原件',Team.cases()+'/'+row.case_id+'/documents/'+row.doc+'/original?rev='+row.rev,'source-jump');
  const where = '第 '+row.page+' 页'+(source.line ? ' · 第 '+source.line+' 行' : '');
  const hashes = lazyFold('核对文件摘要',()=>[
    el('p','原件 SHA-256'),el('code',row.source_hash),el('p','页图 SHA-256'),el('code',row.page_hash),
    el('p','文字层 SHA-256'),el('code',source.text_sha256),el('p','签收底稿 SHA-256'),el('code',row.report_hash),
    el('p','人工签收 SHA-256'),el('code',row.signoff_hash)]);
  const panel=box('invoice-source',el('strong',row.title+' · R'+row.rev),
    el('small','人工决定 · '+statusName(row.decision)+' · '+time(source.signed_at),'small'),
    el('blockquote',row.quote),el('small',basis+' · '+where,'small'),box('chips',origin,original));
  if (comparison) panel.append(el('strong',invoiceMatchLabel[comparison]));
  if (row.identity?.kind==='short_unresolved') panel.append(el('p','前案八位号码缺少可唯一核准的同页代码。','muted'));
  for (const code of row.code_evidence || []) {
    const jump=Team.paperLink('查看代码原文',row.case_id,'source-jump',new URLSearchParams({rev:row.rev,fact:code.fact}));
    jump.target='_blank'; jump.rel='noopener';
    const location='第 '+code.page+' 页'+(code.line?' · 第 '+code.line+' 行':'');
    panel.append(box('line',el('blockquote',code.quote),el('small',location+' · '+statusName(code.status),'small'),jump));
  }
  panel.append(hashes);
  return panel;
}

function invoiceApproval(check, digest) {
  const tasks = new Set(check.matches.map(m=>m.case_id));
  const exact = new Set(check.matches.filter(m=>!m.comparison || m.comparison==='same').map(m=>m.case_id));
  const uncertain = new Set(check.matches.filter(m=>m.comparison==='uncertain').map(m=>m.case_id));
  const label = check.outcome==='no_usable_number' ? '本版缺少可查的已核票号' :
    check.outcome==='incomplete_number' ? '有票号仅列部分字符，签收时无法完整查重' :
    check.outcome==='insufficient_identity' ? '八位票号的同页代码待核' :
    check.outcome==='possible_match' ? tasks.size+' 份同号任务需核对代码或单据归属' :
    '已查 '+check.numbers.length+(check.format==='invoice-approval-v1'?' 个票号':' 个票据标识')+' · '+
      (exact.size ? '命中 '+exact.size+' 份已签收任务'+(uncertain.size?'，另有 '+uncertain.size+' 份含待核引文':'') : '未命中已签收任务');
  const panel = fold('签收时的同票检查',el('strong',label),
    el('p','查验范围为本企业当时已签收的任务。所据底稿 R'+check.source_rev+'，签收版 R'+check.signed_rev+'。','muted'));
  panel.classList.add('invoice-approval');
  const index = graphIndex(state.bundle.report.graph);
  for (const number of check.numbers) {
    panel.append(box('line',el('strong',(number.code?number.code+' / ':'')+number.value),box('chips',...number.facts.map(citation))));
  }
  for (const item of check.withheld || []) {
    panel.append(box('line',el('strong',item.value+' · 号码待补全'),citation(item.fact)));
  }
  for (const match of check.matches) {
    const id='prior/'+match.case_id+'/r'+match.rev+'/'+match.fact;
    const row=index.prior.get(id);
    if (row) panel.append(Team.paperLink(row.title+' · R'+match.rev+' · '+statusName(match.decision),match.case_id,'source-jump',
      new URLSearchParams({rev:match.rev,fact:match.fact})));
  }
  panel.append(lazyFold('核对回执摘要',()=>[el('p','回执 SHA-256'),el('code',digest),
    el('p','查验底稿 SHA-256'),el('code',check.source_sha256),el('p','人工签收内容 SHA-256'),el('code',check.decision_sha256)]));
  if (check.screened?.length) panel.append(lazyFold('查看签收时的同号候选（'+check.screened.length+'）',
    ()=>check.screened.map(row=>signedInvoiceSource(row))));
  return panel;
}

function traceEvidence(report, finding, index) {
  const supported = new Set(report.graph.edges.filter(e=>e.type==='supports_result' && e.to==='finding/'+finding.id).map(e=>e.from));
  const groups = new Map();
  const archived = new Map();
  const other = [];
  for (const ref of finding.evidence) {
    if (!supported.has(ref)) continue;
    const fact = index.facts.get(ref);
    if (fact) {
      if (!groups.has(fact.doc)) groups.set(fact.doc,[]);
      groups.get(fact.doc).push(fact);
    } else if (index.prior.has(ref)) {
      const prior = index.prior.get(ref);
      const group = prior.case_id + '/' + prior.rev;
      if (!archived.has(group)) archived.set(group,[]);
      archived.get(group).push(prior);
    } else if (index.nodes.get(ref)?.type==='page') {
      other.push(citation(ref));
    }
  }
  const panel = box('trace-part trace-sources',el('h3','取用的原文'));
  for (const [doc,facts] of groups) {
    const source = lazyFold((index.documents.get(doc)?.name || doc)+' · '+facts.length+' 条',()=>facts.map(f=>{
      const button = action(f.label+' · 第 '+f.page+' 页',()=>openPage(f.doc,f.page,f.id),'source-jump');
      return box('trace-quote',box('panel-head',button,tag(f.status)),el('blockquote',f.quote));
    }));
    panel.append(source);
  }
  for (const rows of archived.values()) {
    const first = rows[0];
    panel.append(lazyFold(first.title+' · R'+first.rev+' · '+statusName(first.decision),()=>rows.map(row=>
      row.source?.format==='signed-invoice-v1' ? signedInvoiceSource(row,finding.invoice_lookup?.candidates.find(c=>c.id===row.id)?.comparison) :
        box('trace-quote',citation(row.id),el('blockquote',row.quote)))));
  }
  if (other.length) panel.append(box('chips',...other));
  if (!groups.size && !archived.size && !other.length) {
    panel.append(el('p','本项没有可定位的取值引文。','muted'));
    if (finding.scope.length) panel.append(el('p','检查范围包含 '+finding.scope.map(id=>index.nodes.get(id)?.label || id).join('、')));
  }
  return panel;
}

function provenancePanel(report) {
  const graph = report.graph;
  const index = graphIndex(graph);
  const programs = new Map(graph.edges.filter(e=>e.type==='procedure_result').map(e=>[e.to,e.from]));
  const severity = {issue:0,risk:1,missing:2,ok:3};
  const findings = report.findings.filter(f=>programs.has('finding/'+f.id)).sort((a,b)=>severity[a.status]-severity[b.status]);
  if (!findings.length) return null;
  const select=el('select'); select.id='trace-select';
  const key=report.case_id+'@'+state.bundle.rev;
  for (const f of findings) {
    const option=new Option(statusName(f.status)+' · '+f.rule+' '+f.title,f.id);
    if (f.id===state.traceId && state.traceKey===key) option.selected=true;
    select.add(option);
  }
  const label = el('label','选择审计发现'); label.append(select);
  const trail = box('trace-grid');
  function render() {
    const f = findings.find(item=>item.id===select.value);
    state.traceKey=key; state.traceId=f.id;
    const control=programs.get('finding/'+f.id);
    const rule=index.nodes.get(control);
    const methods=graph.edges.filter(e=>e.type==='method_reference' && e.to===control).map(e=>index.nodes.get(e.from)).filter(Boolean);
    const program=box('trace-part',el('h3','执行程序'),el('strong',rule.label+' · '+f.title),el('p',rule.basis));
    if (methods.length) program.append(lazyFold('制度出处与适用范围',()=>methods.map(sourceEntry)));
    const result=box('trace-part trace-result',el('h3','本项结论'),tag(f.status),el('p',f.detail));
    if (f.calculations?.length) result.append(lazyFold('复算金额',()=>f.calculations.map(calculationPanel)));
    trail.replaceChildren(program,traceEvidence(report,f,index),result);
    if (f.rule==='B03') {
      const comparison=accountComparison(f,graph);
      if (comparison) trail.append(comparison);
    }
    if (f.rule==='B08' && graph.payment_history?.installments) {
      const details=installmentDetails(graph.payment_history.installments);
      details.classList.add('trace-installments'); trail.append(details);
    }
  }
  select.addEventListener('change',render); render();
  return box('panel trace-panel',el('h2','审计证据路径'),label,trail);
}
