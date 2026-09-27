"""Vista previa PNG de un esquematico .asc (cables, simbolos, etiquetas) para documentacion
y revision sin abrir LTspice.  Uso: python3 tools/render_asc.py CANAL.asc salida.png"""
import os, re, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle

HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
LIB = os.path.expanduser('~/.wine/drive_c/users/%s/AppData/Local/LTspice/lib/sym' % os.environ.get('USER', ''))
ROT = {'R0': lambda x, y: (x, y), 'R90': lambda x, y: (-y, x), 'R180': lambda x, y: (-x, -y), 'R270': lambda x, y: (y, -x)}
INK, WIRE, SYM, LAB, NOTE = '#0b0b0b', '#1c5cab', '#52514e', '#b8450f', '#6d6c68'


def load_sym(name):
    name = name.replace('\\\\', '/').replace('\\', '/')
    for base in (HERE, LIB):
        p = os.path.join(base, name + '.asy')
        if os.path.exists(p):
            return open(p, encoding='latin-1').read().splitlines()
    return []


def render(asc, png):
    lines = open(os.path.join(HERE, asc), encoding='latin-1').read().splitlines()
    fig, ax = plt.subplots(figsize=(22, 9) if 'CANAL' in asc else (20, 16))
    pts = []
    cur = None
    for l in lines:
        t = l.split()
        if not t:
            continue
        if t[0] == 'WIRE':
            x1, y1, x2, y2 = map(int, t[1:5]); pts += [(x1, y1), (x2, y2)]
            ax.plot([x1, x2], [y1, y2], color=WIRE, lw=1.1)
        elif t[0] == 'FLAG':
            x, y, n = int(t[1]), int(t[2]), t[3]
            if n == '0':
                ax.plot([x - 10, x + 10], [y, y], color=INK, lw=1.2); ax.plot([x - 5, x + 5], [y + 5, y + 5], color=INK, lw=1)
            else:
                ax.text(x, y - 4, n, color=LAB, fontsize=6.5, ha='center', va='bottom', fontweight='bold')
                ax.plot([x], [y], 's', color=LAB, ms=2)
        elif t[0] == 'SYMBOL':
            if cur is not None:
                label(ax, cur)
            cur = {'sym': t[1], 'x': int(t[2]), 'y': int(t[3]), 'rot': t[4], 'name': '', 'value': ''}
            f = ROT.get(cur['rot'], ROT['R0'])
            for s in load_sym(t[1]):
                u = s.split()
                if not u:
                    continue
                if u[0] == 'LINE':
                    a = f(int(u[2]), int(u[3])); b = f(int(u[4]), int(u[5]))
                    ax.plot([cur['x'] + a[0], cur['x'] + b[0]], [cur['y'] + a[1], cur['y'] + b[1]], color=SYM, lw=1)
                elif u[0] == 'RECTANGLE':
                    a = f(int(u[2]), int(u[3])); b = f(int(u[4]), int(u[5]))
                    x0, y0 = cur['x'] + min(a[0], b[0]), cur['y'] + min(a[1], b[1])
                    ax.add_patch(Rectangle((x0, y0), abs(a[0] - b[0]), abs(a[1] - b[1]), fill=False, ec=SYM, lw=1))
                elif u[0] == 'CIRCLE':
                    a = f(int(u[2]), int(u[3])); b = f(int(u[4]), int(u[5]))
                    c = (cur['x'] + (a[0] + b[0]) / 2, cur['y'] + (a[1] + b[1]) / 2)
                    ax.add_patch(Circle(c, abs(a[0] - b[0]) / 2, fill=False, ec=SYM, lw=1))
                elif u[0] == 'TEXT' and cur['sym'] in ('CANAL', 'INA333'):
                    a = f(int(u[1]), int(u[2]))
                    ax.text(cur['x'] + a[0], cur['y'] + a[1], ' '.join(u[5:]), fontsize=6, color=SYM,
                            ha='center' if u[3] == 'Center' else 'left', va='center')
        elif t[0] == 'SYMATTR' and cur is not None:
            if t[1] == 'InstName':
                cur['name'] = t[2]
            elif t[1] == 'Value':
                cur['value'] = ' '.join(t[2:])
            elif t[1] == 'SpiceLine':
                cur['value'] += ' ' + ' '.join(t[2:])
            if t[1] in ('InstName', 'Value', 'SpiceLine'):
                pass
        elif t[0] == 'TEXT':
            x, y = int(t[1]), int(t[2]); s = ' '.join(t[5:])
            d = s.startswith('!')
            ax.text(x, y, s[1:].replace('\\n', '\n'), fontsize=6.5 if d else 7.5, color=INK if d else NOTE,
                    family='monospace' if d else None, va='top', fontweight='normal' if d else 'bold')
        if t[0] in ('SYMBOL', 'TEXT', 'WIRE', 'FLAG', 'IOPIN') and cur is not None and t[0] != 'SYMBOL':
            label(ax, cur); cur = None
    if cur is not None:
        label(ax, cur)
    ax.set_aspect('equal'); ax.invert_yaxis(); ax.axis('off')
    fig.savefig(png, dpi=110, bbox_inches='tight', facecolor='#fcfcfb')
    print('png', png)


def label(ax, c):
    v = c['value'] if len(c['value']) < 28 else c['value'][:26] + '..'
    if c['sym'] in ('CANAL',):
        ax.text(c['x'], c['y'] + 120, c['name'], fontsize=8, ha='center', color=INK, fontweight='bold'); return
    ax.text(c['x'] + 24, c['y'] + 4, f"{c['name']}\n{v}", fontsize=5.5, color=INK, va='top')


if __name__ == '__main__':
    render(sys.argv[1], sys.argv[2])
