package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"time"

	"ssr-ingest/buffer"
	"ssr-ingest/display"
	"ssr-ingest/parser"
	"ssr-ingest/storage"

	"go.bug.st/serial.v1"
)

func main() {
	portName := flag.String("port", "/dev/ttyACM0", "USB CDC serial port")
	baud := flag.Int("baud", 115200, "Baud rate (ignored for CDC)")
	output := flag.String("output", "dataset/sessions", "Output directory")
	duration := flag.Int("duration", 0, "Recording duration in seconds (0 = manual stop)")
	plot := flag.Bool("plot", false, "Show real-time plot (requires Python)")
	flag.Parse()

	mode := &serial.Mode{
		BaudRate: *baud,
	}
	port, err := serial.Open(*portName, mode)
	if err != nil {
		log.Fatalf("Failed to open port %s: %v", *portName, err)
	}
	defer port.Close()

	if err := port.SetReadTimeout(serial.NoTimeout); err != nil {
		log.Fatalf("Failed to set timeout: %v", err)
	}

	ring := buffer.NewRing(10 * time.Second)
	writer := storage.NewWriter(*output)

	parser := parser.NewFrameParser(ring, writer)

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, os.Interrupt)

	stats := display.NewStats()
	stats.Start()

	readBuf := make([]byte, 4096)

	log.Printf("SSR Ingest — listening on %s", *portName)
	log.Printf("Output: %s", *output)

	if *duration > 0 {
		log.Printf("Duration: %ds", *duration)
		go func() {
			time.Sleep(time.Duration(*duration) * time.Second)
			sigCh <- os.Interrupt
		}()
	}

	running := true
	for running {
		select {
		case <-sigCh:
			fmt.Println()
			log.Println("Stopping capture...")
			running = false
		default:
			n, err := port.Read(readBuf)
			if err != nil {
				log.Printf("Read error: %v", err)
				time.Sleep(100 * time.Millisecond)
				continue
			}
			if n > 0 {
				parser.Feed(readBuf[:n])
				stats.Update(parser.FrameCount(), parser.DropCount())
			}
		}
	}

	writer.Close()
	stats.Stop()

	final := stats.Report()
	fmt.Println(final)
}
