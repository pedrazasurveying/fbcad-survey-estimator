from datetime import datetime
import streamlit as st
import requests
from shapely.geometry import shape
from shapely.ops import transform
import pyproj
import re
import simplekml
import tempfile

def generate_kmz(geom, metadata=None, name="parcel.kmz"):
    kml = simplekml.Kml()
    def add_polygon(g):
        coords = [(x, y) for x, y in list(g.exterior.coords)]
        poly = kml.newpolygon(name="Parcel", outerboundaryis=coords)
        poly.style.polystyle.fill = 0
        poly.style.linestyle.color = simplekml.Color.red
        poly.style.linestyle.width = 5
        if metadata:
            html = (
                f"<b>Owner:</b> {metadata['owner']}<br>"
                f"<b>Geo ID:</b> {metadata['propnumber']}<br>"
                f"<b>Legal:</b> {metadata['legal']}<br>"
                f"<b>Deed:</b> {metadata.get('deed', 'N/A')}<br>"
                f"<b>Perimeter:</b> {metadata.get('perimeter_ft', 'N/A')} ft"
            )
            poly.description = html
    try:
        if geom.geom_type == "Polygon":
            add_polygon(geom)
        elif geom.geom_type == "MultiPolygon":
            for g in geom.geoms:
                add_polygon(g)
        else:
            return None
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".kmz")
        kml.savekmz(tmp.name)
        return tmp.name
    except Exception as e:
        st.warning(f"KMZ error: {e}")
        return None

st.set_page_config(page_title="Tejas Surveying - Smart Estimate", layout="centered")
st.title("📍 Property Lookup with Deed, Map & KMZ")

county = st.selectbox("Select County", ["Fort Bend", "Harris"])

county_config = {
    "Fort Bend": {
        "endpoint": "https://gisweb.fbcad.org/arcgis/rest/services/Hosted/FBCAD_Public_Data/FeatureServer/0/query",
        "crs": "EPSG:2278",
        "fields": {
            "street_num": "situssno",
            "street_name": "situssnm",
            "street_type": "situsstp",
            "owner": "ownername",
            "legal": "legal",
            "deed": "instrunum",
            "parcel_id": "propnumber",
            "quickrefid": "quickrefid",
            "acres": "landsizeac",
            "land_val": "landvalue",
            "imp_val": "impvalue"
        }
    },
    "Harris": {
        "endpoint": "https://services.arcgis.com/su8ic9KbA7PYVxPS/ArcGIS/rest/services/Harris_County_Parcels/FeatureServer/1/query",
        "crs": "EPSG:2278",
        "fields": {
            "street_num": "site_str_num",
            "street_name": "site_str_name",
            "street_type": "site_str_sfx",
            "owner": "owner_name_1",
            "legal": "legal_desc",
            "deed": "deed_ref",
            "parcel_id": "HCAD_NUM",
            "quickrefid": "LOWPARCELID",
            "acres": "Acreage",
            "land_val": "LANDVAL",
            "imp_val": "IMPRVAL"
        }
    }
}

config = county_config[county]
fields = config["fields"]
endpoint = config["endpoint"]
crs_target = config["crs"]

def parse_address_loose(address):
    pattern = re.compile(r'^(\d+)?\s*([\w\s]+?)(\s+(RD|ST|DR|LN|BLVD|CT|AVE|HWY|WAY|TRAIL|PKWY|CIR))?$', re.IGNORECASE)
    match = pattern.search(address.strip().upper())
    if match:
        number = match.group(1) or ''
        name = match.group(2).strip()
        st_type = match.group(4).strip() if match.group(4) else ''
        return number.strip(), name, st_type
    return None, None, None

def query_parcels(where_clause):
    params = {
        "where": where_clause,
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson"
    }
    try:
        r = requests.get(endpoint, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("features", [])
    except requests.exceptions.HTTPError as e:
        st.error(f"❌ HTTP Error for query: `{where_clause}`")
        st.text(str(e))
        return []
    except Exception as e:
        st.error("❌ Error fetching parcel data.")
        st.text(str(e))
        return []        return []        st.text(str(e))
