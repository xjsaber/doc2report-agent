你是资深 Python/AI 工程师。请从零新建一个开源仓库 doc2report-agent（MIT 许可），实现一个「文档 → 报告」生成智能体 Demo。所有代码、提示词、示例数据都必须原创，基于公开资料。

一、场景
用户上传 1–3 份上市公司年报 PDF（来自巨潮资讯网等公开来源），系统按可配置的报告模板，自动生成一份《企业经营分析报告》初稿，每个结论都标注出处（文件名 + 页码），可导出 Word。

二、功能（v1 范围）
1. 文档解析：默认 PyMuPDF 抽取文字和表格；可选 MinerU（配置开关，未安装时自动回退）。保留页码。
2. 切块与索引：按标题/段落切块（500–800 字，带重叠），向量库用 Milvus Lite（pymilvus 本地文件模式），同时做 BM25 关键词检索，混合召回 + 简单重排。
3. 报告模板：templates/company_analysis.yaml，章节含：公司概况、主营业务与收入结构、财务表现（营收/净利润/毛利率/现金流）、主要风险、结论与关注点。每章写明要回答的问题和检索关键词。用户可新增模板。
4. 智能体流程用 LangGraph：plan（按模板拆章节问题）→ retrieve（混合检索）→ write（逐章生成，强制引用 [文件名 p页码]）→ verify（检查每段是否有引用、数字是否能在原文片段中找到，找不到则标「待核实」并重写一次）→ assemble（合并为完整报告）。
5. 大模型：OpenAI 兼容接口，通过 .env 配置 BASE_URL / API_KEY / MODEL，默认适配 DeepSeek；Embedding 同样可配置，并提供本地 bge-small-zh 回退。
6. 界面：Streamlit 单页：上传 PDF → 选模板 → 生成（显示每章进度）→ 预览报告（引用可展开查看原文片段）→ 下载 .docx 和 .md。
7. 导出：python-docx 生成 Word，含标题、目录、章节、引用脚注。
8. 评估：scripts/eval.py 输出引用覆盖率、「待核实」数字占比、每章耗时与 token 用量。

三、工程要求
- Python 3.11，目录：app/（streamlit）、core/（parse、index、graph、export）、templates/、scripts/、tests/。
- scripts/download_samples.py：从巨潮资讯网下载 2 份公开年报到 data/samples/（PDF 不提交到仓库，.gitignore 掉）。
- 提供 Dockerfile 和 docker-compose.yml，一条命令启动。
- pytest 覆盖切块、检索、引用校验三个模块。
- 代码有类型标注和简洁注释，日志清晰。

四、README（中文为主，附英文简介）
包含：一句话说明、架构图（mermaid）、效果截图占位、快速开始（3 步）、配置说明、如何新增模板、评估指标、局限与后续计划（多文档对比、表格问答、权限与私有化部署），以及「本项目基于公开数据，与任何机构的内部系统无关」声明。

五、交付顺序
先给目录结构和关键模块接口，确认后再分模块实现；每完成一个模块运行测试。v1 不做登录、多用户、数据库持久化。
