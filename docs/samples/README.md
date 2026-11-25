# 合成财会审计演练

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

以下命令上传四套水印原件。第一套将上限从 4℃ 放宽到 8℃，第二批实测 6℃。第二套收紧到 2℃，第二批仍按 4℃ 验收，实测 3℃。第三套的第二批验收日正好是双方完成盖章日。第四套把盖章日印成「2026年9月1 2日」，需核对原行。每案另附注明第三期的银行回单，以核对这笔 35% 款项的付款前提。

```sh
server/.venv/bin/python docs/samples/batch_quality_changes.py --run
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

`server/.venv/bin/python docs/samples/final_signers.py` 生成八组带水印的虚构设备采购资料，覆盖分批与终验分别具名、同一人只签分批、换人签终验、合同仅指定终验人、缺少总单、全员签字且实测超限、代签影像和合同附加会签。用 `--run --run-id 本次演练编号` 可在本机完成上传、多模态解析、生成件原行核对与规则验收。脚本核对模型调用记录、每期条件、总单签字范围、图谱关系和质保起算，最终签收留给审计人员。

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
