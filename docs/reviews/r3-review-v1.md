# 第 3 轮评审 v1（index / retrieval / qa）

- 评审对象：401ab56 [index]、9578acb [retrieval]、a46cc60 [qa]
- 评审日期：2026-10-27
- 结论：**8.6 / 10，通过，带 2 个阻断项**（第 4 轮开工先修）

## 复现
- Linux（Python 3.12）`pip install -e ".[dev]"` 后 `python -m pytest -q -rs`：**84 passed, 26 skipped**，与提交信息一致。
- Linux 安装 milvus extra 后跑 `tests/test_retrieval.py`：**24 passed**（memory 与 milvus 同一组契约全部通过）。前提是 `setuptools<81`，见问题 3。
- 跳过项：14 个工具业务占位 + 1 个引用校验占位（第 4 轮实现），其余为 milvus extra 未装。
- 敏感信息自查：无 PDF、.env、docx、模型文件；无机构/客户名；Key 只从环境变量 / .env 读取。

## 做得好的
- 去噪只删连续的边缘行，正文中同样文字保留；页码归一化只针对独立页码行。保守、有回归测试。
- RRF 用完整过滤后排名再截断，k=60，排名从 1 开始，同分按 chunk_id 稳定排序；三种模式都有中文测试。
- 本地 embedding 懒加载、`local_files_only=True`，检索时不偷偷联网；CUDA/CPU/EMBED_DEVICE 分支都测了。
- 问答页业务逻辑在 core/qa，Streamlit 只做界面；无 Key 时只展示检索结果。开发日志写清了低置信项，没有编数字。

## 阻断项（第 4 轮先修）
1. **拒答实际不会触发。** 混合检索只要库里有片段，就总会返回 top_k 条，`if not citations` 几乎走不到。需要相关性门槛：
   - BM25 分支：查询分词与片段无任何重叠（BM25 分=0）视为不相关；
   - 向量分支：余弦低于 `MIN_VECTOR_SCORE`（可配，默认 0.35，写明是待实测的经验值）视为不相关；
   - 两路都不相关的片段不进入上下文；全部不相关 → 拒答，不调模型。
   - 同时让模型在资料不足时输出固定句「资料中未找到依据」，检测到该句即 `refused=True`，且不追加引用。
2. **自动补引用掩盖了无引用回答。** `_ensure_citation_markers` 会把所有没被引用的检索标签追加到末尾，于是「缺少引用 → 拒绝展示」的检查永远通过，拒答句也会被挂上引用。改为：
   - 不再自动追加；
   - 解析回答里的 `[文件 pN]`，必须全部属于本次检索结果，出现不在结果里的文件/页码 → 标为无效引用并拒绝展示（或删掉该句并提示）；
   - 回答没有任何有效引用 → 拒绝展示；
   - 补测试：模型编造页码、模型不带引用、模型自己拒答、全部片段不相关四种情况。

## 建议（非阻断）
3. milvus extra 加 `setuptools<81`（milvus-lite 2.5 仍 import pkg_resources，新 setuptools 已移除，Linux 实测缺它直接 ImportError）。
4. bge-small-zh-v1.5 官方建议短查询加检索指令前缀（「为这个句子生成表示以用于检索相关文章：」），做成配置项 `EMBED_QUERY_INSTRUCTION`，查询加、文档不加。
5. MemoryRetriever 每次查询都重建 BM25，单份年报可接受；在 index_chunks 时缓存 tokenized corpus，按 doc_ids 过滤时再建。
6. 问答页：同一文件重复入库应提示已存在（按 doc_id）；入库时显示进度。
7. 仍未验证：真实年报去噪效果、真实 embedding 召回、真实 DeepSeek 调用——第 4 轮用一份公开年报手动跑一次，结果写进 devlog（只写观察，不写无依据的指标）。
