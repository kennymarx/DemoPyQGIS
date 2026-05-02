import math
import os
import sys
import shutil
from PyQt5.QtCore import QMetaType


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
        print("\n测试完成!")
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()