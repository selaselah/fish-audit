// The same evidence reader is used in the workpaper and in the public, watermarked case.
const SupplierCard = (() => {
  function element(tag, text, cls) {
    const node=document.createElement(tag);
    if (text) node.textContent=text;
    if (cls) node.className=cls;
    return node;
  }
  function icon(name) {
    const node=element('i','','ui-glyph ic-'+name);
    node.setAttribute('aria-hidden','true'); return node;
  }
  function command(label, destination, cls) {
    const node=element(typeof destination==='function'?'button':'a',label,cls);
    if (node.tagName==='BUTTON') {
      node.type='button'; node.addEventListener('click',destination);
    } else {
      node.href=destination; node.target='_blank'; node.rel='noopener';
    }
    return node;
  }
  function inspectLink(link,inspect) {
    if (!inspect) return;
    link.setAttribute('aria-haspopup','dialog'); link.setAttribute('aria-controls','sample-review');
    link.addEventListener('click',event=>{
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (inspect(link)) event.preventDefault();
    });
  }

  function difference(left,right) {
    const a=Array.from(left), b=Array.from(right);
    if (a.length>128 || b.length>128 || !a.length || !b.length) return null;
    const lengths=Array.from({length:a.length+1},()=>new Uint16Array(b.length+1));
    for (let i=a.length-1;i>=0;i--) {
      for (let j=b.length-1;j>=0;j--) lengths[i][j]=a[i]===b[j]?1+lengths[i+1][j+1]:Math.max(lengths[i+1][j],lengths[i][j+1]);
    }
    const common=[new Set(),new Set()];
    let i=0,j=0;
    while (i<a.length && j<b.length) {
      if (a[i]===b[j]) {common[0].add(i++);common[1].add(j++);}
      else if (lengths[i+1][j]>=lengths[i][j+1]) i++;
      else j++;
    }
    return [a,b].map((letters,side)=>{
      const fragments=[];
      letters.forEach((letter,n)=>{
        const changed=!common[side].has(n), last=fragments.at(-1);
        if (last?.changed===changed) last.text+=letter;
        else fragments.push({text:letter,changed});
      });
      return fragments;
    });
  }

  function identities(model) {
    const grid=element('div','','supplier-units');
    for (const unit of model.units) {
      const item=element('section','','supplier-unit');
      const heading=element('div','','supplier-document');
      heading.append(icon(unit.role==='contract'?'journal-text':'clipboard-check'),element('span',unit.label),element('small',unit.filename));
      const name=element('strong',unit.name || '名称待核','supplier-name');
      item.append(heading,name);
      for (const row of unit.rows) {
        const link=command('',row.open,'supplier-location');
        inspectLink(link,row.inspect);
        const caption=row.line?'第 '+row.page+' 页 · 第 '+row.line+' 行':'第 '+row.page+' 页 · 影像引文';
        link.setAttribute('aria-label',unit.filename+' · '+caption+' · '+row.quote);
        const strip=element('span','','supplier-strip');
        const literal=element('span',row.quote); strip.append(literal);
        if (row.excerpt) {
          Promise.resolve().then(row.excerpt).then(image=>{
            if (!image) return;
            image.setAttribute('aria-hidden','true');
            strip.replaceChildren(image);
          }).catch(()=>{});
        }
        link.append(strip,element('span',caption,'supplier-locator'),icon('arrows-angle-expand'));
        item.append(link);
      }
      for (const p of unit.unlocated || []) item.append(command('查看第 '+p.page+' 页',p.open,'supplier-file'));
      grid.append(item);
    }
    const names=model.units.map(unit=>unit.name);
    const runs=model.status==='risk' && names.length===2 && names.every(Boolean) && names[0]!==names[1] && difference(...names);
    if (!runs) return grid;
    const container=element('div'), label=element('label','','supplier-difference'), toggle=element('input');
    toggle.type='checkbox';toggle.checked=model.highlight!==false;toggle.setAttribute('role','switch');
    label.append(toggle,element('span','标出名称差异'));
    function highlight() {
      model.highlight=toggle.checked;
      Array.from(grid.querySelectorAll('.supplier-name')).forEach((name,i)=>{
        name.replaceChildren(...runs[i].map(run=>toggle.checked && run.changed?element('mark',run.text):document.createTextNode(run.text)));
      });
    }
    toggle.addEventListener('change',highlight); highlight(); container.append(label,grid);
    return container;
  }

  function proofDetails(page) {
    const details=element('details','','supplier-proof');
    details.append(element('summary','文件校验明细'));
    const list=element('dl');
    const fields=[['提交原件 SHA-256',page.original_sha256],['提交版页图 SHA-256',page.page_sha256]];
    const proof=page.comparison;
    if (proof) fields.push(['首版原件 SHA-256',proof.original_sha256],['首版页图 SHA-256',proof.first_page_sha256],
      ['首版文字 SHA-256',proof.first_text_sha256],['提交版文字 SHA-256',proof.text_sha256],
      ['首版字节数',proof.ends_at.toLocaleString('zh-CN')]);
    for (const [label,value] of fields) list.append(element('dt',label),element('dd',value));
    details.append(list); return details;
  }

  function records(model) {
    const list=element('div','','supplier-records');
    for (const p of model.pages) {
      const record=element('article','','supplier-record');
      const head=element('div','','supplier-record-head');
      if (p.thumbnail && p.open) {
        const preview=command('',p.open,'supplier-thumbnail');
        const image=element('img'); image.src=p.thumbnail; image.alt=''; image.loading='lazy'; image.decoding='async';
        preview.setAttribute('aria-label','核对'+p.filename+'第 '+p.page+' 页原图');
        inspectLink(preview,p.inspect);
        preview.append(image); head.append(preview);
      } else head.append(icon('file-earmark-text'));
      head.append(element('strong',p.filename+' · 第 '+p.page+' 页'));
      const original=command(p.download?'下载原件':'打开原件',p.original,'supplier-file');
      if (p.download) {
        original.download=p.filename; original.removeAttribute('target');
      } else original.append(icon('arrows-angle-expand'));
      head.append(original);
      record.append(head);
      if (p.state==='same_print') {
        const proof=element('div','','supplier-print');
        proof.append(icon('layers'),element('span','首版与提交版的页图、文字和行位一致')); record.append(proof);
      } else if (p.state==='review') {
        record.append(element('p','这页的版式仍需人工核对。','supplier-caution'));
      }
      for (const a of p.annotations) {
        const note=element('div','','supplier-note');
        const label={signature_field:'签名控件',signature_reason:'签名属性 · 签署原因',signature_details:'签名属性待核',annotation:'PDF 批注或表单'}[a.kind];
        note.dataset.kind=a.kind;
        const title=element('div','','supplier-note-label');
        title.append(icon(a.kind==='signature_field'?'shield-check':'journal-text'),element('strong',label),element('small','第 '+a.number+' 项'));
        note.append(title);
        if (a.signing_reason) note.append(element('blockquote',a.signing_reason+(a.reason_shortened?'…':'')));
        if (a.note) note.append(element('blockquote',a.note+(a.shortened?'…':'')));
        if (a.kind!=='signature_field' && !a.signing_reason && !a.note) note.append(element('span','请在原件中查看此项。','supplier-caution'));
        record.append(note);
      }
      if (Number.isInteger(p.count) && p.annotations.length<p.count) record.append(element('small','列出 '+p.annotations.length+' / '+p.count+' 项，完整记录见原件。'));
      record.append(proofDetails(p));
      if (p.related?.length) {
        const related=element('details','','supplier-proof supplier-related');
        related.append(element('summary','关联审计项 · '+p.related.length));
        const links=element('div','','supplier-crosslinks');
        for (const entry of p.related) {
          const button=command(entry.label,entry.open,'supplier-file');
          button.dataset.supplierRelated=entry.id; links.append(button);
        }
        related.append(links); record.append(related);
      }
      list.append(record);
    }
    return list;
  }

  function render(model) {
    const root=element('section','','supplier-card');
    root.id=model.id; root.tabIndex=-1; root.dataset.state=model.status; root.setAttribute('aria-label','供货主体核对');
    const head=element('div','','supplier-card-head');
    const label={ok:'供货主体一致',risk:'供货主体不一致',missing:'供货主体待核'}[model.status];
    const title=element('strong',model.legacy && model.status==='ok'?'当版供货名称相符':label,'supplier-result');
    title.prepend(icon({ok:'clipboard-check',risk:'exclamation-diamond',missing:'question-circle'}[model.status]));
    head.append(title);
    if (model.request) head.append(command('拟补件要求',model.request,'supplier-file'));
    const tabs=element('div','','supplier-tabs'); tabs.setAttribute('role','tablist'); tabs.setAttribute('aria-label','供货主体依据');
    const controls=element('div','','supplier-controls'); controls.append(tabs);
    const body=element('div','','supplier-body'); body.setAttribute('role','tabpanel'); body.tabIndex=0; body.id=model.id+'-body';
    const notes=model.pages.some(p=>p.state==='annotations');
    const views=[['主体原行','layers',identities],['页内记录','journal-text',records]];
    function select(index) {
      const tabFocused=tabs.contains(document.activeElement);
      Array.from(tabs.children).forEach((b,i)=>{ b.tabIndex=i===index?0:-1; b.setAttribute('aria-selected',String(i===index)); });
      body.setAttribute('aria-labelledby',tabs.children[index].id); body.replaceChildren(views[index][2](model));
      controls.querySelector('.supplier-difference')?.remove();
      const differenceSwitch=body.querySelector('.supplier-difference');
      if (differenceSwitch) controls.append(differenceSwitch);
      if (tabFocused) tabs.children[index].focus({preventScroll:true});
    }
    views.forEach(([label,glyph],i)=>{
      const button=command(label,()=>select(i)); button.prepend(icon(glyph)); button.id=model.id+'-tab-'+i;
      button.setAttribute('role','tab'); button.setAttribute('aria-controls',body.id);
      button.addEventListener('keydown',event=>{
        const target={ArrowLeft:1-i,ArrowRight:1-i,Home:0,End:1}[event.key];
        if (target!==undefined) {event.preventDefault();select(target);tabs.children[target].focus();}
      });
      tabs.append(button);
    });
    root.append(head);
    if (model.legacy) root.append(element('p','此版尚未核对签署原因，可打开 PDF 签名属性复查。','supplier-legacy'));
    root.append(controls,body);
    select(model.status==='missing' && notes ? 1 : 0);
    return root;
  }
  return {render};
})();
