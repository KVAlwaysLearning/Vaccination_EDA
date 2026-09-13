"""
Global Vaccination Dashboard
-----------------------------
Connects live to the Neon PostgreSQL database (migrated from vaccination.db)
and answers the same visual requirements as the Power BI plan:
  - KPI indicators
  - Geographical heatmap
  - Trend lines / bar charts
  - Scatter plot (coverage vs. incidence)
  - Vaccine introduction / schedule view
All queries run live against Neon on every filter change - nothing is pre-exported.
"""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text, bindparam
import plotly.express as px

st.set_page_config(page_title="Global Vaccination Dashboard", layout="wide")

# ------------------------------------------------------------------
# Connection (cached so it's reused across reruns, not reopened every click)
# ------------------------------------------------------------------
@st.cache_resource
def get_engine():
    conn_str = st.secrets["neon"]["connection_string"]
    return create_engine(conn_str, pool_pre_ping=True)

engine = get_engine()


@st.cache_data(ttl=600)
def run_query(sql, params=None, expanding_params=None):
    """
    sql: raw SQL string
    params: dict of scalar bind params, e.g. {"antigen": "MCV1"}
    expanding_params: list of bind-param names that are lists (for IN clauses)
    """
    stmt = text(sql)
    if expanding_params:
        stmt = stmt.bindparams(*[bindparam(p, expanding=True) for p in expanding_params])
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn, params=params or {})


# ------------------------------------------------------------------
# Sidebar filters (shared across all tabs)
# ------------------------------------------------------------------
st.sidebar.title("Filters")

years_df = run_query("SELECT DISTINCT year FROM pbi_coverage ORDER BY year;")
all_years = years_df["year"].tolist()
year_range = st.sidebar.slider(
    "Year range", min_value=min(all_years), max_value=max(all_years),
    value=(max(all_years) - 10, max(all_years))
)

regions_df = run_query(
    "SELECT DISTINCT who_region_name FROM pbi_coverage WHERE who_region_name IS NOT NULL ORDER BY 1;"
)
all_regions = regions_df["who_region_name"].tolist()
selected_regions = st.sidebar.multiselect("WHO Region", all_regions, default=all_regions)

antigens_df = run_query(
    "SELECT DISTINCT antigen_code, antigen_description FROM dim_antigen ORDER BY 1;"
)
antigen_choice = st.sidebar.selectbox(
    "Antigen (coverage views)", antigens_df["antigen_code"],
    format_func=lambda code: f"{code} — {antigens_df.set_index('antigen_code').loc[code, 'antigen_description']}"
)

diseases_df = run_query(
    "SELECT DISTINCT disease_code, disease_description FROM dim_disease ORDER BY 1;"
)
disease_choice = st.sidebar.selectbox(
    "Disease (incidence/scatter views)", diseases_df["disease_code"],
    format_func=lambda code: f"{code} — {diseases_df.set_index('disease_code').loc[code, 'disease_description']}"
)

st.sidebar.caption("Filters apply live — every chart re-queries Neon on change.")
st.sidebar.caption("Query results are cached for 10 minutes. If you've just updated data in Neon and want it reflected immediately, use the button below.")
if st.sidebar.button("🔄 Refresh data now"):
    st.cache_data.clear()
    st.rerun()

# Guard against an empty region selection breaking the IN clause
region_param = selected_regions if selected_regions else all_regions

st.title("🌍 Global Vaccination Coverage & Disease Trends")

tab_overview, tab_map, tab_trends, tab_scatter, tab_intro = st.tabs(
    ["KPI Overview", "Geographic Heatmap", "Trends", "Coverage vs Incidence", "Vaccine Introduction"]
)

# ------------------------------------------------------------------
# TAB 1 — KPI overview
# ------------------------------------------------------------------
with tab_overview:
    st.subheader("Key indicators")

    kpi_df = run_query(
        """
        SELECT year, AVG(avg_coverage) AS avg_coverage,
               SUM(total_cases) AS total_cases,
               AVG(avg_incidence_rate) AS avg_incidence
        FROM pbi_country_year_summary
        WHERE who_region_name IN :regions
          AND year BETWEEN :year_from AND :year_to
        GROUP BY year ORDER BY year;
        """,
        params={"regions": tuple(region_param), "year_from": year_range[0], "year_to": year_range[1]},
        expanding_params=["regions"],
    )

    if not kpi_df.empty:
        latest = kpi_df.iloc[-1]
        col1, col2, col3 = st.columns(3)
        col1.metric("Avg coverage (latest year in range)", f"{latest['avg_coverage']:.1f}%")
        col2.metric("Total reported cases (latest year)", f"{int(latest['total_cases']):,}")
        col3.metric("Gap to 95% measles target", f"{95 - latest['avg_coverage']:.1f} pp")

        st.line_chart(kpi_df.set_index("year")[["avg_coverage"]], height=300)
    else:
        st.info("No data for the current filter selection.")

# ------------------------------------------------------------------
# TAB 2 — Geographic heatmap
# ------------------------------------------------------------------
with tab_map:
    st.subheader(f"{antigen_choice} coverage by country — {year_range[1]}")

    map_df = run_query(
        """
        SELECT country_code, country_name, coverage
        FROM pbi_coverage
        WHERE antigen_code = :antigen
          AND coverage_category = 'WUENIC'
          AND is_invalid = 0
          AND year = :year
          AND who_region_name IN :regions;
        """,
        params={"antigen": antigen_choice, "year": year_range[1], "regions": tuple(region_param)},
        expanding_params=["regions"],
    )

    if not map_df.empty:
        fig = px.choropleth(
            map_df, locations="country_code", locationmode="ISO-3",
            color="coverage", hover_name="country_name",
            color_continuous_scale="Blues", range_color=(0, 100),
            labels={"coverage": "Coverage (%)"},
        )
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No coverage data for this antigen/year/region combination.")

# ------------------------------------------------------------------
# TAB 3 — Trend lines / bar charts by region
# ------------------------------------------------------------------
with tab_trends:
    st.subheader("Trends over time by WHO region")

    trend_df = run_query(
        """
        SELECT who_region_name, year, avg_coverage, avg_incidence, total_cases
        FROM pbi_region_kpi
        WHERE who_region_name IN :regions
          AND year BETWEEN :year_from AND :year_to
        ORDER BY year;
        """,
        params={"regions": tuple(region_param), "year_from": year_range[0], "year_to": year_range[1]},
        expanding_params=["regions"],
    )

    if not trend_df.empty:
        fig1 = px.line(
            trend_df, x="year", y="avg_coverage", color="who_region_name",
            title="Average coverage over time", markers=True,
        )
        st.plotly_chart(fig1, use_container_width=True)

        fig2 = px.bar(
            trend_df, x="year", y="total_cases", color="who_region_name",
            title="Total reported cases over time", barmode="group",
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No trend data for the current filter selection.")

# ------------------------------------------------------------------
# TAB 4 — Scatter plot: coverage vs incidence
# ------------------------------------------------------------------
with tab_scatter:
    st.subheader(f"Coverage vs. incidence — {disease_choice}")

    scatter_df = run_query(
        """
        SELECT country_name, who_region_code, year, antigen_coverage, incidence_rate
        FROM pbi_coverage_vs_incidence
        WHERE disease_code = :disease
          AND year BETWEEN :year_from AND :year_to;
        """,
        params={"disease": disease_choice, "year_from": year_range[0], "year_to": year_range[1]},
    )

    if not scatter_df.empty:
        fig = px.scatter(
            scatter_df, x="antigen_coverage", y="incidence_rate",
            hover_name="country_name", color="who_region_code",
            trendline="ols",
            labels={"antigen_coverage": "Antigen coverage (%)", "incidence_rate": "Incidence rate"},
            title=f"{disease_choice}: coverage vs. incidence ({year_range[0]}–{year_range[1]})",
        )
        st.plotly_chart(fig, use_container_width=True)
        corr = scatter_df["antigen_coverage"].corr(scatter_df["incidence_rate"])
        st.caption(f"Pearson correlation: {corr:.3f}")
    else:
        st.info("No matching antigen-disease pair configured for this disease in dim_antigen_disease_map.")

# ------------------------------------------------------------------
# TAB 5 — Vaccine introduction & schedule
# ------------------------------------------------------------------
with tab_intro:
    st.subheader("Vaccine introduction status by region")

    intro_df = run_query(
        """
        SELECT who_region_name, vaccine_name, intro_status, COUNT(DISTINCT country_code) AS n_countries
        FROM pbi_vaccine_introduction
        WHERE who_region_name IN :regions
        GROUP BY who_region_name, vaccine_name, intro_status
        ORDER BY vaccine_name, who_region_name;
        """,
        params={"regions": tuple(region_param)},
        expanding_params=["regions"],
    )
    st.dataframe(intro_df, use_container_width=True, hide_index=True)

    st.subheader("National schedule detail (sample)")
    schedule_df = run_query(
        """
        SELECT country_name, vaccine_description, schedule_round, target_pop_description, age_administered
        FROM pbi_vaccine_schedule
        WHERE who_region_name IN :regions
        ORDER BY country_name
        LIMIT 500;
        """,
        params={"regions": tuple(region_param)},
        expanding_params=["regions"],
    )
    st.dataframe(schedule_df, use_container_width=True, hide_index=True)
