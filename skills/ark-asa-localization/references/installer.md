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
