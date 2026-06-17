import math
import os
import sys
import shutil
import time
import requests
import subprocess
import argparse
import gpxpy
import gpxpy.gpx
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

TIANDITU_TK = 'a96ffd6582a7e32c0084d79f7976e182'
TIANDITU_WMTS_URL = f'http://t0.tianditu.gov.cn/img_w/wmts?tk={TIANDITU_TK}'


class DemMakeQGISHeadless:
    def __init__(self, center_longitude, center_latitude, side_length_km, project_path):
        if side_length_km > 30:
            raise ValueError("边长不能大于30km")
        
        self.project = None
        self.qgs_app = None

        self.center_longitude = center_longitude
        self.center_latitude = center_latitude
        self.side_length_km = side_length_km
        self.project_path = project_path

        self.OUTPUT = os.path.join(self.project_path, "output")
        self.RESOURCES_PATH = os.path.join(self.project_path, "resources")

        self.GPKG_EXTENT_4326 = os.path.join(self.project_path, "地图范围_4326.gpkg")
        self.GPKG_EXTENT_3857 = os.path.join(self.project_path, "地图范围_3857.gpkg")

        self.PRINT_MODEL_PATH = os.path.join(self.RESOURCES_PATH, "printModel")
        self.QPT_PATH = os.path.join(self.PRINT_MODEL_PATH, "layoutmodel2.qpt")

        self.TEMPLATE_PATH = os.path.join(self.RESOURCES_PATH, "template")

        self.TIANDITU_MAP = os.path.join(self.project_path, 'map_extent.tif')
        self.TIANDITU_MAP_LAYER_NAME = "extent_tdt_map"
        self.TIANDITU_MAP_TEMP = os.path.join(self.project_path, 'map_extent_temp.tif')

        self.CONTOUR_FILE = os.path.join(self.project_path, "extent_contour.gpkg")
        self.CONTOUR_LAYER_NAME = "extent_contour"

        # 图层和样式
        self.MAP_OSM = os.path.join(self.project_path, 'map.osm')
        self.EXTENT_OSM_LINES = os.path.join(self.project_path, "extent_osm_lines.gpkg")
        self.EXTENT_OSM_LINES_LAYER_NAME = "extent_osm_lines"
        self.EXTENT_OSM_POINTS = os.path.join(self.project_path, "extent_osm_points.gpkg")
        self.EXTENT_OSM_POINTS_LAYER_NAME = "extent_osm_points"
        self.EXTENT_OSM_MULTIPOLYGONS = os.path.join(self.project_path, "extent_osm_multipolygons.gpkg")
        self.EXTENT_OSM_MULTIPOLYGONS_LAYER_NAME = "extent_osm_multipolygons"
        self.EXTENT_OSM_MULTIPOLYGONS = os.path.join(self.project_path, "extent_osm_multipolygons.gpkg")
        self.EXTENT_OSM_MULTIPOLYGONS_LAYER_NAME = "extent_osm_multipolygons"
        self.EXTENT_ROUTE_LAYER = os.path.join(self.project_path, "extent_route_layer.gpkg")
        self.EXTENT_ROUTE_LAYER_LAYER_NAME = "extent_route_layer"

        self.EXTENT_DEM = os.path.join(self.project_path, "extent_dem.tif")
        self.EXTENT_DEM_LAYER_NAME = "extent_dem"
        self.EXTENT_DEM_HILLSHADOW = os.path.join(self.project_path, "extent_dem_hillshadow.tif")
        self.EXTENT_DEM_HILLSHADOW_LAYER_NAME = "extent_dem_hillshadow"

        self.DPI = 300
        self.LONGEST_SIDE = 1000.0
        self.BLANK_PCT = 0.15
        self.BORDER = 10.0

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
        QgsExpressionContextUtils.setProjectVariable(self.project, "Longest_side", '1000')
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
    
    def _calculate_boundary_points(self):
        from qgis.core import QgsDistanceArea, QgsPointXY
        da = QgsDistanceArea()
        da.setEllipsoid("WGS84")
        
        half_side = self.side_length_km * 500
        
        north_point = da.computeSpheroidProject(
            QgsPointXY(self.center_longitude, self.center_latitude),
            distance=half_side,
            azimuth=math.radians(0)
        )
        
        south_point = da.computeSpheroidProject(
            QgsPointXY(self.center_longitude, self.center_latitude),
            distance=half_side,
            azimuth=math.radians(180)
        )
        
        east_point = da.computeSpheroidProject(
            QgsPointXY(self.center_longitude, self.center_latitude),
            distance=half_side,
            azimuth=math.radians(90)
        )
        
        west_point = da.computeSpheroidProject(
            QgsPointXY(self.center_longitude, self.center_latitude),
            distance=half_side,
            azimuth=math.radians(270)
        )
        
        top_left = QgsPointXY(west_point.x(), north_point.y())
        top_right = QgsPointXY(east_point.x(), north_point.y())
        bottom_right = QgsPointXY(east_point.x(), south_point.y())
        bottom_left = QgsPointXY(west_point.x(), south_point.y())
        
        return [top_left, top_right, bottom_right, bottom_left]
    

    
    def add_map_extent_layer(self):
        """
        加载"地图范围"图层，并运用"地图范围样式.qml"样式文件，然后添加到qgis项目中
        
        返回:
        bool: 成功返回True，失败返回False
        """
        from qgis.core import QgsVectorLayer

        if self.project is None:
            print("错误: 项目未创建")
            return False


        self._create_extent_layer_4326(self.GPKG_EXTENT_4326)
        
        self._create_extent_layer_3857(self.GPKG_EXTENT_3857)

        for layer in self.project.mapLayers().values():
            if layer.name() == "地图范围":
                print("地图范围图层已存在，跳过添加")
                return True

        polygon_layer = QgsVectorLayer(self.GPKG_EXTENT_3857, "地图范围", 'ogr')
        if not polygon_layer.isValid():
            print(f"[错误] 矢量图层加载失败：{polygon_layer}")
            self.qgs_app.exitQgis()
            sys.exit(1)
        else:
            print(f"[OK] 矢量图层加载成功,范围：{polygon_layer.extent()}")

        style_path = os.path.join(self.TEMPLATE_PATH, "地图范围样式.qml")

        if os.path.exists(style_path):
            print(f"加载样式: {style_path}")
            polygon_layer.loadNamedStyle(style_path)
            polygon_layer.triggerRepaint()
        else:
            print("样式文件不存在，未加载样式")

        self.project.addMapLayer(polygon_layer)
        return True

    def save_project(self, project_name="map_project.qgz"):
        if self.project is None:
            raise RuntimeError("项目未创建，请先调用create_project()")

        project_file_path = os.path.join(self.project_path, project_name)
        self.project.write(project_file_path)

        return project_file_path
    
    def _create_extent_layer_4326(self, gpkg_path):
        from qgis.core import QgsVectorLayer, QgsField, QgsGeometry, QgsFeature, QgsVectorFileWriter
        
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

    def _check_gpkg_exists(self):
        
        return os.path.exists(self.GPKG_EXTENT_4326)
    
    def _get_gpkg_extent(self):
        from qgis.core import QgsVectorLayer

        layer = QgsVectorLayer(self.GPKG_EXTENT_4326, "temp", "ogr")
        if not layer.isValid():
            raise RuntimeError("加载gpkg文件失败")
        extent = layer.extent()
        return {
            'lon_min': extent.xMinimum(),
            'lon_max': extent.xMaximum(),
            'lat_min': extent.yMinimum(),
            'lat_max': extent.yMaximum()
        }
    
    def _deg2num(self, lat_deg, lon_deg, zoom):
        lat_rad = math.radians(lat_deg)
        n = 2.0 ** zoom
        xtile = int((lon_deg + 180.0) / 360.0 * n)
        ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
        return (xtile, ytile)
    
    def _num2deg(self, xtile, ytile, zoom):
        n = 2.0 ** zoom
        lon_deg = xtile / n * 360.0 - 180.0
        lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
        lat_deg = math.degrees(lat_rad)
        return (lat_deg, lon_deg)
    
    def _download_tianditu_tiles(self, lon_min, lon_max, lat_min, lat_max, zoom_level=14):
        from owslib.wmts import WebMapTileService
        from PIL import Image
        from osgeo import gdal
        from pyproj import Transformer
        
        print(f"TIANDITU_WMTS_URL: {TIANDITU_WMTS_URL}")
        # 创建WMTS客户端
        wmts = WebMapTileService(url=TIANDITU_WMTS_URL, headers=TIANDITU_HEADERS)

        print("创建WMTS客户端 成功")
        
        layer_name = 'img'
        tile_matrix_set = 'w'
        
        x_min, y_min = self._deg2num(lat_max, lon_min, zoom_level)
        x_max, y_max = self._deg2num(lat_min, lon_max, zoom_level)
        
        tile_output_dir = os.path.join(self.project_path, 'tianditu_tiles')
        os.makedirs(tile_output_dir, exist_ok=True)
        
        total_tiles = (x_max - x_min + 1) * (y_max - y_min + 1)
        count = 0
        print(f"\n开始下载瓦片 (级别: {zoom_level})...")
        print(f"瓦片列范围: {x_min} 到 {x_max}")
        print(f"瓦片行范围: {y_min} 到 {y_max}")
        
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                try:
                    tile = wmts.gettile(
                        base_url=TIANDITU_WMTS_URL,
                        layer=layer_name,
                        tilematrixset=tile_matrix_set,
                        tilematrix=str(zoom_level),
                        row=y,
                        column=x,
                    )
                    
                
                    filename = os.path.join(tile_output_dir, f'tile_{zoom_level}_{x}_{y}.jpg')
                    with open(filename, 'wb') as f:
                        f.write(tile.read())
                    count += 1
                    print(f"已下载 {count}/{total_tiles} 瓦片: {filename}")
                except Exception as e:
                    print(f"下载失败 ({x},{y}): {str(e)}")
        
        print(f"\n瓦片下载完成! 共下载 {count} 个瓦片")
        
        return self._merge_tiles(tile_output_dir, zoom_level, (x_min, x_max), (y_min, y_max), lon_min, lon_max, lat_min, lat_max)
    
    def _merge_tiles(self, tile_output_dir, zoom, x_range, y_range, lon_min, lon_max, lat_min, lat_max):
        from PIL import Image
        from osgeo import gdal
        from pyproj import Transformer
        
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
        
        temp_jpg = self.TIANDITU_MAP_TEMP
        
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
        tif_path = os.path.join(self.project_path, 'map_extent.tif')
        gdal.Translate(tif_path, temp_jpg, options=options)
        print(f"GeoTIFF保存至: {tif_path}")
        
        '''
        if os.path.exists(temp_jpg):
            os.remove(temp_jpg)
        '''
        return tif_path
    
    def _add_tif_to_project(self, tif_path):
        from qgis.core import QgsRasterLayer
        raster_layer = QgsRasterLayer(tif_path, '地图范围-天地图')
        if not raster_layer.isValid():
            raise RuntimeError(f"加载TIF文件失败: {tif_path}")
        self.project.addMapLayer(raster_layer, False)
        root = self.project.layerTreeRoot()
        root.insertLayer(0, raster_layer)
        print(f"已添加图层到项目: {tif_path}")
    
    def download_and_add_tianditu(self, zoom_level=14):
        if os.path.exists(self.TIANDITU_MAP):
            print(f"警告: 天地图影像已存在: {self.TIANDITU_MAP}")
            print(f"跳过下载，直接使用已存在文件: {self.TIANDITU_MAP}")
            return self.TIANDITU_MAP

        if not self._check_gpkg_exists():
            raise RuntimeError(f"{self.GPKG_EXTENT_4326}不存在，请先创建")
        print("\n=== 开始下载天地图影像 ===")
        extent = self._get_gpkg_extent()
        tif_path = self._download_tianditu_tiles(
            extent['lon_min'],
            extent['lon_max'],
            extent['lat_min'],
            extent['lat_max'],
            zoom_level
        )
        self._add_tif_to_project(tif_path)
        print("\n=== 天地图下载完成 ===")
        return tif_path

    def download_osm_data(self, output_file=None, timeout=300):
        """
        从OpenStreetMap下载指定区域的全量OSM数据并保存为.osm格式文件
        
        参数:
        output_file (str): 输出文件路径，默认为项目目录下的map.osm
        timeout (int): 请求超时时间（秒），默认为300秒
        
        返回:
        str: OSM文件路径，如果下载失败返回None
        """

        # 检查OSM文件是否存在
        if os.path.exists(self.MAP_OSM):
            print(f"警告: OSM文件已存在: {self.MAP_OSM}")
            return self.MAP_OSM

        if not self._check_gpkg_exists():
            raise RuntimeError(f"{self.GPKG_EXTENT_4326}不存在，请先创建")
        
        extent = self._get_gpkg_extent()
        min_lon = extent['lon_min']
        min_lat = extent['lat_min']
        max_lon = extent['lon_max']
        max_lat = extent['lat_max']
        
        if output_file is None:
            output_file = os.path.join(self.project_path, 'map.osm')
        
        overpass_url = "https://overpass-api.de/api/map"
        query_params = {
            "bbox": f"{min_lon}, {min_lat}, {max_lon}, {max_lat}"
        }
        
        headers = {
            "User-Agent": "QGIS Headless OSM Downloader/1.0 (https://github.com/kennymarx/DemoPyQGIS)"
        }
        
        print(f"\n=== 开始下载OSM数据 ===")
        print(f"边界框: {min_lon:.6f}, {min_lat:.6f}, {max_lon:.6f}, {max_lat:.6f}")
        print(f"目标文件: {output_file}")
        
        try:
            start_time = time.time()
            response = requests.get(
                overpass_url, 
                params=query_params, 
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
                print(f"错误信息: {response.text}")
                if "Request size too large" in response.text:
                    print("提示: 请求的区域可能太大。请尝试减小边界框的大小。")
                return None
                
        except requests.exceptions.Timeout:
            print(f"请求超时，超时时间: {timeout} 秒")
            return None
        except requests.exceptions.RequestException as e:
            print(f"发生网络错误: {e}")
            return None
        except Exception as e:
            print(f"发生未知错误: {e}")
            return None

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
        
        if not os.path.exists(osm_file):
            print(f"错误: OSM文件不存在: {osm_file}")
            return []
        
        if layers is None:
            layers = ['points', 'lines', 'multipolygons']
        
        output_files = []
        
        print(f"\n=== 开始提取OSM数据 ===")
        print(f"输入文件: {osm_file}")
        print(f"要提取的图层: {layers}")
        
        for layer in layers:
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
                output_files.append(output_file)
            except subprocess.CalledProcessError as e:
                print(f"提取 {layer} 图层失败: {e.stderr}")
        
        print("=== OSM数据提取完成 ===")
        return output_files

    def add_osm_gpkg_layers_to_project(self, gpkg_files=None):
        """
        将提取的OSM GPKG图层添加到QGIS项目
        
        参数:
        gpkg_files (list): GPKG文件路径列表，默认为自动查找项目目录下的osm_*.gpkg文件
        
        返回:
        list: 成功添加的图层对象列表
        """
        from qgis.core import QgsVectorLayer
        
        if gpkg_files is None:
            # 自动查找项目目录下的osm_*.gpkg文件
            gpkg_files = []
            for f in os.listdir(self.project_path):
                if f.startswith('osm_') and f.endswith('.gpkg'):
                    gpkg_files.append(os.path.join(self.project_path, f))
        
        if not gpkg_files:
            print("警告: 未找到OSM GPKG文件")
            return []
        
        added_layers = []
        root = self.project.layerTreeRoot()
        
        print(f"\n=== 开始添加OSM图层到项目 ===")
        
        for gpkg_file in gpkg_files:
            if not os.path.exists(gpkg_file):
                print(f"警告: 文件不存在: {gpkg_file}")
                continue
            
            layer_name = os.path.basename(gpkg_file).replace('.gpkg', '').replace('osm_', '')
            
            # 检查图层是否已存在
            existing_layer = None
            for layer in self.project.mapLayers().values():
                if layer.name() == layer_name:
                    existing_layer = layer
                    break
            
            if existing_layer:
                print(f"图层 {layer_name} 已存在，跳过")
                continue
            
            layer = QgsVectorLayer(gpkg_file, layer_name, 'ogr')
            
            if not layer.isValid():
                print(f"加载图层失败: {gpkg_file}")
                continue
            
            self.project.addMapLayer(layer, False)
            root.addLayer(layer)
            added_layers.append(layer)
            print(f"已添加图层: {layer_name}")
        
        print("=== OSM图层添加完成 ===")
        return added_layers

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
        import geopandas as gpd
        from shapely.errors import TopologicalError
        
        print("\n=== 开始OSM图层与地图范围相交运算 ===")
        
        if extent_gpkg is None:
            extent_gpkg = self.GPKG_EXTENT_4326
        
        if not os.path.exists(extent_gpkg):
            print(f"错误: 地图范围文件不存在: {extent_gpkg}")
            return {}
        
        if osm_layers is None:
            osm_layers = {
                'points': os.path.join(self.project_path, 'osm_points.gpkg'),
                'lines': os.path.join(self.project_path, 'osm_lines.gpkg'),
                'multipolygons': os.path.join(self.project_path, 'osm_multipolygons.gpkg')
            }
        
        result_files = {}
        
        try:
            extent_gdf = gpd.read_file(extent_gpkg)
            if extent_gdf.empty:
                print("警告: 地图范围图层为空")
                return {}
            
            if not extent_gdf.is_valid.all():
                extent_gdf = extent_gdf.make_valid()
                
        except Exception as e:
            print(f"读取地图范围文件失败: {e}")
            return {}
        
        for layer_type, osm_file in osm_layers.items():
            if not os.path.exists(osm_file):
                print(f"警告: OSM文件不存在，跳过: {osm_file}")
                continue
            
            try:
                osm_gdf = gpd.read_file(osm_file)
                
                if osm_gdf.empty:
                    print(f"警告: OSM图层 {layer_type} 为空，跳过")
                    continue
                
                # 调用类方法清理几何
                osm_gdf = self.clean_geometries(osm_gdf)
                print(f"已修复 {layer_type} 图层几何图形错误")
                print(osm_gdf.is_valid.all())
                
                if not osm_gdf.is_valid.all():
                    osm_gdf = osm_gdf.make_valid()
                
                # 根据 layer_type 自动保留正确的几何类型
                if layer_type == "multipolygons":
                    osm_gdf = osm_gdf[osm_gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]
                elif layer_type == "lines":
                    osm_gdf = osm_gdf[osm_gdf.geometry.type.isin(["LineString", "MultiLineString"])]
                elif layer_type == "points":
                    osm_gdf = osm_gdf[osm_gdf.geometry.type.isin(["Point", "MultiPoint"])]
                    
                # 爆炸多部件几何（避免拓扑错误）
                osm_gdf = osm_gdf.explode(index_parts=False).reset_index(drop=True)

                # 最后再清理一次无效几何
                osm_gdf = osm_gdf[osm_gdf.is_valid]
                if osm_gdf.empty:
                    print(f"警告: 过滤无效几何后 {layer_type} 为空，跳过")
                    return result_files
                
                # 检查坐标参考系是否一致
                if extent_gdf.crs != osm_gdf.crs:
                    print(f"坐标参考系不一致，正在转换 {layer_type} 图层...")
                    osm_gdf = osm_gdf.to_crs(extent_gdf.crs)
                
                print(f"执行 {layer_type} 图层相交运算...")
                intersection_gdf = gpd.overlay(osm_gdf, extent_gdf, how='intersection')
                
                if intersection_gdf.empty:
                    print(f"警告: {layer_type} 图层与地图范围无相交部分")
                    continue
                
                output_file = os.path.join(self.project_path, f'extent_osm_{layer_type}.gpkg')
                intersection_gdf.to_file(output_file, layer=f'extent_osm_{layer_type}', driver='GPKG')
                result_files[layer_type] = output_file
                print(f"成功: extent_osm_{layer_type}.gpkg 已生成 ({len(intersection_gdf)} 个要素)")
                
            except TopologicalError as e:
                print(f"拓扑错误 ({layer_type}): {e}")
            except Exception as e:
                print(f"相交运算错误 ({layer_type}): {e}")
        
        print("=== OSM图层相交运算完成 ===")
        return result_files

    def add_extent_osm_layers_with_styles(self, extent_osm_files=None):
        """
        将extent_osm图层添加到QGIS项目并加载QML样式
        
        参数:
        extent_osm_files (dict): extent_osm文件路径字典，key为类型名，value为文件路径
                               默认为项目目录下的extent_osm_points.gpkg等文件
        
        返回:
        list: 成功添加的图层对象列表
        """
        from qgis.core import QgsVectorLayer
        
        if extent_osm_files is None:
            extent_osm_files = {
                'points': os.path.join(self.project_path, 'extent_osm_points.gpkg'),
                'lines': os.path.join(self.project_path, 'extent_osm_lines.gpkg'),
                'multipolygons': os.path.join(self.project_path, 'extent_osm_multipolygons.gpkg')
            }
        
        style_map = {
            'points': os.path.join(self.TEMPLATE_PATH, 'POI图层样式.qml'),
            'lines': os.path.join(self.TEMPLATE_PATH, '线图层样式.qml'),
            'multipolygons': os.path.join(self.TEMPLATE_PATH, '面图层样式.qml') 
        }
        
        added_layers = []
        root = self.project.layerTreeRoot()
        
        print("\n=== 开始添加extent_osm图层并加载样式 ===")
        
        for layer_type, gpkg_file in extent_osm_files.items():
            if not os.path.exists(gpkg_file):
                print(f"警告: 文件不存在，跳过: {gpkg_file}")
                continue
            
            layer_name = f'extent_osm_{layer_type}'
            
            existing_layer = None
            for layer in self.project.mapLayers().values():
                if layer.name() == layer_name:
                    existing_layer = layer
                    break
            
            if existing_layer:
                print(f"图层 {layer_name} 已存在，更新数据...")
                layer = existing_layer
            else:
                layer = QgsVectorLayer(gpkg_file, layer_name, 'ogr')
                if not layer.isValid():
                    print(f"加载图层失败: {gpkg_file}")
                    continue
            
            style_path = os.path.join(self.project_path, style_map.get(layer_type, ''))
            if os.path.exists(style_path):
                print(f"加载样式: {style_path}")
                layer.loadNamedStyle(style_path)
                layer.triggerRepaint()
            else:
                print(f"样式文件不存在: {style_path}")
            
            if not existing_layer:
                self.project.addMapLayer(layer, False)
                root.addLayer(layer)
            
            added_layers.append(layer)
            print(f"已添加图层: {layer_name}")
        
        print("=== extent_osm图层添加完成 ===")
        return added_layers

    def extract_dem_by_extent(self, dem_files_dir=None, extent_gpkg=None):
        """
        根据地图范围裁剪DEM影像，生成extent_dem.tif文件
        
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
            extent_gpkg = self.GPKG_EXTENT_4326
        
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
                
                output_file = os.path.join(self.project_path, "extent_dem.tif")
                
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
                    print(f"成功: extent_dem.tif 已生成")
                    return output_file
                else:
                    print("错误: 裁剪失败，输出文件未生成")
                    return None
                    
            except Exception as e:
                print(f"处理DEM文件时出错: {e}")
                continue
        
        print("未找到包含地图范围的DEM文件")
        return None

    def generate_contour_from_dem(self, dem_file=None, contour_file=None):
        if os.path.exists(self.CONTOUR_FILE):
            print(f"警告: 等高线文件已存在: {self.CONTOUR_FILE}")
            print(f"跳过等高线提取，直接使用已存在文件: {self.CONTOUR_FILE}")
            return self.CONTOUR_FILE
        """
        从DEM文件提取等高线，生成extent_contour.gpkg文件
        
        参数:
        dem_file (str): 输入DEM文件路径，默认为项目目录下的extent_dem.tif
        contour_file (str): 输出等高线GPKG文件路径，默认为extent_contour.gpkg
        
        返回:
        str: 等高线文件路径，如果失败返回None
        """
        import subprocess
        
        print("\n=== 开始提取等高线 ===")
        
        if dem_file is None:
            dem_file = os.path.join(self.project_path, "extent_dem.tif")
        
        if contour_file is None:
            contour_file = os.path.join(self.project_path, "extent_contour.gpkg")
        
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

    def add_contour_layer(self, contour_file=None):
        """
        将等高线图层添加到QGIS项目并加载样式
        
        参数:
        contour_file (str): 等高线GPKG文件路径，默认为extent_contour.gpkg
        
        返回:
        QgsVectorLayer: 添加的图层对象，如果失败返回None
        """
        from qgis.core import QgsVectorLayer
        
        print("\n=== 开始添加等高线图层 ===")
        
        if contour_file is None:
            contour_file = os.path.join(self.project_path, "extent_contour.gpkg")
        
        if not os.path.exists(contour_file):
            print(f"错误: 等高线文件不存在: {contour_file}")
            return None
        
        layer_name = "extent_contour"
        
        existing_layer = None
        for layer in self.project.mapLayers().values():
            if layer.name() == layer_name:
                existing_layer = layer
                break
        
        if existing_layer:
            print(f"图层 {layer_name} 已存在")
            return existing_layer
        
        layer = QgsVectorLayer(contour_file, layer_name, 'ogr')
        if not layer.isValid():
            print(f"加载图层失败: {contour_file}")
            return None
        
        style_path = os.path.join(self.TEMPLATE_PATH, "等高线图层样式.qml")
        if os.path.exists(style_path):
            print(f"加载样式: {style_path}")
            layer.loadNamedStyle(style_path)
            layer.triggerRepaint()
        else:
            print(f"样式文件不存在: {style_path}")
        
        self.project.addMapLayer(layer, False)
        root = self.project.layerTreeRoot()
        root.addLayer(layer)
        
        print(f"已添加图层: {layer_name}")
        return layer

    def add_dem_elevation_layer(self, dem_file=None):
        """
        将DEM高程渲染层添加到QGIS项目并加载样式
        
        参数:
        dem_file (str): DEM文件路径，默认为extent_dem_new.tif
        
        返回:
        QgsRasterLayer: 添加的图层对象，如果失败返回None
        """
        from qgis.core import QgsRasterLayer
        import shutil
        
        print("\n=== 开始添加DEM高程渲染层 ===")
        
        original_dem = os.path.join(self.project_path, "extent_dem.tif")
        if dem_file is None:
            dem_file = os.path.join(self.project_path, "extent_dem_new.tif")
        
        if not os.path.exists(original_dem):
            print(f"错误: 原始DEM文件不存在: {original_dem}")
            return None
        
        shutil.copy2(original_dem, dem_file)
        print(f"复制DEM文件: {original_dem} -> {dem_file}")
        
        layer_name = "extent_dem_new"
        
        existing_layer = None
        for layer in self.project.mapLayers().values():
            if layer.name() == layer_name:
                existing_layer = layer
                break
        
        if existing_layer:
            print(f"图层 {layer_name} 已存在")
            return existing_layer
        
        layer = QgsRasterLayer(dem_file, layer_name)
        if not layer.isValid():
            print(f"加载图层失败: {dem_file}")
            return None
        
        style_path = os.path.join(self.TEMPLATE_PATH, "高程渲染层样式.qml")
        if os.path.exists(style_path):
            print(f"加载样式: {style_path}")
            layer.loadNamedStyle(style_path)
            layer.triggerRepaint()
        else:
            print(f"样式文件不存在: {style_path}")
        
        self.project.addMapLayer(layer, False)
        root = self.project.layerTreeRoot()
        root.addLayer(layer)
        
        print(f"已添加图层: {layer_name}")
        return layer

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
        
        command = [
            "gdaldem",
            "hillshade",
            "-az", str(azimuth),
            "-alt", str(altitude),
            "-z", str(z_factor),
            dem_file,
            hillshade_file
        ]
        
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True
            )
            print("山体阴影生成成功")
            if os.path.exists(hillshade_file):
                return hillshade_file
            else:
                print("错误: 山体阴影文件未生成")
                return None
        except subprocess.CalledProcessError as e:
            print(f"山体阴影生成失败: {e.stderr}")
            return None

    def add_hillshade_layer(self, hillshade_file=None):
        """
        将山体阴影图层添加到QGIS项目
        
        参数:
        hillshade_file (str): 山体阴影文件路径，默认为extent_dem_hillshadow.tif
        
        返回:
        QgsRasterLayer: 添加的图层对象，如果失败返回None
        """
        from qgis.core import QgsRasterLayer
        
        print("\n=== 开始添加山体阴影图层 ===")
        
        if hillshade_file is None:
            hillshade_file = os.path.join(self.project_path, "extent_dem_hillshadow.tif")
        
        if not os.path.exists(hillshade_file):
            print(f"错误: 山体阴影文件不存在: {hillshade_file}")
            return None
        
        layer_name = "extent_dem_hillshadow"
        
        existing_layer = None
        for layer in self.project.mapLayers().values():
            if layer.name() == layer_name:
                existing_layer = layer
                break
        
        if existing_layer:
            print(f"图层 {layer_name} 已存在")
            return existing_layer
        
        layer = QgsRasterLayer(hillshade_file, layer_name)
        if not layer.isValid():
            print(f"加载图层失败: {hillshade_file}")
            return None

        style_path = os.path.join(self.TEMPLATE_PATH, "山体阴影样式.qml")
        if os.path.exists(style_path):
            print(f"加载样式: {style_path}")
            layer.loadNamedStyle(style_path)
            layer.triggerRepaint()
        else:
            print(f"样式文件不存在: {style_path}")
        
        self.project.addMapLayer(layer, False)
        root = self.project.layerTreeRoot()
        root.addLayer(layer)
        
        print(f"已添加图层: {layer_name}")
        return layer

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
    def export_map_by_layout_templet(self,layers_to_show=[]):
        """
        打印地图
        
        参数:
        layers_to_show (list): 要在打印图中显示的图层列表。
        
        返回:
        None
        """
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
        extent_map_layer = QgsVectorLayer(self.GPKG_EXTENT_3857, "地图范围", "ogr")
        if not extent_map_layer.isValid():
            print(f"[错误] 矢量图层加载失败：{self.GPKG_EXTENT_3857}")
            self.qgs_app.exitQgis()
            sys.exit(1)
        else:
            print(f"[OK] 地图范围图层加载成功,范围：{extent_map_layer.extent()}")
            
        extent_map_layer = self._reproject_to_3857(extent_map_layer)
        if not extent_map_layer.isValid():
            print(f"[错误] 矢量图层重投影失败：{self.GPKG_EXTENT_3857}")
            self.qgs_app.exitQgis()
            sys.exit(1)
        else:
            print(f"[OK] 地图范围图层重投影成功,范围：{extent_map_layer.extent()}")

        # 只需要在打印图项目中添加地图范围。
        project_print.addMapLayer(extent_map_layer,False)
        QgsExpressionContextUtils.setProjectVariable(project_print, "bg_satellite", '0')
        QgsExpressionContextUtils.setProjectVariable(project_print, "Blank_pct", '0.15')
        QgsExpressionContextUtils.setProjectVariable(project_print, "Border", '10')
        QgsExpressionContextUtils.setProjectVariable(project_print, "Longest_side", '1000')
        QgsExpressionContextUtils.setProjectVariable(project_print, "project_scale_parm", '1')

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

        QgsExpressionContextUtils.setLayoutVariable(layout, "Longest_side", self.LONGEST_SIDE)
        QgsExpressionContextUtils.setLayoutVariable(layout, "Blank_pct", self.BLANK_PCT)
        QgsExpressionContextUtils.setLayoutVariable(layout, "Border", self.BORDER)

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

        return True

    def add_route_layer(self, gpx_file_path):
        """
        根据GPX文件添加轨迹图层到项目
        
        参数:
        gpx_file_path (str): GPX文件路径
        
        返回:
        bool: 是否成功添加
        """
        print(f"\n=== 开始添加轨迹图层 ===")
        print(f"GPX文件路径: {gpx_file_path}")
        
        try:
            # 1. 判断地图范围文件是否存在
            if not os.path.exists(self.GPKG_EXTENT_4326):
                print(f"错误: 地图范围文件不存在: {self.GPKG_EXTENT_4326}")
                return False
            
            print(f"地图范围文件存在: {self.GPKG_EXTENT_4326}")
            
            # 2. 判断GPX文件是否存在
            if not os.path.exists(gpx_file_path):
                print(f"错误: GPX文件不存在: {gpx_file_path}")
                return False
            
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
                return False
            
            print(f"GPX文件中共有 {len(all_points)} 个轨迹点")
            
            # 4. 判断GPX轨迹是否在地图范围内
            # 读取地图范围文件
            extent_gdf = gpd.read_file(self.GPKG_EXTENT_4326)
            if extent_gdf.empty:
                print("错误: 地图范围文件为空")
                return False
            
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
                return False
            
            print("GPX轨迹在地图范围内")
            
            # 5. 创建轨迹图层
            from qgis.core import QgsVectorLayer, QgsField, QgsGeometry, QgsFeature, QgsVectorFileWriter
            
            temp_layer = QgsVectorLayer("LineString?crs=epsg:4326", "轨迹", "memory")
            
            if not temp_layer.isValid():
                print("错误: 临时图层创建失败")
                return False
            
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
            output_gpkg = os.path.join(self.project_path, "extent_route_layer.gpkg")
            
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
            
            # 7. 添加到QGIS项目
            layer_name = "extent_route_layer"
            
            # 检查是否已存在
            for layer in self.project.mapLayers().values():
                if layer.name() == layer_name:
                    print(f"图层 {layer_name} 已存在，跳过添加")
                    return True
            
            route_layer = QgsVectorLayer(output_gpkg, layer_name, 'ogr')
            if not route_layer.isValid():
                print(f"错误: 加载轨迹图层失败: {output_gpkg}")
                return False
            
            print(f"[OK] 轨迹图层加载成功")
            
            # 加载样式
            style_path = os.path.join(self.TEMPLATE_PATH, "轨迹图层样式.qml")
            if os.path.exists(style_path):
                print(f"加载样式: {style_path}")
                route_layer.loadNamedStyle(style_path)
                route_layer.triggerRepaint()
            else:
                print("样式文件不存在，未加载样式")
            
            self.project.addMapLayer(route_layer)
            
            # 8. 保存项目
            self.save_project()
            print(f"项目已保存")
            
            print("\n=== 轨迹图层添加完成 ===")
            return True
            
        except Exception as e:
            print(f"添加轨迹图层失败: {e}")
            import traceback
            traceback.print_exc()
            return False

def point_to_map(center_lon, center_lat, side_length, project_dir,gpx_file_path=None):
    """
    执行完整的地图制作工作流
    
    Args:
        center_lon (float): 中心点经度
        center_lat (float): 中心点纬度
        side_length (float): 边长（公里）
        project_dir (str): 项目目录路径
        
    Returns:
        bool: 是否成功完成
    """
    print(f"=== 开始地图制作工作流 ===")
    print(f"中心点坐标: ({center_lon}, {center_lat})")
    print(f"边长: {side_length} km")
    print(f"项目目录: {project_dir}")
    
    try:
        maker = DemMakeQGISHeadless(
            center_longitude=center_lon,
            center_latitude=center_lat,
            side_length_km=side_length,
            project_path=project_dir
        )
        
        print("\n创建QGIS项目...")
        maker.create_project()

        print("添加地图范围图层...")
        maker.add_map_extent_layer()

        print("保存项目...")
        project_path = maker.save_project()

        print(f"项目已保存到: {project_path}")

        if gpx_file_path and os.path.exists(gpx_file_path):
            print(f"添加GPX轨迹图层...")
            maker.add_route_layer(gpx_file_path)
        else:
            print("GPX文件不存在，未添加轨迹图层")
        
        print("\n=== 开始天地图下载验证 ===")
        if maker._check_gpkg_exists():
            print(f"地图范围:{maker.GPKG_EXTENT_4326}存在，开始下载天地图...")
            tif_path = maker.download_and_add_tianditu(zoom_level=14)
            
            if os.path.exists(tif_path):
                print(f"验证成功: 地图范围-天地图.tif 已创建!")
                print(f"文件大小: {os.path.getsize(tif_path)} bytes")
                
                print("\n重新保存项目...")
                final_project_path = maker.save_project()
                print(f"最终项目已保存到: {final_project_path}")
            else:
                print("验证失败: 地图范围-天地图.tif 未创建!")
        else:
            print(f"验证失败: {maker.GPKG_EXTENT_4326} 不存在!")
        
        print("\n=== 开始OSM数据下载验证 ===")
        osm_path = None
        if maker._check_gpkg_exists():
            print(f"地图范围:{maker.GPKG_EXTENT_4326}存在，开始下载OSM数据...")
            osm_path = maker.download_osm_data()
            
            if osm_path and os.path.exists(osm_path):
                print(f"验证成功: {osm_path} 已创建!")
                print(f"文件大小: {os.path.getsize(osm_path)} bytes")
            else:
                print("验证失败: OSM数据下载失败!")
        else:
            print(f"验证失败: {maker.GPKG_EXTENT_4326} 不存在!")
        
        print("\n=== 开始OSM数据提取验证 ===")
        gpkg_files = []
        if osm_path and os.path.exists(osm_path):
            print("OSM文件存在，开始提取数据...")
            gpkg_files = maker.extract_osm_to_gpkg(osm_path)
            
            if gpkg_files:
                print(f"验证成功: 已提取 {len(gpkg_files)} 个图层")
                for gpkg in gpkg_files:
                    print(f"  - {os.path.basename(gpkg)}")
            else:
                print("验证失败: OSM数据提取失败!")
        else:
            print("跳过: OSM文件不存在")
        
        print("\n=== 开始添加OSM图层到项目验证 ===")
        if gpkg_files:
            print("开始添加OSM图层到项目...")
            added_layers = maker.add_osm_gpkg_layers_to_project(gpkg_files)
            
            if added_layers:
                print(f"验证成功: 已添加 {len(added_layers)} 个图层")
                print("\n重新保存项目...")
                final_project_path = maker.save_project()
                print(f"最终项目已保存到: {final_project_path}")
            else:
                print("验证失败: 添加图层失败!")
        else:
            print("跳过: 没有可添加的GPKG文件")

        print("\n=== 开始OSM图层相交运算验证 ===")
        osm_gpkg_files = {
            'points': os.path.join(project_dir, 'osm_points.gpkg'),
            'lines': os.path.join(project_dir, 'osm_lines.gpkg'),
            'multipolygons': os.path.join(project_dir, 'osm_multipolygons.gpkg')
        }

        if all(os.path.exists(f) for f in osm_gpkg_files.values()) and os.path.exists(maker.GPKG_EXTENT_4326):
            print(f"OSM图层文件和地图范围:{maker.GPKG_EXTENT_4326}都存在，开始相交运算...")
            extent_osm_files = maker.intersect_osm_with_extent(extent_gpkg=maker.GPKG_EXTENT_4326, osm_layers=osm_gpkg_files)

            if extent_osm_files:
                print(f"验证成功: 已生成 {len(extent_osm_files)} 个extent_osm文件")
                for layer_type, file_path in extent_osm_files.items():
                    print(f"  - {os.path.basename(file_path)}")

                print("\n=== 开始添加extent_osm图层并加载样式验证 ===")
                added_extent_layers = maker.add_extent_osm_layers_with_styles(extent_osm_files)

                if added_extent_layers:
                    print(f"验证成功: 已添加 {len(added_extent_layers)} 个extent_osm图层")
                    print("\n重新保存项目...")
                    final_project_path = maker.save_project()
                    print(f"最终项目已保存到: {final_project_path}")
                else:
                    print("验证失败: 添加extent_osm图层失败!")
            else:
                print("验证失败: 相交运算失败!")
        else:
            missing_files = [f for f in osm_gpkg_files.values() if not os.path.exists(f)]
            if not os.path.exists(maker.GPKG_EXTENT_4326):
                missing_files.append(maker.GPKG_EXTENT_4326)
            print(f"跳过: 缺少必要文件: {[os.path.basename(f) for f in missing_files]}")
        
        print("\n=== 开始DEM影像裁剪验证 ===")
        dem_files_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dem_files")
        
        if os.path.exists(dem_files_dir) and os.path.exists(maker.GPKG_EXTENT_4326):
            print(f"DEM目录和地图范围:{maker.GPKG_EXTENT_4326}都存在，开始裁剪DEM...")
            extent_dem = maker.extract_dem_by_extent(dem_files_dir=dem_files_dir, extent_gpkg=maker.GPKG_EXTENT_4326)
            
            if extent_dem and os.path.exists(extent_dem):
                print(f"验证成功: {os.path.basename(extent_dem)} 已生成")
                print(f"文件大小: {os.path.getsize(extent_dem)} bytes")
            else:
                print("验证失败: DEM裁剪失败!")
        else:
            print("跳过: DEM目录或地图范围文件不存在")
        
        print("\n=== 开始等高线提取验证 ===")
        extent_dem_path = os.path.join(project_dir, "extent_dem.tif")
        
        if os.path.exists(extent_dem_path):
            print("extent_dem.tif存在，开始提取等高线...")
            contour_file = maker.generate_contour_from_dem(dem_file=extent_dem_path)
            
            if contour_file and os.path.exists(contour_file):
                print(f"验证成功: {os.path.basename(contour_file)} 已生成")
                
                print("\n=== 开始添加等高线图层验证 ===")
                contour_layer = maker.add_contour_layer(contour_file=contour_file)
                
                if contour_layer:
                    print("验证成功: 等高线图层已添加")
                    print("\n重新保存项目...")
                    final_project_path = maker.save_project()
                    print(f"项目已保存到: {final_project_path}")
                else:
                    print("验证失败: 添加等高线图层失败!")
            else:
                print("验证失败: 等高线提取失败!")
        else:
            print("跳过: extent_dem.tif不存在")
        
        print("\n=== 开始DEM高程渲染层验证 ===")
        if os.path.exists(extent_dem_path):
            print("extent_dem.tif存在，开始添加DEM高程渲染层...")
            dem_layer = maker.add_dem_elevation_layer()
            
            if dem_layer:
                print("验证成功: DEM高程渲染层已添加")
                print("\n重新保存项目...")
                final_project_path = maker.save_project()
                print(f"项目已保存到: {final_project_path}")
            else:
                print("验证失败: 添加DEM高程渲染层失败!")
        else:
            print("跳过: extent_dem.tif不存在")
        
        print("\n=== 开始山体阴影验证 ===")
        if os.path.exists(extent_dem_path):
            print("extent_dem.tif存在，开始生成山体阴影...")
            hillshade_file = maker.generate_hillshade(dem_file=extent_dem_path)
            
            if hillshade_file and os.path.exists(hillshade_file):
                print(f"验证成功: {os.path.basename(hillshade_file)} 已生成")
                
                print("\n=== 开始添加山体阴影图层验证 ===")
                hillshade_layer = maker.add_hillshade_layer(hillshade_file=hillshade_file)
                
                if hillshade_layer:
                    print("验证成功: 山体阴影图层已添加")
                    print("\n重新保存项目...")
                    final_project_path = maker.save_project()
                    print(f"项目已保存到: {final_project_path}")
                else:
                    print("验证失败: 添加山体阴影图层失败!")
            else:
                print("验证失败: 山体阴影生成失败!")
        else:
            print("跳过: extent_dem.tif不存在")
        
        print("\n=== 开始导出地图验证 ===")
        # 影像地图+等高线
        if gpx_file_path and os.path.exists(gpx_file_path):
            route_layer = maker.load_vector_layer(maker.EXTENT_ROUTE_LAYER, maker.EXTENT_ROUTE_LAYER_LAYER_NAME,"轨迹图层样式.qml")
        else:
            route_layer = None

        tdt_layer = maker.load_raster_layer(maker.TIANDITU_MAP, maker.TIANDITU_MAP_LAYER_NAME)
        contour_layer = maker.load_vector_layer(maker.CONTOUR_FILE, maker.CONTOUR_LAYER_NAME,"等高线图层样式.qml")
        maker.export_map_by_layout_templet(layers_to_show=[contour_layer,route_layer,tdt_layer])

        # OSM地图+等高线+山体阴影+DEM高程渲染层
        osm_points_layer = maker.load_vector_layer(maker.EXTENT_OSM_POINTS, maker.EXTENT_OSM_POINTS_LAYER_NAME,"POI图层样式.qml")
        osm_lines_layer = maker.load_vector_layer(maker.EXTENT_OSM_LINES, maker.EXTENT_OSM_LINES_LAYER_NAME,"线图层样式.qml")
        osm_multipolygons_layer = maker.load_vector_layer(maker.EXTENT_OSM_MULTIPOLYGONS, maker.EXTENT_OSM_MULTIPOLYGONS_LAYER_NAME,"面图层样式.qml")


        dem_layer = maker.load_raster_layer(maker.EXTENT_DEM, maker.EXTENT_DEM_LAYER_NAME,"高程渲染层样式.qml")
        dem_hillshade_layer = maker.load_raster_layer(maker.EXTENT_DEM_HILLSHADOW, maker.EXTENT_DEM_HILLSHADOW_LAYER_NAME,"山体阴影样式.qml")
        maker.export_map_by_layout_templet(layers_to_show=[contour_layer,
            route_layer,
            osm_points_layer,osm_lines_layer,osm_multipolygons_layer,
            dem_hillshade_layer,dem_layer])

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
        
        # 4. 计算中心点到轨迹各点的最大距离（东西南北四个方向）
        max_distance = 0
        for lon, lat in all_points:
            distance = haversine_distance(center_lon, center_lat, lon, lat)
            if distance > max_distance:
                max_distance = distance
        
        print(f"中心点到轨迹的最大距离: {max_distance:.2f} 米")
        
        # 5. 计算half_edge
        # 最大距离 + 500米，然后四舍五入到至少百米
        half_edge_raw = max_distance + 500
        
        # 四舍五入到百米（100米的倍数）
        half_edge = round(half_edge_raw / 100) * 100
        
        print(f"half_edge计算: {max_distance:.2f} + 500 = {half_edge_raw:.2f} → 四舍五入后 {half_edge} 米")
        
        # 6. 计算边长（单位：公里）
        side_length_km = (2 * half_edge) / 1000
        
        print(f"生成的地图边长: {side_length_km:.2f} 公里")
        
        # 7. 创建项目目录
        os.makedirs(project_dir, exist_ok=True)
        
        # 8. 调用point_to_map生成地图
        print("\n=== 开始生成地图项目 ===")
        success = point_to_map(center_lon, center_lat, side_length_km, project_dir, gpx_file_path)
        
        if success:
            print(f"\n=== GPX轨迹地图生成完成 ===")
            print(f"中心点: ({center_lon:.6f}, {center_lat:.6f})")
            print(f"边长: {side_length_km:.2f} 公里")
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
  python make_qgis_headless.py --lon 113.370327 --lat 23.201580 --side 10 --project "C:/path/to/project"
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
        '--side', '--side-length',
        type=float,
        default=10,
        help='边长，单位公里 (默认: 10)'
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
        side_length=args.side,
        project_dir=args.project
    )
    
    # 返回退出码
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    # main_point_to_map()
    gpx_to_map(r"C:\Users\Administrator\Desktop\QGIS\地图制作\DemoMakeQGISMapAuto01\2024-03-03 07 57 火北帽.gpx", r"C:\Users\Administrator\Desktop\QGIS\地图制作\DemoMakeQGISMapAuto01")

