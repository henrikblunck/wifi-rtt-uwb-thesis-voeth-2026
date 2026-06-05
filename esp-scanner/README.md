ESP-IDF Kit installieren

in den Ordner `esp-scanner` navigieren

esp-idf aktivieren
. $HOME/esp/esp-idf/export.sh

Modell wählen
idf.py set-target esp32s3
# oder
idf.py set-target esp32c5

flashen
idf.py build flash -p <PORT>

in den Ordner main navigieren
cd main

Logger starten
python3 startlogger.py
