# 合成财会审计演练

## 重建验收签名所引报告

在仓库根目录运行以下命令，生成同一份两次签名的验收单和两份同名的候选附件。两案分别提交报告号 `JC-2026-081` 和 `JC-2026-018`，其余四份原件逐字节相同。加 `--run` 会提交本机服务，等待审计完成并核对报告号、归属和人工校验建议。每次生成都使用新的自签测试证书。[本机演练结果](../acceptance.md#验收签名所引的检测报告)

```sh
server/.venv/bin/python docs/samples/inspection_report_samples.py
```

## 重建设备清单用例

在仓库根目录运行下列命令，生成四组、共 16 份水印 PDF。每组含采购合同、终验报告、质保确认单和第二期付款回单，分别核对错号、重号、仅换序和末台编号遮盖。

```sh
server/.venv/bin/python docs/samples/delivery_register.py /tmp/fish-delivery-register
```

加 `--case difference` 可只生成错号组。加 `--run --check-fields` 会提交本机审计服务，并按同一批生成件的原页核对当事人、合同编号、验收范围及回单等排印字段。提交时按文件内容识别已生成的同一案例。四组的 16 份重建文件均已逐份核对 SHA-256。[原件行号及本机底稿](../acceptance.md#逐台设备清单与第二期验收款)

要复现设备代用的五个案例，在同一命令后加 `--substitution`。也可以直接加 `--case agreement` 只生成带待签补充协议的一案。五组共 21 份水印 PDF，分别核对合同允许书面批准、终验注明申请待批、待签补充协议、合同明文禁止和保养条款。重建的 21 份文件已逐份核对摘要。[原件与付款结论对照](../acceptance.md#设备代用约定与第二期验收款)

加 `--approval-dates` 生成五组各 5 份水印 PDF，分别模拟终验前、付款当天、付款后所记的批准决定，以及决定点名其他设备、决定写在待签草案上的情形。若只需走查付款早于所记批准日的一组，用 `--case decision_after`。[五案结果和本机入口](../acceptance.md#设备代用批准记载日与验收款)

加 `--case disputed_seal` 可重建签章异议案的五份原件。合同与回单分期一致，补充协议第 9 行是排印的采购方签章，第 11 行写有代用决定。在这份协议的第 9 行选择「字段或引文有异议」，填写依据后点「记录字段异议」。重审后的付款检查会保留这行供人工核验。[已记录异议的水印底稿](http://127.0.0.1:8000/workpaper/c52a58afddba4bf180f5ea4b17bb2687?rev=5&view=payment-checks&stage=H05-8)

## 重建验收数字间距用例

先下载水印母本，再从仓库根目录运行下列命令。生成四组各 4 份 PDF 和 1 份 Word 合同审批单。四组分别改变实测值、合同上限、验收单所引上限或数字与单位间的空白。[母本证据包](http://127.0.0.1:8000/api/cases/64cd9e64345841bab358728a6730f3d8/reports/7/bundle)

```sh
curl -fsS http://127.0.0.1:8000/api/cases/64cd9e64345841bab358728a6730f3d8/reports/7/bundle -o /tmp/inspection-master.zip
server/.venv/bin/python docs/samples/inspection_limits.py /tmp/inspection-master.zip /tmp/inspection-spacing --spacing
```

`--case reading_gap` 可只生成终验读数案例。加 `--run --check-fields` 会把这些带水印的文件送到本机服务进行模型审查，并按母本核对排印字段。单独重建的 20 份原件已经与首次演练逐份核对 SHA-256。[四组原件和模型摘录的对照](../acceptance.md#验收数字中间留白与第二期付款)

## 重建合同与验收报告的签署用例

四组各含采购合同、验收报告、质保期满确认单和银行付款回单，共 16 份带水印的 PDF。合同第 19 行分别写明两份文件都要签字并盖章、两份文件都要盖章并签字、仅合同项下的验收报告须签字并盖章，以及两份文件都可签字或盖章。第二组回单是 9 月 21 日的第二期 6 万元，其余三组是 9 月 2 日的首期 3 万元。

```sh
server/.venv/bin/python docs/samples/contract_signing_forms.py /tmp/fish-shared-signing --shared
```

加 `--case shared_final` 可单独重建第二期案例。加 `--run --check-fields` 会调用本机服务处理这些水印件，并按母本核对排印字段。底稿中的签署凭证仍须由审计人员查验。[四组走查底稿](../acceptance.md#合同与验收报告共用签署条款)

## 重建首期签署用例

生成四组共 17 份水印 PDF。每组均有首期 3 万元银行回单，依次演练双方法定代表人签字并盖章、董事会批准后还须签字、签字或盖章、仅验收单要求签字并盖章。[本机演练结果与底稿入口](../acceptance.md#首期付款所据的签字和盖章条款)

```sh
server/.venv/bin/python docs/samples/contract_signing_forms.py /tmp/fish-signing-forms
```

加 `--case board` 仅生成附董事会决定的案例。加 `--run --check-fields` 会提交水印原件并调用本机审计服务，按演练母本核对实际页图及排印栏。产出的底稿留待人工验收。

## 重建含端点限值和检测记录用例

沿用已校验摘要的冷藏柜采购母本，生成五组、共 25 份有水印的原件。包含恰在上限的取整读数、略高于上限的取整读数、合同上的仪器允差要求、检验费按分舍入，以及验收范围待确认。每组保留同一笔第二期付款。[下载 R7 母本](http://127.0.0.1:8000/api/cases/64cd9e64345841bab358728a6730f3d8/reports/7/bundle) · [逐案核对结果](../acceptance.md#含端点的柜温限值与原始检测记录)

```sh
PYTHONPATH=server server/.venv/bin/python docs/samples/inspection_limits.py /tmp/master-R7.zip /tmp/inspection-precision --precision
```

加 `--case contract_note` 仅生成合同标明仪器允差的案例。加 `--run --check-fields` 会向本机提交资料，核对母本、实际页图和印刷字段，再生成待人工验收的底稿。

## 重建严格限值和取整读数

用已核摘要的 R7 冷藏柜采购母本生成四组水印材料。前三组分别演练合同排除边界、终验单排除边界、双方严格下限均满足。第四组在验收报告第 15 行补入「柜温读数已取整，判定须核对未取整的原始记录」。各组保留原来的第二期付款安排和银行回单。[下载 R7 母本](http://127.0.0.1:8000/api/cases/64cd9e64345841bab358728a6730f3d8/reports/7/bundle) · [四组预期结果和实际底稿](../acceptance.md#实测八度时的严格限值和取整说明)

```sh
PYTHONPATH=server server/.venv/bin/python docs/samples/inspection_limits.py /tmp/master-R7.zip /tmp/strict-limits --strict
```

加 `--case rounded` 可单独生成带取整说明的案例。加 `--run --check-fields` 会提交给本机服务，按水印母本核对实际印刷字段，底稿留待人工验收。

## 重建合同和验收单的限值差异

生成器校验 R7 母本和五份水印原件的 SHA-256，每组只改合同或验收报告里的一行。三组分别覆盖终验放宽限值、终验收紧限值及检验单位错列。以下命令只生成文件。增加 `--run --check-fields` 会提交本机 API，逐页对照母本，演练字段核读并保留待人工验收的底稿。[下载采购母本](http://127.0.0.1:8000/api/cases/64cd9e64345841bab358728a6730f3d8/reports/7/bundle) · [已出具的三份底稿](../acceptance.md#合同与验收单使用不同限值)

```sh
PYTHONPATH=server server/.venv/bin/python docs/samples/inspection_limits.py /tmp/master-R7.zip /tmp/inspection-limits
```

## 会签名单有一人不同

用已核摘要的 R7 水印证据包作母本，生成三组合同、验收、整改、复验、质保、审批及银行回单，其中两组另附补充协议。以下命令在仓库根目录运行。末尾加 `--run --check-fields` 可提交本机服务，并对照水印原行演练核字。重复提交相同原件会返回同一案件。[下载水印母本](http://127.0.0.1:8000/api/cases/c05a306e53bc40eb8d6ef46233a8e731/reports/7/bundle) · [实测结果](../acceptance.md#两人会签的审批单只对上一人)

```sh
PYTHONPATH=server server/.venv/bin/python docs/samples/joint_approval_examples.py /tmp/master-R7.zip /tmp/joint-approvals
```

## 分期付款审批单

生成六组带水印的采购材料，每组七份 PDF。六种写法覆盖提前、延后、同日、拒付、其他期款以及引用另一验收单。末尾加 `--run` 可向本机服务提交。已逐行核对母本时可以同时传入 `--check-against` 和母本归档路径，生成器会校验母本及本案原件摘要，再按实际打印行演练补录、核字。[生成器](installment_approvals.py) · [本机运行结果](../acceptance.md#复验要求另批时核对付款审批单)

```sh
PYTHONPATH=server server/.venv/bin/python docs/samples/installment_approvals.py /tmp/installment-approvals
```

## 复验单付款用途

以下命令生成六组水印材料，每组六份 PDF。它们沿用同一合同、初验、整改、复验及扣款，只改一条用途附注。36 份生成件已逐一与实际上传版本比对摘要。[样本生成器](retest_use_notes.py) · [每种写法对应的实付判断](../acceptance.md#复验合格后第二期付款所据的用途附注)

```sh
server/.venv/bin/python docs/samples/retest_use_notes.py /tmp/inspection-use
```

任选一组上传到本机网站即可审计，也可给生成器加 `--run` 实际提交。若需演练字段复核，另加 `--check-against` 并提供对照版水印证据包。人工核字记录随案例留存。已出具的风险样本可用后两条命令独立核验。

```sh
curl --fail http://127.0.0.1:8000/api/cases/003c1f67ef1a46cead3b42fcaadeb1ba/reports/8/bundle -o /tmp/inspection-master-R8.zip
server/.venv/bin/python docs/samples/retest_use_notes.py /tmp/inspection-use --run --check-against /tmp/inspection-master-R8.zip
curl --fail http://127.0.0.1:8000/api/cases/66fa88c60aed4799a64ab73c0eb92495/reports/11/bundle -o /tmp/inspection-ban-R11.zip
server/.venv/bin/python server/verify.py /tmp/inspection-ban-R11.zip --render-performance --rules-from-git bec9e86
```

## 回单引用初验或复验

全新检出项目可以离线生成五组资料。母本是同一台冷藏柜的六份水印 PDF。生成器保留采购合同、初验、整改、复验及质保单，分别在银行回单末行写入初验号、复验号或一位差异的编号，并设置付款日期。生成后任选一组上传到网站，也可以加 `--run` 调用本机服务。[五组实测与固定版底稿](../acceptance.md#第二期回单究竟引用哪一张验收单)

```sh
server/.venv/bin/python docs/samples/retest_receipts.py /tmp/retest-receipts
```

生成 PDF 需要可嵌入的中文 TrueType 字体，可用 `AUDIT_CJK_FONT` 指定路径。在本机，两种生成方式的 30 份输出均与用于实际模型调用的文件摘要及逐页原文一致。

需要用当时已核的原行演练字段复核时，使用本机存档的 R8 母本。下列命令重建材料，另加 `--run --check-fields` 可提交并逐行核字。

```sh
curl --fail http://127.0.0.1:8000/api/cases/39184eab6f9c4f7ab522c03c8f574b98/reports/8/bundle -o /tmp/retest-master-R8.zip
server/.venv/bin/python docs/samples/retest_receipts.py /tmp/retest-master-R8.zip /tmp/retest-receipts
```

要重放已经出具的提前付款样本，可以从已提交的源码复算，并由六份原件重新生成页图和行坐标。

```sh
curl --fail http://127.0.0.1:8000/api/cases/9cdd1cf88afb490d90ec0d9d37b53fa0/reports/12/bundle -o /tmp/retest-early-R12.zip
server/.venv/bin/python server/verify.py /tmp/retest-early-R12.zip --render-performance --rules-from-git a0656c2
```

## 验收款回单日期与实测超限

母本取自冷藏柜采购 R7 的五份水印原件。合同限值 4℃，终验单列 9 月 20 日实测 8℃，第二期成功回单列 9 月 21 日。以下命令生成三组变体，分别将回单日改为 9 月 19 日、9 月 20 日，以及将回单用途改为「设备采购款」。生成器核对母本及原件摘要、水印和待改原行。

```sh
curl --fail http://127.0.0.1:8000/api/cases/64cd9e64345841bab358728a6730f3d8/reports/7/bundle -o /tmp/payment-quality-R7.zip
server/.venv/bin/python docs/samples/quality_payments.py /tmp/payment-quality-R7.zip /tmp/payment-quality-inputs
```

生成命令可加 `--run --check-fields`，使用本机服务逐页解析和复检，并按这组水印原件核字。下载已出具的 R8 证据包，可直接复核当时使用的程序及实物原页。[各回单的预期及实际结果](../acceptance.md#终验实测超限与第二期实付)

```sh
curl --fail http://127.0.0.1:8000/api/cases/64cd9e64345841bab358728a6730f3d8/reports/8/bundle -o /tmp/payment-quality-R8.zip
server/.venv/bin/python server/verify.py /tmp/payment-quality-R8.zip --render-performance --rules-from-git 312720c
```

## 董事会决议、柜温验收和第二期付款

母本是同一份带水印的采购底稿 R4，共五份原件。生成器先校验 R4 底稿及各原件的 SHA-256 与水印。四组输入分别使用签名覆盖提交版的 PDF、签后有增量修订的 PDF、有原生批注的 Word 及整页 JPEG。`hot` 使用同一份有批注的审批单，将验收单唯一一处实测值从 3℃ 改为 8℃，保留「合格」结论及第二期 6 万元回单。PDF 使用本次演练生成的测试证书。[九案与固定底稿](../acceptance.md#董事会批准条件及第二期验收款)

```sh
curl --fail http://127.0.0.1:8000/api/cases/9c84d34e49034b2096bb2edfe14918d6/reports/4/bundle -o /tmp/board-R4.zip
server/.venv/bin/python docs/samples/board_decisions.py /tmp/board-R4.zip /tmp/board-inputs
```

在生成命令末尾加 `--cases hot --run --check-fields`，可在本机上传该案、运行多模态解析和复检，并按生成的水印原行执行演练核字。以下命令可以独立核对已出具的组合案例，重新生成页图并从发布历史复算。

```sh
curl --fail http://127.0.0.1:8000/api/cases/64cd9e64345841bab358728a6730f3d8/reports/7/bundle -o /tmp/board-hot-R7.zip
server/.venv/bin/python server/verify.py /tmp/board-hot-R7.zip --render-performance --rules-from-git 1683c51
```

## 质保回单与期满单所列日期

用固定底稿 R11 的六份水印原件生成三组演练。回单均列 11 月 24 日，Word 期满单分别列 26 日、24 日和数字断开的「2 2 日」。三组都保留同一条 Word 原批注。生成器检查母本摘要、水印、原行与数字分组。使用 `--run --check-fields` 可向本机提交材料、调用模型并按水印件核字。[逐案验收](../acceptance.md#从质保金回单核对期满单原行)

```sh
curl --fail http://127.0.0.1:8000/api/cases/920ea04963ef4f68905ff87533133fd4/reports/11/bundle -o /tmp/warranty-R11.zip
server/.venv/bin/python docs/samples/warranty_originals_demo.py /tmp/warranty-R11.zip /tmp/warranty-date-inputs --dates
```

要独立复算「回单早 2 天」的底稿，可从本机下载其证据包。以下命令从六份原件重现页图，并使用发布提交中的 Python 程序逐项比较发现和整案建议。

```sh
curl --fail http://127.0.0.1:8000/api/cases/fd51542fc29c401196842a0a207f1e8b/reports/6/bundle -o /tmp/warranty-before-R6.zip
server/.venv/bin/python server/verify.py /tmp/warranty-before-R6.zip --render-performance --rules-from-git 4815867
```

## 同一张期满确认单的签署版本

生成器校验固定底稿 R11 的水印、六份原件和页图摘要，生成测试签名覆盖本版、签后修订、带批注的 Word 以及整页 JPEG 四组资料。加 `--run --check-fields` 会实际提交到本机工作台，按水印原行核字并留存每次复核。每次生成使用新的演练签名，可用独立输出目录保存各批文件。[新版演练结果](../acceptance.md#质保金第三期的期满确认单与原件批注)

```sh
curl --fail http://127.0.0.1:8000/api/cases/920ea04963ef4f68905ff87533133fd4/reports/11/bundle -o /tmp/warranty-R11.zip
server/.venv/bin/python docs/samples/warranty_originals_demo.py /tmp/warranty-R11.zip /tmp/warranty-inputs
```

## 同一期款的两张放行单

以下命令生成三组本地水印件。同一验收单的相反意见、另一验收单上的暂缓意见、相同决定列示不同日期均各有一组。加 `--run --review` 会向本机工作台提交材料，调用模型，再按生成件逐行核对。可通过 `--run-id` 生成新的演练批次。[既有固定底稿](../acceptance.md#多份放行单的适用期次与相反意见)

```sh
server/.venv/bin/python docs/samples/competing_releases.py
```

## 验收签认与复验原件

五案各取一版已签发的水印底稿，离线重算并导出公开的验收原件、页图、字段位置和批注选区。以下命令从本机已有底稿核对发布资产。使用 `--archives /path/to/bundles` 可改从证据包核对，文件名为 `clean-R9.zip`、`limited-R9.zip`、`hot-R9.zip`、`scan-R3.zip`、`retest-R3.zip`。[案件和固定底稿](../acceptance.md#验收签认数量签收与整改复验)

```sh
server/.venv/bin/python docs/samples/publish_acceptance_originals.py --check
```

扫描演练使用排印案 R8 的归档水印 JPEG，复验演练使用六份水印材料。下面的命令在指定目录生成两组输入。加入 `--run --check-fields` 会上传至本机服务，调用模型，并以模拟复核人核对指定字段。[排印验收单 R8 证据包](http://127.0.0.1:8000/api/cases/42400d4c7b5d40b8965a3a2ca69121ea/reports/8/bundle)

```sh
server/.venv/bin/python docs/samples/acceptance_originals_demo.py /path/to/clean-R8.zip /tmp/acceptance-examples
```

## 同一补充协议的 Word 批注与扫描件

本地已签发的两份 R5 和一份 R2 均可离线复算。以下命令核对固定报告摘要、逐页调用记录、公开原件及精确裁片所据的行坐标，两份 Word 的打印页须逐字节相同。[水印演练记录](../acceptance.md#word-与扫描版补充协议的收票条件)

```sh
server/.venv/bin/python docs/samples/publish_addendum_originals.py --check
```

离线运行时添加 `--archives /path/to/bundles`，目录应包含 `word_text.zip`、`word_review.zip`、`photo.zip`。要在本地生成演练输入，提供上一组第二期收票案的 R10 水印包和输出目录。添加 `--run` 会通过本机上传接口建立演练并调用模型。`--check-fields` 核对本次水印案的打印栏文字或扫描件标题，并留存模拟复核记录。[第二期收票 R10](http://127.0.0.1:8000/api/cases/8c2a157237cf4712856f64225466ee2c/reports/10/bundle)

```sh
server/.venv/bin/python docs/samples/addendum_originals_demo.py /path/to/payment-R10.zip /tmp/fish-agreement-demo --run --check-fields
```

## 补充协议的签名覆盖与收票前提

三份柜温协议保留相同水印版面。电子签名使用演练时生成的自签名证书，签后修订版在同一已签文件末尾追加元数据。收票案的补充协议和银行回单来自另一组采购原件。打开现有演练或重建静态资料均无需新调用模型。[演练与固定底稿](../acceptance.md#补充协议签署柜温标准与验收款收票前提)

```sh
server/.venv/bin/python docs/samples/publish_addendum_signing.py --check
```

离线重建时添加 `--archives /path/to/bundles`，目录内依次准备柜温案 R16 的 `typeset.zip`、两个 R1 的 `current.zip` 和 `earlier.zip`、收票案 R10 的 `payment-R10.zip`。导出器核验归档摘要、重绘六份原件、按固定 Git 源码复算，再逐字节比较十项公开资产。

单独准备一批新的签名演练件，可运行下列命令。重复指定同一输出目录会复用已生成的签名文件。在命令末尾加 `--submit` 才会向本机实际上传两组资料并调用模型。

```sh
server/.venv/bin/python docs/samples/addendum_pdf_editions.py /path/to/R15.zip --output /path/to/editions
```

## 四份首期预付款保函

每案有四份带「合成演练」水印的 PDF。采购方于 9 月 3 日签收，银行于 9 月 5 日付款。四份保函分别写明 9 月 4 日届满、9 月 5 日届满且包含当日、9 月 5 日届满但端点含义待核，以及展期申请尚待确认。每案有独立的合同号、保函号和流水号。

```sh
server/.venv/bin/python docs/samples/guarantee_periods.py --seed local-period-review
server/.venv/bin/python docs/samples/guarantee_periods.py --seed local-period-review --run
server/.venv/bin/python docs/samples/publish_guarantee_period.py --check
```

第一条命令生成演练原件，第二条通过本地服务上传并调用模型，第三条从固定的旧函止日风险案重建并逐字节比对公开样张。导出包含四份 PDF、四张原始页图和六条可回查的原行。首页加载这份静态索引。[生成器](guarantee_periods.py) · [固定样张导出器](publish_guarantee_period.py)

## 预付款保函与收函时间

四组盖有演练水印的原件采用三期采购合同。第一期约定预付款 30,000 元，采购方须先收到本合同项下的保函。演练分别提交只有保函、付款后才签收、付款前已签收，以及合同指定受益人与保函记载不同的材料。每组使用独立的合同号、保函编号及银行流水号。

```sh
server/.venv/bin/python docs/samples/advance_guarantees.py --run-id local-advance-review --run
```

省略 `--run` 会在本机临时目录生成 PDF 及原行清单。加上 `--run` 会正常上传并调用服务配置的模型，核对案件、原件、逐页调用、各期检查及首笔回单。同一演练标识可续跑。[固定版本验收底稿](../acceptance.md#预付款保函与首笔银行回单)

## Word 委托书和影像原件

下面的命令生成三套带水印的材料，并通过本机服务提交。两份 DOCX 打印页相同，其中一份的权限栏带有 Word 原生批注。第三份将同样的文字制成略有倾斜的 JPEG。每案还包含采购合同、验收报告、银行付款回单和质保期满确认单。演练按已知生成件核对抄录，保留模型记录与字段核图回执，最终验收交由审计员处理。[固定版本与实际发现](../acceptance.md#word-委托书和影像件)

```sh
server/.venv/bin/python docs/samples/mandate_originals.py --seed mandate-word-photo --run
```

仅生成本机样本时省略 `--run`。提交后可用相同 seed 和输出中的版本号只读核对某案，例如 `--seed mandate-word-photo --check word_review 6`。可选案例为 `word_text`、`word_review`、`photo`。本页已归档案例使用脚本的默认 seed，可用 `--compare 5 6 5` 对照留存的三个旧版与现版。

## 对照采购代理人的三份委托书

在仓库根目录运行以下命令，可生成三套带水印的五份采购材料。三份委托书中的被代理人、代理人、权限和日期相同，分别使用排印签章、自签测试证书、签后追加修订。加上 `--run` 后会提交本机服务，调用配置的多模态模型，按生成件核对字段，再检查签章凭证以及合同分期和实付结论。测试私钥仅存于生成进程内存。[三组演练底稿](../acceptance.md#同一项签约授权的三种签发凭证)

```sh
server/.venv/bin/python docs/samples/mandate_pdf.py --seed demo-mandate --run
```

## 校验首页采购样张

首页为合同、验收单和回单各提供 112、168、420 像素宽的原页缩略图。窄屏图从同一归档页重新取样，下面的校验命令覆盖三个尺寸。验收及合同对照区的窄屏预览复用相应文件。

从冷藏柜采购演练 `ed7751a871aa4fb1a8574eddada0254b` 的 R8 导出证据包。在仓库根目录运行以下命令，可逐字节复核首页使用的缩略图、原行裁片、字段索引及回单页图。省略 `--check` 会从已核对的固定原件重新生成这些文件。[原件和引文登记](../../3rd/showcase-provenance.md#首屏三份原件与九个字段)

```sh
server/.venv/bin/python docs/samples/publish_purchase_preview.py purchase-R8.zip --check
```

## 验收 PDF 的签名覆盖范围

以下命令生成三套带水印的采购合同、验收单和第二期付款回单，在本机服务中运行多模态取证和审计。三份验收单使用相同文字，分别保留排印签字栏、嵌入测试签名、在签后追加修订。测试证书和私钥在生成器进程内创建，人工验收决定留空。

```sh
server/.venv/bin/python docs/samples/pdf_signing.py --acceptance --run --seed local-acceptance-proof
```

只生成本地示例文件时省略 `--run`。同一案的重审、字段核对和导出均按版本留存，已归档的三个案例可直接打开。[工作底稿和实际读数](../acceptance.md#验收签认与分期付款)

## 同一天签认和扣款

下列三笔采购使用同一份终验约定。周宁于 9 月 20 日签认，林岚于 9 月 25 日 15:20 签认。第一笔回单列 13:10 实际扣款，第二笔列 16:30 实际扣款，第三笔只列 16:30 打印时间。均为北京时间。复核员可从第二期验收款点开具名签认和回单原行，核对当时具备的证据。

```sh
server/.venv/bin/python docs/samples/acceptance_signers.py --run --run-id local-signer-clocks --cases clock_early clock_late clock_print
```

## 分期付款所引验收凭证

在项目根目录运行以下命令，将四套带水印的 PDF 发给本机审计服务。各案例保留模型原始观察和后续按原页核对的版本。使用新的运行编号可创建独立演练。

```sh
server/.venv/bin/python docs/samples/delivery_batches.py --run --run-id local-bank-reference --cases bank_cross bank_match bank_absent bank_split
```

四个场景分别覆盖回单错引另一批、单号相符、缺少所引原件，以及同一期两笔回单一笔错批。拆款场景保留合同 35% 的约定和两笔人民币金额。[业务预期与可核对的底稿](../acceptance.md#分期回单引用的验收单号)

## 合同分期付款批注

运行 `server/.venv/bin/python docs/samples/contract_comments.py --seed fish-contract-review-v1` 生成三套水印资料，可用 `--case second` 或 `--case third` 单独生成第二期或第三期有修订建议的版本。三个 Word 合同的打印页完全相同。附加 `--run` 会提交到本机，使用实际模型读页，由脚本对照水印原件、摘要和文字行模拟字段复核，随后断言付款安排及实际受批注影响的发现。已有同一批资料时按原件摘要复用。[本机验收记录](../acceptance.md#合同分期付款批注) · [试核第二期付款](http://127.0.0.1:8000/?scene=contract-comments#workflow)

## Word 验收审阅意见

`server/.venv/bin/python docs/samples/word_acceptance.py --seed fish-word-acceptance-20261126` 生成三套带水印的本地演练资料。`clean` 是 3℃ 且无批注的验收单，`limited` 将数量签收意见附在同一打印行的“合格”上，`hot` 将实测值改为 8℃ 并保留相同批注。可以用 `--case limited` 单独生成第二案。

追加 `--run` 会提交到本机服务，以相同种子及原件摘要重跑时可复用原案。脚本对照水印、文件摘要、页图和文字行模拟字段核读，并核查 H02 和引用它的期款。模拟核图只用于这组水印演练。查看最终意见需要审计员签收。[三份固定底稿](../acceptance.md#word-验收正文与审阅批注) · [试读含批注的验收单](http://127.0.0.1:8000/?scene=word-comments#workflow)

## 供货主体与 PDF 签署意见

运行 `server/.venv/bin/python docs/samples/supplier_annotations.py --seed supplier-demo` 可生成六套带水印的资料，覆盖签后附注要求取得送货单、终验供货方与合同不同、合同或验收单仅签认到货数量，以及同一验收报告两种顺序的连续签名。[供货主体演练结果](../acceptance.md#验收供货主体批注和签署原因)

以下命令会将两个签署范围案例上传至本机服务。脚本核对原件摘要和水印，模拟审计人员核对字段，再检查签名原因原文、所签文件与受影响的期款。生成的自签证书仅用于水印演练。[两个案例的预期差异](../acceptance.md#签名只确认到货数量时的合同与验收款)

```bash
server/.venv/bin/python docs/samples/supplier_annotations.py --seed quantity-review --case reason receipt_reason --run
```

用 `--case receipt_pair receipt_pair_reverse` 可对照两种顺序。脚本核对每条原因及证书所签修订的字节摘要、验收风险引用的修订、后两期条件与实际付款的证据。每次生成使用新的演练证书，上传重试编号由整组原件的摘要确定。[两次签认的预期结果](../acceptance.md#一份验收报告的两次电子签认)

## 排印稿、电子签署版与签后修订版

运行 `server/.venv/bin/python docs/samples/pdf_signing.py --seed pdf-demo`，生成目录会打印到终端。加 `--run` 将这三套水印资料提交到本机审计服务，并在核对原件与页图摘要后模拟审计人员核验。每次生成都会创建新的虚构自签证书，签名文件的摘要随之变化。[固定底稿及实测结果](../acceptance.md#pdf-签名覆盖与付款条件)

## 同一合同上的生效日期

运行 `server/.venv/bin/python docs/samples/printed_dates.py conflict --seed calendar-demo-01` 可生成两处生效日不同的水印合同、验收单、回单和质保确认单，并上传本机审计。把 `conflict` 换成 `mixed` 可核对原件混用分隔符的情况。追加 `--check-fields` 会对这一组水印文件模拟字段核图，先核实本案全部文件摘要和当前版本，再依据原页更正错列或漏读。重复使用相同种子和模式会打开原案。[演练结果](../acceptance.md#合同日期与三期付款)

## Word 验收款比例断字

`server/.venv/bin/python docs/samples/word_percentage.py` 生成一份单页 Word 合同和三份 PDF，每份都印有合成演练水印。第 17 行写作「最终验收合格后支付6 0%」。加 `--run` 会先检查分页和水印，再经本机上传并核对文件摘要、付款计划及第二期结论。[固定样例与旧规则对照](../acceptance.md#word-合同的转录空格与期款比例)

## 合同付款续页

`server/.venv/bin/python docs/samples/payment_folios.py` 生成四套带测试水印的采购资料。每套有两页合同、终验报告、银行回单和质保期满确认单。四套资料的比例均为 30%、60%、10%，分别为同编号续页、讨论稿、异号续页、正文约定首款独立执行。加 `--run` 通过本地服务实际解析，生成器依据文件、页图摘要及逐行原件核对字段并检验逐期结果。

## 冷藏柜试运行日志

四组带水印的采购材料覆盖两班连续交接、中途缺半小时、故障停机半小时和设备号不符。每组有六份原件。日志印在复验签认所在页，断档两端及故障行可在网页逐条核对。

```sh
server/.venv/bin/python docs/samples/device_trial_logs.py --run --run-id trial-demo
```

省略 `--run` 只生成 PDF。使用 `--run` 时经本地服务调用多模态提取和专家程序。演练中的签认和转录补正均对照带水印原件、页图和摘要，保留原始识别及每次修订。

## 合同复验等待期

每案生成带“合成”水印的合同、初验单、整改记录、复验报告、质保确认和第二期付款回单。六案覆盖次日出具报告、间隔充足、提前开验、只有日期、缺开验记录、连续试运行缺证。演练通过上传接口调用多模态模型，按相同原件及页图摘要补录有据的字段、核准水印样本签认栏，再检查验收发现、三期条件和实付结果。

```sh
server/.venv/bin/python docs/samples/reinspection_timing.py --run --run-id wait-demo
```

省略 `--run` 仅生成文件。用 `--cases elapsed boundary` 可只跑实测间隔充足与记时精度不足两例。

## 首款凭证和验收款先后

八组水印采购材料覆盖首款缺件、足额、分笔补足过晚、同日、仅付部分、归属不明、约定收款方实际到账和验收温度超限。每份合同有三期付款，约定首款三万元。脚本逐份核对文件和页图摘要，在生成的水印原件上模拟字段核图。省略 `--run` 可只生成文件。

```sh
server/.venv/bin/python docs/samples/prior_installments.py --run --run-id prior-demo
```

## 逐台测温与抽检范围

十组水印资料均含十万元采购合同、验收报告、质保确认单和第二期六万元回单。七组演练逐台检测不足、逐台齐全、达到抽检下限、同台重复、单台超限、仅有汇总和抽检下限未约定。另三组均要求至少抽检两台且指定 QC-02、QC-03，分别演练指定设备缺记录、记录齐全和其中一台超限。脚本核对生成件、文件摘要和原页后模拟人工更正与核验，旧版底稿保留初次模型结果。去掉 `--run` 可只生成单据。[三组指定设备的实际底稿](../acceptance.md#合同点名的必检设备)

```sh
server/.venv/bin/python docs/samples/unit_inspections.py --run --run-id inspection-demo
```

## 合同照片与扫描用印页

六套水印采购资料覆盖电子正文附扫描页、双方分别回传用印页、整份合同拍照、名称遮挡和仅有交接封面的附件。脚本核对原件、页图摘要及生成页上的印刷文字，模拟审计员核对约定主体、签章栏和印章单位。复跑同一 `--run-id` 会复用相应案件。省略 `--run` 可只生成资料。[六案的实际结果](../acceptance.md#合同照片与扫描用印页)

```sh
server/.venv/bin/python docs/samples/signing_images.py --run --run-id signing-images-demo
```

## 合同约定单位、签章和印章单位

以下命令提交五组虚构的合同履约材料，包含分公司名称不同、三处名称相符、名称遮挡、签章栏直接写分公司、同一方重复列出两个用印单位。每次对照均核验合成资料名称、原 PDF 摘要和实际印刷原行，再模拟字段核图。省略 `--run` 只在本机生成材料。[已验证的五个案例](../acceptance.md#合同签章主体和分公司名称)

```sh
server/.venv/bin/python docs/samples/signing_parties.py --run-id party-seal-demo --run
```

## 横置照片与签认被遮挡的扫描件

两套采购资料分别含一张横置工单照片、一份带封面的双页扫描 PDF。第二页遮住了采购方签认。使用以下命令生成水印样本并提交到本机服务，核对影像页号、文件和页图摘要、状态栏的模拟核图回执及质保金结论。省略 `--run` 可只生成文件。[本机验收底稿](../acceptance.md#拍照与扫描工单的原页和签认)

```sh
server/.venv/bin/python docs/samples/warranty_photos.py --run-id warranty-image-demo --run
```

## 委托书出具与签约时点

四组采购均由同一名演练代理人在 9 月 1 日签约，合同分 30%、60%、10% 三期。分别改变委托书授权起止或出具日期。以下命令实际上传合同、委托书、终验、质保确认单和回单，调用本机配置的多模态模型，按水印生成件核对可见签字和字段，等待出具底稿。去掉 `--run` 可只生成文件。

```sh
server/.venv/bin/python docs/samples/mandates.py --cases last_day before_start issued_later same_issue --run-id mandate-date-demo --run
```

已有的 `expired`、`receipt` 和 `split_expiry` 还可检验签约超过截止日、仅授权收货，以及截止日断字。[各案原件和预期结论](../acceptance.md#委托书出具与代理签约的先后)

## 验收款签字放行

以下命令生成六套带水印的采购合同、验收报告、银行回单、质保确认单和付款放行单。银行实付日相同，分别改变签字日、签认人、原验收单号或日期字段。加 `--run` 后通过本机服务调用已配置的多模态模型，核对生成件后模拟签认，等待生成底稿。`--cases late same` 可仅运行提前及同日两案。

```sh
server/.venv/bin/python docs/samples/payment_releases.py --run-id release-demo
server/.venv/bin/python docs/samples/payment_releases.py --run-id release-demo --run
```

单项结果分别核对合同生效、终验、三期条件和银行实付。整案留待人工验收。[各案期望结果及固定版本](../acceptance.md#具名放行与银行实付)

## 终验报告和付款意见

运行以下命令生成四套水印原件，分别演练全部暂缓、单期暂缓、同一期意见相反以及同意支付但实测超限。加 `--run` 通过本机服务上传到配置的模型，核对原件后模拟签字栏核图。可以用 `--cases phase conflict` 选取场景。

```sh
server/.venv/bin/python docs/samples/final_payment_opinions.py --run-id final-opinion-demo
server/.venv/bin/python docs/samples/final_payment_opinions.py --run-id final-opinion-demo --run
```

每一期的预期结果和固定底稿列在[本机验收记录](../acceptance.md#终验合格与付款能否放行)。

## 验收款新增收票前提

以下命令生成四套采购原件并逐案提交真实模型。四套采用相同的采购及终验条款，合同号各异，第二期均为 60%。协议生效日、买方签收记录和一方的签章状态分别变化。去掉 `--run` 只生成带水印的文件，`--cases earlier same_day` 可选择情形。

```sh
server/.venv/bin/python docs/samples/payment_condition_changes.py --run --run-id payment-change-demo
```

印刷原行与文件摘要对应后，脚本可补正模拟案例的字段及核图记录。最终的人工验收交给审计人员。[四笔底稿与预期判断](../acceptance.md#验收款收票条款变更)

## 两批验收之间改了柜温上限

以下命令上传四套水印原件。第一套将上限从 4℃ 放宽到 8℃，第二批实测 6℃。第二套收紧到 2℃，第二批仍按 4℃ 验收，实测 3℃。第三套的第二批验收日期与乙方盖章栏日期相同。第四套把盖章日印成「2026年9月1 2日」，需核对原行。每案另附注明第三期的银行回单，以核对这笔 35% 款项的付款前提。

```sh
server/.venv/bin/python docs/samples/batch_quality_changes.py --run
```

首页「分批验收标准变更」采用第二套原件和两份已出具的底稿，默认展示 R15 重审，菜单可切换到历史 R14。在仓库根目录执行下列命令可从本机固定版证据包重建并核对 11 个公开文件。已有证据包时，加上 `--r14 /path/to/R14.zip --r15 /path/to/R15.zip` 即可离线核验。[公开数据来源](../../3rd/showcase-provenance.md#两批冷柜的标准与读数) · [四案重审结果](../acceptance.md#两批验收采用哪一版标准)

```sh
server/.venv/bin/python docs/samples/publish_batch_version.py --check
```

## 四台设备的退换交接

七笔水印采购均由合同、初验、整改、交接、复验、银行回单和质保期满确认单组成。在仓库根目录运行下列命令，去掉 `--run` 可只生成原件。

```sh
server/.venv/bin/python docs/samples/equipment_exchanges.py --run --run-id synthetic-equipment-exchange-v1
```

`complete` 的四台退回与四台换入设备分别能和两次验收对应。`serial` 只改交接单上的第四台换入编号，`unsigned` 缺供应方签认，`late` 的交接晚于复验，`other` 的交接单写有另一合同号。`rider` 在交接单另写第二期改付 80%。`scan` 把完整交接单制成只有像素的扫描 PDF，保留实际模型初读和原图。演练可按 `--cases complete serial` 选择。整案的人工验收决定留给审计人员。

扫描案例仍校对其他六份电子原件，并验证扫描页的模型观察与初读一致。交接单上读到的编号可打开原图复核。

## 验收的是哪一种设备

在仓库根目录运行下列命令，可上传十一组合成采购资料。每页均带演练水印。去掉 `--run` 只生成文件，追加 `--cases wrong batches approval` 可选择个别案例。

```sh
server/.venv/bin/python docs/samples/equipment_models.py --run --run-id synthetic-equipment-models-v1
```

`match` 和 `wrong` 的验收数量、温度、签认及回单均相符，合同和验收单的完整型号分别相同或不同。`absent` 缺实收型号，`masked` 遮盖末位，`substitute` 另有经批准方可替代的约定，`image` 将换型说明放在验收页的影像中，`foreign` 使用另一合同号的验收原件。`approval` 的型号相符但缺董事会批准，`quality` 的型号相符但柜温超限，`batches` 的两批独立验收，只有第二批所列型号不同。

`camera` 同时上传原生 Word 合同、只有像素的 JPEG 验收单和两份 PDF。保留模型的首次读图供人工核对。脚本核对模型响应、所据原页、实际期次与整案建议，底稿留待审计人员签收。

执行 `server/.venv/bin/python docs/samples/equipment_reinspection.py --run` 可再核对四组整改资料。`generic` 和 `formal` 的初验型号不同，复验都写回约定型号，两组分别使用普通验收表和专门复验表。`wrong` 的复验温度达标但复验型号有异，`same` 的两次型号相同且温控缺陷有完整整改和复验依据。

## 分期款分几笔支付

在仓库根目录运行以下命令，生成并上传 11 组水印采购资料。每组有合同、验收报告、质保确认单和两张银行回单。本机工作台需已启动。去掉 `--run` 可只生成文件，追加 `--cases approval quality early` 可只运行三个指定情形。

```sh
server/.venv/bin/python docs/samples/stage_transfers.py --run --run-id synthetic-stage-transfers-v1
```

`balanced`、`partial`、`excess` 分别验证本次回单合计等于、少于和超过第二期约定金额。`repeat` 提交同一流水的两份副本，`conflict` 用相同流水列出不同金额，`reversal` 在回单上注明冲正。`allocation` 的一张回单同时写了两个期次，`separate` 的两笔则分属预付款和验收款。`approval` 缺合同要求的董事会批准，`quality` 的实测柜温超过合同上限，`early` 的第一笔付款早于验收。这三组的两张回单均合计 6 万元。

运行时经上传接口调用实际模型，按生成件摘要和印刷原行校对演练资料并留存修订，再断言各项结果。工作台保留最初读图、后续更正及待审计人员签收的最终版本。

## 验收单合成一份 PDF

运行 `server/.venv/bin/python docs/samples/receipt_packets.py` 生成中文水印资料。加 `--run --run-id 本次演练编号` 可走本机上传、逐页多模态识别、合成原件校对与审计流程。`--cases ordered borrowed quality duplicate continuation masked` 分别覆盖倒序装订、只在其他页签名、实测超限、重复单号、归属不清的续页和不完整编号。另有 `retest`、`wrong_defect` 和 `approval`，分别演练同一册内的整改闭环、复验引用错误缺陷号，以及合同约定的董事会决议缺件但验收单均已签齐。每个案例仍保留独立的合同、质保确认与银行回单。脚本按原件摘要、物理页和生成时印刷的文字进行补正和签认，演练不会替审计员签收业务结论。


## 分批验收人与终验签字人

`server/.venv/bin/python docs/samples/final_signers.py` 生成九组带水印的虚构设备采购资料，覆盖分批与终验分别具名、同一人只签分批、换人签终验、合同仅指定终验人、缺少总单、全员签字且实测超限、代签影像和合同附加会签。用 `--run --run-id 本次演练编号` 可在本机完成上传、多模态解析、生成件原行核对与规则验收。脚本核对模型调用记录、每期条件、总单签字范围、图谱关系和质保起算，最终签收留给审计人员。

`server/.venv/bin/python docs/samples/final_signers.py --cases three_scoped` 仅生成三人名单的用例。第二批和全套终验各点名三人，陈和平只签了第二批。第四期质保金回单记载已付 1 万元。加 `--run --run-id 本次演练编号` 可运行上传及审计流程。[固定版原件与预期结果](../acceptance.md#分批签认与单独终验所据的质保期)

## 分批交付后的另行终验

`server/.venv/bin/python docs/samples/batch_final.py` 生成八组带水印的虚构冷柜采购 PDF。每案两批设备、四期付款，末笔回单均为 10,000 元。场景覆盖总单和批次单号相符、漏引、错引、列入其他设备、终验先于末批、实测超限、质保金提前实付和总单影像附注暂停付款。`--run --run-id 本次演练编号` 将原件上传本机工作台并等待真实多模态解析。字段校正和模拟签字核图仅对文件摘要与生成件一致的演练资料执行。演练的最终决定留给审计人员。

所有样本均标注「合成演练资料」「无交易效力」，单位、编号及交易数据均为虚构。可直接在本机工作台打开已运行的案例，也可将 `generated/` 目录中的资料重新上传。

| 场景 | 提交资料与预设事实 | 验收要点 |
| --- | --- | --- |
| 档案柜采购 | Word 合同、电子 PDF 发票、PDF 到货验收单。同合同、主体、标的与一次性结算条款，未税 10,000 元，税额 1,300 元，三单含税均 11,300 元 | 金额勾稽相符。按履约程序重算时，签署与终验范围仍需补证 |
| 同号票据与金额差异 | 两份同号票据各记载含税 13,300 元，未税及税额之和为 11,300 元 | 建议不通过，票内差额为 −2,000 元，同号列为风险，逐份保留原件 |
| 模糊扫描与缺件 | 一份扫描 PDF 的发票总额被模糊处理，缺合同及验收单 | 需要人工校验，视觉候选保留，未用缺失金额推算通过 |
| 分票结算与跨单汇总 | 两张不同号码的分期发票，各 5,650 元，合同和验收均为 11,300 元 | 核对主体、编号、标的、币种和单位后汇总为 11,300 元，分期适用条件交人工校验 |
| 差旅超额与跨期 | 差旅报销申请 1,200 元，所附两张具名住宿票据共 1,050 元，一笔消费发生在返程之后 | 建议不通过，申请超过已关联凭证 150 元，同时列出跨期费用风险 |
| 拍照取证与退回补件 | 同一演练票据的 JPEG 原图，核对清晰的票号，保留模糊的总额 | 核图后生成 R2，R1 仍可查。测试人员以演练身份退回补件 |
| 同票补件重提 | 上一案退回后，提交清晰的同号发票和配套合同、验收单，三单金额均为 11,300 元 | 本案金额相符，命中历史已退回的票号 YL-FP-038。审计人员可对照历史底稿与页图确认补件关系 |
| 采购三单合订 | 一份三页电子 PDF，依次放入合同、发票、验收单，三页含税金额均为 11,300 元 | 三份单据的标题、金额和引用分别绑定第 1、2、3 页。按履约程序重算时，签署与验收材料仍需复核 |

## 复现

样本生成工具还需要 `python-docx` 和 `reportlab`。本机环境已具备。以下命令在仓库根目录运行。

```sh
server/.venv/bin/python docs/samples/run.py
```

`run.py` 首次运行会生成资料，随后通过真实上传接口运行五组样本，等待后台完成并检查预期的建议、差额及证据状态。再次使用原样本和原提交编号将复用已有任务。手动更新或重新生成样本后，使用新的 `--run-id` 提交修改后的资料。照片场景可另行上传 `03-模糊扫描与缺件/现场拍照.jpg` 并在界面填写演练验收意见。

对照照片原页核准「发票号码」字段 YL-FP-038，并以演练身份退回归档后，可运行 `run.py --include-resubmission` 加验归档票号勾稽。历史照片的单据标题尚待核准时，底稿同时注明「原资料类型待核」。真实模型可能留下待核字段，如住宿发票被误分类。请在工作台查看原页、更正或提出异议，重算后再次运行同一命令即可复用现有任务。

`run.py --include-packet` 加验合订件。两个选项可以同时使用。

## 同票报销签收

`server/.venv/bin/python docs/samples/concurrent_invoices.py --run` 在本机提交两份票号相同的 636 元合成差旅报销。等两案均生成底稿后签收甲案，验证乙案原版被拦下，再核对重算后的同号发现。生成使用可嵌入的中文 TrueType 字体，可通过 `AUDIT_CJK_FONT` 指定。改用 `--pause-after-first` 会将乙案留在待验收，可运行 `node frontend/tests/workspace.mjs --invoice-conflict-case 乙案编号 --live`，在 Chrome 打开签收提示并实际重审。

差旅补件签收场景可运行 `server/.venv/bin/python docs/samples/invoice_approval.py --run`。先退回只有住宿发票的任务，再沿用原件补交报销单，由另一名演练审计员核对同票前案并签收。改用 `--refer` 可停在提交复核，随后用 `node frontend/tests/workspace.mjs --invoice-approval-case 补件编号 --live` 在浏览器签收并查看回执。`--single-ready` 准备另一份独立的完整报销，可用同一网页测试命令验证没有匹配前案的初审签收。

## 离线回归

`server/.venv/bin/python docs/samples/writer_contention.py` 会建立独立临时数据库，处理一张带演练标记的照片。页面提取与专家响应由受控函数提供，SQLite、网页和后台写入走真实流程。Chrome 在桌面和手机宽度看到等待提示后，演练释放写锁，检查原任务完成且只处理一次响应，再离线复算底稿。

```sh
PYTHONPATH=server server/.venv/bin/python -m unittest discover -s server/tests -v
```

离线回归使用独立临时目录与受控模型输出，覆盖小数差异、量纲、歧义、图谱引用、人工核图、重复提交、旧版验收拦截、重启恢复和证据包一致性。上述真实样本运行另行核实模型可用性和文档呈现效果。

### 专家响应中断恢复

`server/.venv/bin/python docs/samples/expert_recovery.py --run --browser` 在临时企业里提交一张带水印的发票，真实调用模型。子进程在底稿写入前退出，Chrome 可检查此时的逐页进度和专家响应保存状态。脚本接着备份、恢复到新目录，清空恢复进程的模型密钥并把请求额度设为已用数量，再核对重新生成的底稿、专家响应编号和企业用量。可省略 `--browser` 只运行恢复与证据包核验。

## 银行回单演练

`server/.venv/bin/python docs/samples/bank.py` 生成两套带水印的虚构合同与回单，使用可嵌入的本机中文 TrueType 字体。加 `--run` 会实际上传并核对两案结论。第一套合同与付款同为 8,400 元，收款账户相符。第二套回单为 8,550 元，较合同高 150 元，且与约定收款账户不同。长账号出现模型多读数字时，程序会保留待核引文，审计人员可打开原页逐项更正后重算。测试账号和页面均无交易效力。

### 跨任务付款回单

`server/.venv/bin/python docs/samples/cross_payments.py --run` 在本地演示库顺序提交三项任务。脚本先核对合成原件摘要、合同号、账户、流水及通过建议，再以「合成演练验收」签收自身生成的首次付款。随后提交原回单副本和另一张全额付款回单，两案分别应命中 B06 和 B07，停在待人工验收。单独运行脚本会仅生成带水印的 PDF。指定新的 `--run-id` 会生成独立的合同号及流水，可重复演练。

### 跨案分期付款

`server/.venv/bin/python docs/samples/installment_payments.py --run` 生成总额 8,400 元的合成合同，先核对原件摘要和成功流水，以演练身份签收 4,200 元首期回单。再提交 4,350 元的另一流水，检查 B08 的 150 元超额线索。另案重复提交首期回单，B06 提示重复，B08 只累计一次。用 `node frontend/tests/workspace.mjs --installment-case 案件编号` 可在浏览器检查任一后续案例，点回签收版原页。

### 退回后补充或替换原件

`server/.venv/bin/python docs/samples/returned_files.py --run` 创建只含合同的虚构付款案，核对原件摘要及 B01 缺口后以演练身份退回。随后沿用同一合同，补交对应回单，并检查原退回版本及本次建议。加 `--prepare-parent` 可仅准备退回任务供网页操作。

对已退回、已核票号 YL-FP-038 的合成照片，使用 `--replace-photo 前案编号` 会以合同、发票、验收单三份合成 PDF 替换原照片，核对历史同号风险和签收来源。脚本只对指定的本机演练资料执行。

### 付款差额的独立复核

`server/.venv/bin/python docs/samples/second_signoff.py --run` 提交两份带水印的合成 PDF。脚本先核对原件摘要及 B04 算出的 150 元超付款，再用两个演练姓名完成转交与退回，检查两个版本的模型建议和原图一致。用 `--refer` 只执行到转交，可在台账的「待复核」里接手。选择新的 `--run-id` 会生成独立的合同号和流水号。

### 对照原照片核准票号

`server/.venv/bin/python docs/samples/field_confirmation.py --run` 上传一张带水印的合成发票照片。脚本核对上传原件的摘要，按生成时印入的票号模拟确认、更正或补录，只签认票号。模糊的金额保留待核。完成后会输出可直接打开该字段的底稿链接。用 `node frontend/tests/workspace.mjs --field-case 案件编号` 可在 Chrome 验证原版底稿链接，读取实际原件与页图比对摘要，并检查六档屏幕宽度下的核图记录。

### 八位同号的两张电子普通发票

`server/.venv/bin/python docs/samples/invoice_codes.py --run` 生成两张带水印的虚构发票，代码分别为 099926001011、099926002011，票号相同，金额分别为 212 元和 424 元。一份合订 PDF 载两张发票，另一份报销单逐项列出组合。脚本核对 I01 的票据标识，并检查缺少可核申请引文时 T03 暂缓计算。

使用 `server/.venv/bin/python docs/samples/invoice_codes.py --cross` 可提交三个独立的合成任务。甲、乙为同号异代码两笔报销，乙签收时重新查询并随回执保存甲的代码原页。第三案沿用甲票，签收时提示前案有变化，重审后同时显示与甲的同票线索和乙的排除依据。第三案留给审计人员复核。用 `node frontend/tests/workspace.mjs --invoice-code-case 案件编号` 可在浏览器检查乙或第三案的原页跳转。

使用 `server/.venv/bin/python docs/samples/invoice_codes.py --masked` 生成金额同为 636 元、号码同样有星号遮盖的申请和 PDF 发票。`--masked-photo` 改用带水印的发票照片，以演练身份只确认抬头及实际可见的号码字符。两个脚本均检查系统暂停完整标识比对与报销金额勾稽。用 `node frontend/tests/workspace.mjs --masked-invoice-case 案件编号` 可检查两份资料的引文及手机页面。

### 遮盖流水与只列尾号的回单

运行 `server/.venv/bin/python docs/samples/partial_receipts.py --run`，工作台将分别接收中段印有 XX 的回单，以及流水栏印有 0042、同页另行说明仅显示后四位的回单。脚本核对上传原件、原文提示、分期规则状态及累计金额是否暂缓。使用 `--run-id` 可生成新的一组演练合同。

### 照片流水栏和页脚说明

`server/.venv/bin/python docs/samples/partial_receipts.py --photo --run` 生成一份合同 PDF 和一张带水印的 JPEG 回单，通过本地接口上传、等候模型读图并检查分期付款结果。脚本核对照片 SHA-256，并按生成时留存的抬头、付款户名、流水和说明原文模拟核图，所用演练身份和操作均记入底稿。可用 `--run-id` 指定另一组样本。

`--whole-photo --run` 生成完整流水恰为 0042 的水印回单，模拟核对栏内字符，留下整页展示范围供审计员判断。加 `--scan` 可用纯图像 PDF 跑同一流程。在合成照片任务中，`node frontend/tests/workspace.mjs --visibility-case 案件编号` 会先核对上传原件与本机样本摘要，再通过真实网页登记“完整显示”，检查新版是否引用操作时的底稿。

### 账号抄录与原页对照

在带水印的付款任务上运行 `node frontend/tests/workspace.mjs --account-review-case 案件编号 --account-revision 版本号`，检查 B03 的合同和回单引文、逐位差异、原图定位以及缩窄窗口后的可读性。该工具同时验证预览加载失败后的原页重试。省略 `--account-revision` 可检查最新底稿。
## 合同履约演练

运行 `server/.venv/bin/python docs/samples/contract_milestones.py --run` 生成水印 PDF，上传本机工作台，从多模态提取一直执行到逐期审查。脚本仅对与生成件摘要、原页文字均一致的虚构签署栏写入演练核图记录。

三组合同价均为 10 万元，分 30%、60%、10% 三期，回单均记载第二期 6 万元。第一组在终验前付款，且缺少质保到期确认。第二组报告写“合格”，实测柜温 8℃ 超过约定上限 4℃。第三组实测 3℃，终验后付款，同时提交质保期满确认。旧版样本的历史结论保留在相应版本；以新方法重算时，缺少履约证据的样本会提示人工校验。

加上 `--cases approved denied` 单独运行两组附董事会批准条件的案例。两组合同签署及验收材料同样齐全，审批决定分别是“批准”和“退回补议”。

### 采购方委托代理人签约

运行 `server/.venv/bin/python docs/samples/mandates.py --run` 会上传四组水印件。每组各含合同、委托书、验收报告、质保确认和一份第二期回单。签约日都是 9 月 1 日。第一组书面授权签约至 9 月 30 日，第二组在 8 月 31 日到期，第三组只授权收货验收，第四组的备注要求采购总监另行书面批准。脚本以生成件摘要和逐行原文核对演练签字、签章及字段分类。可在本机用 `node frontend/tests/workspace.mjs --performance-case 案件编号` 检查授权日期、权限、备注以及各期条款的原页跳转。

使用 `--cases prepay_limit amount_limit two_approvals split_expiry` 可检验一份委托书载有两条不同的限制、签约总价超过上限、两份审批待核和授权截止日断字。浏览器回归入口为 `node frontend/tests/workspace.mjs --mandate-case 案件编号`。[四笔底稿、原件与版本](../acceptance.md#2026-11-25--合同签约权限的四笔演练)

运行 `server/.venv/bin/python docs/samples/mandates.py --run --cases role joint redacted --run-id synthetic-signing-identity-v1` 可比较两份文件同写“采购负责人”、同列两名代理人、同写“张某”的三种签约情形。每组均核对受托人原文字段、未确认的图谱关系、三期条件及第二期实付时点。

运行 `server/.venv/bin/python docs/samples/mandates.py --run --cases spaced compound --run-id synthetic-printed-agent-v1` 比较两组四字写法。一组签字栏、受托人栏均印“周宁 方程”，另一组均印“欧阳明月”。演练核对姓名中的间隔、原页逐行记录和各期付款条件。

### 缺陷整改及最终复验

以下四组资料可复核整改附注、日期断字、缺陷关闭及复验错号。带 `--run` 时从本机提交水印文件，按原件核对模型观察及模拟签章。各案的审计员最终决定留空。[四案原件和固定底稿](../acceptance.md)

```sh
server/.venv/bin/python docs/samples/quality_reinspection.py --run --cases temporary split_repair_date closed mismatch --run-id synthetic-repair-completion-20261125-21
```

运行 `server/.venv/bin/python docs/samples/quality_reinspection.py --run` 生成并核验三组水印件。9 月 10 日交付的冷藏柜实测 8℃，高于合同上限 4℃。9 月 16 日完成整改，9 月 20 日复验实测 3℃。三案分别核查复验后的第二期付款、复验前已付的验收款以及缺陷号不同的复验报告。每一组均保留首次失败记录。

### 合同指定验收人和共同签字

运行 `server/.venv/bin/python docs/samples/acceptance_signers.py` 生成带水印的虚构采购资料。加上 `--run` 会通过本机网页使用的上传接口提交五案，核对原件摘要后按印刷行补正并模拟核图。用 `--cases joint missing different retest image` 可单独选择签字齐备、缺一人、换人签字、复验缺签或含影像代签说明的案例。每笔仍以同一总价及三期安排核查，可从 H02 签字栏原页追到受影响的付款结论。[已验证的五份本机底稿](../acceptance.md#2026-11-24-合同约定的验收签认)

### 合同期间、验收日和实付日

`server/.venv/bin/python docs/samples/contract_dates.py --run` 生成四笔相同金额及分期比例的水印采购。可用 `--cases early reversed same_day warranty` 选择终验早于董事会批准生效、合同截止早于生效、同日验收并付款或期内验收且期后质保届满的场景。

### 两次交付各付 35%

运行下列命令，从本机上传入口提交七笔虚构的冷藏柜采购案。每案合同价 10 万元，四期比例为 20%、35%、35%、10%。每批约定验收两台。样本脚本核对原件摘要及印刷原行后，为水印签字栏留存模拟核图记录。生成的 PDF 在 `docs/samples/generated/30-分批交付与独立验收付款/` 下。

```sh
server/.venv/bin/python docs/samples/delivery_batches.py --run --run-id synthetic-delivery-batches-v1
```

以下四案分别在第二批原件登记数量暂收、单列全合同暂缓付款、同时出现两种意见，以及付款栏指向页末扫描批注。每案的银行回单都指向第一批对应的第二期，便于核对已有独立依据的付款和仍需复核的支付时点。

```sh
server/.venv/bin/python docs/samples/delivery_batches.py --run --run-id synthetic-batch-scope-20261125-18 --cases batch_count_only payment_hold both_remarks hold_image
```

`--cases` 可选 `complete`（两批合格）、`missing`（缺第二批原件）、`quality`（报告称合格但第二批实测 8℃ 超出合同 4℃ 上限）、`duplicate`（两批登记相同设备）、`early`（9 月 15 日支付的第三期早于 9 月 20 日第二批验收）、`separate`（另行终验）及 `image`（原页附有影像暂收说明）。省略 `--run` 可仅生成资料。

核对具名分批验收可另行运行下列命令。各案均使用一张 35,000 元回单，合同明确第二期对应第一批、第三期对应第二批。样本依次为各批签齐、缺第二批原件、第二批缺一人共同签字、由其他人签字、签齐后实测超限、各批共用同一组签认人员、签字页内嵌代签说明、合同末行另约监理会签。

```sh
server/.venv/bin/python docs/samples/delivery_batches.py --run --run-id synthetic-batch-signatures-v1 --cases named undelivered cosign substitute signed_quality common sign_image sign_rider
```

### 双方盖章后仍有附加生效条件

运行 `server/.venv/bin/python docs/samples/contract_effect.py --run` 可演练五笔水印采购。原有的 `approved`、`written`、`image` 分别展示董事会批准、合同文字附加条件和合同影像附加条件。新增 `board_note` 把「仅批准谈判，签约须另行表决」印在审批单的决定栏下方，`board_image` 将同一附注嵌入审批单影像。可用 `--cases approved board_note board_image` 单独比较三份董事会审批记录。各份采购的合同条款、实收资料和三期比例一致，演练按原件摘要核对并保存必要的字段补正和签认。

### 同一笔质保金在什么条件下可以释放

八组水印资料的合同总价均为 100,000 元，分三期支付 30%、60% 和 10%，回单均写第三期 10,000 元。对照相对质保期间届满、明确约定的截止日、十二个月尚未届满、遗留故障、供应方不符、同日签认付款、影像附注暂缓返还、缺少清结记录。脚本仅对与本次生成件摘要一致的演练文件模拟原页核对。专家对测试水印另有提示时，保留整案的人工校验建议。最终业务验收决定留给审计人员。

```sh
server/.venv/bin/python docs/samples/warranty_release.py --run --run-id synthetic-warranty-20261124-31
```

### 有付款期限的预付款和验收款

九组水印采购案使用相同的总价及 30%、60%、10% 三期比例。可核对按期支付、提前付款、固定日期后的晚付、跨国庆假期的工作日末日、末日当天转账、工作日口径待核、验收影像的附加约定、以到账为准及合同生效后的首期预付。每案包括合同、验收、质保确认和银行回单四份 PDF。

```sh
server/.venv/bin/python docs/samples/payment_deadlines.py --run --run-id synthetic-deadline-20261125-01
```

`--cases national boundary` 只运行末日相同、分别在末日当天及两天后转账的两案。省略 `--run` 可只生成原件。联机演练对生成文件的摘要和原行做比对，在对应水印页模拟核图并保留各版记录。

### 到货签收、终验和复验的保留意见

```sh
server/.venv/bin/python docs/samples/acceptance_remarks.py --run --run-id synthetic-remarks-20261125-02
```

六案总价、三期比例和回单金额相同。`clear` 已完成完整终验，`reserved` 的验收附注只承认到货签收，`image` 将限制写在影像中，`limit` 实测超出合同上限，`approval` 缺少合同生效所需的批准文件，`retest` 的复验单仍有未检项目。可以用 `--cases` 指定案例，省略 `--run` 只生成水印 PDF。

### 分日盖章与首期预付款

`server/.venv/bin/python docs/samples/contract_seal_dates.py --run --run-id synthetic-seals-20261125-03` 生成三笔相同总价和预付比例的采购。`complete` 在双方完成盖章后支付，`early` 在乙方盖章前付款，`partial` 的合同仅见甲方盖章日期。三案均附验收、质保确认及回单原件。

### 补充协议调整交付数量

九笔交付数量变更演练可用 `server/.venv/bin/python docs/samples/quantity_changes.py --run` 提交到本机。主合同原数量均为四台冷柜，总价 100,000 元，成功回单均为第二期 60,000 元。`--cases complete short later same_day quality note image price` 分别对应足量、短收、协议晚于终验、同日顺序待辨、质量超限、欠交文字、影像附注和价款另议。`--cases orphan` 在主合同另列六台，没有单独提交变更协议。只生成带水印的 PDF 时省略 `--run`。

### 终验供应方与委托交付

`server/.venv/bin/python docs/samples/acceptance_suppliers.py --run --run-id synthetic-supplier-20261125-04` 提交七笔水印采购案。`--cases match absent different delegate image` 的五笔采购总价、三期比例及实测质量一致，分别检查供货方名称一致、验收缺栏、名称相异、原生附注和影像附注。`--cases once unspecified` 的两笔回单均为全款 100,000 元，前一份合同明确约定终验后一次付清，后一份未载付款安排。可从底稿顶部进入合同原页或待核回单。

### 复现首次读图的编号误分类

运行 `server/.venv/bin/python docs/samples/quality_readback.py --run`，可用上述复验后付款案例的 R1 重测。脚本校验原版本证据包，把两份 PDF 与固定种子重新生成的水印样本逐字节比较，并检查重渲染的页图和文字层。随后只将两张水印页图连同真实初读候选送入视觉复检，将回执另存入演练目录。原底稿仍可照常打开。

省略 `--run` 可仅查看待复检的原始引文。使用 `--bundle 原版证据包.zip --verify-receipt 读图回执.json` 可离线复核归档请求摘要、逐项判断和图谱采信结果。要从正常上传入口重跑六份文件，可用 `quality_reinspection.py --run --cases closed --run-id synthetic-quality-readback-v2`。

### 三张单据都有 0042 时能否关闭缺陷

运行以下命令会通过本机工作台分别上传三组水印资料。第一组在三份记录的缺陷栏都印“尾号0042”。第二组都印“0042”，仅复验报告另行注明本单只列尾号。第三组的完整缺陷号就是“0042”。合同约定、签认、温度和付款时点相同。

```sh
server/.venv/bin/python docs/samples/quality_reinspection.py --run --cases partial noted short --run-id synthetic-quality-number-visibility-v1
```

`server/.venv/bin/python docs/samples/quality_image_notes.py --run` 从同一张水印原页生成 JPEG 和无文字层的扫描 PDF，分别上传工作台。脚本只模拟核对编号栏“0042”及其同页说明。两个任务用于查看影像取证，每案仅含复验报告。可用 `node frontend/tests/workspace.mjs --quality-image-case 案件编号` 在 Chrome 的桌面和手机宽度从编号跳到原始读图说明。

### 合同另约定验收款须先收票

运行 `server/.venv/bin/python docs/samples/receipt_before_payment.py` 生成四套水印资料。加 `--run` 会上传至本机 8000 端口，使用项目配置的多模态模型，并按生成件原页核验模拟签章。可用 `--cases invoice_only paid_early before_payment different` 选取情形，用 `--run-id` 标识独立的一次演练。默认四笔均比较 H04 现时条件和 H05 回单付款时点。[原件字段与运行结果](../acceptance.md#2026-11-25--验收款收票前提与实付日期)

### 复验签认与未结项目

运行 `server/.venv/bin/python docs/samples/reinspection_register.py --run`，可在本机工作台提交四组水印资料。冷藏柜探头有原验收、整改记录和复验签认，复验表的另一栏分别记录门封待换、等待试运行、另一缺陷关闭、无未结事项。脚本核对生成件和归档页图摘要，并检查第二期验收款和第三期质保金的状态。

### 两位终验人分日签认

运行 `server/.venv/bin/python docs/samples/acceptance_signers.py --run --cases before same_day after` 可提交三笔带水印的分期采购。三份合同均约定终验合格付 60%，两名验收人分别在 9 月 20 日和 25 日签认。三笔回单分别写 9 月 22、25、26 日。发生器只在演练标记、原件摘要及印刷行核对一致后对虚构签字执行模拟核图，初次识别和每次更正均保留。

| 成功回单 | 时序结果 | 固定版底稿 |
| --- | --- | --- |
| 9 月 22 日 | 早 3 天，付款时点列为风险 | [R8](http://127.0.0.1:8000/workpaper/00cc3c6b67964491b6f1ba9686440062?rev=8&view=signer-timing) |
| 9 月 25 日 | 同日，需核对签认及扣款时分 | [R8](http://127.0.0.1:8000/workpaper/d70cda968be04a7a8fc0c9e235b151b9?rev=8&view=signer-timing) |
| 9 月 26 日 | 晚 1 天，合同及验收依据继续待核 | [R6](http://127.0.0.1:8000/workpaper/95f293ec9d9140f3857c382e5c5eb676?rev=6&view=signer-timing) |

要从提前付款案例的固定版证据包重建首页时序样本，运行 `server/.venv/bin/python docs/samples/publish_signer_timing.py <证据包.zip> --seed signer-timing-nov26`。脚本将每份已提交原件与水印生成件比对，重绘页面，核对物理行和页图摘要后生成公开材料。

## 状态栏与回单页脚

同一套四门冷藏柜采购资料的第二期占 60%。四组演练覆盖回单页脚限定实际扣款、只提交付款申请、仅提示收款方到账，以及同案含两份不同用途的凭证。运行 `server/.venv/bin/python docs/samples/bank_execution_notices.py` 生成四份带水印的 PDF，追加 `--run` 可通过本地接口提交和核对原件。脚本会先校验合成案例名称及文件摘要，再按逐字原行补正或确认识别记录。[案例脚本](bank_execution_notices.py) · [业务依据](../../3rd/payment-acceptance.md#受理回执能证明什么)


| 水印案例 | H05 与原件核对结果 |
| --- | --- |
| [验收款回单 R4](http://127.0.0.1:8000/workpaper/585a6b42d73043ddbe026e814a588d16?rev=4&view=payment-proof&receipt=H05-8) | 第 8 行列示交易成功，第 10 行限定为受理凭证。第二期实付待复核，验收及三期约定分别有据。 |
| [付款申请 R7](http://127.0.0.1:8000/workpaper/972d00581478461fa1dece2d48b623a4?rev=7&view=payment-proof&receipt=H05-8) | 第 2 行是申请单标题，第 8 行列示审批通过。留存申请时间，并标示期次待核。 |
| [收款方到账提示 R5](http://127.0.0.1:8000/workpaper/a111692053cd40908cebd70262ac317e?rev=5) | 页脚只提示收款方到账情况。合同签署证据不足，本笔履约付款时点仍待核。 |
| [同案两份凭证 R8](http://127.0.0.1:8000/workpaper/22aae5a4b20545c994e6a68361d40986?rev=8&view=payment-proof&receipt=H05-9) | 第二期回单有受理限定。另一份申请单自行列示第三期，相关核对保留在其自己的单据和原行上。 |
