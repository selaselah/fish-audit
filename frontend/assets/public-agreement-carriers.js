// The public carrier picker compares separate issued workpapers from the same watermarked purchase.
const PublicAgreementCarriers = (() => {
  const versions=[
    {key:'pdf',label:'PDF'},
    {key:'printed',label:'Word 排印',state:'word_text',original:'/showcase/addendum-original-printed.docx'},
    {key:'commented',label:'Word 批注',state:'word_review',original:'/showcase/addendum-original-commented.docx'},
    {key:'scan',label:'扫描件',state:'photo',original:'/assets/addendum-invoice-agreement.jpg'},
  ];
  const params=new URLSearchParams(location.search), requested=params.getAll('carrier');
  let selected=params.get('scene')==='addendum-invoice' && requested.length===1 && versions.some(v=>v.key===requested[0])?requested[0]:'pdf';
  let index;
  function address(url) {
    if (url.searchParams.get('scene')==='addendum-invoice' && selected!=='pdf') url.searchParams.set('carrier',selected);
    else url.searchParams.delete('carrier');
  }
  function node(tag,text,cls) {
    const el=document.createElement(tag);if (text) el.textContent=text;if (cls) el.className=cls;return el;
  }
  function walk(doc,ref,opener,scale='line') {
    const event=new CustomEvent(ref?'inspect-sample-line':'inspect-sample-page',{cancelable:true,detail:{
      doc,ref,opener,scale,loadPage:()=>VerifiedSamplePage.load(doc)}});
    return !document.dispatchEvent(event);
  }
  function source(doc,ref,scale='line') {
    const a=node('a');a.href=doc.original;a.target='_blank';a.rel='noopener';
    a.setAttribute('aria-haspopup','dialog');a.setAttribute('aria-controls','sample-review');
    if (ref) a.dataset.source=ref;
    a.addEventListener('click',e=>{
      if (!e.button && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey && walk(doc,ref,a,scale)) e.preventDefault();
    });
    return a;
  }
  async function load(integrity) {
    if (!/^sha256-[A-Za-z0-9+/]{43}=$/.test(integrity)) throw new Error('索引摘要缺失');
    if (!index) index=fetch('/assets/addendum-originals-sample.json',{integrity}).then(async r=>{
      if (!r.ok) throw new Error('索引不可用');
      const sample=await r.json();
      if (sample.rule_version!=='2026.11.27.09' || sample.editions.map(e=>e.key).join()!=='word_text,word_review,photo') throw new Error('案例范围不符');
      return sample.editions;
    }).catch(error=>{ index=null; throw error; });
    return index;
  }
  function render(version,s,editions) {
    const {doc,notes}=s, scan=s.key==='photo', digest=value=>/^[a-f0-9]{64}$/.test(value);
    if (s.key!==version.state || !digest(s.report_sha256) || s.record_id!=='addendum-original/'+doc.id || doc.id!=='d04' ||
        !Number.isSafeInteger(s.rev) || s.rev<1 || doc.version!=='合成案例 · R'+s.rev ||
        s.applies!=='pending' || s.effective_on!==null || s.status!=='missing' || doc.original!==version.original ||
        doc.image!=='/assets/addendum-original-'+(scan?'scan':'word')+'.jpg' || !digest(doc.source_sha256) || !digest(doc.page_sha256) ||
        doc.media!==(scan?'image':'word') || doc.page!==1 || !Array.isArray(doc.lines) || !Array.isArray(notes)) throw new Error('文件来源待核');
    const fields=['previous_payment_stage','revised_payment_stage','buyer_signature','seller_signature'];
    if (doc.lines.length!==(scan?0:4) || doc.lines.some((r,i)=>r.field!==fields[i] || !r.ref.startsWith(doc.id+'/p1/') ||
        !Number.isSafeInteger(r.line) || !r.rects?.length || r.quote!==r.label+'：'+r.value) || notes.length!==(s.key==='word_review'?1:0)) throw new Error('原行不符');
    const comments=notes.map(n=>{
      const row=doc.lines[1], loc=n.location;
      if (loc?.unit!==doc.id || loc.page!==1 || loc.page_sha256!==doc.page_sha256 || loc.line!==row.line ||
          loc.facts?.length!==1 || loc.facts[0]!==row.ref || loc.printed!==row.quote || !n.anchor?.selected ||
          [...n.anchor.quote].slice(n.anchor.start,n.anchor.end).join('')!==n.anchor.selected || !n.text || n.shortened) throw new Error('批注来源不符');
      return {...n,open:opener=>walk(doc,row.ref,opener)};
    });
    const native={record:{kind:doc.media,state:s.key,unplaced:0},filename:doc.name,original:doc.original,page:1,
      label:{word_text:'Word 排印原件',word_review:'Word 定稿待核',photo:'补充协议影像'}[s.key],
      sourceHash:doc.source_sha256,sharedPage:s.key==='word_review' && editions.some(e=>e.key==='word_text' &&
        e.doc.page_sha256===doc.page_sha256 && e.doc.source_sha256!==doc.source_sha256),
      pages:[{number:1,hash:doc.page_sha256,load:()=>VerifiedSamplePage.load(doc),control:()=>source(doc,doc.lines[0]?.ref,'page')}],
      notes:comments,word:s.review,rows:doc.lines.slice(2).map((r,i)=>({...r,
        side:i?'乙方签章栏':'甲方签章栏',control:()=>source(doc,r.ref)}))};
    const terms=doc.lines.slice(0,2).map((r,i)=>({...r,page:1,label:i?'协议拟用':'变更前',
      control:()=>source(doc,r.ref),excerpt:()=>VerifiedSamplePage.load(doc).then(img=>VerifiedSamplePage.crop(img,r.rect))}));
    return AddendumCard.render([{key:s.record_id,label:version.label,native,terms}],'public-native-agreement');
  }
  function open(slot,loadPdf) {
    if (slot.showCarrier) { slot.showCarrier(selected);return; }
    const tabs=node('div',null,'agreement-carriers'), body=node('div'), pdf=node('div'), native=node('div');
    tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','对照补充协议的提交载体');
    pdf.dataset.integrity=slot.dataset.integrity;pdf.append(...slot.childNodes);
    body.id='public-agreement-carrier';body.setAttribute('role','tabpanel');body.tabIndex=0;
    body.append(pdf,native); slot.replaceChildren(tabs,body);
    let generation=0, loaded=null;
    const edition=()=>document.getElementById('payment-version');
    function versionLabel(text) {
      if (!slot.hidden && !document.getElementById('scene-folios').hidden) edition().textContent=text;
    }
    async function select(key) {
      const version=versions.find(v=>v.key===key);
      if (!version) return;
      const token=++generation;
      selected=key;body.setAttribute('aria-labelledby','carrier-'+key);body.dataset.carrier=key;
      for (const tab of tabs.children) {
        const active=tab.id==='carrier-'+key;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;
      }
      const url=new URL(location.href);
      if (url.searchParams.get('scene')==='addendum-invoice') {address(url);history.replaceState(history.state,'',url);}
      pdf.hidden=key!=='pdf';native.hidden=!pdf.hidden;
      if (!pdf.hidden) {
        native.removeAttribute('aria-busy');
        versionLabel('合成案例 · R10');
        if (!pdf.querySelector('#public-addendum-invoice')) await loadPdf(pdf);
        return;
      }
      if (loaded?.key===key) {versionLabel(loaded.version);return;}
      versionLabel('合成案例');
      const restore=native.querySelector('.standard-retry')===document.activeElement;
      const status=node('span','载入版本…');status.setAttribute('role','status');native.replaceChildren(status);loaded=null;
      native.setAttribute('aria-busy','true');
      try {
        const editions=await load(slot.dataset.carrierIntegrity), sample=editions.find(e=>e.key===version.state);
        if (token!==generation) return;
        const card=render(version,sample,editions);
        native.replaceChildren(card);loaded={key,version:sample.doc.version};versionLabel(loaded.version);
        if (restore) card.focus({preventScroll:true});
      } catch {
        if (token!==generation) return;
        status.textContent='演练版本暂未载入';
        const link=node('a','打开水印原件'),retry=node('button','重新载入','standard-retry');
        link.href=version.original;link.target='_blank';link.rel='noopener';
        retry.type='button';retry.addEventListener('click',()=>select(key));native.append(link,retry);
      } finally {
        if (token===generation) native.removeAttribute('aria-busy');
      }
    }
    for (const [i,v] of versions.entries()) {
      const tab=node('button',v.label);tab.type='button';tab.id='carrier-'+v.key;
      tab.setAttribute('role','tab');tab.setAttribute('aria-controls',body.id);
      tab.addEventListener('click',()=>select(v.key));
      tab.addEventListener('keydown',e=>{
        const j={ArrowLeft:(i+versions.length-1)%versions.length,ArrowRight:(i+1)%versions.length,Home:0,End:versions.length-1}[e.key];
        if (j!==undefined) { e.preventDefault(); tabs.children[j].focus(); select(versions[j].key); }
      });
      tabs.append(tab);
    }
    slot.showCarrier=select;select(selected);
  }
  function forQuery(query) {
    if (/批注/u.test(query)) selected='commented';
    else if (/扫描|照片/u.test(query)) selected='scan';
    else if (/排印|word|docx/iu.test(query)) selected='printed';
  }
  return {open,address,forQuery};
})();
