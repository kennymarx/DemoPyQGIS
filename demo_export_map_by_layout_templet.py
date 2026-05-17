# -*- coding: utf-8 -*-
"""
PyQGIS Standalone Script
- 运行环境：Miniforge 虚拟环境 qgis_sample（conda-forge 安装的 QGIS）
- 功能：加载 等高线.gpkg + 天地图-影像地图.tif，
       套用 layoutmodel.qpt 布局模板，输出 PNG
- 不使用 QgsLayoutExporter，改用 QPainter 直接渲染
"""

import os
import sys
from datetime import datetime


# ─────────────────────────────────────────────
# 0. 路径配置
# ─────────────────────────────────────────────
DATA_DIR   = r"C:\Users\Administrator\Desktop\QGIS\TestQGISMapProject"
'''
# 等高线
GPK_PATH   = os.path.join(DATA_DIR, "extent_contour-火龙.gpkg")
# 天地图影像地图
TIF_PATH   = os.path.join(DATA_DIR, "map_extent-火龙.tif")
# 地图范围
SHP_PATH   = os.path.join(DATA_DIR, "地图范围-火龙.gpkg")  
'''
GPK_PATH   = os.path.join(DATA_DIR, "extent_contour.gpkg")
# 天地图影像地图
TIF_PATH   = os.path.join(DATA_DIR, "map_extent.tif")
# 地图范围
SHP_PATH   = os.path.join(DATA_DIR, "地图范围.gpkg")  

# 打印模板
QPT_PATH   = os.path.join(DATA_DIR, "layoutmodel-new.qpt")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
DPI        = 300

# ─────────────────────────────────────────────
# 1. 初始化 QGIS Application
#    Miniforge/conda-forge Windows 布局：
#      - qgis 模块在  <prefix>/Library/python
#      - QGIS DLL 在  <prefix>/Library/bin
# ─────────────────────────────────────────────

# 1-a. 让 Python 能 import qgis
_conda_prefix = sys.prefix  # e.g. C:/ProgramData/miniforge3/envs/qgis_sample
_qgis_python  = os.path.join(_conda_prefix, "Library", "python")
if _qgis_python not in sys.path:
    sys.path.insert(0, _qgis_python)

# 1-b. 让系统能找到 QGIS 的 DLL（必须在 import qgis 之前设置）
_qgis_bin = os.path.join(_conda_prefix, "Library", "bin")
os.environ["PATH"] = _qgis_bin + os.pathsep + os.environ.get("PATH", "")
# Python 3.8+ 需要显式添加 DLL 搜索目录
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(_qgis_bin)

from qgis.core import QgsApplication

qgis_prefix = os.path.join(_conda_prefix, "Library")  # Windows conda 布局
QgsApplication.setPrefixPath(qgis_prefix, True)
qgs = QgsApplication([], False)   # False = 无 GUI
qgs.initQgis()

# ─────────────────────────────────────────────
# 2. 导入其余 QGIS 模块（必须在 initQgis 之后）
# ─────────────────────────────────────────────
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsPrintLayout,
    QgsReadWriteContext,
    QgsVectorFileWriter,
    QgsLayoutItemMap,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsWkbTypes,
    QgsFeature
)
from qgis.PyQt.QtXml import QDomDocument


def reproject_to_3857(layer: QgsVectorLayer) -> QgsVectorLayer:
    """
    QGIS无头模式下，将矢量图层重投影为 EPSG:3857
    不使用native算法，纯QGIS API遍历要素重投影
    """
    # 目标坐标系 EPSG:3857
    target_crs = QgsCoordinateReferenceSystem("EPSG:3857")
    
    # 获取当前图层坐标系
    source_crs = layer.crs()
    
    # 如果已经是3857，直接返回原图层
    if source_crs.authid() == target_crs.authid():
        print(f"[OK] 图层 {layer.name()} 已是 EPSG:3857，无需重投影")
        return layer.clone()

    print(f"[INFO] 图层 {layer.name()} 从 {source_crs.authid()} 重投影为 {target_crs.authid()}")
    # 初始化坐标转换工具（QGIS标准API，非native）
    temp_project = QgsProject.instance()
    transform = QgsCoordinateTransform(
        source_crs,
        target_crs,
        temp_project
    )

    # 创建输出内存图层（保持几何类型、字段不变）
    geom_type = QgsWkbTypes.displayString(layer.wkbType())
    uri = f"{geom_type}?crs=EPSG:3857"
    output_layer = QgsVectorLayer(uri, f"{layer.name()}", "memory")

    # 复制字段结构
    output_layer.dataProvider().addAttributes(layer.fields())
    output_layer.updateFields()

    # 遍历所有要素 → 重投影 → 添加到新图层
    output_features = []
    for feat in layer.getFeatures():
        new_feat = QgsFeature(feat)
        
        # 核心：重投影几何（纯QGIS API）
        geom = feat.geometry()
        if not geom.isEmpty():
            geom.transform(transform)  # 关键重投影方法
            new_feat.setGeometry(geom)
        
        output_features.append(new_feat)

    # 批量写入要素
    output_layer.dataProvider().addFeatures(output_features)
    
    
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.fileEncoding = "UTF-8"
    transform_context = temp_project.transformContext()
    
    # 保存shp_layer到文件，格式为GeoPackage
    QgsVectorFileWriter.writeAsVectorFormatV3(
            output_layer,
            os.path.join(OUTPUT_DIR, "地图范围_3857.gpkg"),
            transform_context,
            options
        )
    
    return output_layer

# ─────────────────────────────────────────────
# 3. 加载图层到项目
# ─────────────────────────────────────────────
project = QgsProject.instance()

# 影像图层（栅格，底层）
tif_layer = QgsRasterLayer(TIF_PATH, "天地图-影像地图")
if not tif_layer.isValid():
    print(f"[错误] 栅格图层加载失败：{TIF_PATH}")
    qgs.exitQgis()
    sys.exit(1)

# 等高线矢量图层（GeoPackage，上层）
# GeoPackage 单图层写法：路径|layername=图层名  或直接路径（取第一个图层）
gpk_layer = QgsVectorLayer(GPK_PATH, "等高线", "ogr")
if not gpk_layer.isValid():
    # 尝试显式指定 layername
    gpk_layer = QgsVectorLayer(f"{GPK_PATH}|layername=等高线", "等高线", "ogr")
if not gpk_layer.isValid():
    print(f"[错误] 矢量图层加载失败：{GPK_PATH}")
    qgs.exitQgis()
    sys.exit(1)

# 栅格先加（渲染在下），矢量后加（渲染在上）
project.addMapLayer(tif_layer)
project.addMapLayer(gpk_layer)

# 地图范围矢量图层（shp，仅加入项目，设为不可见，不参与布局渲染）
shp_layer = QgsVectorLayer(SHP_PATH, "地图范围", "ogr")
if not shp_layer.isValid():
    print(f"[错误] 矢量图层加载失败：{SHP_PATH}")
    qgs.exitQgis()
    sys.exit(1)
# addMapLayer 第二个参数 False = 不自动加入图层树（即不可见）
# shp_layer.setCrs(tif_layer.crs())
shp_layer = reproject_to_3857(shp_layer)
project.addMapLayer(shp_layer, False)
print(f"[OK] 已加载图层：{tif_layer.name()}、{gpk_layer.name()}、{shp_layer.name()}（不可见）")


# 以栅格图层的 CRS 作为项目 CRS
project.setCrs(shp_layer.crs())
print(f"[OK] 项目 CRS：{shp_layer.crs().authid()}")

# ─────────────────────────────────────────────
# 4. 加载 QPT 布局模板
# ─────────────────────────────────────────────
if not os.path.exists(QPT_PATH):
    print(f"[错误] 找不到布局模板：{QPT_PATH}")
    qgs.exitQgis()
    sys.exit(1)

with open(QPT_PATH, "r", encoding="utf-8") as f:
    qpt_xml = f.read()

doc = QDomDocument()
ok, err_msg, err_line, err_col = doc.setContent(qpt_xml)

if not ok:
    print(f"[错误] QPT XML 解析失败（第 {err_line} 行，列 {err_col}）：{err_msg}")
    qgs.exitQgis()
    sys.exit(1)

layout = QgsPrintLayout(project)

layout.initializeDefaults()

ctx = QgsReadWriteContext()
# 用 QPT 文件所在目录作为相对路径基准，确保 ./图标库/... 等相对路径能正确解析
# 若直接用 project.pathResolver()，基准为项目文件目录（未保存项目时为空，
# 退回进程工作目录），导致 SVG 等资源找不到
from qgis.core import QgsPathResolver
ctx.setPathResolver(QgsPathResolver(QPT_PATH))

# loadFromTemplate 返回 (list[QgsLayoutItem], Optional[bool])
# False（默认）：不清除现有布局，直接用模板内容覆盖（推荐）
# True：先清空布局里的所有元素，再加载模板
# 建议：如果你是刚创建的空布局，用默认 False 即可
#loaded_items, loaded_ok = layout.loadFromTemplate(doc, ctx, False)
loaded_items, loaded_ok = layout.loadFromTemplate(doc, ctx, True)
if not loaded_ok:
    print("[错误] 布局模板加载失败，请检查 QPT 文件格式")
    qgs.exitQgis()
    sys.exit(1)

print(f"[OK] {QPT_PATH} 布局模板已加载，共 {len(loaded_items)} 个布局项")

# ─────────────────────────────────────────────
# 5. 注入布局变量（模板所有 dataDefinedWidth/Height/Position 均依赖这三个变量）
#    @Longest_side : 页面最长边目标尺寸（mm），决定整体输出大小
#    @Blank_pct    : 下方图例/空白区占页面的比例（0~1）
#    @Border       : 地图边框宽度（mm）
#    这三个变量必须在 refresh 之前设置，否则页面和所有元素尺寸全为 NULL
# ─────────────────────────────────────────────
from qgis.core import QgsExpressionContextUtils

#LONGEST_SIDE = 420.0   # mm，A3 横向最长边；可按需调整
LONGEST_SIDE = 1000.0   
#BLANK_PCT    = 0.2     # 下方空白/图例区占 20%
BLANK_PCT    = 0.15 
#BORDER       = 5.0     # mm，边框宽度
BORDER       = 10.0

QgsExpressionContextUtils.setLayoutVariable(layout, "Longest_side", LONGEST_SIDE)
QgsExpressionContextUtils.setLayoutVariable(layout, "Blank_pct",    BLANK_PCT)
QgsExpressionContextUtils.setLayoutVariable(layout, "Border",       BORDER)
print(f"[OK] 布局变量已设置：Longest_side={LONGEST_SIDE}, Blank_pct={BLANK_PCT}, Border={BORDER}")

# ─────────────────────────────────────────────
# 6. 绑定地图项图层 + 设置显示范围，然后整体刷新布局
# ─────────────────────────────────────────────
map_extent     = shp_layer.extent()
layers_to_show = [gpk_layer, tif_layer]   # 上层在前，下层在后

map_items_found = 0
for item in layout.items():
    if isinstance(item, QgsLayoutItemMap):
        map_items_found += 1
        item.setFollowVisibilityPreset(False)
        item.setKeepLayerSet(True)
        item.setLayers(layers_to_show)
        item.setCrs(tif_layer.crs())
        item.setExtent(map_extent)

# test
print(f"tif_layer crs: {tif_layer.crs()}")
print(f"gpk_layer crs:{gpk_layer.crs()}")
print(f"shp_layer crs: {shp_layer.crs()}")
print(f"map_extent: {map_extent.toString(4)}")

if map_items_found == 0:
    print("[警告] 布局模板中未找到地图项（QgsLayoutItemMap）")

# 刷新整个布局：触发所有 dataDefinedWidth/Height 表达式重新求值
layout.refresh()

# 刷新后打印地图项实际范围（供调试）
for item in layout.items():
    if isinstance(item, QgsLayoutItemMap):
        print(f"[OK] 地图项 '{item.id()}' 实际范围：{item.extent().toString(4)}")

# ─────────────────────────────────────────────
# 7. 计算渲染区域：取所有布局元素的场景包围盒联合
#    renderPageToImage 只渲染页面边界内的内容；
#    若页面动态表达式未能扩大页面，元素会被截掉。
#    改用 renderRegionToImage，以所有元素的实际包围盒为准，确保完整输出。
# ─────────────────────────────────────────────
from qgis.core import QgsLayoutExporter
from qgis.PyQt.QtCore import QSize, QRectF

page = layout.pageCollection().page(0)
if page is None:
    print("[错误] 布局中未找到页面")
    qgs.exitQgis()
    sys.exit(1)

# 先读取 pageSize（可能是动态计算后的正确值，也可能是旧值）
page_sz = page.pageSize()
print(f"[OK] page.pageSize() = {page_sz.width():.2f} x {page_sz.height():.2f} mm")

# 计算所有布局元素的场景包围盒（单位：mm，scene 坐标系）
all_items = layout.items()
if all_items:
    union_rect = all_items[0].sceneBoundingRect()
    for it in all_items[1:]:
        union_rect = union_rect.united(it.sceneBoundingRect())
    print(f"[OK] 所有元素包围盒（场景mm）：({union_rect.x():.2f},{union_rect.y():.2f}) "
          f"{union_rect.width():.2f} x {union_rect.height():.2f} mm")
else:
    union_rect = QRectF(0, 0, page_sz.width(), page_sz.height())

# 渲染区域：取 page 尺寸 与 元素包围盒 的较大值，确保不截断任何元素
render_w = max(page_sz.width(),  union_rect.right())
render_h = max(page_sz.height(), union_rect.bottom())
# 起点始终从 (0,0) 开始（场景原点即页面左上角）
render_rect = QRectF(0, 0, render_w, render_h)
print(f"[OK] 最终渲染区域：{render_w:.2f} x {render_h:.2f} mm")

px_w = int(render_w / 25.4 * DPI)
px_h = int(render_h / 25.4 * DPI)
print(f"[OK] 输出像素：{px_w} x {px_h} @ {DPI} DPI")

# ─────────────────────────────────────────────
# 8. 用 renderRegionToImage 渲染完整布局区域
# ─────────────────────────────────────────────
exporter = QgsLayoutExporter(layout)
image = exporter.renderRegionToImage(render_rect, QSize(px_w, px_h))

if image.isNull():
    print("[错误] 渲染失败，返回了空图像（内存不足或布局无效）")
    qgs.exitQgis()
    sys.exit(1)

# ─────────────────────────────────────────────
# 9. 保存 PNG
# ─────────────────────────────────────────────
os.makedirs(OUTPUT_DIR, exist_ok=True)
timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
output_png = os.path.join(OUTPUT_DIR, f"map_{timestamp}.png")

saved = image.save(output_png, "png")
if saved:
    print(f"[OK] PNG 已保存：{output_png}")
else:
    print(f"[错误] PNG 保存失败，请检查输出目录权限：{OUTPUT_DIR}")

# ─────────────────────────────────────────────
# 10. 清理退出
# ─────────────────────────────────────────────
qgs.exitQgis()
