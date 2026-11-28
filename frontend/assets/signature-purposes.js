const SignaturePurposes = (() => {
  const format='signed-pdf-purpose-v1', revisionFormat='signed-pdf-purpose-v2';
  const labels={contract:'合同',acceptance:'验收报告',reinspection:'复验报告'};
  const sum=value=>typeof value==='string' && /^[a-f0-9]{64}$/u.test(value);
  const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  const anchor=(finding,row)=>'signature-purpose-'+finding.id+'-'+row.doc+(row.coverage?'-r'+row.revision:'');
  function bind(report,finding,id) {
    const graph=report?.graph, ledger=graph?.signature_purposes;
    if (!finding?.signature_purposes?.includes(id) || ![format,revisionFormat].includes(ledger?.format) || report.policy.signature_purposes!==ledger.format ||
        !sum(report.policy.code_sha256?.['signature_purposes.py'])) return null;
    const row=ledger.rows?.find(r=>r.id===id);
    if (!row || row.id!=='signature-purpose/'+row.doc+(row.coverage?'/r'+row.revision:'') ||
        !Object.hasOwn(labels,row.role) || !['quantity_only','as_stated'].includes(row.scope) ||
        !finding.scope.includes(row.doc) || !graph.documents_by_kind[row.role]?.includes(row.doc) || typeof row.reason!=='string' || !row.reason.trim()) return null;
    const contract=row.role==='contract', direct=contract?'H01':'H02';
    if (finding.rule!==direct && !(['H04','H05'].includes(finding.rule) && finding.stage)) return null;
    const index=graphIndex(graph), doc=index.documents.get(row.doc), result='finding/'+finding.id;
    const parent=contract?graph.pdf_execution_sources?.documents?.find(r=>r.doc===row.doc && same(r.units,[row.doc])):
      graph.acceptance_pdf_sources?.records?.find(r=>r.unit===row.doc && r.doc===row.doc);
    const matches=parent?.signatures?.filter(s=>s.field===row.field && s.revision===row.revision) || [];
    const [sig]=matches;
    if (doc?.ext!=='.pdf' || matches.length!==1 || !sum(doc.sha256) || doc.sha256!==row.original_sha256 || index.nodes.get(doc.id)?.sha256!==doc.sha256 ||
        parent.id!==row.source || parent.original_sha256!==doc.sha256 || parent.state!=='current' ||
        !sum(sig.certificate_sha256) || sig.certificate_sha256!==row.certificate_sha256) return null;
    const current=sig.state==='current' && sig.coverage==='ENTIRE_FILE' && sig.ends_at===doc.size;
    if (row.coverage) {
      const earlier=sig.state==='earlier' && sig.coverage==='ENTIRE_REVISION' && sig.ends_at>0 && sig.ends_at<doc.size;
      if (ledger.format!==revisionFormat || parent.signatures.length<2 || !Number.isSafeInteger(row.revision) || row.revision<1 ||
          (!earlier && !current) || sig.coverage!==row.coverage || row.ends_at!==sig.ends_at || !sum(row.signed_sha256) ||
          (row.signed_sha256===doc.sha256)!==current) return null;
    } else if (!current || parent.signatures.length!==1) return null;
    const edges=graph.edges, node=index.nodes.get(id), inspection=index.nodes.get(row.source), procedure=index.nodes.get(result);
    if ((!contract && (!Array.isArray(parent.pages) || !Array.isArray(parent.fields))) ||
        inspection?.type!==(contract?'pdf_signature_inspection':'acceptance_pdf_inspection') || inspection.doc!==doc.id ||
        inspection.sha256!==doc.sha256 || procedure?.status!==finding.status || procedure.detail!==finding.detail ||
        !edges.some(e=>e.type===(contract?'pdf_signature_source':'acceptance_pdf_source') && e.from===doc.id && e.to===row.source &&
          same(e.evidence,contract?[doc.id]:[doc.id,...parent.pages.map(p=>p.ref),...parent.fields]))) return null;
    if (node?.type!=='pdf_signature_purpose' || node.doc!==row.doc || node.label!==row.reason ||
        !edges.some(e=>e.type==='declares_signature_purpose' && e.from===row.source && e.to===id && same(e.evidence,[doc.id,row.source])) ||
        ![id,doc.id,row.source].every(ref=>finding.evidence.includes(ref) && edges.some(e=>e.type==='supports_result' &&
          e.from===ref && e.to===result && same(e.evidence,[ref])))) return null;
    const expert=report.calls?.expert, used=ledger.rows.filter(r=>finding.signature_purposes.includes(r.id));
    if (!expert?.response_id || !expert.input?.procedures?.some(p=>p.rule===finding.rule && p.status===finding.status &&
        p.observation===finding.detail && same(p.evidence,finding.evidence) && same(p.stage,finding.stage) && same(p.signature_purposes,used))) return null;
    return {row,doc};
  }
  function params(finding) {
    if (finding.rule==='H01') return {view:'contract-checks'};
    if (finding.rule==='H02') return {view:'acceptance-checks'};
    return {view:'payment-checks',stage:finding.id};
  }
  function panel(report,finding,rev) {
    const group=document.createDocumentFragment(), series=new Map();
    for (const id of finding.signature_purposes || []) {
      const proof=bind(report,finding,id);
      if (!proof) continue;
      const {row,doc}=proof, detail=el('details','','signature-purpose');
      const summary=el('summary');
      summary.id=anchor(finding,row);
      Object.assign(summary.dataset,{signaturePurpose:id,findingKey:finding.id,caseId:report.case_id,rev:String(rev)});
      const older=row.coverage==='ENTIRE_REVISION', edition='修订 '+row.revision;
      const title=row.coverage?box('purpose-edition',el('strong',edition),el('small',older?'较早签名':'覆盖提交件')):
        el('strong',labels[row.role]+'签名原因');
      summary.append(box('purpose-title',title,glyph('chevron-down')),el('q',row.reason));
      if (!row.coverage) summary.append(el('small',doc.name+' · PDF 签名属性'));
      const source=row.coverage?link('下载'+edition,base()+'/reports/'+rev+'/documents/'+doc.id+'/signed-revisions/'+row.revision,'scope-open-original'):
        link('下载所签原件',workpaperSource(doc.id,'original'),'scope-open-original');
      source.download=row.coverage?doc.name.slice(0,-4)+'-修订'+row.revision+'.pdf':doc.name;
      const list=el('dl');
      for (const [key,text] of [['签名域',row.field],['签名覆盖','文件'+edition+' · '+(older?'较早修订':'整份提交件')]])
        list.append(el('dt',key),el('dd',text));
      const hash=el('dd',row.certificate_sha256,'purpose-fingerprint');
      hash.dir='ltr';
      list.append(el('dt','签名证书 SHA-256'),hash);
      if (row.coverage) {
        const hash=el('dd',row.signed_sha256,'purpose-fingerprint');
        hash.dir='ltr';list.append(el('dt','所签修订 SHA-256'),hash);
      }
      const download=row.coverage?box('purpose-download',source,el('small',row.ends_at.toLocaleString('zh-CN')+' 字节')):source;
      detail.append(summary,box('purpose-attributes',list,download));
      if (row.coverage) {
        if (!series.has(doc.id)) {
          const section=el('section','','purpose-series');
          section.append(el('h4',doc.name+' · 签名原因'));series.set(doc.id,section);group.append(section);
        }
        detail.name='purposes-'+finding.id+'-'+doc.id;
        series.get(doc.id).append(detail);
      } else group.append(detail);
    }
    return group.childElementCount?group:null;
  }
  function locate(report,anchor) {
    const match=/^signature-purpose-(H0[1245]-[1-9]\d*)-(d\d{2,8})(?:-r([1-9]\d{0,7}))?$/u.exec(anchor || '');
    if (!match) return null;
    const finding=report.findings.find(f=>f.id===match[1]), proof=bind(report,finding,'signature-purpose/'+match[2]+(match[3]?'/r'+match[3]:''));
    return proof && {...proof,finding};
  }
  function citation(report,finding,ref,rev) {
    const owner=finding || report.findings.find(f=>['H01','H02'].includes(f.rule) && f.signature_purposes?.includes(ref));
    const proof=bind(report,owner,ref);
    if (!proof) return null;
    const mark=anchor(owner,proof.row);
    const target=Team.hash('case/'+report.case_id+'?'+new URLSearchParams({rev:String(rev),...params(owner)}));
    const where=proof.row.coverage?'修订 '+proof.row.revision+' 签名原因':'签名原因';
    return link(proof.doc.name+' · '+where,'/app?walkat='+mark+target,'button ref');
  }
  return {panel,bind,locate,params,citation};
})();
