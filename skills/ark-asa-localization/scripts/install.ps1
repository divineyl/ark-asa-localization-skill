param(
    [ValidateSet('Install','Uninstall','Detect')][string]$Action = 'Install',
    [string]$GamePath = '',
    [string]$SteamPath = '',
    [string]$ManifestPath = '',
    [switch]$NonInteractive
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (!$ManifestPath) { $ManifestPath = Join-Path $PackageRoot 'manifest.json' }
try {
    $Manifest = [IO.File]::ReadAllText([IO.Path]::GetFullPath($ManifestPath)) | ConvertFrom-Json
    if ($Manifest.schema -ne 1 -or [string]$Manifest.mod_id -notmatch '^[1-9][0-9]{0,11}$') { throw 'Invalid manifest schema or mod_id.' }
    $Target = [string]$Manifest.target
    if ($Target -cnotmatch '^[A-Za-z][A-Za-z0-9_]{2,47}$' -or $Target -in @('Engine','ShooterGame')) { throw 'Invalid localization target.' }
    $PakName = [string]$Manifest.pak_name
    if ($PakName -cnotmatch '^[A-Za-z0-9_.-]+_P\.pak$' -or $PakName.IndexOf($Target,[StringComparison]::OrdinalIgnoreCase) -lt 0) { throw 'PAK basename must include the target and end in _P.pak.' }
    $PakHash = [string]$Manifest.pak_sha256
    if ($PakHash -cnotmatch '^[a-f0-9]{64}$') { throw 'Invalid PAK SHA256.' }
    $ModId = [string]$Manifest.mod_id
    $ExpectedVersion = [string]$Manifest.mod_version
    if (!$ExpectedVersion) { throw 'mod_version is required.' }
} catch { Write-Host ('清单错误：' + $_.Exception.Message) -ForegroundColor Red; exit 1 }
$TargetPath = '../../../ShooterGame/Content/Localization/' + $Target
$DefaultPath = '../../../ShooterGame/Content/Localization/ShooterGame'
$BeginMarker = '; ' + $Target + ' BEGIN - managed by installer'
$EndMarker = '; ' + $Target + ' END - managed by installer'

function Get-Hash([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}

function Get-GameRoot([string]$Path) {
    $Path = $Path.Trim().Trim('"')
    if (!(Test-Path -LiteralPath $Path)) { return }
    $current = [IO.Path]::GetFullPath($Path.Trim().Trim('"'))
    if (Test-Path -LiteralPath $current -PathType Leaf) { $current = Split-Path -Parent $current }
    for ($i = 0; $i -lt 14 -and $current; $i++) {
        $exe = Join-Path $current 'ShooterGame\Binaries\Win64\ArkAscended.exe'
        $be = Join-Path $current 'ShooterGame\Binaries\Win64\ArkAscended_BE.exe'
        if (((Test-Path -LiteralPath $exe -PathType Leaf) -or (Test-Path -LiteralPath $be -PathType Leaf)) -and
            (Test-Path -LiteralPath (Join-Path $current 'ShooterGame\Content\Paks') -PathType Container)) {
            return $current.TrimEnd('\')
        }
        $parent = Split-Path -Parent $current
        if ($parent -eq $current) { break }
        $current = $parent
    }
}

function Find-Games {
    $steamRoots = @()
    if ($SteamPath) {
        $steamRoots += $SteamPath
    } else {
        foreach ($key in @('HKCU:\Software\Valve\Steam','HKLM:\SOFTWARE\WOW6432Node\Valve\Steam')) {
            $value = Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
            if ($value) { $steamRoots += @($value.SteamPath, $value.InstallPath) | Where-Object { $_ } }
        }
        if (${env:ProgramFiles(x86)}) { $steamRoots += Join-Path ${env:ProgramFiles(x86)} 'Steam' }
        foreach ($drive in @(Get-PSDrive -PSProvider FileSystem)) {
            foreach ($name in @('Steam','SteamLibrary','Program Files (x86)\Steam')) {
                $steamRoots += Join-Path $drive.Root $name
            }
        }
    }
    $libraries = @($steamRoots)
    foreach ($steam in @($steamRoots | Sort-Object -Unique)) {
        $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
        if (Test-Path -LiteralPath $vdf -PathType Leaf) {
            $text = [IO.File]::ReadAllText($vdf)
            foreach ($m in [regex]::Matches($text, '"(?:path|\d+)"\s+"([^"]+)"')) {
                $p = $m.Groups[1].Value.Replace('\\','\')
                if ([IO.Path]::IsPathRooted($p)) { $libraries += $p }
            }
        }
    }
    $results = @()
    foreach ($lib in @($libraries | Where-Object { $_ } | Sort-Object -Unique)) {
        $candidates = @((Join-Path $lib 'steamapps\common\ARK Survival Ascended'))
        $manifest = Join-Path $lib 'steamapps\appmanifest_2399830.acf'
        if (Test-Path -LiteralPath $manifest -PathType Leaf) {
            $m = [regex]::Match([IO.File]::ReadAllText($manifest), '"installdir"\s+"([^"]+)"')
            if ($m.Success -and $m.Groups[1].Value -notmatch '[\\/:]') {
                $candidates += Join-Path (Join-Path $lib 'steamapps\common') $m.Groups[1].Value
            }
        }
        foreach ($candidate in $candidates) {
            $found = Get-GameRoot $candidate
            if ($found) { $results += $found }
        }
    }
    return @($results | Sort-Object -Unique)
}

function Find-Mods([string]$Root) {
    $results = @()
    # These are candidate directories only. Confirm identity from the uplugin,
    # rather than trusting a folder name, cache, registry record or download ZIP.
    foreach ($relative in @('ShooterGame\Binaries\Win64\ShooterGame\Mods\83374',
                            'ShooterGame\Mods\83374','ShooterGame\Mods')) {
        $base = Join-Path $Root $relative
        if (!(Test-Path -LiteralPath $base -PathType Container)) { continue }
        $queue = New-Object Collections.Queue
        $queue.Enqueue(@($base, 0))
        while ($queue.Count -gt 0) {
            $node = $queue.Dequeue()
            foreach ($entry in @(Get-ChildItem -LiteralPath $node[0] -Force -ErrorAction SilentlyContinue)) {
                if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
                if ($entry.PSIsContainer) {
                    if ($node[1] -lt 4) { $queue.Enqueue(@($entry.FullName, ($node[1] + 1))) }
                } elseif ($entry.Extension -eq '.uplugin') {
                    try {
                        $meta = [IO.File]::ReadAllText($entry.FullName) | ConvertFrom-Json
                        if ($meta.Description -match ('cf_ugcID=' + [regex]::Escape($ModId) + '(?=[&#\s]|$)')) {
                            $results += [pscustomobject]@{ Path=$entry.DirectoryName; Version=$meta.VersionName }
                        }
                    } catch { Write-Warning ('无法读取模组描述：' + $entry.FullName) }
                }
            }
        }
    }
    return @($results | Sort-Object -Property Path -Unique)
}

function Read-Ini([string]$Path) {
    $bytes = [byte[]]@()
    if (Test-Path -LiteralPath $Path -PathType Leaf) { $bytes = [IO.File]::ReadAllBytes($Path) }
    $offset = 0
    $encoding = New-Object Text.UTF8Encoding($false, $true)
    $prefix = [byte[]]@()
    if ($bytes.Length -ge 4 -and (($bytes[0] -eq 255 -and $bytes[1] -eq 254 -and $bytes[2] -eq 0 -and $bytes[3] -eq 0) -or
        ($bytes[0] -eq 0 -and $bytes[1] -eq 0 -and $bytes[2] -eq 254 -and $bytes[3] -eq 255))) {
        throw 'Game.ini 为 UTF-32，未修改。请先将其另存为 UTF-8。'
    } elseif ($bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191) {
        $prefix = [byte[]]@(239,187,191); $offset = 3
    } elseif ($bytes.Length -ge 2 -and $bytes[0] -eq 255 -and $bytes[1] -eq 254) {
        $encoding = New-Object Text.UnicodeEncoding($false, $false, $true)
        $prefix = [byte[]]@(255,254); $offset = 2
    } elseif ($bytes.Length -ge 2 -and $bytes[0] -eq 254 -and $bytes[1] -eq 255) {
        $encoding = New-Object Text.UnicodeEncoding($true, $false, $true)
        $prefix = [byte[]]@(254,255); $offset = 2
    }
    try { $text = $encoding.GetString($bytes, $offset, ($bytes.Length - $offset)) }
    catch { throw '无法无损读取 Game.ini 的编码，未修改。请先备份并另存为 UTF-8。' }
    if ($text.Contains([char]0)) { throw 'Game.ini 包含异常空字符，未修改。' }
    if ($text.Contains("`r") -and !$text.Contains("`n")) { throw '仅 CR 换行的 Game.ini 暂不支持，未修改。' }
    $newline = "`r`n"
    $m = [regex]::Match($text, '\r\n|\n|\r')
    if ($m.Success) { $newline = $m.Value }
    return [pscustomobject]@{ Text=$text; Encoding=$encoding; Prefix=$prefix; Newline=$newline }
}

function Plan-Ini($Doc, [bool]$Remove, [bool]$OwnsBlock) {
    $text = $Doc.Text
    $sections = @([regex]::Matches($text, '(?im)^[ \t]*\[Internationalization\][ \t]*(?:[;#][^\r\n]*)?\r?$'))
    if ($sections.Count -gt 1) { throw 'Game.ini 有多个 Internationalization 节，请合并后再运行，未修改。' }
    $blockPattern = '(?ms)^' + [regex]::Escape($BeginMarker) + '\r?\n(.*?)^' + [regex]::Escape($EndMarker) + '(?:\r?\n|$)'
    $blocks = @([regex]::Matches($text, $blockPattern))
    if ($blocks.Count -gt 1) { throw '检测到重复的安装标记，未修改。' }
    $beginCount = [regex]::Matches($text, [regex]::Escape($BeginMarker)).Count
    $endCount = [regex]::Matches($text, [regex]::Escape($EndMarker)).Count
    if ($beginCount -ne $blocks.Count -or $endCount -ne $blocks.Count) { throw '安装标记被修改，未修改 Game.ini。' }
    if ($Remove) {
        if ($OwnsBlock -and $blocks.Count -eq 1) {
            $block = $blocks[0]
            # Keep default paths and any personal edits inside the managed block.
            $kept = [regex]::Replace($block.Groups[1].Value,
                '(?im)^[ \t]*LocalizationPaths[ \t]*=[ \t]*' + [regex]::Escape($TargetPath) + '[ \t]*\r?$(?:\n)?', '')
            $text = $text.Remove($block.Index, $block.Length).Insert($block.Index, $kept)
        }
        return [pscustomobject]@{ Text=$text; OwnsBlock=$false }
    }
    $start = $text.Length; $end = $text.Length
    if ($sections.Count -eq 1) {
        $start = $sections[0].Index + $sections[0].Length
        $next = [regex]::Match($text.Substring($start), '(?m)^[ \t]*\[')
        if ($next.Success) { $end = $start + $next.Index }
    }
    $body = $text.Substring($start, ($end - $start))
    if ($body -match '(?im)^[ \t]*[+.!-]LocalizationPaths[ \t]*=') {
        throw 'Game.ini 使用了 LocalizationPaths 数组操作符，需先人工核对，未修改。'
    }
    foreach ($m in [regex]::Matches($body, '(?im)^[ \t]*LocalizationPaths[ \t]*=[ \t]*([^\r\n]*)')) {
        if ($m.Groups[1].Value.Trim().Trim('"').Replace('\','/').TrimEnd('/') -ieq $TargetPath) {
            # Markers alone do not prove this installation owns existing content.
            return [pscustomobject]@{ Text=$text; OwnsBlock=$OwnsBlock }
        }
    }
    if ($blocks.Count) { throw '原有安装标记内的加载路径被更改，未修改。请先检查配置。' }
    $lines = @($BeginMarker)
    if ($body -notmatch '(?im)^[ \t]*LocalizationPaths[ \t]*=') { $lines += 'LocalizationPaths=' + $DefaultPath }
    $lines += 'LocalizationPaths=' + $TargetPath
    $lines += $EndMarker
    $addition = ($lines -join $Doc.Newline) + $Doc.Newline
    if ($sections.Count -eq 0) { $addition = '[Internationalization]' + $Doc.Newline + $addition }
    if ($end -gt 0 -and $text[$end - 1] -ne "`n" -and $text[$end - 1] -ne "`r") { $addition = $Doc.Newline + $addition }
    $text = $text.Insert($end, $addition)
    return [pscustomobject]@{ Text=$text; OwnsBlock=$true }
}

function Write-Ini([string]$Path, $Doc, [string]$Text) {
    [byte[]]$data = @($Doc.Prefix) + @($Doc.Encoding.GetBytes($Text))
    [IO.File]::WriteAllBytes($Path, $data)
    if ((Read-Ini $Path).Text -cne $Text) { throw 'Game.ini 写入校验失败。' }
}

function Invoke-Installer {
    $game = ''
    if ($GamePath) {
        $game = Get-GameRoot $GamePath
        if (!$game) { throw '指定目录不是 Steam Windows 飞升客户端：需有 ArkAscended.exe 和 Content\Paks。不会安装到进化或独立服务器。' }
    } else {
        $games = @(Find-Games)
        if ($games.Count -eq 1) { $game = $games[0] }
        elseif ($NonInteractive) { throw ('检测到 ' + $games.Count + ' 个飞升客户端，无法唯一确定。请用 -GamePath 指定目录。') }
        elseif ($games.Count -gt 1) {
            for ($i = 0; $i -lt $games.Count; $i++) { Write-Host ('[' + ($i + 1) + '] ' + $games[$i]) }
            $choice = Read-Host '找到多个飞升客户端，请输入序号'
            $number = 0
            if (![int]::TryParse($choice, [ref]$number) -or $number -lt 1 -or $number -gt $games.Count) { throw '无效序号，未安装。' }
            $game = $games[$number - 1]
        } else {
            Write-Host '未在 Steam 库找到飞升。可以从 Steam 管理菜单打开“浏览本地文件”。'
            $manual = Read-Host '请粘贴飞升目录，也可以粘贴它的 Mods 目录'
            $game = Get-GameRoot $manual
            if (!$game) { throw '没有找到有效的飞升客户端，未安装。' }
        }
    }
    Write-Host ('飞升目录：' + $game)
    $mods = @(Find-Mods $game)
    foreach ($mod in $mods) {
        Write-Host ('模组 ' + $ModId + '：' + $mod.Path)
        if ($mod.Version -ne $ExpectedVersion) {
            Write-Warning ('模组版本不同；期望 ' + $ExpectedVersion + '，实际 ' + $mod.Version + '。词条匹配需要重新验证。')
        }
    }
    if ($Action -ne 'Uninstall' -and !$mods.Count) {
        throw ('未检测到已解压安装的模组 ' + $ModId + '。请先在飞升内下载并启用该模组，退出后重试。')
    }
    Write-Host '汉化资源安装到飞升 Content\Paks；原模组文件保持原样。'
    if ($Action -eq 'Detect') { Write-Host '检测完成，没有写入文件。'; return }
    if (Get-Process -Name 'ArkAscended','ArkAscended_BE','ArkAscendedServer' -ErrorAction SilentlyContinue) {
        throw '请先完全退出飞升客户端和服务器，再运行脚本。'
    }
    $pak = Join-Path $game ('ShooterGame\Content\Paks\' + $PakName)
    $ini = Join-Path $game 'ShooterGame\Saved\Config\Windows\Game.ini'
    $statePath = Join-Path $game ('ShooterGame\Saved\LocalizationInstallers\' + $Target + '.json')
    $source = Join-Path $PackageRoot $PakName
    $state = $null
    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        $state = [IO.File]::ReadAllText($statePath) | ConvertFrom-Json
        if ($state.Schema -ne 1 -or $state.GameRoot -ine $game -or $state.PakHash -ne $PakHash -or $state.Target -cne $Target -or $state.ModId -ne $ModId) { throw '已有安装记录不匹配，未修改。' }
    }
    if ($Action -eq 'Uninstall' -and !$state) { Write-Host '没有本工具的安装记录，未修改任何文件。'; return }
    if ($Action -eq 'Install') {
        if (!(Test-Path -LiteralPath $source -PathType Leaf) -or (Get-Hash $source) -ne $PakHash) {
            throw '安装包中的 PAK 丢失或校验不符，请重新解压完整安装包。'
        }
    }
    $pakExists = Test-Path -LiteralPath $pak -PathType Leaf
    if ($pakExists -and (Get-Hash $pak) -ne $PakHash) { throw '目标位置已有内容不同的同名 PAK，未覆盖。请先将它另行备份。' }
    $doc = Read-Ini $ini
    $ownsBlock = $false
    if ($state) { $ownsBlock = [bool]$state.OwnsBlock }
    $plan = Plan-Ini $doc ($Action -eq 'Uninstall') $ownsBlock
    $ownsPak = !$pakExists
    if ($state) { $ownsPak = (!$pakExists -or [bool]$state.OwnsPak) }
    $newStateText = ''
    if ($Action -eq 'Install') {
        $newStateText = [pscustomobject]@{Schema=1; Target=$Target; ModId=$ModId; GameRoot=$game; PakHash=$PakHash; OwnsPak=$ownsPak; OwnsBlock=$plan.OwnsBlock} | ConvertTo-Json
        if ($state -and $pakExists -and $plan.Text -ceq $doc.Text -and $state.OwnsBlock -eq $plan.OwnsBlock) {
            Write-Host '已安装，PAK 校验通过，加载路径已存在，无需重复修改。'; return
        }
    }
    $backup = Join-Path $game ('ShooterGame\Saved\LocalizationBackups\' + $Target + '\' +
        (Get-Date -Format 'yyyyMMdd_HHmmss_fff') + '_' + [guid]::NewGuid().ToString('N').Substring(0,8))
    [void][IO.Directory]::CreateDirectory($backup)
    $snapshots = @()
    foreach ($pair in @(@($ini, 'Game.ini'), @($pak, $PakName), @($statePath, 'install-state.json'))) {
        $exists = Test-Path -LiteralPath $pair[0] -PathType Leaf
        $copy = Join-Path $backup $pair[1]
        if ($exists) {
            [IO.File]::Copy($pair[0], $copy, $false)
            if ((Get-Hash $copy) -ne (Get-Hash $pair[0])) { throw '备份校验失败，未安装。' }
        }
        $snapshots += [pscustomobject]@{Path=$pair[0]; Backup=$copy; Existed=$exists; Changed=$false}
    }
    $snapshots | Select-Object Path,Backup,Existed | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backup 'snapshot.json') -Encoding UTF8
    try {
        if ($Action -eq 'Install') {
            if (!$pakExists) {
                $snapshots[1].Changed = $true
                [IO.File]::Copy($source, $pak, $false)
                if ((Get-Hash $pak) -ne $PakHash) { throw '复制后的 PAK 校验失败。' }
            }
        } elseif ($ownsPak -and $pakExists) {
            $snapshots[1].Changed = $true
            [IO.File]::Delete($pak)
        }
        if ($plan.Text -cne $doc.Text) {
            [void][IO.Directory]::CreateDirectory((Split-Path -Parent $ini))
            # Mark only after successful write; failed locked-file writes leave bytes unchanged.
            # On partial write, compare bytes to the snapshot and restore below as well.
            Write-Ini $ini $doc $plan.Text
            $snapshots[0].Changed = $true
        }
        $snapshots[2].Changed = $true
        if ($Action -eq 'Install') {
            [void][IO.Directory]::CreateDirectory((Split-Path -Parent $statePath))
            [IO.File]::WriteAllText($statePath, $newStateText, (New-Object Text.UTF8Encoding($false)))
        } else { [IO.File]::Delete($statePath) }
    } catch {
        $failure = $_.Exception.Message
        $restoreFailures = @()
        foreach ($snap in $snapshots) {
            $changed = $snap.Changed
            if (!$changed -and (Test-Path -LiteralPath $snap.Path -PathType Leaf)) {
                $changed = !$snap.Existed -or ((Get-Hash $snap.Path) -ne (Get-Hash $snap.Backup))
            }
            if (!$changed) { continue }
            try {
                if ($snap.Existed) { [IO.File]::Copy($snap.Backup, $snap.Path, $true) }
                elseif (Test-Path -LiteralPath $snap.Path -PathType Leaf) { [IO.File]::Delete($snap.Path) }
            } catch { $restoreFailures += $snap.Path }
        }
        if ($restoreFailures.Count) { throw ('操作失败：' + $failure + '；部分文件回退失败：' + ($restoreFailures -join ', ') + '；原始备份：' + $backup) }
        throw ('操作失败，文件已回退：' + $failure + '；备份：' + $backup)
    }
    Write-Host ('备份目录：' + $backup)
    if ($Action -eq 'Install') {
        Write-Host '小包文件和 Game.ini 加载路径已安装。请用简体中文启动飞升测试。'
        Write-Host '研究测试版：安装校验通过不代表 ASA 已加载词条，尚无游戏内实测结论。'
    } else { Write-Host '已卸载本工具添加的小包和路径，保留其他配置及后续修改。' }
}

try { Invoke-Installer }
catch { Write-Host ('失败：' + $_.Exception.Message) -ForegroundColor Red; exit 1 }
