补充需求：工具层（tools）设计，请在现有代码上加入，不要推翻已完成的模块。

一、目标
把智能体用到的能力封装成独立「工具」，统一注册、可单测、可被 LangGraph 节点调用，也可通过 MCP 对外暴露（Claude Desktop / Cursor 等可直接调用）。仓库中工具也是展示重点，README 单独一节介绍。

二、目录与规范
• core/tools/：每个工具一个文件；core/tools/registry.py 统一注册。
• 每个工具用 Pydantic 定义输入/输出模型，带 name、description（中英文）、版本号；函数纯 Python，无 UI 依赖。
• 统一返回结构：{ok: bool, data: ..., error: str|None, sources: [{file, page, chunk_id}]}。
• 每次调用记录日志：工具名、参数摘要、耗时、是否成功（供 eval.py 统计）。
• 不允许工具直接访问网络，除 download_samples 外。

三、工具清单（v1）
1. parse_document
   输入：file_path, engine("pymupdf"|"mineru", 默认 pymupdf)
   输出：doc_id, pages(页数), sections[{title, page_start, page_end}], tables[{table_id, page, caption}]
2. search_chunks
   输入：query, doc_ids(可选), top_k(默认 8), mode("hybrid"|"vector"|"bm25")
   输出：chunks[{chunk_id, text, file, page, score}]
3. get_table
   输入：doc_id, table_id 或 keyword（如「合并利润表」）
   输出：表头 + 行数据（二维数组）+ 页码；解析失败时返回原文片段
4. calc_financials
   输入：指标原值字典（营业收入、营业成本、净利润、经营活动现金流、总资产、总负债，当期与上期）
   输出：同比增速、毛利率、净利率、资产负债率、净现比；每个结果附计算公式与输入来源
   说明：纯计算、不调用大模型，避免模型算错数字
5. verify_claim
   输入：claim（一句含数字的结论）, source_chunk_ids
   输出：status("supported"|"not_found"|"mismatch"), evidence（原文片段）, 差异说明
6. render_section
   输入：section_name, template_id, facts[{text, sources}]
   输出：带 [文件名 p页码] 引用的 Markdown 段落
7. export_report
   输入：report_md, format("docx"|"md"), title
   输出：文件路径
8. list_templates / load_template
   输出：可用报告模板及其章节、问题、检索关键词

四、与流程的关系
• plan 节点：load_template
• retrieve 节点：search_chunks、get_table
• write 节点：calc_financials（先算数）→ render_section
• verify 节点：verify_claim，not_found/mismatch 的结论标「待核实」并重写一次
• assemble 节点：export_report

五、对外暴露
• mcp_server.py：用官方 Python MCP SDK 把以上工具暴露为 MCP tools（stdio 模式），README 给出 Claude Desktop 配置示例。
• 可选：FastAPI 的 /tools/{name} 接口，方便集成商接入自己系统。

六、测试与文档
• tests/tools/ 每个工具至少 1 个正例 + 1 个异常例；calc_financials 用手算数据核对。
• docs/tools.md：工具表（名称、用途、输入、输出、示例调用），由 registry 自动生成。
