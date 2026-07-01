/**
 * prompt.generate.js — 定制曦曦（换装升维）的 OpenClaw 提示词构造器。
 *
 * 供 DIY 页面（customize.html）在点"封装"时调用：
 *   POST /api/generate 拿 task_id → gateway.sendMessage(buildGenPrompt(comboId, taskId))
 * combo id 形如 "3_2"（衣3+配2）。本流程【不打印】，只出 .stl 供扫码下载。
 *
 * 开发期 USE_MOCK=true：generate_3d.py 走 --mock，不调 Meshy、零额度。
 * 真演示前改 false，并在服务端配好 MESHY_API_KEY（或 .meshy_key）。
 */

const GEN_WORK_DIR = "/Users/hefei/Desktop/MX_intern/OC3D";
const GEN_USE_MOCK = true; // true=占位零额度；false=真调 Meshy

function buildGenPrompt(comboId, taskId) {
  const mockFlag = GEN_USE_MOCK ? " --mock" : "";
  const setStatus = [
    `import sys, os; os.environ['PYTHONIOENCODING'] = 'utf-8'`,
    `sys.path.insert(0, '${GEN_WORK_DIR}')`,
    `from task_state import set_status`,
  ].join("\n");

  return `
定制曦曦升维任务：搭配 combo=${comboId}，task_id=${taskId}。
本任务【不打印】，只把换装升维成 3D 文件(.stl)供用户扫码下载。

## 规则
- 逐字执行下列命令，不改参数/路径。命令只跑一次，失败不重试、不找替代方案。
- 判定：命令输出含「✅ Generated」才算成功；否则一律 set_status failed、把原始输出原样发用户、然后停止。

## 步骤 1 — 标记开始
\`\`\`python
${setStatus}
set_status('${taskId}', 'running', step='generating', progress=5, message='升维生成中...')
\`\`\`

## 步骤 2 — 升维生成（合成图 → 升维模型 → STL；进度由脚本写入）
此命令阻塞运行直到出文件，耐心等待，不要中断、不要并发。
\`\`\`bash
cd "${GEN_WORK_DIR}"
python3 "${GEN_WORK_DIR}/generate_3d.py" --combo ${comboId} --task-id ${taskId} --out-dir "${GEN_WORK_DIR}/work/${taskId}"${mockFlag}
\`\`\`
- 输出含「✅ Generated」→ 执行步骤 3。
- 失败 → 立即执行并停止：
\`\`\`python
${setStatus}
set_status('${taskId}', 'failed', step='generating', progress=0, message='升维生成失败')
\`\`\`

## 步骤 3 — 完成，给下载/二维码
\`\`\`python
${setStatus}
set_status('${taskId}', 'done', step='done', progress=100,
  download_url='/api/download/${taskId}',
  qr_url='/api/qr/${taskId}',
  message='模型已生成（约10cm），扫码或点击下载 .stl')
\`\`\`
告诉用户：模型已生成，可扫码下载带走。
`.trim();
}
