// Resolve the release record and mandate against the same issued case and finding.
const ReleaseEvidence = (() => {
  function fact(graph,finding,ref) {
    const release=finding?.payment_opinion?.release;
    const index=graphIndex(graph);
    if (!ref || !release?.evidence.includes(ref) || !finding.evidence.includes(ref) ||
        !index.supports.get('finding/'+finding.id)?.has(ref)) return null;
    const f=index.facts.get(ref);
    return f?.source_line?.rects?.length && f.source_line.text===f.quote ? f : null;
  }
  function sources(graph,finding) {
    const ledger=graph.payment_release_sources;
    if (!ledger) return [];
    const idx=graphIndex(graph);
    if (!idx.releaseSources) {
      const edges=graph.edges.filter(e=>e.type==='payment_release_basis');
      idx.releaseSources=ledger.lines.flatMap(row=>{
        const page=row.doc+'/p'+row.page;
        const edge=edges.find(e=>e.from===row.unit && e.to===page && e.line===row.line && e.evidence.includes(page) &&
          (row.line || row.facts.some(id=>e.evidence.includes(id))));
        return edge?[{...row,facts:row.facts.filter(id=>edge.evidence.includes(id))}]:[];
      });
    }
    if (!finding) return idx.releaseSources;
    const release=finding.payment_opinion?.release;
    if (!release) return [];
    const refs=idx.supports.get('finding/'+finding.id);
    return idx.releaseSources.filter(row=>{
      const page=row.doc+'/p'+row.page;
      return refs?.has(page) && release.evidence.includes(page) && finding.evidence.includes(page) &&
        release.sources.some(s=>s.unit===row.unit && s.doc===row.doc && s.page===row.page && s.line===row.line && s.quote===row.quote && s.role===row.role);
    }).map(row=>({...row,facts:row.facts.filter(id=>refs.has(id) && release.evidence.includes(id) && finding.evidence.includes(id))}));
  }
  function one(rows,role) {
    const found=rows.filter(s=>s.role===role);
    return found.length===1?found[0]:null;
  }
  function caption(release,rows) {
    if (release.state==='pending' && one(rows,'approval_date') && !rows.some(s=>s.role==='date')) return '缺放行签字日';
    return {matched:'已核具名放行',signer_mismatch:'签发人不符',reference_mismatch:'原验收单号不符',absent:'待补放行单',future:'签字日晚于提交日'}[release.state] || '放行依据待核';
  }
  function stops(phase,notes,graph) {
    const release=phase.payment_opinion?.release;
    if (!release || notes.length!==1) return [];
    const rows=sources(graph,phase), authority=one(rows,'authority');
    const kind={signer_mismatch:'signature',reference_mismatch:'receipt',future:'date'}[release.state];
    const entry=kind?one(rows,kind):release.state==='pending' && !one(rows,'date')?one(rows,'approval_date') || one(rows,'decision'):one(rows,'decision');
    const items=[{key:'hold',label:'暂缓',row:notes[0]}];
    if (authority) items.push({key:'authority',label:'权限',row:authority});
    if (entry) items.push({key:'release',label:'放行单',row:entry});
    return items;
  }
  return {fact,sources,one,caption,stops};
})();
