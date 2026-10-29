# 提取、审稿和排查

若任务限定“只能在指定工作目录写入”，使用 `python -B` 或设置 `PYTHONDONTWRITEBYTECODE=1`，避免 import 在安装的 skill 目录生成 `__pycache__`。本工具的封包验证临时输出放在 build 工作目录下并自动清理；外部工具也应按实际能力限制临时目录，不默认其没有其他缓存副作用。

## 原件与格式

先记录 ZIP 名、大小、SHA-256、CRC、成员相对路径和 `.uplugin`。`inspect-zip` 拒绝路径逃逸、Windows 保留名、大小写重名、符号链接、加密 ZIP 和超限展开量；默认展开总量上限 4 GiB。只写全新输出目录，原 ZIP 不变。体积更大的合法模组可在审查清单后调用 Python API 显式调整 `max_unpacked`，不要盲目提高限制。

`.uplugin.Description` 的 `cf_ugcID`、FriendlyName、VersionName、SDKVersion 是识别线索，不是所有文件都相容的证明；缺字段时不要猜 ID。ASA PAK 内可能只有 AssetRegistry，主体在 IoStore。两个案例的原 PAK 都不是 repak 可直接读的标准 V11 输入；用于输出的小包是另一回事。

ASE 中观察到的 `402/7`、`404/10` 包头/偏移/导出表和 `.z` 缓存安装方法不适用于 ASA Zen chunks。保留扩展名不等于保留布局。新版本资产、加密或缺 global/script objects 等情况应记录具体错误，选择已验证工具或 DevKit 路线，不能修改版本头骗过解析器。

## 外部解包（工作副本）

retoc v0.1.5 在 Barsboldia 容器上使用：

```powershell
retoc.exe info "mod.utoc"
retoc.exe verify "mod.utoc"
retoc.exe unpack "mod.utoc" "work/extracted"
```

`.ucas` 放在对应 `.utoc` 旁。记录 info 的版本、压缩方式、mount point、包数量和 verify/解包结果。`unpack` 输出仍可能是 Zen chunks，不是可套用 ASE 写入器的 legacy 包。未将 retoc 或其可能加载的 Oodle DLL 放入 skill 或交付包；获取与授权见来源参考。

## 扫描能力及审稿

`inventory` 是只读候选扫描器，不是完整 Unreal 包解析器。输出相对路径、整文件哈希、字节 offset/end、kind、source、可见 namespace/key；默认 `display=false`。

- `ftext-base`：有限 flags + Base history 布局；重叠 lookahead 防止连续零字节造成漏检。即使结构匹配，仍须结合上下文确认。
- `textconst`：受限 ASCII Blueprint LocalizedText 常量候选。
- `fstring` / `stringconst`：ASCII 属性或 Blueprint 常量候选，包含内部名称、材质参数和噪声。
- Unicode 源可由 Base FText 读出；非 ASCII FString 全量扫描、复杂 FText history、StringTable 引用、纹理文字和完整字节码反编译不在脚本保证范围。

确认显示项后为该条增加：

```json
{"display":true,"translation":"切换火炮姿态","review_note":"骑乘按键帮助标签，结合 HUD 上下文确认"}
```

这是现有记录上的增补字段，不是完整 plan。禁止删除其 `path/source_sha256/offset/kind/source/namespace/key` 定位信息。`validate-plan` 会重算源件哈希、重新扫描并比对实际位置；嵌在显式文本中的 FString 不可另选为全局 CRC 项。

不要翻译事件/函数、资源路径、配置查找键、对象名、材质参数、刷怪条目名、按键绑定 ID。纯英文不是显示证据；人工 review_note 也不能替代对字段用途的检查。JSON UI 应只改确认的显示值，不改 JSON 键/事件/权限/绑定。

同原文不同身份允许不同译法；同 namespace/key 的原文或译文冲突应停下来分析，不按最后一条覆盖。无键同原文经 CRC 合并后无法保留上下文差异，冲突时不要生成这种候选。

## 文本校验与漏项

保留数字及正负号、百分比、printf/命名占位符、富文本标签顺序、CRLF/换行数量。`10% damage` 不能被识别成 `% d`；校验器宁可报告需人工处理的差异，也不自动改玩法数值。还应人工检查不影响 token 的必要空格、语气和布局。

`parse_jsonc` 用字符串状态处理注释和尾逗号；注释用空白替换，避免 `1/*x*/2` 变成 12；保留引号中的 `//`、`/*`、`,]`。对不合法内容报错，禁止正则盲删后当成合法配置。

扫描计数不代表界面覆盖率。游戏中的英文可能来自服务器消息、动态格式、内置目标、其他模组、存档名称或纹理。记录“原文 + 界面/触发动作 + 客户端/服务器来源 + 版本”，再定位。若全包无效先查挂载、目标登记和语言；局部无效先查实际身份及原文精确字节，不先重做大底包。
