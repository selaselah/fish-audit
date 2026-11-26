const PeerReview = {
  pending: null,

  findingLink(caseId, rev, finding, separate=false) {
    const params = new URLSearchParams({rev:String(rev),finding:finding.id});
    const original = Team.paperLink(finding.rule+' · '+finding.title,caseId,'source-jump',params);
    if (!separate) return original;
    const tab = link('查看依据',original.href,'source-jump');
    tab.target = '_blank'; tab.rel = 'noopener';
    tab.setAttribute('aria-label',finding.rule+' '+finding.title+'，在新页查看依据');
    return tab;
  },

  panel(detail,bundle) {
    const receipt = bundle.report.peer_review;
    if (receipt) {
      const first = receipt.referral;
      const panel = box('panel peer-panel',el('h3','复核依据'),
        el('p',first.reviewer+' 在 R'+first.rev+' 转交复核'),el('blockquote',first.note));
      const href = Team.paperLink('查看转交底稿 R'+first.rev,detail.id,'source-jump',new URLSearchParams({rev:first.rev}));
      panel.append(href,el('h4','复核人核对的发现'));
      const cited = new Set(receipt.findings);
      for (const f of bundle.report.findings.filter(f=>cited.has(f.id)))
        panel.append(box('line',this.findingLink(detail.id,first.rev,f)));
      const record = fold('签收身份与版本存证',el('p','底稿 SHA-256'),el('code',receipt.source_hash),
        el('p','转交意见 SHA-256'),el('code',receipt.referral_hash));
      if (first.workspace==='local') record.append(el('p','此本机演练使用手填签收姓名。','small'));
      else record.append(el('p','转交账号'),el('code',first.actor),el('p','复核账号'),el('code',receipt.resolution.actor));
      panel.append(record);
      return panel;
    }
    const pin = detail.referrals?.find(row=>row.rev===bundle.rev);
    if (!pin) return null;
    const first = detail.decisions.find(row=>row.rev===pin.rev);
    const panel = box('panel peer-panel',el('h3','复核签收'));
    if (pin.resolved_rev) {
      panel.append(Team.paperLink('查看复核签收版 R'+pin.resolved_rev,detail.id,'source-jump',new URLSearchParams({rev:pin.resolved_rev})));
    } else if (Team.current && first.actor===Team.session.user.id) {
      panel.append(el('p','已转交，等待同企业另一位审计人员复核。','muted'));
    } else {
      panel.append(el('p','核对转交意见与原版发现后，记录复核决定。','muted'),
        action('填写复核意见',()=>this.open(detail,bundle,pin,first),'primary'));
    }
    return panel;
  },

  open(detail,bundle,pin,first) {
    this.pending = {url:Team.cases()+'/'+detail.id+'/peer-review',rev:pin.rev,
      report_hash:pin.report_hash, signoff_hash:pin.signoff_hash};
    $('#peer-form').reset(); $('#peer-error').replaceChildren();
    $('#peer-decision option[value="approve"]').disabled=false;
    $('#peer-origin').textContent = detail.title+' · R'+pin.rev+' · '+first.reviewer+' 转交：'+first.note;
    $('#peer-reviewer').value = Team.current ? Team.session.user.name : '';
    $('#peer-reviewer').readOnly = !!Team.current;
    const list = $('#peer-findings'); list.replaceChildren();
    const found = bundle.report.findings;
    const row = finding=>{
      const label = el('label','','check-label');
      const input = el('input'); input.type='checkbox'; input.value=finding.id;
      label.append(input,el('span',finding.rule+' · '+finding.title+' · '+statusName(finding.status)));
      return box('peer-finding',label,this.findingLink(detail.id,pin.rev,finding,true));
    };
    const exceptions = found.filter(f=>f.status!=='ok');
    const matching = found.filter(f=>f.status==='ok');
    list.append(...exceptions.map(row));
    if (matching.length && exceptions.length) list.append(fold('相符的程序（'+matching.length+'）',...matching.map(row)));
    else list.append(...matching.map(row));
    $('#peer-dialog').showModal();
  },

  bind() {
    $('#peer-form').addEventListener('submit',async event=>{
      event.preventDefault();
      const pending = this.pending;
      if (!pending) return;
      const findings = [...$('#peer-findings').querySelectorAll('input:checked')].map(input=>input.value);
      const error = $('#peer-error'); error.replaceChildren();
      if (!findings.length) { error.textContent='请勾选至少一项已核对的审计发现。'; return; }
      const submit = $('#peer-submit'); submit.disabled = true;
      try {
        const {url,...pins} = pending;
        const saved = await post(url,{...pins,findings,decision:$('#peer-decision').value,
          reviewer:$('#peer-reviewer').value,note:$('#peer-note').value});
        $('#peer-dialog').close(); chooseRevision(saved.rev); state.tab='report'; await refresh();
      } catch (failure) {
        if (failure.paymentSource) {
          showPaymentSourceError(error,failure);
          return;
        }
        if (failure.invoiceHistory || failure.incompleteNumbers) {
          const decision=$('#peer-decision');
          decision.querySelector('option[value=approve]').disabled=true;
          decision.value='';
          showInvoiceReviewConflict(error,failure);
          error.append(action('选择退回补件',()=>{
            $('#peer-decision').value='return'; $('#peer-note').focus();
          },'text-button'));
          return;
        }
        error.textContent = failure.message;
        if (failure.status===409) error.append(' ',action('查看最新底稿',async()=>{
          $('#peer-dialog').close(); chooseRevision(); await refresh();
        },'text-button'));
      } finally { submit.disabled=false; }
    });
  },
};
