# Fish Audit 界面重做资料索引

界面调研始于 2026-11-25，合同日期与签章原行对照更新于 2026-11-26（北京时间）。归档保留审计与会计软件的官方帮助配图、演示动图和说明书链接，记录具体画面及本工作台采用的做法。

| 要核对什么 | 查阅入口 |
| --- | --- |
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
