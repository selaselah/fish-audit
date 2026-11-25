# Fish Audit 界面重做资料索引

界面调研始于 2026-11-25，签章原行对照更新于 2026-11-26（北京时间）。归档保留审计与会计软件的官方帮助配图、演示动图和说明书链接，记录具体画面及本工作台采用的做法。

| 要核对什么 | 查阅入口 |
| --- | --- |
| 七款软件的原始链接、可见操作和国内工作台用法，包括 Karbon 看板和 Fieldguide 侧栏 | [产品界面调研](product-research.md) |
| Ramp、Xero、Fieldguide 与 FloQast 怎样用颜色区分操作、选择和风险 | [官方截图的配色观察](interface-color.md) |
| 本工程采用的研究方法、法规条款、外部软件及字体来源 | [文献、制度与技术来源](project-sources.md) |
| 首页的合同金额、柜温、分期条件及三份水印 PDF 的逐字节摘要 | [合成资料声明与 R7 底稿字段](showcase-provenance.md) |

### 审计取证与关账协作参考

| DataSnipper · 审计取证 | FloQast Close · 关账协作 |
| --- | --- |
| 单元格如何回到证据的页内位置，编制人与复核人各要保留什么。[How to document your audit procedures with DataSnipper](https://knowledge.datasnipper.com/en/articles/685955-how-to-document-your-audit-procedures-with-datasnipper) | 第 1 页展示跨任务的进度和日期，第 2 页展示逐项责任与签核。[FloQast Close（官方 PDF）](https://get.floqast.com/hubfs/FloQast_Data%20Sheet_Close_March%202024.pdf) |

### 首页合成资料声明

首页选用「所验型号相符但实测温度超限」R7，案例号为 `ed7751a871aa4fb1a8574eddada0254b`。合同含税总额 100,000 元，约定柜温不高于 4℃，验收单填「合格」却记录实测 8℃。合同约定分三期支付 30%、60%、10%，本案只有第二期 60,000 元的付款回单。三份展示原件均带「合成演练资料　仅供系统测试　无交易效力」水印。[首页展示位置](../frontend/landing.html) · [采购合同](../frontend/showcase/contract.pdf) · [验收报告](../frontend/showcase/acceptance.pdf) · [银行付款回单](../frontend/showcase/transfer.pdf)
