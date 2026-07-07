/**
 * prompt.js — OpenClaw 打印提示词（唤醒经典 / 打印半）。
 *
 * printing_classic.html 引用，向 OpenClaw Agent 发送 3MF 直连打印指令。
 * bambu.py 通过 LAN (MQTT + FTPS) 直接与打印机通信。
 *
 * 步骤 2 的监控用后台非阻塞方式启动（bash nohup + disown，对应 master 版
 * PowerShell 的 Start-Process）：Agent 发完指令立即返回，不等打印完成——
 * 真正的 done/failed 由 monitor_bridge.py 自己在后台跑完后写 task_state，
 * 前端靠 /ws/task/{id} 收到（monitor_bridge.py 本身与 master 一致，未改）。
 */

const WORK_DIR   = "/Users/hefei/Desktop/MX_intern/OC3D";
const SKILLS_DIR = "/Users/hefei/Desktop/MX_intern/OC3D";
const STOCK_DIR  = "/Users/hefei/Desktop/MX_intern/OC3D/static/3D";
const PRINTER_SERIAL = '20P6BJ652100030';
const PRINTER_IP     = '172.20.10.6';
const ACCESS_CODE    = 'be45c93c';


function buildPrintPrompt(modelName, taskId, modelFile) {
  const modelPath = `${STOCK_DIR}/${modelFile}`;
  const bambuDir  = `${SKILLS_DIR}/bambu-studio-ai/scripts`;
  const setStatus = [
    `import sys, os; os.environ['PYTHONIOENCODING'] = 'utf-8'`,
    `sys.path.insert(0, '${WORK_DIR}')`,
    `from task_state import set_status`,
  ].join('\n');

  return `
打印任务：${modelName}，模型 ${modelPath}，task_id=${taskId}。

bambu.py 直连打印机（LAN MQTT + FTPS），上传 .3mf 并下发打印指令；
monitor_bridge.py 后台持续轮询并写状态文件，后端自动推送前端。

## 你的职责
只需按顺序执行命令。步骤 1 等待完成，步骤 2 用后台方式启动后立即继续，
不要等它跑完。不要轮询状态、不要解析输出、不要推送前端——这些由
monitor_bridge.py 和后端 WebSocket 自动完成。

**重要**：每一步失败都必须 set_status failed，确保前端能看到失败信息。

## 规则
- 按步骤逐字执行命令，不改参数，不改路径，不改环境变量。
- 不修改任何文件。
- 命令只跑一次，失败不重试。
- 判定标准见各步骤说明。

## 步骤 1 — 发送打印文件
\`\`\`bash
export BAMBU_MODE=local BAMBU_IP="${PRINTER_IP}" BAMBU_SERIAL="${PRINTER_SERIAL}" BAMBU_ACCESS_CODE="${ACCESS_CODE}" PYTHONIOENCODING=utf-8
python3 "${bambuDir}/bambu.py" print "${modelPath}" --confirmed
\`\`\`
- 输出含「Started printing」→ 更新状态后继续步骤 2。
- **失败**（不含 Started printing 或命令异常退出）→ 立即执行：
\`\`\`python
${setStatus}
set_status('${taskId}', 'failed', step='print', progress=0, message='${modelName} 打印发送失败')
\`\`\`
如果失败就停止，不再执行后续步骤。

成功后更新状态：
\`\`\`python
${setStatus}
set_status('${taskId}', 'sending', step='sending', progress=5, message='${modelName} 已发送至打印机')
\`\`\`

## 步骤 2 — 后台启动监控，定时获取打印状态
用 nohup 把 monitor_bridge.py 丢到后台运行，命令必须立即返回，不要等待它跑完。
\`\`\`bash
export BAMBU_MODE=local BAMBU_IP="${PRINTER_IP}" BAMBU_SERIAL="${PRINTER_SERIAL}" BAMBU_ACCESS_CODE="${ACCESS_CODE}" PYTHONIOENCODING=utf-8
nohup python3 "${WORK_DIR}/monitor_bridge.py" "${taskId}" --interval 15 > "/tmp/monitor_${taskId}.log" 2>&1 &
disown
\`\`\`
这条命令应该几乎立即返回（不阻塞）。
- **命令本身执行出错**（不是"打印还没完成"，而是命令报错无法启动）→ 执行：
\`\`\`python
${setStatus}
set_status('${taskId}', 'failed', step='monitoring', progress=0, message='${modelName} 监控启动失败')
\`\`\`
停止，不再执行后续步骤。

## 步骤 3 — 确认监控运行中
\`\`\`python
${setStatus}
set_status('${taskId}', 'printing', step='printing', progress=10, message='${modelName} 打印进行中，后台监控已就位')
\`\`\`
告诉用户：${modelName} 打印已启动！打印监控在后台运行中，完成后会自动更新状态。
`.trim();
}
