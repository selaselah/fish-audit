# Word 验收批注与证据定位

Microsoft 的 WordprocessingML 示例把批注正文放在主文档所关联的 comments 部件，用同一编号将批注与正文的开始位置、结束位置和引用标记对应。读取时可以取到文本、署名和记录时间。Fish Audit 以提交的原件为准保存这些值，批注署名的身份与验收权限由审计人员结合签认材料复核。[Microsoft 添加批注](https://learn.microsoft.com/en-us/office/open-xml/word/how-to-insert-a-comment-into-a-word-processing-document) · [Microsoft 读取批注](https://learn.microsoft.com/en-us/office/open-xml/word/how-to-retrieve-comments-from-a-word-processing-document)

三个测试文件通过 python-docx 对已经写入的“合格”文字添加标准批注。模型处理三案实际打印出的页图。程序另从原始 DOCX 读取正文选区，回到本案文字层核对行号，再将结果与该行字段绑定。解析器对扩展批注、修订痕迹和无法可靠定位的文字保留人工复核入口。[python-docx 批注接口](https://python-docx.readthedocs.io/en/latest/user/comments.html) · [合成资料生成](../docs/samples/word_acceptance.py) · [解析与复算](../server/acceptance_comments.py)

DataSnipper 的 Text Snip 用选区连接工作表数据和原件。这里借鉴“从所选字段打开实际来源”的操作，分别提供原件行、Word 审阅意见及引用这条意见的期款。在本项目的规则目录中，键盘可以切换目录项目、逐条翻阅出处。批注卡的选项卡支持左右方向键及 Home、End。[DataSnipper 官方交互说明](https://knowledge.datasnipper.com/en/articles/694306-how-to-add-a-text-snip-to-a-document) · [W3C 选项卡交互](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/) · [本项目交互实拍](../docs/interaction-design/README.md#验收批注与关联款项)
