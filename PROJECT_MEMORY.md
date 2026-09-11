# 项目记忆

## 最近完成的修改

### 2026-09-11：初始化协作文档

- 需求：建立可跨对话恢复的四份根目录协作文件；每次修改更新记忆、测试并提交 Git commit。
- 改动：创建项目记忆、长期决策、交接状态和共用协作规则；新增基于 Python 标准库的文档验证测试。
- 关键文件：PROJECT_MEMORY.md、DECISIONS.md、HANDOFF.md、CLAUDE.md、tests/test_project_memory.py。
- 验证结果：`python3 -B -m unittest discover -s tests -v` 全部通过（3 项）；`git diff --check` 通过，提交前再检查暂存差异。
- 剩余问题：尚未明确产品需求和技术栈；尚无业务功能可验证。

### 2026-09-11：达芬奇原生中文字幕 MVP

- 需求：用户选择 Qwen3-ASR 本地方案，并明确整个工具必须是达芬奇脚本，没有网页界面。
- 改动：实现原生 UIManager 窗口、独立推理进程、模型缓存、简体转换、对齐时间戳、字幕断句/校对/偏移、SRT 保存及媒体池导入；加入安装脚本、依赖锁定及使用说明。移除先前误做的网页实现，未将网页版本提交。
- 关键文件：scripts/VinciSub.py、vincisub/native_ui.py、jobs.py、worker.py、subtitles.py、resolve.py、README.md、requirements.lock、tests/。
- 验证结果：27 项自动测试；本机 Resolve Studio 21.1 原生启动及中文文件选择、Qwen 0.6B MPS 实际识别 8.7 秒样本为 3 条字幕、原生 Timer 自动展示结果、校对与偏移持久化、任务取消；SRT 导入临时项目实测通过并恢复原项目。提交前执行全套测试和差异检查。
- 剩余问题：自动时间线音频渲染实测失败，当前需先手动导出音频；导入媒体池后需手动拖到字幕轨道。未验证真实长音频、1.7B 或跨系统兼容。

## 关键文件

- PROJECT_MEMORY.md、DECISIONS.md、HANDOFF.md、CLAUDE.md：跨对话协作入口。
- scripts/VinciSub.py、scripts/install-resolve.sh：原生脚本启动与安装。
- vincisub/native_ui.py、jobs.py：原生窗口、任务状态和结果保存。
- vincisub/worker.py、audio.py、subtitles.py：本地识别、音频处理和字幕规则。
- vincisub/resolve.py、scripts/verify_resolve.py：媒体池导入及隔离实测。
- tests/：文档、入口、音频、字幕、任务和 Resolve 适配测试。
- README.md：安装、使用方法、当前边界和验证命令。

## 短期问题

- 自动导出时间线音频尚未解决，详见 HANDOFF.md；不要将其描述为已完成。
- 下一步用真实简体中文口播素材验证准确率、长音频边界和使用体验。
