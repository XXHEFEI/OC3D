/**
 * Dormant OpenClaw prompt for the future 2D-to-3D path.
 *
 * No active page loads this file.  It preserves the hand-off contract without
 * carrying a local Python path, Meshy key, or OpenClaw model configuration.
 */

// A future reconnect must opt into a real model run explicitly.  Mock mode is
// the safe default for this dormant interface.
const GEN_USE_MOCK = true;

function buildGenPrompt(comboId, taskId) {
  const mockFlag = GEN_USE_MOCK ? ' --mock' : '';
  const setStatus = [
    "import os, sys; os.environ['PYTHONIOENCODING'] = 'utf-8'",
    "sys.path.insert(0, os.environ['OC3D_PROJECT_DIR'])",
    'from task_state import set_status',
  ].join('\n');

  return `
定制曦曦升维任务：combo=${comboId}，task_id=${taskId}。
本任务只生成可下载的 3D 文件，不发送打印任务。

执行环境必须已由外部运维提供 OC3D_PROJECT_DIR；可选的
OC3D_GENERATOR_PYTHON 指向具备生成依赖的 Python。不要读取或展示任何模型
服务凭据，也不要修改 OpenClaw 配置。

## 步骤 1 — 标记开始
\`\`\`python
${setStatus}
set_status('${taskId}', 'running', step='generating', progress=5, message='升维生成中...')
\`\`\`

## 步骤 2 — 生成
\`\`\`bash
export PYTHONIOENCODING=utf-8
"\${OC3D_GENERATOR_PYTHON:-python3}" "$OC3D_PROJECT_DIR/generate_3d.py" \
  --combo ${comboId} --task-id ${taskId} --out-dir "$OC3D_PROJECT_DIR/work/${taskId}"${mockFlag}
\`\`\`
- 输出含「✅ Generated」才算成功；失败时写 failed 后停止。

## 步骤 3 — 完成
\`\`\`python
${setStatus}
set_status('${taskId}', 'done', step='done', progress=100,
  download_url='/api/download/${taskId}', qr_url='/api/qr/${taskId}',
  message='模型已生成，可扫码或下载')
\`\`\`
`.trim();
}
