# ROADMAP

## v1（Demo，约 12 月）
- PyMuPDF 解析（MinerU 可选，未安装自动回退），保留页码
- 切块 + Milvus Lite 向量 + BM25 混合召回；检索通过 Retriever 接口（RETRIEVER=milvus）
- LangGraph：plan → retrieve → write → verify → assemble，强制引用 [文件名 p页码]
- 工具层 8 个工具（见 TOOLS_SPEC），统一返回结构，calc_financials 纯代码计算，verify_claim，MCP 暴露
- 模型：OpenAI 兼容接口，默认 MODEL=deepseek-flash（非思考模式），可配置
- Streamlit：报告生成页 + **独立的 RAG 知识库问答页**（上传/选文档 → 混合检索 → 带引用回答，不依赖报告流程，可单独启动演示）
- python-docx 导出、scripts/eval.py 评估、Docker 一键起、pytest

## v2
- Elasticsearch 两级检索（chapters/items，BM25 + kNN + RRF）作为第二个 Retriever 实现
- FastAPI /tools 内部接口
- Spring Boot 3 / JDK 21 业务平台：登录角色、模板配置、任务、Word 导出（poi-tl）、审计，MySQL
- Vue3 + Element Plus 溯源报告页
- docker compose 一键起全套

## v3
- 私有化部署说明、失败兜底、方案对比（售前物料）
