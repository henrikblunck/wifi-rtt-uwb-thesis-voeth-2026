import matplotlib.pyplot as plt
import pandas as pd

datei_name = "uwb_messung.csv"


def plot_uwb_data(file_path):
    try:
        df = pd.read_csv(file_path, sep=";")

        start_zeit = df["Zeitstempel_ms"].iloc[0]
        df["Zeit_s"] = (df["Zeitstempel_ms"] - start_zeit) / 1000.0

        plt.figure(figsize=(12, 8))

        if "True_Range_cm" in df.columns:
            plt.plot(
                df["Zeit_s"],
                df["True_Range_cm"],
                label="True Range (Referenz)",
                color="black",
                linewidth=2,
                linestyle=":",
            )

        plt.plot(
            df["Zeit_s"],
            df["Rohwert_cm"],
            label="Rohwert (cm)",
            color="orange",
            alpha=0.5,
            linestyle="--",
        )
        plt.plot(
            df["Zeit_s"],
            df["Wert_mit_Offset_cm"],
            label="Wert mit Offset (cm)",
            color="green",
            alpha=0.5,
            linestyle="--",
        )

        plt.plot(
            df["Zeit_s"],
            df["SMA_ohne_Offset_cm"],
            label="SMA ohne Offset (cm)",
            color="red",
            linewidth=1.5,
        )
        plt.plot(
            df["Zeit_s"],
            df["SMA_mit_Offset_cm"],
            label="SMA mit Offset (cm)",
            color="blue",
            linewidth=2,
        )

        plt.title("UWB Distanzmessung: Auswertung der Sensordaten")
        plt.xlabel("Zeit (Sekunden)")
        plt.ylabel("Distanz (cm)")
        plt.legend(loc="upper right")
        plt.grid(True, linestyle=":", alpha=0.7)

        plt.tight_layout()
        plt.show()

    except FileNotFoundError:
        print(f"Fehler: Die Datei '{file_path}' konnte nicht gefunden werden.")
        print(
            "Stellen Sie sicher, dass das Logger-Skript lief und die Datei im selben Ordner liegt."
        )
    except KeyError as e:
        print(f"Fehler: Spalte nicht gefunden. Stimmt das neue Header-Format? ({e})")
    except Exception as e:
        print(f"Unerwarteter Fehler: {e}")


if __name__ == "__main__":
    plot_uwb_data(datei_name)
