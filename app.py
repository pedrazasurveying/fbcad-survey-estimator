import streamlit as st
import requests
from shapely.geometry import shape
from shapely.ops import transform
import pyproj

st.set_page_config(page_title="Tejas Surveying - Instant Estimate", layout="centered")
st.title("📐 Instant Boundary Survey Estimate")

query = st.text_input("Enter Property Address or Geographic ID")
rate = st.number_input("Rate per foot ($)", min_value=0.0, value=1.25)

def lookup_geo_id_from_address(address):
    addr_clean = address.upper().replace(" ROAD", "").replace(" RD", "").replace(" STREET", "").replace(" ST", "").strip()
    where_clause = f"situsaddress LIKE '%{addr_clean}%' AND accttype = 'R'"

    url = "https://gisweb.fbcad.org/arcgis/rest/services/Hosted/FBCAD_Public_Data/FeatureServer/0/query"
    params = {
        "where": where_clause,
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson"
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if "features" in data and len(data["features"]) > 0:
            return data["features"][0]  # return first real property parcel match
        return None
    except Exception:
        return None

def lookup_by_geo_id(geo_id):
    where_clause = f"propnumber='{geo_id}'"
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
    return r.json()

if st.button("Get Estimate"):
    if not query:
        st.warning("Please enter an address or Geographic ID.")
    else:
        feature = None
        # Determine if it's a Geo ID or address
        if any(char.isdigit() for char in query) and '-' in query:
            data = lookup_by_geo_id(query)
            if "features" in data and data["features"]:
                feature = data["features"][0]
        else:
            feature = lookup_geo_id_from_address(query)

        if not feature:
            st.error("❌ No real property parcel found matching your input.")
        else:
            props = feature["properties"]
            try:
                geom = shape(feature["geometry"])
                project = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2277", always_xy=True).transform
                geom_proj = transform(project, geom)

                perimeter_ft = geom_proj.length
                estimate = perimeter_ft * rate
                area_ft2 = geom_proj.area
                area_acres = area_ft2 / 43560

                st.success("✅ Parcel found and estimate generated.")
                st.markdown(f"**Owner:** {props.get('ownername', 'N/A')}")
                st.markdown(f"**Site Address:** {props.get('situsaddress', 'N/A')}")
                st.markdown(f"**Parcel Size:** {area_acres:.2f} acres")
                st.markdown(f"**Legal Description:** {props.get('legaldesc', 'N/A')}")
                st.markdown(f"**Deed Reference:** {props.get('deedreference', 'N/A')}")
                st.markdown(f"**Perimeter:** {perimeter_ft:.2f} ft")
                st.markdown(f"**Estimated Survey Cost:** ${estimate:,.2f}")

                if area_acres < 2:
                    st.info("ℹ️ This parcel appears to be less than 2 acres — consider checking if additional parcels are associated.")
            except Exception:
                st.error("❌ Unable to process parcel geometry. Parcel may be missing shape data.")
