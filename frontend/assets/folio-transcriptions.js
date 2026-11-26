const FolioTranscriptions = (() => {
  const fields = {
    signed_on: ['date', ['签约日期','签订日期','签署日期']],
    effect_on: ['date', ['实际生效日期','生效确认日期']],
    valid_until: ['date', ['合同有效期至','合同有效截止日']],
    quantity_agreed: ['quantity', ['约定交付数量','合同交付数量']],
    acceptance_criteria: ['temperature', ['约定验收标准','合同验收标准']],
    payment_stage: ['installment'], payment_term: ['installment'],
  };
  const bodies = {
    date: /^([0-9]{4}) *年 *([0-9]{1,2}) *月 *([0-9]{1,2}) *日$/u,
    quantity: /^([0-9]{1,9}) *(台|套|件)$/u,
    temperature: /^(柜温不高于|柜温不低于) *(-?[0-9]{1,3}(?:\.[0-9]{1,3})?) *(?:℃|°C)$/u,
    installment: /^(合同生效后支付|最终验收合格后支付|质保期满后支付) *([0-9]{1,3}(?:\.[0-9]{1,2})?) *%$/u,
  };
  const stage = /^(?:第[一二两三四五六七八九十0-9]+期|首付款|预付款|进度款|验收款|质保金|尾款)$/u;
  const labelBody = /^([^:：\s]+[:：]) *(.*)$/u;

  function literalMatch(row, fact) {
    const proof = row.transcription, spec = fields[fact.field];
    const native = labelBody.exec(row.quote), quoted = labelBody.exec(fact.quote);
    if (!spec || spec[0] !== proof.form || !native || !quoted || native[1] !== quoted[1] ||
        row.quote === fact.quote && native[2] === fact.value) return false;
    const label = native[1].slice(0,-1);
    if (spec[1] ? !spec[1].includes(label) : !stage.test(label)) return false;
    const tokens = bodies[proof.form].exec(native[2]);
    if (!tokens || ![quoted[2],fact.value].every(value => {
      const other = bodies[proof.form].exec(value);
      return other && other[0] === value && tokens.slice(1).every((t,i) => t === other[i+1]);
    })) return false;
    if (proof.form === 'date') {
      const [y,m,d] = tokens.slice(1).map(Number), day = new Date(0);
      day.setUTCFullYear(y,m-1,d);
      return y > 0 && day.getUTCFullYear() === y && day.getUTCMonth() === m-1 && day.getUTCDate() === d;
    }
    return proof.form !== 'installment' || Number(tokens[2]) > 0 && Number(tokens[2]) <= 100;
  }

  function verified(row, fact, call, doc, page) {
    const proof = row.transcription;
    if (!fact || !row.supported || !fact.source_line?.rects?.length || fact.source_line.text !== row.quote ||
        fact.source_line.number !== row.line || row.facts.length !== 1 || row.facts[0] !== proof.ref ||
        proof.quote !== fact.quote || proof.value !== fact.value || !literalMatch(row,fact)) return false;
    if (proof.basis === 'field_receipt') return Boolean(fieldReceiptOperation(fact,doc,page));
    const check = call.check, ref = /\/f([1-9][0-9]*)$/u.exec(fact.id)?.[1];
    if (proof.basis !== 'visual_check' || fact.status !== 'anchored' || fact.visual_check !== 'clear' ||
        fact.amendment || !ref || !call.response_id || !check?.response_id || call.response_id === check.response_id ||
        fact.response_id !== call.response_id || fact.check_response_id !== check.response_id) return false;
    if (!Array.isArray(check.input) || !Array.isArray(check.output?.checks)) return false;
    const original = call.output?.facts?.[Number(ref)-1];
    const inputs = check.input.filter(r => r.index === ref), votes = check.output.checks.filter(r => r.index === ref);
    return original?.field === fact.field && inputs?.length === 1 && inputs[0].field === fact.label &&
      votes?.length === 1 && votes[0].support === 'clear' &&
      ['value','quote'].every(k => original[k]?.trim() === fact[k] && inputs[0][k]?.trim() === fact[k]);
  }

  function markedSpaces(text, show) {
    const line = el('span','','folio-literal');
    if (!show) { line.textContent=text; return line; }
    for (const segment of text.split(/( +)/u)) {
      line.append(segment.startsWith(' ') ? el('mark','·'.repeat(segment.length)) : document.createTextNode(segment));
    }
    line.setAttribute('aria-label',text);
    return line;
  }

  function reader(rows, openOriginal, selectOriginal, currentSelection) {
    const options = rows.filter(r => r.transcription);
    if (!options.length) return null;
    const details = el('details','','folio-transcripts'), summary = el('summary');
    summary.append(el('span','转录对照'),el('small',String(options.length)));
    let selected=0;
    const previous=action('‹',()=>move(selected-1),'folio-transcript-step');
    const next=action('›',()=>move(selected+1),'folio-transcript-step');
    previous.setAttribute('aria-label','上一处转录'); next.setAttribute('aria-label','下一处转录');
    const position=el('output','','folio-transcript-position');
    const checkbox = el('input'), toggle = el('label','','folio-spaces');
    checkbox.type='checkbox'; toggle.append(checkbox,document.createTextNode('显示空格'));
    const comparison = box('folio-versions'), basis=el('small'), page=el('span');
    const original=action('',()=>openOriginal(options[selected]),'folio-source-link');
    original.append(page,glyph('arrows-angle-expand'));
    const foot=box('folio-transcript-foot',basis,original);
    function show(id) {
      const row = options.find(r => r.id === id);
      if (!row) return;
      selected=options.indexOf(row);
      previous.disabled=selected===0; next.disabled=selected===options.length-1;
      position.textContent=(selected+1)+' / '+options.length;
      position.setAttribute('aria-label','第 '+(selected+1)+' 处，共 '+options.length+' 处转录');
      const proof=row.transcription;
      const entries=[['原件文字层',row.quote],['提取引文',proof.quote],['字段值',proof.value]];
      comparison.replaceChildren(...entries.map(([label,text]) => box('folio-version',el('small',label),markedSpaces(text,checkbox.checked))));
      page.textContent='第 '+row.page+' 页 · 第 '+row.line+' 行';
      original.setAttribute('aria-label','打开转录所据原件，'+page.textContent);
      basis.textContent=proof.basis==='field_receipt'?'人工核图':'已核对两次模型记录';
      details.dataset.folioTranscript=row.id;
    }
    function move(i) {
      if (!options[i]) return;
      show(options[i].id); selectOriginal(options[i].id);
    }
    details.addEventListener('toggle',()=>{
      if (!details.open) return;
      const current=options.findIndex(r=>r.id===currentSelection());
      move(current<0?selected:current);
    });
    checkbox.addEventListener('change',()=>show(options[selected].id));
    details.append(summary,box('folio-transcript-controls',box('folio-transcript-nav',previous,position,next),toggle),comparison,foot);
    show(options[0].id);
    return {details,show};
  }
  return {verified,reader};
})();
