# Diagnóstico del portátil y actualización de diarización

Revisión local del 8 de septiembre de 2026. Horas de Windows en Europe/Madrid.

## Equipo y versiones comprobadas

- ASUS ROG Strix G614JU_G614JU, i9-13980HX (32 procesadores lógicos), aproximadamente 64 GB de RAM.
- NVIDIA RTX 4050 Laptop, 6 GB; driver 610.88 (32.0.16.1088).
- Intel UHD Graphics: 32.0.101.7088. Coincide con el paquete oficial Intel publicado para las generaciones 11–14 al revisar las fuentes.
- BIOS G614JU.334, también listado por ASUS. No se ha actualizado durante esta revisión.
- FFmpeg 7.0.1, Python 3.11.9.

## Qué explica la evidencia y qué sigue sin conocerse

La primera prueba completó la transcripción de 22 minutos y 40 segundos con Whisper medium. El registro del programa se interrumpe durante la diarización CUDA. Windows registró Kernel-Power 41 el 8 de septiembre a las 13:40:51, con BugcheckCode 0, y un cierre inesperado 6008. No se encontró un registro contemporáneo que identificara un fallo de NVIDIA, WHEA o un volcado que estableciera la causa.

El evento 41 registra un apagado inesperado; **no demuestra sobrecalentamiento, falta de VRAM ni un driver concreto**. WMI no proporcionó temperatura de CPU. Más tarde se pudieron consultar lecturas de 89–93 °C en la interfaz de Armoury Crate durante la nueva prueba GPU, con la GPU a 59–63 °C. El perfil Manual ya estaba activo, con ventilador CPU a 6800 RPM y del sistema a 7500 RPM; no se han cambiado esos ajustes. Son muestras puntuales, no un registro de temperatura en el instante del reinicio. Intel especifica Tjunction de 100 °C para el i9-13980HX: la lectura alta merece atención, pero no demuestra una avería térmica. Una muestra posterior de tres segundos midió 1,1% de CPU total para el worker Community-1 y 7,8% para el sistema mediante psutil.

La consulta del perfil `Manual mode 1`, conectado a corriente, mostró **CPU PL1 140 W / PL2 175 W**, y **GPU Base Clock Offset +50 MHz / Memory Clock Offset +100 MHz**, Dynamic Boost 25 W y Thermal Target 87 °C. Por tanto, el perfil activo no se limita a aumentar ventiladores: también permite presupuestos de potencia elevados y tiene offsets positivos de frecuencia GPU. Son factores a evaluar al diagnosticar carga térmica o inestabilidad; no prueban causalidad. Solo se leyeron las pestañas CPU/GPU: no se pulsó Guardar ni Aplicar. Un siguiente ajuste del equipo debe valorar un perfil sin offsets GPU y con menor presupuesto CPU, conservando antes una copia del perfil actual.

Hay antecedentes más concretos en Windows Error Reporting: el 25 de agosto a las 10:34:38 y el 25 de julio a las 10:05:49 aparecen informes `LKD_0x141_Tdr:6_IMAGE_igdkmdn64.sys_GEN12LP_DX10_RINGHANG`. Corresponden a tiempos de espera del motor gráfico Intel integrado. Son incidentes anteriores: no prueban que el reinicio de septiembre tenga la misma causa. Actualizar NVIDIA por sí solo no aborda ese antecedente Intel.

No se han hecho cambios de ventiladores, voltajes, límites eléctricos, BIOS ni instalaciones de drivers. Tras probar la alternativa CPU, el usuario pidió mantener la aceleración GPU por el tiempo de ejecución. Se prepara una validación gradual del nuevo modelo con la ruta GPU descrita abajo. No hay evidencia suficiente para prescribir una versión concreta de driver como reparación. Si vuelve a reiniciarse con esta ruta limitada, conviene conservar la hora y los eventos de ese incidente y evaluar alimentación, refrigeración y gráficos híbridos con soporte ASUS; este cambio de software no sustituye esa comprobación.

## Cambio aplicado al programa

La identificación usa `pyannote/speaker-diarization-community-1` con pyannote.audio 4.0.7. La ficha oficial muestra mejoras de identificación y recuento en muchos conjuntos de prueba respecto a 3.1; no garantiza mejoras en todos los audios. Se usa su diarización exclusiva para asociar las frases de Whisper a un hablante por duración de solapamiento. Si una frase contiene varias voces, todavía recibe una sola etiqueta: no se han añadido marcas de tiempo por palabra.

El modelo dispone de `.venv-diarization` con Torch/torchaudio 2.8.0 **CPU**, y `.venv-diarization-gpu` con las versiones 2.8.0 **CUDA 12.8**, separados del Torch 2.5.1 CUDA de Whisper. El worker CPU rechaza Torch con CUDA. FFmpeg decodifica a mono de 16 kHz y entrega la onda en memoria; no depende de DLL opcionales de TorchCodec en Windows.

En este equipo se aplican dos hilos, lotes de cuatro y un Job Object de Windows con límite estricto del 6% del tiempo total de CPU. La prioridad es inferior a la normal. Un mutex evita dos diarizaciones simultáneas dentro de la sesión de Windows. La app vigila la memoria del worker y sus hijos cada 250 ms y cancela por encima de 4 GB; es vigilancia, no un límite estricto de asignación. También hay un tiempo máximo de dos horas y cancelación del proceso desde la interfaz. Estos límites reducen la carga; no controlan directamente la temperatura.

La ruta **GPU rápida**, predeterminada tras medir el rendimiento, activa cuDNN con `benchmark=False`, usa lotes de ocho y pausas de 30 ms. El perfil **GPU compatible** conserva cuDNN desactivado, lotes de cuatro para segmentación y dos para embeddings, con pausas de 50 y 150 ms. Desactivar completamente cuDNN y añadir esas pausas largas había penalizado excesivamente la primera versión del perfil. Ambos limitan el asignador CUDA de Torch al 45% de VRAM. Desde la corrección del 9 de septiembre, el supervisor consulta NVIDIA cada dos segundos y comunica al worker una **pausa cooperativa** a 78 °C u 80 W, en vez de matarlo. El worker termina el lote en curso, conserva su estado en memoria y reanuda al bajar a 74 °C y 65 W. A partir de 75 °C o 70 W añade 60 ms entre lotes. Si falta telemetría o está obsoleta también espera; Cancelar y el tiempo máximo siguen funcionando desde el supervisor. Estos umbrales son una decisión conservadora de la app, no límites máximos oficiales del hardware. Tampoco controlan la temperatura de CPU, los picos entre lecturas ni el consumo eléctrico: no pueden garantizar evitar un apagado.

El [issue 1813 de Pyannote](https://github.com/pyannote/pyannote-audio/issues/1813) describe un fallo GPU con diarización 3.1 en Ubuntu/RTX 4090; el autor informó que reinstalar CUDA lo resolvió. Es un antecedente de otro entorno, no evidencia de que el portátil tenga la misma avería. El cambio a un runtime CUDA 12.8 aislado debe juzgarse por las pruebas locales; no se ha presentado como una reparación demostrada. La [documentación de PyTorch](https://docs.pytorch.org/docs/2.8/backends.html) distingue entre habilitar cuDNN y activar la búsqueda de algoritmos mediante `benchmark`; no es necesario desactivar todo cuDNN para evitar esa búsqueda.

Whisper conserva medium como perfil para la RTX 4050 de 6 GB. Turbo está disponible en el selector, pero no se ha validado en este portátil y su estimación oficial de VRAM deja poco margen. La reanudación con JSON válido evita cargar Whisper otra vez.

## Validación local

- Las 14 pruebas de regresión pasan; `pip check` no detecta conflictos en los tres entornos.
- Fragmento CPU de 30 segundos: 12 turnos, dos hablantes, 37,64 s de procesamiento con lotes de cuatro. La prueba completa CPU se canceló para atender la preferencia del usuario por GPU; no se presenta como validada hasta el final.
- Primer fragmento GPU con lotes de cuatro: 14,00 s, máximo muestreado de 79,8 W. La siguiente prueba completa se detuvo automáticamente al alcanzar un umbral del supervisor; no hubo reinicio ni pérdida del texto. Se redujeron los lotes de embeddings a dos y se añadieron pausas de 150 ms.
- Fragmento GPU ajustado: 14,50 s de procesamiento, 23,81 s incluyendo arranque del worker; máximos muestreados de 62 °C / 22,27 W.
- **Audio completo con GPU ajustada**: 1360,44 s de onda decodificada, 574,44 s de procesamiento y 581,64 s incluyendo arranque del worker. Completó el 8 de septiembre a las 14:34:15 sin reinicio. Máximos muestreados: 64 °C, 27,1 W, 393 MB de memoria GPU total; asignación máxima del modelo mediante Torch: 207,9 MB; RAM agregada del worker y sus hijos: 1627,8 MB.
- Se generaron 320 turnos de diarización exclusiva y se asignaron las 326 frases de Whisper: 187 a SPEAKER_00, 138 a SPEAKER_01 y una sin asignar en 654,40–656,08 s. La comprobación posterior al guardado verificó que el texto y los tiempos originales se conservan, descontando espacios exteriores.
- El flujo de interfaz permitió añadir el archivo desde Descargas, recuperar su JSON sin cargar Whisper, ejecutar la diarización completa, abrir el editor, reproducir un fragmento y guardar con Ctrl+S. No se ha medido una tasa de error frente a una transcripción etiquetada manualmente; una ejecución correcta no equivale a precisión perfecta.

Los registros y resultados del audio permanecen en la carpeta local `output`, excluida de Git. La memoria/temperatura muestreadas no son máximos físicos garantizados entre lecturas. No se repitió la transcripción pesada: se validó la recuperación del resultado que Whisper ya había completado.

### Corrección posterior de rendimiento

La primera configuración compatible no era una optimización satisfactoria: las pausas de los 2028 lotes de embeddings y los lotes de segmentación añadían por sí solas más de cinco minutos. Se habilitó cuDNN sin activar su búsqueda de algoritmos y se aumentaron los lotes a ocho. Una prueba de 120 segundos sin pausas alcanzó una lectura de 86,5 W a 65 °C y fue detenida por el supervisor, sin reinicio. Con pausas de 30 ms, el mismo tramo terminó en 6,97 s de inferencia y 18,09 s incluyendo arranque, con máximo muestreado de 66,89 W.

La prueba definitiva del audio **completo** terminó en **83,81 s de worker**, desglosados en 0,64 s de decodificación, 3,42 s de carga del modelo y 72,30 s de inferencia, más el arranque del proceso. La inferencia incluye 20,96 s medidos de pausas. Frente a 581,64 s del perfil compatible, supone **6,94 veces más velocidad**. Máximos muestreados: 68 °C, 69,73 W y 709 MB de memoria GPU total; asignación máxima de Torch de 436,4 MB y RAM agregada de 1729,7 MB. **Los 320 turnos, sus etiquetas y sus tiempos coinciden exactamente con el resultado compatible**. No se registró otro Kernel-Power 41. El informe local es `community_gpu_efficient_full.json`; el archivo de transcripción abierto en el editor no se sobrescribió durante esta comparación.

### Corrección del 9 de septiembre

La corrección del 9 de septiembre reproduce la lectura comunicada por el usuario (78 °C, 73,9 W) como entrada de prueba, sin calentar artificialmente el ordenador. En una ejecución real de 120 segundos de audio se inyectó temporalmente esa lectura en el supervisor: el worker pausó, reanudó y produjo los mismos 48 turnos que la ejecución de referencia. También se comprobó que una lectura obsoleta no permite continuar. `output/cooling_resume_validation.json` identifica explícitamente la telemetría inyectada para no confundirla con temperaturas físicas medidas. La conservación del progreso durante la pausa es en memoria; no es un punto de control persistente de diarización ante un cierre de la app o un reinicio del equipo.

La recuperación completa de `2026-09-09 12_27_40.mp3` (1027,8 segundos) terminó en 79,36 segundos, sin repetir Whisper: 351 turnos, dos hablantes y las 183 frases con texto y tiempos originales conservados. Hubo tres pausas automáticas, con 6,59 segundos de espera acumulada. Los máximos muestreados fueron 75 °C y 96,21 W: el umbral de consumo activa una pausa cooperativa, no impone un límite físico de potencia.

## Fuentes oficiales

- [Modelo Community-1 y comparativa](https://huggingface.co/pyannote/speaker-diarization-community-1)
- [Dependencias de pyannote.audio 4.0.7](https://github.com/pyannote/pyannote-audio/blob/4.0.7/pyproject.toml)
- [Versiones y compatibilidad de TorchCodec](https://github.com/meta-pytorch/torchcodec)
- [Microsoft: cómo interpretar Kernel-Power 41](https://learn.microsoft.com/es-es/troubleshoot/windows-client/performance/event-id-41-restart)
- [Microsoft: VIDEO_ENGINE_TIMEOUT_DETECTED 0x141](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/bug-check-0x141---video-engine-timeout-detected)
- [Microsoft: límite de CPU mediante Job Object](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_cpu_rate_control_information)
- [Driver Intel de generaciones 11–14](https://www.intel.com/content/www/us/en/download/864990/intel-11th-14th-gen-processor-graphics-windows.html)
- [BIOS ASUS G614JU](https://www.asus.com/supportonly/g614ju/helpdesk_bios/)
- [Whisper y estimaciones de VRAM](https://github.com/openai/whisper)
- [Intel i9-13980HX: especificaciones térmicas](https://www.intel.com/content/www/us/en/products/sku/232138/intel-core-i913980hx-processor-36m-cache-up-to-5-60-ghz/specifications.html)
