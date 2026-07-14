# 经典打印 AMS 报错 — 交接 TODO（给接手的 agent）

> 现场 demo 的"经典打印"链路。目标：网页选模型→选黑/白→确认打印→打印机把猫打出来。
> 本文件自足，不用读别的 TODO。项目根：`/Users/hefei/Desktop/MX_intern/OC3D`（分支 macos）。

## 现在卡在哪（最新状态）

FTP 553（中文文件名）**已解决**（切片文件已全部重命名为 ASCII）。
当前报错：**`0700-8012「多次获取 AMS 映射表失败」`**（错误码后面那串如 110514/114614 是**时间戳** HH:MM:SS，不是子错误码，别被误导——一直是同一个 0700-8012）。

### ✅ 已定位的真正根因（重要！）
**槽位是切片时写进 gcode 的 `M620 S{n}A` 载料指令，不是我们代码写死的。** 实测：

| 文件 | gcode 里 `M620 S?A` 载料槽 | 料丝编号 |
|---|---|---|
| `cat.gcode.3mf`（历史能打） | **S0**（槽0=外置/默认，不需要真 AMS） | 1 |
| 所有 `*_black` | **S2**（物理 AMS 槽 C，索引 2） | G-code 逻辑料丝 2 |
| 所有 `*_white` | **S1**（物理 AMS 槽 B，索引 1） | G-code 逻辑料丝 1 |

所以：黑模型被切成"从 AMS 槽2 载料"、白从槽1；而这台打印机 AMS 没被稳定识别 → 取不到映射表 → 0700-8012。
cat 能打是因为它用槽0。命令层的 `ams_mapping` 不是改写 G-code 的 `M620`，而是告诉打印机每个项目逻辑料丝对应哪个物理 AMS 槽。
当前映射已按切片文件写入：黑传 `-1,-1,2`，白传 `-1,1`；未使用的逻辑料丝用 `-1` 占位。

排查命令（看某文件切到哪个槽）：
```bash
python3 -c "import zipfile,re;g=zipfile.ZipFile('static/3D_model/spring_cat_black.gcode.3mf').read('Metadata/plate_1.gcode').decode('utf-8','ignore');print(re.search(r'M620 S(\d+)A',g).group(0))"
```

## 两条修复路线（二选一，需现场决策）

**路 A —— 真双色（最接近产品目标，且切片不用重做）**
- 现有切片已天然支持：黑→槽2、白→槽1。
- 前提：**修好打印机↔AMS 硬件连接**（0700-8012 是打印机没稳定读到 AMS，硬件层面，软件改不了）。
  在打印机屏幕上要能稳定看到 4 个槽。
- 物理装料：**黑丝→AMS 槽2（第3槽/C），白丝→AMS 槽1（第2槽/B）**（槽0索引 A=0/B=1/C=2/D=3）。
- 代码上：`prompt.js` 按颜色传项目索引映射：黑 `--ams-mapping "-1,-1,2"`，白 `--ams-mapping "-1,1"`，让 G-code 逻辑料丝映射到对应物理槽。
- 结果：选黑打黑、选白打白自动成立。

**路 B —— 单色应急（不依赖 AMS）**
- 在 Bambu Studio 里把 8 个模型**全部重切成走"外置料架/单色/槽0"**（切出来 gcode 应是 `M620 S0` 或无 AMS 载料），
  同名覆盖 `static/3D_model/*.gcode.3mf`。
- 保留 `--ams-mapping "0"`（或无所谓，因为 gcode 不再依赖 AMS）。
- 结果：单色，操作员按需换主喷嘴料卷；UI 选色只是预览。

> 注：之前尝试的"命令层 `use_ams=false` / `--ams-mapping 0`"路线**已证明无效**，因为槽位烤在 gcode 内部。
> 别再在这条路上耗——要么修 AMS 硬件走路 A，要么重切走路 B。

## 打印链路（谁调谁）

```
select_classic.html → preview_classic.html(选色) → printing_classic.html
  → POST /api/generate {ip_id} 拿 task_id
  → gateway.sendMessage(buildPrintPrompt(...))  // prompt.js 生成提示词
  → OpenClaw Agent 执行提示词里的 bash：
       python3 <OC3D>/bambu-studio-ai/scripts/bambu.py print <切片路径> --confirmed --ams-mapping "<按颜色生成的项目索引映射>"
  → bambu.py：FTP 上传 .3mf 到打印机 + MQTT project_file 起打
  → monitor_bridge.py 后台轮询写 task_state，前端经 /ws/task/{id} 收状态
```

- 切片文件目录（打印真读这里）：`static/3D_model/`（ASCII 名，如 `spring_cat_black.gcode.3mf`）
- `prompt.js` 里 `STOCK_DIR = .../static/3D_model`，打印命令按文件名传黑 `-1,-1,2` 或白 `-1,1`
- `ips/list.json`：每个 IP 有 `turntable`(中文转台文件夹) + `models{黑,白}`(ASCII 切片名)

## ⚠️ 关键坑：有两个 bambu.py（这是之前排查最久的点）

1. `<OC3D>/bambu-studio-ai/scripts/bambu.py` —— prompt.js 明确指向这份（在 git 仓库里）
2. `/Users/hefei/Desktop/openclaw-home/.openclaw/workspace/skills/bambu-studio-ai/scripts/bambu.py`
   —— OpenClaw 技能副本（**不在 git 仓库**，是 agent 可能实际跑的那份）

两份实现不同，且旧副本原来有个 bug：`use_ams = bool(ams_mapping)` → `bool([0])=True`，
导致 `--ams-mapping "0"` 关不掉 AMS。**已把两份的 use_ams 逻辑都改成 `any(m not in (0,-1) for m in mapping)`**
（`[0]`→`use_ams=False`）。**改动清单见下。**

## 已做的改动（大多未提交）

已提交（macos 分支 `04c97d5`）：升维改纯视觉演示等（与本打印问题无关）。

**未提交 / 需注意：**
- `static/prompt.js`：`STOCK_DIR`→`static/3D_model`；打印命令按文件名传黑 `-1,-1,2` 或白 `-1,1`
- `templates/printing_classic.html`：prompt.js 引入加 `?v=6`（缓存刷新，避免浏览器继续使用旧提示词）
- `templates/preview_classic.html`、`templates/select_classic.html`：打印文件名与转台文件夹名解耦
  （select 传 `tt`/`mb`/`mw`；preview 用 `tt` 取帧、按颜色取 `mb`/`mw` 打印）
- `ips/list.json`：加 `turntable` 字段 + `models` 改 ASCII 名
- `static/3D_model/` 8 个切片重命名为 ASCII（spring/cloud/ring/catkeychain × black/white）
- **`main.py`**：`STOCK_PRINT_3MF`→`static/3D_model/cat.gcode.3mf`
- **OpenClaw 副本 bambu.py（不在仓库！）**：已同步项目索引映射参数和 `use_ams` 逻辑。
  **别的机器部署时这份修复不会跟着 git 走，要么手动同步，要么让该机直接用 OC3D 仓库那份。**
- `bambu-studio-ai/scripts/bambu.py`（OC3D 版）：**已还原为提交版**（之前试过在这里清洗文件名，已撤销，改走重命名方案）

## 下一步要做的

**先和用户定走路 A 还是路 B（见上）。** 然后：

**若走路 A（真双色）：**
1. 修打印机↔AMS 连接，屏幕上能稳定看到 4 个槽。
2. 黑丝插 AMS 槽2、白丝插槽1。
3. 保持 `static/prompt.js` 的按颜色映射：黑传 `-1,-1,2`，白传 `-1,1`；确认浏览器拿到 `prompt.js?v=6`。
4. 网页硬刷新（Cmd+Shift+R，拿新 prompt.js）→ 打印 → 应选黑打黑、选白打白。

**若走路 B（单色）：**
1. Bambu Studio 重切 8 个模型为外置料架/槽0，同名覆盖 `static/3D_model/*.gcode.3mf`。
2. 用上面排查命令确认新 gcode 是 `M620 S0`。
3. 网页硬刷新 → 打印 → 单色出件。

> 已完成的代码侧修复：prompt.js 按黑/白传项目索引映射、printing_classic.html 更新到 `?v=6`，
> 两份 bambu.py 都按项目索引解释 `ams_mapping`，并避免把 `filament_sequence.json` 误当成物理槽位。

## 排查命令（有用）

```bash
# 看两份 bambu.py 的 use_ams 是否都已修
grep -n "use_ams = " <OC3D>/bambu-studio-ai/scripts/bambu.py
grep -n "use_ams = " /Users/hefei/Desktop/openclaw-home/.openclaw/workspace/skills/bambu-studio-ai/scripts/bambu.py
# 看切片实际要哪个料丝（filament: N，1=紫 2=白 3=黑；不是槽位）
python3 -c "import zipfile;print([l for l in zipfile.ZipFile('static/3D_model/spring_cat_black.gcode.3mf').read('Metadata/plate_1.gcode').decode('utf-8','ignore').splitlines()[:60] if l.startswith('; filament:')])"
# 打印机侧 AMS 实际状态（需打印机在线、局域网可达）
BAMBU_MODE=local BAMBU_IP=<printer-ip> BAMBU_ACCESS_CODE=<access-code> python3 bambu-studio-ai/scripts/bambu.py ams
```

## 若要做"真·选色即打对应色"（AMS 多色，后续）

- 前提：先修好**打印机↔AMS 硬件连接**（`0700-8012` 是打印机没稳定读到 AMS，不是软件）。
  在打印机屏幕上要能稳定看到 4 个槽。
- 切片里：黑用料丝 3、白用料丝 2（工程料丝编号，1索引：1=紫 2=白 3=黑）。
- 物理槽位（0索引 A/B/C/D = 0/1/2/3）与料丝编号是两回事，要核对 AMS 实际装料位置。
- 届时把 prompt.js 的 `--ams-mapping "0"` 改成按颜色传对应槽位（黑传黑槽、白传白槽），
  并去掉 use_ams=false 的强制。**这套先不做，当前单色能打就行。**

## 约束
- Git 写操作（commit/push）必须先跟用户确认。当前一堆改动**未提交**。
- 别动升维/换装侧（那边已是纯视觉演示，与打印无关）。
