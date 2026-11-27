# Word 验收批注与证据定位

财政部《企业内部控制应用指引第 7 号》第十一条涉及采购验收的品种、规格、数量、质量和异常报告，第十二、十三条涉及履约记录和付款审核。本项目据此把到货数量、性能实测、签认范围和具体期次分别留证。中注协审计准则第 1301 号第三、十一条要求结合来源、性质和获取环境评价证据的可靠性与相关性。在演练中，拿到带姓名的打印页后，审计员还能查提交的 Word、审阅选区或影像，并向经办人员核对实际签认依据。[财政部应用指引（第 29 至 30 页）](https://kjs.mof.gov.cn/zhengcefabu/201005/P020230421440664863663.pdf#page=29) · [中注协《审计证据》](https://www.cicpa.org.cn/ztzl1/Professional_standards/xxzztx/zyzz/sjzz/202105/P020240412542695263912.pdf)

DataSnipper 的 Alwin 在复核工作表时，能从已摘录的单元格打开文档原位，再从文档选区定位工作表。本项目参考了这种往返操作。验收栏位、原批注和引用该凭证的分期检查各自可定位，退出原页或返回验收记录后，键盘焦点回到先前操作的位置。[DataSnipper 复核任务结果](https://knowledge.datasnipper.com/en/articles/882479-how-to-review-a-task-s-output-in-alwin) · [交互设计](../docs/interaction-design/README.md#从验收风险直接核对原件)

书面委托的核查复用 Word 原生选区，分别呈现正文中的权限和批注中的拟议条件。两份打印页相同的文件可能有不同的审阅记录。Microsoft 的示例说明怎样在提交的 DOCX 中查找 comments 部件以及作者、时间和意见。审计判断同时核对书面委托的记载事项、委托方签名或盖章的依据。[Microsoft WordprocessingML 批注读取](https://learn.microsoft.com/en-us/office/open-xml/word/how-to-retrieve-comments-from-a-word-processing-document) · [《民法典》第一百六十五条](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_60fb3863b7364b759123a42d1df568ca.html)

Microsoft 的 WordprocessingML 示例把批注正文放在主文档所关联的 comments 部件，用同一编号将批注与正文的开始位置、结束位置和引用标记对应。读取时可以取到文本、署名和记录时间。Fish Audit 以提交的原件为准保存这些值，批注署名的身份与验收权限由审计人员结合签认材料复核。[Microsoft 添加批注](https://learn.microsoft.com/en-us/office/open-xml/word/how-to-insert-a-comment-into-a-word-processing-document) · [Microsoft 读取批注](https://learn.microsoft.com/en-us/office/open-xml/word/how-to-retrieve-comments-from-a-word-processing-document)

三个测试文件通过 python-docx 对已经写入的“合格”文字添加标准批注。模型处理三案实际打印出的页图。程序另从原始 DOCX 读取正文选区，回到本案文字层核对行号，再将结果与该行字段绑定。解析器对扩展批注、修订痕迹和无法可靠定位的文字保留人工复核入口。[python-docx 批注接口](https://python-docx.readthedocs.io/en/latest/user/comments.html) · [合成资料生成](../docs/samples/word_acceptance.py) · [解析与复算](../server/acceptance_comments.py)

DataSnipper 的 Text Snip 用选区连接工作表数据和原件。这里借鉴“从所选字段打开实际来源”的操作，分别提供原件行、Word 审阅意见及引用这条意见的期款。在本项目的规则目录中，键盘可以切换目录项目、逐条翻阅出处。批注卡的选项卡支持左右方向键及 Home、End。[DataSnipper 官方交互说明](https://knowledge.datasnipper.com/en/articles/694306-how-to-add-a-text-snip-to-a-document) · [W3C 选项卡交互](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/) · [本项目交互实拍](../docs/interaction-design/README.md#验收批注与关联款项)
