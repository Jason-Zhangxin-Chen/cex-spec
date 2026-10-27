# CLAUDE.md — 多活高可用 CEX 交易系统 IcePanel 设计项目

## 语言规则（最高优先级）

- **所有面向客户的交付内容一律使用中文**：页面文案、README、IcePanel 模型中的 `name` / `description`、脚本输出信息、注释与对话总结。
- 技术标识符保持 ASCII：对象 `id`（如 `a-spot`、`s-gts`）、文件名、命令、代码。
- 原因：客户是中国人，用户明确要求全部输出中文。

## 项目结构

- 根目录 `spec.md` —— 客户提供的文字规格说明，**权威来源**。一切绘制以它为准，不得自行发明系统结构；若客户提供图片输入，放入 `inputs/` 目录并按下述工作流规则处理。
- `cex-trading-system.html` —— 输出页面，按章节组装。**第 1 节固定为「系统概览」**（依据 `spec.md`），后续章节随新的 spec/输入文件递增，末尾保留「导入 IcePanel」节。
- `icepanel-landscape.json` —— IcePanel Model-as-code 模型。对象 ID 保持稳定（重复导入是 upsert 更新，不是重复创建）。
- `import_to_icepanel.py` —— 导入脚本（中文输出）。
- `inputs/ocr_result.json`、`inputs/boxes.json` —— OCR 与框图检测的中间结果（仅当客户提供图片输入时生成）。

## 工作流规则

1. **先提取，后绘制**：文字规格说明（如 `spec.md`）直接作为绘制依据；客户提供图片输入（`inputs/`）时，先 OCR（rapidocr-onnxruntime，注意输出带坐标的文本框）再 OpenCV 检测框图/长边界线，若会话图片通道可用则直接看图。图里的空白格与缺失区域要如实保留，不要脑补内容。
2. **画布风格**：IcePanel 风 —— 点阵网格背景、大边界用虚线框（VPC 用蓝色虚线 + 顶部标签签）、分组容器用虚线框 + 左上角色点 + 标题、服务盒为圆角矩形带分类色边框、数据库为圆柱体、连接为折线 + 箭头。
3. **分类配色**（浅色/深色主题各一套，统一走 CSS 变量）：外部系统 `--c-ext` 灰蓝；边缘防护 `--c-edge` 红；网关 `--c-gw` 橙；后端服务 `--c-core` 蓝；行情/数据 `--c-md` 绿；支撑服务 `--c-acc` 紫；存储 `--c-infra` 青。
4. **每节完成后必须校验**：
   - 解析 SVG：框数、连线数、端点越界、标签是否贴近所属连线；
   - `google-chrome --headless --disable-gpu --screenshot=render_*.png --window-size=1600,1800 --hide-scrollbars "file://$PWD/cex-trading-system.html"` 渲染截图人工确认。
5. **页面与模型同步**：画布上的对象/连接与 `icepanel-landscape.json` 保持一致；页面统计数字（对象数、连接数）以 JSON 实际数量为准。
6. 新增内容时更新 `README.md` 的进度表。

## 已知环境问题

- 会话图片显示通道不稳定：Read 图片返回 `[Unsupported Image]` 后图像经常不送达 → 用 OCR + OpenCV 提取代替，或转为小尺寸 JPEG 重试。
- 发布 Artifact 被阻止：环境使用 `ANTHROPIC_AUTH_TOKEN` 认证，优先于 claude.ai 账号。需用户 `unset ANTHROPIC_AUTH_TOKEN` 并 `/login` 后才能发布。
- 无 sudo 权限：工具需通过 pip 安装（如 rapidocr-onnxruntime、opencv-python）。
- 语音输出已配置：用户级 Stop hook 自动用普通话朗读每轮回复（`~/.claude/hooks/tts-speak.sh`，spd-say），`/hooks` 可停用；语音输入（`/voice` 听写）需 claude.ai 登录，`ANTHROPIC_AUTH_TOKEN` 环境下不可用（与 Artifact 同因）。
