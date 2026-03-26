"""Quick check: replicate the digest numbers from the local DB copy."""
import analysis

df = analysis.load_events(days=7)
print(f"Total events (last 7 days): {len(df)}")
print(f"Date range: {df['date'].min()} to {df['date'].max()}")
print()

# Category summary
cat = analysis.events_by_category(df)
print("=== Week Summary by Category ===")
for _, r in cat.iterrows():
    print(f"  {r['category']:20s}  {r['events']:3d} events   avg {r['avg_duration_min']:.0f} min")
print()

# Busiest day
day_counts = df.groupby("date").size()
print(f"Busiest day: {day_counts.idxmax()} ({day_counts.max()} events)")
print()

# Incident hotspots
print("=== Top Incident Hotspots ===")
inc = analysis.incident_hotspots(df, top_n=5)
for _, r in inc.iterrows():
    print(f"  {r['section']:20s}  {r['events']} incidents")
print()

# Congestion hotspots
print("=== Top Congestion Hotspots ===")
cong = analysis.worst_sections(df, top_n=5, category="Congestion")
for _, r in cong.iterrows():
    print(f"  {r['section']:20s}  {r['events']} events   avg {r['avg_duration_min']:.0f} min")
