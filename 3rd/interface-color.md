# 海外财务软件界面用色观察

2026-11-25 查看以下厂商公开的账单、对账与审计任务画面。表中用色来自指定的截图或演示帧，Fish Audit 的色值列在项目的交互设计文档中。

| 官方界面与查看位置 | 画面中的用色 | 在 Fish Audit 中的取舍 |
| --- | --- | --- |
| Ramp Bill Pay 的「Drafts」截图，图中展开 Options | 账单表以白底、深色文字和淡灰分隔线呈现。New bill 用亮黄，Ready for review 用较柔和的黄色标签，Scheduled 接近灰色。图中红框是帮助文章的操作标注。[官方帮助](https://support.ramp.com/managing-bills-and-payments-on-bill-pay/) · [原图](https://assets.ramp.com/help-center/managing-bills-and-payments-on-bill-pay/attachments/31521883345939.png) | 保留高饱和色给主要操作。任务台账中的金额、标题和时间保持中性，需处理的结论可单独辨认。 |
| Xero 银行对账页的开头演示，以及「smart automation」对账方法示例 | 演示中的导航使用蓝色，交易明细是白底和灰色表头。方法示例用浅蓝小标签承载 Rule、Match 等深色文字。[官方演示页](https://www.xero.com/us/accounting-software/reconcile-bank-transactions/) | 主按钮使用钴蓝实底，选中的文件页签、队列用蓝字或浅蓝底。单据正文保持白底。 |
| Fieldguide Requests 的任务列表和 Status 筛选框 | 状态行以蓝点标 Open，橙点标 Ready for Review，红点标 Changes Requested，每个点旁都有状态文字。列表区域使用白色和浅灰，创建按钮另用品牌绿。[官方截图与操作说明](https://help.fieldguide.io/en/articles/7207259-managing-requests) | 为待核事项和已知问题分配不同颜色。台账仍显示「需要人工校验」等结论，读者可直接读出要做的事。 |
| FloQast Close 官方说明书第 2 页右上 Checklist 截图 | 表格以白色和浅灰色交替显示任务行，文件链接用蓝色，日期和右侧开关分别使用少量橙色与绿色。[官方说明书第 2 页](https://get.floqast.com/hubfs/FloQast_Data%20Sheet_Close_March%202024.pdf#page=2) | 底稿里用蓝色链接返回原件。人工签收、处理进度和审计判断各自保留明确的文字标签。 |

颜色可读性使用相对亮度检查。WCAG 2.2 的 1.4.3 涉及文字与背景的对比度，1.4.1 要求通过颜色以外的线索传达信息。对应的本地实现和检查范围见项目记录。[W3C 文字对比度](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) · [W3C 颜色使用](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html) · [项目色板与实测截图](../docs/interaction-design/README.md#颜色与含义)
