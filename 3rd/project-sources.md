# 工程所据的文献、制度与外部项目

查阅于 2026-11-25。已有源码和文档以 Git 提交 `1b1dd92ab83fe4612eba44d206a103105f9c3fb0` 为核对基线。方法的取舍记录在本仓库，外链指向论文作者、标准发布方、主管部门或软件项目。首页演练有自己的底稿版本和原件摘要。[合成资料声明](showcase-provenance.md)

## 公开文献与标准

| 出处及版本 | 项目采用的做法 | 仓库与一手来源 |
| --- | --- | --- |
| Chen 等，*FinQA: A Dataset of Numerical Reasoning over Financial Data*，EMNLP 2021 | 将财务数字推理写成可执行的运算，底稿留存公式、取数及结果，可从原件复算。 | [研究记录](../docs/research.md) · [计算实现](../server/calculations.py) · [论文](https://aclanthology.org/2021.emnlp-main.300/) · [作者项目](https://github.com/czyssrs/FinQA) |
| Zhu 等，*TAT-QA: A Question Answering Benchmark on a Hybrid of Tabular and Textual Content in Finance*，ACL-IJCNLP 2021 | 表格里的数字要结合正文解释。每个操作数标明所属单据、字段、币种、单位和引文，便于发现相同金额取错来源。 | [取数与重算](../docs/research.md#查看与重算) · [论文](https://aclanthology.org/2021.acl-long.254/) · [作者项目](https://github.com/NExTplusplus/TAT-QA) |
| Zhao 等，*FinRAGBench-V: A Benchmark for Multimodal RAG with Visual Citation in the Financial Domain*，EMNLP 2025 | 视觉引文需要在文档中定位。工作台保留实际读入的页图，有可信文字层时可标原行，扫描图或引文冲突交人工核图。 | [研究记录](../docs/research.md) · [逐页形成证据](../docs/audit-method.md#逐页形成证据) · [论文](https://aclanthology.org/2025.emnlp-main.211/) · [作者项目](https://github.com/zhaosuifeng/FinRAGBench-V) |
| W3C，*PROV-DM: The PROV Data Model*，2013-04-30 Recommendation，第 5.2 节 | 用修订、引用和原始来源解释跨底稿取证。前案版本、引文、页图和签收意见一并保留，读者可查是谁在何版作了决定。 | [跨底稿引文与签收](../docs/research.md#跨底稿引文与签收) · [W3C 固定版本](https://www.w3.org/TR/2013/REC-prov-dm-20130430/#component2) |

以上三篇论文在本工程用作方法参照。首页合同、验收和回单的数据来源是本仓库的带水印样本生成器。[案例生成出处](showcase-provenance.md#版本与生成出处)

## 已有法规、内控指引与审计准则

下表保留项目实际引用的版本与条款。规则与来源的对应关系见 `SOURCES` 和 `MAPPING`。注册会计师准则用于解释取证与底稿编制，企业审核某笔付款时还要查该笔合同、验收材料及本单位权限制度。[审计方法](../docs/audit-method.md) · [来源与程序映射](../server/policy.py)

| 项目引用的版本 | 对应的审核事项 | 仓库与发布方 |
| --- | --- | --- |
| 《中华人民共和国会计法》2024 年修正，第十四条 | 核验原始凭证的准确性、完整性，记录需要补正之处。 | [适用范围](../docs/audit-method.md#本期适用范围) · [财政部全文](https://kjs.mof.gov.cn/zhengcefabu/202408/t20240812_3941615.htm) |
| 《中华人民共和国民法典》2020-05-28 通过 | 授权、签约与生效见第 143、165、490、502 条等，变更见第 543、544 条，约定质量、检验及付款见第 615、620 至 623、626、628 条，期间见第 200 至 204 条。工作台据此组织 H01、H02、H04、H05 的核对事项，具体条件逐案取自原文。 | [合同履约与分期](../docs/audit-method.md#合同履约与分期) · [最高人民法院全文](https://www.court.gov.cn/zixun/xiangqing/233181.html) |
| 《企业内部控制应用指引第 7 号——采购业务》（财会〔2010〕11 号）及财政部会计司 2010-06-11 解读 | 第四条涉及职责权限，第十一至十三条涉及验收、异常处理与付款，第十五条涉及记录及核对往来。对应实际型号、数量、质量、异常处理和付款审核。 | [采购与验收方法](../docs/audit-method.md#约定的设备和实际验收的设备) · [财政部指引，第 27 页起](https://kjs.mof.gov.cn/zhengcefabu/201005/P020230421440664863663.pdf#page=27) · [会计司解读](https://kjs.mof.gov.cn/zhengcejiedu/201006/t20100611_322435.htm) |
| 《企业内部控制应用指引第 16 号——合同管理》（财会〔2010〕11 号）及财政部会计司 2010-07-06 解读 | 对照解读中「合同签署」环节，查看签约权限、委托依据和用印。具名代理人及其权限由委托书确定。 | [代理签约与授权](../docs/audit-method.md#代理人签约及书面授权) · [财政部指引，第 71 页起](https://kjs.mof.gov.cn/zhengcefabu/201005/P020230421440664863663.pdf#page=71) · [会计司解读](https://kjs.mof.gov.cn/zhengcejiedu/201007/t20100706_325984.htm) |
| 《中国注册会计师审计准则第 1131 号——审计工作底稿》，2022-01-05 修订，第十、十一条 | 记录程序、证据、结果与受测事项的识别特征，合订件中的验收单也要落到各自的单号和原页。 | [合订件与底稿](../docs/audit-method.md#同一份-pdf-中的验收单) · [财政部准则正文](https://kjs.mof.gov.cn/zhengcefabu/202201/P020220107606618642900.pdf) |
| 《中国注册会计师审计准则第 1301 号——审计证据》，2022-12-22 修订，第三、十、十一、十三、十五条 | 核对证据来源与可靠性。证据之间矛盾时，保留矛盾并考虑追加程序。 | [适用范围](../docs/audit-method.md#本期适用范围) · [中注协 PDF，按正文首页编号](https://www.cicpa.org.cn/ztzl1/Professional_standards/xxzztx/zyzz/sjzz/202105/P020240412542695263912.pdf) |
| 财政部、国家档案局《关于规范电子会计凭证报销入账归档的通知》，财会〔2020〕6 号，第三条第（三）项 | 在仅使用电子会计凭证报销入账归档的情形下，关联审签程序、防止重复入账与项目的已签收同票核查。 | [项目程序清单](../docs/audit-method.md#程序清单) · [两部门通知](https://www.mof.gov.cn/zcsjtsgb/gfxwj/202003/t20200323_3583778.htm) |
| 国家税务总局公告 2015 年第 84 号第四条、2024 年第 11 号第一、三、四条 | 前者说明该类电子普通发票的 12 位代码和 8 位号码，后者规定数电发票统一赋号、号码 20 位。传统票逐票比对代码与号码，保留前导零。 | [八位票号的逐票关联](../docs/audit-method.md#八位票号的逐票关联) · [2015 年公告](https://fgk.chinatax.gov.cn/zcfgk/c100012/c5194596/content.html) · [2024 年公告](https://fgk.chinatax.gov.cn/zcfgk/c100012/c5236067/content.html) |
| 《国务院办公厅关于 2026 年部分节假日安排的通知》，国办发明电〔2025〕7 号 | 合同明确采用全国调休日历时，按 2026 年放假和补班安排逐日复算付款末日。 | [逐日计算及版本](../server/cn_workdays.py) · [项目引用的国务院公报](https://www.gov.cn/gongbao/2025/issue_12406/material/gwygb202532.pdf) · [政府转载正文](https://www.beijing.gov.cn/cs/gncs/zcwj/202603/t20260327_4568275.html) |

## 外部技术项目与资源

服务端依赖以仓库锁定值为准。表中注明「本机」的版本实读于项目 Python 环境，系统程序由部署环境提供。[依赖清单](../server/requirements.txt) · [运行环境](../docs/README.md#在新环境安装)

| 项目及版本依据 | 在本工程中可核对的用途 | 仓库与上游 |
| --- | --- | --- |
| SQLite，本机 Python 3.12.14 所连 SQLite 为 3.53.1 | 事务保存底稿及其索引。表达式索引跟踪逐页状态，支持 FTS5 trigram 时用其检索三个字符以上的引文。 | [企业检索说明](../docs/saas.md#任务台账与证据检索) · [存储实现](../server/storage.py) · [表达式索引](https://www.sqlite.org/expridx.html) · [FTS5 trigram](https://www.sqlite.org/fts5.html#the_trigram_tokenizer) |
| OpenAI Responses API，仓库默认模型及首页 R7 逐页与专家调用均为 `gpt-4.1-mini-2025-04-14` | 将页图交模型提取观察值，再按 JSON Schema 形成可核对的字段。底稿可追到实际送入的页图、请求和模型版本。 | [模型配置](../server/config.py) · [请求格式](../server/protocol.py) · [图像输入](https://developers.openai.com/api/docs/guides/images-vision) · [结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs) |
| pypdfium2 5.13.0、Pillow 13.0.0（仓库锁定），LibreOffice（随部署环境） | 用 PDFium 渲染原页、取文字和位置，用 Pillow 处理照片方向与多页图片，Word 经 LibreOffice 无界面转换后进入逐页流程。 | [分页与文字定位实现](../server/documents.py) · [pypdfium2](https://pypdfium2.readthedocs.io/en/stable/) · [Pillow](https://pillow.readthedocs.io/en/stable/) · [LibreOffice 命令参数](https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html) |
| Flask 3.1.3、Waitress 3.0.2、python-dotenv 1.2.4，均由仓库锁定 | 工作台、原页和底稿从同源 HTTP 接口读取，企业实例由 Waitress 提供服务，服务配置由 python-dotenv 读取。 | [HTTP 入口](../server/main.py) · [配置入口](../server/config.py) · [Flask](https://flask.palletsprojects.com/en/stable/) · [Waitress](https://docs.pylonsproject.org/projects/waitress/en/stable/) · [python-dotenv](https://github.com/theskumar/python-dotenv) |
| ReportLab 4.4.9、python-docx 1.2.0（本机） | 演练脚本用前者生成带水印的 PDF，用后者生成 Word 对照样本。首页三份原件均为 PDF。 | [样本生成器](../docs/samples/generate.py) · [演练环境说明](../docs/samples/README.md#复现) · [ReportLab](https://docs.reportlab.com/) · [python-docx](https://python-docx.readthedocs.io/en/latest/) |

本轮桌面及手机浏览器回归另用 axe-core 4.14.1 检查首页、台账、提交资料、原件核图与登录页。检测工具在开发机执行。[axe-core 官方项目](https://github.com/dequelabs/axe-core)

### 操作图标

工作台和首页的操作图标取自 Bootstrap Icons v1.13.1。所用 25 个字形按该版本的官方码点从 WOFF2 字体裁出，随本站加载。图标按钮具备独立文字或无障碍名称。[官方版本](https://github.com/twbs/icons/tree/v1.13.1) · [官方码点表](https://github.com/twbs/icons/blob/v1.13.1/font/bootstrap-icons.json) · [MIT 许可](licenses/bootstrap-icons-MIT.txt) · [本地字体](../frontend/assets/audit-icons.woff2)

### 首页字体

两份首页子集的许可证均为 SIL Open Font License 1.1。下表摘要来自本轮实际使用的 WOFF2 文件。

| 字体及首页用途 | 本轮文件 SHA-256 | 仓库与上游 |
| --- | --- | --- |
| Noto Serif SC，首页标题的中文子集。Google Fonts 元数据记录的上游为 `notofonts/noto-cjk` 提交 `985fa52c81c1d6692ccdd82bc3656e8fb932fd89`。 | `239bfb03268dc2556d036e44c92dd933913f5ed3baca3233fc3cd3723ac5a36b` | [字体文件](../frontend/assets/noto-serif-sc.woff2) · [标题样式](../frontend/landing.css) · [notoserifsc-OFL.txt](licenses/notoserifsc-OFL.txt) · [Google Fonts 字样](https://fonts.google.com/noto/specimen/Noto+Serif+SC) · [上游元数据](https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifsc/METADATA.pb) |
| Geist Latin，界面拉丁文字和数字的子集。 | `9b6f5ff45b278c744b5f379a2c4ecbaf858a842b8eaf82ac8d21b699ca16c608` | [字体文件](../frontend/assets/geist-latin.woff2) · [界面字体样式](../frontend/brand.css) · [geist-OFL.txt](licenses/geist-OFL.txt) · [Geist 官方项目](https://github.com/vercel/geist-font) |
