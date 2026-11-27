const PublicReleaseExamples = (() => {
  const choices={late:'回单早一天',current:'签名覆盖本版',earlier:'签后另存新版',comment:'Word 草稿会签',scan:'扫描签认栏'};
  const format={late:'typeset',current:'current',earlier:'earlier',comment:'word_review',scan:'photo'};
  const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text)e.textContent=text;return e;};
  let loading;
  function inspect(doc,ref,opener,whole=false) {
    const fallback=doc.original || doc.pdf;
    const target=ref || doc.lines[0]?.ref;
    const request=new CustomEvent(target?'inspect-sample-line':'inspect-sample-page',{cancelable:true,
      detail:{doc,ref:target,opener,scale:whole || !ref?'page':'line',loadPage:()=>VerifiedSamplePage.load(doc)}});
    if (document.dispatchEvent(request)) window.open(fallback,'_blank','noopener');
  }
  function form(sample) {
    const {docs,rows,record,key}=sample,doc=docs[record.doc],views={};
    if (format[key]!==record.state || doc.source_sha256!==record.original_sha256 || record.pages.length!==1 ||
        record.pages[0].sha256!==doc.page_sha256 || record.pages[0].ref!==doc.id+'/p1') throw new Error('未匹配原件');
    for (const [name,row] of Object.entries(rows)) {
      const d=docs[row.doc];
      const line=d?.lines.find(l=>row.ref && l.ref===row.ref && l.line===row.line);
      if (!d || row.ref && !line) throw new Error('未匹配原行');
      const rects=line?.rects;
      const bounds=rects && [Math.min(...rects.map(r=>r[0])),Math.min(...rects.map(r=>r[1])),Math.max(...rects.map(r=>r[2])),Math.max(...rects.map(r=>r[3]))];
      views[name]={value:row.value,verbatim:line?.value===row.value,place:row.ref?'第 1 页 · 第 '+row.line+' 行':'第 1 页 · 整页',
        excerpt:bounds?async()=>VerifiedSamplePage.crop(await VerifiedSamplePage.load(d),bounds):null,
        open:opener=>inspect(d,row.ref,opener)};
    }
    const notes=sample.notes.map(n=>({...n,place:views.annotation.place,open:views.annotation.open}));
    const original=doc.original || doc.pdf;
    const thumbnail=async()=>{
      const image=await VerifiedSamplePage.load(doc), canvas=node('canvas');
      canvas.width=144;canvas.height=Math.round(144*image.naturalHeight/image.naturalWidth);
      canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);return canvas;
    };
    const earlyPayment=sample.bank_status==='risk' && sample.timing==='before';
    return ReleaseCard.render({record,state:sample.status,doc:{name:doc.name,hash:doc.source_sha256,original},
      page:{number:1,open:opener=>inspect(doc,null,opener,true),thumbnail},rows:views,notes,
      initial:earlyPayment?'dates':'version',timing:sample.timing,dates:sample.dates,earlyPayment,
      flag:sample.status==='scope_pending'?'放行归属待核':'签署身份待核',
      digital:record.signatures?{...record,size:doc.size}:null},'public-release-'+key);
  }
  async function open() {
    const slot=document.getElementById('payment-release'),edition=document.getElementById('payment-version');
    if (slot.dataset.revision) {
      if (slot.dataset.requestedSlip) {
        const select=slot.querySelector('select');select.value=slot.dataset.requestedSlip;delete slot.dataset.requestedSlip;
        select.dispatchEvent(new Event('change'));
      }
      if (!slot.closest('[hidden]')) edition.textContent='合成演练 · R'+slot.dataset.revision;
      return;
    }
    if (loading) return loading;
    slot.setAttribute('aria-busy','true');
    loading=(async()=>{
      try {
        const res=await fetch('/assets/release-examples.json',{integrity:slot.dataset.integrity});
        if (!res.ok) throw new Error('案例索引未载入');
        const data=await res.json();
        if (data.rule!=='2026.11.27.11' || data.editions.length!==5 ||
            !data.editions.every((s,i)=>s.key===Object.keys(choices)[i])) throw new Error('案例版本待核');
        const toolbar=node('div','release-example-tools'),select=node('select'),out=node('div');
        const label=node('label','','样本');
        select.id='release-example';
        label.htmlFor=select.id;
        Object.entries(choices).forEach(([key,name])=>select.add(new Option(name,key)));
        toolbar.append(label,select);
        function selectCase(key,updateUrl) {
          const sample=data.editions.find(s=>s.key===key) || data.editions[0];
          const focused=document.activeElement===select,card=form(sample);
          card.querySelector('.release-flag').before(toolbar);out.replaceChildren(card);select.value=sample.key;slot.dataset.revision=String(sample.rev);
          if (focused) select.focus({preventScroll:true});
          if (!slot.closest('[hidden]')) edition.textContent='合成演练 · R'+sample.rev;
          if (updateUrl) {
            const url=new URL(location.href);url.searchParams.set('scene','payment-release');url.searchParams.set('slip',sample.key);
            history.replaceState(history.state,'',url);
          }
        }
        select.addEventListener('change',()=>selectCase(select.value,true));
        const requested=slot.dataset.requestedSlip;delete slot.dataset.requestedSlip;
        selectCase(requested || new URL(location.href).searchParams.get('slip'),Boolean(requested));
        slot.replaceChildren(out);
      } catch {
        const retry=node('button','standard-retry','重新载入案例');retry.type='button';
        retry.addEventListener('click',()=>{retry.remove();open();});
        slot.querySelector('.standard-retry')?.remove();slot.append(retry);
      } finally {slot.removeAttribute('aria-busy');loading=null;}
    })();
    return loading;
  }
  return {open};
})();
