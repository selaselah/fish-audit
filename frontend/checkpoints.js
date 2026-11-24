const PageProgress = {
  id: null,
  files: new Map(),
  states: {prepared:'已分页', read:'已保存提取', checked:'已记录视觉复检', invalid:'提取记录待检查'},
  operations: {prepare:'校验原件并分页', read:'多模态读取', check:'逐字段视觉复检', integrity:'校验页图'},

  reset() {
    this.id = null;
    this.files.clear();
    $('#file-progress').hidden = true;
    $('#checkpoint-totals').textContent = '';
    $('#checkpoint-files').replaceChildren();
  },

  render(detail,viewedRevision) {
    const progress = detail.page_progress;
    if (!progress) { this.reset(); return; }
    const panel = $('#file-progress');
    if (this.id !== detail.id) {
      this.reset();
      this.id = detail.id;
      panel.open = ['queued','running','failed'].includes(detail.status);
      panel.hidden = false;
      for (const doc of detail.documents) {
        const group = el('details','','checkpoint-document');
        const label = el('span','','small');
        const summary = el('summary');
        summary.append(el('strong',doc.name),label);
        const list = el('ul','','checkpoint-pages');
        group.append(summary,list);
        $('#checkpoint-files').append(group);
        this.files.set(doc.id,{label,list,rows:new Map()});
      }
    }
    const counts = progress.counts;
    const recomputing = ['queued','running','failed'].includes(detail.status);
    const scope = viewedRevision && (viewedRevision<detail.rev || recomputing) ? '当前任务进度 · 正在查看 R'+viewedRevision+' · ' : '';
    const expert = progress.expert ? ' · R'+progress.expert.target_rev+' 专家响应已保存' : '';
    const total = scope+'已分页 '+counts.prepared+' 页 · 已提取 '+counts.read+' 页 · 有复检记录 '+counts.checked+' 页'+expert;
    if ($('#checkpoint-totals').textContent!==total) $('#checkpoint-totals').textContent = total;
    for (const [doc,file] of this.files) {
      const pages = progress.documents[doc] || [];
      const present = new Set(pages.map(p=>p.page));
      for (const [number,saved] of file.rows) {
        if (!present.has(number)) { saved.row.remove(); file.rows.delete(number); }
      }
      const active = progress.activity?.doc===doc ? progress.activity : null;
      const at = detail.status==='failed' ? '中断位置 · ' : '正在';
      const activity = active ? at+this.operations[active.operation]+(active.page?' · 第 '+active.page+' 页':'') : '';
      const read = pages.filter(p=>p.state==='read' || p.state==='checked').length;
      const status = pages.length ? '已提取 '+read+' / 已分页 '+pages.length+' 页' : '尚无已保存的分页';
      const label = activity ? status+' · '+activity : status;
      if (file.label.textContent!==label) file.label.textContent = label;
      for (const p of pages) {
        let saved = file.rows.get(p.page);
        if (!saved) {
          const row = el('li');
          const source = link('第 '+p.page+' 页原图',Team.cases()+'/'+detail.id+'/documents/'+doc+'/pages/'+p.page);
          source.target='_blank'; source.rel='noopener';
          const text = el('span');
          row.append(source,text); file.list.append(row);
          saved = {row,text}; file.rows.set(p.page,saved);
        }
        const current = active?.page===p.page;
        const state = current ? this.states[p.state]+' · '+activity : this.states[p.state];
        if (saved.text.textContent!==state) saved.text.textContent = state;
        saved.row.classList.toggle('checkpoint-active',current);
      }
    }
  },
};
