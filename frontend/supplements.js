function resetIntake() {
  state.intakeParent = null;
  state.key = null;
  $('#upload-form').reset();
  $('#chosen-files').replaceChildren();
  $('#retain-files').replaceChildren(el('legend','沿用前案原件'));
  $('#return-reason').textContent = '';
  $('#upload-error').textContent = '';
  $('#upload-heading').textContent = '新建审计';
  $('#upload-file-label').textContent = '待审资料';
  $('#supplement-fields').hidden = true;
  $('#upload-profile').disabled = false;
  $('#upload-files').required = true;
  profileChanged();
}

function openIntake(parent=null) {
  if ((state.intakeParent?.id || null) !== (parent?.id || null)) {
    resetIntake();
    if (parent) {
      const decision = parent.decisions.find(d=>d.rev===parent.rev && d.decision==='return');
      if (!decision) return;
      state.intakeParent = {id:parent.id,rev:decision.rev};
      $('#upload-heading').textContent = '提交补件';
      $('#upload-title').value = parent.title.slice(0,94)+' · 补件';
      $('#upload-profile').value = parent.profile;
      $('#upload-profile').disabled = true;
      $('#upload-file-label').textContent = '新增或替换的资料';
      $('#upload-files').required = false;
      $('#return-reason').textContent = 'R'+decision.rev+' 退回意见 · '+decision.note;
      $('#supplement-fields').hidden = false;
      for (const doc of parent.documents) {
        const check = el('input');
        check.type='checkbox'; check.checked=true; check.value=doc.id; check.dataset.bytes=String(doc.size);
        const label = el('label','','check-label');
        label.append(check,el('span',doc.name)); $('#retain-files').append(label);
      }
      profileChanged();
    }
  }
  $('#upload-dialog').showModal();
}

function renderSupplementFamily(detail, revision) {
  const panel = $('#supplement-family');
  const parent = detail.supplement_of;
  const children = detail.supplements || [];
  const returned = detail.decisions.some(d=>d.rev===detail.rev && d.decision==='return') && (!revision || revision===detail.rev);
  panel.replaceChildren();
  panel.hidden = !(parent || children.length || returned);
  if (panel.hidden) return;
  const header=box('panel-head',el('h2','补件往来'));
  if (returned) header.append(action('提交补件',()=>openIntake(detail),'button'));
  panel.append(header);
  if (parent) panel.append(Team.paperLink('退回底稿 · '+parent.title+' · R'+parent.rev,parent.id,'source-jump',new URLSearchParams({rev:parent.rev})));
  for (const child of children) panel.append(box('panel-head',
    Team.paperLink(child.title,child.id,'source-jump'),tag(child.status)));
}

function returnComparison(report, revision) {
  const source = report.supplement;
  const panel = box('panel return-comparison',el('h2','前案退回事项'),el('blockquote',source.reason),
    el('small',source.returned_by+' · '+time(source.returned_at)+' · R'+source.rev,'small'));
  if (source.note) panel.append(el('p','补件说明 · '+source.note));
  const originals = new Map(report.graph.documents.map(d=>[d.id,d]));
  const retained = new Set(source.retained.map(r=>r.doc));
  panel.append(fold('本次资料 · 沿用 '+retained.size+' 份，新增 '+(originals.size-retained.size)+' 份',
    ...[...originals.values()].map(d=>box('line',el('span',retained.has(d.id)?'沿用':'新增'),
      link(d.name,workpaperSource(d.id,'original'))))));
  if (source.parent_rule_version!==report.policy.version) panel.append(el('p','前案规则集 '+source.parent_rule_version+'，本次规则集 '+report.policy.version+'。','muted'));
  for (const group of source.comparisons) {
    const open = group.after.filter(f=>f.status!=='ok').length;
    const issues = group.after.filter(f=>f.status==='issue').length;
    const result = !group.after.length ? '本次未执行' : issues ? '本次有 '+issues+' 项问题' : open ? '本次待核 '+open+' 项' : '本次均相符';
    panel.append(lazyFold(group.rule+' '+group.title+' · '+result,()=>[
      ...group.before.map(f=>box('line',Team.paperLink('前案 · '+f.id+' · '+statusName(f.status),source.parent,'source-jump',
        new URLSearchParams({rev:source.rev,finding:f.id})),el('p',f.detail))),
      ...group.after.map(f=>Team.paperLink('本次 · '+f.id+' · '+statusName(f.status),report.case_id,'source-jump',
        new URLSearchParams({rev:revision,finding:f.id})))]));
  }
  const compared = new Set(source.comparisons.map(g=>g.rule));
  const other = report.findings.filter(f=>f.status!=='ok' && !compared.has(f.rule));
  if (other.length) panel.append(lazyFold('本次其他风险与缺口（'+other.length+'）',()=>other.map(f=>
    box('line',Team.paperLink(f.rule+' '+f.title+' · '+statusName(f.status),report.case_id,'source-jump',
      new URLSearchParams({rev:revision,finding:f.id})),el('p',f.detail)))));
  return panel;
}
