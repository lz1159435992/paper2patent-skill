---
name: paper2patent
description: Draft and revise Chinese invention patent text from academic papers, audit claims, and generate traceable monochrome patent diagrams. Use for paper-to-patent conversion, patent draft revision, claim checking, patent figure generation, or exporting the bundled original prompts.
---

# Paper2patent

将论文已披露的技术方案组织为中国发明专利草稿、权项审查结果或黑白附图。先按请求选模式，再读取该模式的规范。

## 模式与必读文件

| 请求 | 输入基础 | 必读规范 |
| --- | --- | --- |
| Flash / Pro 完整转换 | 标题、摘要、完整核心方法；全文优先 | [input-pack.md](references/input-pack.md)、[patent-writing.md](references/patent-writing.md)、[evidence-mapping.md](references/evidence-mapping.md) |
| 草稿修订 | 草稿与修改目标；核验技术内容需要来源材料 | 上述三份规范，仅执行所请求的修订 |
| 权项检查 | 权项文本；说明书用于支持性核查 | [patent-writing.md](references/patent-writing.md)、[claim-rules.json](references/claim-rules.json) |
| 附图规划、生成或修订 | 已有权项、说明书及附图说明；论文可选 | [figure-generation.md](references/figure-generation.md)、[evidence-mapping.md](references/evidence-mapping.md) |
| 导出原 prompt 或比较 README | 无需论文 | 对应原版参考文件 |

完整转换未指定深度时用 Pro；Flash 缩减篇幅和可选材料，不降低来源核验、清晰性和必要技术特征要求。单项任务按请求处理，不自动扩成五部分文件。

## 执行顺序

1. **核验材料。** 按模式清点输入，记录来源位置、缺口及草稿中未核验的内容。PDF 核对双栏顺序、方法、公式和原图；扫描件先 OCR，再回看关键页面。方法缺失时完成有依据的部分并说明需要的材料。
2. **建立对应。** 提炼区别点、技术问题、技术方案与技术效果；按证据规范映射到来源、权项、实施方式和附图。定义算法实现或参数的必要公式予以保留。
3. **起草或生成。** 按当前规范处理。需要附图时先稳定术语、步骤及标号，再生成独立图文件。草稿属于待核验材料；仅附图可以根据已有说明书核对一致性。
4. **验证与交付。** 执行所请求模式的机械检查，再回查技术支持和范围。完整转换或附图任务记录证据后运行evidence_check，并读取checks区分已执行与未执行项；实际图生成后登记artifacts并启用--verify-delivery，规划阶段明确未核验文件。只做权项格式检查不强制补齐证据表。最多三轮修正，材料不能确定的问题保留为待核验项；图文件交付已通过不等于源稿已全部复核。

## 当前规范与原版档案

当前执行以本文件及模式表中的规范为准。法定要求、项目习惯及自动检查边界见 [legal-basis.md](references/legal-basis.md)。涉及申请条件、可专利性结论或用户要求法律合规核查时，读取该文件并核对官方适用版本。

原版 prompt 保留历史措辞，仅用于复制、溯源和比较；冲突依当前规范解决：

原版 prompt 与 README 档案来源于[7toCR/paper2patent](https://github.com/7toCR/paper2patent)，按MIT许可保留版权；来源及本项目增量见[NOTICE.md](NOTICE.md)，原许可及社区说明见[upstream-license.txt](references/upstream-license.txt)和[upstream-community-guidelines.md](references/upstream-community-guidelines.md)。

- [flash-prompt.md](references/flash-prompt.md)：原始 Flash prompt。
- [pro-prompt.md](references/pro-prompt.md)：原始 Pro prompt。
- [gemini-figure-prompt.md](references/gemini-figure-prompt.md)：原始外部模型附图 prompt；提供参考不表示已调用服务。
- [readme-overview.md](references/readme-overview.md)、[readme-notes.md](references/readme-notes.md)：README 背景、归属和说明。

## 工具与完成条件

脚本路径以 skill 目录为基准，输入输出以用户项目为基准，使用绝对路径调用。

- [claim_lint.py](scripts/claim_lint.py)：编号、末尾句号、引用关系和措辞提示；--json 输出结构化结果，--strict 将待复核提示纳入失败状态，--patent 追加摘要含标点长度预检。
- [patent_figure_svg.py](scripts/patent_figure_svg.py)：JSON 转 SVG，支持分支标签、手动布线和可选 PNG；能力边界见附图规范。
- [evidence_check.py](scripts/evidence_check.py)：统一schema、必需输入、来源、定位、图文对应和实际SVG校验；报告检查范围及独立交付状态，缺口保持草稿状态。
- [test_tools.py](scripts/test_tools.py)：维护脚本时执行的行为回归验证。
- [test_acceptance.py](scripts/test_acceptance.py)：公开合成技术案例的五部分交付与异常输入集成验收。维护流程或工具后执行；范围与人工检查项见[acceptance-cases.md](references/acceptance-cases.md)。
- [patent-output-template.txt](assets/patent-output-template.txt)、[evidence-map-template.json](assets/evidence-map-template.json)、[figure-spec-example.json](assets/figure-spec-example.json)：正文、证据和图结构模板。

完成前确认必要特征有来源与实施说明、引用关系正确、术语标号一致、相关权项被附图覆盖且没有新增技术关系。脚本只核验机械规则，引用基础、实施可行性和保护范围另作语义检查。

最终专利正文默认纯文本五部分；审查和仅附图请求交付对应结果。来源表、检查摘要及待核验项独立于正文，记录可核验事实，不输出内部推理。正文有实质缺口时明确草稿状态。
