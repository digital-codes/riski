#!/usr/bin/env python3
"""
Cluster & distribution analysis for pgvector embeddings using ONLY common packages:
- numpy, pandas, sqlalchemy, scikit-learn, matplotlib

Pipeline:
1) Load embeddings from Postgres
2) L2-normalize (good default for embeddings)
3) PCA -> 50D for clustering (fast + denoise)
4) OPTICS clustering (unknown number of clusters)
5) PCA -> 2D for plotting
6) Basic cluster summaries + filename token hints

Install (Fedora-ish):
  python3 -m pip install numpy pandas sqlalchemy psycopg2-binary scikit-learn matplotlib
(or use dnf packages if you prefer)
"""

from __future__ import annotations

import os
import re
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text, event
from pgvector.psycopg2 import register_vector

import matplotlib.pyplot as plt

from sklearn.preprocessing import normalize
from sklearn.decomposition import PCA
from sklearn.cluster import OPTICS, DBSCAN, Birch
from sklearn.metrics.pairwise import cosine_distances

import os
os.environ.setdefault("OMP_NUM_THREADS", "8")        # 0 lets runtime decide (often all cores)
os.environ.setdefault("OPENBLAS_NUM_THREADS", "8")
os.environ.setdefault("MKL_NUM_THREADS", "8")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "8")


def parse_filename_meta(name: str) -> dict:
    name2 = str(name).replace("\\", "/")
    parts = name2.split("/")
    filename = parts[-1] if parts else name2
    folder = parts[-2] if len(parts) >= 2 else ""
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    stem = ".".join(filename.split(".")[:-1]) if "." in filename else filename
    m = re.split(r"[_\-]", stem, maxsplit=1)
    prefix = m[0] if m else stem
    return {"folder": folder, "filename": filename, "extension": ext, "stem": stem, "prefix": prefix}


def top_tokens(stems: pd.Series, k: int = 10) -> list[str]:
    # simple tokenization without extra deps
    counts = {}
    for s in stems.astype(str).values:
        for tok in re.findall(r"[A-Za-z0-9_]+", s):
            if len(tok) < 3:
                continue
            counts[tok] = counts.get(tok, 0) + 1
    return [t for t, _ in sorted(counts.items(), key=lambda x: -x[1])[:k]]


def load_df(table: str, limit: int = 0) -> tuple[pd.DataFrame, np.ndarray]:
    import private as pr
    engine = create_engine(f"postgresql+psycopg2://{pr.PG_USER}:{pr.PG_PWD}@{pr.DB_HOST}/{pr.PG_NAME}")

    @event.listens_for(engine, "connect")
    def _register_pgvector(dbapi_connection, connection_record):
        register_vector(dbapi_connection)

    lim = f" LIMIT {int(limit)}" if limit and limit > 0 else ""
    sql = text(f"SELECT id, name, value FROM {table}{lim}")
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)

    if df.empty:
        raise SystemExit("0 rows returned. Check DSN/table/permissions.")

    X = np.vstack(df["value"].values).astype(np.float32, copy=False)
    df = df.drop(columns=["value"])
    return df, X


def distance_histogram(X: np.ndarray, outpath: Path, sample_n: int = 2000) -> None:
    n = min(sample_n, len(X))
    if n < 2:
        return
    idx = np.random.choice(len(X), n, replace=False)
    D = cosine_distances(X[idx])
    plt.figure(figsize=(10, 6))
    plt.hist(D.ravel(), bins=120)
    plt.title(f"Pairwise cosine distance (sample n={n})")
    plt.xlabel("distance")
    plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(outpath, dpi=160)
    plt.close()


def plot_2d(X2: np.ndarray, labels: np.ndarray, outpath: Path, title: str) -> None:
    plt.figure(figsize=(10, 8))
    plt.scatter(X2[:, 0], X2[:, 1], c=labels, s=5, cmap="Spectral")
    plt.title(title)
    plt.xlabel("PC1")
    plt.ylabel("PC2")
    plt.tight_layout()
    plt.savefig(outpath, dpi=180)
    plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default="embeddings")
    ap.add_argument("--limit", type=int, default=0)

    ap.add_argument("--outdir", default="out_embeddings_sklearn")
    ap.add_argument("--pca-dim", type=int, default=50, help="PCA dims for clustering")
    ap.add_argument("--pca-seed", type=int, default=42)

    # OPTICS params (recommended)
    ap.add_argument("--method", choices=["optics", "dbscan", "birch"], default="optics")
    ap.add_argument("--min-samples", type=int, default=20, help="OPTICS/DBSCAN: neighborhood size")
    ap.add_argument("--xi", type=float, default=0.05, help="OPTICS: smaller => more clusters")
    ap.add_argument("--min-cluster-size", type=int, default=50, help="OPTICS: minimum cluster size")

    # DBSCAN param
    ap.add_argument("--eps", type=float, default=0.25, help="DBSCAN eps (on PCA space)")

    # Birch param
    ap.add_argument("--threshold", type=float, default=0.5, help="Birch threshold (smaller => more clusters)")

    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    print("Loading embeddings...")
    df, X = load_df(args.table, args.limit)
    print(f"Rows={len(df)} dim={X.shape[1]}")

    # filename metadata
    meta = df["name"].apply(parse_filename_meta).apply(pd.Series)
    df = pd.concat([df, meta], axis=1)

    print("Normalize (L2)...")
    Xn = normalize(X)  # cosine-friendly

    print("Distance distribution...")
    distance_histogram(Xn, outdir / "distance_hist.png")

    print(f"PCA -> {args.pca_dim}D for clustering...")
    pca = PCA(n_components=args.pca_dim, random_state=args.pca_seed)
    Xc = pca.fit_transform(Xn)
    print(f"Explained variance (sum): {pca.explained_variance_ratio_.sum():.3f}")

    print(f"Clustering method: {args.method}")
    if args.method == "optics":
        # OPTICS finds clusters without pre-setting number; good default for unknown cluster count.
        model = OPTICS(
            min_samples=args.min_samples,
            xi=args.xi,
            min_cluster_size=args.min_cluster_size,
            metric="euclidean",
            cluster_method="xi",
            n_jobs=-1,
        )
        labels = model.fit_predict(Xc)

    elif args.method == "dbscan":
        model = DBSCAN(
            eps=args.eps,
            min_samples=args.min_samples,
            metric="euclidean",
            n_jobs=-1,
        )
        labels = model.fit_predict(Xc)

    else:  # birch
        model = Birch(
            threshold=args.threshold,
            n_clusters=None,  # let it form as many as needed
        )
        labels = model.fit_predict(Xc)

    df["cluster"] = labels.astype(np.int32)


    # 2D PCA for plotting
    print("PCA -> 2D for plot...")
    pca2 = PCA(n_components=2, random_state=args.pca_seed)
    X2 = pca2.fit_transform(Xn)
    plot_2d(X2, labels, outdir / "pca_clusters.png", f"PCA(2D) + {args.method.upper()} clusters")

    outliers = df[X2[:,0] > 0.45]
    print("Outliers:",outliers["name"].head(50))


    # Save outputs
    out_csv = outdir / "clusters.csv"
    df_out = df[["id", "name", "folder", "filename", "extension", "prefix", "cluster"]].copy()
    df_out["pca2_x"] = X2[:, 0].astype(np.float32)
    df_out["pca2_y"] = X2[:, 1].astype(np.float32)
    df_out.to_csv(out_csv, index=False)
    print(f"Wrote: {out_csv}")
    print(f"Wrote: {outdir / 'distance_hist.png'}")
    print(f"Wrote: {outdir / 'pca_clusters.png'}")

    # Summary
    sizes = df["cluster"].value_counts()
    n_noise = int((df["cluster"] == -1).sum())
    print("\n--- summary ---")
    print(f"clusters (excl -1): {(sizes.index != -1).sum()}")
    print(f"noise (-1): {n_noise} ({n_noise / len(df):.2%})")
    print("\nTop 15 cluster sizes:")
    print(sizes.head(15))

    print("\n--- cluster token hints (from filenames) ---")
    for c in sizes.index[:15]:
        if c == -1:
            continue
        sub = df[df["cluster"] == c]
        toks = top_tokens(sub["stem"], k=10)
        print(f"cluster {c:>4} (n={len(sub):>5}): {toks}")

    print("\n--- sample filenames from largest clusters ---")
    for c in sizes.index[:8]:
        if c == -1:
            continue
        sub = df[df["cluster"] == c]
        print(f"\ncluster {c} (n={len(sub)}):")
        print(sub["name"].sample(min(12, len(sub)), random_state=0).tolist())


if __name__ == "__main__":
    main()
    
