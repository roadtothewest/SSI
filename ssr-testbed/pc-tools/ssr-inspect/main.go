package main

import (
	"encoding/binary"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
)

func main() {
	input := flag.String("input", "", "Input .ssr file (required)")
	verbose := flag.Bool("v", false, "Verbose: print all frame headers")
	first := flag.Int("first", 10, "Number of frames to show in verbose mode")
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

	totalFrames := 0
	accFrames := 0
	audioFrames := 0
	unknownFrames := 0
	minTs := uint32(0xFFFFFFFF)
	maxTs := uint32(0)
	firstAccTs := uint32(0)
	firstAudioTs := uint32(0)
	pos := 0
	shown := 0

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

		totalFrames++
		ts := binary.LittleEndian.Uint32(data[pos+4 : pos+8])
		frameType := data[pos+2]

		if ts < minTs {
			minTs = ts
		}
		if ts > maxTs {
			maxTs = ts
		}

		switch frameType {
		case 0x01:
			accFrames++
			if firstAccTs == 0 {
				firstAccTs = ts
			}
		case 0x02:
			audioFrames++
			if firstAudioTs == 0 {
				firstAudioTs = ts
			}
		default:
			unknownFrames++
		}

		if *verbose && shown < *first {
			shown++
			typeName := "ACC"
			if frameType == 0x02 {
				typeName = "AUDIO"
			} else if frameType != 0x01 {
				typeName = fmt.Sprintf("UNK(0x%02X)", frameType)
			}
			fmt.Printf("#%04d: %s ts=%10d len=%4d flags=0x%02X\n",
				totalFrames, typeName, ts, dataLen, data[pos+3])
		}

		pos += frameSize
	}

	duration := float64(maxTs-minTs) / 1e6

	fmt.Printf("\n=== File: %s ===\n", *input)
	fmt.Printf("Total size:   %d bytes\n", len(data))
	fmt.Printf("Total frames: %d\n", totalFrames)
	fmt.Printf("  ACC:   %d (%.1f%%)\n", accFrames, float64(accFrames)/float64(totalFrames)*100)
	fmt.Printf("  AUDIO: %d (%.1f%%)\n", audioFrames, float64(audioFrames)/float64(totalFrames)*100)
	fmt.Printf("  UNK:   %d\n", unknownFrames)
	fmt.Printf("Time range:   %.3f s (ts %d → %d)\n", duration, minTs, maxTs)
	fmt.Printf("ACC rate:     %.1f fps\n", float64(accFrames)/duration)
	fmt.Printf("AUDIO rate:   %.1f fps\n", float64(audioFrames)/duration)

	if firstAccTs != 0 && firstAudioTs != 0 {
		offset := int32(firstAudioTs) - int32(firstAccTs)
		fmt.Printf("First frame offset (AUDIO - ACC): %d μs\n", offset)
	}
}
