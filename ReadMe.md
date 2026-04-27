# 第三阶段（2026年4月）

## demo_make_map_extent_shp.py

```
设置中心点坐标（北京天安门）
    ↓
计算以该点为中心、10km边长的正方形四角坐标
    ↓
使用QgsDistanceArea进行椭球距离计算
    ↓
创建多点图层（9个特征点）
    ↓
创建多边形图层（正方形边界）
    ↓
加载省级边界shp作为底图
    ↓
导出Shapefile文件
    ↓
保存QGIS项目
```

这是一个 创建地图范围多边形 Shapefile 的脚本。

### 核心功能
1. 以某点为中心，创建指定边长的正方形范围
2. 生成多个矢量图层 ：
   - 多点图层（包含中心点、四方向点、四角点）
   - 多边形图层（正方形边界）
3. 叠加省级边界底图
4. 保存 QGIS 项目文件

### 关键计算
项目 值 中心点 天安门 (116.397428, 39.908569) 边长 10 km 坐标系 EPSG:4326 (WGS84)

### 使用的 QGIS API
- QgsDistanceArea.computeSpheroidProject() - 椭球距离计算
- QgsGeometry.fromPointXY() - 创建点几何
- QgsGeometry.fromPolygonXY() - 创建多边形几何
- QgsVectorFileWriter.writeAsVectorFormatV3() - 导出矢量文件
### 输出文件
- multipointLayer.shp - 多点矢量图层
- polygonLayer.shp - 多边形边界图层
- project4.qgz - QGIS 项目文件

## demo_intersect_osm_with_map_extent.py

这个脚本实现了以下功能：

### 1. 创建地图范围图层
- 根据中心坐标点和长宽（公里）计算四个角点坐标
- 使用 QgsDistanceArea 进行椭球距离计算，生成指定范围的矩形多边形
### 2. 下载 OSM 数据
- 使用 Overpass API 从 OpenStreetMap 下载指定边界框的地图数据
- 支持进度条显示下载进度
### 3. 提取 OSM 图层
- 使用 ogr2ogr 将 OSM 文件转换为 GeoPackage 格式
- 分别提取 points （点）、 lines （线）、 multipolygons （面）图层
### 4. 图层相交操作
- 将地图范围图层与 OSM 各图层进行**相交（intersection）**运算
- 只保留落在地图范围内的 OSM 数据
### 5. 结果输出
- 将相交结果保存为 GeoPackage 文件
- 添加到 QGIS 项目中并应用样式
- 保存 QGIS 项目文件

## demo_download_osm_by_overpassmap.py

这是一个 简单的 OSM 数据下载脚本 ，功能单一。

### 核心功能
从 OpenStreetMap 下载指定区域的地图数据

- 使用 Overpass API 的 /api/map 接口下载全量 OSM 数据
- 输入参数：边界的最小/最大经纬度
- 输出： .osm 格式的 XML 文件

```PlainText
定义边界框 (min_lon, min_lat, max_lon, max_lat)
    ↓
构建 Overpass API 请求 (https://overpass-api.de/api/map?bbox=...)
    ↓
发送 HTTP GET 请求（带用户代理头）
    ↓
以流式方式下载数据，显示进度条
    ↓
保存为 .osm 文件
```

## demo_download_tianditu.py

```PlainText
连接天地图 WMTS 服务 (需API密钥)
    ↓
定义下载区域 (经纬度边界) + 缩放级别 (14级)
    ↓
将经纬度 → 瓦片坐标 (x, y)
    ↓
遍历下载所有瓦片图片
    ↓
拼接瓦片 → 完整影像图
    ↓
使用 GCP (地面控制点) 将图片转换为 GeoTIFF
    ↓
输出带地理坐标的 .tif 文件
```

这是一个 下载并拼接天地图影像瓦片 的脚本。

### 核心功能
1. 连接天地图 WMTS 服务
2. 按缩放级别下载指定区域的瓦片
3. 拼接瓦片为完整图像
4. 转换为 GeoTIFF 地理配准图像

### 关键技术点
技术 说明 OWSLib WMTS 连接天地图 Web Map Tile Service deg2num() 经纬度 → 瓦片编号的转换算法 GCP 配准 使用 4 个控制点将图像转换为 GeoTIFF 坐标转换 EPSG:4326 (WGS84) → EPSG:3857 (Web Mercator)

### 测试区域
- 北京地区
- 经度范围：116.2 ~ 116.6
- 纬度范围：39.7 ~ 40.1
- 缩放级别：14 级
### 输出文件
- tianditu_merge.jpg - 拼接后的影像图
- tianditu_merge.tif - 地理配准的 GeoTIFF 文件

## demo_extract_osm_by_ogr2ogr.py

```
输入 OSM 文件 (.osm)
    ↓
调用 ogr2ogr 命令行工具
    ↓
按图层类型分别转换：
  - points (点)
  - lines (线)
  - multilinestrings (多线)
  - multipolygons (多边形)
    ↓
输出各图层的 shp/gpkg 文件
```

这是一个 使用 ogr2ogr 命令行工具提取 OSM 数据 的脚本。

### 核心功能

使用 GDAL 的 ogr2ogr 工具将 .osm 文件转换为 GIS 常用格式：

- Shapefile (.shp)
- GeoPackage (.gpkg)

### 关键函数
函数 功能 osm_to_shp_ogr2ogr() 转换为 Shapefile 格式 osm_to_gpkg_ogr2ogr() 转换为 GeoPackage 格式

### 转换的图层类型
- points - OSM 中的点要素（POI）
- lines - OSM 中的线要素（道路等）
- multilinestrings - 多线要素
- multipolygons - 多边形要素（建筑物等）
### 脚本使用
```
# 转换为 Shapefile
osm_to_shp_ogr2ogr(osm_file, project_dir)

# 转换为 GeoPackage
osm_to_gpkg_ogr2ogr(osm_file, project_dir)
```
注意： 该脚本依赖 ogr2ogr 命令行工具（随 GDAL 安装），需要确保系统 PATH 中包含 GDAL 工具。

## demo_make_dem_contour.py

```
读取 DEM 文件 (.tif)
    ↓
获取地理信息和无数据值
    ↓
创建输出 GeoPackage 数据源
    ↓
调用 gdal.ContourGenerate() 生成等高线
    ↓
输出等高线 LineString 图层（带 ELEV 字段）
```

这是一个 从 DEM（数字高程模型）生成等高线 的脚本。

### 核心功能
使用 GDAL 的 ContourGenerate() 函数从栅格 DEM 数据提取等高线，并保存为 GeoPackage 格式。

### GDAL 函数
```python
gdal.ContourGenerate(
    band,           # 源栅格波段
    interval,       # 等高线间隔
    0,              # 起始高程
    [],             # 固定高程列表
    1,              # 使用无数据值标志
    no_data_value,  # 无数据值
    contour_layer,  # 输出图层
    -1,             # 不使用ID字段
    0               # 高程字段索引
)
```
### 输出
- 格式 : GeoPackage (.gpkg)
- 图层名 : contours
- 要素类型 : LineString
- 属性字段 : ELEV （高程值，单位与 DEM 一致）
### 注意事项
- DEM 文件需要带有正确的地理坐标信息
- 脚本硬编码了 GDAL_DATA 路径，需要根据实际环境调整
- 默认等高线间隔 10 米，可根据需要修改

## demo_make_dem_contour_by_gdal.py

一个**使用 `gdal_contour` 命令行工具生成等高线**的脚本。

### 核心功能

调用 QGIS 安装目录中的 `gdal_contour.exe` 命令行工具，从 DEM 数据生成等高线。

### 工作流程

```
输入 DEM 文件路径（命令行参数1）
输入输出 GPKG 文件路径（命令行参数2）
    ↓
设置 GDAL_DATA 环境变量
    ↓
创建输出目录（如果不存在）
    ↓
构建并执行 gdal_contour 命令
    ↓
生成等高线 GeoPackage 文件
```

### 关键参数

| 参数      | 说明                  |
| --------- | --------------------- |
| `-b 1`    | 使用第 1 波段         |
| `-a ELEV` | 高程字段名            |
| `-i 10.0` | 等高线间隔 10 米      |
| `-f GPKG` | 输出格式为 GeoPackage |

### 命令示例

```bash
python demo_make_dem_contour_by_gdal.py input_dem.tif output_contours.gpkg
```

### 代码结构

1. **`make_dem_contour()` 函数**
   - 设置环境变量
   - 构建命令参数
   - 执行 subprocess 调用
   - 处理执行结果

2. **`__main__` 主程序**
   - 检查命令行参数
   - 调用 `make_dem_contour()` 函数

### 依赖

- **QGIS 3.34.13** 安装环境（提供 `gdal_contour.exe`）
- **GDAL_DATA** 环境变量（硬编码路径）

### 注意事项

- 脚本硬编码了 gdal_contour 工具路径，需要根据实际安装位置调整
- 只支持固定的等高线间隔（10米）
- 需要确保输入 DEM 文件存在且格式正确
- 输出格式固定为 GeoPackage

### 与其他等高线生成脚本的区别

| 脚本                               | 实现方式        | 优势                                       |
| ---------------------------------- | --------------- | ------------------------------------------ |
| `demo_make_dem_contour.py`         | GDAL Python API | 纯 Python 实现，无需外部依赖               |
| `demo_make_dem_contour_by_gdal.py` | 外部命令行工具  | 利用成熟的 gdal_contour 工具，参数配置简单 |

## demo_make_dem_hillshadow.py

**使用 GDAL 命令行工具生成山体阴影**的脚本。

### 核心功能

1. **生成基础山体阴影**
   - 使用 `gdaldem hillshade` 命令从 DEM 数据生成山体阴影
   - 支持自定义太阳方位角、高度角和高程缩放因子

2. **提取高于指定海拔的山体阴影**
   - 使用 `gdal_calc` 命令计算并提取高于指定海拔阈值的山体阴影
   - 将低于阈值的区域设为 `NaN`（无数据）

### 工作流程

```
输入 DEM 文件 (dem-test.tif)
    ↓
生成完整山体阴影 (hillshade.tif)
    ↓
计算高于40米的山体阴影 (hillshade_above_40m.tif)
```

### 关键参数

| 函数                                  | 参数                  | 说明                              |
| ------------------------------------- | --------------------- | --------------------------------- |
| `generate_hillshade`                  | `azimuth`             | 太阳方位角（默认 315°，西北方向） |
| `generate_hillshade`                  | `altitude`            | 太阳高度角（默认 45°）            |
| `generate_hillshade`                  | `z_factor`            | 高程缩放因子（默认 1）            |
| `calculate_hillshade_above_elevation` | `elevation_threshold` | 海拔阈值（默认 40 米）            |

### 使用的 GDAL 命令

1. **山体阴影生成**：
   ```bash
   gdaldem hillshade -az 315 -alt 45 -z 1 dem-test.tif hillshade.tif
   ```

2. **海拔阈值过滤**：
   ```bash
   gdal_calc --calc="numpy.where(B >= 40, A, numpy.nan)" --format GTiff --type Float32 -A hillshade.tif -B dem-test.tif --outfile hillshade_above_40m.tif
   ```

### 输出文件

- `hillshade.tif` - 完整的山体阴影
- `hillshade_above_40m.tif` - 高于 40 米海拔的山体阴影

### 环境依赖

- Miniforge 虚拟环境：`qgis_py3.9_new`
- GDAL 命令行工具（`gdaldem.exe`, `gdal_calc.exe`）
- NumPy（用于 gdal_calc 的计算）

### 注意事项

- 脚本硬编码了环境路径，需要根据实际安装位置调整
- 默认海拔阈值为 40 米，可根据需要修改
- 输入 DEM 文件默认为 `dem-test.tif`，需要确保文件存在

## demo_export_map_by_layout_templet.py

**使用 QGIS 布局模板导出地图**的脚本，功能完整且专业。

### 核心功能

1. **加载多种图层**：
   - 天地图影像（栅格）
   - 等高线（矢量 GeoPackage）
   - 地图范围（矢量 Shapefile，不可见）

2. **应用布局模板**：
   - 加载 `.qpt` 布局模板文件
   - 注入布局变量（最长边、空白比例、边框宽度）

3. **地图渲染**：
   - 绑定图层到地图项
   - 设置显示范围
   - 计算最佳渲染区域
   - 使用 `renderRegionToImage` 渲染

4. **输出 PNG**：
   - 带时间戳的文件名
   - 高 DPI 输出（300 DPI）

### 工作流程

```
初始化 QGIS 应用
    ↓
加载图层（影像 → 等高线 → 地图范围）
    ↓
设置项目 CRS
    ↓
加载 QPT 布局模板
    ↓
注入布局变量（Longest_side, Blank_pct, Border）
    ↓
绑定图层到地图项并设置范围
    ↓
计算渲染区域（所有元素的包围盒）
    ↓
渲染布局到图像
    ↓
保存为 PNG 文件
    ↓
退出 QGIS 应用
```

### 关键技术点

| 技术                  | 说明                                                |
| --------------------- | --------------------------------------------------- |
| **QgsLayoutExporter** | 布局导出工具，使用 `renderRegionToImage` 方法       |
| **QPT 模板**          | QGIS 布局模板文件，包含地图项、图例等               |
| **布局变量**          | 通过 `QgsExpressionContextUtils` 注入，控制布局尺寸 |
| **渲染区域计算**      | 基于所有布局元素的包围盒，确保完整输出              |
| **DPI 计算**          | 从毫米转换为像素：`px = mm / 25.4 * DPI`            |

### 配置参数

| 参数           | 默认值    | 说明                |
| -------------- | --------- | ------------------- |
| `LONGEST_SIDE` | 1000.0 mm | 页面最长边尺寸      |
| `BLANK_PCT`    | 0.15      | 下方空白/图例区比例 |
| `BORDER`       | 10.0 mm   | 地图边框宽度        |
| `DPI`          | 300       | 输出分辨率          |

### 输出文件

- **格式**：PNG
- **命名**：`map_YYYYMMDD_HHMMSS.png`
- **路径**：`QGISMapProject/output/`

### 环境要求

- Miniforge 虚拟环境：`qgis_sample`（conda-forge 安装的 QGIS）
- Python 3.8+（支持 `os.add_dll_directory`）
- 所需数据文件：
  - `天地图-影像地图.tif`
  - `等高线.gpkg`
  - `地图范围.shp`
  - `layoutmodel-new.qpt`（布局模板）

---

**特点**：
- 不使用 `QgsLayoutExporter.exportToImage()`，而是使用 `renderRegionToImage` + `image.save()` 避免 PNG 驱动更新错误
- 支持动态布局变量，可灵活调整输出尺寸
- 详细的日志输出，便于调试
- 完整的错误处理机制
