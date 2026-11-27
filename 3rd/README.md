# Fish Audit 外部资料与源码索引

## Agent 工作流源码

两个源码目录都用 Git 子模块固定到具体提交。在新的工作副本中，从项目根目录运行 `git submodule update --init -- 3rd/ClaudeCode 3rd/deepseek-harness` 即可取回对应版本。

| 本地目录 | 固定版本 | 对照审计工作流时先看什么 |
| --- | --- | --- |
| [ClaudeCode](ClaudeCode/) | [Rito-w/ClaudeCode · 895221e](https://github.com/Rito-w/ClaudeCode/tree/895221e6964cf288c5fa1d2bb86edb568c491061) | 多份原件可并行读取，有先后依赖的步骤需依序执行。可对照一次模型调用如何接收工具结果，以及调度器如何决定并行或串行。[主循环](https://github.com/Rito-w/ClaudeCode/blob/895221e6964cf288c5fa1d2bb86edb568c491061/src/query.ts) · [工具调度](https://github.com/Rito-w/ClaudeCode/blob/895221e6964cf288c5fa1d2bb86edb568c491061/src/services/tools/toolOrchestration.ts) |
| [DeepSeek Harness](deepseek-harness/) | [deepseek-ai/deepseek-harness · 4b399c3](https://github.com/deepseek-ai/deepseek-harness/tree/4b399c39a6d1479cd84ca591b4d7c88e24d38a96) | 追踪解析、构图和审计各阶段时，可对照运行开始、阶段变化、取消与结束如何传到进度界面。[工作流引擎](https://github.com/deepseek-ai/deepseek-harness/blob/4b399c39a6d1479cd84ca591b4d7c88e24d38a96/packages/workflow/workflow-ptc/src/index.ts) · [进度面板](https://github.com/deepseek-ai/deepseek-harness/blob/4b399c39a6d1479cd84ca591b4d7c88e24d38a96/packages/client/ui-workflow-run/src/client/WorkflowRunPanel.tsx) |

Rito-w 将其仓库标注为从公开发行包还原的非官方研究学习版本，版权归 Anthropic。DeepSeek 官方仓库的根许可证为 MIT，随附组件另有第三方声明。[ClaudeCode 来源说明](https://github.com/Rito-w/ClaudeCode/blob/895221e6964cf288c5fa1d2bb86edb568c491061/README.md) · [DeepSeek 官方入口](https://www.deepseek.com/harness/zh/) · [MIT 许可](https://github.com/deepseek-ai/deepseek-harness/blob/4b399c39a6d1479cd84ca591b4d7c88e24d38a96/LICENSE) · [第三方声明](https://github.com/deepseek-ai/deepseek-harness/blob/4b399c39a6d1479cd84ca591b4d7c88e24d38a96/THIRD_PARTY_NOTICES.md)

## 界面与审计资料

界面调研始于 2026-11-25，首付款保函与案例搜索资料更新于 2026-11-27（北京时间）。归档保留审计与会计软件的官方帮助配图、演示动图和说明书链接，记录具体画面及本工作台采用的做法。

| 要核对什么 | 查阅入口 |
| --- | --- |
| 如何对照付款日与预付款保函期间，如何直接找到相关案例 | [采购担保原文、SAP、Stripe 与 W3C](contract-payment-review.md#付款日与银行保函期间) |
| 从一条分期付款引文翻到签章或验收附件 | [DataSnipper、Adobe 与 Ramp 的原件阅览交互](product-research.md#从审计引文翻到相邻原页) |
| 第三期回单引用了哪一批验收单 | [采购付款内控、Xero 与 DataSnipper](payment-acceptance.md) |
| 怎样确定检验范围，以及怎样切换整批设备和合同指定的设备 | 财政部采购指引第十一条要求企业确定检验方式、核对采购项目并出具验收证明。演练中的必检编号和最低台数取自该案合同。界面采用 SAP Fiori 小范围视图切换的做法，旁列有记录台数。[财政部原文](https://kjs.mof.gov.cn/zhengcefabu/201005/P020230421440664863663.pdf) · [财政部会计司解读的验收环节](https://kjs.mof.gov.cn/zhengcejiedu/201006/t20100611_322435.htm) · [SAP Fiori 分段选择器](https://www.sap.com/design-system/fiori-design-web/v1-142/ui-elements/segmented-button) |
| Word 验收原件的审阅选区、DataSnipper 证据定位，以及规则出处的逐项核对 | [Word 审阅与交互依据](word-acceptance-review.md) · [公开演练原件](showcase-provenance.md#word-验收批注与第二期回单) |
| 七款软件的原始链接、可见操作和国内工作台用法，包括 Karbon 看板和 Fieldguide 侧栏 | [产品界面调研](product-research.md) |
| Ramp、Xero、Fieldguide 与 FloQast 怎样用颜色区分操作、选择和风险 | [官方截图的配色观察](interface-color.md) |
| 采购收货状态、原件定位和签署意见如何进入复核界面 | [Ramp、DataSnipper 与 PDF 签署资料](pdf-signature-review.md) · [固定水印原件](showcase-provenance.md#供货主体与签署原因) |
| 本工程采用的研究方法、法规条款、外部软件及字体来源 | [文献、制度与技术来源](project-sources.md) |
| 首页的合同金额、柜温、分期条件及三份水印 PDF 的逐字节摘要 | [合成资料声明与 R7 底稿字段](showcase-provenance.md) |

### 在底稿中逐项核对原件

Ramp 的采购界面按供应商、状态、金额和开票进度浏览采购单，选中一笔再看明细。DataSnipper 的细节测试把选定字段引用到相关证据的位置，复核人可从工作表返回原件。Fish Audit 在同一笔采购里保留待核事项队列，用项目选择器切换签署、合同日期与验收依据，原件与该版读数同时可见。以上参考用于操作方式。[Ramp 官方采购指南](https://support.ramp.com/hc/en-us/articles/49355243914387-Ramp-Procurement-Quick-Start-Guide) · [DataSnipper 官方细节测试](https://www.datasnipper.com/external-audit/test-of-detail) · [本项目交互实拍](../docs/interaction-design/README.md#一次核对一个项目)

### 从签章栏追到签署凭证

DataSnipper 用工作底稿与证据文件中具体位置的交叉引用支持同步审阅。本项目在签署方切换器中展示真实页图的行片段，并在原页、字段更正及引用该行的付款程序之间保留版本定位。[DataSnipper 官方操作文档](https://knowledge.datasnipper.com/en/articles/685955-how-to-document-your-audit-procedures-with-datasnipper)

Docusign 的完成证书记录信封、参与人和签署事件。这里借鉴其对签署过程留痕的做法，在补件意见中请求能够对应合同版本及签署方的材料。国内个案中的电子签署依据参照《电子签名法》第八、十三、十四条，由审计人员结合当事人的约定和实际资料复核。[Docusign 交易记录说明](https://www.docusign.com/trust/security/transaction-data-use) · [工信部公布的法律全文](https://wap.miit.gov.cn/zwgk/zcwj/flfg/art/2022/art_4ed0e4a46946479c90a9e0f2c76a11ef.html)

### 审计取证与关账协作参考

| DataSnipper · 审计取证 | FloQast Close · 关账协作 |
| --- | --- |
| 单元格如何回到证据的页内位置，编制人与复核人各要保留什么。[How to document your audit procedures with DataSnipper](https://knowledge.datasnipper.com/en/articles/685955-how-to-document-your-audit-procedures-with-datasnipper) | 第 1 页展示跨任务的进度和日期，第 2 页展示逐项责任与签核。[FloQast Close（官方 PDF）](https://get.floqast.com/hubfs/FloQast_Data%20Sheet_Close_March%202024.pdf) |

### 首页合成资料声明

首页选用「所验型号相符但实测温度超限」R7，案例号为 `ed7751a871aa4fb1a8574eddada0254b`。合同含税总额 100,000 元，约定柜温不高于 4℃，验收单填「合格」却记录实测 8℃。合同约定分三期支付 30%、60%、10%，本案只有第二期 60,000 元的付款回单。三份展示原件均带「合成演练资料　仅供系统测试　无交易效力」水印。[首页展示位置](../frontend/landing.html) · [采购合同](../frontend/showcase/contract.pdf) · [验收报告](../frontend/showcase/acceptance.pdf) · [银行付款回单](../frontend/showcase/transfer.pdf)
