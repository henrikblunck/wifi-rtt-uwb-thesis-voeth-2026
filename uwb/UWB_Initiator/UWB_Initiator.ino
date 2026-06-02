/*
For ESP32S3 UWB AT Demo

Use 2.0.0   Wire
Use 1.11.7   Adafruit_GFX_Library
Use 1.14.4   Adafruit_BusIO
Use 2.0.0   SPI
Use 2.5.7   Adafruit_SSD1306
*/

// User config          ------------------------------------------
#define UWB_INDEX 0
#define TAG
#define UWB_TAG_COUNT 64
// User config end       ------------------------------------------

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Arduino.h>

#define SERIAL_LOG Serial
#define SERIAL_AT mySerial2

HardwareSerial SERIAL_AT(2);

#define RESET 16

#define IO_RXD2 18
#define IO_TXD2 17

#define I2C_SDA 39
#define I2C_SCL 38

// SMA Konfiguration
#define FILTER_GROESSE 10
float pufferRaw[FILTER_GROESSE];
float pufferOffset[FILTER_GROESSE];
int pufferIndex = 0;
bool pufferGefuellt = false;

Adafruit_SSD1306 display(128, 64, &Wire, -1);

float aktuelleDistanz = 0.0;
unsigned long letztesDisplayUpdate = 0;
const unsigned long DISPLAY_INTERVALL = 1000;

void setup()
{
    pinMode(RESET, OUTPUT);
    digitalWrite(RESET, HIGH);

    SERIAL_LOG.begin(115200);

    SERIAL_LOG.print(F("Hello! ESP32-S3 AT command V1.0 Test"));
    SERIAL_AT.begin(115200, SERIAL_8N1, IO_RXD2, IO_TXD2);

    SERIAL_AT.println("AT");
    Wire.begin(I2C_SDA, I2C_SCL);
    delay(1000);
    // SSD1306_SWITCHCAPVCC = generate display voltage from 3.3V internally
    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C))
    { // Address 0x3C for 128x32
        for (;;)
            ; // Don't proceed, loop forever
    }
    display.clearDisplay();

    logoshow();

    sendData("AT?", 2000, 1);
    sendData("AT+RESTORE", 5000, 1);

    sendData(config_cmd(), 2000, 1);
    sendData(cap_cmd(), 2000, 1);

    sendData("AT+SETRPT=1", 2000, 1);
    sendData("AT+SAVE", 2000, 1);
    sendData("AT+RESTART", 2000, 1);
}

long int runtime = 0;

String response = "";
String rec_head = "AT+RANGE";

void loop()
{
    while (SERIAL_LOG.available() > 0)
    {
        SERIAL_AT.write(SERIAL_LOG.read());
        yield();
    }

    while (SERIAL_AT.available() > 0)
    {
        char c = SERIAL_AT.read();
        if (c == '\n') {
            int rangePos = response.indexOf("range:(");
            if (rangePos != -1) {
                int start = rangePos + 7;
                int end = response.indexOf(",", start);

                if (end != -1) {
                    String distanzString = response.substring(start, end);
                    float wert = distanzString.toFloat();

                    float kalibrierungsOffset = 50.0; // Offset pi * Daumen
                    float wertOffset = wert - kalibrierungsOffset; // wert - minus Offset

                    //SMA für Raw- und Offset-Werte
                    pufferRaw[pufferIndex] = wert;
                    pufferOffset[pufferIndex] = wertOffset;
                    pufferIndex++;

                    if (pufferIndex >= FILTER_GROESSE) {
                        pufferIndex = 0;
                        pufferGefuellt = true;
                    }

                    // Durchschnitte berechnen
                    float summeRaw = 0.0;
                    float summeOffset = 0.0;
                    int anzahlWerte = pufferGefuellt ? FILTER_GROESSE : pufferIndex;

                    for (int i = 0; i < anzahlWerte; i++) {
                        summeRaw += pufferRaw[i];
                        summeOffset += pufferOffset[i];
                    }

                    float smaRaw = summeRaw / anzahlWerte;
                    float smaOffset = summeOffset / anzahlWerte;

                    aktuelleDistanz = smaOffset;

                    // CSV-Ausgabe
                    SERIAL_LOG.print(millis());
                    SERIAL_LOG.print(";");
                    SERIAL_LOG.print(wert);
                    SERIAL_LOG.print(";");
                    SERIAL_LOG.print(wertOffset);
                    SERIAL_LOG.print(";");
                    SERIAL_LOG.print(smaRaw);
                    SERIAL_LOG.print(";");
                    SERIAL_LOG.println(smaOffset);
                }
            }
            response = "";
        } else if (c != '\r') {
            response += c;
        }
    }

    if (millis() - letztesDisplayUpdate >= DISPLAY_INTERVALL) {
        letztesDisplayUpdate = millis();
        zeigeDistanzAufDisplay(aktuelleDistanz);
    }
}

//Anzeige auf Display der Distanz
void zeigeDistanzAufDisplay(float distanz) {
    display.clearDisplay();

    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 20);
    display.println(F("UWB Tag 0"));

    display.drawLine(0, 12, 128, 12, SSD1306_WHITE);

    display.setTextSize(2);
    display.setCursor(0, 40);

    if (distanz > 0.0) {
        display.print(distanz);
        display.println(F(" cm"));
    } else {
        display.println(F("Warte..."));
    }

    display.display();
}

// Display für Startup
void logoshow(void)
{
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println(F("MaUWB DW3000"));

    display.setCursor(0, 20);

    display.setTextSize(1);
    String temp = "";
    temp = temp + "Tag " + UWB_INDEX;
    display.println(temp);
    display.setCursor(0, 40);

    display.setTextSize(2);
    display.println("Starte Tag...");

    display.display();
    delay(2000);
}

String sendData(String command, const int timeout, boolean debug)
{
    String response = "";
    SERIAL_LOG.println(command);
    SERIAL_AT.println(command);

    long int time = millis();

    while ((time + timeout) > millis())
    {
        while (SERIAL_AT.available())
        {
            char c = SERIAL_AT.read();
            response += c;
        }
    }

    if (debug)
    {
        SERIAL_LOG.println(response);
    }

    return response;
}

String config_cmd()
{
    String temp = "AT+SETCFG=";
    temp = temp + UWB_INDEX;
    temp = temp + ",0";
    temp = temp + ",1";
    temp = temp + ",1";
    return temp;
}

String cap_cmd()
{
    String temp = "AT+SETCAP=";
    temp = temp + UWB_TAG_COUNT;
    temp = temp + ",10";
    temp = temp + ",1";
    return temp;
}
