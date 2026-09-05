import math
import os
import sys
import shutil
import time
import tempfile
import random
import requests
import subprocess
import argparse
import gpxpy
import gpxpy.gpx
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from PyQt5.QtCore import QMetaType
from shapely.validation import make_valid
from shapely.geometry import Point
from datetime import datetime
import geopandas as gpd


TIANDITU_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Referer': 'https://www.yourdomain.com/',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive'
}

TIANDITU_TK = 'ab6c93b744918ea333a0b0f9c4e9e15d'
TIANDITU_WMTS_URL = f'http://t0.tianditu.gov.cn/img_w/wmts?tk={TIANDITU_TK}'

# Overpass(OSM) 请求头：overpass-api.de 会封锁 requests 默认 UA(python-requests/*)并返回 406，
# 预检与下载必须统一使用此自定义 UA（实测自定义 UA/curl UA 均返回 200）
OSM_HEADERS = {
    'User-Agent': 'QGIS Headless OSM Downloader/1.0 (https://github.com/kennymarx/DemoPyQGIS)',
}


class DemMakeQGISHeadless:
    # Overpass(OSM) 服务器列表：预检时逐个网络测试，下载时直接使用测通的第一个
    # type=map         : OSM Map API，GET + bbox 查询参数
    # type=interpreter : Overpass QL 接口，POST + QL 查询语句
    OVERPASS_SERVERS = [
        {"name": "overpass-api.de(主)", "type": "map",
         "url": "https://overpass-api.de/api/map",
         "status_url": "https://overpass-api.de/api/status"},
        {"name": "overpass.private.coffee(镜像)", "type": "interpreter",
         "url": "https://overpass.private.coffee/api/interpreter",
         "status_url": "https://overpass.private.coffee/api/status"},
    ]

    def __init__(self, center_longitude, center_latitude, north_south_length_km, east_west_length_km, project_path):
        if north_south_length_km > 30:
            raise ValueError("南北边长不能大于30km")
        if east_west_length_km > 30:
            raise ValueError("东西边长不能大于30km")
        
        self.project = None
        self.qgs_app = None

        self.center_longitude = center_longitude
        self.center_latitude = center_latitude
        self.north_south_length_km = north_south_length_km
        self.east_west_length_km = east_west_length_km
        self.project_path = project_path

        self.OUTPUT = os.path.join(self.project_path, "output")
        self.RESOURCES_PATH = os.path.join(self.project_path, "resources")

        self.MAP_EXTENT_4326 = os.path.join(self.project_path, "地图范围_4326.gpkg")
        self.MAP_EXTENT_3587 = os.path.join(self.project_path, "地图范围_3857.gpkg")
        self.MAP_EXTENT_LAYER_NAME = "地图范围"

        self.PRINT_MODEL_PATH = os.path.join(self.RESOURCES_PATH, "printModel")
        self.QPT_PATH = os.path.join(self.PRINT_MODEL_PATH, "layoutmodel-横向.qpt")
        
        # 天地图地图 map_extent.tif，map_extent_temp.tif，extent_tdt_map
        self.TIANDITU_MAP = os.path.join(self.project_path, 'extent_satellite_map.tif')
        self.TIANDITU_MAP_LAYER_NAME = "extent_satellite_map"
        self.TIANDITU_MAP_TEMP = os.path.join(self.project_path, 'extent_satellite_map_temp.tif')

        # Google地图影像
        self.GOOGLE_MAP = os.path.join(self.project_path, 'extent_google_map.tif')
        self.GOOGLE_MAP_LAYER_NAME = "extent_google_map"
        self.GOOGLE_MAP_TEMP = os.path.join(self.project_path, 'extent_google_map_temp.tif')

        # OSM数据图层
        self.MAP_OSM = os.path.join(self.project_path, 'map.osm')

        self.OSM_POINTS = os.path.join(self.project_path, "osm_points.gpkg")
        self.OSM_LINES = os.path.join(self.project_path, "osm_lines.gpkg")
        self.OSM_MULTIPOLYGONS = os.path.join(self.project_path, "osm_multipolygons.gpkg")

        self.EXTENT_OSM_POINTS = os.path.join(self.project_path, "extent_osm_points.gpkg")
        self.EXTENT_OSM_POINTS_LAYER_NAME = "extent_osm_points"
        
        self.EXTENT_OSM_LINES = os.path.join(self.project_path, "extent_osm_lines.gpkg")
        self.EXTENT_OSM_LINES_LAYER_NAME = "extent_osm_lines"

    
        self.EXTENT_OSM_MULTIPOLYGONS = os.path.join(self.project_path, "extent_osm_multipolygons.gpkg")
        self.EXTENT_OSM_MULTIPOLYGONS_LAYER_NAME = "extent_osm_multipolygons"

        # 轨迹图层
        self.EXTENT_ROUTE_LAYER = os.path.join(self.project_path, "extent_route_layer.gpkg")
        self.EXTENT_ROUTE_LAYER_NAME = "extent_route_layer"

        # DEM图层
        self.EXTENT_DEM = os.path.join(self.project_path, "extent_dem.tif")
        self.EXTENT_DEM_LAYER_NAME = "extent_dem"

        # DEM 高程渲染层样式
        self.EXTENT_DEM_RENDER_LAYER = os.path.join(self.project_path, "extent_dem_render_layer.tif")
        self.EXTENT_DEM_RENDER_LAYER_NAME = "extent_dem_render_layer"

        # DEM 三次重采样（平滑）
        self.EXTENT_DEM_RESAMPLED = os.path.join(self.project_path, "extent_dem_resampled.tif")
        self.EXTENT_DEM_RESAMPLED_LAYER_NAME = "extent_dem_resampled"
        # 重采样分辨率（米）
        self.EXTENT_DEM_RESAMPLED_RESOLUTION_M = 10


        # DEM阴影图层
        self.EXTENT_DEM_HILLSHADOW = os.path.join(self.project_path, "extent_dem_hillshadow.tif")
        self.EXTENT_DEM_HILLSHADOW_LAYER_NAME = "extent_dem_hillshadow"

        # DEM阴影夸张图层
        self.EXTENT_DEM_HILLSHADOW_EXAG = os.path.join(self.project_path, "extent_dem_hillshadow_exag.tif")
        self.EXTENT_DEM_HILLSHADOW_EXAG_LAYER_NAME = "extent_dem_hillshadow_exag"
        # 阴影夸张因子
        self.EXTENT_DEM_HILLSHADOW_EXAG_Z_FACTOR = 5
        self.EXTENT_DEM_HILLSHADOW_EXAG_AZIMUTH = 90
        self.EXTENT_DEM_HILLSHADOW_EXAG_ALTITUDE = 30
        self.Z_FACTOR_LEN = "111120"

        # 等值线图层
        self.CONTOUR_FILE = os.path.join(self.project_path, "extent_contour.gpkg")
        self.CONTOUR_LAYER_NAME = "extent_contour"

        # 模板文件
        self.TEMPLATE_PATH = os.path.join(self.RESOURCES_PATH, "template")

        # 默认模板文件
        self.DEFAULT_TEMPLATE = {
            self.MAP_EXTENT_LAYER_NAME:os.path.join(self.TEMPLATE_PATH, "地图范围样式.qml"),
            self.EXTENT_OSM_POINTS_LAYER_NAME:os.path.join(self.TEMPLATE_PATH, "POI图层样式.qml"),
            self.EXTENT_OSM_LINES_LAYER_NAME:os.path.join(self.TEMPLATE_PATH, "线图层样式.qml"),
            self.EXTENT_OSM_MULTIPOLYGONS_LAYER_NAME:os.path.join(self.TEMPLATE_PATH, "面图层样式.qml"),
            self.CONTOUR_LAYER_NAME:os.path.join(self.TEMPLATE_PATH, "等高线图层样式.qml"),
            self.EXTENT_DEM_RENDER_LAYER_NAME:os.path.join(self.TEMPLATE_PATH, "高程渲染层样式.qml"),
            self.EXTENT_DEM_HILLSHADOW_LAYER_NAME:os.path.join(self.TEMPLATE_PATH, "山体阴影样式.qml"),
            self.EXTENT_DEM_HILLSHADOW_EXAG_LAYER_NAME:os.path.join(self.TEMPLATE_PATH, "山体阴影样式.qml"),
            self.EXTENT_ROUTE_LAYER_NAME:os.path.join(self.TEMPLATE_PATH, "轨迹图层样式.qml"),
            self.GOOGLE_MAP_LAYER_NAME:os.path.join(self.TEMPLATE_PATH, "谷歌卫图图层样式.qml"),
        }

        # 打印模板
        self.LAYOUT_MODEL_HORIZONTAL = os.path.join(self.PRINT_MODEL_PATH, "layoutmodel-横向.qpt")
        self.LAYOUT_MODEL_HORIZONTAL_NAME = "layoutmodel-横向"
        self.LAYOUT_MODEL_VERTICAL = os.path.join(self.PRINT_MODEL_PATH, "layoutmodel-纵向.qpt")
        self.LAYOUT_MODEL_VERTICAL_NAME = "layoutmodel-纵向"

        # 系统参数
        self.DPI = 300
        # 打印地图最大边长
        self.SYS_PARAMS_LONGEST_SIDE = "Longest_side"
        self.SYS_PARAMS_BLANK_PCT = "Blank_pct"
        self.SYS_PARAMS_BORDER = "Border"
        self.SYS_PARAMS_PROJECT_SCALE_PARM = "project_scale_parm"
        self.SYS_PARAMS_BG_SATELLITE = "bg_satellite"

        self.LONGEST_SIDE = 1000.0
        self.BLANK_PCT = 0.15
        self.BORDER = 10.0
        self.PROJECT_SCALE_PARM = 1.0
        self.BG_SATELLITE_Y = 1
        self.BG_SATELLITE_N = 0
        self.ICON_CLR = "default"
        self.ICON_CLR_orange = "橙"
        self.SYS_PARAMS_MAP_TITLE = "map_title"
        self.SYS_PARAMS_MAP_MAKER = "map_maker"
        self.SYS_PARAMS_ICON_CLR = "icon_clr"
        

        os.makedirs(self.project_path, exist_ok=True)

        # 初始化项目资源
        self._copy_resources()
        
        self._init_qgis_environment()
        
        from qgis.core import QgsCoordinateReferenceSystem
        self.crs = QgsCoordinateReferenceSystem('EPSG:3857')
    
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
        print("[OK] QGIS 已初始化")
    
    def __del__(self):
        if self.qgs_app:
            self.qgs_app.exitQgis()
            print("[OK] QGIS 已退出")

    # 创建项目
    def create_project(self):
        from qgis.core import QgsProject
        from qgis.core import QgsExpressionContextUtils
        # 创建项目
        self.project = QgsProject.instance()
        # 清空项目
        self.project.clear()
        # 设置项目的坐标系wsg84
        self.project.setCrs(self.crs)
        # 设置项目常用属性
        QgsExpressionContextUtils.setProjectVariable(self.project, "bg_satellite", '0')
        QgsExpressionContextUtils.setProjectVariable(self.project, "Blank_pct", '0.15')
        QgsExpressionContextUtils.setProjectVariable(self.project, "Border", '10')
        QgsExpressionContextUtils.setProjectVariable(self.project, "Longest_side", self.LONGEST_SIDE)
        QgsExpressionContextUtils.setProjectVariable(self.project, "project_scale_parm", '1')
        
    # 定义私有方法，将./resources目录下的所有文件拷贝到项目目录下
    def _copy_resources(self):
        # 当前脚本的位置
        current_dir = os.path.dirname(os.path.abspath(__file__))
        resources_dir = os.path.join(current_dir, "resources")
        dst_resources_dir = os.path.join(self.project_path, "resources")
    
        # 拷贝资源目录到项目目录，保持原目录结构
        print(f"拷贝资源目录 {resources_dir} 到项目目录 {dst_resources_dir}")
        
        try:
            # 如果目标目录已存在，先删除
            if os.path.exists(dst_resources_dir):
                shutil.rmtree(dst_resources_dir)
            # 递归拷贝整个资源目录（包括目录本身及其所有内容）
            shutil.copytree(resources_dir, dst_resources_dir)
            print("资源目录拷贝完成")
        except Exception as e:
            print(f"拷贝资源目录失败：{e}")

    # 计算地图范围边界点
    def _calculate_boundary_points(self):
        from qgis.core import QgsDistanceArea, QgsPointXY
        da = QgsDistanceArea()
        da.setEllipsoid("WGS84")
        
        half_ns = self.north_south_length_km * 500
        half_ew = self.east_west_length_km * 500
        
        north_point = da.computeSpheroidProject(
            QgsPointXY(self.center_longitude, self.center_latitude),
            distance=half_ns,
            azimuth=math.radians(0)
        )
        
        south_point = da.computeSpheroidProject(
            QgsPointXY(self.center_longitude, self.center_latitude),
            distance=half_ns,
            azimuth=math.radians(180)
        )
        
        east_point = da.computeSpheroidProject(
            QgsPointXY(self.center_longitude, self.center_latitude),
            distance=half_ew,
            azimuth=math.radians(90)
        )
        
        west_point = da.computeSpheroidProject(
            QgsPointXY(self.center_longitude, self.center_latitude),
            distance=half_ew,
            azimuth=math.radians(270)
        )
        
        top_left = QgsPointXY(west_point.x(), north_point.y())
        top_right = QgsPointXY(east_point.x(), north_point.y())
        bottom_right = QgsPointXY(east_point.x(), south_point.y())
        bottom_left = QgsPointXY(west_point.x(), south_point.y())
        
        return [top_left, top_right, bottom_right, bottom_left]
    
    # 创建地图范围图层
    def make_map_extent_layer(self):
        """
        创建地图范围GPKG文件
        
        返回:
        str: 成功返回地图范围图层文件路径，失败返回None
        """
        if self.project is None:
            print("错误: 项目未创建")
            sys.exit(1)

        self._create_extent_layer_4326(self.MAP_EXTENT_4326)
        
        self._create_extent_layer_3857(self.MAP_EXTENT_3587)

        return self.MAP_EXTENT_3587

    # 将图层加载到项目
    def add_layer_to_project(self, layer_path, layer_name, layer_style=None):
        """
        根据图层文件路径加载图层，添加到QGIS项目，并加载指定样式

        参数:
        layer_path (str): 待添加的图层文件路径
        layer_name (str): 图层名称
        layer_style (str): 图层样式文件名或完整路径

        返回:
        QgsLayer: 成功返回 图层对象，失败返回 None
        """
        from qgis.core import QgsRasterLayer, QgsVectorLayer

        if self.project is None:
            print("错误: 项目未创建")
            return None

        if not layer_path or not os.path.exists(layer_path):
            print(f"错误: 图层文件不存在: {layer_path}")
            return None

        if not layer_name:
            print("错误: 图层名称不能为空")
            return None

        raster_extensions = (".tif", ".tiff", ".jpg", ".jpeg", ".png")
        if os.path.splitext(layer_path)[1].lower() in raster_extensions:
            layer = QgsRasterLayer(layer_path, layer_name)
            layer_type = "栅格"
        else:
            layer = QgsVectorLayer(layer_path, layer_name, 'ogr')
            layer_type = "矢量"

        if not layer.isValid():
            print(f"[错误] {layer_type}图层加载失败：{layer_path}")
            return None
        else:
            print(f"[OK] {layer_type}图层加载成功,范围：{layer.extent()}")

        # 检查图层是否已存在，如果存在则清理旧图层，重新添加
        for project_layer in self.project.mapLayers().values():
            if project_layer.name() == layer.name():
                print(f"{layer.name()}图层已存在，清理旧图层")
                self.project.removeMapLayer(layer)

        style_path = layer_style
        if layer_style and not os.path.isabs(layer_style):
            style_path = os.path.join(self.TEMPLATE_PATH, layer_style)

        if style_path:
            if os.path.exists(style_path):
                print(f"加载样式: {style_path}")
                layer.loadNamedStyle(style_path)
                layer.triggerRepaint()
            else:
                print(f"样式文件不存在，未加载样式: {style_path}")
        else:
            print("未指定样式文件，不加载样式")

        print(f"[OK] {layer_type}图层添加到项目")
        self.project.addMapLayer(layer)
        return layer


    # 保存项目
    def save_project(self, project_name="map_project.qgz"):
        if self.project is None:
            raise RuntimeError("项目未创建，请先调用create_project()")

        project_file_path = os.path.join(self.project_path, project_name)
        self.project.write(project_file_path)

        return project_file_path
    # 4326地图范围图层
    def _create_extent_layer_4326(self, gpkg_path):
        from qgis.core import QgsVectorLayer, QgsField, QgsGeometry, QgsFeature, QgsVectorFileWriter
        
        print(f"创建4326地图范围图层: {gpkg_path}")
        
        temp_layer = QgsVectorLayer("polygon?crs=epsg:4326", "地图范围", "memory")
        
        if not temp_layer.isValid():
            raise RuntimeError("图层创建失败")
        
        temp_layer.startEditing()
        
        temp_layer.dataProvider().addAttributes([
            QgsField("id", QMetaType.Type.Int)
        ])
        temp_layer.updateFields()
        
        boundary_points = self._calculate_boundary_points()
        boundary_points.append(boundary_points[0])
        
        polygon = QgsGeometry.fromPolygonXY([boundary_points])
        
        feature = QgsFeature()
        feature.setGeometry(polygon)
        feature.setAttributes([1])
        temp_layer.dataProvider().addFeature(feature)
        
        temp_layer.updateExtents()
        temp_layer.commitChanges()
        
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.fileEncoding = "UTF-8"
        transform_context = self.project.transformContext()
        
        QgsVectorFileWriter.writeAsVectorFormatV3(
            temp_layer,
            gpkg_path,
            transform_context,
            options
        )
    # 3857地理范围图层
    def _create_extent_layer_3857(self, gpkg_path):
        from qgis.core import QgsVectorLayer, QgsField, QgsGeometry, QgsFeature, QgsVectorFileWriter, QgsCoordinateReferenceSystem, QgsCoordinateTransform
        
        temp_layer = QgsVectorLayer("polygon?crs=epsg:3857", "地理范围_3857", "memory")
        
        if not temp_layer.isValid():
            raise RuntimeError("3857图层创建失败")
        
        temp_layer.startEditing()
        
        temp_layer.dataProvider().addAttributes([
            QgsField("id", QMetaType.Type.Int)
        ])
        temp_layer.updateFields()
        
        boundary_points_4326 = self._calculate_boundary_points()
        boundary_points_4326.append(boundary_points_4326[0])
        
        crs_4326 = QgsCoordinateReferenceSystem("EPSG:4326")
        crs_3857 = QgsCoordinateReferenceSystem("EPSG:3857")
        transform = QgsCoordinateTransform(crs_4326, crs_3857, self.project)
        
        boundary_points_3857 = [transform.transform(point) for point in boundary_points_4326]
        
        polygon = QgsGeometry.fromPolygonXY([boundary_points_3857])
        
        feature = QgsFeature()
        feature.setGeometry(polygon)
        feature.setAttributes([1])
        temp_layer.dataProvider().addFeature(feature)
        
        temp_layer.updateExtents()
        temp_layer.commitChanges()
        
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.fileEncoding = "UTF-8"
        transform_context = self.project.transformContext()
        
        QgsVectorFileWriter.writeAsVectorFormatV3(
            temp_layer,
            gpkg_path,
            transform_context,
            options
        )
        print(f"3857地理范围图层已生成: {gpkg_path}")

    # 获取gpkg文件范围
    def _get_gpkg_extent(self):
        from qgis.core import QgsVectorLayer

        layer = QgsVectorLayer(self.MAP_EXTENT_4326, "temp", "ogr")
        if not layer.isValid():
            raise RuntimeError("加载gpkg文件失败")
        extent = layer.extent()
        return {
            'lon_min': extent.xMinimum(),
            'lon_max': extent.xMaximum(),
            'lat_min': extent.yMinimum(),
            'lat_max': extent.yMaximum()
        }
    # 度转瓦片索引
    def _deg2num(self, lat_deg, lon_deg, zoom):
        lat_rad = math.radians(lat_deg)
        n = 2.0 ** zoom
        xtile = int((lon_deg + 180.0) / 360.0 * n)
        ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
        return (xtile, ytile)
    # 瓦片索引转度
    def _num2deg(self, xtile, ytile, zoom):
        n = 2.0 ** zoom
        lon_deg = xtile / n * 360.0 - 180.0
        lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
        lat_deg = math.degrees(lat_rad)
        return (lat_deg, lon_deg)
    # 下载天地图瓦片（多线程并行版，与 _download_google_tiles 同一套设计）
    def _download_tianditu_tiles(self, lon_min, lon_max, lat_min, lat_max, zoom_level=14,
                                 max_workers=4, max_retries=3):
        """
        并行下载 天地图 卫星瓦片。

        与串行版相比的优化点（与 Google 并行版保持同一套设计）：
          1. 多线程并发下载（ThreadPoolExecutor，默认 16 线程，瓶颈通常在网络）。
          2. 每个线程使用独立的 WMTS 客户端（owslib 非保证线程安全，
             对应 Google 版的"每线程独立 Session"）。
          3. 已下载的瓦片直接跳过（断点续传，重复运行不重下）。
          4. 失败指数退避重试（最多 max_retries 次）。
          5. 线程锁保护的进度打印与计数。
        """
        from owslib.wmts import WebMapTileService

        print(f"TIANDITU_WMTS_URL: {TIANDITU_WMTS_URL}")
        # 主线程先创建一次客户端，验证 URL/TK 可用（能力文档解析报错能尽早暴露）
        WebMapTileService(url=TIANDITU_WMTS_URL, headers=TIANDITU_HEADERS)
        print("创建WMTS客户端 成功")

        layer_name = 'img'
        tile_matrix_set = 'w'

        x_min, y_min = self._deg2num(lat_max, lon_min, zoom_level)
        x_max, y_max = self._deg2num(lat_min, lon_max, zoom_level)

        tile_output_dir = os.path.join(self.project_path, 'tianditu_tiles')
        os.makedirs(tile_output_dir, exist_ok=True)

        total_tiles = (x_max - x_min + 1) * (y_max - y_min + 1)

        # 先把所有 (x, y, 目标文件名) 构造成任务队列
        tasks = []
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                filename = os.path.join(tile_output_dir, f'tile_{zoom_level}_{x}_{y}.jpg')
                tasks.append((x, y, filename))

        # 统计"已下载的瓦片数量"：预先扫描已存在文件，支持断点续传
        existed = sum(1 for _, _, fn in tasks if os.path.exists(fn))
        pending = total_tiles - existed

        # 线程锁 + 原子计数器（保护并发写）
        counter_lock = threading.Lock()
        done = {'success': existed, 'fail': 0}

        print(f"\n开始并行下载 天地图 瓦片 (级别: {zoom_level}, 线程: {max_workers})...")
        print(f"瓦片列范围: {x_min} 到 {x_max}")
        print(f"瓦片行范围: {y_min} 到 {y_max}")
        print(f"总瓦片数: {total_tiles}，已存在跳过: {existed}，待下载: {pending}")

        # 线程局部对象：每个线程各自持有 1 个 WMTS 客户端，避免跨线程共享
        tls = threading.local()

        def _get_wmts():
            """获取当前线程独有的 WMTS 客户端（懒加载）"""
            if not hasattr(tls, 'wmts'):
                tls.wmts = WebMapTileService(url=TIANDITU_WMTS_URL, headers=TIANDITU_HEADERS)
            return tls.wmts

        def _download_one(x, y, filename):
            """下载单个瓦片，返回 bool 成功与否。
            内部自带：断点续传跳过、指数退避重试。"""
            # ① 断点续传：文件已存在且非空就跳过
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                return True

            wmts = _get_wmts()

            # ② 指数退避重试：0s → 1s → 2s → 4s
            last_err = None
            for attempt in range(max_retries):
                try:
                    tile = wmts.gettile(
                        base_url=TIANDITU_WMTS_URL,
                        layer=layer_name,
                        tilematrixset=tile_matrix_set,
                        tilematrix=str(zoom_level),
                        row=y,
                        column=x,
                    )
                    content = tile.read()
                    # 空响应视为失败，进入重试
                    if not content:
                        last_err = "空响应"
                        time.sleep(2 ** attempt)
                        continue
                    with open(filename, 'wb', buffering=1024 * 1024) as f:
                        f.write(content)
                    return True
                except Exception as e:
                    last_err = str(e)
                    time.sleep(2 ** attempt)

            # 走到这里表示所有重试均失败
            print(f"    下载失败 ({x},{y}): {last_err}")
            return False

        # ③ 提交所有任务到线程池
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            future_map = {
                ex.submit(_download_one, x, y, fn): (x, y, fn)
                for (x, y, fn) in tasks
            }
            for fut in as_completed(future_map):
                ok = fut.result()
                with counter_lock:
                    if ok:
                        done['success'] += 1
                    else:
                        done['fail'] += 1
                    progress = done['success'] + done['fail']
                    if progress % 25 == 0 or progress == total_tiles:
                        print(f"  进度: {progress}/{total_tiles}  成功 {done['success']}  失败 {done['fail']}")

        print(f"\n天地图 瓦片并行下载完成! 成功 {done['success']} 个，失败 {done['fail']} 个")

        return self._merge_tiles(tile_output_dir, zoom_level, (x_min, x_max), (y_min, y_max), lon_min, lon_max, lat_min, lat_max)
    # 拼接瓦片
    def _merge_tiles(self, tile_output_dir, zoom, x_range, y_range, lon_min, lon_max, lat_min, lat_max, temp_jpg=None, tif_path=None):
        from PIL import Image
        from osgeo import gdal
        from pyproj import Transformer
        
        if temp_jpg is None:
            temp_jpg = self.TIANDITU_MAP_TEMP
        if tif_path is None:
            tif_path = self.TIANDITU_MAP
        
        tile_width = 256
        tile_height = 256
        width = (x_range[1] - x_range[0] + 1) * tile_width
        height = (y_range[1] - y_range[0] + 1) * tile_height
        
        merged = Image.new('RGB', (width, height))
        
        print("\n开始拼接瓦片...")
        for x in range(x_range[0], x_range[1] + 1):
            for y in range(y_range[0], y_range[1] + 1):
                try:
                    tile_path = os.path.join(tile_output_dir, f'tile_{zoom}_{x}_{y}.jpg')
                    tile_img = Image.open(tile_path)

                    pos_x = (x - x_range[0]) * tile_width
                    pos_y = (y - y_range[0]) * tile_height

                    merged.paste(tile_img, (pos_x, pos_y))
                    print(f"已拼接瓦片 ({x},{y})")
                except Exception as e:
                    print(f"拼接失败 ({x},{y}): {str(e)}")
        
        merged.save(temp_jpg)
        print(f"\n拼接完成! 临时图像保存至: {temp_jpg}")
        
        # 关键修复：根据实际下载的瓦片范围反算地理坐标
        # 因为瓦片拼接后，实际的地理范围会大于下载的瓦片范围（地图范围）
        # 左上角瓦片 (x_min, y_min) 对应的实际地理范围
        top_lat, left_lon = self._num2deg(x_range[0], y_range[0], zoom)
        # 右下角瓦片 (x_max+1, y_max+1) 对应的实际地理范围（+1 是因为瓦片坐标表示左下角）
        bottom_lat, right_lon = self._num2deg(x_range[1] + 1, y_range[1] + 1, zoom)
        
        # 使用反算出的实际范围计算 GCP 坐标
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        x_min_3857, y_max_3857 = transformer.transform(left_lon, top_lat)    # 左上角
        x_max_3857, y_min_3857 = transformer.transform(right_lon, bottom_lat) # 右下角
        
        gcp_list = [
            gdal.GCP(x_min_3857, y_max_3857, 0, 0, 0),           # 左上角
            gdal.GCP(x_max_3857, y_max_3857, 0, merged.width, 0),  # 右上角
            gdal.GCP(x_min_3857, y_min_3857, 0, 0, merged.height), # 左下角
            gdal.GCP(x_max_3857, y_min_3857, 0, merged.width, merged.height)  # 右下角
        ]
        # 消除警告 + 明确开启异常（推荐）
        gdal.UseExceptions()
        
        gcp_list = [
            gdal.GCP(x_min_3857, y_max_3857, 0, 0, 0),
            gdal.GCP(x_max_3857, y_max_3857, 0, merged.width, 0),
            gdal.GCP(x_min_3857, y_min_3857, 0, 0, merged.height),
            gdal.GCP(x_max_3857, y_min_3857, 0, merged.width, merged.height)
        ]
        
        options = gdal.TranslateOptions(format='GTiff', outputSRS='EPSG:3857', GCPs=gcp_list)
        gdal.Translate(tif_path, temp_jpg, options=options)
        print(f"GeoTIFF保存至: {tif_path}")
        
        '''
        if os.path.exists(temp_jpg):
            os.remove(temp_jpg)
        '''
        return tif_path
    # 添加tif文件到项目
    def _add_tif_to_project(self, tif_path):
        from qgis.core import QgsRasterLayer
        raster_layer = QgsRasterLayer(tif_path, '地图范围-天地图')
        if not raster_layer.isValid():
            raise RuntimeError(f"加载TIF文件失败: {tif_path}")
        self.project.addMapLayer(raster_layer, False)
        root = self.project.layerTreeRoot()
        root.insertLayer(0, raster_layer)
        print(f"已添加图层到项目: {tif_path}")

    # 创建天地图影像图层
    def make_tianditu_layer(self, zoom_level=14):
        """
        下载天地图瓦片并生成GeoTIFF影像

        参数:
        zoom_level (int): 瓦片缩放级别

        返回:
        str: 成功返回天地图影像文件路径，失败返回None
        """
        if os.path.exists(self.TIANDITU_MAP):
            print(f"警告: 天地图影像已存在: {self.TIANDITU_MAP}")
            print(f"跳过下载，直接使用已存在文件: {self.TIANDITU_MAP}")
            return self.TIANDITU_MAP

        if not os.path.exists(self.MAP_EXTENT_4326):
            raise RuntimeError(f"{self.MAP_EXTENT_4326}不存在，请先创建")

        # 网络连通性预检：失败则报警并跳过下载
        print("\n[预检] 正在测试 天地图 服务器连通性...")
        if not self._check_tianditu_network():
            print("=" * 60)
            print("!!! 网络报警: 天地图 服务器无法连接，请检查网络或 TK 配置 !!!")
            print("=" * 60)
            self._alert_beep()
            print("跳过 天地图 下载")
            return None

        print("[预检] 网络连通正常")
        print("\n=== 开始下载天地图影像 ===")
        extent = self._get_gpkg_extent()
        tif_path = self._download_tianditu_tiles(
            extent['lon_min'],
            extent['lon_max'],
            extent['lat_min'],
            extent['lat_max'],
            zoom_level
        )

        print("\n=== 天地图下载完成 ===")
        return tif_path

    # 下载Google地图瓦片（多线程并行版）
    def _download_google_tiles(self, lon_min, lon_max, lat_min, lat_max, zoom_level=14,
                               max_workers=16, max_retries=3):
        """
        并行下载 Google 卫星瓦片。

        相对串行版的优化点：
          1. 多线程并发下载（ThreadPoolExecutor，默认 16 线程，瓶颈通常在网络）。
          2. 每个线程使用独立的 requests.Session，复用 TLS 连接，避免重复握手。
          3. 每个线程使用独立 headers 副本，避免共享可变 dict 被覆盖（经验教训）。
          4. 已下载的瓦片直接跳过（断点续传，重复运行不重下）。
          5. 多域名轮询（mt0~mt3），突破单域名连接数/限速上限。
          6. 失败指数退避重试（最多 max_retries 次）。
          7. 线程锁保护的进度打印与计数。
        """
        # 多个 Google 瓦片子域名，线程轮询使用以分散负载
        google_urls = [
            'https://mt0.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
            'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
            'https://mt2.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
            'https://mt3.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
        ]
        # 基础 headers（每个线程会 .copy() 一份，不共享）
        google_base_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }

        print(f"Google瓦片URL模板(共 {len(google_urls)} 个子域名轮询): {google_urls[0]}")

        x_min, y_min = self._deg2num(lat_max, lon_min, zoom_level)
        x_max, y_max = self._deg2num(lat_min, lon_max, zoom_level)

        tile_output_dir = os.path.join(self.project_path, 'google_tiles')
        os.makedirs(tile_output_dir, exist_ok=True)

        total_tiles = (x_max - x_min + 1) * (y_max - y_min + 1)

        # 先把所有 (x, y, 目标文件名) 构造成任务队列
        tasks = []
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                filename = os.path.join(tile_output_dir, f'tile_{zoom_level}_{x}_{y}.jpg')
                tasks.append((x, y, filename))

        # 统计"已下载的瓦片数量"：预先扫描已存在文件，支持断点续传
        existed = sum(1 for _, _, fn in tasks if os.path.exists(fn))
        pending = total_tiles - existed

        # 线程锁 + 原子计数器（保护并发写）
        counter_lock = threading.Lock()
        done = {'success': existed, 'fail': 0}

        print(f"\n开始并行下载 Google 瓦片 (级别: {zoom_level}, 线程: {max_workers})...")
        print(f"瓦片列范围: {x_min} 到 {x_max}")
        print(f"瓦片行范围: {y_min} 到 {y_max}")
        print(f"总瓦片数: {total_tiles}，已存在跳过: {existed}，待下载: {pending}")

        # 线程局部对象：每个线程各自持有 1 个 Session，避免跨线程共享
        tls = threading.local()

        def _get_session():
            """获取当前线程独有的 Session + headers（懒加载）"""
            if not hasattr(tls, 'session'):
                tls.session = requests.Session()
                # 每个线程独立的 headers 副本
                tls.session.headers.update(google_base_headers.copy())
            return tls.session

        def _download_one(x, y, filename):
            """下载单个瓦片，返回 bool 成功与否。
            内部自带：断点续传跳过、多域名轮询、指数退避重试。"""
            # ① 断点续传：文件已存在且非空就跳过
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                return True

            # ② 多域名轮询：挑一个随机的 mt{0..3}
            url_tpl = random.choice(google_urls)
            url = url_tpl.format(x=x, y=y, z=zoom_level)

            sess = _get_session()

            # ③ 指数退避重试：0s → 1s → 2s → 4s
            last_err = None
            for attempt in range(max_retries):
                try:
                    resp = sess.get(url, timeout=(5, 15))
                    if resp.status_code != 200:
                        last_err = f"HTTP {resp.status_code}"
                        # 4xx 没必要重试
                        if 400 <= resp.status_code < 500:
                            break
                        time.sleep(2 ** attempt)
                        continue
                    with open(filename, 'wb', buffering=1024 * 1024) as f:
                        f.write(resp.content)
                    return True
                except Exception as e:
                    last_err = str(e)
                    time.sleep(2 ** attempt)

            # 走到这里表示所有重试均失败
            print(f"    下载失败 ({x},{y}): {last_err}")
            return False

        # ④ 提交所有任务到线程池
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            future_map = {
                ex.submit(_download_one, x, y, fn): (x, y, fn)
                for (x, y, fn) in tasks
            }
            for fut in as_completed(future_map):
                ok = fut.result()
                with counter_lock:
                    if ok:
                        done['success'] += 1
                    else:
                        done['fail'] += 1
                    progress = done['success'] + done['fail']
                    if progress % 25 == 0 or progress == total_tiles:
                        print(f"  进度: {progress}/{total_tiles}  成功 {done['success']}  失败 {done['fail']}")

        print(f"\nGoogle 瓦片并行下载完成! 成功 {done['success']} 个，失败 {done['fail']} 个")

        return self._merge_tiles(
            tile_output_dir, zoom_level, (x_min, x_max), (y_min, y_max),
            lon_min, lon_max, lat_min, lat_max,
            temp_jpg=self.GOOGLE_MAP_TEMP,
            tif_path=self.GOOGLE_MAP
        )

    # 通用网络连通性检查
    def _check_network(self, url, timeout=5, headers=None):
        """发送轻量 GET 请求探测服务器是否可达，返回 bool"""
        try:
            resp = requests.get(url, timeout=timeout, headers=headers)
            ok = (resp.status_code == 200)
            if not ok:
                print(f"网络探测异常: HTTP {resp.status_code}")
            return ok
        except Exception as e:
            print(f"网络探测失败: {e}")
            return False

    # 检查Google瓦片服务器网络连通性
    def _check_google_network(self, timeout=5):
        """用一个小瓦片请求探测 Google 瓦片服务器是否可达，返回 bool"""
        return self._check_network('https://mt1.google.com/vt/lyrs=s&x=0&y=0&z=1', timeout)

    # 网络测试各 Overpass(OSM) 服务器，返回第一个测通的服务器配置（全不通返回 None）
    def _check_osm_network(self, timeout=5):
        """逐个测试 OVERPASS_SERVERS 的状态接口，返回测通的服务器 dict 或 None"""
        for server in self.OVERPASS_SERVERS:
            # 必须带自定义 UA：overpass-api.de 封锁 requests 默认 UA(python-requests/*) 返回 406
            ok = self._check_network(server["status_url"], timeout, headers=OSM_HEADERS)
            print(f"  Overpass服务器 {server['name']}: {'可达' if ok else '不可达'}")
            if ok:
                return server
        return None

    # 检查天地图服务器网络连通性
    def _check_tianditu_network(self, timeout=5):
        """用一个小瓦片请求探测 天地图 服务器是否可达（同时验证TK有效性），返回 bool"""
        probe_url = (
            f'http://t0.tianditu.gov.cn/img_w/wmts?tk={TIANDITU_TK}'
            f'&layer=img&style=default&tilematrixset=w&Service=WMTS'
            f'&Request=GetTile&Version=1.0.0&Format=image/jpeg'
            f'&TileMatrix=1&TileRow=0&TileCol=0'
        )
        # 浏览器端类型的 TK 会校验请求特征，必须带浏览器 UA，否则返回 403(错误码301012)
        return self._check_network(probe_url, timeout, headers=TIANDITU_HEADERS)

    # 报警提示音（Windows 下蜂鸣，其他平台静默跳过）
    @staticmethod
    def _alert_beep(times=3):
        try:
            import winsound
            for _ in range(times):
                winsound.Beep(1000, 300)  # 1000Hz, 300ms
                time.sleep(0.2)
        except Exception:
            pass  # 非 Windows 或无声音设备时静默

    # 读取 OSM 文件头(header)中的数据范围 bbox；无法判定时返回 None
    def _get_osm_header_box(self, osm_path):
        """
        读取 OSM 文件(.osm/.osm.pbf) header 中记录的数据 bbox，
        只读文件头不扫描数据体，大文件也秒回。

        返回 (西, 南, 东, 北)；文件无 bbox 记录或读取失败返回 None。
        """
        try:
            import osmium
            reader = osmium.io.Reader(osm_path)
            try:
                box = reader.header().box()   # header 是方法，需调用后再取 box
            finally:
                reader.close()
            if not box.valid():
                return None
            bl = box.bottom_left   # pyosmium 中为属性(非方法)，.lon/.lat 返回度数
            tr = box.top_right
            return (bl.lon, bl.lat, tr.lon, tr.lat)
        except Exception:
            return None

    # 从本地 osm_files 目录查找可用的 OSM 资源（网络下载失败时的回退）
    def _find_local_osm_file(self, extent=None):
        """
        在脚本所在目录的 osm_files/ 下查找本地 OSM 资源(.osm/.osm.pbf)。

        挑选规则:
          提供 extent(地图范围)时:
            1. 优先在"数据范围(header bbox)包含地图范围"的文件中选体量最小的
               （例如同时有全国 pbf 和省级 pbf 都覆盖地图范围时，自动选省文件）；
            2. 若所有文件都无法判定数据范围（header 无 bbox），退回选体量最小的；
            3. 明确不包含地图范围的文件直接跳过。
          未提供 extent 时: 选体量最小的。

        找到返回文件路径，找不到返回 None。
        """
        local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'osm_files')
        if not os.path.isdir(local_dir):
            print(f"本地OSM资源目录不存在: {local_dir}")
            return None

        # 收集候选文件（排除 Office 临时文件 ~$ 开头），统一按体量挑选
        candidates = []
        for f in os.listdir(local_dir):
            if f.lower().endswith(('.osm', '.osm.pbf')) and not f.startswith('~'):
                path = os.path.join(local_dir, f)
                candidates.append((path, os.path.getsize(path)))

        if not candidates:
            print(f"本地OSM资源目录中无可用文件(.osm/.osm.pbf): {local_dir}")
            return None

        # 未提供地图范围：直接选体量最小的
        if extent is None:
            path, size = min(candidates, key=lambda t: t[1])
            print(f"找到本地OSM资源: {path} ({size / (1024 * 1024):.1f} MB)")
            return path

        # 读取各文件的数据范围 bbox，分为"包含地图范围"与"无法判定"两组
        containing, unknown = [], []
        for path, size in candidates:
            box = self._get_osm_header_box(path)
            if box is None:
                unknown.append((path, size))
                continue
            west, south, east, north = box
            if (west <= extent['lon_min'] and east >= extent['lon_max']
                    and south <= extent['lat_min'] and north >= extent['lat_max']):
                containing.append((path, size))
            else:
                print(f"  跳过(数据范围不含地图范围): {path} "
                      f"(bbox: {west:.2f},{south:.2f},{east:.2f},{north:.2f})")

        # 优先: 包含地图范围的文件中选体量最小的
        if containing:
            containing.sort(key=lambda t: t[1])
            for path, size in containing:
                print(f"  候选(包含地图范围): {path} ({size / (1024 * 1024):.1f} MB)")
            path, size = containing[0]
            print(f"选择体量最小的候选: {path} ({size / (1024 * 1024):.1f} MB)")
            return path

        # 回退: 都无法判定数据范围时，选体量最小的（保持流程可用）
        if unknown:
            path, size = min(unknown, key=lambda t: t[1])
            print(f"所有文件均无法判定数据范围，回退选体量最小: {path} ({size / (1024 * 1024):.1f} MB)")
            return path

        print("本地OSM资源均不包含地图范围，无法使用")
        return None

    def _get_ascii_temp_dir(self):
        """
        返回一个纯 ASCII 路径且可写的临时目录，供 pyosmium 读写子集使用。

        pyosmium(libosmium) 在 Windows 上经窄字符 API 打开文件，路径含中文等
        非 ASCII 字符时会直接报 "The system cannot find the file specified"
        （即使目录真实存在）。优先使用系统临时目录（通常为纯英文，如
        C:\\Users\\Administrator\\AppData\\Local\\Temp）；若系统临时目录本身
        含非 ASCII（如中文用户名 C:\\Users\\张三\\...），则回退到脚本旁的
        osm_files/ 目录（脚本能在此运行说明其路径为 ASCII）。找不到时返回 None。
        """
        candidates = [tempfile.gettempdir()]
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if script_dir.isascii():
            osm_files_dir = os.path.join(script_dir, 'osm_files')
            try:
                os.makedirs(osm_files_dir, exist_ok=True)
                candidates.append(osm_files_dir)
            except OSError:
                pass
        for d in candidates:
            try:
                if d.isascii() and os.path.isdir(d) and os.access(d, os.W_OK):
                    return d
            except Exception:
                continue
        return None

    # 用 pyosmium 按地图范围从本地 OSM 数据提取子集（避免对全国级大文件做全量转换）
    def _extract_osm_subset(self, local_osm_path, extent):
        """
        按地图范围(extent)从本地 OSM 数据(.osm/.osm.pbf)提取子集，
        输出到项目目录下的 map.osm.pbf。

        使用 pyosmium(Python 库)两遍扫描实现，等价于
        `osmium extract --strategy complete_ways`:
          第一遍: 判定并收集——bbox 内的节点、与 bbox 相交的 way（并记录
                  其引用的全部节点，含 bbox 外节点，保证跨边界几何完整）、
                  成员被保留的 relation；
          第二遍: 按 node -> way -> relation 的规范顺序写出子集。

        依赖: pip install osmium
        成功返回子集路径；库缺失或提取失败返回 None（调用方回退为直接
        使用原文件）。
        """
        try:
            import osmium   # 惰性导入：未安装时其余功能不受影响
        except ImportError:
            print("警告: 未安装 pyosmium 库，跳过子集提取")
            print("      安装后可大幅加速本地回退处理: pip install osmium")
            return None

        out_path = os.path.join(self.project_path, 'map.osm.pbf')

        # 子集已存在则直接复用（避免重复提取）
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            print(f"OSM子集已存在，直接使用: {out_path}")
            return out_path

        # Windows 上 pyosmium(libosmium) 只能打开纯 ASCII 路径：项目目录含中文时
        # SimpleWriter 直接写 out_path 会报 "The system cannot find the file specified"。
        # 因此子集先写到 ASCII 临时目录，writer 关闭后再用 shutil.move 移入项目目录
        # （shutil 走系统宽字符 API，中文路径正常；同盘移动为重命名，瞬时完成）。
        tmp_dir = self._get_ascii_temp_dir()
        if tmp_dir is None:
            print("警告: 未找到可用的 ASCII 临时目录，跳过子集提取")
            return None
        fd, tmp_path = tempfile.mkstemp(suffix='.osm.pbf', dir=tmp_dir)
        os.close(fd)
        os.remove(tmp_path)  # mkstemp 会预建空文件，交由 SimpleWriter 自行创建

        # bbox 顺序：西,南,东,北
        west = extent['lon_min']
        south = extent['lat_min']
        east = extent['lon_max']
        north = extent['lat_max']
        print(f"按地图范围提取OSM子集 (bbox: {west},{south},{east},{north}) ...")

        try:
            start_time = time.time()

            # ---- 第一遍：判定与收集（pbf 中节点/way/relation 按类型分块存储，
            #      处理 way 时全部节点已回调完毕，relation 时全部 way 已处理完）----
            node_ids = set()   # bbox 内的 node id
            way_ids = set()    # 与 bbox 相交的 way id
            way_refs = {}      # way_id -> 引用的全部节点 id（含 bbox 外，补齐跨边界节点）
            rel_ids = set()    # 成员被保留的 relation id

            class CollectHandler(osmium.SimpleHandler):
                _count = 0

                def node(self, n):
                    CollectHandler._count += 1
                    if CollectHandler._count % 10000000 == 0:
                        print(f"  第一遍扫描中... 已处理 {CollectHandler._count} 个节点")
                    if n.location.valid() and west <= n.location.lon <= east and south <= n.location.lat <= north:
                        node_ids.add(n.id)

                def way(self, w):
                    refs = [nd.ref for nd in w.nodes]
                    if any(ref in node_ids for ref in refs):
                        way_ids.add(w.id)
                        way_refs[w.id] = refs

                def relation(self, r):
                    for m in r.members:
                        if (m.type == 'w' and m.ref in way_ids) or (m.type == 'n' and m.ref in node_ids):
                            rel_ids.add(r.id)
                            break

            CollectHandler().apply_file(local_osm_path, locations=False)

            # 需写出的节点 = bbox 内节点 + 相交 way 引用的全部节点（含 bbox 外）
            referenced_nodes = set(node_ids)
            for refs in way_refs.values():
                referenced_nodes.update(refs)

            if not way_ids:
                print("警告: 地图范围内没有找到任何 OSM 数据（way 为空），请检查范围与数据是否匹配")
            print(f"  第一遍完成: bbox内节点 {len(node_ids)} | 相交way {len(way_ids)} | "
                  f"关联relation {len(rel_ids)} | 需写出节点 {len(referenced_nodes)} | "
                  f"用时 {time.time() - start_time:.0f} 秒")

            # ---- 第二遍：按 node -> way -> relation 的规范顺序写出子集 ----
            # 先写到 ASCII 临时路径（pyosmium 无法直接写含中文的项目目录）
            print(f"写入临时文件 {tmp_path} ...")
            writer = osmium.SimpleWriter(tmp_path)

            class WriteHandler(osmium.SimpleHandler):
                def node(self, n):
                    if n.id in referenced_nodes:
                        writer.add_node(n)

                def way(self, w):
                    if w.id in way_ids:
                        writer.add_way(w)

                def relation(self, r):
                    if r.id in rel_ids:
                        writer.add_relation(r)

            WriteHandler().apply_file(local_osm_path, locations=False)
            writer.close()

            # 子集在 ASCII 临时路径写好后，再移动到（可能含中文的）项目目录
            print(f"移动临时文件 {tmp_path} 到项目目录 {out_path} ...")
            shutil.move(tmp_path, out_path)

            size_mb = os.path.getsize(out_path) / (1024 * 1024)
            print(f"OSM子集提取完成: {out_path} ({size_mb:.1f} MB), "
                  f"总用时 {time.time() - start_time:.0f} 秒")
            return out_path
        except Exception as e:
            # 清理可能不完整的临时文件与输出文件，避免下次误判为已缓存
            for p in (tmp_path, out_path):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            print(f"OSM子集提取失败: {e}")
            return None

    # 本地回退：报警并从 osm_files 寻找本地 OSM 资源，按范围提取子集后返回路径或 None
    def _fallback_local_osm(self):
        """下载/预检失败时的统一回退入口：蜂鸣报警 + 本地资源查找 + 子集提取"""
        self._alert_beep()
        print("尝试从本地 osm_files 目录回退...")
        # 先取地图范围，用于挑选"包含范围且体量最小"的本地数据
        extent = self._get_gpkg_extent()
        local_osm = self._find_local_osm_file(extent)
        if not local_osm:
            print("本地无可用OSM资源")
            return None
        print(f"使用本地OSM资源替代网络下载: {local_osm}")
        # 按地图范围提取子集（全国级大 pbf 直接全量转换非常慢）
        subset = self._extract_osm_subset(local_osm, extent)
        return subset if subset else local_osm

    # 创建Google地图影像图层
    def make_google_layer(self, zoom_level=14):
        """
        下载Google地图瓦片并生成GeoTIFF影像

        参数:
        zoom_level (int): 瓦片缩放级别

        返回:
        str: 成功返回Google影像文件路径，失败返回None
        """
        if os.path.exists(self.GOOGLE_MAP):
            print(f"警告: Google地图影像已存在: {self.GOOGLE_MAP}")
            print(f"跳过下载，直接使用已存在文件: {self.GOOGLE_MAP}")
            return self.GOOGLE_MAP

        if not os.path.exists(self.MAP_EXTENT_4326):
            raise RuntimeError(f"{self.MAP_EXTENT_4326}不存在，请先创建")

        # 网络连通性预检：失败则报警并跳过下载
        print("\n[预检] 正在测试 Google 瓦片服务器连通性...")
        if not self._check_google_network():
            print("=" * 60)
            print("!!! 网络报警: Google 瓦片服务器无法连接，请检查网络/代理 !!!")
            print("=" * 60)
            self._alert_beep()
            print("跳过 Google 地图下载")
            return None

        print("[预检] 网络连通正常")
        print("\n=== 开始下载Google地图影像 ===")
        extent = self._get_gpkg_extent()
        tif_path = self._download_google_tiles(
            extent['lon_min'],
            extent['lon_max'],
            extent['lat_min'],
            extent['lat_max'],
            zoom_level
        )

        print("\n=== Google地图下载完成 ===")
        return tif_path


    # 下载OSM数据
    def download_osm_data(self, output_file=None, timeout=300):
        """
        从OpenStreetMap下载指定区域的全量OSM数据并保存为.osm格式文件

        网络预检失败时，自动回退使用脚本目录 osm_files/ 下的本地OSM资源
        （.osm 或 .osm.pbf，ogr2ogr 原生支持 pbf，后续流程无需转换）。

        参数:
        output_file (str): 输出文件路径，默认为项目目录下的map.osm
        timeout (int): 请求超时时间（秒），默认为300秒

        返回:
        str: OSM文件路径（网络下载或本地回退），失败返回None
        """

        # 检查OSM文件是否存在
        if os.path.exists(self.MAP_OSM):
            print(f"警告: OSM文件已存在: {self.MAP_OSM}")
            return self.MAP_OSM

        if not os.path.exists(self.MAP_EXTENT_4326):
            raise RuntimeError(f"{self.MAP_EXTENT_4326}不存在，请先创建")

        # 网络预检：逐个测试服务器，测通的第一个直接用于下载（下载时不再重新尝试其他服务器）
        print("\n[预检] 正在测试 Overpass(OSM) 服务器连通性...")
        server = self._check_osm_network()
        # 测试：强制使用本地回退，跳过网络下载
        #server = None
        if server is None:
            print("=" * 60)
            print("!!! 网络报警: 所有 Overpass(OSM) 服务器均无法连接，请检查网络/代理 !!!")
            print("=" * 60)
            local_osm = self._fallback_local_osm()
            return local_osm if local_osm else None

        print(f"[预检] 使用服务器: {server['name']} ({server['url']})")

        extent = self._get_gpkg_extent()
        min_lon = extent['lon_min']
        min_lat = extent['lat_min']
        max_lon = extent['lon_max']
        max_lat = extent['lat_max']

        if output_file is None:
            output_file = os.path.join(self.project_path, 'map.osm')

        query_params = {
            "bbox": f"{min_lon}, {min_lat}, {max_lon}, {max_lat}"
        }
        # Overpass QL 查询（供 interpreter 类服务器使用），bbox 顺序：南,西,北,东
        ql_query = (
            f"[out:xml][timeout:{timeout}];"
            f"(node({min_lat},{min_lon},{max_lat},{max_lon});"
            f"way({min_lat},{min_lon},{max_lat},{max_lon});"
            f"relation({min_lat},{min_lon},{max_lat},{max_lon}););"
            f"(._;>;);"   # 递归补齐 way/relation 引用的节点，保证几何完整
            f"out body;"
        )

        headers = OSM_HEADERS

        print(f"\n=== 开始下载OSM数据 ===")
        print(f"边界框: {min_lon:.6f}, {min_lat:.6f}, {max_lon:.6f}, {max_lat:.6f}")
        print(f"目标文件: {output_file}")

        try:
            start_time = time.time()
            if server["type"] == "map":
                # Map API: GET + bbox 查询参数
                response = requests.get(
                    server["url"],
                    params=query_params,
                    headers=headers,
                    timeout=timeout,
                    stream=True
                )
            else:
                # Interpreter API: POST + Overpass QL
                response = requests.post(
                    server["url"],
                    data={"data": ql_query},
                    headers=headers,
                    timeout=timeout,
                    stream=True
                )

            if response.status_code == 200:
                total_size = int(response.headers.get('content-length', 0))
                block_size = 1024

                os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)

                with open(output_file, 'wb') as file:
                    downloaded_size = 0
                    for data in response.iter_content(block_size):
                        downloaded_size += len(data)
                        file.write(data)
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            print(f"\r下载进度: {progress:.1f}% ({downloaded_size / 1024:.1f} KB)", end='')

                download_time = time.time() - start_time
                file_size = os.path.getsize(output_file)
                print(f"\n下载完成！文件大小: {file_size / (1024 * 1024):.2f} MB")
                print(f"下载用时: {download_time:.2f} 秒")
                print("=== OSM数据下载完成 ===")

                return output_file
            else:
                print(f"下载失败，状态码: {response.status_code}")
                if "Request size too large" in response.text:
                    print("提示: 请求的区域可能太大。请尝试减小边界框的大小。")

        except requests.exceptions.Timeout:
            print(f"请求超时，超时时间: {timeout} 秒")
        except requests.exceptions.RequestException as e:
            print(f"发生网络错误: {e}")
        except Exception as e:
            print(f"发生未知错误: {e}")

        # 下载失败：报警并回退本地资源
        print("=" * 60)
        print("!!! 网络下载失败，尝试本地回退 !!!")
        print("=" * 60)
        local_osm = self._fallback_local_osm()
        return local_osm if local_osm else None
    # 提取OSM数据到GPKG文件
    def extract_osm_to_gpkg(self, osm_file=None, layers=None):
        """
        使用ogr2ogr命令行工具提取OSM文件，转换为GeoPackage格式
        
        参数:
        osm_file (str): 输入OSM文件路径，默认为项目目录下的map.osm
        layers (list): 要转换的图层列表，如['points', 'lines', 'multipolygons']
                      默认为['points', 'lines', 'multipolygons']
        
        返回:
        list: 成功转换的GPKG文件路径列表
        """
        if osm_file is None:
            osm_file = os.path.join(self.project_path, 'map.osm')
        
        if layers is None:
            layers = ['points', 'lines', 'multipolygons']

        output_files = {}

        # 断点续传：产物已存在且非空的图层直接复用，只提取缺失图层
        pending_layers = []
        for layer in layers:
            output_file = os.path.join(self.project_path, f'osm_{layer}.gpkg')
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                print(f"跳过提取(产物已存在): {os.path.basename(output_file)}")
                output_files[layer] = output_file
            else:
                pending_layers.append(layer)

        if not pending_layers:
            print("全部OSM图层产物已存在，跳过提取")
            return output_files

        if not os.path.exists(osm_file):
            print(f"错误: OSM文件不存在: {osm_file}")
            sys.exit(1)

        print(f"\n=== 开始提取OSM数据 ===")
        print(f"输入文件: {osm_file}")
        print(f"待提取图层: {pending_layers}")

        for layer in pending_layers:
            output_file = os.path.join(self.project_path, f'osm_{layer}.gpkg')

            cmd = [
                'ogr2ogr',
                '-f', 'GPKG',
                '-nln', layer,
                output_file,
                osm_file,
                layer
            ]
            
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                print(f"成功提取 {layer} 图层 -> {os.path.basename(output_file)}")
                output_files[layer] = output_file
            except subprocess.CalledProcessError as e:
                print(f"提取 {layer} 图层失败: {e.stderr}")
        
        print("=== OSM数据提取完成 ===")
        return output_files


    # 修复几何图形错误
    def clean_geometries(self, gdf):
        gdf = gdf[gdf.geometry.notna()].copy()
        # 官方修复函数，比 buffer(0) 更精准
        gdf['geometry'] = gdf['geometry'].apply(make_valid)
        # 过滤修复后依然无效的几何
        gdf = gdf[gdf.is_valid]
        # 单部件化
        gdf = gdf.explode(index_parts=False).reset_index(drop=True)
        return gdf
    # 日志记录函数
    def log_step(self, message):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [OSM相交] {message}", flush=True)

    # 检查OSM相交产物是否已全部生成（断点续传）
    def _get_cached_extent_osm_files(self):
        """
        检查三个OSM相交产物(extent_osm_*.gpkg)是否全部存在且非空。

        全部存在返回 {layer_type: 文件路径} 字典；任一缺失返回 None。
        """
        products = {
            'points': self.EXTENT_OSM_POINTS,
            'lines': self.EXTENT_OSM_LINES,
            'multipolygons': self.EXTENT_OSM_MULTIPOLYGONS,
        }
        missing = [p for p in products.values()
                   if not (os.path.exists(p) and os.path.getsize(p) > 0)]
        if missing:
            for p in missing:
                print(f"OSM相交产物缺失: {os.path.basename(p)}")
            return None
        print("OSM相交产物已全部存在，跳过OSM下载/提取/相交")
        return products

    # 相交OSM图层与地图范围图层
    def intersect_osm_with_extent(self, extent_gpkg=None, osm_layers=None):
        """
        将OSM图层与地图范围图层进行相交运算，只保留落在地图范围内的OSM数据

        参数:
        extent_gpkg (str): 地图范围GPKG文件路径，默认为项目目录下的"地图范围"
        osm_layers (dict): OSM图层字典，key为类型名，value为图层文件路径
                          默认为项目目录下的osm_points.gpkg, osm_lines.gpkg, osm_multipolygons.gpkg

        返回:
        dict: 相交结果文件路径字典，key为类型名，value为输出文件路径
        """
        # 断点续传：相交产物全部已存在时直接返回（避免无谓的读取与运算）
        cached = self._get_cached_extent_osm_files()
        if cached is not None:
            self.log_step("相交产物已全部存在，跳过相交运算")
            return cached

        import geopandas as gpd
        from shapely.errors import TopologicalError

        print("\n=== 开始OSM图层与地图范围相交运算 ===")
        self.log_step("函数已进入")
        
        if extent_gpkg is None:
            extent_gpkg = self.MAP_EXTENT_4326
        
        self.log_step(f"地图范围文件: {extent_gpkg}")
        if not os.path.exists(extent_gpkg):
            print(f"错误: 地图范围文件不存在: {extent_gpkg}")
            return {}
        self.log_step(f"地图范围文件存在，大小: {os.path.getsize(extent_gpkg)} bytes")
        
        if osm_layers is None:
            osm_layers = {
                'points': self.OSM_POINTS,
                'lines': self.OSM_LINES,
                'multipolygons': self.OSM_MULTIPOLYGONS
            }
        self.log_step(f"待相交OSM图层: {osm_layers}")
        
        result_files = {}
        
        try:
            self.log_step("开始读取地图范围GPKG")
            extent_gdf = gpd.read_file(extent_gpkg)
            self.log_step(f"地图范围读取完成，要素数: {len(extent_gdf)}, CRS: {extent_gdf.crs}")
            if extent_gdf.empty:
                print("警告: 地图范围图层为空")
                return {}
            
            self.log_step("开始检查地图范围几何有效性")
            if not extent_gdf.is_valid.all():
                self.log_step("地图范围存在无效几何，开始make_valid")
                extent_gdf = extent_gdf.make_valid()
                self.log_step("地图范围make_valid完成")
            else:
                self.log_step("地图范围几何全部有效")
                
        except Exception as e:
            print(f"读取地图范围文件失败: {e}")
            return {}
        
        for layer_type, osm_file in osm_layers.items():
            # 断点续传：该层相交产物已存在且非空时跳过，只处理缺失图层
            output_file = os.path.join(self.project_path, f'extent_osm_{layer_type}.gpkg')
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                self.log_step(f"跳过相交(产物已存在): {os.path.basename(output_file)}")
                result_files[layer_type] = output_file
                continue
            self.log_step(f"开始处理 {layer_type} 图层: {osm_file}")
            if not os.path.exists(osm_file):
                print(f"警告: OSM文件不存在，跳过: {osm_file}")
                continue
            self.log_step(f"{layer_type} 文件存在，大小: {os.path.getsize(osm_file)} bytes")
            
            try:
                layer_start_time = time.time()
                self.log_step(f"开始读取 {layer_type} GPKG")
                osm_gdf = gpd.read_file(osm_file)
                self.log_step(f"{layer_type} 读取完成，要素数: {len(osm_gdf)}, CRS: {osm_gdf.crs}")
                
                if osm_gdf.empty:
                    print(f"警告: OSM图层 {layer_type} 为空，跳过")
                    continue
                
                # 调用类方法清理几何
                self.log_step(f"开始清理 {layer_type} 几何")
                osm_gdf = self.clean_geometries(osm_gdf)
                self.log_step(f"{layer_type} 几何清理完成，剩余要素数: {len(osm_gdf)}, 是否全部有效: {osm_gdf.is_valid.all()}")
                
                if not osm_gdf.is_valid.all():
                    self.log_step(f"{layer_type} 仍存在无效几何，开始make_valid")
                    osm_gdf = osm_gdf.make_valid()
                    self.log_step(f"{layer_type} make_valid完成")
                
                # 根据 layer_type 自动保留正确的几何类型
                before_filter_count = len(osm_gdf)
                self.log_step(f"开始按几何类型过滤 {layer_type}，过滤前要素数: {before_filter_count}")
                if layer_type == "multipolygons":
                    osm_gdf = osm_gdf[osm_gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]
                elif layer_type == "lines":
                    osm_gdf = osm_gdf[osm_gdf.geometry.type.isin(["LineString", "MultiLineString"])]
                elif layer_type == "points":
                    osm_gdf = osm_gdf[osm_gdf.geometry.type.isin(["Point", "MultiPoint"])]
                self.log_step(f"{layer_type} 几何类型过滤完成，过滤后要素数: {len(osm_gdf)}")
                    
                # 爆炸多部件几何（避免拓扑错误）
                self.log_step(f"开始explode {layer_type} 多部件几何")
                osm_gdf = osm_gdf.explode(index_parts=False).reset_index(drop=True)
                self.log_step(f"{layer_type} explode完成，要素数: {len(osm_gdf)}")

                # 最后再清理一次无效几何
                self.log_step(f"开始最终过滤 {layer_type} 无效几何")
                osm_gdf = osm_gdf[osm_gdf.is_valid]
                self.log_step(f"{layer_type} 最终有效几何过滤完成，要素数: {len(osm_gdf)}")
                if osm_gdf.empty:
                    print(f"警告: 过滤无效几何后 {layer_type} 为空，跳过")
                    return result_files
                
                # 检查坐标参考系是否一致
                if extent_gdf.crs != osm_gdf.crs:
                    print(f"坐标参考系不一致，正在转换 {layer_type} 图层...")
                    self.log_step(f"{layer_type} CRS转换开始: {osm_gdf.crs} -> {extent_gdf.crs}")
                    osm_gdf = osm_gdf.to_crs(extent_gdf.crs)
                    self.log_step(f"{layer_type} CRS转换完成")
                else:
                    self.log_step(f"{layer_type} CRS一致，无需转换")
                
                print(f"执行 {layer_type} 图层相交运算...")
                self.log_step(f"{layer_type} overlay开始，OSM要素数: {len(osm_gdf)}, 范围要素数: {len(extent_gdf)}")
                intersection_gdf = gpd.overlay(osm_gdf, extent_gdf, how='intersection')
                self.log_step(f"{layer_type} overlay完成，结果要素数: {len(intersection_gdf)}")
                
                if intersection_gdf.empty:
                    self.log_step(f"警告: {layer_type} 图层与地图范围无相交部分")
                    continue
                
                output_file = os.path.join(self.project_path, f'extent_osm_{layer_type}.gpkg')
                self.log_step(f"开始写出 {layer_type} 相交结果: {output_file}")
                intersection_gdf.to_file(output_file, layer=f'extent_osm_{layer_type}', driver='GPKG')
                self.log_step(f"{layer_type} 写出完成，文件大小: {os.path.getsize(output_file)} bytes")
                result_files[layer_type] = output_file
                self.log_step(f"成功: extent_osm_{layer_type}.gpkg 已生成 ({len(intersection_gdf)} 个要素)")
                self.log_step(f"{layer_type} 图层处理完成，耗时: {time.time() - layer_start_time:.2f} 秒")
                
            except TopologicalError as e:
                self.log_step(f"拓扑错误 ({layer_type}): {e}")
                sys.exit(1)
            except Exception as e:
                self.log_step(f"相交运算错误 ({layer_type}) Exception: {type(e).__name__}: {e}")
                sys.exit(1)
        
        self.log_step(f"全部OSM相交处理结束，生成结果: {result_files}")
        self.log_step("=== OSM图层相交运算完成 ===")
        return result_files
        
    # 添加extent_osm图层到项目并加载样式
    def add_extent_osm_layers_with_styles(self, extent_osm_files=None,style_map=None):
        """
        将extent_osm图层添加到QGIS项目并加载QML样式
        
        参数:
        extent_osm_files (dict): extent_osm文件路径字典，key为类型名，value为文件路径
                               默认为项目目录下的 EXTENT_OSM_POINTS 等文件
        
        返回:
        list: 成功添加的图层对象列表
        """
        if extent_osm_files is None:
            extent_osm_files = {
                'multipolygons': self.EXTENT_OSM_MULTIPOLYGONS,
                'lines': self.EXTENT_OSM_LINES,
                'points': self.EXTENT_OSM_POINTS,
            }
        
        if style_map is None:
            style_map = {
                'points': self.DEFAULT_TEMPLATE[self.EXTENT_OSM_POINTS_LAYER_NAME],
                'lines': self.DEFAULT_TEMPLATE[self.EXTENT_OSM_LINES_LAYER_NAME],
                'multipolygons': self.DEFAULT_TEMPLATE[self.EXTENT_OSM_MULTIPOLYGONS_LAYER_NAME]
            }
        
        added_layers = []
        
        print("\n=== 开始添加extent_osm图层并加载样式 ===")
        
        for layer_type, gpkg_file in extent_osm_files.items():
            layer_name = f'extent_osm_{layer_type}'
            layer_style = style_map.get(layer_type)
            
            added = self.add_layer_to_project(gpkg_file, layer_name, layer_style)
            if not added:
                continue
            
            for layer in self.project.mapLayers().values():
                if layer.name() == layer_name:
                    added_layers.append(layer)
                    break
        
        print(f"extent_os_osm图层添加完成: {added_layers}")
        return added_layers
        
    # 裁剪DEM影像
    def extract_dem_by_extent(self, dem_files_dir=None, extent_gpkg=None):
        """
        根据地图范围裁剪DEM影像，生成 EXTENT_DEM 文件
        
        参数:
        dem_files_dir (str): DEM文件所在目录，默认为脚本目录下的dem_files文件夹
        extent_gpkg (str): 地图范围GPKG文件路径，默认为项目目录下的"地图范围"
        
        返回:
        str: 裁剪后的DEM文件路径，如果失败返回None
        """
        from osgeo import gdal
        
        print("\n=== 开始裁剪DEM影像 ===")
        
        if dem_files_dir is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            dem_files_dir = os.path.join(current_dir, "dem_files")
        
        if extent_gpkg is None:
            extent_gpkg = self.MAP_EXTENT_4326
        
        if not os.path.exists(dem_files_dir):
            print(f"错误: DEM文件目录不存在: {dem_files_dir}")
            return None
        
        if not os.path.exists(extent_gpkg):
            print(f"错误: 地图范围文件不存在: {extent_gpkg}")
            return None
        
        dem_files = []
        for f in os.listdir(dem_files_dir):
            if f.lower().endswith(('.tif', '.tiff')):
                dem_files.append(os.path.join(dem_files_dir, f))
        
        if not dem_files:
            print("警告: DEM文件目录中未找到TIF文件")
            return None
        
        extent_info = self._get_gpkg_extent()
        lon_min = extent_info['lon_min']
        lon_max = extent_info['lon_max']
        lat_min = extent_info['lat_min']
        lat_max = extent_info['lat_max']
        
        print(f"地图范围: lon[{lon_min:.6f}, {lon_max:.6f}], lat[{lat_min:.6f}, {lat_max:.6f}]")
        
        for dem_file in dem_files:
            print(f"检查DEM文件: {os.path.basename(dem_file)}")
            
            try:
                ds = gdal.Open(dem_file)
                if not ds:
                    print(f"无法打开DEM文件: {dem_file}")
                    continue
                
                geotransform = ds.GetGeoTransform()
                dem_min_x = geotransform[0]
                dem_max_x = geotransform[0] + geotransform[1] * ds.RasterXSize
                dem_min_y = geotransform[3] + geotransform[5] * ds.RasterYSize
                dem_max_y = geotransform[3]
                
                if (lon_min >= dem_max_x or lon_max <= dem_min_x or
                    lat_min >= dem_max_y or lat_max <= dem_min_y):
                    print(f"DEM文件不包含地图范围，跳过")
                    ds = None
                    continue
                
                print(f"DEM文件包含地图范围，开始裁剪...")
                
                output_file = self.EXTENT_DEM
                
                gdal.Warp(
                    output_file,
                    dem_file,
                    outputBounds=[lon_min, lat_min, lon_max, lat_max],
                    dstSRS="EPSG:4326",
                    format="GTiff",
                    resampleAlg=gdal.GRA_Bilinear
                )
                
                ds = None
                
                if os.path.exists(output_file):
                    print(f"成功: {output_file} 已生成")
                    return output_file
                else:
                    print("错误: 裁剪失败，输出文件未生成")
                    return None
                    
            except Exception as e:
                print(f"处理DEM文件时出错: {e}")
                continue
        
        print("未找到包含地图范围的DEM文件")
        return None

    # 从DEM文件进行三次方重采样，生成平滑的图层
    def generate_dem_resampled_by_gra_cubic(self, dem_file=None, output_file=None, resolution_m=10):
        """
        使用GDAL三次方插值对DEM进行重采样，生成约10m精度的更精细DEM栅格。

        参数:
        dem_file (str): 输入DEM文件路径，默认为项目目录下的 EXTENT_DEM
        output_file (str): 输出DEM文件路径，默认为项目目录下的 EXTENT_DEM_RESAMPLED
        resolution_m (float): 输出DEM目标像元大小，单位米，默认10

        返回:
        str: 重采样后的DEM文件路径，如果失败返回None
        """
        from osgeo import gdal, osr

        print("\n=== 开始DEM三次方重采样 ===")

        if dem_file is None:
            dem_file = self.EXTENT_DEM

        if output_file is None:
            output_file = self.EXTENT_DEM_RESAMPLED

        if resolution_m <= 0:
            print(f"错误: 输出DEM目标像元大小必须大于0米，当前值: {resolution_m}")
            return None

        if not os.path.exists(dem_file):
            print(f"错误: DEM文件不存在: {dem_file}")
            return None

        output_dir = os.path.dirname(output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        os.environ['GDAL_DATA'] = os.path.join(sys.prefix, "Library", "share", "gdal")
        os.environ['PATH'] = f"{os.path.join(sys.prefix, 'Library', 'bin')};{os.environ['PATH']}"

        if os.path.abspath(dem_file) == os.path.abspath(output_file):
            print("错误: 输出DEM文件不能与输入DEM文件相同")
            return None

        try:
            gdal.UseExceptions()
            src_ds = gdal.Open(dem_file, gdal.GA_ReadOnly)
            if src_ds is None:
                print(f"错误: 无法打开DEM文件: {dem_file}")
                return None

            src_band = src_ds.GetRasterBand(1)
            nodata_value = src_band.GetNoDataValue() if src_band else None

            geotransform = src_ds.GetGeoTransform()
            projection = src_ds.GetProjection()
            spatial_ref = osr.SpatialReference()
            is_geographic = False
            if projection and spatial_ref.ImportFromWkt(projection) == 0:
                is_geographic = bool(spatial_ref.IsGeographic())

            if is_geographic:
                min_y = geotransform[3] + geotransform[5] * src_ds.RasterYSize
                max_y = geotransform[3]
                center_lat = (min_y + max_y) / 2
                meters_per_degree_lat = 111320.0
                meters_per_degree_lon = meters_per_degree_lat * math.cos(math.radians(center_lat))
                if abs(meters_per_degree_lon) < 1e-6:
                    print("错误: 无法在极区附近将10米分辨率换算为经度单位")
                    src_ds = None
                    return None
                x_res = resolution_m / meters_per_degree_lon
                y_res = resolution_m / meters_per_degree_lat
                print(f"输入DEM为经纬度坐标系，按中心纬度{center_lat:.6f}换算为约{resolution_m}m像元")
            else:
                linear_units = spatial_ref.GetLinearUnits() if projection else 1.0
                if linear_units <= 0:
                    linear_units = 1.0
                x_res = resolution_m / linear_units
                y_res = resolution_m / linear_units
                print(f"输入DEM为投影坐标系，输出像元大小设置为{resolution_m}m x {resolution_m}m")

            warp_kwargs = {
                "format": "GTiff",
                "xRes": x_res,
                "yRes": y_res,
                "resampleAlg": gdal.GRA_Cubic,
                "outputType": gdal.GDT_Float32,
                "multithread": True,
                "creationOptions": ["TILED=YES", "COMPRESS=LZW", "BIGTIFF=IF_SAFER"]
            }
            if nodata_value is not None:
                warp_kwargs["srcNodata"] = nodata_value
                warp_kwargs["dstNodata"] = nodata_value

            result_ds = gdal.Warp(
                output_file,
                src_ds,
                options=gdal.WarpOptions(options=["-overwrite"], **warp_kwargs)
            )

            src_ds = None
            if result_ds is not None:
                result_ds = None

            if os.path.exists(output_file):
                print(f"DEM三次方重采样成功: {output_file}")
                return output_file

            print("错误: DEM三次方重采样失败，输出文件未生成")
            return None
        except Exception as e:
            print(f"DEM三次方重采样失败: {e}")
            return None

    # 从DEM文件提取等高线
    def generate_contour_from_dem(self, dem_file=None, contour_file=None):
        if os.path.exists(self.CONTOUR_FILE):
            print(f"警告: 等高线文件已存在: {self.CONTOUR_FILE}")
            print(f"跳过等高线提取，直接使用已存在文件: {self.CONTOUR_FILE}")
            return self.CONTOUR_FILE
        """
        从DEM文件提取等高线，生成 CONTOUR_FILE 文件
        
        参数:
        dem_file (str): 输入DEM文件路径，默认为项目目录下的 EXTENT_DEM
        contour_file (str): 输出等高线GPKG文件路径，默认为 CONTOUR_FILE
        
        返回:
        str: 等高线文件路径，如果失败返回None
        """
        import subprocess
        
        print("\n=== 开始提取等高线 ===")
        
        if dem_file is None:
            dem_file = self.EXTENT_DEM
        
        if contour_file is None:
            contour_file = self.CONTOUR_FILE
        
        if not os.path.exists(dem_file):
            print(f"错误: DEM文件不存在: {dem_file}")
            return None
        
        os.environ['GDAL_DATA'] = os.path.join(sys.prefix, "Library", "share", "gdal")
        os.environ['PATH'] = f"{os.path.join(sys.prefix, 'Library', 'bin')};{os.environ['PATH']}"
        
        command = [
            "gdal_contour",
            "-b", "1",
            "-a", "ELEV",
            "-i", "10.0",
            "-f", "GPKG",
            dem_file,
            contour_file
        ]
        
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True
            )
            print("等高线提取成功")
            if os.path.exists(contour_file):
                self.CONTOUR_FILE = contour_file
                return contour_file
            else:
                print("错误: 等高线文件未生成")
                return None
        except subprocess.CalledProcessError as e:
            print(f"等高线提取失败: {e.stderr}")
            return None

    # 生成DEM高程渲染层
    def make_dem_render_layer(self, dem_file=None, render_file=None):
        """
        生成DEM高程渲染层文件
        
        参数:
        dem_file (str): 输入DEM文件路径，默认为 EXTENT_DEM
        render_file (str): 输出DEM高程渲染层文件路径，默认为 EXTENT_DEM_RENDER_LAYER
        
        返回:
        str: DEM高程渲染层文件路径，如果失败返回None
        """
        import shutil
        
        print("\n=== 开始生成DEM高程渲染层 ===")
        
        if dem_file is None:
            dem_file = self.EXTENT_DEM
        
        if render_file is None:
            render_file = self.EXTENT_DEM_RENDER_LAYER

        if not os.path.exists(dem_file):
            print(f"错误: DEM文件不存在: {dem_file}")
            return None
        
        shutil.copy2(dem_file, render_file)
        print(f"生成DEM高程渲染层文件: {dem_file} -> {render_file}")

        return render_file


    # 生成山体阴影
    def generate_hillshade(self, dem_file=None, hillshade_file=None, azimuth=315, altitude=45, z_factor=1):
        """
        生成山体阴影
        
        参数:
        dem_file (str): 输入DEM文件路径，默认为项目目录下的extent_dem.tif
        hillshade_file (str): 输出山体阴影文件路径，默认为extent_dem_hillshadow.tif
        azimuth (float): 太阳方位角（度），默认315度（西北方向）
        altitude (float): 太阳高度角（度），默认45度
        z_factor (float): 高程缩放因子，默认1
        
        返回:
        str: 山体阴影文件路径，如果失败返回None
        """
        import subprocess
        from qgis.core import QgsRasterLayer
        
        print("\n=== 开始生成山体阴影 ===")
        
        if dem_file is None:
            dem_file = os.path.join(self.project_path, "extent_dem.tif")
        
        if hillshade_file is None:
            hillshade_file = os.path.join(self.project_path, "extent_dem_hillshadow.tif")
        
        if not os.path.exists(dem_file):
            print(f"错误: DEM文件不存在: {dem_file}")
            return None
        
        os.environ['GDAL_DATA'] = os.path.join(sys.prefix, "Library", "share", "gdal")
        os.environ['PATH'] = f"{os.path.join(sys.prefix, 'Library', 'bin')};{os.environ['PATH']}"
        
        # 3857时候执行的命令
        command = [
            "gdaldem",
            "hillshade",
            "-az", str(azimuth),
            "-alt", str(altitude),
            "-z", str(z_factor),
            dem_file,
            hillshade_file
        ]

        # 判断dem_file的坐标系，如果是4326，则需要添加 -s参数
        # 4326坐标系需要添加 -s参数
        dem_file_layer = QgsRasterLayer(dem_file, self.EXTENT_DEM_LAYER_NAME)
        crs = dem_file_layer.crs()
        print(f"DEM文件坐标系: {crs.authid()}")
        if crs.authid() == "EPSG:4326":
            print("DEM文件坐标系为4326，需要添加 -s参数")
            command.append("-s")
            command.append(self.Z_FACTOR_LEN)
        
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True
            )
            print(f"山体阴影生成成功:{result}")

            if os.path.exists(hillshade_file):
                return hillshade_file
            else:
                print("错误: 山体阴影文件未生成")
                return None
        except subprocess.CalledProcessError as e:
            print(f"山体阴影生成失败: {e.stderr}")
            return None


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
        '''
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
        '''
        return output_layer
    
    def load_raster_layer(self, raster_file, layer_name=None, style_name=""):
        """
        加载栅格图层
        
        参数:
        raster_file (str): 栅格文件路径
        
        返回:
        QgsRasterLayer: 加载的图层对象，如果失败返回None
        """
        from qgis.core import QgsRasterLayer
        
        raster_layer = QgsRasterLayer(raster_file, layer_name or os.path.basename(raster_file))
        if not raster_layer.isValid():
            print(f"错误: 栅格图层加载失败: {raster_file}")
            return None
        else:
            print(f"加载栅格图层成功: {raster_file}")
            if style_name:
                style_path = os.path.join(self.TEMPLATE_PATH, style_name)
                if os.path.exists(style_path):
                    print(f"加载样式: {style_path}")
                    raster_layer.loadNamedStyle(style_path)
                    raster_layer.triggerRepaint()
                else:
                    print(f"样式文件不存在: {style_path}")
            else:
                print(f"未指定样式文件，不加载样式")
            return raster_layer

    def load_vector_layer(self, vector_file, layer_name=None, style_name=""):
        """
        加载矢量图层
        
        参数:
        vector_file (str): 矢量文件路径
        
        返回:
        QgsVectorLayer: 加载的图层对象，如果失败返回None
        """
        from qgis.core import QgsVectorLayer
        
        vector_layer = QgsVectorLayer(vector_file, layer_name or os.path.basename(vector_file), "ogr")
        if not vector_layer.isValid():
            print(f"[错误] 矢量图层加载失败：{vector_file}")
            self.qgs_app.exitQgis()
            sys.exit(1)
        else:
            print(f"[OK] 矢量图层加载成功,范围：{vector_layer.extent()}")
     
        vector_layer = self._reproject_to_3857(vector_layer)
        if not vector_layer.isValid():
            print(f"[错误] 矢量图层重投影为 EPSG:3857 失败：{vector_file}")
            self.qgs_app.exitQgis()
            sys.exit(1)
        else:
            print(f"[OK] 矢量图层重投影成功,范围：{vector_layer.extent()}")

        if style_name:
            style_path = os.path.join(self.TEMPLATE_PATH, style_name)
            if os.path.exists(style_path):
                print(f"加载样式: {style_path}")
                vector_layer.loadNamedStyle(style_path)
                vector_layer.triggerRepaint()
            else:
                print(f"样式文件不存在: {style_path}")
        else:
            print(f"未指定样式文件，不加载样式")
        
        return vector_layer
        

    # 20260524，改成通用打印模式
    # 将打印布局模板(qpt)添加到当前 QGIS 工程
    def add_layout_templet(self, qpt_path, layout_name):
        """
        把打印布局模板(.qpt)注册到工程的布局管理器，随 save_project 一起保存。

        参数:
        qpt_path (str): qpt 模板文件路径
        layout_name (str): 布局名称（同名布局已存在时会先移除，避免重复）

        返回:
        bool: 添加成功返回 True，失败返回 False（不中断后续流程）
        """
        from qgis.core import (
            QgsProject,
            QgsPrintLayout,
            QgsReadWriteContext,
            QgsPathResolver
        )
        from qgis.PyQt.QtXml import QDomDocument

        if not os.path.exists(qpt_path):
            print(f"[错误] 找不到布局模板：{qpt_path}")
            return False

        project = QgsProject.instance()
        layout_manager = project.layoutManager()

        # 同名布局已存在时先移除，避免重复添加
        for existing in layout_manager.layouts():
            if existing.name() == layout_name:
                layout_manager.removeLayout(existing)
                print(f"[OK] 已移除同名布局：{layout_name}")

        # 解析 qpt 模板
        doc = QDomDocument()
        with open(qpt_path, "r", encoding="utf-8") as f:
            qpt_xml = f.read()
        ok, err_msg, err_line, err_col = doc.setContent(qpt_xml)
        if not ok:
            print(f"[错误] QPT XML 解析失败（第 {err_line} 行，列 {err_col}）：{err_msg}")
            return False

        # 从模板加载布局项
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        ctx = QgsReadWriteContext()
        ctx.setPathResolver(QgsPathResolver(qpt_path))
        loaded_items, loaded_ok = layout.loadFromTemplate(doc, ctx, True)
        if not loaded_ok:
            print(f"[错误] 布局模板加载失败：{qpt_path}")
            return False
        layout.setName(layout_name)

        layout_manager.addLayout(layout)
        print(f"[OK] 打印布局已添加到工程：{layout_name} <- {qpt_path}（{len(loaded_items)} 个布局项）")
        return True

    def export_map_by_layout_templet(self,layers_to_show=[],
        map_title="广州蓝天训练用途",
        map_maker="1121-奀奀的排骨",
        bg_satellite=None,
        blank_pct=None,
        border=None,
        longest_side=None,
        project_scale_parm=None,
        icon_clr=None
        ):
        """
        打印地图
        
        参数:
        layers_to_show (list): 要在打印图中显示的图层列表。
        map_title (str): 地图标题。
        map_maker (str): 地图制作人。
        bg_satellite (str): 背景卫星图层。
        blank_pct (float): 空白比例。
        border (float): 边框宽度。
        longest_side (float): 最长边长度。
        project_scale_parm (float): 项目比例参数。
        
        返回:
        None
        """
        # 参数默认值在类定义时求值（此时 self 尚不存在），故用 None 哨兵，这里回退到实例属性
        if bg_satellite is None:
            bg_satellite = self.BG_SATELLITE_N
        if blank_pct is None:
            blank_pct = self.BLANK_PCT
        if border is None:
            border = self.BORDER
        if longest_side is None:
            longest_side = self.LONGEST_SIDE
        if project_scale_parm is None:
            project_scale_parm = self.PROJECT_SCALE_PARM
        if icon_clr is None:
            icon_clr = self.ICON_CLR
            
        from qgis.core import (
            QgsProject,
            QgsPrintLayout,
            QgsReadWriteContext,
            QgsLayoutItemMap,
            QgsExpressionContextUtils, 
            QgsLayoutExporter,
            QgsPathResolver,
            QgsVectorLayer
        )
        from qgis.PyQt.QtXml import QDomDocument
        from qgis.PyQt.QtCore import QSize, QRectF
        
        if layers_to_show:
            print(f"[OK] 打印图中显示的图层：{layers_to_show}")
            # 创建打印项目
            project_print = QgsProject.instance()
            project_print.clear()
            project_print.setCrs(self.crs)
            print(f"[OK] 打印qgis项目 CRS：{self.crs.authid()}")
        else:
            print(f"[错误] 打印图中显示的图层为空")
            self.qgs_app.exitQgis()
            sys.exit(1)

        # 加载地图范围图层
        extent_map_layer = QgsVectorLayer(self.MAP_EXTENT_3587, "地图范围", "ogr")
        if not extent_map_layer.isValid():
            print(f"[错误] 矢量图层加载失败：{self.MAP_EXTENT_3587}")
            self.qgs_app.exitQgis()
            sys.exit(1)
        else:
            print(f"[OK] 地图范围图层加载成功,范围：{extent_map_layer.extent()}")
            
        extent_map_layer = self._reproject_to_3857(extent_map_layer)
        if not extent_map_layer.isValid():
            print(f"[错误] 矢量图层重投影失败：{self.MAP_EXTENT_3587}")
            self.qgs_app.exitQgis()
            sys.exit(1)
        else:
            print(f"[OK] 地图范围图层重投影成功,范围：{extent_map_layer.extent()}")

        # 只需要在打印图项目中添加地图范围。
        project_print.addMapLayer(extent_map_layer,False)
        QgsExpressionContextUtils.setProjectVariable(project_print, self.SYS_PARAMS_BG_SATELLITE, bg_satellite)
        QgsExpressionContextUtils.setProjectVariable(project_print, self.SYS_PARAMS_BORDER, border)
        QgsExpressionContextUtils.setProjectVariable(project_print, self.SYS_PARAMS_LONGEST_SIDE, longest_side)
        QgsExpressionContextUtils.setProjectVariable(project_print, self.SYS_PARAMS_PROJECT_SCALE_PARM, project_scale_parm)
        QgsExpressionContextUtils.setProjectVariable(project_print, self.SYS_PARAMS_BLANK_PCT, blank_pct)
        QgsExpressionContextUtils.setProjectVariable(project_print, self.SYS_PARAMS_MAP_TITLE, map_title)
        QgsExpressionContextUtils.setProjectVariable(project_print, self.SYS_PARAMS_MAP_MAKER, map_maker)
        if bg_satellite == self.BG_SATELLITE_Y:
            QgsExpressionContextUtils.setProjectVariable(project_print, self.SYS_PARAMS_ICON_CLR, self.ICON_CLR_orange)
        else:
            QgsExpressionContextUtils.setProjectVariable(project_print, self.SYS_PARAMS_ICON_CLR, self.ICON_CLR)



        if not os.path.exists(self.QPT_PATH):
            print(f"[错误] 找不到布局模板：{self.QPT_PATH}")
            self.qgs_app.exitQgis()
            sys.exit(1)
        else:
            print(f"[OK] 找到布局模板：{self.QPT_PATH}")

        with open(self.QPT_PATH, "r", encoding="utf-8") as f:
            qpt_xml = f.read()
        
        print(f"已读取布局模板内容")
        doc = QDomDocument()
        ok, err_msg, err_line, err_col = doc.setContent(qpt_xml)

        if not ok:
            print(f"[错误] QPT XML 解析失败（第 {err_line} 行，列 {err_col}）：{err_msg}")
            self.qgs_app.exitQgis()
            sys.exit(1)

        layout = QgsPrintLayout(project_print)
        layout.initializeDefaults()
        print(f"已初始化布局模板: {self.QPT_PATH}")

        ctx = QgsReadWriteContext()
        ctx.setPathResolver(QgsPathResolver(self.QPT_PATH))

        loaded_items, loaded_ok = layout.loadFromTemplate(doc, ctx, True)
        if not loaded_ok:
            print("[错误] 布局模板加载失败，请检查 QPT 文件格式")
            self.qgs_app.exitQgis()
            sys.exit(1)

        print(f"[OK] {self.QPT_PATH} 布局模板已加载，共 {len(loaded_items)} 个布局项")

        QgsExpressionContextUtils.setLayoutVariable(layout, self.SYS_PARAMS_BG_SATELLITE, bg_satellite)
        QgsExpressionContextUtils.setLayoutVariable(layout, self.SYS_PARAMS_BORDER, border)
        QgsExpressionContextUtils.setLayoutVariable(layout, self.SYS_PARAMS_LONGEST_SIDE, longest_side)
        QgsExpressionContextUtils.setLayoutVariable(layout, self.SYS_PARAMS_PROJECT_SCALE_PARM, project_scale_parm)
        QgsExpressionContextUtils.setLayoutVariable(layout, self.SYS_PARAMS_BLANK_PCT, blank_pct)
        QgsExpressionContextUtils.setLayoutVariable(layout, self.SYS_PARAMS_MAP_TITLE, map_title)
        QgsExpressionContextUtils.setLayoutVariable(layout, self.SYS_PARAMS_MAP_MAKER, map_maker)
        if bg_satellite == self.BG_SATELLITE_Y:
            QgsExpressionContextUtils.setLayoutVariable(layout, self.SYS_PARAMS_ICON_CLR, self.ICON_CLR_orange)
        else:
            QgsExpressionContextUtils.setLayoutVariable(layout, self.SYS_PARAMS_ICON_CLR, self.ICON_CLR)

        print(f"[OK] 布局变量已设置：Longest_side={self.LONGEST_SIDE}, Blank_pct={self.BLANK_PCT}, Border={self.BORDER}")

        # 设置打印范围
        map_extent = extent_map_layer.extent()
        
        map_items_found = 0
        for item in layout.items():
            if isinstance(item, QgsLayoutItemMap):
                map_items_found += 1
                item.setFollowVisibilityPreset(False)
                item.setKeepLayerSet(True)
                item.setLayers(layers_to_show)
                item.setCrs(extent_map_layer.crs())
                item.setExtent(map_extent)

        '''
        print(f"tif_layer crs: {tdt_layer.crs()}")
        print(f"gpk_layer crs: {contour_layer.crs()}")
        print(f"shp_layer crs: {extent_map_layer.crs()}")
        print(f"map_extent: {map_extent.toString(4)}")
        '''
        
        if map_items_found == 0:
            print("[警告] 布局模板中未找到地图项（qgsLayoutItemMap）")

        layout.refresh()

        for item in layout.items():
            if isinstance(item, QgsLayoutItemMap):
                print(f"[OK] 地图项 '{item.id()}' 实际范围：{item.extent().toString(4)}")

        page = layout.pageCollection().page(0)
        if page is None:
            print("[错误] 布局中未找到页面")
            self.qgs_app.exitQgis()
            sys.exit(1)

        page_sz = page.pageSize()
        print(f"[OK] page.pageSize() = {page_sz.width():.2f} x {page_sz.height():.2f} mm")

        # 采用打印页面尺寸
        render_w = page_sz.width()
        render_h = page_sz.height()
        render_rect = QRectF(0, 0, render_w, render_h)
        print(f"[OK] 采用打印页面尺寸，最终渲染区域：{render_w:.2f} x {render_h:.2f} mm")

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

        return True

    # 创建轨迹图层
    def make_route_layer(self, gpx_file_path):
        """
        根据GPX文件创建轨迹图层
        
        参数:
        gpx_file_path (str): GPX文件路径
        
        返回:
        str: 成功返回轨迹图层文件路径，失败返回None
        """
        print(f"\n=== 开始创建轨迹图层 ===")
        print(f"GPX文件路径: {gpx_file_path}")
        
        try:
            # 1. 判断地图范围文件是否存在
            if not os.path.exists(self.MAP_EXTENT_4326):
                print(f"错误: 地图范围文件不存在: {self.MAP_EXTENT_4326}")
                return None
            
            print(f"地图范围文件存在: {self.MAP_EXTENT_4326}")
            
            # 2. 判断GPX文件是否存在
            if not os.path.exists(gpx_file_path):
                print(f"错误: GPX文件不存在: {gpx_file_path}")
                return None
            
            # 3. 读取GPX文件，获取所有轨迹点
            with open(gpx_file_path, 'r', encoding='utf-8') as f:
                gpx = gpxpy.parse(f)
            
            all_points = []
            for track in gpx.tracks:
                for segment in track.segments:
                    for point in segment.points:
                        all_points.append((point.longitude, point.latitude))
            
            if not all_points:
                print("错误: GPX文件中没有找到轨迹点")
                return None
            
            print(f"GPX文件中共有 {len(all_points)} 个轨迹点")
            
            # 4. 判断GPX轨迹是否在地图范围内
            # 读取地图范围文件
            extent_gdf = gpd.read_file(self.MAP_EXTENT_4326)
            if extent_gdf.empty:
                print("错误: 地图范围文件为空")
                return None
            
            extent_geometry = extent_gdf.geometry.iloc[0]
            
            # 检查是否有轨迹点在范围内
            has_point_in_extent = False
            for lon, lat in all_points:
                point = Point(lon, lat)
                if extent_geometry.contains(point) or extent_geometry.intersects(point):
                    has_point_in_extent = True
                    break
            
            if not has_point_in_extent:
                print("错误: GPX轨迹不在地图范围内")
                return None
            
            print("GPX轨迹在地图范围内")
            
            # 5. 创建轨迹图层
            from qgis.core import QgsVectorLayer, QgsField, QgsGeometry, QgsFeature, QgsVectorFileWriter
            
            temp_layer = QgsVectorLayer("LineString?crs=epsg:4326", "轨迹", "memory")
            
            if not temp_layer.isValid():
                print("错误: 临时图层创建失败")
                return None
            
            temp_layer.startEditing()
            
            temp_layer.dataProvider().addAttributes([
                QgsField("id", QMetaType.Type.Int),
                QgsField("name", QMetaType.Type.QString)
            ])
            temp_layer.updateFields()
            
            # 创建线要素
            from qgis.core import QgsPointXY
            
            if len(all_points) >= 2:
                qgis_points = [QgsPointXY(lon, lat) for lon, lat in all_points]
                line_geometry = QgsGeometry.fromPolylineXY(qgis_points)
                
                feature = QgsFeature()
                feature.setGeometry(line_geometry)
                feature.setAttributes([1, "轨迹"])
                temp_layer.dataProvider().addFeature(feature)
            
            temp_layer.updateExtents()
            temp_layer.commitChanges()
            
            # 6. 保存为GPKG文件
            output_gpkg = self.EXTENT_ROUTE_LAYER
            
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.fileEncoding = "UTF-8"
            transform_context = self.project.transformContext()
            
            QgsVectorFileWriter.writeAsVectorFormatV3(
                temp_layer,
                output_gpkg,
                transform_context,
                options
            )
            
            print(f"轨迹图层已保存: {output_gpkg}")
            return output_gpkg
            
        except Exception as e:
            print(f"创建轨迹图层失败: {e}")
            import traceback
            traceback.print_exc()
            return None


def point_to_map(center_lon, center_lat, north_south_length, east_west_length, project_dir,gpx_file_path=None,map_title="广州蓝天训练用途",map_maker="1121-奀奀的排骨"):
    """
    执行完整的地图制作工作流
    
    Args:
        center_lon (float): 中心点经度
        center_lat (float): 中心点纬度
        north_south_length (float): 南北边长（公里）
        east_west_length (float): 东西边长（公里）
        project_dir (str): 项目目录路径
        
    Returns:
        bool: 是否成功完成
    """
    print(f"=== 开始地图制作工作流 ===")
    print(f"中心点坐标: ({center_lon}, {center_lat})")
    print(f"南北边长: {north_south_length} km")
    print(f"东西边长: {east_west_length} km")
    print(f"项目目录: {project_dir}")
    
    try:
    	# 初始化地图制作器 ===========================
        maker = DemMakeQGISHeadless(
            center_longitude=center_lon,
            center_latitude=center_lat,
            north_south_length_km=north_south_length,
            east_west_length_km=east_west_length,
            project_path=project_dir
        )

        # 创建QGIS项目 ===========================
        print("\n创建QGIS项目...")
        maker.create_project()
        
        # 生成图层 ===========================
        # 生成地图范围图层
        map_extent_file = maker.make_map_extent_layer()

        # 生成天地图图层
        extent_tianditu_file = maker.make_tianditu_layer(zoom_level=18)

        # 生成谷歌地图图层
        extent_google_file = maker.make_google_layer(zoom_level=18)

        # 生成dem图层
        extent_dem_file = maker.extract_dem_by_extent(dem_files_dir=None, extent_gpkg=maker.MAP_EXTENT_4326)

        # 生成重采样dem图层
        extent_dem_resampled_file = maker.generate_dem_resampled_by_gra_cubic(dem_file=extent_dem_file, resolution_m=10)
        
        # 生成等高线图层
        extent_dem_contour_file = maker.generate_contour_from_dem(dem_file=extent_dem_resampled_file)

        # 生成高程渲染图层
        extent_dem_render_file = maker.make_dem_render_layer(dem_file=extent_dem_resampled_file)

        # 生成阴影图层
        extent_dem_hillshade_file = maker.generate_hillshade(dem_file=extent_dem_resampled_file)

        # 生成夸张的阴影图层
        extent_dem_hillshade_extreme_file = maker.generate_hillshade(dem_file=extent_dem_resampled_file, hillshade_file=maker.EXTENT_DEM_HILLSHADOW_EXAG, z_factor=6)

        # 生成轨迹图层
        if gpx_file_path:
            print(f"生成轨迹图层: {gpx_file_path}")
            extent_route_file = maker.make_route_layer(gpx_file_path)

        # OSM数据处理：相交产物(extent_osm_*.gpkg)已全部生成时，跳过下载/提取/相交（断点续传）
        extent_osm_files = maker._get_cached_extent_osm_files()
        if extent_osm_files is None:
            # 下载OSM数据图层
            osm_file = maker.download_osm_data()

            # 提取osm数据图层
            osm_gpkg_files = maker.extract_osm_to_gpkg(osm_file)

            # 生成osm相交图层
            extent_osm_files = maker.intersect_osm_with_extent(extent_gpkg=maker.MAP_EXTENT_4326, osm_layers=osm_gpkg_files)

        # 添加图层到项目 ===========================
        # 添加dem图层
        maker.add_layer_to_project(
            layer_path=extent_dem_file,
            layer_name=maker.EXTENT_DEM_LAYER_NAME,
            layer_style=None
        )

        # 添加重采样dem图层
        maker.add_layer_to_project(
            layer_path=extent_dem_resampled_file,
            layer_name=maker.EXTENT_DEM_RESAMPLED_LAYER_NAME,
            layer_style=None
        )

        # 添加高程渲染图层
        maker.add_layer_to_project(
            layer_path=extent_dem_render_file,
            layer_name=maker.EXTENT_DEM_RENDER_LAYER_NAME,
            layer_style=maker.DEFAULT_TEMPLATE[maker.EXTENT_DEM_RENDER_LAYER_NAME]
        )

        # 添加地图范围
        maker.add_layer_to_project(
            layer_path=map_extent_file,
            layer_name=maker.MAP_EXTENT_LAYER_NAME,
            layer_style=maker.DEFAULT_TEMPLATE[maker.MAP_EXTENT_LAYER_NAME]
        )

        # 添加天地图图层
        maker.add_layer_to_project(
            layer_path=extent_tianditu_file,
            layer_name=maker.TIANDITU_MAP_LAYER_NAME,
            layer_style=maker.DEFAULT_TEMPLATE[maker.GOOGLE_MAP_LAYER_NAME]
        )
        
        # 添加谷歌地图图层
        maker.add_layer_to_project(
            layer_path=extent_google_file,
            layer_name=maker.GOOGLE_MAP_LAYER_NAME,
            layer_style=maker.DEFAULT_TEMPLATE[maker.GOOGLE_MAP_LAYER_NAME]
        )
        
        # 添加等高线图层
        maker.add_layer_to_project(
            layer_path=extent_dem_contour_file,
            layer_name=maker.CONTOUR_LAYER_NAME,
            layer_style=maker.DEFAULT_TEMPLATE[maker.CONTOUR_LAYER_NAME]
        )

        # 添加osm
        maker.add_extent_osm_layers_with_styles(extent_osm_files)

        # 添加夸张的阴影图层
        maker.add_layer_to_project(
            layer_path=extent_dem_hillshade_extreme_file,
            layer_name=maker.EXTENT_DEM_HILLSHADOW_EXAG_LAYER_NAME,
            layer_style=maker.DEFAULT_TEMPLATE[maker.EXTENT_DEM_HILLSHADOW_EXAG_LAYER_NAME]
        )

        # 添加阴影图层
        maker.add_layer_to_project(
            layer_path=extent_dem_hillshade_file,
            layer_name=maker.EXTENT_DEM_HILLSHADOW_LAYER_NAME,
            layer_style=maker.DEFAULT_TEMPLATE[maker.EXTENT_DEM_HILLSHADOW_LAYER_NAME]
        )

        # 添加轨迹图层
        if "extent_route_file" in locals():
            maker.add_layer_to_project(
                layer_path=extent_route_file,
                layer_name=maker.EXTENT_ROUTE_LAYER_NAME,
                layer_style=maker.DEFAULT_TEMPLATE[maker.EXTENT_ROUTE_LAYER_NAME]
            )

        # 添加打印模板-横向 layoutmodel-横向.qpt
        maker.add_layout_templet(maker.LAYOUT_MODEL_HORIZONTAL, maker.LAYOUT_MODEL_HORIZONTAL_NAME)
        # 添加打印模板-纵向 layoutmodel-纵向.qpt
        maker.add_layout_templet(maker.LAYOUT_MODEL_VERTICAL, maker.LAYOUT_MODEL_VERTICAL_NAME)

        # 保存项目
        print("保存项目...")
        project_path = maker.save_project()

        print(f"项目已保存到: {project_path}")

        # 导出地图验证 ===========================
        print("\n=== 开始导出地图验证 ===")
        # OSM地图+等高线+影像地图
        osm_points_layer = maker.load_vector_layer(maker.EXTENT_OSM_POINTS, maker.EXTENT_OSM_POINTS_LAYER_NAME,maker.DEFAULT_TEMPLATE[maker.EXTENT_OSM_POINTS_LAYER_NAME])
        osm_lines_layer = maker.load_vector_layer(maker.EXTENT_OSM_LINES, maker.EXTENT_OSM_LINES_LAYER_NAME,maker.DEFAULT_TEMPLATE[maker.EXTENT_OSM_LINES_LAYER_NAME])
        osm_multipolygons_layer = maker.load_vector_layer(maker.EXTENT_OSM_MULTIPOLYGONS, maker.EXTENT_OSM_MULTIPOLYGONS_LAYER_NAME,maker.DEFAULT_TEMPLATE[maker.EXTENT_OSM_MULTIPOLYGONS_LAYER_NAME])

        if gpx_file_path and os.path.exists(gpx_file_path):
            route_layer = maker.load_vector_layer(maker.EXTENT_ROUTE_LAYER, maker.EXTENT_ROUTE_LAYER_NAME,maker.DEFAULT_TEMPLATE[maker.EXTENT_ROUTE_LAYER_NAME])
        else:
            route_layer = None

        tdt_layer = maker.load_raster_layer(maker.GOOGLE_MAP, maker.GOOGLE_MAP_LAYER_NAME,maker.DEFAULT_TEMPLATE[maker.GOOGLE_MAP_LAYER_NAME])
        contour_layer = maker.load_vector_layer(maker.CONTOUR_FILE, maker.CONTOUR_LAYER_NAME,maker.DEFAULT_TEMPLATE[maker.CONTOUR_LAYER_NAME])
        maker.export_map_by_layout_templet(layers_to_show=[contour_layer,
            route_layer,
            osm_points_layer,osm_lines_layer,osm_multipolygons_layer,
            tdt_layer],
            bg_satellite=maker.BG_SATELLITE_Y,
            map_title=map_title,
            map_maker=map_maker
            )

        # OSM地图+等高线+山体阴影+DEM高程渲染层
        dem_layer = maker.load_raster_layer(maker.EXTENT_DEM_RENDER_LAYER, maker.EXTENT_DEM_RENDER_LAYER_NAME,maker.DEFAULT_TEMPLATE[maker.EXTENT_DEM_RENDER_LAYER_NAME])
        # 山体阴影图层
        #dem_hillshade_layer = maker.load_raster_layer(maker.EXTENT_DEM_HILLSHADOW, maker.EXTENT_DEM_HILLSHADOW_LAYER_NAME,maker.DEFAULT_TEMPLATE[maker.EXTENT_DEM_HILLSHADOW_LAYER_NAME])
        # 夸张的阴影图层
        dem_hillshade_layer = maker.load_raster_layer(maker.EXTENT_DEM_HILLSHADOW_EXAG, maker.EXTENT_DEM_HILLSHADOW_EXAG_LAYER_NAME,maker.DEFAULT_TEMPLATE[maker.EXTENT_DEM_HILLSHADOW_EXAG_LAYER_NAME])
        maker.export_map_by_layout_templet(layers_to_show=[contour_layer,
            route_layer,
            osm_points_layer,osm_lines_layer,osm_multipolygons_layer,
            dem_hillshade_layer,dem_layer],
            map_title=map_title,
            map_maker=map_maker
            )

        # 待操作 - OSM地图（定制样式）+等高线+山体阴影+地图范围样式（底色）

        print("\n=== 所有测试完成 ===")
        return True
        
    except Exception as e:
        print(f"工作流执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False


# 使用Haversine公式计算两点之间的距离
def haversine_distance(lon1, lat1, lon2, lat2):
    """计算两点之间的距离（米）"""
    R = 6371000  # 地球半径（米）
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat/2) * math.sin(d_lat/2) + \
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
            math.sin(d_lon/2) * math.sin(d_lon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def gpx_to_map(gpx_file_path, project_dir):
    """
    根据GPX轨迹文件生成地图项目
    
    Args:
        gpx_file_path (str): GPX文件路径
        project_dir (str): 项目目录路径
        
    Returns:
        bool: 是否成功完成
    """
    print(f"=== 开始GPX轨迹处理 ===")
    print(f"GPX文件路径: {gpx_file_path}")
    print(f"项目目录: {project_dir}")
    
    try:
        # 1. 读取GPX文件
        with open(gpx_file_path, 'r', encoding='utf-8') as f:
            gpx = gpxpy.parse(f)
        
        # 2. 提取所有轨迹点
        all_points = []
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    all_points.append((point.longitude, point.latitude))
        
        if not all_points:
            print("错误: GPX文件中没有找到轨迹点")
            return False
        
        # 3. 计算中心点
        lons = [p[0] for p in all_points]
        lats = [p[1] for p in all_points]
        
        center_lon = sum(lons) / len(lons)
        center_lat = sum(lats) / len(lats)
        
        print(f"中心点坐标: ({center_lon:.6f}, {center_lat:.6f})")
        
        # 4. 计算中心点到轨迹各点的南北/东西最大距离
        max_ns_distance = 0
        max_ew_distance = 0
        for lon, lat in all_points:
            # 南北方向：根据纬度差计算
            ns_distance = haversine_distance(center_lon, center_lat, center_lon, lat)
            if ns_distance > max_ns_distance:
                max_ns_distance = ns_distance
            # 东西方向：根据经度差计算
            ew_distance = haversine_distance(center_lon, center_lat, lon, center_lat)
            if ew_distance > max_ew_distance:
                max_ew_distance = ew_distance
        
        print(f"中心点到轨迹的南北最大距离: {max_ns_distance:.2f} 米")
        print(f"中心点到轨迹的东西最大距离: {max_ew_distance:.2f} 米")
        
        # 5. 计算南北/东西的half_edge
        # 最大距离 + 500米，然后四舍五入到至少百米
        half_ns_raw = max_ns_distance + 500
        half_ew_raw = max_ew_distance + 500
        
        # 四舍五入到百米（100米的倍数）
        half_ns = round(half_ns_raw / 100) * 100
        half_ew = round(half_ew_raw / 100) * 100
        
        print(f"南北half_edge计算: {max_ns_distance:.2f} + 500 = {half_ns_raw:.2f} → 四舍五入后 {half_ns} 米")
        print(f"东西half_edge计算: {max_ew_distance:.2f} + 500 = {half_ew_raw:.2f} → 四舍五入后 {half_ew} 米")
        
        # 6. 计算边长（单位：公里）
        north_south_length_km = (2 * half_ns) / 1000
        east_west_length_km = (2 * half_ew) / 1000
        
        print(f"生成的地图南北边长: {north_south_length_km:.2f} 公里")
        print(f"生成的地图东西边长: {east_west_length_km:.2f} 公里")
        
        # 7. 创建项目目录
        os.makedirs(project_dir, exist_ok=True)
        
        # 8. 调用point_to_map生成地图
        print("\n=== 开始生成地图项目 ===")
        success = point_to_map(center_lon, center_lat, north_south_length_km, east_west_length_km, project_dir, gpx_file_path)
        
        if success:
            print(f"\n=== GPX轨迹地图生成完成 ===")
            print(f"中心点: ({center_lon:.6f}, {center_lat:.6f})")
            print(f"南北边长: {north_south_length_km:.2f} 公里")
            print(f"东西边长: {east_west_length_km:.2f} 公里")
            print(f"项目目录: {project_dir}")
        
        return success
        
    except Exception as e:
        print(f"GPX处理失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main_point_to_map():
    """命令行入口函数"""
    parser = argparse.ArgumentParser(
        description='QGIS无头地图制作工具 - 完整工作流',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认参数
  python make_qgis_headless.py
  
  # 指定参数
  python make_qgis_headless.py --lon 113.370327 --lat 23.201580 --ns-length 10 --ew-length 10 --project "C:/path/to/project"
        """
    )
    
    parser.add_argument(
        '--lon', '--longitude',
        type=float,
        default=113.370327,
        help='中心点经度 (默认: 113.370327)'
    )
    
    parser.add_argument(
        '--lat', '--latitude',
        type=float,
        default=23.201580,
        help='中心点纬度 (默认: 23.201580)'
    )
    
    parser.add_argument(
        '--ns-length', '--north-south-length',
        type=float,
        default=10,
        help='南北边长，单位公里 (默认: 10)'
    )
    
    parser.add_argument(
        '--ew-length', '--east-west-length',
        type=float,
        default=10,
        help='东西边长，单位公里 (默认: 10)'
    )
    
    parser.add_argument(
        '--project', '--project-dir',
        type=str,
        default=r"C:\Users\Administrator\Desktop\QGIS\地图制作\DemoMakeQGISMapAuto01",
        help='项目目录路径 (默认: C:\\Users\\Administrator\\Desktop\\QGIS\\地图制作\\DemoMakeQGISMapAuto01)'
    )
    
    args = parser.parse_args()
    
    # 执行工作流
    success = point_to_map(
        center_lon=args.lon,
        center_lat=args.lat,
        north_south_length=args.ns_length,
        east_west_length=args.ew_length,
        project_dir=args.project
    )
    
    # 返回退出码
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    # main_point_to_map()

    # point_to_map(center_lon=113.428453, center_lat=23.191103, north_south_length=15, east_west_length=10, 
    #     project_dir=r"C:\Users\Administrator\Desktop\QGIS\地图制作\DemoMakeQGISMapAuto01", 
    #     gpx_file_path=r"C:\Users\Administrator\Desktop\QGIS\地图制作\火帽北山\2024-03-03 07 57 火北帽.gpx")
    r''''''
    point_to_map(center_lon=113.375531, center_lat=23.243997, north_south_length=5.5, east_west_length=6.5, 
        project_dir=r"C:\Users\Administrator\Desktop\QGIS\地图制作\DemoMakeQGISMapAuto2026082802",
        map_title="广州蓝天救援协会大源杓麻训练地图",
        map_maker="1121-奀奀的排骨"
        )
    
    r'''
    # 23.23448,113.55742
    point_to_map(center_lon=113.55742, center_lat=23.23448, north_south_length=6, east_west_length=7, 
        project_dir=r"C:\Users\Administrator\Desktop\QGIS\地图制作\DemoMakeQGISMapAuto2026082803",
        map_title="广州蓝天救援协会训练地图",
        map_maker="1121-奀奀的排骨"
        )
    '''
    # gpx_to_map(r"C:\Users\Administrator\Desktop\QGIS\地图制作\火帽北山\2024-03-03 07 57 火北帽.gpx", 
    #   r"C:\Users\Administrator\Desktop\QGIS\地图制作\DemoMakeQGISMapAuto02")

