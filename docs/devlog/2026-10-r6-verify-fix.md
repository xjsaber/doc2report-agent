# 第 6 轮 · 任务 1 [verify-fix]

## 这一步要解决什么
阻断 2：【待核实】误标。引用标记里的年份/页码、Markdown 标题与列表序号被当成数字；裸子串回退过宽；无数字句也被标待核实；比率缺少 calc_financials 重算路径。

## 我做了哪些决定
1. `strip_claim_noise`：抽数前去掉 `[file pN]`、【待核实】、`（据第 X 页数据计算）`、Markdown 标题/列表序号、`20XX年`、`第 N 页`。
2. 数字按数值比较：千分位、`元/万元/亿元` 换算到元；百分数按双方较粗精度四舍五入；**去掉** `n not in joined` 裸子串回退。
3. 无数字句（剥离噪声后）只要有证据即 `supported`。
4. 句含「（据第 X 页数据计算）」时走 `recalculate_ratio`（毛利率/同比/净利率/资产负债率）重算核对。
5. write 提示禁止心算比率；`_try_build_calc_context` 尽力从片段抽数调用 `calc_financials` 写入上下文。
6. 新增 `scripts/export_verify_debug.py`，对上轮 `output/e2e/report.md` 逐句导出 `output/verify-debug.json`（不入库）。

## 踩了什么坑
- 原文系统提示是「若**关键**数字…」，补丁误写成「相关」导致替换失败，已按原文对齐。
- 负号同比需在数字正则中捕获可选 `-`。

## 修前 / 修后（基于上轮实跑报告 + 新核验逻辑离线重放）
- 修前（第 5 轮实跑）：五章 `verification_status=mismatch`，全文大量【待核实】（见 `docs/devlog/2026-10-r5-e2e.md`）。
- 修后离线重放数字见笔记本跑 `python scripts/export_verify_debug.py` 的 summary（写入本段下方「实跑补充」）；完整 graph 重跑留到 [retrieve-fix]。

## 人工需要确认什么
- 计算句标记「（据第 X 页数据计算）」依赖模型遵从提示；若模型漏标，verify 仍按普通数字句处理。
- `_try_build_calc_context` 为尽力而为，抽不到两列金额时不注入比率。

## 运行环境
- 开发/单测：Linux box，Python 3.13（CI 式）；目标机原生 Windows 10，Python 3.12.10，torch 2.6.0+cu124，RTX 3050
- 测试：见本轮 commit 与 README
