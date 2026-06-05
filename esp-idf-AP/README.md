ESP-IDF Kit installieren

in den Ordner `esp-idf-AP` navigieren

esp-idf aktivieren
. $HOME/esp/esp-idf/export.sh

Modell wählen
idf.py set-target esp32s3
# oder
idf.py set-target esp32c5

flashen
idf.py build flash -p <PORT>

AP kann abgesteckt werden und startet automatisch bei Stromanfall.
