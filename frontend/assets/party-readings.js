const PartyReadings = (() => {
  const format='reviewed-party-line-v1';
  const labels={seller:['供应方','销方','销售方','乙方','卖方','供方','供应商','供货单位'],
    buyer:['采购方','购方','购买方','甲方','买方','需方','采购单位','验收单位']};
  const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  const rect=r=>Array.isArray(r) && r.length===4 && r.every(n=>Number.isFinite(n) && n>=0 && n<=1) && r[0]<r[2] && r[1]<r[3];

  function operation(fact, kind, doc, page) {
    const confirmed=fieldReceiptOperation(fact,doc,page), edit=fact.amendment, source=edit?.source_check;
    return (confirmed===kind || confirmed==='confirm') && source?.operation===kind && source.format==='field-source-v1' &&
      source.case_id===state.bundle?.report.case_id && source.doc===doc.id && source.page===1 &&
      source.original_sha256===doc.sha256 && source.page_sha256===page.sha256 && source.rev===edit.rev &&
      edit.target===fact.id && ['doc','page','field','quote','value'].every(key=>edit[key]===fact[key]) &&
      source.rev<=fact.attestation.rev && state.detail.revisions.some(r=>r.rev===source.rev && r.hash===source.report_hash);
  }

  function bind(report,id,finding) {
    const g=report?.graph, collection=g?.reviewed_party_lines;
    if (collection?.format!==format || report.policy?.party_readings!==format ||
        !/^[a-f0-9]{64}$/.test(report.policy.code_sha256?.['party_readings.py']) || !Array.isArray(collection.rows) ||
        !/^\d{4}\.\d{1,2}\.\d{1,2}\.\d+$/.test(report.policy.version) ||
        report.policy.version.localeCompare('2026.11.27.22','en',{numeric:true})<0 ||
        report.case_id!==state.detail?.id || report.case_id!==state.bundle?.report.case_id) return null;
    const matches=collection.rows.filter(r=>r.id===id);
    if (matches.length!==1) return null;
    const [r]=matches, pid=r.doc+'/p1', role=labels[r.field];
    if (!role || r.unit!==r.doc || !/^d\d{2,8}$/.test(r.doc) || r.page!==1 || !Number.isSafeInteger(r.line) || r.line<1 ||
        id!=='party-line/'+pid+'/l'+r.line || !['pending','same_line'].includes(r.state) ||
        !Array.isArray(r.rects) || !r.rects.length || !r.rects.every(rect)) return null;
    const doc=issuedPageDocument(g,r), page=g.nodes.find(n=>n.id===pid);
    const place=g.payment_window_sources?.pages?.filter(p=>p.doc===r.doc);
    if (doc?.ext!=='.pdf' || doc.pages!==1 || r.original_sha256!==doc.sha256 || page.layer!=='text' || !page.clause_text_only ||
        place?.length!==1 || !place[0].native || !place[0].text_only || place[0].unit!==doc.id ||
        !['contract','acceptance','remediation','reinspection'].includes(place[0].document_kind) ||
        !g.documents_by_kind[place[0].document_kind]?.includes(doc.id) || g.gaps.some(v=>v.doc===doc.id)) return null;
    const names=g.facts.filter(f=>f.doc===r.doc && f.field===r.field);
    if (names.length!==2) return null;
    const model=names.find(f=>f.id===r.model_ref), added=names.find(f=>f.id===r.added_ref);
    if (!model || !added || !new RegExp('^'+pid+'/f[1-9][0-9]*$').test(model.id) || !new RegExp('^'+pid+'/h[a-f0-9]{12}$').test(added.id) ||
        names.some(f=>f.value!==r.value || f.page!==1 || f.source_sha256!==doc.sha256 || f.page_sha256!==page.sha256) ||
        !operation(added,'add',doc,page) || added.original_candidate || added.quote!==r.quote || added.source_line?.text!==r.quote ||
        added.source_line.number!==r.line || !same(added.source_line.rects,r.rects)) return null;
    const printed=/^([^:：]+)[:：](.*)$/u.exec(r.quote), first=/^([^:：]+)[:：](.*)$/u.exec(r.model_quote);
    if (!first || !printed || !r.value || /[*×□…/、；;：:]|待定|不详|同上|另见|同(?:主)?合同/u.test(r.value) ||
        !role.includes(printed[1].trim()) || !role.includes(first[1].replace(/\s/g,'')) ||
        printed[2].trim()!==r.value || first[2].trim()!==r.value) return null;
    const calls=report.calls?.pages?.filter(c=>c.doc===r.doc && c.page===1);
    if (calls?.length!==1) return null;
    const [call]=calls;
    const index=model.id.split('/f')[1], initial=call?.output?.facts?.[Number(index)-1];
    const inputs=call?.check?.input?.filter(item=>item.index===index), votes=call?.check?.output?.checks?.filter(item=>item.index===index);
    if (!initial || initial.quote!==r.model_quote || initial.field!==r.field || initial.value!==r.value ||
        !call.response_id || call.response_id!==model.response_id || !call.check?.response_id || call.check.response_id!==model.check_response_id ||
        call.check.response_id===call.response_id || inputs?.length!==1 || inputs[0].field!==model.label ||
        inputs[0].quote!==r.model_quote || inputs[0].value!==r.value || votes?.length!==1 || !['clear','conflict','unreadable'].includes(votes[0].support) ||
        call.page_sha256!==page.sha256) return null;
    const corrected=r.state==='same_line';
    if (corrected ? (!operation(model,'correct',doc,page) || model.original_candidate?.quote!==initial.quote ||
        model.original_candidate?.value!==initial.value || model.original_candidate?.field!==initial.field ||
        model.quote!==r.quote || !same(model.source_line,added.source_line)) :
        (model.quote!==initial.quote || model.status!=='visual' || model.source_line || model.amendment || model.attestation || r.quote===model.quote)) return null;
    const observed=g.facts.filter(f=>f.doc===r.doc && f.page===1 && f.source_line?.number===r.line).map(f=>f.id).sort();
    if (!same(observed,corrected?[model.id,added.id].sort():[added.id])) return null;
    const node=g.nodes.filter(n=>n.id===id);
    if (node.length!==1 || node[0].type!=='party_reading_line' || node[0].label!==r.quote || node[0].state!==r.state ||
        node[0].doc!==r.doc || node[0].page!==1 || node[0].line!==r.line) return null;
    const edge=(type,from,to,refs)=>g.edges.filter(e=>e.type===type && e.from===from && e.to===to && same(e.evidence,refs)).length===1;
    const owners=g.nodes.filter(n=>n.type==='party' && n.label===r.value);
    if (owners.length!==1 || names.some(f=>!edge('records',pid,f.id,[f.id]) ||
        (f.status==='confirmed' && !edge(r.field,r.doc,owners[0].id,[f.id]))) ||
        !edge('locates_party_reading',pid,id,[pid,added.id]) ||
        g.edges.filter(e=>e.from===model.id && e.to===added.id && ['shares_party_line','compares_party_readings'].includes(e.type)).length!==1 ||
        !edge(corrected?'shares_party_line':'compares_party_readings',model.id,added.id,[model.id,id,added.id])) return null;
    if (finding) {
      const result=g.nodes.filter(n=>n.id==='finding/'+finding.id);
      if (result.length!==1 || result[0].status!==finding.status || result[0].detail!==finding.detail ||
          !finding.party_readings?.includes(id) || !finding.scope.includes(doc.id) ||
          [id,pid,model.id,added.id].some(ref=>!finding.evidence.includes(ref) || !edge('supports_result',ref,result[0].id,[ref]))) return null;
    }
    return {row:r,model,added,doc,role:r.field==='seller'?'供应方':'采购方'};
  }

  function onPage(report,doc,page) {
    const proofs=new Map();
    for (const row of report?.graph.reviewed_party_lines?.rows || []) {
      if (row.doc!==doc || row.page!==page) continue;
      const pair=bind(report,row.id);
      if (pair) {
        proofs.set(pair.model.id,pair);
        proofs.set(pair.added.id,pair);
      }
    }
    return proofs;
  }

  function citation(report,id,finding) {
    const proof=bind(report,id,finding);
    if (!proof) return el('span','主体原行待核','small');
    const {row,role,doc}=proof;
    const link=action(role+'核字 · '+(row.state==='pending'?'两条读数待核':'已核为同一原行'),
      ()=>openPage(doc.id,1,row.model_ref),'source-jump party-reading-jump');
    link.title=doc.name+' · 第 1 页第 '+row.line+' 行';
    return link;
  }

  function panel(proof,editable,showLine,showSupplement) {
    const {row,model,added,doc,role}=proof, pending=row.state==='pending';
    const card=el('section','','party-reading');
    card.id='party-reading-'+model.id.replaceAll('/','-');
    card.dataset.partyReading=row.id; card.dataset.caseId=state.detail.id; card.dataset.rev=state.bundle.rev;
    card.dataset.state=row.state;
    card.dataset.originalLabel=role+'核字 · '+doc.name;
    card.setAttribute('aria-label',card.dataset.originalLabel+' 第 1 页第 '+row.line+' 行');
    const comparison=el('dl');
    for (const [label,value] of [['模型初读',row.model_quote],['原件第 '+row.line+' 行',row.quote]])
      comparison.append(el('dt',label),el('dd',value));
    const original=action('看原件第 '+row.line+' 行',showLine,'ref');
    const receipt=action('补录回执',showSupplement,'ref');
    receipt.title='查看底稿 R'+added.amendment.rev+' 的补录依据和核图人';
    const actions=box('party-reading-actions',original,receipt);
    if (pending && editable) actions.append(action('据原行更正',()=>openAmend(doc.id,1,model,{partyLine:row.id}),'primary'));
    card.append(box('panel-head',el('strong',role+'核字'),el('small',pending?'栏名待核':'已核为同一行')),comparison,actions);
    return card;
  }
  return {bind,onPage,citation,panel};
})();
