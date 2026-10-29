# 2026-10-r9 [content-fix] Windows 观察

## 环境

- 系统：原生 Windows 11（笔记本）
- Python：3.12.10（仓库 `.venv`）
- GPU：NVIDIA GeForce RTX 3050 Laptop GPU（嵌入 CUDA）
- 样本：`data/samples/public-annual-report-2024.pdf`（公开年报，已 gitignore）
- 代码基线：已合入 `30c7554` [content-fix]（模板 keywords/section_hints）+ `822d64f` [r10]；本提交补 **Windows 端到端重跑观察** 与截图核对，不重复改模板。

## 决策

1. 模板「公司概况」hints（公司信息 / 注册地址 / 股票简称）沿用已合入版本，本机不重写。
2. 同一公开年报在本机 CLI 重跑，只记观察。
3. 报告正文相对 r8 截图已变（公司概况现有名称/注册地），按规则重拍 `report-preview` / `report-progress`（不做示意截图；真实 Streamlit）。

## 端到端观察（output/r9w）

命令：

```text
python -m core.graph.run --pdf data/samples/public-annual-report-2024.pdf --out-dir output/r9w --summary-json output/r9w/run-summary.json --download-model
```

- chunks：1646
- 耗时：parse 82.3s / index 95.8s / graph 163.6s / **total 342.0s**
- docx：`output/r9w/年报分析-20261029-122253.docx`（不入库）
- md：`output/r9w/年报分析-20261029-122253.md`
- `pending_marks_total`：**2**（r8c 为 5；Linux r9 为 3）
- `errors`：[]
- 正文未出现 `calc_financials` / 「写作上下文」 / 「销售净利率」；财务章有「归母」相关表述。
- `.env` 中 `RETRIEVER=milvus`，win32 工厂回落 memory（与 [v1-ready] 行为一致）。

### 每章核验状态

| 章 | status | rewrite | 【待核实】 | cited_pages | retrieved_pages | elapsed_s |
| --- | --- | ---: | ---: | --- | --- | ---: |
| 公司概况 | supported | 0 | 0 | 6, 7, 26, 88 | 6, 7, 26, 33, 87, 88 | 20.2 |
| 主营业务 | supported | 0 | 0 | 23, 26, 64, 153, 154 | 9, 23, 26, 64, 153, 154 | 17.6 |
| 财务表现 | supported | 0 | 0 | 7, 8, 68 | 7, 8, 67, 68, 69, 92 | 34.1 |
| 风险因素 | supported | 0 | 0 | 2, 30, 31, 167 | 2, 27, 30, 31, 167 | 26.9 |
| 结论 | supported | 1 | 2 | 23, 25, 29, 43 | 9, 23, 25, 29, 43 | 44.7 |

### 【待核实】原句（2，均在结论）

1. 「资产构成重大变动情况在检索片段中仅呈现标题…【待核实】」（p23）
2. 「培训计划的具体实施成效…未在检索片段中披露【待核实】」（p43）

### 公司概况是否出现公司名称 / 注册地

- **有。** 中文名称「深圳市远望谷信息技术股份有限公司」、股票简称「远望谷」、注册地址「深圳市南山区粤海街道高新南十道 63 号…」，引用 **p6、p88**（retrieved 含 p6）。
- r8c 当时写「检索片段中没有提供」工商信息；hints 生效后本机亦能写出。

## 截图

- 已重拍并入库：`docs/images/report-preview.png`（242800 B）、`report-progress.png`（120618 B）。
- 命令：`python scripts/screenshots.py --skip-qa --pdf data/samples/public-annual-report-2024.pdf`
- 时间戳（Asia/Shanghai）：2026-10-29 12:29:17 / 12:29:19。真实 Streamlit，无示意占位图。

## 人工确认项

- 作者通读 Word：`output/r9w/年报分析-20261029-122253.docx`
- Word 打开图 `docs/images/word-open.png` 仍由作者本机拍（代理不生成）。

## 测试（Windows 11 / Python 3.12.10）

复用本轮 [pending-audit] 本机结果（代码未再改检索/写作逻辑）：

```text
187 passed, 11 skipped, 0 failed
```

（content-fix 提交前若再跑一遍，以 commit message 为准。）
