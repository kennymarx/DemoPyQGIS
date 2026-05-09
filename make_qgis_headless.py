import math
import os
import sys
import shutil
from PyQt5.QtCore import QMetaType


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
        if side_length_km > 10:
            raise ValueError("边长不能大于10km")
        
        self.center_longitude = center_longitude
        self.center_latitude = center_latitude
        self.side_length_km = side_length_km
        self.project_path = project_path
        
        self.project = None
        self.qgs_app = None
        
        os.makedirs(project_path, exist_ok=True)

        # 初始化项目资源
        self._copy_resources()
        
        self._init_qgis_environment()
        
        from qgis.core import QgsCoordinateReferenceSystem
        self.crs = QgsCoordinateReferenceSystem('EPSG:4326')
    
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
        # 创建项目
        self.project = QgsProject.instance()
        # 清空项目
        self.project.clear()
        # 设置项目的坐标系wsg84
        self.project.setCrs(self.crs)
        
    # 定义私有方法，将./resources目录下的所有文件拷贝到项目目录下
    def _copy_resources(self):
        # 当前脚本的位置
        current_dir = os.path.dirname(os.path.abspath(__file__))
        resources_dir = os.path.join(current_dir, "resources")
    
        # 拷贝资源目录下的所有文件到项目目录
        print(f"拷贝资源目录 {resources_dir} 到项目目录 {self.project_path}")
        # 拷贝资源目录下的所有文件到项目目录
        # 遍历资源目录，逐个拷贝/覆盖
        for item in os.listdir(resources_dir):
            src_path = os.path.join(resources_dir, item)
            dst_path = os.path.join(self.project_path, item)
            
            try:
                if os.path.isdir(src_path):
                    # 如果是文件夹，递归拷贝（存在则覆盖）
                    if os.path.exists(dst_path):
                        shutil.rmtree(dst_path)
                    shutil.copytree(src_path, dst_path)
                else:
                    # 如果是文件，直接拷贝覆盖
                    shutil.copy2(src_path, dst_path)
            except Exception as e:
                print(f"拷贝 {item} 失败：{e}")
    
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
    

    
    def save_project(self, project_name="map_project.qgz"):
        if self.project is None:
            raise RuntimeError("项目未创建，请先调用create_project()")
        
        gpkg_path = os.path.join(self.project_path, "地图范围.gpkg")
        
        self._create_gpkg_file(gpkg_path)
        
        from qgis.core import QgsVectorLayer, QgsMapLayerStyle
        polygon_layer = QgsVectorLayer(gpkg_path, "地图范围", "ogr")
        
        if not polygon_layer.isValid():
            raise RuntimeError("加载gpkg文件失败")
        
        style_path = os.path.join(self.project_path, "地图范围样式.qml")

        if os.path.exists(style_path):
            print(f"加载样式: {style_path}")
            # 直接用图层对象加载
            polygon_layer.loadNamedStyle(style_path)
            polygon_layer.triggerRepaint()
        else:
            print("样式文件不存在，未加载样式")
            
        
        self.project.addMapLayer(polygon_layer)
        
        project_file_path = os.path.join(self.project_path, project_name)
        self.project.write(project_file_path)
        
        return project_file_path
    
    def _create_gpkg_file(self, gpkg_path):
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
    
    def _check_gpkg_exists(self):
        gpkg_path = os.path.join(self.project_path, "地图范围.gpkg")
        return os.path.exists(gpkg_path)
    
    def _get_gpkg_extent(self):
        from qgis.core import QgsVectorLayer
        gpkg_path = os.path.join(self.project_path, "地图范围.gpkg")
        layer = QgsVectorLayer(gpkg_path, "temp", "ogr")
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
        
        temp_jpg = os.path.join(self.project_path, 'tianditu_temp.jpg')
        merged.save(temp_jpg)
        print(f"\n拼接完成! 临时图像保存至: {temp_jpg}")
        
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
       
        print(f"lon_min: {lon_min}, lon_max: {lon_max}, lat_min: {lat_min}, lat_max: {lat_max}")
        x_min_3857, y_min_3857 = transformer.transform(lon_min, lat_min)
        x_max_3857, y_max_3857 = transformer.transform(lon_max, lat_max)
        
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
        if not self._check_gpkg_exists():
            raise RuntimeError("地图范围.gpkg不存在，请先创建")
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


if __name__ == "__main__":
    center_lon = 113.370327
    center_lat = 23.201580
    side_length = 10
    project_dir = r"C:\Users\Administrator\Desktop\QGIS\地图制作\DemoMakeQGISMapAuto01"
    
    print(f"=== 测试 DemMakeQGISHeadless ===")
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
        
        print("保存项目...")
        project_path = maker.save_project()
        
        print(f"项目已保存到: {project_path}")
        
        print("\n=== 开始天地图下载验证 ===")
        if maker._check_gpkg_exists():
            print("地图范围.gpkg存在，开始下载天地图...")
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
            print("验证失败: 地图范围.gpkg 不存在!")
        
        print("\n=== 所有测试完成 ===")
        
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
