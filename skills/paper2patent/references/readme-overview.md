# README Overview

> README 原文背景档案；当前执行规则与版本见 [legal-basis.md](legal-basis.md)。

原始来源：[7toCR/paper2patent](https://github.com/7toCR/paper2patent)。原MIT许可保存在[upstream-license.txt](upstream-license.txt)，完整归属见[NOTICE.md](../NOTICE.md)。

This file mirrors the overview sections of the original README as closely as practical inside the skill package.

## Copyright And Use Notice

© 2026-present [7toCR] · All Rights Reserved

欢迎免费公开使用，但严禁将本项目直接复制到其他仓库并声称是你的原创成果。如需引用或参考，请注明原始来源并链接回本仓库。

本项目基于 MIT License 开源。

## Slogan

Make AI Writing Better for Everyone

## 为什么做这个项目

当你熬夜肝完一篇顶会论文，满心欢喜准备投稿时，是否也在发愁：这项成果能不能转化成专利？专利该怎么写？权利要求怎么组织？说明书有什么规范？

在学术圈，将研究成果转化为知识产权保护正变得越来越重要。论文是学术贡献的证明，专利才是技术的法律护城河。然而，专利撰写有着极高的专业门槛：法律文本规范、权利要求布局、技术效果论证……这些对于科研人员来说，往往是从零摸索的漫长过程。我们不想看到好的研究因为不懂专利撰写而错失保护机会。

## 我们做了什么

我们调研了高校科研团队、企业研究院的专利工程师和科研人员，总结了他们将论文转化为专利时的核心痛点和实战经验，将这套论文转专利的智能转换模板开源出来：

- 专利结构模板：提供完整的专利五大部分结构（说明书摘要、摘要附图、权利要求书、说明书、说明书附图），严格遵循中国专利法及其实施细则的撰写规范
- 权利要求布局：包含独立权利要求与从属权利要求的撰写规范，保护范围层层递进
- 智能转换流程：从论文中自动提取核心技术贡献，重构为专利法律文本的表达方式
- 质量检查清单：内置多条核心规则检查，确保专利文件的合规性
- 附图绘制规范：提供系统框图、流程图等专利附图的标准模板

## 特点

- 合规权威：严格遵循中国专利法及其实施细则（2020年修订版）的撰写规范
- 开箱即用：复制 prompt 即可启动转换，无需记忆复杂的专利撰写流程
- 忠实原文：所有技术内容严格源自论文原文，不添加、不修改、不歪曲
- 保护范围合理：权利要求层次化布局，核心发明点到具体实施例层层递进

## README Core Contents

README 的核心目录指向三条主线：

1. 论文转专利Flash
2. 论文转专利Pro
3. 专利附图生成（Gemini）

本 skill 中与之对应的镜像文件分别是：

- [flash-prompt.md](./flash-prompt.md)
- [pro-prompt.md](./pro-prompt.md)
- [gemini-figure-prompt.md](./gemini-figure-prompt.md)

此外，skill 还补充了工程化分层文档，用于把 README 中的设计转成可执行工作流：

- [input-pack.md](./input-pack.md)
- [patent-writing.md](./patent-writing.md)
- [figure-generation.md](./figure-generation.md)
