# AGENTS.md（给 Codex 的开发约定）

## 红线
- 只用巨潮资讯网等公开年报和原创代码、提示词、样例；不引用任何机构的内部代码、模板、提示词或数据。
- 不提交 .env、API key、PDF、向量库文件、导出的 docx（见 .gitignore）。提交前 `git status` 自查，并搜一遍代码里是否有 key。

## 需求来源
1. docs/CODEX_PROMPT.md：v1 功能与工程要求
2. docs/TOOLS_SPEC.md：8 个工具与统一返回结构
3. docs/ROADMAP.md：分期；以下补充优先于 CODEX_PROMPT：
   - 检索层在 core/index 定义 Retriever 接口（index_chunks、search(query, doc_ids, top_k, mode)），Milvus Lite + BM25 为默认实现，search_chunks 工具只依赖接口；v2 加 ES 实现，本期不做。
   - 默认 MODEL=deepseek-flash，关闭思考模式。
   - Streamlit 增加独立的 RAG 知识库问答页，可单独启动。

## 开工流程
1. 第一次：先提交目录结构、关键模块接口和空测试（不实现细节），push 后等评审。
2. 之后每轮最多做 2 个模块，每个模块完成后跑 pytest，README 记录测试结果和未验证项。
3. 每轮结束 push 到 main（或开 PR），提交信息格式：`[模块] 简述`。
