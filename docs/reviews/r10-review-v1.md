# 第 10 轮评审 v1（HEAD fa5dd47）

**结论：9.2 / 10，无阻断项，可以打 v1.0.0。** 打 tag 前只剩作者本机的发布动作：补拍 Word 打开图，并把版本号、发布日期补齐。

## 复现

- 提交：4a2562f [guard-generalize] → e42118c [final-run] → fa5dd47 [readme-final]，作者邮箱都是 noreply，未强推、未打 tag。
- Linux（Python 3.12，dev+milvus+qa，setuptools<81）：`197 passed, 0 skipped`；Windows 本机 186 passed / 11 skipped（Milvus Lite），186 + 11 = 197，一致。
- 仓库里没有 PDF、.env、docx、模型文件、output/；README、core、app 中没有单位或客户名。
- 截图：report-preview / report-progress 已在 4a2562f 上重拍，均为空闲态、真实页面。

## 对照 r10 提示词

| 项 | 结论 |
| --- | --- |
| 守卫处理 | 选了「v1 删除」：disclosure_guard.py 和 14 个专用测试已删；写作提示加了「含表格行时不得写未披露」，并有提示契约测试。删除理由写在 devlog，**ROADMAP v2 也已记录**（先建标注样本，只加待核实，不改写正文），CHANGELOG 已知局限同步。 |
| final-run devlog | **齐全**：命令、chunks 1646、各阶段耗时（87.6 / 77.6 / 178.8，总 344.5 s）、errors=[]、五章状态 / 重写 / 待核实 / 引用页、公司名称和注册地引 p6、内部词 0 次；「守卫触发」如实写成不适用。 |
| README 只留当前 HEAD | **是**：测试表只剩 Windows 186/11 和「Linux 以评审复现为准」；端到端只留 4a2562f 那次。 |
| C:\Users 路径 | **已清干净**，新增 `test_readme_and_docs_have_no_windows_user_paths`。Codex 顺手把 r9 评审里引用的用户名路径也改写了，我认可。 |
| CHANGELOG / ROADMAP | CHANGELOG 发布日期留空等作者确认；ROADMAP「v1 打 tag」写成「待作者补 Word 图并确认」。 |

## Word 打开图用哪个文件

`output/v1-final/年报分析-20261029-205134.docx`（final-run devlog 记录，生成于 4a2562f，和当前报告代码一致）。

## 做得好的

1. 删守卫的决定和理由都对：没有标注集时，与其上一个会误标的通用规则，不如先删掉，并把通用版的验收方式写进 v2。
2. 实跑、截图、README 都锚定同一个运行代码提交（4a2562f），并说明后续提交只改文档。
3. 「0 处【待核实】≠ 全部正确」「supported ≠ 语义正确」继续保持诚实表述。

## 阻断项

无。

## 发布前小项（作者本机，一次提交完成）

1. 用上面那个 docx 在 Word 里打开，截一张能看到「年报分析」标题、章节标题层级和若干 `[public-annual-report-2024.pdf pN]` 引用的图，保存为 `docs/images/word-open.png`（建议宽 1440 左右；不要露出本机用户名、其他文件或任务栏通知），并取消 README 第 17~19 行的注释。
2. `pyproject.toml` 的 `version = "0.1.0"` 改成 `1.0.0`。
3. CHANGELOG 填发布日期，ROADMAP「v1 打 tag」改成已完成。
4. 提交、推送后，由作者执行：`git tag -a v1.0.0 -m "v1.0.0"` 和 `git push origin v1.0.0`。

## v1.0.1 建议（不阻断）

- report-preview 截图里「公司概况 · 主营定位 / 整体经营情况」两小节写成了对检索片段的元叙述（「片段中与主营定位相关的可核验信息主要来自…」「暂不列示报告期营业收入…」），而同一份报告的财务章其实有这些数据。建议写作提示禁止在正文提「片段」这个词；概况章的经营数字复用财务章检索到的主要会计数据页（p7 / p13）。改完后重拍 report-preview。
- `app/rag.py` 写死 `get_retriever("memory")`（docs/core-api.md 已注明），拆问答仓前改成读 `RETRIEVER`。
