const ReceiptParties = (() => {
  const format='printed-bank-party-roles-v1';
  const names={buyer:'采购方',seller:'供应方',payer:'付款户名',payee:'收款户名'};
  const labels={payer:['付款户名','付款人名称','付款人户名'],payee:['收款户名','收款人名称','收款人户名'],
    buyer:['采购方','甲方','买方','购买方','需方','采购单位'],seller:['供应方','乙方','卖方','销售方','供方','供应商']};
  const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  const literal=value=>value.normalize('NFKC').trim();
  function column(quote) {
    if (typeof quote!=='string') return [];
    const split=quote.search(/[:：﹕︓]/u);
    return split<0?[]:[literal(quote.slice(0,split)),quote.slice(split+1).trim()];
  }
  function bind(report,finding,id) {
    const {graph}=report, ledger=graph.bank_party_readings;
    if (report.policy.bank_party_readings!==format || ledger?.format!==format || finding?.rule!=='H05' ||
        !finding.bank_party_readings?.includes(id)) return null;
    const row=ledger.rows?.find(r=>r.id===id);
    if (!row || !finding.scope.includes(row.unit) || !['pending','corrected'].includes(row.state)) return null;
    const index=graphIndex(graph), pid=row.doc+'/p'+row.page, rid='finding/'+finding.id, fact=index.facts.get(row.fact);
    const call=report.calls?.pages?.find(c=>c.doc===row.doc && c.page===row.page);
    const doc=call && issuedPageDocument(graph,call), line=fact?.source_line;
    const label=column(row.quote), original=fact?.original_candidate || fact;
    const originalRole=original?.field, expected=labels[row.printed_role];
    if (!doc || doc.sha256!==row.original_sha256 || fact?.source_sha256!==doc.sha256 || !expected ||
        row.page_sha256!==call.page_sha256 || fact.page_sha256!==row.page_sha256 || fact.doc!==row.doc || fact.page!==row.page ||
        (fact.unit || fact.doc)!==row.unit || !expected.includes(label[0]) || literal(label[1])!==row.value ||
        row.model_role!==originalRole || !names[originalRole] || row.model_role===row.printed_role ||
        !line?.rects?.length || line.text!==row.quote || line.number!==row.line || !same(line.rects,row.rects) ||
        original.quote!==row.quote || typeof original.value!=='string' || ![row.value,literal(row.quote)].includes(literal(original.value)) ||
        (row.state==='pending'?fact.amendment || fact.field!==originalRole:
          fact.status!=='confirmed' || fact.field!==row.printed_role || fact.amendment?.source_check?.case_id!==report.case_id)) return null;
    const refs=[row.id,row.fact,pid,row.title_ref], links=PerformanceIndex.fieldLinks(graph);
    const edge=(from,to,type,cites)=>graph.edges.some(e=>e.from===from && e.to===to && e.type===type && same(e.evidence,cites));
    if (refs.some(ref=>!finding.evidence.includes(ref) || !links.has(ref+' '+rid)) ||
        index.nodes.get(id)?.state!==row.state || index.nodes.get(rid)?.detail!==finding.detail ||
        !links.has(pid+' '+fact.id) || !edge(pid,id,'locates_bank_party_reading',[pid,fact.id]) ||
        !edge(fact.id,id,'compares_bank_party_role',[fact.id])) return null;
    const offset=fact.id.match(/\/f([1-9]\d*)$/u)?.[1], read=call.output?.facts?.[Number(offset)-1];
    const input=call.check?.input?.filter(i=>i.index===offset), opinions=call.check?.output?.checks?.filter(i=>i.index===offset);
    if (!read || read.field!==originalRole || read.quote!==row.quote || read.value!==original.value ||
        !call.response_id || call.response_id!==fact.response_id || !call.check?.response_id ||
        call.check.response_id===call.response_id || call.check.response_id!==fact.check_response_id ||
        input?.length!==1 || input[0].field!==names[originalRole] || input[0].quote!==read.quote || input[0].value!==read.value ||
        opinions?.length!==1 || !['clear','conflict','unreadable'].includes(opinions[0].support)) return null;
    const expert=report.calls.expert, used=ledger.rows.filter(r=>finding.bank_party_readings.includes(r.id));
    if (!expert?.response_id || !expert.input?.procedures?.some(p=>p.rule===finding.rule && p.status===finding.status &&
        p.observation===finding.detail && same(p.evidence,finding.evidence) && same(p.stage,finding.stage) && same(p.bank_party_readings,used))) return null;
    const role=row.printed_role==='payer'?'buyer':'seller';
    const contracts=graph.documents_by_kind.contract?.filter(u=>finding.scope.includes(u)) || [];
    const peers=contracts.length===1?PerformanceIndex.originals(finding,graph).filter(s=>s.line && s.fact.field===role &&
      (s.fact.unit || s.fact.doc)===contracts[0] && s.fact.quote===s.fact.source_line.text && labels[role].includes(column(s.fact.quote)[0])):[];
    const peer=peers.length===1?peers[0]:null;
    return {row,printedValue:label[1],bank:{fact,doc,line:line.number},peer,role};
  }
  function selection(button,report,rev) {
    const card=button.closest('#performance-index[open] [data-bank-party]');
    if (!card || card.dataset.caseId!==report.case_id || card.dataset.rev!==String(rev)) return null;
    const proof=bind(report,report.findings.find(f=>f.id===card.dataset.findingKey),card.dataset.bankParty);
    return proof && [proof.bank,proof.peer].find(s=>s?.fact.id===button.dataset.bankRoleSource);
  }
  function panel(finding,report,rev) {
    if (!finding.bank_party_readings?.length) return null;
    const group=document.createDocumentFragment();
    for (const ref of finding.bank_party_readings) {
      const proof=bind(report,finding,ref);
      if (!proof) continue;
      const {row,bank,peer,role}=proof, pending=row.state==='pending';
      const card=el('section','','bank-role-reading');
      Object.assign(card.dataset,{bankParty:ref,caseId:report.case_id,rev:String(rev),findingKey:finding.id,state:row.state});
      const title=names[row.printed_role]+'核对';
      card.setAttribute('aria-label',title);
      card.append(box('bank-role-head',el('h4',title),el('span',pending?'分类待核':'已核图更正')));
      const comparison=box('bank-role-sources');
      function source(item,label,value) {
        const {fact,doc,line}=item, place=doc.name+' · 第 '+fact.page+' 页 · 第 '+line+' 行';
        const button=action('',()=>openPage(fact.doc,fact.page,fact.id),'bank-role-source');
        button.dataset.bankRoleSource=fact.id;button.dataset.originalLabel=label+' · '+place;
        button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-controls','page-dialog');
        button.append(el('span',label),el('strong',value),el('small',doc.name),el('small','第 '+fact.page+' 页 · 第 '+line+' 行'));comparison.append(button);
      }
      source(bank,'回单'+names[row.printed_role],proof.printedValue);
      if (peer) source(peer,'合同'+names[role],column(peer.fact.quote)[1]);
      card.append(comparison);
      const info=box('bank-role-actions',el('span','原模型字段 · '+names[row.model_role]));
      if (pending && canReviewCurrentPaper()) {
        const edit=action('据原件更正',()=>openAmend(bank.fact.doc,bank.fact.page,bank.fact,{bankParty:ref,finding:finding.id}),'ref');
        edit.dataset.bankRoleEdit=ref;info.append(edit);
      }
      card.append(info);group.append(card);
    }
    return group.childElementCount?group:null;
  }
  async function amendPreview(proof,image,graph) {
    const canvas=await EvidenceCompare.lineExcerpt(proof.bank.fact,graphIndex(graph),image);
    const pane=image.closest('#amend-original');
    if (!pane || !canvas || !pane.closest('dialog[open]')) return;
    const {row}=proof, view=box('bank-role-preview'), toggle=action('',flip,'ref');
    canvas.setAttribute('role','img');canvas.setAttribute('aria-label','回单原行图像，'+row.quote);
    const caption=el('strong','第 '+row.page+' 页 · 第 '+row.line+' 行');
    view.append(box('bank-role-preview-head',caption,toggle),canvas);
    pane.prepend(view);setView('line');
    function setView(value) {
      pane.dataset.bankView=value;
      toggle.textContent=value==='line'?'查看整页':'返回原行';
      toggle.setAttribute('aria-expanded',String(value==='page'));
      toggle.setAttribute('aria-controls','amend-image');
    }
    function flip() {setView(pane.dataset.bankView==='line'?'page':'line');}
  }
  return {bind,panel,selection,names,amendPreview};
})();
