function contractPreview(report, task) {
  if (task.profile!=='cn-contract-performance/v1' || report.case_id!==task.id || report.policy?.profile!==task.profile) return null;
  const findings=report.findings, graph=report.graph;
  const signing=findings.find(f=>f.rule==='H01'), acceptance=findings.find(f=>f.rule==='H02'), plan=findings.find(f=>f.rule==='H03');
  if (!signing || !acceptance || !plan) return null;
  function jump(f,label,cls='preview-finding',view) {
    const query=new URLSearchParams({rev:String(task.rev),...(view?{view}:{finding:f.id})});
    if (view==='payment-acceptance') query.set('receipt',f.id);
    const node=Team.paperLink(label,task.id,cls,query);
    node.dataset.findingId=f.id;
    if (view!=='payment-acceptance') node.append(tag(f.status));
    node.append(glyph('arrows-angle-expand'));return node;
  }
  const panel=el('section','','preview-contract');
  panel.setAttribute('aria-label','合同履约速览');
  const receiptCheck=acceptance.inspection_coverage?jump(acceptance,'验收设备','preview-check','inspection'):jump(acceptance,'交付验收','preview-check');
  panel.append(box('preview-checks',jump(signing,'合同生效','preview-check'),receiptCheck));
  const header=box('preview-plan-head',el('h3','付款安排'),jump(plan,'全部条款','preview-plan-jump'));
  panel.append(header);
  const phases=findings.filter(f=>f.rule==='H04' && f.stage), index=graphIndex(graph);
  if (!phases.length || phases.some(f=>!index.facts.has(f.stage.clause_ref) || !traceReferences(graph,f).includes(f.stage.clause_ref))) return panel;
  const stages=phases.map(f=>{
    const refs=traceReferences(graph,f);
    const related=findings.filter(r=>['H05','H06'].includes(r.rule) && PhaseEvidence.sameStage(f.stage,r.stage) && traceReferences(graph,r).includes(f.stage.clause_ref));
    const noted=f.contract_comments?.notes.some(n=>refs.includes(n)) || false;
    return {f,related,noted,status:PhaseEvidence.combined([f,...related])};
  });
  const content=el('div','','preview-phase-detail');
  const pick=stages.length>4?el('select'):box('preview-phase-tabs');
  if (pick.tagName==='SELECT') pick.setAttribute('aria-label','选择付款期次');
  else {pick.setAttribute('role','tablist');pick.setAttribute('aria-label','查看付款期次');content.setAttribute('role','tabpanel');}
  content.id='preview-selected-phase';
  function select(i) {
    const {f,related}=stages[i];
    if (pick.tagName==='SELECT') pick.selectedIndex=i;
    else {
      [...pick.children].forEach((tab,n)=>{tab.tabIndex=n===i?0:-1;tab.setAttribute('aria-selected',String(n===i));});
      content.setAttribute('aria-labelledby',pick.children[i].id);
    }
    const payments=related.filter(r=>r.rule==='H05');
    content.replaceChildren(jump(f,'付款条件'));
    for (const r of related) {
      const bank=payments.length>1 && r.rule==='H05' && traceReferences(graph,r).map(ref=>index.facts.get(ref)).find(v=>v?.field==='bank_receipt');
      content.append(jump(r,r.rule==='H06'?'本期回单合计':bank?.name || '实付时点'));
    }
    const referenced=payments.filter(r=>r.payment_acceptance);
    if (referenced.length) content.append(jump(referenced.find(r=>r.payment_acceptance.state==='other_batch') || referenced[0],
      '核对验收单号','preview-finding','payment-acceptance'));
    if (!payments.length) content.append(el('span','本期未关联回单','preview-no-receipt'));
  }
  stages.forEach(({f},i)=>{
    const {name,share}=f.stage, percent=share?share+'%':'比例待核';
    if (pick.tagName==='SELECT') {pick.append(el('option',name+' · '+percent));return;}
    const tab=action('',()=>select(i),'preview-phase-tab');
    tab.id='preview-phase-'+i;tab.setAttribute('role','tab');tab.setAttribute('aria-controls',content.id);
    tab.append(el('span',name),el('strong',percent));pick.append(tab);
    tab.addEventListener('keydown',event=>{
      const target={ArrowRight:(i+1)%stages.length,ArrowLeft:(i+stages.length-1)%stages.length,Home:0,End:stages.length-1}[event.key];
      if (target!==undefined) {event.preventDefault();select(target);pick.children[target].focus();}
    });
  });
  if (pick.tagName==='SELECT') pick.addEventListener('change',()=>select(pick.selectedIndex));
  const priority=PhaseEvidence.combined(stages), attention=stages.findIndex(s=>s.status===priority && s.noted);
  const receipt=stages.findIndex(s=>s.status===priority && s.related.some(r=>r.rule==='H05'));
  select(attention>=0?attention:receipt>=0?receipt:Math.max(0,stages.findIndex(s=>s.status===priority)));
  panel.append(pick,content); return panel;
}

const Desk = {
  page: 1, libraryPage: 1, search: '', status: 'verified', fingerprint: '', debounce: 0,
  previewRequest: null, previewSequence:[], view:'board', verdict:'', lane:'', queryKey:'',
  laneLabels:{reject:'建议不通过',review:'需要人工校验',pass:'建议通过',pending:'尚无建议'},
  tenantPath(resource) { return (Team.current ? '/api/w/'+Team.current.id : '/api')+'/'+resource; },
  reset() {
    this.page = 1; this.libraryPage = 1; this.search = ''; this.status = 'verified'; this.fingerprint = '';
    this.verdict=''; this.lane=''; this.queryKey='';
    clearTimeout(this.debounce);
    state.filter = 'all';
    for (const id of ['case-search','library-query','desk-profile']) $('#'+id).value = '';
    $('#desk-sort').value='updated'; $('#library-status').value='verified';
    $('#desk-filters').open = false;
    this.updateFilterBadge();
    if ($('#case-preview').open) $('#case-preview').close();
    for (const id of ['library-results','library-pager','desk-pager','case-list']) $('#'+id).replaceChildren();
    for (const n of document.querySelectorAll('[data-metric] strong')) n.textContent = '—';
    $('#queue-count').textContent = '';
    $('#queue-title').textContent = '任务台账';
    $('#verdict-filter').hidden=true; $('#verdict-filter').replaceChildren(); $('#desk-announcement').textContent='';
  },
  pager(id, data, go, unit) {
    const parent = $('#'+id); parent.replaceChildren();
    if (!data.total) return;
    parent.append(el('span','共 '+data.total+' '+unit,'small'));
    if (data.pages > 1) {
      const prev = action('上一页', ()=>go(data.page-1),'page-button');
      const next = action('下一页', ()=>go(data.page+1),'page-button');
      prev.disabled = data.page === 1; next.disabled = data.page === data.pages;
      parent.append(box('flow',prev,el('span',data.page+' / '+data.pages,'mono'),next));
    }
  },
  filter(status) { state.filter = status; this.page=1; this.fingerprint=''; refresh(); },
  setView(view, verdict='') {
    this.view=view; this.verdict=verdict; this.page=1;
    try { localStorage.setItem('fish-audit-desk-view',view); } catch {}
    refresh();
  },
  renderBoard(data) {
    const list=$('#case-list');
    if (!data.total) {
      list.replaceChildren(el('p',state.filter==='all' && !$('#case-search').value && !$('#desk-profile').value ?
        '还没有任务，选择「新建审计」上传资料。' : '当前筛选条件下没有任务。','empty'));
      return;
    }
    const lanes=Object.keys(this.laneLabels).filter(id=>id!=='pending' || data.lanes[id].total)
      .map(id=>[id,data.lanes[id]]);
    if (!lanes.some(([id])=>id===this.lane)) this.lane=lanes.find(([,lane])=>lane.total)[0];
    const selector=box('lane-selector'), board=box('verdict-board');
    selector.setAttribute('role','group'); selector.setAttribute('aria-label','选择审计建议');
    const selectLane=id=>{
      this.lane=id;
      for (const b of selector.children) b.setAttribute('aria-pressed',String(b.dataset.laneChoice===id));
      for (const col of board.children) col.classList.toggle('selected-lane',col.dataset.lane===id);
    };
    for (const [id,lane] of lanes) {
      const label=this.laneLabels[id];
      const count=lane.total.toLocaleString('zh-CN');
      const choice=action('',()=>selectLane(id),'lane-choice');
      choice.dataset.laneChoice=id; choice.setAttribute('aria-controls','lane-'+id);
      choice.append(el('span',label),el('strong',count)); selector.append(choice);
      const col=el('section','','verdict-lane'); col.id='lane-'+id; col.dataset.lane=id;
      const heading=el('h3',label); heading.id='lane-title-'+id; col.setAttribute('aria-labelledby',heading.id);
      col.append(box('lane-heading',glyph(({reject:'exclamation-diamond',review:'eye',pass:'shield-check',pending:'clock-history'})[id]),heading,el('strong',count)));
      for (const row of lane.cases) {
        const {title,training}=caseName(row,true);
        const meta=el('small',[training?'合成演练':'',row.rev?'R'+row.rev:'',profileName(row.profile)].filter(Boolean).join(' · '),'card-meta');
        const card=el('article','','audit-card');
        const stamp=el('small',[training?'演练':'',row.rev?'R'+row.rev:''].filter(Boolean).join(' · '),'card-edition');
        card.append(meta,title);
        if (['queued','running'].includes(row.status)) {
          const progress=el('progress'); progress.max=100; progress.value=row.progress;
          progress.setAttribute('aria-label',statusName(row.stage)+' '+row.progress+'%');
          card.append(box('card-progress',el('span',statusName(row.stage)+' · '+row.progress+'%'),progress));
        } else if (row.issues || row.risks || row.missing) {
          const signals=box('card-signals');
          for (const [num,word,kind] of [[row.issues,'问题','issue'],[row.risks,'风险','risk'],[row.missing,'证据不足','missing']]) {
            if (num) signals.append(el('span',num+' '+word,kind));
          }
          card.append(signals);
        }
        const files=el('span',row.files+' 份','card-files'); files.prepend(glyph('paperclip'));
        const status=row.decision ? el('span','人工'+statusName(row.decision),'card-decision') : tag(row.status);
        card.append(box('card-foot',status,stamp,files,peekButton(row,lane.cases))); col.append(card);
      }
      if (!lane.cases.length) col.append(el('p','暂无任务','lane-empty'));
      if (lane.total>lane.cases.length) {
        const more=action('查看全部 '+count+' 项',()=>{ this.setView('list',id); $('#desk-views [data-desk-view=list]').focus(); },'lane-more');
        more.setAttribute('aria-label',more.textContent+'，'+label); more.dataset.moreLane=id; col.append(more);
      }
      board.append(col);
    }
    selectLane(this.lane);
    list.replaceChildren(selector,board);
  },
  updateFilterBadge() {
    const count = Number(Boolean($('#desk-profile').value)) + Number($('#desk-sort').value!=='updated');
    $('#filter-count').hidden = count===0;
    $('#filter-count').textContent = String(count);
  },
  movePreview(step) {
    const index=this.previewSequence.findIndex(r=>r.id===$('#case-preview').dataset.caseId);
    if (index<0 || !this.previewSequence[index+step]) return;
    this.peek(this.previewSequence[index+step]);
  },
  async peek(row,sequence) {
    const dialog = $('#case-preview');
    const content = $('#preview-body');
    const footer = $('#preview-action');
    this.previewRequest?.abort();
    const request = new AbortController();
    this.previewRequest = request;
    const path = Team.cases()+'/'+row.id;
    const current = () => !request.signal.aborted && dialog.open && path===Team.cases()+'/'+row.id;
    if (sequence) this.previewSequence=sequence.map(r=>({id:r.id,title:r.title}));
    const position=this.previewSequence.findIndex(r=>r.id===row.id);
    const pager=$('#preview-pager'),prev=$('#preview-prev'),next=$('#preview-next');
    pager.hidden=this.previewSequence.length<2 || position<0;
    prev.disabled=position<=0;next.disabled=position<0 || position===this.previewSequence.length-1;
    $('#preview-position').value=(position+1)+' / '+this.previewSequence.length;
    if (document.activeElement===prev && prev.disabled && !next.disabled) next.focus();
    if (document.activeElement===next && next.disabled && !prev.disabled) prev.focus();
    dialog.dataset.caseId = row.id;
    $('#preview-title').textContent = row.title;
    content.replaceChildren(el('p','正在读取任务…','muted'));
    footer.replaceChildren();content.scrollTop=0;
    if (!dialog.open) dialog.showModal();
    try {
      let task = await api(path,{signal:request.signal});
      if (!current()) return;
      const open = Team.paperLink('打开任务',task.id,'button preview-open');
      footer.replaceChildren(open);
      const meta = box('preview-meta',tag(task.status),el('span',profileName(task.profile)),el('span',time(task.updated)));
      const files = el('ul','','preview-files');
      const pageCounts = new Map();
      for (const doc of task.documents) {
        const pages=el('small');
        pageCounts.set(doc.id,pages);
        const file=el('li');
        file.append(glyph('file-earmark-text'),el('span',doc.name),pages); files.append(file);
      }
      function updatePages() {
        for (const doc of task.documents) {
          const count=doc.pages ? doc.pages+' 页' : '待分页';
          const label=pageCounts.get(doc.id);
          if (label && label.textContent!==count) label.textContent=count;
        }
      }
      updatePages();
      const sources = box('preview-section',el('h3','原始资料 · '+task.documents.length+' 份'),files);
      content.replaceChildren(meta,sources);
      const processing = () => ['queued','running'].includes(task.status);
      if (processing()) {
        const meter=el('progress'); meter.max=100; meter.setAttribute('aria-label','审计任务进度');
        const heading=el('h3'), message=el('p','','muted');
        const progress=box('preview-section',heading,meter,message);
        content.insertBefore(progress,sources);
        while (processing()) {
          const text=statusName(task.stage)+' · '+task.progress+'%';
          if (heading.textContent!==text) heading.textContent=text;
          if (message.textContent!==task.message) message.textContent=task.message;
          if (!meter.hasAttribute('value') || meter.value!==task.progress) meter.value=task.progress;
          await new Promise(resolve=>setTimeout(resolve,1600));
          if (!current()) return;
          task=await api(path,{signal:request.signal});
          if (!current()) return;
          updatePages();
          if (meta.firstChild.dataset.state!==task.status) meta.firstChild.replaceWith(tag(task.status));
          const updated=time(task.updated);
          if (meta.lastChild.textContent!==updated) meta.lastChild.textContent=updated;
        }
        progress.remove();
      }
      if (!(task.can_review && task.rev>0)) {
        content.insertBefore(el('p',task.message,'muted'),sources); return;
      }
      const pinned=Team.paperLink('打开 R'+task.rev+' 底稿',task.id,'button preview-open',new URLSearchParams({rev:String(task.rev)}));
      const hadFocus=document.activeElement===open;
      footer.replaceChildren(pinned);
      if (hadFocus) pinned.focus();
      const loading=el('p','正在读取 R'+task.rev+' 审计建议…','muted');
      content.insertBefore(loading,sources);
      const {report} = await api(path+'/reports/'+task.rev,{signal:request.signal});
      if (!current()) return;
      loading.remove();
      const verdict=box('preview-verdict',tag(report.result.verdict));
      appendHumanReview(verdict,report.result,'small');
      const result=box('preview-section',el('h3','审计建议'),verdict);
      const signed=task.decisions.find(d=>d.rev===task.rev);
      if (signed) result.append(el('p','人工决定 · '+statusName(signed.decision),'small'));
      const priorities=priorityFindings(report.findings);
      const contract=contractPreview(report,task);
      let list=result;
      if (contract) {
        result.append(contract);
        if (priorities.length) {
          list=el('details','','preview-other');
          list.append(el('summary','优先核对 · '+Math.min(3,priorities.length)+' 项'));result.append(list);
        }
        const documents=el('details','','preview-other');
        documents.append(el('summary','原始资料 · '+task.documents.length+' 份'),files);
        sources.replaceChildren(documents);
      }
      for (const item of priorities.slice(0,3)) {
        const target=Team.paperLink(item.stage ? item.stage.name+' · '+item.title : item.title,task.id,'preview-finding',
          new URLSearchParams({rev:String(task.rev),finding:item.id}));
        target.append(tag(item.status)); list.append(target);
      }
      content.insertBefore(result,sources);
    } catch (error) {
      if (!current()) return;
      const message=el('p',error.message,'note'); message.setAttribute('role','alert');
      content.replaceChildren(message);
      if ([401,403,404].includes(error.status)) footer.replaceChildren();
    }
  },
  async load(epoch) {
    const view=Team.current?.role==='employee' ? 'list' : this.view;
    const params = new URLSearchParams({q:$('#case-search').value.trim(), profile:$('#desk-profile').value,
      sort:$('#desk-sort').value, page:String(this.page), status:state.filter,view});
    if (view==='list' && this.verdict) params.set('verdict',this.verdict);
    const path=this.tenantPath('inbox')+'?'+params;
    if (path!==this.queryKey) {
      this.queryKey=path; this.fingerprint='';
      this.lane='';
      $('#case-list').replaceChildren(el('p','正在读取任务…','empty'));
      $('#verdict-filter').hidden=true; $('#desk-pager').replaceChildren();
    }
    const data = await api(path);
    if (epoch !== state.epoch) return;
    const fingerprint = params + JSON.stringify(data);
    if (this.fingerprint === fingerprint) return;
    this.fingerprint = fingerprint; this.page = data.page || 1; state.cases = data.cases || [];
    for (const button of document.querySelectorAll('[data-metric]')) {
      const key = button.dataset.metric;
      button.querySelector('strong').textContent = data.counts[key].toLocaleString('zh-CN');
      button.setAttribute('aria-pressed', String(state.filter===key));
    }
    document.querySelector('[data-filter=failed]').hidden = !data.counts.failed && state.filter !== 'failed';
    const active = document.querySelector('[data-filter="'+state.filter+'"] span');
    $('#queue-title').textContent = state.filter === 'all' ? (view==='board'?'审计建议':'任务台账') : active.textContent;
    $('#queue-count').textContent = data.total.toLocaleString('zh-CN')+' 项';
    $('#desk-views').hidden=Team.current?.role==='employee';
    $('#desk-density-label').hidden=view!=='board';
    for (const b of $('#desk-views').children) b.setAttribute('aria-pressed',String(b.dataset.deskView===view));
    const filter=$('#verdict-filter');
    filter.hidden=!this.verdict; filter.replaceChildren();
    if (this.verdict) {
      const clear=action(this.laneLabels[this.verdict],()=>{ this.setView('list'); $('#desk-views [data-desk-view=list]').focus(); },'verdict-chip');
      clear.setAttribute('aria-label','移除建议筛选：'+this.laneLabels[this.verdict]); clear.append(glyph('x-lg')); filter.append(clear);
    }
    const focus=document.activeElement;
    const focused=['previewCase','caseId','laneChoice','moreLane'].find(k=>focus?.dataset[k]);
    if (view==='board') this.renderBoard(data); else renderList();
    if (focused && !focus.isConnected) {
      const restored=[...$('#case-list').querySelectorAll('a,button')].find(n=>n.dataset[focused]===focus.dataset[focused]);
      (restored || $('#case-search')).focus({preventScroll:true});
    }
    if (view==='list') this.pager('desk-pager',data,page=>{this.page=page; refresh();},'项任务');
    else $('#desk-pager').replaceChildren();
    const message=$('#queue-title').textContent+'，'+data.total+' 项任务';
    if ($('#desk-announcement').textContent!==message) $('#desk-announcement').textContent=message;
  },
  async library(epoch) {
    const results = $('#library-results');
    if (!this.search) {
      results.replaceChildren(el('p','输入关键词，在当前工作区各任务的最新底稿中查找引文。','empty'));
      $('#library-pager').replaceChildren(); return;
    }
    const params = new URLSearchParams({q:this.search, status:this.status, page:String(this.libraryPage)});
    const data = await api(this.tenantPath('evidence')+'?'+params);
    if (epoch !== state.epoch) return;
    this.libraryPage = data.page;
    const nodes = data.hits.map(hit=>{
      const params = new URLSearchParams({rev:String(hit.rev),fact:hit.fact});
      return box('evidence-hit', box('panel-head',el('strong',hit.label+' · '+hit.value),tag(hit.status)),
        el('blockquote',hit.quote),box('hit-foot',el('small',hit.title+' · R'+hit.rev,'small'),
        Team.paperLink(hit.name+' · 第 '+hit.page+' 页',hit.case_id,'source-jump',params)));
    });
    if (!nodes.length) nodes.push(el('p','当前范围没有匹配引文。可调整关键词或核验状态。','empty'));
    results.replaceChildren(...nodes);
    this.pager('library-pager',data,page=>{this.libraryPage=page; refresh();},'条引文');
  },
  bind() {
    try { if (localStorage.getItem('fish-audit-desk-view')==='list') this.view='list'; } catch {}
    const density=$('#desk-density'), list=$('#case-list');
    try { density.checked=localStorage.getItem('fish-audit-card-details')==='expanded'; } catch {}
    const showDetails=()=>list.dataset.density=density.checked?'expanded':'compact';
    showDetails();
    density.addEventListener('change',()=>{
      showDetails();
      try { localStorage.setItem('fish-audit-card-details',list.dataset.density); } catch {}
    });
    for (const b of $('#desk-views').children) b.addEventListener('click',()=>this.setView(b.dataset.deskView));
    const icons = {all:'inboxes',active:'clock-history',ready:'clipboard-check',attention:'exclamation-diamond',
      in_review:'layers',closed:'folder2-open',failed:'exclamation-triangle'};
    for (const button of document.querySelectorAll('[data-metric]')) button.querySelector('span').prepend(glyph(icons[button.dataset.metric]));
    const options=$('#desk-filters');
    const update=()=>{this.page=1; this.updateFilterBadge(); refresh();};
    $('#reset-filters').addEventListener('click',()=>{
      $('#desk-profile').value=''; $('#desk-sort').value='updated'; update();
      options.open=false; options.querySelector('summary').focus();
    });
    document.addEventListener('pointerdown',event=>{if (options.open && !options.contains(event.target)) options.open=false;});
    document.addEventListener('keydown',event=>{
      if ($('#desk').hidden || document.querySelector('dialog[open]') || event.isComposing) return;
      if (event.key==='Escape' && options.open) { options.open=false; options.querySelector('summary').focus(); return; }
      if (event.key==='/' && !event.metaKey && !event.ctrlKey && !event.altKey && !event.target.closest('input,select,textarea,[contenteditable=true]')) {
        event.preventDefault(); $('#case-search').focus();
      }
    });
    $('#preview-prev').addEventListener('click',()=>this.movePreview(-1));
    $('#preview-next').addEventListener('click',()=>this.movePreview(1));
    $('#case-preview').addEventListener('keydown',event=>{
      if (!event.altKey || event.metaKey || event.ctrlKey || event.shiftKey || event.isComposing || $('#preview-pager').hidden) return;
      if (event.key==='ArrowUp' || event.key==='ArrowDown') {event.preventDefault();this.movePreview(event.key==='ArrowUp'?-1:1);}
    });
    $('#case-preview').addEventListener('close',()=>{
      if ($('#case-preview').open) return;
      this.previewRequest?.abort();this.previewSequence=[];
      $('#preview-title').textContent=''; $('#preview-body').replaceChildren(); $('#preview-action').replaceChildren();
      if (!$('#desk').hidden && Team.route().page==='desk' && (document.activeElement===document.body || document.activeElement.matches('[data-preview-case]'))) {
        const key=$('#case-preview').dataset.caseId;
        (document.querySelector('[data-preview-case="'+CSS.escape(key)+'"]') || $('#case-search')).focus();
      }
    });
    $('#case-search').addEventListener('input',()=>{
      clearTimeout(this.debounce); this.debounce=setTimeout(()=>{this.page=1;refresh();},200);
    });
    for (const id of ['desk-sort','desk-profile']) $('#'+id).addEventListener('change',update);
    for (const button of document.querySelectorAll('[data-metric],[data-filter]')) {
      button.addEventListener('click',()=>this.filter(button.dataset.filter || button.dataset.metric));
    }
    $('#library-form').addEventListener('submit',event=>{
      event.preventDefault(); this.search=$('#library-query').value.trim(); this.status=$('#library-status').value;
      this.libraryPage=1;refresh();
    });
  }
};
