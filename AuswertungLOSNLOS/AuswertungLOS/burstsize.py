import os

import pandas as pd


def berechne_erfolgsquote(hauptordner):
    daten = []

    for eintrag in os.listdir(hauptordner):
        ordner_pfad = os.path.join(hauptordner, eintrag)

        if os.path.isdir(ordner_pfad):
            gesamt_success = 0
            gesamt_burst = 0

            for datei in os.listdir(ordner_pfad):
                if datei.endswith(".csv"):
                    datei_pfad = os.path.join(ordner_pfad, datei)
                    try:
                        df = pd.read_csv(datei_pfad)

                        spalten_lower = {c.lower(): c for c in df.columns}

                        col_success = None
                        for s in ["succseses", "successes", "succses", "success"]:
                            if s in spalten_lower:
                                col_success = spalten_lower[s]
                                break

                        col_burst = spalten_lower.get("burst")

                        if col_success and col_burst:
                            success_werte = pd.to_numeric(
                                df[col_success], errors="coerce"
                            ).fillna(0)
                            burst_werte = pd.to_numeric(
                                df[col_burst], errors="coerce"
                            ).fillna(0)

                            burst_werte = burst_werte.apply(
                                lambda x: x - 2 if x == 16 else x
                            )

                            gesamt_success += success_werte.sum()
                            gesamt_burst += burst_werte.sum()
                    except Exception as e:
                        print(f"Fehler beim Lesen von {datei_pfad}: {e}")

            quote = (gesamt_success / gesamt_burst * 100) if gesamt_burst > 0 else 0.0

            daten.append(
                {
                    "Ordner": eintrag,
                    "Gesamt Burst": int(gesamt_burst),
                    "Gesamt Erfolgreich": int(gesamt_success),
                    "Erfolgsquote (%)": round(quote, 2),
                }
            )

    df_ergebnis = pd.DataFrame(daten)
    print(df_ergebnis.to_string(index=False))


berechne_erfolgsquote("./vorcalib")
