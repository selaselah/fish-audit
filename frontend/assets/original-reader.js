const OriginalReader = (() => {
  const dialog = document.querySelector('#page-dialog');
  const navigation = document.querySelector('#reader-navigation');
  let active;

  function pageNumbers(item, graph) {
    if (!graph) return Array.from({length:item.pages}, (_, i)=>i+1);
    const prefix = item.id+'/p';
    return graph.nodes.filter(n=>n.type==='page' && n.id.startsWith(prefix))
      .map(n=>n.id.slice(prefix.length)).filter(n=>/^[1-9]\d*$/.test(n)).map(Number).sort((a,b)=>a-b);
  }

  function clear() {
    active?.dispose();
    active = null;
    navigation.replaceChildren();
    navigation.hidden = true;
    document.querySelector('#page-content').replaceChildren();
  }
  dialog.addEventListener('close',()=>{ if (!dialog.open) clear(); });
  dialog.addEventListener('keydown',event=>{
    if (event.key==='Escape' && !event.defaultPrevented && !event.isComposing &&
        document.querySelector('dialog[open]:not(#page-dialog)')) {
      event.preventDefault(); event.stopPropagation(); dialog.close();
    }
  });

  function sync() {
    if (active && !active.current()) {
      if (dialog.open) dialog.close();
      clear();
    }
  }

  function open(item, first, anchor) {
    clear();
    const root = base(), revision = state.bundle?.rev, graph = state.bundle?.report.graph;
    const pages = pageNumbers(item,graph);
    const selections = new Map();
    const pinned = revision ? '?rev='+revision : '';
    const url = (page, thumbnail=false)=>root+'/documents/'+item.id+'/pages/'+page+(thumbnail?'/thumbnail':'')+pinned;
    const editable = canReviewCurrentPaper();
    const current = ()=>state.detail && base()===root && state.bundle?.rev===revision && canReviewCurrentPaper()===editable;
    const revisionLabel = document.querySelector('#reader-revision');
    revisionLabel.hidden = !revision;
    revisionLabel.textContent = revision ? 'R'+revision : '';
    let at = first, observer, request;
    active = {current, dispose() { observer?.disconnect(); request?.abort(); }};

    function show(page) {
      if (!current()) { sync(); return; }
      request?.abort();
      request = new AbortController();
      at = page;
      if (!selections.has(page)) selections.set(page,new Set());
      renderOriginalPage(item, page, page===first?anchor:{}, selections.get(page), url(page), request.signal);
    }
    show(first);
    if (pages.length<2 || !pages.includes(first)) return;

    const strip = box('reader-thumbnails');
    const overview = box('reader-map-content',strip);
    overview.id = 'reader-thumbnails'; overview.hidden = true;
    strip.setAttribute('role','group'); strip.setAttribute('aria-label','选择原件页图');
    const position = el('span','','reader-position');
    const map = action('',()=>toggle(overview.hidden),'reader-map');
    map.append(glyph('layers'),position,glyph('chevron-down'));
    map.setAttribute('aria-controls',overview.id); map.setAttribute('aria-expanded','false');
    const arrow = (label, step)=>{
      const button = action('',()=>navigate(pages[pages.indexOf(at)+step],button),'reader-step');
      button.append(glyph('chevron-down')); button.title = label;
      button.setAttribute('aria-label',label); button.dataset.step = String(step);
      return button;
    };
    const previous = arrow('上一页',-1), next = arrow('下一页',1);
    const back = action('返回引文',()=>navigate(first,map),'reader-return');
    back.prepend(glyph('arrow-counterclockwise'));
    back.setAttribute('aria-label','返回引文，第 '+first+' 页');
    const cited = Boolean(anchor.lineHint || anchor.rawRef || graph?.facts.some(f=>f.id===anchor.highlight));
    const pager = box('reader-pager',previous,map,next);
    pager.setAttribute('role','group'); pager.setAttribute('aria-label','原件翻页');
    const bar = box('reader-bar',pager,back);
    const announced = el('output','','visually-hidden');
    const thumbs = new Map();
    let jump;
    if (pages.length>6) {
      jump = el('select');
      jump.setAttribute('aria-label','跳到原件页码');
      for (const page of pages) jump.add(new Option('第 '+page+' 页',String(page)));
      jump.addEventListener('change',()=>navigate(Number(jump.value),jump));
      const label = el('label','跳到','reader-jump');
      label.append(jump); overview.prepend(label);
    }
    navigation.replaceChildren(bar,overview,announced); navigation.hidden = false;
    function keepVisible(button) {
      if (overview.hidden || !button) return;
      const page = button.getBoundingClientRect(), area = strip.getBoundingClientRect();
      if (page.left<area.left+5) strip.scrollLeft += page.left-area.left-5;
      else if (page.right>area.right-5) strip.scrollLeft += page.right-area.right+5;
    }
    function update() {
      const i = pages.indexOf(at);
      previous.disabled = i===0; next.disabled = i===pages.length-1;
      back.hidden = !cited || at===first;
      if (jump) jump.value = String(at);
      position.textContent = at+' / '+item.pages;
      map.setAttribute('aria-label',position.textContent+'，原件缩略图，共 '+pages.length+' 张可阅页图');
      map.title = '展开或收起原件缩略图';
      for (const [number,button] of thumbs) {
        button.tabIndex = number===at?0:-1;
        if (number===at) button.setAttribute('aria-current','page');
        else button.removeAttribute('aria-current');
      }
      keepVisible(thumbs.get(at));
    }
    function navigate(page, control) {
      if (!pages.includes(page)) return;
      if (page!==at) {
        show(page);
        if (!current()) return;
        announced.textContent = item.name+'，第 '+at+' 页';
        update();
      }
      (control?.disabled?map:control)?.focus({preventScroll:true});
    }
    function fill() {
      observer = new IntersectionObserver(entries=>{
        for (const entry of entries) {
          if (!entry.isIntersecting || !entry.target.isConnected || overview.hidden) continue;
          const button = entry.target, image = button.querySelector('img');
          image.src = url(Number(button.dataset.page),true);
          observer.unobserve(button);
        }
      },{root:strip,rootMargin:'0px 36px'});
      for (const page of pages) {
        const image = el('img'); image.alt = ''; image.decoding = 'async';
        const preview = box('reader-miniature',glyph('file-earmark-text'),image);
        const button = action('',()=>navigate(page,button),'reader-thumb');
        button.dataset.page = String(page);
        const label = '查看第 '+page+' 页';
        button.setAttribute('aria-label',label);
        image.addEventListener('load',()=>{ preview.dataset.state='loaded'; button.setAttribute('aria-label',label); });
        image.addEventListener('error',()=>{ preview.dataset.state='failed'; button.setAttribute('aria-label',label+'，缩略图未载入'); });
        button.append(preview,el('span','第 '+page+' 页'));
        thumbs.set(page,button); strip.append(button); observer.observe(button);
      }
      strip.addEventListener('keydown',event=>{
        const i = pages.indexOf(at);
        const page = {ArrowLeft:pages[i-1],ArrowRight:pages[i+1],Home:pages[0],End:pages.at(-1)}[event.key];
        if (page) { event.preventDefault(); navigate(page,thumbs.get(page)); }
      });
    }
    function toggle(expanded) {
      overview.hidden = !expanded;
      map.setAttribute('aria-expanded',String(expanded));
      if (!expanded) return;
      if (!thumbs.size) fill();
      else for (const failed of strip.querySelectorAll('[data-state="failed"]')) observer.observe(failed.parentElement);
      update();
      thumbs.get(at)?.focus({preventScroll:true});
    }
    update();
  }
  return {open, sync, pageNumbers};
})();
