#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <signal.h>

#ifdef _WIN32
  #include <windows.h>
  typedef HANDLE serial_fd_t;
  #define INVALID_FD INVALID_HANDLE_VALUE
#else
  #include <unistd.h>
  #include <fcntl.h>
  #include <termios.h>
  typedef int serial_fd_t;
  #define INVALID_FD (-1)
#endif

static volatile int g_running = 1;
static FILE        *g_csv_fp  = NULL;

static void sig_handler(int sig)
{
    (void)sig;
    g_running = 0;
    if (g_csv_fp) { fflush(g_csv_fp); fclose(g_csv_fp); g_csv_fp = NULL; }
    printf("\n[Logger] Signal empfangen, beende ...\n");
}

#ifdef _WIN32

static serial_fd_t serial_open(const char *port, int baud)
{
    char full_port[64];
    snprintf(full_port, sizeof(full_port), "\\\\.\\%s", port);
    HANDLE h = CreateFileA(full_port, GENERIC_READ | GENERIC_WRITE,
                           0, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) {
        fprintf(stderr, "[Logger] Kann %s nicht oeffnen (0x%lx)\n", port, GetLastError());
        return INVALID_HANDLE_VALUE;
    }
    DCB dcb = {0};
    dcb.DCBlength = sizeof(DCB);
    GetCommState(h, &dcb);
    dcb.BaudRate = (DWORD)baud;
    dcb.ByteSize = 8; dcb.Parity = NOPARITY; dcb.StopBits = ONESTOPBIT;
    SetCommState(h, &dcb);
    COMMTIMEOUTS t = {100, 0, 500, 0, 0};
    SetCommTimeouts(h, &t);
    return h;
}

static int serial_read_byte(serial_fd_t fd, unsigned char *b)
{
    DWORD n = 0;
    if (!ReadFile(fd, b, 1, &n, NULL)) return -1;
    return (n == 1) ? 0 : 1;
}

static void serial_close(serial_fd_t fd) { CloseHandle(fd); }

#else

static speed_t baud_to_speed(int baud)
{
    switch (baud) {
        case 9600:   return B9600;
        case 19200:  return B19200;
        case 38400:  return B38400;
        case 57600:  return B57600;
        case 115200: return B115200;
        case 230400: return B230400;
        case 460800: return B460800;
        case 921600: return B921600;
        default:     return B115200;
    }
}

static serial_fd_t serial_open(const char *port, int baud)
{
    int fd = open(port, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0) {
        fprintf(stderr, "[Logger] Kann %s nicht oeffnen: %s\n", port, strerror(errno));
        return INVALID_FD;
    }
    fcntl(fd, F_SETFL, fcntl(fd, F_GETFL, 0) & ~O_NONBLOCK);

    struct termios tty;
    tcgetattr(fd, &tty);
    cfsetispeed(&tty, baud_to_speed(baud));
    cfsetospeed(&tty, baud_to_speed(baud));
    tty.c_cflag &= ~(PARENB | CSTOPB | CSIZE | CRTSCTS);
    tty.c_cflag |=  CS8 | CREAD | CLOCAL;
    tty.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);
    tty.c_iflag &= ~(IXON | IXOFF | IXANY | ICRNL);
    tty.c_oflag &= ~OPOST;
    tty.c_cc[VMIN] = 0; tty.c_cc[VTIME] = 5;
    tcsetattr(fd, TCSANOW, &tty);
    return fd;
}

static int serial_read_byte(serial_fd_t fd, unsigned char *b)
{
    ssize_t n = read(fd, b, 1);
    if (n < 0) return -1;
    if (n == 0) return  1;
    return 0;
}

static void serial_close(serial_fd_t fd) { close(fd); }

#endif

#define LINE_BUF_SIZE 512

static int read_line(serial_fd_t fd, char *buf, int maxlen)
{
    int pos = 0;
    while (g_running && pos < maxlen - 1) {
        unsigned char c;
        int r = serial_read_byte(fd, &c);
        if (r < 0) return -1;
        if (r > 0) continue;
        if (c == '\r') continue;
        if (c == '\n') { buf[pos] = '\0'; return pos; }
        buf[pos++] = (char)c;
    }
    buf[pos] = '\0';
    return pos;
}

#define CSV_TAG     ") CSV: "
#define CSV_TAG_LEN (sizeof(CSV_TAG) - 1)

static const char *CSV_HEADER =
    "Time_ms,TrueRange_m,Raw_m,Filtered_m,Calibrated_m,NLOS_Min_m,Kalman_m,Variance_m2,StdDev_m,"
    "Successes,Burst,FTM_RSSI_dBm,AP_RSSI_dBm,Ch_MHz,BW_MHz,Env_Status,SSID\n";

static int count_commas(const char *s)
{
    int n = 0;
    while (*s) { if (*s++ == ',') n++; }
    return n;
}

static int is_clean(const char *s)
{
    while (*s) {
        unsigned char c = (unsigned char)*s++;
        if (c < 0x20 && c != '\t') return 0;
        if (c > 0x7E) return 0;
    }
    return 1;
}

static int open_csv(const char *path)
{
    int write_header = 1;
    FILE *test = fopen(path, "r");
    if (test) { fclose(test); write_header = 0; printf("[Logger] Haenge an '%s'.\n", path); }
    else printf("[Logger] Erstelle neue Datei '%s'.\n", path);

    g_csv_fp = fopen(path, write_header ? "w" : "a");
    if (!g_csv_fp) { fprintf(stderr, "[Logger] Fehler: %s\n", strerror(errno)); return -1; }
    if (write_header) { fputs(CSV_HEADER, g_csv_fp); fflush(g_csv_fp); }
    return 0;
}

static void process_line(char *line, long *row_count, float true_range)
{
    char *esc = strchr(line, '\033');
    if (esc) *esc = '\0';

    const char *found = strstr(line, CSV_TAG);
    if (!found) {
        printf("%s\n", line);
        return;
    }

    const char *data = found + CSV_TAG_LEN;

    int commas = count_commas(data);
    if (commas != 15) {
        printf("[Logger] VERWORFEN (%d Felder): %s\n", commas + 1, data);
        return;
    }
    if (!is_clean(data)) {
        printf("[Logger] VERWORFEN (ungueltige Zeichen): %s\n", data);
        return;
    }

    char out[LINE_BUF_SIZE];
    const char *c1 = strchr(data, ',');

    if (c1) {
        int plen = (int)(c1 - data);
        snprintf(out, sizeof(out), "%.*s,%.3f%s", plen, data, (double)true_range, c1);
    } else {
        return;
    }

    fprintf(g_csv_fp, "%s\n", out);
    fflush(g_csv_fp);
#ifndef _WIN32
    fsync(fileno(g_csv_fp));
#endif

    (*row_count)++;
    printf("[Logger] Zeile #%ld: %s\n", *row_count, out);
}

int main(int argc, char *argv[])
{
    if (argc < 5) {
        fprintf(stderr,
                "Verwendung: %s <port> <baudrate> <ausgabe.csv> <true_range_m> [max_requests]\n"
                "Beispiel:   %s /dev/ttyUSB0 115200 rtt-log.csv 1.5 100\n",
                argv[0], argv[0]);
        return EXIT_FAILURE;
    }

    const char *port         = argv[1];
    int         baud         = atoi(argv[2]);
    const char *csv_path     = argv[3];
    float       true_range   = (float)atof(argv[4]);

    // Neues Argument auslesen
    int         max_requests = 0;
    if (argc >= 6) {
        max_requests = atoi(argv[5]);
    }

    signal(SIGINT,  sig_handler);
    signal(SIGTERM, sig_handler);

    serial_fd_t fd = serial_open(port, baud);
    if (fd == INVALID_FD) return EXIT_FAILURE;
    printf("[Logger] Port %s geöffnet (%d Baud).\n", port, baud);

    if (open_csv(csv_path) != 0) { serial_close(fd); return EXIT_FAILURE; }

    printf("[Logger] True Range: %.3f m\n", true_range);
    if (max_requests > 0) {
        printf("[Logger] Limit: %d erfolgreiche Anfragen\n", max_requests);
    } else {
        printf("[Logger] Limit: Unendlich\n");
    }
    printf("[Logger] Warte auf Daten ... (Ctrl+C zum Beenden)\n\n");

    char line_buf[LINE_BUF_SIZE];
    long row_count = 0;

    while (g_running) {
        int len = read_line(fd, line_buf, sizeof(line_buf));
        if (len < 0) { fprintf(stderr, "[Logger] Lesefehler.\n"); break; }
        if (len == 0) continue;

        process_line(line_buf, &row_count, true_range);

        // Nach dem Verarbeiten prüfen, ob wir das Limit erreicht haben
        if (max_requests > 0 && row_count >= max_requests) {
            printf("\n[Logger] Ziel von %d Zeilen erreicht.\n", max_requests);
            break;
        }
    }

    printf("\n[Logger] Beende. %ld Zeilen in '%s'.\n", row_count, csv_path);
    if (g_csv_fp) { fflush(g_csv_fp); fclose(g_csv_fp); }
    serial_close(fd);
    return EXIT_SUCCESS;
}
