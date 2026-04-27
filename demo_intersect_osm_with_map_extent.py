import math
import sys
import time
import os
import subprocess

import requests
from PyQt5.QtCore import QMetaType
from qgis.core import *
from tqdm import tqdm
import geopandas as gpd
from shapely.errors import TopologicalError
import traceback

def createMapExtentsLayer(max_long,min_long,max_lat,min_lat,crs):
    """
        创建地图范围图层

        参数:
        给定四个坐标

        返回:
        地图范围图层
    """
    # 创建polygon图层
    polygonLayer = QgsVectorLayer(f"polygon?crs=epsg:4326", "polygonLayer", "memory")
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

    # 创建多边形几何
    # 确定四个角点坐标
    # 西北
    top_left = QgsPointXY(min_long, max_lat)

    # 东北
    top_right = QgsPointXY(max_long, max_lat)

    # 东南
    bottom_right = QgsPointXY(max_long, min_lat)

    # 西南
    bottom_left = QgsPointXY(min_long, min_lat)

    polygon = QgsGeometry.fromPolygonXY([[
        top_left,
        top_right,
        bottom_right,
        bottom_left,
        top_left  # 闭合多边形
    ]])

    # 创建要素并添加到图层
    feature = QgsFeature()
    feature.setGeometry(polygon)
    feature.setAttributes([1])
    polygonLayer.dataProvider().addFeature(feature)

    # 更新
    polygonLayer.updateExtents()
    polygonLayer.commitChanges()

    extent = polygonLayer.extent()

    # 打印范围信息
    print(f"图层范围: {extent}")
    print(f"最小X坐标: {extent.xMinimum()}")
    print(f"最小Y坐标: {extent.yMinimum()}")
    print(f"最大X坐标: {extent.xMaximum()}")
    print(f"最大Y坐标: {extent.yMaximum()}")

    return polygonLayer


def getFourConnerPoints(center_longitude, center_latitude, wide_km, long_km):
    """
        创建地图范围图层

        参数:
            中心坐标
            长km
            宽km

        返回:
            地图范围图层
    """
    # 计算正方形四个角点 ------
    # 使用QgsDistanceArea进行精确距离计算
    da = QgsDistanceArea()
    da.setEllipsoid("WGS84")

    # 计算经纬度偏移量（米），半边长
    long_half_side = long_km * 500
    wide_half_side = wide_km * 500
    print(long_half_side,wide_half_side)
    print(center_longitude, center_latitude)
    # 北
    north_point = da.computeSpheroidProject(
        QgsPointXY(center_longitude, center_latitude),
        distance=wide_half_side,
        azimuth=math.radians(0)  # 正北方向
    )
    print(north_point)

    # 南
    south_point = da.computeSpheroidProject(
        QgsPointXY(center_longitude, center_latitude),
        distance=wide_half_side,
        azimuth=math.radians(180)  # 正南方向
    )


    # 东
    east_point = da.computeSpheroidProject(
        QgsPointXY(center_longitude, center_latitude),
        distance=long_half_side,
        azimuth=math.radians(90)  # 正东方向
    )


    # 西
    west_point = da.computeSpheroidProject(
        QgsPointXY(center_longitude, center_latitude),
        distance=long_half_side,
        azimuth=math.radians(270)  # 正西方向
    )

    max_long, min_long, max_lat, min_lat = east_point.x(),west_point.x(),north_point.y(),south_point.y()
    return max_long, min_long, max_lat, min_lat


def saveVectorLayerFile(vectorLayer, qgsProject, project_dir, polygonLayerFileName,driverName='ESRI Shapefile',fileEncoding='UTF-8'):
    save_options = QgsVectorFileWriter.SaveVectorOptions()
    save_options.driverName = "ESRI Shapefile"
    save_options.fileEncoding = "UTF-8"
    transform_context = qgsProject.transformContext()
    save_options.transformContext = transform_context
    save_options.layerName = vectorLayer.name()
    save_options.addAttributes = True
    save_options.updateFile = True
    # 执行导出
    '''
    write_result : 成功 0 
    error_message ： str
    new_file ： str
    new_layer ： str
    '''
    write_result, error_message, new_file, new_layer = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer=vectorLayer,
        fileName=project_dir + '\\' + polygonLayerFileName,
        transformContext=transform_context,
        options=save_options
    )

    return new_file


def setVectorLayerQml(vectorLayer, mapExtentsLayerQmlFilename):
    # 加载样式并应用
    print(f'加载样式：{mapExtentsLayerQmlFilename}')
    # 验证文件是否存在
    try:
        if not os.path.exists(mapExtentsLayerQmlFilename):
            print(f"错误：样式文件不存在 - {mapExtentsLayerQmlFilename}")
        else:
            # 尝试加载样式
            error_msg,success = vectorLayer.loadNamedStyle(mapExtentsLayerQmlFilename)

            if success:
                print(f'加载样式成功：{success}')
                vectorLayer.triggerRepaint()
            else:
                print(f"加载样式失败: {error_msg}")

        return vectorLayer
    except Exception as e:
        print(f"加载样式时发生未预期错误: {str(e)}")
        print("详细错误堆栈:")
        print(traceback.format_exc())
        return False
def download_osm_data(min_lon, min_lat, max_lon, max_lat, output_file="map.osm", timeout=300):
    """
    从OpenStreetMap下载地图数据并保存为OSM文件

    参数:
    min_lon (float): 边界框的最小经度
    min_lat (float): 边界框的最小纬度
    max_lon (float): 边界框的最大经度
    max_lat (float): 边界框的最大纬度
    output_file (str): 输出文件的路径，默认为"map.osm"
    timeout (int): 请求超时时间（秒），默认为300秒
    """
    # 构建Overpass API查询URL
    overpass_url = "https://overpass-api.de/api/map"
    query_params = {
        "bbox": f"{min_lon}, {min_lat}, {max_lon}, {max_lat}"
    }



    # 准备请求头，设置用户代理
    headers = {
        "User-Agent": "OSM Data Downloader/1.0 (https://example.com; your_email@example.com)"
    }

    print(f"正在下载OSM数据，边界框: {min_lon}, {min_lat}, {max_lon}, {max_lat}")
    print(f"目标文件: {output_file}")

    try:
        # 发送请求并获取响应
        start_time = time.time()
        response = requests.get(overpass_url, params=query_params, headers=headers, timeout=timeout, stream=True)

        # 检查响应状态码
        if response.status_code == 200:
            # 获取响应的总大小（如果可用）
            total_size = int(response.headers.get('content-length', 0))
            block_size = 1024  # 1 KB

            # 创建保存文件的目录（如果不存在）
            os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)

            # 使用tqdm显示下载进度
            with open(output_file, 'wb') as file, tqdm(
                    desc="下载进度",
                    total=total_size,
                    unit='B',
                    unit_scale=True,
                    unit_divisor=1024
            ) as bar:
                for data in response.iter_content(block_size):
                    bar.update(len(data))
                    file.write(data)

            download_time = time.time() - start_time
            print(f"下载完成！文件大小: {os.path.getsize(output_file) / (1024 * 1024):.2f} MB")
            print(f"下载用时: {download_time:.2f} 秒")
        else:
            print(f"下载失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")

            # 检查是否是请求过大的错误
            if "Request size too large" in response.text:
                print("提示: 请求的区域可能太大。请尝试减小边界框的大小。")

    except requests.exceptions.Timeout:
        print(f"请求超时，超时时间: {timeout} 秒")
    except requests.exceptions.RequestException as e:
        print(f"发生网络错误: {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")

# 提取osm的点线面，'points', 'lines', 'multipolygons'

def extract_osm_layer_gpkg(osm_path, output_path, layer, crs=None):
    """
    从OSM文件提取线图层

    参数:
    osm_path (str): OSM文件路径(.osm, .pbf)
    output_path (str): 输出文件路径，默认不保存
    layer(str)：一般有['points', 'lines', 'multilinestrings', 'multipolygons']
    crs (str/int, optional): 输出图层的CRS，默认使用OSM原始CRS (EPSG:4326)

    返回:
    gpkg文件
    """
    # 检查文件是否存在
    if not os.path.exists(osm_path):
        raise FileNotFoundError(f"OSM文件不存在: {osm_path}")

    output_file = f'{output_path}/osm_{layer}.gpkg'
    if os.path.isfile(output_file):
        os.remove(output_file)
        print(f"文件 '{output_file}' 已成功删除")

    # 读取OSM文件
    try:
        cmd = [
            'ogr2ogr',
            '-f', 'GPKG',
            '-nln', f'{layer}',
            output_file,
            osm_path,
            layer
        ]

        subprocess.run(cmd, check=True)
        print(f"文件 '{output_file}' 已生成")
        return output_file

    except subprocess.CalledProcessError as e:
        print(f"转换 {layer} 图层失败: {e}")
        return None
    except Exception as e:
        print(f"处理OSM文件时出错: {e}")
        return None


def layer_intersection(project_dir,shp_file, gpkg_file, gpkg_layer_name):
    """
    实现 Shapefile 与 GeoPackage图层的相交操作

    参数:
        shp_file: Shapefile文件路径
        gpkg_file: GeoPackage文件路径
        gpkg_layer_name: GeoPackage中的图层名称
        output_path: 相交结果保存路径（.gpkg格式）
    """
    try:
        # 读取Shapefile数据
        first_picture_file = f'{project_dir}\\{shp_file}'
        print(f"读取Shapefile: {first_picture_file}")
        if os.path.isfile(first_picture_file):
            shp_gdf = gpd.read_file(first_picture_file)
        else:
            raise FileNotFoundError(f"shp文件不存在: {first_picture_file}")

        if shp_gdf.empty:
            print("警告：读取的shp图层为空")
            return None
        else:
            # 获取边界范围 (minx, miny, maxx, maxy)
            bounds = shp_gdf.total_bounds

            # 组织成字典返回
            result = {
                'min_x': bounds[0],
                'max_x': bounds[2],
                'min_y': bounds[1],
                'max_y': bounds[3]
            }

            print(f'图层一的坐标系:{shp_gdf.crs}')
            print(f"图层边界坐标：")
            print(f"最小X坐标 (min_x): {result['min_x']:.6f}")
            print(f"最大X坐标 (max_x): {result['max_x']:.6f}")
            print(f"最小Y坐标 (min_y): {result['min_y']:.6f}")
            print(f"最大Y坐标 (max_y): {result['max_y']:.6f}")

        # 检查几何有效性
        if shp_gdf.is_valid.all():
            print(f"Shapefile几何有效性:{shp_gdf.is_valid.all()}")
        else:
            shp_gdf = shp_gdf.make_valid()

        # 读取GeoPackage数据
        first_picture_file = f'{project_dir}\\{gpkg_file}'
        print(f"读取GeoPackage图层: {first_picture_file} 中的 {gpkg_layer_name}")
        if os.path.isfile(first_picture_file):
            gpkg_gdf = gpd.read_file(first_picture_file, layer=gpkg_layer_name)
        else:
            raise FileNotFoundError(f"gpkg文件不存在: {first_picture_file}")


        if gpkg_gdf.empty:
            print("警告：读取的pgkp图层为空")
            return None
        else:
            # 获取边界范围 (minx, miny, maxx, maxy)
            bounds = gpkg_gdf.total_bounds

            # 组织成字典返回
            result = {
                'min_x': bounds[0],
                'max_x': bounds[2],
                'min_y': bounds[1],
                'max_y': bounds[3]
            }

            print(f'图层二的坐标系:{gpkg_gdf.crs}')
            print(f"图层边界坐标：")
            print(f"最小X坐标 (min_x): {result['min_x']:.6f}")
            print(f"最大X坐标 (max_x): {result['max_x']:.6f}")
            print(f"最小Y坐标 (min_y): {result['min_y']:.6f}")
            print(f"最大Y坐标 (max_y): {result['max_y']:.6f}")

        # 检查几何有效性
        if gpkg_gdf.is_valid.all():
            print(f"GPKG几何有效性:{gpkg_gdf.is_valid.all()}")
        else:
            gpkg_gdf = gpkg_gdf.make_valid()

        # 检查坐标参考系是否一致，不一致则进行转换
        if shp_gdf.crs != gpkg_gdf.crs:
            print("坐标参考系不一致，正在转换...")
            # 将gpkg图层转换为与shp相同的坐标系统
            gpkg_gdf = gpkg_gdf.to_crs(shp_gdf.crs)


        # 执行相交操作
        print("执行图层相交操作...")
        # 参数一是要保留的，参数二是交集的范围。
        intersection_gdf = gpd.overlay(gpkg_gdf,shp_gdf, how='intersection')

        # print(f'交接后的数据长度:{len(intersection_gdf)}')
        # 检查结果是否为空
        if intersection_gdf.empty:
            print("警告：两个图层没有相交部分")
            return None

        # 保存相交结果为GeoPackage
        output_file = f'{project_dir}/osm_{gpkg_layer_name}_intersection.gpkg'
        print(f"保存相交结果到: {output_file}")
        intersection_gdf.to_file(output_file, layer=f'osm_{gpkg_layer_name}_intersection', driver="GPKG")

        print(f"相交操作完成，共生成 {len(intersection_gdf)} 个要素")
        return output_file

    except FileNotFoundError as e:
        print(f"错误：文件未找到 - {e}")
        return None
    except TopologicalError as e:
        print(f"错误：拓扑错误 - {e}")
        return None
    except Exception as e:
        print(f"发生错误：{e}")
        return None


if __name__ == '__main__':
    # qgis项目路径
    project_dir = r'C:\Users\Administrator\Desktop\QGIS\projectTest\mapExtentsCrossOSM'

    # 设置项目坐标系
    crs = 'epsg:4326'
    # 创建qgis工程
    project = QgsProject.instance()

    # 设置项目的坐标系wsg84
    crs = QgsCoordinateReferenceSystem(crs)
    project.setCrs(crs)

    # 设置一点中心节点，龙洞地区
    center_longitude,center_latitude = 113.371560,23.208652

    # 设置地图方位的长宽
    long_km = 10
    wide_km = 9

    # 通过中心节点，获得最大最小经纬度坐标
    max_long,min_long,max_lat,min_lat = getFourConnerPoints(center_longitude,center_latitude,wide_km,long_km)
    print(max_long,min_long,max_lat,min_lat)

    # 1.生成地图范围 ************************
    # 通过中心节点，获取指定长宽的地图范围，layer
    mapExtentsLayer = createMapExtentsLayer(max_long,min_long,max_lat,min_lat,crs)

    mapExtentsLayerFilename = 'mapExtentsLayer.shp'
    # 保存矢量图层文件
    saveVectorLayerFilename = saveVectorLayerFile(mapExtentsLayer,project,project_dir,mapExtentsLayerFilename)

    # 读取保存的矢量文件
    project_add_layer = QgsVectorLayer(saveVectorLayerFilename, '地图范围', 'ogr')
    project_add_layer.setCrs(crs)

    # 设置矢量图层样式,文件无法保存样式，只有工程里的文件可以
    mapExtentsLayerQml = '地图范围样式.qml'
    mapExtentsLayerQmlFilename = f'{project_dir}\\{mapExtentsLayerQml}'
    project_add_layer = setVectorLayerQml(project_add_layer,mapExtentsLayerQmlFilename)

    if not project_add_layer.isValid():
        print("加载矢量文件失败")
        sys.exit(-1)

    # 图层坐标系不一致，则修改为项目坐标系
    if project.crs().authid() != project_add_layer.crs().authid():
        project_add_layer.setCrs(project.crs())
        print("图层坐标系不一致，已修改为项目坐标系")
    else:
        print("图层坐标系一致")

    # 添加图层
    project.addMapLayer(project_add_layer)

    # 2.下载osm ************************
    output_file_name = 'mapExtentsCrossOSM.osm'
    output_file = f'{project_dir}\\{output_file_name}'

    # min_lon, min_lat, max_lon, max_lat
    download_osm_data(
        min_lon=min_long,  # 最小经度
        min_lat=min_lat,  # 最小纬度
        max_lon=max_long,  # 最大经度
        max_lat=max_lat,  # 最大纬度
        output_file=output_file
    )

    # 3.提取：点、线、面 ************************
    # 提取osm的 points
    layer_file_points = extract_osm_layer_gpkg(output_file, project_dir, 'points', crs=None)
    # 提取osm的 lines
    layer_file_lines = extract_osm_layer_gpkg(output_file, project_dir, 'lines', crs=None)
    # 提取osm的 multipolygons
    layer_file_multipolygons = extract_osm_layer_gpkg(output_file, project_dir, 'multipolygons', crs=None)

    # 4.提取：相交点、线、面 ************************
    # points
    layer_file_points_intersection = layer_intersection(project_dir, mapExtentsLayerFilename, os.path.basename(layer_file_points), 'points')
    # lines
    layer_file_lines_intersection = layer_intersection(project_dir, mapExtentsLayerFilename, os.path.basename(layer_file_lines), 'lines')
    # multipolygons
    layer_file_multipolygons_intersection = layer_intersection(project_dir, mapExtentsLayerFilename, os.path.basename(layer_file_multipolygons), 'multipolygons')

    # 5.添加到项目中，并加载样式
    # lines
    '''
    project_add_layer_lines = QgsVectorLayer(layer_file_lines_intersection, 'lines', 'ogr')
    project_add_layer_lines.setCrs(crs)

    if not project_add_layer_lines.isValid():
        print("加载矢量文件失败")
        sys.exit(-1)
    else:
        print(f'加载矢量文件成功:{layer_file_lines_intersection}')

    # 设置矢量图层样式,文件无法保存样式，只有工程里的文件可以
    mapExtentsLayerQml = '线图层样式.qml'
    mapExtentsLayerQmlFilename = f'{project_dir}\\{mapExtentsLayerQml}'

    project_add_layer_lines = setVectorLayerQml(project_add_layer_lines, mapExtentsLayerQmlFilename)

    # 图层坐标系不一致，则修改为项目坐标系
    if project.crs().authid() != project_add_layer_lines.crs().authid():
        project_add_layer_lines.setCrs(project.crs())
        print("图层坐标系不一致，已修改为项目坐标系")
    else:
        print("图层坐标系一致")

    # 添加图层
    project.addMapLayer(project_add_layer_lines)
    '''

    ''' '''
    # points
    project_add_layer = QgsVectorLayer(layer_file_points_intersection, 'POI', 'ogr')
    project_add_layer.setCrs(crs)

    if not project_add_layer.isValid():
        print("加载矢量文件失败")
        sys.exit(-1)
    else:
        print(f'加载矢量文件成功:{layer_file_points_intersection}')

    # 设置矢量图层样式,文件无法保存样式，只有工程里的文件可以

    #mapExtentsLayerQml = 'POI图层样式.qml'
    mapExtentsLayerQml = 'POI图层样式_原始.qml'
    mapExtentsLayerQmlFilename = f'{project_dir}\\{mapExtentsLayerQml}'
    project_add_layer = setVectorLayerQml(project_add_layer,mapExtentsLayerQmlFilename)


    # 图层坐标系不一致，则修改为项目坐标系
    if project.crs().authid() != project_add_layer.crs().authid():
        project_add_layer.setCrs(project.crs())
        print("图层坐标系不一致，已修改为项目坐标系")
    else:
        print("图层坐标系一致")

    # 添加图层
    project.addMapLayer(project_add_layer)


    # 保存项目到项目路径
    projectName = 'mapExtentsCrossOSM.qgz'
    project.write(project_dir + '\\' + projectName)

