# 合同付款批注与财务复核交互

## 采购放行的身份与签署版本

《企业内部控制应用指引第 7 号》第十三条要求付款审核结合预算、合同、单据凭证及审批程序。演练合同自行约定第二期暂缓须由指定人签字解除。项目据此分别留存合同授权条款、验收原单、放行单签认栏和付款日期。[财政部采购业务应用指引，第 30 页](https://kjs.mof.gov.cn/zhengcefabu/201005/P020230421440664863663.pdf#page=30)

《电子签名法》第十三条涉及制作数据与签名人的关系、签署时的控制以及对后续改动的可发现性，第十四条规定可靠电子签名的法律效力。项目核对签名对 PDF 修订的覆盖范围，保留证书摘要，并交由审计员补核实际签署人、代表权限及审批链。公开 PDF 采用自签测试证书。[《中华人民共和国电子签名法》](https://ynca.miit.gov.cn/zwgk/zcwj/flfg/art/2022/art_a6ec461de9174d6b87ef092d15615652.html) · [PDF 签名核验技术资料](pdf-signature-review.md)

## 核对同一协议的排印内容与审阅记录

2026 年 11 月 27 日查阅。Microsoft Word 将批注与所选文字关联，修订可逐项接受或拒绝。本项目把 Word 的原生选区和批注正文并排出示，分别核对提交文件与打印页摘要。相同的打印页仍可来自不同的审阅版本。[Word 批注与修订](https://support.microsoft.com/en-us/word/give-and-receive-feedback-in-word) · [接受或拒绝修订](https://support.microsoft.com/en-us/word/training/accept-tracked-changes)

Workiva 支持从文档历史选两版比较，并切换修订展示方式。DataSnipper 的 Alwin 支持从工作簿打开对应原件，点击高亮位置选择相关单元格，并用箭头逐条核查多个证据位置。Fish Audit 在首页使用物理行顺序的前后导航，在底稿中保留独立的条款、批注和签章栏入口。定位结果须能回到本版留存的文件或页图。[Workiva 版本对照](https://support.workiva.com/hc/en-us/articles/360036002711-Create-and-view-document-blacklines) · [DataSnipper 证据核查](https://knowledge.datasnipper.com/en/articles/882479-how-to-review-a-task-s-output-in-alwin)

## 补充协议的签署版本与原文对照

Adobe Acrobat 允许在签名面板中打开签名属性和证书，另有比较已签修订的入口。Docusign 将签署参与者、动作和时间留在交易历史与完成证书中。本项目据此把文件覆盖范围、身份与授权、归档原行做成独立的检查入口。演练里的 349 字节是从两份水印 PDF 长度和签名范围得到的实际差值。[Adobe 签名属性与证书](https://helpx.adobe.com/acrobat/desktop/e-sign-documents/manage-digital-signatures/validate-digital-sign.html) · [Acrobat 比较已签版本](https://helpx.adobe.com/acrobat/desktop/e-sign-documents/manage-digital-signatures/compare-versions.html) · [Docusign 交易记录与完成证书](https://www.docusign.com/trust/security/transaction-data-use)

Adobe Spectrum 的标签控件用横线或竖线指示当前项。首页把同一采购的合同、验收、回单放在同一组选项下，手机使用蓝色底线和选中状态。橙色只用于待核提示，合同数字或文字的变化在原文中标出。[Spectrum Web Components 标签控件](https://opensource.adobe.com/spectrum-web-components/components/tabs/)

民法典第五百四十三、五百四十四条涉及合同变更的协商一致及内容约定不明确的情形。电子签名法第十三、十四条涉及可靠电子签名及其法律效力。项目据此提示核对双方是否同意及电子签署依据。具体条款、日期与付款前提取自提交的合同、补充协议和回单。[最高法公布的《民法典》](https://www.court.gov.cn/zixun/xiangqing/233181.html) · [工信部公布的《电子签名法》](https://shca.miit.gov.cn/xxgk/flfg/gjfl/art/2020/art_6c628dbd51254637b385f3d7f46aa58d.html) · [水印资料与签发底稿](../docs/acceptance.md#补充协议签署柜温标准与验收款收票前提)

## 付款日与银行保函期间

洛阳市政府采购中心的预付款担保格式将生效与预付款实际支付相联系，将终止与进度付款证书载明扣清预付款相联系。这类文本需要事件凭证。本项目只有在提交的具体合同要求按日期比较、保函也清楚载明日期时，才将首笔实际付款放入该期间核对。[采购文件「附件9 预付款担保」](https://gongyi.zfcg.henan.gov.cn/cmsweb81e27e/luoyang/rootfiles/2025/08/27/f64130d012bc478386fb54fc8efe9332.pdf)

SAP 的银行保函展期流程可以修改期限和到期日。演练中出现待确认的展期申请时，审计程序保留原函日期，单独列出需向开立机构核验的展期凭证。界面参考 SAP Fiori 甘特图的时间比例和里程碑符号，使用区间带表示原函期间、菱形标记实际付款日。[SAP 银行保函展期](https://help.sap.com/docs/s4hana-cloud-best-practices/bank-guarantee-management-2nz-kw/rollover-bank-guarantee) · [SAP Fiori 时间轴和里程碑](https://www.sap.com/design-system/fiori-design-web/v1-145/ui-elements/gantt-chart)

Stripe Dashboard 支持搜索并跳转到账单、付款等具体资源。首页的「查找案例」借鉴了从搜索结果直接打开业务对象的交互。搜索框内保留输入焦点，方向键移动结果，回车打开，Esc 取消。组合框的活动选项遵循 WAI-ARIA 的键盘模式。[Stripe Dashboard 搜索](https://docs.stripe.com/dashboard/search) · [W3C 组合框交互](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/)

## 预付款保函的收取

洛阳市政府采购中心一份货物采购文件在合同第五条约定，采购人收到与预付款等额的银行保函后支付合同价款的 80%，安装调试和验收合格后再处理保函退还和余款。这个项目说明付款条件可以随期次变化。演练中的 30% 及其受益人条款均来自合成合同，实际案件按各自提交的约定审查。[采购文件，第五条付款方式](https://sqsmqx.zfcg.henan.gov.cn/cmsweb35rc67w/lyslnx/rootfiles/2026/11/25/eec6bed0c0a2480b9692f5cd1a63edc7.pdf)

SAP 在收到银行保函后，由资金专员在 Fiori 中登记该份保函及交易对手。本项目将收函作为单独的审计事件，按本期单据展示开立、签收、银行付款三种日期。点选日期、单位或编号可以检查记载该事实的原件。[SAP 收取银行保函](https://help.sap.com/docs/s4hana-cloud-best-practices/bank-guarantee-management-2nz-kw/receive-bank-guarantee-1be4b6c5308d47aea4c688cc6450f6fc?locale=en-US&state=PRODUCTION&version=2608)

## 合同批注与分期复核

Microsoft 的 Open XML 文档说明正文中的评论引用如何通过同一标识连接范围起点、终点和批注正文。Word 的上下文视图把批注放在原文旁，选择批注会定位所选文字。项目保留 DOCX 的选区、署名、批注部件摘要以及单独渲染的打印行，两份记录均可回查。[Microsoft 评论引用](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.commentreference?view=openxml-3.0.1) · [Word 上下文批注](https://support.microsoft.com/en-us/word/using-modern-comments-in-word)

Docusign 的合同审查把疑点链接到具体条款，由审阅者判断修订建议。FloQast 的对账工作区将支持材料、复核意见和签收记录与对应事项放在一起。本项目据此把“第二期付款条件”和“第二期实付时点”做成独立原件入口，让审计人员直接从期次进入该版本的底稿。[Docusign 合同审查](https://www.docusign.com/company/news-center/docusign-introduces-ai-contract-review-assistant-to-streamline-agreements-workflows) · [FloQast 对账与复核](https://www.floqast.com/close-management/products/account-reconciliations)

公开演示使用本项目生成的冷藏柜采购合同和银行回单。两份原件、页图和支付比例都来自同一份演练底稿。示例中的合成单位、署名和水印均保留在下载件中。[水印资料生成器](../docs/samples/contract_comments.py) · [演示数据与原件摘要](../frontend/assets/contract-comment-sample.json) · [验收记录](../docs/acceptance.md#合同分期付款批注)

## 质保确认与维修记录的取证参考

中国注册会计师审计准则第 1301 号第十五条要求，在不同来源的证据存在差异时判断需要追加哪些审计程序。应用指南第 57 段还涉及重大事项中差异处理的记录。本项目据此将确认单原行、关联工单及需补查的关闭签认留在同一项发现中。合同约定、实际维修进度和付款依据各自需要相应原件。[中注协发布的审计准则第 1301 号，第十五条](https://www.cicpa.org.cn/ztzl1/Professional_standards/xxzztx/zyzz/sjzz/202105/P020240412542695263912.pdf#page=4) · [第 1301 号应用指南，第 57 段](https://cicpa.org.cn/xxfb/tzgg/202304/W020230410260829897530.pdf#page=17)

IBM Maximo 的工单应用把单张工单的状态、附件和处理历史放在可选择的记录中。SAP Fiori 的 Filter Bar 支持使用状态条件筛选列表。这里允许审计员按差异筛选工单，选中后就地打开原始记录。[IBM Maximo Work Orders](https://www.ibm.com/docs/en/masv-and-l/maximo-manage/cd?topic=module-work-orders-application) · [SAP Fiori Filter Bar](https://www.sap.com/design-system/fiori-design-web/v1-139/ui-elements/filter-bar)
