const PublicAcceptanceOriginals = (() => {
  const word='/showcase/acceptance-original-',shared='/assets/acceptance-review-page.jpg';
  const choices={
    history:['原批注 · 历史 R7','/showcase/acceptance-review.docx'],
    clean:['排印签认',word+'clean.docx','word_text','missing'],limited:['数量签收批注','/showcase/acceptance-review.docx','word_review','risk'],
    hot:['实测超限',word+'hot.docx','word_review','issue'],scan:['扫描验收单',shared,'photo','missing'],
    retest:['整改后复验',word+'retest.docx','word_text','issue'],
  };
  const states={missing:'验收依据不足',risk:'验收风险',issue:'验收问题'};
  const params=new URLSearchParams(location.search),initial=params.getAll('record');
  let selected=params.get('scene')==='word-comments' && initial.length===1 && Object.hasOwn(choices,initial[0])?initial[0]:'history';
  let pending;
  function address(url) {
    if (url.searchParams.get('scene')==='word-comments' && selected!=='history') url.searchParams.set('record',selected);
    else url.searchParams.delete('record');
  }
  function forQuery(query) {
    if (/复验|整改/u.test(query)) selected='retest';
    else if (/扫描|照片/u.test(query)) selected='scan';
    else if (/超限/u.test(query)) selected='hot';
    else if (/排印|签认原件/u.test(query)) selected='clean';
    else if (/数量签收/u.test(query)) selected='limited';
    else selected='history';
  }
  function node(tag,label,cls) {
    const el=document.createElement(tag);if (label) el.textContent=label;if (cls) el.className=cls;return el;
  }
  async function index(integrity) {
    if (!/^sha256-[A-Za-z0-9+/]{43}=$/.test(integrity)) throw new Error('验收索引缺少摘要');
    if (!pending) pending=fetch('/assets/acceptance-original-samples.json',{integrity}).then(async response=>{
      if (!response.ok) throw new Error('验收索引未载入');
      const source=await response.json();
      if (source.rule_version!=='2026.11.27.10' || source.editions.map(s=>s.key).join()!=='clean,limited,hot,scan,retest') throw new Error('演练版次待核');
      return source.editions;
    }).catch(e=>{pending=null;throw e;});
    return pending;
  }
  function inspect(doc,ref,opener,scale='line') {
    const event=new CustomEvent(ref?'inspect-sample-line':'inspect-sample-page',{cancelable:true,
      detail:{doc,ref,opener,scale,loadPage:()=>VerifiedSamplePage.load(doc)}});
    return !document.dispatchEvent(event);
  }
  function control(doc,ref,scale) {
    return ()=>{
      const a=node('a');a.href=doc.original;a.target='_blank';a.rel='noopener';
      a.setAttribute('aria-haspopup','dialog');a.setAttribute('aria-controls','sample-review');
      a.addEventListener('click',e=>{
        if (!e.button && !e.metaKey && !e.ctrlKey && !e.altKey && !e.shiftKey && inspect(doc,ref,a,scale)) e.preventDefault();
      });return a;
    };
  }
  function card(s) {
    const {doc}=s,choice=choices[s.key],scan=s.key==='scan';
    const hash=v=>typeof v==='string' && /^[a-f0-9]{64}$/.test(v);
    const image=['clean','limited'].includes(s.key)?shared:'/assets/acceptance-original-'+s.key+'.jpg';
    if (doc.original!==choice[1] || doc.image!==image || s.state!==choice[2] || s.status!==choice[3] ||
        s.id!=='acceptance-original/'+doc.id || !hash(s.report_sha256) || !hash(doc.source_sha256) || !hash(doc.page_sha256) ||
        doc.page!==1 || doc.media!==(scan?'image':'word') || !Number.isSafeInteger(s.rev) || doc.version!=='合成案例 · R'+s.rev ||
        !Array.isArray(doc.lines) || doc.lines.map(r=>r.field).join()!==(scan?'':'acceptance_result,measured_result,acceptance_signer'+(s.key==='retest'?',defect_closure':'')) ||
        !Array.isArray(s.notes) || s.notes.length!==Number(['limited','hot'].includes(s.key))) throw new Error('演练原件未对应');
    const seen=new Set(),lines=doc.lines.map(row=>{
      if (row.page!==1 || !row.ref.startsWith(doc.id+'/p1/') || !Number.isSafeInteger(row.line) || row.line<=0 ||
          !['acceptance_result','acceptance_signer','measured_result','defect_closure'].includes(row.field) ||
          seen.has(row.field) || row.quote!==row.label+'：'+row.value || !row.rects?.length) throw new Error('原行待核');
      seen.add(row.field);
      return {...row,control:control(doc,row.ref,'line'),excerpt:async()=>VerifiedSamplePage.crop(await VerifiedSamplePage.load(doc),row.rect)};
    });
    const notes=s.notes.map(n=>{
      const located=lines.find(l=>l.field==='acceptance_result' && l.line===n.location?.line);
      if (!located || n.location.page!==1 || n.location.unit!==doc.id || n.location.page_sha256!==doc.page_sha256 ||
          n.location.facts?.length!==1 || n.location.facts[0]!==located.ref || n.anchor?.quote!==located.quote ||
          [...n.anchor.quote].slice(n.anchor.start,n.anchor.end).join('')!==n.anchor.selected || n.shortened) throw new Error('批注位置待核');
      return {...n,open:opener=>inspect(doc,located.ref,opener)};
    });
    const thumbnail=async()=>{
      const img=await VerifiedSamplePage.load(doc),canvas=node('canvas');canvas.width=128;canvas.height=Math.round(128*img.naturalHeight/img.naturalWidth);
      canvas.getContext('2d').drawImage(img,0,0,canvas.width,canvas.height);return canvas;
    };
    return AcceptanceOriginalCard.render({record:s.id,name:doc.name,original:doc.original,hash:doc.source_sha256,label:'扫描或拍照原件',
      initial:{limited:'notes',hot:'measured_result',retest:'defect_closure'}[s.key],
      pages:[{number:1,control:control(doc,doc.lines[0]?.ref,'page'),thumbnail}],lines,notes},'public-acceptance-'+s.key);
  }
  function open(slot,legacyOpen) {
    if (slot.showOriginal) {slot.showOriginal(selected);return;}
    const toolbar=node('div',null,'accept-example-tools'),label=node('label','验收资料'),select=node('select'),out=node('output');
    select.id='acceptance-record';label.htmlFor=select.id;
    for (const [key,[name]] of Object.entries(choices)) select.add(new Option(name,key));
    toolbar.append(label,select,out);
    const legacy=node('div'),body=node('div',null,'public-accept-file');
    legacy.append(...slot.childNodes);slot.replaceChildren(toolbar,legacy,body);
    const version=document.getElementById('inspection-version');
    let generation=0,shown;
    function visibleVersion(copy) {if (!slot.hidden && !document.getElementById('scene-inspection').hidden) version.textContent=copy;}
    async function choose(key) {
      if (!Object.hasOwn(choices,key)) return;
      const ticket=++generation;selected=key;select.value=key;
      const url=new URL(location.href);
      if (url.searchParams.get('scene')==='word-comments') {address(url);history.replaceState(history.state,'',url);}
      legacy.hidden=key!=='history';body.hidden=!legacy.hidden;out.textContent='';out.removeAttribute('data-state');
      if (!legacy.hidden) {body.removeAttribute('aria-busy');visibleVersion('合成案例 · R7');await legacyOpen(legacy);return;}
      if (shown?.key===key) {visibleVersion(shown.doc.version);out.textContent=states[shown.status];out.dataset.state=shown.status;return;}
      const restore=document.activeElement?.classList.contains('accept-source-retry');
      const status=node('span','正在载入验收原件…');status.setAttribute('role','status');
      body.replaceChildren(status);body.setAttribute('aria-busy','true');shown=null;visibleVersion('合成案例');
      try {
        const list=await index(slot.dataset.integrity),sample=list.find(s=>s.key===key);
        if (ticket!==generation) return;
        const view=card(sample);body.replaceChildren(view);shown=sample;visibleVersion(sample.doc.version);
        out.textContent=states[sample.status];out.dataset.state=sample.status;
        if (restore) view.focus({preventScroll:true});
      } catch {
        if (ticket!==generation) return;
        status.textContent='原件索引暂未载入';const file=node('a','打开水印原件'),retry=node('button','重新载入','accept-source-retry');
        file.href=choices[key][1];file.target='_blank';file.rel='noopener';retry.type='button';retry.addEventListener('click',()=>choose(key));body.append(file,retry);
      } finally {if (ticket===generation) body.removeAttribute('aria-busy');}
    }
    select.addEventListener('change',()=>choose(select.value));slot.showOriginal=choose;choose(selected);
  }
  return {open,address,forQuery};
})();
