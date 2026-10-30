from pathlib import Path

import pandas as pd
import folium
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from branca.colormap import LinearColormap
from folium.plugins import FastMarkerCluster
from streamlit_folium import st_folium


ROOT = Path(__file__).resolve().parent
MUNICIPAL_FILE = ROOT / "data" / "processed" / "gemeente_voorzieningen_woz.csv"
NEIGHBORHOOD_FILE = ROOT / "data" / "processed" / "buurt_voorzieningen_woz.csv"
RAW_FOLDER = ROOT / "data" / "raw"
MUNICIPAL_CENTROID_FILE = RAW_FOLDER / "geography" / "municipality_centroids.csv"
NEIGHBORHOOD_CENTROID_FILE = RAW_FOLDER / "geography" / "neighborhood_centroids.csv"

MUNICIPAL_FACILITIES = {
    "Huisarts": "Gemiddelde_AfstandTotHuisartsenpraktijk_5",
    "Apotheek": "Gemiddelde_AfstandTotApotheek_10",
    "Ziekenhuis": "Gemiddelde_AfstandTotZiekenhuis_11",
    "Grote supermarkt": "Gemiddelde_AfstandTotGroteSupermarkt_24",
    "Kinderdagverblijf": "Gemiddelde_AfstandTotKinderdagverblijf_52",
    "Basisschool": "Gemiddelde_AfstandTotSchool_60",
}
NEIGHBORHOOD_FACILITIES = {
    "Huisarts": "AfstandTotHuisartsenpraktijk_5",
    "Apotheek": "AfstandTotApotheek_10",
    "Ziekenhuis": "AfstandTotZiekenhuis_11",
    "Grote supermarkt": "AfstandTotGroteSupermarkt_24",
    "Kinderdagverblijf": "AfstandTotKinderdagverblijf_52",
    "Basisschool": "AfstandTotSchool_60",
}
COLORS = ["#d97706", "#f6f8fc", "#2563eb"]
BLUE = "#2563eb"
TEAL = "#087f8c"
ORANGE = "#d97706"
INK = "#142d4e"
px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = [BLUE, TEAL, ORANGE]


st.set_page_config(
    page_title="Nabijheid en woningwaarde",
    page_icon="N",
    layout="wide",
)
st.markdown(
    """
    <style>
    :root {
        --ink: #142d4e;
        --muted: #526780;
        --teal: #087f8c;
        --paper: #f6f8fc;
        --line: #dee6f0;
    }
    .stApp, [data-testid="stAppViewContainer"] {
        background: var(--paper);
        color: var(--ink);
    }
    .block-container { max-width: 1440px; padding-top: 3.8rem; padding-bottom: 3rem; }
    h1, h2, h3 { color: var(--ink); letter-spacing: 0; }
    h1 { font-size: 2rem; }
    [data-testid="stSidebar"] { background: #eaf0f8; }
    [data-testid="stAppViewContainer"] :not(svg):not(path),
    [data-testid="stSidebar"] :not(svg):not(path) { color: var(--ink); }
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 16px;
    }
    [data-testid="stMetricLabel"], [data-testid="stCaptionContainer"] { color: var(--muted) !important; }
    [data-testid="stMetricValue"] { color: var(--ink) !important; }
    [data-testid="stAlert"] { background: #eaf0f8 !important; border: 1px solid var(--line); }
    [data-testid="stAlert"] * { color: var(--ink) !important; }
    [data-baseweb="select"] > div { background: #ffffff; border-color: var(--line); }
    .eyebrow {
        color: var(--teal);
        font-size: .8rem;
        font-weight: 700;
        letter-spacing: .14em;
        margin-bottom: .35rem;
    }
    .hero {
        background: #142d4e;
        border-radius: 18px;
        color: #ffffff;
        margin: 8px 0 22px;
        padding: 25px 30px;
    }
    .hero-title {
        color: #ffffff !important;
        font-size: 2rem;
        font-weight: 700;
        line-height: 1.2;
        margin-bottom: .6rem;
    }
    .hero-copy { color: #d8e6f6 !important; margin: 0; max-width: 900px; }
    [data-baseweb="tab-list"] { gap: .4rem; }
    [data-baseweb="tab"] { padding: .5rem .45rem; font-size: .9rem; }
    [data-baseweb="tag"] { background: var(--teal) !important; }
    [data-baseweb="tag"] * { color: #ffffff !important; }
    hr { border-color: var(--line); }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_processed_data(path: str, file_mtime: float) -> pd.DataFrame:
    return pd.read_csv(path)


@st.cache_data
def load_raw_data(path: str) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False)


def add_accessibility_score(data: pd.DataFrame, selected_columns: list[str]) -> pd.DataFrame:
    distances = data[selected_columns]
    ranked_distances = distances.rank(pct=True, ascending=False)
    result = data.copy()
    result["Nabijheidsscore"] = ranked_distances.mean(axis=1) * 100
    return result


st.sidebar.header("Analyse")
analysis_level = st.sidebar.radio("Geografisch niveau", ["Buurt", "Gemeente"], index=0)
is_neighborhood = analysis_level == "Buurt"
processed_file = NEIGHBORHOOD_FILE if is_neighborhood else MUNICIPAL_FILE
centroid_file = NEIGHBORHOOD_CENTROID_FILE if is_neighborhood else MUNICIPAL_CENTROID_FILE
if not processed_file.exists():
    st.error("Verwerkte data ontbreekt. Voer fetch_cbs_data.py en daarna prepare_cbs_data.py uit.")
    st.stop()
if not centroid_file.exists():
    st.error("Kaartcoördinaten ontbreken. Voer fetch_cbs_data.py opnieuw uit.")
    st.stop()

data = load_processed_data(str(processed_file), processed_file.stat().st_mtime)
source_data = data.copy()
facility_columns = NEIGHBORHOOD_FACILITIES if is_neighborhood else MUNICIPAL_FACILITIES
area_name_column = "BuurtNaam" if is_neighborhood else "GemeenteNaam"
area_code_column = "WijkenEnBuurten" if is_neighborhood else "RegioS"
area_label = "buurten" if is_neighborhood else "gemeenten"
density_column = "Bevolkingsdichtheid_2024" if is_neighborhood else "Bevolkingsdichtheid_2026"
address_density_column = (
    "Omgevingsadressendichtheid_2024" if is_neighborhood else "Omgevingsadressendichtheid_2026"
)
available_years = sorted(
    int(column.split("_")[1])
    for column in data.columns
    if column.startswith("WOZ_") and column.endswith("_euro")
)
default_year = 2025 if 2025 in available_years else max(available_years)

if len(available_years) > 1:
    woz_year = st.sidebar.slider(
        "WOZ-jaar",
        min_value=min(available_years),
        max_value=max(available_years),
        value=default_year,
        step=1,
        key="woz_year_slider",
    )
else:
    woz_year = available_years[0]
    st.sidebar.caption(f"WOZ-jaar: {woz_year} · enige buurtbron beschikbaar")
selected_facilities = st.sidebar.multiselect(
    "Voorzieningen in de nabijheidsscore",
    list(facility_columns),
    default=list(facility_columns),
)
top_count = st.sidebar.slider(f"{analysis_level} in de ranglijst", 5, 30, 10)
map_measure = st.sidebar.radio(
    "Kleur op de kaart",
    ["WOZ-afwijking", "WOZ-waarde", "Nabijheidsscore"],
)
map_municipality = "Alle gemeenten"
if is_neighborhood:
    map_municipality = st.sidebar.selectbox(
        "Zoom naar gemeente",
        ["Alle gemeenten", *sorted(data["GemeenteNaam"].dropna().unique())],
    )
show_raw_data = st.sidebar.checkbox("Toon brondata")

if not selected_facilities:
    st.warning("Selecteer minimaal één voorziening om de nabijheidsscore te berekenen.")
    st.stop()

selected_columns = [facility_columns[name] for name in selected_facilities]
data = add_accessibility_score(data, selected_columns)
score_range = st.sidebar.slider(
    "Nabijheidsscore",
    0.0,
    100.0,
    (0.0, 100.0),
)
data = data.loc[data["Nabijheidsscore"].between(*score_range)].copy()

woz_column = f"WOZ_{woz_year}_euro"
analysis_data = data.dropna(subset=["Nabijheidsscore", woz_column]).copy()
if len(analysis_data) < 3 or analysis_data["Nabijheidsscore"].nunique() < 2:
    st.error(f"Er zijn te weinig verschillende {area_label} voor de regressie.")
    st.stop()

x_values = analysis_data["Nabijheidsscore"]
y_values = analysis_data[woz_column]
x_centered = x_values - x_values.mean()
y_centered = y_values - y_values.mean()
slope = (x_centered * y_centered).sum() / (x_centered**2).sum()
intercept = y_values.mean() - slope * x_values.mean()
analysis_data["WOZ_voorspeld"] = intercept + slope * x_values
analysis_data["WOZ_residu"] = y_values - analysis_data["WOZ_voorspeld"]
correlation = x_values.corr(y_values)
residual_sum_squares = (analysis_data["WOZ_residu"] ** 2).sum()
total_sum_squares = (y_centered**2).sum()
r_squared = 1 - residual_sum_squares / total_sum_squares
slope_standard_error = (
    (residual_sum_squares / (len(analysis_data) - 2))
    / (x_centered**2).sum()
) ** 0.5
confidence_lower = slope - 1.96 * slope_standard_error
confidence_upper = slope + 1.96 * slope_standard_error

map_columns = {
    "WOZ-afwijking": "WOZ_residu",
    "WOZ-waarde": woz_column,
    "Nabijheidsscore": "Nabijheidsscore",
}
map_column = map_columns[map_measure]
map_data = analysis_data.dropna(subset=["Latitude", "Longitude", map_column])
if is_neighborhood and map_municipality != "Alle gemeenten":
    map_data = map_data.loc[map_data["GemeenteNaam"].eq(map_municipality)]

analysis_data["Nabijheidsgroep"] = pd.qcut(
    analysis_data["Nabijheidsscore"].rank(method="first"),
    q=4,
    labels=["Q1 · minst dichtbij", "Q2", "Q3", "Q4 · meest dichtbij"],
)
quartile_order = ["Q1 · minst dichtbij", "Q2", "Q3", "Q4 · meest dichtbij"]
quartile_colors = {
    "Q1 · minst dichtbij": BLUE,
    "Q2": TEAL,
    "Q3": ORANGE,
    "Q4 · meest dichtbij": INK,
}
high_access = analysis_data.loc[
    analysis_data["Nabijheidsscore"] >= analysis_data["Nabijheidsscore"].median()
]
focus_candidates = high_access.loc[high_access["WOZ_residu"] < 0].sort_values("WOZ_residu")
if focus_candidates.empty:
    focus_text = "In deze selectie is geen gemeente met zowel bovengemiddelde nabijheid als een WOZ onder de lineaire verwachting."
else:
    focus = focus_candidates.iloc[0]
    focus_gap = abs(focus["WOZ_residu"])
    focus_text = (
        f"{focus[area_name_column]} combineert een nabijheidsscore van "
        f"{focus['Nabijheidsscore']:.1f} met een WOZ die € {focus_gap:,.0f} "
        f"({focus_gap / focus['WOZ_voorspeld']:.1%}) onder de modelverwachting ligt."
    ).replace(",", ".")

year_columns = sorted(
    [column for column in analysis_data if column.startswith("WOZ_") and column.endswith("_euro")],
    key=lambda column: int(column.split("_")[1]),
)
woz_trend = analysis_data.melt(
    id_vars=["Nabijheidsgroep"],
    value_vars=year_columns,
    var_name="WOZ-kolom",
    value_name="WOZ-euro",
).dropna(subset=["WOZ-euro"])
woz_trend["Jaar"] = woz_trend["WOZ-kolom"].str.extract(r"(\d{4})").astype(int)
woz_trend = (
    woz_trend.groupby(["Jaar", "Nabijheidsgroep"], observed=True)["WOZ-euro"]
    .mean()
    .reset_index()
)

st.caption(
    f"SELECTIE · WOZ {woz_year} · {len(analysis_data)} {area_label} · "
    f"{len(selected_facilities)} voorzieningen · score {score_range[0]:.0f}–{score_range[1]:.0f}"
)
overview_tab, map_tab, facilities_tab, method_tab = st.tabs(
    ["Overzicht", "Kaart & afwijking", "Voorzieningen", "Data & methode"]
)

with overview_tab:
    st.markdown(
        '<div class="eyebrow">NEDERLAND / CASE 7 · RICHTING B</div>'
        f'<div class="hero"><div class="hero-title">Welke {area_label} combineren goede nabijheid met lage woningwaarde?</div>'
        f'<p class="hero-copy">{focus_text} De analyse zoekt {area_label} met een negatieve afwijking, '
        "niet simpelweg de laagste WOZ.</p></div>",
        unsafe_allow_html=True,
    )
    if is_neighborhood:
        st.info(
            "WOZ komt uit CBS Kerncijfers wijken en buurten 2024; voorzieningen zijn uit 2025. "
            "Slechts buurten met WOZ én een matchende code zijn in de analyse opgenomen."
        )
    else:
        st.warning(
            "De gemeentelijke WOZ is een alternatief analyseniveau. Buurt-afstanden worden hiervoor per gemeente gemiddeld."
        )

    metric_columns = st.columns(4)
    metric_columns[0].metric(analysis_level + "en" if is_neighborhood else "Gemeenten", f"{len(analysis_data):,}".replace(",", "."))
    metric_columns[1].metric(
        f"WOZ {woz_year}",
        f"€ {analysis_data[woz_column].mean() / 1000:.1f}k".replace(".", ","),
    )
    metric_columns[2].metric("Correlatie r", f"{correlation:.2f}")
    metric_columns[3].metric("Model R²", f"{r_squared:.2f}")

    st.caption(
        f"Lineaire samenhang: 10 punten hogere nabijheidsscore hangen samen met "
        f"€ {10 * slope:,.0f} WOZ-verschil (benaderd 95%-BI € {10 * confidence_lower:,.0f} tot "
        f"€ {10 * confidence_upper:,.0f}). Het model verklaart {r_squared:.1%} van de variatie. "
        "Dit is een associatie, geen causaal effect."
        .replace(",", ".")
    )

    scatter_panel, group_panel = st.columns([1.2, 1])
    with scatter_panel:
        st.subheader("Nabijheid tegenover woningwaarde")
        scatter_figure = px.scatter(
            analysis_data,
            x="Nabijheidsscore",
            y=woz_column,
            color="WOZ_residu",
            color_continuous_scale=COLORS,
            color_continuous_midpoint=0,
            hover_name=area_name_column,
            hover_data={
                "Nabijheidsscore": ":.1f",
                "WOZ_residu": ":,.0f",
                density_column: ":,.0f",
            },
            labels={
                "Nabijheidsscore": "Nabijheidsscore (hoger = dichterbij)",
                woz_column: f"Gemiddelde WOZ {woz_year} (€)",
                "WOZ_residu": "Afwijking t.o.v. model (€)",
            },
        )
        line_scores = [
            analysis_data["Nabijheidsscore"].min()
            + (analysis_data["Nabijheidsscore"].max() - analysis_data["Nabijheidsscore"].min())
            * step
            / 50
            for step in range(51)
        ]
        line_prediction = [intercept + slope * score for score in line_scores]
        scatter_figure.add_trace(
            go.Scatter(
                x=line_scores,
                y=line_prediction,
                mode="lines",
                name="Lineair model",
                line={"color": INK, "width": 2},
                hoverinfo="skip",
            )
        )
        scatter_figure.update_layout(
            height=440,
            margin={"l": 12, "r": 20, "t": 30, "b": 30},
            yaxis={"tickprefix": "€ ", "tickformat": ",.0f"},
            coloraxis_colorbar={"title": "Afwijking (€)"},
            legend={"orientation": "h", "y": -0.2},
        )
        st.plotly_chart(scatter_figure, width="stretch")
        st.caption("Onder de lijn = lagere WOZ dan het model verwacht; boven de lijn = hogere WOZ.")

    with group_panel:
        st.subheader("WOZ per nabijheidskwartiel")
        quartile_figure = px.box(
            analysis_data,
            x="Nabijheidsgroep",
            y=woz_column,
            color="Nabijheidsgroep",
            category_orders={"Nabijheidsgroep": quartile_order},
            color_discrete_map=quartile_colors,
            points="outliers",
            labels={
                "Nabijheidsgroep": "Relatieve nabijheid",
                woz_column: f"Gemiddelde WOZ {woz_year} (€)",
            },
        )
        quartile_figure.update_layout(
            height=440,
            showlegend=False,
            margin={"l": 12, "r": 20, "t": 30, "b": 65},
            yaxis={"tickprefix": "€ ", "tickformat": ",.0f"},
        )
        st.plotly_chart(quartile_figure, width="stretch")
        st.caption(f"Kwartielen vergelijken de WOZ-verdeling van {area_label}, niet individuele woningen.")

    trend_figure = px.line(
        woz_trend,
        x="Jaar",
        y="WOZ-euro",
        color="Nabijheidsgroep",
        markers=True,
        category_orders={"Nabijheidsgroep": quartile_order},
        color_discrete_map=quartile_colors,
        labels={"WOZ-euro": "Gemiddelde WOZ (€)", "Jaar": "WOZ-jaar"},
    )
    trend_figure.update_layout(
        height=390,
        margin={"l": 12, "r": 20, "t": 30, "b": 30},
        yaxis={"tickprefix": "€ ", "tickformat": ",.0f"},
        legend_title_text="Nabijheidsgroep",
    )
    st.subheader("Hoe ontwikkelde de WOZ zich per nabijheidsgroep?")
    st.plotly_chart(trend_figure, width="stretch")
    st.caption(
        f"De {area_label} zijn gegroepeerd op hun geselecteerde voorzieningen-score. "
        f"De score is een relatieve rangscore; de WOZ-lijn is het gemiddelde op {analysis_level.lower()}niveau."
    )

with map_tab:
    st.markdown('<div class="eyebrow">CASE 7B / RUIMTELIJK PATROON</div>', unsafe_allow_html=True)
    st.title(f"Waar zitten de {area_label} met de grootste afwijking?")
    st.write(
        f"De kaart kleurt op afwijking van de regressielijn. Rood/oranje markeert een lagere WOZ dan verwacht; "
        f"blauw markeert een hogere WOZ. De puntgrootte laat de relatieve nabijheidsscore per {analysis_level.lower()} zien."
    )
    map_min = map_data[map_column].min()
    map_max = map_data[map_column].max()
    if map_column == "WOZ_residu":
        map_limit = max(abs(map_min), abs(map_max), 1)
        map_min = -map_limit
        map_max = map_limit
    elif map_min == map_max:
        map_max = map_min + 1

    color_map = LinearColormap(
        colors=COLORS,
        vmin=map_min,
        vmax=map_max,
        caption=map_measure,
    )
    folium_map = folium.Map(
        location=[52.15, 5.35],
        zoom_start=7,
        control_scale=True,
    )
    marker_data = []
    for row in map_data.itertuples(index=False):
        value = getattr(row, map_column)
        if map_column == "Nabijheidsscore":
            value_label = f"{value:.1f} punten"
        else:
            value_label = f"€ {value:,.0f}".replace(",", ".")
        popup_text = (
            f"<strong>{getattr(row, area_name_column)}</strong><br>"
            f"{area_code_column}: {getattr(row, area_code_column)}<br>"
            f"{map_measure}: {value_label}<br>"
            f"WOZ {woz_year}: € {getattr(row, woz_column):,.0f}<br>"
            f"Modelverwachting: € {row.WOZ_voorspeld:,.0f}<br>"
            f"Nabijheidsscore: {row.Nabijheidsscore:.1f}<br>"
            f"Bevolkingsdichtheid: {getattr(row, density_column):,.0f} inwoners/km²"
        ).replace(",", ".")
        marker_data.append(
            [
                row.Latitude,
                row.Longitude,
                color_map(value),
                f"{getattr(row, area_name_column)} · {map_measure}: {value_label}",
                popup_text,
                4 + row.Nabijheidsscore / 30,
            ]
        )
    marker_callback = """
    function (row) {
        var marker = L.circleMarker([row[0], row[1]], {
            radius: row[5],
            color: row[2],
            fillColor: row[2],
            fillOpacity: 0.85,
            weight: 1
        });
        marker.bindTooltip(row[3]);
        marker.bindPopup(row[4]);
        return marker;
    }
    """
    FastMarkerCluster(
        data=marker_data,
        callback=marker_callback,
        options={"maxClusterRadius": 35, "disableClusteringAtZoom": 11},
        name=area_label.capitalize(),
        control=False,
    ).add_to(folium_map)
    color_map.add_to(folium_map)
    st_folium(
        folium_map,
        height=620,
        width=None,
        use_container_width=True,
        returned_objects=[],
        key=f"{analysis_level.lower()}_residual_map",
    )
    st.caption(
        f"De kaart gebruikt centroiden van {area_label}. Afwijking = werkelijke WOZ − modelverwachting."
    )

    ranking_data = analysis_data
    if is_neighborhood and map_municipality != "Alle gemeenten":
        ranking_data = ranking_data.loc[ranking_data["GemeenteNaam"].eq(map_municipality)]
    low_residuals = ranking_data.nsmallest(top_count, "WOZ_residu").copy()
    high_residuals = ranking_data.nlargest(top_count, "WOZ_residu").copy()
    residual_examples = pd.concat([low_residuals, high_residuals]).drop_duplicates(area_code_column)
    residual_figure = px.bar(
        residual_examples.sort_values("WOZ_residu"),
        x="WOZ_residu",
        y=area_name_column,
        orientation="h",
        color="WOZ_residu",
        color_continuous_scale=COLORS,
        color_continuous_midpoint=0,
        hover_data={"Nabijheidsscore": ":.1f", woz_column: ":,.0f", "WOZ_voorspeld": ":,.0f"},
        labels={"WOZ_residu": "Afwijking (€)", area_name_column: analysis_level},
    )
    residual_figure.add_vline(x=0, line_color=INK, line_width=1)
    residual_figure.update_layout(
        height=620,
        margin={"l": 12, "r": 20, "t": 25, "b": 30},
        coloraxis_colorbar={"title": "Afwijking (€)"},
        yaxis={"categoryorder": "total ascending"},
    )
    st.subheader(f"{analysis_level}en met de grootste afwijking" if is_neighborhood else "Gemeenten met de grootste afwijking")
    st.plotly_chart(residual_figure, width="stretch")
    st.caption(f"Links van nul zijn {area_label} waar de WOZ lager ligt dan op basis van de score wordt verwacht.")

with facilities_tab:
    st.markdown('<div class="eyebrow">CASE 7B / WAT ONDERSCHEIDT ZE?</div>', unsafe_allow_html=True)
    st.title(f"Voorzieningen en context per {analysis_level.lower()}")
    st.write(
        f"De samengestelde score geeft één relatieve maat per {analysis_level.lower()}. "
        "Hieronder zie je ook de zes afstanden los, zodat een gemiddelde score geen verschil tussen voorzieningen verbergt."
    )

    service_summary = pd.DataFrame(
        {
            "Voorziening": [
                name for name, column in facility_columns.items() if column in selected_columns
            ],
            "Gemiddelde afstand (km)": [analysis_data[column].mean() for column in selected_columns],
        }
    ).sort_values("Gemiddelde afstand (km)")
    service_figure = px.bar(
        service_summary,
        x="Gemiddelde afstand (km)",
        y="Voorziening",
        orientation="h",
        color="Gemiddelde afstand (km)",
        color_continuous_scale=[TEAL, BLUE],
            labels={
                "Gemiddelde afstand (km)": (
                    "Buurt-afstand (km)" if is_neighborhood else "Gemiddelde buurt-afstand per gemeente (km)"
                )
            },
    )
    service_figure.update_layout(
        height=390,
        coloraxis_showscale=False,
        margin={"l": 12, "r": 20, "t": 25, "b": 30},
    )
    st.plotly_chart(service_figure, width="stretch")
    st.caption(
        "Elke buurt weegt hier gelijk; dit is geen inwonergewogen gemiddelde."
        if is_neighborhood
        else "Elke gemeente weegt hier gelijk; dit is geen inwonergewogen gemiddelde."
    )

    density_panel, distribution_panel = st.columns([1.1, 1])
    with density_panel:
        st.subheader("Context: dichtheid en WOZ-afwijking")
        density_figure = px.scatter(
            analysis_data,
            x=density_column,
            y="WOZ_residu",
            color="Nabijheidsgroep",
            color_discrete_map=quartile_colors,
            hover_name=area_name_column,
            hover_data={
                address_density_column: ":,.0f",
                "Nabijheidsscore": ":.1f",
                woz_column: ":,.0f",
            },
            labels={
                density_column: f"Inwoners per km² · {2024 if is_neighborhood else 2026}",
                "WOZ_residu": "WOZ-afwijking (€)",
                "Nabijheidsgroep": "Nabijheidsgroep",
            },
        )
        density_figure.update_xaxes(type="log")
        density_figure.add_hline(y=0, line_color=INK, line_width=1)
        density_figure.update_layout(
            height=430,
            margin={"l": 12, "r": 20, "t": 25, "b": 35},
            coloraxis_colorbar={"title": "WOZ-afwijking (€)"},
        )
        st.plotly_chart(density_figure, width="stretch")
        density_rank = analysis_data[density_column].rank(method="average")
        residual_rank = analysis_data["WOZ_residu"].rank(method="average")
        density_correlation = density_rank.corr(residual_rank)
        st.caption(
            f"Spearman ρ tussen bevolkingsdichtheid en WOZ-afwijking per {analysis_level.lower()}: "
            f"{density_correlation:.2f}. "
            "Dichtheid is context, geen verklaring op zichzelf; de x-as is logaritmisch."
        )

    with distribution_panel:
        st.subheader("Hoe breed is de residuverdeling?")
        residual_histogram = px.histogram(
            analysis_data,
            x="WOZ_residu",
            nbins=24,
            color_discrete_sequence=[TEAL],
            labels={"WOZ_residu": "Werkelijke WOZ − modelverwachting (€)"},
        )
        residual_histogram.add_vline(x=0, line_color=INK, line_width=2)
        residual_histogram.update_layout(
            height=430,
            margin={"l": 12, "r": 20, "t": 25, "b": 35},
            yaxis_title=f"Aantal {area_label}",
            showlegend=False,
        )
        st.plotly_chart(residual_histogram, width="stretch")
        st.caption(f"De verticale nul-lijn is de modelverwachting; negatieve uitschieters zijn de richting-B-kandidaten.")

with method_tab:
    st.markdown('<div class="eyebrow">CASE 7B / DATA & METHODE</div>', unsafe_allow_html=True)
    st.title("Van CBS-codes naar een controleerbare vergelijking")
    st.write(
        "De CBS-tabellen bevatten codes in plaats van bruikbare namen. De codeboeken zijn toegepast vóór de koppeling; "
        "WOZ is op BU-code gekoppeld aan voorzieningen en lokale kaartpunten."
    )

    source_columns = st.columns(4)
    source_details = [
        (
            "Voorzieningen · 86270NED",
            "Afstanden per buurt in 2025. BU-codes opgeschoond en via het buurtcodeboek aan WOZ-codes gekoppeld.",
        ),
        (
            "WOZ per buurt · 85984NED",
            "Kerncijfers 2024. WOZ in duizenden euro’s; vermenigvuldigd met 1.000 vóór analyse.",
        ),
        (
            "Buurtcodeboek · 85984NED",
            "WijkenEnBuurten vertaalt BU-code naar buurtnaam en GM-code; de join is many-to-one gevalideerd.",
        ),
        (
            "Kaart · CBS/PDOK 2025",
            "Buurtgeometrieën op BU-code; vereenvoudigd tot centroiden en lokaal opgeslagen voor de kaart.",
        ),
    ]
    for column, (source_title, source_text) in zip(source_columns, source_details):
        with column:
            st.markdown(f"**{source_title}**")
            st.write(source_text)

    method_metrics = st.columns(4)
    method_metrics[0].metric(
        f"{analysis_level}codes",
        f"{source_data[area_code_column].nunique():,}".replace(",", "."),
    )
    method_metrics[1].metric(
        "WOZ gekoppeld",
        f"{analysis_data[area_code_column].nunique():,}".replace(",", "."),
    )
    method_metrics[2].metric(
        "WOZ ontbreekt",
        f"{source_data[woz_column].isna().sum():,}".replace(",", "."),
    )
    method_metrics[3].metric(
        "Kaartpunten",
        f"{map_data[area_code_column].nunique():,}".replace(",", "."),
    )

    st.subheader("Hoe is de afgeleide nabijheidsscore gemaakt?")
    st.write(
          f"Voor elke geselecteerde voorziening rangschikken we {area_label} op afstand. "
        "De kortste afstand krijgt de hoogste percentielrang; het gemiddelde van die rangen × 100 "
          "is de nabijheidsscore. Daardoor weegt elk gekozen type voorziening even zwaar. "
          "De score wordt binnen het gekozen geografische niveau berekend."
    )
    st.code(
        'rangen = afstanden.rank(pct=True, ascending=False)\n'
        'data["Nabijheidsscore"] = rangen.mean(axis=1) * 100',
        language="python",
    )
    st.write(
        "Het lineaire model voorspelt WOZ uit deze score. Het residu is: werkelijke WOZ − voorspelde WOZ. "
        "Een negatief residu betekent dus lager dan het model verwacht, niet automatisch ‘goedkoop’ of ‘betaalbaar’."
    )
    if is_neighborhood:
        missing_woz = source_data[woz_column].isna().sum()
        total_neighborhoods = source_data[area_code_column].nunique()
        st.info(
            f"Beperkingen: {missing_woz:,} van de {total_neighborhoods:,} voorzieningenbuurten "
            "missen WOZ en vallen uit de regressie; voorzieningen zijn uit 2025 en WOZ uit 2024. "
            "Buurten krijgen geen inwonersweging. Het model bevat geen woningtype, inkomen of andere verklarende factoren. "
            "Een negatief residu is geen bewijs dat voorzieningen WOZ veroorzaken."
            .replace(",", ".")
        )
    else:
        st.info(
            "Gemeentelijke WOZ is een alternatieve aggregatie; buurtverschillen vallen daarin weg. "
            "Voorzieningen zijn buurtgemiddelden en geen inwonergewogen gemeentelijke afstanden."
        )

    with st.expander("Bekijk een CBS-bronbestand"):
        source_files = {
            "Nabijheid voorzieningen · 2025": RAW_FOLDER / "86270NED" / "TypedDataSet.csv",
            "Kerncijfers wijken en buurten · 2024 (buurt-WOZ)": RAW_FOLDER / "85984NED" / "TypedDataSet.csv",
            "Kerncijfers wijken en buurten · 2026": RAW_FOLDER / "86358NED" / "TypedDataSet.csv",
            "WOZ-waarde per regio en jaar · gemeente": RAW_FOLDER / "85036NED" / "TypedDataSet.csv",
        }
        selected_source = st.selectbox("CBS-bron", list(source_files))
        source_path = source_files[selected_source]
        if source_path.exists():
            source_data = load_raw_data(str(source_path))
            st.caption(
                f"{len(source_data):,} rijen · {len(source_data.columns)} kolommen".replace(",", ".")
            )
            st.dataframe(source_data.head(100), width="stretch", hide_index=True)
        else:
            st.info("Dit bronbestand is nog niet opgehaald.")
        if show_raw_data:
            st.dataframe(data, width="stretch", hide_index=True)

    st.download_button(
        f"Download analyse per {analysis_level.lower()} als CSV",
        analysis_data.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{area_label}_voorzieningen_woz_{woz_year}.csv",
        mime="text/csv",
    )
