import glob
import os

import numpy as np
import pandas as pd


def parse_uwb_file(filepath):
    try:
        df = pd.read_csv(filepath, sep=";")
        if df.empty:
            return None
        gt_m = df["True_Range_cm"].iloc[0] / 100.0
        df_clean = pd.DataFrame(
            {
                "Ground_Truth": np.round(gt_m, 2),
                "Messwert": df["Rohwert_cm"] / 100.0,
                "Konfiguration": "UWB_Referenz",
            }
        )
        return df_clean
    except Exception as e:
        print(f"Fehler beim Lesen von UWB-Datei {filepath}: {e}")
        return None


def parse_wifi_file(filepath, config_name):
    try:
        df = pd.read_csv(filepath)
        if df.empty:
            return None
        gt_m = df["TrueRange_m"].iloc[0]
        df_clean = pd.DataFrame(
            {
                "Ground_Truth": np.round(gt_m, 2),
                "Messwert": df["Raw_m"],
                "Konfiguration": config_name,
            }
        )
        return df_clean
    except Exception as e:
        print(f"Fehler beim Lesen von WiFi-Datei {filepath}: {e}")
        return None


def main():
    base_dir = "./Daten"
    uwb_folder = "uwb"
    all_data_list = []

    uwb_files = glob.glob(os.path.join(base_dir, uwb_folder, "*.csv"))
    for f in uwb_files:
        parsed = parse_uwb_file(f)
        if parsed is not None:
            all_data_list.append(parsed)

    wifi_folders = [
        d
        for d in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, d))
        and d != uwb_folder
        and not d.startswith(".")
    ]

    for config in wifi_folders:
        wifi_files = glob.glob(os.path.join(base_dir, config, "*.csv"))
        for f in wifi_files:
            parsed = parse_wifi_file(f, config)
            if parsed is not None:
                all_data_list.append(parsed)

    if not all_data_list:
        raise FileNotFoundError("Keine gültigen Messdaten in den Ordnern gefunden.")

    df_all = pd.concat(all_data_list, ignore_index=True)
    df_all["Fehler"] = df_all["Messwert"] - df_all["Ground_Truth"]

    unique_configs = sorted(df_all["Konfiguration"].unique())

    print(
        f"{'Konfiguration':<20} | {'StdDev [m]':<12} | {'IQR Spanne [m]':<15} | {'90% Spanne [m]':<15}"
    )

    rauschen_summary = []

    for config in unique_configs:
        df_sub = df_all[df_all["Konfiguration"] == config]
        errors = df_sub["Fehler"]

        std_dev = np.std(errors)
        iqr = np.percentile(errors, 75) - np.percentile(errors, 25)
        spanne_90 = np.percentile(errors, 95) - np.percentile(errors, 5)

        print(
            f"{config:<20} | {std_dev:.4f}       | {iqr:.4f}          | {spanne_90:.4f}"
        )

        rauschen_summary.append(
            {
                "Konfiguration": config,
                "Globale_StdDev_m": np.round(std_dev, 4),
                "Globale_Spanne_IQR_m": np.round(iqr, 4),
                "Globale_Spanne_90_m": np.round(spanne_90, 4),
            }
        )


if __name__ == "__main__":
    main()
