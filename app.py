from flask import Flask, Response, render_template_string, request, jsonify
import cv2
import serial
import threading
import time
import os

eventos = []
ruta = []
contador_img = 0
os.makedirs("rostros_detectados", exist_ok=True)

# MOVIMIENTO CONTINUO
movimiento_continuo = {
    "activo": False,
    "cmd": None,
    "thread": None
}
movimiento_lock = threading.Lock()

app = Flask(__name__)

# CONFIGURACION ARDUINO

PUERTO_ARDUINO = '/dev/ttyACM0'  

arduino = None

try:
    arduino = serial.Serial(PUERTO_ARDUINO, 9600, timeout=1)
    time.sleep(2)
    print("Arduino conectado")
except:
    print("Arduino NO conectado")

# DATOS


datos = {
    "temp": "--",
    "hum": "--",
    "gas": "--",
    "dist": "--"
}

persona_detectada = False

# MAPA / CROQUIS


MAPA_COLS = 41
MAPA_FILAS = 41
CENTRO = [MAPA_COLS // 2, MAPA_FILAS // 2] 
mapa = {
    "pos_x": CENTRO[0],     
    "pos_y": CENTRO[1],     
    "dir": 0,                 
    "celdas_visitadas": [],   
    "personas": [],          
}

mapa["celdas_visitadas"].append({"x": CENTRO[0], "y": CENTRO[1]})

PASO = 1

def actualizar_mapa(cmd):
    
    import math

    x = mapa["pos_x"]
    y = mapa["pos_y"]
    d = mapa["dir"]

    if cmd == "F":
        
        rad = math.radians(d)
        x += round(math.sin(rad)) * PASO
        y -= round(math.cos(rad)) * PASO  
    elif cmd == "B":
        rad = math.radians(d)
        x -= round(math.sin(rad)) * PASO
        y += round(math.cos(rad)) * PASO
    elif cmd == "L":
        d = (d - 90) % 360
    elif cmd == "R":
        d = (d + 90) % 360

    x = max(0, min(MAPA_COLS - 1, x))
    y = max(0, min(MAPA_FILAS - 1, y))

    mapa["pos_x"] = x
    mapa["pos_y"] = y
    mapa["dir"] = d

    celda = {"x": x, "y": y}
    visitadas = mapa["celdas_visitadas"]
    if not visitadas or visitadas[-1] != celda:
        visitadas.append(celda)

def _hilo_movimiento_continuo():

    while True:
        with movimiento_lock:
            activo = movimiento_continuo["activo"]
            cmd    = movimiento_continuo["cmd"]
        if not activo:
            break
        actualizar_mapa(cmd)
        if arduino and cmd:
            arduino.write((cmd + '\n').encode())
            arduino.flush()
        time.sleep(2)


def iniciar_movimiento_continuo(cmd):
    with movimiento_lock:
        movimiento_continuo["activo"] = True
        movimiento_continuo["cmd"]    = cmd
    t = threading.Thread(target=_hilo_movimiento_continuo, daemon=True)
    movimiento_continuo["thread"] = t
    t.start()


def detener_movimiento_continuo():
    with movimiento_lock:
        movimiento_continuo["activo"] = False
        movimiento_continuo["cmd"]    = None

camara = cv2.VideoCapture(0)

face = cv2.CascadeClassifier(
    '/home/lito/Documentos/openCv/haarcascade_frontalface_default.xml'
)

if face.empty():
    print("ERROR cargando Haar Cascade")
else:
    print("Haar Cascade cargado")

# LECTURA SERIAL

def leer_serial():

    if arduino is None:
        return

    while True:

        try:

            linea = arduino.readline().decode().strip()

            if linea.startswith("TEMP:"):
                datos["temp"] = linea.split(":")[1]

            elif linea.startswith("HUM:"):
                datos["hum"] = linea.split(":")[1]

            elif linea.startswith("GAS:"):
                datos["gas"] = linea.split(":")[1]

            elif linea.startswith("DIST:"):
                datos["dist"] = linea.split(":")[1]

        except:
            pass

# VIDEO

def generar_video():

    global persona_detectada, contador_img

    cara_anterior = False

    while True:

        success, frame = camara.read()

        if not success:
            continue

        gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        rostros = face.detectMultiScale(
            gris,
            scaleFactor=1.3,
            minNeighbors=5
        )

        cara_actual = len(rostros) > 0
        persona_detectada = cara_actual

        for (x, y, w, h) in rostros:

            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            cv2.putText(
                frame,
                "PERSONA DETECTADA",
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2
            )

        if cara_actual and not cara_anterior:

            timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
            nombre_archivo = f"rostros_detectados/face_{contador_img}_{timestamp}.jpg"
            cv2.imwrite(nombre_archivo, frame)

            eventos.append({
                "tipo": "cara_detectada",
                "imagen": nombre_archivo,
                "ruta_robot": list(mapa["celdas_visitadas"]),
                "hora": timestamp
            })

            mapa["personas"].append({
                "x": mapa["pos_x"],
                "y": mapa["pos_y"],
                "hora": timestamp
            })

            contador_img += 1
            print("Cara guardada:", nombre_archivo)

        cara_anterior = cara_actual

        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' +
            frame +
            b'\r\n'
        )

# HTML

HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Robot Rescatista</title>
<style>

* { box-sizing: border-box; }

body {
    background: #f4f6f9;
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 20px;
    text-align: center;
}

h1 { color: #1f2937; }

h2 { color: #374151; margin-top: 24px; }

.video {
    border-radius: 15px;
    box-shadow: 0 0 15px rgba(0,0,0,.2);
}

.panel {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 15px;
    margin-top: 20px;
}

.card {
    background: white;
    width: 180px;
    padding: 15px;
    border-radius: 15px;
    box-shadow: 0 0 10px rgba(0,0,0,.1);
}

.valor {
    font-size: 28px;
    font-weight: bold;
}

.estado {
    margin-top: 15px;
    font-size: 22px;
    font-weight: bold;
}

.ok    { color: green; }
.alerta{ color: red;   }

button {
    width: 90px;
    height: 60px;
    margin: 5px;
    border: none;
    border-radius: 12px;
    font-size: 22px;
    background: #2563eb;
    color: white;
    cursor: pointer;
    transition: transform .1s;
}

button:hover { transform: scale(1.05); }

/* ── Mapa ── */
.mapa-wrapper {
    display: inline-block;
    background: white;
    border-radius: 15px;
    box-shadow: 0 0 15px rgba(0,0,0,.15);
    padding: 16px 20px 12px;
    margin-top: 8px;
}

.mapa-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
    gap: 16px;
}

.mapa-toolbar span {
    font-size: 13px;
    color: #6b7280;
}

.leyenda {
    display: flex;
    gap: 14px;
    align-items: center;
    font-size: 12px;
    color: #374151;
}

.leyenda-item {
    display: flex;
    align-items: center;
    gap: 5px;
}

.dot-robot   { width:12px; height:12px; background:#2563eb; border-radius:50%; }
.dot-path    { width:12px; height:12px; background:#bfdbfe; border-radius:2px; }
.dot-persona { width:12px; height:12px; background:#ef4444; border-radius:50%; }
.dot-inicio  { width:12px; height:12px; background:#fbbf24; border-radius:2px; }

#btnResetMapa {
    width: auto;
    height: auto;
    padding: 5px 12px;
    font-size: 13px;
    background: #6b7280;
    border-radius: 8px;
}

canvas {
    display: block;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    image-rendering: pixelated;
}

.personas-lista {
    text-align: left;
    margin-top: 16px;
    max-height: 160px;
    overflow-y: auto;
    font-size: 13px;
    color: #374151;
}

.personas-lista h3 {
    margin: 0 0 8px;
    font-size: 14px;
    color: #1f2937;
}

.persona-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 0;
    border-bottom: 1px solid #f3f4f6;
}

.persona-item .badge {
    background: #ef4444;
    color: white;
    border-radius: 50%;
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    flex-shrink: 0;
}

/* ── Movimiento continuo ── */
#estadoMovimiento {
    display: inline-block;
    margin-top: 8px;
    padding: 5px 16px;
    border-radius: 20px;
    font-size: 14px;
    font-weight: bold;
    background: #e5e7eb;
    color: #6b7280;
    transition: background .3s, color .3s;
}
#estadoMovimiento.activo {
    background: #dcfce7;
    color: #16a34a;
    animation: pulso 1.2s infinite;
}
@keyframes pulso {
    0%,100% { opacity:1; }
    50%      { opacity:.6; }
}

button.btn-stop {
    background: #dc2626;
}
button.btn-stop:hover { background: #b91c1c; }

/* ── Galería de capturas ── */
.galeria-section {
    margin-top: 30px;
}

.galeria-grid {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 12px;
    margin-top: 12px;
}

.galeria-card {
    background: white;
    border-radius: 12px;
    box-shadow: 0 0 10px rgba(0,0,0,.1);
    padding: 8px;
    width: 160px;
    text-align: center;
}

.galeria-card img {
    width: 144px;
    height: 108px;
    object-fit: cover;
    border-radius: 8px;
    border: 1px solid #e5e7eb;
}

.galeria-card .cap-nombre {
    font-size: 11px;
    color: #6b7280;
    margin-top: 5px;
    word-break: break-all;
}

#sinCapturas {
    color: #9ca3af;
    font-style: italic;
    margin-top: 8px;
}

</style>
</head>
<body>

<h1>Robot Rescatista</h1>

<img class="video" src="/video" width="640">

<div id="estadoPersona" class="estado">Sin detección</div>

<div class="panel">
    <div class="card"><h3>Temperatura</h3><div id="temp" class="valor">--</div></div>
    <div class="card"><h3>Humedad</h3>   <div id="hum"  class="valor">--</div></div>
    <div class="card"><h3>Gas</h3>        <div id="gas"  class="valor">--</div></div>
    <div class="card"><h3>Distancia</h3>  <div id="dist" class="valor">--</div></div>
</div>

<h2>Movimiento</h2>

<button onclick="enviarMovimiento('F')">↑</button><br>
<button onclick="enviarMovimiento('L')">←</button>
<button class="btn-stop" onclick="enviarStop()">■</button>
<button onclick="enviarMovimiento('R')">→</button><br>
<button onclick="enviarMovimiento('B')">↓</button>

<div id="estadoMovimiento">Detenido</div>

<h2>Cámara</h2>
<button onclick="enviar('CL')">⟲</button>
<button onclick="enviar('CR')">⟳</button>

<!--  Ultimas 5 capturas personas   -->

<div class="galeria-section">
    <h2>Últimas 5 Capturas</h2>
    <div id="galeriaGrid" class="galeria-grid">
        <span id="sinCapturas">Aún no hay capturas</span>
    </div>
</div>

<!-- Mapa -->

<h2>Croquis de Exploración</h2>

<div class="mapa-wrapper">

    <div class="mapa-toolbar">
        <div class="leyenda">
            <div class="leyenda-item"><div class="dot-inicio"></div>  Inicio</div>
            <div class="leyenda-item"><div class="dot-path"></div>    Recorrido</div>
            <div class="leyenda-item"><div class="dot-robot"></div>   Robot</div>
            <div class="leyenda-item"><div class="dot-persona"></div> Persona</div>
        </div>
        <button id="btnResetMapa" onclick="resetMapa()">Reiniciar mapa</button>
    </div>

    <canvas id="mapaCanvas" width="500" height="500"></canvas>

    <div class="personas-lista" id="listaPersonas">
        <h3>Personas detectadas</h3>
        <div id="personasItems"><em style="color:#9ca3af">Ninguna aún</em></div>
    </div>

</div>

<script>

//  SENSORES Y ESTADO

function enviar(cmd) {
    fetch('/comando?cmd=' + cmd);
}

//  MOVIMIENTO CONTINUO

let movimientoActivo = false;

function enviarMovimiento(cmd) {
    // Parar cualquier intervalo local previo
    movimientoActivo = true;
    fetch('/comando?cmd=' + cmd);
    let etiqueta = cmd === 'F' ? '▲ Avanzando...' : '▼ Retrocediendo...';
    let el = document.getElementById('estadoMovimiento');
    el.textContent = etiqueta;
    el.classList.add('activo');
}

function enviarStop() {
    movimientoActivo = false;
    fetch('/comando?cmd=S');
    let el = document.getElementById('estadoMovimiento');
    el.textContent = 'Detenido';
    el.classList.remove('activo');
}

function actualizar() {
    fetch('/sensores')
    .then(r => r.json())
    .then(data => {
        document.getElementById("temp").innerHTML = data.temp;
        document.getElementById("hum").innerHTML  = data.hum;
        document.getElementById("gas").innerHTML  = data.gas;
        document.getElementById("dist").innerHTML = data.dist;

        let estado = document.getElementById("estadoPersona");
        if (data.persona) {
            estado.innerHTML   = "⚠ PERSONA DETECTADA";
            estado.className   = "estado alerta";
        } else {
            estado.innerHTML   = "Sin detección";
            estado.className   = "estado ok";
        }
    });
}

setInterval(actualizar, 1000);
actualizar();

//  GALERÍA DE CAPTURAS

function actualizarGaleria() {
    fetch('/capturas')
    .then(r => r.json())
    .then(capturas => {
        let grid = document.getElementById('galeriaGrid');
        if (capturas.length === 0) {
            grid.innerHTML = '<span id="sinCapturas">Aún no hay capturas</span>';
            return;
        }
        grid.innerHTML = capturas.map(c => `
            <div class="galeria-card">
                <img src="data:image/jpeg;base64,${c.data}" alt="${c.nombre}">
                <div class="cap-nombre">${c.nombre}</div>
            </div>
        `).join('');
    });
}

setInterval(actualizarGaleria, 3000);
actualizarGaleria();

//  MAPA

const canvas = document.getElementById("mapaCanvas");
const ctx    = canvas.getContext("2d");

// Tamaño de celda en px (500px / 41 celdas ≈ 12px)
const CELDA  = Math.floor(canvas.width / 41);
const OFFSET = (canvas.width - CELDA * 41) / 2;

function celdaAPx(c) {
    return OFFSET + c * CELDA;
}

function dibujarMapa(mapaData) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Fondo gris muy suave
    ctx.fillStyle = "#f9fafb";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Grid tenue
    ctx.strokeStyle = "#e5e7eb";
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 41; i++) {
        let p = OFFSET + i * CELDA;
        ctx.beginPath(); ctx.moveTo(p, OFFSET); ctx.lineTo(p, OFFSET + 41 * CELDA); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(OFFSET, p); ctx.lineTo(OFFSET + 41 * CELDA, p); ctx.stroke();
    }

    const visitadas = mapaData.celdas_visitadas;
    const personas  = mapaData.personas;
    const cx        = mapaData.pos_x;
    const cy        = mapaData.pos_y;
    const dir       = mapaData.dir;

    // Celda inicial 
    if (visitadas.length > 0) {
        let ini = visitadas[0];
        ctx.fillStyle = "#fde68a";
        ctx.fillRect(celdaAPx(ini.x) + 1, celdaAPx(ini.y) + 1, CELDA - 2, CELDA - 2);
    }

    // Camino recorrido
    ctx.fillStyle = "#bfdbfe";
    for (let i = 1; i < visitadas.length; i++) {
        let v = visitadas[i];
        ctx.fillRect(celdaAPx(v.x) + 1, celdaAPx(v.y) + 1, CELDA - 2, CELDA - 2);
    }

    // Linea del recorrido
    if (visitadas.length > 1) {
        ctx.strokeStyle = "#93c5fd";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(celdaAPx(visitadas[0].x) + CELDA/2, celdaAPx(visitadas[0].y) + CELDA/2);
        for (let i = 1; i < visitadas.length; i++) {
            ctx.lineTo(celdaAPx(visitadas[i].x) + CELDA/2, celdaAPx(visitadas[i].y) + CELDA/2);
        }
        ctx.stroke();
    }

    // Personas detectadas 
    personas.forEach((p, idx) => {
        let px = celdaAPx(p.x) + CELDA / 2;
        let py = celdaAPx(p.y) + CELDA / 2;
        ctx.beginPath();
        ctx.arc(px, py, CELDA * 0.55, 0, Math.PI * 2);
        ctx.fillStyle = "#ef4444";
        ctx.fill();
        ctx.strokeStyle = "white";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.fillStyle = "white";
        ctx.font = "bold " + Math.max(8, CELDA * 0.55) + "px Arial";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(idx + 1, px, py);
    });

    // Robot (triangulo apuntando en la direccion actual)
    let rx = celdaAPx(cx) + CELDA / 2;
    let ry = celdaAPx(cy) + CELDA / 2;
    let r  = CELDA * 0.55;
    let angleRad = dir * Math.PI / 180;

    ctx.save();
    ctx.translate(rx, ry);
    ctx.rotate(angleRad);
    ctx.beginPath();
    ctx.moveTo(0, -r);
    ctx.lineTo(r * 0.65, r * 0.65);
    ctx.lineTo(-r * 0.65, r * 0.65);
    ctx.closePath();
    ctx.fillStyle = "#2563eb";
    ctx.fill();
    ctx.strokeStyle = "white";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.restore();

    // Actualizar lista de personas
    actualizarListaPersonas(personas);
}

function actualizarListaPersonas(personas) {
    let cont = document.getElementById("personasItems");
    if (personas.length === 0) {
        cont.innerHTML = '<em style="color:#9ca3af">Ninguna aún</em>';
        return;
    }
    cont.innerHTML = personas.map((p, i) =>
        `<div class="persona-item">
            <div class="badge">${i + 1}</div>
            <span>Celda (${p.x}, ${p.y}) &mdash; ${p.hora}</span>
        </div>`
    ).join("");
}

function actualizarMapa() {
    fetch('/mapa')
    .then(r => r.json())
    .then(data => dibujarMapa(data));
}

function resetMapa() {
    fetch('/mapa/reset', { method: 'POST' })
    .then(() => actualizarMapa());
}

// Dibujar mapa inicial vacio
dibujarMapa({
    pos_x: 20, pos_y: 20, dir: 0,
    celdas_visitadas: [{ x: 20, y: 20 }],
    personas: []
});

setInterval(actualizarMapa, 1000);

</script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/video')
def video():
    return Response(
        generar_video(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/sensores')
def sensores():
    return jsonify({
        "temp":   datos["temp"],
        "hum":    datos["hum"],
        "gas":    datos["gas"],
        "dist":   datos["dist"],
        "persona": persona_detectada
    })

@app.route('/comando')
def comando():
    cmd = request.args.get('cmd')

    if cmd == 'S':

        detener_movimiento_continuo()
        if arduino:
            arduino.write(('S\n').encode())
            arduino.flush()
        return "OK"

    if cmd in ('F', 'B'):

        detener_movimiento_continuo()

        time.sleep(0.05)  
        actualizar_mapa(cmd)

        if arduino:
            arduino.write((cmd + '\n').encode())
            arduino.flush()
        iniciar_movimiento_continuo(cmd)
        return "OK"


    if arduino and cmd:
        print("ENVIANDO:", cmd)
        arduino.write((cmd + '\n').encode())
        arduino.flush()

    if cmd in ('L', 'R'):
        actualizar_mapa(cmd)

    return "OK"

@app.route('/capturas')
def get_capturas():

    import glob, base64

    archivos = sorted(glob.glob("rostros_detectados/*.jpg"), key=os.path.getmtime, reverse=True)
    ultimas  = archivos[:5]
    resultado = []

    for ruta_img in ultimas:
        with open(ruta_img, "rb") as f:
            datos_b64 = base64.b64encode(f.read()).decode()
        nombre = os.path.basename(ruta_img)
        resultado.append({"nombre": nombre, "data": datos_b64})
    return jsonify(resultado)



def get_mapa():
    return jsonify({
        "pos_x":            mapa["pos_x"],
        "pos_y":            mapa["pos_y"],
        "dir":              mapa["dir"],
        "celdas_visitadas": mapa["celdas_visitadas"],
        "personas":         mapa["personas"]
    })

@app.route('/mapa/reset', methods=['POST'])
def reset_mapa():
    mapa["pos_x"] = CENTRO[0]
    mapa["pos_y"] = CENTRO[1]
    mapa["dir"]   = 0
    mapa["celdas_visitadas"] = [{"x": CENTRO[0], "y": CENTRO[1]}]
    mapa["personas"] = []
    return "OK"

# HILO SERIAL

threading.Thread(target=leer_serial, daemon=True).start()

# INICIO

app.run(host='0.0.0.0', port=5000, threaded=True)