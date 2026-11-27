// One issued release, with separate views for signing, authority and dates.
const ReleaseCard = (() => {
  const states={typeset:'排印签认栏',visual:'签署页含图形',current:'签名覆盖本版',earlier:'签名仅覆盖前版',
    mismatch:'签名校验不符',review:'签署凭证待核',word_text:'Word 排印件',word_visual:'Word 含图形',
    word_review:'Word 审阅版',photo:'扫描或拍照原件'};
  const prompts={typeset:'请调取签署页或签批记录。',visual:'请核对原页上的签章及其签署人。',
    current:'仍需核对证书持有人与合同指定人的关系。',earlier:'请核对签后追加内容及最终审批版本。',
    mismatch:'请向签署平台调取原件。',word_review:'请核对最终签发稿和会签记录。',
    word_visual:'请对照签认区和签批记录。',word_text:'请核对最终签发稿。',photo:'请对照整页核实签章和放行权限。',
    review:'请核对原件和签批记录。'};
  function node(tag,cls,text) {
    const n=document.createElement(tag);if (cls) n.className=cls;if (text) n.textContent=text;return n;
  }
  function icon(name) {
    const i=node('i','ui-glyph ic-'+name);i.setAttribute('aria-hidden','true');return i;
  }
  function button(cls,callback) {
    const b=node('button',cls);b.type='button';b.addEventListener('click',()=>callback(b));return b;
  }
  function entry(label,row,empty='待定位',images=false) {
    const item=row?button('release-entry',opener=>row.open(opener)):node('div','release-entry');
    const value=node('strong','',row?.value || empty);
    item.append(node('small','',label),value);
    if (row) {
      item.setAttribute('aria-haspopup','dialog');item.title='查看原件，'+row.place;
      if (images && row.excerpt) {
        const crop=node('span','release-crop');crop.setAttribute('aria-busy','true');item.append(crop);
        Promise.resolve().then(row.excerpt).then(canvas=>{
          if (!canvas) throw new Error('原行图缺失');
          canvas.setAttribute('aria-hidden','true');crop.replaceChildren(canvas);
          if (row.verbatim) value.classList.add('release-transcribed');
        }).catch(()=>{crop.textContent='原行未载入，可打开原页';}).finally(()=>crop.removeAttribute('aria-busy'));
      }
      const place=node('span','release-place',row.place.replace(/^第 (\d+) 页 · 第 (\d+) 行$/,'$1 页 · $2 行'));
      place.append(icon('arrows-angle-expand'));item.append(place);
    }
    return item;
  }
  function render(model,id) {
    const root=node('section','release-card'), {record,doc,rows}=model;
    root.dataset.releaseRecord=record.id;root.dataset.releaseState=model.state;
    root.setAttribute('aria-label','付款放行单核对');
    const head=node('header','release-head'), title=node('div','release-filename');
    title.append(icon('file-earmark-text'),node('strong','',doc.name));
    const flag=node('span','release-flag');
    head.append(title,flag);root.append(head);
    const body=node('div','release-body'),sheet=button('release-sheet',model.page.open),thumb=node('span','release-thumb');
    sheet.setAttribute('aria-label','查看'+doc.name+'第 '+model.page.number+' 页整页');
    thumb.append(icon('file-earmark-text'));
    const loc=node('span','release-sheet-label','第 '+model.page.number+' 页');loc.append(icon('arrows-angle-expand'));
    sheet.append(thumb,loc);body.append(sheet);
    Promise.resolve().then(model.page.thumbnail).then(img=>{
      if (img) {img.setAttribute('aria-hidden','true');thumb.replaceChildren(img);}
    }).catch(()=>{});
    const work=node('div','release-inspector'),tabs=node('div','release-tabs'),panel=node('div','release-pane');
    tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','核对放行依据');
    panel.setAttribute('role','tabpanel');panel.id=id+'-pane';panel.tabIndex=0;
    work.append(tabs,panel);body.append(work);root.append(body);
    const choices=[['version','签署版本'],['authority','放行权限']];
    if (rows.date || rows.paid || rows.approval) choices.push(['dates','付款时点']);
    let images=false;
    function sideBySide(left,right) {const pair=node('div','release-pair');pair.append(left,right);panel.append(pair);}
    function dateEntry(label,row,day,empty) {
      const item=entry(label,row,empty,images);
      if (row && /^\d{4}-\d{2}-\d{2}$/.test(day || '')) {
        const time=node('time','release-date'),year=node('span','release-year',day.slice(0,4)+' 年');
        time.dateTime=day;time.append(year,node('b','',day.slice(5)));item.querySelector('strong').replaceWith(time);
      }
      return item;
    }
    function show(key) {
      panel.replaceChildren();panel.dataset.releaseView=key;panel.dataset.originals=String(images);
      const early=key==='dates' && model.earlyPayment && rows.paid && rows.date;
      flag.textContent=early?'提前付款风险':model.flag;
      flag.dataset.risk=String(Boolean(early || model.risk));
      for (const tab of tabs.children) {
        const active=tab.dataset.view===key;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;
        if (active) panel.setAttribute('aria-labelledby',tab.id);
      }
      const available=key==='authority'?[rows.authority,rows.signer,rows.hold,rows.original,rows.receipt]
        :key==='dates'?[rows.date,rows.paid,rows.approval]:[];
      if (available.some(r=>r?.excerpt)) {
        const toggle=button('release-crop-toggle',()=>{
          images=!images;show(key);panel.querySelector('[role=switch]').focus({preventScroll:true});
        });
        toggle.setAttribute('role','switch');toggle.setAttribute('aria-checked',String(images));
        toggle.append(node('span','release-switch-track'),document.createTextNode('显示原行'));panel.append(toggle);
      }
      if (key==='authority') {
        sideBySide(entry('合同指定人',rows.authority,'待定位',images),entry('放行单签认栏',rows.signer,'待定位',images));
        if (model.state==='reference_mismatch') sideBySide(entry('验收单编号',rows.original,'待定位',images),entry('放行单所引编号',rows.receipt,'待定位',images));
        if (rows.hold) panel.append(entry('验收单付款意见',rows.hold,'待定位',images));
      } else if (key==='dates') {
        const signed=dateEntry('单上所列签字日',rows.date,model.dates?.signed,'日期待核');
        const paid=dateEntry('回单付款日',rows.paid,model.dates?.paid,'回单归属待核');
        const delta=(Date.parse(model.dates?.paid)-Date.parse(model.dates?.signed))/86400000;
        const sequence=delta<0?'before':delta>0?'after':'same_day';
        if (rows.date && rows.paid && Number.isInteger(delta) && sequence===model.timing) {
          const ribbon=node('div','release-dates'),span=node('div','release-span');
          ribbon.dataset.sequence=sequence;
          span.append(node('span','',delta?'间隔 '+Math.abs(delta)+' 天':'同日'));
          ribbon.append(delta<0?paid:signed,span,delta<0?signed:paid);panel.append(ribbon);
        } else sideBySide(signed,paid);
        if (!rows.date && rows.approval) panel.append(entry('单上审批日期',rows.approval,'待定位',images));
        const reading={before:'回单早于所列签字日',same_day:'两单同日，先后待核',after:'回单晚于所列签字日'};
        panel.append(node('p','release-guidance',reading[model.timing] || '实际放行时间待核'));
      } else {
        const heading=node('div','release-version');heading.append(icon('journal-text'),node('h4','',states[record.state]));panel.append(heading);
        if (model.digital?.signatures.length) panel.append(PdfSignatureCard.digital(model.digital));
        if (model.notes.length) {
          const notePanel=node('div','release-note');
          function noteAt(i) {
            const n=model.notes[i];notePanel.replaceChildren();
            notePanel.append(node('small','',n.author?'批注 · '+n.author:'原件批注'),node('blockquote','',n.text));
            if (n.anchor && n.open) notePanel.append(entry('所选正文',{value:n.anchor,place:n.place,open:n.open}));
            if (!n.open || n.shortened) notePanel.append(node('p','release-guidance',
              [!n.open && '正文位置待核',n.shortened && '批注节录，全文见原件'].filter(Boolean).join(' · ')));
          }
          if (model.notes.length>1) {
            const label=node('label','release-note-choice','原批注'),select=node('select','release-note-select');
            model.notes.forEach((_,i)=>select.add(new Option('批注 '+(i+1),String(i))));
            select.addEventListener('change',()=>noteAt(select.selectedIndex));
            label.append(select);panel.append(label);
          }
          noteAt(0);panel.append(notePanel);
        } else if (!model.digital?.signatures.length && rows.signer) panel.append(entry('签认栏原文',rows.signer));
        const qualifications=[];
        if (record.unplaced) qualifications.push(record.unplaced+' 条批注的单元归属待核');
        if (model.reviewCoverage && model.reviewCoverage!=='complete') qualifications.push('Word 审阅范围待核');
        panel.append(node('p','release-guidance',[...qualifications,prompts[record.state]].join(' · ')));
      }
    }
    for (const [key,label] of choices) {
      const tab=button('release-tab',()=>show(key));tab.textContent=label;tab.id=id+'-'+key;tab.dataset.view=key;
      tab.setAttribute('role','tab');tab.setAttribute('aria-controls',panel.id);tabs.append(tab);
    }
    tabs.addEventListener('keydown',event=>{
      const buttons=[...tabs.children],i=buttons.indexOf(event.target);
      const next={ArrowRight:(i+1)%buttons.length,ArrowLeft:(i+buttons.length-1)%buttons.length,Home:0,End:buttons.length-1}[event.key];
      if (i<0 || next===undefined) return;
      event.preventDefault();buttons[next].click();buttons[next].focus();
    });
    show(choices.some(([key])=>key===model.initial)?model.initial:'version');
    const foot=node('footer','release-foot'),download=node('a','release-download','下载原件');
    download.href=doc.original;download.download=doc.name;download.prepend(icon('folder2-open'));
    const files=node('div','release-file-actions');files.append(download);
    if (model.permalink) files.append(model.permalink);
    foot.append(files,originalFileCheck(doc.original,doc.hash));root.append(foot);
    return root;
  }
  return {render,states};
})();
