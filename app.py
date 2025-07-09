import streamlit as st
import requests
from shapely.geometry import shape
from shapely.ops import transform
import pyproj
import re

st.set_page_config(page_title="Tejas Surveying - Smart Estimate", layout="centered")
st.title("📍 Address Lookup with Fallback + Deed Link")

query = st.text_input("Enter Property Address (e.g. 9439 Jeske or Jeske Rd)")
rate = st.number_input("Rate per foot ($)", min_value=0.0, value=1.25)

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

feature = None

if query:
    number, name, st_type = parse_address_loose(query)
    if not name:
        st.error("❌ Could not parse address. Try something like '9439 Jeske Rd' or 'Jeske'")
    else:
        matches = []
        if number and st_type:
            where1 = f"situssno = '{number}' AND UPPER(situssnm) LIKE '%{name.upper()}%' AND UPPER(situsstp) = '{st_type.upper()}'"
            matches = query_parcels(where1)

        if not matches and number:
            where2 = f"situssno = '{number}' AND UPPER(situssnm) LIKE '%{name.upper()}%'"
            matches = query_parcels(where2)

        if not matches:
            where3 = f"UPPER(situssnm) LIKE '%{name.upper()}%'"
            matches = query_parcels(where3)

        if not matches:
            st.error("❌ No parcels found with any fallback method.")
        elif len(matches) == 1:
            feature = matches[0]
        else:
            options = {f"{f['properties'].get('propnumber')} | {f['properties'].get('ownername', 'N/A')} | {f['properties'].get('legal', 'N/A')[:40]}": f for f in matches}
            selected = st.selectbox("Multiple parcels found. Select one:", list(options.keys()))
            if selected:
                feature = options[selected]

if feature:
    props = feature["properties"]
    try:
        geom = shape(feature["geometry"])
        perimeter_ft, area_acres, estimate = estimate_perimeter_cost(geom, rate)

        st.success("✅ Parcel found and estimate generated.")
        st.markdown(f"**Owner:** {props.get('ownername', 'N/A')}")
        st.markdown(f"**Geo ID:** {props.get('propnumber', 'N/A')}")
        st.markdown(f"**Legal Description:** {props.get('legal', 'N/A')}")
        deed = props.get('instrunum', '')
        if deed:
            deed_url = f"https://www.fortbendcountyclerktexas.com/OfficialRecords/search?instrumentNumber={deed}"
            st.markdown(f"**Deed Reference:** [{deed}]({deed_url})")
        else:
            st.markdown("**Deed Reference:** N/A")
        st.markdown(f"**Parcel Size:** {area_acres:.2f} acres")
        st.markdown(f"**Perimeter:** {perimeter_ft:.2f} ft")
        st.markdown(f"**Estimated Survey Cost:** ${estimate:,.2f}")
    except Exception:
        st.error("❌ Unable to process parcel geometry.")
