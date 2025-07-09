import streamlit as st
import requests
from shapely.geometry import shape
from shapely.ops import transform
import pyproj
import re

st.set_page_config(page_title="Tejas Surveying - Instant Estimate", layout="centered")
st.title("📐 Instant Boundary Survey Estimate")

query = st.text_input("Enter Property Address (e.g. 9439 Jeske Rd)")
rate = st.number_input("Rate per foot ($)", min_value=0.0, value=1.25)

def parse_address(address):
    pattern = re.compile(r'^(\d+)\s+([\w\s]+?)\s+(RD|ST|DR|LN|BLVD|CT|AVE|HWY|WAY|TRAIL|PKWY|CIR)$', re.IGNORECASE)
    match = pattern.search(address.strip().upper())
    if match:
        number, name, st_type = match.groups()
        return number.strip(), name.strip(), st_type.strip()
    return None, None, None

def lookup_parcel_by_address(number, name, st_type):
    where_clause = f"situssno = '{number}' AND situssnm LIKE '%{name}%' AND situsstp = '{st_type}'"
    url = "https://gisweb.fbcad.org/arcgis/rest/services/Hosted/FBCAD_Public_Data/FeatureServer/0/query"
    params = {
        "where": where_clause,
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson"
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    if "features" in data and data["features"]:
        return data["features"][0]
    return None

def estimate_perimeter_cost(geom, rate):
    project = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2277", always_xy=True).transform
    geom_proj = transform(project, geom)
    perimeter_ft = geom_proj.length
    area_ft2 = geom_proj.area
    area_acres = area_ft2 / 43560
    estimate = perimeter_ft * rate
    return perimeter_ft, area_acres, estimate

if st.button("Get Estimate"):
    if not query:
        st.warning("Please enter an address like '9439 Jeske Rd'.")
    else:
        number, name, st_type = parse_address(query)
        if not all([number, name, st_type]):
            st.error("❌ Unable to parse address. Use format like '9439 Jeske Rd'")
        else:
            feature = lookup_parcel_by_address(number, name, st_type)
            if not feature:
                st.error("❌ No real property parcel matched that address.")
            else:
                props = feature["properties"]
                try:
                    geom = shape(feature["geometry"])
                    perimeter_ft, area_acres, estimate = estimate_perimeter_cost(geom, rate)

                    st.success("✅ Parcel found and estimate generated.")
                    st.markdown(f"**Owner:** {props.get('ownername', 'N/A')}")
                    st.markdown(f"**Address:** {query}")
                    st.markdown(f"**Parcel Size:** {area_acres:.2f} acres")
                    st.markdown(f"**Legal Description:** {props.get('legal', 'N/A')}")
                    st.markdown(f"**Deed Reference:** {props.get('instrunum', 'N/A')}")
                    st.markdown(f"**Perimeter:** {perimeter_ft:.2f} ft")
                    st.markdown(f"**Estimated Survey Cost:** ${estimate:,.2f}")

                    if area_acres < 2:
                        st.info("ℹ️ This parcel appears to be less than 2 acres — consider checking for additional parcels.")
                except Exception:
                    st.error("❌ Unable to process parcel geometry.")
