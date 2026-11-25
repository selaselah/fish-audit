// Render only the signing lines and comparisons cited by this version of the workpaper.
const SigningParties = (() => {
  const sides = {buyer:'甲方', seller:'乙方', unspecified:'归属待核'};
  const roles = {party:'约定主体', signature:'签章栏', imprint:'印章单位'};
  const pending = {
    multiple:'同一方有多处记载', partial:'单位名称不完整', side:'印章归属待核',
    image:'需核对整页影像', party:'约定主体待核', signature:'签章栏待核图', pending:'原行依据待核'
  };

  function sources(graph) {
    const ledger = graph?.contract_effect_sources;
    if (ledger?.format !== 'contract-effect-sources-v4' || !Array.isArray(ledger.signing_rows)) return [];
    const index = graphIndex(graph);
    const links = new Map(graph.edges.filter(e => e.type === 'contract_signing_source').map(e => [e.to,e]));
    return ledger.signing_rows.filter(row => {
      const node = index.nodes.get(row.id);
      const page = row.doc+'/p'+row.page;
      const link = links.get(row.id);
      return graph.documents_by_kind.contract?.includes(row.unit) &&
        ledger.pages.some(p => p.unit === row.unit && p.doc === row.doc && p.page === row.page) &&
        node?.type === 'contract_signing_line' && node.doc === row.doc && node.page === row.page &&
        node.line === row.line && node.label === row.quote && index.nodes.get(page)?.type === 'page' &&
        link?.from === page && link.evidence.length === row.facts.length+1 &&
        link.evidence[0] === page && row.facts.every((id,i) => link.evidence[i+1] === id);
    });
  }

  function observation(row, graph) {
    const index = graphIndex(graph);
    const matches = row.facts.map(id => index.facts.get(id)).filter(f =>
      f && f.doc === row.doc && (f.unit || f.doc) === row.unit && f.page === row.page &&
      f.field === row.field && f.quote === row.quote && (row.line == null ||
        f.source_line?.number === row.line && f.source_line.text === row.quote && f.source_line.rects?.length));
    return matches.length === 1 ? matches[0] : null;
  }

  function value(row) {
    const colon = row.quote.search(/[:：]/u);
    return colon < 0 ? row.quote : row.quote.slice(colon+1).trim();
  }

  function rectangles(row,graph) {
    if (!row.line) return [];
    const index=graphIndex(graph);
    const doc=index.documents.get(row.doc), page=index.nodes.get(row.doc+'/p'+row.page);
    const candidates=row.facts.map(id=>index.facts.get(id)).filter(f=>
      f && f.doc===row.doc && f.page===row.page && (f.unit || f.doc)===row.unit &&
      f.source_sha256===doc?.sha256 && f.page_sha256===page?.sha256 &&
      f.source_line?.number===row.line && f.source_line.text===row.quote && f.source_line.rects?.length);
    const bounds=candidates[0]?.source_line.rects || [];
    return candidates.every(f=>JSON.stringify(f.source_line.rects)===JSON.stringify(bounds)) ? bounds : [];
  }

  function sealName(row) {
    const name = value(row);
    return row.role === 'signature' ? name.replace(/(?:（已盖章）|\(已盖章\)|已盖章)$/u,'').trimEnd() : name;
  }

  function inspect(finding, record, available, graph) {
    const index = graphIndex(graph);
    const supports = index.supports.get('finding/'+finding.id);
    const rows = {};
    const expectedStatus = record.state === 'match' ? 'ok' : record.state === 'different' ? 'risk' : 'missing';
    let bound = finding.scope.includes(record.unit) && record.status === expectedStatus;
    for (const role of Object.keys(roles)) {
      const ids = record.rows[role];
      rows[role] = ids.map(id => available.find(r => r.id === id && r.side === record.side &&
        r.role === role && r.unit === record.unit && [id, r.doc+'/p'+r.page, ...r.facts].every(ref =>
          finding.evidence.includes(ref) && record.evidence.includes(ref) && supports?.has(ref)))).filter(Boolean);
      if (rows[role].length !== ids.length) bound = false;
    }
    const [left,right] = record.comparison;
    const original = rows.party.find(r => r.id === left);
    const subject = [...rows.imprint,...rows.signature].find(r => r.id === right);
    const relation = graph.edges.some(e => e.type === 'contract_seal_name_comparison' &&
      e.from === left && e.to === right && e.side === record.side && e.status === record.status &&
      e.evidence.length === record.evidence.length && e.evidence.every((id,i) => id === record.evidence[i]));
    if (record.status === 'ok' || record.status === 'risk') {
      const declared=original && observation(original,graph);
      bound &&= Boolean(subject && relation && declared && ['anchored','confirmed'].includes(declared.status) &&
        graph.edges.some(e=>e.from===record.unit && e.type===record.side && e.evidence.includes(declared.id)));
      if (bound && record.state === 'match') {
        bound = rows.signature.length === 1 && rows.imprint.length === 1 &&
          sealName(original) === sealName(subject) && sealName(original) === sealName(rows.signature[0]) &&
          Boolean(observation(rows.signature[0],graph));
      } else if (bound) {
        bound = record.state === 'different' && sealName(original) !== sealName(subject);
      }
      if (bound && (record.state === 'match' || subject.role === 'signature')) {
        const signing=rows.signature[0], f=observation(signing,graph);
        bound = Boolean(fieldReceiptOperation(f,index.documents.get(signing.doc),index.nodes.get(signing.doc+'/p'+signing.page)));
      }
    }
    return {record,rows,original,subject,state:bound ? record.state : 'pending',status:bound ? record.status : 'missing'};
  }

  function open(row,graph) {
    const fact = observation(row,graph);
    openPage(row.doc,row.page,fact?.id || null,fact ? undefined : row.line);
  }

  function markDifference(span, base, current, printed) {
    const a = Array.from(base), b = Array.from(current);
    let start = 0, end = 0;
    while (start < a.length && start < b.length && a[start] === b[start]) start++;
    while (end < a.length-start && end < b.length-start && a[a.length-1-end] === b[b.length-1-end]) end++;
    const difference = b.slice(start,b.length-end).join('');
    if (!difference) span.append(current);
    else span.append(b.slice(0,start).join(''),el('mark',difference),b.slice(b.length-end).join(''));
    if (printed.length>current.length) span.append(el('span',printed.slice(current.length),'seal-suffix'));
  }

  function comparisons(finding,graph) {
    const records = finding?.effect_review?.party_seals;
    if (!records?.length || graph.contract_effect_sources?.format !== 'contract-effect-sources-v4') return [];
    const available = sources(graph);
    return records.map(r => inspect(finding,r,available,graph));
  }

  function relations(finding,graph) {
    const paired=comparisons(finding,graph).filter(v=>v.state==='match' || v.state==='different');
    if (!paired.length) return null;
    const disclosure=lazyFold('签章主体的原行关系（'+paired.length+'）',()=>paired.map(view=>{
      const label=sides[view.record.side]+(view.state==='different'?' · 名称有差异':' · 所列名称相符');
      const row=box('seal-pair',el('strong',label),citation(view.original.id),citation(view.subject.id));
      row.dataset.side=view.record.side;
      return row;
    }));
    disclosure.classList.add('signing-relations');
    return disclosure;
  }

  function panel(finding, graph, phases) {
    const views = comparisons(finding,graph);
    if (!views.length) return null;
    const root = el('details','','seal-inspector');
    const summary = el('summary');
    const badge = el('span','','seal-summary-status');
    summary.append(glyph('journal-text'),el('strong','签章主体'),badge);
    const choices = box('seal-choices'), body = box('seal-body');
    const panelId = 'seal-fields-'+finding.id;
    body.id = panelId; body.setAttribute('role','tabpanel');
    choices.setAttribute('role','tablist'); choices.setAttribute('aria-label','合同签署方');

    function select(i) {
      const {record,rows,original,subject,state,status} = views[i];
      root.dataset.side = record.side; root.dataset.state = state; root.dataset.status = status;
      for (const [k,tab] of [...choices.children].entries()) {
        tab.tabIndex = k === i ? 0 : -1;
        tab.setAttribute('aria-selected', String(k === i));
      }
      body.setAttribute('aria-labelledby',choices.children[i].id);
      body.replaceChildren();
      for (const [role,label] of Object.entries(roles)) {
        // A direct signature discrepancy can exist on a contract with no separate imprint field.
        if (!rows[role].length && !record.rows[role].length && (role === 'imprint' || record.side === 'unspecified')) continue;
        const items = rows[role].length ? rows[role] : [null];
        for (const row of items) {
          const name = el('span','','seal-value');
          if (!row) {
            body.append(box('seal-row seal-empty',el('span',label,'seal-field'),el('span','原行待核')));
            continue;
          }
          const printed = value(row);
          if (state === 'different' && row.id === subject.id)
            markDifference(name,sealName(original),sealName(subject),printed);
          else if (state === 'different' && row.id === original.id)
            markDifference(name,sealName(subject),sealName(original),printed);
          else if (role === 'signature' && sealName(row)!==printed) {
            const company=sealName(row);
            name.append(company,el('span',printed.slice(company.length),'seal-suffix'));
          }
          else name.textContent = printed;
          const button = action('',()=>open(row,graph),'seal-row');
          button.dataset.signingRow = row.id;
          button.title=row.quote;
          const location='，查看原件第 '+row.page+' 页'+(row.line ? '第 '+row.line+' 行' : '');
          button.append(el('span', label,'seal-field'),name,glyph('arrows-angle-expand'),el('span',location,'visually-hidden'));
          body.append(button);
        }
      }
      const held = phases.filter(f => f.status !== 'ok' && f.scope.includes(record.unit));
      if (status !== 'ok' && held.length) {
        const jump = action(held.length+' 期付款待核',()=>{
          const tab = document.querySelector('[data-phase-choice="'+CSS.escape(held[0].id)+'"]');
          if (tab) { tab.click(); tab.focus(); }
        },'seal-payments');
        body.append(jump);
      }
    }
    for (const [i,view] of views.entries()) {
      const side = view.record.side;
      const short = view.status === 'risk' ? '差异' : view.status === 'ok' ? '相符' : '待核';
      const tab = action((sides[side] || '待归属')+' · '+short,()=>select(i),'seal-side');
      tab.dataset.side = side; tab.dataset.status = view.status;
      tab.id = panelId+'-'+side; tab.setAttribute('role','tab'); tab.setAttribute('aria-controls',panelId);
      tab.addEventListener('keydown',event=>{
        const next = {ArrowLeft:(i+views.length-1)%views.length,ArrowRight:(i+1)%views.length,Home:0,End:views.length-1}[event.key];
        if (next === undefined) return;
        event.preventDefault(); select(next); choices.children[next].focus();
      });
      choices.append(tab);
    }
    const initial = views.find(v=>v.status==='risk') || views.find(v=>v.status!=='ok') || views[0];
    root.dataset.overall=initial.status;
    badge.textContent = initial.state === 'match' ? '所列名称相符' :
      initial.state === 'different' ? (sides[initial.record.side] || '')+'名称有差异' : pending[initial.state] || '原行依据待核';
    root.open = views.some(v=>v.status!=='ok');
    root.append(summary,choices,body); select(views.indexOf(initial));
    return root;
  }
  return {sources,observation,rectangles,open,panel,relations};
})();
