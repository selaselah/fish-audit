const RevisionComparison = (() => {
  const groups=['状态有变','发现或依据有变','分别查阅','所比项目一致'];
  const names={H01:'签署与生效',H02:'交付与验收',H03:'付款安排',H04:'付款条件',H05:'实付时点',H06:'分笔付款',H07:'质保工单'};
  const changes={status:'状态',detail:'发现原文',basis:'核对依据',citations:'引文字段',records:'程序记录'};
  let active;
  const panel=()=>document.getElementById('revision-comparison');
  function params(rev,prior,entry) {
    const p=new URLSearchParams({rev,view:'revision-comparison',prior});
    if (entry) p.set('entry',entry);
    return p;
  }
  function clear() {
    active?.controller.abort(); active=null;
    const root=panel(); root.hidden=true; root.replaceChildren();
    delete root.dataset.caseId; delete root.dataset.rev; delete root.dataset.prior; delete root.dataset.entry;
  }
  function group(row) {
    if (!row.earlier || !row.later) return 2;
    return row.changes.includes('status')?0:row.changes.length?1:3;
  }
  function caption(row) {
    const s=row.later || row.earlier;
    const file=s.instrument && s.instrument.name+(s.instrument.page?' 第 '+s.instrument.page+' 页':'');
    return [row.earlier && row.later?'':row.earlier?'前版':'本版',s.stage,names[s.rule],file,
      (!row.later || !row.earlier || s.rule==='H05')?s.id:''].filter(Boolean).join(' · ');
  }
  function excerpt(detail,other) {
    const sentences=s=>s.match(/[^。！？]+[。！？]?/gu) || [];
    const here=sentences(detail), there=new Set(sentences(other || '').map(s=>s.trim()));
    const start=Math.max(0,here.findIndex(s=>!there.has(s.trim())));
    const next=here[start+1];
    if (other && next && !there.has(next.trim()) && (here[start]+next).length<=150) return (here[start]+next).trim();
    return here[start]?.trim() || detail;
  }
  function column(cid,meta,item,other,rowId,side) {
    const card=el('section','','revision-side');
    card.dataset.side=side; card.id='revision-'+rowId+'-'+side;
    const version=el('h3','R'+meta.rev);
    card.setAttribute('aria-labelledby',card.id+'-title'); version.id=card.id+'-title';
    const head=box('revision-side-head',version,el('small','规则 '+meta.rules));
    if (item) head.append(tag(item.status));
    card.append(head);
    if (!item) {card.append(el('p','本版缺少可唯一对应的发现。','small'));return card;}
    const original=excerpt(item.detail,other?.detail);
    card.append(el('blockquote',original));
    if (original!==item.detail || item.basis) {
      const full=fold(original===item.detail?'核对依据':item.basis?'完整发现与依据':'完整发现');
      full.firstChild.id=card.id+'-detail';
      if (original!==item.detail) full.append(el('p',item.detail));
      if (item.basis) {
        if (original!==item.detail) full.append(el('strong','本版核对依据'));
        full.append(el('p',item.basis,'revision-basis'));
      }
      card.append(full);
    }
    if (item.sources.length) {
      const list=el('ul','','revision-sources');
      for (const s of item.sources) {
        const a=Team.paperLink(s.name+' · '+s.page+' 页 '+s.line+' 行',cid,'',new URLSearchParams({rev:meta.rev,fact:s.ref}));
        a.id=card.id+'-'+s.ref.replaceAll('/','-');a.title=s.label;
        const li=el('li');li.append(a,el('q',s.text));
        if (s.different) {
          li.append(el('small','本版字段 · '+statusName(s.status)+' · '+s.value));
          if (s.quote!==s.text) li.append(el('small','本版引文 · '+s.quote));
        }
        list.append(li);
      }
      const cited=fold('原件引文 · '+item.sources.length+(item.source_count>item.sources.length?' / '+item.source_count:''),list);
      cited.firstChild.id=card.id+'-sources';card.append(cited);
    }
    const links=box('revision-links',Team.paperLink('查看本版发现',cid,'text-button',new URLSearchParams({rev:meta.rev,finding:item.id})));
    if (item.certificate) links.append(Team.paperLink('期满单原件',cid,'text-button',
      new URLSearchParams({rev:meta.rev,view:'warranty-certificate',stage:item.id})));
    links.firstChild.id=card.id+'-finding';
    if (item.certificate) links.lastChild.id=card.id+'-certificate';
    if (item.board_decision) {
      const board=Team.paperLink('董事会审批原件',cid,'text-button',new URLSearchParams({rev:meta.rev,view:'board-decision'}));
      board.id=card.id+'-board';links.append(board);
    }
    if (item.payment_quality) {
      const quality=Team.paperLink('验收款质量对照',cid,'text-button',new URLSearchParams({rev:meta.rev,view:'payment-checks',stage:item.id}));
      quality.id=card.id+'-quality';links.append(quality);
    }
    if (item.retest_reference || item.inspection_use) {
      const receipt=Team.paperLink(item.inspection_use?'验收单付款用途':'回单所引验收单',cid,'text-button',new URLSearchParams({rev:meta.rev,view:'payment-checks',stage:item.id}));
      receipt.id=card.id+'-retest';links.append(receipt);
    }
    card.append(links);
    return card;
  }
  function draw(job,comparison,versions,entry) {
    const root=panel(), {case_id:cid,earlier,later,rows}=comparison;
    const previous=el('select'); previous.id='revision-prior';
    for (const r of versions) previous.add(new Option('R'+r.rev,r.rev));
    previous.value=String(earlier.rev);
    previous.addEventListener('change',()=>{location.hash=Team.hash('case/'+cid+'?'+params(later.rev,previous.value));});
    const priorLabel=el('label','对照版本');priorLabel.htmlFor=previous.id;priorLabel.append(previous);
    const close=Team.paperLink('收起对照',cid,'text-button',new URLSearchParams({rev:later.rev}));
    const title=el('h2','履约版本对照'); title.id='revision-heading';
    const top=box('revision-head',title,close);
    const pick=el('select');pick.id='revision-entry';
    const ordered=groups.flatMap((_,i)=>rows.filter(r=>group(r)===i));
    for (const [i,label] of groups.entries()) {
      const matches=ordered.filter(r=>group(r)===i);
      if (!matches.length) continue;
      const options=el('optgroup');options.label=label+' · '+matches.length;
      for (const r of matches) options.append(new Option(caption(r),r.id));
      pick.append(options);
    }
    const pickLabel=el('label','履约发现');pickLabel.htmlFor=pick.id;pickLabel.append(pick);
    const body=box('revision-body');body.setAttribute('aria-live','polite');
    function show(id) {
      const current=ordered.find(r=>r.id===id || (r.earlier && 'old-'+r.earlier.id===id));
      if (!current) {
        pick.selectedIndex=-1;delete root.dataset.entry;
        body.replaceChildren(el('p',rows.length?'这两版中没有所选位置，请选择一项履约发现。':'所选版本中没有合同履约发现。','small'));
        return;
      }
      root.dataset.entry=id;pick.value=current.id;
      const label=current.changes.length?current.changes.map(s=>changes[s]).join('、')+'有变':groups[group(current)];
      body.replaceChildren(el('p',label,'revision-change'),box('revision-columns',
        column(cid,earlier,current.earlier,current.later,current.id,'earlier'),column(cid,later,current.later,current.earlier,current.id,'later')));
    }
    pick.addEventListener('change',()=>{
      show(pick.value);
      const route=Team.hash('case/'+cid+'?'+params(later.rev,earlier.rev,pick.value));
      history.replaceState(history.state,'',route);state.openedCitation=location.hash;job.entry=pick.value;
    });
    root.dataset.caseId=cid;root.dataset.rev=String(later.rev);
    root.replaceChildren(top,box('revision-options',priorLabel,pickLabel),body);
    show(entry || ordered[0]?.id);
  }
  function sync(data,bundle) {
    const slot=document.getElementById('revision-launch'), p=Team.route().params;
    const versions=bundle?data.revisions.filter(r=>r.rev<bundle.rev):[];
    const supported=bundle?.report.findings.some(f=>Object.hasOwn(names,f.rule));
    const origin=Team.cases()+'/'+data.id;
    const key=versions.length && supported?origin+'@'+bundle.rev+'/'+versions[0].rev:'';
    if (slot.dataset.key!==key) {
      slot.replaceChildren();slot.dataset.key=key;
      if (key) slot.append(Team.paperLink('对照前版',data.id,'text-button',params(bundle.rev,versions[0].rev)));
    }
    const opened=bundle && state.tab==='report' && p.get('view')==='revision-comparison';
    slot.hidden=!key || opened;
    if (!opened) {if (active || !panel().hidden) clear(); return;}
    const prior=versions.find(r=>String(r.rev)===p.get('prior')), entry=p.get('entry'), root=panel();
    if (!prior || ['rev','view','prior'].some(k=>p.getAll(k).length!==1) || p.getAll('entry').length>1 || String(bundle.rev)!==p.get('rev')) {
      clear();root.hidden=false;root.replaceChildren(el('p','这组底稿版本无法对照。','note'));return;
    }
    if (active?.bundle===bundle && active.prior===prior.rev && active.origin===origin && active.entry===entry) return;
    clear();
    const job={controller:new AbortController(),bundle,prior:prior.rev,origin,entry};
    active=job;root.hidden=false;root.dataset.prior=String(prior.rev);
    root.replaceChildren(el('p','正在读取两版底稿…','small'));
    api(origin+'/reports/'+bundle.rev+'/comparison/'+prior.rev,{signal:job.controller.signal}).then(result=>{
      if (active!==job || state.bundle!==bundle) return;
      if (result.format!=='contract-revision-comparison-v1' || result.case_id!==data.id ||
          result.earlier.rev!==prior.rev || result.later.rev!==bundle.rev || result.earlier.sha256!==prior.hash || result.later.sha256!==bundle.sha256)
        throw new Error('对照结果与所选底稿的版本摘要不符。');
      draw(job,result,versions,entry);
    }).catch(error=>{
      if (active!==job || job.controller.signal.aborted) return;
      root.replaceChildren(el('p',error.message,'note'),action('重新读取',()=>{clear();sync(data,bundle);},'text-button'));
    });
  }
  return {sync,clear};
})();
