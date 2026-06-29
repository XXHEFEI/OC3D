"""Final status update for aa60840bba task"""
import sys
sys.path.insert(0, r"C:\Users\i26293\.openclaw\workspace\ip-print-web")
from task_state import set_status

set_status(
    'aa60840bba',
    'done',
    step='done',
    progress=100,
    preview_url='/static/previews/aa60840bba.png',
    download_url='/api/download/aa60840bba',
    message='任务完成！costume_1 .3mf 文件已生成。',
    color_palette=[
        {"hex": "#FDFDFD", "rgb": [253, 253, 253], "pct": 29.7, "family": "white"},
        {"hex": "#A98E6D", "rgb": [169, 142, 109], "pct": 20.7, "family": "brown"},
        {"hex": "#ADBBC6", "rgb": [173, 187, 198], "pct": 15.6, "family": "cyan"},
        {"hex": "#E2E2D9", "rgb": [226, 226, 217], "pct": 14.1, "family": "white"},
        {"hex": "#423730", "rgb": [66, 55, 48], "pct": 12.3, "family": "black"},
        {"hex": "#E8CD86", "rgb": [232, 205, 134], "pct": 7.6, "family": "yellow"},
    ],
    color_groups=[
        {"group_id": 1, "hex": "#ADBBC6", "rgb": [173, 187, 198], "faces": 179, "family": "gray-blue", "pct": 55.9},
        {"group_id": 2, "hex": "#A98E6D", "rgb": [169, 142, 109], "faces": 121, "family": "brown", "pct": 37.8},
        {"group_id": 3, "hex": "#FDFDFD", "rgb": [253, 253, 253], "faces": 20, "family": "white", "pct": 6.3},
    ],
    model_info={
        "dimensions_mm": [80.0, 79.69, 78.58],
        "triangle_count": 320,
        "vertex_count": 162,
        "color_groups": 3,
        "material": "PLA",
        "height_mm": 80,
        "score": 10.0,
    }
)

print("Final status updated for aa60840bba: DONE")
print("Preview: /static/previews/aa60840bba.png")
print("Download: /api/download/aa60840bba")