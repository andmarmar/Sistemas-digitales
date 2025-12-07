import sys
import json
import time
import csv
import math
from datetime import datetime
from vosk import Model, KaldiRecognizer, SpkModel # Importamos SpkModel
import pyaudio

print("Cargando modelos (Voz y Hablantes)...")

# --- CARGA DE MODELOS ---
# Asegúrate de tener la carpeta 'model-es' y 'model-spk'
model = Model("model-es") 
spk_model = SpkModel("model-spk") # <--- NUEVO: Modelo de identidad de voz

# Añadimos el spk_model al reconocedor
rec = KaldiRecognizer(model, 16000, spk_model)

p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                input=True, frames_per_buffer=4096)
stream.start_stream()

subtitulo_actual = ""
momento_ultima_palabra = time.time()

# --- GESTIÓN DE HABLANTES ---
known_speakers = [] # Lista para guardar los vectores de voz de los hablantes encontrados
speaker_names = []  # Lista para guardar los nombres (Hablante 1, Hablante 2...)

# Función matemática simple para comparar voces (Distancia Coseno)
# Devuelve un valor entre 0 (misma persona) y 1 (persona muy distinta)
def get_distance(vec1, vec2):
    dot_product = sum(a*b for a, b in zip(vec1, vec2))
    norm_a = math.sqrt(sum(a*a for a in vec1))
    norm_b = math.sqrt(sum(b*b for b in vec2)) 
    return 1 - (dot_product / (norm_a * norm_b))

def identificar_hablante(vector_voz):
    umbral = 0.85  # Ajusta esto si confunde personas (0.3 estricto - 0.6 relajado)
    best_dist = 100
    speaker_idx = -1

    # Comparamos la voz actual con las que ya conocemos
    for i, known_vec in enumerate(known_speakers):
        dist = get_distance(vector_voz, known_vec)
        if dist < best_dist:
            best_dist = dist
            speaker_idx = i

    if speaker_idx != -1:
        print(f"   (Diferencia con {speaker_names[speaker_idx]}: {best_dist:.4f})")
    
    # Si la distancia es menor al umbral, es alguien conocido
    if best_dist < umbral and speaker_idx != -1:
        return speaker_names[speaker_idx]
    else:
        # Es alguien nuevo
        new_name = f"Hablante {len(known_speakers) + 1}"
        known_speakers.append(vector_voz)
        speaker_names.append(new_name)
        return new_name

# --- CONTADOR DE PALABRAS ---
frecuencia_palabras = {}
tiempo_inicio = time.time()

print("Habla cuando quieras (Detectando hablantes...):\n")

def actualizar_frecuencias(texto):
    palabras = texto.lower().split()
    for p in palabras:
        p = p.strip(".,;:¿?¡!()\"'")
        if p:
            frecuencia_palabras[p] = frecuencia_palabras.get(p, 0) + 1

def generar_csv():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    nombre_archivo = f"palabras_frecuencia_{timestamp}.csv"

    with open(nombre_archivo, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["palabra", "frecuencia"])
        for palabra, freq in sorted(frecuencia_palabras.items(), key=lambda x: -x[1]):
            writer.writerow([palabra, freq])
    
    print(f"\n[CSV generado] {nombre_archivo}\n")

while True:
    data = stream.read(4000, exception_on_overflow=False)

    # --- Comprobamos si terminó una frase ---
    if rec.AcceptWaveform(data):
        resultado = json.loads(rec.Result())
        texto = resultado.get("text", "").strip()
        
        # Obtenemos el vector de voz (spk) si existe
        spk_vector = resultado.get("spk")

        if texto:
            nombre_hablante = "Desconocido"
            
            # Si Vosk detectó un vector de voz, identificamos quién es
            if spk_vector:
                nombre_hablante = identificar_hablante(spk_vector)

            # Imprimimos con el formato: [Hablante X]: Texto
            print(f"\n[{nombre_hablante}]: {texto}")
            
            actualizar_frecuencias(texto)
            subtitulo_actual = ""      
            print("")
    else:
        # --- Texto parcial en tiempo real ---
        parcial = json.loads(rec.PartialResult())
        texto = parcial.get("partial", "").strip()

        if texto:
            subtitulo_actual = texto
            # Nota: No podemos identificar hablante en el parcial, solo al final
            sys.stdout.write("\r" + "..." + subtitulo_actual + " " * 20)
            sys.stdout.flush()
            momento_ultima_palabra = time.time()

    # --- Generar CSV cada 60 segundos ---
    if time.time() - tiempo_inicio >= 60:
        generar_csv()
        frecuencia_palabras.clear()
        tiempo_inicio = time.time()



