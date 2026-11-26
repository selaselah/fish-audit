// The palette enumerates the current user's visible navigation and the selected workpaper only.
(() => {
  const dialog = $('#quick-dialog'), input = $('#quick-query'), results = $('#quick-results');
  const trigger = $('#quick-open');
  const shortcut=/Mac|iPad|iPhone/.test(navigator.platform) ? '⌘ K' : 'Ctrl K';
  trigger.querySelector('kbd').textContent=shortcut;
  trigger.setAttribute('aria-label','快速定位 '+shortcut);
  let options = [], active = 0, origin, path, paper, context;
  function visible(element) { return Boolean(element?.getClientRects().length); }
  function jump(target) {
    if (!target) return;
    if (!target.hasAttribute('tabindex')) target.tabIndex = -1;
    revealPaperTarget(target);
  }
  function commands() {
    const all = [];
    const add = (group, label, icon, run, meta = '', words = '', tone = '') =>
      all.push({group, label, icon, run, meta, words, tone});
    const route = Team.route();
    const inCase = visible($('#case')) && state.detail && route.page === 'case/'+state.detail.id && route.id === (Team.current?.id || null);
    if (inCase) {
      if (visible($('#progress-panel'))) add('当前任务','查看处理进度','clock-history',()=>jump($('#progress-panel')));
      if (visible($('#file-progress'))) add('当前任务','逐份资料进度','file-earmark-text',()=>{
        const panel=$('#file-progress'); panel.open=true; jump(panel.querySelector('summary'));
      }, '', '解析 页数 进度');
      if (paper) {
        if (paper.report.findings.some(f=>f.rule==='H02' && f.inspection_coverage)) add('底稿视图','核对验收设备','card-checklist',()=>{
          state.tab='report'; renderCase(true); jump($('#inspection-coverage'));
        },'R'+paper.rev,'合同 必检 抽检 设备编号 测温 原行');
        if (AcceptanceComments.current(paper.report)) add('底稿视图','对照验收批注','journal-text',()=>{
          state.tab='report'; renderCase(true); jump($('#acceptance-comments'));
        },'R'+paper.rev,'Word 审阅 原文 期款');
        if (SupplierPages.current(paper.report)) add('底稿视图','核对供货主体','layers',()=>{
          state.tab='report'; renderCase(true); jump($('#supplier-pages'));
        },'R'+paper.rev,'合同 供应方 验收 原行 批注 签署原因');
        const signature=paper.report.findings.find(f=>f.rule==='H01')?.effect_review;
        if (signature?.pdf_execution || signature?.word_signatures) add('底稿视图','核对签署凭证','shield-check',()=>{
          state.tab='report'; renderCase(true); jump($(signature.pdf_execution?'#pdf-signatures':'#word-signatures'));
        },'R'+paper.rev,'电子签名 证书 签章 盖章 PDF Word 签署页');
        if (ContractCalendar.available()) add('底稿视图','核对合同日期','clock-history',()=>{
          state.tab='report'; renderCase(true); jump($('#contract-calendar'));
        },'R'+paper.rev,'签订日 生效日 截止日 原件 冲突');
        if (EntityBrowser.items(paper.report.graph).length) add('底稿视图','按对象查原件','diagram-3',()=>{
          graphIndex(paper.report.graph).graphBrowseMode='entities'; state.tab='graph'; renderCase(true); jump($('#case-entity-browser'));
        },'R'+paper.rev,'合同编号 发票号码 单号 往来单位 标的 关联单据 图谱');
        const findings=priorityFindings(paper.report.findings);
        const showFinding=item=>{
          state.tab='report'; renderCase();
          jump(document.querySelector('[data-finding="'+CSS.escape(item.id)+'"]'));
        };
        for (const f of findings) {
          const label = (f.stage ? f.stage.name+' · ' : '') + f.title;
          add('待核发现', label, f.status==='missing' ? 'question-circle' : 'exclamation-diamond',
            ()=>showFinding(f), statusName(f.status), f.rule+' '+(f.prior_installment?'首款 前款 回单 分期 ':'')+f.detail, f.status);
        }
        for (const doc of paper.report.graph.documents) {
          add('本版原件', doc.name, 'file-earmark-text', ()=>openPage(doc.id,1), 'R'+paper.rev, '原件 文件 扫描 附件 '+doc.id);
        }
        for (const node of $('#tabs').children) {
          add('底稿视图', node.textContent.trim(), 'journal-text', ()=>{node.click(); node.focus();}, 'R'+paper.rev);
        }
      }
    }
    if (visible($('#new-case'))) add('工作区','新建审计','plus-lg',()=>$('#new-case').click(), '', '上传 PDF Word 图片 发票 合同');
    if (visible($('#desk'))) {
      for (const [filter,label,icon,words] of [['active','查看处理中任务','clock-history','进度'],['attention','有疑点待验收','eye','问题 风险 缺件'],['in_review','查看待复核任务','clipboard-check','人工']]) {
        const button=document.querySelector('[data-metric="'+filter+'"]');
        if (visible(button)) add('工作区',label,icon,()=>{button.click();button.focus();},button.querySelector('strong').textContent+' 项',words);
      }
    }
    for (const [key,icon] of [['desk','card-checklist'],['library','search'],['rules','journal-text'],['team','clipboard-check'],['account','shield-check']]) {
      const anchor=$('#nav-'+key);
      if (visible(anchor)) add('导航',anchor.textContent.trim(),icon,()=>{anchor.focus();anchor.click();});
    }
    return all;
  }
  function setActive(index, scroll = false) {
    active = index;
    const rows=results.querySelectorAll('[role="option"]');
    rows.forEach((row, i)=>row.setAttribute('aria-selected',String(i===active)));
    if (!rows[active]) { input.removeAttribute('aria-activedescendant'); return; }
    input.setAttribute('aria-activedescendant',rows[active].id);
    if (scroll) rows[active].scrollIntoView({block:'nearest'});
  }
  function run(index) {
    const destination=options[index];
    if (!destination) return;
    if (location.hash!==path || state.bundle!==paper || context!==Team.current?.id) { dialog.close(); return; }
    dialog.close(); destination.run();
  }
  const normalize = value => value.normalize('NFKC').toLocaleLowerCase().trim();
  function draw() {
    const query=normalize(input.value).split(/\s+/).filter(Boolean);
    const items=commands();
    const filtered=items.filter(o=>query.every(word=>normalize([o.label,o.group,o.meta,o.words].join(' ')).includes(word)));
    // Short entry list; a typed query can reach every finding or file in this revision.
    const each = new Map();
    options=filtered.filter(o=>{
      const count=(each.get(o.group)||0)+1; each.set(o.group,count);
      return query.length || count <= (o.group==='导航' || o.group==='工作区' ? 5 : 3);
    });
    results.replaceChildren();
    let group;
    for (const [i,o] of options.entries()) {
      if (o.group!==group?.getAttribute('aria-label')) {
        group=el('div','','quick-group'); group.setAttribute('role','group'); group.setAttribute('aria-label',o.group);
        const title=el('div',o.group,'quick-group-title'); title.setAttribute('aria-hidden','true'); group.append(title); results.append(group);
      }
      const row=el('div','','quick-option'); row.id='quick-option-'+i;
      row.setAttribute('role','option'); row.dataset.tone=o.tone;
      row.append(glyph(o.icon),el('span',o.label,'quick-label'),el('small',o.meta,'quick-meta'));
      row.addEventListener('pointermove',event=>{ if (event.pointerType==='mouse' && active!==i) setActive(i); });
      row.addEventListener('click',()=>run(i)); group.append(row);
    }
    $('#quick-empty').hidden=Boolean(options.length);
    $('#quick-count').textContent=options.length+' 个匹配项';
    setActive(0); results.scrollTop=0;
  }
  function open() {
    if (!Team.session || document.querySelector('dialog[open]')) return;
    origin=document.activeElement; path=location.hash; paper=state.bundle; context=Team.current?.id;
    $('#quick-scope').textContent=visible($('#case')) && paper ? '当前底稿 · R'+paper.rev : Team.current?.name || (Team.session.mode==='local'?'本机工作区':'企业工作区');
    input.value=''; dialog.showModal(); draw(); input.focus();
  }
  trigger.addEventListener('click',open);
  $('#quick-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',event=>{ if (event.target===dialog) {const r=dialog.getBoundingClientRect(); if (event.clientX<r.left || event.clientX>r.right || event.clientY<r.top || event.clientY>r.bottom) dialog.close();} });
  dialog.addEventListener('close',()=>{
    if (dialog.open) return;
    results.replaceChildren(); input.value=''; input.removeAttribute('aria-activedescendant'); options=[]; paper=null;
    if (document.activeElement===document.body && visible(origin)) origin.focus();
  });
  input.addEventListener('input',draw);
  input.addEventListener('keydown',event=>{
    if (event.isComposing || event.keyCode===229 || !options.length) return;
    if (event.key==='Enter') {event.preventDefault();run(active);return;}
    if (!['ArrowDown','ArrowUp','Home','End'].includes(event.key)) return;
    event.preventDefault();
    setActive(event.key==='Home'?0:event.key==='End'?options.length-1:(active+(event.key==='ArrowDown'?1:-1)+options.length)%options.length,true);
  });
  document.addEventListener('keydown',event=>{
    if (event.isComposing || event.repeat || event.altKey || event.shiftKey || !(event.ctrlKey || event.metaKey) || event.key.toLowerCase()!=='k') return;
    if (!dialog.open && document.querySelector('dialog[open]')) return;
    event.preventDefault(); if (dialog.open) dialog.close(); else open();
  });
  window.addEventListener('hashchange',()=>{ if (dialog.open) dialog.close(); });
})();
