# PDF 签署核查的技术与交互资料

委托书签发的审计检查依据《民法典》第一百六十五条确定书面委托的记载事项及被代理人的签名或盖章要求。证书签名覆盖文件的检查与电子签名法第十三条所述可靠条件分别取证。第十四条涉及可靠电子签名的法律效力。工作台保存可复算的文件和签名属性，审计人员可据此继续查证签署人身份、控制及授权。[国家市场监督管理总局公布的民法典](https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_60fb3863b7364b759123a42d1df568ca.html) · [工业和信息化部云南省通信管理局公布的电子签名法](https://ynca.miit.gov.cn/zwgk/zcwj/flfg/art/2022/art_a6ec461de9174d6b87ef092d15615652.html)

Acrobat 从签名面板选择一条签名后，可查看它所签的版本并与当前版本比较。DataSnipper 将底稿字段链接到支持文件的具体区域。本项目将这两步放在委托书审查中，先给出可点开的签章行，再展开签名覆盖范围及原件摘要。[Acrobat 签署版比较](https://helpx.adobe.com/acrobat/desktop/e-sign-documents/manage-digital-signatures/compare-versions.html) · [DataSnipper 原件区域引用](https://knowledge.datasnipper.com/en/articles/694306-how-to-add-a-text-snip-to-a-document)

| 来源 | 项目中的用法 |
| --- | --- |
| pyHanko 0.38.2 | 从上传的原件枚举已填写的签名域，读取 CMS 容器，校验已签字节摘要和签名值，区分覆盖整份文件与覆盖较早修订。使用固定版本和本地计算。[版本发布](https://pypi.org/project/pyHanko/0.38.2/) · [PDF 签名结构](https://docs.pyhanko.eu/en/latest/lib-guide/signing.html) · [验证结果的各个维度](https://docs.pyhanko.eu/en/latest/lib-guide/validation/status.html) |
| 《中华人民共和国电子签名法》（2019 年修正） | 第八、十三、十四条是 H01 既有的方法参考。检查以本次合同原文为起点。签名完整性、签署人身份和代表权限分别留证，证书信任链、吊销状态和双方代表权限交人工核验。[工信部公布的法律全文](https://www.miit.gov.cn/zwgk/zcwj/flfg/art/2022/art_4ed0e4a46946479c90a9e0f2c76a11ef.html) |
| Adobe Acrobat | 参考签名面板按记录查看验证状态、签名属性及证书的交互。底稿用版本线展示签名范围，文件摘要和证书指纹默认收起。[Adobe 签名验证说明](https://helpx.adobe.com/acrobat/desktop/e-sign-documents/manage-digital-signatures/validate-digital-sign.html) |
| BlackLine Account Reconciliations | 参考其将待处理事项、证明材料与人工复核放在同一工作区的方式。审计人员可以从疑点直接定位原件，并起草补件要求。[BlackLine 产品说明](https://www.blackline.com/products/financial-close/account-reconciliations/) |
| PDFium 与 pyHanko | 从 PDF 的修订结束位置确定首版边界，并与已签字节范围、独立解析结果交叉核对。后续修订需检查变更类别。签署原因是签名属性中的人为填写文字，进入验收复核依据。[PDFium 原生接口](https://pdfium.googlesource.com/pdfium/+/refs/heads/main/public/fpdfview.h) · [增量修订分析](https://docs.pyhanko.eu/en/latest/lib-guide/validation/diff-analysis.html) · [签署原因字段](https://docs.pyhanko.eu/en/latest/api-docs/pyhanko.sign.signers.html#pyhanko.sign.signers.pdf_signer.PdfSignatureMetadata.reason) |
| DataSnipper 与 Ramp Procurement | DataSnipper 把证据字段链接回原件中的矩形位置。Ramp 的采购核对把收货情况、采购单和发票联系起来。工作台据此提供供货主体双栏、可切换的逐字差异和原行定位。验收意见按本案合同与收货资料单独判定。[DataSnipper 证据定位](https://knowledge.datasnipper.com/en/articles/694306-how-to-add-a-text-snip-to-a-document) · [Ramp 三单匹配](https://support.ramp.com/3-way-match-with-ramp-procurement/) |

公开示例的文件、签名和批注均为项目自制的水印演练材料。测试证书私钥仅在生成进程内存中使用。[生成器](../docs/samples/pdf_signing.py) · [公开原件及字段出处](showcase-provenance.md#电子签名演练)
