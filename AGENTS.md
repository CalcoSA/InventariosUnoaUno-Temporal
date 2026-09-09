# Ejecución local de esta aplicación

- No dejar servidores Flask/Python iniciados por el agente al finalizar una tarea.
- No iniciar `run.py` automáticamente. Para comprobaciones de rutas, preferir el test client de Flask, que no abre un puerto.
- Si una prueba concreta exige iniciar un servidor, registrar cuál es el proceso propio y detenerlo al terminar, incluso si la prueba falla. Comprobar que no quedó escuchando.
- No detener procesos ajenos ni procesos iniciados manualmente por el usuario sin autorización.
- La aplicación solo debe permanecer ejecutándose cuando el usuario la inicia manualmente con `.\.venv\Scripts\python.exe run.py`.
