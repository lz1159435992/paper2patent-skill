# paper2patent-skill

[![CI](https://github.com/lz1159435992/paper2patent-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/lz1159435992/paper2patent-skill/actions/workflows/ci.yml)

面向 Codex 的论文转中国发明专利草稿 skill，支持 Flash / Pro、草稿修订、权利要求检查，以及有来源对应的黑白 SVG 附图。当前版本为 **0.1.0 预览版**。

本项目基于 [7toCR/paper2patent](https://github.com/7toCR/paper2patent) 的原版 prompt 和 README 设计进行工程化扩展。三套原版 prompt 保存在 references 中，上游原作与本项目的增量说明见 [NOTICE.md](NOTICE.md)。这不是上游官方发行版。

## 能力与边界

- 依据论文已披露内容起草纯文本五部分文件：说明书摘要、摘要附图、权利要求书、说明书、说明书附图。
- 只做权项检查、草稿修订或附图时，按所请求的范围交付。
- 使用来源位置、引文、哈希、权项、实施方式和图节点记录对应关系。
- 从 JSON 生成可编辑的黑白 SVG，支持分支、反馈、自动绕障和手动路径；PNG 预览可选。
- 机械检查报告哪些项目已执行，以及图文件是否交付；技术支持和保护范围仍需语义复核。

skill 指令由支持本地 skills 的 AI 客户端执行。Python 工具只检查材料或绘图，不会独立调用模型生成专利，也不会自动上传材料、调用 Gemini 或提交申请。内置工具没有 DOCX / PDF 导出器。

检查通过不代表充分公开、可专利性或申请授权。原版 prompt 是历史档案；执行规则和适用版本以当前 skill 规范为准。新颖性检索、申请策略及最终申请文件需另行审查。

## 安装

复制的是整个 `skills/paper2patent/` 目录，包括 references、scripts、assets、tests、LICENSE 和 NOTICE。仅复制 SKILL.md 会丢失工具及规范。

### Windows / PowerShell

以下示例安装到用户级 `.agents/skills/`；已有同名目录时停止，避免覆盖现有本机 skill。

```powershell
git clone https://github.com/lz1159435992/paper2patent-skill.git
cd paper2patent-skill
$patentInstallPath = Join-Path $env:USERPROFILE '.agents/skills/paper2patent'
if (Test-Path -LiteralPath $patentInstallPath) {
    throw '已有 paper2patent：请先比较版本并决定更新方式。'
}
New-Item -ItemType Directory -Path (Split-Path $patentInstallPath) -Force | Out-Null
Copy-Item -LiteralPath './skills/paper2patent' -Destination $patentInstallPath -Recurse
```

### Linux / macOS

```bash
git clone https://github.com/lz1159435992/paper2patent-skill.git
cd paper2patent-skill
patent_install_path="${HOME}/.agents/skills/paper2patent"
if [ -e "$patent_install_path" ]; then
  echo "已有 paper2patent：请先比较版本并决定更新方式。" >&2
  exit 1
fi
mkdir -p "${HOME}/.agents/skills"
cp -R skills/paper2patent "$patent_install_path"
```

如果客户端配置了其他 skill 目录，使用其实际目录。客户端重新加载 skills 后，用 `$paper2patent` 调用。macOS 尚未在 CI 中验证；其他客户端的加载路径需按其文档配置。

## 使用示例

在支持 skills 的客户端中提供本地材料与目标：

```text
使用 $paper2patent，将提供的论文全文按 Pro 模式起草中国发明专利草稿。
保留实现所需公式，为技术特征记录来源位置，生成总体流程附图。
材料不支持的内容列为待核验项。
```

```text
使用 $paper2patent，仅检查这份权利要求的编号、引用关系和说明书支持。
```

```text
使用 $paper2patent，仅根据现有权利要求、说明书和附图说明生成图1。
交付 SVG、可编辑 JSON 和对应依据；说明哪些论文来源未核验。
```

完整转换需要标题、摘要和完整核心方法，全文优先。只有摘要时先交付有依据的规划及缺口，不编造方法或实施例。仅附图可使用已有说明书，论文回溯可按材料情况说明。

## 运行 Python 工具

支持范围为 Python 3.10+；CI 检查 Windows、Ubuntu 的 Python 3.10 / 3.13。正文、JSON、脚本均使用 UTF-8。核心工具与测试只使用标准库。

以下命令从仓库根目录运行，处理的是允许公开的合成案例。在某些系统中将 `python` 替换为 `python3`。

```bash
python -X utf8 -B skills/paper2patent/scripts/claim_lint.py skills/paper2patent/tests/fixtures/synthetic-patent-draft.txt --patent --json
python -X utf8 -B skills/paper2patent/scripts/patent_figure_svg.py skills/paper2patent/tests/fixtures/synthetic-figure1.json build/demo.svg
python -X utf8 -B skills/paper2patent/scripts/evidence_check.py skills/paper2patent/tests/fixtures/synthetic-evidence.json --patent skills/paper2patent/tests/fixtures/synthetic-patent-draft.txt --figures skills/paper2patent/tests/fixtures/synthetic-figure1.json --mode full --json --strict
```

证据表中的相对来源和图文件路径，以证据表所在目录为基准。上述证据命令验证规划对应；实际交付时先登记 `artifacts`，再使用 `--verify-delivery`，见 [证据规范](skills/paper2patent/references/evidence-mapping.md)。

`ready_for_semantic_review` 表示已运行的机械检查允许进入语义复核；`draft` 表示仍有缺口、待核验项或处于草稿模式。`checks` 区分已执行和未执行项；`delivery_status` 独立报告附图文件交付状态。以退出码判断 CLI 成功，`--strict` 把待复核提示纳入失败状态。

### 可选 PNG

```bash
python -m pip install -r requirements-png.txt
python -X utf8 -B skills/paper2patent/scripts/patent_figure_svg.py skills/paper2patent/tests/fixtures/synthetic-figure1.json build/demo.svg --png build/demo.png
```

PNG 需要 CairoSVG、可用的 Cairo 运行库和中文字体。仅安装 Python 包不一定补齐系统依赖；按 [CairoSVG 安装说明](https://cairosvg.org/documentation/) 配置。转换不可用时保留 SVG，并记录预览状态。字体方框、文字重叠、裁剪及箭头关系需要视觉检查。

## 验证与贡献

```bash
python -X utf8 -B tools/check_release.py
python -X utf8 -B skills/paper2patent/scripts/test_tools.py
python -X utf8 -B skills/paper2patent/scripts/test_acceptance.py
git diff --check
```

目前有 37 项工具回归测试和 31 项合成案例集成测试。它们验证脚本行为，不是独立模型评测，也不证明在任意论文上的转换质量。评估范围见 [验收说明](skills/paper2patent/references/acceptance-cases.md)，贡献约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。

公开案例为专门编写的传感器窗口技术披露，包含公式、分支、来源定位和图交付。仓库不包含真实用户论文、专利草稿、会话试用记录或这些文件的旧 Git 历史。

## 许可证与来源

代码、当前规范和合成测试案例采用 [MIT License](LICENSE)。上游 prompt 和 README 档案保留 7toCR 版权及 [原 MIT 许可](skills/paper2patent/references/upstream-license.txt)，上游社区说明保存在 [档案](skills/paper2patent/references/upstream-community-guidelines.md) 中。复制或再分发 skill 时同时保留 LICENSE 和 NOTICE。
