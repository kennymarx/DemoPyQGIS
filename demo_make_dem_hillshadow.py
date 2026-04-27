#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成山体阴影
使用GDAL命令行工具将DEM文件生成山体阴影TIFF文件
"""

import subprocess
import os
import sys


def generate_hillshade(dem_path, output_path, azimuth=315, altitude=45, z_factor=1):
    """
    生成山体阴影
    
    Args:
        dem_path (str): DEM文件路径
        output_path (str): 输出山体阴影文件路径
        azimuth (float): 太阳方位角（度），默认315度（西北方向）
        altitude (float): 太阳高度角（度），默认45度
        z_factor (float): 高程缩放因子，默认1
    """
    # 设置GDAL_DATA环境变量
    os.environ['GDAL_DATA'] = "C:/ProgramData/miniforge3/envs/qgis_py3.9_new/Library/share/gdal"
    os.environ['PATH'] = f"C:/ProgramData/miniforge3/envs/qgis_py3.9_new/Library/bin;{os.environ['PATH']}"
    
    # 构建gdal命令
    command = [
        "C:/ProgramData/miniforge3/envs/qgis_py3.9_new/Library/bin/gdaldem.exe",
        "hillshade",
        "-az", str(azimuth),
        "-alt", str(altitude),
        "-z", str(z_factor),
        dem_path,
        output_path
    ]
    
    try:
        # 执行命令
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True
        )
        print("命令执行成功:")
        print(result.stdout)
        print(f"山体阴影已生成: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print("命令执行失败:")
        print(f"错误信息: {e.stderr}")
        return False


def calculate_hillshade_above_elevation(hillshade_path, dem_path, output_path, elevation_threshold=20):
    """
    使用gdal_calc.py计算大于指定海拔的山体阴影
    
    Args:
        hillshade_path (str): 山体阴影文件路径
        dem_path (str): DEM文件路径
        output_path (str): 输出文件路径
        elevation_threshold (float): 海拔阈值，默认20米
    """
    # 设置环境变量
    os.environ['GDAL_DATA'] = "C:/ProgramData/miniforge3/envs/qgis_py3.9_new/Library/share/gdal"
    os.environ['PATH'] = f"C:/ProgramData/miniforge3/envs/qgis_py3.9_new/Library/bin;{os.environ['PATH']}"
    os.environ['PATH'] = f"C:/ProgramData/miniforge3/envs/qgis_py3.9_new/Scripts;{os.environ['PATH']}"
    os.environ['PYTHONPATH'] = "C:/ProgramData/miniforge3/envs/qgis_py3.9_new/Lib/site-packages"
    
    # 构建gdal_calc命令
    command = [
        #"C:/ProgramData/miniforge3/envs/qgis_py3.9_new/Scripts/gdal_calc.exe",
        "gdal_calc.exe",
        "--overwrite",
        f"--calc=numpy.where(B >= {elevation_threshold}, A, numpy.nan)",
        "--format", "GTiff",
        "--type", "Float32",
        "-A", hillshade_path,
        "--A_band", "1",
        "-B", dem_path,
        "--outfile", output_path
    ]
    
    try:
        # 执行命令
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True
        )
        print("栅格计算器执行成功:")
        print(result.stdout)
        print(f"大于{elevation_threshold}米的山体阴影已生成: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print("栅格计算器执行失败:")
        print(f"错误信息: {e.stderr}")
        return False


def main():
    """
    主函数
    """
    # 输入DEM文件路径
    dem_path = "dem-test.tif"
    # 输出山体阴影文件路径
    hillshade_path = "hillshade.tif"
    # 输出大于20米海拔的山体阴影文件路径
    output_path = "hillshade_above_40m.tif"
    
    # 检查DEM文件是否存在
    if not os.path.exists(dem_path):
        print(f"DEM文件不存在: {dem_path}")
        return
    
    # 生成山体阴影
    if generate_hillshade(dem_path, hillshade_path):
        # 计算大于20米海拔的山体阴影
        calculate_hillshade_above_elevation(hillshade_path, dem_path, output_path,elevation_threshold=40)


if __name__ == "__main__":
    main()
