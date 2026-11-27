// Show a comparison only after locating the actual clause, named field and contract counterparties.
const ApprovalNames = (() => {
  const firstFormat='cited-inspection-payment-use-v5', format='cited-inspection-payment-use-v6';
  const jointFormat='cited-inspection-payment-use-v9';
  const supports=value=>[firstFormat,format,'cited-inspection-payment-use-v7','cited-inspection-payment-use-v8',jointFormat].includes(value);
  const signers=['签批人姓名','审批人姓名','实际签批人'];
  const labels={listed:'两处姓名相符',different:'签批人不同',joint_difference:'会签名单有一人不同',partial:'共同签批少一人',missing:'签批姓名待补',other_stage:'属于其他期款',scope:'签批范围待核'};
  const headings=['付款签批约定','付款审批人约定'];
  const ordinary=['contract','bank_receipt','acceptance','reinspection','remediation','warranty'];
  const same=(a,b)=>Array.isArray(a) && Array.isArray(b) && a.length===b.length && a.every((v,i)=>v===b[i]);
  const archived=report=>/^[a-f0-9]{64}$/u.test(report.policy.code_sha256?.['approval_names.py']);
  const column=r=>r.quote.split(/[:：]/u,1)[0].trim();
  const value=r=>r.quote.slice(r.quote.search(/[:：]/u)+1).trim();
  const unnamed=new Set(['','指定人','未指定','未确定','不确定','待指定','待审批','待签','待签批','未签','未填写','未填','未注明',
    '未载明','未记载','未具名','未署名','无姓名','空白','空缺','空栏','无','待补','待核','待确认','未知','不详','不适用','无法辨认',
    '董事会','指定人员','负责人','经办人','审批人','签批人','财务部','财务负责人','总经理','有权审批人','采购负责人']);
  const pointers=new Set(['详附件','见附件','见签章','见附表','见下页','详附表','另附','见授权书']);
  function name(text,version) {
    return /^[\u3400-\u9fff]{2,4}$/u.test(text) &&
      !(version!==firstFormat && (unnamed.has(text) || pointers.has(text))) &&
      !/某|或|匿名|隐去|遮盖|脱敏|不详|略去|代签|代为|代验|未签|待签|代表|以及|及其|等人|等$|任何|其他|全体|双方|其本人|签批人|审批人|当事人|经授权|两人|二人|任一|共同|联合|分别|任选|之一|授权|另见|同上|详见/u.test(text) &&
      !/(?:负责人|经办人?|主管|经理|董事长?|总监|专员|员工|人员|主任|部长|组长|科长|职员|代理人|法人|签字人|法务|会计|出纳|处|科|部|室|公司|组|员|职工|工程师|总工|班长|老师)$/u.test(text) &&
      !['未填','未填写','未载明','空白','待定','本人','不适用','见附件','见签章','甲方','乙方','采购','销售','代理','无法辨认','模糊',
        '待补充','待核','空缺','未提供','未注明','收货人','验收人','未记载','待确认','待明确','无名氏','签章','签字栏','仅盖章','甲单位','乙单位','待补','未知','不清楚'].includes(text);
  }
  function list(text,version) {
    const names=text.split('、');
    return names.length<=2 && names.every(n=>name(n,version)) && new Set(names).size===names.length?names:null;
  }
  function clause(row,version) {
    if (!headings.includes(column(row))) return null;
    const match=/^第([0-9一二两三四五六七八九十]+)期(验收款|预付款|质保金)须由([\u3400-\u9fff]{2,8}?)(?:签批|[与、]([\u3400-\u9fff]{2,8}?)共同签批)。?$/u.exec(value(row));
    if (!match) return null;
    const names=match[4]?[match[3],match[4]]:[match[3]],index=BatchPhase.ordinal(match[1]);
    return index && names.every(n=>name(n,version)) && new Set(names).size===names.length?{names,index,role:match[2]}:null;
  }
  function jointDifference(required,listed,version) {
    if (version!==jointFormat || required?.length!==2 || listed?.length!==2) return null;
    const missing=required.filter(n=>!listed.includes(n)), other=listed.filter(n=>!required.includes(n));
    return missing.length===1 && other.length===1?{missing,other}:null;
  }
  const jointSummary=check=>'审批单未列'+check.missing_names[0]+'，另列'+check.other_names[0]+'。';
  function bind(item,report,sheet,readRow) {
    const c=item.inspection_use,a=c.approval,check=a.names,g=report.graph;
    const links=g.edges.filter(e=>e.type==='compares_approval_names' && e.evidence?.[0]===c.citation);
    const pages=g.inspection_use_sources.approver_terms || [];
    if (!supports(c.format) || !pages.length || !['earlier','later','same_day','refused'].includes(a.state)) return !check && !links.length?[]:null;
    if (!archived(report) || !check) return null;
    const entries=[];
    for (const p of pages) {
      const place=g.payment_window_sources.pages.find(v=>v.doc===p.doc && v.page===p.page && v.unit===p.unit);
      if (place?.document_kind!=='contract' || !place.native) return null;
      for (const row of p.rows) {
        const doc=readRow(row);
        if (!doc || !row.id.startsWith('contract-approver/') || row.doc!==p.doc || row.page!==p.page || row.unit!==p.unit ||
            row.field!==(headings.includes(column(row))?'named_clause':'qualification') ||
            ![row.id,row.doc+'/p'+row.page,...row.facts].every(id=>a.evidence.includes(id)) ||
            p.complete && (!place.text_only || p.unit!==p.doc || p.page!==1 || doc.ext!=='.pdf' || doc.pages!==1 ||
            g.facts.some(f=>f.doc===p.doc && f.status==='disputed') ||
            g.gaps.some(v=>v.doc===p.doc && ['partial','unreadable','section_unresolved'].includes(v.quality)))) return null;
        entries.push({row,doc,scope:'contract_term'});
      }
    }
    const signer=sheet.find(e=>e.row.field==='signed_by')?.row,raw=entries[0]?.row, kinds=g.documents_by_kind;
    if (!same(check.rows,entries.map(e=>e.row.id)) || check.signed_by!==(signer?.id || null)) return null;
    const term=raw && clause(raw,c.format), fields={}, sources=PerformanceIndex.originals(item,g);
    const units=new Set([...ordinary.flatMap(k=>kinds[k] || []),...a.documents]);
    const eligible=pages.length===1 && pages[0].complete && entries.length===1 && raw.rects.length && term &&
      same(kinds.contract,[raw.unit]) && units.size===g.documents.length && g.documents.every(d=>units.has(d.id)) &&
      Object.entries(kinds).every(([k,v])=>!v.length || ordinary.includes(k) || k==='other');
    if (eligible) {
      const ledger=g.retest_reference_sources?.rows?.length?g.retest_reference_sources.rows:g.payment_quality_sources?.rows || [];
      for (const [key,side] of [['contract_id','contract_id'],['buyer','payer'],['seller','payee']]) {
        const found=sources.filter(s=>PerformanceIndex.matchesPrintedField(s,report,ledger,raw.unit,key));
        if (found.length!==1 || value(sheet.find(e=>e.row.field===side).row)!==value({quote:found[0].fact.source_line.text})) break;
        fields[key]=found[0].fact.id;
      }
    }
    let state='scope',required,listed;
    if (Object.keys(fields).length===3) {
      if (Object.keys(check.contract_fields || {}).length!==3 || Object.entries(fields).some(([k,id])=>check.contract_fields[k]!==id || !a.evidence.includes(id))) return null;
      const stage=/^第(.+)期$/u.exec(item.stage.name);
      if (!stage || BatchPhase.ordinal(stage[1])!==term.index || term.role!=='验收款') state='other_stage';
      else {
        required=term.names;listed=signer?list(value(signer),c.format):[];
        if (signer && !listed && c.format!==firstFormat && unnamed.has(value(signer))) listed=[];
        if (!listed) return null;
        if (!listed.length) state='missing';
        else if (listed.every(n=>required.includes(n))) state=listed.length===required.length?'listed':'partial';
        else if (listed.every(n=>!required.includes(n))) state='different';
      }
    } else if (check.contract_fields) return null;
    const difference=jointDifference(required,listed,c.format);
    if (difference) {
      state='joint_difference';
      if (!same(check.missing_names,difference.missing) || !same(check.other_names,difference.other)) return null;
    } else if (Object.hasOwn(check,'missing_names') || Object.hasOwn(check,'other_names')) return null;
    if (state!==check.state || (required?!same(required,check.required):Object.hasOwn(check,'required')) ||
        (listed?!same(listed,check.listed):Object.hasOwn(check,'listed'))) return null;
    if (['listed','different','partial','joint_difference'].includes(state)) {
      if (links.length!==1 || links[0].from!==raw.id || links[0].to!==signer.id ||
          !same(links[0].evidence,[c.citation,a.request,item.stage.clause_ref,fields.contract_id,fields.buyer,fields.seller,raw.id,signer.id])) return null;
    } else if (links.length) return null;
    return entries;
  }
  return {format,firstFormat,jointFormat,supports,unnamed,signers,labels,archived,list,clause,bind,jointDifference,jointSummary};
})();
