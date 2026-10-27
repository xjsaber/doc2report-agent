# 第 5 轮 · 任务 1 [graph-fix]

## 这一步要解决什么
r4 评审阻断项：verify 回写时 `write_node` 会把已通过章节全部重生成；建议 2/3：BM25 重叠前去停用词、relevance 复用 Retriever 已存向量。

## 我做了哪些决定
1. `write_node`：已有 markdown 且 `needs_verification=False` 的章节直接跳过；首轮 markdown 为空时仍写全部章节。补测试要求 5 章里 1 章失败时模型调用次数 = 6。
2. `core/index/relevance.py`：内置小停用词表，并按候选片段文档频率 >50% 动态加停用词；`has_bm25_overlap` 只比非停用词。
3. `MemoryRetriever.get_stored_vectors` + `filter_relevant_hits(hit_vectors=...)`：有存量向量时只对查询做 embedding；缺失时才回退重算。
4. 补「问年报里不存在的事」拒答测试（假 embedding，不下载模型）。

## 踩了什么坑
- 本机 `%TEMP%\pytest-of-*` 拒绝访问，pytest 改用 `--basetemp=.tmp/pytest/basetemp`。
- git https 连 GitHub 偶发 Connection reset；本任务 commit 后按可用通道 push。

## 人工需要确认什么
- `MIN_VECTOR_SCORE=0.35` 仍待真实年报调参。
- 停用词表偏年报口吻，其他文体可能过杀；v2 可外置配置。

## 运行环境
- 系统：原生 Windows 10
- Python：3.12.10（仓库 `.venv`）
- GPU：本任务测试用假 embedding，未加载 bge，未用 GPU
- 测试：`python -m pytest -q -rs --basetemp=.tmp/pytest/basetemp` → **111 passed, 13 skipped, 0 failed**
