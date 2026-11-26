// Use the published options as the directory so search, selection and deep links always refer to the same case.
const PublicCaseFinder = (() => {
  const terms={
    'signing-example':{company:'盖章 签章 主体 公司',word:'docx 排印 签章',calendar:'日期 同日 盖章',pdf:'电子签名 数字签名 签后修改 证书'},
    'inspection-example':{readings:'实测 温度 柜温 超限',standards:'补充协议 标准变更 批次 温度',signers:'人员 联签 签字',
      equipment:'数量 设备',named:'编号 序列号 设备',supplier:'供货 主体 签署',comments:'批注 docx'},
    'payment-example':{guarantee:'预付款 保函 担保 有效期 到期 过期 展期',comments:'分期 比例 批注 docx',reference:'回单 批次 单号',
      timing:'验收 签字 扣款 日期',clock:'签字 扣款 时分',proof:'扣款 银行 受理 申请',folios:'多页 合同号 续页'}
  };
  function mount(tabs,pickers,choose) {
    const opener=document.getElementById('find-case'), dialog=document.getElementById('case-finder');
    if (typeof dialog.showModal!=='function') return;
    const input=dialog.querySelector('input'), results=dialog.querySelector('[role=listbox]'), empty=dialog.querySelector('.finder-empty');
    const status=dialog.querySelector('[role=status]');
    const catalog=pickers.flatMap((picker,i)=>Array.from(picker.options,option=>{
      const tab=tabs[i], group=tab.querySelector('strong').textContent, label=option.textContent, value=option.value;
      return {tab,picker,value,label,group,icon:tab.querySelector('i').className,
        words:(label+' '+group+' '+(terms[picker.id]?.[value] || '')).normalize('NFKC').toLowerCase()};
    }));
    let filtered=[], options=[], index=0, previous;
    function highlight(n,reveal=false) {
      index=n;
      const active=options[n];
      for (const row of options) row.setAttribute('aria-selected',String(row===active));
      if (active) {
        input.setAttribute('aria-activedescendant',active.id);
        if (reveal) active.scrollIntoView({block:'nearest',behavior:'instant'});
      } else input.removeAttribute('aria-activedescendant');
    }
    function filter() {
      const query=input.value.trim().normalize('NFKC').toLowerCase().split(/\s+/u).filter(Boolean);
      filtered=catalog.filter(entry=>query.every(word=>entry.words.includes(word)));
      const groups=new Map();
      options=filtered.map((item,i)=>{
        if (!groups.has(item.group)) {
          const group=document.createElement('div'); group.setAttribute('role','group'); group.setAttribute('aria-label',item.group);
          const heading=document.createElement('div'); heading.className='finder-group-title'; heading.setAttribute('aria-hidden','true');
          const icon=document.createElement('i'); icon.className=item.icon; heading.append(icon,item.group);
          group.append(heading); groups.set(item.group,group);
        }
        const option=document.createElement('div'); option.setAttribute('role','option'); option.id='finder-option-'+i;
        const label=document.createElement('strong'), enter=document.createElement('span'); label.textContent=item.label;
        enter.className='finder-enter'; enter.textContent='↵'; enter.setAttribute('aria-hidden','true');
        option.append(label,enter); groups.get(item.group).append(option);
        return option;
      });
      results.replaceChildren(...groups.values()); results.scrollTop=0; empty.hidden=Boolean(filtered.length);
      status.textContent=filtered.length+' 个案例';
      highlight(0);
    }
    function accept(i) {
      const item=filtered[i];
      if (!item) return;
      dialog.close(); choose(item.tab,item.picker,item.value);
    }
    function dismiss() {
      dialog.close();
      (previous && previous!==document.body?previous:opener).focus({preventScroll:true});
    }
    function open() {
      if (document.querySelector('dialog[open]')) return;
      previous=document.activeElement; input.value=''; filter();
      dialog.showModal(); input.focus({preventScroll:true}); fitKeyboard();
    }
    function fitKeyboard() {
      const viewport=window.visualViewport;
      if (!dialog.open || !viewport) return;
      dialog.style.setProperty('--finder-space',Math.round(viewport.height)+'px');
      dialog.style.setProperty('--finder-keyboard',Math.max(0,Math.round(innerHeight-viewport.height-viewport.offsetTop))+'px');
    }
    window.visualViewport?.addEventListener('resize',fitKeyboard);
    window.visualViewport?.addEventListener('scroll',fitKeyboard);
    opener.querySelector('kbd').textContent=/Mac|iPad|iPhone/u.test(navigator.platform)?'⌘ K':'Ctrl K';
    opener.hidden=false; opener.addEventListener('click',open);
    document.addEventListener('keydown',event=>{
      if ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase()==='k' &&
          !event.isComposing && !document.querySelector('dialog[open]')) {
        event.preventDefault(); open();
      }
    });
    input.addEventListener('input',filter);
    input.addEventListener('keydown',event=>{
      if (event.isComposing || event.keyCode===229 || !filtered.length) return;
      if (event.key==='Enter') { event.preventDefault(); accept(index); }
      else if (event.key==='ArrowDown' || event.key==='ArrowUp') {
        event.preventDefault(); highlight((index+(event.key==='ArrowDown'?1:-1)+filtered.length)%filtered.length,true);
      }
    });
    results.addEventListener('click',event=>{
      const option=event.target.closest('[role=option]');
      if (option) accept(options.indexOf(option));
    });
    dialog.addEventListener('click',event=>{
      if (event.target!==dialog) return;
      const r=dialog.getBoundingClientRect();
      if (event.clientX<r.left || event.clientX>r.right || event.clientY<r.top || event.clientY>r.bottom) dismiss();
    });
    dialog.addEventListener('cancel',event=>{event.preventDefault(); dismiss();});
    dialog.querySelector('form').addEventListener('submit',event=>{event.preventDefault(); dismiss();});
  }
  return {mount};
})();
