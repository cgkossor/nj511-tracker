import argparse
import webbrowser
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import analysis


def build_report(days=30, db_path=None):
    df = analysis.load_events(days=days, db_path=db_path)
    if df.empty:
        return "<html><body><h1>No congestion data found</h1></body></html>"

    figs = []

    # 1. Worst Sections Bar Chart
    worst = analysis.worst_sections(df, top_n=15)
    if not worst.empty:
        fig = go.Figure(go.Bar(
            y=worst["section"], x=worst["events"],
            orientation="h", marker_color="#e74c3c",
            text=worst["events"], textposition="auto",
        ))
        fig.update_layout(title="Most Congested Sections", yaxis=dict(autorange="reversed"),
                          xaxis_title="Number of Events", height=500, margin=dict(l=120))
        figs.append(fig)

    # 2. Direction x Time of Day
    dir_time = analysis.direction_by_time_of_day(df)
    if not dir_time.empty:
        fig = go.Figure()
        for direction in ["Northbound", "Southbound"]:
            subset = dir_time[dir_time["direction"] == direction]
            color = "#3498db" if direction == "Northbound" else "#e67e22"
            fig.add_trace(go.Bar(x=subset["hour"], y=subset["events"], name=direction, marker_color=color))
        fig.update_layout(title="Congestion by Hour of Day (NB vs SB)", barmode="group",
                          xaxis_title="Hour", yaxis_title="Events", height=400)
        figs.append(fig)

    # 3. Commute Comparison
    commute = analysis.commute_comparison(df)
    if not commute.empty:
        fig = make_subplots(rows=1, cols=2, subplot_titles=("Event Count", "Avg Duration (min)"))
        colors = {"Northbound": "#3498db", "Southbound": "#e67e22"}
        for direction in ["Northbound", "Southbound"]:
            subset = commute[commute["direction"] == direction]
            fig.add_trace(go.Bar(x=subset["period"], y=subset["events"], name=direction,
                                 marker_color=colors[direction], showlegend=True), row=1, col=1)
            fig.add_trace(go.Bar(x=subset["period"], y=subset["avg_duration_min"], name=direction,
                                 marker_color=colors[direction], showlegend=False), row=1, col=2)
        fig.update_layout(title="Commute Comparison: Morning vs Evening", barmode="group", height=400)
        figs.append(fig)

    # 4. Day of Week Patterns
    dow = analysis.day_of_week_patterns(df)
    if not dow.empty:
        fig = go.Figure()
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for direction in ["Northbound", "Southbound"]:
            subset = dow[dow["direction"] == direction]
            color = "#3498db" if direction == "Northbound" else "#e67e22"
            fig.add_trace(go.Bar(x=subset["dow_name"], y=subset["events"], name=direction, marker_color=color))
        fig.update_layout(title="Congestion by Day of Week", barmode="group",
                          xaxis=dict(categoryorder="array", categoryarray=day_order),
                          yaxis_title="Events", height=400)
        figs.append(fig)

    # 5. Peak Hours Heatmap
    heatmap = analysis.peak_hours_heatmap(df)
    if not heatmap.empty:
        fig = go.Figure(go.Heatmap(
            z=heatmap.values, x=heatmap.columns.tolist(), y=heatmap.index.tolist(),
            colorscale="YlOrRd", text=heatmap.values.astype(int), texttemplate="%{text}",
        ))
        fig.update_layout(title="Peak Hours Heatmap (Hour x Day of Week)",
                          xaxis_title="Day", yaxis_title="Hour", height=500,
                          yaxis=dict(dtick=1))
        figs.append(fig)

    # 6. Weekly Trend
    trend = analysis.weekly_trend(df)
    if not trend.empty:
        fig = go.Figure(go.Scatter(
            x=trend["week"], y=trend["events"], mode="lines+markers",
            marker_color="#2ecc71", line=dict(width=3),
        ))
        fig.update_layout(title="Weekly Congestion Trend", xaxis_title="Week",
                          yaxis_title="Events", height=350)
        figs.append(fig)

    # 7. Duration Distribution
    durations = df[df["duration_min"] > 0]["duration_min"]
    if not durations.empty:
        fig = go.Figure(go.Histogram(x=durations, nbinsx=30, marker_color="#9b59b6"))
        fig.update_layout(title="Congestion Duration Distribution",
                          xaxis_title="Duration (minutes)", yaxis_title="Count", height=350)
        figs.append(fig)

    # Build HTML
    chart_html = "\n".join(
        f'<div style="margin-bottom:40px;">{fig.to_html(full_html=False, include_plotlyjs=False)}</div>'
        for fig in figs
    )

    from datetime import datetime
    html = f"""\
<!DOCTYPE html>
<html>
<head>
<title>GSP Congestion Report</title>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<style>
  body {{ font-family: sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; background: #fafafa; }}
  h1 {{ color: #2c3e50; }}
  .meta {{ color: #888; margin-bottom: 30px; }}
</style>
</head>
<body>
<h1>GSP Congestion Trend Report</h1>
<p class="meta">Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')} | Last {days} days | {len(df)} events</p>
{chart_html}
</body>
</html>
"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Generate GSP congestion trend report")
    parser.add_argument("--days", type=int, default=30, help="Number of days to include (default: 30)")
    parser.add_argument("--db", type=str, default=None, help="Path to congestion DB (default: from config)")
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
