"""
Driver Performance Clustering — KMeans se drivers ko automatically
categorize karta hai based on Total KM, Avg KM/Day, aur Avg Efficiency.

Categories: "🟢 Top Performer", "🔵 Consistent", "🟠 Needs Attention"
(cluster centers ke overall-score ke hisaab se label assign hoti hai,
isliye label hamesha meaningful rehta hai chahe data kaisa bhi ho).
"""

import pandas as pd

MIN_DRIVERS_FOR_CLUSTERING = 3  # itne drivers na ho to clustering meaningless hai


def cluster_drivers(driver_perf: pd.DataFrame) -> pd.DataFrame:
    """driver_perf: columns Driver, Total_KM, Avg_KM_Day, Days, Avg_Efficiency, Income
    Returns same DataFrame + ek naya "Category" column."""
    if driver_perf.empty or len(driver_perf) < MIN_DRIVERS_FOR_CLUSTERING:
        out = driver_perf.copy()
        out["Category"] = "—"
        return out

    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        out = driver_perf.copy()
        out["Category"] = "—"
        return out

    features = driver_perf[["Total_KM", "Avg_KM_Day", "Avg_Efficiency"]].fillna(0)
    scaled = StandardScaler().fit_transform(features)

    n_clusters = min(3, len(driver_perf))
    km = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
    labels = km.fit_predict(scaled)

    # Har cluster ka "overall score" nikal ke rank karo — taaki label hamesha
    # meaningful ho (jo cluster ka avg sabse zyada hai wahi "Top Performer")
    out = driver_perf.copy()
    out["_cluster"] = labels
    cluster_scores = out.groupby("_cluster")[["Total_KM", "Avg_Efficiency"]].mean()
    cluster_scores["score"] = cluster_scores["Total_KM"].rank() + cluster_scores["Avg_Efficiency"].rank()
    ranked_clusters = cluster_scores.sort_values("score", ascending=False).index.tolist()

    label_map = {}
    category_names = ["🟢 Top Performer", "🔵 Consistent", "🟠 Needs Attention"]
    for i, cluster_id in enumerate(ranked_clusters):
        label_map[cluster_id] = category_names[i] if i < len(category_names) else f"Group {i+1}"

    out["Category"] = out["_cluster"].map(label_map)
    out = out.drop(columns=["_cluster"])
    return out
