// The issued procedure supplies the names. Bind each displayed row to the cited physical record.
const AcceptanceRoster = (() => {
  const sameText=(a,b)=>typeof a==='string' && typeof b==='string' && a.normalize('NFKC').trim()===b.normalize('NFKC').trim();
  function bind(item,report) {
    const entry=item.acceptance_authority, graph=report.graph, ledger=graph.acceptance_authority_sources;
    if (item.rule!=='H02' || !entry || !/^named-acceptance-signatures-v[1-5]$/.test(ledger?.format) ||
        report.policy?.acceptance_authority!==ledger.format || !['single','joint'].includes(entry.mode) ||
        !entry.records?.length || ledger.clauses?.length!==1 || entry.clause_evidence?.length!==1) return null;
    const rows=new Map(PerformanceIndex.originals(item,graph).map(row=>[row.fact.id,row]));
    const index=graphIndex(graph), kinds=graph.documents_by_kind, cited=new Set(traceReferences(graph,item));
    function source(raw,field) {
      const bound=rows.get(raw.fact);
      if (!bound?.line || !raw.native || raw.facts?.length!==1 || raw.facts[0]!==raw.fact) return null;
      const {doc,fact,line}=bound;
      if (fact.field!==field || fact.doc!==raw.doc || (fact.unit || fact.doc)!==raw.unit ||
          fact.page!==raw.page || line!==raw.line || !sameText(raw.quote,fact.source_line.text) ||
          !sameText(raw.quote,fact.quote) || !/^[a-f0-9]{64}$/.test(doc.sha256) ||
          !/^[a-f0-9]{64}$/.test(fact.page_sha256)) return null;
      return {ref:fact.id,file:doc.name,page:fact.page,line,quote:fact.source_line.text,
        rects:fact.source_line.rects,thumbnail:()=>EvidenceCompare.pageThumbnail(fact,index),
        excerpt:()=>EvidenceCompare.lineExcerpt(fact,index),open:()=>openPage(doc.id,fact.page,fact.id)};
    }
    const clause=ledger.clauses[0], contract=source(clause,'acceptance_signing_clause'), required=entry.required;
    if (!contract || clause.fact!==entry.clause_evidence[0] || !kinds.contract?.includes(clause.unit) ||
        !entry.units?.includes(clause.unit) || !entry.evidence?.includes(clause.fact) ||
        !Array.isArray(required) || required.length!==(entry.mode==='joint'?2:1) || new Set(required).size!==required.length ||
        !required.every(name=>typeof name==='string' && name.length)) return null;
    // Compare the whole name span to the issued list, including short names embedded in longer names.
    const body=clause.quote.normalize('NFKC').split(':').slice(1).join(':').trim().replace(/。$/u,'');
    const printed=body.match(/^(?:终验及整改复验|最终验收及整改复验|终验|最终验收)(?:均)?(?:须|应)?由(.+?)(共同)?签[字名]确认$/u);
    const named=printed?.[1] || body;
    if (Boolean(printed?.[2])!==(entry.mode==='joint') ||
        JSON.stringify(entry.mode==='joint'?named.split(/[、与和]/u).map(n=>n.trim()):[named.trim()])!==JSON.stringify(required)) return null;
    const stageItems=report.findings.filter(f=>f.rule==='H04' && f.stage?.clause_ref);
    const records=[];
    for (const record of entry.records) {
      if (!['acceptance','reinspection'].includes(record.role) || !['ok','risk','missing'].includes(record.status) ||
          !(kinds.acceptance || []).concat(kinds.reinspection || []).includes(record.unit) ||
          records.some(r=>r.unit===record.unit)) return null;
      const pages=ledger.pages.filter(p=>p.unit===record.unit), signatures=ledger.signatures.filter(s=>s.unit===record.unit);
      const reinspection=kinds.reinspection?.includes(record.unit) || graph.facts.some(f=>(f.unit || f.doc)===record.unit &&
        ['original_acceptance','repair_number','defect_closure'].includes(f.field));
      if (!entry.units.includes(record.unit) || (record.role==='reinspection')!==Boolean(reinspection) ||
          !pages.length || pages.some(p=>!cited.has(p.doc+'/p'+p.page)) || !Array.isArray(record.signed) ||
          signatures.length!==record.signed.length) return null;
      const doc=index.documents.get(pages[0].doc);
      if (!doc?.sha256 || index.nodes.get(doc.id)?.sha256!==doc.sha256 ||
          pages.some(p=>p.doc!==doc.id || !/^[a-f0-9]{64}$/.test(index.nodes.get(p.doc+'/p'+p.page)?.sha256))) return null;
      const signed=[], seen=new Set();
      for (const raw of record.signed) {
        const witness=signatures.find(s=>s.fact===raw.fact), row=source(raw,'acceptance_signer');
        const name=raw.quote?.normalize('NFKC').match(/^[^:]+:\s*([^:()]+?)\s*\(\s*已签[字名]\s*\)\s*$/u)?.[1];
        const place=raw.doc+'/p'+raw.page+'/l'+raw.line;
        if (!row || !witness || !sameText(name,raw.name) || typeof raw.confirmed!=='boolean' ||
            seen.has(place) || !record.evidence.includes(raw.fact) ||
            !pages.some(p=>p.doc===raw.doc && p.page===raw.page) ||
            !['unit','doc','page','line','name','confirmed','native','quote'].every(k=>witness[k]===raw[k])) return null;
        const fact=rows.get(raw.fact).fact, att=fact.attestation, check=att?.source_check;
        if (raw.confirmed && (fact.status!=='confirmed' || att?.decision!=='confirm' || att.fact!==fact.id || !check ||
            check.doc!==raw.doc || check.page!==raw.page || check.original_sha256!==doc.sha256 ||
            check.page_sha256!==fact.page_sha256 || check.case_id!==report.case_id)) return null;
        seen.add(place); signed.push({name:raw.name,confirmed:raw.confirmed,source:row});
      }
      const confirmed=new Set(signed.filter(s=>s.confirmed).map(s=>s.name));
      const missing=required.filter(name=>!confirmed.has(name)), others=[...confirmed].filter(name=>!required.includes(name));
      if (JSON.stringify(missing)!==JSON.stringify(record.missing_names) ||
          JSON.stringify(others)!==JSON.stringify(record.other_names)) return null;
      const phases=[];
      for (const finding of stageItems) {
        const lines=PerformanceIndex.originals(finding,graph);
        const citedFields=new Set(lines.map(l=>l.fact.id));
        if (!citedFields.has(clause.fact) || !signed.length || !signed.every(s=>citedFields.has(s.source.ref))) continue;
        const stage=finding.stage, term=lines.find(l=>l.fact.id===stage.clause_ref);
        if (!term?.line || term.fact.field!=='payment_stage' || (term.fact.unit || term.fact.doc)!==clause.unit ||
            !term.fact.source_line.text.normalize('NFKC').includes(stage.clause.normalize('NFKC'))) continue;
        phases.push({name:stage.name,status:finding.status,source:{ref:term.fact.id,file:term.doc.name,page:term.fact.page,
          line:term.line,quote:term.fact.source_line.text,open:()=>openPage(term.doc.id,term.fact.page,term.fact.id)}});
      }
      records.push({unit:record.unit,file:doc.name,role:record.role,status:record.status,detail:record.detail,signed,phases});
    }
    return {contract,required,mode:entry.mode,records};
  }
  return {bind};
})();
