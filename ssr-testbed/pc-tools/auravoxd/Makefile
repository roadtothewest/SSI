# Desde la red AuraVox; en otra red: make deploy PI=aura@<IP>
PI ?= aura@auravox.lan

# Binario para esta máquina (pruebas con -src sim).
build:
	go build -o auravoxd .

# Raspberry Pi OS de 64 bits (uname -m = aarch64). Para 32 bits (armv7l): make build-pi ARCH=arm
ARCH ?= arm64
build-pi:
	CGO_ENABLED=0 GOOS=linux GOARCH=$(ARCH) GOARM=7 go build -trimpath -ldflags "-s -w" -o dist/auravoxd .
	cp deploy/auravoxd.service deploy/install.sh deploy/auravox-dns.conf dist/

# Copia a la Pi e instala el servicio.
deploy: build-pi
	scp dist/* $(PI):/tmp/
	ssh -t $(PI) 'cd /tmp && sudo sh install.sh'

# Paquetes de Python del clasificador (onnxruntime + numpy) para la Pi, sin pip ni sudo en ella.
ml-lib:
	sh deploy/ml-lib.sh

deploy-ml-lib: ml-lib
	ssh $(PI) mkdir -p /home/aura/auravox/ml
	rsync -a --delete dist/ml-lib/ $(PI):/home/aura/auravox/ml/lib/

test:
	go vet ./... && go test ./...

.PHONY: build build-pi deploy ml-lib deploy-ml-lib test
