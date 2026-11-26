const IntakeProfiles = [
  {key:'contract',id:'cn-contract-performance/v1',label:'合同履约与分期',documents:['合同','验收单','注明期次的付款回单'],
    checks:['合同签章与生效','交付范围与验收质量','各期付款条件'],
    note:'上传合同、验收单及注明期次的付款回单。分批交付时请附各批验收单。涉及代理、审批、整改或质保时，可附授权委托书、审批记录、复验报告及质保期满确认单。'},
  {key:'purchase',id:'cn-procurement-full-settlement/v1',label:'采购与付款',documents:['采购合同','验收单','发票','付款回单'],
    checks:['合同与验收','发票身份与抬头','全额结算勾稽'],
    note:'核对合同签署、交付验收与付款约定，并勾稽发票及全额结算资料。'},
  {key:'travel',id:'cn-travel-reimbursement/v1',label:'差旅报销',documents:['差旅报销单','具名发票'],
    checks:['报销人与票据','行程及发生日期','申请金额'],
    note:'按一份差旅报销单和所附具名发票勾稽，检查票号、实际发生日期和申请金额。'},
  {key:'payment',id:'cn-bank-contract-payment/v1',label:'付款回单核对',documents:['一份合同','一张银行回单'],
    checks:['收款账户','重复流水','分期累计付款'],
    note:'每个任务上传一份合同和一张银行回单。可核对收款账户、重复流水及全额差额，分期付款可与本企业已签收的回单累计比较。'}
];

function requestedIntakeProfile() {
  const key=new URLSearchParams(location.search).get('new');
  return IntakeProfiles.find(profile=>profile.key===key);
}
