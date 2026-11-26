# 审计与会计软件的公开界面

## 验收决定与原件

Ramp Bill Pay 的审阅流程允许审批人在手机上查看单据、选择处理结果，并在退回时写明原因。Fish Audit 将这种直接操作用于底稿验收。选定「退回补件」后，表单显示「需补资料与原因」。财务人员另行点确认，决定和意见一同归入当前底稿版本。原图核验有单独的字段级记录。[Ramp 官方审批说明](https://support.ramp.com/bill-pay-approvals/)

决定卡使用同名的原生单选输入。Tab 进入和离开选项组，方向键可切换选项，触屏可点整张卡片。系统给出的审计建议另行展示，打开验收表单时由审计员选择本次决定。[W3C 单选组键盘模式](https://www.w3.org/WAI/ARIA/apg/patterns/radio/) · [手机验收实拍](../docs/interaction-design/signoff-decisions-mobile.webp)

## 从本期付款查到本批收货

Microsoft Dynamics 365 Finance 允许应付会计选择采购收货单，再打开匹配明细。Fish Audit 将这一做法用于分批履约。审计员先选付款期，再在合同约定、本批验收单之间切换。每个可核字段保留文件、页码和行号。该参考用于交互设计，审计依据来自具体底稿的原件。[Microsoft Dynamics 365 Finance 采购收货匹配流程](https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/tasks/record-vendor-invoice-match-against-received-quantity)

SAP Fiori 的列表与详情布局会随所选记录更新详情，在较窄屏幕上调整可见列。底稿沿用同一期次选择，桌面显示检查清单和该项凭据，手机将清单收为期次选择器。关闭原件后，焦点回到触发它的字段。[SAP Fiori Flexible Column Layout](https://www.sap.com/design-system/fiori-design-web/v1-154/page-types/page-layouts/flexible-column-layout)

## 在单据上选择字段

DataSnipper 将工作底稿的检查项目链接到原始凭证，复核人可以沿链接重看证据。Dext 按单据类型说明哪些字段可以提取，审阅时可以把提取值与原件对照。Fish Audit 将这两种操作用于同一笔采购。在合同、验收单和银行回单之间切换时，页签下方列出这份文件可定位的原行。查看整页后也可以直接点选标线。页面上的图和读数都取自本项目的水印演练资料。[DataSnipper 审计程序与原始凭证](https://knowledge.datasnipper.com/en/articles/685955-how-to-document-your-audit-procedures-with-datasnipper) · [Dext 单据类型和提取字段](https://help.dext.com/en/articles/416691-what-information-does-dext-extract-from-costs-and-sales-documents) · [演练原件登记](showcase-provenance.md#首屏三份原件与九个字段)

## 从审计引文翻到相邻原页

DataSnipper Alwin 把证据片段在当前组里的位置放在阅读器中，点击位置可展开清单，再回到对应片段。Adobe Acrobat 提供逐页翻阅、按页码直达和返回先前视图。Fish Audit 采用可展开的页码控件，同一份原件连续翻页，一键回到进入时的审计引文。[DataSnipper 任务结果复核](https://knowledge.datasnipper.com/en/articles/882479-how-to-review-a-task-s-output-in-alwin) · [Adobe Acrobat 页间导航](https://helpx.adobe.com/acrobat/desktop/get-started/learn-the-basics/navigation.html)

Ramp 的账单查看器把旋转、缩放和下载原件放在单据旁。Fish Audit 的原件入口采用白底文件列表，蓝色标识当前物理页，字段另用文字标明「已匹配文字层」「待核原图」等证据状态。[Ramp 账单与原始凭证](https://support.ramp.com/managing-bills-and-payments-on-bill-pay/) · [颜色参考](interface-color.md)

## 在合同正文和付款续页之间定位

Adobe Acrobat 的页面缩略图用于在长文档中识别和切换物理页。Fish Audit 保留真实页形，缩略图旁列出各页载明的期次。发现编号不符时，正文与续页的号码同时显示，审计员可切换原图与字符差异，打开所据页和行。全部展示素材均为本项目的水印演练件。[Adobe Acrobat 页面缩略图与书签](https://helpx.adobe.com/acrobat/using/page-thumbnails-bookmarks-pdfs.html) · [本例原件登记](showcase-provenance.md#付款续页案例-r10)

## 选择审计范围和核对运行时段

Caseware Cloud 的立项入口先选业务应用，再填写项目资料。IBM Carbon 的单选卡片允许整块选择，并保留单选标识。Fish Audit 把四种范围直接放在「新建审计」中，每块仅显示业务名称和所核凭证。产品首页的合同案例入口预选履约审计，资料要求可按需展开。[Caseware 项目创建流程](https://www.caseware.com/docs/en/cloud/caseware-cloud/engagement-management/planning/create-and-set-up-an-engagement-file) · [IBM Carbon 单选卡片](https://www.carbondesignsystem.com/building-blocks/core/components/tile/guidelines)

Grafana 的状态时间线用区间描述对象状态，并保留缺数的空档。Fish Audit 参考这一呈现方式，按签认运行记录的实际起止绘制时段。蓝色对应原件所载无异常，断档和故障分别使用不同纹理、标记与文字。断档可直接核对前一行的截止和后一行的起始。连续时长、付款判断和原件定位由本项目实现。[Grafana 状态时间线](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/state-timeline/)

## 逐份翻阅一个业务对象的凭证

DataSnipper 的复核操作可由工作表的引用回到证据文件中的对应页与位置。Fish Audit 在“按业务对象”中采用相同的取证动作。切换合同号或单位后，只展示所选单据的一处原文。点击“对照原行”可以核对实际印刷图像。所用原图均来自本地水印案例。[DataSnipper 官方复核说明](https://knowledge.datasnipper.com/en/articles/685955-how-to-document-your-audit-procedures-with-datasnipper)

IBM Carbon 的内容切换器适用于在同一屏位置切换相关视图。Fish Audit 用它切换审计发现与业务对象，以及等待期核对中的合同、整改和复验依据。Ironclad 的合同义务工作台按状态、类型和到期日组织义务，本项目在具体付款期旁展示实际待核的等待条件和凭据。[IBM Carbon 内容切换器](https://www.carbondesignsystem.com/building-blocks/core/components/content-switcher/guidelines) · [Ironclad 合同义务工作台](https://support.ironcladapp.com/en-us/articles/18170710-obligations-dashboard)

## 整改复验与原件核对

Procore Punch List 把整改执行、提交复核、待关闭和关闭列为不同状态。Fish Audit 在做合同履约审查时，保留原验收、整改、复验各自的记录。最终报告上的关闭文字仍须对应到具体缺陷与措施。[Procore 整改项工作流说明](https://support.procore.com/faq/how-does-the-punch-list-workflow-affect-my-existing-punch-list-items)

GOV.UK Design System 将标签页用于经常操作的办案系统，并指出跨标签来回记忆不适合比较。工作底稿按阶段切换，同一页的签认结论和保留事项直接并列。已有双原件对照入口仍用于跨文书核查。方向键、Home、End 的操作参考 W3C 标签页模式。[GOV.UK 标签页](https://design-system.service.gov.uk/components/tabs/) · [W3C Tabs Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/)

## 搜索当前底稿和按日期核对付款

QuickBooks Online 的顶部搜索可查交易、操作和报告，支持按单号、交易类型等关键词定位。Fish Audit 在工作台提供一处「快速定位」入口，审计员可按规则编号或原件名称进入选定版本。桌面支持快捷键，手机可直接点放大镜。Ramp 的 Bill Pay 按不同业务日期提供筛选，包括账单日、发送日和到账日。Fish Audit 的首款凭证控件使用本案实际具备的两个时点，即案件提交日和某一张验收款回单的实付日。不同日期下展示不同的首款凭证金额。 [Intuit 搜索说明](https://quickbooks.intuit.com/learn-support/en-us/help-article/bank-transactions/search-transactions-quickbooks-online/L4hBemuUP_US_en_US) · [Ramp Bill Pay 操作说明与画面](https://support.ramp.com/managing-bills-and-payments-on-bill-pay/)

## 从单台设备读数查到凭证

DataSnipper 的审阅界面允许从结果单元格直接打开相应来源。一项结果有多个片段时，审阅者可以逐条切换。Fish Audit 将这项操作用于验收单。选择设备编号后可以逐条打开读数，同一设备重复测温时保留两个原件入口。选中缺记录的设备则可核对验收清单和合同条款。中性的灰蓝承载正常数据，钴蓝表示选中，超限与缺项同时用颜色和文字提示。[DataSnipper 官方审阅说明](https://knowledge.datasnipper.com/en/articles/882479-how-to-review-a-task-s-output-in-alwin) · [Fish Audit 交互实拍](../docs/interaction-design/README.md#按设备检查验收记录)

## 扫描附件按原页核对

Acrobat 使用页面缩略图导航长文档，可从小图直接进入对应物理页。本项目把页码、真实缩略图和文件名放在签章栏旁。甲乙方分别回传不同页时，切换签署方会显示该方的用印页。两页对照沿用固定版底稿中的两条引文。电子正文有可验证坐标时，可看原行。扫描件按整页展示。[Adobe Acrobat 页面缩略图](https://helpx.adobe.com/acrobat/using/page-thumbnails-bookmarks-pdfs.html) · [工作台实拍](../docs/interaction-design/README.md#扫描用印页)

## 从名称差异回到合同原行

Ramp 的采购订单匹配把核对摘要放在账单行上方，实际匹配仍落实到具体的采购行。Acrobat 的文档比较以高亮标出差异，读者可选择单个差异查看它所处的原文。Fish Audit 借用了这两个操作习惯。审计员先选择甲方或乙方，纵向对齐同一方的几个单位名称，仅给有差异的字加琥珀色底和下划线。点击该行即可核查对应原件。首页使用独立的水印合同演示这次操作。[Ramp 采购订单与账单行匹配](https://support.ramp.com/importing-and-matching-purchase-orders-pos-on-ramp-bill-pay/) · [Acrobat 文档比较](https://helpx.adobe.com/acrobat/using/compare-documents.html) · [本地界面与实拍](../docs/interaction-design/README.md#签章主体对照)

## 拍照凭证的阅读方向

Acrobat 的阅读视图可顺时针或逆时针转动页面，每次 90°，也可按页宽或放大比例阅读。Fish Audit 在固定版原件查看器上采用这两项操作。审计员把横置照片转正后可以放大核对状态栏，同一份原件在另一台设备上仍从归档方向打开。[Adobe Acrobat 调整页面视图](https://helpx.adobe.com/acrobat/using/adjusting-pdf-views.html) · [本机拍照凭证演练](../docs/acceptance.md#拍照与扫描工单的原页和签认)

## 维修工单与两份原件的核对

Zendesk 将报修受理、等待处理、已解决和已关闭分别记录。Fish Audit 从上传工单上读取状态原文，在合同要求清结缺陷时，把「待维修」与期满确认单上的「无未关闭缺陷」同时摆到审计员面前。多单同案时优先展示有风险的工单，可以按工单号切换。[Zendesk 工单生命周期](https://support.zendesk.com/hc/en-us/articles/8263915942938-About-the-ticket-lifecycle-and-ticket-statuses)

Acrobat Pro 的比对视图并排显示两个版本，在对应位置高亮差异。本项目将这种原件对照用于不同种类的业务凭证。回单早于工单关闭时，两个窗口分别打开回单付款日和工单关闭日，保留页码、印刷行和底稿版本。[Adobe Acrobat 文件对照](https://helpx.adobe.com/acrobat/using/compare-documents.html) · [本项目的工单交互](../docs/interaction-design/README.md#维修工单)

财政部对采购业务内部控制的解读说明了采购验收和付款审核的联系。演练中「缺陷清结后返还质保金」取自虚构合同，核对时同时追溯该案的原始条款、确认单、维修工单和回单。[财政部会计司《企业内部控制应用指引第7号——采购业务》解读](https://kjs.mof.gov.cn/zhengcejiedu/201006/t20100611_322435.htm)

## 合同义务与质保时点

Ironclad 的 Obligations Dashboard 可按义务状态、类型和截止日查看合同义务，也能筛出待核验事项。Fish Audit 把这两个问题放在一期质保金里分别回答。合同条件是否具备看 H04，成功回单在提交时能否支持实付看 H05。[Ironclad 义务工作台](https://support.ironcladapp.com/en-us/articles/18170710-obligations-dashboard)

Asana Timeline 在日期标尺上用菱形表示里程碑。本项目用菱形表示根据合同推算的质保末日，圆点表示凭证所列日期。审计员可切换全程和提交日前后七天，选择日期后直接核对当版原件。深蓝与琥珀色沿用工作台的证据和风险配色，形状、日期差和文字提供同样的信息。[Asana 官方时间线说明](https://help.asana.com/s/article/plan-and-execute-projects-with-timeline) · [Fish Audit 交互设计](../docs/interaction-design/README.md#质保金时点)

每项记录给出厂商原页、查看位置和查阅日。「画面」来自公开截图或动图，「操作说明」来自对应的帮助正文。「本地用法」说明国内中小企业的采购员、会计或复核人可以如何处理一笔业务。观察范围限于这些公开资料。

## 合同关键日期与授权期间

2026-11-25 查阅 Docusign Agreement Manager 的属性说明。生效、到期和续约通知各有独立定义。Fish Audit 将合同签约、委托书出具和授权起止列为四个来源，签发与签约即便同日也各有自己的原件入口。[Docusign 的协议数据定义](https://support.docusign.com/s/document-item?bundleId=pqz1702943441912&language=en_US&topicId=uwk1702945852405.html)

Adobe React Spectrum 的 RangeCalendar 以月网格展示连续日期区间。Fish Audit 采用月视图显示能从本案原件核实的授权期间，点击有凭证的日期便可阅读对应印刷行。日期和区间取自固定版底稿。[Adobe RangeCalendar](https://react-spectrum.adobe.com/RangeCalendar) · [本地月历实拍](../docs/interaction-design/mandate-calendar-issuance.webp)

## 付款条款与原件定位

ApprovalMax 的 NetSuite 审批报告按时间记录经办审批的人及相应时间戳。Fish Audit 用相同的提问审查采购原件。选中一期可核对合同指定人和实际签认人，再沿时间线查放行与实付。企业上传的两张凭证如只记同一日期，两项共用一个日期位置，界面提示补核时分。[ApprovalMax 官方报告说明](https://support.approvalmax.com/en/articles/457333-how-audit-reports-work-in-approvalmax-for-netsuite) · [本项目时间线](../docs/interaction-design/payment-release-dates.webp)

2026-11-25 查阅 Adobe Acrobat 的文件比较说明。并排模式将旧文件放在左侧、新文件放在右侧，可显示或隐藏差异标记。Fish Audit 的「对照新旧条款」沿用这个阅读顺序。只有两条已定位原行在去掉明确的字段名后可逐字验证一段新增文字，右栏才提供标记开关。[Adobe 官方操作说明](https://helpx.adobe.com/acrobat/using/compare-documents.html) · [本地实拍](../docs/interaction-design/payment-clause-diff.webp)

DataSnipper 的 Alwin 帮助说明展示了从选定单元格定位到原件对应位置，也可从原件选中相应单元格。首页演练选用其中的单向操作，点击验收结论、检验依据或实测值，立即切到同一页的对应原行，并可放回整页核查上下文。[DataSnipper 官方操作说明](https://knowledge.datasnipper.com/en/articles/882479-how-to-review-a-task-s-output-in-alwin) · [R7 页图及字段出处](showcase-provenance.md#展示原件)

## Karbon · 工作清单与看板

Karbon 的客户入职指南末页展示了事务所的容量看板。桌面按负责人分列，列头标件数，卡上保留任务名称与流程状态。其 2026-11-23 发布说明还介绍了工作清单和看板中的筛选标签。Fieldguide 的请求清单支持分组，点一条任务可在侧栏核对详情。查阅日期为 2026-11-25。[Karbon 指南末页的看板](https://assets.ctfassets.net/2wd1w7hp7waa/3iNm7OuDbSMWsHkMfu4xjd/05872a25e95083b64d1abb8ece37f998/The_Definitive_Guide_to_Client_Onboarding_by_Karbon.pdf) · [Karbon 发布说明](https://karbonhq.com/en-GB/release-notes/nov-23-2026/) · [Fieldguide 请求管理](https://help.fieldguide.io/en/articles/7207259-managing-requests)

Fish Audit 在同一检索范围下提供建议看板与任务台账。卡片据底稿分组，点列底可以逐页查看全部命中项。卡片保留底稿版本和人工处理状态。切换视图、分组或速览均为读取操作，签收须在底稿上登记意见。[看板实拍与交互](../docs/interaction-design/README.md#任务队列与资料提交)

## DataSnipper · 底稿单元格如何指向证据

荷兰，查阅于 2026-11-25。审计留档帮助页标注 2026-07-06，可查看审计复核、文档保留及按测试类型分工的表格。[How to document your audit procedures with DataSnipper](https://knowledge.datasnipper.com/en/articles/685955-how-to-document-your-audit-procedures-with-datasnipper)

- **画面**　补充帮助页的 Text Snip 动图中，左侧是 Excel 测试明细，右侧是发票查看器，顶部保留插件工具栏。动图后段发票金额有选框，左侧对应单元格填入金额。[How to add a Text Snip to a document](https://knowledge.datasnipper.com/en/articles/694306-how-to-add-a-text-snip-to-a-document)
- **操作说明**　先选单元格，再框选原件区域，交叉引用保存在工作簿里。复核人可由单元格回到原页相应位置。留档帮助页也列明编制和复核各自的留档动作。
- **本地用法**　会计看到「柜温超限」时，分别从 4℃ 和 8℃ 打开合同、验收单的对应原行。侧边保留当前底稿版本和两份单据名，让接手的复核人能重做同一次比对。[首页 R7 的取数位置](showcase-provenance.md#从首页数字回到原行)

## FloQast Close · 从关账全局看到责任人

美国，查阅于 2026-11-25。厂商产品说明书共两页。文件名含 March 2024，第 2 页页脚标 © 2025、OS022423。当日 PDF 的 SHA-256 为 `e0b075db000f81b63c6c5cd7b0898abf5633138677b3cbe77e9d54cb8a664b2f`。[FloQast Close（官方 PDF）](https://get.floqast.com/hubfs/FloQast_Data%20Sheet_Close_March%202024.pdf)

- **画面**　第 1 页右下的两幅小图，一幅以签核进度环和状态数量汇总工作，另一幅按文件夹排行、按日期排列状态格。第 2 页右上的清单把任务、到期日、经办人头像与签核状态排在同一行，右侧中部另有对账清单和评论浮层。
- **说明书表述**　厂商介绍了按成员、实体和流程筛选、跨期结转清单等能力。快速实施、节省时间属于产品宣传。PDF 能核实清单的排布，交互效果只取其文字说明。
- **本地用法**　小企业月末交接时，负责人先看哪些采购案等补件、哪些等签收，再在对应行查经办人和待办事项。案件处理进度与审计人员的最终决定分别标示。[工作台台账与核验流程](../docs/README.md#使用工作台)

## Caseware Cloud · 编制完成后如何交给复核人

加拿大，查阅于 2026-11-25。官方帮助的第 1 步展示项目状态，第 3 步展示复核签核菜单。截图保留了示例项目的历史日期。[Review prepared documents](https://www.caseware.com/docs/en/cloud/caseware-cloud/engagement-management/documentation-and-review/review-prepared-documents)

- **画面**　项目页左侧选中 My Work，中间的 Document Status 横条分别列出未完成、已编制、已复核的件数。进入单份底稿，右上角展开的签核菜单中，一行已有编制人和日期，另一行留有复核签核入口。
- **操作说明**　先选项目，点 Open，按文档前的签核图标找出待复核件。检查完成后以复核人身份签核，文档状态随之更新。
- **本地用法**　审计员转交一笔采购案时，在任务行显示待复核版本，打开后保留初审人的处理意见。另一位复核人可以在同版原件旁记录签收或退回原因。[独立人工复核](../docs/api.md#独立人工复核)

## Fieldguide · 一张缺件清单怎样跟进

美国，查阅于 2026-11-25。官方帮助标注 2026-09-01，重点看单条请求与列表管理两节的配图。[Managing requests](https://help.fieldguide.io/en/articles/7207259-managing-requests)

- **画面**　左侧列表保留请求编号、状态和标题。右侧打开董事会会议资料请求，面板带日期、评论、活动记录和拖入文件区域。截图上的第一个页签写 Details，正文称 Overview。新建截图将基本资料、日期与负责人分段填写。
- **操作说明**　选中一行展开侧栏，按到期日分组可查逾期项。客户提交资料后可送审，事务所可要求补正或确认完成。
- **本地用法**　采购员收到「请补正式复验单」时，同一条请求应能看到对应合同、哪一期款受影响、退回原因和补交文件。审计员从这条记录接着核对，保留原退回版本。[从退回版本提交补件](../docs/api.md#从退回版本提交补件)

本轮采用行内速览。任务台账保留检索范围，侧栏展示文件清单、实际处理阶段和当前版本的重点发现。发现链接保留案件与底稿版本。[Fieldguide 任务侧栏说明](https://help.fieldguide.io/en/articles/7207259-managing-requests) · [本项目工作台](../docs/interaction-design/README.md#任务队列与资料提交)

## Dext · 逐行比对发票与录入值

英国，查阅于 2026-11-25。官方帮助标注 2026-08-04，可直接看纵向分栏示例和表格设置面板两幅图。[How to customise the line item editor in Dext](https://help.dext.com/en/articles/760441-how-to-customise-the-line-item-editor-in-dext)

- **画面**　左边是有行项目和合计的完整发票，右边是可编辑明细，列出净额、税额、总额。行末下方有差额汇总，中间分隔条标出拖动位置。第二幅图中，齿轮面板可勾选列并选择三档行距。
- **操作说明**　编辑器可切换纵横分栏、拖动分隔线或暂时隐藏预览，列和行距选择经 Apply 生效。
- **本地用法**　会计核对人民币发票时，可让原件与不含税额、税额、价税合计并排，差额紧跟合计。扫描栏读数不清时，保留原图入口。核准或更正后，下一位复核人仍可查到此前读数。[项目的取数与重算](../docs/research.md#查看与重算)

本轮将页图缩放放在原件一侧，字段切换放在引文一侧。审阅者能放大原件，再按所见读数登记核图意见。[Dext 原件与行项目编辑器](https://help.dext.com/en/articles/760441-how-to-customise-the-line-item-editor-in-dext) · [本项目原件核验](../docs/interaction-design/README.md#从审计建议回到原件)

在验收争议中，两份原件也需要同时阅读。Fish Audit 的「原件对照」把同一发现引用的合同条款、验收实测或签章日期放入左右两栏。两侧可以分别搜索和更换引文，点击页图可查看该版底稿所据整页。该设计借鉴了 Dext 同屏查看原件与明细的分栏操作。[Dext 分栏操作](https://help.dext.com/en/articles/760441-how-to-customise-the-line-item-editor-in-dext)

## MindBridge · 从异常列表追到单笔明细

加拿大，查阅于 2026-11-25。官方帮助标注更新于 2025-10-03，适用总账分析 MAC v.2。观察开头的编号截图，并核对配置视图和下钻小节。[Data table dashboard: Overview for GL (MAC v.2)](https://support.mindbridge.ai/hc/en-us/articles/360058192493-Data-table-dashboard-Overview-for-GL-MAC-v-2)

- **画面**　Data table 页签下，搜索框与科目、金额、风险分数、日期筛选位于表格上方。示例选择分录视图，每行同时显示交易号、科目、借贷金额和带文字与颜色的分数，右侧有列设置入口。
- **操作说明**　可以切换分录或交易视图。在交易视图中展开交易号可看所属分录，点选一笔则进入详情，查看构成该笔结果的控制点。
- **本地用法**　工作台可用已有的「问题／风险／待补证」筛选发现，行内保留程序编号和期次。选中第二期验收款时，应能沿 H04 的付款条件打开 H02 所据的合同与验收证据。[履约规则与实际证据](../docs/audit-method.md#合同履约与分期)

## 日期、审批状态与签收依据

2026-11-25 复查。Ramp 的账单页将缺资料、已批准待排期、已发起和已支付列为不同状态。FloQast 的产品说明把经办输出可追溯与人工最终签核列为两项能力。Fish Audit 针对合同履约采用两项判断，分别展示当前付款条件和当时实付时点。日期控件、证据对照以及中文风险文案由项目自行设计。[Ramp 的账单和付款状态](https://support.ramp.com/managing-bills-and-payments-on-bill-pay/) · [FloQast 的人工签核与可追溯输出说明](https://www.floqast.com/) · [项目实拍](../docs/interaction-design/receipt-timeline.webp)

同一验收单既有交付结论又有付款意见时，本项目把两个原件片段并排，保留页码和行号供审计员核查。这个交互借鉴了 Dext 的原件分栏阅读和 Ramp 对审批、支付状态的区分。国内采购控制依据另列于审计方法。[Dext 的原件分栏交互](https://help.dext.com/en/articles/760441-how-to-customise-the-line-item-editor-in-dext) · [Ramp 的账单状态](https://support.ramp.com/managing-bills-and-payments-on-bill-pay/) · [本项目交互](../docs/interaction-design/README.md#验收单上的付款意见)

## 从一项检查回到多份原件

核对验收人时，我们参考了 FloQast 采购复核画面中人员、签核状态及附件的位置，以及 DataSnipper 从单元格定位文档原行的方式。Fish Audit 把合同点名和本单签字栏排在同一行，保留原件切换。共同签字中的每个人有自己的核对状态，复验使用另一份单据。[FloQast 采购复核及附件示例](https://www.floqast.com/risk-compliance/products/audit-readiness) · [DataSnipper 底稿与对应原件的复核](https://knowledge.datasnipper.com/en/articles/685955-how-to-document-your-audit-procedures-with-datasnipper) · [Fish Audit 签字核对](../docs/interaction-design/README.md#验收签字核对)

DataSnipper 的 Alwin 复核界面能把结果中的一个单元格定位到来源文件。一个结果对应多处引文时，可以按文件列出证据并切换原页。Fish Audit 的合同履约底稿采用同样的查看顺序。先选本版的一项检查，再选它实际引用的字段或两条需要对照的原行。页图、检查状态和人工确认状态各自标注。[DataSnipper 的任务结果复核说明](https://knowledge.datasnipper.com/en/articles/882479-how-to-review-a-task-s-output-in-alwin)

Fieldguide 允许按状态筛选请求。Fish Audit 的检查面板默认列出待核项，同时保留查看本组全部结果的入口。当两种筛选会返回同一组记录时，界面收起筛选器。[Fieldguide 的请求管理界面](https://help.fieldguide.io/en/articles/7207259-managing-requests)
