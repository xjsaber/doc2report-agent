# 2026-10-r9 [content-fix]

## 环境

- 系统：Debian 13 Linux（Grok Bot box）
- Python：3.13（`.venv`）
- GPU：无（嵌入 CPU）
- 样本：`data/samples/public-annual-report-2024.pdf`（公开年报）
- **本机重跑，非原笔记本 output/r8c。**

## 决策

1. 模板「公司概况」`keywords` / `section_hints` 增加「公司信息」「注册地址」「股票简称」。
2. 同一公开年报端到端 CLI 重跑，只记观察，不编效果数字。
3. 报告内容相对 r8 截图已变（公司概况现有名称/注册地），但 box 未装 playwright，**未重拍** report-preview / report-progress（不做示意截图）。

## 端到端观察（output/r9）

命令：

```bash
python -m core.graph.run --pdf data/samples/public-annual-report-2024.pdf \
  --out-dir output/r9 --summary-json output/r9/run-summary.json --download-model
```

- chunks：1646
- 耗时：parse 17.8s / index 14.6s / graph 132.1s / **total 164.5s**
- docx：`output/r9/年报分析-20261029-083533.docx`（不入库）
- md：`output/r9/年报分析-20261029-083533.md`
- `pending_marks_total`：**3**（r8c 为 5）
- `errors`：[]
- 正文未出现 `calc_financials` / 「写作上下文」 / 「销售净利率」；财务章出现「归母净利润口径」。

### 每章核验状态

| 章 | status | rewrite | 【待核实】 | cited_pages | retrieved_pages | elapsed_s |
| --- | --- | ---: | ---: | --- | --- | ---: |
| 公司概况 | supported | 0 | 0 | 6, 88 | 6, 9, 26, 33, 88, 169 | 13.9 |
| 主营业务 | supported | 0 | 0 | 18, 19, 153, 154 | 18, 19, 153, 154 | 13.2 |
| 财务表现 | mismatch | 1 | 3 | 8, 13, 18, 72 | 8, 13, 18, 71, 72, 153 | 55.7 |
| 风险因素 | supported | 0 | 0 | 2, 30, 167 | 2, 30, 167 | 35.3 |
| 结论 | supported | 0 | 0 | 13, 27, 51, 90, 153 | 13, 27, 51, 90, 153 | 12.0 |

财务表现 notes：`净利率 claimed 0.95% but recalculated 5.10%`——同句含「下降 0.95%」与「净利率 5.10%」，核验器把 0.95% 误当成净利率主张后打了【待核实】（观察，本轮未改核验器）。

### 【待核实】原句（3）

1. 「…按归母净利润口径计算的净利率为 5.10%…【待核实】」（接在正确净利率句后，疑为上述误标残留）
2. 「…整体毛利率及其同比变化【待核实】」（p18；与已知列表头表局限一致）
3. 「…资产负债结构及资产负债率相关要点【待核实】」（检索未覆盖资产负债）

### 公司概况是否出现公司名称 / 注册地

- **有。** 股票简称「远望谷」、中文名称「深圳市远望谷信息技术股份有限公司」、注册地址「深圳市南山区粤海街道高新南十道63号…」等，引用 **p6、p88**（retrieved 含 p6）。
- r8c 当时写「检索片段中没有提供」工商信息；本轮 hints 生效后已能写出。

## 截图

未重拍。原因：box 无 `playwright` 包；按规则不做示意截图。现有 `docs/images/report-*.png` 仍为 r8 画面，与本轮公司概况正文不一致——待 Windows 笔记本补拍。

## 测试

```text
python -m pytest -q -rs -p no:cacheprovider --basetemp=/tmp/d2r-pytest-r9-t2
```

191 passed, 0 skipped, 0 failed
