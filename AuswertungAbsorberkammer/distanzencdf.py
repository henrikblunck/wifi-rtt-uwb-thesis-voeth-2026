import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


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
                "Konfiguration": "UWB",
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

        parts = config_name.split("_")
        if len(parts) == 3:
            kanal, bandbreite, suffix = parts

            if kanal == "11":
                freq = "2,4GHz"
            elif kanal == "36":
                freq = "5GHz"
            else:
                freq = f"{kanal}GHz"

            suffix = "C5" if suffix == "c5" else "S3"
            bw = f"{bandbreite}MHz"
            pretty_config_name = f"{suffix} {freq} {bw}"
        else:
            pretty_config_name = config_name

        df_clean = pd.DataFrame(
            {
                "Ground_Truth": np.round(gt_m, 2),
                "Messwert": df["Raw_m"],
                "Konfiguration": pretty_config_name,
            }
        )
        return df_clean
    except Exception as e:
        print(f"Fehler beim Lesen von WiFi-Datei {filepath}: {e}")
        return None


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
df_all["Absoluter_Fehler"] = np.abs(df_all["Fehler"])

# Farb-Mapping definieren
unique_configs = sorted(df_all["Konfiguration"].unique())
palette = sns.color_palette("Set1", len(unique_configs))
color_map = {config: color for config, color in zip(unique_configs, palette)}
if "UWB_Referenz" in color_map:
    color_map["UWB_Referenz"] = "black"

os.makedirs("./Bilder", exist_ok=True)

plt.figure(figsize=(12, 6))

for config in unique_configs:
    df_sub = df_all[df_all["Konfiguration"] == config]

    perzentile_liste = [10, 25, 40, 50, 75, 90, 95, 100]
    werte = np.percentile(df_sub["Absoluter_Fehler"], perzentile_liste)
    perzentil_dict = dict(zip(perzentile_liste, werte))

    p10 = perzentil_dict[10]
    p90 = perzentil_dict[90]

    if p90 != p10:
        steigung = (0.9 - 0.1) / (p90 - p10)
    else:
        steigung = float("inf")

    print(f"\nKonfiguration: {config}")
    print(f"  Steigung (P10 bis P90): {steigung:.4f}")
    perzentil_str = " | ".join(
        [f"P{p}: {perzentil_dict[p]:.3f}m" for p in perzentile_liste]
    )
    print(f"  Perzentile: {perzentil_str}")

    linestyle = ":" if config == "UWB_Referenz" else "-"
    linewidth = 2 if config == "UWB_Referenz" else 1.5
    label_text = f"{config} (S: {steigung:.2f})"

    sns.ecdfplot(
        data=df_sub,
        x="Absoluter_Fehler",
        label=label_text,
        color=color_map[config],
        linestyle=linestyle,
        linewidth=linewidth,
    )

plt.xlabel("Absoluter Lokalisierungsfehler [m]")
plt.ylabel("Kumulierte Wahrscheinlichkeit")
plt.xlim(-0.1, 5)
plt.legend(fontsize="small", loc="lower right")
plt.grid(True, linestyle=":", alpha=0.6)
plt.savefig(
    "./Bilder/02_cdf_vergleich_konfigurationen.png", bbox_inches="tight", dpi=300
)
plt.close()
