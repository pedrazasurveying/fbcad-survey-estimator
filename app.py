import streamlit as st
import requests
from shapely.geometry import shape
import math

st.set_page_config(page_title="Tejas Surveying - Instant Estimate", layout="centered")

st.title("📐 Instant Boundary Survey Estimate")

# User input
query = st.text_input("Enter Property Address or Geographic ID")
rate = st.number_input("Rate per foot ($)", min_value=0.0, value=1.25)

def search_parcel(query):
    is_geo_id = any(char.isdigit() for char in query) and '-' in query
    if is_geo_id:
        where_clause = f"propnumber='{query}'"
    else:
        query_clean = query.replace("'", "''")
        where_clause = f"situsaddress LIKE '%{query_clean}%'"

    url = "https://gisweb.fbcad.org/arcgis/rest/services/Hosted/FBCAD_Public_Data/FeatureServer/0/query"
    params = {
        "where": where_clause,
        "outFields": "*",
        "outSR": "4326",
        "f": "geojson"
    }
    r = requests.get(url, params=params)
    return r.json()

if st.button("Get Estimate"):
    if not query:
        st.warning("Please enter a valid address or Geographic ID.")
    else:
        data = search_parcel(query)
        if "features" in data and data["features"]:
            feature = data["features"][0]
            props = feature["properties"]
            geom = shape(feature["geometry"])
            perimeter_meters = geom.length
            perimeter_ft = perimeter_meters * 3.28084
            estimate = perimeter_ft * rate

            st.success("✅ Parcel found and estimate generated.")
            st.markdown(f"**Owner:** {props.get('ownername', 'N/A')}")
            st.markdown(f"**Site Address:** {props.get('situsaddress', 'N/A')}")
            st.markdown(f"**Perimeter:** {perimeter_ft:.2f} ft")
            st.markdown(f"**Estimated Survey Cost:** ${estimate:,.2f}")
        else:
            st.error("No parcel found. Try refining the address or checking the ID.")