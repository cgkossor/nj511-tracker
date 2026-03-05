import argparse
import webbrowser
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timezone
import analysis

CATEGORY_COLORS = {
    "Incident": "#e74c3c",
    "Congestion": "#e67e22",
    "Construction": "#f39c12",
    "Weather": "#3498db",
    "Special Event": "#9b59b6",
    "Planned": "#95a5a6",
}

DIR_COLORS = {"Northbound": "#3498db", "Southbound": "#e67e22"}


def hour_labels(hours):
    return [analysis.format_hour_label(h) for h in hours]


def build_report(days=30, db_path=None):
    df = analysis.load_events(days=days, db_path=db_path)
    if df.empty:
        return "<html><body><h1>No data found</h1></body></html>"

    now_et = analysis.to_et(datetime.now(timezone.utc))
    generated = analysis.format_datetime(now_et)
    figs = []

    # ============================================================
    # OVERVIEW
    # ============================================================

    # 1. Events by Category
    by_cat = analysis.events_by_category(df)
    if not by_cat.empty:
        fig = go.Figure(go.Bar(
            x=by_cat["category"], y=by_cat["events"],
            marker_color=[CATEGORY_COLORS.get(c, "#888") for c in by_cat["category"]],
            text=by_cat["events"], textposition="auto",
        ))
        fig.update_layout(title="Events by Category", yaxis_title="Events", height=400)
        figs.append(("Overview", fig))

    # 2. All Events by Hour (stacked by category)
    cat_hour = analysis.category_by_time_of_day(df)
    if not cat_hour.empty:
        fig = go.Figure()
        for cat in sorted(df["category"].unique()):
            subset = cat_hour[cat_hour["category"] == cat]
            fig.add_trace(go.Bar(
                x=hour_labels(subset["hour"]), y=subset["events"],
                name=cat, marker_color=CATEGORY_COLORS.get(cat, "#888"),
            ))
        fig.update_layout(title="All Events by Hour of Day (ET)", barmode="stack",
                          xaxis_title="Hour (ET)", yaxis_title="Events", height=450)
        figs.append(("Overview", fig))

    # 3. Section Severity Ranking (stacked by category)
    severity = analysis.severity_ranking(df, top_n=15)
    if not severity.empty:
        fig = go.Figure()
        sections_ordered = severity.groupby("section")["events"].sum().sort_values(ascending=True).index.tolist()
        for cat in sorted(severity["category"].unique()):
            subset = severity[severity["category"] == cat]
            fig.add_trace(go.Bar(
                y=subset["section"], x=subset["events"], name=cat,
                orientation="h", marker_color=CATEGORY_COLORS.get(cat, "#888"),
            ))
        fig.update_layout(title="Section Severity Ranking (All Categories)",
                          barmode="stack", height=550, margin=dict(l=130),
                          yaxis=dict(categoryorder="array", categoryarray=sections_ordered),
                          xaxis_title="Total Events")
        figs.append(("Overview", fig))

    # ============================================================
    # INCIDENT ANALYSIS
    # ============================================================

    # 4. Incident Hotspots
    inc_hot = analysis.incident_hotspots(df, top_n=15)
    if not inc_hot.empty:
        fig = go.Figure(go.Bar(
            y=inc_hot["section"], x=inc_hot["events"],
            orientation="h", marker_color="#e74c3c",
            text=inc_hot["events"], textposition="auto",
        ))
        fig.update_layout(title="Incident Hotspots", yaxis=dict(autorange="reversed"),
                          xaxis_title="Incidents", height=500, margin=dict(l=130))
        figs.append(("Incident Analysis", fig))

    # 5. Incident vs Congestion Correlation (scatter)
    corr = analysis.incident_congestion_correlation(df)
    if not corr.empty and len(corr) > 1:
        fig = go.Figure(go.Scatter(
            x=corr["incidents"], y=corr["congestion"],
            mode="markers+text", text=corr["section"],
            textposition="top center", textfont=dict(size=9),
            marker=dict(size=10, color="#e74c3c"),
        ))
        fig.update_layout(title="Incident vs Congestion Correlation by Section",
                          xaxis_title="Incident Count", yaxis_title="Congestion Count",
                          height=500)
        figs.append(("Incident Analysis", fig))

    # 6. Incident-Congestion Time Overlap
    overlap = analysis.concurrent_events(df)
    if not overlap.empty:
        fig = go.Figure(go.Bar(
            y=overlap.head(15)["section"], x=overlap.head(15)["overlaps"],
            orientation="h", marker_color="#c0392b",
            text=overlap.head(15)["overlaps"], textposition="auto",
        ))
        fig.update_layout(title="Sections with Simultaneous Incidents + Congestion",
                          yaxis=dict(autorange="reversed"),
                          xaxis_title="Overlapping Event Pairs", height=450, margin=dict(l=130))
        figs.append(("Incident Analysis", fig))

    # ============================================================
    # CONGESTION ANALYSIS
    # ============================================================

    # 7. Congestion Hotspots
    cong_worst = analysis.worst_sections(df, top_n=15, category="Congestion")
    if not cong_worst.empty:
        fig = go.Figure(go.Bar(
            y=cong_worst["section"], x=cong_worst["events"],
            orientation="h", marker_color="#e67e22",
            text=cong_worst["events"], textposition="auto",
        ))
        fig.update_layout(title="Most Congested Sections", yaxis=dict(autorange="reversed"),
                          xaxis_title="Congestion Events", height=500, margin=dict(l=130))
        figs.append(("Congestion Analysis", fig))

    # 8. Congestion NB vs SB by Hour
    dir_time = analysis.direction_by_time_of_day(df, category="Congestion")
    if not dir_time.empty:
        fig = go.Figure()
        for direction in ["Northbound", "Southbound"]:
            subset = dir_time[dir_time["direction"] == direction]
            fig.add_trace(go.Bar(
                x=hour_labels(subset["hour"]), y=subset["events"],
                name=direction, marker_color=DIR_COLORS[direction],
            ))
        fig.update_layout(title="Congestion by Hour (NB vs SB, ET)", barmode="group",
                          xaxis_title="Hour (ET)", yaxis_title="Events", height=400)
        figs.append(("Congestion Analysis", fig))

    # 9. Commute Comparison
    commute = analysis.commute_comparison(df)
    if not commute.empty:
        fig = make_subplots(rows=1, cols=2, subplot_titles=("Event Count", "Avg Duration (min)"))
        for direction in ["Northbound", "Southbound"]:
            subset = commute[commute["direction"] == direction]
            fig.add_trace(go.Bar(x=subset["period"], y=subset["events"], name=direction,
                                 marker_color=DIR_COLORS[direction], showlegend=True), row=1, col=1)
            fig.add_trace(go.Bar(x=subset["period"], y=subset["avg_duration_min"], name=direction,
                                 marker_color=DIR_COLORS[direction], showlegend=False), row=1, col=2)
        fig.update_layout(title="Commute Comparison: Morning vs Evening (Congestion)", barmode="group", height=400)
        figs.append(("Congestion Analysis", fig))

    # 10. Day of Week (Congestion)
    dow = analysis.day_of_week_patterns(df, category="Congestion")
    if not dow.empty:
        fig = go.Figure()
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for direction in ["Northbound", "Southbound"]:
            subset = dow[dow["direction"] == direction]
            fig.add_trace(go.Bar(x=subset["dow_name"], y=subset["events"], name=direction,
                                 marker_color=DIR_COLORS[direction]))
        fig.update_layout(title="Congestion by Day of Week", barmode="group",
                          xaxis=dict(categoryorder="array", categoryarray=day_order),
                          yaxis_title="Events", height=400)
        figs.append(("Congestion Analysis", fig))

    # ============================================================
    # TRENDS & PATTERNS
    # ============================================================

    # 11. Peak Hours Heatmap (all events)
    heatmap = analysis.peak_hours_heatmap(df)
    if not heatmap.empty:
        fig = go.Figure(go.Heatmap(
            z=heatmap.values,
            x=heatmap.columns.tolist(),
            y=[analysis.format_hour_label(h) for h in heatmap.index.tolist()],
            colorscale="YlOrRd", text=heatmap.values.astype(int), texttemplate="%{text}",
        ))
        fig.update_layout(title="Peak Hours Heatmap (All Events, ET)",
                          xaxis_title="Day", yaxis_title="Hour (ET)", height=550,
                          yaxis=dict(dtick=1))
        figs.append(("Trends & Patterns", fig))

    # 12. Weekly Trend by Category
    trend_cat = analysis.weekly_trend_by_category(df)
    if not trend_cat.empty:
        fig = go.Figure()
        for cat in sorted(trend_cat["category"].unique()):
            subset = trend_cat[trend_cat["category"] == cat]
            fig.add_trace(go.Scatter(
                x=subset["week"], y=subset["events"], mode="lines+markers",
                name=cat, marker_color=CATEGORY_COLORS.get(cat, "#888"),
                line=dict(width=2),
            ))
        fig.update_layout(title="Weekly Trend by Category",
                          xaxis_title="Week", yaxis_title="Events", height=400)
        figs.append(("Trends & Patterns", fig))

    # 13. Duration Distribution (Congestion)
    cong_durations = df[(df["category"] == "Congestion") & (df["duration_min"] > 0)]["duration_min"]
    if not cong_durations.empty:
        fig = go.Figure(go.Histogram(x=cong_durations, nbinsx=30, marker_color="#9b59b6"))
        fig.update_layout(title="Congestion Duration Distribution",
                          xaxis_title="Duration (minutes)", yaxis_title="Count", height=350)
        figs.append(("Trends & Patterns", fig))

    # --- Build HTML with sections ---
    sections = {}
    for section_name, fig in figs:
        sections.setdefault(section_name, []).append(fig)

    chart_html = ""
    for section_name, section_figs in sections.items():
        chart_html += f'<h2 style="margin-top:50px;color:#2c3e50;border-bottom:2px solid #eee;padding-bottom:10px;">{section_name}</h2>\n'
        for fig in section_figs:
            chart_html += f'<div style="margin-bottom:40px;">{fig.to_html(full_html=False, include_plotlyjs=False)}</div>\n'

    html = f"""\
<!DOCTYPE html>
<html>
<head>
<title>GSP Traffic Analysis Report</title>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<style>
  body {{ font-family: sans-serif; max-width: 1100px; margin: 0 auto; padding: 20px; background: #fafafa; }}
  h1 {{ color: #2c3e50; }}
  .meta {{ color: #888; margin-bottom: 30px; }}
</style>
</head>
<body>
<h1>GSP Traffic Analysis Report</h1>
<p class="meta">Generated {generated} | Last {days} days | {len(df)} events across {df['category'].nunique()} categories</p>
{chart_html}
</body>
</html>
"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Generate GSP traffic analysis report")
    parser.add_argument("--days", type=int, default=30, help="Number of days to include (default: 30)")
    parser.add_argument("--db", type=str, default=None, help="Path to DB (default: from config)")
    parser.add_argument("--output", type=str, default="gsp_report.html", help="Output HTML file")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open in browser")
    args = parser.parse_args()

    html = build_report(days=args.days, db_path=args.db)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report saved to {args.output}")

    if not args.no_open:
        webbrowser.open(f"file://{os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()
