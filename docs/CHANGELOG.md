# Changelog

本文件记录面向使用者的版本说明。版本号遵循 SemVer 意向；**tag 由作者打，代理不打 tag。**

## [v1.0.0] — 草稿（未打 tag）

### 已实现

- 公开年报 PDF → 带 `[文件名 p页码]` 引用的《年报分析》Markdown / Word（python-docx）
- 解析：PyMuPDF（MinerU 可选回退）、页眉页脚去噪、切块保留页码
- 检索：Retriever 接口；memory（默认）与 Milvus Lite；向量 + BM25 + RRF；`search_chunks`
- LangGraph：plan → retrieve → write → verify → assemble；失败章最多重写 1 次；【待核实】标记
- 工具：`calc_financials`（纯代码四类比率）、`verify_claim`、模板加载等（见 `docs/TOOLS_SPEC.md`）
- 净利率：优先合并净利润；仅能抽到归母时正文写明「归母净利润口径」；assemble 清理内部工具名
- Streamlit：报告生成页 + 独立 RAG 问答页
- 文档：README 快速开始（Windows/Linux）、已知局限、`docs/core-api.md`、开发日志与评审

### 已知局限

- 原生 Windows 无 Milvus Lite（默认 memory；误设 milvus 会回落）
- 「分行业/分产品」列表头表营业成本/毛利率抽取不完整（见 README）
- 括号会计负数不支持；核验对无数字句只查引用不查语义
- Word 打开截图需作者本机补拍 `docs/images/word-open.png`
- 未做：MCP 暴露、Docker 一键起、评估脚本/评估集、多模板、问答页拆仓（见 ROADMAP v2）
- 模型输出有随机性；效果数字只以本机 `--summary-json` 实测为准（评估脚本已挪到 v2）

### 不在本草稿内

- 不提交 PDF、`.env`、密钥、模型权重、`output/`、生成报告
- 不出现客户/本职单位名称作为项目背书
