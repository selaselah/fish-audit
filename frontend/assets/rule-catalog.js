// The public directory uses the current policy. A workpaper passes its own archived sources.
const RuleCatalog = (() => {
  function sourceDetail(source) {
    const official=link('查看发布原文',source.url,'catalog-official');
    official.target='_blank'; official.rel='noopener noreferrer'; official.append(glyph('arrows-angle-expand'));
    const title=el('h3',source.title,'catalog-source-title');
    const part=box('catalog-source-detail',title);
    const place=[source.locator,source.edition].filter(Boolean);
    if (place.length) part.append(el('p',place.join(' · '),'catalog-locator'));
    if (source.scope) part.append(box('catalog-scope',el('strong','适用范围'),el('p',source.scope)));
    if (source.summary) part.append(fold('出处摘要',el('p',source.summary)));
    part.append(official);
    return part;
  }

  function sourceChooser(entries,version,selected,onChange) {
    const pane=el('section','','catalog-sources');
    const head=box('catalog-source-head',glyph('journal-text'),el('strong','制度出处'));
    if (version) head.append(el('small','规则版本 '+version,'catalog-version'));
    pane.append(head);
    if (!entries.length) return pane;
    const options=new Map(entries), keys=[...options.keys()], select=el('select'), detail=box('catalog-source-body');
    const count=el('span','','catalog-position');
    const previous=action('‹',()=>move(-1),'catalog-step'), next=action('›',()=>move(1),'catalog-step');
    previous.setAttribute('aria-label','上一条制度出处'); next.setAttribute('aria-label','下一条制度出处');
    function show(key,notify=false) {
      const i=keys.indexOf(key);
      select.selectedIndex=i;
      pane.dataset.source=i<0?'':key;
      count.textContent=(i<0?'—':String(i+1))+' / '+keys.length;
      previous.disabled=i<=0; next.disabled=i===keys.length-1;
      if (i>=0) detail.replaceChildren(sourceDetail(options.get(key)));
      else detail.replaceChildren(el('p','此出处未列入本项程序的当版依据。','catalog-empty'));
      if (notify) onChange?.(key);
    }
    function move(delta) {
      const target=keys[select.selectedIndex+delta];
      if (!target) return;
      const focus=document.activeElement;
      show(target,true);
      if (focus===previous && previous.disabled || focus===next && next.disabled) select.focus();
    }
    if (entries.length>1) {
      select.setAttribute('aria-label','选择本项制度出处');
      for (const [key,source] of entries) {
        const option=el('option',[source.title,source.locator].filter(Boolean).join(' · ')); option.value=key;
        select.append(option);
      }
      const picker=el('label','','catalog-picker');
      picker.append(count,glyph('chevron-down'),select);
      head.append(box('catalog-stepper',previous,picker,next));
      select.addEventListener('change',()=>show(select.value,true));
    }
    pane.append(detail);
    show(selected || keys[0]);
    if (selected && !options.has(selected) && entries.length===1)
      detail.append(action('查看已列出处',()=>show(keys[0],true),'text-button'));
    return pane;
  }

  function render(data,params) {
    const sources=data.sources || (data.background?{background:data.background}:{});
    const mappings=data.rule_sources || {};
    const rules=new Map(data.rules.map(rule=>[rule.id,rule]));
    const all={
      rule:data.rules.map(r=>({key:r.id,title:r.name,search:[r.id,r.name,r.basis,...(mappings[r.id] || [])
        .map(id=>sources[id]).filter(Boolean).map(s=>s.title+' '+(s.locator || ''))].join(' ')})),
      source:Object.entries(sources).map(([key,s])=>({key,title:s.title,sub:s.locator,search:[s.title,s.locator,s.edition,s.summary,s.scope].filter(Boolean).join(' ')}))
    };
    const label={rule:'检查程序',source:'制度出处'};
    let mode=!params.has('rule') && (params.has('source') || params.get('tab')==='sources')?'source':'rule';
    let selected=params.get(mode), sourceKey=mode==='rule'?params.get('source'):null;
    const root=box('catalog-browser'), modes=box('catalog-modes');
    modes.setAttribute('role','group'); modes.setAttribute('aria-label','浏览内容');
    const release=el('details','','catalog-policy'), version=el('summary','当前规则 '+data.version,'catalog-release');
    const profiles=Object.values(data.profiles || {});
    release.append(version);
    if (profiles.length) {
      const modules=el('ul');
      for (const name of profiles) modules.append(el('li',name));
      release.append(box('catalog-module-list',el('strong','业务模块'),modules));
    }
    const toolbar=box('catalog-toolbar',modes,profiles.length?release:el('span',version.textContent,'catalog-release'));
    const filter=el('input'); filter.type='search'; filter.placeholder='搜编号、关键词或条文';
    filter.setAttribute('aria-label','检索当前目录'); filter.maxLength=120; filter.value=(params.get('q') || '').slice(0,120);
    const search=box('catalog-search',glyph('search'),filter);
    const master=el('nav','','catalog-master'); master.setAttribute('aria-label','规则依据目录');
    const results=el('output','','catalog-count'); results.setAttribute('aria-live','polite');
    const list=box('catalog-list'); list.setAttribute('role','listbox'); list.setAttribute('aria-label','目录项目');
    const compact=el('select','','catalog-compact'); compact.setAttribute('aria-label','选择目录项目');
    const detail=el('section','','catalog-detail'); detail.setAttribute('aria-label','所选项目');
    const picker=el('label','','catalog-mobile-picker');
    picker.append(glyph('layers'),el('span','目录'),glyph('chevron-down'),compact);
    master.append(search,picker,results,list);
    root.append(toolbar,box('catalog-columns',master,detail));
    let rows=[];
    function address() {
      const query=new URLSearchParams();
      if (selected) query.set(mode,selected);
      if (mode==='source' && !selected) query.set('tab','sources');
      if (filter.value) query.set('q',filter.value);
      if (mode==='rule' && sourceKey) query.set('source',sourceKey);
      history.replaceState(history.state,'',Team.hash('rules')+(query.size?'?'+query:''));
    }
    function show() {
      const row=rows.find(r=>r.key===selected);
      detail.replaceChildren();
      if (!row) {
        detail.append(el('p',rows.length?'本版没有收录所选项目。':'没有匹配的项目。','catalog-empty'));
        if (filter.value) detail.append(action('清除搜索',()=>{filter.value='';populate();address();filter.focus();},'text-button'));
        return;
      }
      detail.dataset.record=row.key;
      if (mode==='source') {
        detail.append(sourceDetail(sources[row.key]));
        const users=data.rules.filter(r=>mappings[r.id]?.includes(row.key));
        if (users.length) {
          const select=el('select'); select.setAttribute('aria-label','查看引用此出处的检查程序');
          const placeholder=el('option','查看引用程序（'+users.length+'）'); placeholder.value='';select.append(placeholder);
          for (const rule of users) {const opt=el('option',rule.id+' · '+rule.name);opt.value=rule.id;select.append(opt);}
          select.addEventListener('change',()=>{
            if (!select.value) return;
            const previous=selected;
            mode='rule'; selected=select.value; sourceKey=previous; filter.value='';populate();address();
            (matchMedia('(max-width:740px)').matches?compact:list.querySelector('[aria-selected=true]'))?.focus();
          });
          detail.append(select);
        }
        return;
      }
      const rule=rules.get(row.key);
      detail.append(box('catalog-rule-head',el('span',row.key,'catalog-rule-code'),el('h2',rule.name)),
        el('p',rule.basis,'catalog-basis'));
      const entries=(mappings[row.key] || []).filter(id=>sources[id]).map(id=>[id,sources[id]]);
      if (entries.length) detail.append(sourceChooser(entries,null,sourceKey,key=>{sourceKey=key;address();}));
    }
    function select(key,userAction) {
      selected=key;
      compact.value=selected || '';
      const hasSelection=rows.some(r=>r.key===selected);
      Array.from(list.children).forEach((b,i)=>{
        const active=rows[i].key===selected;
        b.tabIndex=active || i===0 && !hasSelection?0:-1;
        b.setAttribute('aria-selected',String(active));
      });
      delete detail.dataset.record; show();
      if (userAction) address();
    }
    function populate(unknown=false) {
      for (const b of modes.children) b.setAttribute('aria-pressed',String(b.dataset.mode===mode));
      const terms=filter.value.normalize('NFKC').trim().toLowerCase().split(/\s+/).filter(Boolean);
      rows=all[mode].filter(r=>terms.every(t=>r.search.normalize('NFKC').toLowerCase().includes(t)));
      list.replaceChildren(); compact.replaceChildren();
      for (const [i,row] of rows.entries()) {
        const button=action('',()=>{sourceKey=null;select(row.key,true);},'catalog-row');
        button.setAttribute('role','option');
        if (mode==='rule') button.append(el('span',row.key,'catalog-code'));
        button.append(box('catalog-row-copy',el('strong',row.title),...(row.sub?[el('small',row.sub)]:[])));
        button.addEventListener('keydown',event=>{
          const to={ArrowDown:Math.min(i+1,rows.length-1),ArrowUp:Math.max(i-1,0),Home:0,End:rows.length-1}[event.key];
          if (to===undefined) return;
          event.preventDefault(); sourceKey=null;select(rows[to].key,true);list.children[to].focus();
        });
        list.append(button);
        const option=el('option',mode==='rule'?row.key+' · '+row.title:[row.title,row.sub].filter(Boolean).join(' · '));
        option.value=row.key;compact.append(option);
      }
      results.value=terms.length?'匹配 '+rows.length+' / '+all[mode].length+' 项':'';
      compact.disabled=!rows.length;
      if (!unknown && !rows.some(r=>r.key===selected)) {selected=rows[0]?.key || null;sourceKey=null;}
      select(selected,false);
      const chosen=list.querySelector('[aria-selected=true]');
      if (chosen && list.clientHeight && chosen.offsetTop>list.scrollTop+list.clientHeight) list.scrollTop=chosen.offsetTop;
    }
    for (const id of ['rule','source']) {
      const button=action('',()=>{
        if (mode===id) return;
        mode=id; selected=null; sourceKey=null; filter.value='';populate();address();
      });
      button.dataset.mode=id;
      button.append(glyph(id==='rule'?'card-checklist':'journal-text'),el('span',label[id]),el('small',String(all[id].length)));
      modes.append(button);
    }
    compact.addEventListener('change',()=>{sourceKey=null;select(compact.value,true);});
    filter.addEventListener('input',()=>{populate();address();});
    populate(Boolean(selected && !all[mode].some(r=>r.key===selected)));
    return root;
  }
  return {render,sourceChooser};
})();
