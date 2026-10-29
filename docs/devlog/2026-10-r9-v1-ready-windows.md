# 2026-10-r9 [v1-ready] Windows 收尾

## 环境

- 系统：原生 Windows 11（笔记本）
- Python：3.12.10（仓库 `.venv`）
- GPU：NVIDIA GeForce RTX 3050 Laptop GPU
- 相对 Linux `9b3af7e` 的收紧：**删除** `scripts/eval.py`（含最小版）与 `tests/test_eval.py`，文档写明评估挪到 v2。

## 决策

1. `.env.example` 默认 `RETRIEVER=memory`、win32 上 milvus→memory 回落：沿用已合入实现，本提交不改工厂逻辑。
2. **删掉** `scripts/eval.py` 与 `tests/test_eval.py`；不留 NotImplementedError，也不保留最小评估进 v1。
3. README：去掉「最小评估」整节与 `scripts/eval.py` 表述；`docs/images/word-open.png` 不存在时图片行保持 HTML 注释（**不生成、不放占位图**）。
4. ROADMAP「v1 交付计划」：评估项改为「挪到 v2」；v2 节补评估脚本/评估集；CHANGELOG v1.0.0 草稿同步去掉「已有最小 eval」。
5. **不打 tag。**

## 人工确认项

- 作者本机补拍 `docs/images/word-open.png` 后取消 README 注释。
- 确认后由作者打 `v1.0.0` tag（代理不打）。

## 测试（Windows 11 / Python 3.12.10）

```text
python -m pytest -q -rs -p no:cacheprovider --basetemp=C:\Temp\d2r-pytest-r9-t3b
185 passed, 11 skipped, 0 failed
```

11 skip = Milvus Lite 原生 Windows 不可用。相对删 eval 前少 2 条（原 `tests/test_eval.py`）。
