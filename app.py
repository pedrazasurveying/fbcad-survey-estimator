from datetime import datetime
import streamlit as st
import requests
from shapely.geometry import shape
from shapely.ops import transform
import pyproj
import re
import simplekml
import tempfile

st.set_page_config(page_title="Tejas Surveying - Smart Estimate", layout="centered")
st.title("📍 Property Lookup with Deed, Map & KMZ")

# 🔍 Enhanced Search Options
search_mode = st.radio("Search by:", ["Address", "Quick Ref ID", "Owner Name"])
query = ""
last = first = ""
matches = []

if search_mode == "Address":
    query = st.text_input("Enter Property Address (e.g. 1810 First Oaks or First Oaks St)")
    if query:
        number, name, st_type = parse_address_loose(query)
        if name:
            if number and st_type:
                where1 = f"situssno = '{number}' AND UPPER(situssnm) LIKE '%{name.upper()}%' AND UPPER(situsstp) = '{st_type.upper()}'"
                matches = query_parcels(where1)
            if not matches and number:
                where2 = f"situssno = '{number}' AND UPPER(situssnm) LIKE '%{name.upper()}%'"
                matches = query_parcels(where2)
            if not matches:
                where3 = f"UPPER(situssnm) LIKE '%{name.upper()}%'"
                matches = query_parcels(where3)

elif search_mode == "Quick Ref ID":
    query = st.text_input("Enter Quick Ref ID (e.g. R123456)")
    if query:
        where = f"quickrefid = '{query.strip()}'"
        matches = query_parcels(where)

elif search_mode == "Owner Name":
    last = st.text_input("Last Name")
    first = st.text_input("First Name (optional)")
    if last:
        lname = last.strip().upper()
        fname = first.strip().upper()
        if fname:
            where = f"UPPER(ownername) LIKE '{lname}, {fname}%'"
        else:
            where = f"UPPER(ownername) LIKE '{lname}%'"
        matches = query_parcels(where)

# Replace old `feature = None; if query: ...` logic:
feature = None
if matches:
    if len(matches) == 1:
        feature = matches[0]
    else:
        options = {
            f"{f['properties'].get('quickrefid')} | {f['properties'].get('ownername')} | {f['properties'].get('legal', '')[:40]}": f
            for f in matches
        }
        selected = st.selectbox("Multiple parcels found. Select one:", list(options.keys()))
        if selected:
            feature = options[selected]
else:
    if query or last:
        st.warning("No matching parcels found.")
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
    legal = props.get('legal', 'N/A')
    quickrefid = props.get("quickrefid", "")
    deed = props.get('instrunum', '').strip()
    subdivision = block = lot = acres = None

    if legal and legal != "N/A":
        subdivision, block, lot, acres = parse_legal_description(legal)

    try:
        geom = shape(feature["geometry"])
        perimeter_ft, area_acres, estimate = estimate_perimeter_cost(geom, rate)

        st.success("✅ Parcel found and estimate generated.")
        st.markdown(f"**Owner:** {props.get('ownername', 'N/A')}")
        st.markdown(f"**Quick Ref ID:** {quickrefid}")
        st.markdown(f"**Geo ID:** {props.get('propnumber', 'N/A')}")
        st.markdown(f"**Legal Description:** {legal}")
        if subdivision:
            st.markdown(f"**Subdivision:** {subdivision}")
        if block:
            st.markdown(f"**Block:** {block}")
        if lot:
            st.markdown(f"**Lot/Reserve:** {lot}")
        if acres:
            st.markdown(f"**Called Acreage:** {acres}")

        if deed:
            if deed.isdigit():
                deed_url = f"https://www.fortbendcountyclerktexas.com/OfficialRecords/search?instrumentNumber={deed}"
                st.markdown(f"**Deed Reference:** [{deed}]({deed_url})")
            else:
                st.markdown(f"**Deed Reference:** {deed}")
        else:
            st.markdown("**Deed Reference:** N/A")
        
        if quickrefid:
            esearch_url = f"https://esearch.fbcad.org/Property/View?Id={quickrefid}&year={datetime.now().year}"
            st.markdown(f"**Deed History:** [View on FBCAD →]({esearch_url})")
        else:
            st.markdown("**Deed History:** Not available")

        st.markdown(f"**Parcel Size:** {area_acres:.2f} acres")
        st.markdown(f"**Perimeter:** {perimeter_ft:.2f} ft")
        st.markdown(f"**Estimated Survey Cost:** ${estimate:,.2f}")

        centroid = geom.centroid
        maps_url = f"https://www.google.com/maps/search/?api=1&query={centroid.y},{centroid.x}"
        st.markdown(f"**📍 View on Google Maps:** [Open Map]({maps_url})")

        kmz_data = {
            "owner": props.get("ownername", "N/A"),
            "propnumber": props.get("propnumber", "N/A"),
            "legal": legal,
            "subdivision": subdivision,
            "block": block,
            "lot": lot,
            "acres": acres,
            "deed": deed,
            "perimeter_ft": f"{perimeter_ft:,.2f}"
        }

        kmz_path = generate_kmz(geom, metadata=kmz_data)
        with open(kmz_path, "rb") as f:
            st.download_button("📥 Download KMZ (Google Earth)", f, file_name="parcel.kmz")

    except Exception as e:
        st.error("❌ Unable to process parcel geometry.")
        st.text(str(e))
