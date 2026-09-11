# 项目交接

## 当前状态

- 原生达芬奇脚本：工作区 → 脚本 → Utility → VinciSub；已安装入口链接到项目源码，关闭旧窗口重开加载新代码。
- 默认识别所有可听音轨，跟随多轨 Solo / Mute；可指定单轨。有入出点使用范围，无标记使用整条时间线，单侧标记补齐边界；音频范围优先。
- 音频从片段源文件解码至内存，无手动导出、无中间音频文件、无渲染任务。不复现 Fairlight 效果。
- 已接线：原生生成结束自动启动 placement 进程，在原始时间线新建 VinciSub 字幕轨；逐条 SRT 追加后由独立 macOS Helper 调整原生检查器起止帧并回读；保存凭据避免重复，失败清理本次新增字幕。
- 定位期间原生窗口隐藏，结束显示状态；写入后在原生字幕轨校对。保存 SRT 是识别结果副本，不含原生轨道后续编辑。
- 当前验收状态：终端助手定位三条字幕、保留已有字幕、音视频不变、重复预防已通过；独立应用最终完整流程仍待重新授权后验证，不能宣称已完成验收。

## 下一步任务

1. 用户已开启过 Helper 权限，但修复启动重新编译后，系统仍返回未授权。已请求用户移除后重新添加 `.vincisub/bin/VinciSub Helper.app` 并开启；收到回复后继续预检和两个实测，不再无故重编译助手。
2. 执行 verify_timeline 完整原生按钮 → Qwen → 原时间线字幕轨；执行 verify_placement 已有字幕场景。两者默认必须成功，否则保持未验收状态。
3. 通过后更新本文件和 README 的验收状态，回写 PROJECT_MEMORY 并提交 Git。
4. 后续验证长音频、更多实际口播、非 25fps、英文界面和高级音频路由。

## 已知风险

- 当前自动落轨仅放行 macOS / Resolve 21.1 / 整数 24、25、30、48、50、60fps；实际定位只验证 25fps 中文界面。首次需 Swift Command Line Tools 编译和辅助功能 / System Events 自动化授权。重新编译本地签名应用可能需重新授权。
- 界面定位要求达芬奇保持焦点；期间不要操作。焦点丢失、身份或位置不匹配时停止。异常进程退出可能残留本次字幕轨及 `.vincisub/placement.lock`，须检查后清理，不自动猜测恢复。
- SRT Append 忽略 recordFrame；绝不能传 source startFrame/endFrame（曾触发 Resolve 退出）。启用新字幕轨后需等待异步状态生效。
- 自动 Solo / Mute 从临时 DRT 元数据读取，限制 21.1；不复现总线、Solo Safe 或 Fairlight 效果。
- 变速仅首尾映射，速度曲线需校对；倒放、嵌套/复合及外部同步音频映射明确拒绝。单次范围最长 30 分钟；大批量逐条落轨耗时待验证。
- 模型仅 Apple Silicon / Qwen 0.6B MPS 实测，1.7B 未实测。用户真实项目未写入测试素材。

## 阻塞点

- 当前独立 Helper 的系统授权与完整链路验收尚未完成。直接由 Resolve 子进程发送 Apple Events 返回 -1743；已改独立 app 通过 LaunchServices 启动。
- macOS 27 / 本机 Swift 默认部署目标异常为 28，已显式编译目标 macOS 13；助手初始化 NSApplication，通过请求/响应 JSON 回传，避免 open -W 等待。

## 需要验证的内容

- `.venv/bin/python -B -m unittest discover -s tests -v`：52 项通过。
- `.venv/bin/python -m scripts.verify_placement .vincisub/verification/mandarin.mp4`：独立项目保留已有字幕、准确定位三条新字幕、音视频不变与重复预防；旧终端助手通过，当前独立 app 待授权后复测。
- `.venv/bin/python -m scripts.verify_timeline .vincisub/verification/mandarin.mp4`：双音轨、范围、静音筛选、原生生成、真实识别到自动落轨。当前真实 ASR 已完成，但助手权限/启动失败，完整测试未通过。
- `.venv/bin/python -m scripts.verify_resolve .vincisub/verification/mandarin.mp4`：旧媒体池导入兼容回归已通过。
- 所有实测使用保存后新建的独立项目，finally 恢复原项目并清理测试项目。不要用用户原项目写入验证。
- 提交前检查 git diff --check 和暂存差异，提交后检查工作区干净。
