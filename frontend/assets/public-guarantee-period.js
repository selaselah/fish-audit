// This landing example is an immutable export of one watermarked workpaper.
const PublicGuaranteePeriod = (() => {
  const expected={contract:['receipt_clause','clause'],guarantee:['start','end'],receipt:['received'],bank:['paid']};
  function printedLine(row,link) {
    const sheet=document.createElement('canvas'), strip=document.createElement('canvas'), text=document.createElement('span');
    sheet.className='period-sheet'; strip.className='period-print'; text.className='period-transcript'; text.textContent=row.quote;
    for (const canvas of [sheet,strip]) { canvas.hidden=true; canvas.setAttribute('aria-hidden','true'); }
    link.classList.add('period-has-preview'); link.append(sheet,strip,text);
    VerifiedSamplePage.load(row.doc).then(img=>{
      const w=img.naturalWidth,h=img.naturalHeight;
      VerifiedSamplePage.crop(img,row.rect,strip);
      sheet.width=152; sheet.height=Math.round(152*h/w);
      const ctx=sheet.getContext('2d'); ctx.drawImage(img,0,0,sheet.width,sheet.height);
      ctx.fillStyle='rgba(226,170,59,.45)'; ctx.strokeStyle='#8c5812'; ctx.lineWidth=1.3;
      for (const [left,top,right,bottom] of row.rects) {
        const box=[left*sheet.width,top*sheet.height,(right-left)*sheet.width,(bottom-top)*sheet.height];
        ctx.fillRect(...box); ctx.strokeRect(...box);
      }
      for (const canvas of [sheet,strip]) { canvas.hidden=false; canvas.dataset.source=row.ref; }
      link.dataset.visual=''; link.dataset.printed='true'; text.hidden=true;
    }).catch(()=>{ /* The fixed quotation and PDF link remain available. */ });
  }
  function source(row,title) {
    const link=VerifiedSamplePage.link(row), meta=document.createElement('span'), name=document.createElement('strong');
    link.className='period-original-link';
    link.dataset.source=row.ref; link.dataset.key=row.key;
    link.setAttribute('aria-description',row.quote);
    meta.textContent=title+' · 第 '+row.doc.page+' 页 / '+row.line+' 行'; name.textContent=row.doc.title+'.pdf';
    const arrow=document.createElement('i'); arrow.className='ui-glyph ic-arrows-angle-expand'; arrow.setAttribute('aria-hidden','true');
    link.append(meta,name,arrow);
    if (['start','end','paid'].includes(row.key)) printedLine(row,link);
    return link;
  }
  function published(sample) {
    if (sample.case_id!=='dcda3682a4994b1f94b35b29fd22dbe5' || sample.rev!==2 || sample.rule_version!=='2026.11.27.06' ||
        sample.finding!=='H05-8' || sample.stage!=='第一期' || sample.state!=='expired' || !/^[a-f0-9]{64}$/.test(sample.report_sha256))
      throw new Error('Unexpected workpaper');
    const fields=new Map();
    for (const [role,keys] of Object.entries(expected)) {
      const doc=sample.documents[role];
      if (!doc || doc.lines.length!==keys.length || doc.page!==1 || doc.pdf!=='/showcase/guarantee-period-'+role+'.pdf' ||
          doc.image!=='/assets/guarantee-period-'+role+'.jpg' || ![doc.source_sha256,doc.page_sha256].every(s=>/^[a-f0-9]{64}$/.test(s)))
        throw new Error('Document mismatch');
      for (const line of doc.lines) {
        if (!keys.includes(line.key) || fields.has(line.key) || !Number.isSafeInteger(line.line) || line.line<=0 ||
            !/^advance-guarantee\/d\d+\/p1\/l\d+$/.test(line.ref) || !line.ref.endsWith('/l'+line.line) ||
            line.quote!==line.label+'：'+line.value || !Array.isArray(line.rects) || !line.rects.length ||
            !line.rects.every(r=>Array.isArray(r) && r.length===4 && r.every(n=>Number.isFinite(n) && n>=0 && n<=1) && r[0]<r[2] && r[1]<r[3]))
          throw new Error('Source location mismatch');
        fields.set(line.key,{...line,doc});
      }
    }
    const rows=Object.fromEntries(['clause','start','end','paid'].map(key=>[key,[fields.get(key)]]));
    rows.related=[fields.get('received'),fields.get('receipt_clause')];
    const day=key=>GuaranteePeriodCard.iso(fields.get(key).value);
    const start=day('start'),end=day('end'),paid=day('paid');
    if (!start || !end || !paid || start>end || paid<=end || fields.get('end').label!=='保函有效期至（含当日）') throw new Error('Unmatched dates');
    return {rows,start,end,paid,state:sample.state,inclusive:true};
  }
  let busy=false;
  async function open() {
    const slot=document.getElementById('payment-guarantee-period');
    if (slot.dataset.revision || busy) return;
    const retryFocus=slot.querySelector('.standard-retry')===document.activeElement;
    busy=true; slot.setAttribute('aria-busy','true');
    try {
      const integrity=slot.dataset.integrity;
      if (!/^sha256-[A-Za-z0-9+/]{43}=$/.test(integrity)) throw new Error('Missing sample digest');
      const res=await fetch('/assets/guarantee-period-sample.json',{integrity});
      if (!res.ok) throw new Error('Sample unavailable');
      const sample=await res.json(), model=published(sample);
      const heading=document.createElement('div'), title=document.createElement('h3'), badge=document.createElement('span');
      heading.className='public-period-heading'; title.textContent='首期预付款保函';
      badge.className='period-decision'; badge.textContent=GuaranteePeriodCard.describe(model).label;
      heading.append(title,badge);
      slot.replaceChildren(heading,GuaranteePeriodCard.render(model,'public-guarantee-period',source));
      slot.dataset.revision=sample.rev;
      if (!slot.hidden && !slot.closest('[role=tabpanel]').hidden) {
        document.getElementById('payment-version').textContent='合成案例 · R'+sample.rev;
        if (retryFocus) slot.querySelector('[role=tab][aria-selected=true]').focus({preventScroll:true});
      }
    } catch {
      const fallback=slot.querySelector('.period-fallback');
      if (fallback && !fallback.querySelector('button')) {
        const retry=document.createElement('button'), notice=document.createElement('span');
        notice.className='standard-load-status'; notice.setAttribute('role','status'); notice.textContent='日期对照暂未载入';
        retry.type='button'; retry.className='standard-retry'; retry.textContent='重新载入'; retry.addEventListener('click',open);
        fallback.append(notice,retry);
      }
    } finally { busy=false; slot.setAttribute('aria-busy','false'); }
  }
  return {open};
})();
