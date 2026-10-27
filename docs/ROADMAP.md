# ROADMAP

## v1（Demo，约 12 月）
- PyMuPDF 解析（MinerU 可选，未安装自动回退），保留页码
- 切块 + Milvus Lite 向量 + BM25 混合召回；检索通过 Retriever 接口（RETRIEVER=milvus）
- LangGraph：plan → retrieve → write → verify → assemble，强制引用 [文件名 p页码]
- 工具层 8 个工具（见 TOOLS_SPEC），统一返回结构，calc_financials 纯代码计算，verify_claim，MCP 暴露
- 模型：OpenAI 兼容接口，默认 MODEL=deepseek-flash（非思考模式），可配置
- Streamlit：报告生成页 + **独立的 RAG 知识库问答页**（上传/选文档 → 混合检索 → 带引用回答，不依赖报告流程，可单独启动演示）
- python-docx 导出、scripts/eval.py 评估、Docker 一键起、pytest

## v1 交付计划（2026-10-27 作者确认，目标 2026-11-14）
目标：可作为公开代表作品——公开年报 PDF → 带页码引用的 Word 报告，端到端可跑。
- 第 3 轮（约 10-30）：页眉页脚去噪；Retriever memory（Windows/测试默认）+ milvus；向量+BM25 RRF；search_chunks；**独立 RAG 问答页**。
- 第 4 轮（约 11-06）：LangGraph plan → retrieve → write → verify → assemble；calc_financials、verify_claim 等报告所需工具；强制引用。
- 第 5 轮（约 11-13）：python-docx 导出；Streamlit 报告生成页；README 完整化（安装、用法、架构图、运行截图）；最小评估脚本。
- v1 范围收缩，挪到 v2：MCP 暴露、Docker 一键启动、完整评估集；报告模板 v1 只做「年报分析」一种。
- 仓库只放截图（docs/images/），v1 阶段不放演示视频或 GIF。
- v1 完成后，把问答页拆成一个薄的独立小仓库（依赖本库 core），作为第二个可独立演示的作品。

## v2
- Elasticsearch 两级检索（chapters/items，BM25 + kNN + RRF）作为第二个 Retriever 实现
- FastAPI /tools 内部接口
- Spring Boot 3 / JDK 21 业务平台：登录角色、模板配置、任务、Word 导出（poi-tl）、审计，MySQL
- Vue3 + Element Plus 溯源报告页
- docker compose 一键起全套

## v3
- 私有化部署说明、失败兜底、方案对比（售前物料）
