#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "freertos/queue.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "esp_mac.h"
#include "esp_timer.h"

#define WIFI_SSID               "FTM_PINK"
#define WIFI_PASSWORD           ""

#define FTM_FRMS_PER_BURST      16
#define FTM_BURST_PERIOD        2
#define MEASUREMENT_INTERVAL_MS 500

#define MIN_FILTER_WINDOW 8

//Vars für die Lineare Regression (Beispielwerte wurden nur durch drei Messungen erhoben)
//Werden in Pythonscript errechnet
// #define RTT_REG_M1    0.3286f
// #define RTT_REG_M2    -0.0554f
// #define RTT_REG_B     -1.6927f

//hsbo
// #define RTT_REG_M1    0.2359f
// #define RTT_REG_M2    -0.0877f
// #define RTT_REG_B     -2.1656f

//hsbo multipath
#define RTT_REG_M1    0.3214f
#define RTT_REG_M2    -0.0064f
#define RTT_REG_B     -0.2207f

/* Bereich für gleitende Stddev über aufeinanderfolgende Messungen */
#define STDDEV_WINDOW           16

static const char *TAG = "wifi_rtt";
static const char *CSV = "CSV";

#define WIFI_CONNECTED_BIT  BIT0
#define FTM_DONE_BIT        BIT1

static EventGroupHandle_t       s_wifi_event_group;
static QueueHandle_t            s_ftm_queue;

// Struktur für Datenübergabe aus dem Event-Loop
typedef struct {
    uint32_t          rtt_est_ns;
    int32_t           dist_est_cm;
    int8_t            rssi;
    uint8_t           num_entries;
    wifi_ftm_status_t status;
} ftm_raw_data_t;

static uint8_t                  s_ftm_report_num_entries = 0;
static uint32_t                 s_rtt_raw_ns             = 0;
static int32_t                  s_dist_raw_cm            = 0;
static int32_t                  s_dist_filtered_cm       = 0;
static float                    s_stddev_m               = 0.0f;
static float                    s_variance_m2            = 0.0f;
static int8_t                   s_ftm_rssi               = 0;

static char    s_ap_ssid[33]  = {0};
static uint8_t s_ap_channel   = 0;
static int16_t s_ap_rssi      = 0;
static uint8_t s_ap_bandwidth = 20;

static float s_dist_calibrated_m = 0.0f;

// Diese Werte dienen der Klassifizierung der Umgebung (LOS vs. NLOS) (FSPL Free Space Path Loss)
#define CALIB_RSSI_1M          -54.0f  // 1m Meter RSSI
#define CALIB_PATH_LOSS_EXP    2.2f    // Pfadverlust-Exponent (n) für Indoor LOS
#define FSPL_PENALTY_THRESHOLD 4.0f    // Schwellenwert (dB) für NLOS Erkennung vllt abändern zu 6 oder 7
#define FSPL_VARIANCE_TH       1.5f    // Schwellenwert (m^2) für extreme Multipath Erkennung

typedef enum {
    ENV_LOS       = 0,
    ENV_NLOS_VAR  = 1,
    ENV_NLOS_RSSI = 2,
    ENV_NLOS_BOTH = 3
} env_condition_t;

static env_condition_t s_current_env = ENV_LOS;

// Diese Koeffizienten aus Training für MLR
typedef struct {
    float beta_0;    //Offset
    float beta_raw;  // Gewichtung der raw Distanz
    float beta_rssi; // Gewichtung des RSSI
    float beta_var;  // Gewichtung der Varianz
} mlr_profile_t;

// Genaue Koeffizienten aus Training für MLR für LOS und NLOS
// static const mlr_profile_t mlr_los  = { -1.0364f, 0.6334f, -0.0290f, -0.0882f };
// static const mlr_profile_t mlr_nlos = { -20.8002f, 0.2037f, -0.4223f, 0.4244f };

//s3
static const mlr_profile_t mlr_los = {
    .beta_0    =  -0.8626f,
    .beta_raw  =   0.2851f,
    .beta_rssi =  -0.0400f,
    .beta_var  =  -0.0159f
};
static const mlr_profile_t mlr_nlos = {
    .beta_0    =  -2.8615f,
    .beta_raw  =   0.2961f,
    .beta_rssi =  -0.0234f,
    .beta_var  =  -0.0436f
};

// //S3 40
// static const mlr_profile_t mlr_los = {
//     .beta_0    =  -3.6681f,
//     .beta_raw  =   0.7802f,
//     .beta_rssi =  -0.0184f,
//     .beta_var  =  -0.5153f
// };
// static const mlr_profile_t mlr_nlos = {
//     .beta_0    =  21.2034f,
//     .beta_raw  =  -0.0116f,
//     .beta_rssi =   0.1721f,
//     .beta_var  =   0.0186f
// };

//c5
// static const mlr_profile_t mlr_los = {
//     .beta_0    =  -1.0663f,
//     .beta_raw  =   0.6292f,
//     .beta_rssi =  -0.0301f,
//     .beta_var  =  -0.0867f
// };
// static const mlr_profile_t mlr_nlos = {
//     .beta_0    =  -0.1427f,
//     .beta_raw  =   0.0747f,
//     .beta_rssi =  -0.0641f,
//     .beta_var  =  -0.0614f
// };

// Zustandvariablen für den 1D Kalman-Filter
static float s_kalman_est_m   = 0.0f;       //Geschätzter Zustand
static float s_kalman_err_est = 1.0f;       //Fehler des geschätzten Zustands
//static const float KALMAN_R_BASE    = 2.5f; // Basis-Rauschen unter optimalen Bedingungen
static const float KALMAN_Q         = 0.001f; // Prozessrauschen
static const float KALMAN_GATE_M    = 2.0f; // Gating für Indoor sollte 2m reichen
static uint8_t s_gating_block_count = 0;
static const uint8_t MAX_GATING_BLOCKS = 5;

typedef struct {
    int8_t rssi_threshold;
    float offset_m;
} rtt_bias_entry_t;


// wichtig diese Werte noch Kalibrieren
static const rtt_bias_entry_t rtt_lut[] = {
    {-30, -0.40f},
    {-45, -0.25f},
    {-60, -0.10f},
    {-75,  0.00f},
    {-90,  0.15f}
};
static const int RTT_LUT_SIZE = sizeof(rtt_lut) / sizeof(rtt_bias_entry_t);

// Konstanten für die RSSI-Sensorfusion (Kalman)
// static const float RSSI_TX_POWER_1M = -35.0f; // Emptirischer RSSI bei 1m Distanz
// static const float RSSI_PATH_LOSS_N = 2.5f;   // Dämpfungsexponent (2.5 - 3.0)

//NLOS-Minimum FLiter Vars
static int32_t s_min_window[MIN_FILTER_WINDOW] = {0};
static int     s_min_window_pos   = 0;
static int     s_min_window_count = 0;

static int32_t s_dist_nlos_min_cm = 0;


//Ringpuffer der letzten Distanzwerte in cm
static int32_t s_dist_window[STDDEV_WINDOW] = {0};
static int     s_dist_window_pos            = 0;
static int     s_dist_window_count          = 0;

//FSPL Klassifizierung der Umgebung (LOS vs. NLOS)
static env_condition_t detect_environment(float raw_dist_m, int8_t measured_rssi, float variance_m2)
{
    // Verhindere mathematische Fehler (log10 von <= 0) bei zu nahen Objekten
    if (raw_dist_m < 1.0f) {
        return ENV_LOS;
    }

    // FSPL Formel: Theoretischer Wert in freien Raum
    float expected_rssi = CALIB_RSSI_1M - (10.0f * CALIB_PATH_LOSS_EXP * log10f(raw_dist_m));

    float rssi_difference = expected_rssi - (float)measured_rssi;


    bool nlos_rssi = (rssi_difference > FSPL_PENALTY_THRESHOLD);
    bool nlos_var  = (variance_m2 > FSPL_VARIANCE_TH);
    if (nlos_rssi && nlos_var) {
            return ENV_NLOS_BOTH;
        } else if (nlos_rssi) {
            return ENV_NLOS_RSSI;
        } else if (nlos_var) {
            return ENV_NLOS_VAR;
        }

        return ENV_LOS;
}

static float calc_window_variance(void)
{
    if (s_dist_window_count < 2) return 0.0f;

    double sum = 0.0;
    for (int i = 0; i < s_dist_window_count; i++)
        sum += s_dist_window[i];
    double mean = sum / s_dist_window_count;

    double var = 0.0;
    for (int i = 0; i < s_dist_window_count; i++) {
        double d = s_dist_window[i] - mean;
        var += d * d;
    }
    var /= s_dist_window_count;

    return (float)(var / 10000.0); // früher 100.0f, so besser?
}

static float get_rtt_bias_m(int8_t current_rssi) {
    if (current_rssi >= rtt_lut[0].rssi_threshold) return rtt_lut[0].offset_m;
    if (current_rssi <= rtt_lut[RTT_LUT_SIZE - 1].rssi_threshold) return rtt_lut[RTT_LUT_SIZE - 1].offset_m;

    for (int i = 0; i < RTT_LUT_SIZE - 1; i++) {
        if (current_rssi <= rtt_lut[i].rssi_threshold && current_rssi > rtt_lut[i+1].rssi_threshold) {
            float rssi_diff = rtt_lut[i].rssi_threshold - rtt_lut[i+1].rssi_threshold;
            float offset_diff = rtt_lut[i].offset_m - rtt_lut[i+1].offset_m;
            float factor = (current_rssi - rtt_lut[i+1].rssi_threshold) / rssi_diff;
            return rtt_lut[i+1].offset_m + (offset_diff * factor);
        }
    }
    return 0.0f;
}

static bool update_kalman_1d(float measurement_m, float current_variance_m2)
{
    // Initialisierung, der allererste Wert wird sofort als Wahrheit genommen
    if (s_kalman_est_m == 0.0f) {
        s_kalman_est_m = measurement_m;
        s_kalman_err_est = 1.0f;
        return true;
    }

    // Prädiktionsschritt
    float prior_err_est = s_kalman_err_est + KALMAN_Q;
    float innovation = measurement_m - s_kalman_est_m;

    // Innovation-Gating mit Failsafe-Zähler
    if (fabs(innovation) > KALMAN_GATE_M) {
        s_gating_block_count++;

        // Wenn der Filter blockiert, resetten
        if (s_gating_block_count >= MAX_GATING_BLOCKS) {
            ESP_LOGW(TAG, "Filter Lock-out erkannt! Erzwungener Reset auf %.2f m", measurement_m);
            s_kalman_est_m = measurement_m;
            s_kalman_err_est = 1.0f;
            s_gating_block_count = 0;
            return true;
        }
        return false;
    }

    s_gating_block_count = 0;

    // Diese alte Heuristik wurde mit RSSI genutzt, ist outdated, weil nun die Variance genutzt wird
    //RSSI-Sensorfusion mit Limitierung (Cap)
    // float dynamic_r = KALMAN_R_BASE;

    // if (current_rssi < 0 && current_rssi > -100) {
    //     float expected_dist_m = powf(10.0f, (RSSI_TX_POWER_1M - (float)current_rssi) / (10.0f * RSSI_PATH_LOSS_N));

    //     if (measurement_m > expected_dist_m * 1.5f) {
    //         float penalty = measurement_m - expected_dist_m;
    //         dynamic_r += (penalty * penalty);

    //         //Verhindert, dass der Kalman-Gain 0 wird und der Filter einfriert.
    //         if (dynamic_r > 50.0f) {
    //             dynamic_r = 50.0f;
    //         }
    //     }
    // }

    //Kalman-Gain berechnen
    float dynamic_r = (current_variance_m2 > 0.01f) ? current_variance_m2 : 0.5f;

    float kalman_gain = prior_err_est / (prior_err_est + dynamic_r);

    s_kalman_est_m = s_kalman_est_m + kalman_gain * innovation;
    s_kalman_err_est = (1.0f - kalman_gain) * prior_err_est;

    return true;
}


static int32_t process_nlos_min_filter(int32_t new_dist_cm)
{
    s_min_window[s_min_window_pos] = new_dist_cm;
    s_min_window_pos = (s_min_window_pos + 1) % MIN_FILTER_WINDOW;
    if (s_min_window_count < MIN_FILTER_WINDOW) s_min_window_count++;

    //Minimum im aktuellen Fenster suchen
    int32_t current_min = s_min_window[0];
    for (int i = 1; i < s_min_window_count; i++) {
        if (s_min_window[i] < current_min) {
            current_min = s_min_window[i];
        }
    }

    return current_min;
}

static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
    if (event_base != WIFI_EVENT) return;
    switch (event_id) {
        case WIFI_EVENT_STA_START:
            ESP_LOGI(TAG, "WLAN verbinden ...");
            esp_wifi_connect();
            break;
        case WIFI_EVENT_STA_CONNECTED:
            ESP_LOGI(TAG, "Mit AP verbunden.");
            xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
            break;
        case WIFI_EVENT_STA_DISCONNECTED:
            ESP_LOGW(TAG, "Verbindung verloren, erneuter Versuch ...");
            esp_wifi_connect();
            xEventGroupClearBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
            break;
        case WIFI_EVENT_FTM_REPORT: {
            wifi_event_ftm_report_t *ftm = (wifi_event_ftm_report_t *)event_data;

            wifi_ap_record_t ap_info;
            int8_t current_rssi = -127;

            if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
                current_rssi = ap_info.rssi;
            }

            ftm_raw_data_t raw_data = {
                .rtt_est_ns  = ftm->rtt_est,
                .dist_est_cm = ftm->dist_est,
                .rssi        = current_rssi,
                .num_entries = ftm->ftm_report_num_entries,
                .status      = ftm->status
            };

            // Timeout = 0, um Event-Loop bei voller Queue nicht blockiert
            if (xQueueSend(s_ftm_queue, &raw_data, 0) != pdTRUE) {
                ESP_LOGW(TAG, "FTM Queue voll, Report verworfen!");
            }
            break;
        }
        default: break;
    }
}

// Simple Moving Average (SMA) Filter (Glättung)
static void ftm_filter_task(void *pvParameters)
{
    ftm_raw_data_t data;

    while (1) {
        if (xQueueReceive(s_ftm_queue, &data, portMAX_DELAY) == pdTRUE) {

            if (data.status == FTM_STATUS_SUCCESS) {
                s_rtt_raw_ns             = data.rtt_est_ns;
                s_dist_raw_cm            = data.dist_est_cm;
                s_ftm_report_num_entries = data.num_entries;
                s_ftm_rssi               = data.rssi;

                //Ringpuffer aktualisieren
                s_dist_window[s_dist_window_pos] = data.dist_est_cm;
                s_dist_window_pos = (s_dist_window_pos + 1) % STDDEV_WINDOW;
                if (s_dist_window_count < STDDEV_WINDOW) s_dist_window_count++;

                //SMA berechnen
                int64_t sum = 0;
                for (int i = 0; i < s_dist_window_count; i++) {
                    sum += s_dist_window[i];
                }
                s_dist_filtered_cm = (int32_t)(sum / s_dist_window_count);

                s_dist_nlos_min_cm = process_nlos_min_filter(data.dist_est_cm);

                // Varianz für MLR berechnen
                s_variance_m2 = calc_window_variance();
                s_stddev_m    = sqrtf(s_variance_m2);

                float raw_dist_m = (float)data.dist_est_cm / 100.0f;
                float hardware_offset_m = get_rtt_bias_m(s_ftm_rssi);
                float lut_corrected_dist_m = raw_dist_m + hardware_offset_m;
                if (lut_corrected_dist_m < 0.0f) lut_corrected_dist_m = 0.0f;
                update_kalman_1d(lut_corrected_dist_m, s_variance_m2);

            } else {
                ESP_LOGW(TAG, "FTM fehlgeschlagen, Status: %d", data.status);
                s_rtt_raw_ns       = 0;
                s_dist_raw_cm      = 0;
                s_dist_filtered_cm = 0;
                s_variance_m2      = 0.0f;
                s_stddev_m         = 0.0f;
            }
            xEventGroupSetBits(s_wifi_event_group, FTM_DONE_BIT);
        }
    }
}

static void wifi_init(void)
{
    s_wifi_event_group = xEventGroupCreate();
    s_ftm_queue = xQueueCreate(10, sizeof(ftm_raw_data_t));

    ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    wifi_config_t wifi_config = {
        .sta = {
            .ssid               = WIFI_SSID,
            .password           = WIFI_PASSWORD,
            .threshold.authmode = WIFI_AUTH_OPEN,
            .scan_method        = WIFI_ALL_CHANNEL_SCAN,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    // 5 GHz Bereich

    //ESP_ERROR_CHECK(esp_wifi_set_band_mode(WIFI_BAND_MODE_5G_ONLY));
    //ESP_ERROR_CHECK(esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_11A | WIFI_PROTOCOL_11N));

    // 2,4 GHZ Bereich

    ESP_ERROR_CHECK(esp_wifi_set_band_mode(WIFI_BAND_MODE_2G_ONLY));
    ESP_ERROR_CHECK(esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G | WIFI_PROTOCOL_11N));

    // Erzwingen von 40 Mhz
    //ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW40));
    ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW20));


    ESP_LOGI(TAG, "Warte auf WLAN-Verbindung ...");
    xEventGroupWaitBits(s_wifi_event_group, WIFI_CONNECTED_BIT,
                        pdFALSE, pdTRUE, portMAX_DELAY);
    ESP_LOGI(TAG, "WLAN verbunden.");
}

static esp_err_t start_ftm_session(void)
{
    wifi_ap_record_t ap_info;
    if (esp_wifi_sta_get_ap_info(&ap_info) != ESP_OK) {
        ESP_LOGE(TAG, "AP-Info konnte nicht abgerufen werden");
        return ESP_FAIL;
    }
    strncpy(s_ap_ssid, (char *)ap_info.ssid, sizeof(s_ap_ssid) - 1);
    s_ap_channel   = ap_info.primary;
    s_ap_rssi      = ap_info.rssi;
    s_ap_bandwidth = (ap_info.second == WIFI_SECOND_CHAN_NONE) ? 20 : 40;

    wifi_ftm_initiator_cfg_t ftm_cfg = {
        .frm_count          = FTM_FRMS_PER_BURST,
        .burst_period       = FTM_BURST_PERIOD,
    };
    memcpy(ftm_cfg.resp_mac, ap_info.bssid, 6);
    ftm_cfg.channel = ap_info.primary;

    return esp_wifi_ftm_initiate_session(&ftm_cfg);
}

static void print_csv_line(void)
{
    uint64_t time_ms     = esp_timer_get_time() / 1000ULL;
    float    dist_raw_m  = s_dist_raw_cm / 100.0f;
    float    dist_filt_m = s_dist_filtered_cm / 100.0f;
    float    dist_nlos_m = s_dist_nlos_min_cm / 100.0f;
    int      ch_mhz      = 0;

    // Berechnung der Frequenz in MHz abhängig vom Band
    if (s_ap_channel <= 14) {
        ch_mhz = (s_ap_channel == 14) ? 2484 : (2407 + s_ap_channel * 5);
    } else {
        ch_mhz = 5000 + s_ap_channel * 5;
    }

    ESP_LOGI(CSV, "%" PRIu64 ",%.3f,%.3f,%.3f,%.3f,%.3f,%.5f,%.3f,%d,%d,%d,%d,%d,%d,%d,%s",
            time_ms,
            dist_raw_m,
            dist_filt_m,
            s_dist_calibrated_m,
            dist_nlos_m,
            s_kalman_est_m,
            s_variance_m2,
            s_stddev_m,
            (int)s_ftm_report_num_entries,
            FTM_FRMS_PER_BURST,
            (int)s_ftm_rssi,
            (int)s_ap_rssi,
            ch_mhz,
            (int)s_ap_bandwidth,
            (int)s_current_env,
            s_ap_ssid);
}

static void rtt_measurement_task(void *pvParameters)
{
    uint32_t n = 0;
    while (1) {
        n++;
        EventBits_t bits = xEventGroupGetBits(s_wifi_event_group);
        if (!(bits & WIFI_CONNECTED_BIT)) {
            ESP_LOGW(TAG, "Nicht verbunden, warte ...");
            vTaskDelay(pdMS_TO_TICKS(MEASUREMENT_INTERVAL_MS));
            continue;
        }
        xEventGroupClearBits(s_wifi_event_group, FTM_DONE_BIT);

        if (start_ftm_session() != ESP_OK) {
            ESP_LOGE(TAG, "FTM-Session konnte nicht gestartet werden");
            vTaskDelay(pdMS_TO_TICKS(MEASUREMENT_INTERVAL_MS));
            continue;
        }

        // Warten auf Filter-Task
        bits = xEventGroupWaitBits(s_wifi_event_group, FTM_DONE_BIT,
                                   pdTRUE, pdTRUE, pdMS_TO_TICKS(5000));

        if (bits & FTM_DONE_BIT) {
            if (s_rtt_raw_ns > 0) {
                float raw_dist_m = s_dist_raw_cm / 100.0f;

                // MLR + FSPL FUNKTION: Piecewise Regression anwenden

                s_current_env = detect_environment(raw_dist_m, s_ftm_rssi, s_variance_m2);

                //Enscheiden zwischen LOS und NLOS
                const mlr_profile_t *active_profile = (s_current_env == ENV_LOS) ? &mlr_los : &mlr_nlos;

                float sma_dist_m = s_dist_filtered_cm / 100.0f;

                // Lineare Regressionsgleichung
                s_dist_calibrated_m = active_profile->beta_0 +
                                      (active_profile->beta_raw * sma_dist_m) +
                                      (active_profile->beta_rssi * (float)s_ftm_rssi) +
                                      (active_profile->beta_var * s_variance_m2);

                // Fallback für falsche Berechnung (Besser wäre Vorgängerwert)
                if (s_dist_calibrated_m < 0.0f) {
                    ESP_LOGW(TAG, "MLR ergab negativen Wert (%.2fm). Fallback auf SMA.", s_dist_calibrated_m);
                    s_dist_calibrated_m = sma_dist_m;
                }

                ESP_LOGI(TAG, "── Messung #%" PRIu32 " ──", n);
                ESP_LOGI(TAG, "Umgebung:    %s", (s_current_env == ENV_LOS) ? "LOS (Sichtlinie)" : "NLOS (Verdeckt)");
                ESP_LOGI(TAG, "  Raw:        %.2f m", raw_dist_m);
                ESP_LOGI(TAG, "  Calibrated: %.2f m (MLR)", s_dist_calibrated_m);
                // ESP_LOGI(TAG, "  Methode B:  %.2f m (LUT + Kalman)", s_kalman_est_m);
                // ESP_LOGI(TAG, "  Varianz:    %.5f m^2 | RSSI: %d dBm", s_variance_m2, s_ftm_rssi);
                print_csv_line();
            } else {
                ESP_LOGW(TAG, "Messung fehlgeschlagen (RTT = 0)");
            }
        } else {
            ESP_LOGE(TAG, "Timeout: Keine FTM-Antwort erhalten");
            esp_wifi_ftm_end_session();
        }
        vTaskDelay(pdMS_TO_TICKS(MEASUREMENT_INTERVAL_MS));
    }
}

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    esp_log_level_set("*", ESP_LOG_NONE);
    esp_log_level_set("event", ESP_LOG_INFO);
    esp_log_level_set("CSV", ESP_LOG_INFO);
    esp_log_level_set("wifi_rtt", ESP_LOG_INFO);

    wifi_init();
    xTaskCreate(ftm_filter_task, "ftm_filter", 4096, NULL, 4, NULL);
    xTaskCreate(rtt_measurement_task, "rtt_task", 4096, NULL, 5, NULL);
}
