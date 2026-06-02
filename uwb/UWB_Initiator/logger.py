import csv
import time

import serial

SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200
datei_name = ""
ANZAHL = 200
count = 0

eingabe = input("Bitte geben Sie die wahre Distanz (True Range) in m ein: ")
try:
    true_range = float(eingabe.replace(",", "."))
except ValueError:
    print("Ungültige Eingabe. Skript wird beendet.")
    exit(1)

try:
    datei_name = eingabe + ".csv"
    eingabe = eingabe * 100
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)
    print(f"Logging gestartet... Speichere in {datei_name}")

    with open(datei_name, mode="w", newline="") as file:
        writer = csv.writer(file, delimiter=";")

        # Erweiterter Header
        writer.writerow(
            [
                "Zeitstempel_ms",
                "True_Range_cm",
                "Rohwert_cm",
                "Wert_mit_Offset_cm",
                "SMA_ohne_Offset_cm",
                "SMA_mit_Offset_cm",
            ]
        )

        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode("utf-8").strip()
                parts = line.split(";")

                # Prüfen der Länge der Übertragenen Daten
                if len(parts) == 5:
                    # True Range an Index 1 einfügen
                    row = [parts[0], true_range, parts[1], parts[2], parts[3], parts[4]]
                    writer.writerow(row)
                    file.flush()
                    count = count + 1
                    print(f"Gespeichert:{count} {row}")
                    if count == ANZAHL:
                        break

except KeyboardInterrupt:
    print("\nLogging durch Nutzer beendet.")
finally:
    if "ser" in locals():
        ser.close()
