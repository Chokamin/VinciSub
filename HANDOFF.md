# 项目交接

## 当前状态

- 原生达芬奇脚本：工作区 → 脚本 → Utility → VinciSub；已安装入口链接到项目源码，关闭旧窗口重开加载新代码。
- 默认识别所有可听音轨，跟随多轨 Solo / Mute；可指定单轨。有入出点使用范围，无标记使用整条时间线，单侧标记补齐边界；音频范围优先。
- 音频从片段源文件解码至内存，无手动导出、无中间音频文件、无渲染任务。不复现 Fairlight 效果。
- 已接线：原生生成结束自动启动 placement 进程，在原始时间线新建 VinciSub 字幕轨；整份 SRT 通过 AppendToTimeline 素材列表重载一次写入并回读；保存凭据避免重复，失败清理本次新增字幕。
- 写入期间原生窗口保持显示并更新状态；写入后在原生字幕轨校对。保存 SRT 是识别结果副本，不含原生轨道后续编辑。
- 当前验收状态：直接 API 写入的已有字幕、精确定位与播放头恢复已通过；原生生成 → Qwen 识别 → API 自动写入原时间线完整流程通过；已有字幕保留、音视频不变与重复预防复测通过。

## 下一步任务

1. 验证长音频、更多实际口播、非 25fps、英文界面和高级音频路由。
2. 新字幕写入前明确停用旧字幕轨、启用新字幕轨，修复仅启用新轨时偶发误投旧轨的问题；失败恢复原启用状态。继续保留错轨清理和诊断，不依赖 trackIndex 单独决定落点。

## 已知风险

- 自动落轨限制 Resolve 21.1 / 整数 24、25、30、48、50、60fps；实际写入验证 25fps。没有界面语言、Swift 或辅助功能依赖；其他平台与帧率仍待实测。
- 使用 AppendToTimeline 的素材列表重载；clipInfo 字典会将 SRT 放到末尾，source startFrame/endFrame 曾触发退出，不要混用。启用新字幕轨后等待异步状态生效。
- 异常进程退出可能残留本次字幕轨及 `.vincisub/placement.lock`，须检查后清理，不自动猜测恢复。
- 自动 Solo / Mute 从临时 DRT 元数据读取，限制 21.1；不复现总线、Solo Safe 或 Fairlight 效果。
- 变速仅首尾映射，速度曲线需校对；倒放、嵌套/复合及外部同步音频映射明确拒绝。单次范围最长 30 分钟；大批量逐条落轨耗时待验证。
- 模型仅 Apple Silicon / Qwen 0.6B MPS 实测，1.7B 未实测。用户真实项目未写入测试素材。

## 阻塞点

- 已移除旧 Helper 的全部生产调用及 Swift 源码。直接 API 写入不再受系统辅助功能或自动化授权阻塞。旧 `.vincisub/bin/` Helper 缓存不再执行。

## 需要验证的内容

- `.venv/bin/python -B -m unittest discover -s tests -v`：52 项通过。
- `.venv/bin/python -m scripts.verify_placement .vincisub/verification/mandarin.mp4`：独立项目保留已有字幕、准确定位三条新字幕、音视频不变与重复预防；直接 API 版本通过，包含已有字幕数量和文字前置断言，并核对播放头与页面不变。
- `.venv/bin/python -m scripts.verify_timeline .vincisub/verification/mandarin.mp4`：双音轨、范围、静音筛选、原生生成、真实识别到自动落轨。完整流程通过：生成两条字幕，位于相对时间线 2.04–4.20s 与 4.36–4.84s，原始时间线身份不变、无渲染和音频输出。
- `.venv/bin/python -m scripts.verify_resolve .vincisub/verification/mandarin.mp4`：旧媒体池导入兼容回归已通过。
- 所有实测使用保存后新建的独立项目，finally 恢复原项目并清理测试项目。不要用用户原项目写入验证。
- 提交前检查 git diff --check 和暂存差异，提交后检查工作区干净。
