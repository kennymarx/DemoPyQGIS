import os
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from osgeo import ogr, gdal

# ============ 配置区 ============
# 输入OSM PBF文件路径
osm_pbf_file = r'C:\Users\Administrator\Documents\trae_projects\webframetest\DemoPyQGIS\osm_files\guangdong-260828.osm.pbf'

# 输出目录
output_dir = r'C:\Users\Administrator\Documents\trae_projects\webframetest\DemoPyQGIS\osm_files\guangdong_cities'

# 广东省边界GeoJSON文件路径（自动从DataV下载）
# DataV.GeoAtlas 接口: https://geo.datav.aliyun.com/areas_v3/bound/{adcode}_full.json
# 440000 = 广东省，_full.json 包含下辖所有地级市边界
guangdong_adcode = '440000'
city_boundary_geojson = os.path.join(
    os.path.dirname(osm_pbf_file),
    f'guangdong_boundary_{guangdong_adcode}.json'
)
dataV_url = f'https://geo.datav.aliyun.com/areas_v3/bound/{guangdong_adcode}_full.json'

# 修复后的边界文件路径（MakeValid 处理自相交后输出，裁剪时使用此文件）
# 使用 GPKG（二进制）避免 GeoJSON 文本序列化导致坐标精度损失、自相交复发
city_boundary_fixed = os.path.join(
    os.path.dirname(osm_pbf_file),
    f'guangdong_boundary_{guangdong_adcode}_fixed.gpkg'
)

# 边界文件中城市名称字段名（DataV GeoJSON中使用 'name' 字段）
city_name_field = 'name'

# OSM PBF中的图层
osm_layers = ['points', 'lines', 'multilinestrings', 'multipolygons']

# 并行拆分的并发进程数（每个 ogr2ogr 进程约占 0.5~1.5GB 内存，按机器内存调整）
max_workers = 4

# 广东省21个地级市（与DataV GeoJSON中的name属性对应）
guangdong_cities = [
    '广州市', '深圳市', '珠海市', '汕头市', '佛山市',
    '韶关市', '湛江市', '肇庆市', '江门市', '茂名市',
    '惠州市', '梅州市', '汕尾市', '河源市', '阳江市',
    '清远市', '东莞市', '中山市', '潮州市', '揭阳市',
    '云浮市'
]


def download_boundary_file(url, output_path):
    """
    下载广东省边界GeoJSON文件

    参数:
        url: DataV GeoJSON API地址
        output_path: 本地保存路径
    """
    print(f"正在从DataV下载广东省边界数据...")
    print(f"URL: {url}")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response:
            data = response.read()
        with open(output_path, 'wb') as f:
            f.write(data)
        file_size = os.path.getsize(output_path) / 1024
        print(f"下载成功: {output_path} ({file_size:.2f} KB)")
        return True
    except Exception as e:
        print(f"下载失败: {e}")
        return False


def _extract_polygons(geom):
    """
    递归提取几何中的多边形部件。
    MakeValid 可能返回 GeometryCollection（含线/点），需要只保留面要素。

    参数:
        geom: ogr.Geometry

    返回:
        list[ogr.Geometry]: 多边形列表（wkbPolygon）
    """
    polygons = []
    if geom is None:
        return polygons

    geom_type = geom.GetGeometryType()
    if geom_type == ogr.wkbPolygon:
        polygons.append(geom.Clone())
    elif geom_type == ogr.wkbMultiPolygon:
        for i in range(geom.GetGeometryCount()):
            part = geom.GetGeometryRef(i)
            if part is not None:
                polygons.extend(_extract_polygons(part))
    elif geom_type in (ogr.wkbGeometryCollection,
                       ogr.wkbGeometryCollection25D):
        for i in range(geom.GetGeometryCount()):
            polygons.extend(_extract_polygons(geom.GetGeometryRef(i)))

    return polygons


def fix_boundary_geometry(input_path, output_path):
    """
    对边界 GeoJSON 中每个要素的几何进行有效性修复（处理自相交等问题），
    输出一个可安全用于 ogr2ogr -clipsrc 的修复版文件。

    参数:
        input_path: 原始边界 GeoJSON 路径
        output_path: 修复后输出路径

    返回:
        bool: 是否成功
    """
    print(f"\n正在修复边界几何自相交问题...")
    print(f"  输入: {input_path}")
    print(f"  输出: {output_path}")

    if os.path.exists(output_path):
        os.remove(output_path)

    ogr.UseExceptions()

    in_ds = ogr.Open(input_path)
    if in_ds is None:
        print(f"  错误: 无法打开边界文件: {input_path}")
        return False

    in_layer = in_ds.GetLayer()
    srs = in_layer.GetSpatialRef()

    # 输出为 GPKG（二进制），避免 GeoJSON 文本序列化导致坐标精度损失
    out_driver = ogr.GetDriverByName('GPKG')
    out_ds = out_driver.CreateDataSource(output_path)
    out_layer = out_ds.CreateLayer(
        in_layer.GetName(), srs=srs, geom_type=ogr.wkbMultiPolygon
    )

    # 复制字段
    in_layer_defn = in_layer.GetLayerDefn()
    for i in range(in_layer_defn.GetFieldCount()):
        field_defn = in_layer_defn.GetFieldDefn(i)
        out_layer.CreateField(field_defn)

    fixed_count = 0
    for feat in in_layer:
        geom = feat.GetGeometryRef()
        if geom is None:
            continue

        # 对无效几何进行修复
        if not geom.IsValid():
            city_name = feat.GetFieldAsString(city_name_field)
            print(f"  修复自相交: {city_name}")
            # Buffer(0) 能直接将自相交多边形修正为有效面（取重叠区域并集）
            fixed = geom.Buffer(0)
            if fixed is not None and not fixed.IsEmpty() and fixed.IsValid():
                geom = fixed
            else:
                # Buffer(0) 失败时回退到 MakeValid
                geom = geom.MakeValid()

        # MakeValid 可能返回 GeometryCollection，只保留面部件
        polygons = _extract_polygons(geom)
        if not polygons:
            continue

        # 组装为 MultiPolygon
        multi = ogr.Geometry(ogr.wkbMultiPolygon)
        for poly in polygons:
            if poly.GetArea() > 0:
                multi.AddGeometry(poly)

        if multi.GetGeometryCount() == 0:
            continue

        out_feat = ogr.Feature(out_layer.GetLayerDefn())
        # 先复制属性字段（SetFrom 会覆盖几何，所以必须在 SetGeometry 之前调用）
        out_feat.SetFrom(feat)
        # 再设置修复后的几何
        out_feat.SetGeometry(multi)
        out_layer.CreateFeature(out_feat)
        fixed_count += 1

    out_ds = None
    in_ds = None

    print(f"  修复完成，共处理 {fixed_count} 个城市边界")
    return fixed_count > 0


def split_osm_by_city(osm_pbf, city_boundary, city_field, city_name, output_path):
    """
    使用ogr2ogr将OSM PBF按照地级市边界进行裁剪，输出GPKG文件

    参数:
        osm_pbf: 输入OSM PBF文件路径
        city_boundary: 地级市边界文件路径（GeoJSON或SHP）
        city_field: 边界文件中城市名称字段
        city_name: 要裁剪的城市名称
        output_path: 输出GPKG文件路径

    返回:
        bool: 是否成功
    """
    # 如果输出文件已存在，先删除
    if os.path.exists(output_path):
        os.remove(output_path)
        print(f"  已删除旧文件: {output_path}")

    # 一次传入全部图层，PBF只解析一遍；不指定 -nln 时输出图层名沿用源图层名
    cmd = [
        'ogr2ogr',
        '-f', 'GPKG',
        '-clipsrc', city_boundary,
        '-clipsrcwhere', f"{city_field}='{city_name}'",
        output_path,
        osm_pbf,
    ] + osm_layers

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        err = e.stderr[:300] if e.stderr else str(e)
        print(f"  裁剪 {city_name} 失败: {err}")
        return False


if __name__ == '__main__':
    # 创建输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print("=" * 60)
    print("开始拆分OSM PBF文件（按广东省地级市）")
    print(f"输入文件: {osm_pbf_file}")
    print(f"输出目录: {output_dir}")
    print(f"广东省共 {len(guangdong_cities)} 个地级市")
    print("=" * 60)

    # 检查输入文件
    if not os.path.exists(osm_pbf_file):
        print(f"错误: 输入OSM PBF文件不存在: {osm_pbf_file}")
        exit(1)

    # 检查边界文件，不存在则自动下载
    if not os.path.exists(city_boundary_geojson):
        print(f"\n边界文件不存在，准备从DataV下载...")
        ok = download_boundary_file(dataV_url, city_boundary_geojson)
        if not ok:
            print("错误: 无法下载边界文件，请检查网络或手动下载")
            print(f"手动下载地址: {dataV_url}")
            exit(1)
    else:
        print(f"\n使用已有边界文件: {city_boundary_geojson}")

    # 修复边界几何自相交（DataV 边界数据可能存在无效几何），裁剪时使用修复版
    ok = fix_boundary_geometry(city_boundary_geojson, city_boundary_fixed)
    if not ok:
        print("错误: 边界几何修复失败")
        exit(1)
    clip_boundary = city_boundary_fixed

    success_cities = []
    failed_cities = []

    # 准备任务列表（输出文件名去掉'市'字简化）
    tasks = [
        (city, os.path.join(output_dir, f'{city.replace("市", "")}.gpkg'))
        for city in guangdong_cities
    ]

    print(f"\n开始并行拆分（{max_workers} 个并发进程）...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                split_osm_by_city,
                osm_pbf=osm_pbf_file,
                city_boundary=clip_boundary,
                city_field=city_name_field,
                city_name=city,
                output_path=output_file
            ): (city, output_file)
            for city, output_file in tasks
        }

        done_count = 0
        for future in as_completed(future_map):
            city, output_file = future_map[future]
            done_count += 1
            try:
                result = future.result()
            except Exception as e:
                print(f"  任务异常: {city}: {e}")
                result = False

            if result:
                success_cities.append(city)
                file_size = os.path.getsize(output_file) / (1024 * 1024)
                print(f"[{done_count}/{len(tasks)}] {city} 完成 ({file_size:.2f} MB)")
            else:
                failed_cities.append(city)
                print(f"[{done_count}/{len(tasks)}] {city} 失败")

    print("\n" + "=" * 60)
    print("拆分完成！")
    print(f"成功: {len(success_cities)} 个城市")
    print(f"失败: {len(failed_cities)} 个城市")
    if failed_cities:
        print(f"失败城市: {', '.join(failed_cities)}")
    print("=" * 60)
