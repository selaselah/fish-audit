const ExecutionTrace = (() => {
  const stages = {initial:'多模态提取', check:'独立复检', expert:'专家追加程序'};
  const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const isSha256 = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  const clock = new Intl.DateTimeFormat('zh-CN', {timeZone:'Asia/Shanghai', year:'numeric', month:'2-digit',
    day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hourCycle:'h23'});
  const logs = new WeakMap();
  const zoned = value => typeof value === 'string' && /T\d{2}:\d{2}.*(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) && Number.isFinite(Date.parse(value));

  function stamp(value) {
    if (typeof value !== 'string' || !value) return el('span','未记录');
    if (!zoned(value)) return el('span',value);
    const instant = Date.parse(value);
    const node = el('time',clock.format(instant));
    node.dateTime = value;
    node.title = value;
    return node;
  }

  function sourcePage(graph, page) {
    if (typeof page.doc !== 'string' || !Number.isSafeInteger(page.page) || page.page < 1 || !isSha256(page.page_sha256)) return;
    if (!Array.isArray(graph?.documents) || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) return;
    const manifests = graph.documents.filter(doc => doc?.id === page.doc);
    const documents = graph.nodes.filter(node => node?.id === page.doc);
    if (manifests.length !== 1 || documents.length !== 1) return;
    const [manifest] = manifests, [documentNode] = documents;
    if (documentNode.type !== 'document' || !isSha256(manifest.sha256) || documentNode.sha256 !== manifest.sha256 ||
        (Number.isInteger(manifest.pages) && page.page > manifest.pages)) return;

    const ref = page.doc + '/p' + page.page;
    const pages = graph.nodes.filter(node => node?.id === ref);
    if (pages.length !== 1 || pages[0].type !== 'page' || pages[0].sha256 !== page.page_sha256) return;
    const parents = graph.edges.filter(edge => edge?.type === 'contains' && edge.to === ref);
    if (parents.length !== 1) return;
    const [parent] = parents;
    if (parent.from === page.doc && Array.isArray(parent.evidence) && parent.evidence.length === 1 && parent.evidence[0] === ref)
      return manifest;
  }

  function technicalText(value, label) {
    const pre = el('pre',value);
    pre.tabIndex = 0;
    pre.setAttribute('role','region');
    pre.setAttribute('aria-label',label);
    return pre;
  }

  function inspector(bundle) {
    const {calls = {},graph,case_id:caseId} = bundle.report;
    const root = box('panel execution-trace');
    root.dataset.rev = bundle.rev;
    const scope = Team.current?.id || null;
    function inScope() {
      const route = Team.route();
      const rev = route.params.get('rev');
      return state.bundle === bundle && state.detail?.id === caseId &&
        route.id === scope && (Team.current?.id || null) === scope && route.page === 'case/'+caseId &&
        (!rev || Number(rev) === bundle.rev) && (!state.pinned || state.pinned === bundle.rev);
    }
    const picker = el('select');
    picker.id = 'execution-trace-page';
    const label = el('label','资料与页码');
    label.htmlFor = picker.id;
    const items = [], steps = [], positions = new Map();
    const params = Team.route().params;
    const requested = params.get('view') === 'execution' && params.has('call') ? params.getAll('call') : null;
    function add(title, page, source, entries) {
      const pos = items.length;
      const item = {title,page,source,steps:[],pos};
      items.push(item);
      picker.add(new Option(title,String(pos)));
      for (const [kind, trace] of entries) {
        const bound = (page ? [page,trace] : [trace]).every(call=>
          (call.case_id === undefined || call.case_id === caseId) && (call.rev === undefined || call.rev === bundle.rev) &&
          (!page || ((call.doc === undefined || call.doc === page.doc) && (call.page === undefined || call.page === page.page) &&
            (call.page_sha256 === undefined || call.page_sha256 === page.page_sha256))));
        let ref = null;
        if (bound && kind === 'expert') ref = 'expert';
        else if (bound && /^d[0-9]{2,8}$/.test(page.doc) && Number.isSafeInteger(page.page) && page.page > 0 && page.page <= 99999999)
          ref = page.doc+'/p'+page.page+'/'+kind;
        if (ref) {
          if (!positions.has(ref)) positions.set(ref,[]);
          positions.get(ref).push(steps.length);
        }
        item.steps.push(steps.length);
        steps.push({item,kind,trace,ref,bound});
      }
    }
    for (const page of Array.isArray(calls?.pages) ? calls.pages : []) {
      if (!isRecord(page)) continue;
      const source = sourcePage(graph,page);
      const name = source?.name || page.doc || '未记录资料';
      const title = name + (Number.isInteger(page.page) ? ' · 第 '+page.page+' 页' : ' · 页码未记录');
      const entries = [['initial',page]];
      if (isRecord(page.check)) entries.push(['check',page.check]);
      add(title,page,source,entries);
    }
    if (isRecord(calls?.expert)) add(stages.expert,null,null,[['expert',calls.expert]]);
    const heading = box('execution-heading',el('h2','本版模型调用'),el('span','R'+bundle.rev,'execution-rev'));
    root.append(heading);
    if (!steps.length) {
      const empty = el('p',requested ? '本版未留存请求的调用记录。' : '本版未留存调用记录。','muted execution-unavailable');
      empty.id = picker.id;
      empty.tabIndex = -1;
      root.append(empty);
    } else {
      let at = -1;
      const prev = action('上一步',()=>select(at-1));
      const next = action('下一步',()=>select(at+1));
      const count = el('span','','execution-count');
      const navigation = box('execution-navigation',prev,count,next);
      const switcher = box('execution-steps');
      switcher.setAttribute('role','group');
      switcher.setAttribute('aria-label','调用步骤');
      const facts = el('dl','','execution-facts');
      const details = box('execution-details');
      const sourceSlot = box('execution-source');
      const stepRow = box('execution-step-row',switcher,sourceSlot);
      const unavailable = el('p','','execution-unavailable');
      unavailable.setAttribute('role','status');
      const currentStep = el('span','','visually-hidden');
      currentStep.setAttribute('role','status');
      root.append(box('execution-picker',box('execution-field',label,picker),navigation),
        unavailable,stepRow,facts,details,currentStep);
      picker.addEventListener('change',()=>select(items[picker.selectedIndex]?.steps[0]));
      picker.addEventListener('keydown',event=>{
        if (!['Home','End'].includes(event.key) || event.altKey || event.metaKey || event.ctrlKey || event.isComposing) return;
        event.preventDefault();
        select(items[event.key === 'Home' ? 0 : items.length-1].steps[0]);
      });
      function select(index) {
        if (!steps[index]) return;
        const {item,kind,trace,ref,bound} = steps[index], changed = switcher.dataset.item !== String(item.pos);
        at = index;
        root.dataset.step = kind;
        picker.value = String(item.pos);
        unavailable.hidden = true;
        stepRow.hidden = facts.hidden = details.hidden = false;
        const ordinal = (at+1)+' / '+steps.length+' 步';
        if (inScope() && positions.get(ref)?.length === 1 && Number.isSafeInteger(bundle.rev) && bundle.rev > 0) {
          const target = Team.paperLink(ordinal,caseId,'execution-permalink',new URLSearchParams({rev:bundle.rev,view:'execution',call:ref}));
          target.title = '此步骤的固定链接 · R'+bundle.rev+' · '+item.title+' · '+stages[kind];
          target.setAttribute('aria-label',ordinal+'，'+target.title);
          target.setAttribute('aria-description','可复制链接以分享此版调用记录');
          count.replaceChildren(target);
        } else count.textContent = ordinal;
        prev.setAttribute('aria-disabled',String(at===0));
        next.setAttribute('aria-disabled',String(at===steps.length-1));
        if (changed) {
          switcher.dataset.item = item.pos;
          switcher.replaceChildren(...item.steps.map(i=>action(stages[steps[i].kind],()=>select(i))));
        }
        const page = item.page;
        if (!item.source || !bound || !inScope()) sourceSlot.replaceChildren();
        else if (changed || !sourceSlot.firstChild) {
          const open = action('查看原页',()=>{
            if (open.isConnected && steps[at].item === item && inScope()) openPage(page.doc,page.page);
          });
          open.prepend(glyph('file-earmark-text'));
          sourceSlot.replaceChildren(open);
        }
        Array.from(switcher.children).forEach((btn,i)=>btn.setAttribute('aria-pressed',String(item.steps[i]===at)));
        const model = typeof trace.model === 'string' && trace.model ? trace.model : '未记录';
        const meta = [['实际模型',model],['尝试次数',Number.isSafeInteger(trace.attempts) && trace.attempts>=0 ? String(trace.attempts) : '未记录'],
          [zoned(trace.started)?'开始（北京时间）':'开始时间',stamp(trace.started)],[zoned(trace.completed)?'完成（北京时间）':'完成时间',stamp(trace.completed)]];
        if (typeof trace.requested_model === 'string' && trace.requested_model && trace.requested_model !== trace.model)
          meta.push(['请求模型',trace.requested_model]);
        facts.replaceChildren(...meta.map(([name,value])=>{
          const term = el('dd'); term.append(value);
          return box('',el('dt',name),term);
        }));
        const json = lazyFold('原始调用 JSON',()=>[technicalText(JSON.stringify(trace,null,2),'原始调用 JSON'),
          lazyFold('查看整版调用 JSON',()=>[technicalText(JSON.stringify(calls,null,2),'整版调用 JSON')])]);
        const [key,unit] = {initial:['facts',' 条提取记录'],check:['checks',' 条复检记录'],expert:['followups',' 条追加建议']}[kind];
        if (Array.isArray(trace.output?.[key])) json.firstElementChild.append(el('small',trace.output[key].length+unit,'execution-output-count'));
        const prompt = lazyFold('模型指令',()=>{
          const hash = trace.prompt_sha256;
          const value = hash && Object.hasOwn(calls.instructions || {},hash) ? calls.instructions[hash] : trace.instruction;
          return typeof value === 'string' ? [technicalText(value,'模型指令')] : [el('p','本版未留存此步指令。','muted')];
        });
        details.replaceChildren(json,prompt);
        currentStep.textContent = item.title+'，'+stages[kind]+'，第 '+(at+1)+' 步';
      }
      const pinned = params.getAll('rev').length === 1 && params.get('rev') === String(bundle.rev) && params.getAll('view').length === 1;
      const matches = requested?.length === 1 && pinned && inScope() ? positions.get(requested[0]) : null;
      if (!requested) select(0);
      else if (matches?.length === 1) select(matches[0]);
      else {
        root.dataset.step = 'unavailable';
        picker.selectedIndex = -1;
        stepRow.hidden = facts.hidden = details.hidden = true;
        prev.setAttribute('aria-disabled','true');
        count.textContent = '共 '+steps.length+' 步';
        unavailable.textContent = matches?.length > 1 || requested.length > 1 ?
          '本版有多条调用与链接相符，无法唯一定位。请选择资料与页码。' : '本版未留存链接所指的调用。请选择资料与页码。';
      }
    }
    const instructions = calls?.instructions;
    if (isRecord(instructions) && Object.keys(instructions).length) {
      const assigned = new Set(steps.map(step=>step.trace.prompt_sha256));
      const other = Object.keys(instructions).filter(hash=>!assigned.has(hash));
      if (other.length) root.append(lazyFold('其他留存指令',()=>other.map(hash=>box('',el('code',hash),technicalText(instructions[hash],'留存指令')))));
    }
    return root;
  }

  function log(data) {
    const root = box('panel execution-events');
    root.dataset.case = data.id;
    const count = el('span','','execution-events-count');
    const compact = el('ol');
    const all = el('ol');
    const disclosure = fold('');
    disclosure.append(all);
    root.append(box('execution-heading',el('h2','当前任务日志'),count),compact,disclosure);
    const view = {count,compact,all,disclosure,entries:[]};
    logs.set(root,view);
    disclosure.addEventListener('toggle',()=>{
      compact.hidden = disclosure.open;
      if (disclosure.open) all.replaceChildren(...view.entries.map(entry=>eventRow(entry,true)));
      else all.replaceChildren();
    });
    updateLog(root,data);
    return root;
  }

  function eventRow(entry,full) {
    const li = el('li');
    li.dataset.seq = entry.seq ?? '';
    const origin = box('execution-event-time',stamp(entry.time));
    if (full) {
      const detail = [entry.seq == null ? '' : '#'+entry.seq, entry.stage].filter(Boolean).join(' · ');
      if (detail) origin.append(el('small',detail));
    }
    li.append(origin,el('span',entry.message));
    return li;
  }

  function updateLog(root,data) {
    const view = logs.get(root);
    if (!view || root.dataset.case !== data.id) return;
    const events = Array.isArray(data.events) ? data.events : [];
    const key = JSON.stringify(events);
    if (view.key === key) return;
    view.key = key;
    const previous = view.entries;
    view.entries = [...events].reverse();
    view.count.textContent = events.length+' 条';
    view.disclosure.firstElementChild.textContent = '查看全部 '+events.length+' 条';
    view.disclosure.hidden = events.length <= 3;
    if (view.disclosure.hidden) view.disclosure.open = false;
    view.compact.hidden = view.disclosure.open;
    view.compact.replaceChildren(...view.entries.slice(0,3).map(entry=>eventRow(entry,false)));
    if (view.disclosure.open) {
      const added = events.length - previous.length;
      const appended = added > 0 && view.all.childElementCount === previous.length && previous.every((entry,i)=>{
        const old = view.entries[added+i];
        return entry.seq === old.seq && entry.time === old.time && entry.stage === old.stage && entry.message === old.message;
      });
      if (appended) view.all.prepend(...view.entries.slice(0,added).map(entry=>eventRow(entry,true)));
      else view.all.replaceChildren(...view.entries.map(entry=>eventRow(entry,true)));
    }
  }
  return {inspector,log,updateLog};
})();
