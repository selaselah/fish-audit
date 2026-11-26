const WordSigning = (() => {
  const roles = {buyer:'甲方', seller:'乙方'};
  const labels = {
    buyer:['甲方签署','甲方签章','采购方签署','买方签章'],
    seller:['乙方签署','乙方签章','供应方签署','卖方签章'],
  };
  const names = {unread:'尚未提取', multiple:'有多条候选', disputed:'已登记异议', pending:'文字待核', checked:'文字已核', field:'字段错列'};

  function resolve(finding,graph,calls) {
    const check=finding?.effect_review?.word_signatures, ledger=graph?.contract_effect_sources;
    if (!check || ledger?.format!=='contract-effect-sources-v6' || !graph.documents_by_kind?.contract?.includes(check.unit) ||
        !finding.scope.includes(check.unit) || finding.status==='ok' || !Array.isArray(check.pages) ||
        !check.pages.length || !Array.isArray(check.rows)) return null;
    const index=graphIndex(graph), cited=new Set(traceReferences(graph,finding));
    const originals=ledger.pages.filter(p=>p.unit===check.unit);
    const textPages=originals.filter(p=>p.native && p.text_only && ['.docx','.doc'].includes(index.documents.get(p.doc)?.ext));
    const native=new Set(textPages.map(p=>p.doc+'/p'+p.page));
    const rows=SigningParties.sources(graph).filter(r=>r.unit===check.unit && r.role==='signature' &&
      Number.isInteger(r.line) && r.line>0 && native.has(r.doc+'/p'+r.page));
    const expected=rows.length ? new Set(rows.map(r=>r.doc+'/p'+r.page)) : native;
    if (expected.size!==check.pages.length || new Set(check.pages).size!==expected.size ||
        !check.pages.every(ref=>expected.has(ref)) || rows.length!==check.rows.length ||
        !rows.length && textPages.length!==originals.length) return null;
    const pages=textPages.filter(p=>expected.has(p.doc+'/p'+p.page));
    for (const p of pages) {
      const id=p.doc+'/p'+p.page, doc=index.documents.get(p.doc), page=index.nodes.get(id);
      const call=calls?.find(c=>c.doc===p.doc && c.page===p.page);
      if (!cited.has(id) || !['.docx','.doc'].includes(doc?.ext) || !p.native || !p.text_only ||
          page?.type!=='page' || page.layer!=='text' || !page.clause_text_only || !call?.clause_text_only ||
          !page.sha256 || call.page_sha256!==page.sha256 ||
          !graph.edges.some(e=>e.type==='contains' && e.from===p.doc && e.to===id && e.evidence.includes(id))) return null;
    }
    const readings=[];
    for (const [i,row] of rows.entries()) {
      const saved=check.rows[i], id=row.doc+'/p'+row.page, page=index.nodes.get(id), doc=index.documents.get(row.doc);
      const label=row.quote.split(/[:：]/u,1)[0].trim(), field=row.side+'_signature';
      if (saved?.row!==row.id || !labels[row.side]?.includes(label) || row.field!==field ||
          ![row.id,...row.facts].every(ref=>cited.has(ref)) || !row.facts.every(ref=>{
            const f=index.facts.get(ref);
            return f?.doc===row.doc && (f.unit || f.doc)===row.unit && f.page===row.page &&
              f.page_sha256===page.sha256 && f.source_sha256===doc.sha256 &&
              f.source_line?.number===row.line && f.source_line.text===row.quote;
          })) return null;
      const fact=row.facts.length===1 ? index.facts.get(row.facts[0]) : null;
      const literal=row.quote.slice(row.quote.search(/[:：]/u)+1).trim();
      let status;
      if (!fact) status=row.facts.length ? 'multiple' : 'unread';
      else if (fact.status==='disputed') status='disputed';
      else if (fact.field!==field) status='field';
      else if (fact.quote===row.quote && [row.quote,literal].includes(fact.value.trim()) &&
          fact.source_line.rects?.length && fieldReceiptOperation(fact,doc,page)) status='checked';
      else status='pending';
      if (saved.fact!==(fact?.id || null) || saved.state!==status ||
          saved.receipt_rev!==(status==='checked' ? fact.attestation.rev : null)) return null;
      readings.push({row,doc,fact,status,label,rev:saved.receipt_rev});
    }
    return {pages,readings,unit:check.unit};
  }

  function canReview() {
    return state.detail?.status==='ready' && state.detail.rev===state.bundle?.rev &&
      (!Team.current || ['admin','auditor'].includes(Team.current.role));
  }

  function editButton(reading) {
    if (!canReview() || !['pending','field','unread'].includes(reading.status)) return null;
    const {row,fact}=reading;
    if (fact && !fact.source_line.rects?.length) return null;
    if (!fact && state.bundle.report.graph.facts.some(f=>f.doc===row.doc && f.page===row.page &&
        f.field===row.field && !f.source_line)) return null;
    const edit=action(fact?'更正字段':'补录字段',()=>openAmend(row.doc,row.page,fact,{field:row.field,quote:row.quote}),'word-edit');
    edit.dataset.wordEdit=row.id;
    edit.setAttribute('aria-label',edit.textContent+'，'+reading.label+'，第 '+row.line+' 行');
    return edit;
  }

  function panel(finding,graph,findings,calls) {
    const data=resolve(finding,graph,calls);
    if (!data) return null;
    const index=graphIndex(graph), root=el('details','','seal-inspector word-signatures');
    root.id='word-signatures'; root.tabIndex=-1;
    const summary=el('summary');
    summary.append(glyph('journal-text'),el('strong','签署凭证'),el('span','待补核','word-pending'));
    const body=box('word-signing-body'), note=box('word-requirement',el('span','需取得本版合同的签署页或电子签署记录。'));
    if (canReview()) {
      const draft=action('拟补件意见',()=>{
        openReview();
        $('#review-decision').value='return';
        $('#review-decision').dispatchEvent(new Event('change'));
        const doc=index.documents.get(data.pages[0].doc);
        $('#review-note').value='请补充与《'+doc.name+'》对应的签署版原件或电子签署记录，并注明签署方和所对应的合同版本。';
        $('#review-note').focus();
      },'word-draft');
      note.append(draft);
    }
    root.append(summary,body);
    if (!data.readings.length) {
      body.append(note);
      for (const p of data.pages) body.append(action('查看原件第 '+p.page+' 页',()=>openPage(p.doc,p.page),'ref'));
      return root;
    }
    const picker=box('word-sides'), content=box('word-reading');
    picker.setAttribute('role','tablist'); picker.setAttribute('aria-label','签章栏');
    content.id='word-signing-reading'; content.setAttribute('role','tabpanel');
    const phaseBox=box('word-related'), phases=findings.filter(f=>['H04','H05'].includes(f.rule) && f.stage);
    let active=0, request=0;
    function show(position) {
      active=position;
      const reading=data.readings[position], {row,fact,status,doc}=reading;
      for (const [i,b] of [...picker.children].entries()) {
        b.tabIndex=i===position?0:-1;
        b.setAttribute('aria-selected',String(i===position));
      }
      content.setAttribute('aria-labelledby',picker.children[position].id);
      content.dataset.row=row.id;
      const location='第 '+row.page+' 页 · 第 '+row.line+' 行';
      const original=action('',()=>openPage(row.doc,row.page,null,row.line),'word-excerpt');
      original.setAttribute('aria-label','打开'+doc.name+'，'+location+'，'+row.quote);
      const preview=el('span',row.quote,'word-line');
      original.append(box('word-file',el('span',doc.name),el('small',location),glyph('arrows-angle-expand')),preview);
      const readingLabel=el('span',names[status],'word-reading-state');
      const fields=box('word-reading-meta',readingLabel);
      if (status==='checked') {
        const params=new URLSearchParams({rev:String(reading.rev)});
        if (fact.attestation.source_check.operation!=='add') params.set('fact',fact.id);
        const previous=Team.paperLink('核图底稿 R'+reading.rev,state.detail.id,'source-jump',params);
        previous.target='_blank'; previous.rel='noopener'; fields.append(previous);
      } else fields.append(el('span',status==='field' ? fact.label+' → '+reading.label : reading.label));
      const edit=editButton(reading);
      if (edit) fields.append(edit);
      content.replaceChildren(original,fields);
      const current=++request;
      if (root.open && fact?.source_line.rects?.length) EvidenceCompare.lineExcerpt(fact,index).then(canvas=>{
        if (current===request && canvas) {
          canvas.setAttribute('aria-hidden','true'); preview.replaceChildren(canvas);
        }
      }).catch(()=>{}); // The same printed quotation and the full-page action remain available.
      const linked=phases.filter(f=>f.scope.includes(data.unit) && traceReferences(graph,f).includes(row.id));
      phaseBox.replaceChildren(); phaseBox.hidden=!linked.length;
      if (linked.length) {
        phaseBox.append(el('small','引用此行'));
        for (const f of linked) {
          const label=f.stage.name+(f.rule==='H05'?'实付':'');
          const jump=action(label,()=>revealPaperTarget(document.querySelector('[data-finding="'+CSS.escape(f.id)+'"]')),'word-phase');
          jump.dataset.wordPhase=f.id; jump.setAttribute('aria-label',label+' · '+statusName(f.status)+'，查看审计依据');
          phaseBox.append(jump);
        }
      }
    }
    for (const [i,{row}] of data.readings.entries()) {
      let name=roles[row.side];
      if (data.readings.some((r,j)=>i!==j && r.row.side===row.side)) name+=' · '+row.page+' 页 '+row.line+' 行';
      const tab=action(name,()=>show(i),'seal-side');
      tab.id='word-signing-tab-'+i; tab.setAttribute('role','tab'); tab.setAttribute('aria-controls',content.id);
      tab.addEventListener('keydown',event=>{
        const n=data.readings.length;
        const to={ArrowLeft:(i+n-1)%n,ArrowRight:(i+1)%n,Home:0,End:n-1}[event.key];
        if (to!==undefined) { event.preventDefault(); show(to); picker.children[to].focus(); }
      });
      picker.append(tab);
    }
    body.append(picker,content,note,phaseBox);
    root.addEventListener('toggle',()=>{ if (root.open) show(active); else request++; });
    show(0);
    return root;
  }
  return {resolve,panel,editButton};
})();
