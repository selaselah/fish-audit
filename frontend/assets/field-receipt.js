function fieldReceiptOperation(fact, doc, page) {
  const attestation = fact?.attestation;
  const receipt = attestation?.source_check;
  const bundle = state.bundle;
  if (fact?.status !== 'confirmed' || attestation?.decision !== 'confirm' || attestation.fact !== fact.id ||
      !receipt || receipt.format !== 'field-source-v1' || receipt.case_id !== bundle?.report.case_id ||
      receipt.rev !== attestation.rev || !Number.isInteger(receipt.rev) || receipt.rev < 1 || receipt.rev >= bundle.rev ||
      !state.detail?.revisions?.some(r => r.rev === receipt.rev && r.hash === receipt.report_hash) ||
      !doc || doc.id !== fact.doc || doc.sha256 !== fact.source_sha256 || receipt.original_sha256 !== doc.sha256 ||
      !page || page.id !== fact.doc+'/p'+fact.page || page.sha256 !== fact.page_sha256 || receipt.page_sha256 !== page.sha256 ||
      receipt.doc !== fact.doc || receipt.page !== fact.page) return null;
  if (receipt.operation === 'confirm') return 'confirm';
  const edit = fact.amendment;
  if (!['add','correct'].includes(receipt.operation) || !edit?.source_check ||
      edit.target !== fact.id || edit.field !== fact.field || edit.value !== fact.value || edit.quote !== fact.quote) return null;
  const keys = ['format','case_id','rev','doc','page','original_sha256','page_sha256','report_hash','operation','checked_at'];
  return keys.every(k => edit.source_check[k] === receipt[k]) ? receipt.operation : null;
}
