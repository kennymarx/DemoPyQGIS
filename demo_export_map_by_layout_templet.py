# -*- coding: utf-8 -*-
"""
PyQGIS Standalone Script
- 运行环境：Miniforge 虚拟环境 qgis_sample（conda-forge 安装的 QGIS）
- 功能：加载 等高线.gpkg + 天地图-影像地图.tif，
       套用 layoutmodel.qpt 布局模板，输出 PNG
- 不使用 qgsLayoutExporter，改用 qPainter 直接渲染
"""

import os
import sys
from datetime import datetime

class MapExporter:
    CRS = "EPSG:3857"
    PROJECT_DIR = r"C:\Users\Administrator\Desktop\QGIS\TestQGISMapProject"
    VEC_FILE_EXTENT = os.path.join(PROJECT_DIR, "地图范围.gpkg")
    VEC_FILE_CONTOUR = os.path.join(PROJECT_DIR, "extent_contour.gpkg")
    RASTER_FILE_SAT = os.path.join(PROJECT_DIR, "map_extent.tif")
    OUTPUT = os.path.join(PROJECT_DIR, "output")
    QPT_PATH = os.path.join(PROJECT_DIR, "layoutmodel-new.qpt")
    DPI = 300
    LONGEST_SIDE = 1000.0
    BLANK_PCT = 0.15
    BORDER = 10.0

    def __init__(self):
        self.project = None
        self.qgs_app = None
        self.tif_layer = None
        self.gpk_layer = None
        self.shp_layer = None

    def _init_qgis_environment(self):
        _conda_prefix = sys.prefix
        _qgis_python = os.path.join(_conda_prefix, "Library", "python")
        if _qgis_python not in sys.path:
            sys.path.insert(0, _qgis_python)

        _qgis_bin = os.path.join(_conda_prefix, "Library", "bin")
        os.environ["PATH"] = _qgis_bin + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(_qgis_bin)

        from qgis.core import QgsApplication

        qgis_prefix = os.path.join(_conda_prefix, "Library")
        QgsApplication.setPrefixPath(qgis_prefix, True)
        self.qgs_app = QgsApplication([], False)
        self.qgs_app.initQgis()

        print("[OK] QGIS 环境初始化完成")

    def create_qgis_project(self):
        from qgis.core import (
            QgsProject,
            QgsCoordinateReferenceSystem,
        )

        self.project = QgsProject.instance()
        self.project.setCrs(QgsCoordinateReferenceSystem(self.CRS))
        print(f"[OK] QGIS 项目已创建，CRS = {self.CRS}")

    def _reproject_to_3857(self, layer):
        
        from qgis.core import (
            QgsProject,
            QgsVectorLayer,
            QgsVectorFileWriter,
            QgsCoordinateReferenceSystem,
            QgsCoordinateTransform,
            QgsWkbTypes,
            QgsFeature
        )

        target_crs = QgsCoordinateReferenceSystem("EPSG:3857")
        source_crs = layer.crs()

        if source_crs.authid() == target_crs.authid():
            print(f"[OK] 图层 {layer.name()} 已是 EPSG:3857，无需重投影")
            return layer.clone()

        print(f"[INFO] 图层 {layer.name()} 从 {source_crs.authid()} 重投影为 {target_crs.authid()}")
        temp_project = QgsProject.instance()
        transform = QgsCoordinateTransform(
            source_crs,
            target_crs,
            temp_project
        )

        geom_type = QgsWkbTypes.displayString(layer.wkbType())
        uri = f"{geom_type}?crs=EPSG:3857"
        output_layer = QgsVectorLayer(uri, f"{layer.name()}", "memory")

        output_layer.dataProvider().addAttributes(layer.fields())
        output_layer.updateFields()

        output_features = []
        for feat in layer.getFeatures():
            new_feat = QgsFeature(feat)
            geom = feat.geometry()
            if not geom.isEmpty():
                geom.transform(transform)
                new_feat.setGeometry(geom)
            output_features.append(new_feat)

        output_layer.dataProvider().addFeatures(output_features)

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.fileEncoding = "UTF-8"
        transform_context = temp_project.transformContext()

        QgsVectorFileWriter.writeAsVectorFormatV3(
            output_layer,
            os.path.join(self.OUTPUT, "地图范围_3857.gpkg"),
            transform_context,
            options
        )

        return output_layer

    def export_map_by_layout_templet(self):
        style_path = os.path.join(self.PROJECT_DIR, "等高线图层样式.qml")
        

        from qgis.core import (
            QgsVectorLayer,
            QgsRasterLayer,
            QgsPrintLayout,
            QgsReadWriteContext,
            QgsLayoutItemMap,
        )
        from qgis.PyQt.QtXml import QDomDocument
        from qgis.core import QgsExpressionContextUtils, QgsLayoutExporter
        from qgis.PyQt.QtCore import QSize, QRectF
        from qgis.core import QgsPathResolver

        self.tif_layer = QgsRasterLayer(self.RASTER_FILE_SAT, "天地图-影像地图")
        if not self.tif_layer.isValid():
            print(f"[错误] 栅格图层加载失败：{self.RASTER_FILE_SAT}")
            self.qgs_app.exitQgis()
            sys.exit(1)
        else:
            print(f"[OK] 栅格图层加载成功，范围：{self.tif_layer.extent()}")

        self.gpk_layer = QgsVectorLayer(self.VEC_FILE_CONTOUR, "等高线", "ogr")
        if not self.gpk_layer.isValid():
            print(f"[错误] 矢量图层加载失败：{self.VEC_FILE_CONTOUR}")
            self.qgs_app.exitQgis()
            sys.exit(1)
        else:
            print(f"[OK] 等高线图层加载成功，范围：{self.gpk_layer.extent()}")
        
        self.gpk_layer = self._reproject_to_3857(self.gpk_layer)
        if not self.gpk_layer.isValid():
            print(f"[错误] 矢量图层重投影为 EPSG:3857 失败：{self.VEC_FILE_CONTOUR}")
            self.qgs_app.exitQgis()
            sys.exit(1)
        else:
            print(f"[OK] 等高线图层加载成功，范围：{self.gpk_layer.extent()}")

        if os.path.exists(style_path):
            print(f"加载样式: {style_path}")
            self.gpk_layer.loadNamedStyle(style_path)
            self.gpk_layer.triggerRepaint()
        else:
            print("样式文件不存在，未加载样式")

        #self.project.addMapLayer(self.tif_layer)
        #self.project.addMapLayer(self.gpk_layer)

        self.shp_layer = QgsVectorLayer(self.VEC_FILE_EXTENT, "地图范围", "ogr")
        if not self.shp_layer.isValid():
            print(f"[错误] 矢量图层加载失败：{self.VEC_FILE_EXTENT}")
            self.qgs_app.exitQgis()
            sys.exit(1)
        else:
            print(f"[OK] 地图范围图层加载成功,范围：{self.shp_layer.extent()}")

        self.shp_layer = self._reproject_to_3857(self.shp_layer)
        if not self.shp_layer.isValid():
            print(f"[错误] 矢量图层重投影为 EPSG:3857 失败：{self.VEC_FILE_EXTENT}")
            self.qgs_app.exitQgis()
            sys.exit(1)
        else:
            print(f"[OK] 地图范围图层加载成功,范围：{self.shp_layer.extent()}")
            
        self.project.addMapLayer(self.shp_layer, False)
        print(f"[OK] 已加载图层：{self.tif_layer.name()}、{self.gpk_layer.name()}、{self.shp_layer.name()}（不可见）")

        #self.project.setCrs(self.shp_layer.crs())
        print(f"[OK] 项目 CRS：{self.shp_layer.crs().authid()}")

        if not os.path.exists(self.QPT_PATH):
            print(f"[错误] 找不到布局模板：{self.QPT_PATH}")
            self.qgs_app.exitQgis()
            sys.exit(1)

        with open(self.QPT_PATH, "r", encoding="utf-8") as f:
            qpt_xml = f.read()

        doc = QDomDocument()
        ok, err_msg, err_line, err_col = doc.setContent(qpt_xml)

        if not ok:
            print(f"[错误] QPT XML 解析失败（第 {err_line} 行，列 {err_col}）：{err_msg}")
            self.qgs_app.exitQgis()
            sys.exit(1)

        layout = QgsPrintLayout(self.project)
        layout.initializeDefaults()

        ctx = QgsReadWriteContext()
        ctx.setPathResolver(QgsPathResolver(self.QPT_PATH))

        loaded_items, loaded_ok = layout.loadFromTemplate(doc, ctx, True)
        if not loaded_ok:
            print("[错误] 布局模板加载失败，请检查 QPT 文件格式")
            self.qgs_app.exitQgis()
            sys.exit(1)

        print(f"[OK] {self.QPT_PATH} 布局模板已加载，共 {len(loaded_items)} 个布局项")

        QgsExpressionContextUtils.setLayoutVariable(layout, "Longest_side", self.LONGEST_SIDE)
        QgsExpressionContextUtils.setLayoutVariable(layout, "Blank_pct", self.BLANK_PCT)
        QgsExpressionContextUtils.setLayoutVariable(layout, "Border", self.BORDER)
        print(f"[OK] 布局变量已设置：Longest_side={self.LONGEST_SIDE}, Blank_pct={self.BLANK_PCT}, Border={self.BORDER}")

        map_extent = self.shp_layer.extent()
        layers_to_show = [self.gpk_layer, self.tif_layer]

        map_items_found = 0
        for item in layout.items():
            if isinstance(item, QgsLayoutItemMap):
                map_items_found += 1
                item.setFollowVisibilityPreset(False)
                item.setKeepLayerSet(True)
                item.setLayers(layers_to_show)
                item.setCrs(self.tif_layer.crs())
                item.setExtent(map_extent)

        print(f"tif_layer crs: {self.tif_layer.crs()}")
        print(f"gpk_layer crs: {self.gpk_layer.crs()}")
        print(f"shp_layer crs: {self.shp_layer.crs()}")
        print(f"map_extent: {map_extent.toString(4)}")

        if map_items_found == 0:
            print("[警告] 布局模板中未找到地图项（qgsLayoutItemMap）")

        layout.refresh()

        for item in layout.items():
            if isinstance(item, QgsLayoutItemMap):
                print(f"[OK] 地图项 '{item.id()}' 实际范围：{item.extent().toString(4)}")

        page = layout.pageCollection().page(0)
        if page is None:
            print("[错误] 布局中未找到页面")
        if page is None:
            print("[错误] 布局中未找到页面")
            self.qgs_app.exitQgis()
            sys.exit(1)

        page_sz = page.pageSize()
        print(f"[OK] page.pageSize() = {page_sz.width():.2f} x {page_sz.height():.2f} mm")

        all_items = layout.items()
        if all_items:
            union_rect = all_items[0].sceneBoundingRect()
            for it in all_items[1:]:
                union_rect = union_rect.united(it.sceneBoundingRect())
            print(f"[OK] 所有元素包围盒（场景mm）：({union_rect.x():.2f},{union_rect.y():.2f}) "
                  f"{union_rect.width():.2f} x {union_rect.height():.2f} mm")
        else:
            union_rect = QRectF(0, 0, page_sz.width(), page_sz.height())

        render_w = max(page_sz.width(), union_rect.right())
        render_h = max(page_sz.height(), union_rect.bottom())
        render_rect = QRectF(0, 0, render_w, render_h)
        print(f"[OK] 最终渲染区域：{render_w:.2f} x {render_h:.2f} mm")

        px_w = int(render_w / 25.4 * self.DPI)
        px_h = int(render_h / 25.4 * self.DPI)
        print(f"[OK] 输出像素：{px_w} x {px_h} @ {self.DPI} DPI")

        exporter = QgsLayoutExporter(layout)    
        image = exporter.renderRegionToImage(render_rect, QSize(px_w, px_h))

        if image.isNull():
            print("[错误] 渲染失败，返回了空图像（内存不足或布局无效）")
            self.qgs_app.exitQgis()
            sys.exit(1)

        os.makedirs(self.OUTPUT, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_png = os.path.join(self.OUTPUT, f"map_{timestamp}.png")

        saved = image.save(output_png, "png")
        if saved:
            print(f"[OK] PNG 已保存：{output_png}")
        else:
            print(f"[错误] PNG 保存失败，请检查输出目录权限：{self.OUTPUT}")

        self.qgs_app.exitQgis()


def main():
    exporter = MapExporter()
    exporter._init_qgis_environment()
    exporter.create_qgis_project()
    exporter.export_map_by_layout_templet()


if __name__ == "__main__":
    main()
