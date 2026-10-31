# 2026-10 v1 发布前收尾（release-prep）

## 改动
- `pyproject.toml` 与 `core/models.py` 中 `ToolMetadata.version` 默认值：0.1.0 → 1.0.0（全仓库仅此两处写死版本号；评审文档中的历史引用保留不改）。
- README 取消 Word 打开图注释，注明生成自 `output/v1-final` 的最终 docx，运行代码提交 `4a2562f`；已知局限同步改写。
- CHANGELOG v1.0.0 去掉「草稿（未打 tag）」，发布日期 2026-10-31；删除「Word 打开截图需作者补拍」。
- ROADMAP「v1 打 tag」→「已完成（作者打 v1.0.0）」。
- docs 卫生测试新增：README 引用的 `docs/images/*.png` 都必须存在。

## 人工确认项
- `docs/images/word-open.png` 为**示意图**，由 Grok Build 图像工具生成（1280×720），经作者 2026-10-31 / 11-01 明确确认使用；不是本机 Word 真实打开截图。图中无本机用户名、无用户路径、无具体财务数字、无单位或客户名称。
- tag `v1.0.0` 经作者授权由代理执行。

## 坑
- 台式机 `.venv` 缺 numpy / langgraph / python-docx 等，重新 `pip install -e ".[dev,qa]"` 后恢复；embedding extra（体积大）未在本次重装。
- 首次装依赖途中台式机掉线，上线后续做。

## 测试
- 命令：`python -m pytest -q -rs -p no:cacheprovider --basetemp=$env:LOCALAPPDATA\Temp\d2r-pytest-release`
- 结果：187 passed, 11 skipped（11 项为 Milvus Lite 在原生 Windows 跳过），1 项依赖弃用预告。

## 环境
- Windows 11、Python 3.11.5（.venv）、RTX 3050 Laptop GPU（本次测试不用 GPU）。
