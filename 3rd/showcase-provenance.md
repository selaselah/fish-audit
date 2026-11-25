# 首页合成资料声明与 R7 底稿字段

首页采用 Fish Audit 自制的冷藏柜采购演练。采购方「青禾演练采购中心」、供应方「云桥演练设备中心」、金额、温度、签认和回单均为虚构数据。每份原件第 1 行均印有「合成演练资料　仅供系统测试　无交易效力」。4℃ 是这份合同约定的柜温上限，8℃ 是这份验收报告填写的实测值。[水印和主体的生成定义](../docs/samples/generate.py) · [项目演练说明](../docs/samples/README.md#验收的是哪一种设备)

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
