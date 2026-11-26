# 首页合成资料声明与固定版底稿字段

首页采用 Fish Audit 自制的冷藏柜采购演练。采购方「青禾演练采购中心」、供应方「云桥演练设备中心」、金额、温度、签认和回单均为虚构数据。每份原件第 1 行均印有「合成演练资料　仅供系统测试　无交易效力」。4℃ 是这份合同约定的柜温上限，8℃ 是这份验收报告填写的实测值。[水印和主体的生成定义](../docs/samples/generate.py) · [项目演练说明](../docs/samples/README.md#验收的是哪一种设备)

## 供货主体与签署原因

首页「采购验收」下的「供货主体」来自水印合同 `YL-LY-57C4A51A`，固定 R5 底稿摘要为 `a9a6623df3ffd107117f3fad4b1152e9cc70309e0b1fa236b54a9723e675ff1a`。两份公开 PDF 和 JPEG 原页逐字节取自证据包。供应方局部图裁自各自第 5 行的原图坐标，原件窗口还可定位第 3 行合同编号和第 4 行采购方。签署原因逐字取自同一份合同的签名属性。仅发布此案核对所需的两份水印原件。[完整页图与文件摘要](../frontend/assets/supplier-sample.json) · [固定 R5](http://127.0.0.1:8000/workpaper/3471aa3a67544af3835aa45f7a0cc321?rev=5&view=suppliers)

## 电子签名演练

三套文件共用同一合同正文、验收单和回单。页图和排印行完全一致。「排印稿」来自 R5，「电子签署版」和「签后修订版」来自各自的 R4。后一份保留了前一份的签名，在文件末尾追加 349 字节的测试元数据。签署页缩略图和两个签章栏裁片取自三案字节一致的归档页图，裁片定位到第 11、12 行。公开文件逐字节取自对应底稿的归档原件，当前版与前版使用同一测试证书。[公开演练](http://127.0.0.1:8000/?scene=pdf-signing#workflow) · [三份文件的 SHA-256 与校验明细](../frontend/assets/pdf-signing-samples.json) · [技术与交互资料](pdf-signature-review.md)

## 合同日期冲突案例 R6

首页「合同生效」的日期冲突取自虚构的水印合同 `YL-LY-985A11F2`。首页的两个日期入口和签约日期入口均可打开原页。日期冲突的判断取自本案 H01，三期付款条件和第二期实付均需复核。[公开原件](../frontend/showcase/calendar-contract.pdf) · [归档页图](../frontend/assets/showcase-calendar-page.jpg) · [固定 R6](http://127.0.0.1:8000/workpaper/ad3f0a459eaa44c393ef346d0c64bdfc?rev=6&view=calendar)

| 采购合同第 1 页 | 印刷栏与读数 | R6 图谱观察 |
| --- | --- | --- |
| 第 8 行 | 签约日期，2026 年 9 月 1 日 | `d01/p1/f6` |
| 第 9 行 | 实际生效日期，2026 年 9 月 1 日 | `d01/p1/f7` |
| 第 10 行 | 生效确认日期，2026 年 9 月 23 日 | `d01/p1/f8` |

PDF 的 SHA-256 为 `c9751b24f4902a8f18e963b86b3f2c6b1eeaf5562483814be397165e9a0eb741`，归档 JPEG 的 SHA-256 为 `63e7a392710a1adde85eafb3816b43e4abe70bf8a0e2eaf17a6ca0891b45d79c`，R6 底稿的 SHA-256 为 `a803f44f2f582e72fa81eeedefaf4b54685f7fb4738fc91cafdc1454bea5ef37`。168 × 238 像素缩略图由这张页图缩放，两个标记分别使用第 9、10 行坐标。[首页日期演练](http://127.0.0.1:8000/?scene=contract-dates#workflow)

## Word 签章栏案例 R6

公开例子从虚构任务 `5106e6c347f34b90bdd964b490496cdf` 的 R6 证据包提取。合同有水印，签章栏由普通文字排印，核图回执分别来自 R1 和 R2。首页沿用该版的三条原行及矩形坐标。[生成脚本](../docs/samples/word_signing.py) · [公开案例](http://127.0.0.1:8000/?scene=word-signing#workflow) · [本机固定底稿](http://127.0.0.1:8000/workpaper/5106e6c347f34b90bdd964b490496cdf?rev=6&view=signatures)

| 公开文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| [水印合同 Word](../frontend/showcase/signing-text.docx) | 37,192 | `1902b237402d810010cc477e6327368dba4e32d50da4f610d3188180ef78b184` |
| [合同第 1 页](../frontend/assets/showcase-word-signing-page.jpg) | 165,345 | `b22afb14f83e9a80fc635518e167bbb9465df63a0939572197c2cf2bd6789a70` |

生效条款、甲方签章、乙方签章分别对应第 10、11、12 行，字段引用为 `d01/p1/f9`、`d01/p1/f10`、`d01/p1/f11`。216 × 279 像素的缩略图由同一张页图等比缩小，页内提示标出两个签章栏的位置。打开原行或整页时才载入完整 JPEG。企业底稿的原件由各自的工作区接口鉴权。[公开缩略图](../frontend/assets/showcase-word-signing-thumb.webp)

## 付款续页案例 R10

首页「付款续页」引用虚构合同正文的 `YL-LY-D1094C6B` 和续页的 `YL-OTHER-D1094C6B`，分别是同一份 PDF 第 1 页和第 2 页的第 3 行。两页都印有合成演练水印。公开 PDF 的 SHA-256 为 `053f0ca1aec9a45b5ddef9eacc7e5f8d85b0caa39b73b908bda0bb814aec9ad9`。两张完整 JPEG 直接取自 R10 证据包。缩略图由页图按比例缩至 150 像素宽，标记位置取自该版的原行坐标。公开演示只使用随项目发布的静态资料。[两页合同](../frontend/showcase/payment-folios.pdf) · [各页摘要和六处原行坐标](../frontend/assets/showcase-payment-folios.json) · [本机 R10](http://127.0.0.1:8000/workpaper/9c91f77a45f84a8496cfeb09d1fcf8ba?rev=10&view=contract-pages)

## 首页双原件同步缩放

首页验收报告的「原件对照」取固定 R7 的采购合同和验收报告。左片使用采购合同第 14 行，右片使用验收报告第 12 行。两份可下载 PDF、归档页图摘要及引用编号列在下方的 R7 清单中。滑杆使用同一档比例重绘两张原页，分别以证据行框为中心。窄屏改为上下排列。 [合同原页](../frontend/assets/showcase-contract-page.jpg) · [归档验收页](../frontend/assets/showcase-acceptance-page.png) · [浏览器实拍](../docs/interaction-design/public-source-compare.webp)
## 设备测温案例 R11

「设备抽检」演示取自有水印的本机 R11。主合同第 1 页第 13、14、19 行分别记载交付数量、柜温限值和逐台检测要求。验收单第 1 页第 15 至 17 行分别列出四个设备编号、自报实测一台，以及 QC-01 的 3℃ 读数。公开阅读器直接使用两份归档 PDF 及其页图，点击原行可核对上下文。清单逐项记录文件和页图 SHA-256、物理行号、引文及原始坐标。[公开样本清单](../frontend/assets/showcase-inspection.json) · [水印采购合同](../frontend/showcase/inspection-contract.pdf) · [水印验收报告](../frontend/showcase/inspection-acceptance.pdf) · [固定 R11](http://127.0.0.1:8000/workpaper/08fdfa388dce4718a4cd46dada1385d8?rev=11)

## 合同签章案例 R9

流程区「合同签章」使用另一笔水印采购合同，编号为 `YL-LY-926F5898`。公开 PDF 和页图逐字节取自固定 R9，页图为本机服务保存的 JPEG。合同摘要为 `f5d63eb3c3630fe538e409a55df09b641ab4b9b9987136bdd19f3a2d3ff4390d`，第一页图摘要为 `5bcc03f483827ae679d14455dec8c3e8a85b04dd8b218c197417c2cfd57988fc`，底稿摘要为 `b02663e03026719ba54b5e0620582e4a6a0fe6f9b5f9777f80f5731aa4e8ff1c`。[固定 R9](http://127.0.0.1:8000/workpaper/bb8ca31f78554b16a1a0e338503ee3be?rev=9) · [公开 PDF](../frontend/showcase/signing-contract.pdf) · [签章案例生成器](../docs/samples/signing_parties.py)

| 合同第 1 页 | 字段 | 底稿观察 |
| --- | --- | --- |
| 第 4 行 | 采购方，青禾演练设备有限公司 | `d02/p1/f3` |
| 第 11 行 | 甲方签章，青禾演练设备有限公司（已盖章） | `d02/p1/f10` |
| 第 19 行 | 甲方印章单位名称，青禾演练设备有限公司杭州分公司 | `d02/p1/f18` |

首页复用同一个原件阅读器，按所点字段的归档矩形定位，并提供逐行和整页视图。审计人员在工作台可核对双方、完整图谱引用及其他历史版本。[公开交互演示](http://127.0.0.1:8000/?scene=signing#workflow)

## 版本与生成出处

| 标识 | 定选值 |
| --- | --- |
| 案件、合同 | `ed7751a871aa4fb1a8574eddada0254b`，合同号 `YL-LY-32EED203`，案名「合成演练 · 所验型号相符但实测温度超限」 |
| 样本批次 | `synthetic-equipment-models-20261125-13`，分支 `quality`，任务键为两者用连字符拼接 |
| 样本生成器版本 | `equipment_models.py` 对应 Git 提交 `168ca95be2825e3ac5a2907367af85ed5d469ae9` |
| 原始展示底稿 | R7，2026-11-25 09:35（北京时间），业务范围 `cn-contract-performance/v1` |
| R7 规则 | `policy.version = 2026.11.25.13`，`policy.equipment_models = printed-equipment-models-v1` |
| 首页当前底稿 | R8，规则 `2026.11.26.14`，底稿 SHA-256 为 `b0100d48118210a67d504c09dfad461ce4daaa5b5e3fc8aad1c78a1321ed15f5` |
| R7 底稿 SHA-256 | `cfed6075a9836ab6c851d4133b5ad0b29c4f69c848db6c46eb52d1937b763e11` |

样本沿用 `contract_milestones.documents(code, "complete")` 的总价、付款条款、回单与质保期满确认。设备型号生成器在合同和验收单各写入 YL-C4，`quality` 分支将实测结果改为 8℃，保留结论「合格」和遗留事项「无」。仓库验收记录在「合同约定型号、分批验收与整改后换货」一节设有「实测温度 R7」入口。[基础合同与回单](../docs/samples/contract_milestones.py) · [定选案例生成器](../docs/samples/equipment_models.py) · [版本验收记录](../docs/acceptance.md#2026-11-25--合同约定型号分批验收与整改后换货) · [当版字段说明](../docs/api.md#约定设备型号与实收型号)

## 展示原件

首页核图窗口打开时载入 R8 水印验收页图，原件、页图字节和引文位置已与 R7 逐项核对。该页归档为 JPEG，沿用最初的公开资源名 `showcase-acceptance-page.png`，服务以 `image/jpeg` 返回原始字节。页图宽 1547、高 2190 像素，SHA-256 为 `fb4799101ab7c9ee46baa4705ed0712abeede3e50e22d8f0b8aebfb5a9ef27bd`。三处高亮分别取自第 9、11、12 行的 `source_line.rects`，切换整页和原行使用相同坐标。[归档页图副本](../frontend/assets/showcase-acceptance-page.png) · [验收报告 PDF](../frontend/showcase/acceptance.pdf)

首页「看原行」显示 R7 两张已归档页图的像素裁片。以下裁切坐标按左、上、右、下排列，单位为原始像素。可从对应 PDF 阅读完整上下文。

| 裁片 | 引文及行号 | 原页 SHA-256 | 裁切框 |
| --- | --- | --- | --- |
| [合同原行](../frontend/assets/showcase-contract-line.png) | `d02/p1/f13`，第 14 行 | `aa535f590439173143a8a0654f3c4ed2f482477502cf247b7b2438277394dfdb` | 120，1236，660，1283 |
| [验收原行](../frontend/assets/showcase-acceptance-line.png) | `d04/p1/f11`，第 12 行 | `fb4799101ab7c9ee46baa4705ed0712abeede3e50e22d8f0b8aebfb5a9ef27bd` | 121，1096，465，1143 |

2026-11-25 已将以下三个展示文件与归档原件逐字节比对，并与 R7 的 `graph.documents[].sha256` 核对。三份 PDF 均为一页，保留原水印。

| 展示文件 | R7 单据 | 字节数 | SHA-256 |
| --- | --- | ---: | --- |
| [contract.pdf](../frontend/showcase/contract.pdf) | `d02` 采购合同 | 61,069 | `546d0efde4b8a9bc2bc501c866dedaf60a3ac20ef46cc1af63194aa75e4e1af2` |
| [acceptance.pdf](../frontend/showcase/acceptance.pdf) | `d04` 验收报告 | 58,903 | `587d052e348bf67e32399f0daafc1a065d061a13f669f08396ce75875b4153cf` |
| [transfer.pdf](../frontend/showcase/transfer.pdf) | `d03` 银行付款回单 | 49,185 | `8b0087142d831b111eea4cf1c77913b8df67a96a26a1da1a288a9875744df586` |

完整 R7 另有 `d01`《质保期满确认单》，原页记载双方于 2026-11-20 确认期满。这份凭据解释了第三期所据的材料。其 SHA-256 为 `0e409084f5d03a70542b1e0233a3de05f46727b319b6f8244d0e0e8c9c44e21f`。[质保确认单的字段来源](../docs/samples/contract_milestones.py)

## 从首页数字回到原行

下表行号从物理第 1 页的水印行算起。事实编号可在 R7 的 `graph.facts[]` 中查找，`source_line.number` 和 `source_line.text` 对应原页文字层。打开上表 PDF 即可独立核对。

| 首页所述事实 | 原页和文字层行 | R7 事实编号与字段 |
| --- | --- | --- |
| 含税总额 100,000.00 元 | 采购合同第 7 行 | `d02/p1/f6` · `total` |
| 合同约定柜温不高于 4℃ | 采购合同第 14 行 | `d02/p1/f13` · `acceptance_criteria` |
| 9 月 20 日终验，结论栏填「合格」 | 验收报告第 7、9 行 | `d04/p1/f6` · `accepted_on`，`d04/p1/f8` · `acceptance_result` |
| 检验依据为 4℃ 上限，实测 8℃，遗留事项填「无」 | 验收报告第 11、12、13 行 | `d04/p1/f10` · `inspection_basis`，`d04/p1/f11` · `measured_result`，`d04/p1/f12` · `acceptance_exception` |
| 约定与实收型号均为 YL-C4，数量均为四台 | 采购合同第 13、19 行，验收报告第 10、15 行 | 合同 `d02/p1/f12`、`d02/p1/f18`，验收 `d04/p1/f9`、`d04/p1/f14` |
| 生效后付 30%，终验合格后付 60%，质保期满后付 10% | 采购合同第 16、17、18 行 | 三条 `payment_stage` 分别为 `d02/p1/f15`、`d02/p1/f16`、`d02/p1/f17`，也是三项 `stage.clause_ref` |
| 回单记载第二期 60,000.00 元，9 月 21 日交易成功 | 银行付款回单第 6 至 9 行 | `d03/p1/f5` · `transfer_amount`，`f6` · `payment_designation`，`f7` · `transfer_status`，`f8` · `paid_on`（均为 `d03/p1`） |

按合同总额乘各期比例，三期约定金额分别为 **30,000、60,000、10,000 元**。收到的回单只记载第二期实付。R7 的 H02-3 判为 `issue`，实测 8℃ 高于合同上限 4℃。H04-5 第一期生效条件相符，H04-6 第二期和 H04-7 第三期均因终验依据不足标为 `risk`。H05-8 标为 `missing`，表示付款日是否已具备全部前提仍缺证。整案建议不通过（`result.verdict = reject`），查阅时待人工签收。[合同履约程序](../docs/audit-method.md#合同履约与分期) · [签收字段与流程](../docs/api.md#核图与最终决定)

首页当前显示 R8。H01 和三期 H04 均为证据不足，H02 仍为实测温度超限问题，H03 的付款比例可核，H05 要求核对付款日条件。签署栏只有排印文字。首次重审保留了 R7 的原始文件和页图，旧版结论仍可单独打开。[当前签署原件](http://127.0.0.1:8000/workpaper/ed7751a871aa4fb1a8574eddada0254b?rev=8&view=signatures)

在仓库根目录运行以下命令即可复核三个展示文件的摘要。

```sh
shasum -a 256 frontend/showcase/contract.pdf frontend/showcase/acceptance.pdf frontend/showcase/transfer.pdf
```
