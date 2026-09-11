# 项目记忆

## 最近完成的修改

### 2026-09-11：初始化协作文档

- 需求：建立可跨对话恢复的四份根目录协作文件；每次修改更新记忆、测试并提交 Git commit。
- 改动：创建项目记忆、长期决策、交接状态和共用协作规则；新增基于 Python 标准库的文档验证测试。
- 关键文件：PROJECT_MEMORY.md、DECISIONS.md、HANDOFF.md、CLAUDE.md、tests/test_project_memory.py。
- 验证结果：`python3 -B -m unittest discover -s tests -v` 全部通过（3 项）；`git diff --check` 通过，提交前再检查暂存差异。
- 剩余问题：尚未明确产品需求和技术栈；尚无业务功能可验证。

## 关键文件

- PROJECT_MEMORY.md：近期修改、关键文件、验证结果和短期问题。
- DECISIONS.md：长期产品、UI、技术、数据结构与工作流决策。
- HANDOFF.md：当前状态、下一步任务、风险、阻塞点和待验证项。
- CLAUDE.md：Codex 与 Claude Code 的共同协作规则。
- tests/test_project_memory.py：四份文档的存在性、结构与协作入口引用检查。

## 短期问题

- 等待具体产品需求后开始业务开发。
