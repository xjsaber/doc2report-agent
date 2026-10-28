# 2026-10 第 8 轮 · 任务 3：readme-v1prep（v1 交付前文档整理）

本任务只改文档，不改代码；不打 tag。

## 环境

- Windows：Windows 11 家庭版 中文版 10.0.26300，PowerShell 5.1，Python 3.12.10（.venv）；GPU 为 NVIDIA GeForce RTX 3050 Laptop GPU，torch 2.6.0+cu124，CUDA 可用。
- Linux：Debian GNU/Linux 13 (trixie)，内核 6.12，x86_64、8 核、无 GPU；Python 3.12.15 venv。
  - 安装了 `.[dev,qa,milvus]`：pymilvus 2.6.17、milvus-lite 2.5.1。
  - 测试使用 fake embedding，不需要模型权重。

## 改动

1. **README「快速开始」**：替换原来的「安装」和「启动」两节。
   - Windows（PowerShell）和 Linux / WSL / macOS 分开写：建 venv、安装 extras、复制 `.env`、`--download-model` 显式下载模型。
   - 加 `.env` 示例，Key 用占位符。
   - 三个入口的表：报告页、问答页、CLI，每个都给出 Windows 和 Linux 写法。
   - 加两种系统的 pytest 命令。
   - 说明样本 PDF 需自行下载，放到 `data/samples/`（gitignored）。
2. **README「已知局限」**：并入原「已知限制」一节，新增以下几条，均已对照当前代码确认：
   - 原生 Windows 下 `MilvusRetriever` 直接抛错（`core/index/milvus.py`）。`.env.example` 默认写的是 `RETRIEVER=milvus`，因此 README 明确提示 Windows 用户要改。
   - 不含数字的句子：`verify_claim` 在有证据时直接判为 supported，只校验引用本身。
   - `calc_financials` 只算四类比率：同比增速（营业收入、净利润）、毛利率、净利率、资产负债率。
   - 「分行业 / 分产品」表若以列标题排列，抽不出营业成本，因此可能没有毛利率。
   - `_NUMBER_RE` 只识别前导减号，括号负数不识别。
   - 写作模型偶尔把工具名写进正文。这一条来自任务 1 的实跑观察。
3. **README「测试结果」**：
   - Windows 和 Linux 两套环境的真实结果，Linux 一套包含 Milvus Lite 契约测试。
   - 附任务 1 的一次本机端到端实测（r8c，2026-10-28 23:35 UTC+8），注明环境，并说明不是基准。
4. **新增 `docs/core-api.md`**：如实记录当前状态，包括：
   - 解析与入库、检索、问答、配置几组函数的签名和返回结构；
   - `app/rag.py` 写死了 `get_retriever("memory")`；
   - `core/qa` 有 `__all__`，`core/index` 没有。
   - 没有为此改代码。
5. **ROADMAP**：在「v1 交付计划」下加完成情况表。
   - `scripts/eval.py` 仍是入口占位，如实标为「未完成」。
   - 拆独立问答小仓库标为「未开始」。
   - v1 tag 未打。

## 踩坑

- `.env.example` 写的是 `RETRIEVER=milvus`，而代码的平台默认值是 Windows 用 memory、其它用 milvus。复制模板后，`.env` 里的值会覆盖平台默认，Windows 首次运行就会报错。本轮只在 README 里提示，没有改 `.env.example`，是否改由作者决定。
- 第 8 轮中途中断过一次。续跑前先核对了 git 状态、origin、WIP 和 output，任务 1、2 没有重跑。
- 长耗时的截图和 CLI 都放到后台跑，日志写到 `output/*.log`。

## 需人工确认

- `scripts/eval.py` 未实现，是 v1 交付计划里唯一明确没完成的项。是否在打 v1 tag 前补上，请作者决定。
- 是否把 `.env.example` 的默认值改成 `RETRIEVER=memory`，或改为留空让平台默认生效。
- README 里的端到端耗时只是本机一次运行的结果。

## 测试

- Windows：`python -m pytest -q -rs -p no:cacheprovider --basetemp=$env:LOCALAPPDATA\Temp\d2r-pytest-r8g` → 174 passed, 11 skipped, 0 failed
- Linux：`python -m pytest -q -rs -p no:cacheprovider --basetemp=/tmp/d2r-pytest-r8-linux2` → 185 passed, 0 skipped, 0 failed
