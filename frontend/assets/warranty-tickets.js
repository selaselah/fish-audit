// Read the two original documents attached to this issued warranty finding.
const WarrantyTickets = (() => {
  const plain=value=>String(value ?? '').normalize('NFKC').trim();
  const days=(later,earlier)=>(Date.parse(later)-Date.parse(earlier))/86400000;
  const titles={scope:'工单范围待核',identity:'工单归属待核',number:'工单编号待核',period:'工单适用期间待核',
    future:'工单列有提交后的日期',pending:'工单关闭依据待核',stated_closed:'工单列有关闭记录，签发待核'};
  const value=f=>f?plain(f.source_line.text).split(':').slice(1).join(':').trim():'';
  const supports=(index,finding,ref)=>Boolean(ref && finding.evidence.includes(ref) && index.supports.get('finding/'+finding.id)?.has(ref));
  function printedFact(index,finding,ref,field) {
    const f=index.facts.get(ref), line=f?.source_line;
    if (!line?.rects?.length || !['anchored','confirmed'].includes(f.status) || f.field!==field ||
        !finding.scope.includes(f.unit || f.doc) || !supports(index,finding,ref) || plain(line.text)!==plain(f.quote)) return null;
    const whole=plain(line.text);
    return whole.indexOf(':')>0 && [whole,value(f)].includes(plain(f.value))?f:null;
  }
  function ticketFact(index,finding,ledger,t,key) {
    const f=printedFact(index,finding,t.refs[key],key);
    if (!f || (f.unit || f.doc)!==t.unit || !t.evidence.includes(f.id)) return null;
    return ledger.lines.some(l=>l.kind==='ticket_line' && l.field===key && l.unit===t.unit && l.doc===f.doc &&
      l.page===f.page && l.line===f.source_line.number && l.quote===f.source_line.text && l.facts.includes(f.id))?f:null;
  }
  function linkedState(index,graph,finding,t,state) {
    if (!state || !t.linked) return false;
    const w=finding.warranty_check, clause=finding.stage.clause_ref, refs=[clause,state.id,w.confirmation_ref,w.condition_ref];
    return graph.edges.some(e=>e.type==='warranty_ticket_comparison' && e.from===clause && e.to===state.id &&
      refs.every(ref=>supports(index,finding,ref) && e.evidence.includes(ref)));
  }
  function pairs(finding,graph) {
    const w=finding.warranty_check, ledger=graph.warranty_sources;
    if (!w?.tickets || !['contract-warranty-release-v3','contract-warranty-release-v4','contract-warranty-release-v5'].includes(ledger?.format)) return [];
    const index=graphIndex(graph), result=[];
    function fact(ref,field,units) {
      const f=printedFact(index,finding,ref,field);
      return f && units?.includes(f.unit || f.doc)?f:null;
    }
    for (const t of w.tickets) {
      const add=(role,label,left,right)=>{
        if (left && right && left.id!==right.id) result.push({key:'warranty-'+role+'-'+t.unit,label:(w.tickets.length>1?(t.number || '工单')+' · ':'')+label,left,right,unit:t.unit,role});
      };
      const item=key=>ticketFact(index,finding,ledger,t,key);
      for (const p of t.identity_conflicts || []) {
        const left=fact(p.contract_ref,p.field,graph.documents_by_kind.contract), right=item(p.field);
        if (left && right?.id===p.ticket_ref && value(left)!==value(right)) add('identity-'+p.field,'核对'+left.label,left,right);
      }
      const state=item('warranty_ticket_state');
      if (!linkedState(index,graph,finding,t,state)) continue;
      const other=(ref,field)=>fact(ref,field,graph.documents_by_kind.warranty);
      add('state','工单与期满记录',other(w.defect_ref,'warranty_defects'),state);
      const closed=item('warranty_closed_on'), cert=other(w.confirmation_ref,'warranty_release');
      if (closed && PhaseEvidence.dateOn(closed)===t.closed_on) {
        if (cert && PhaseEvidence.dateOn(cert)===WarrantyTimeline.statedDate(w)) add('dates',w.certificate?'两单所列日期':'关闭与期满确认日期',cert,closed);
        const bank=finding.warranty_payment;
        if (bank?.date_refs.length===1) {
          const paid=fact(bank.date_refs[0],'paid_on',graph.documents_by_kind.bank_receipt);
          if (paid && PhaseEvidence.dateOn(paid)===bank.paid_on) add('payment','回单与关闭日期',paid,closed);
        }
      }
    }
    return result;
  }
  function panel(phase,payments,graph) {
    const entry=phase.warranty_check, stored=entry?.tickets, ledger=graph.warranty_sources;
    if (!stored?.length || !['contract-warranty-release-v3','contract-warranty-release-v4','contract-warranty-release-v5'].includes(ledger?.format)) return null;
    const index=graphIndex(graph), within=ref=>supports(index,phase,ref);
    function paper(ref,field,kind) {
      const f=printedFact(index,phase,ref,field);
      return f && ledger.lines.some(l=>l.kind===kind && l.doc===f.doc && l.page===f.page && l.line===f.source_line.number &&
        l.quote===f.source_line.text && l.facts.includes(ref))?f:null;
    }
    const defects=paper(entry.defect_ref,'warranty_defects','warranty_defects');
    const cert=paper(entry.confirmation_ref,'warranty_release','warranty_release');
    const stated=WarrantyTimeline.statedDate(entry);
    const confirmDay=cert && PhaseEvidence.dateOn(cert)===stated?stated:null;
    const bankDates=payments.flatMap(p=>{
      const bank=p.warranty_payment;
      if (!bank || p.warranty_check?.at_submission?.as_of!==entry.at_submission?.as_of) return [];
      const found=bank.date_refs.map(id=>printedFact(index,p,id,'paid_on')).filter(f=>f && PhaseEvidence.dateOn(f)===bank.paid_on);
      return found.length===1?[{date:bank.paid_on,fact:found[0]}]:[];
    });
    const tickets=stored.filter(r=>phase.scope.includes(r.unit) && entry.scope.includes(r.unit) &&
      ledger.pages.some(p=>p.ticket && p.unit===r.unit && within(p.doc+'/p'+p.page)));
    if (!tickets.length) return null;
    const line=(t,key)=>ticketFact(index,phase,ledger,t,key);
    function link(label,f,cls) {
      const btn=action('',()=>openPage(f.doc,f.page,f.id),cls);
      btn.dataset.source=f.id; btn.append(el('span',label)); return btn;
    }
    const root=el('section','','ticket-review');
    root.setAttribute('aria-label','维修工单核对');
    const heading=el('h4'), head=box('ticket-head',heading);
    const body=box('ticket-body');
    const pick=el('select','','ticket-picker');
    if (tickets.length>1) {
      pick.setAttribute('aria-label','选择维修工单');
      for (const [i,r] of tickets.entries()) {
        const id=line(r,'warranty_ticket_id'), state=line(r,'warranty_ticket_state');
        pick.add(new Option((id && r.number===value(id)?r.number:'工单 '+(i+1))+(state?' · '+value(state):''),String(i)));
      }
      pick.addEventListener('keydown',event=>{
        if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
        const last=pick.options.length-1;
        const index={ArrowUp:Math.max(0,pick.selectedIndex-1),ArrowDown:Math.min(last,pick.selectedIndex+1),Home:0,End:last}[event.key];
        if (index===undefined) return;
        event.preventDefault();
        if (index!==pick.selectedIndex) select(index);
      });
      head.append(pick);
    }
    root.append(head,body);
    function preview() {
      if (!root.isConnected || !root.getClientRects().length) return;
      body.querySelector('.ticket-image-review')?.dispatchEvent(new Event('show-image'));
      for (const ink of body.querySelectorAll('.ticket-ink[data-preview="idle"]')) {
        ink.dataset.preview='loading';
        EvidenceCompare.lineExcerpt(index.facts.get(ink.parentElement.dataset.source),index).then(canvas=>{
          if (!ink.isConnected) return;
          if (canvas) ink.append(canvas);
          ink.dataset.preview=canvas?'image':'text';
        }).catch(()=>{ink.dataset.preview='text';});
      }
    }
    root.addEventListener('show-tickets',()=>{
      for (const ink of body.querySelectorAll('.ticket-ink[data-preview="text"]')) ink.dataset.preview='idle';
      requestAnimationFrame(preview);
    });
    const previewBlock=(label,f,page,slot)=>{
      const card=box('ticket-original',box('ticket-source-head',glyph('file-earmark-text'),el('strong',label)));
      card.dataset.side=slot;
      if (f) {
        const source=action('',()=>openPage(f.doc,f.page,f.id),'ticket-source');
        source.dataset.source=f.id;
        const ink=el('span','','ticket-ink'); ink.dataset.preview='idle'; ink.append(el('q',f.source_line.text));
        source.append(ink,box('ticket-location',el('span',f.name+' · '+f.page+' 页 · '+f.source_line.number+' 行'),glyph('arrows-angle-expand')));
        card.append(source);
      } else if (page) {
        const source=action('查看第 '+page.page+' 页原件',()=>openPage(page.doc,page.page),'ticket-page');
        source.dataset.page=page.doc+'/p'+page.page; card.append(source);
      } else card.append(el('span','原件待核','small'));
      return card;
    };
    function select(i) {
      const r=tickets[i], id=line(r,'warranty_ticket_id'), fault=line(r,'warranty_fault'), state=line(r,'warranty_ticket_state');
      const date=line(r,'warranty_closed_on'), signer=line(r,'warranty_closed_by'), reported=line(r,'warranty_reported_on');
      const closed=date && PhaseEvidence.dateOn(date)===r.closed_on?r.closed_on:null;
      const opening=reported && PhaseEvidence.dateOn(reported)===r.reported_on?r.reported_on:null;
      const witness=signer?.status==='confirmed' && signer.attestation?.decision==='confirm' && signer.attestation?.source_check &&
        value(signer).replace(/\s*\(\s*已签(?:字|名)\s*\)$/u,'')===r.closed_by ? r.closed_by : null;
      const compare=linkedState(index,graph,phase,r,state);
      const proven=compare && state && value(state)===r.printed_state && opening && confirmDay &&
        ((r.state==='open' && ['待维修','未关闭','维修中','待复修','处理中'].includes(value(state))) ||
        (['closed','late','same_day'].includes(r.state) && witness && closed && ['已关闭','已修复并关闭'].includes(value(state))));
      const recordedClose=r.state==='stated_closed' && entry.certificate && r.linked && witness && closed && confirmDay &&
        closed<confirmDay && state && ['已关闭','已修复并关闭'].includes(value(state));
      const decision=proven || recordedClose?r.state:(titles[r.state] && r.state!=='stated_closed'?r.state:'pending');
      const conflicts=(r.identity_conflicts || []).flatMap(p=>{
        const left=printedFact(index,phase,p.contract_ref,p.field), right=line(r,p.field);
        return left && graph.documents_by_kind.contract?.includes(left.unit || left.doc) && right?.id===p.ticket_ref &&
          value(left)!==value(right)?[{left,right,label:left.label,field:p.field}]:[];
      });
      const before=closed && bankDates.filter(b=>b.date<closed).sort((a,b)=>a.date.localeCompare(b.date))[0];
      let caption=titles[decision];
      if (decision==='open') caption=value(defects)==='无未关闭缺陷'?(entry.certificate?'期满单记载与「':'期满确认与「')+value(state)+'」工单冲突':'工单状态为「'+value(state)+'」';
      if (decision==='closed') caption='工单关闭早于期满确认 '+days(confirmDay,closed)+' 天';
      if (decision==='same_day') caption=entry.certificate?'两单列同日，关闭与签发先后待核':'关闭与期满确认同日，先后待核';
      if (decision==='late') caption=before?'回单早于工单关闭 '+days(closed,before.date)+' 天':(entry.certificate?'工单关闭日晚于单上期满日 ':'工单关闭晚于期满确认 ')+days(closed,confirmDay)+' 天';
      if (decision==='identity' && conflicts.length) caption='工单与合同的'+conflicts.map(p=>p.label).join('、')+'不同';
      root.dataset.ticketState=decision; root.dataset.unit=r.unit;
      heading.textContent=caption; pick.value=String(i); body.replaceChildren(); delete root.dataset.details;
      const ticketPages=ledger.pages.filter(p=>p.ticket && p.unit===r.unit && within(p.doc+'/p'+p.page));
      const alternatives=pairs(phase,graph).filter(p=>p.unit===r.unit);
      const pairing=decision==='late' && before && payments.map(f=>({f,p:pairs(f,graph).find(p=>p.unit===r.unit &&
        p.role==='payment' && p.left.id===before.fact.id)})).find(x=>x.p);
      const role=conflicts.length?'identity-'+conflicts[0].field:
        ['late','same_day','closed','stated_closed'].includes(decision)?'dates':'state';
      const chosen=pairing?.p || alternatives.find(p=>p.role===role);
      const primary=box('ticket-pair');
      const scan=decision==='scope' && WarrantyImages.panel(phase,r,ledger,index);
      if (scan) {
        heading.textContent='工单影像待核'; root.dataset.ticketState='scope';
      } else if (conflicts.length) {
        for (const p of conflicts) primary.append(previewBlock('合同'+p.label,p.left,null,'contract'),previewBlock('工单'+p.label,p.right,null,'ticket'));
      } else if (chosen?.role==='payment' || chosen?.role==='dates') {
        const payment=chosen.role==='payment';
        primary.append(previewBlock(payment?'银行回单':'期满确认单',chosen.left,null,payment?'bank':'certificate'),
                       previewBlock('维修工单',chosen.right,null,'ticket'));
      } else {
        const certPage=ledger.pages.find(p=>graph.documents_by_kind.warranty?.includes(p.unit) && within(p.doc+'/p'+p.page));
        primary.append(previewBlock('期满确认单',defects,certPage,'certificate'),previewBlock('维修工单',state,ticketPages[0],'ticket'));
      }
      const toolbar=box('ticket-toolbar');
      body.append(scan || primary,toolbar);
      if (chosen) {
        const jump=action('双页对照',()=>showFindingPath(pairing?.f || phase,true,chosen.key),'ticket-compare');
        jump.prepend(glyph('arrows-angle-expand')); jump.append(el('span','，'+chosen.label,'visually-hidden'));
        jump.dataset.ticketPair=chosen.key; toolbar.append(jump);
      }
      const facts=box('ticket-fields');
      facts.id='ticket-fields-'+phase.id; facts.hidden=true;
      function field(label,f,text) {
        if (!f || !text) return;
        const btn=link(label,f,'ticket-field');
        btn.append(el('strong',text)); facts.append(btn);
      }
      field('工单编号',id,r.number===value(id)?r.number:null);
      field('报修事项',fault,r.fault===value(fault)?r.fault:null);
      field('工单状态',state,value(state));
      field('期满遗留事项',defects,value(defects));
      field('报修日',reported,opening);
      field('关闭日',date,closed);
      field(witness?'采购方签认':'签认栏待核',signer,witness || value(signer));
      field(entry.certificate?'单上期满日':'期满确认',cert,confirmDay);
      for (const b of bankDates) field(bankDates.length>1?b.fact.name:'回单落款',b.fact,b.date);
      if (facts.children.length || scan) {
        const disclosure=action('工单详情',()=>{
          facts.hidden=!facts.hidden;
          root.dataset.details=facts.hidden?'closed':'open';
          disclosure.setAttribute('aria-expanded',String(!facts.hidden));
        },'ticket-disclosure');
        disclosure.setAttribute('aria-controls',scan?facts.id+' scan-details-'+phase.id:facts.id); disclosure.setAttribute('aria-expanded','false');
        disclosure.append(glyph('chevron-down')); toolbar.append(disclosure); body.append(facts);
      }
      const riders=ledger.lines.filter(l=>l.kind==='ticket_line' && l.unit===r.unit && l.field==='qualification' && l.line && within(l.doc+'/p'+l.page));
      if (decision==='scope' && (!scan || riders.length || ticketPages.some(p=>p.native))) {
        const more=fold('核对工单原页及附注');
        for (const p of ticketPages) more.append(action((index.documents.get(p.doc)?.name || '原件')+' · 第 '+p.page+' 页',()=>openPage(p.doc,p.page),'ref'));
        for (const l of riders) more.append(action(l.quote,()=>openPage(l.doc,l.page,null,l.line),'ref'));
        body.append(more);
      }
      requestAnimationFrame(preview);
    }
    pick.addEventListener('change',()=>select(pick.selectedIndex));
    const priority=tickets.findIndex(r=>r.status==='risk'), pending=tickets.findIndex(r=>r.status==='missing');
    select(priority>=0?priority:pending>=0?pending:0);
    return root;
  }
  return {panel,pairs};
})();
