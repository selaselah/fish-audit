const WarrantyRegisterEvidence = (() => {
  const format = 'contract-warranty-release-v5';
  const norm = text => typeof text==='string' ? text.normalize('NFKC').trim() : '';
  const unique = items => items?.length===1 ? items[0] : null;
  const sameRefs = (a,b) => Array.isArray(a) && Array.isArray(b) && a.length===b.length &&
    new Set(a).size===a.length && new Set(b).size===b.length && a.every(ref=>b.includes(ref));
  const rects = r => Array.isArray(r) && r.length===4 && r.every(n=>Number.isFinite(n) && n>=0 && n<=1) && r[0]<r[2] && r[1]<r[3];

  function resolve(report,phase,payments) {
    const graph=report.graph, ledger=graph.warranty_sources, check=phase.warranty_check;
    if (!Array.isArray(check?.tickets) || !check.tickets.length || !phase.stage || ledger?.format!==format || report.policy?.warranty_checks!==format ||
        unique(report.findings.filter(f=>f.rule==='H04' && f.warranty_check))!==phase) return null;
    const claims=report.findings.filter(f=>f.rule==='H07' && f.warranty_difference);
    if (!claims.length) return null;
    const pages=Array.isArray(ledger.register_pages)?ledger.register_pages:[];
    const index=graphIndex(graph);
    const support=new Map(), documents=new Map();
    for (const edge of graph.edges) {
      if (edge.type!=='supports_result') continue;
      const key=edge.to+'|'+edge.from;
      support.set(key,support.has(key)?null:edge);
    }
    const supports=(f,ref)=>Array.isArray(f.evidence) && f.evidence.includes(ref) &&
      sameRefs(support.get('finding/'+f.id+'|'+ref)?.evidence,[ref]);
    function field(f,ref,name,unit) {
      if (!ref || !Array.isArray(f.scope) || !f.scope.includes(unit) || !supports(f,ref)) return null;
      const fact=unique(graph.facts.filter(row=>row.id===ref)), loc=fact?.source_line;
      if (!fact || fact.field!==name || (fact.unit || fact.doc)!==unit || fact.doc!==unit ||
          !['anchored','confirmed'].includes(fact.status) || !Number.isSafeInteger(loc?.number) || loc.number<1 ||
          !Array.isArray(loc.rects) || !loc.rects.length || !loc.rects.every(rects)) return null;
      const pageId=unit+'/p'+fact.page;
      if (!documents.has(pageId)) {
        const call=unique(report.calls?.pages?.filter(p=>p.doc===unit && p.page===fact.page));
        documents.set(pageId,{call,doc:call && issuedPageDocument(graph,call)});
      }
      const {doc,call}=documents.get(pageId);
      const observation=unique(graph.nodes.filter(n=>n.id===ref));
      const recorded=unique(graph.edges.filter(e=>e.type==='records' && e.to===ref));
      if (!doc || doc.sha256!==fact.source_sha256 || doc.name!==fact.name || !ref.startsWith(pageId+'/') ||
          observation?.type!=='observation' || observation.status!==fact.status || observation.label!==fact.label ||
          recorded?.from!==pageId || !sameRefs(recorded.evidence,[ref]) || call?.page_sha256!==fact.page_sha256 ||
          !call.response_id || !call.check?.response_id || (fact.response_id && fact.response_id!==call.response_id) ||
          (fact.check_response_id && fact.check_response_id!==call.check.response_id)) return null;
      const text=norm(loc.text), split=text.indexOf(':'), value=text.slice(split+1).trim();
      const printedDate=name==='warranty_release' && check.certificate && Object.hasOwn(check.certificate,'date') && WarrantyDates.issued(phase,graph)?.fact===fact;
      if (split<1 || !value || !printedDate && (norm(fact.quote)!==text || ![text,value].includes(norm(fact.value)))) return null;
      return {ref,fact,page:fact.page,line:loc.number,quote:loc.text,value:loc.text.slice(loc.text.search(/[:：]/u)+1).trim()};
    }
    function record(unit,role) { return unique(pages.filter(p=>p.doc===unit && p.role===role && p.bounded && p.text_only)); }
    const release=unique(pages.filter(p=>p.role==='warranty')), contract=unique(pages.filter(p=>p.role==='contract'));
    function sheetField(f,sheet,name,ref) {
      const row=sheet && field(f,ref,name,sheet.doc);
      if (!row || row.page!==sheet.page || !sameRefs(sheet.refs?.[name],[ref])) return null;
      if (sheet.role==='warranty_ticket' || ['warranty_defects','warranty_release','warranty_condition'].includes(name)) {
        const entry=unique(ledger.lines?.filter(l=>l.unit===sheet.doc && l.doc===sheet.doc && l.page===sheet.page &&
          l.facts?.includes(ref) && (sheet.role==='warranty_ticket'?l.kind==='ticket_line' && l.field===name:l.kind===name)));
        if (!entry || entry.line!==row.line || entry.quote!==row.quote) return null;
      }
      return row;
    }
    const certificate=sheetField(phase,release,'warranty_defects',check.defect_ref);
    const confirmed=sheetField(phase,release,'warranty_release',check.confirmation_ref);
    const inline=check.condition_ref===phase.stage.clause_ref;
    const condition=inline ? field(phase,check.condition_ref,'payment_stage',contract?.doc) :
      sheetField(phase,contract,'warranty_condition',check.condition_ref);
    function proven(f,t,part) {
      const d=f.warranty_difference, refs=d.refs;
      const sheet=record(t.unit,'warranty_ticket'), ruleNode=unique(graph.nodes.filter(n=>n.id==='finding/'+f.id));
      if (!/^[a-f0-9]{64}$/.test(report.policy.code_sha256?.['warranty_register.py']) ||
          !sheet || !release || !contract || !refs || !certificate || !confirmed || !condition ||
          !check.requires_defect_clearance || !contract.refs?.clause?.includes(phase.stage.clause_ref) ||
          !pages.every(p=>p.bounded && p.text_only) || !sameRefs(pages.map(p=>p.doc+'/p'+p.page),graph.nodes.filter(n=>n.type==='page').map(n=>n.id)) ||
          f.status!=='risk' || ruleNode?.type!=='finding' || ruleNode.status!==f.status || ruleNode.detail!==f.detail ||
          !sameRefs(f.scope,[contract.doc,release.doc,t.unit]) || d.state!=='record_difference' || d.release_unit!==release.doc ||
          !t.linked || t.identity_conflicts?.length || !part.number || !part.fault || !part.reported || !part.state ||
          ![refs.defects,refs.confirmation,refs.condition,refs.ticket_id,refs.fault,refs.reported_on,refs.ticket_state].every((ref,i)=>
            ref===[certificate,confirmed,condition,part.number,part.fault,part.reported,part.state][i].ref) ||
          d.number!==part.number.value || t.number!==d.number || t.fault!==part.fault.value ||
          d.printed_state!==part.state.value || t.printed_state!==d.printed_state ||
          !['待维修','未关闭','维修中','待复修','处理中'].includes(d.printed_state) ||
          !['无未关闭缺陷','无未结质量问题','无未解决质量问题'].includes(norm(certificate.value).replace(/。$/u,'')) ||
          part.closed || part.signer || t.refs.warranty_closed_on || t.refs.warranty_closed_by) return false;
      const reported=PhaseEvidence.dateOn(part.reported.fact);
      const confirmedDay=check.certificate && Object.hasOwn(check.certificate,'date')?WarrantyDates.issued(phase,graph)?.iso:PhaseEvidence.dateOn(confirmed.fact);
      if (!reported || !confirmedDay || d.reported_on!==reported || t.reported_on!==reported ||
          d.confirmed_on!==confirmedDay || WarrantyTimeline.statedDate(check)!==confirmedDay || reported>=confirmedDay ||
          !check.at_submission?.as_of || confirmedDay>check.at_submission.as_of) return false;
      for (const name of ['contract_id','buyer','seller','subject']) {
        const identities=[contract,release,sheet].map(p=>sheetField(f,p,name,unique(p.refs?.[name])));
        if (identities.some(row=>!row) || new Set(identities.map(row=>norm(row.value))).size!==1) return false;
      }
      const signer=sheetField(f,release,'acceptance_signer',unique(release.refs?.acceptance_signer))?.fact;
      const att=signer?.attestation, source=att?.source_check;
      if (signer?.status!=='confirmed' || att?.decision!=='confirm' || source?.case_id!==report.case_id ||
          source.doc!==signer.doc || source.page!==signer.page || source.original_sha256!==signer.source_sha256 ||
          source.page_sha256!==signer.page_sha256 || att.fact!==signer.id) return false;
      const edge=unique(graph.edges.filter(e=>e.type==='warranty_record_difference' && e.to===part.state.ref));
      const procedure=unique(graph.edges.filter(e=>e.type==='procedure_result' && e.to==='finding/'+f.id));
      return procedure?.from==='control/H07' && sameRefs(procedure.evidence,f.evidence) &&
        edge?.from===certificate.ref && sameRefs(edge.evidence,f.evidence) &&
        [phase.stage.clause_ref,...Object.values(refs),signer.id].every(ref=>f.evidence.includes(ref)) && f.evidence.every(ref=>supports(f,ref));
    }
    const tickets=check.tickets.map(t=>{
      const sheet=record(t.unit,'warranty_ticket');
      const row=name=>t.evidence?.includes(t.refs?.[name]) ? sheetField(phase,sheet,name,t.refs[name]) : null;
      const part={key:t.unit,number:row('warranty_ticket_id'),fault:row('warranty_fault'),state:row('warranty_ticket_state'),
        reported:row('warranty_reported_on'),closed:row('warranty_closed_on'),signer:row('warranty_closed_by')};
      const matches=claims.filter(f=>f.warranty_difference.ticket_unit===t.unit), claim=unique(matches);
      part.difference=Boolean(claim && proven(claim,t,part));
      part.review=Boolean(matches.length && !part.difference);
      if (part.difference) part.finding=claim.id;
      return part;
    });
    const payment=unique(payments.filter(p=>p.rule==='H05' && p.warranty_payment && PhaseEvidence.sameStage(phase.stage,p.stage)));
    const dateRef=unique(payment?.warranty_payment.date_refs), bankDoc=index.facts.get(dateRef)?.doc;
    const paid=payment && graph.documents_by_kind?.bank_receipt?.includes(bankDoc) && field(payment,dateRef,'paid_on',bankDoc);
    return {tickets,certificate,confirmed,condition,paid,phaseName:phase.stage.name,phaseStatus:phase.status,paymentStatus:payment?.status};
  }
  function panel(phase,payments,report) {
    if (!report || report!==state.bundle?.report || !report.findings.includes(phase) ||
        !payments.every(p=>report.findings.includes(p))) return null;
    const model=resolve(report,phase,payments);
    if (!model) return null;
    const bundle=state.bundle, workspace=Team.current?.id || null;
    function current() {
      const route=Team.route(), revisions=route.params.getAll('rev');
      return state.bundle===bundle && state.detail?.id===report.case_id && state.detail?.can_review!==false &&
        state.detail.workspace===(workspace || 'local') && workspace===(Team.current?.id || null) && route.id===workspace &&
        route.page==='case/'+report.case_id &&
        (!revisions.length || revisions.length===1 && Number(revisions[0])===bundle.rev) && (!state.pinned || state.pinned===bundle.rev);
    }
    function source(row,label,preview) {
      const control=action('',()=>{ if (current()) openPage(row.fact.doc,row.page,row.ref); });
      control.setAttribute('aria-haspopup','dialog'); control.setAttribute('aria-controls','page-dialog');
      return WarrantyRegister.source(control,row,label,preview && (async()=>current() && EvidenceCompare.lineExcerpt(row.fact,graphIndex(report.graph))));
    }
    function compare(ticket) {
      const change=report.findings.find(f=>f.id===ticket.finding);
      return action('双页对照',()=>{
        if (current()) showFindingPath(change,true,'warranty-record-'+ticket.key);
      },'wr-compare');
    }
    function permalink(ticket) {
      const params=new URLSearchParams({rev:bundle.rev,view:'warranty-register',ticket:ticket.key});
      const link=Team.paperLink('固定链接',report.case_id,'wr-permalink',params);
      link.setAttribute('aria-label','本版所选工单的固定链接，'+(ticket.number?.value || ticket.key));
      return link;
    }
    return WarrantyRegister.render(model,'warranty-register-'+phase.id,source,'h4',compare,permalink);
  }
  function pair(finding,report) {
    const phase=unique(report?.findings.filter(f=>f.rule==='H04' && f.warranty_check));
    if (!phase || !report.findings.includes(finding)) return null;
    const model=resolve(report,phase,[]);
    const ticket=model?.tickets.find(t=>t.finding===finding.id);
    return ticket && {key:'warranty-record-'+ticket.key,label:'期满声明与工单状态',left:model.certificate.fact,right:ticket.state.fact};
  }
  function revealTab(tab) {
    const phase=tab?.closest('[data-phase-finding]');
    if (!phase) return;
    document.querySelector('[data-phase-choice="'+CSS.escape(phase.dataset.phaseFinding)+'"]')?.click();
    phase.querySelector('[data-mode="tickets"].proof-mode')?.click();
    if (tab.hidden) phase.querySelector('.wr-filters button')?.click();
    tab.click(); revealPaperTarget(tab);
  }
  function jump(finding,label='核对两份记载') {
    const bundle=state.bundle;
    if (!bundle || !pair(finding,bundle.report)) return null;
    return action(label,()=>{
      if (state.bundle!==bundle || state.detail?.id!==bundle.report.case_id || state.detail.can_review===false) return;
      revealTab(document.querySelector('[data-difference-finding="'+CSS.escape(finding.id)+'"]'));
    },'text-button');
  }
  function locate(overview,params) {
    if (!overview) return;
    const root=overview.querySelector('.warranty-register');
    const tickets=params.getAll('ticket');
    const tab=tickets.length===0 ? root?.querySelector('.wr-row[aria-selected=true]') :
      tickets.length===1 && root?.querySelector('.wr-row[data-ticket="'+CSS.escape(tickets[0])+'"]');
    if (tab) { revealTab(tab); return; }
    const message=el('p',root?'本版没有所选工单。':'本版未收录质保工单记载差异对照。','note');
    message.setAttribute('role','status'); message.tabIndex=-1; overview.prepend(message); revealPaperTarget(message);
  }
  return {panel,resolve,pair,jump,locate};
})();
