# 合成财会审计演练

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

运行 `server/.venv/bin/python docs/samples/mandates.py --run --cases role joint redacted --run-id synthetic-signing-identity-v1` 可比较两份文件同写“采购负责人”、同列两名代理人、同写“张某”的三种签约情形。每组均核对受托人原文字段、未确认的图谱关系、三期条件及第二期实付时点。

运行 `server/.venv/bin/python docs/samples/mandates.py --run --cases spaced compound --run-id synthetic-printed-agent-v1` 比较两组四字写法。一组签字栏、受托人栏均印“周宁 方程”，另一组均印“欧阳明月”。演练核对姓名中的间隔、原页逐行记录和各期付款条件。

### 缺陷整改及最终复验

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

`--cases` 可选 `complete`（两批合格）、`missing`（缺第二批原件）、`quality`（报告称合格但第二批实测 8℃ 超出合同 4℃ 上限）、`duplicate`（两批登记相同设备）、`early`（9 月 15 日支付的第三期早于 9 月 20 日第二批验收）、`separate`（另行终验）及 `image`（原页附有影像暂收说明）。省略 `--run` 可仅生成资料。

### 双方盖章后仍有附加生效条件

`server/.venv/bin/python docs/samples/contract_effect.py --run` 上传三笔水印采购案。`approved` 随合同提交约定的董事会批准决议，`written` 在合同页末印有另须取得书面批准的条件，`image` 把同一条件写在嵌入的影像框内。三案分别核对 H01 及履约付款条件。脚本仅对摘要一致的合成原件模拟字段补录、签认及人工核图。

### 复现首次读图的编号误分类

运行 `server/.venv/bin/python docs/samples/quality_readback.py --run`，可用上述复验后付款案例的 R1 重测。脚本校验原版本证据包，把两份 PDF 与固定种子重新生成的水印样本逐字节比较，并检查重渲染的页图和文字层。随后只将两张水印页图连同真实初读候选送入视觉复检，将回执另存入演练目录。原底稿仍可照常打开。

省略 `--run` 可仅查看待复检的原始引文。使用 `--bundle 原版证据包.zip --verify-receipt 读图回执.json` 可离线复核归档请求摘要、逐项判断和图谱采信结果。要从正常上传入口重跑六份文件，可用 `quality_reinspection.py --run --cases closed --run-id synthetic-quality-readback-v2`。

### 三张单据都有 0042 时能否关闭缺陷

运行以下命令会通过本机工作台分别上传三组水印资料。第一组在三份记录的缺陷栏都印“尾号0042”。第二组都印“0042”，仅复验报告另行注明本单只列尾号。第三组的完整缺陷号就是“0042”。合同约定、签认、温度和付款时点相同。

```sh
server/.venv/bin/python docs/samples/quality_reinspection.py --run --cases partial noted short --run-id synthetic-quality-number-visibility-v1
```

`server/.venv/bin/python docs/samples/quality_image_notes.py --run` 从同一张水印原页生成 JPEG 和无文字层的扫描 PDF，分别上传工作台。脚本只模拟核对编号栏“0042”及其同页说明。两个任务用于查看影像取证，每案仅含复验报告。可用 `node frontend/tests/workspace.mjs --quality-image-case 案件编号` 在 Chrome 的桌面和手机宽度从编号跳到原始读图说明。
