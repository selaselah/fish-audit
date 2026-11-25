# 本机审计接口

## 设备换货交接与最终复验

规则 `2026.11.25.15` 使用 `printed-equipment-models-v3`。识别到设备换货交接原件或验收页所引交接单号时，`graph.equipment_model_sources.exchange` 保存候选单据及实际页行。每条原行包含物理文件、页码、行号、逐字引文和观察编号。影像中的引文按观察定位，`line` 为空。

H02 的 `equipment_models.exchange.checks` 给出每项判断及其依据。交接单的范围、合同及主体、所引单号、型号、退回清单、换入清单、实际交付记载、交接时点、双方签认和最终复验分别显示状态。单号和归属可确认时，图谱中的 `equipment_exchange_returned` 连接初验和交接页，`equipment_exchange_received` 连接交接和复验页。边的状态表示对应清单的核对结果，整笔换货结论见 `exchange.status`。

全部检查成立时，`equipment_models.sequence.outcome` 为 `replacement_verified`。有金额差异以外的未决事项时，H04 继续依合同各期前提给出结论。验收不明时，H05 也会保留实付款日和未证实的履约前提。历史底稿沿用发行时的程序复算。

网页用 H04、H05 各自的 `scope` 和 `evidence` 确认本期引用的交接原页，再链接 `exchange.checks` 中的具体检查。换入编号差异可从相应验收款直接定位，交接单另列付款约定时可从受影响的期款定位到该原行。

## 约定设备型号与实收型号

规则 `2026.11.25.14` 使用 `printed-equipment-models-v2`。遇有复验时，H02 的 `equipment_models.sequence` 记录原验收、整改、复验资料按既有程序核对后的 `record_chain_state`，以及型号核对的 `outcome`。`records[].inspection_role` 按原单与缺陷关系区分 `original`、`final`，支持标题仍为「验收报告」的复验单。

| `outcome` | 所据材料及含义 |
| --- | --- |
| `same_model` | 原验收与复验所列型号均与约定相同，缺陷的关闭另依整改和复验记录。 |
| `replacement_unverified` | 原单型号不同，复验写回约定型号，缺陷记录可衔接，实物换货与交接尚待证明。 |
| `final_differs` | 有对应的复验记录，复验实收型号与合同约定仍不一致。 |
| `model_unresolved`、`links_pending` | 初验或复验的型号不完整，或原单、整改、复验的关联尚待核实。 |

`record_chain_state=closed` 表示三份资料中的缺陷编号、措施、签认及复验关闭记载能够衔接。若设备身份仍待核，H02 的 `reinspection.state` 保留 `open`，验收款和质保金继续待核。v1 底稿按当时规则复算。申请通过签收 v1 中存在整改前后型号差异的底稿时，接口返回 409 并提示重审。

该程序首次发布于规则 `2026.11.25.13`，其标记为 `policy.equipment_models=printed-equipment-models-v1`。报告的 `graph.equipment_model_sources` 保存涉查原页和型号引文。每个 `lines[]` 元素保存原件 `doc`、物理页 `page`、逻辑单据 `unit`、角色、原行号 `line`、原文 `quote`、原值 `value` 和同一原行的观察 ID `facts`。只有图像引文时行号为空。识别到型号的文字行可独立留存，模型漏录时 `facts` 可以为空。

H02 的 `equipment_models` 包含约定原行 `ordered`、逐份验收或复验的 `records[]`、汇总状态、理由和证据。每份记录的 `received` 指向实收原行，`identity` 保留合同号、双方和标的的关联结果与双方引文，`comparison` 取 `match`、`different` 或 `unresolved`。`status` 另行反映条款、归属及复核因素。例如两原件列示不同型号、合同生效尚待证时，记录可同时为 `different` 和 `risk`。型号完全相符时，H01 的批准条件及 H02 的实测质量仍分别计算。

可逐字比较的两条原行产生 `equipment_model_comparison` 图关系，保存双方物理页、各自原行号、审查状态及用于关联单据的观察引用。型号遮盖、替代条件或归属不清时，原件仍供查看。验收记录分别参与依赖该单据的 H04 和 H05 判断。签收和离线校验会核对原页、所载型号及关系。旧版载有设备型号且已有肯定验收或付款判断的底稿，需按新程序重审后签收。

## 同一次提交的分期回单

规则 `2026.11.25.12` 在报告中保存 `policy.stage_payments=submitted-stage-transfers-v1`。当合同履约程序识别到多份回单或同页有多组交易栏位时，`graph.stage_payment_sources` 列出银行单据 `banks`、所核原页 `pages`、原文附注 `notes`、待归属单据 `unknown_units` 及单笔边界待核的单据 `ambiguous_units`。附注保留原件、页、行号、引文以及能与原文相连的观察 ID。

每个涉及实付的期次生成一项 H06。未能唯一归期的回单另列一项。每项的 `stage_payments` 包含以下字段。

| 字段 | 内容 |
| --- | --- |
| `state` | `balanced` 表示本次合计与约定相符，`partial` 表示少于约定，`over` 表示超过约定，`unresolved` 表示计算或归属依据待核。 |
| `expected`、`seen`、`difference` | 原约定金额、本次所见成功流水去重合计、合计减去原约定。人民币元金额用两位小数字符串表示。无法支持某项数值时为 `null`。 |
| `base`、`records[]` | 合同原值、逐笔回单。`inputs` 中每个可核字段含观察 ID `ref` 和原行值 `value`。副本的 `duplicate_of` 指向已计入的单据，两张回单的原页均保留。 |
| `condition`、`timing[]`、`reasons[]` | 本期 H04 条件状态、每笔 H05 的单据与实付时点状态、影响复算的原因。即使 `state=balanced`，H06 仍可能报告履约证据缺失或提前付款。 |

当 `seen` 有数值时，`graph.edges` 为每笔计入交易保存 `stage_transfer_operand`，其证据引用依次为合同分期条款、合同总额、完整银行流水和付款金额。历史底稿按各自规则快照重放。旧版对多份回单只审了付款时点，且已有肯定判断时，申请通过签收会收到 HTTP 409，并提示先重审该期款。

## 验收合订件的原页归属

规则 `2026.11.25.11` 保存 `policy.receipt_packets=numbered-acceptance-pages-v2`。版本 v2 按原页栏目区分验收单号、复验单号和引用号。同一本册只有一张初验单、另两页分别是已识别的整改与复验材料时，`packets` 为空，H02 的 `reinspection.steps` 保存三种角色及各自原页。规则 `2026.11.25.10` 的 v1 底稿按其原版复算。报告的 `graph.receipt_packet_sources.packets[]` 按上传原件列出审查过的验收页。每条含原件 `doc`、`status` 和 `pages[]`。页记录有物理页 `page`、原文编号 `number`、文字版式标记 `text_only`、待核原因 `reasons[]`、原行 `rows[]`。原行记录字段、页、行号、引文和能与原行逐字对应的观察 ID。

`split` 表示各张验收单可分别核对。所有字段和签认保留物理 `doc/page`，`unit` 指向该页的逻辑单据。每个 `acceptance_page_identity` 关系从逻辑单据指向标题或本单编号，引文包含页 ID 及观察 ID。`review` 表示该组合内的验收依据尚待核实，理由也发布到 `graph.gaps` 的 `receipt_packet` 项。H02 及依赖该资料的付款条件保留相关页的证据引用。签收与离线核验按底稿版本检查归属、页码、文本、图关系及原件摘要。


规则 `2026.11.25.11` 同时使用 `policy.delivery_batches=contract-delivery-batches-v5`。当书面签认条款和对应原单俱全，H02 可记录各页签字人与条款所列姓名是否对应。即使签字观察均已核图，合同尚欠生效审批时，各批结论和付款条件仍显示待核，`completion_on` 为空。可沿 H01 的引文查看缺件，沿 H02 的 `signing.signed` 查看已核的签字。v4 底稿按原有判断顺序复算。

规则 `2026.11.25.09` 使用 `policy.delivery_batches=contract-delivery-batches-v4`。在各批独立付款且另行终验的合同中，H02 的 `batch_acceptance.separate_final.signing_requirement` 保存合同逐字可核的终验签认要求，`required` 是指定姓名，`clause_ref` 定位条款。合同有这项要求、尚缺终验原件时，仍返回要求及空的 `separate_final.records`。

已归属的总单在 `batch_acceptance.records[]` 内以 `role=final` 标识。该单的 `signing` 包含逐人所据的 `signed[]`、`missing_names`、`other_names`、`status` 和 `detail`。原页有签字行而观察漏提时，可用 `doc`、`page`、`line`、`quote` 复查，`confirmed` 为 false。终验的全部条件相符后，`final_named_signature` 从合同指定终验人的观察指向总单上每一条已核签字观察，`batch_named_signature` 仍对应各批自己的签字。归档的 v1、v2 和 v3 继续按各自程序复算。

规则 `2026.11.25.08` 使用 `policy.delivery_batches=contract-delivery-batches-v3`。H02 的 `batch_acceptance.separate_final` 在合同明确约定另行终验时返回 `status`、`detail`、总单所在的 `records[]`，以及各批原件编号的 `basis[]`。每个依据含批序 `index`、文档 `unit`、原单号 `number` 及观察 `number_ref`。已识别的总单在 `batch_acceptance.records[]` 中标为 `role=final`，`refs_ref` 指向其引用栏，`receipt_numbers[]` 保留原件顺序。引用栏缺失时这两个字段分别为 null 和空数组。

另行终验成立时 `deemed_final` 为 false，`completion_on` 取终验单签认的验收日。`batch_final_basis` 从总单的 `batch_receipt_refs` 观察逐份指向对应批次的 `acceptance_number` 观察。人工可从两端打开原页。待核或冲突状态保留原单与引用栏，证据图仅在核查相符时建立这组关系。离线校验按归档规则版本复算。

规则 `2026.11.25.07` 使用 `policy.delivery_batches=contract-delivery-batches-v2`。合同明定分批独立验收付款，且按批或统一指定验收人时，H02 的 `batch_acceptance.batches[].signing_requirement` 保存本批所需人员 `required` 和合同引文 `clause_ref`。每张可归属的验收单在 `records[].signing` 保存签字原行 `signed`、所缺人员 `missing_names`、额外签字人 `other_names`、对照状态和原因。签字原行含资料、页、行、引文及核图状态。原页有字而模型漏读时，事实编号可为空。

每条 `batch_named_signature` 关系从本批合同签认条款指向该批一人的已核图签字行，仅在整批验收有充分依据时生成。签字相符、质量实测超限时，H02 会保留两个判断。H04 按该期对应的批次取证，H05 再核对回单所指的期次及支付日。旧版 `contract-delivery-batches-v1` 底稿继续按出具版本复算。

规则 `2026.11.25.06` 的 `policy.quality_addenda` 为 `acceptance-addendum-v2`。出现交付数量变更线索时，`graph.quality_addenda.quantities` 保存合同、变更协议及验收资料的页清单、数量原行与关键身份和日期栏。每一条 `delivery_quantity_basis` 关系可定位到资料单元、页和行，`evidence` 包含原页及已有模型或人工引文。原生文字行可独立于模型抄录保存。

H02 的 `quality_change.quantity` 列出 `original`、`previous`、`revised`、`accepted` 和 `applicable`。可核数量以 `{count, unit}` 表示，待核值为 `null`。`difference` 为同单位实收减应验，负数表示短收，零表示数量相符。变更的 `state` 为 `applied`、`original` 或 `pending`，质量检测与分期条件仍各有自己的发现。旧版仍按出具时程序复算，旧版终验曾判相符且原页现查见数量变更线索时，申请通过会返回 409 并要求重审。

自规则 `2026.11.25.05` 起，合同未提取到任何付款安排或无法确定唯一现行合同时，每个已识别的 `bank_receipt` 仍生成一项 H05。其 `status` 为 `missing`，没有 `stage`。从 `scope` 和 `evidence` 可定位各自的回单、可见用途、金额、日期以及候核合同页。没有回单时不生成此项。历史版本按原程序复算，申请通过一份漏列可识别回单的履约底稿时返回 409 并提示重新审计。

规则 `2026.11.25.04` 使用 `policy.acceptance_reservations=acceptance-reservations-v2`。H02 的 `acceptance_reservations.supplier` 包含 `status`、`detail`、逐项名称 `names`、所据 `pages` 与 `lines`。名称以资料或分册单元为键，取自受支持的原文字段。`graph.acceptance_reservation_sources.supplier_rows` 列示 `seller` 原行和 `delivery_note` 附注，`supplier_identity_basis` 关系从资料单元连到该页。申请通过旧版底稿时，会重查原已判相符的终验供货主体及第三方交付线索。

规则 `2026.11.25.03` 的 `policy.contract_effect` 为 `contract-effect-sources-v2`。有单独签章日期记载时，H01 的 `effect_review.conditions` 保留 `kind=seal_date` 的原件引文，`effect_review.seals.dates` 按 `buyer_sealed_on`、`seller_sealed_on` 保存证据支持的日期。`declared_on` 为原件所列生效日，`completed_on` 为按约定核准的最后盖章日，未核清时为 `null`。旧版仍按原规则回放，申请通过时会重新核验所据主合同的日期。

基础地址为 `http://127.0.0.1:8000`。接口与前端同源。审计资料只在当前电脑的本地工作区共享。所有时间戳以 UTC 保存，网页按北京时间显示。

创建任务时可提交 `profile=cn-contract-performance/v1` 审查合同履约与分期。当前规则在采购及银行回单范围也执行 H01–H05。报告的 `findings` 保留各程序的 `status`、`evidence` 和 `scope`。已识别的 H04/H05 期次还包含 `stage.name`（期名）、`share`（百分数文本）、`clause`（本期条款）和 `clause_ref`（完整原文的证据编号）。缺少证明的项目仍进入报告。

涉及整改的 H02 可包含 `reinspection`。其中 `state` 为 `open` 或 `closed`，`steps` 按原验收、整改、复验三种角色列出实际收到的来源。每步保存 `role`（`original`、`repair`、`final`）、`unit`（文件或分册页）、`date`（ISO 日期或 null）及 `evidence`（原页证据编号）。当次是否可以据此认定验收或付款条件满足，分别由 H02、H04 和 H05 的状态说明。

当 `policy.delegation_checks` 为 `written-contract-mandate-v1`、`written-contract-mandate-v2` 或 `written-contract-mandate-v3`，涉及代理签署的 H01 会给出 `delegations`。每项含 `side`（`buyer`、`seller` 或 `unassigned`）、签字栏字段 `signature_field`、签字栏可读内容 `agent`、委托书归属 `units`、`status`、`detail` 和 `evidence`。四个 ISO 日期字段 `signed_on`、`issued_on`、`valid_from`、`valid_until` 的未知值为 null。`graph.delegation_coverage.pages` 按原件页列出是否有可核原生文字层，以及尚未归入已核授权字段的行号和原文。图谱可用 `grant_principal`、`grant_counterparty` 关联采购主体，用 `buyer_grant_ref` 或 `seller_grant_ref` 核对委托书自己的 `grant_number`。

v2 中甲、乙方代理核查的 `agent_kind` 记录姓名栏判读类别。取值为 `named`（单个具名写法）、`role`（岗位或机构）、`joint`（多人）、`redacted`（隐名）或 `unclear`（待核）。`graph.delegation_coverage.agent_holds` 中的每一项记录委托书受托人栏的 `fact`、`field`、`unit`、`doc`、`page`、`value` 和待核原因 `kind`。相应的 `unresolved_grant_agent` 关系从单据指向本页事实，只能据此追溯原文。旧版若曾凭这些记载核准代理签约，再次提交通过决定时返回 409 并提示重审。

v3 另在 `graph.delegation_coverage.signer_holds` 登记待核的合同签字栏。两类登记均有 `lines`，其中的 `line` 是原页文字层的一基行号，`quote` 含原有姓名间隔。多个印刷行在去除空白后相同时，附上全部匹配行。影像没有原生行时该数组为空。`joint` 表示须核对是否多人，`agent` 中的连写内容须结合登记原文解释。旧版已经据此核准书面授权时，签收通过会重新检查所引原页。

当 `policy.quality_number_classification` 为 `printed-quality-number-v1` 时，按原页标签改归的编号事实带有 `origin: "printed_quality_number"`。`field` 是核对后的分类，`model_field` 保留初次分类，`value` 和 `quote` 保留当时抄录。按 `doc` 和 `page` 找到 `calls.pages[].check`，事实编号末尾 `f` 后的数字及 `classification_index` 分别对应原分类和印刷标签的候选项。两项的具体输入在 `input`，判断在 `output.checks`。底稿支持按 `?rev=版本号&fact=事实编号` 定位页图。

`policy.quality_references` 为 `quality-reference-visibility-v1` 时，`graph.quality_references.holds` 记录需补全的验收、整改或缺陷编号。每项含原观察 `fact`、字段名 `field`、原始取值、页码及资料归属，可定位行在 `lines` 中，图像页上的相关读图引文在 `observations` 中。对应图谱边的类型带 `incomplete_` 前缀，直接连到本页事实。若旧版的缺陷关闭依赖这种部分编号，签收通过接口返回 409，说明需要重审。

| 请求 | 作用 |
| --- | --- |
| `GET /api/health` | 服务状态，`audit` 中提供审计服务商、模型、业务范围及页数限制。兼容字段 `mode` 指旧版文本审核模式 |
| `GET /api/controls` | 采购及差旅程序编号、规则版本、适用背景与来源 |
| `POST /api/cases` | multipart 表单，`title` 和一个或多个同名 `files` 字段，返回 HTTP 202 和 `id` |
| `GET /api/cases` | 台账，含处理进度、建议、底稿版本和人工决定 |
| `GET /api/cases/{id}` | 原件清单、阶段、百分比、逐页进度 `page_progress`、事件、版本和验收历史 |
| `GET /api/cases/{id}/reports/{rev}` | 特定版本的完整底稿、生成时间及摘要 |
| `POST /api/cases/{id}/reports/{rev}/replay` | 用服务端可信版本库复算指定版的检查程序和专家追加程序。请求可为空或 `{}` |
| `GET /api/cases/{id}/reports/{rev}/bundle` | 下载该版本原件、页图、文字层、底稿与导出时的日志 ZIP |
| `GET /api/cases/{id}/reports/{rev}/methods/{name}` | 阅读该版本配套的程序源码，文件名取自底稿中的 `policy.code_sha256`。保存了源码快照的版本可用 |
| `GET /api/cases/{id}/documents/{doc}/original` | 下载原始文件 |
| `GET /api/cases/{id}/documents/{doc}/pages/{page}` | 查看模型读取的页图，页码从 1 开始 |
| `POST /api/cases/{id}/retry` | 中断任务从已保存的检查点继续 |
| `POST /api/cases/{id}/rerun` | 提交当前 `rev`，沿用已保存的视觉提取重新执行审计，生成新版 |
| `POST /api/cases/{id}/attest` | 对指定底稿中的若干观察确认或提出异议，生成新版 |
| `POST /api/cases/{id}/amend` | 根据指定原页更正已有候选或补录新字段，保留模型原值与人工取值 |
| `POST /api/cases/{id}/signoff` | 对当前底稿填写人工决定并归档 |

客户端可发送 `Idempotency-Key`（12 至 100 个字母、数字、下划线或短横线）。相同键与相同文件内容、顺序、文件名和任务名称复用原任务。内容变化时返回 409。

可选表单字段 `profile` 指定业务范围。默认 `cn-procurement-full-settlement/v1` 运行采购程序，`cn-travel-reimbursement/v1` 运行差旅全凭票报销程序，`cn-bank-contract-payment/v1` 核对一份合同及一张银行回单。不同业务范围具有独立的适用前提和底稿。

```sh
curl -F 'title=本月采购验收' -F 'files=@合同.docx' -F 'files=@发票.pdf' \
  -F 'files=@验收照片.jpg' http://127.0.0.1:8000/api/cases
```

## 逐页进度与资料预览

`GET /api/ready` 是公开的就绪探测接口。任务线程运行且数据库可读时，响应为 `{"status":"ready","mode":"local"}` 或企业模式 `saas`。未就绪时返回 HTTP 503，`component` 为 `worker`、`database` 或 `database_write`。后者表明任务线程遇到数据库写锁，正在原事务开始或提交的位置等待。前台操作遇到持续写入占用时会返回 503，调用方可在解除占用后重试。在排队或处理中的任务详情内，`waiting_for_database: true` 用于显示这个等待状态。

任务详情的 `page_progress.counts` 分别给出已分页 `prepared`、已提取 `read`、已有视觉复检记录 `checked` 的页数。三项分别计数，已复检页也计入已提取页。`documents` 以原件编号列出页码及最近保存的状态，`invalid` 表示提取记录需要检查。`activity` 提供当前处理或中断位置的原件、页码及步骤，队列中、已完成及整案处理阶段可为空。完成视觉复检的页仍可能有待人工确认的字段。

专家模型已经返回且响应已保存、底稿尚待生成时，`page_progress.expert` 提供目标底稿版本 `target_rev` 与保存时间 `saved_at`。写入响应的同时，工作台进度更新为 96%。恢复后若同案同版的完整请求与原记录相符，系统标记 97% 并沿用原响应。底稿成功提交时清理临时响应，完整专家执行记录进入该版底稿。

原件下载和页图预览在响应前核对 SHA-256。请求支持 ETag、HEAD 和字节范围。审计人员或管理员可加 `?rev=版本号`，同时校验所选底稿及其图谱中的来源摘要，底稿引用默认使用这个入口。员工可从本人任务读取已登记的当前原件和页图。已登记的文件缺失或内容与相应摘要不符时返回 409。

## 复算历史底稿

审计岗可从独立网址 `/workpaper/{id}?rev={版本}&view=replay` 打开复算入口，企业访问沿用 `/w/{企业编号}` 前缀。复算接口遵循企业权限与 CSRF 校验，只读取所选版本。每次都从服务器读取底稿并校验其 SHA-256。

`state=verified` 表示逐项发现、引文编号、算式及整案建议均与当时的图谱和专家建议复算一致。`mismatch` 表示已找到对应规则，但数据或输出无法对齐。`unavailable` 会说明缺少源码摘要、发布历史无匹配或本机依赖不可用等原因。已完成的三种结果均返回 HTTP 200。响应包含底稿版本、摘要、时间和规则集版本，有可运行代码时还包括匹配提交 `commit`、受信发布历史的起点 `trusted_tip` 及各依赖的 SHA-256。复算一致时另含发现数、整案建议、`findings_sha256` 和 `result_sha256`。

匹配使用同一个本地 Git 提交里规则及其递归导入的项目源码。仅匹配到相同版本号不足以执行。记录中的提交说明其中的规则源码与底稿相符。该提交可以晚于底稿出具。复算直接使用当时留存的模型建议作为输入。原件、页图和模型请求的一致性可随证据包离线校验。

## 核图与最终决定

初审或独立复核提交 `approve` 时，服务端在同一写事务内重新读取本企业与本案已核发票号码匹配的签收记录。当前规则中，新增、消失或改变的相同标识与归属待核记录会返回 409 和 `invoice_history`。同号但双方已核代码不同的新增记录保存在签收回执中，审计人员可直接签收当版。旧版仍按出具时的号码检索口径验收。其中 `count` 为变化的票号引文总数，`changes` 最多返回前八处，每处包含 `previous` 和 `current`。新增引用的 `previous` 为空，原引消失时 `current` 为空，有前后版本时两者均给出案件、版本、引文编号、原文和人工决定。此响应保留当前任务状态。初审可走原有重新审计接口，独立复核可在原转交版签收为退回。

核图请求使用 `application/json`。姓名与意见必填。决定可为 `confirm` 或 `dispute`，`facts` 取自当前版本的证据编号。

```json
{"rev":1,"reviewer":"演练人员","decision":"confirm","facts":["d01/p1/f3"],"note":"已对照合成原页的票号。"}
```

提交确认、更正或补录时，服务端重新读取所选字段的原件与页图，核对字节与当前底稿登记的 SHA-256。一次选中多页时，任一页缺失、内容变化，或核对期间有人签收该案，整次操作返回 409，不写入其中任何一项。所选字段不属于该底稿或页码时返回 400。对资料提出 `dispute` 仍可记录无法核实的原因。

新记录的 `source_check` 保存动作 `confirm`、`correct` 或 `add`，以及案件、底稿版本与摘要、文档编号、页码、原件与页图的 SHA-256 和 UTC 核对时间。新版底稿的字段通过 `attestation` 或 `amendment` 引用这项记录。ZIP 在 `field-checks/r{版本}/report.json` 保存所引旧底稿的原始字节，每个版本一份。操作针对导出版本时直接引用包内的 `report.json`。旧记录沿用其历史字段，只有实际执行过这项校验的操作才有 `source_check`。

当 `policy.invoice_sources` 为 `signed-invoice-v1` 时，每条 `graph.prior_invoices` 记录均含前案底稿摘要 `report_hash`、人工签收摘要 `signoff_hash`、原件和页图摘要。其 `source` 保存依据类别 `basis`、原文字层的 SHA-256、可定位的行号及签收时间。`native_line` 表示原生文字行匹配，`field_check` 表示带原件核对记录的人工确认。`historical_record` 和 `historical_confirmation` 分别表示旧版底稿的字段记录与旧版人工确认。

证据包的 `prior/{案件}/r{版本}/` 包含所据的 `report.json`、`signoff.json`、对应发票原件、页图和文字层。引用过人工核图或独立复核的版本还带有相应的来源底稿。旧包可按所记的证据格式校验。跨案付款检查也会核对所引人工字段的原件与页图。

最终决定的字段为 `rev`、`reviewer`、`decision`、`note`，决定可为 `approve`、`return` 或 `escalate`。已归档、正在重算或提交过期版本返回 409。下载及操作均以任务和版本为范围。错误响应采用 `{"error":"可读说明"}`。

采购、差旅签收通过时，服务在写入人工决定的同一事务内保存同票检索回执。审计人员读取签收版 `GET /reports/{rev}` 响应的 `invoice_approval` 可见当时的工作区、原查验版与摘要、签收版、签收时间、查询票号、原文字段及命中的前案版本。首版回执的 `outcome` 取 `matched`、`no_match` 或 `no_usable_number`。其中 `no_match` 限于本企业当时已签收的任务。提交复核的原版及独立复核签收版各有版本号。报告正文的 SHA-256 与验收前一致。

签收记录的 `invoice_check_hash` 固定 `approval/invoices.json` 的原始字节。回执的 `decision_sha256` 对应含案件、企业、标题、版本、签收人、决定、意见和时间的原始签收内容，计算时排除回执摘要本身。审计人员可在独立离线校验中重建票号与命中清单并核对人工意见。本版开始实际执行过签收的记录才会带回执。

更正或补录时提交 `rev`、`doc`、`page`、`field`、`quote`、`value`、`region`、`reviewer`、`note`。更正须携带本页的 `target` 证据编号，补录时设为 null。`field` 取自 `GET /api/controls` 的 `fields`，`region` 为 top、middle 或 bottom。新记录与该页 SHA-256 一起保存。

任务从 `queued`、`running` 进入 `ready`。人工通过或退回后的状态为 `closed`，提交复核后为 `in_review`，复核人签收后为 `closed`。`failed` 保留阶段、原因与已完成页面。同号核查可引用本工作区已签收或已转交复核的记录，另一笔全额付款检查只采用已通过的历史签收。旧原型的 `POST /api/reviews` 继续支持文本审核。

### 独立人工复核

审计岗从任务详情的 `referrals` 取得转交版本 `rev`、`report_hash` 和 `signoff_hash`。向 `POST /api/cases/{id}/peer-review` 提交这三个字段，以及 `decision`（`approve` 或 `return`）、`note` 和 `findings`（所核原版发现编号的非空数组）。企业入口使用同样的工作区前缀与 CSRF。企业模式从会话取得签收身份，复核人须为同企业中另一名审计人员或管理员。本机模式填写 `reviewer`，以姓名区分两次演练签收。

成功返回 HTTP 200 和复核签收版 `rev`。相同签收请求重试可取回同一版本，另一人已签收、摘要变化或付款依据过期返回 409。首次转交版仍可按原版本号访问。新版本 `peer_review` 记录两次签收与所据发现，证据包的 `review/source-report.json` 保存当时的原始字节，`review/referral.json` 保存转交记录。旧版已提交复核的任务升级后进入待复核队列，`origin=migration` 表示在升级时建立了两项摘要。

### 从退回版本提交补件

`POST /api/cases/{id}/supplements` 接受 multipart 表单。企业客户端使用相同的工作区前缀、CSRF 与提交编号。成功返回 HTTP 202 和新任务编号。

| 字段 | 含义 |
| --- | --- |
| `title`、`rev` | 新任务名称、前案最终退回的底稿版本。待验收、已通过、提交复核或版本过期时返回 409 |
| `retain` | 可重复，填写前案原件编号。新案按前案原件顺序复制这些文件并逐字节核验摘要 |
| `files` | 可重复，新增文件排在沿用文件之后。留空可只提交选定的原件，省略 `retain` 可整套替换 |
| `note`、`profile` | 选填补件说明。审计范围沿用前案，如填写 `profile` 必须一致 |

文件数、字节和页数限额适用于整个新案。任务详情的 `supplement_of`、`supplements` 提供可访问的前后关联。新底稿的 `supplement` 保存原签收版本、两项受理摘要、资料映射以及按程序编号比较的前后发现。独立网址 `/workpaper/{id}?rev=1&finding=B01-2` 可定位具体发现，企业网址带 `/w/{企业编号}` 前缀。归档签收意见和本案受理说明均可在证据包中离线核验。

### 付款底稿的历史核查

付款回单程序自规则集 `2026.11.24.1` 起，在报告的 `graph.payment_history` 中返回 UTC 检索时间 `as_of`、两类命中数 `counts.same/full` 和各自最近八份签收底稿 `matches`。每个命中都记录历史任务与版本、人工决定、签收时间、底稿及签收摘要，还包含可定位原页的字段引文。应结合 B06、B07 的状态读取计数。证据不足时对应程序为 `missing`。

提交付款任务的 `approve` 决定时，若出现新增的匹配归档，签收接口返回 HTTP 409。审计人员可基于当前版本请求 `rerun`，取得新版证据后再签收。原版本及当时的历史查询结果可继续读取。

自规则集 `2026.11.24.2` 起，有分期条款线索的底稿还提供 `graph.payment_history.installments`。其中 `count` 为同企业、同合同号与同收付双方已通过的历史任务数，`matches` 保存至多 32 份历史任务的版本、签收摘要、引用原文和取数。审核通过或独立复核通过前，会在同一写事务中重查历史列表。

`calculation.state` 为 `calculated` 时，`payments` 逐笔给出日期、完整流水、人民币元金额、原文字段及 `copies` 中的副本引用。`paid_total`、`contract_total` 和 `difference` 均为精确到分的十进制字符串，差额为累计减合同。遇到证据不足、记载冲突、命中过多时，分别返回 `missing`、`conflict`、`incomplete` 与原因，省略金额。证据包内的历史签收底稿、所引原件、页图和文字层可离线复查。

## 企业与工作台

企业登录流程及岗位权限见[企业工作区](saas.md)。下表的业务路径可接在本机 `/api` 或登录后的 `/api/w/{企业编号}` 之后。企业请求从 `GET /api/session` 获取会话信息，所有写请求携带 `X-CSRF-Token`。

| 路径 | 参数与返回 |
| --- | --- |
| `GET /inbox` | `q`、`profile`、`sort=updated/created`、`status=all/ready/active/attention/in_review/closed/failed`、`page`。返回 `cases`、`counts`、总数及页数 |
| `GET /evidence` | `q`、`status=verified/pending/all`、`page`。返回本企业最新版本中命中的原文、证据编号、任务、文件、页码、核验状态及版本。需审计或管理权限 |

版本引用可使用 `/w/{企业编号}/workpaper/{任务编号}?rev=版本&fact=证据编号`，本机使用 `/workpaper/{任务编号}`。浏览器会进入对应工作区和原页，服务端按登录账号核验资料访问权限。

规则集 `2026.11.24.6` 开始返回 `graph.invoice_identity`。图中 `invoice_identity` 节点代表已获同页证据支持的完整票据标识，`identified_invoice` 边的 `evidence` 可定位到号码和配套代码。单笔代码字段为 `invoice_code`，报销单同一行明列的组合为 `claim_full_ref`。原件只列短号或代码有异议时，可从 I01、T02、T03 的状态和引用查看补证原因。

`origin=printed_claim_pair` 的 `claim_full_ref` 保留 `model_field=claim_ref`。它记录模型逐字抄下代码和号码后，系统凭唯一可定位的原生文字行、明确印刷的组合标签及对应视觉复检作出的归类。离线校验会对照原始模型候选值、完整引文、标签与复检记录。

规则集 `2026.11.24.8` 将同号初筛与完整标识比对分别记录。每笔 I02 的 `invoice_lookup.number` 保留本案标识、代码与原文编号，`candidates` 逐条指向前案引文，分类为 `same`、`different`、`uncertain`。同一前案与本案多张票据的比对结果可以不同。完整前案清单在 `graph.prior_invoices`，每条含 `identity` 和 `code_evidence`，可定位签收时的原页。上版仅留存八位号码时，本版提示人工核对前案代码。

`invoice-approval-v2` 在 `screened` 留存签收时查看的全部同号引文，`matches` 仅列相同标识和判定依据不足的候选。`possible_match` 表示仅有待核候选，`insufficient_identity` 表示本案短号的代码待核。报告出具后新出现的排除项也能沿回执打开前案的代码原文。当前签收版导出的 ZIP 随附该次筛查直接引用的历史签收、底稿、原件、页图及文字层。离线工具能复核候选分类 和每个排除依据，检索范围以企业当时的数据库为准。

规则集 `2026.11.24.10` 起，`graph.number_masks.facts` 保留含明确遮盖符或尾号提示的已核引文、页码和可见原值。相应的 `incomplete_invoice_id`、`incomplete_claim_ref` 或 `incomplete_claim_full_ref` 边分别连回各自的观察记录。I02 的 `invoice_lookup.withheld` 列出本次无法作精确查重的发票字段。签收回执的 `withheld` 保留查验范围缺口，`incomplete_number` 表示本次有票号不全且没有相同或待判定的前案候选。

对于尚待签收、使用旧规则的底稿，若其中已核的遮盖号码仍以可精确匹配的票号进入图谱，初审或独立复核选择通过会返回 409。`incomplete_numbers` 包含原案件、版本、涉及字段的 `count` 及前八条 `facts`。每条含证据编号、实际可见值和页码。初审可在原对话框查看引文，保留原版后重新审计。独立复核人可选择退回补件。已签收的历史版本仍可导出并复算当时的结论。

## 付款原件核验与签收

付款案初审或独立复核选择通过时，服务核验本案原件及页图，并按底稿中所引历史版本检查前案的签收决定、逐字段引文、原件、相关页图和归档文字层。原件或页图缺失、文件摘要不符或核验期间文件发生变化会返回 409。响应中的 `payment_source` 提供工作区内的 `case_id`、`rev`、`doc`、文件名 `name`、`file`（`original` 或 `page`）及可定位的 `fact`。页图另含页码 `page`。工作台保留审计员已填的意见，可跳到对应版底稿。成功通过后执行记录的 `payment_sources` 事件列出核对的历史底稿数和文件数。

新版付款底稿的 `policy.payment_checks` 为 `payment-findings-v1`。底稿的 `graph.payment_history` 保存实际检索时点和前案版本。签收与离线核验会重新核对已列前案的签收时间、匹配类型、字段引文和分期金额。若前案引文缺项、发现的文字或金额与当版计算不符，或底稿总结与逐项发现矛盾，验收会返回 409。缺失的依据应通过重新审计或退回补件处理。

### 回单照片的流水展示说明

自规则 `2026.11.24.15` 起，`policy.payment_references` 与 `graph.transfer_references.format` 记为 `receipt-reference-v2`。受独立引文限定的流水在 `facts[].notes` 中返回说明字段编号、逐字引文和来源状态。`state=pending_note` 表示同页候选说明待核图，`state=partial` 表示已有来源支持部分展示。关系 `proposed_transfer_note`、`qualifies_transfer_ref` 均保留说明和流水两个证据编号。原生文字页的说明行仍可在 `lines` 中查看。

跨案分期核查在 `incomplete_references` 中携带相同的来源。系统按本次比较采用的规则阅读旧版原文，旧版证据包仍按出具时的规则复算。

### 整页流水核图

规则 `2026.11.24.16` 使用 `receipt-reference-v3`。照片、扫描页或无法逐字定位流水栏的混合 PDF，只有“已核对栏内字符”时会返回 `state=visibility_unchecked`。审计员可在现有的 `POST /attest` 请求中按已选字段分别登记展示范围。

```json
{
  "rev": 3,
  "reviewer": "水印样本校验",
  "decision": "confirm",
  "facts": ["d02/p1/f7"],
  "reference_visibility": {"d02/p1/f7": "complete"},
  "note": "对照本次水印原件的流水栏、备注与页脚，整页完整显示 0042。"
}
```

可选值为 `complete` 和 `partial`。省略这一字段表示只确认引文。同一请求内某项无效时会整批退回。只有所选的付款回单任务流水字段支持该意见。原生文字可精确定位、原件已变化、已登记的印刷限定位与完整意见冲突时，可根据接口返回原因处理。独立说明仍待核时，也需先处理说明。

流水字段的 `attestation.source_check.reference_visibility` 留存意见、字段编号、当时的取值和逐字引文。外层回执保存核图时的底稿、原件与页图摘要。人工确认部分展示时会返回 `reviewed_partial`，若另有印刷限定，底稿继续保留其逐行来源。引用历史回单时，证据包另附所引原页的核图登记摘录 `field-checks/reference-visibility.json`。

## 补充协议与验收标准

自规则 2026.11.24.25 起使用 `contract-performance-v7`。涉及补充协议的 H02 发现附有 `quality_change`。其中 `state` 可取 `applied`（本次终验适用变更后标准）、`original`（本次终验适用原标准）、`pending`（需人工核对）。`original_criterion`、`revised_criterion` 和 `applied_criterion` 分别记录原约定、新约定和本次实际采用的标准。待核的采用值为 `null`。

`buyer_sealed_on`、`seller_sealed_on`、`effective_on`、`accepted_on` 使用 ISO 日期或 `null`。`scope_clear` 记录已能确认变更只涉及验收标准。`units` 表示涉及变更的资料，`evidence` 指向字段或原页。图谱的 `quality_addenda` 保留原件中的变更线索、编号展示限制、协议各页的文字和版式覆盖情况，以及尚待核对的行号与引文。每期 H04 及每张回单 H05 单独出具状态。

下载证据包后，使用 `server/.venv/bin/python server/verify.py --rules-from-git main --render-addenda 证据包.zip` 可以从本地可信提交复算结论，并从提交的原合同、补充协议及本次终验所据资料重新分页，核对页图、文字、引文位置及版式。重新分页使用与该版底稿匹配的本机分页程序和依赖。常规包校验也可以直接用系统 Python 执行。

规则 2026.11.24.26 对已有文字定位的旧案按需补充版式记录。遇到补充协议线索时，使用原件重新分页，逐项比较旧页图摘要、文字及坐标，匹配后记录该页是否包含图片或批注。旧版原页无法重现时，相应补充协议继续要求人工通读。

## 合同约定的验收签认

自规则 `2026.11.24.27`，`policy.performance_checks` 为 `contract-performance-v8`，`policy.acceptance_authority` 为 `named-acceptance-signatures-v1`。当原件含有验收签认约定或身份待查的签字栏时，H02 的 `acceptance_authority` 保存合同要求、逐份记录和所据证据。

| 字段 | 含义 |
| --- | --- |
| `mode`、`required` | `single` 为一名指定人员，`joint` 为须共同签认的两人，`unresolved` 为约定待核。人员按条款原序排列。 |
| `applies_to` | `final` 为终验，`final_and_reinspection` 为终验及整改复验。约定范围未确定时为 null。 |
| `records[]` | 分别列出 `acceptance`、`reinspection` 原件的 `unit`、`date`、`status`、`detail`、`signed` 和 `evidence`。`missing_names` 表示尚缺独立核准签认的人，`other_names` 表示已核签字栏里约定以外的人。 |
| `clause_evidence`、`contract_evidence`、`evidence` | 对应签认约定、合同身份和生效时间、整体结论所引用的证据编号。 |

`graph.acceptance_authority_sources` 按原件及页码保留条款 `clauses`、签字行 `signatures`、覆盖页 `pages` 和影像线索 `visual_notes`。签字行记录精确原文、原生行号及 `confirmed`。一条 `named_acceptance_signature` 关系将该份合同的条款连到一个经独立核图并符合约定的签字栏。签认相符证明所列人员与条款对应，交付数量、质量、缺陷关闭及付款时点仍需分别核验。

本机通过决定会核对相关原件、页图、签认记录和来源。旧版曾给出终验相符并有未经检查的签认约定时，签收返回 409，请按当前规则重审。离线校验可用 `server/.venv/bin/python server/verify.py --rules-from-git main --render-performance 证据包.zip` 重新分页并复算指定版本的发现。

## 附加生效条件

自规则 `2026.11.24.30` 起，`policy.contract_effect` 为 `contract-effect-sources-v1`，履约程序为 `contract-performance-v11`。单合同的 H01 包含 `effect_review.conditions[]` 和 `mixed_pages[]`，分别列出有待核对的生效或状态记载，以及需要整页核图的合同页。每条记载都有 `doc`、`page`、`quote` 和 `facts`。原生文字可有 `line`，纯影像观察保留读图引用。

`graph.contract_effect_sources` 保留合同原件的页清单和候核引文。发现的 `evidence` 包含各合同页，可以复查模型遗漏的正文或页末条件。原版记录可继续查看。对曾判为签署与生效相符的旧底稿签收时，若查到当版未核的条件或版式，返回 HTTP 409 并提示使用现行规则重新审计。

## 分批验收与付款

规则 `2026.11.24.29` 沿用下述日期校验，并用 `contract-performance-v10` 核对合同分批条款。在有相应条款的案件，H02 的 `batch_acceptance` 给出 `independent`、`deemed_final`、`completion_on`、`rule_ref`、各批 `batches[]`、验收原件 `records[]` 及可能影响合同或付款的 `riders[]`。`completion_on` 仅在合同明确约定全部合格即终验且证据完整时写入日期。每批保留合同原文引用、约定数量单位及编号、状态、原因、关联验收单和证据范围。H04/H05 的 `stage.batch_index` 与 `stage.batch_date` 指向各自所据的批次及有据的合格日期。

分批程序最初的 `policy.delivery_batches` 标记为 `contract-delivery-batches-v1`，具名分批签认使用 v2。`graph.delivery_batch_sources` 保存分批线索、各页已覆盖范围、漏提的原行和影像观察。`delivery_batch_acceptance` 关系由交付批次条款指向验收范围，`batch_payment_basis` 由当期付款条款指向同一份验收记录。签收前及离线复算均核对这些关系和原文。证据包支持 `--render-performance` 从版本中的原件重现相关页图和条款版式。

## 质保金释放依据

规则 `2026.11.24.31` 使用 `policy.performance_checks=contract-performance-v12` 和 `policy.warranty_checks=contract-warranty-release-v1`。合同履约、采购及回单核对中，已识别的质保期次 H04 和对应成功回单 H05 附有 `warranty_check`。外层 `status` 还受签署、生效、验收及分期安排约束。

| 字段 | 含义 |
| --- | --- |
| `accepted_on`、`calendar_end`、`confirmed_on` | 经核对的合格终验或复验日、可复算的日历末日、已关联签认的期满记录日。缺证用 `null` |
| `period` | 原条款给出的单位、数量或固定日期，`unadjusted` 表示合同明确约定不顺延 |
| `requires_defect_clearance`、`defect_open` | 已定位的释放前提明确要求缺陷清结、确认单明确记载未解决问题。需结合 `status` 和原文判断 |
| `term_ref`、`condition_ref`、`confirmation_ref`、`defect_ref` | 指回原条款及确认记录的事实编号 |
| `identity_conflicts`、`problems`、`scope`、`evidence` | 所列主体或标的不一致的两端事实、待核原因、相关资料和引用 |

`graph.warranty_sources.pages` 记录合同、验收及期满确认原页的文字和影像覆盖，`lines` 保留日历口径、释放条件、确认及未核原文。原生文字可按 `doc/page/line` 定位，影像观察保留事实编号并可打开页图。`warranty_release_basis` 从已获支持的付款期次指向确认单原文。归档复算重读原页文字和关系，签收重新核验所据原件。旧底稿可按原版复算，旧正向结论遇到现行质保程序核不清的条款或记录时，签收返回 HTTP 409。

## 逐期付款时限与回单日期

规则 `2026.11.25.01` 的 `policy.performance_checks` 为 `contract-performance-v13`，`policy.payment_windows` 为 `phase-payment-window-v1`。遇到付款时限原文或相关页需核图时，H04 和已识别期次的 H05 可附 `payment_window`。H04 说明触发日期和该期付款条件，H05 核对某份回单的实际日期。各条发现的 `status` 和整案的 `result.verdict` 分别保存。

| 字段 | 含义 |
| --- | --- |
| `state` | `fixed` 表示可据约定计算末日，`nominal` 表示已算出顺延前的日历末日，`unresolved` 表示依据待核，`conflict` 表示原件日期冲突 |
| `terms` | 识别到的条款，包括 `basis`（固定日、自然日或工作日等，分别为 `fixed`、`calendar`、`working`）、期限及日历口径 |
| `term_ref`、`trigger_ref`、`trigger_on`、`calendar_end` | 合同付款条款与履约日期事实编号、起算日期、复算末日。缺少依据用 `null` |
| `lines`、`mixed_pages` | 相关原文及需要查看整页的材料。原文保留文件、页、可用行号、引文和事实编号，未被读成字段的原生文字也可定位 |
| `calendar_source`、`days` | 所用调休日历来源键及逐日的 `date`、`kind`、`counted`、累计 `total`。来源键指向 `policy.sources` 的年度通知 |
| H05 的 `paid_ref`、`paid_on`、`outcome`、`days_late` | 回单日期依据与取值。比较结果为 `within`、`early`、`late`、`same_day`、`extension_unknown` 或 `unresolved`。仅 `late` 给出晚于可核末日的自然日数 |

`graph.payment_window_sources` 逐页保存原件覆盖及付款时限原文。`payment_window_comparison` 关联付款期限条款与回单日期，两端均带证据编号。核验归档时可按当版方法重算全部日期和日历。提交通过决定时会重查相关原件，旧底稿曾判相符、现可定位到相冲突或待核的付款条件时返回 HTTP 409。

## 终验和复验保留意见

规则 `2026.11.25.02` 使用 `contract-performance-v14` 和 `policy.acceptance_reservations=acceptance-reservations-v1`。`graph.acceptance_reservation_sources.pages` 登记验收及复验原件的分册、资料、页号、文字层和整页版式。`lines` 保留 `doc`、`unit`、`page`、原生行号 `line`、逐字引文 `quote`、线索种类 `kind` 及观察编号 `facts`。原件有文字而模型未抽成字段时，行号仍可查。影像观察的行号为 `null`。每条 `acceptance_reservation` 边连接所属资料与对应原页。

在整体验收或复验程序中，H02 的 `acceptance_reservations` 包含本次所据的 `pages`、`lines` 和需要通读的 `mixed_pages`。`limited` 表示文字涉及验收范围限制，`unclear` 表示保留意见需解释。已知的超限或原验收失败仍可使 H02 为 `issue`。是否有材料支持某一期付款，由该期 H04 及实付 H05 分别说明。核验旧底稿可按当时规则重算。原先判定终验相符，现识别到保留意见或必须通读的影像时，提交通过决定返回 HTTP 409，提示重新审计。

## 履约日期核对

规则 `2026.11.24.28` 使用 `contract-performance-v9`。涉及日期疑点的 H01、H02 或 H05 附有 `date_checks[]`。每一项保存 `event`（`contract_period`、`acceptance`、`reinspection` 或 `payment`）、`status`（`risk` 或 `missing`）、案情说明 `detail` 和引用 `evidence`。原生日期的证据可定位到逐字引文和文字层原行，人工核图的日期可以回到其核图回执。H04 继承该期所据的签署、验收或质保条件。历史底稿保留当时的程序，申请签收时会重新检查原为相符的日期判断。

`--render-performance` 可从 v9 本案的合同、审批、验收、质保、回单等履约程序所据原件重现分页，同时校核文字、定位和版式。使用 `--rules-from-git main` 可按当时的程序重算各版结论。
