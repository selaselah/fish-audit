# 首页合成资料声明与固定版底稿字段

首页采用 Fish Audit 自制的冷藏柜采购演练。采购方「青禾演练采购中心」、供应方「云桥演练设备中心」、金额、温度、签认和回单均为虚构数据。每份原件第 1 行均印有「合成演练资料　仅供系统测试　无交易效力」。4℃ 是这份合同约定的柜温上限，8℃ 是这份验收报告填写的实测值。[水印和主体的生成定义](../docs/samples/generate.py) · [项目演练说明](../docs/samples/README.md#验收的是哪一种设备)


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
| 底稿 | R7，2026-11-25 09:35（北京时间），业务范围 `cn-contract-performance/v1` |
| 当版规则 | `policy.version = 2026.11.25.13`，`policy.equipment_models = printed-equipment-models-v1` |
| R7 底稿 SHA-256 | `cfed6075a9836ab6c851d4133b5ad0b29c4f69c848db6c46eb52d1937b763e11` |

样本沿用 `contract_milestones.documents(code, "complete")` 的总价、付款条款、回单与质保期满确认。设备型号生成器在合同和验收单各写入 YL-C4，`quality` 分支将实测结果改为 8℃，保留结论「合格」和遗留事项「无」。仓库验收记录在「合同约定型号、分批验收与整改后换货」一节设有「实测温度 R7」入口。[基础合同与回单](../docs/samples/contract_milestones.py) · [定选案例生成器](../docs/samples/equipment_models.py) · [版本验收记录](../docs/acceptance.md#2026-11-25--合同约定型号分批验收与整改后换货) · [当版字段说明](../docs/api.md#约定设备型号与实收型号)

## 展示原件

首页核图窗口只在打开时载入水印验收报告的固定 R7 页图。该页归档为 JPEG，沿用最初的公开资源名 `showcase-acceptance-page.png`，服务以 `image/jpeg` 返回原始字节。页图宽 1547、高 2190 像素，SHA-256 为 `fb4799101ab7c9ee46baa4705ed0712abeede3e50e22d8f0b8aebfb5a9ef27bd`。三处高亮分别取自第 9、11、12 行的 `source_line.rects`，切换整页和原行使用相同坐标。[归档页图副本](../frontend/assets/showcase-acceptance-page.png) · [验收报告 PDF](../frontend/showcase/acceptance.pdf)

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

在仓库根目录运行以下命令即可复核三个展示文件的摘要。

```sh
shasum -a 256 frontend/showcase/contract.pdf frontend/showcase/acceptance.pdf frontend/showcase/transfer.pdf
```
