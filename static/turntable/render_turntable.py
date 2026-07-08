"""
render_turntable.py — 离线渲染经典模型的 360° 转台帧序列（黑/白两色变体）。

从未切片的原始 3mf/stl（含真实网格）渲染多帧透明 PNG，供前端按角度切图
实现"自动旋转 + 手动拖动"的转台预览，替换 preview_classic.html 里现在
"正/侧/背"按钮切图的静态展示方式。
注意：static/3D/*.gcode.3mf 是切片后导出的"发送到打印机"包，不含网格，
必须用切片前的原始设计文件（例如 /Users/hefei/Desktop/MX_intern/3D模型/*.3mf）。

用法:
  python3 render_turntable.py <源文件路径> <输出名>
  例: python3 render_turntable.py "/Users/hefei/Desktop/MX_intern/3D模型/弹簧小猫.3mf" 弹簧小猫

产出（透明背景 PNG，每色 37 帧，0~36，第 36 帧与第 0 帧角度重合，方便按整数
下标闭环）:
  static/turntable/<输出名>/黑/0.png ~ 36.png
  static/turntable/<输出名>/白/0.png ~ 36.png
"""

import argparse
import gc
import os

import numpy as np
import trimesh
import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

BASE = os.path.dirname(os.path.abspath(__file__))

parser = argparse.ArgumentParser()
parser.add_argument("src", help="未切片原始 3mf/stl 路径（需含真实网格）")
parser.add_argument("name", help="输出文件夹名，例如 弹簧小猫")
args = parser.parse_args()

SRC = args.src
STATIC_OUT_DIR = os.path.join(BASE, args.name)

MAX_FACES = 40000  # 网页缩略图用不到打印级精度，超过这个面数就抽稀，换取渲染速度

loaded = trimesh.load(SRC)
if isinstance(loaded, trimesh.Scene):
    # 打印工程文件的场景里可能摆了多份同一个模型（批量打印），只取其中一个实例，
    # 不要用 force="mesh" 把摆盘的所有副本拼在一起渲染。
    mesh = list(loaded.geometry.values())[0]
else:
    mesh = loaded

print(f"原始网格: {len(mesh.vertices)} 顶点 / {len(mesh.faces)} 面")
if len(mesh.faces) > MAX_FACES:
    mesh = mesh.simplify_quadric_decimation(face_count=MAX_FACES)
    print(f"抽稀后: {len(mesh.vertices)} 顶点 / {len(mesh.faces)} 面")

mesh.vertices -= mesh.bounds.mean(axis=0)  # center at origin

verts = mesh.vertices
faces = mesh.faces
face_normals = mesh.face_normals

LIGHT_DIR = np.array([0.4, -0.6, 0.7])
LIGHT_DIR = LIGHT_DIR / np.linalg.norm(LIGHT_DIR)

# 黑色塑料几乎不靠漫反射显形，主要靠高光 + 边缘菲涅尔光勾出轮廓（不然跟深色
# 舞台背景糊在一起），rim 越大边缘越亮；白色塑料漫反射为主，不需要额外补边缘光。
COLOR_VARIANTS = {
    "黑": dict(base=np.array([62, 62, 68]) / 255, ambient=0.32, diffuse=0.40, spec=0.5, shininess=18, rim=0.8),
    "白": dict(base=np.array([238, 238, 240]) / 255, ambient=0.55, diffuse=0.55, spec=0.35, shininess=12, rim=0.0),
}

N_STEPS = 36  # 360° 分成 36 步，额外渲染第 36 帧（=第 0 帧角度）方便下标闭环
RADIUS = np.max(np.linalg.norm(verts, axis=1)) * 1.6


def shade(normals, view_dir, params):
    ndotl = np.clip(normals @ LIGHT_DIR, 0, 1)
    ndotv = np.clip(np.abs(normals @ view_dir), 0.15, 1)
    half_vec = LIGHT_DIR + view_dir
    half_vec = half_vec / np.linalg.norm(half_vec)
    ndoth = np.clip(normals @ half_vec, 0, 1)
    specular = params["spec"] * (ndoth ** params["shininess"])

    # 菲涅尔边缘光：越靠近轮廓（ndotv 越小）越亮，让暗色模型的轮廓在暗背景上也能读出来
    fresnel = (1 - ndotv) ** 2
    rim = params.get("rim", 0.0) * fresnel

    intensity = params["ambient"] + params["diffuse"] * ndotl + rim
    colors = params["base"][None, :] * intensity[:, None] + specular[:, None]
    return np.clip(colors, 0, 1)


for color_name, params in COLOR_VARIANTS.items():
    out_dir = os.path.join(STATIC_OUT_DIR, color_name)
    os.makedirs(out_dir, exist_ok=True)

    for i in range(N_STEPS + 1):
        angle = 360.0 * i / N_STEPS
        fig = Figure(figsize=(6, 6), dpi=140)
        FigureCanvasAgg(fig)
        ax = fig.add_subplot(111, projection="3d")
        ax.set_box_aspect([1, 1, 1])

        elev = 22
        azim = angle
        ax.view_init(elev=elev, azim=azim)

        elev_r = np.radians(elev)
        azim_r = np.radians(azim)
        view_dir = np.array([
            np.cos(elev_r) * np.cos(azim_r),
            np.cos(elev_r) * np.sin(azim_r),
            np.sin(elev_r),
        ])

        colors = shade(face_normals, view_dir, params)
        poly = Poly3DCollection(verts[faces], facecolor=colors, edgecolor="none", linewidths=0)
        poly.set_zsort("average")
        ax.add_collection3d(poly)

        lim = RADIUS
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_zlim(-lim, lim)
        ax.set_axis_off()
        fig.patch.set_alpha(0)
        ax.set_facecolor((0, 0, 0, 0))

        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        out_path = os.path.join(out_dir, f"{i}.png")
        fig.savefig(out_path, transparent=True)
        del poly, ax, fig
        gc.collect()
        print("saved", out_path)

print("done:", STATIC_OUT_DIR)
