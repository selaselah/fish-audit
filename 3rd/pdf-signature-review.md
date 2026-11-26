# PDF 签署核查的技术与交互资料

| 来源 | 项目中的用法 |
| --- | --- |
| pyHanko 0.38.2 | 从上传的原件枚举已填写的签名域，读取 CMS 容器，校验已签字节摘要和签名值，区分覆盖整份文件与覆盖较早修订。使用固定版本和本地计算。[版本发布](https://pypi.org/project/pyHanko/0.38.2/) · [PDF 签名结构](https://docs.pyhanko.eu/en/latest/lib-guide/signing.html) · [验证结果的各个维度](https://docs.pyhanko.eu/en/latest/lib-guide/validation/status.html) |
| 《中华人民共和国电子签名法》（2019 年修正） | 第八、十三、十四条是 H01 既有的方法参考。检查以本次合同原文为起点。签名完整性、签署人身份和代表权限分别留证，证书信任链、吊销状态和双方代表权限交人工核验。[工信部公布的法律全文](https://www.miit.gov.cn/zwgk/zcwj/flfg/art/2022/art_4ed0e4a46946479c90a9e0f2c76a11ef.html) |
| Adobe Acrobat | 参考签名面板按记录查看验证状态、签名属性及证书的交互。底稿用版本线展示签名范围，文件摘要和证书指纹默认收起。[Adobe 签名验证说明](https://helpx.adobe.com/acrobat/desktop/e-sign-documents/manage-digital-signatures/validate-digital-sign.html) |
| BlackLine Account Reconciliations | 参考其将待处理事项、证明材料与人工复核放在同一工作区的方式。审计人员可以从疑点直接定位原件，并起草补件要求。[BlackLine 产品说明](https://www.blackline.com/products/financial-close/account-reconciliations/) |

公开示例的文件、签名和批注均为项目自制的水印演练材料。测试证书私钥仅在生成进程内存中使用。[生成器](../docs/samples/pdf_signing.py) · [公开原件及字段出处](showcase-provenance.md#电子签名演练)
