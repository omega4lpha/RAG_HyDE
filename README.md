# RAG SENTINEL: SISTEMA DE RECUPERACIÓN AUMENTADA POR GENERACIÓN

## 1. INTRODUCCIÓN
RAG Sentinel es una infraestructura de inteligencia artificial local diseñada para la consulta avanzada de documentos técnicos y corporativos. El sistema implementa una arquitectura RAG (Retrieval-Augmented Generation) que desacopla el almacenamiento de conocimiento masivo de la ventana de contexto del modelo de lenguaje (LLM), optimizando el uso de recursos computacionales y garantizando la precisión de las respuestas mediante la inyección de contexto verificado.

## 2. ARQUITECTURA TÉCNICA
El proyecto se fundamenta en una topología de tres capas:

### 2.1. CAPA DE INGESTA Y PERSISTENCIA (BACKEND)
* **Procesamiento de Documentos:** Extracción de texto desde formatos PDF, DOCX y TXT.
* **Segmentación (Chunking):** División estratégica de la información para preservar la semántica.
* **Vectorización (Embeddings):** Uso de modelos de HuggingFace para transformar texto en vectores matemáticos.
* **Base de Datos Vectorial:** Implementación de ChromaDB para el almacenamiento y búsqueda por similitud de coseno.

### 2.2. CAPA DE INFERENCIA (MOTOR LLM)
* **Integración Local:** Conexión mediante API REST con LM Studio.
* **Gestión de Contexto:** Implementación de KV Caching para la reducción de latencia en consultas recurrentes.
* **Streaming:** Procesamiento de respuestas token a token para mejorar la experiencia de usuario (Time To First Token optimizado).

### 2.3. CAPA DE INTERFAZ Y TELEMETRÍA (FRONTEND)
* **Renderizado:** Cliente web dinámico con soporte para Markdown (marked.js).
* **Protocolo de Comunicación:** Dualidad entre HTTP (Consultas) y WebSockets (Telemetría de sistema en tiempo real vía Socket.IO).
* **Mitigación de Red:** Implementación de buffers de reconstrucción para prevenir fallos por fragmentación de paquetes TCP.

## 3. DEPENDENCIAS DEL SISTEMA
El entorno de ejecución requiere las siguientes librerías core registradas en el manifiesto de dependencias:

| Librería | Propósito |
| :--- | :--- |
| flask | Framework de servidor web y routing API. |
| flask-socketio | Gestión de telemetría y logs bidireccionales en tiempo real. |
| requests | Cliente HTTP para la comunicación con el orquestador LM Studio. |
| langchain | Orquestación de la cadena RAG y el flujo de documentos. |
| chromadb | Motor de persistencia de vectores de alta velocidad. |
| sentence-transformers | Generación de embeddings locales (HuggingFace). |
| pypdf / python-docx | Parsers de archivos binarios a texto plano. |

## 4. GUÍA DE INSTALACIÓN Y DESPLIEGUE

### 4.1. PREPARACIÓN DEL ENTORNO VIRTUAL
Es imperativo el aislamiento de dependencias para evitar conflictos de binarios:

1. Creación del entorno:
   python -m venv .venv

2. Activación (PowerShell):
   .\.venv\Scripts\Activate.ps1

3. Instalación de paquetes:
   pip install -r requirements.txt

### 4.2. CONFIGURACIÓN DEL MOTOR DE INFERENCIA (LM STUDIO)
Para un rendimiento óptimo bajo esta arquitectura, se deben aplicar los siguientes parámetros en LM Studio:

* **Model Identifier:** google/gemma-4-e4b (o equivalente GGUF).
* **Context Length:** 4096 tokens (mínimo sugerido).
* **GPU Offload:** 0 (Cero) para arquitecturas de CPU híbrida (Intel P-Cores/E-Cores).
* **Enable Thinking:** Desactivado (Evita colisiones en el parseo JSON de la API).
* **Server Port:** 1234.

## 5. DECISIONES DE INGENIERÍA Y OPTIMIZACIÓN

### 5.1. ROBUSTEZ EN REDES DISTRIBUIDAS
Para permitir el acceso desde múltiples terminales en una red local (LAN):
* **Problema:** La fragmentación TCP rompía los objetos JSON en el streaming.
* **Solución:** Se implementó un buffer en JavaScript que acumula datos hasta detectar el delimitador de línea (\n) antes de intentar el parseo JSON.

### 5.2. TELEMETRÍA AVANZADA
El sistema reporta métricas críticas a la terminal integrada:
* **TTFT (Time To First Token):** Mide la latencia de procesamiento del prompt.
* **TPS (Tokens Per Second):** Mide el rendimiento de generación del modelo.
* **Logs de Sistema:** Notificación de estados de ingesta, errores de conexión y purga de vectores.

## 6. MANUAL DE OPERACIÓN

### 6.1. INGESTA DE DOCUMENTOS
1. Seleccionar archivo mediante el componente custom-file-upload.
2. Ejecutar "Subir e Indexar". El sistema generará una versión .txt, la fragmentará y almacenará los vectores en ChromaDB.
3. El archivo aparecerá en la lista con estado "Indexado" y podrá ser eliminado mediante el botón de purga (X).

### 6.2. CONSULTAS
* Las consultas se envían mediante la tecla Enter o el botón de ejecución.
* El sistema recupera automáticamente el contexto más relevante y lo presenta en cuadros de referencia antes de la respuesta de la IA.


## 7. NOTA FINAL DE DESARROLLO
Este proyecto representa la integración exitosa de tecnologías de vanguardia en procesamiento de lenguaje natural y desarrollo web. La arquitectura actual permite la escalabilidad hacia modelos más robustos siempre que la infraestructura de memoria RAM sea proporcional a la ventana de contexto requerida.