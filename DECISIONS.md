# 长期决策

## 2026-09-11：项目协作与事实来源

- 决策：代码库是事实源，项目记忆文件是协作源；不以聊天历史保存长期事实。
- 决策：PROJECT_MEMORY.md、DECISIONS.md、HANDOFF.md、CLAUDE.md 均位于项目根目录并纳入 Git，供 Codex 和 Claude Code 跨对话协作。
- 决策：每次工作先读取四份文件；每次修改完成后回写修改记录和交接状态。长期决策及协作规则仅在相应内容变化时更新。
- 决策：每次改动必须编写或更新相关测试，全部测试与验证通过后交付，并创建对应 Git commit。
- 原因：用户要求项目可以跨会话恢复，且每次变更可验证、可追踪、可回滚。
- 影响：后续所有项目修改均遵守 CLAUDE.md 中的协作流程。

## 产品与技术

### 2026-09-11：达芬奇原生字幕脚本

- 产品：VinciSub 为达芬奇脚本，使用原生 UIManager 窗口，不建立网页 UI 或 HTTP 服务。这是用户明确指定的工具形态。
- 识别：本机 Qwen3-ASR，默认 0.6B，配合 Qwen3-ForcedAligner-0.6B 生成实测时间戳；OpenCC 转简体。用户已选择 Qwen3-ASR 本地方案。
- 架构：Resolve 内置解释器仅运行轻量 UI/任务控制；Python 3.12 独立进程加载模型，避免依赖污染并支持取消释放内存。UI 使用原生 Timer 更新状态。
- 数据：任务状态、请求和字幕 JSON 持久化于 `.vincisub/jobs/<uuid>/`；模型位于 `.vincisub/models/`，均不提交 Git。JSON 显式 UTF-8、原子替换；字幕使用秒制时间戳，SRT 使用毫秒和 UTF-8 BOM。
- MVP 边界：手动从时间线导出音频后，在原生窗口识别、校对、保存 SRT 或导入媒体池，再拖入字幕轨道。自动导出和自动放置字幕属于后续工作，不以未通过的接口冒充完成。
- 验证：macOS Apple Silicon / Resolve Studio 21.1 / Qwen 0.6B MPS 已实测；1.7B、其他操作系统及 Resolve 版本尚未实测。
