/**
 * prompt.generate.js — 定制曦曦（换装升维）流程的提示词 + 数据。
 *
 * 与 prompt.js（打印体验）平行、互不相干：这套【不连打印机、不切片】，
 * 只把换装升维成 3D 文件(.stl)供用户扫码下载带走。
 *
 * 用法：把 templates/index.html 的 <script src="/static/prompt.js"> 换成
 * 本文件即可（沿用现有 UI 逻辑：渲染 COSTUMES 卡片 → 选一个 → 按钮 →
 * buildPrompt → task_state 状态 → 下载/二维码）。UI 文件无需改动。
 *
 * 开发期 USE_MOCK=true：generate_3d.py 走 --mock，不调 Meshy、零额度。
 * 真演示前改成 false，并在服务端配好 MESHY_API_KEY。
 */

const WORK_DIR = "/Users/hefei/Desktop/MX_intern/OC3D";
const USE_MOCK = true;   // true=占位零额度；false=真调 Meshy

// 24 套搭配 = 6 件衣服 × 4 个配饰（与 combos.json 的 id 保持一致）。
// 卡片缩略图暂用占位（真实换装预览图由美术补；UI/缩略图你来定）。
const COSTUMES = (() => {
  const clothes = [1, 2, 3, 4, 5, 6];
  const accessories = [1, 2, 3, 4];
  const placeholder = '/static/ip-costumes/1.png';
  const list = [];
  for (const c of clothes) {
    for (const a of accessories) {
      list.push({
        id: `c${c}_a${a}`,
        name: `衣服${c}·配饰${a}`,
        image: placeholder,
        combo: `c${c}_a${a}`,
      });
    }
  }
  return list;
})();

function buildPrompt(costume, taskId) {
  const comboId = costume.combo || costume.id;
  const mockFlag = USE_MOCK ? ' --mock' : '';
  const setStatus = [
    `import sys, os; os.environ['PYTHONIOENCODING'] = 'utf-8'`,
    `sys.path.insert(0, '${WORK_DIR}')`,
    `from task_state import set_status`,
  ].join('\n');

  return `
定制曦曦升维任务：搭配 ${costume.name}（combo=${comboId}），task_id=${taskId}。
本任务【不打印】，只把换装升维成 3D 文件(.stl)供用户下载，最后展示二维码。

## 规则
- 按步骤逐字执行命令，不改参数/路径/环境变量。
- 不修改任何文件。命令只跑一次，失败不重试、不找替代方案。
- 判定：命令输出含「✅ Generated」才算成功；否则一律 set_status failed、把原始输出原样发用户、然后停止。

## 步骤 1 — 标记开始
\`\`\`python
${setStatus}
set_status('${taskId}', 'running', step='generating', progress=10, message='${costume.name} 升维生成中...')
\`\`\`

## 步骤 2 — 升维生成（合成视图 → 升维模型 → 出 STL）
此命令阻塞运行直到出文件。耐心等待，不要中断、不要并发。
\`\`\`bash
cd "${WORK_DIR}"
python3 "${WORK_DIR}/generate_3d.py" --combo ${comboId} --out-dir "${WORK_DIR}/work/${taskId}"${mockFlag}
\`\`\`
- 输出含「✅ Generated」→ 执行步骤 3。
- 失败（无「✅ Generated」或异常退出）→ 立即执行并停止：
\`\`\`python
${setStatus}
set_status('${taskId}', 'failed', step='generating', progress=0, message='${costume.name} 升维生成失败')
\`\`\`

## 步骤 3 — 完成，给下载/二维码
\`\`\`python
${setStatus}
set_status('${taskId}', 'done', step='done', progress=100,
  download_url='/api/download/${taskId}',
  qr_url='/api/qr/${taskId}',
  message='${costume.name} 已生成（约10cm），扫码或点击下载 .stl')
\`\`\`
告诉用户：${costume.name} 的 3D 模型已生成，可扫码下载带走。
`.trim();
}
