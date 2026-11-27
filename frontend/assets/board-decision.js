// Inspect the archived approval filing, the contract clause and the checks that cite it.
const BoardDecision=(()=>{
  const tabs=[['decision','决议原文'],['signing','签发版本'],['payments','关联期款']];
  function panel(finding,report) {
    const check=finding.effect_review?.board_decision;
    if (!check) return null;
    const root=el('section','','board-decision');root.id='board-decision';root.tabIndex=-1;
    root.setAttribute('aria-label','董事会审批原件');
    const verified=PerformanceIndex.boardProofs(finding,report);
    if (!verified) {
      root.append(el('p','本版签发凭证与所引原件尚待核对。','note'));
      return root;
    }
    const {proofs,fields}=verified, rev=state.bundle.rev, cid=report.case_id, graph=report.graph, index=graphIndex(graph);
    root.dataset.caseId=cid;root.dataset.rev=String(rev);
    const controls=box('board-tabs'), body=box('board-body'), foot=box('release-foot');
    controls.setAttribute('role','group');controls.setAttribute('aria-label','董事会决议核对项目');
    const filebar=box('warranty-file-head'), pick=el('select');
    pick.setAttribute('aria-label','选择董事会审批原件');pick.id='board-filing-choice';
    for (const {record,doc,page} of proofs) pick.add(new Option(doc.name+(record.unit===doc.id?'':' · 第 '+page+' 页'),record.unit));
    const route=Team.route().params, pinned=route.get('view')==='board-decision';
    const setting=pinned?route.get('filing'):null;
    let unit=setting || proofs[0].record.unit, part=pinned && route.get('part') || 'decision';
    const query=()=>new URLSearchParams({rev,view:'board-decision',filing:unit,part});
    const choose=(paper,tab)=>{
      unit=paper;part=tab;draw();
      if (pinned) {
        history.replaceState(history.state,'',Team.hash('case/'+cid+'?'+query()));
        state.openedCitation=location.hash;
      }
    };
    for (const [key,label] of tabs) {
      const button=action(label,()=>choose(unit,key),'seg');
      button.id='board-tab-'+key;button.dataset.part=key;controls.append(button);
    }
    pick.addEventListener('change',()=>choose(pick.value,part));
    function row(label,key,proof) {
      const source=fields[key], f=source?.fact;
      if (!f || key!=='effect_clause' && (f.unit || f.doc)!==proof.record.unit) return null;
      const jump=action(source.doc.name+' · 第 '+f.page+' 页 '+source.line+' 行',()=>openPage(f.doc,f.page,f.id),'text-button');
      jump.id='board-line-'+f.id.replaceAll('/','-');jump.dataset.boardField=key;
      const field=box('board-row',el('small',label),el('q',f.source_line.text),jump);
      field.id=jump.id+'-row';field.dataset.boardRow=key;
      return field;
    }
    function draw() {
      for (const b of controls.children) b.setAttribute('aria-pressed',String(part===b.dataset.part));
      const proof=proofs.find(p=>p.record.unit===unit);
      if (!proof || !tabs.some(([key])=>key===part)) {
        filebar.replaceChildren(pick);pick.selectedIndex=-1;foot.replaceChildren();
        body.replaceChildren(el('p','本版没有所选的审批原件或核对位置。','note'));
        delete root.dataset.boardFiling;delete root.dataset.boardPart;
        return;
      }
      const {record,doc,page}=proof, prefix='board-'+record.unit.replaceAll('/','-');
      root.dataset.boardFiling=unit;root.dataset.boardPart=part;root.dataset.state=record.state;
      const file=action(doc.name,()=>openPage(doc.id,page),'warranty-file');file.id=prefix+'-page';
      file.dataset.boardPage=doc.id+'/p'+page;
      file.prepend(glyph('file-earmark-text'));file.append(glyph('arrows-angle-expand'));
      filebar.replaceChildren(file,el('strong',proof.label,'warranty-file-state'));
      if (proofs.length>1) {pick.value=unit;filebar.append(pick);}
      body.replaceChildren();
      if (part==='decision') {
        const pair=box('board-rows');
        for (const [label,key] of [['合同约定','effect_clause'],['审批单所列决定','approval_result']]) {
          const item=row(label,key,proof);
          pair.append(item || box('board-row',el('small',label),el('p','请核对原页','small')));
        }
        body.append(pair);
        const more=['approval_authority','approved_on','approval_signer'].map((k,i)=>row(['审批机构','决定日期','审批签认'][i],k,proof)).filter(Boolean);
        if (more.length) {
          const foldout=fold('机构、日期与签认',...more);foldout.firstChild.id=prefix+'-identity';body.append(foldout);
        }
        if (!check.linked) body.append(el('p','审批单与合同、约定机构的归属待核。','small'));
      } else if (part==='signing') {
        if (proof.signature?.signatures.length) body.append(PdfSignatureCard.digital(proof.signature));
        if (proof.notes?.length) for (const [i,n] of proof.notes.entries()) {
          const note=box('warranty-original-note',el('small',n.author?'原批注 · '+n.author:'原批注'),el('blockquote',n.text));
          note.dataset.boardNote=n.id;note.id=prefix+'-note-'+(i+1);
          if (n.location) {
            const loc=n.location;
            const jump=action('第 '+loc.page+' 页 · 第 '+loc.line+' 行',()=>openPage(doc.id,loc.page,loc.facts[0],loc.line),'text-button');
            jump.id=note.id+'-line';note.append(jump);
          }
          body.append(note);
        }
        if (record.unplaced || proof.word?.coverage && proof.word.coverage!=='complete')
          body.append(el('p','部分审阅内容的页行归属待核。','small'));
        const next={typeset:'取得签发原件或对应签署记录。',visual:'查验整页签认和批准范围。',current:'查验签署人身份、议决权限和最终决议。',
          earlier:'查验签后变更与最终表决文本。',mismatch:'核对签署平台留存的原件。',word_review:'查验批注是否采纳及签认定稿。',
          word_text:'取得已签认的定稿。',word_visual:'查验图形签认与最终版本。',photo:'打开整页核对签认、所属合同与审批机构。'};
        body.append(el('p',next[record.state] || '查验决议原件及签发依据。','small'));
      } else {
        const items=report.findings.filter(f=>['H04','H05'].includes(f.rule) && f.scope.includes(unit) && f.evidence.includes(record.id) &&
          index.nodes.get('finding/'+f.id)?.status===f.status && graph.edges.some(e=>e.type==='supports_result' &&
            e.from===record.id && e.to==='finding/'+f.id && e.evidence.length===1 && e.evidence[0]===record.id));
        for (const f of items) {
          const jump=Team.paperLink((f.stage?.name || '期次待核')+' · '+(f.rule==='H04'?'付款条件':'实付时点'),cid,'text-button',new URLSearchParams({rev,finding:f.id}));
          jump.id=prefix+'-'+f.id;body.append(box('board-payment',jump,tag(f.status)));
        }
        if (!items.length) body.append(el('p','本版没有引用这份决议的期款检查。','small'));
      }
      const download=link('下载原件',workpaperSource(doc.id,'original'),'release-download');download.download=doc.name;download.id=prefix+'-download';
      const fixed=Team.paperLink('R'+rev+' 固定链接',cid,'release-download',query());fixed.id=prefix+'-link';
      const verify=originalFileCheck(download.href,doc.sha256);verify.querySelector('button').id=prefix+'-verify';
      foot.replaceChildren(box('release-file-actions',download,fixed),verify);
    }
    root.append(filebar,controls,body,foot);draw();
    root.addEventListener('select-board-decision',e=>{unit=e.detail.get('filing') || proofs[0].record.unit;part=e.detail.get('part') || 'decision';draw();});
    return root;
  }
  return {panel};
})();
