import glob
import os
import re
from ftplib import parse257

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def load_all_datasets(base_dir="."):
    all_data = []

    for folder in ["nachcalib"]:
        search_path = os.path.join(base_dir, folder, "**", "*.csv")
        file_list = glob.glob(search_path, recursive=True)

        for filepath in file_list:
            filename = os.path.basename(filepath)

            config_match = re.search(r"rtt_(.*?)_dist-", filename)
            if not config_match:
                continue
            freq_bw = config_match.group(1)

            filepath_lower = filepath.lower()
            if "c5" in filepath_lower:
                model_name = "C5"
            elif "s3" in filepath_lower:
                model_name = "S3"
            else:
                model_name = "Unknown"

            config_name = f"{model_name}_{freq_bw}"

            try:
                df = pd.read_csv(filepath, sep=",")
                df_clean = pd.DataFrame(
                    {
                        "config": config_name,
                        "dist_measured": df["Calibrated_m"],
                        "dist_real": df["TrueRange_m"],
                    }
                )
                all_data.append(df_clean)
            except Exception as e:
                print(f"Parsing-Fehler Wi-Fi ({filename}): {e}")

    uwb_files = []
    for ext in ["*.csv", "*.ucsv"]:
        uwb_files.extend(glob.glob(os.path.join(base_dir, "uwb", ext)))

    for filepath in uwb_files:
        filename = os.path.basename(filepath)
        try:
            df = pd.read_csv(filepath, sep=";")
            df_clean = pd.DataFrame(
                {
                    "config": "UWB",
                    "dist_measured": df["Rohwert_cm"] / 100.0,
                    "dist_real": df["True_Range_cm"],
                }
            )
            all_data.append(df_clean)
        except Exception as e:
            print(f"Parsing-Fehler UWB ({filename}): {e}")

    if not all_data:
        raise ValueError("Keine Daten gefunden. Bitte Verzeichnisse prüfen.")

    return pd.concat(all_data, ignore_index=True)


def plot_raw_cdf(df):
    df["error_raw"] = (df["dist_measured"] - df["dist_real"]).abs()

    output_dir = "./Bilder"
    os.makedirs(output_dir, exist_ok=True)

    plt.figure(figsize=(11, 7))

    configs = sorted(df["config"].unique(), key=lambda x: 1 if x == "UWB" else 0)

    for config in configs:
        config_df = df[df["config"] == config]
        errors = config_df["error_raw"].dropna().values

        if len(errors) == 0:
            continue

        p0 = np.percentile(errors, 0)
        p10 = np.percentile(errors, 10)
        p25 = np.percentile(errors, 25)
        p50 = np.percentile(errors, 50)
        p90 = np.percentile(errors, 90)
        p89 = np.percentile(errors, 89)
        p96 = np.percentile(errors, 96)
        p97 = np.percentile(errors, 97)
        p98 = np.percentile(errors, 98)
        p99 = np.percentile(errors, 99)
        p100 = np.percentile(errors, 100)

        x_sorted = np.sort(errors)
        x_sorted = np.insert(x_sorted, 0, 0.0)
        y_values = np.arange(0, len(x_sorted)) / (len(x_sorted) - 1)

        mask = x_sorted <= p90
        if np.sum(mask) > 1:
            slope, _ = np.polyfit(x_sorted[mask], y_values[mask], 1)
        else:
            slope = 0.0

        if p90 != p10:
            slope_10_90 = 0.8 / (p90 - p10)
        else:
            slope_10_90 = float("inf")

        print(f"Konfiguration: {config.replace('_', ' ')}")
        print(f"  -> Steigung (P10 bis P90):         {slope_10_90:6.3f} Delta-P/m")
        print(f"  -> 0% Perzentil (Minimum):         {p0:6.3f} m")
        print(f"  -> 10% Perzentil:                  {p10:6.3f} m")
        print(f"  -> 25% Perzentil:                  {p25:6.3f} m")
        print(f"  -> 50% Perzentil (Median):         {p50:6.3f} m")
        print(f"  -> 90% Perzentil (CE90):           {p90:6.3f} m")
        print(f"  -> 89% Perzentil:                  {p89:6.3f} m")
        print(f"  -> 96% Perzentil:                  {p96:6.3f} m")
        print(f"  -> 97% Perzentil:                  {p97:6.3f} m")
        print(f"  -> 98% Perzentil:                  {p98:6.3f} m")
        print(f"  -> 99% Perzentil:                  {p99:6.3f} m")
        print(f"  -> 100% Perzentil (Maximum):       {p100:6.3f} m")

        print("-" * 65)

        clean_label = config.replace("_", " ")

        if config == "UWB":
            linestyle = "--"
            linewidth = 2.5
            label_text = f"BENCHMARK: {clean_label} (S: {slope_10_90:.2f})"
            zorder = 10
            line_color = "black"
        else:
            linestyle = "-"
            linewidth = 2.0
            label_text = f"{clean_label} (S: {slope_10_90:.2f})"
            zorder = 2
            line_color = None

        plt.step(
            x_sorted,
            y_values,
            where="post",
            linestyle=linestyle,
            label=label_text,
            color=line_color,
            linewidth=linewidth,
            zorder=zorder,
        )

    # plt.title(
    #     "Empirische CDF des absoluten Lokalisierungsfehlers (nach Kalibrierung)",
    #     fontsize=12,
    #     fontweight="bold",
    #     pad=15,
    # )
    plt.xlabel("Absoluter Lokalisierungsfehler [m]", fontsize=11)
    plt.ylabel("Kumulierte Wahrscheinlichkeit", fontsize=11)

    plt.xlim(-0.05, 17)
    plt.ylim(0.0, 1.02)
    plt.grid(True, which="both", linestyle=":", alpha=0.6)
    plt.legend(loc="lower right", fontsize=9.0, framealpha=0.9)
    plt.tight_layout()

    output_filename = os.path.join(output_dir, "cdf_nlos_mitcalib.png")
    plt.savefig(output_filename, dpi=300)


if __name__ == "__main__":
    try:
        df_all = load_all_datasets(base_dir=".")

        plot_raw_cdf(df_all)
    except Exception as e:
        print(f"Kritischer Fehler während der Auswertung: {e}")
