// Display only observations connected to the selected finding in its issued graph.
const EvidenceCompare = (() => {
  function presets(finding, facts, graph) {
    const result = WarrantyTickets.pairs(finding,graph).filter(p=>facts.some(f=>f.id===p.left.id) && facts.some(f=>f.id===p.right.id));
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
      for (const entry of finding.delegations || []) {
        if (!entry.signature_field || entry.units.length!==1) continue;
        const observed=id=>facts.find(f=>f.id===id && entry.evidence.includes(id));
        const field=(key,units)=>{
          const f=unique(key,units); return f && entry.evidence.includes(f.id) ? f : null;
        };
        const name=finding.delegations.length>1 ? (entry.side==='buyer'?'甲方':'乙方') : '';
        function mandate(key,label,left,right,extra={}) {
          if (!left || !right || left.id===right.id) return;
          result.push({key:'mandate-'+entry.side+'-'+key,label:name+label,left,right,authority:true,...extra});
        }
        const limits=entry.limits || [];
        for (const limit of [...limits].sort((a,b)=>Number(b.status==='risk')-Number(a.status==='risk'))) {
          if (!limit.comparison_ref) continue;
          const left=observed(limit.field_ref),right=observed(limit.comparison_ref);
          if (!left || !right || !entry.units.includes(unit(left)) || !contract?.includes(unit(right))) continue;
          const label=limit.kind==='prepayment'?'预付款权限':'签约金额上限';
          mandate(left.id+'-'+right.id,label,left,right,{status:limit.status,stageRef:limit.kind==='prepayment'?right.id:null});
        }
        const pending=limits.filter(c=>c.status!=='ok').map(c=>observed(c.field_ref)).filter(Boolean);
        const distinct=[...new Map(pending.map(f=>[f.id,f])).values()];
        if (distinct.length>=2) mandate('clauses','两条授权限制',distinct[0],distinct[1],{status:'missing'});
        for (const [key,prop,text] of [['grant_until','valid_until','签约与截止日'],['grant_from','valid_from','签约与起始日'],['granted_on','issued_on','签约与出具日']]) {
          const outside=entry.signed_on && entry[prop] && (key==='grant_until'?entry.signed_on>entry[prop]:entry.signed_on<entry[prop]);
          const same=Boolean(entry.signed_on && entry.signed_on===entry[prop]);
          const needsTime=key==='granted_on' && same && entry.issuance_order?.state==='same_day';
          if (key==='grant_until' || outside || same || !entry[prop]) mandate(key,text,field('signed_on',contract),field(key,entry.units),
            {status:outside?'risk':(!entry[prop] || !entry.signed_on || needsTime?'missing':null)});
        }
        mandate('signer','签字与受托人',field(entry.signature_field,contract),field('grant_agent',entry.units));
      }
      result.sort((a,b)=>({risk:0,missing:1}[a.status]??2)-({risk:0,missing:1}[b.status]??2));
      add('signatures', '双方签署', unique('buyer_signature', contract), unique('seller_signature', contract));
    }
    const byRef=ref=>facts.find(f=>f.id===ref && finding.evidence.includes(ref));
    if (finding.payment_opinion) {
      const notes=AcceptanceOpinion.rows(graph,finding);
      const release=finding.payment_opinion.release;
      function printed(row) {
        const f=row?.line && AcceptanceOpinion.observation(row,graph);
        return f && byRef(f.id);
      }
      const hold=notes.filter(n=>n.stance==='hold'), assent=notes.filter(n=>n.stance==='assent');
      if (finding.payment_opinion.state==='conflict' && hold.length===1 && assent.length===1 && hold[0].unit===assent[0].unit)
        add('opinion-conflict','暂缓与同意原文',printed(hold[0]),printed(assent[0]));
      if (release) {
        const rows=ReleaseEvidence.sources(graph,finding), authority=ReleaseEvidence.one(rows,'authority');
        const ref=id=>ReleaseEvidence.fact(graph,finding,id) && byRef(id);
        if (authority) add('release-authority','合同指定人与放行签认',printed(authority),ref(release.signature_ref));
        add('release-receipt','验收单号与放行所引原单',ref(release.original_ref),ref(release.receipt_ref));
        if (finding.rule==='H05' && release.state==='matched') add('release-transfer','放行签字日与实付日',ref(release.date_ref),ref(release.paid_ref));
      } else if (finding.rule==='H05' && notes.length===1 && ['hold','assent'].includes(finding.payment_opinion.state)) {
        const paid=unique('paid_on',kinds.bank_receipt);
        if (paid?.source_line?.rects?.length) add('opinion-transfer','付款意见与实付日期',printed(notes[0]),paid);
      }
    }
    const edition=finding.payment_change;
    if (edition) {
      const observed=ref=>edition.evidence.includes(ref)?byRef(ref):null;
      add('amendment-terms','原合同与变更条款',observed(edition.original_ref),observed(edition.revised_ref));
      add('amendment-seals','协议双方盖章日期',observed(edition.buyer_date_ref),observed(edition.seller_date_ref));
      if (edition.effective_on && finding.rule==='H05') {
        const seal=edition.effective_on===edition.seller_on?edition.seller_date_ref:edition.buyer_date_ref;
        add('amendment-payment-date','协议生效与实付日期',observed(seal),observed(edition.paid_ref));
      }
    }
    const gate=finding.invoice_receipt;
    if (gate) {
      add('receipt-number','发票与签收登记票号',byRef(gate.invoice.number_ref),byRef(gate.receipt.number_ref));
      if (finding.rule==='H05') add('receipt-payment-date','收票与实付日期',byRef(gate.receipt.date_ref),unique('paid_on',kinds.bank_receipt));
    }
    if (finding.rule === 'H05' && finding.stage && (!edition || ['original','amended'].includes(edition.applies))) {
      const clause = byRef(edition?.applies==='amended'?edition.revised_ref:finding.stage.clause_ref);
      add('payment', '付款条款与回单', clause, unique('paid_on', kinds.bank_receipt));
    }
    if (finding.rule !== 'H02') return result;
    const chain = finding.reinspection;
    if (chain) {
      function stepField(role, field) {
        const steps = chain.steps.filter(s => s.role === role);
        if (steps.length !== 1) return null;
        const fact = unique(field,[steps[0].unit]);
        return fact && steps[0].evidence.includes(fact.id) ? fact : null;
      }
      add('retest-readings','初验与复验读数',stepField('original','measured_result'),stepField('final','measured_result'));
      add('retest-repair','整改与关闭结论',stepField('repair','repair_result'),stepField('final','defect_closure'));
      add('retest-dates','整改与复验日期',stepField('repair','repaired_on'),stepField('final','accepted_on'));
      add('retest-defect','初验与复验缺陷号',stepField('original','defect_number'),stepField('final','defect_number'));
    }
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

  function repairNotice(chain, index) {
    const checks = chain.steps.filter(step => step.completion?.status && step.completion.status !== 'ok');
    if (!checks.length) return null;
    const notice = box('repair-notice');
    for (const {completion} of checks) {
      const rows = ['qualification',...(!completion.date?['date']:[]),'unreviewed'].flatMap(kind=>completion.lines.filter(r=>r.kind===kind));
      const title = rows[0]?.kind==='qualification' ? '整改记录另有说明' : !completion.date ? '整改完成日待核' : '整改原页待核';
      const block = box('repair-notice-item',box('repair-notice-title',glyph('exclamation-triangle'),el('strong',title)));
      const sources = rows.map(row=>{
        const fact = row.facts.map(ref=>index.facts.get(ref)).find(f=>f?.quote===row.quote);
        const button = action(row.line ? '查看原件第 '+row.line+' 行' : '查看原件',
          ()=>openPage(row.doc,row.page,fact?.id,fact?null:row.line),'text-button');
        button.dataset.repairSource = fact?.id || row.doc+'/p'+row.page+(row.line?'/l'+row.line:'');
        return box('repair-notice-line',el('q',row.quote),button);
      });
      if (!rows.length) block.append(el('span',completion.detail));
      for (const page of completion.mixed_pages) {
        sources.push(action('核对第 '+page.page+' 页影像',()=>openPage(page.doc,page.page),'text-button'));
      }
      if (sources.length) block.append(sources[0]);
      if (sources.length>1) block.append(fold('另有 '+(sources.length-1)+' 处依据',...sources.slice(1)));
      notice.append(block);
    }
    return notice;
  }

  function rectangles(fact) {
    return (fact.source_line?.rects || []).filter(r=>Array.isArray(r) && r.length===4 &&
      r.every(n=>Number.isFinite(n) && n>=0 && n<=1) && r[2]>r[0] && r[3]>r[1]);
  }

  function drawExcerpt(image, rects, compact=false) {
    const width = image.naturalWidth, height = image.naturalHeight;
    let x = 0, y = 0, w = width, h = height;
    if (rects.length) {
      const left = Math.min(...rects.map(r => r[0])) * width;
      const top = Math.min(...rects.map(r => r[1])) * height;
      const right = Math.max(...rects.map(r => r[2])) * width;
      const bottom = Math.max(...rects.map(r => r[3])) * height;
      w = Math.min(width, compact?right-left+width*.025:Math.max(width*.55,right-left+width*.08));
      h = Math.min(height, compact?bottom-top+height*.011:Math.max(w/4.5,bottom-top+height*.045));
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

  function addedWording(pair) {
    const before=pair?.left.source_line, after=pair?.right.source_line;
    if (!before?.rects?.length || !after?.rects?.length) return null;
    const label=after.text.match(/^(?:变更后付款条款|新付款条款)\s*[：:]\s*/u);
    if (!label) return null;
    const old=before.text, revised=after.text.slice(label[0].length), length=revised.length-old.length;
    if (!old || length<=0) return null;
    let start=0;
    while (start<old.length && old[start]===revised[start]) start++;
    if (old.slice(start)!==revised.slice(start+length)) return null;
    const offset=label[0].length+start;
    return [after.text.slice(0,offset),after.text.slice(offset,offset+length),after.text.slice(offset+length)];
  }

  function pageImage(fact,index) {
    const pages=index.images ??= new Map();
    const url=workpaperSource(fact.doc,'pages/'+fact.page);
    if (!pages.has(url)) {
      if (pages.size>=4) pages.delete(pages.keys().next().value);
      const image=new Image();
      const request=loadReviewImage(image,url).then(()=>image).catch(error=>{
        if (pages.get(url)===request) pages.delete(url);
        throw error;
      });
      pages.set(url,request);
    }
    return pages.get(url);
  }

  async function lineExcerpt(fact,index) {
    const rects=rectangles(fact);
    if (!rects.length) return null;
    return drawExcerpt(await pageImage(fact,index),rects,true);
  }

  function panel(finding, facts, pairs, index) {
    const root = box('evidence-compare');
    const versionLabels={applied:'按补充协议',original:'按原合同',by_batch:'按各批验收日核对',pending:'适用版本待核'};
    const versionNote=box('compare-version');
    const shortcuts = box('compare-presets');
    shortcuts.setAttribute('role','group'); shortcuts.setAttribute('aria-label','选择对照内容');
    const terms=pairs.find(p=>p.key==='amendment-terms');
    const added=finding.payment_change?.scope_clear && addedWording(terms);
    const highlight=el('label','','compare-highlight');
    const toggle=el('input'); toggle.type='checkbox'; toggle.checked=true;
    highlight.append(toggle,el('span','标出新增文字'));
    toggle.addEventListener('change',sync);
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
      const rects = rectangles(fact);
      const frame = box('compare-scan',el('span','载入原页…'));
      frame.dataset.located = String(Boolean(rects.length));
      const origin = '第 ' + fact.page + ' 页' + (rects.length ? ' · 第 ' + fact.source_line.number + ' 行' : ' · 整页影像');
      const open = action('', () => openPage(fact.doc, fact.page, fact.id), 'compare-original');
      open.append(frame,box('compare-source-foot',el('span',origin),box('compare-open-label',el('span','查看原页'),glyph('arrows-angle-expand'))),
        el('span','，'+nameText+'，核对'+fact.label,'visually-hidden'));
      const printed = rects.length && fact.source_line.text || fact.quote;
      const differs = printed !== fact.quote;
      const stateTag = differs && fact.status==='anchored' ? el('span','抄录与原行有差异','tag transcription-difference') : tag(fact.status);
      const quote = box('compare-quote',stateTag,el('blockquote',printed));
      if (differs) {
        const transcript = fold('对照字段抄录',el('p',fact.quote));
        transcript.classList.add('compare-transcript'); quote.append(transcript);
      }
      sheet.replaceChildren(quote,open);
      pageImage(fact,index).then(image => {
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
      if (added) {
        highlight.hidden=selected?.key!=='amendment-terms';
        const quote=sides[1].sheet.querySelector('blockquote');
        if (!highlight.hidden && toggle.checked) quote.replaceChildren(added[0],el('mark',added[1]),added[2]);
        else if (quote?.querySelector('mark')) quote.textContent=right.source_line.text;
      }
      if (finding.delegations) {
        versionNote.hidden=!selected?.status;
        if (selected?.status) versionNote.replaceChildren(tag(selected.status));
      }
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
    if (added) bar.append(highlight);
    if (finding.quality_change || finding.delegations) bar.append(versionNote);
    if (finding.reinspection) {
      const closed = finding.reinspection.state === 'closed';
      const state = box('compare-version',glyph(closed?'clipboard-check':'clock-history'),el('span',closed?'缺陷已关闭':'缺陷待核'));
      state.dataset.state = closed?'closed':'pending'; bar.append(state);
    }
    if (bar.childElementCount) root.append(bar);
    const note = finding.reinspection && repairNotice(finding.reinspection,index);
    if (note) root.append(note);
    root.append(box('compare-spread',...sides.map(s => s.node)),announcement,finder.dialog);
    const batches=finding.batch_acceptance?.batches || [];
    const changed=batches.filter(b=>finding.batch_acceptance.records.some(r=>b.records.includes(r.unit) && r.standard?.state==='applied'));
    const initial=[...priorityFindings(batches),...changed].map(b=>pairs.find(p=>p.key==='batch-'+b.index)).find(Boolean);
    const focus = pairs.find(p=>p.key==='retest-'+finding.reinspection?.focus);
    use(focus || initial || pairs[0]);
    return root;
  }
  return {presets,panel,lineExcerpt};
})();
