// Render only the signing lines and comparisons cited by this version of the workpaper.
const SigningParties = (() => {
  const sides = {buyer:'甲方', seller:'乙方', unspecified:'归属待核'};
  const roles = {party:'约定主体', signature:'签章栏', imprint:'印章单位'};
  const imageFormats = new Set(['contract-effect-sources-v5','contract-effect-sources-v6','contract-effect-sources-v7']);
  const formats = new Set(['contract-effect-sources-v4',...imageFormats]);
  const pending = {
    multiple:'同一方有多处记载', partial:'单位名称不完整', side:'印章归属待核',
    image_pending:'影像栏位待核', unlocated:'原行待定位', ambiguous:'多条候选待核', disputed:'栏位有异议',
    image:'需核对整页影像', party:'约定主体待核', signature:'签章栏待核图', pending:'原行依据待核'
  };

  function sources(graph) {
    const ledger = graph?.contract_effect_sources;
    if (!formats.has(ledger?.format) || !Array.isArray(ledger.signing_rows)) return [];
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

  function fieldBasis(row,record,graph) {
    const index=graphIndex(graph), ref=row.doc+'/p'+row.page;
    const page=index.nodes.get(ref), doc=index.documents.get(row.doc);
    const entries=record.field_sources?.filter(s=>s.row===row.id);
    const unknown={kind:'unknown',label:'来源待核',usable:false};
    if (entries?.length!==1 || !page || !doc) return unknown;
    const [entry]=entries;
    let kind='unlocated';
    if (page.layer==='text' && row.line!=null) kind=page.clause_text_only?'text':'mixed';
    if (['image','image_overlay'].includes(page.layer) && row.line==null) kind='image';
    const candidate=observation(row,graph);
    const fact=candidate && [value(row),row.quote].some(s=>s.normalize('NFC')===candidate.value.trim().normalize('NFC')) ? candidate : null;
    if (entry.kind!==kind || entry.fact!==(fact?.id || null) ||
        fact && (fact.source_sha256!==doc.sha256 || fact.page_sha256!==page.sha256) ||
        kind==='image' && fact?.source_line?.rects?.length ||
        !graph.edges.some(e=>e.type==='contains' && e.from===row.doc && e.to===ref && e.evidence.includes(ref))) return unknown;
    const owned=fact && graph.edges.some(e=>e.from===row.unit && e.type===row.field && e.evidence.includes(fact.id));
    const checked=Boolean(owned && fieldReceiptOperation(fact,doc,page));
    if (entry.receipt_rev!==(checked ? fact.attestation.rev : null) || entry.disputed!==(fact?.status==='disputed')) return unknown;
    if (entry.disputed) return {kind,label:'有异议',usable:false};
    if (kind==='unlocated') return {kind,label:'原行待定位',usable:false};
    if (kind==='text') {
      const usable=row.role==='imprint' || (row.role==='signature' ? checked : owned && ['anchored','confirmed'].includes(fact.status));
      return {kind,label:checked?'原行已核图':'文字原行',usable};
    }
    const label=kind==='mixed'?'图文':'影像';
    return {kind,label:label+(checked?'已核':'待核'),usable:checked};
  }

  function inspect(finding, record, available, graph) {
    const index = graphIndex(graph);
    const supports = index.supports.get('finding/'+finding.id);
    const rows = {}, basis=new Map();
    const expectedStatus = record.state === 'match' ? 'ok' : record.state === 'different' ? 'risk' : 'missing';
    let bound = finding.scope.includes(record.unit) && record.status === expectedStatus;
    for (const role of Object.keys(roles)) {
      const ids = record.rows[role];
      rows[role] = ids.map(id => available.find(r => r.id === id && r.side === record.side &&
        r.role === role && r.unit === record.unit && [id, r.doc+'/p'+r.page, ...r.facts].every(ref =>
          finding.evidence.includes(ref) && record.evidence.includes(ref) && supports?.has(ref)))).filter(Boolean);
      if (rows[role].length !== ids.length) bound = false;
      if (imageFormats.has(graph.contract_effect_sources.format)) {
        for (const row of rows[role]) basis.set(row.id,fieldBasis(row,record,graph));
      }
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
      if (bound && imageFormats.has(graph.contract_effect_sources.format)) {
        const required=record.state==='match' ? [original,subject,rows.signature[0]] : [original,subject];
        bound=required.every(row=>basis.get(row.id)?.usable);
      }
      if (bound && (record.state === 'match' || subject.role === 'signature')) {
        const signing=rows.signature[0], f=observation(signing,graph);
        bound = Boolean(fieldReceiptOperation(f,index.documents.get(signing.doc),index.nodes.get(signing.doc+'/p'+signing.page)));
      }
    }
    return {record,rows,original,subject,basis,state:bound ? record.state : 'pending',status:bound ? record.status : 'missing'};
  }

  function open(row,graph) {
    const fact = observation(row,graph);
    const layer=graphIndex(graph).nodes.get(row.doc+'/p'+row.page)?.layer;
    const located=fact && (layer==='text' || !fact.source_line?.rects?.length);
    openPage(row.doc,row.page,located ? fact.id : null,located ? undefined : row.line);
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
    if (!records?.length || !formats.has(graph.contract_effect_sources?.format)) return [];
    const available = sources(graph);
    return records.map(r => inspect(finding,r,available,graph));
  }

  function pagePair(view,graph) {
    const {original,subject,record,basis,state}=view;
    if (!['match','different'].includes(state) || original.doc===subject.doc && original.page===subject.page ||
        ![original,subject].some(r=>['image','mixed'].includes(basis.get(r.id)?.kind))) return null;
    const left=observation(original,graph), right=observation(subject,graph);
    if (!left || !right) return null;
    return {key:'signing-'+record.side,label:sides[record.side]+'约定与用印',left,right,
      signing:{original,subject,different:state==='different'}};
  }

  function pagePairs(finding,graph) {
    return comparisons(finding,graph).map(v=>pagePair(v,graph)).filter(Boolean);
  }

  function markQuotes(pair,quotes) {
    if (!pair?.signing?.different) return;
    const {original,subject}=pair.signing;
    for (const [i,row] of [original,subject].entries()) {
      const quote=quotes[i], name=sealName(row), other=sealName(i===0?subject:original);
      const offset=row.quote.indexOf(name,row.quote.search(/[:：]/u)+1);
      if (offset<0 || quote.textContent!==row.quote) continue;
      quote.replaceChildren(row.quote.slice(0,offset));
      markDifference(quote,other,name,name);
      quote.append(row.quote.slice(offset+name.length));
      quote.classList.add('seal-quote');
    }
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

  function reviewPages(finding,graph) {
    const ledger=graph.contract_effect_sources;
    if (!finding?.effect_review || !imageFormats.has(ledger?.format)) return [];
    const index=graphIndex(graph), support=index.supports.get('finding/'+finding.id);
    return finding.effect_review.mixed_pages.flatMap(p=>{
      const ref=p.doc+'/p'+p.page, doc=index.documents.get(p.doc), page=index.nodes.get(ref);
      const section=graph.audit_documents?.find(d=>d.source===p.doc && d.page===p.page);
      if (p.kind==='board_approval' || !finding.scope.includes(p.unit) || !graph.documents_by_kind.contract?.includes(p.unit) ||
          (section?.id || p.doc)!==p.unit || !finding.evidence.includes(ref) || !support?.has(ref) ||
          page?.type!=='page' || !doc || !/^[0-9a-f]{64}$/.test(doc.sha256) || !/^[0-9a-f]{64}$/.test(page.sha256) ||
          p.native!==(page.layer==='text') || p.text_only!==(page.clause_text_only===true) || (p.native && p.text_only) ||
          !ledger.pages.some(s=>s.doc===p.doc && s.unit===p.unit && s.page===p.page && s.kind===p.kind && s.native===p.native && s.text_only===p.text_only) ||
          !graph.edges.some(e=>e.type==='contains' && e.from===p.doc && e.to===ref && e.evidence.includes(ref)) ||
          (section && !graph.edges.some(e=>e.type==='contains_section' && e.from===p.doc && e.to===p.unit && e.evidence.includes(ref)))) return [];
      return [{...p,ref,name:doc.name}];
    });
  }

  function pagePreview(pages,inspector) {
    const rail=el('section','','seal-pages');
    rail.setAttribute('aria-label','合同影像原页');
    const filename=el('strong','','seal-filename'), caption=el('span','','seal-page-number');
    const picker=el('select','','seal-page-picker');
    picker.setAttribute('aria-label','选择待核合同原页');
    const multipleDocs=new Set(pages.map(p=>p.doc)).size>1;
    for (const [i,p] of pages.entries())
      picker.add(new Option((multipleDocs?p.name+' · ':'')+'第 '+p.page+' 页',String(i)));
    const choice=el('label','原页','seal-page-choice');
    choice.append(picker);
    const head=box('seal-page-head',filename,pages.length>1?choice:caption);
    const content=box('seal-preview-content');
    rail.append(head,content);
    let show;
    function render(i) {
      const p=pages[i], source=workpaperSource(p.doc,'pages/'+p.page);
      filename.textContent=p.name; filename.title=p.name; caption.textContent='第 '+p.page+' 页';
      picker.value=String(i); rail.dataset.page=p.ref; rail.dataset.preview='idle';
      const image=el('img'); image.alt=''; image.hidden=true;
      const placeholder=el('span','载入中','seal-preview-state');
      const frame=box('seal-thumb',image,placeholder);
      const thumb=action('',()=>openPage(p.doc,p.page),'seal-preview-link');
      thumb.append(frame,box('seal-open-label',glyph('arrows-angle-expand'),el('span','查看整页')),
        el('span','，'+p.name+'，第 '+p.page+' 页','visually-hidden'));
      const retry=action('重试',load,'seal-retry'); retry.hidden=true;
      content.replaceChildren(thumb,retry);
      async function load() {
        if (!inspector.open || !frame.isConnected || rail.dataset.preview==='loading') return;
        const focused=document.activeElement===retry;
        rail.dataset.preview='loading'; placeholder.textContent='载入中'; retry.disabled=true;
        try {
          await loadReviewImage(image,source);
          if (!frame.isConnected) return;
          image.hidden=false; placeholder.hidden=true; retry.hidden=true; rail.dataset.preview='image';
          if (focused) thumb.focus({preventScroll:true});
        } catch {
          if (!frame.isConnected) return;
          placeholder.textContent='页图未载入'; retry.hidden=false; retry.disabled=false; rail.dataset.preview='error';
          if (focused) retry.focus({preventScroll:true});
        }
      }
      show=()=>{if (rail.dataset.preview==='idle') load();};
      requestAnimationFrame(show);
    }
    picker.addEventListener('change',()=>render(picker.selectedIndex));
    inspector.addEventListener('toggle',()=>show());
    function showRows(rows) {
      for (const group of [rows.imprint,rows.signature,rows.party]) {
        const matches=pages.filter(p=>group.some(row=>row.doc===p.doc && row.page===p.page));
        if (!matches.length) continue;
        if (!matches.some(p=>p.ref===rail.dataset.page)) render(pages.indexOf(matches[0]));
        return;
      }
    }
    render(0);
    return {element:rail,showRows};
  }

  function panel(finding, graph, phases) {
    const views = comparisons(finding,graph);
    const pages = reviewPages(finding,graph);
    if (!views.length && !pages.length) return null;
    const root = el('details','','seal-inspector');
    const summary = el('summary');
    const badge = el('span','','seal-summary-status');
    summary.append(glyph('journal-text'),el('strong',views.length?'签章主体':'合同影像'),badge);
    const preview=pages.length ? pagePreview(pages,root) : null;
    if (!views.length) {
      badge.textContent='整页待核'; root.open=true;
      root.classList.add('seal-page-only');
      root.append(summary,preview.element);
      return root;
    }
    const choices = box('seal-choices'), body = box('seal-body');
    const panelId = 'seal-fields-'+finding.id;
    body.id = panelId; body.setAttribute('role','tabpanel');
    choices.setAttribute('role','tablist'); choices.setAttribute('aria-label','合同签署方');

    function select(i) {
      const {record,rows,original,subject,basis,state,status} = views[i];
      root.dataset.side = record.side; root.dataset.state = state; root.dataset.status = status;
      for (const [k,tab] of [...choices.children].entries()) {
        tab.tabIndex = k === i ? 0 : -1;
        tab.setAttribute('aria-selected', String(k === i));
      }
      body.setAttribute('aria-labelledby',choices.children[i].id);
      body.replaceChildren();
      preview?.showRows(rows);
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
          const field=el('span',label,'seal-field');
          const source=basis.get(row.id);
          if (source && (pages.length || source.kind!=='text')) {
            const origin=el('small',source.label+' · P'+row.page,'seal-origin');
            origin.dataset.kind=source.kind; origin.dataset.usable=String(Boolean(source.usable));
            const receipt=record.field_sources.find(s=>s.row===row.id)?.receipt_rev;
            if (source.usable && receipt) origin.title='核图所据底稿 R'+receipt;
            field.append(origin);
          }
          button.append(field,name,glyph('arrows-angle-expand'),el('span',location,'visually-hidden'));
          body.append(button);
        }
      }
      const held = phases.filter(f => f.status !== 'ok' && f.scope.includes(record.unit));
      const tools=box('seal-actions'), pair=pagePair(views[i],graph);
      if (pair) {
        const compare=action('双页对照',()=>showFindingPath(finding,true,pair.key),'seal-compare');
        compare.dataset.pair=pair.key; compare.prepend(glyph('layout-sidebar-inset-reverse'));
        tools.append(compare);
      }
      if (status !== 'ok' && held.length) {
        const jump = action(held.length+' 期付款待核',()=>{
          const tab = document.querySelector('[data-phase-choice="'+CSS.escape(held[0].id)+'"]');
          if (tab) { tab.click(); tab.focus(); }
        },'seal-payments');
        tools.append(jump);
      }
      if (tools.childElementCount) body.append(tools);
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
    root.dataset.overall=pages.length && initial.status==='ok' ? 'missing' : initial.status;
    badge.textContent = initial.state === 'match' ? '所列名称相符' :
      initial.state === 'different' ? (sides[initial.record.side] || '')+'名称有差异' : pending[initial.state] || '原行依据待核';
    root.open = Boolean(pages.length) || views.some(v=>v.status!=='ok');
    if (pages.length && initial.status==='ok') badge.textContent=finding.status==='risk'?'栏位同名 · 生效存疑':'栏位同名 · 整页待核';
    root.append(summary);
    if (preview) root.append(box('seal-review-grid',box('seal-fields',choices,body),preview.element));
    else root.append(choices,body);
    select(views.indexOf(initial));
    return root;
  }
  return {sources,observation,rectangles,open,panel,relations,pagePairs,markQuotes};
})();
