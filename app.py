import streamlit as st
import requests
from shapely.geometry import shape
from shapely.ops import transform
import pyproj
import re
import simplekml
import tempfile

st.set_page_config(page_title="Tejas Surveying - Smart Estimate", layout="centered")
st.title("📍 Address Lookup with Deed, Map & KMZ")

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

def parse_legal_description(legal):
    subdivision = block = lot = acreage = None
    legal = legal.strip()
    subdivision_match = re.match(r'^(.*?)(BLOCK|LOT|RESERVE|ACRES)', legal, re.IGNORECASE)
    if subdivision_match:
        subdivision = subdivision_match.group(1).strip(", ").title()
    block_match = re.search(r'BLOCK\s+(\w+)', legal, re.IGNORECASE)
    if not block_match:
        block_match = re.search(r'BLK\s+(\w+)', legal, re.IGNORECASE)
    if block_match:
        block = block_match.group(1)
    lot_match = re.search(r'LOT\s+["\w]+', legal, re.IGNORECASE)
    if lot_match:
        lot = lot_match.group(0).strip()
    reserve_match = re.search(r'RESERVE\s+["\w\s]+', legal, re.IGNORECASE)
    if reserve_match:
        lot = reserve_match.group(0).strip()
    acres_match = re.search(r'ACRES\s+([0-9.]+)', legal, re.IGNORECASE)
    if acres_match:
        acreage = acres_match.group(1)
    return subdivision, block, lot, acreage

def generate_kmz(geom, metadata=None, name="parcel.kmz"):
    kml = simplekml.Kml()
    if geom.geom_type == "Polygon":
        coords = [(x, y) for x, y in list(geom.exterior.coords)]
        poly = kml.newpolygon(name="Parcel", outerboundaryis=coords)
    elif geom.geom_type == "MultiPolygon":
        for poly_geom in geom.geoms:
            coords = [(x, y) for x, y in list(poly_geom.exterior.coords)]
            poly = kml.newpolygon(name="Parcel Part", outerboundaryis=coords)
    poly.style.polystyle.fill = 0
    poly.style.linestyle.color = simplekml.Color.red
    poly.style.linestyle.width = 5
    if metadata:
        html = f"""<b>Owner:</b> {metadata['owner']}<br>
<b>Geo ID:</b> {metadata['propnumber']}<br>
<b>Subdivision:</b> {metadata.get('subdivision', 'N/A')}<br>
<b>Block:</b> {metadata.get('block', 'N/A')}<br>
<b>Lot/Reserve:</b> {metadata.get('lot', 'N/A')}<br>
<b>Called Acreage:</b> {metadata.get('acres', 'N/A')}<br>
<b>Legal:</b> {metadata['legal']}<br>
<b>Deed:</b> {metadata.get('deed', 'N/A')}<br>
<b>Perimeter:</b> {metadata.get('perimeter_ft', 'N/A')} ft"""
        poly.description = html
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".kmz")
    kml.savekmz(tmp.name)
    return tmp.name

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

        legal = props.get('legal', 'N/A')
        st.markdown(f"**Legal Description:** {legal}")
        subdivision, block, lot, acres = parse_legal_description(legal)
        if subdivision:
            st.markdown(f"**Subdivision:** {subdivision}")
        if block:
            st.markdown(f"**Block:** {block}")
        if lot:
            st.markdown(f"**Lot/Reserve:** {lot}")
        if acres:
            st.markdown(f"**Called Acreage:** {acres}")

        deed = props.get('instrunum', '').strip()
        if deed:
            if deed.isdigit():
                deed_url = f"https://www.fortbendcountyclerktexas.com/OfficialRecords/search?instrumentNumber={deed}"
                st.markdown(f"**Deed Reference:** [{deed}]({deed_url})")
            else:
                st.markdown(f"**Deed Reference:** {deed}")
        else:
            st.markdown("**Deed Reference:** N/A")

        st.markdown(f"**Parcel Size:** {area_acres:.2f} acres")
        st.markdown(f"**Perimeter:** {perimeter_ft:.2f} ft")
        st.markdown(f"**Estimated Survey Cost:** ${estimate:,.2f}")

        # Add Google Maps link
        centroid = geom.centroid
        maps_url = f"https://www.google.com/maps/search/?api=1&query={centroid.y},{centroid.x}"
        st.markdown(f"**📍 View on Google Maps:** [Open Map]({maps_url})")

        # Add KMZ download
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

    except Exception:
        st.error("❌ Unable to process parcel geometry.")
