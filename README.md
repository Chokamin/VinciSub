# VinciSub

达芬奇原生 Python 脚本，用 Qwen3-ASR 在本机识别中文并生成 SRT。所有操作在达芬奇的脚本窗口中完成，无网页界面或本地 HTTP 服务。

## 当前 MVP

1. 在达芬奇打开时间线，需要局部识别时按 I / O 设置入点、出点；未设置时使用整条时间线。
2. 打开 **工作区 → 脚本 → Utility → VinciSub**，在音轨列表勾选一条或多条音轨；不勾选时自动识别所有可听音轨。
3. 确认窗口显示的范围，点击「生成字幕」。无需导出音频、选择文件或设置保存路径。
4. 识别完成后通过 Resolve API 写入原始时间线，并校验全部字幕位置。再次生成时，选区与最近可验证的 VinciSub 字幕轨没有重叠，就复用该轨；有重叠则新建字幕轨。窗口保持显示，无菜单点击或检查器操作。
5. 选中或双击列表里的字幕，在下方编辑文字及开始/结束时间，再点击「保存并同步」。修改会更新本次生成的原字幕轨，不再新建轨道；「写入字幕轨」也可用于重试同步。

**接入验证状态：**macOS / Resolve Studio 21.1 / 25fps 中文界面已通过原生生成 → 本地识别 → 原时间线字幕轨的完整实测，以及已有字幕保留和重复写入防护测试。

音频直接从所选音轨对应的源素材解码到内存，不调用 Resolve 渲染、不创建导出音频文件。保留片段裁剪、空隙和时间线位置；字幕时间以整条时间线起点为零，包括时间线从 01:00:00:00 开始的情况。

入出点优先读取音频范围，其次视频范围；只有单侧标记时，另一侧使用时间线边界。窗口自动更新范围，新增或重命名轨道后点击「刷新时间线 / 音轨」。自动模式下，有 Solo 时只识别未静音的 Solo 轨道，否则识别全部未静音音轨；支持多条 Solo。点击生成时读取最新状态，全部静音时明确提示。禁用片段和断开的音频通道会跳过；显式选中的轨道即使在混音中静音也可识别。

## 安装（macOS）

已实测：Apple Silicon、DaVinci Resolve Studio 21.1、Python 3.12、Qwen3-ASR-0.6B + Qwen3-ForcedAligner-0.6B，使用 MPS 推理。其他版本及 1.7B 模型尚未实测。

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 和 FFmpeg（`brew install ffmpeg`），然后在项目目录执行：

```sh
bash scripts/setup.sh
bash scripts/install-resolve.sh
```

自动落轨直接调用 Resolve API，不需要 Swift、辅助功能或 System Events 自动化授权。旧版 VinciSub Helper 已不再使用。

重启达芬奇后从脚本菜单打开。需要 Studio 版的 UIManager，并将偏好设置 → 系统 → 常规 → 外部脚本设为「本地」。脚本入口链接到项目目录，移动目录后需重新安装入口；安装程序不会覆盖已有同名入口。

默认使用 0.6B 模型，首次运行会从 Hugging Face 下载识别和时间对齐模型，需网络及数 GB 空间；之后完整缓存可离线使用。音频留在本机，不上传识别服务。模型许可证见 [Qwen3-ASR 官方仓库](https://github.com/QwenLM/Qwen3-ASR)。

## 限制与数据

- 自动 Solo / Mute 模式目前仅验证 Resolve 21.1：Mute 通过接口读取，Solo 通过临时时间线元数据读取；元数据用后删除，不导出音频。无法读取时明确报错，不回退识别全部轨道。其他版本暂用手动勾选音轨模式；总线 Solo / Mute 和 Solo Safe 等高级路由未验证。
- 单次选定范围最长 30 分钟；长音频按低能量位置分块，边界附近仍可能出现错字或漏字。
- 简体转换、标点恢复、按停顿和字数断句；不支持说话人分离、翻译、字幕样式或实时识别。识别后仍需校对。
- 识别源音频，不复现 Fairlight 的降噪、增益自动化、音效或总线混音。变速片段按首尾时间映射并提示校对，速度曲线中的局部时序可能存在偏差；倒放、嵌套/复合片段及外部同步音频映射暂不支持，会明确报错。
- 初次写入新建字幕轨；后续无重叠选区复用已有 VinciSub 轨道，合并旧字幕并刷新片段，保留旧文字、时间及其他轨道。校对只更新当前任务所属字幕。单条字幕样式会随片段重建，请在校对完成后设置；轨道样式不主动更改。
- 同步前核对全部字幕 ID、文字和时间；若在达芬奇内改过或轨道已锁定，校对同步拒绝覆盖，新选区生成则新建轨道。失败时尝试恢复原字幕内容，恢复失败会提示检查任务目录的 `edit-backup.json`。
- 自动落轨目前限制 macOS / Resolve 21.1 / 整数帧率 24、25、30、48、50、60；实际写入仅验证 25fps；其他帧率待实测，写入不依赖界面语言。掉帧及分数帧率明确拒绝。长字幕任务尚未实测。
- 「保存 SRT」包含在插件里保存的修改；不回读在原生字幕轨中的外部编辑。
- 字幕必须有合法、不重叠的起止时间，偏移后不能早于时间线起点。
- 模型、结果及任务日志在 `.vincisub/`，不纳入 Git。关闭程序后可按需清理旧的 `jobs/`（旧版文件模式可能留有音频）；保留 `models/` 避免重新下载。
- 任务在独立 Python 进程中执行；取消会结束进程并释放模型内存。关闭窗口前须先取消正在运行的任务。
- 出错时查看对应任务的 `.vincisub/jobs/<任务编号>/worker.log`；落轨问题另看 `placement.json` 和 `placement.log`。异常退出残留 `placement.lock` 时，先检查本次字幕轨再清理锁，避免重复写入。

## 开发验证

先阅读 HANDOFF.md、PROJECT_MEMORY.md、DECISIONS.md、CLAUDE.md。

```sh
.venv/bin/python -B -m unittest discover -s tests -v
# 可选：需打开达芬奇；在临时项目验证 SRT 导入，结束后恢复原项目
.venv/bin/python -m scripts.verify_resolve /absolute/path/to/sample.wav
.venv/bin/python -m scripts.verify_timeline /absolute/path/to/sample.mp4
.venv/bin/python -m scripts.verify_placement /absolute/path/to/sample.mp4
git diff --check
```

原生入口 `scripts/VinciSub.py`；窗口 `vincisub/native_ui.py`；任务控制 `jobs.py`；推理 `worker.py`；字幕规则 `subtitles.py`；时间线范围及音频读取 `timeline.py`；达芬奇导入 `resolve.py`。
