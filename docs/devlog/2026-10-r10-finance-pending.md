# 2026-10-r10 [finance-pending]

## 环境

- 系统：Debian 13 Linux（Grok Bot box），非 Windows 笔记本
- Python：3.13（项目 `.venv`）
- GPU：无（CPU 本地 embedding + 云端写作模型）
- 样本：`data/samples/public-annual-report-2024.pdf`（gitignore，不提交）

## 目标

修 r9 重跑财务表现章三处【待核实】/误挂：净利率误绑同比%、毛利率列表头局限、资产负债率检索未覆盖。

## 三句处理

### 1. 净利率误挂「下降 0.95%」→ **误标已修**

- **原句摘要**：同段既有「归母净利润…下降 0.95%」又有「按归母净利润口径计算的净利率为 5.10%」；`notes=净利率 claimed 0.95% but recalculated 5.10%`，【待核实】挂在净利率句后。
- **根因**：`_extract_claimed_ratio` 取句内第一个百分比，把同比「下降 0.95%」当成净利率主张。
- **修复**：`verify_claim.py` 按比率种类优先匹配关键词（毛利率/净利率/资产负债率 先于 同比），并用 `_percent_near_span` 只绑定紧挨关键词的 `%`。
- **单测**：`test_net_margin_ignores_prior_yoy_decline_percent`（修前会 mismatch、修后 supported）；`test_yoy_percent_still_binds_when_no_net_margin_keyword`。
- **重跑**：财务章 `verification_status=supported`，`pending_marks=0`，notes 空；不再出现 0.95↔5.10 误标。

### 2. 毛利率【待核实】→ **合理保留**

- **原句摘要**：「整体毛利率及其同比变化【待核实】」（约 p18 列表头「分行业/分产品」表）。
- **决策**：v1 **不**扩列表头表抽取。页内虽可能有 41.51% 类纯文本，但稳定抽「营业成本」行仍依赖列表头能力；硬扩超出本轮范围。
- **处理**：README 已知局限写清「可能算不出毛利率；写作者可能标【待核实】；v1 不扩列表头表抽取」。本轮重跑写作者改为「检索片段未包含毛利率数据，暂无法列示」，未再打【待核实】——仍属证据不足下的合理省略，不是抽取器已修好。

### 3. 资产负债率【待核实】→ **误标/缺口已修（检索增强）**

- **原句摘要**：检索未覆盖合并资产负债表要点，资产负债率待核实。
- **诊断**：仅加 keywords/hints 不够——`合并资产负债表` 命中标题页 p67，而「资产总计 / 负债合计」在 p68–69，且 chunk 的 `section` 常为碎裂的 `0.00`，hybrid 很难排到合计行。
- **修复**：
  1. `templates/company_analysis.yaml` 财务章 keywords/section_hints 增加：资产负债率、资产总额、负债总额、合并资产负债表、资产总计、负债合计。
  2. retrieve：hints 单独二次检索并 `_merge_search_hits`。
  3. `_expand_balance_sheet_neighbor_chunks`：命中「合并资产负债表」后，从 `MemoryRetriever._chunks` 拉同文档后续页（默认 +0..+2）中含「资产总计/负债合计」的 chunk；`_prefer_hinted` 对正文含上述 metric token 的命中一并优先。
- **重跑观察**：财务章 `retrieved_pages` 含 67/68/69；正文写出「资产总计 2,699,505,021.46 元、负债合计 1,163,813,202.39 元 [p68]；资产负债率 43.11%（据第 68 页数据计算）」；该点不再【待核实】。

## 顺带

- `tests/test_relevance.py::test_filter_keeps_bm25_overlap_even_with_low_vector`：在默认 BGE query-instruction 前缀下 stub embedder 认不出裸查询，误放行无关 hit；测试内 `EMBED_QUERY_INSTRUCTION=""` 固定行为（与本轮财务无关，但阻塞全绿）。

## 验证

- pytest：`python -m pytest -q -rs -p no:cacheprovider --basetemp=<新临时目录>` → **198 passed, 0 skipped, 0 failed**
- e2e：`python -m core.graph.run --pdf data/samples/public-annual-report-2024.pdf --out-dir output/r10 --summary-json output/r10/run-summary.json`
  - 产物：`年报分析-20261029-090130.md` / `.docx`
  - `pending_marks_total=0`；总耗时约 **152.3s**（parse 17.6 + index 15.9 + graph 118.7）
  - 各章 verification_status 均为 `supported`；财务表现 notes=`[]`，pending_marks=0

## 观察

- 资产负债率数字来自合计行邻页扩展，不依赖列表头表抽取；与毛利率局限正交。
- 写作模型偶发仍可能在结论等章引入无证据数字（上一次中间跑曾出现结论 mismatch）；本轮最终跑结论亦 supported。
- 未打 tag；未生成 word-open 占位图；未提交 PDF / `.env` / output / docx。
