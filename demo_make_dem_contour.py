import os
import numpy as np
from osgeo import gdal, ogr, osr

# 启用GDAL异常处理
gdal.UseExceptions()

# 直接设置GDAL_DATA环境变量
os.environ['GDAL_DATA'] = r'C:\ProgramData\miniforge3\envs\qgis_py3.9_new\share\gdal'
print(f"设置GDAL_DATA为: {os.environ['GDAL_DATA']}")

def create_dem_contours(dem_path, output_gpkg, interval=10):
    """
    从DEM数据创建等高线
    
    参数:
        dem_path: DEM文件路径
        output_gpkg: 输出等高线GPKG路径
        interval: 等高线间隔
    """
    # 打开DEM文件
    dem_ds = gdal.Open(dem_path)
    if dem_ds is None:
        print(f"无法打开DEM文件: {dem_path}")
        return False
    
    # 获取DEM的地理信息
    band = dem_ds.GetRasterBand(1)
    transform = dem_ds.GetGeoTransform()
    proj = dem_ds.GetProjection()
    
    # 创建输出GPKG
    driver = ogr.GetDriverByName('GPKG')
    if os.path.exists(output_gpkg):
        driver.DeleteDataSource(output_gpkg)
    
    out_ds = driver.CreateDataSource(output_gpkg)
    if out_ds is None:
        print(f"无法创建输出GPKG: {output_gpkg}")
        return False
    
    # 创建空间参考
    srs = osr.SpatialReference(wkt=proj)
    
    # 创建等高线图层
    contour_layer = out_ds.CreateLayer('contours', srs, ogr.wkbLineString)
    
    # 添加字段
    contour_layer.CreateField(ogr.FieldDefn('ELEV', ogr.OFTReal))
    
    # 生成等高线
    print(f"正在生成等高线，间隔: {interval}米")
    # 获取无数据值，如果不存在则使用-9999
    no_data_value = band.GetNoDataValue() or -9999
    # 使用正确的参数顺序和类型
    gdal.ContourGenerate(
        band,
        interval,  # 等高线间隔
        0,        # 起始高程
        [],       # 固定高程列表（空列表）
        1,        # 使用无数据值
        no_data_value,  # 无数据值
        contour_layer,  # 输出图层
        -1,       # 不使用ID字段（-1表示不使用）
        0         # 高程字段索引
    )
    
    # 清理
    dem_ds = None
    out_ds = None
    print(f"等高线生成完成，保存到: {output_gpkg}")
    return True

def main():
    """
    主函数，演示DEM等高线生成
    """
    # 示例DEM路径（需要根据实际情况修改）
    dem_path = 'dem-test.tif'
    output_gpkg = 'contours.gpkg'
    
    # 检查DEM文件是否存在
    if not os.path.exists(dem_path):
        print(f"DEM文件不存在: {dem_path}")
        print("请修改脚本中的dem_path为实际的DEM文件路径")
        return
    
    # 生成等高线
    create_dem_contours(dem_path, output_gpkg, interval=10)

if __name__ == "__main__":
    main()
