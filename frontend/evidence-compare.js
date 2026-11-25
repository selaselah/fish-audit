// Display only observations connected to the selected finding in its issued graph.
const EvidenceCompare = (() => {
  function presets(finding, facts, graph) {
    const result = [];
    const unit = fact => fact.unit || fact.doc;
    function unique(field, units) {
      const matches = facts.filter(f => f.field === field && units?.includes(unit(f)));
      return matches.length === 1 ? matches[0] : null;
    }
    function add(key, label, left, right) {
      if (left && right && left.id !== right.id) result.push({key, label, left, right});
    }
    const kinds = graph.documents_by_kind || {};
    const contract = kinds.contract;
    if (finding.rule === 'H01') {
      add('signatures', '双方签署', unique('buyer_signature', contract), unique('seller_signature', contract));
    }
    if (finding.rule === 'H05' && finding.stage) {
      const clause = facts.find(f => f.id === finding.stage.clause_ref);
      add('payment', '付款条款与回单', clause, unique('paid_on', kinds.bank_receipt));
    }
    if (finding.rule !== 'H02') return result;
    const change = finding.quality_change;
    const original = unique('acceptance_criteria', contract);
    const revised = unique('revised_criterion', change?.units);
    const actual = unique('measured_result', kinds.acceptance);
    const basis = unique('inspection_basis', kinds.acceptance);
    if (change?.quantity) {
      const q = change.quantity;
      const prior = unique('quantity_agreed', contract);
      const next = unique('revised_quantity', change.units);
      const applied = change.state === 'applied' ? next : prior;
      if (q.applicable && ['original','applied'].includes(change.state)) {
        add('quantity', '约定与实收', applied, unique('quantity_accepted', kinds.acceptance));
      }
      add('versions', '新旧数量', prior, next);
    } else {
      const applied = !change ? original : change.applied_criterion &&
        ({original, applied:revised})[change.state];
      if (!finding.batch_acceptance && !finding.reinspection) {
        add('reading', change ? '适用标准与实测' : '合同标准与实测', applied, actual);
        if (change) add('basis', '适用标准与验收依据', applied, basis);
      }
      if (!change || finding.batch_acceptance?.records.some(r => r.standard)) {
        const records = finding.batch_acceptance?.records || [];
        for (const batch of finding.batch_acceptance?.batches || []) {
          if (batch.records.length !== 1) continue;
          const record = records.find(r => r.unit === batch.records[0] && r.index === batch.index);
          const reading = record && unique('measured_result', [record.unit]);
          if (record?.standard) {
            const standard=record.standard;
            if (standard.criterion_ref) {
              add('batch-'+batch.index, batch.label+'实测', facts.find(f=>f.id===standard.criterion_ref),
                facts.find(f=>f.id===standard.reading_ref));
            } else if (standard.effective_on && standard.date_ref && change.buyer_sealed_on!==change.seller_sealed_on) {
              const seal=['buyer_sealed_on','seller_sealed_on'].find(field=>change[field]===standard.effective_on);
              if (seal) add('batch-'+batch.index,batch.label+'日期',unique(seal,change.units),facts.find(f=>f.id===standard.date_ref));
            } else {
              add('batch-'+batch.index,batch.label+'原单',facts.find(f=>f.id===standard.date_ref),facts.find(f=>f.id===standard.reading_ref));
            }
          } else if (!record?.scope_unclear && reading && record.evidence.includes(reading.id)) {
            add('batch-' + batch.index, batch.label + '实测', original, reading);
          }
        }
      }
      add('versions', '新旧标准', original, revised);
    }
    if (change?.effective_on && change.accepted_on && change.buyer_sealed_on !== change.seller_sealed_on) {
      const seal = ['buyer_sealed_on','seller_sealed_on'].find(field => change[field] === change.effective_on);
      if (seal) add('dates', '签章与验收日期', unique(seal, change.units), unique('accepted_on', kinds.acceptance));
    }
    return result;
  }

  function drawExcerpt(image, rects) {
    const width = image.naturalWidth, height = image.naturalHeight;
    let x = 0, y = 0, w = width, h = height;
    if (rects.length) {
      const left = Math.min(...rects.map(r => r[0])) * width;
      const top = Math.min(...rects.map(r => r[1])) * height;
      const right = Math.max(...rects.map(r => r[2])) * width;
      const bottom = Math.max(...rects.map(r => r[3])) * height;
      w = Math.min(width, Math.max(width * .55, right - left + width * .08));
      h = Math.min(height, Math.max(w / 4.5, bottom - top + height * .045));
      x = Math.max(0, Math.min(width - w, (left + right - w) / 2));
      y = Math.max(0, Math.min(height - h, (top + bottom - h) / 2));
    }
    const canvas = el('canvas');
    const scale = Math.min(1, 1200 / w, 850 / h);
    canvas.width = Math.max(1, Math.round(w * scale));
    canvas.height = Math.max(1, Math.round(h * scale));
    const ctx = canvas.getContext('2d');
    ctx.scale(canvas.width / w, canvas.height / h);
    ctx.drawImage(image, x, y, w, h, 0, 0, w, h);
    ctx.fillStyle = 'rgba(255, 196, 49, .25)';
    ctx.strokeStyle = '#a5670e';
    ctx.lineWidth = Math.max(1, w / 520);
    for (const [left,top,right,bottom] of rects) {
      const box = [left*width-x, top*height-y, (right-left)*width, (bottom-top)*height];
      ctx.fillRect(...box); ctx.strokeRect(...box);
    }
    canvas.setAttribute('aria-hidden','true');
    return canvas;
  }

  function citationFinder(facts, index, choose) {
    const dialog = el('dialog','','citation-finder');
    const title = el('h2'); title.id = 'citation-finder-title';
    dialog.setAttribute('aria-labelledby', title.id);
    const close = action('', () => dialog.close(), 'icon-button');
    close.append(glyph('x-lg')); close.setAttribute('aria-label','关闭引文选择');
    const query = el('input'); query.type = 'search'; query.autocomplete = 'off';
    query.placeholder = '搜索文件、字段或原文';
    const search = el('label','','finder-search');
    search.append(glyph('search'), el('span',query.placeholder,'visually-hidden'), query);
    const count = el('output','','finder-count');
    const list = box('finder-results');
    const normal = s => s.normalize('NFKC').toLowerCase();
    const entries = facts.map(fact => {
      const name = index.documents.get(fact.doc)?.name || fact.doc;
      const where = name + ' · 第 ' + fact.page + ' 页' + (fact.source_line?.number ? '第 ' + fact.source_line.number + ' 行' : '');
      return {fact, where, text:normal([where,fact.label,fact.quote,fact.value,fact.id,statusName(fact.status)].join(' '))};
    });
    let side, current, opposite;
    function render() {
      const words = normal(query.value.trim()).split(/\s+/).filter(Boolean);
      const matches = entries.filter(e => e.fact.id !== opposite && words.every(word => e.text.includes(word)));
      count.textContent = matches.length + ' 条引文';
      list.replaceChildren(...matches.map(({fact,where}) => {
        const button = action('', () => {
          choose(side,fact);
          dialog.close();
        }, 'finder-choice');
        button.dataset.ref = fact.id;
        if (fact.id === current) button.setAttribute('aria-current','true');
        button.append(box('finder-field',el('strong',fact.label),tag(fact.status)),el('span',fact.quote,'finder-quote'),el('small',where));
        return button;
      }));
      if (!matches.length) list.append(el('p','没有匹配的引文','finder-empty'));
      list.scrollTop = 0;
    }
    query.addEventListener('input',render);
    query.addEventListener('keydown',event => {
      if (event.isComposing || event.keyCode === 229) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        dialog.close();
        return;
      }
      const first = list.querySelector('button');
      if (first && ['ArrowDown','Enter'].includes(event.key)) {
        event.preventDefault();
        if (event.key === 'Enter') first.click();
        else first.focus();
      }
    });
    list.addEventListener('keydown',event => {
      const row = event.target.closest('button');
      if (!row) return;
      const next = {ArrowDown:row.nextElementSibling || row, ArrowUp:row.previousElementSibling || query,
        Home:list.firstElementChild, End:list.lastElementChild}[event.key];
      if (next) { event.preventDefault(); next.focus(); }
    });
    dialog.append(box('finder-heading',title,close),search,count,list);
    return {dialog,open(i,selected,excluded) {
      side=i; current=selected?.id; opposite=excluded?.id;
      title.textContent = '选择' + (side === 0 ? '左侧' : '右侧') + '引文';
      query.value=''; render(); dialog.showModal(); query.focus();
    }};
  }

  function panel(finding, facts, pairs, index) {
    // The image cache belongs to this finding and revision. A failed fetch can be retried.
    const pages = new Map();
    function pageImage(fact) {
      const url = workpaperSource(fact.doc, 'pages/' + fact.page);
      if (!pages.has(url)) {
        if (pages.size >= 4) pages.delete(pages.keys().next().value);
        const image = new Image();
        const request = loadReviewImage(image, url).then(() => image).catch(error => {
          if (pages.get(url) === request) pages.delete(url);
          throw error;
        });
        pages.set(url,request);
      }
      return pages.get(url);
    }
    const root = box('evidence-compare');
    const versionLabels={applied:'按补充协议',original:'按原合同',by_batch:'按各批验收日核对',pending:'适用版本待核'};
    const versionNote=box('compare-version');
    const shortcuts = box('compare-presets');
    shortcuts.setAttribute('role','group'); shortcuts.setAttribute('aria-label','选择对照内容');
    const announcement = el('output','','visually-hidden');
    const selection = [null,null];
    const finder = citationFinder(facts,index,(i,fact) => {
      selection[i]=fact; paint(i); sync();
    });
    const sides = ['左侧','右侧'].map((side,i) => {
      const pick = action('',() => finder.open(i,selection[i],selection[1-i]),'compare-pick');
      pick.setAttribute('aria-haspopup','dialog');
      const name = el('strong','选择原件');
      const sheet = box('compare-sheet');
      const node = box('compare-leaf',box('compare-file',glyph('file-earmark-text'),name,pick),sheet);
      return {side,pick,name,sheet,node};
    });

    function paint(i) {
      const {side,pick,name,sheet,node} = sides[i];
      const fact = selection[i];
      pick.replaceChildren(glyph('search'),el('span',fact?'换引文':'选引文'),
        el('span','，'+side+(fact?'，当前为'+fact.label:''),'visually-hidden'));
      node.dataset.fact = fact?.id || '';
      if (!fact) {
        name.textContent = '选择原件';
        sheet.replaceChildren(box('compare-empty',glyph('journal-text'),el('span','尚未选择引文')));
        return;
      }
      const nameText = index.documents.get(fact.doc)?.name || fact.doc;
      name.textContent = nameText;
      const rects = (fact.source_line?.rects || []).filter(r => Array.isArray(r) && r.length === 4 &&
        r.every(n => Number.isFinite(n) && n >= 0 && n <= 1) && r[2] > r[0] && r[3] > r[1]);
      const frame = box('compare-scan',el('span','载入原页…'));
      frame.dataset.located = String(Boolean(rects.length));
      const origin = '第 ' + fact.page + ' 页' + (rects.length ? ' · 第 ' + fact.source_line.number + ' 行' : ' · 整页影像');
      const open = action('', () => openPage(fact.doc, fact.page, fact.id), 'compare-original');
      open.append(frame,box('compare-source-foot',el('span',origin),box('compare-open-label',el('span','查看原页'),glyph('arrows-angle-expand'))),
        el('span','，'+nameText+'，核对'+fact.label,'visually-hidden'));
      sheet.replaceChildren(box('compare-quote',tag(fact.status),el('blockquote',fact.quote)),open);
      pageImage(fact).then(image => {
        frame.replaceChildren(drawExcerpt(image, rects));
      }).catch(() => {
        frame.replaceChildren(el('span','页图载入失败'));
        frame.setAttribute('role','alert');
      });
    }
    function sync() {
      const [left,right] = selection;
      const selected = pairs.find(p => p.left.id === left?.id && p.right.id === right?.id);
      for (const button of shortcuts.children) button.setAttribute('aria-pressed',String(button.dataset.pair === selected?.key));
      if (finding.quality_change) {
        const batch=finding.batch_acceptance?.batches.find(b=>'batch-'+b.index===selected?.key);
        const record=batch?.records.length===1 && finding.batch_acceptance.records.find(r=>r.unit===batch.records[0]);
        const state=record?.standard?.state || finding.quality_change.state;
        const label=record?.standard ? batch.label : ['applied','original'].includes(state) ? '本次' : '';
        versionNote.replaceChildren(glyph('layers'),el('span',label+versionLabels[state]));
        versionNote.dataset.state=state;
      }
      announcement.textContent = selection.map(fact => fact?.quote || '未选引文').join(' / ');
    }
    function use(pair) {
      selection[0] = pair?.left; selection[1] = pair?.right;
      paint(0); paint(1); sync();
    }
    for (const pair of pairs) {
      const button = action(pair.label, () => use(pair));
      button.dataset.pair = pair.key; shortcuts.append(button);
    }
    const bar = box('compare-bar');
    if (pairs.length) bar.append(shortcuts);
    if (finding.quality_change) bar.append(versionNote);
    if (bar.childElementCount) root.append(bar);
    root.append(box('compare-spread',...sides.map(s => s.node)),announcement,finder.dialog);
    const batches=finding.batch_acceptance?.batches || [];
    const changed=batches.filter(b=>finding.batch_acceptance.records.some(r=>b.records.includes(r.unit) && r.standard?.state==='applied'));
    const initial=[...priorityFindings(batches),...changed].map(b=>pairs.find(p=>p.key==='batch-'+b.index)).find(Boolean);
    use(initial || pairs[0]);
    return root;
  }
  return {presets, panel};
})();
