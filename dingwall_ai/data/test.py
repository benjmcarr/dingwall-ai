import zipfile
from pathlib import Path

import folium
import geopandas as gpd
import numpy as np
from sentinelsat.sentinel import SentinelAPI
import rasterio
import matplotlib.pyplot as plt
from rasterio import plot
from rasterio.plot import show
from rasterio.mask import mask
from osgeo import gdal

# connect to the API
from sentinelsat import SentinelAPI, read_geojson, geojson_to_wkt
from datetime import date

DATA_DIR = Path("/home/ben/projects/dingwall-ai/data")
TILE_DIR = DATA_DIR / "tiles"

centre = [57.729899455398794, -4.283983505297812]
m = folium.Map(centre, zoom_start=11)
geojson_path = DATA_DIR / "map.geojson"
boundary = gpd.read_file(geojson_path)
folium.GeoJson(boundary).add_to(m)
m.save(DATA_DIR / "map.html")

footprint = geojson_to_wkt(read_geojson(geojson_path))

api = SentinelAPI(None, None, "https://scihub.copernicus.eu/dhus/")
products = api.query(
    footprint,
    date=("20221001", "20221030"),
    platformname="Sentinel-2",
    cloudcoverpercentage=(0, 20),
    limit=10,
)
assert len(products), "No products for that query"
gdf = api.to_geodataframe(products)
gdf_sorted = gdf.sort_values(["cloudcoverpercentage"], ascending=[True])
uuid = gdf_sorted.index[0]
api.download(uuid, directory_path=TILE_DIR)

tile_path = next(TILE_DIR.iterdir())
with zipfile.ZipFile(tile_path, "r") as zip_ref:
    zip_ref.extractall(TILE_DIR)
tile_path = (
        tile_path.with_suffix(".SAFE") / "GRANULE" / "L1C_T30VVJ_A029178_20221007T114346"
)
band_prefix = "_".join(next((tile_path / "IMG_DATA").iterdir()).stem.split("_")[:-1])
blue = rasterio.open(tile_path / "IMG_DATA" / (band_prefix + "_B02.jp2"))
green = rasterio.open(tile_path / "IMG_DATA" / (band_prefix + "_B03.jp2"))
red = rasterio.open(tile_path / "IMG_DATA" / (band_prefix + "_B04.jp2"))

check = rasterio.open(DATA_DIR / "map.tiff")
print(check.crs)

tiff_path = DATA_DIR / "map.tiff"
with rasterio.open(
        tiff_path,
        "w",
        driver="Gtiff",
        width=blue.width,
        height=blue.height,
        count=3,
        crs=blue.crs,
        transform=blue.transform,
        dtype=blue.dtypes[0],
) as rgb:
    rgb.write(blue.read(1), 3)
    rgb.write(green.read(1), 2)
    rgb.write(red.read(1), 1)

bound_crs = boundary.to_crs({"init": "epsg:32630"})
with rasterio.open(tiff_path) as src:
    out_image, out_transform = mask(src, bound_crs.geometry, crop=True)
    out_meta = src.meta.copy()
    out_meta.update(
        {
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
        }
    )

with rasterio.open(DATA_DIR / "masked_image.tif", "w", **out_meta) as final:
    final.write(out_image)


def normalize(array):
    array_min, array_max = array.min(), array.max()
    return (array - array_min) / (array_max - array_min)


src = rasterio.open(DATA_DIR / "masked_image.tif")
plt.figure(figsize=(6, 6))

r = normalize(src.read(1))
g = normalize(src.read(2))
b = normalize(src.read(3))
rgb = np.dstack((r, g, b))
plt.imshow(rgb, cmap="pink")

plt.savefig(DATA_DIR / "map.png")
