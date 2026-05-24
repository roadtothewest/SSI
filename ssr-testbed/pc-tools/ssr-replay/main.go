package main

import (
	"encoding/binary"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"time"
)

func main() {
	input := flag.String("input", "", "Input .ssr file (required)")
	speed := flag.Float64("speed", 1.0, "Playback speed multiplier")
	loop := flag.Bool("loop", false, "Loop playback")
	port := flag.String("port", "/dev/ttyACM0", "Output serial port")
	flag.Parse()

	if *input == "" {
		log.Fatal("--input is required")
	}

	f, err := os.Open(*input)
	if err != nil {
		log.Fatalf("Failed to open %s: %v", *input, err)
	}
	defer f.Close()

	data, err := io.ReadAll(f)
	if err != nil {
		log.Fatalf("Failed to read: %v", err)
	}

	info := analyzeFile(data)
	fmt.Println(info)

	baseDelay := time.Second / time.Duration(*speed * 26700.0 / float64(info.accSamplesPerFrame * 3 * 2))

	for {
		pos := 0
		startTime := time.Now()
		firstTs := uint32(0)
		for pos < len(data) {
			if pos+10 > len(data) {
				break
			}
			if data[pos] != 0xAA || data[pos+1] != 0x55 {
				pos++
				continue
			}
			dataLen := int(binary.LittleEndian.Uint16(data[pos+8 : pos+10]))
			frameSize := 10 + dataLen
			if pos+frameSize > len(data) {
				break
			}

			ts := binary.LittleEndian.Uint32(data[pos+4 : pos+8])
			frameType := data[pos+2]

			if firstTs == 0 {
				firstTs = ts
			}
			elapsed := time.Duration(ts-firstTs) * time.Microsecond
			elapsed = time.Duration(float64(elapsed) / *speed)
			target := startTime.Add(elapsed)
			now := time.Now()
			if target.After(now) {
				time.Sleep(target.Sub(now))
			}

			desc := "ACC"
			if frameType == 0x02 {
				desc = "AUDIO"
			}

			if *port != "" {
			}

			pos += frameSize
			if frameType == 0x01 {
				fmt.Printf("\rReplaying: ts=%d %s", ts, desc)
			}
		}

		if !*loop {
			break
		}
		fmt.Println("\nLooping...")
	}
	fmt.Println("\nReplay complete")
}

type fileInfo struct {
	frames             int
	accFrames          int
	audioFrames        int
	accSamplesPerFrame int
}

func analyzeFile(data []byte) fileInfo {
	info := fileInfo{}
	pos := 0
	for pos+10 <= len(data) {
		if data[pos] != 0xAA || data[pos+1] != 0x55 {
			pos++
			continue
		}
		dataLen := int(binary.LittleEndian.Uint16(data[pos+8 : pos+10]))
		frameSize := 10 + dataLen
		if pos+frameSize > len(data) {
			break
		}
		info.frames++
		if data[pos+2] == 0x01 {
			info.accFrames++
			info.accSamplesPerFrame = dataLen / 6
		} else if data[pos+2] == 0x02 {
			info.audioFrames++
		}
		pos += frameSize
	}
	return info
}

func (i fileInfo) String() string {
	return fmt.Sprintf("Frames: %d (ACC: %d, AUDIO: %d) | ACC samples/frame: %d",
		i.frames, i.accFrames, i.audioFrames, i.accSamplesPerFrame)
}
