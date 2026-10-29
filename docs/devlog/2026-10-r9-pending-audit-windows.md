# 2026-10-r9 [pending-audit] Windows 观察

## 环境

- 系统：原生 Windows 11（笔记本 machine）
- Python：3.12.10（仓库 .venv）
- GPU：NVIDIA GeForce RTX 3050 Laptop GPU（torch CUDA 可用；本轮归因/pytest 不跑嵌入）
- 样本归因对象：**本机** output/r8c/年报分析-20261028-233544.md + output/r8c/verify-debug.json + 
un-summary.json（与 Linux box 第 9 轮所用 r8 遗留产物不同）
- 代码基线：已合入 6e2afc5 [pending-audit] + 822d64f [r10]；本提交只补 Windows 侧归因记录与实测，不重复改抽取/写作逻辑。

## 决策

1. 对笔记本真实 r8c 报告的 5 句【待核实】做逐句归因，分成「证据确实不足（合理）」与「误标（要修）」；误标对应的代码修复已在 6e2afc5/822d64f，本机以单测回归确认。
2. 不回退 r10 对净利率误绑同比%、资产负债邻页扩展的修复。
3. README 原生 Windows 实测更新为第 9 轮本机 pytest（187 passed / 11 skipped）。

## 5 句【待核实】归因表（本机 output/r8c）

| # | 章节 | 原句（摘要） | 引用页 | 抽到的数字 / 核验 | 原因 | 分类 | 处理 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 主营业务 | 主要产品/服务构成【待核实】；仅能确认营业收入扣除表「主营业务收入」 | p154 | 无产品名数字；verify-debug 未对该无数字句建 pending 行 | 本章检索多为扣除表，未拿到产品名片段 | **合理** | 保持【待核实】；检索增强见 content-fix |
| 2 | 主营业务 | 称 p18「未包含」分部/分行业/分地区明细；分部收入结构【待核实】 | p18 | 同页实际有分行业/分产品表（verify 证据预览可见物联网营收行） | 写作者在已引用页上误判「未披露」 | **误标（提示层）** | 写作禁令+公司/财务检索增强已合入；不改抽取器 |
| 3 | 财务表现 | 「写作上下文 calc_financials 给出净利率为5.10%【待核实】」（据第13、71页） | p13、p71 | claim 5.10%；status=**mismatch**（claim_numbers 还夹了页码 13/71；证据含营收/归母净利润） | 内部工具名进正文 + 计算句被标待核实 | **误标（已修）** | sanitize_internal_terms + 写作禁内部词；归母口径标注；单测覆盖 |
| 4 | 财务表现 | 物联网业营收/成本已写，毛利率相关结论【待核实】 | p18 | 营收/成本 **supported**；同页可见毛利率但列表头表抽取仍是已知局限 | 写作者自标待核实 | **合理（已知局限）** | 保持；毛利率列表头表抽到 v2 |
| 5 | 财务表现 | 全年经营现金流净额及资产负债率相关分析【待核实】 | （句内无页码；上文多引分季度 p8） | 缺全年与资产负债率完整证据 | 检索覆盖不足 | **合理** | r10 已扩资产负债邻页；端到端观察见 content-fix |

补充：erify-debug.json 汇总 sentences=20 / supported=18 / mismatch=1 / not_found=1 / had_pending_mark=2（仅 #3、#4 建成带 pending 标记的核验行；#1/#2/#5 为无数字或未建行的正文自标）。

## 代码确认（已合入，本提交无再改）

- sanitize_internal_terms：本机抽查「写作上下文 calc_financials 给出净利率为5.10%」→ 去掉内部词。
- 净利率归母口径、禁止「销售净利率」、assemble 前再扫：见 core/graph/workflow.py + 既有单测。

## 坑

- PowerShell 下 git rev-parse @{u} 需写成 '@{u}'，否则被解析成哈希字面量。
- GitHub HTTPS 偶发连不上时，若 origin/main 对象已在本地，可用 git merge --ff-only origin/main 对齐，稍后再 push。

## 人工确认项

- Word 正文通读（归母口径表述）仍建议作者过一眼。
- 端到端重跑与截图放在同轮 [content-fix]。

## 测试（Windows 11 / Python 3.12.10）

`	ext
python -m pytest -q -rs -p no:cacheprovider --basetemp=C:\Temp\d2r-pytest-r9-t1
187 passed, 11 skipped, 0 failed
`

11 skip = Milvus Lite 原生 Windows 不可用契约测试。
