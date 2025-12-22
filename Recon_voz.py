import sys
import json
import time
import csv
import math
from datetime import datetime
import audioop
from vosk import Model, KaldiRecognizer, SpkModel # Importamos SpkModel
import pyaudio
import os

import threading
from deep_translator import GoogleTranslator
from gtts import gTTS

# --- CONFIGURACION NUEVA ---
# Aqui ponemos el ID 1 que te dio el script de busqueda
INDICE_MICROFONO = 1
INPUT_RATE = 44100   # Tasa que le gusta al USB (44.1kHz)
VOSK_RATE = 16000    # Tasa que necesita Vosk (16kHz)

print("Cargando modelos (Voz y Hablantes)...")

try:
    model = Model("model-es") 
    spk_model = SpkModel("model-spk")
except Exception as e:
    print(f"Error cargando modelos: {e}")
    sys.exit()

rec = KaldiRecognizer(model, VOSK_RATE, spk_model)

p = pyaudio.PyAudio()

print(f"Abriendo microfono ID {INDICE_MICROFONO} a {INPUT_RATE}Hz...")

try:
    stream = p.open(format=pyaudio.paInt16, 
                    channels=1, 
                    rate=INPUT_RATE, 
                    input=True, 
                    input_device_index=INDICE_MICROFONO,
                    frames_per_buffer=4096)
except Exception as e:
    print(f"\n[ERROR] Fallo al abrir a {INPUT_RATE}Hz. Intentando con 48000Hz...")
    try:
        # Si 44100 falla, probamos 48000 (el otro estandar)
        INPUT_RATE = 48000
        stream = p.open(format=pyaudio.paInt16, 
                        channels=1, 
                        rate=INPUT_RATE, 
                        input=True, 
                        input_device_index=INDICE_MICROFONO,
                        frames_per_buffer=4096)
    except Exception as e2:
        print(f"\n[ERROR FATAL] El microfono no acepta ni 44.1k ni 48k.")
        print(f"Error: {e2}")
        sys.exit()

stream.start_stream()


subtitulo_actual = ""
momento_ultima_palabra = time.time()

known_speakers = [] 
speaker_names = []

def get_distance(vec1, vec2):
    dot_product = sum(a*b for a, b in zip(vec1, vec2))
    norm_a = math.sqrt(sum(a*a for a in vec1))
    norm_b = math.sqrt(sum(b*b for b in vec2)) 
    return 1 - (dot_product / (norm_a * norm_b))

def identificar_hablante(vector_voz):
    umbral = 0.85 
    best_dist = 100
    speaker_idx = -1

    for i, known_vec in enumerate(known_speakers):
        dist = get_distance(vector_voz, known_vec)
        if dist < best_dist:
            best_dist = dist
            speaker_idx = i

    if speaker_idx != -1:
        print(f"   (Diferencia con {speaker_names[speaker_idx]}: {best_dist:.4f})")
    
    if best_dist < umbral and speaker_idx != -1:
        return speaker_names[speaker_idx]
    else:
        new_name = f"Hablante {len(known_speakers) + 1}"
        known_speakers.append(vector_voz)
        speaker_names.append(new_name)
        return new_name

frecuencia_palabras = {}
tiempo_inicio = time.time()


def actualizar_frecuencias(texto):
    palabras = texto.lower().split()
    for p in palabras:
        p = p.strip(".,;:Â¿?Â¡!()\"'")
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

def narrar_traduccion(texto_original, hablante):
    try:
        traductor = GoogleTranslator(source='es', target='en')
        texto_ingles = traductor.translate(texto_original)
        
        print(f"   >>> [Traduccion]: {texto_ingles}")
        
        tts = gTTS(text=texto_ingles, lang='en', slow=False)
        
        nombre_mp3 = f"temp_{int(time.time()*1000)}.mp3"
        tts.save(nombre_mp3)
        
        os.system(f"mpg123 -q {nombre_mp3}")
        
        os.remove(nombre_mp3)

    except Exception as e:
        print(f"[Error Traductor]: {e}")
        
print("Habla cuando quieras (Detectando hablantes...):\n")

        
while True:
    try:
        # 1. Leer datos raw del microfono
        data = stream.read(4096, exception_on_overflow=False)
        
        # 2. CONVERSION IMPORTANTE: De 44100Hz a 16000Hz
        # Sin esta linea, Vosk no entendera nada
        data, _ = audioop.ratecv(data, 2, 1, INPUT_RATE, VOSK_RATE, None)

        if rec.AcceptWaveform(data):
            resultado = json.loads(rec.Result())
            texto = resultado.get("text", "").strip()

            spk_vector = resultado.get("spk")

            if texto:
                nombre_hablante = "Desconocido"

                if spk_vector:
                    nombre_hablante = identificar_hablante(spk_vector)

                print(f"\n[{nombre_hablante}]: {texto}")
            
                actualizar_frecuencias(texto)
                t = threading.Thread(target=narrar_traduccion, args=(texto, nombre_hablante))
                t.start()
                subtitulo_actual = ""      
                print("")

        else:
            parcial = json.loads(rec.PartialResult())
            texto = parcial.get("partial", "").strip()

            if texto:
                subtitulo_actual = texto
                sys.stdout.write("\r" + "..." + subtitulo_actual + " " * 20)
                sys.stdout.flush()
                momento_ultima_palabra = time.time()

        if time.time() - tiempo_inicio >= 60:
            generar_csv()
            frecuencia_palabras.clear()
            tiempo_inicio = time.time()

    except KeyboardInterrupt:
            print("\nSaliendo...")
            break
