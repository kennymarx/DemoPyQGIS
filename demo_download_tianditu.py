from owslib.wmts import WebMapTileService
import os
from PIL import Image
import math
from osgeo import gdal
from pyproj import Transformer

# 必须设置header,因为天地图设置的api是浏览器，否则认为是爬虫，返回418疑似攻击。
headers ={
    'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Referer':'https://www.yourdomain.com/',
    'Accept-Language':'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding':'gzip, deflate',
    'Connection':'keep-alive'
}
# 天地图WMTS服务地址（需替换为你的API密钥）
tk = 'a96ffd6582a7e32c0084d79f7976e182'
wmts_url = f'http://t0.tianditu.gov.cn/img_w/wmts?tk={tk}'


# 创建WMTS客户端
wmts = WebMapTileService(url=wmts_url,headers=headers)

print(wmts_url)
print(headers)

# 打印可用图层信息
print("可用图层:")
for layer in wmts.contents:
    print(f"- {layer}")

# 选择图层（影像底图）
layer_name = 'img'

# 获取图层信息
layer = wmts[layer_name]
print(f"\n选择图层: {layer_name}")
print(f"标题: {layer.title}")
print(f"抽象信息: {layer.abstract}")
#print(f"坐标系: {layer.crsOptions}")
#print(f"瓦片矩阵集: {layer.tilematrixsets}")


# 设置下载参数
zoom_level = 14  # 缩放级别 (0-18)
tile_matrix_set = 'w'  # 使用Web Mercator投影
output_dir = 'tianditu_tiles'
os.makedirs(output_dir, exist_ok=True)

# 北京地区的经纬度范围
# wgs 84 EPSG:4326
# lon_min, lon_max = 116.2, 116.6
lon_min, lon_max = 116.2, 116.3
# lat_min, lat_max = 39.7, 40.1
lat_min, lat_max = 39.7, 39.8


# 将经纬度转换为瓦片坐标
def deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    print(f"xtile:{xtile}")
    print(f"xtile:{ytile}")
    return (xtile, ytile)


# 计算瓦片范围
x_min, y_min = deg2num(lat_max, lon_min, zoom_level)
x_max, y_max = deg2num(lat_min, lon_max, zoom_level)

print(f"\n下载级别: {zoom_level}")
print(f"瓦片列范围: {x_min} 到 {x_max}")
print(f"瓦片行范围: {y_min} 到 {y_max}")

# 下载瓦片
total_tiles = (x_max - x_min + 1) * (y_max - y_min + 1)
count = 0

print("\n开始下载瓦片...")
for x in range(x_min, x_max + 1):
    for y in range(y_min, y_max + 1):

        try:
            # 获取瓦片图像
            '''
            默认情况下，base_url 使用 WebMapTileService（） 返回的 GetCapabilities 
            <ows:Operation name="GetCapabilities">
            <ows:DCP>
            <ows:HTTP>
            <ows:Get xlink:href="http://t0.tianditu.gov.cn/img_w/wmts?">
            <ows:Constraint name="GetEncoding">
            <ows:AllowedValues>
            <ows:Value>KVP</ows:Value>
            </ows:AllowedValues>
            </ows:Constraint>
            </ows:Get>
            </ows:HTTP>
            </ows:DCP>
            
            即http://t0.tianditu.gov.cn/img_w/wmts?，
            缺少tk变量（key）
            所以这里必须再次设置 base_url = wmts_url
            '''
            tile = wmts.gettile(
                base_url=wmts_url,
                layer=layer_name,
                tilematrixset=tile_matrix_set,
                tilematrix=str(zoom_level),
                row=y,
                column=x,
                #tk={tk}
            )

            # print(wmts_url)
            # 保存瓦片
            filename = os.path.join(output_dir, f'tile_{zoom_level}_{x}_{y}.jpg')
            with open(filename, 'wb') as f:
                f.write(tile.read())

            count += 1
            print(f"已下载 {count}/{total_tiles} 瓦片: {filename}")

        except Exception as e:
            print(f"下载失败 ({x},{y}): {str(e)}")

print(f"\n瓦片下载完成! 共下载 {count} 个瓦片到目录: {output_dir}")


# 拼接瓦片（可选）
def merge_tiles(output_dir, zoom, x_range, y_range, output_image):
    tile_width = 256
    tile_height = 256

    # 计算拼接后图像尺寸
    width = (x_range[1] - x_range[0] + 1) * tile_width
    height = (y_range[1] - y_range[0] + 1) * tile_height

    # 创建空白画布
    merged = Image.new('RGB', (width, height))

    # 拼接所有瓦片
    for x in range(x_range[0], x_range[1] + 1):
        for y in range(y_range[0], y_range[1] + 1):
            try:
                tile_path = os.path.join(output_dir, f'tile_{zoom}_{x}_{y}.jpg')
                tile_img = Image.open(tile_path)

                # 计算位置
                pos_x = (x - x_range[0]) * tile_width
                pos_y = (y - y_range[0]) * tile_height

                merged.paste(tile_img, (pos_x, pos_y))
                print(f"已拼接瓦片 ({x},{y})")
            except Exception as e:
                print(f"拼接失败 ({x},{y}): {str(e)}")

    # 保存拼接后的图像
    merged.save(output_image)
    print(f"\n拼接完成! 图像保存至: {output_image}")
    return merged


# 执行拼接
picture_name = 'tianditu_merge'
output_image = picture_name+r'.jpg'
merged_img = merge_tiles(
    output_dir=output_dir,
    zoom=zoom_level,
    x_range=(x_min, x_max),
    y_range=(y_min, y_max),
    output_image=output_image
)

# 显示拼接后的图像（可选）
# merged_img.show()

# merged_img的像素列坐标
print(f'merged_img的像素列坐标:{merged_img.width}')
# merged_img的像素行坐标
print(f'merged_img的像素行坐标:{merged_img.height}')
# 图像尺寸
print(f'merged_img的图像尺寸:{merged_img.size}')

# 转换成GeoTIFF

'''
# 坐标转换
transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
x_min_3857, y_min_3857 = transformer.transform(lon_min, lat_min)
x_max_3857, y_max_3857 = transformer.transform(lon_max, lat_max)
#
'''
# 关键修复：根据实际下载的瓦片范围反算地理坐标
# 左上角瓦片 (x_min, y_min) 对应的实际地理范围
top_lat, left_lon = self._num2deg(x_range[0], y_range[0], zoom)
# 右下角瓦片 (x_max+1, y_max+1) 对应的实际地理范围（+1 是因为瓦片坐标表示左下角）
bottom_lat, right_lon = self._num2deg(x_range[1] + 1, y_range[1] + 1, zoom)
        
# 使用反算出的实际范围计算 GCP 坐标
transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
x_min_3857, y_max_3857 = transformer.transform(left_lon, top_lat)    # 左上角
x_max_3857, y_min_3857 = transformer.transform(right_lon, bottom_lat) # 右下角

# 消除警告 + 明确开启异常（推荐）
gdal.UseExceptions()

'''
gdal.GCP(x, y, z, pixel, line)
x: 地面控制点的经度坐标 (目标坐标系，如 EPSG:4326)
y: 地面控制点的纬度坐标 (目标坐标系，如 EPSG:4326)
z: 高程值 (通常设为 0 如果不使用高程)
pixel: 图像列坐标 (图像中的 X 坐标)
line: 图像行坐标 (图像中的 Y 坐标)
'''
gcp_list = [
    gdal.GCP(x_min_3857, y_max_3857, 0, 0, 0),  # 西北
    gdal.GCP(x_max_3857, y_max_3857, 0, merged_img.width, 0),  # 东北
    gdal.GCP(x_min_3857, y_min_3857, 0, 0, merged_img.height),  # 西南
    gdal.GCP(x_max_3857, y_min_3857, 0, merged_img.width, merged_img.height)  # 东南
]

# tif 需要使用名称	EPSG:3857 - WGS 84 / Pseudo-Mercator，单位：米
options = gdal.TranslateOptions(format='GTiff', outputSRS='EPSG:3857', GCPs=gcp_list)
geotiffFilename = picture_name + '.tif'
gdal.Translate(geotiffFilename, output_image, options=options)
