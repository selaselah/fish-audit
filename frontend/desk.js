const Desk = {
  page: 1, libraryPage: 1, search: '', status: 'verified', fingerprint: '', debounce: 0,
  tenantPath(resource) { return (Team.current ? '/api/w/'+Team.current.id : '/api')+'/'+resource; },
  reset() {
    this.page = 1; this.libraryPage = 1; this.search = ''; this.status = 'verified'; this.fingerprint = '';
    clearTimeout(this.debounce);
    state.filter = 'all';
    for (const id of ['case-search','library-query','desk-profile']) $('#'+id).value = '';
    $('#desk-sort').value='updated'; $('#library-status').value='verified';
    for (const id of ['library-results','library-pager','desk-pager','case-list']) $('#'+id).replaceChildren();
    for (const n of document.querySelectorAll('[data-metric] strong')) n.textContent = '—';
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
  async load(epoch) {
    const params = new URLSearchParams({q:$('#case-search').value.trim(), profile:$('#desk-profile').value,
      sort:$('#desk-sort').value, page:String(this.page), status:state.filter});
    const data = await api(this.tenantPath('inbox')+'?'+params);
    if (epoch !== state.epoch) return;
    const fingerprint = params + JSON.stringify(data);
    if (this.fingerprint === fingerprint) return;
    this.fingerprint = fingerprint; this.page = data.page; state.cases = data.cases;
    for (const button of document.querySelectorAll('[data-metric]')) {
      const key = button.dataset.metric;
      button.querySelector('strong').textContent = data.counts[key].toLocaleString('zh-CN');
      button.setAttribute('aria-pressed', String(state.filter===key));
    }
    document.querySelector('[data-filter=failed]').hidden = !data.counts.failed && state.filter !== 'failed';
    renderList();
    this.pager('desk-pager',data,page=>{this.page=page; refresh();},'项任务');
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
    $('#case-search').addEventListener('input',()=>{
      clearTimeout(this.debounce); this.debounce=setTimeout(()=>{this.page=1;refresh();},200);
    });
    for (const id of ['desk-sort','desk-profile']) $('#'+id).addEventListener('change',()=>{this.page=1;refresh();});
    for (const button of document.querySelectorAll('[data-metric],[data-filter]')) {
      button.addEventListener('click',()=>this.filter(button.dataset.filter || button.dataset.metric));
    }
    $('#library-form').addEventListener('submit',event=>{
      event.preventDefault(); this.search=$('#library-query').value.trim(); this.status=$('#library-status').value;
      this.libraryPage=1;refresh();
    });
  }
};
