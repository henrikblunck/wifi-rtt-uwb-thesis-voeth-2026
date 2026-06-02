#!/usr/bin/env python3

import glob
import os
import subprocess
import sys
import time
from datetime import datetime

# --- Farben für die Konsole ---
R = "\033[0m"
B = "\033[1m"
DIM = "\033[2m"
CY = "\033[96m"
GR = "\033[92m"
YL = "\033[93m"
RD = "\033[91m"
MG = "\033[95m"


def set_usb_permissions():
    try:
        if os.name != "nt":
            subprocess.run(["sudo", "chmod", "666", "/dev/ttyUSB0"], check=False)
    except:
        pass


set_usb_permissions()


def cls():
    os.system("cls" if os.name == "nt" else "clear")


def header():
    print("ESP32-S3  WiFi RTT  Logger  Launcher ")


LOGGER_BIN = os.path.join(os.path.dirname(__file__), "rtt_logger")
if os.name == "nt":
    LOGGER_BIN += ".exe"

BAUD = 115200


def ts():
    """Zeitstempel für Dateinamen."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def list_serial_ports():
    if os.name == "nt":
        import serial.tools.list_ports as lp

        try:
            return [p.device for p in lp.comports()]
        except ImportError:
            return [f"COM{i}" for i in range(1, 10)]
    else:
        return sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))


def pick_from_list(title, items, extra_hint=""):
    print(f"{B}{YL}{title}{R}")
    if extra_hint:
        print(f"  {DIM}{extra_hint}{R}")
    for i, item in enumerate(items):
        print(f"  {CY}{i + 1:2d}{R}  {item}")
    print()
    while True:
        try:
            raw = input(f"{GR}  Auswahl (1–{len(items)}): {R}").strip()
            idx = int(raw) - 1
            if 0 <= idx < len(items):
                return idx, items[idx]
        except (ValueError, KeyboardInterrupt):
            pass
        print(f"  {RD}Ungültige Eingabe.{R}")


# Änderung von Distanzvoreinstellungen
def ask_true_range():
    print(f"{B}{YL}Tatsächliche Distanz (True Range){R}")
    presets = ["0.5 m", "1.0 m", "2.0 m", "5.0 m", "10.0 m", "[Eigene Eingabe ...]"]
    preset_vals = [0.5, 1.0, 2.0, 5.0, 10.0, None]

    for i, p in enumerate(presets):
        print(f"  {CY}{i + 1:2d}{R}  {p}")

    while True:
        try:
            raw = input(f"\n{GR}  Auswahl: {R}").strip()
            idx = int(raw) - 1
            if 0 <= idx < len(presets):
                val = preset_vals[idx]
                if val is not None:
                    return val
                raw2 = input(f"{GR}  Distanz in Metern (z.B. 4.5): {R}").strip()
                return float(raw2.replace(",", "."))
        except ValueError:
            pass


def ask_max_requests():
    print(f"{B}{YL}Anzahl der Messungen (Limit){R}")
    print(f"  {DIM}0 = Unendlich{R}")
    while True:
        try:
            raw = input(f"{GR}  Limit (z.B. 100): {R}").strip()
            if not raw:
                return 0
            val = int(raw)
            if val >= 0:
                return val
        except ValueError:
            pass


def check_logger_binary():
    """Prüft ob der Logger kompiliert ist."""
    if not os.path.isfile(LOGGER_BIN):
        print(f"{RD}{B}Logger-Binary nicht gefunden:{R} {LOGGER_BIN}")
        print(f"\n{YL}Bitte zuerst kompilieren:{R}")
        print(f"  gcc -O2 -o rtt_logger rtt_logger.c -lm\n")
        return False
    return True


def main():
    cls()
    header()

    if not check_logger_binary():
        compile_now = input(f"{GR}Jetzt kompilieren? (j/n): {R}").strip().lower()
        if compile_now == "j":
            src = os.path.join(os.path.dirname(__file__), "rtt_logger.c")
            result = subprocess.run(
                ["gcc", "-O2", "-o", LOGGER_BIN, src, "-lm"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"{RD}Kompilierung fehlgeschlagen:\n{result.stderr}{R}")
                sys.exit(1)
            print(f"{GR}✓ Erfolgreich kompiliert.{R}\n")
        else:
            sys.exit(0)
    ports = list_serial_ports()
    if not ports:
        port = input(f"{RD}Kein Port gefunden. Manuell eingeben: {R}").strip()
    else:
        ports.append("[Manuell eingeben ...]")
        _, chosen = pick_from_list("Serieller Port wählen", ports)
        port = (
            input(f"{GR}  Port: {R}").strip()
            if chosen == "[Manuell eingeben ...]"
            else chosen
        )

    print()

    _, band = pick_from_list("WLAN Frequenzband", ["2.4GHz", "5GHz", "6GHz"])
    print()
    _, mhz = pick_from_list("Bandbreite (MHz)", ["20MHz", "40MHz", "80MHz", "160MHz"])
    print()

    true_range = ask_true_range()
    print()

    max_requests = ask_max_requests()
    print()

    date_str = ts()
    filename = f"rtt_{band}_{mhz}_dist-{true_range}m_{date_str}.csv"

    base_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(base_dir, "data")
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, filename)

    cls()
    header()
    print(f"{B}  Zusammenfassung{R}")
    print(f"  {DIM}{'─' * 46}{R}")
    print(f"  {YL}Port:        {R} {port}")
    print(f"  {YL}Frequenz:    {R} {band} / {mhz}")
    print(f"  {YL}True Range:  {R} {true_range} m")
    print(f"  {YL}Limit:       {R} {'Keines' if max_requests == 0 else max_requests}")
    print(f"  {YL}Datei:       {R} {filename}")
    print(f"  {DIM}{'─' * 46}{R}\n")

    if input(f"{GR}  Logger starten? (j/n): {R}").lower() != "j":
        sys.exit(0)

    print(f"\n{CY}  Warte 10 Sekunden vor dem Start...{R}")
    time.sleep(10)

    startzeit = time.time()
    cmd = [LOGGER_BIN, port, str(BAUD), csv_path, str(true_range), str(max_requests)]

    try:
        print(f"\n{CY}  Starte Messung... Beenden mit Ctrl+C{R}\n")
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass
    endzeit = time.time()
    dauer = endzeit - startzeit
    print(f"Fertig! Das Skript hat {dauer:.2f} Sekunden gebraucht.")
    print(f"\n{GR}  Fertig! Datei gespeichert unter:{R}")
    print(f"  {csv_path}")


if __name__ == "__main__":
    main()
