/**
 * OpenClaw print-prompt builder.
 *
 * This file deliberately contains no OpenClaw provider settings, model keys,
 * printer address, serial number, or access code.  Those values belong to the
 * already-configured OpenClaw host environment.
 */

// The sliced files keep the project filament index in the G-code:
// black: logical filament 2 -> physical AMS slot 2 (C)
// white: logical filament 1 -> physical AMS slot 1 (B)
function getAmsMapping(modelFile) {
  const name = (modelFile || '').toLowerCase();
  if (name.includes('_black.gcode.3mf')) return '-1,-1,2';
  if (name.includes('_white.gcode.3mf')) return '-1,1';
  return '';
}

function buildPrintPrompt(modelName, taskId, modelFile) {
  const amsMapping = getAmsMapping(modelFile);
  // Values starting with -1 must be passed with = so argparse treats them as
  // the value of --ams-mapping rather than another option.
  const amsMappingArg = amsMapping ? ` --ams-mapping="${amsMapping}"` : '';
  const setStatus = [
    "import os, sys; os.environ['PYTHONIOENCODING'] = 'utf-8'",
    "sys.path.insert(0, os.environ['OC3D_PROJECT_DIR'])",
    'from task_state import set_status',
  ].join('\n');

  return `
打印任务：${modelName}，切片文件 ${modelFile}，task_id=${taskId}。

本仓库只提供 OpenClaw 调用接口。执行环境已由现场运维预先配置：
- OC3D_PROJECT_DIR：本仓库绝对路径。
- BAMBU_MODE、BAMBU_IP、BAMBU_SERIAL、BAMBU_ACCESS_CODE：打印机本机环境变量。
不要读取、显示、回传或修改这些环境变量的值，也不要创建或修改配置文件。

bambu.py 通过 LAN MQTT + FTPS 发送已切片的 3MF；monitor_bridge.py 在后台
写入任务状态，后端 WebSocket 会自动推送进度。

## 规则
- 逐字执行下列命令，不改参数或路径；命令只跑一次，失败不重试。
- 不要轮询打印机、解析输出或直接推送前端。
- 输出含「Started printing」才算发送成功；失败时写 task_state 为 failed 后停止。

## 步骤 1 — 发送打印文件
\`\`\`bash
export PYTHONIOENCODING=utf-8
python3 "$OC3D_PROJECT_DIR/bambu-studio-ai/scripts/bambu.py" print \
  "$OC3D_PROJECT_DIR/static/3D_model/${modelFile}" --confirmed${amsMappingArg}
\`\`\`
- 失败时立即执行并停止：
\`\`\`python
${setStatus}
set_status('${taskId}', 'failed', step='print', progress=0, message='${modelName} 打印发送失败')
\`\`\`

## 步骤 2 — 后台启动监控
\`\`\`bash
export PYTHONIOENCODING=utf-8
nohup python3 "$OC3D_PROJECT_DIR/monitor_bridge.py" "${taskId}" --interval 15 \
  > "/tmp/monitor_${taskId}.log" 2>&1 &
disown
\`\`\`
- 监控无法启动时写 failed 后停止；后台命令启动成功后不要等待它结束。

## 步骤 3 — 标记监控已就位
\`\`\`python
${setStatus}
set_status('${taskId}', 'printing', step='printing', progress=10,
           message='${modelName} 打印进行中，后台监控已就位')
\`\`\`
告诉用户：打印已启动，完成后页面会自动更新。
`.trim();
}
