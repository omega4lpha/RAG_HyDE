/**
 * RAG Sentinel - Cliente Frontend
 * Módulo principal de interacción con el backend Flask.
 */

const socket = io();

const chatHistory = document.getElementById('chat-history');
const userInput = document.getElementById('user-input');
const btnSend = document.getElementById('btn-send');
const btnStop = document.getElementById('btn-stop');
const consoleDiv = document.getElementById('admin-console');
const fileInput = document.getElementById('file-input');
const btnUpload = document.getElementById('btn-upload');
const fileListTags = document.getElementById('file-list-tags');
const fileNameDisplay = document.getElementById('file-name-display');

const SVG_DOCUMENT_ICON = `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>`;
const SVG_DELETE_ICON = `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>`;
const SVG_DOWNLOAD_ICON = `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>`; // Nuevo ícono de descarga
// --- MEMORIA A CORTO PLAZO DEL FRONTEND ---
let memoriaConversacion = [];

socket.on('admin_log', data => {
    const div = document.createElement('div');
    div.textContent = `> ${data.msg}`;
    consoleDiv.appendChild(div);
    consoleDiv.scrollTop = consoleDiv.scrollHeight;
});

fileInput.addEventListener('change', function() {
    if (this.files && this.files.length > 0) {
        fileNameDisplay.textContent = this.files[0].name;
        fileNameDisplay.style.color = 'var(--text-primary)';
    } else {
        fileNameDisplay.textContent = 'Ningún archivo seleccionado';
        fileNameDisplay.style.color = 'var(--text-muted)';
    }
});

async function actualizarListaArchivos() {
    try {
        const res = await fetch('/api/archivos');
        const data = await res.json();
        
        if (data.archivos && data.archivos.length > 0) {
            fileListTags.innerHTML = data.archivos.map(f => {
                const cssClass = f.estado === 'Indexado' ? 'status-ok' : 'status-wait';
                return `
                    <span class="file-tag ${cssClass}" style="display: flex; align-items: center; gap: 8px;">
                        ${SVG_DOCUMENT_ICON} 
                        <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${f.nombre}</span> 
                        <small style="opacity: 0.7;">(${f.estado})</small>
                        
                        <div style="display: flex; gap: 4px; margin-left: auto;">
                            <a href="/api/descargar/${encodeURIComponent(f.nombre)}" title="Descargar documento" target="_blank" 
                               style="display: flex; align-items: center; justify-content: center; padding: 4px; color: inherit; text-decoration: none; opacity: 0.7; transition: opacity 0.2s;"
                               onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                ${SVG_DOWNLOAD_ICON}
                            </a>
                            <button class="btn-delete-file" onclick="borrarArchivo('${f.nombre}')" title="Eliminar de BD" 
                                    style="background: transparent; border: none; color: inherit; cursor: pointer; padding: 4px; opacity: 0.7; transition: opacity 0.2s;"
                                    onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.7'">
                                ${SVG_DELETE_ICON}
                            </button>
                        </div>
                    </span>
                `;
            }).join('');
        } else {
            fileListTags.innerHTML = '<span style="color: var(--text-muted); font-size: 0.8rem;">Repositorio vacío.</span>';
        }
    } catch (err) {
        console.error("[CRITICAL] Fallo en sincronización:", err);
    }
}

window.borrarArchivo = async function(nombreArchivo) {
    if(!confirm(`¿Desea eliminar definitivamente "${nombreArchivo}" de la base de datos?`)) return;
    try {
        const res = await fetch('/api/borrar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre: nombreArchivo })
        });
        if(res.ok) actualizarListaArchivos();
    } catch (e) {
        alert("Error al intentar purgar el archivo.");
    }
};

btnUpload.addEventListener('click', async () => {
    if (!fileInput.files[0]) return alert("Seleccione un archivo primero.");
    btnUpload.disabled = true;
    btnUpload.textContent = "Indexando...";
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    try {
        const response = await fetch('/api/subir', { method: 'POST', body: formData });
        if (response.ok) {
            fileInput.value = '';
            fileNameDisplay.textContent = 'Ningún archivo seleccionado';
            actualizarListaArchivos();
        }
    } catch (error) {
        alert("Error de red durante la carga.");
    } finally {
        btnUpload.disabled = false;
        btnUpload.textContent = "Subir e Indexar Documento";
    }
});

async function enviarPregunta() {
    const q = userInput.value.trim();
    if(!q) return;
    
    const userMsg = document.createElement('div');
    userMsg.className = 'message user-msg';
    userMsg.textContent = q;
    chatHistory.appendChild(userMsg);
    userInput.value = '';

    btnSend.style.display = 'none';
    btnStop.style.display = 'block';

    const botMsgContainer = document.createElement('div');
    botMsgContainer.className = 'message bot-msg';
    chatHistory.appendChild(botMsgContainer);

    // Limitamos la memoria a los últimos 6 mensajes (3 turnos) para no saturar tokens
    const historialReducido = memoriaConversacion.slice(-6);

    try {
        const res = await fetch('/ask', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                pregunta: q,
                historial: historialReducido // Enviamos la memoria al backend
            })
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder("utf-8");
        
        let answerDiv = document.createElement('div');
        answerDiv.className = 'bot-answer';
        botMsgContainer.appendChild(answerDiv);

        let textoCompletoBot = ''; 
        let bufferRed = '';

        while(true) {
            const {value, done} = await reader.read();
            if(done) break;
            
            bufferRed += decoder.decode(value, {stream: true});
            const lines = bufferRed.split('\n');
            bufferRed = lines.pop();

            for(let line of lines) {
                line = line.trim();
                if(!line) continue;
                
                try {
                    const data = JSON.parse(line);
                    
                    if(data.tipo === 'chunk') {
                        textoCompletoBot += data.texto;
                        
                        // --- LÓGICA DE AUTO-SCROLL INTELIGENTE ---
                        // Comprueba si el usuario está a menos de 40px del fondo
                        const isAtBottom = chatHistory.scrollHeight - chatHistory.clientHeight <= chatHistory.scrollTop + 40;
                        
                        answerDiv.innerHTML = marked.parse(textoCompletoBot);
                        
                        // Solo empuja hacia abajo si el usuario no estaba leyendo más arriba
                        if (isAtBottom) {
                            chatHistory.scrollTop = chatHistory.scrollHeight;
                        }
                    } 
                    else if(data.tipo === 'contexto') {
                        data.datos.forEach(ctx => {
                            const ctxBox = document.createElement('div');
                            ctxBox.className = 'context-box';
                            // Magia HTML5: <details> crea el acordeón, <summary> es el título clickeable
                            ctxBox.innerHTML = `
                                <details>
                                    <summary style="cursor: pointer; color: var(--accent-primary);">
                                        <strong>📄 ${ctx.titulo}</strong> (Clic para inspeccionar)
                                    </summary>
                                    <div style="margin-top: 10px; padding-left: 10px; border-left: 2px solid var(--border-color);">
                                        <em>${ctx.contenido}</em>
                                    </div>
                                </details>
                            `;
                            botMsgContainer.insertBefore(ctxBox, answerDiv);
                        });
                    }
                } catch (e) {
                    console.error("JSON parse error en stream");
                }
            }
        }
        
        // --- GUARDAR EN MEMORIA TRAS FINALIZAR ---
        memoriaConversacion.push({"role": "user", "content": q});
        memoriaConversacion.push({"role": "assistant", "content": textoCompletoBot});

    } catch (error) {
        console.error("Critical error:", error);
    } finally {
        btnSend.style.display = 'block';
        btnStop.style.display = 'none';
        userInput.focus();
    }
}

userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); btnSend.click(); }
});

btnSend.addEventListener('click', enviarPregunta);
btnStop.addEventListener('click', () => fetch('/stop', {method: 'POST'}));
document.addEventListener('DOMContentLoaded', actualizarListaArchivos);