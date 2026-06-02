import os

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# Erzeugt Abbildung 10 und Tabelle 2


def process_all_measurements(base_dir="Daten"):
    results = []

    if not os.path.exists(base_dir):
        print(f"Fehler: Der Ordner '{base_dir}' wurde nicht gefunden.")
        return pd.DataFrame()

    for folder_name in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder_name)

        if not os.path.isdir(folder_path):
            continue

        is_uwb = "uwb" in folder_name.lower()

        for file_name in os.listdir(folder_path):
            if not file_name.endswith(".csv"):
                continue

            file_path = os.path.join(folder_path, file_name)

            try:
                if is_uwb:
                    df = pd.read_csv(file_path, sep=";")
                    if df.empty:
                        continue

                    true_range = df["True_Range_cm"].iloc[0] / 100.0
                    mean_raw = (df["Rohwert_cm"] / 100.0).mean()
                    std_raw = (df["Rohwert_cm"] / 100.0).std()
                    offset = mean_raw - true_range

                    results.append(
                        {
                            "Technologie": "UWB",
                            "Chip": "UWB_Modul",
                            "Band": "UWB",
                            "Bandbreite_MHz": "UWB",
                            "Ordner": folder_name,
                            "Reale_Distanz_m": true_range,
                            "Gemessen_Mittel_m": mean_raw,
                            "Standardabweichung_m": std_raw,
                            "Offset_m": offset,
                        }
                    )

                else:
                    df = pd.read_csv(file_path, sep=",")
                    df_clean = df[df["Successes"] > 0]
                    if df_clean.empty:
                        continue

                    true_range = df_clean["TrueRange_m"].iloc[0]
                    mean_raw = df_clean["Raw_m"].mean()
                    std_raw = df_clean["Raw_m"].std()
                    offset = mean_raw - true_range

                    ch_mhz = df_clean["Ch_MHz"].iloc[0]
                    bw_mhz = df_clean["BW_MHz"].iloc[0]

                    chip = (
                        "S3"
                        if "s3" in folder_name.lower()
                        else "C5"
                        if "c5" in folder_name.lower()
                        else "Unbekannt"
                    )
                    band = "5 GHz" if ch_mhz > 4000 else "2.4 GHz"

                    results.append(
                        {
                            "Technologie": "WiFi RTT",
                            "Chip": f"ESP32-{chip}",
                            "Band": band,
                            "Bandbreite_MHz": f"{bw_mhz} MHz",
                            "Ordner": folder_name,
                            "Reale_Distanz_m": true_range,
                            "Gemessen_Mittel_m": mean_raw,
                            "Standardabweichung_m": std_raw,
                            "Offset_m": offset,
                        }
                    )
            except Exception as e:
                print(f"Fehler beim Verarbeiten von {file_path}: {e}")

    df_results = pd.DataFrame(results)

    if not df_results.empty:
        df_results.sort_values(
            by=["Technologie", "Chip", "Band", "Bandbreite_MHz", "Reale_Distanz_m"],
            inplace=True,
        )
        df_results.reset_index(drop=True, inplace=True)

    return df_results


def generate_evaluation_plot(df):
    if df.empty:
        print("Keine Daten für die Auswertung verfügbar.")
        return

    df_wifi = df[df["Technologie"] == "WiFi RTT"].copy()
    df_uwb = df[df["Technologie"] == "UWB"].copy()

    if not df_wifi.empty:
        df_wifi["Konfiguration"] = df_wifi["Chip"] + " | " + df_wifi["Band"]
        df_wifi["Bandbreite_MHz"] = df_wifi["Bandbreite_MHz"].astype(str)

    if not df_uwb.empty:
        df_uwb["Konfiguration"] = "UWB"
        df_uwb["Bandbreite_MHz"] = "UWB"

    df_plot = pd.concat([df_wifi, df_uwb], ignore_index=True)

    if not df_uwb.empty:
        print("\n--- UWB Rohdaten ---")
        uwb_cols = [
            "Konfiguration",
            "Reale_Distanz_m",
            "Offset_m",
            "Standardabweichung_m",
        ]
        ausgabe_cols_uwb = [col for col in uwb_cols if col in df_uwb.columns]
        print(
            df_uwb[ausgabe_cols_uwb]
            .sort_values(by="Reale_Distanz_m")
            .to_string(index=False)
        )

    if not df_plot.empty:
        summary_df = (
            df_plot.groupby(["Konfiguration", "Bandbreite_MHz"])["Offset_m"]
            .agg(Durchschnitt="mean", Min="min", Max="max")
            .reset_index()
        )

        summary_df["Spanne"] = summary_df["Max"] - summary_df["Min"]

        summary_df["Durchschnitt"] = summary_df["Durchschnitt"].round(4)
        summary_df["Min"] = summary_df["Min"].round(4)
        summary_df["Max"] = summary_df["Max"].round(4)
        summary_df["Spanne"] = summary_df["Spanne"].round(4)

        print(summary_df.to_string(index=False))

    sns.set_theme(style="whitegrid", context="talk")
    plt.rcParams.update({"figure.autolayout": True})

    os.makedirs("./Bilder", exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 6))
    sns.lineplot(
        data=df_plot,
        x="Reale_Distanz_m",
        y="Offset_m",
        hue="Konfiguration",
        style="Bandbreite_MHz",
        markers=True,
        dashes=False,
        linewidth=2.5,
        markersize=10,
        ax=ax,
    )
    ax.set_xlabel("Reale Distanz [m]")
    ax.set_ylabel("Hardware-Offset [m]")
    ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.savefig("./Bilder/01_Offset_Ueber_Distanz.png", bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    master_table = process_all_measurements("Daten")
    generate_evaluation_plot(master_table)
