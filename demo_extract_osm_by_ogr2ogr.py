import subprocess

import os
# qgis项目路径
project_dir = r'C:\Users\Administrator\Desktop\QGIS\projectTest\extractOSMFileByOgr2ogr'
osm_file_name = r'mapExtentsCrossOSM.osm'
osm_file = project_dir + r'/' + osm_file_name

def osm_to_shp_ogr2ogr(osm_file, output_dir, layers=None):
    """
    使用ogr2ogr命令将OSM转换为SHP

    参数:
    osm_file (str): 输入OSM文件路径
    output_dir (str): 输出目录
    layers (list): 要转换的图层列表，如['points', 'lines', 'multipolygons']
                  默认为全部图层
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 默认转换所有图层
    if layers is None:
        layers = ['points', 'lines', 'multilinestrings', 'multipolygons']

    for layer in layers:
        cmd = [
            'ogr2ogr',
            '-f', 'ESRI Shapefile',
            "-lco", "ENCODING=UTF-8",  # 指定编码为 UTF-8
            f'{output_dir}/{layer}.shp',
            osm_file,
            layer
        ]

        try:
            subprocess.run(cmd, check=True)
            print(f"成功转换 {layer} 图层")
        except subprocess.CalledProcessError as e:
            print(f"转换 {layer} 图层失败: {e}")


def osm_to_gpkg_ogr2ogr(osm_file, output_dir, layers=None):
    """
    使用ogr2ogr命令将OSM转换为SHP

    参数:
    osm_file (str): 输入OSM文件路径
    output_dir (str): 输出目录
    layers (list): 要转换的图层列表，如['points', 'lines', 'multipolygons']
                  默认为全部图层
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 默认转换所有图层
    if layers is None:
        layers = ['points', 'lines', 'multilinestrings', 'multipolygons']

    for layer in layers:
        cmd = [
            'ogr2ogr',
            '-f', 'GPKG',
            '-nln',f'{layer}',
            f'{output_dir}/{layer}.gpkg',
            osm_file,
            layer
        ]

        try:
            subprocess.run(cmd, check=True)
            print(f"成功转换 {layer} 图层")
        except subprocess.CalledProcessError as e:
            print(f"转换 {layer} 图层失败: {e}")


#osm_to_shp_ogr2ogr(osm_file,project_dir)
osm_to_gpkg_ogr2ogr(osm_file,project_dir)