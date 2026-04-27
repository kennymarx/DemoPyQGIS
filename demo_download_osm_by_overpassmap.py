import requests
import os
import time
from tqdm import tqdm

from script import project

"""
api/map
一般用于全量下载，较少的查询功能。

请考虑使用下面列出的来源来导出：
Overpass API
从 OpenStreetMap 数据库的一个镜像下载此限定边框

https://overpass-api.de/api/map?bbox=99.8,14.6,66.8,86.0
 <bounds minlat="14.6000000" minlon="99.8000000" maxlat="86.0000000" maxlon="66.8000000"/>
 
 f"https://overpass-api.de/api/map?bbox={min_lon},{minlat},{maxlon},{maxlat}"
 min_lon=113.35,  # 最小经度
 min_lat=23.18,  # 最小纬度
 max_lon=113.42,  # 最大经度
 max_lat=23.23,  # 最大纬度
"""
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


if __name__ == "__main__":
    project_dir = r'C:\Users\Administrator\Desktop\QGIS\qgis笔记\QGIS开发\projectTest\downloadOSMByOverpassMap'
    output_file_name = 'downloadosmbyrequestmap.osm'
    output_file = project_dir + r'\\' + output_file_name

    # 龙洞
    download_osm_data(
        min_lon=113.35,  # 最小经度
        min_lat=23.18,  # 最小纬度
        max_lon=113.42,  # 最大经度
        max_lat=23.23,  # 最大纬度
        output_file=output_file
    )
