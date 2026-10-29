# 第 10 轮任务 2：final-run

## 环境与执行基线

- Windows 11 / PowerShell 7.6.5 / 现有 .venv Python 3.12.10 / NVIDIA GeForce RTX 3050 Laptop GPU。
- CLI 和截图运行代码提交：4a2562f（任务 1 已推送）。后续任务仅整理文档及卫生测试，不改变报告运行代码。
- 使用原公开年报与现有模型配置；CLI 明确使用 memory。未输出密钥，未下载新模型，未启动重复 CLI。

## 实跑观察（非基准、重跑会变）

`python -m core.graph.run --pdf data/samples/public-annual-report-2024.pdf --out-dir output/v1-final --summary-json output/v1-final/run-summary.json`

- chunks：1646。
- 解析 87.6 s；入库 77.6 s；graph 178.8 s；总计 344.5 s。
- errors：[]。
- 导出：["output\\v1-final\\年报分析-20261029-205134.md", "output\\v1-final\\年报分析-20261029-205134.docx"]。文件保留在 output，不提交。

| 章节 | 核验状态 | 重写次数 | 【待核实】 | 引用页 | 耗时 (s) |
| --- | --- | ---: | ---: | --- | ---: |
| 公司概况 | supported | 0 | 0 | 6, 7, 26, 88 | 32.4 |
| 主营业务 | supported | 0 | 0 | 23, 26, 153, 154 | 16.9 |
| 财务表现 | supported | 0 | 0 | 7, 8, 68 | 41.6 |
| 风险因素 | supported | 0 | 0 | 2, 30, 31, 167 | 41.6 |
| 结论 | supported | 0 | 0 | 23, 25, 29, 43 | 20.7 |

### 【待核实】原句（总计 0 处）

本次没有精确的【待核实】标记。

精确标记计数不代表所有事实已验证；正文可能仍有“待核验”和数据缺失陈述。

### 公司名称与注册地引用

- 公司中文名称为深圳市远望谷信息技术股份有限公司，中文简称为远望谷；外文名称为 Invengo Information Technology Co.，Ltd.，外文名称缩写为 Invengo [public-annual-report-2024.pdf p6]。

- 公司注册地址历史变更情况为不适用 [public-annual-report-2024.pdf p6]。

- 公司注册地址为深圳市南山区粤海街道高新南十道 63 号高新区联合总部大厦 27、28 楼，注册地址邮政编码为 518052 [public-annual-report-2024.pdf p6]。

### 内部词与任务 1 规则

calc_financials：0 次；写作上下文：0 次；销售净利率：0 次。

任务 1 选择删除自动守卫，仅保留写作提示。提示在每次章节写作/重写时传入；没有自动矛盾检测器，因此“是否触发守卫”为不适用，不能记录成守卫成功触发 0 次。无法仅凭 summary 判断模型是否逐条遵守提示；需人工结合引用片段核对。

## 截图、测试与人工确认

- 在同一代码提交运行 `python scripts/screenshots.py --skip-qa --pdf data/samples/public-annual-report-2024.pdf --report-port 8513`，重拍 report-preview / report-progress。
- 脚本生成真实 Streamlit 报告，UI 与 CLI 是独立模型运行；截图对应同一 HEAD，不冒充 CLI 的逐字输出。
- 测试命令：`python -m pytest -q -rs -p no:cacheprovider --basetemp=$env:LOCALAPPDATA\Temp\d2r-pytest-r10`。
- 本任务 185 passed / 11 skipped / 1 warning，10.27 s。跳过均为原生 Windows 无 Milvus Lite；warning 为既有 LangChain 弃用预告。
- 只读检查 `wsl --list --quiet` 返回需安装 WSL 的提示；本机没有可用于本轮复测的 Linux 环境，Linux 以评审复现为准，不复用旧 HEAD 的数字。
- 人工确认：作者用本次 DOCX 在本机打开并拍摄 Word 图；代理不生成此图、不打 tag。supported 不等于完整语义核验。
- 坑：截图脚本会独立重跑模型，输出可能不同；只记录各自实际观察。原有未跟踪 JSON 保留。
