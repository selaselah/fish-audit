const PublicWarrantyRegister = (() => {
  const sha = /^[a-f0-9]{64}$/;
  const units = {contract:'d04',certificate:'d02',open:'d01',closed:'d03',bank:'d05'};
  function require(value) { if (!value) throw new Error('Warranty sample evidence mismatch'); }
  function published(sample) {
    const {phase,payment,comparison,documents} = sample;
    require(sample.case_id==='920ea04963ef4f68905ff87533133fd4' && sample.rev===11 && sha.test(sample.report_sha256) &&
      sample.rule_version==='2026.11.27.07' && phase.id==='H04-7' && payment.id==='H05-8' && phase.stage==='第三期' &&
      payment.stage===phase.stage && phase.status==='missing' && payment.status==='missing' && !phase.calendar_end &&
      /^H07-[1-9]\d*$/.test(comparison.id) && comparison.status==='risk' && comparison.state==='record_difference' &&
      comparison.ticket_unit===units.open && comparison.release_unit===units.certificate);
    const pages = {};
    for (const [role,unit] of Object.entries(units)) {
      const doc = documents[role], fields = new Map(), locations = new Set();
      require(doc.page===1 && doc.pdf==='/showcase/warranty-register-'+role+'.pdf' &&
        doc.image==='/assets/warranty-register-'+role+'.jpg' && sha.test(doc.source_sha256) && sha.test(doc.page_sha256));
      for (const row of doc.lines) {
        require(!fields.has(row.field) && !locations.has(row.line) && row.ref.startsWith(unit+'/p1/') &&
          /\/p1\/(?:[ft][1-9]\d*|h[a-f0-9]{12})$/.test(row.ref) && Number.isSafeInteger(row.line) && row.line>0 &&
          row.quote===row.label+'：'+row.value && row.value && Array.isArray(row.rects) && row.rects.length &&
          row.rects.every(r=>Array.isArray(r) && r.length===4 && r.every(n=>Number.isFinite(n) && n>=0 && n<=1) && r[0]<r[2] && r[1]<r[3]));
        const bounds = [0,1,2,3].map((j)=>Math[j<2?'min':'max'](...row.rects.map(r=>r[j])));
        require(row.rect?.length===4 && bounds.every((n,j)=>n===row.rect[j]));
        fields.set(row.field,{...row,doc,page:doc.page}); locations.add(row.line);
      }
      pages[role] = fields;
    }
    const claim = comparison.refs;
    function match(role,field,ref) {
      const row = pages[role].get(field); require(row && row.ref===ref); return row;
    }
    const certificate = match('certificate','warranty_defects',claim.defects);
    const confirmed = match('certificate','warranty_release',claim.confirmation);
    const condition = match('contract','warranty_condition',claim.condition);
    const tickets = ['open','closed'].map(role=>{
      const binding = comparison.tickets[role]; require(binding.unit===units[role]);
      const field = name=>match(role,name,binding.refs[name]);
      const number=field('warranty_ticket_id'), fault=field('warranty_fault'), state=field('warranty_ticket_state'), reported=field('warranty_reported_on');
      const difference=role==='open';
      if (difference) require([number.ref,fault.ref,state.ref,reported.ref].every((ref,i)=>
        ref===claim[['ticket_id','fault','ticket_state','reported_on'][i]]));
      return {key:binding.unit,number,fault,state,reported,difference,
        closed:difference?null:field('warranty_closed_on'),signer:difference?null:field('warranty_closed_by')};
    });
    const paid = pages.bank.get('paid_on');
    require(paid && pages.bank.get('payment_designation')?.value===phase.stage);
    return {tickets,certificate,confirmed,condition,paid,phaseName:phase.stage,phaseStatus:phase.status,paymentStatus:payment.status};
  }
  function source(row,label,preview) {
    const load = preview && (()=>VerifiedSamplePage.load(row.doc).then(image=>VerifiedSamplePage.crop(image,row.rect)));
    return WarrantyRegister.source(VerifiedSamplePage.link(row),row,label,load);
  }
  let busy = false;
  async function open() {
    const slot = document.getElementById('payment-warranty-register');
    if (slot.dataset.revision || busy) return;
    const focus = slot.querySelector('.standard-retry')===document.activeElement;
    busy = true; slot.setAttribute('aria-busy','true');
    try {
      const integrity = slot.dataset.integrity;
      require(/^sha256-[A-Za-z0-9+/]{43}=$/.test(integrity));
      const response = await fetch('/assets/warranty-register-sample.json',{integrity});
      require(response.ok);
      const sample = await response.json();
      const view = WarrantyRegister.render(published(sample),'public-warranty-register',source,'h3');
      slot.replaceChildren(view); slot.dataset.revision = sample.rev;
      if (!slot.hidden && !slot.closest('[role=tabpanel]').hidden) {
        document.getElementById('payment-version').textContent='合成案例 · R'+sample.rev;
        if (focus) view.querySelector('[aria-selected=true]').focus({preventScroll:true});
      }
    } catch {
      const fallback = slot.querySelector('.period-fallback');
      if (fallback && !fallback.querySelector('button')) {
        const retry=document.createElement('button'), notice=document.createElement('span');
        notice.setAttribute('role','status'); notice.className='standard-load-status'; notice.textContent='工单对照暂未载入';
        retry.type='button'; retry.className='standard-retry'; retry.textContent='重新载入'; retry.addEventListener('click',open);
        fallback.append(notice,retry);
      }
    } finally { busy=false; slot.setAttribute('aria-busy','false'); }
  }
  return {open};
})();
