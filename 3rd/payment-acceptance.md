# 付款回单与验收凭证的逐笔核对

2026 年 11 月 26 日查阅。水印案例由本项目生成，公开页面使用该案经核对的五份原件。

## 采购付款依据

财政部《企业内部控制应用指引第7号——采购业务》第十一条涉及按数量、规格、质量等验收并出具证明，第十三条涉及审核合同、相关单据和审批手续，第十五条涉及采购、验收、付款记录的勾稽。上述条文提供检查方向。具体哪一期引用哪一批，取自该笔采购的合同和原件。回单是否设有验收单号栏取决于实际资料。[财政部指引原文，第 29 至 31 页](https://kjs.mof.gov.cn/zhengcefabu/201005/P020230421440664863663.pdf#page=29) · [财政部会计司对采购流程的解读](https://kjs.mof.gov.cn/zhengcejiedu/201006/t20100611_322435.htm)

## 海外产品的证据交互

Xero 的银行对账页将银行流水与候选业务记录并排。审计工作台采用逐笔选择、左右对读和返回原单的交互。跨批判断使用合同期次、验收范围、原始单号和双方信息。[Xero 银行对账界面及操作](https://central.xero.com/0/article/Reconcile-your-bank-account)

DataSnipper 的文档匹配可追查匹配到的原始文档。这里把相同的追查动作放到单号下方，审计员可以核对印刷行、打开全页，并查看采用的资料版本。每一处高亮均来自本案原页位置。[DataSnipper 文档匹配说明](https://knowledge.datasnipper.com/en/articles/676049-faqs-for-document-matching)

## 公开演练原件

公开页面使用分批验收水印案例 R9。两笔回单分别为 15,000.00 元和 20,000.00 元。合同第三期对应第二批，第一笔回单引用第一批验收单。公开数据中保留底稿摘要、五份 PDF 和页图的 SHA-256、所列印刷行及其位置。浏览器测试逐份核对 PDF 与页图的摘要。原页裁片使用同版页图。[公开演练](http://127.0.0.1:8000/?scene=payment-acceptance#workflow) · [公开证据索引](../frontend/assets/batch-payment-reference.json) · [案例发生器](../docs/samples/delivery_batches.py)

## 共同签认的付款时点

财政部会计司的采购业务解读将验收、付款和会计控制列为相互关联的业务环节。本演练的两人共同签字要求、付款期次和比例均来自水印合同。比较的是同笔成功回单与两条具名签认栏所列的自然日。签名真实性、合同效力及其他履约条件另由各自原件支持。[财政部会计司采购业务解读](https://kjs.mof.gov.cn/zhengcejiedu/201006/t20100611_322435.htm)

Xero 在每笔银行匹配旁提供所据记录和文件，Ramp 的账单表按状态组织任务，并能切换查看付款明细。Fish Audit 的时序控件采用逐笔选择，点选一个日期即可见文件名、页码、行号和原件局部。同日签认与扣款并列，风险由文字、点形和颜色共同表示。[Xero 银行对账](https://www.xero.com/us/accounting-software/reconcile-bank-transactions/) · [Ramp 账单及付款管理](https://support.ramp.com/managing-bills-and-payments-on-bill-pay/)

首页时序演练取自本机水印案例 R8。合同、验收单和回单共三份 PDF，索引保存文件、原始页图和底稿摘要。首页的三期合同原行取自另一份已公开的冷藏柜采购合同，编号 YL-LY-32EED203，第 16–18 行。上述六张原行裁片均已按原页坐标逐像素核对。[签认时序证据](../frontend/assets/joint-signing.json) · [三期合同原行](../frontend/assets/installment-originals.json)
