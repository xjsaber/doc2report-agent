# 第 6 轮评审 v1（HEAD a773b08）

**结论：8.0 / 10。** r5 三个阻断里，示意截图和答非所问已基本解决，【待核实】误标的主体修好了；但新增的比率计算路径会把年份当营业收入，算出荒谬比率并被 verify 判为 supported，这是本轮唯一阻断，r7 必须先修。

## 复现

- 提交：615ecee [verify-fix] → 18fb5cf [retrieve-fix] → a773b08 [screens]
- Linux（Python 3.12，dev+milvus+qa，setuptools<81，milvus-lite 可用）：`142 passed, 0 skipped`。Windows 本机 131 passed / 11 skipped（Milvus Lite 不支持 win32），两边一致。
- 敏感信息：本轮改动文件未发现银行/金融/客户/单位名、密钥；未提交 PDF、.env、模型、output/、docx。
- 截图：四张均为 1440×900 真实 Streamlit 页面，有侧边栏、真实文件名与 185 页 / 1646 块，无本机用户名/路径/Key。

## 做得好的

1. **截图换成实拍**，scripts/screenshots.py 用 Playwright 驱动真实上传/入库/提问/生成；拒答页不再展示「命中原文」，answer_question 拒答时清空 citations，逻辑和 UI 一致。
2. **数值核验思路对了**：strip_claim_noise 去引用标记、标题序号、年份、页码；按数值比较并统一到元；去掉裸子串回退；无数字句只验引用。
3. **检索结构化**：drop_toc_pages + 标题块前向并入 + section_hints 先章节内再全局补。同份年报切块 2066→1646，端到端约 527s→358s，【待核实】从几乎全文降到 2 句（作者实测观察）。
4. embedding 缺模型不再静默联网，`--download-model` / `EMBEDDING_ALLOW_DOWNLOAD=1` 显式化，README 同步。
5. devlog 有修前/修后对照表，只写观察，没有编指标。

## 阻断项

### B1 比率计算路径会算出并"核验通过"错误比率

`core/graph/workflow.py::_try_build_calc_context` 和 `core/tools/verify_claim.py::recalculate_ratio` 的抽数都存在问题，在 Linux 上已复现：

```python
# 片段：'2024年 营业收入 2024年度 1,234,567,890.12' + '营业成本 987,654,321.00'
_try_build_calc_context(...)  # → 毛利率 = -48797050.25%（把 2024 当营业收入）
verify_calculated_sentence('毛利率为-48797050.25%（据第 13 页数据计算）…', 同上片段)  # → ('supported', None)
verify_calculated_sentence('毛利率为20.00%（据第 13 页数据计算）…', 同上片段)       # → ('mismatch', …)
```

具体问题：
- `label[^\d]{0,12}` 取标签后第一个数字，年份/「本期」列标题会被当金额；单位取数字后缀，年报实际写在表头「单位：元/万元」。
- 页码回查用 `match.group("num")`（带千分位）去匹配 `text.replace(",", "")`，带千分位的数一律查不到，页码回落成 **1**（`据第 1 页数据计算` 是错的引用）。
- `Source(file="context")` 不是真实文件名。
- `recalculate_ratio` 的标签过宽（「收入」「成本」「本期」），同比只取第一处数字，无法区分本期/上期列。
- 计算和核验共用同一类错误抽数，错误会互相"印证"——这正是最危险的形态。

修复方向：计算与核验共用一个结构化抽取函数（识别「主要会计数据和财务指标」表行：标签 + 本期 + 上期 + 同比，表头单位），排除 4 位年份与页码；页码、文件名取命中块真实值；比率做合理性检查（毛利率/净利率/资产负债率应在 -100%~100%，超出即不注入、不判 supported）；抽不到就不注入，宁缺勿错。

## 建议（非阻断）

1. **财务章节内容待确认**：report-preview 的「关注点」写着「本次检索片段未覆盖营收、毛利率、净利率、资产负债率等关键财务数据」，与「财务表现 supported」并存，说明结论章或财务章没拿到主要财务指标表。请在 devlog 贴财务表现章前 3 句和引用页，确认营业收入、净利润是否出现。
2. **审计套话被当关注点**：「审计师责任部分提及…可能导致不能持续经营」是审计报告标准措辞，不是公司风险。审计报告页（审计意见/审计师责任/关键审计事项的通用段）应在风险/结论章降权或排除。
3. **公司概况仍 mismatch**（引用 p13/p10/p90）：在 verify-debug 里看是哪句、哪个数字没对上，修掉或解释。
4. **截图时机**：qa-cited 和 report-preview 右上角仍显示 Stop（页面在 rerun），qa-cited 侧边栏多出一个半透明的「已入库文档」重影，且回答引用 p89/p28 而「命中原文」只显示 p19。screenshots.py 应等运行指示消失再截；report-preview 滚动到章节标题，避免顶部半行被裁。
5. **命中原文排序**：回答实际引用的片段放前面并标「已引用」，未引用的折叠在后。
6. **devlog 有控制字符**：2026-10-r6-screens.md 中 `answer_question`、`file_uploader`、`report-*`、```text 被 PowerShell 反引号转义吃掉（\x07、\x0c、\t 等）；verify-fix devlog 的「实跑补充」占位未填。写文件用 Python 或 `Set-Content -Encoding utf8` 并避免反引号转义。

## 下一轮（r7）

calc-fix（B1 + 建议 1~3）/ polish（建议 4~6）/ README 收尾与 v1 准备。Word 打开图在 r7 修完后用户本机补拍，v1 tag 放 r8。
