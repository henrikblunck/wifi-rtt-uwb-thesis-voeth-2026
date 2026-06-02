#!/usr/bin/env python3

# python3 regression.py <los|nlos> <ordner_pfad>

import os
import sys

import matplotlib.pyplot as plt
import numpy
import pandas as pd
import seaborn as sns
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def train_mlr(csv_file_paths, env_type):
    print(
        f"Lese Daten aus {len(csv_file_paths)} Dateien für Umgebung: {env_type.upper()}"
    )

    df_list = []
    required_cols = ["TrueRange_m", "Filtered_m", "FTM_RSSI_dBm", "Variance_m2"]

    for file_path in csv_file_paths:
        if not os.path.isfile(file_path):
            print(f"Fehler: Datei nicht gefunden -> {file_path}")
            continue

        try:
            df = pd.read_csv(file_path, skipinitialspace=True)
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                print(f"Ueberspringe {file_path}: Fehlende Spalten {missing_cols}")
                continue

            df_list.append(df)
            print(f" -> {file_path} erfolgreich geladen ({len(df)} Zeilen).")
        except Exception as e:
            print(f"Fehler beim Lesen von {file_path}: {e}")

    if not df_list:
        print(
            "\nKritischer Fehler: Keine gueltigen CSV-Dateien konnten geladen werden."
        )
        sys.exit(1)

    df_master = pd.concat(df_list, ignore_index=True)
    df_clean = df_master[
        (df_master["Filtered_m"] > 0.0) & (df_master["TrueRange_m"] > 0.0)
    ].dropna(subset=required_cols)

    if df_clean.empty:
        print(
            "Kritischer Fehler: Keine gueltigen Trainingsdaten nach Bereinigung uebrig."
        )
        sys.exit(1)

    X = df_clean[["Filtered_m", "FTM_RSSI_dBm", "Variance_m2"]]
    y = df_clean["TrueRange_m"]

    model = LinearRegression()
    model = Ridge(alpha=50.0)
    model.fit(X, y)

    y_pred = model.predict(X)

    mae = mean_absolute_error(y, y_pred)
    mse = mean_squared_error(y, y_pred)
    r2 = r2_score(y, y_pred)

    # Berechnung adjustierten Bestimmtheitsmass
    n = len(df_clean)
    p = X.shape[1]
    r2_adj = 1 - ((1 - r2) * (n - 1) / (n - p - 1))

    mae_raw = mean_absolute_error(y, df_clean["Filtered_m"])

    print("\n========================================")
    print(f" MODELL EVALUIERUNG: {env_type.upper()}")
    print("========================================")
    print(f"Verwendete Samples:    {len(df_clean)} von {len(df_master)} (aggregiert)")
    print(f"R2 Score:              {r2:.4f} (Perfekt = 1.0)")
    print(f"R2 Score (adjustiert): {r2_adj:.4f}")
    print(f"MAE (Rohdaten):        {mae_raw:.4f} m")
    print(f"MAE (Kalibriert):      {mae:.4f} m")
    print(f"Verbesserung:          {(mae_raw - mae):.4f} m")

    beta_0 = model.intercept_
    beta_raw = model.coef_[0]
    beta_rssi = model.coef_[1]
    beta_var = model.coef_[2]

    struct_name = "mlr_los" if env_type.lower() == "los" else "mlr_nlos"

    plt.figure(figsize=(14, 6))

    print(f"    .beta_0    = {beta_0:8.4f}f,")
    print(f"    .beta_raw  = {beta_raw:8.4f}f,")
    print(f"    .beta_rssi = {beta_rssi:8.4f}f,")
    print(f"    .beta_var  = {beta_var:8.4f}f,")

    plt.subplot(1, 2, 1)
    plt.scatter(
        df_clean["TrueRange_m"],
        df_clean["Filtered_m"],
        alpha=0.3,
        label="Rohdaten (Unkorrigiert)",
        color="blue",
    )
    plt.scatter(
        df_clean["TrueRange_m"],
        y_pred,
        alpha=0.5,
        label="MLR (Kalibriert)",
        color="green",
    )

    min_dist = df_clean["TrueRange_m"].min()
    max_dist = df_clean["TrueRange_m"].max()
    plt.plot(
        [min_dist, max_dist],
        [min_dist, max_dist],
        "r--",
        label="Ideallinie (Ground Truth)",
    )

    plt.title(f"Distanz-Regression: {env_type.upper()}")
    plt.xlabel("Reale Distanz [m]")
    plt.ylabel("Gemessene/Berechnete Distanz [m]")
    plt.legend()
    plt.grid(True, linestyle=":", alpha=0.7)

    # Subplot 2: Fehlerverteilung (Residuals)
    plt.subplot(1, 2, 2)
    error_raw = df_clean["Filtered_m"] - df_clean["TrueRange_m"]
    error_mlr = y_pred - df_clean["TrueRange_m"]

    sns.kdeplot(
        error_raw,
        label=f"Fehler Rohdaten (MAE: {mae_raw:.2f}m)",
        fill=True,
        color="blue",
        alpha=0.3,
    )
    sns.kdeplot(
        error_mlr,
        label=f"Fehler MLR (MAE: {mae:.2f}m)",
        fill=True,
        color="green",
        alpha=0.5,
    )
    plt.axvline(0, color="black", linestyle="--", linewidth=1)

    plt.title("Fehlerverteilung (Residuals)")
    plt.xlabel("Abweichung von der realen Distanz [m]")
    plt.ylabel("Dichte")
    plt.legend()
    plt.grid(True, linestyle=":", alpha=0.7)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Verwendung: python regression.py <los|nlos> <ordner_pfad>")
        sys.exit(1)

    env_arg = sys.argv[1]
    folder_path = sys.argv[2]

    if env_arg.lower() not in ["los", "nlos"]:
        print("Fehler: Das erste Argument muss zwingend 'los' oder 'nlos' sein.")
        sys.exit(1)

    if not os.path.isdir(folder_path):
        print(f"Fehler: Ordner nicht gefunden -> {folder_path}")
        sys.exit(1)

    files = [
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if f.lower().endswith(".csv")
    ]

    if not files:
        print(f"Fehler: Keine CSV-Dateien im Ordner '{folder_path}' gefunden.")
        sys.exit(1)

    train_mlr(files, env_arg)
