# Global Vaccination Dashboard (Streamlit + Neon)

Connects live to the Neon PostgreSQL database and reproduces the dashboard
requirements from the project report: KPI indicators, a geographic heatmap,
trend lines/bar charts, a coverage-vs-incidence scatter plot, and vaccine
introduction/schedule tables — with sidebar filters (year range, WHO region,
antigen, disease) that re-run live SQL queries against Neon on every change.

## Files

- `app.py` — the whole dashboard
- `requirements.txt` — Python dependencies
- `.streamlit/secrets.toml.example` — template only, shows the format for the Neon connection string (never commit a real one)
- `.gitignore` — keeps a real `secrets.toml` out of git if you ever create one locally

## Deploy on Streamlit Community Cloud (no local machine needed)

1. **Create a GitHub repo** (public or private) and add these files to it.
   - Easiest with no git installed locally: on github.com, create a new repo,
     then use "Add file -> Upload files" and drag in `app.py`, `requirements.txt`,
     `.gitignore`, and the `.streamlit/secrets.toml.example` file.
   - Do **not** upload a real `secrets.toml` with your actual Neon password in it.

2. **Go to** [share.streamlit.io](https://share.streamlit.io) -> **New app**.
   - Connect your GitHub account if you haven't already.
   - Select the repo, branch (usually `main`), and `app.py` as the entry point.
   - Click **Deploy**. It will fail on first boot — that's expected, because
     secrets haven't been added yet.

3. **Add your real secret**: in the app's page on Streamlit Cloud, go to
   **Settings -> Secrets**, paste:
   ```toml
   [neon]
   connection_string = "postgresql://<user>:<password>@<host>/<dbname>?sslmode=require"
   ```
   using your actual Neon connection string (from the Neon console ->
   your project -> Connection Details), then **Save**. The app redeploys
   automatically and should come up working.

4. Every time you push a change to the GitHub repo, Streamlit Cloud
   redeploys automatically — no separate hosting step needed.

## Notes

- Neon's free-tier compute scales to zero after 5 minutes idle — the first
  query after a period of inactivity may take a couple of seconds longer
  while it wakes up. Normal, not a bug.
- All queries are cached for 10 minutes (`st.cache_data(ttl=600)`) to avoid
  re-hitting Neon on every widget tweak within that window — adjust `ttl`
  in `app.py` if you want fresher/staler data.
- The scatter tab depends on `dim_antigen_disease_map` having an entry for
  the selected disease — not every disease in `dim_disease` has a mapped
  antigen (e.g. mumps, typhoid have limited/no vaccine-coverage tracking in
  this dataset), so some disease selections will show "no data" by design.
