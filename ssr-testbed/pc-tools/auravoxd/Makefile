PI ?= aura@192.168.0.103

# Binario para esta máquina (pruebas con -src sim).
build:
	go build -o auravoxd .

# Raspberry Pi OS de 64 bits (uname -m = aarch64). Para 32 bits (armv7l): make build-pi ARCH=arm
ARCH ?= arm64
build-pi:
	CGO_ENABLED=0 GOOS=linux GOARCH=$(ARCH) GOARM=7 go build -trimpath -ldflags "-s -w" -o dist/auravoxd .
	cp deploy/auravoxd.service deploy/install.sh dist/

# Copia a la Pi e instala el servicio.
deploy: build-pi
	scp dist/* $(PI):/tmp/
	ssh -t $(PI) 'cd /tmp && sudo sh install.sh'

test:
	go vet ./... && go test ./...

.PHONY: build build-pi deploy test
