const graphIndexes = new WeakMap();

function graphIndex(graph) {
  let index = graphIndexes.get(graph);
  if (!index) {
    index = {
      facts:new Map(graph.facts.map(f=>[f.id,f])),
      documents:new Map(graph.documents.map(d=>[d.id,d])),
      prior:new Map((graph.prior_invoices || []).map(r=>[r.id,r])),
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

function traceEvidence(report, finding, index) {
  const supported = new Set(report.graph.edges.filter(e=>e.type==='supports_result' && e.to==='finding/'+finding.id).map(e=>e.from));
  const groups = new Map();
  const other = [];
  for (const ref of finding.evidence) {
    if (!supported.has(ref)) continue;
    const fact = index.facts.get(ref);
    if (fact) {
      if (!groups.has(fact.doc)) groups.set(fact.doc,[]);
      groups.get(fact.doc).push(fact);
    } else if (index.prior.has(ref) || index.nodes.get(ref)?.type==='page') {
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
  if (other.length) panel.append(box('chips',...other));
  if (!groups.size && !other.length) {
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
  }
  select.addEventListener('change',render); render();
  return box('panel trace-panel',el('h2','审计证据路径'),label,trail);
}
