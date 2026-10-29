# 2026-10-r9 [pending-audit]

## 环境

- 系统：Debian 13 Linux（Grok Bot box），非 Windows 笔记本
- Python：3.13（`.venv`）
- GPU：无（嵌入走 CPU）
- 样本：`data/samples/public-annual-report-2024.pdf`（公开年报，已 gitignore）
- **归因来源说明：非原笔记本 `output/r8c`（该目录未入库且笔记本离线）。本轮基于第 8 轮遗留产物 `/workspace/r8/r8c.md` + `/workspace/r8/r8cvd.json` + `/workspace/r8/r8csum.json` 做逐句归因；代码修复用单测回归，端到端重跑放在 [content-fix]。**

## 决策

1. 【待核实】5 句按「证据确实不足（合理）」/「误标（要修）」分类；误标修写作提示 + assemble 清理，并补单测。
2. 写作正文禁止 `calc_financials`、「写作上下文」；assemble 前 `sanitize_internal_terms` 再扫一遍，命中则替换/删除并写入 `errors`。
3. 净利率：抽取优先「合并净利润」→ 裸「净利润」→ 归母口径；归母时 calc 上下文写「净利率（归母净利润口径）」；禁止「销售净利率」。裸「净利润」匹配时拒绝「归属于…」前缀，避免吃进归母行。
4. 毛利率列表头表抽取仍属已知局限（v2），本轮不扩抽取器。

## 5 句【待核实】归因表（基于 r8 遗留 r8c，非本机重跑报告）

| # | 章节 | 原句（摘要） | 引用页 | 抽到的数字 / 核验 | 原因 | 分类 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 主营业务 | 主要产品/服务构成【待核实】 | p154（邻近句还引 p18） | 无产品名数字；verify 未对无数字句建行 | 本章检索命中多为扣除表/勾选表，未拿到产品名片段 | **合理** |
| 2 | 主营业务 | 分部收入结构【待核实】；并称 p18 无分行业/分地区明细 | p18 | 声称「未包含」但同页实际有分行业/分产品/分地区 | 写作者在已引用页上误判「未披露」 | **误标（提示层）**；本轮以写作禁令+后续检索增强缓解，不改抽取器 |
| 3 | 财务表现 | 「写作上下文 calc_financials 给出净利率为5.10%【待核实】」 | p13、p71 | claim `5.10%`；status=**mismatch**（证据有营收/归母净利润，但句中还夹了页码数字 13/71 且含内部词） | 内部工具名进正文 + 把计算句标待核实 | **误标（已修）** |
| 4 | 财务表现 | 毛利率相关结论【待核实】；前文已写物联网业营收/成本 | p18 | 营收/成本数字 **supported**；同页证据预览可见 `41.51%` 毛利率，但列表头表抽取仍是已知局限 | 写作者自标待核实；与 README 已知局限一致 | **合理（已知局限）** |
| 5 | 财务表现 | 全年经营现金流净额及资产负债率相关分析【待核实】 | p8（分季度） | 分季度现金流数字在证据中；缺全年与资产负债率 | 检索未覆盖全年现金流/资产负债表 | **合理** |

补充（无【待核实】但 verify debug 为 not_found）：公司概况「报告期净利率约为 5.10%（据第 13 页数据计算）」——无 `[file pN]` 标记且 evidence 空，status=not_found。与 #3 同源计算；本轮要求归母口径写明且禁止内部词后，写作者应带引用重写该类句。

## 代码改动

- `core/tools/financial_extract.py`：净利润标签优先级；`归属于` 前缀拒绝；`is_parent_attributable_profit_label`；按标签优先跨 chunk 选取。
- `core/graph/workflow.py`：calc 上下文去掉工具名、归母口径标注；写作 system 禁内部词/销售净利率；`sanitize_internal_terms`；assemble 调用。
- 测试：`test_prefer_consolidated_net_profit_over_parent_attributable`、`test_calc_context_annotates_parent_attributable_net_margin`、`test_sanitize_internal_terms_strips_tool_names`、`test_assemble_sanitizes_internal_terms`、`test_write_prompt_forbids_internal_terms_and_sales_net_margin`。

## 坑

- 裸标签「净利润」会匹配到「归属于母公司所有者的净利润」子串；必须在 `_prefix_rejected` 里检测「归属于」出现在 match 之前（endswith 不够，因为前面还有「母公司所有者的」）。
- `is_parent_attributable_profit_label` 不能用 `compact in full_label`，否则裸「净利润」会被误判为归母。

## 人工确认项

- 报告正文人工通读（归母口径表述是否自然）仍建议作者在 Word 里过一眼。
- Windows 截图 / win32 实测本轮在 box 上无法补；留给笔记本开机后。

## 测试

```text
python -m pytest -q -rs -p no:cacheprovider --basetemp=/tmp/d2r-pytest-r9-t1
190 passed, 0 skipped, 0 failed
```
