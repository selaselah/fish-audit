// Review image observations on their archived pages. A field receipt attests only its own quote.
const WarrantyImages=(()=>{
  const labels={
    warranty_ticket_state:['工单状态','维修工单状态'],warranty_closed_on:['关闭日期','工单关闭日期'],
    warranty_closed_by:['采购方关闭签认','买方关闭签认'],warranty_ticket_id:['质保工单编号','维修工单编号','报修工单编号'],
    warranty_reported_on:['报修日期'],warranty_fault:['报修事项','报修故障'],
  };
  const short={warranty_ticket_state:'工单状态',warranty_closed_on:'关闭日期',warranty_closed_by:'采购方签认',warranty_ticket_id:'工单编号',
    warranty_reported_on:'报修日期',warranty_fault:'报修事项'};
  const norm=s=>String(s ?? '').normalize('NFKC').trim();
  function fieldStatus(f,doc,node) {
    if (f.status==='disputed') return '有异议';
    const a=f.attestation, receipt=a?.source_check || f.amendment?.source_check;
    const confirmed=a?.decision==='confirm' && receipt?.operation==='confirm';
    const amended=f.amendment && receipt?.operation==='amend';
    const bundle=state.bundle;
    if (f.status==='confirmed' && (confirmed || amended) && receipt?.format==='field-source-v1' &&
        receipt.case_id===bundle?.report?.case_id && Number.isInteger(receipt.rev) && receipt.rev>0 && receipt.rev<bundle.rev &&
        state.detail?.revisions?.some(r=>r.rev===receipt.rev && r.hash===receipt.report_hash) &&
        receipt.doc===f.doc && receipt.page===f.page &&
        receipt.original_sha256===doc.sha256 && receipt.page_sha256===node.sha256) return confirmed?'已核图':'已补录';
    return '待核图';
  }
  function panel(finding,t,ledger,index) {
    const support=index.supports.get('finding/'+finding.id);
    const owns=ref=>finding.evidence.includes(ref) && support?.has(ref);
    const pages=[];
    for (const p of ledger.pages) {
      const ref=p.doc+'/p'+p.page, node=index.nodes.get(ref), doc=index.documents.get(p.doc);
      if (!p.ticket || p.unit!==t.unit || p.native || p.bounded || !owns(ref) || !t.evidence.includes(ref) ||
          !['image','image_overlay'].includes(node?.layer) || !doc || !/^[a-f0-9]{64}$/.test(doc.sha256) ||
          !/^[a-f0-9]{64}$/.test(node.sha256)) continue;
      const fields=new Map();
      for (const l of ledger.lines) {
        if (l.kind!=='ticket_line' || l.unit!==t.unit || l.doc!==p.doc || l.page!==p.page || l.line!==null ||
            !Object.hasOwn(labels,l.field)) continue;
        for (const id of l.facts) {
          const f=index.facts.get(id);
          if (!f || !owns(id) || !t.evidence.includes(id) || f.doc!==p.doc || f.page!==p.page || (f.unit || f.doc)!==t.unit ||
              f.field!==l.field || f.source_line?.rects?.length || f.quote!==l.quote || !['visual','confirmed','disputed'].includes(f.status)) continue;
          const quote=norm(f.quote), split=quote.indexOf(':'), body=quote.slice(split+1).trim();
          if (split<1 || !labels[f.field].includes(quote.slice(0,split).trim()) || !body || ![body,quote].includes(norm(f.value))) continue;
          fields.set(id,{f,body,status:fieldStatus(f,doc,node)});
        }
      }
      pages.push({p,doc,fields:[...fields.values()]});
    }
    if (!pages.length) return null;
    pages.sort((a,b)=>a.p.doc.localeCompare(b.p.doc) || a.p.page-b.p.page);
    const root=el('section','','ticket-image-review'); root.setAttribute('aria-label','工单影像原页核对');
    const label=el('strong','','scan-file'), pageSelect=el('select','','scan-page-picker');
    pageSelect.setAttribute('aria-label','选择工单原页');
    const head=box('scan-title',label);
    if (pages.length>1) {
      for (const [i,{p}] of pages.entries()) pageSelect.add(new Option('第 '+p.page+' 页',String(i)));
      head.append(pageSelect);
    }
    const content=box('scan-review-content'); root.append(head,content);
    let show;
    function render(i) {
      const {p,doc,fields}=pages[i];
      const thumb=action('',()=>openPage(p.doc,p.page),'scan-open-page');
      const photo=el('img'); photo.alt=''; photo.hidden=true;
      const source=workpaperSource(p.doc,'pages/'+p.page);
      const retry=action('重新载入缩略图',load,'ref'); retry.hidden=true;
      const status=el('span','载入页图…','scan-preview-state');
      const frame=box('scan-thumb',photo,status);
      thumb.append(frame,box('scan-zoom-link',glyph('arrows-angle-expand'),el('span','查看第 '+p.page+' 页原件')));
      const entry=box('scan-image-source',thumb,retry);
      const list=box('scan-fields');
      const extra=box('scan-field-details'); extra.id='scan-details-'+finding.id;
      const closed=fields.some(row=>row.f.field==='warranty_ticket_state' && ['已关闭','已修复并关闭'].includes(row.body));
      for (const field of Object.keys(labels)) {
        const matches=fields.filter(row=>row.f.field===field);
        for (const {f,body,status} of matches) {
          const button=action('',()=>openPage(p.doc,p.page,f.id),'scan-field');
          button.dataset.scanFact=f.id; button.dataset.verification=status;
          button.append(el('small',short[field]),el('strong',body),el('span',status,'scan-receipt'));
          (['warranty_reported_on','warranty_fault'].includes(field)?extra:list).append(button);
        }
        if (closed && field==='warranty_closed_by' && !matches.length) {
          const button=action('',()=>openPage(p.doc,p.page),'scan-field');
          button.dataset.scanGap=field;
          button.append(el('small',short[field]),el('strong','待查原页'),glyph('arrows-angle-expand')); list.append(button);
        }
      }
      if (!list.children.length) list.append(el('p',extra.children.length?'报修字段见工单详情。':'本页没有可定位的工单字段。','small'));
      list.append(extra);
      root.dataset.page=p.doc+'/p'+p.page; root.dataset.preview='idle';
      label.textContent=doc.name+(pages.length===1?' · 第 '+p.page+' 页':'');
      pageSelect.value=String(i); content.replaceChildren(entry,list);
      async function load() {
        if (!root.isConnected || !root.getClientRects().length || !frame.isConnected || root.dataset.preview==='loading') return;
        const returnFocus=document.activeElement===retry;
        root.dataset.preview='loading'; retry.disabled=true; status.textContent='载入页图…';
        try {
          await loadReviewImage(photo,source);
          if (!frame.isConnected) return;
          photo.hidden=false; status.hidden=true; retry.hidden=true; root.dataset.preview='image';
          if (returnFocus) thumb.focus({preventScroll:true});
        } catch {
          if (!frame.isConnected) return;
          status.textContent='页图暂未载入'; retry.disabled=false; retry.hidden=false; root.dataset.preview='error';
          if (returnFocus) retry.focus({preventScroll:true});
        }
      }
      show=()=>{if (root.dataset.preview==='idle') load();};
      requestAnimationFrame(show);
    }
    root.addEventListener('show-image',()=>show());
    pageSelect.addEventListener('change',()=>render(pageSelect.selectedIndex));
    const withState=pages.findIndex(page=>page.fields.some(row=>row.f.field==='warranty_ticket_state'));
    const indicated=pages.findIndex(page=>page.p.image_ticket_refs?.length || page.fields.length);
    render(withState>=0?withState:Math.max(indicated,0));
    return root;
  }
  return {panel};
})();
