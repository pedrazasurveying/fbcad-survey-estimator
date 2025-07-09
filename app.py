import streamlit as st
import requests
from shapely.geometry import shape
from shapely.ops import transform
import pyproj
import re

st.set_page_config(page_title="Tejas Surveying - Address Lookup Debug", layout="centered")
st.title("📍 Address Lookup - Smart Fallback Mode")

query = st.text_input("Enter Property Address (e.g. 9439 Jeske Rd)")
rate = st.number_input("Rate per foot ($)", min_value=0.0, value=1.25)

def parse_address(address):
    pattern = re.compile(r'^(\d+)\s+([\w\s]+?)\s+(RD|ST|DR|LN|BLVD|CT|AVE|HWY|WAY|TRAIL|PKWY|CIR)$', re.IGNORECASE)
    match = pattern.search(address.strip().upper())
    if match:
        number, name, st_type = match.groups()
        return number.strip(), name.strip(), st_type.strip()
    return None, None, None

def query_parcels(where_clause):
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
    return r.json().get("features", [])

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
            # Try full match
            where1 = f"situssno = '{number}' AND UPPER(situssnm) LIKE '%{name.upper()}%' AND UPPER(situsstp) = '{st_type.upper()}'"
            matches = query_parcels(where1)

            if not matches:
                # Try number + street name only
                where2 = f"situssno = '{number}' AND UPPER(situssnm) LIKE '%{name.upper()}%'"
                matches = query_parcels(where2)

            if not matches:
                # Try just the street name
                where3 = f"UPPER(situssnm) LIKE '%{name.upper()}%'"
                matches = query_parcels(where3)

            if not matches:
                st.error("❌ No parcels found with any fallback method.")
            elif len(matches) == 1:
                feature = matches[0]
            else:
                options = {f"{f['properties'].get('propnumber')} | {f['properties'].get('ownername', 'N/A')} | {f['properties'].get('legal', 'N/A')[:40]}": f for f in matches}
                choice = st.selectbox("Multiple parcels found. Select one:", options.keys())
                feature = options[choice]

            if matches:
                props = feature["properties"]
                try:
                    geom = shape(feature["geometry"])
                    perimeter_ft, area_acres, estimate = estimate_perimeter_cost(geom, rate)

                    st.success("✅ Parcel found and estimate generated.")
                    st.markdown(f"**Owner:** {props.get('ownername', 'N/A')}")
                    st.markdown(f"**Geo ID:** {props.get('propnumber', 'N/A')}")
                    st.markdown(f"**Legal Description:** {props.get('legal', 'N/A')}")
                    st.markdown(f"**Deed Reference:** {props.get('instrunum', 'N/A')}")
                    st.markdown(f"**Parcel Size:** {area_acres:.2f} acres")
                    st.markdown(f"**Perimeter:** {perimeter_ft:.2f} ft")
                    st.markdown(f"**Estimated Survey Cost:** ${estimate:,.2f}")
                except Exception:
                    st.error("❌ Unable to process parcel geometry.")
