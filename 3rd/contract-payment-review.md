# 合同付款批注与财务复核交互

Microsoft 的 Open XML 文档说明正文中的评论引用如何通过同一标识连接范围起点、终点和批注正文。Word 的上下文视图把批注放在原文旁，选择批注会定位所选文字。项目保留 DOCX 的选区、署名、批注部件摘要以及单独渲染的打印行，两份记录均可回查。[Microsoft 评论引用](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.commentreference?view=openxml-3.0.1) · [Word 上下文批注](https://support.microsoft.com/en-us/word/using-modern-comments-in-word)

Docusign 的合同审查把疑点链接到具体条款，由审阅者判断修订建议。FloQast 的对账工作区将支持材料、复核意见和签收记录与对应事项放在一起。本项目据此把“第二期付款条件”和“第二期实付时点”做成独立原件入口，让审计人员直接从期次进入该版本的底稿。[Docusign 合同审查](https://www.docusign.com/company/news-center/docusign-introduces-ai-contract-review-assistant-to-streamline-agreements-workflows) · [FloQast 对账与复核](https://www.floqast.com/close-management/products/account-reconciliations)

公开演示使用本项目生成的冷藏柜采购合同和银行回单。两份原件、页图和支付比例都来自同一份演练底稿。示例中的合成单位、署名和水印均保留在下载件中。[水印资料生成器](../docs/samples/contract_comments.py) · [演示数据与原件摘要](../frontend/assets/contract-comment-sample.json) · [验收记录](../docs/acceptance.md#合同分期付款批注)
