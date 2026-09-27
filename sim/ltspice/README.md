# Simulación LTspice del AFE sEMG (4 canales)

Resultados, figuras y cómo abrir o correr todo: `docs/afe-emg/resultados_simulacion.md`.

Inicio rápido:

```bash
cd ~/SSI/sim/ltspice
wine "C:\Program Files\ADI\LTspice\LTspice.exe" AFE_4CH.asc     # esquemático (GUI)
wine "C:\Program Files\ADI\LTspice\LTspice.exe" -b t2_ac.cir    # una prueba en batch -> t2_ac.log
```

Si se modifica `tools/make_asc.py`, regenerar y verificar los esquemáticos:

```bash
python3 tools/make_asc.py && python3 tools/check_asc.py
```
