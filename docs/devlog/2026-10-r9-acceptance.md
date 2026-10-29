# 第9轮补充验收（2026-10-29）

## 环境与决策

- Windows 11 / PowerShell 7.6.5 / 现有 .venv Python 3.12.10 / NVIDIA GeForce RTX 3050 Laptop GPU。
- 复用原三个任务提交459061d、7156ff2、d7bafa1；本次为真实补充验收，不改写提交、不打tag。
- git pull成功；邮箱xjsaber@users.noreply.github.com；用户已有未跟踪观察JSON保留。
- API使用已有配置，未输出密钥；CLI明确使用memory检索器。只用原公开年报，不下载新模型。
- 用Python UTF-8修复pending-audit日志的排版和五句完整原文，纠正第4句的过强“合理”分类。
- 既有多页计算、内部词清理、合并优先与归母口径均有测试，未新增重复代码或测试。

## 本次CLI实跑

`python -m core.graph.run --pdf data/samples/public-annual-report-2024.pdf --out-dir output/r9-acceptance --summary-json output/r9-acceptance/run-summary.json`

- 记录时间UTC：2026-10-29T12:12:38.948526+00:00
- chunks：1646；errors：[]。
- parse：77.7s；index：145.1s；graph：177.3s；total：400.5s。
- 待核实标记总数：0。
- 导出：["output\\r9-acceptance\\年报分析-20261029-201218.md", "output\\r9-acceptance\\年报分析-20261029-201218.docx"]（均不提交）。

| 章 | 核验状态 | 重写次数 | 待核实数 | 引用页 | 召回页 | 耗时(s) |
| --- | --- | ---: | ---: | --- | --- | ---: |
| 公司概况 | supported | 0 | 0 | 6,7,26,88 | 6,7,26,33,87,88 | 27.8 |
| 主营业务 | supported | 0 | 0 | 23,26,153,154 | 9,23,26,64,153,154 | 21.4 |
| 财务表现 | supported | 0 | 0 | 7,8,68 | 7,8,67,68,69,92 | 27.3 |
| 风险因素 | supported | 1 | 0 | 2,30,31,167 | 2,27,30,31,167 | 62.6 |
| 结论 | supported | 0 | 0 | 9,23,25,29,43 | 9,23,25,29,43 | 19.3 |

### 待核实原句

本次无【待核实】原句。正文仍出现“公司主营定位待核验”、主要会计数据“相关数据待核验”，以及无法确认全年同比/毛利率的陈述。0处仅是该精确标记的计数，不等于未解决事项为0，也不能据此宣称内容质量提升。

### 公司信息与引用

### 公司基本信息与注册地

公司中文名称为深圳市远望谷信息技术股份有限公司，中文简称为远望谷，外文名称为 Invengo Information Technology Co., Ltd.，外文名称缩写为 Invengo [public-annual-report-2024.pdf p6]。

公司注册地址为深圳市南山区粤海街道高新南十道63号高新区联合总部大厦27、28楼，注册地址邮政编码为518052，办公地址与注册地址相同 [public-annual-report-2024.pdf p6]。

公司注册地址历史变更情况为不适用 [public-annual-report-2024.pdf p6]。

### 内部词检查

calc_financials=0；写作上下文=0；销售净利率=0。

## 截图与人工确认

- 使用 `python scripts/screenshots.py --skip-qa --pdf data/samples/public-annual-report-2024.pdf --report-port 8512` 重拍 report-preview / report-progress。
- 脚本运行真实Streamlit并独立调用模型；截图对应UI实跑，不冒充上述CLI相同输出。模型输出可能不同，截图不能替代CLI summary。
- Word打开截图仍由作者拍摄，README对应图片行保持注释；本次不生成占位图。
- 人工确认：通读DOCX，尤其无数字语义和否定披露陈述。supported不是完整事实人工验收；见审计日志第2/4句与额外not_found。

## 测试与坑

`python -m pytest -q -rs -p no:cacheprovider --basetemp=C:\Users\xjsab\AppData\Local\Temp\d2r-r9-acceptance-final-20261029`

185 passed / 11 skipped / 1 warning，13.23s。11项为Milvus Lite原生Windows不支持；warning为LangChainPendingDeprecationWarning。
沙箱对外部仓库git操作最初返回工作树错误，受支持提权审批后git pull成功；未绕过拒绝。
脚本标准输出有缓冲，长任务进度由进程与产物确认；不以无即时输出判定失败。
