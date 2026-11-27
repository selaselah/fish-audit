// Shared presentation for the signed original in a workpaper or the watermarked public example.
const PdfSignatureCard = (() => {
  const labels = {typeset:'排印签章栏',visual:'签署影像待核',current:'签名覆盖本版',earlier:'签名仅覆盖前版',
    mismatch:'签名校验不符',review:'签名结果待核',timestamp:'文档时间戳'};
  const instructions = {
    typeset:'请取得双方签署页或对应版本的电子签署记录。',
    visual:'请核对签署页影像、用印主体与授权依据。',
    current:'请核对证书信任链、双方签署身份及代表权限。',
    earlier:'请核对追加内容，以及双方最终确认的文件版本。',
    mismatch:'请调取签署平台原件，核对签名和文件版本。',
    review:'请取得签署平台记录，人工核对签名与原件。'
  };

  function node(tag, text, cls) {
    const result=document.createElement(tag);
    if (text) result.textContent=text;
    if (cls) result.className=cls;
    return result;
  }
  function icon(name) {
    const i=node('i','','ui-glyph ic-'+name); i.setAttribute('aria-hidden','true'); return i;
  }
  const bytes = value => Number.isSafeInteger(value) ? value.toLocaleString('zh-CN')+' 字节' : '待核';
  function attributes(pairs) {
    const list=node('dl','','pdf-facts');
    for (const [label,value] of pairs) {
      const row=node('div'); row.append(node('dt',label),node('dd',value)); list.append(row);
    }
    return list;
  }
  function digital(record) {
    const section=node('div','','pdf-digital');
    const entries=record.signatures;
    const selector=node('select');
    selector.setAttribute('aria-label','选择嵌入的签名记录');
    for (const [i,s] of entries.entries()) selector.add(new Option('记录 '+(i+1)+' · '+(labels[s.state] || '待核'),String(i)));
    if (entries.length>1) section.append(selector);
    const display=node('div'); section.append(display);
    function show(i) {
      const s=entries[i], reading=s?.state;
      const coverage=['current','earlier','mismatch'].includes(reading);
      const timeline=node('div','','pdf-timeline');
      timeline.dataset.state=reading || record.state;
      const first=node('div'), last=node('div');
      first.append(node('small',coverage?'签名所及':'嵌入式签名'),node('strong',coverage?'PDF 修订 '+s.revision:record.state==='unsigned'?'未检出':'待人工核对'));
      last.append(node('small','本次提交'),node('strong',reading==='current'?'同一版本':reading==='earlier'?'含后续修订':bytes(record.size)));
      const track=node('div','','pdf-track'); track.setAttribute('aria-hidden','true'); track.append(node('i'),node('i'),node('i'));
      timeline.append(first,last,track);
      if (reading==='earlier') {
        const added=node('span','签后追加 '+bytes(record.size-s.ends_at),'pdf-byte-delta');
        timeline.append(added);
      }
      const details=node('details','','pdf-technical');
      details.append(node('summary','查看文件校验明细'));
      const values=[['原件 SHA-256',record.original_sha256],['原件大小',bytes(record.size)]];
      if (s) {
        if (s.field) values.push(['PDF 字段名',s.field]);
        if (s.subfilter) values.push(['签名格式',s.subfilter]);
        if (s.ends_at) values.push(['签名范围终点',bytes(s.ends_at)]);
        if (s.digest) values.push(['摘要算法',s.digest.toUpperCase()]);
        if (s.certificate_sha256) values.push(['证书 SHA-256',s.certificate_sha256]);
      }
      details.append(attributes(values)); display.replaceChildren(timeline,details);
    }
    selector.selectedIndex=Math.max(0,entries.findIndex(s=>s.state===record.state));
    selector.addEventListener('change',()=>show(selector.selectedIndex));
    show(selector.selectedIndex);
    return section;
  }

  function render(model) {
    const {record,state,filename,original,rows,page,request}=model;
    const root=node('section','','pdf-signature-card');
    root.id=model.id; root.tabIndex=-1; root.dataset.state=state; root.setAttribute('aria-label','PDF 签署凭证');
    const head=node('div','','pdf-signature-head'), file=node('div');
    if (model.thumbnail) {
      const thumb=node('img','','pdf-document-thumb');thumb.alt='';thumb.loading='lazy';thumb.decoding='async';
      thumb.width=32;thumb.height=44;thumb.src=model.thumbnail;
      thumb.addEventListener('error',()=>thumb.replaceWith(icon('file-earmark-text')),{once:true});file.append(thumb);
    } else file.append(icon('file-earmark-text'));
    file.append(node('strong',filename));
    const download=node('a',model.originalLabel || '打开原件'); download.href=original; download.target='_blank'; download.rel='noopener';
    download.append(icon('arrows-angle-expand')); head.append(file,download);
    const title=node('div','','pdf-signature-title');
    title.append(node('strong',labels[state]),node('span',state==='mismatch'?'风险':'需人工校验'));
    const switches=node('div','','pdf-switches'); switches.setAttribute('role','tablist'); switches.setAttribute('aria-label','签署核对项目');
    const panel=node('div','','pdf-selected'); panel.id=root.id+'-body'; panel.setAttribute('role','tabpanel'); panel.tabIndex=0;
    const actions=[['签署页','journal-text'],['电子签名','shield-check'],['身份与授权','card-checklist']];
    function show(index) {
      [...switches.children].forEach((button,i)=>{ button.tabIndex=i===index?0:-1; button.setAttribute('aria-selected',String(i===index)); });
      panel.setAttribute('aria-labelledby',switches.children[index].id);
      if (index===0) {
        const content=node('div','','pdf-original-lines');
        if (rows.length) {
          for (const row of rows) {
            const source=row.control ? row.control() : row.open ? node('button') : node('a');
            if (!row.control && row.open) {source.type='button';source.addEventListener('click',row.open);}
            else if (!row.control) {source.href=original+'#page='+row.page;source.target='_blank';source.rel='noopener';}
            const place=row.side+' · 第 '+row.page+' 页'+(row.line?' 第 '+row.line+' 行':'');
            source.setAttribute('aria-label',place+'，'+row.quote);
            const preview=node('span','','pdf-line-quote');
            preview.append(node('span',row.quote,'pdf-line-literal'));
            function display(image) {
              if (!image) return;
              image.setAttribute('aria-hidden','true');preview.append(image);preview.classList.add('has-image');
            }
            if (row.image) {
              const image=node('img');image.alt='';image.decoding='async';
              image.addEventListener('load',()=>display(image),{once:true});image.src=row.image;
            } else if (row.excerpt) row.excerpt().then(display).catch(()=>{});
            source.append(node('small',place),preview,icon('arrows-angle-expand')); content.append(source);
          }
        } else {
          const open=node(page?'button':'a','核对签署原页');
          if (page) {open.type='button';open.addEventListener('click',page);}
          else {open.href=original+'#page=1';open.target='_blank';open.rel='noopener';}
          content.append(open);
        }
        panel.replaceChildren(content);
      } else if (index===1) panel.replaceChildren(digital(record));
      else {
        const content=node('div','','pdf-authority');
        content.append(icon('clipboard-check'),node('p',instructions[state]));
        if (request) {
          const button=node('button','起草补件要求');button.type='button';button.addEventListener('click',()=>request(instructions[state]));content.append(button);
        }
        if (model.basis) {
          const basis=node('a',model.basis.label,'pdf-basis');
          basis.href=model.basis.url; basis.target='_blank'; basis.rel='noopener'; content.append(basis);
        }
        panel.replaceChildren(content);
      }
    }
    actions.forEach(([label,symbol],i)=>{
      const button=node('button');button.type='button';button.id=root.id+'-tab-'+i;
      button.setAttribute('role','tab');button.setAttribute('aria-controls',panel.id);
      button.append(icon(symbol),node('span',label)); button.addEventListener('click',()=>show(i));
      button.addEventListener('keydown',e=>{
        const to={ArrowLeft:(i+2)%3,ArrowRight:(i+1)%3,Home:0,End:2}[e.key];
        if (to!==undefined) {e.preventDefault();show(to);switches.children[to].focus();}
      });
      switches.append(button);
    });
    root.append(head,title,switches,panel);show(state==='typeset'||state==='visual'?0:1);
    return root;
  }
  return {render,digital};
})();
