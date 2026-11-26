// Use the same document-by-document comparison for an issued workpaper and a watermarked specimen.
const AcceptanceRosterCard = (() => {
  function make(tag,cls,text) {
    const node=document.createElement(tag);
    if (cls) node.className=cls;
    if (text) node.textContent=text;
    return node;
  }
  function render(data,id,dialogId,headingLevel='h4') {
    const panel=make('section','acceptance-roster');
    const heading=make(headingLevel,'roster-title','验收签字核对'); heading.id=id+'-title';
    panel.setAttribute('aria-labelledby',heading.id);
    const header=make('div','roster-head'), context=make('div','roster-document');
    const mode=make('span','roster-requirement',data.mode==='joint'?'共同签字':'指定签字');
    const formats=make('div','roster-formats');
    formats.setAttribute('role','group'); formats.setAttribute('aria-label','原行影像或文字抄录');
    function setFormat(format) {
      panel.dataset.format=format;
      for (const button of formats.children) button.setAttribute('aria-pressed',String(button.value===format));
    }
    for (const [value,label] of [['image','原行'],['text','文字']]) {
      const button=make('button','',label); button.type='button'; button.value=value;
      button.addEventListener('click',()=>setFormat(value)); formats.append(button);
    }
    setFormat('image'); header.append(heading,formats);
    const picker=make('select','roster-picker'); picker.setAttribute('aria-label','选择验收或复验单据');
    const recordLabel=r=>(r.role==='reinspection'?'整改复验':'原验收')+' · '+r.file;
    for (const r of data.records) {
      const option=make('option','',recordLabel(r)); option.value=r.unit; picker.append(option);
    }
    context.append(mode,data.records.length>1?picker:make('span','',recordLabel(data.records[0])));
    const fields=make('fieldset','roster-people'), legend=make('legend','roster-sr','选择姓名核对原行');
    const columns=make('div','roster-columns'); columns.setAttribute('aria-hidden','true');
    for (const title of ['姓名','合同条款','本单签字栏']) columns.append(make('span','',title));
    const rows=make('div','roster-rows');
    fields.append(legend,columns,rows);
    const evidence=make('div','roster-evidence'); evidence.dataset.visual='';
    const note=make('p','roster-review-note');
    const announce=make('span','roster-sr'); announce.setAttribute('role','status');
    const phases=make('details','roster-phases'), phaseTitle=make('summary','','引用本单签字栏的付款条件');
    const phaseList=make('div','roster-phase-list');
    phases.append(phaseTitle,phaseList);
    panel.append(header,context,fields,note,evidence,phases,announce);

    function original(source,kind,person) {
      const open=make(source.url?'a':'button','roster-source'), head=make('span','roster-locator');
      const place='第 '+source.page+' 页 · 第 '+source.line+' 行';
      if (source.url) { open.href=source.url; open.target='_blank'; open.rel='noopener'; }
      else open.type='button';
      open.setAttribute('aria-controls',dialogId); open.setAttribute('aria-haspopup','dialog');
      open.dataset.rosterSource=source.ref;
      const icon=make('i','ui-glyph ic-arrows-angle-expand'); icon.setAttribute('aria-hidden','true');
      head.append(make('strong','',kind),make('small','',place),icon);
      const strip=make('span','roster-strip'), quote=make('span','roster-quote',source.quote);
      const at=person?source.quote.indexOf(person):-1;
      if (at!==-1) quote.replaceChildren(source.quote.slice(0,at),make('mark','',person),source.quote.slice(at+person.length));
      const body=make('span','roster-source-body');
      body.append(head,strip,quote); open.append(body,make('span','roster-sr','，打开'+source.file+'原页'));
      const transcription=make('span','roster-copy-label','文字抄录');
      if (source.excerpt) head.firstChild.after(transcription);
      source.excerpt?.().then(crop=>{
        if (!crop || !evidence.contains(open)) return;
        crop.setAttribute('aria-hidden','true'); strip.replaceChildren(crop); body.dataset.crop='true';
      }).catch(()=>{ /* Show the quoted physical line when its image is unavailable. */ });
      source.thumbnail?.().then(sheet=>{
        if (!sheet || !evidence.contains(open)) return;
        const miniature=make('span','roster-sheet'); miniature.setAttribute('aria-hidden','true'); miniature.append(sheet);
        for (const [left,top,right,bottom] of source.rects) {
          const mark=make('i');
          Object.assign(mark.style,{left:100*left+'%',top:100*top+'%',width:100*(right-left)+'%',height:100*(bottom-top)+'%'});
          miniature.append(mark);
        }
        open.append(miniature); open.classList.add('with-sheet');
      }).catch(()=>{ /* The cited line and full-page control work independently. */ });
      open.addEventListener('click',event=>{
        if (source.url && (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)) return;
        if (source.open(open)!==false) event.preventDefault();
      });
      return open;
    }
    function selectRecord(record) {
      panel.dataset.record=record.unit; picker.value=record.unit;
      const names=[...new Set([...data.required,...record.signed.map(s=>s.name)])];
      const people=names.map(name=>{
        const signed=record.signed.filter(r=>r.name===name), listed=data.required.includes(name);
        const checked=signed.filter(r=>r.confirmed).length;
        const printed=signed.length>1?signed.length+' 栏待核':checked?'已核图':signed.length?'待核图':'缺已核栏';
        return {name,listed,signed,printed,attention:!listed || signed.length!==1 || checked!==1};
      });
      const initial=people.find(p=>!p.listed) || people.find(p=>p.attention) || people[0];
      const detail=record.detail || '';
      const authorization='请核查代签授权或其他依据。';
      if (detail.endsWith(authorization)) {
        const names=people.filter(p=>!p.listed && p.signed.some(s=>s.confirmed)).map(p=>p.name);
        note.textContent=names.length?names.join('、')+' · '+authorization:detail;
      } else note.textContent=record.status==='ok' || /^尚缺.+逐人对照原页核准的签字。$/u.test(detail)?'':detail;
      note.hidden=!note.textContent;
      function selectPerson(person,notify) {
        panel.dataset.person=person.name;
        evidence.replaceChildren(original(data.contract,'合同约定',person.name));
        for (const signed of person.signed) evidence.append(original(signed.source,record.role==='reinspection'?'复验签字栏':'验收签字栏',person.name));
        if (!person.signed.length)
          evidence.append(make('p','roster-absent','本单缺少'+person.name+'的已核签字栏'));
        if (notify) announce.textContent=record.file+'，'+person.name+'，'+person.printed;
      }
      rows.replaceChildren();
      for (const person of people) {
        const label=make('label','roster-row'), name=make('span','roster-name'), radio=make('input');
        const designation=person.listed?'已列名':'条款未列';
        radio.type='radio'; radio.name=id+'-person'; radio.value=person.name; radio.checked=person===initial;
        radio.setAttribute('aria-label',person.name+'，合同'+designation+'，本单'+person.printed);
        radio.addEventListener('change',()=>{ if (radio.checked) selectPerson(person,true); });
        name.append(radio,make('strong','',person.name));
        label.append(name,make('span',person.listed?'':'roster-discrepancy',designation),
          make('span',person.signed.length===1 && person.signed[0].confirmed?'':'roster-discrepancy',person.printed));
        rows.append(label);
      }
      selectPerson(initial,false);
      phases.hidden=!record.phases.length; phases.open=false; phaseList.replaceChildren();
      for (const phase of record.phases) {
        const status={ok:'条件相符',missing:'待补依据',risk:'有风险',issue:'有问题'}[phase.status];
        phaseList.append(original(phase.source,phase.name+' · '+status));
      }
    }
    picker.addEventListener('change',()=>selectRecord(data.records.find(r=>r.unit===picker.value)));
    selectRecord(data.records.find(r=>r.status==='risk') || data.records.find(r=>r.status==='missing') || data.records[0]);
    return panel;
  }
  return {render};
})();
