# 六款审计与会计软件的公开界面

每项记录给出厂商原页、查看位置和查阅日。「画面」来自公开截图或动图，「操作说明」来自对应的帮助正文。「本地用法」说明国内中小企业的采购员、会计或复核人可以如何处理一笔业务。观察范围限于这些公开资料。

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

## MindBridge · 从异常列表追到单笔明细

加拿大，查阅于 2026-11-25。官方帮助标注更新于 2025-10-03，适用总账分析 MAC v.2。观察开头的编号截图，并核对配置视图和下钻小节。[Data table dashboard: Overview for GL (MAC v.2)](https://support.mindbridge.ai/hc/en-us/articles/360058192493-Data-table-dashboard-Overview-for-GL-MAC-v-2)

- **画面**　Data table 页签下，搜索框与科目、金额、风险分数、日期筛选位于表格上方。示例选择分录视图，每行同时显示交易号、科目、借贷金额和带文字与颜色的分数，右侧有列设置入口。
- **操作说明**　可以切换分录或交易视图。在交易视图中展开交易号可看所属分录，点选一笔则进入详情，查看构成该笔结果的控制点。
- **本地用法**　工作台可用已有的「问题／风险／待补证」筛选发现，行内保留程序编号和期次。选中第二期验收款时，应能沿 H04 的付款条件打开 H02 所据的合同与验收证据。[履约规则与实际证据](../docs/audit-method.md#合同履约与分期)
