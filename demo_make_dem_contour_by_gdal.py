import subprocess
import os
import sys

def make_dem_contour(input_file, output_file):
    """
    使用gdal_contour命令生成等高线图层
    
    参数:
    input_file: str - 输入DEM文件路径
    output_file: str - 输出等高线GPKG文件路径
    """
        # 设置GDAL_DATA环境变量
    os.environ['GDAL_DATA'] = "C:/ProgramData/miniforge3/envs/qgis_py3.9_new/Library/share/gdal"
    os.environ['PATH'] = f"C:/ProgramData/miniforge3/envs/qgis_py3.9_new/Library/bin;{os.environ['PATH']}"
    
    # 创建输出目录
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"创建输出目录: {output_dir}")
    
    # 构建gdal_contour命令
    command = [
        "gdal_contour",
        "-b", "1",
        "-a", "ELEV",
        "-i", "10.0",
        "-f", "GPKG",
        input_file,
        output_file
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
        return True
    except subprocess.CalledProcessError as e:
        print("命令执行失败:")
        print(f"错误信息: {e.stderr}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: python makeDemContourDemoWithgdal_contour.py <输入DEM文件> <输出GPKG文件>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    make_dem_contour(input_file, output_file)
