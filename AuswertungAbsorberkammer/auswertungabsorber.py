import glob

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import linregress

csv_files = glob.glob("./Daten/11_20_s3/*.csv")
if not csv_files:
    csv_files = glob.glob("*.csv")
if not csv_files:
    raise ValueError("Keine CSV-Dateien gefunden. Bitte prüfe den Pfad.")

df_list = []
for file in csv_files:
    try:
        df_temp = pd.read_csv(file)
        df_temp.columns = df_temp.columns.str.strip()

        if "TrueRange_m" not in df_temp.columns:
            continue

        df_list.append(df_temp)
        # print(f"Datei geladen: {file} ({len(df_temp)} Zeilen)")
    except Exception as e:
        print(f"Fehler beim Laden von {file}: {e}")

if not df_list:
    raise ValueError("Es konnten keine gültigen RTT-Daten geladen werden.")

df = pd.concat(df_list, ignore_index=True)
initial_count = len(df)


# print("\n--- Datenbereinigung ---")
# Nur gültige Messungen
df = df[df["Raw_m"] > 0]


# Ausreißer Filter (IQR Methode) über Maske
def filter_iqr_mask(x):
    Q1 = x.quantile(0.25)
    Q3 = x.quantile(0.75)
    IQR = Q3 - Q1
    lower_bound = Q1 - 1.5 * IQR
    upper_bound = Q3 + 1.5 * IQR
    return (x >= lower_bound) & (x <= upper_bound)


mask = df.groupby(["TrueRange_m", "BW_MHz"])["Raw_m"].transform(filter_iqr_mask)
df_clean = df[mask.astype(bool)].copy()

# print(f"Daten bereinigt: {initial_count} -> {len(df_clean)} Zeilen\n")

stats = (
    df_clean.groupby(["TrueRange_m", "BW_MHz"])["Raw_m"]
    .agg(["mean", "std", "count"])
    .reset_index()
)
print(stats.to_string(index=False), "\n")

plt.figure(figsize=(14, 10))

ax1 = plt.subplot(2, 2, (1, 2))
sns.scatterplot(
    data=df_clean,
    x="TrueRange_m",
    y="Raw_m",
    hue="BW_MHz",
    alpha=0.1,
    palette="Set1",
    ax=ax1,
)

for bw in df_clean["BW_MHz"].unique():
    df_bw = df_clean[df_clean["BW_MHz"] == bw]
    means = df_bw.groupby("TrueRange_m")["Raw_m"].mean().reset_index()

    slope, intercept, r_value, p_value, std_err = linregress(
        means["TrueRange_m"], means["Raw_m"]
    )
    print(
        f"Regression für {bw} MHz: Steigung (m) = {slope:.4f}, Offset (b) = {intercept:.4f} m"
    )

    x_min, x_max = df_clean["TrueRange_m"].min(), df_clean["TrueRange_m"].max()
    x_vals = np.array([x_min, x_max])
    y_vals = intercept + slope * x_vals
    ax1.plot(
        x_vals,
        y_vals,
        label=f"Regression {bw}MHz (y={slope:.2f}x + {intercept:.2f})",
        linewidth=2,
    )

ax1.plot([x_min, x_max], [x_min, x_max], "k--", label="Ideal (y=x)", alpha=0.5)
ax1.set_title("Absorberkammer: Gemessene Distanz vs. Reale Distanz (Hardware Offset)")
ax1.set_xlabel("Reale Distanz [m]")
ax1.set_ylabel("Gemessene Distanz (Raw_m) [m]")
ax1.legend()
ax1.grid(True)

# --- PLOT 2: Boxplot / Jitter (Unten Links) ---
ax2 = plt.subplot(2, 2, 3)
sns.boxplot(
    data=df_clean, x="TrueRange_m", y="Raw_m", hue="BW_MHz", palette="Set2", ax=ax2
)
ax2.set_title("Varianz der Messwerte (Jitter)")
ax2.set_xlabel("Reale Distanz [m]")
ax2.set_ylabel("Gemessene Distanz [m]")
ax2.grid(True, axis="y", linestyle="--", alpha=0.7)

ax3 = plt.subplot(2, 2, 4)
sns.lineplot(
    data=stats,
    x="TrueRange_m",
    y="std",
    hue="BW_MHz",
    marker="o",
    palette="Set1",
    ax=ax3,
)
ax3.set_title("Systemrauschen (Standardabweichung)")
ax3.set_xlabel("Reale Distanz [m]")
ax3.set_ylabel("Standardabweichung [m]")
ax3.grid(True)
ax3.set_ylim(0, stats["std"].max() * 1.2)

plt.tight_layout()
plt.show()
