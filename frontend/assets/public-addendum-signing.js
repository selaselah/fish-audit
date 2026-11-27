const PublicAddendumSigning = (() => {
  const labels={typeset:'排印件',current:'电子签名版',earlier:'签后修订版'};
  const requested=new URL(location.href).searchParams.getAll('copy');
  let selected=requested.length===1 && Object.hasOwn(labels,requested[0])?requested[0]:'typeset';
  function address(url) { url.searchParams.set('copy',selected); }
  function evidence(row) {
    const link=VerifiedSamplePage.link(row);link.dataset.source=row.ref;return link;
  }
  function terms(doc,fields) {
    return fields.map((field,i)=>{
      const line=doc.lines.find(r=>r.field===field);
      if (!line) throw new Error('缺少变更原行');
      const row={...line,doc,page:doc.page};
      return {...row,label:i?'协议拟用':'变更前',excerpt:()=>VerifiedSamplePage.load(doc).then(image=>VerifiedSamplePage.crop(image,row.rect)),
        control:()=>evidence(row)};
    });
  }
  function model(sample) {
    const {key,doc}=sample, sha=/^[a-f0-9]{64}$/;
    const pdf=key==='typeset'?'/showcase/batch-version-addendum.pdf':'/showcase/addendum-signing-'+key+'.pdf';
    if (!Object.hasOwn(labels,key) || sample.state!==key || !sha.test(sample.report_sha256) ||
        sample.record_id!=='addendum-pdf/'+doc.id || doc.pdf!==pdf || doc.image!=='/assets/batch-version-addendum.jpg' ||
        !sha.test(doc.source_sha256) || !sha.test(doc.page_sha256) || !Array.isArray(sample.signatures)) throw new Error('协议索引不符');
    const rows=doc.lines.map(line=>({...line,doc,page:doc.page}));
    const parties=rows.filter(row=>['buyer_signature','seller_signature'].includes(row.field)).map(row=>({
      side:row.field==='buyer_signature'?'甲方签章栏':'乙方签章栏',page:row.page,line:row.line,quote:row.quote,
      control:()=>evidence(row),excerpt:()=>VerifiedSamplePage.load(doc).then(image=>VerifiedSamplePage.crop(image,row.rect)),
    }));
    return {key,label:labels[key],terms:terms(doc,['previous_criterion','revised_criterion']),pdf:{
      record:{state:key==='typeset'?'unsigned':key,size:sample.size,original_sha256:doc.source_sha256,signatures:sample.signatures},
      state:key,filename:doc.title+'.pdf',original:doc.pdf,thumbnail:doc.image,rows:parties,
    },onSelect:()=>{
      selected=key;
      if (document.getElementById('signing-example').value!=='addendum') return;
      document.getElementById('signing-example-version').textContent=doc.version;
      const url=new URL(location.href);
      if (url.searchParams.get('scene')==='addendum-signing') {
        address(url);history.replaceState(history.state,'',url);
      }
    }};
  }
  async function load(slot,path,render) {
    if (slot.getAttribute('aria-busy')==='true') return;
    slot.setAttribute('aria-busy','true');
    const focus=slot.querySelector('.standard-retry')===document.activeElement;
    try {
      const integrity=slot.dataset.integrity;
      if (!/^sha256-[A-Za-z0-9+/]{43}=$/.test(integrity)) throw new Error('缺少索引摘要');
      const response=await fetch(path,{integrity});
      if (!response.ok) throw new Error('索引不可用');
      const sample=await response.json();
      if (sample.rule_version!=='2026.11.27.08') throw new Error('演练版本不符');
      const panel=render(sample);
      slot.replaceChildren(panel);
      if (focus && slot.getClientRects().length) (panel.querySelector('[aria-pressed=true]') || panel).focus({preventScroll:true});
    } catch {
      if (!slot.querySelector('.standard-retry')) {
        const button=document.createElement('button'), status=document.createElement('span');
        status.setAttribute('role','status');status.textContent='协议凭证暂未载入';
        button.className='standard-retry'; button.type='button'; button.textContent='重新载入';
        button.addEventListener('click',()=>load(slot,path,render)); slot.querySelector('.period-fallback').append(status,button);
      }
    } finally { slot.setAttribute('aria-busy','false'); }
  }
  function open() {
    const slot=document.getElementById('signing-addendum'),card=slot.querySelector('.addendum-card');
    if (card) { card.dispatchEvent(new CustomEvent('select-agreement',{detail:selected})); return; }
    return load(slot,'/assets/addendum-signing-sample.json',sample=>{
      if (sample.editions.map(e=>e.key).join()!=='typeset,current,earlier') throw new Error('演练原件不符');
      return AddendumCard.render(sample.editions.map(model),'public-addendum-signing',selected);
    });
  }
  function openInvoice() {
    const slot=document.getElementById('payment-addendum-invoice');
    if (slot.querySelector('.addendum-card')) return;
    return load(slot,'/assets/addendum-invoice-sample.json',s=>{
      const {agreement,bank}=s.documents;
      const sha=/^[a-f0-9]{64}$/;
      if (s.record_id!=='addendum-pdf/'+agreement.id || !sha.test(s.report_sha256) ||
          ![s.phase,s.payment].every(f=>f?.status==='missing' && f.applies==='pending' && f.effective_on===null) ||
          !Object.entries(s.documents).every(([role,d])=>['agreement','bank'].includes(role) && sha.test(d.source_sha256) &&
            sha.test(d.page_sha256) && d.pdf==='/showcase/addendum-invoice-'+role+'.pdf' && d.image==='/assets/addendum-invoice-'+role+'.jpg')) throw new Error('协议与回单来源不符');
      const panel=document.createElement('section');panel.id='public-addendum-invoice';panel.className='addendum-card addendum-invoice';panel.tabIndex=-1;
      const head=document.createElement('header'), title=document.createElement('h3'), status=document.createElement('span');
      title.id='public-addendum-invoice-title';title.textContent=s.stage+'验收款 · '+s.share+'%';panel.setAttribute('aria-labelledby',title.id);
      status.textContent='实付依据待核';head.append(title,status);
      panel.append(head,AddendumCard.termPanel(terms(agreement,['previous_payment_stage','revised_payment_stage'])));
      const dates=document.createElement('ol');dates.className='addendum-dates';dates.setAttribute('aria-label','原件所列日期');
      for (const [doc,field,label,iso] of [[agreement,'buyer_sealed_on','甲方盖章栏日期',s.buyer_on],
        [bank,'paid_on','银行实付',s.paid_on],[agreement,'seller_sealed_on','乙方盖章栏日期',s.seller_on]]) {
        const row=doc.lines.find(line=>line.field===field);
        if (!row || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) throw new Error('缺少日期原行');
        const li=document.createElement('li'), link=evidence({...row,doc}),caption=document.createElement('small'),day=document.createElement('time');
        caption.textContent=label;day.dateTime=iso;day.textContent=row.value;
        link.append(caption,day);li.append(link);dates.append(li);
      }
      panel.append(dates); return panel;
    });
  }
  return {open,openInvoice,address};
})();
