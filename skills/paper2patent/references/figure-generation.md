# 当前附图规范

## 输入和图文对应

仅附图任务使用已有权项、说明书及附图说明；论文可选，不因缺少论文阻止一致性工作。依 [evidence-mapping.md](evidence-mapping.md) 记录节点与连线的文本依据。稳定相关术语、步骤编号、模块标号、分支条件和反馈方向后生成。

图1通常为总体方法或系统，图2为关键细节，其余图按必要内容和正文引用顺序选择。方法图覆盖相关独立项步骤，系统图覆盖所描述模块；有依据的从属子步骤可另图展开。简称先在术语表建立对应，不用缩写隐藏新内容。

## 样式和交付

默认黑色线条、白色背景；处理用矩形，起止用圆角矩形，判断用菱形；简体中文短标签，步骤用S101等标号，同一组件跨图标号相同。外框仅白底遮挡线条，不使用装饰性填充、灰色、阴影或渐变。

每幅图独立生成，默认显示图号及提供的标题；明确要求外置图号时可关闭图内显示，并在文档对应图面加图号。正文附图说明、图文件和摘要图实际对应；空白 ASCII 框、文字说明和 prompt 仅属于规划材料。

## JSON 参数

使用 [figure-spec-example.json](../assets/figure-spec-example.json) 起步，[figure-spec.schema.json](../assets/figure-spec.schema.json) 描述结构。脚本自身验证必要字段、尺寸、唯一ID、连接端点和布局；ID引用和技术支持仍需对照正文。

[figure-branch-example.json](../assets/figure-branch-example.json) 演示判断分支、汇聚与反馈的手动布线；示例仅说明绘图参数，不作为用户专利的技术来源。

| 项 | 字段 |
| --- | --- |
| 图 | diagram_type 为 flowchart 或 block；figure_no、title；show_figure_no、show_title 默认 true |
| 布局 | block 的 layout 为 horizontal / vertical；box_w、box_h、gap、margin、font_size、wrap_width、font_family |
| 画布 | width / height 是最小尺寸，会按实际内容扩大；负坐标通过 viewBox 保留 |
| 节点 | 必需 id / label；可选 x / y / w / h、shape、rounded、reference、note、wrap_width、font_size |
| 连线 | [source,target] 或对象 source / target；可选 label、label_x / label_y、points、route: bottom_return；source_port / target_port 可选 top / bottom / left / right |
| 注释 | annotations 数组，每项 x / y / text，可选 font_size / wrap_width |

文本按可用宽度换行，节点高度自动扩大。source_port / target_port 同时适用于自动和手动连线；手动 points 首尾贴合实际端口，未指定时选最近端口。所有路径（含自循环、反馈和手动折线）检查节点、标题碰撞，斜线也接受检查；手动路线穿框时明确报错。自动布线使用可通行网格绕障，bottom_return 从节点下方绕行；自循环选不同端口。默认连线标签选择不盖住节点的一侧，复杂布局仍需目检。

复杂交互、密集循环或几何示意可使用手动 points 或适合的可编辑绘图工具。多项手动布局混合时核对层级和连线，脚本不推断技术关系。

## 运行和检查

使用实际 skill 路径和用户项目的绝对输入输出路径；以下 PowerShell 示例从发布仓库根目录运行，生成合成演示图：

    $patentSkillRoot = (Resolve-Path './skills/paper2patent').Path
    $patentFigureSpec = Join-Path $patentSkillRoot 'tests/fixtures/synthetic-figure1.json'
    $patentFigureOutput = Join-Path ([System.IO.Path]::GetTempPath()) 'paper2patent-demo.svg'
    python -X utf8 (Join-Path $patentSkillRoot 'scripts/patent_figure_svg.py') $patentFigureSpec $patentFigureOutput

已安装 skill 时，将patentSkillRoot改为实际安装目录。POSIX shell 示例：

    python3 -X utf8 skills/paper2patent/scripts/patent_figure_svg.py skills/paper2patent/tests/fixtures/synthetic-figure1.json /tmp/paper2patent-demo.svg

SVG 只需要 Python 标准库；可选 PNG 预览需要 CairoSVG 及运行时字体。PNG 转换不可用时保留 SVG 并报告预览状态。字体缺失导致方框时指定本机可用的中文字体再渲染。字形宽度估计用于布局，不能替代视觉检查。

生成后渲染并检查裁剪、字体、重叠、箭头方向、分支标签及缩小可读性。将实际SVG登记至证据表artifacts，运行evidence_check --mode figures --verify-delivery核对文件、最新图规范和正文对应；规划时报告交付检查未执行。正文以图号引用即可，显式文件名出现时也需对应。交付实际图和可编辑JSON；PNG作为预览或按请求交付。
