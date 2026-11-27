# 付款回单与验收凭证的逐笔核对

2026 年 11 月 26 日查阅。水印案例由本项目生成，公开页面使用该案经核对的五份原件。

## 采购付款依据

2026 年 11 月 28 日复查财政部会计司采购业务解读第（八）项。其付款控制涉及审核人职责、合同、单据和审批程序。水印案例中第二期由谁签批、是否需要两人会签，均逐字取自该案采购合同。审计员可对照合同第 19 行和付款审批单第 12 行核查这项发现。[财政部会计司采购业务解读](https://kjs.mof.gov.cn/zhengcejiedu/201006/t20100611_322435.htm) · [具名签批四案](../docs/acceptance.md#合同指定谁签批第二期款)

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

## 同日时刻与原行对照

Ramp 的付款列表区分发起、在途和已付款，单据详情可以查看付款进展及回单。FloQast 的官方界面示例将某一期间的控制执行、签核人和附件集中在同一视图。Fish Audit 采用蓝色选中态、带文字的风险提示和可切换的原件对照。审计员可在一张卡内核对具名签认和实际扣款，点开任一原行查看整页。[Ramp 付款进度](https://support.ramp.com/bill-payment-methods-and-timelines/) · [Ramp 账单与付款管理](https://support.ramp.com/managing-bills-and-payments-on-bill-pay/) · [FloQast 控制审阅界面](https://get.floqast.com/hubfs/Assets/FloQast_Data%20Sheet_Achieving%20Connected%20Compliance%20with%20FloQast_July%202024.pdf)

公开同日演练来自本地生成的三份水印 PDF。导出时逐份核对了生成件摘要、该版图谱引用和页图摘要。九张 WebP 裁片均逐像素核对，包括模型遗漏的实际扣款时间原行。[固定版公开数据](../frontend/assets/signer-clock.json) · [首页试核](http://127.0.0.1:8000/?scene=signer-clock#workflow)

## 受理回执能证明什么

兴业银行的个人网银说明明确限定了转账回单的证明范围。建设银行的企业网银指南分别说明查询交易明细、打印回执和查询正式回单的入口。两家产品的用语说明了审计员需要核对具体单据载明的范围。水印案例中的措辞由项目自行编写，各项判断回引本案原件。[兴业银行转账回单查询说明](https://www.cib.com.cn/cn/e-banking/personal/faqs/tips/notice4.html) · [建设银行企业网银指南，第 13–15 页](https://www.ccb.com/chn/attachDir/2020/07/2020070614245962247.pdf#page=13)

付款凭证复核沿用 Xero 逐笔对读和 Ramp 按处理状态浏览的交互。复核员可以从状态栏或页脚直接打开该笔原页。风险用图形和文字共同标注。[Xero 银行对账](https://www.xero.com/us/accounting-software/reconcile-bank-transactions/) · [Ramp 账单与付款视图](https://support.ramp.com/managing-bills-and-payments-on-bill-pay/)

## 验收单的付款用途

2026 年 11 月 27 日复查会计司解读的第（八）项「付款」。本项目据此将合同、验收凭证、付款审批及实际扣款放在同一项付款检查下。审批岗位、所据验收单和期次从当案原文读取。使用日期先后与审批决定评估的是已提交凭据的一致性，实际授权还须查阅企业授权和签批记录。[财政部会计司《企业内部控制应用指引第7号——采购业务》解读](https://kjs.mof.gov.cn/zhengcejiedu/201006/t20100611_322435.htm) · [采购分期付款审批演练](../docs/acceptance.md#复验要求另批时核对付款审批单)

财政部会计司解读《企业内部控制应用指引第7号——采购业务》时，在第（七）项讨论到货验收，在第（八）项讨论付款前核查合同、凭证、审批手续和审核人权限。演练中的质量结论、单据用途与实际扣款分别对应不同的原始记录。案例所称「财务负责人」来自水印复验单上的具名岗位，实际案件须结合送审单位的授权及签批材料核实。[财政部会计司原文](https://kjs.mof.gov.cn/zhengcejiedu/201006/t20100611_322435.htm) · [用途附注演练](../docs/acceptance.md#复验合格后第二期付款所据的用途附注)
