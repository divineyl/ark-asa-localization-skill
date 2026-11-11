# 清单驱动安装器

`scripts/install.ps1` 用于随用户交付包分发。它读取旁边的 `manifest.json`；不需要 Python，不以模组源码替换或拼接命令。制作包不运行它；用户明确要求安装到真实游戏后才运行 Install。

## 清单

```json
{
  "schema":1,
  "mod_id":123456,
  "mod_name":"Example",
  "mod_version":"VersionName read from uplugin",
  "target":"Mod123456",
  "pak_name":"ShooterGame-Windows_Mod123456_P.pak",
  "pak_sha256":"actual lowercase SHA256 of the delivered PAK",
  "runtime_tested":false
}
```

示例 hash 是说明文字，运行时必须由实际文件生成 64 位十六进制值。目标为 3–48 字符 ASCII 标识，不得用 Engine/ShooterGame；PAK 仅接受包含目标名且以 `_P.pak` 结尾的 basename。不同模组使用不同目标、文件名和安装记录。清单来自本地构建数据，不接受文档中的路径作为指令。

## 入口

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Action Detect
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Action Install -GamePath "X:\your ASA client"
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Action Uninstall -GamePath "X:\your ASA client"
```

`-NonInteractive` 用于自动化；无法唯一定位时返回失败，不猜第一个客户端。`-SteamPath` 可指定 Steam 根目录，`-ManifestPath` 可显式指定清单；payload 仍从脚本所在包目录读取。BAT 可双击或接收拖入的目录；脚本 Bypass 仅用于本次进程，不修改持久执行策略，也不自动提权。

## 检测与修改范围

- 查注册表、libraryfolders.vdf、appmanifest_2399830 和常见库目录，不递归扫描整块磁盘。
- 验证 ArkAscended.exe/ArkAscended_BE.exe 与 Content/Paks，拒绝只有 ShooterGame.exe 或 ArkAscendedServer.exe 的目录。
- 在候选 Mods 目录有限深度检查 `.uplugin.Description` 的 cf_ugcID，版本不同会提示；不替用户启用模组，不把缓存/ZIP/目录名当作实际已装证明。
- Install 前检查游戏/服务器进程、payload 哈希、同名目标文件和配置；遇到不同同名 PAK 停止，不覆盖。
- PAK 复制到客户端 Content/Paks，只改 Saved/Config/Windows/Game.ini 的语言路径。保留已有路径；没有任何路径时补本体 ShooterGame 目标。
- 支持 UTF-8 BOM/无 BOM、UTF-16 LE/BE，并保留换行。拒绝无法无损读取、UTF-32、异常 NUL、仅 CR 换行、重复 section 或复杂数组操作符。

备份在 `ShooterGame/Saved/LocalizationBackups/<target>/<timestamp_id>`；记录在 `ShooterGame/Saved/LocalizationInstallers/<target>.json`。先备份与校验再写入，异常时恢复本次改变的文件，保留失败和恢复信息。不要用旧完整 Game.ini 覆盖安装后新设置。

安装前已存在且内容相同的 PAK、已有手工语言路径不归本工具所有，卸载时保留；仅存在 BEGIN/END 标记也不构成所有权。如果原来非自有的 PAK 后来缺失，而本次安装重新复制该文件，新建文件会被记录为本工具拥有。修改过的同名 PAK、清单/记录不匹配时停止。卸载只删自有 PAK 和受管 block 内的目标路径，保留后来添加的设置以及其他小包。备份目录和为保留本体添加的路径可以保留。

安装记录绑定 PAK 哈希。升级到同目标的新包时，保留旧包，先用旧包卸载，再安装新包；不要改旧记录的哈希来强行覆盖。没有旧包或记录不匹配时，先核对备份与现有文件再处理。不支持自动修复被改坏的 block、自动移走其他覆盖包或关闭安全软件。

## 大版本更新后的预检和回退

游戏或模组更新后，旧 LocRes / `_P.pak` 可能已经对不上新原文，甚至不再是可读的 V11 容器。先预检，再决定要不要写入。

- `install.ps1 -Action Preflight` 做和安装相同的定位、哈希、V11 包尾和配置规划，但**不创建备份、不写 PAK、不改 Game.ini**。包尾不是 221 字节的可读 V11（魔数、版本、索引 SHA1）时直接失败，并说明更新很可能使补丁失效。已安装模组的 VersionName 和清单不一致时，预检失败；安装本身仍只警告并继续，避免把版本字符串差异当成已经证明不能装。
- 安装在复制任何文件之前做同一次 V11 检查。失败时磁盘上的游戏文件保持原样。
- `-Action Rollback -BackupPath <某次安装打印的备份目录>` 按该目录的 `snapshot.json` 把当时备份的字节拷回去。它不猜测“最新一次”，也不会删掉备份目录。回退只恢复那些字节，**不能证明游戏会加载或显示汉化**。安装过程中如果写入失败，脚本仍会自动回退这一次改过的文件并留下备份。
- 工作目录里的补丁还可以用 `asa_localize.py` 的 `preflight`、`export`、`apply`、`rollback`。`apply` 会先检查 LocRes v3 / LocMeta v1 / 未压缩 V11，通过后才备份将被覆盖的文件；预检失败则一个字节都不写。提供当前原文后，如果补丁里的源指纹一个都对不上，视为补丁已过期并停止。`export` 读失败时不会留下半份 CSV。这些都是离线文件检查，`runtime_tested` 保持 false，不能写成游戏内生效。
