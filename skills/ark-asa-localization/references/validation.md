# 验证、测试和交付用语

## 自动验证

建议在临时 venv 安装构建依赖，再从 skill 根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r scripts/requirements-build.txt
$env:ASA_TEST_TOOLS = "X:\work\tools.json"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

不设置 ASA_TEST_TOOLS 时，外部独立工具整链测试会明确 skip；不能将它称为已通过。Windows PowerShell 安装器测试仅在 Windows 运行，其他系统 skip。所有游戏文件为 temporary fixtures，没有真实安装授权需求。

- core：危险 ZIP/CRC、原件不变、重叠 FText、Unicode Base text、审查定位与源件变化、JSONC 字符串和注释、数值/百分号/标签/占位符。
- resources：真实案例源 CRC 向量、显式身份保留、候选计数、冲突拒绝、中文/emoji UTF-16 回读、截断和元数据。
- installer：真实 PowerShell 进程操作临时目录，测试 Steam、手工内部路径、多客户端交互、缺模组/错误游戏/哈希异常、配置编码、已有所有权、反复安装、失败回退和多目标共存。
- pipeline：从临时原件扫描→人工标记 fixture→资源构建→UnrealLocres 导出→repak list/unpack→交付 ZIP→实际 BAT 检测/安装/卸载，检查效果而非 grep 源码。

生成的 `verification.json` 列出源件哈希、资源哈希、工具版本与 SHA、身份证据计数和独立导出结果；`package` 会再次验证包体、资源、元数据和当前实际译文，拒绝校验后被修改的 PAK。包内提供清单、译文对照和 ZIP 成员哈希。默认输出路径必须不存在，失败输出可保留排错，重试使用新路径。

## 真实游戏测试清单

在用户授权、已退出游戏并可回退的条件下：

1. 记录 ASA build、模组 VersionName/文件版本、地图/单机或服务器、客户端语言、其他翻译覆盖包；确认测试的是目标模组而非旧包。
2. 运行 Detect 核对客户端和已安装 `.uplugin`；安装后核对 PAK 哈希及客户端 Saved Game.ini 的目标路径。检测目录不证明存档已启用模组。
3. 在可用日志中寻找 PAK mount 和本地化目标加载证据。若日志不含相关信息，记录“未观察到”，不能以文件存在替代。
4. 用简体中文检查：物品/生物名称与说明、Buff/HUD、设置标签、动态提示、格式化参数、按键显示、文本布局和中文字体。
5. 记录每个文本的原文/身份、实际显示、触发方式、截图或日志；分开统计显式键与 CRC 候选的命中/未命中/未测。
6. 验证菜单/骑乘/火炮等相关功能仍正常，不因文本处理破坏查表、绑定或事件；不为测试改变玩法数值或删除存档。
7. 重启检查持久性；卸载确认恢复和个人设置保留。记录语言切换及其他小包并存情况。

发现全部英文时先查加载配置、语言链、容器挂载，再查键；局部英文时检查原文/hash、namespace/key、运行时路径、服务器直接返回文本和存档自定义值。方框缺字与翻译匹配失败分开诊断，不自动加入字体 DLL。

## 可用的交付表述

“已制作 N 条译文，离线独立导出/封包校验通过；仍是研究测试版，目标加载和部分候选匹配待游戏实测。”

禁止把“安装校验通过”“148 个身份”“文件体积小”“工具支持 UE5”改写成“全界面汉化成功”“148 条命中”或“适配所有飞升版本”。将来真实测试通过也只陈述测试过的版本、界面和条件，保留未测范围。

skill 格式可用 skill-creator 的 quick_validate.py 检查；格式验证不替代上述行为测试。独立执行者的行为演练用于检查 skill 是否会引导正确决策，不冒充游戏运行测试。
