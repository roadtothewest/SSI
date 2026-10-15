# Evaluador ONNX de auravoxd: lo lanza ml.Runner y no sabe nada del preproceso.
#   argv[1] = modelo .onnx
#   salida:  una línea JSON con las entradas y salidas del modelo; después, por cada
#            pedido (u32 LE n + n bytes float32 LE con las entradas concatenadas en el
#            orden de "inputs"), responde u32 LE n + la primera salida en float32 LE.
import json
import struct
import sys

import numpy as np
import onnxruntime as ort


def read_exact(f, n):
    buf = b""
    while len(buf) < n:
        chunk = f.read(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def main():
    sess = ort.InferenceSession(sys.argv[1], providers=["CPUExecutionProvider"])
    ins, out = sess.get_inputs(), sess.get_outputs()[0]
    shapes = [[d if isinstance(d, int) else 1 for d in i.shape] for i in ins]
    sizes = [int(np.prod(s)) for s in shapes]
    head = {
        "inputs": [{"name": i.name, "shape": s} for i, s in zip(ins, shapes)],
        "output": {"name": out.name, "shape": out.shape},
        "ort": ort.__version__,
    }
    sys.stdout.write(json.dumps(head) + "\n")
    sys.stdout.flush()
    rd, wr = sys.stdin.buffer, sys.stdout.buffer
    while True:
        h = read_exact(rd, 4)
        if h is None:
            return
        body = read_exact(rd, struct.unpack("<I", h)[0])
        if body is None:
            return
        x = np.frombuffer(body, dtype="<f4")
        feeds, off = {}, 0
        for i, s, n in zip(ins, shapes, sizes):
            feeds[i.name] = x[off:off + n].reshape(s)
            off += n
        y = np.asarray(sess.run([out.name], feeds)[0], dtype="<f4").ravel()
        wr.write(struct.pack("<I", y.nbytes) + y.tobytes())
        wr.flush()


if __name__ == "__main__":
    main()
