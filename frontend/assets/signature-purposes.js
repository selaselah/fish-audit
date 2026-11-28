const SignaturePurposes = (() => {
  const format='signed-pdf-purpose-v1', revisionFormat='signed-pdf-purpose-v2', referenceFormat='signed-pdf-purpose-v3';
  const labels={contract:'合同',acceptance:'验收报告',reinspection:'复验报告'};
  const states={unlocated:'待查报告原件',unidentified:'所引编号待核',multiple:'有多份报告',uncertain:'编号归属待核',
    other_contract:'合同编号不同',different:'报告编号不同',matched:'已定位报告 · 终验待核'};
  const fields={title:'报告标题',number:'报告编号',contract:'合同编号',conclusion:'报告所载结论'};
  const scopeFields={metric:'检测项目',scope:'报告检测范围',count:'报告所载台数'};
  const scopeStates={sample:'样机台数待核',review:'检测口径待核',short:'报告台数不足',count_only:'台数相符 · 逐台记录待核'};
  const sum=value=>typeof value==='string' && /^[a-f0-9]{64}$/u.test(value);
  const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  const anchor=(finding,row)=>'signature-purpose-'+finding.id+'-'+row.doc+(row.coverage?'-r'+row.revision:'');
  function bind(report,finding,id) {
    const graph=report?.graph, ledger=graph?.signature_purposes;
    if (!finding?.signature_purposes?.includes(id) || ![format,revisionFormat,referenceFormat].includes(ledger?.format) || report.policy.signature_purposes!==ledger.format ||
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
      if (ledger.format===format || parent.signatures.length<2 || !Number.isSafeInteger(row.revision) || row.revision<1 ||
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
    if (row.report_reference && !validReference(report,finding,row,index)) return null;
    return {row,doc};
  }
  function validReference(report,finding,row,index) {
    const ref=row.report_reference, graph=report.graph, node=index.nodes.get(ref.id), result='finding/'+finding.id;
    const edge=(from,to,type,evidence)=>graph.edges.some(e=>e.from===from && e.to===to && e.type===type && same(e.evidence,evidence));
    const cited=id=>finding.evidence.includes(id) && edge(id,result,'supports_result',[id]);
    if (graph.signature_purposes.format!==referenceFormat || !sum(report.policy.code_sha256['inspection_reports.py']) ||
        !Object.hasOwn(states,ref.state) || !['检测报告','检验报告'].includes(ref.kind) || row.role==='contract' || finding.status==='ok' ||
        ref.id!==row.id.replace('signature-purpose/','inspection-report/') || node?.type!=='signed_inspection_reference' ||
        node.doc!==row.doc || node.label!==ref.kind || !Array.isArray(ref.candidates) || !cited(ref.id) ||
        !edge(row.id,ref.id,'requires_inspection_report',[row.id])) return false;
    const contract=ref.signed_contract;
    if (contract) {
      const fact=index.facts.get(contract.fact);
      if (fact?.doc!==row.doc || fact.field!=='contract_id' || fact.source_line?.number!==contract.line ||
          fact.source_line.text!==contract.quote || fact.value!==contract.value || !cited(contract.fact) ||
          !edge(contract.fact,ref.id,'inspection_contract_number',[contract.fact])) return false;
    }
    if (ref.coverage && !validScope(report,ref,index,cited,edge)) return false;
    return ref.candidates.every(c=>{
      const doc=index.documents.get(c.doc), pid=c.doc+'/p1', page=index.nodes.get(pid);
      return c.page===1 && c.kind===ref.kind && doc?.ext==='.pdf' && doc.pages===1 && sum(doc.sha256) && doc.sha256===c.original_sha256 &&
        index.nodes.get(doc.id)?.sha256===doc.sha256 && page?.type==='page' && page.layer==='text' && page.clause_text_only &&
        sum(page.sha256) && page.sha256===c.page_sha256 && edge(doc.id,pid,'contains',[pid]) &&
        edge(pid,ref.id,'inspection_attachment_page',[doc.id,pid]) && cited(doc.id) && cited(pid) &&
        c.title && Object.keys(fields).every(key=>!c[key] || located(c[key]));
    });
  }
  function located(r) {
    return Number.isSafeInteger(r?.line) && r.line>0 && typeof r.quote==='string' && r.rects?.length &&
      r.rects.every(b=>Array.isArray(b) && b.length===4 && b.every(x=>Number.isFinite(x) && x>=0 && x<=1) && b[2]>b[0] && b[3]>b[1]);
  }
  function validScope(report,ref,index,cited,edge) {
    const c=ref.coverage;
    if (!sum(report.policy.code_sha256?.['inspection_report_scope.py']) || ref.state!=='matched' || ref.candidates.length!==1 ||
        c.format!=='inspection-report-scope-v1' || !Object.hasOwn(scopeStates,c.state) || !c.basis || !c.report_rows) return false;
    for (const [key,item] of Object.entries(c.report_rows)) {
      if (!Object.hasOwn(scopeFields,key) || !located(item) || typeof item.value!=='string') return false;
    }
    for (const line of Object.values(c.basis)) {
      const f=index.facts.get(line.fact);
      if (!f || !['anchored','confirmed'].includes(f.status) || f.page!==1 || f.source_line?.number!==line.line ||
          f.source_line.text!==line.quote || f.quote!==line.quote || ![line.value,line.quote].includes(f.value) ||
          !cited(f.id) || !edge(f.id,ref.id,'inspection_scope_basis',[f.id])) return false;
    }
    const count=v=>{const m=/^(0|[1-9][0-9]{0,5})\s*台$/u.exec(v || '');return m ? Number(m[1]) : null;};
    if (count(c.report_rows.count?.value)!==c.reported || count(c.basis.accepted?.value)!==c.received ||
        count(c.basis.ordered?.value)!==c.ordered) return false;
    if (c.state==='short' || c.state==='count_only') {
      return c.basis.clause && c.basis.acceptance_scope && c.ordered>0 && c.ordered===c.received &&
        Number.isSafeInteger(c.required) && c.required>0 && c.required<=c.ordered && Number.isSafeInteger(c.reported) &&
        c.reported<=c.ordered && c.difference===Math.max(0,c.required-c.reported) && (c.state==='short')===(c.difference>0);
    }
    return c.difference===null;
  }
  function printed(candidate,key,r=candidate[key]) {
    const label=fields[key] || scopeFields[key];
    return {ref:'inspection-report-line/'+candidate.doc+'/p1/l'+r.line,doc:candidate.doc,page:1,rawLine:r.line,quote:r.quote,
      rects:r.rects,label,option:label+' · 第 '+r.line+' 行',quality:'inspection_report_source'};
  }
  function reportLines(report,doc,page) {
    if (page!==1 || report?.policy?.signature_purposes!==referenceFormat) return [];
    const graph=report.graph, lines=new Map();
    for (const row of graph.signature_purposes.rows) {
      const candidate=row.report_reference?.candidates.find(c=>c.doc===doc);
      if (!candidate) continue;
      const cited=report.findings.filter(f=>f.signature_purposes?.includes(row.id));
      const owner=cited.find(f=>f.rule==='H02') || cited[0];
      if (!bind(report,owner,row.id)) continue;
      for (const key of Object.keys(fields)) {
        if (candidate[key]) {const source=printed(candidate,key);lines.set(source.ref,source);}
      }
      for (const [key,item] of Object.entries(row.report_reference.coverage?.report_rows || {})) {
        const source=printed(candidate,key,item);lines.set(source.ref,source);
      }
    }
    return [...lines.values()];
  }
  function reportButton(report,file,source,label,cls='purpose-report-line') {
    const b=action('',()=>{
      if (state.bundle?.report===report) OriginalReader.open(file,1,{lineHint:source.rawLine,rawRef:source.ref,printedSource:source});
    },cls);
    Object.assign(b.dataset,{inspectionLine:source.ref,doc:file.id});
    b.setAttribute('aria-haspopup','dialog'); b.setAttribute('aria-controls','page-dialog'); b.title=source.quote;
    if (label) b.append(label);
    return b;
  }
  function scopePanel(report,ref,file) {
    const c=ref.coverage, candidate=ref.candidates[0], facts=graphIndex(report.graph).facts;
    const block=el('section','','report-scope'); block.setAttribute('aria-label','检测范围对照');
    const heading=el('h6',c.required==null?'验收与检测范围':'合同应检下限 '+c.required+' 台');
    if (c.state==='short') heading.textContent='报告台数比合同下限少 '+c.difference+' 台';
    function basisControl(key,label,cls) {
      const line=c.basis[key], fact=line && facts.get(line.fact);
      if (!fact) return null;
      const b=action('',()=>{if (state.bundle?.report===report) openPage(fact.doc,1,fact.id);},cls);
      b.dataset.inspectionBasis=fact.id; b.title=line.quote;
      b.setAttribute('aria-haspopup','dialog');b.setAttribute('aria-controls','page-dialog');b.append(label);
      return b;
    }
    const tile=(label,value)=>box('report-scope-value',el('small',label),el('strong',value));
    const count=n=>n==null?'待核':n+' 台';
    const received=tile('验收单实收',count(c.received)), tested=tile('报告检测',count(c.reported));
    const compare=box('report-scope-counts',basisControl('accepted',received,'report-scope-tile') || received);
    const measured=c.report_rows.count;
    if (measured) compare.append(reportButton(report,file,printed(candidate,'count',measured),tested,'report-scope-tile'));
    else compare.append(tested);
    block.append(heading,compare);
    const origins=el('div','','report-scope-basis');
    for (const [key,label] of [['clause',c.basis.clause?.value],['ordered',c.ordered==null?'合同交付数量':'合同交付 '+c.ordered+' 台'],
      ['acceptance_scope',c.basis.acceptance_scope?.value]]) {
      const control=basisControl(key,el('span',label || ''),'scope-open-original');
      if (control) origins.append(control);
    }
    if (origins.childElementCount) block.append(origins);
    return block;
  }
  function attachmentPanel(report,ref,rev) {
    const section=el('section','','purpose-report');
    Object.assign(section.dataset,{caseId:report.case_id,rev:String(rev)});
    section.append(el('h5',ref.kind+'核对'));
    if (!ref.candidates.length) {
      section.append(el('p','尚未定位到可核对的报告原页。请检查已交附件，必要时补件。'));
      return section;
    }
    const docs=graphIndex(report.graph).documents;
    for (const candidate of ref.candidates) {
      const file=docs.get(candidate.doc), block=el('div','','purpose-report-file');
      block.append(el('small',file.name+' · 第 1 页'));
      if (ref.coverage) block.append(scopePanel(report,ref,file));
      const keys=candidate.number || candidate.contract || candidate.conclusion ? ['number','contract','scope','conclusion'] : ['title'];
      for (const key of keys) {
        const item=candidate[key] || ref.coverage?.report_rows[key];
        if (!item) continue;
        const source=printed(candidate,key,item), button=reportButton(report,file,source);
        button.append(el('span',source.quote),el('small','第 '+source.rawLine+' 行'),glyph('arrows-angle-expand'));
        block.append(button);
      }
      const download=link('下载报告原件',workpaperSource(file.id,'original'),'scope-open-original');
      download.download=file.name;
      block.append(download); section.append(block);
    }
    return section;
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
      if (row.report_reference) {
        const ref=row.report_reference;
        summary.append(el('small',ref.coverage?'已定位报告 · '+scopeStates[ref.coverage.state]:states[ref.state],'purpose-report-state'));
      }
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
      detail.append(summary);
      if (row.report_reference) detail.append(attachmentPanel(report,row.report_reference,rev));
      detail.append(box('purpose-attributes',list,download));
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
    const attachment=ref.startsWith('inspection-report/');
    const id=attachment ? ref.replace('inspection-report/','signature-purpose/') : ref;
    const owner=finding || report.findings.find(f=>['H01','H02'].includes(f.rule) && f.signature_purposes?.includes(id));
    const proof=bind(report,owner,id);
    if (!proof) return null;
    if (attachment && proof.row.report_reference?.id!==ref) return null;
    const mark=anchor(owner,proof.row);
    const target=Team.hash('case/'+report.case_id+'?'+new URLSearchParams({rev:String(rev),...params(owner)}));
    const where=proof.row.coverage?'修订 '+proof.row.revision+' 签名原因':'签名原因';
    const label=attachment ? proof.row.report_reference.kind+' · '+states[proof.row.report_reference.state] : proof.doc.name+' · '+where;
    return link(label,'/app?walkat='+mark+target,'button ref');
  }
  return {panel,bind,locate,params,citation,reportLines};
})();
