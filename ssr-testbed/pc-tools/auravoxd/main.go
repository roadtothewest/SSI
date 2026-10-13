// auravoxd: servicio de la Raspberry Pi para AuraVox.
//
// Goroutines en paralelo:
//
//	source   → bloques crudos del DK (SPI + DRDY), simulados o de archivo
//	decoder  → valida CRC/seq y ordena las tuplas en los buffers (stream.Store)
//	recorder → graba la sesión en disco cuando se pide
//	cwt      → escalogramas CWT (magnitud y fase), una columna por hop
//	stats    → correlación cruzada sEMG→voz, cross-wavelet, enunciados, estadísticas
//	web      → HMI en http://<pi>:8080 (SSE, sin internet)
package main

import (
	"context"
	"errors"
	"flag"
	"log"
	"net"
	"net/http"
	"os/signal"
	"syscall"
	"time"

	"auravoxd/analysis"
	"auravoxd/record"
	"auravoxd/source"
	"auravoxd/stream"
	"auravoxd/web"
)

type Source interface {
	Run(ctx context.Context, out chan<- []byte)
}

func main() {
	src := flag.String("src", "spi", "fuente: spi | sim | file")
	file := flag.String("file", "", "sesión .avx para -src file")
	addr := flag.String("addr", ":8080", "dirección de la HMI")
	data := flag.String("data", "./data", "carpeta de las sesiones grabadas")
	dev := flag.String("spi-dev", "/dev/spidev0.0", "dispositivo spidev")
	hz := flag.Uint("spi-hz", 4_000_000, "reloj SPI [Hz]")
	chip := flag.String("gpiochip", "gpiochip0", "chip GPIO de la línea DRDY")
	drdy := flag.Int("drdy", 25, "GPIO de DRDY (-1 = sin DRDY, lee cada 10 ms)")
	hop := flag.Int("hop", 10, "hop de la CWT [ms]: 5, 10 o 20")
	lag := flag.Float64("sim-lag", 60, "adelanto del sEMG en la simulación [ms]")
	vozDelay := flag.Float64("voz-delay", 0.75, "retardo fijo de la voz respecto del sEMG [ms] (filtro del firmware: ADMP401 0.75, INMP441 1.078)")
	conv := stream.Conv{}
	flag.Float64Var(&conv.VrefADC, "vref-adc", 1.8, "referencia del ADC del DK [V]")
	flag.Float64Var(&conv.GDK, "gdk", 0.5437, "ganancia del pin Arduino al ADC (divisor 560/1030 del DK, MB1939)")
	flag.Float64Var(&conv.VMid, "vmid", 1.65, "VREF del AFE [V]")
	flag.Float64Var(&conv.Gain, "gain", 2500, "ganancia total del AFE")
	flag.Parse()

	var s Source
	switch *src {
	case "spi":
		s = &source.SPI{Dev: *dev, Hz: uint32(*hz), Chip: *chip, DRDY: *drdy}
	case "sim":
		s = &source.Sim{Conv: conv, LagMS: *lag}
	case "file":
		s = &source.File{Path: *file}
	default:
		log.Fatalf("fuente desconocida: %s", *src)
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	st := stream.NewStore(conv)
	an := analysis.New(st, *hop)
	an.VozDelayMS = *vozDelay
	if *src == "sim" && !flagSet("voz-delay") {
		an.VozDelayMS = 0 // la simulación no pasa la voz por el filtro del firmware
	}
	rec := record.New(*data)
	an.OnUtterance = rec.AddUtterance

	raw := make(chan []byte, 256)
	go s.Run(ctx, raw)
	go func() { // decoder
		for {
			select {
			case <-ctx.Done():
				return
			case b := <-raw:
				if st.Ingest(b) {
					rec.Feed(b)
				}
			}
		}
	}()
	go rec.Run(ctx)
	go an.RunCWT(ctx)
	go an.RunStats(ctx)

	srv := &http.Server{
		Addr:        *addr,
		Handler:     (&web.Server{St: st, An: an, Rec: rec, Conv: conv, Source: *src, DataDir: *data}).Handler(),
		BaseContext: func(net.Listener) context.Context { return ctx }, // cierra los SSE al apagar
	}
	go func() {
		<-ctx.Done()
		sc, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		srv.Shutdown(sc)
	}()
	log.Printf("auravoxd: fuente %s, HMI en %s", *src, *addr)
	if err := srv.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
	rec.Stop()
}

func flagSet(name string) (set bool) {
	flag.Visit(func(f *flag.Flag) { set = set || f.Name == name })
	return
}
