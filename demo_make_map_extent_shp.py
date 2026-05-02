import math
import os
import sys

from PyQt5.QtCore import QMetaType
from PyQt5.QtGui import QColor

# 初始化qgis环境，固定写法
_conda_prefix = sys.prefix
        
_qgis_python = os.path.join(_conda_prefix, "Library", "python")
if _qgis_python not in sys.path:
    sys.path.insert(0, _qgis_python)
        
_qgis_bin = os.path.join(_conda_prefix, "Library", "bin")
os.environ["PATH"] = _qgis_bin + os.pathsep + os.environ.get("PATH", "")

if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(_qgis_bin)

from qgis.core import *
qgis_prefix = os.path.join(_conda_prefix, "Library")
QgsApplication.setPrefixPath(qgis_prefix, True)
        
qgs_app = QgsApplication([], False)
qgs_app.initQgis()

# 设置qgis项目路径
# C:\Users\Administrator\Desktop\QGIS\qgis笔记\QGIS开发\projectTest\project4
# projectPath = r'C:\Users\Administrator\Desktop\QGIS\qgis笔记\QGIS开发\projectTest\makeMapExtentShp'
projectPath = r'C:\Users\Administrator\Desktop\QGIS\projectTest\makeMapExtentShp'

project = QgsProject.instance()

# 设置项目的坐标系wsg84
crs = QgsCoordinateReferenceSystem('EPSG:4326')
project.setCrs(crs)

# 创建多点矢量图层
multipointLayer = QgsVectorLayer("multipoint?crs=epsg:4326", "multipointLayer", "memory")

# 校验图层是否创建成功
if not multipointLayer.isValid():
    print("图层创建失败")
    exit(1)

# 图层开启编辑模式
multipointLayer.startEditing()

# 给多点图层添加属性id和name
multipointLayer.dataProvider().addAttributes([
    QgsField("id", QMetaType.Type.Int),
    QgsField("name", QMetaType.Type.QString,"text", len=254)
])

multipointLayer.updateFields()

# 添加一个经纬度坐标，天安门
center_longitude = 116.397428
center_latitude = 39.908569
side_length_km = 10

# point = QgsFeature(QgsGeometry.fromPointXY(QgsPointXY(116.397428, 39.908569)), 1)
# 创建multipoint_layer一个QgsFeature对象
feat = QgsFeature(multipointLayer.fields())
feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(center_longitude, center_latitude)))

# 设置点的属性值
# feat.setAttribute("name", "天安门")
feat['name'] = "天安门"

# 添加到点图层
multipointLayer.dataProvider().addFeatures([feat])


# 计算正方形四个角点 ------
# 使用QgsDistanceArea进行精确距离计算
da = QgsDistanceArea()
da.setEllipsoid("WGS84")

# 计算经纬度偏移量（米），半边长
half_side = side_length_km * 500

# 计算四个方向上的边界点
# 北
north_point = da.computeSpheroidProject(
    QgsPointXY(center_longitude, center_latitude),
    distance=half_side,
    azimuth=math.radians(0) # 正北方向
)
print(north_point)
north = QgsPointXY(north_point.x(), north_point.y())
feat = QgsFeature(multipointLayer.fields())
feat['name'] = "北"
feat.setGeometry(QgsGeometry.fromPointXY(north))
multipointLayer.dataProvider().addFeatures([feat])

# 南
south_point = da.computeSpheroidProject(
    QgsPointXY(center_longitude, center_latitude),
    distance=half_side,
    azimuth=math.radians(180) # 正南方向
)
south = QgsPointXY(south_point.x(), south_point.y())
feat = QgsFeature(multipointLayer.fields())
feat['name'] = "南"
feat.setGeometry(QgsGeometry.fromPointXY(south))
multipointLayer.dataProvider().addFeatures([feat])

# 东
east_point = da.computeSpheroidProject(
    QgsPointXY(center_longitude, center_latitude),
    distance=half_side,
    azimuth=math.radians(90)  # 正东方向
)
east = QgsPointXY(east_point.x(), east_point.y())
feat = QgsFeature(multipointLayer.fields())
feat['name'] = "东"
feat.setGeometry(QgsGeometry.fromPointXY(east))
multipointLayer.dataProvider().addFeatures([feat])

# 西
west_point = da.computeSpheroidProject(
    QgsPointXY(center_longitude, center_latitude),
    distance=half_side,
    azimuth=math.radians(270) # 正西方向
)
top_left = QgsPointXY(west_point.x(), west_point.y())
feat = QgsFeature(multipointLayer.fields())
feat['name'] = "西"
feat.setGeometry(QgsGeometry.fromPointXY(top_left))
multipointLayer.dataProvider().addFeatures([feat])

# 确定四个角点坐标
# 西北
top_left = QgsPointXY(west_point.x(), north_point.y())
feat = QgsFeature(multipointLayer.fields())
feat['name'] = "西北"
feat.setGeometry(QgsGeometry.fromPointXY(top_left))
multipointLayer.dataProvider().addFeatures([feat])
# 东北
top_right = QgsPointXY(east_point.x(), north_point.y())
feat = QgsFeature(multipointLayer.fields())
feat['name'] = "东北"
feat.setGeometry(QgsGeometry.fromPointXY(top_right))
multipointLayer.dataProvider().addFeatures([feat])
# 东南
bottom_right = QgsPointXY(east_point.x(), south_point.y())
feat = QgsFeature(multipointLayer.fields())
feat['name'] = "东南"
feat.setGeometry(QgsGeometry.fromPointXY(bottom_right))
multipointLayer.dataProvider().addFeatures([feat])
# 西南
bottom_left = QgsPointXY(west_point.x(), south_point.y())
feat = QgsFeature(multipointLayer.fields())
feat['name'] = "西南"
feat.setGeometry(QgsGeometry.fromPointXY(bottom_left))
multipointLayer.dataProvider().addFeatures([feat])

# 重画
multipointLayer.triggerRepaint()

# 更新图层
multipointLayer.updateExtents()
multipointLayer.commitChanges()


# 设置点图层文件名
# multipointLayer.setFileName(projectPath + "\\multipointLayer.shp")
multipointLayerFileName = "multipointLayer.shp"

# 定义导出参数
save_options = QgsVectorFileWriter.SaveVectorOptions()
save_options.driverName = "ESRI Shapefile"
save_options.fileEncoding = "UTF-8"
transform_context = QgsProject.instance().transformContext()
save_options.transformContext = transform_context
save_options.layerName = multipointLayer.name()
save_options.addAttributes = True
save_options.updateFile = True

# 图层导出
# QgsVectorFileWriter.writeAsVectorFormat(multipointLayer, projectPath + "\\" + shpFileName, "utf-8", None, "ESRI Shapefile"))
# 执行导出,qgis版本3.40
write_result, error_message, new_file, new_layer = QgsVectorFileWriter.writeAsVectorFormatV3(
    layer=multipointLayer,
    fileName=projectPath+'\\'+multipointLayerFileName,
    transformContext=transform_context,
    options=save_options
)

# 创建polygon图层
polygonLayer = QgsVectorLayer("polygon?crs=epsg:4326", "polygonLayer", "memory")
if not polygonLayer.isValid():
    print("图层创建失败")
    exit(1)

# 开始编辑
polygonLayer.startEditing()

# 设置图层属性，id
polygonLayer.dataProvider().addAttributes([
    QgsField("id", QMetaType.Type.Int)
])

# 更新属性
polygonLayer.updateFields()


# ===== 3. 创建多边形几何 =====
polygon = QgsGeometry.fromPolygonXY([[
    top_left,
    top_right,
    bottom_right,
    bottom_left,
    top_left  # 闭合多边形
]])



# ===== 4. 创建要素并添加到图层 =====
feature = QgsFeature()
feature.setGeometry(polygon)
feature.setAttributes([1])
polygonLayer.dataProvider().addFeature(feature)

# 更新
polygonLayer.updateExtents()
polygonLayer.commitChanges()

#  设置图层文件名
polygonLayerFileName = "polygonLayer.shp"

# 设置存储参数
save_options = QgsVectorFileWriter.SaveVectorOptions()
save_options.driverName = "ESRI Shapefile"
save_options.fileEncoding = "UTF-8"
transform_context = QgsProject.instance().transformContext()
save_options.transformContext = transform_context
save_options.layerName = polygonLayer.name()
save_options.addAttributes = True
save_options.updateFile = True
# 执行导出
write_result, error_message, new_file, new_layer = QgsVectorFileWriter.writeAsVectorFormatV3(
    layer=polygonLayer,
    fileName=projectPath+'\\'+polygonLayerFileName,
    transformContext=transform_context,
    options=save_options
)

# 省级边界路径，2024年省级边界
proshpname = r'2024年初省级.shp'
provshpfile = projectPath + '\\2024年省级边界\\' + proshpname

# 从路径创建图层  provshpPath
provshp = QgsVectorLayer(provshpfile, '2024年省级边界', 'ogr')
# 设置图层的坐标系
provshp.setCrs(crs)

# 在省级边界样式设置部分修改：
provshp.startEditing()
symbol = provshp.renderer().symbol()
# 设置填充色
symbol.setColor(QColor(238, 232, 170))
# 设置边线宽度（需先获取符号层）
symbol_layer = symbol.symbolLayer(0)
symbol_layer.setStrokeWidth(0.2)
symbol_layer.setStrokeColor(QColor(0, 0, 0))  # 可选：设置边线颜色
provshp.triggerRepaint()
provshp.updateExtents()

#  添加图层
project.addMapLayer(provshp)


# 从项目路劲加载"multipoint.shp"
polygonLayer_shp_path = projectPath+'\\'+polygonLayerFileName
polygonLayer_layer = QgsVectorLayer(polygonLayer_shp_path, "polygonLayer", "ogr")

if not polygonLayer_layer.isValid():
    print("加载矢量文件失败")
    sys.exit(-1)

# 图层坐标系不一致，则修改为项目坐标系
if project.crs().authid() != polygonLayer_layer.crs().authid():
    polygonLayer_layer.setCrs(project.crs())
    print("图层坐标系不一致，已修改为项目坐标系")
else:
        print("图层坐标系一致")

# 添加图层
project.addMapLayer(polygonLayer_layer)

# 从项目路劲加载"multipoint.shp"
multipoint_shp_path = projectPath+'\\'+multipointLayerFileName
multipoint_layer = QgsVectorLayer(multipoint_shp_path, "multipointLayer", "ogr")

if not multipoint_layer.isValid():
    print("加载矢量文件失败")
    sys.exit(-1)

# 图层坐标系不一致，则修改为项目坐标系
if project.crs().authid() != multipoint_layer.crs().authid():
    multipoint_layer.setCrs(project.crs())
    print("图层坐标系不一致，已修改为项目坐标系")
else:
        print("图层坐标系一致")

# 添加图层
project.addMapLayer(multipoint_layer)

# 保存项目（包含实体文件引用） ▼
projectName = 'project4.qgz'
project.write(projectPath+'\\'+projectName)