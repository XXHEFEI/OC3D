# 转台预览（黑/白帧序列版）

离线渲染的 360° 转台预览：每个模型 2 个配色（黑/白）× 37 帧透明背景 PNG，
前端用一个几十行的 JS 播放器按角度切图，效果是"自动旋转 + 鼠标/手指拖动可
手动转动"，用来替换 `preview_classic.html` 现在"正面/侧面/背面"三个按钮切图
的静态展示方式。

## 目录结构

```
static/turntable/
├── render_turntable.py     # 渲染脚本（源码在这台 Mac 上跑，见下文"怎么加新模型"）
├── README.md                # 本文件
└── 弹簧小猫/                 # 每个模型一个文件夹，文件夹名 = 展示用的模型名
    ├── 黑/
    │   ├── 0.png ~ 36.png   # 37 帧，0~35 用于播放，第 36 帧=第 0 帧角度（闭环用，前端不用）
    └── 白/
        └── 0.png ~ 36.png
```

目前只做了**弹簧小猫**一个模型。云朵小猫 / 戒指小猫 / CatKeychain 还没渲染，
需要的话找我要，或者按下面"怎么加新模型"自己跑。

## 怎么接进 `preview_classic.html`

现在 `preview_classic.html` 里长这样（`templates/preview_classic.html`）：

```html
<div class="stage-center">
    <div class="stage-ground"></div>
    <img id="model-display" src="" class="model-img">
</div>
<div class="controls">
    <button class="angle-btn active" onclick="changeAngle('front', this)">正面</button>
    <button class="angle-btn" onclick="changeAngle('side', this)">侧面</button>
    <button id="btn-back-view" class="angle-btn" onclick="changeAngle('back', this)">背面</button>
</div>
```

配套 JS 是拼 `_front.png` / `_side.png` / `_back.png` 三张固定图 + `changeAngle()`
切图。**这一整块（HTML + JS 里 `imgFront/imgSide/imgBack` 拼路径的逻辑 +
`changeAngle` 函数）都可以整个删掉**，换成下面这套：

```html
<div class="stage-center" id="stage">
    <div class="stage-ground"></div>
    <img id="model-display" src="" class="model-img" style="pointer-events:none;">
</div>
```

（`.stage-center` 保留，加个 `id="stage"` 用来挂拖动事件；`.model-img` 原来的
样式不用动，宽高/居中都还是它）

JS 部分（放在原来 `changeAngle` 的位置）：

```js
const TURNTABLE_FRAME_COUNT = 36; // 0~35 播放，36 是重复帧不用
const stage = document.getElementById('stage');
const modelDisplay = document.getElementById('model-display');

// modelName 换成实际要展示的模型名，需要跟 static/turntable/<这个名字>/ 对上
// 现在只有"弹簧小猫"渲染好了；黑/白哪个默认看具体产品配色，这里先写死"黑"
let turntableColor = '黑';

function turntableSrc(i) {
    const idx = ((i % TURNTABLE_FRAME_COUNT) + TURNTABLE_FRAME_COUNT) % TURNTABLE_FRAME_COUNT;
    return `static/turntable/${modelName}/${turntableColor}/${idx}.png`;
}

let currentFrame = 0;
let autoplayTimer = null;
let resumeTimer = null;

function renderFrame() {
    modelDisplay.src = turntableSrc(currentFrame);
}

function startAutoplay() {
    if (autoplayTimer) return;
    autoplayTimer = setInterval(() => { currentFrame += 1; renderFrame(); }, 60);
}
function stopAutoplay() {
    if (autoplayTimer) { clearInterval(autoplayTimer); autoplayTimer = null; }
}

let dragging = false, dragStartX = 0, dragStartFrame = 0;
function onDragStart(clientX) {
    dragging = true; dragStartX = clientX; dragStartFrame = currentFrame;
    stopAutoplay(); clearTimeout(resumeTimer);
}
function onDragMove(clientX) {
    if (!dragging) return;
    const deltaFrames = Math.round(-(clientX - dragStartX) / 6);
    currentFrame = dragStartFrame + deltaFrames;
    renderFrame();
}
function onDragEnd() {
    if (!dragging) return;
    dragging = false;
    clearTimeout(resumeTimer);
    resumeTimer = setTimeout(startAutoplay, 1200);
}

stage.addEventListener('mousedown', (e) => onDragStart(e.clientX));
window.addEventListener('mousemove', (e) => onDragMove(e.clientX));
window.addEventListener('mouseup', onDragEnd);
stage.addEventListener('touchstart', (e) => onDragStart(e.touches[0].clientX), { passive: true });
window.addEventListener('touchmove', (e) => onDragMove(e.touches[0].clientX), { passive: true });
window.addEventListener('touchend', onDragEnd);

renderFrame();
startAutoplay();
```

`modelName` 用页面已有的、从 URL 参数解析出来的模型名变量就行（原来算
`imgFront/imgSide/imgBack` 用的那个 `basePath`/`modelName` 变量，看你们那边具体
叫什么）——**只要这个值能跟 `static/turntable/` 下的文件夹名对上就行**，对不上
就只是图裂掉，不会报错崩页面。

原来那三个按钮（正面/侧面/背面）和"喵！正面看起来简直完美"那段引导文案可以删掉，
不需要了——现在是连续转动，不是三个固定角度。

完整能跑的参考实现（本机可以直接打开对着抄）：`templates/preview_classic_test.html`
（在同一个仓库里，跑起来是 `http://<host>:8000/preview_classic_test.html`）。

## 怎么加新模型（云朵小猫 / 戒指小猫 / CatKeychain）

```bash
pip install trimesh matplotlib pillow fast_simplification
python3 static/turntable/render_turntable.py "<未切片原始 3mf/stl 路径>" <模型名>
```

**注意**：必须用切片前的原始设计文件（含真实网格），不能用
`static/3D/*.gcode.3mf`——那是切片后导出的"发送到打印机"包，不含网格数据，
渲染不出东西。

跑完自动产出 `static/turntable/<模型名>/黑/` 和 `/白/`，不用再手动挪文件。

如果源文件是"摆盘里放了好几份同一个模型"（批量打印用的工程文件），脚本会自动
只取其中一份来渲染，不会把摆盘上的副本全部糊在一起。
