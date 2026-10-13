# README Notes

> README 说明档案；其中历史版本信息不代替 [当前法规依据](legal-basis.md)。

This file mirrors the explanatory and trailing sections of the original README as closely as practical inside the skill package.

## Patent Conversion Notes

### 从论文到专利的关键转换策略

#### 论文与专利的核心差异

| 维度 | 论文 | 专利 |
|-----|-----|-----|
| 目标 | 学术影响力、可复现性 | 法律保护范围、技术垄断 |
| 表达 | 详细、全面、深入 | 精炼、抽象、可实施 |
| 结构 | 引言-方法-实验-结论 | 背景-问题-方案-效果 |
| 权利 | 无需权利要求 | 权利要求限定保护范围 |
| 深度 | 越深越好 | 充分即可，不过度详细 |

### 转换过程中的常见陷阱

**陷阱1：过度详细**
- 问题：将论文的所有细节都写入权利要求。
- 后果：保护范围过窄，他人稍作修改即可绕过。
- 正确做法：权利要求保持抽象，具体细节放入说明书。

**陷阱2：添加内容**
- 问题：为了使专利“更完整”而添加论文未提及的内容。
- 后果：超范围，专利可能被无效。
- 正确做法：严格忠实于论文原文，不添加任何内容。

**陷阱3：保护范围过宽**
- 问题：权利要求过于抽象，覆盖了论文未实际验证的技术方案。
- 后果：说明书不支持，专利可能被驳回或无效。
- 正确做法：权利要求应当得到说明书的支持。

**陷阱4：技术问题模糊**
- 问题：未清晰定义现有技术存在的问题。
- 后果：发明缺乏新颖性或创造性。
- 正确做法：详细分析现有技术的问题和不足。

### 专利撰写人员的思维转换

1. 从读者思维到审查员思维：想象审查员会如何评估你的专利，预先消除可能的驳回理由。
2. 从创新者思维到保护者思维：不仅描述你的创新是什么，更要确保创新被充分且恰当地保护。
3. 从学术表达到法律表达：将技术语言转换为法律语言，确保法律效力。
4. 从完美主义到实用主义：保护范围和可实现性之间找到平衡。

## Template Version Information

- 模板名称：论文转专利智能转换模板
- 模板版本：v1.0
- 适用领域：计算机视觉、人工智能、深度学习、图像处理、自然语言处理、语音识别等前沿技术领域
- 撰写规范：依据《中华人民共和国专利法》及其实施细则（2020年修订版）
- 最后更新：2026年4月

## 致谢 / Acknowledgments

本项目的 README 结构与内容参考了 `awesome-ai-research-writing`，感谢作者的整理与分享。本项目的部分内容受到了该仓库的启发。

## 其他说明

本项目的 LICENSE 文件采用 MIT License。
详细社区使用规范请参阅 `CLAUSE.md`。

上段保留原README的相对文件名。此skill中的对应档案为[upstream-community-guidelines.md](upstream-community-guidelines.md)，原MIT许可见[upstream-license.txt](upstream-license.txt)，来源为[7toCR/paper2patent](https://github.com/7toCR/paper2patent)。

## Mirror Use Guidance

- 当用户询问这个 skill 和原 README 的关系时，优先查看本文件与 [readme-overview.md](./readme-overview.md)
- 当用户需要 README 级别的说明性背景时，优先查看这两份 README 镜像文件
- 当用户需要真正执行论文转专利任务时，回到 [input-pack.md](./input-pack.md)、[patent-writing.md](./patent-writing.md)、[figure-generation.md](./figure-generation.md)
