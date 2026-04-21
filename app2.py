import os
import json
import sys
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename

try:
    from pypdf import PdfReader
    from docx import Document
except ImportError:
    print("[CRITICAL] Missing pypdf or python-docx")
    sys.exit(1)

from huggingface_hub import snapshot_download
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

load_dotenv()

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Configuración de LM Studio
LM_STUDIO_URL = "http://172.21.19.55:1234/v1/chat/completions"

# Configuración de carpetas
PORT = int(os.getenv("PUERTO_FLASK", 5050))
FOLDER_FUENTES = "fuentes"
FOLDER_DB = "db"
FOLDER_MODELOS = "modelos"
FOLDER_EMBEDDINGS = os.path.join(FOLDER_MODELOS, "embeddings")
PROCESSED_FILE = "procesados.json"
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'doc'}

for folder in [FOLDER_FUENTES, FOLDER_DB, FOLDER_MODELOS, FOLDER_EMBEDDINGS]:
    os.makedirs(folder, exist_ok=True)

def emit_log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    print(formatted_msg, flush=True)
    socketio.emit('admin_log', {'msg': formatted_msg})

def convertir_a_txt(filename):
    ruta_orig = os.path.join(FOLDER_FUENTES, filename)
    nombre_base = os.path.splitext(filename)[0]
    ruta_txt = os.path.join(FOLDER_FUENTES, f"{nombre_base}.txt")
    if os.path.exists(ruta_txt): return True
    ext = filename.rsplit('.', 1)[1].lower()
    try:
        if ext == 'pdf':
            reader = PdfReader(ruta_orig)
            texto = "".join([p.extract_text() + "\n" for p in reader.pages if p.extract_text()])
            with open(ruta_txt, "w", encoding="utf-8") as f: f.write(texto)
        elif ext in ['docx', 'doc']:
            doc = Document(ruta_orig)
            texto = "\n".join([p.text for p in doc.paragraphs])
            with open(ruta_txt, "w", encoding="utf-8") as f: f.write(texto)
        return True
    except Exception as e:
        emit_log(f"[ERROR] {filename}: {str(e)}")
        return False

embeddings = None
vectorstore = None
detener_generacion = False

def inicializar_sistema():
    global embeddings, vectorstore
    emit_log("[SYSTEM] Conectando con servicios de búsqueda...")
    
    # CAMBIO: Modelo de embeddings de nivel Enterprise (BGE-M3)
    # Es infinitamente superior en comprensión semántica al MiniLM.
    REPO_EMBEDDINGS = "BAAI/bge-m3"
    
    if not os.path.exists(os.path.join(FOLDER_EMBEDDINGS, "config.json")):
        emit_log("[INFO] Descargando modelo de embeddings avanzado (BGE-M3)...")
        try:
            snapshot_download(
                repo_id=REPO_EMBEDDINGS, 
                local_dir=FOLDER_EMBEDDINGS,
                token=os.getenv("HF_TOKEN")
            )
            emit_log("[INFO] Descarga completada exitosamente.")
        except Exception as e:
            emit_log(f"[ERROR] Fallo en descarga de embeddings: {e}")
            sys.exit(1)
    
    os.environ['HF_HUB_OFFLINE'] = '1'
    
    emit_log("[SYSTEM] Cargando modelo vectorial pesado en memoria...")
    embeddings = HuggingFaceEmbeddings(
        model_name=FOLDER_EMBEDDINGS, 
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True, 'batch_size': 32}
    )
    
    vectorstore = Chroma(persist_directory=FOLDER_DB, embedding_function=embeddings)
    emit_log("[SYSTEM] Retriever semántico listo. Inferencia delegada a LM Studio.")

def actualizar_db():
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r") as f: procesados = json.load(f)
    else: procesados = []
    
    fuentes = os.listdir(FOLDER_FUENTES)
    for f in fuentes:
        if f.rsplit('.', 1)[1].lower() in ['pdf', 'docx', 'doc']: convertir_a_txt(f)
    
    txts = [f for f in os.listdir(FOLDER_FUENTES) if f.endswith('.txt')]
    nuevos = [f for f in txts if f not in procesados]
    
    if nuevos:
        # CAMBIO: Fragmentos más pequeños y superposición ajustada. 
        # Esto evita mezclar contextos y hace la búsqueda más "quirúrgica".
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
        for archivo in nuevos:
            try:
                loader = TextLoader(os.path.join(FOLDER_FUENTES, archivo), encoding='utf-8')
                vectorstore.add_documents(splitter.split_documents(loader.load()))
                procesados.append(archivo)
            except Exception as e: emit_log(f"[ERROR] {archivo}: {e}")
        with open(PROCESSED_FILE, "w") as f: json.dump(procesados, f)
        emit_log("[INFO] Base de datos sincronizada y vectorizada.")

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/archivos')
def listar_archivos():
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r") as f: procesados = json.load(f)
    else: procesados = []
    
    todos_archivos = os.listdir(FOLDER_FUENTES)
    resultado = []
    for f in todos_archivos:
        nombre_base = os.path.splitext(f)[0]
        es_txt = f.endswith('.txt')
        estado = "Indexado" if (f in procesados or f"{nombre_base}.txt" in procesados) else "Pendiente"
        if not es_txt: resultado.append({"nombre": f, "estado": estado})
            
    return jsonify({"archivos": resultado})

@app.route('/api/subir', methods=['POST'])
def subir_archivo():
    file = request.files['file']
    filename = secure_filename(file.filename)
    file.save(os.path.join(FOLDER_FUENTES, filename))
    actualizar_db()
    return jsonify({"status": "ok"})

@app.route('/api/borrar', methods=['POST'])
def borrar_archivo():
    nombre_archivo = request.json.get('nombre')
    if not nombre_archivo: return jsonify({"error": "Nombre no proporcionado"}), 400

    emit_log(f"[SISTEMA] Solicitud de purga recibida para: {nombre_archivo}")
    procesados = []
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r") as f: procesados = json.load(f)
        
    nombre_base = os.path.splitext(nombre_archivo)[0]
    txt_name = f"{nombre_base}.txt"
    
    if nombre_archivo in procesados: procesados.remove(nombre_archivo)
    if txt_name in procesados: procesados.remove(txt_name)
        
    with open(PROCESSED_FILE, "w") as f: json.dump(procesados, f)

    ruta_orig = os.path.join(FOLDER_FUENTES, nombre_archivo)
    ruta_txt = os.path.join(FOLDER_FUENTES, txt_name)
    try:
        if os.path.exists(ruta_orig): os.remove(ruta_orig)
        if os.path.exists(ruta_txt): os.remove(ruta_txt)
    except Exception as e: emit_log(f"[WARN] Error borrando físico: {e}")

    try:
        ruta_para_chroma = os.path.join(FOLDER_FUENTES, txt_name)
        vectorstore._collection.delete(where={"source": ruta_para_chroma})
        emit_log("[INFO] Vectores purgados de ChromaDB exitosamente.")
    except Exception as e: emit_log(f"[WARN] ChromaDB Delete warning: {e}")

    return jsonify({"status": "ok"})

@app.route('/stop', methods=['POST'])
def stop():
    global detener_generacion
    detener_generacion = True
    return jsonify({"status": "ok"})

@app.route('/ask', methods=['POST'])
def ask():
    global detener_generacion
    detener_generacion = False
    
    pregunta_original = request.json.get("pregunta", "")
    historial = request.json.get("historial", []) 

    emit_log(f"[USER] Consulta entrante: '{pregunta_original}'")
    
    # --- FASE 0: QUERY EXPANSION / HyDE ---
    # CAMBIO VITAL: Ahora no pedimos palabras clave, pedimos un párrafo experto.
    # Los vectores encuentran coincidencias asombrosas cuando comparas "párrafo experto" vs "documentación".
    emit_log("[INFO] Fase 0: Aplicando Expansión Contextual (HyDE)...")
    
    prompt_expansion = (
        "Eres un experto analista. El usuario hará una pregunta. "
        "Tu tarea es reescribir esta pregunta como si fuera un párrafo formal extraído "
        "directamente de un manual técnico o documentación oficial que responda a esa pregunta. "
        "Expande los conceptos con sinónimos técnicos profesionales. "
        "NO converses. Responde ÚNICAMENTE con el párrafo hipotético ampliado."
    )
    
    payload_rewrite = {
        "messages": [
            {"role": "system", "content": prompt_expansion},
            {"role": "user", "content": pregunta_original}
        ],
        "temperature": 0.4, 
        "max_tokens": 150,
        "stream": False 
    }
    
    consulta_limpia = pregunta_original
    try:
        res_rewrite = requests.post(LM_STUDIO_URL, json=payload_rewrite, timeout=15)
        if res_rewrite.status_code == 200:
            consulta_limpia = res_rewrite.json()['choices'][0]['message']['content'].strip()
            emit_log(f"[DEBUG] Expansión semántica generada:\n{consulta_limpia}")
    except Exception as e:
        emit_log(f"[WARN] Fallo en Query Expansion. Usando consulta original. Error: {e}")

    # --- FASE 1: BÚSQUEDA VECTORIAL ---
    emit_log("[INFO] Fase 1: Escaneando base de datos vectorial con la expansión...")
    start_time = time.perf_counter()
    # CAMBIO: Buscamos 8 fragmentos (k=8) ya que los hicimos más pequeños (800 caracteres).
    docs = vectorstore.similarity_search(consulta_limpia, k=8) 
    
    emit_log(f"[INFO] Fase 2: {len(docs)} fragmentos quirúrgicos extraídos. Preparando inferencia.")

    texto_contexto = ""
    contextos_formateados = []
    for d in docs:
        titulo = os.path.basename(d.metadata.get('source', 'Desconocido'))
        contextos_formateados.append({"titulo": titulo, "contenido": d.page_content})
        texto_contexto += f"--- DOC: {titulo} ---\n{d.page_content}\n\n"
    
    # --- FASE 3: PREPARACIÓN DEL ENVÍO FINAL ---
    mensajes_finales = [
        {
            "role": "user", 
            "content": (
                "INSTRUCCIONES DE COMPORTAMIENTO:\n"
                "Eres un asistente experto en análisis documental y síntesis de información. "
                "Tu objetivo es responder basándote ÚNICAMENTE en el contexto proporcionado. "
                "1. FIDELIDAD ABSOLUTA: Cero alucinaciones...\n"
                "2. SÍNTESIS INTELIGENTE...\n"
                "(...resto de tus reglas...)\n\n"
                f"CONTEXTO DE BASE DE DATOS:\n{texto_contexto}\n\n"
                f"PREGUNTA DEL USUARIO: {pregunta_original}"
            )
        }
    ]
    
    for msg in historial[-4:]: # Limitamos el historial a los últimos 4 mensajes para no diluir la memoria
        mensajes_finales.append({"role": msg["role"], "content": msg["content"]})
        
    mensajes_finales.append({
        "role": "user", 
        "content": f"CONTEXTO DE BASE DE DATOS:\n{texto_contexto}\n\nPREGUNTA DEL USUARIO: {pregunta_original}"
    })

    payload = {
        "messages": mensajes_finales,
        "temperature": 0.2, # Ligeramente más bajo para RAG preciso pero articulado
        "max_tokens": 2048, 
        "stream": True
    }

    def generar():
        yield json.dumps({"tipo": "contexto", "datos": contextos_formateados}) + "\n"
        emit_log("[INFO] Fase 3: Transmitiendo datos a LM Studio...")
        
        stream_start_time = time.perf_counter()
        ttft_reached = False
        ttft = 0 
        token_count = 0
        
        try:
            response = requests.post(LM_STUDIO_URL, json=payload, stream=True, timeout=None)
            for line in response.iter_lines():
                if detener_generacion: 
                    emit_log("[WARN] Inferencia detenida por el usuario.")
                    break
                    
                if line:
                    line_text = line.decode('utf-8')
                    if line_text.startswith("data: "):
                        data_str = line_text[6:]
                        if data_str == "[DONE]": break
                        
                        try:
                            data_json = json.loads(data_str)
                            choices = data_json.get('choices', [])
                            if choices:
                                chunk = choices[0].get('delta', {}).get('content', '')
                                if chunk:
                                    if not ttft_reached:
                                        ttft = time.perf_counter() - stream_start_time
                                        emit_log(f"[PERF] Primer token en {ttft:.2f} s.")
                                        ttft_reached = True
                                    token_count += 1
                                    if token_count % 50 == 0:
                                        emit_log(f"[INFO] Generando: {token_count} tokens...")
                                    yield json.dumps({"tipo": "chunk", "texto": chunk}) + "\n"
                        except Exception:
                            pass 
            
            total_time = time.perf_counter() - stream_start_time
            gen_time = total_time - ttft 
            tps = token_count / gen_time if gen_time > 0 else 0 
            emit_log(f"[PERF] Completado. Velocidad: {tps:.2f} tokens/s")
            
        except Exception as e: emit_log(f"[ERROR] Conexión LM Studio: {e}")

    return Response(generar(), mimetype='application/x-ndjson')

if __name__ == '__main__':
    emit_log("[SISTEMA] Entorno verificado. Iniciando Sentinel RAG Avanzado...")
    inicializar_sistema()
    actualizar_db()
    from werkzeug.serving import run_simple
    run_simple('0.0.0.0', PORT, app, threaded=True)