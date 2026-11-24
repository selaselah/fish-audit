# 本机审计接口

基础地址为 `http://127.0.0.1:8000`。接口与前端同源。审计资料只在当前电脑的本地工作区共享。所有时间戳以 UTC 保存，网页按北京时间显示。

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

任务详情的 `page_progress.counts` 分别给出已分页 `prepared`、已提取 `read`、已有视觉复检记录 `checked` 的页数。三项分别计数，已复检页也计入已提取页。`documents` 以原件编号列出页码及最近保存的状态，`invalid` 表示提取记录需要检查。`activity` 提供当前处理或中断位置的原件、页码及步骤，队列中、已完成及整案处理阶段可为空。完成视觉复检的页仍可能有待人工确认的字段。

专家模型已经返回且响应已保存、底稿尚待生成时，`page_progress.expert` 提供目标底稿版本 `target_rev` 与保存时间 `saved_at`。写入响应的同时，工作台进度更新为 96%。恢复后若同案同版的完整请求与原记录相符，系统标记 97% 并沿用原响应。底稿成功提交时清理临时响应，完整专家执行记录进入该版底稿。

原件下载和页图预览在响应前核对 SHA-256。请求支持 ETag、HEAD 和字节范围。审计人员或管理员可加 `?rev=版本号`，同时校验所选底稿及其图谱中的来源摘要，底稿引用默认使用这个入口。员工可从本人任务读取已登记的当前原件和页图。已登记的文件缺失或内容与相应摘要不符时返回 409。

## 复算历史底稿

审计岗可从独立网址 `/workpaper/{id}?rev={版本}&view=replay` 打开复算入口，企业访问沿用 `/w/{企业编号}` 前缀。复算接口遵循企业权限与 CSRF 校验，只读取所选版本。每次都从服务器读取底稿并校验其 SHA-256。

`state=verified` 表示逐项发现、引文编号、算式及整案建议均与当时的图谱和专家建议复算一致。`mismatch` 表示已找到对应规则，但数据或输出无法对齐。`unavailable` 会说明缺少源码摘要、发布历史无匹配或本机依赖不可用等原因。已完成的三种结果均返回 HTTP 200。响应包含底稿版本、摘要、时间和规则集版本，有可运行代码时还包括匹配提交 `commit`、受信发布历史的起点 `trusted_tip` 及各依赖的 SHA-256。复算一致时另含发现数、整案建议、`findings_sha256` 和 `result_sha256`。

匹配使用同一个本地 Git 提交里规则及其递归导入的项目源码。仅匹配到相同版本号不足以执行。记录中的提交说明其中的规则源码与底稿相符。该提交可以晚于底稿出具。复算直接使用当时留存的模型建议作为输入。原件、页图和模型请求的一致性可随证据包离线校验。

## 核图与最终决定

核图请求使用 `application/json`。姓名与意见必填。决定可为 `confirm` 或 `dispute`，`facts` 取自当前版本的证据编号。

```json
{"rev":1,"reviewer":"演练人员","decision":"confirm","facts":["d01/p1/f3"],"note":"已对照合成原页的票号。"}
```

提交确认、更正或补录时，服务端重新读取所选字段的原件与页图，核对字节与当前底稿登记的 SHA-256。一次选中多页时，任一页缺失、内容变化，或核对期间有人签收该案，整次操作返回 409，不写入其中任何一项。所选字段不属于该底稿或页码时返回 400。对资料提出 `dispute` 仍可记录无法核实的原因。

新记录的 `source_check` 保存动作 `confirm`、`correct` 或 `add`，以及案件、底稿版本与摘要、文档编号、页码、原件与页图的 SHA-256 和 UTC 核对时间。新版底稿的字段通过 `attestation` 或 `amendment` 引用这项记录。ZIP 在 `field-checks/r{版本}/report.json` 保存所引旧底稿的原始字节，每个版本一份。操作针对导出版本时直接引用包内的 `report.json`。旧记录沿用其历史字段，只有实际执行过这项校验的操作才有 `source_check`。

跨案同票命中带核图存证的票号时，`graph.prior_invoices` 的该条记录含 `checked_field` 和历史人工决定的 `signoff_hash`。导出包的 `prior/{案件}/r{版本}/` 下可核对签收意见、当时的底稿及票号原页。跨案付款检查同样会重新核对其所引人工字段的原件与页图。

最终决定的字段为 `rev`、`reviewer`、`decision`、`note`，决定可为 `approve`、`return` 或 `escalate`。已归档、正在重算或提交过期版本返回 409。下载及操作均以任务和版本为范围。错误响应采用 `{"error":"可读说明"}`。

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
