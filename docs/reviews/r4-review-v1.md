# 第 4 轮评审 v1（qa-fix / graph / tools）

- 评审对象：4837d4f [qa-fix]、6513239 [graph]、a24a449 [tools]、b4da239 [docs]
- 评审日期：2026-10-27
- 结论：**8.7 / 10，通过，带 1 个阻断项**（第 5 轮开工先修）

## 复现
- Linux，Python 3.12，装 dev + milvus extra（setuptools<81）+ langgraph 0.6.11：**118 passed, 2 skipped**（仅 export_report 占位）。作者 Windows 107/13 的差值就是 11 个 Milvus 平台 skip。
- 敏感信息：无 PDF、.env、docx、output/；无机构/客户名。实跑 PDF 留在本机 data/samples/，未提交。

## r3 阻断项复核
- 拒答门槛：已加（BM25 词重叠 或 余弦 ≥ MIN_VECTOR_SCORE，默认 0.35 标为待实测），全部不相关直接拒答不调模型。✅
- 引用：去掉自动追加；回答里每个 [文件 pN] 必须属于本次检索结果，编造页码/无引用拒绝展示；固定拒答句检测。四种情况有测试。✅
- setuptools<81、EMBED_QUERY_INSTRUCTION 已加。✅

## 做得好的
- LangGraph 五节点清楚，verify 失败只重写一次，第二次保留【待核实】，不会死循环。
- calc_financials 纯 Decimal，除零写 note；verify_claim 逐句查数字；工具都有 success/error 测试。
- CLI 无 Key 时退出码 4 + 明确提示；devlog 如实写「未调真实模型」「假 embedding」，没有编数字。

## 阻断项（第 5 轮先修）
1. **重写时把所有章节都重写了。** verify 后只要有一章 needs_verification，就回到 write_node，而 write_node 对每一章都重新调模型：已通过的章节被重新生成（内容可能变差、费用翻倍），新内容还会再进 verify，可能在 rewrite_count=0 的情况下又被打回一次。改为：回到 write 时只处理 needs_verification=True 的章节，其余原样保留；补测试「5 章里 1 章失败，只有这一章被重写，模型调用次数=6」。

## 建议（非阻断）
2. 相关性门槛太宽：年报里「公司」「年度」「报告期」几乎每块都有，只要问题里有这些词，BM25 重叠就恒为真。重叠判断前去掉停用词（内置一份小停用词表 + 文档频率 >50% 的词视为停用），并补一个「问年报里不存在的事」的拒答测试。
3. relevance 对命中片段重新算 embedding；MemoryRetriever 已存了向量，改为复用，真实 bge 在 CPU 上能省一次编码。
4. 实跑用的是假 embedding。185 页切出约 3240 块偏碎（平均每页 17 块），第 5 轮用真实 bge-small-zh 跑一次，记录切块数、入库耗时（CPU/GPU 各一次，若笔记本可用）；考虑合并过短块。
5. langgraph 锁在 <1；1.x 已发布，v1 先不升，ROADMAP v2 记一笔。
6. 真实模型完整跑（write/verify）仍是空白——作者配好 .env 后第 5 轮必跑，结果只写观察：每章是否有引用、【待核实】大概出现在哪些章节、总耗时。
