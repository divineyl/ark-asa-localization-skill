# 身份、语言资源与实验边界

## 身份不是英文字符串本身

优先保留经过上下文审查的 namespace/key。源指纹来自精确原文，不来自中文。源文本中的空格、标点、CRLF 变化都会影响候选匹配。namespace/key 的 hash 与 source hash 是不同用途。

本工具的 v3 key hash 使用外部 CityHash64 对 UTF-16LE（无终止符）计算，折叠为 `(low32 + high32 * 23) & 0xffffffff`；空串返回 0。已与两个案例及 50,332 个基线身份的原有 key/namespace hash 比较。

ASCII 源指纹采用 CRC32(UTF-32LE)，与案例使用的原文指纹一致。脚本对非 ASCII 源拒绝自动计算，避免将未经核对的 Unicode/TCHAR 规则冒充证据。确有独立读取的原始资源指纹时，在 plan 记录 `source_hash`（uint32）与 `source_hash_origin`（资源/条目出处），并重新校验；不要将 arbitrary 手填值称为 observed。

`make_identities` 默认只收显式键。显式启用候选时：

- 空 namespace 的显式键可附加 GraphLiteral 别名，证据为 `namespace-alias-candidate`。
- 无显式键、经过显示审查且不嵌在 keyed 文本里的原文，可生成 Content、GraphLiteral、空 namespace 的 source CRC 候选。
- 显式标签不因为有相同 FString 表示就自动生成全局 CRC；不能用候选命名空间替换已观察的原 namespace。

候选会进入全局本地化身份空间，不能以自定义目标目录就认定隔离了键冲突。相同原文的语境差异与其他目标冲突需要审查和运行测试。

## 新建目标的四个资源

目标示例 Mod123456（实际应按模组取唯一标识）：

```text
ShooterGame/Content/Localization/Mod123456/Mod123456.locmeta
ShooterGame/Content/Localization/Mod123456/en/Mod123456.locres
ShooterGame/Content/Localization/Mod123456/zh/Mod123456.locres
ShooterGame/Content/Localization/Mod123456/zh-Hans/Mod123456.locres
```

`en` 存原文，`zh` 与 `zh-Hans` 存中文，使用相同身份和源指纹。不覆盖本体 ShooterGame.locres。LocMeta v1：16-byte GUID、uint8 version=1、native culture FString、native resource 相对路径 FString、int32 culture 数量、各 culture FString。GUID 字节与本地已回读的格式一致；资源目录名、文件基名和 native resource 路径一起校验。

LocRes v3：16-byte magic、uint8 version=3、uint64 string-table offset、uint32 total key count；namespace 及 key 记录带 uint32 hash，键记录带 source hash、字符串索引；字符串表包含文本及引用数量。FString 空串可用长度 0，ASCII 长度含终止符，UTF-16LE 使用负 code-unit 长度（含终止符，不能按 Python 字符数计数）。中文与非 BMP 译文已通过独立读取测试。

附带 serializer 是新建本地化资源的工具，不是通用 Zen/IoStore 写入器。它不复制未知版本的二进制结构，不进行 cooked 资产长度或导出偏移修补。

## 加载需要单独验证

UE5.3 的参考实现按 localization path 的 basename 查找 `.locres/.locmeta`。存在 `LoadFromDirectory` API，不能证明 ASA 主加载器会扫描任意新增文件名。

本实验通过 Saved/Config/Windows/Game.ini 的 `[Internationalization] LocalizationPaths` 登记新目标，不使用 GEngineIni 来替代。保存配置的重复裸键与 DefaultGame.ini 源层级的 `+/-/./!` 数组操作不能混用。安装器保留已有裸键；遇到复杂操作符或重复 section 就停止，交由人工核对。

参考 UE 源码不等于 ASA 定制源码；PAK V11 挂载优先级、语言链、Saved 配置有效性、自定义目标加载和动态 FString 的本地化入口，都仍需要真实客户端验证。
