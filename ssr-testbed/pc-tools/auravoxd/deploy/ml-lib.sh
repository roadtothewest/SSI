#!/bin/sh
# Arma en dist/ml-lib los paquetes de Python del evaluador ONNX (onnxruntime + numpy y sus
# dependencias) para la Pi, sin pip ni internet en ella: se descargan las ruedas en este PC y
# se descomprimen. auravoxd las pone en PYTHONPATH desde <data>/ml/lib.
#
#   sh deploy/ml-lib.sh                       # Pi 5: Debian 13, Python 3.13, aarch64
#   PYVER=3.12 PLAT=manylinux_2_28_x86_64 sh deploy/ml-lib.sh   # otro destino
#
# Copiar a la Pi: make deploy-ml-lib (o scp -r dist/ml-lib aura@<pi>:/home/aura/auravox/ml/lib)
set -eu
PYVER=${PYVER:-3.13}
PLAT=${PLAT:-manylinux_2_28_aarch64}
OUT=${OUT:-dist/ml-lib}
WHL=$(mktemp -d)
trap 'rm -rf "$WHL"' EXIT

python3 -m pip download --quiet --only-binary=:all: --python-version "$PYVER" \
	--platform "$PLAT" --platform manylinux_2_17_"${PLAT##*_2_28_}" --platform manylinux2014_"${PLAT##*_2_28_}" \
	--implementation cp --dest "$WHL" onnxruntime numpy
rm -rf "$OUT" && mkdir -p "$OUT"
for w in "$WHL"/*.whl; do
	python3 -m zipfile -e "$w" "$OUT"
done
echo "$OUT: $(ls "$WHL" | wc -l) ruedas para Python $PYVER / $PLAT ($(du -sh "$OUT" | cut -f1))"
ls "$WHL"
