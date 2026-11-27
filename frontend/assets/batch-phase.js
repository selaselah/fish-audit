// A batch installment may qualify before the contract's separate final acceptance.
const BatchPhase = (() => {
  const clean = text => typeof text === 'string' ? text.normalize('NFKC').replace(/\s+/gu, '') : '';
  const printed = fact => fact.source_line.text.replace(/^[^:：]+[:：]\s*/u, '').trim();
  const unit = fact => fact.unit || fact.doc;
  const label = proof => proof.index ? '第 ' + proof.index + ' 批验收' : '批次验收';
  function sameIds(left, right) {
    return Array.isArray(left) && Array.isArray(right) && left.length === right.length &&
      new Set(left).size === left.length && left.every(id => right.includes(id));
  }
  function sameOrdinal(text,index) {
    const digits = '零一二三四五六七八九', tens = Math.floor(index / 10), ones = index % 10;
    const ordinal = tens ? (tens === 1 ? '' : digits[tens]) + '十' + (ones ? digits[ones] : '') : digits[ones];
    return [String(index),ordinal,ordinal?.replace(/二/g,'两')].includes(text);
  }
  function ordinal(text) {
    if (typeof text!=='string') return null;
    if (/^[1-9][0-9]?$/u.test(text)) return Number(text);
    const digits='零一二三四五六七八九', normalized=text.replaceAll('两','二');
    if (/^[一二三四五六七八九]$/u.test(normalized)) return digits.indexOf(normalized);
    const tens=/^([一二三四五六七八九]?)十([一二三四五六七八九]?)$/u.exec(normalized);
    return tens ? (tens[1]?digits.indexOf(tens[1]):1)*10+(tens[2]?digits.indexOf(tens[2]):0) : null;
  }
  function batchPrefix(text, index) {
    const refs = [...clean(text).matchAll(/第([\d零一二两三四五六七八九十]+)批/gu)];
    return refs.length === 1 && refs[0].index === 0 && sameOrdinal(refs[0][1],index);
  }
  function resolve(phase, acceptance, graph, pages) {
    const stage = phase?.stage, index = stage?.batch_index;
    if (phase?.rule !== 'H04' || (index == null && !/^第[\d零一二两三四五六七八九十]+批/u.test(clean(stage?.clause)))) return null;
    const validIndex = Number.isSafeInteger(index) && index >= 1 && index <= 99;
    const pending = {index: validIndex ? index : null, status: 'missing', verified: false};
    const ledger = acceptance?.rule === 'H02' && acceptance.batch_acceptance;
    if (!validIndex || !Array.isArray(ledger?.batches) || !Array.isArray(ledger.records)) return pending;
    const matches = ledger.batches.filter(batch => batch.index === index);
    if (matches.length !== 1) return pending;
    const batch = matches[0];
    if (![phase,acceptance,batch].every(f=>Array.isArray(f.evidence) && Array.isArray(f.scope))) return pending;
    const stageRows=PerformanceIndex.originals(phase,graph), acceptedRows=PerformanceIndex.originals(acceptance,graph);
    const lines=rows=>new Map(rows.filter(s=>s.line).map(s=>[s.fact.id,s.fact]));
    const stages=lines(stageRows), accepted=lines(acceptedRows);
    const clause = stages.get(stage.clause_ref), allocation = stages.get(batch.clause_ref);
    const kinds = graph.documents_by_kind || {};
    if (clause?.field !== 'payment_stage' || allocation?.field !== 'delivery_batch' ||
        unit(clause) !== unit(allocation) || !kinds.contract?.includes(unit(clause)) || !accepted.has(allocation.id) ||
        clean(clause.source_line.text) !== clean(stage.name + ':' + stage.clause) || !batchPrefix(printed(clause), index) ||
        allocation.source_line.text !== batch.quote || !batchPrefix(printed(allocation), index)) return pending;
    if (!Array.isArray(batch.evidence) || !batch.evidence.includes(allocation.id) ||
        !batch.evidence.every(id => phase.evidence.includes(id) && acceptance.evidence.includes(id)) ||
        !['ok', 'risk', 'issue', 'missing'].includes(batch.status) || !batch.detail) return pending;
    const links = PerformanceIndex.fieldLinks(graph);
    if (!batch.evidence.every(id => links.has(id + ' finding/' + phase.id) && links.has(id + ' finding/' + acceptance.id))) return pending;
    const rows = ledger.records.filter(row => row.index === index && row.role !== 'final');
    if (!sameIds(batch.records, rows.map(row => row.unit))) return pending;
    const evidence = new Set(batch.evidence), records = [];
    let quality = null, standard = null;
    const changed=Boolean(acceptance.quality_change && !acceptance.quality_change.quantity || rows.some(r=>r.standard));
    if (changed && rows.some(r=>ledger.records.filter(other=>other.unit===r.unit).length!==1 ||
        ledger.batches.filter(other=>other.records?.includes(r.unit)).length!==1)) return pending;
    const receipts = [...(kinds.acceptance || []), ...(kinds.reinspection || [])];
    for (const row of rows) {
      const scope = stages.get(row.scope_ref);
      if (scope?.field !== 'acceptance_scope' || unit(scope) !== row.unit || !accepted.has(scope.id) ||
          !batch.scope?.includes(row.unit) || !phase.scope?.includes(row.unit) || !evidence.has(scope.id) ||
          !receipts.includes(row.unit) || !batchPrefix(printed(scope), index)) return pending;
      const fields = [...stages.values()].filter(f => unit(f) === row.unit && evidence.has(f.id) &&
        accepted.has(f.id) && row.evidence?.includes(f.id));
      const dates = fields.filter(f => f.field === 'accepted_on' && row.date && PhaseEvidence.dateOn(f) === row.date);
      const numbers = fields.filter(f => f.field === 'acceptance_number' && row.number &&
        (!row.number_ref || f.id === row.number_ref) && clean(printed(f)) === clean(row.number));
      if (changed && rows.length===1) {
        standard=BatchStandard.resolve({phase,acceptance,graph,pages,batch,row,clause,allocation,stages,accepted,stageRows,acceptedRows});
      }
      const date=changed?standard?.date:dates.length===1?dates[0]:null;
      records.push({scope, number: numbers.length === 1 ? numbers[0] : null, date});
      if (!changed && batch.status === 'issue' && row.status === 'issue' && rows.length === 1) {
        const criteria = [...stages.values()].filter(f => f.field === 'acceptance_criteria' && unit(f) === unit(clause) &&
          evidence.has(f.id) && accepted.has(f.id));
        const readings = fields.filter(f => f.field === 'measured_result');
        if (criteria.length === 1 && readings.length === 1 && [criteria[0], readings[0]].every(f => clean(printed(f)) === clean(f.value)) &&
            [row.detail, batch.detail, phase.detail].every(detail => typeof detail === 'string' &&
              PerformanceIndex.issuedLimitBreach(detail, criteria[0], readings[0]))) quality = {criterion: criteria[0], reading: readings[0]};
      }
    }
    function edge(type, from, to, refs) {
      return graph.edges.some(e => e.type === type && e.from === from && e.to === to && sameIds(e.evidence, refs));
    }
    if (batch.status === 'ok') {
      const receipt = records[0];
      const facts = graphIndex(graph).facts;
      if (batch.evidence.some(id => facts.has(id) && !(stages.has(id) && accepted.has(id)))) return pending;
      if (!ledger.contract_clear || !ledger.independent || records.length !== 1 || rows[0].status !== 'ok' ||
          !receipt.date || batch.date !== PhaseEvidence.dateOn(receipt.date) || stage.batch_date !== batch.date ||
          !edge('delivery_batch_acceptance', allocation.id, receipt.scope.id, batch.evidence) ||
          (phase.status === 'ok' && !edge('batch_payment_basis', clause.id, receipt.scope.id, phase.evidence))) return pending;
    } else if (phase.status === 'ok') return pending;
    // An uploaded packet can still be awaiting allocation to a batch.
    const classified = new Set(Object.values(kinds).flat());
    const classifiedDocs = new Set(graph.facts.filter(f => classified.has(unit(f))).map(f => f.doc));
    const accountedFor = graph.documents.every(d => classified.has(d.id) || classifiedDocs.has(d.id)) &&
      receipts.every(id => ledger.records.some(r => r.unit === id && !r.scope_unclear &&
        ((Number.isSafeInteger(r.index) && r.index > 0) || r.role === 'final')));
    const missingReceipt = !records.length && batch.status === 'missing' && accountedFor &&
      batch.detail.includes('缺少对应本批的验收原件');
    const uncertain=changed && (!standard || standard.state==='pending' && rows[0]?.standard?.state!=='pending' ||
      batch.status==='ok' && !standard.chosen);
    return {index, status:uncertain?'missing':batch.status, verified:true,
      detail:uncertain?'本批适用标准的原件关系待核。':batch.detail, clause, allocation, records, missingReceipt, quality, standard};
  }

  function panel(proof, stage) {
    const root = box('batch-phase-proof');
    root.dataset.batch = proof.index ?? ''; root.dataset.verified = String(proof.verified);
    root.append(box('batch-phase-heading', el('h4', label(proof)), tag(proof.status)));
    if (!proof.verified) {
      root.append(el('p', '本期条款与批次原件的引用关系待核。'));
      return root;
    }
    function source(title, fact, note, open) {
      const button = action('', open || (() => openPage(fact.doc, fact.page, fact.id)), 'batch-phase-source');
      const place = '第 ' + fact.page + ' 页 · 第 ' + fact.source_line.number + ' 行';
      button.dataset.fact = fact.id;
      button.title = fact.name + ' · ' + place;
      button.setAttribute('aria-haspopup', 'dialog'); button.setAttribute('aria-controls', 'page-dialog');
      const caption=el('small',title);
      if (note) caption.append(el('em',note));
      button.append(caption, el('strong', printed(fact)), el('span', place), glyph('arrows-angle-expand'));
      return button;
    }
    function file(name, ...rows) {
      return box('batch-phase-file', box('batch-phase-filename', glyph('file-earmark-text'), el('strong', name)), ...rows);
    }
    const contract = file(proof.clause.name, source('付款条件', proof.clause), source('交付约定', proof.allocation));
    const receipts = box('batch-phase-receipts');
    for (const record of proof.records) {
      const rows = [source('验收范围', record.scope)];
      if (record.number) rows.push(source('验收单号', record.number));
      if (record.date) rows.push(source('单据日期', record.date));
      receipts.append(file(record.scope.name, ...rows));
    }
    if (!proof.records.length) {
      const note = proof.missingReceipt ? '待补第 ' + proof.index + ' 批验收单' : '现有材料的批次归属待核';
      const empty = box('batch-phase-empty', glyph('inboxes'), el('strong', note));
      if (proof.missingReceipt && canReviewCurrentPaper()) {
        empty.append(action('拟补件意见', () => draftSupplement('请补交与《' + proof.clause.name + '》第 ' +
          proof.clause.page + ' 页第 ' + proof.clause.source_line.number + ' 行「' + stage.clause + '」对应的第 ' +
          proof.index + ' 批验收单，供核对' + stage.name + '付款条件。'), 'text-button'));
      }
      receipts.append(empty);
    }
    const modes = box('batch-phase-modes');
    modes.setAttribute('role', 'group'); modes.setAttribute('aria-label', label(proof) + '凭据');
    const views = [['contract', '合同约定', contract], ['receipt', '验收凭证', receipts]];
    if (proof.standard) views.push(['standard','标准核对',BatchStandard.panel(proof.standard,source)]);
    if (proof.quality) {
      const {criterion, reading} = proof.quality;
      const comparison = box('batch-phase-comparison', source('合同标准', criterion), source('本批实测', reading));
      views.push(['quality', '实测对照', comparison]);
    }
    function select(key) {
      for (const [id,, view] of views) {
        view.hidden = id !== key;
        modes.querySelector('[data-source="' + id + '"]').setAttribute('aria-pressed', String(id === key));
      }
    }
    for (const [i, [id, title]] of views.entries()) {
      const button = action(title, () => select(id));
      button.addEventListener('keydown', event => {
        const total = views.length;
        const next = {ArrowRight:(i + 1) % total, ArrowLeft:(i + total - 1) % total, Home:0, End:total - 1}[event.key];
        if (next === undefined) return;
        event.preventDefault(); select(views[next][0]); modes.children[next].focus();
      });
      button.dataset.source = id; modes.append(button);
    }
    root.append(modes, ...views.map(view => view[2]));
    if (proof.status !== 'ok') {
      const reason = proof.detail.trim(), first = reason.indexOf('。') + 1 || reason.length;
      if (proof.records.length && !proof.quality && !proof.standard) root.append(el('p', reason.slice(0, first), 'batch-phase-reason'));
      if (proof.standard || proof.quality || reason.length > first || (!proof.missingReceipt && !proof.records.length))
        root.append(fold('本批检查依据', el('p', reason)));
    }
    select(proof.standard?'standard':proof.quality?'quality':'receipt');
    return root;
  }
  return {resolve, panel, label, batchPrefix, sameOrdinal, ordinal};
})();
