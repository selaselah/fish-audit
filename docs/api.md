# 本机审计接口

基础地址为 `http://127.0.0.1:8000`。接口与前端同源。审计资料只在当前电脑的本地工作区共享。所有时间戳以 UTC 保存，网页按北京时间显示。

| 请求 | 作用 |
| --- | --- |
| `GET /api/health` | 服务状态，`audit` 中提供审计服务商、模型、业务范围及页数限制。兼容字段 `mode` 指旧版文本审核模式 |
| `GET /api/controls` | 采购及差旅程序编号、规则版本、适用背景与来源 |
| `POST /api/cases` | multipart 表单，`title` 和一个或多个同名 `files` 字段，返回 HTTP 202 和 `id` |
| `GET /api/cases` | 台账，含处理进度、建议、底稿版本和人工决定 |
| `GET /api/cases/{id}` | 原件清单、阶段、百分比、事件、版本和验收历史 |
| `GET /api/cases/{id}/reports/{rev}` | 特定版本的完整底稿、生成时间及摘要 |
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

## 核图与最终决定

核图请求使用 `application/json`。姓名与意见必填。决定可为 `confirm` 或 `dispute`，`facts` 取自当前版本的证据编号。

```json
{"rev":1,"reviewer":"演练人员","decision":"confirm","facts":["d01/p1/f3"],"note":"已对照合成原页的票号。"}
```

最终决定的字段为 `rev`、`reviewer`、`decision`、`note`，决定可为 `approve`、`return` 或 `escalate`。已归档、正在重算或提交过期版本返回 409。下载及操作均以任务和版本为范围。错误响应采用 `{"error":"可读说明"}`。

更正或补录时提交 `rev`、`doc`、`page`、`field`、`quote`、`value`、`region`、`reviewer`、`note`。更正须携带本页的 `target` 证据编号，补录时设为 null。`field` 取自 `GET /api/controls` 的 `fields`，`region` 为 top、middle 或 bottom。新记录与该页 SHA-256 一起保存。

任务状态依次为 `queued`、`running`、`ready`（可验收）、`closed`（已归档）。`failed` 保留阶段、原因与已完成页面。同号提示既查本案已核票据，也查询本工作区运行审计时已归档的底稿。旧原型的 `POST /api/reviews` 继续支持文本审核。

## 企业与工作台

企业登录流程及岗位权限见[企业工作区](saas.md)。下表的业务路径可接在本机 `/api` 或登录后的 `/api/w/{企业编号}` 之后。企业请求从 `GET /api/session` 获取会话信息，所有写请求携带 `X-CSRF-Token`。

| 路径 | 参数与返回 |
| --- | --- |
| `GET /inbox` | `q`、`profile`、`sort=updated/created`、`status=all/ready/active/attention/closed/failed`、`page`。返回 `cases`、`counts`、总数及页数 |
| `GET /evidence` | `q`、`status=verified/pending/all`、`page`。返回本企业最新版本中命中的原文、证据编号、任务、文件、页码、核验状态及版本。需审计或管理权限 |

版本引用可使用 `/w/{企业编号}/workpaper/{任务编号}?rev=版本&fact=证据编号`，本机使用 `/workpaper/{任务编号}`。浏览器会进入对应工作区和原页，服务端按登录账号核验资料访问权限。
