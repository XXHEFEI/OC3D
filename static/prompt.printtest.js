/**
 * prompt.printtest.js — TEST VARIANT: 3MF 直接打印流程（跳过 2D→3D 生成）。
 *
 * 用户选择形象 → OpenClaw Agent 直连打印机 → 发送对应 .3mf 文件打印。
 * bambu.py 通过 LAN (MQTT + FTPS) 直接与打印机通信，无需 Bambu Studio。
 *
 * Not wired permanently into index.html. To use: temporarily swap the
 * <script src> in templates/index.html from prompt.js to prompt.printtest.js,
 * then swap back to prompt.js when done testing.
 *
 */

const WORK_DIR   = "C:\\Users\\i26293\\Desktop\\ip-print-web";
const SKILLS_DIR = "C:\\Users\\i26293\\Desktop\\ip-print-web";
const STOCK_DIR  = "C:\\Users\\i26293\\Desktop\\ip-print-web\\static\\3D";
const PRINTER_SERIAL = '20P6BJ652100030';
const PRINTER_IP     = '10.238.235.64';
const ACCESS_CODE    = 'c1957072';


const COSTUMES = [
  { id: 'costume_1', name: '猫1', image: '/static/ip-costumes/1.png', model: 'cat.gcode.3mf' },
  { id: 'costume_2', name: '猫2', image: '/static/ip-costumes/2.png', model: 'cat.gcode.3mf' },
  { id: 'painter',   name: '画家',   image: '/static/ip-costumes/画家.png', model: 'cat.gcode.3mf' },
];

function buildPrompt(costume, taskId) {
  const modelPath = `${STOCK_DIR}\\${costume.model}`;
  const bambuDir  = `${SKILLS_DIR}\\bambu-studio-ai\\scripts`;
  const setStatus  = [
    `import sys, os; os.environ['PYTHONIOENCODING'] = 'utf-8'`,
    `sys.path.insert(0, '${WORK_DIR}')`,
    `from task_state import set_status`,
  ].join('\n');

  return `
打印任务：${costume.name}，模型 ${modelPath}，task_id=${taskId}。

bambu.py 直连打印机（LAN MQTT + FTPS），上传 .3mf 并下发打印指令；
monitor_bridge.py 持续轮询并写状态文件，后端自动推送前端。

## 你的职责
只需按顺序执行命令，等每条命令自然结束。不要轮询状态、不要解析输出、
不要推送前端——这些由 monitor_bridge.py 和后端 WebSocket 自动完成。

## 规则
- 按步骤逐字执行命令，不改参数，不改路径，不改环境变量。
- 不修改任何文件。
- 命令只跑一次，失败不重试。
- 判定标准见各步骤说明。

## 步骤 1 — 发送打印
\`\`\`powershell
$env:BAMBU_MODE = "local"; $env:BAMBU_IP = "${PRINTER_IP}"; $env:BAMBU_SERIAL = "${PRINTER_SERIAL}"; $env:BAMBU_ACCESS_CODE = "${ACCESS_CODE}"; $env:PYTHONIOENCODING = "utf-8"
python "${bambuDir}\\bambu.py" print "${modelPath}" --confirmed
\`\`\`
输出含「Started printing」→ 继续。否则 set_status failed，停止。

成功后更新状态：
\`\`\`python
${setStatus}
set_status('${taskId}', 'printing', step='printing', progress=0, message='${costume.name} 已发送至打印机，监控中...')
\`\`\`

## 步骤 2 — 等待打印完成
此命令阻塞运行直到打印结束自动退出。耐心等待，不要中断、不要并发。
\`\`\`powershell
$env:BAMBU_MODE = "local"; $env:BAMBU_IP = "${PRINTER_IP}"; $env:BAMBU_SERIAL = "${PRINTER_SERIAL}"; $env:BAMBU_ACCESS_CODE = "${ACCESS_CODE}"; $env:PYTHONIOENCODING = "utf-8"
python "${WORK_DIR}\\monitor_bridge.py" ${taskId} --interval 60
\`\`\`
脚本内部自行轮询、写状态、判断退出。你不需要解析输出。

## 步骤 3 — 完成
\`\`\`python
${setStatus}
set_status('${taskId}', 'done', step='done', progress=100, message='${costume.name} 打印完成')
\`\`\`
告诉用户：${costume.name} 打印已完成。
`.trim();
}
