import pygame
import cv2
import numpy as np
import random
import threading
import time
import platform  # detectar Windows

# --- CONFIGURACIÓN PYGAME ---
pygame.init()
WIDTH, HEIGHT = 500, 900
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Brick Breaker")
clock = pygame.time.Clock()

# --- COLORES ---
# Tuplas RGB para colores usados en el juego
white = (255, 255, 255)
black = (0, 0, 0)
gray = (128, 128, 128)
hud_bg = (30, 30, 30)
colors = [(255, 0, 0), (255, 128, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255)]

# --- LAYOUT / HUD ---
# Dimensiones de bloques y posiciones fijas
BLOCK_W, BLOCK_H = 100, 40
BLOCK_INNER_W, BLOCK_INNER_H = 98, 38
HUD_HEIGHT = BLOCK_H            # una “fila” para el puntaje
BOARD_TOP = HUD_HEIGHT          # el tablero empieza debajo del HUD

# --- VARIABLES DE JUEGO ---
# Posición inicial del jugador (paddle)
player_x = 190
# Posición y velocidad inicial de la pelota
ball_x, ball_y = WIDTH // 2, HEIGHT - 30
ball_dx, ball_dy = 4, -4
# Fuente para textos (puntaje, mensajes)
font = pygame.font.Font(None, 36)
score = 0

# --- COOLDOWN (para mostrar mensaje inicial y tras perder) ---
cooldown_time = 3  # segundos de espera inicial y tras perder
cooldown_active = True  # empieza con cooldown inicial activo
starting_cooldown = True
last_loss_time = time.time() # marca temporal del último "loss" para calcular cooldown

# --- VARIABLE COMPARTIDA ENTRE HILOS ---
# Aquí se guardará la coordenada X del centro del objeto azul detectado por la cámara.
# Se actualiza desde el hilo de la cámara y se lee desde el loop principal de pygame.
blue_x_shared = None

# --- FUNCIÓN DE DETECCIÓN DE COLOR AZUL ---
def get_blue_mask(frame):
    """
    Detecta el objeto azul más grande en el frame y devuelve:
      - cx: coordenada X del centro del bounding box del contorno principal (o None si no hay)
      - masked: frame enmascarado (solo píxeles dentro de la máscara)
    Explicación de los pasos:
      - Convertimos BGR->HSV: HSV separa tono (H) de saturación (S) y valor (V).
        Esto facilita la segmentación por color independientemente de la intensidad.
      - inRange aplica un umbral por canales H,S,V para obtener una máscara binaria.
      - GaussianBlur reduce ruido de alta frecuencia antes de operaciones morfológicas.
      - Erode/dilate (morfología) limpian pequeños blobs y cierran huecos.
      - findContours detecta regiones conectadas; elegimos la de mayor área (filtro por área mínima).
    """
    # Convertir a HSV para segmentación por color
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # RANGO DE AZUL EN HSV
    lower_blue = np.array([100, 120, 70])
    upper_blue = np.array([130, 255, 255])
    mask = cv2.inRange(hsv, lower_blue, upper_blue)

    # suavizado y morfología
    # - GaussianBlur reduce ruido que podría crear contornos pequeños.
    # - Erode elimina pequeñas regiones aisladas.
    # - Dilate vuelve a amplificar las regiones relevantes
    mask = cv2.GaussianBlur(mask, (7, 7), 0)
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)

    # contornos -> escoger el contorno más grande (después de filtrar por área mínima)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cx = None
    if contours:
        # Filtramos contornos pequeños para evitar ruido (min_area ajustable según escala de la cámara)
        min_area = 800  # ajustable
        large = [c for c in contours if cv2.contourArea(c) > min_area]
        if large:
            # Elegimos el contorno de mayor área: asumimos que es el objeto de interés
            c = max(large, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(c)
            cx = x + w // 2 # centro horizontal del bounding box
            # Dibujar rectángulo en el frame para visualización
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

    # masked: imagen donde solo se muestran los píxeles que corresponden al color detectado
    masked = cv2.bitwise_and(frame, frame, mask=mask)
    return cx, masked

# --- HILO DE CÁMARA ---
def cam_thread():
    """
    Hilo que captura frames de la cámara en paralelo para no bloquear el loop principal de Pygame.
    - Usar un hilo separado permite leer y procesar la cámara a una tasa independiente.
    - Comunicamos la posición X del objeto azul mediante la variable global `blue_x_shared`.
    """
    global blue_x_shared

    # Abrir cámara con backends que funcionan mejor en Windows
    if platform.system() == "Windows":
        cap = None
        for backend in [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_VFW]:
            cap = cv2.VideoCapture(0, backend)
            if cap.isOpened():
                break
        if cap is None or not cap.isOpened():
            cap = cv2.VideoCapture(0)  # último recurso
    else:
        cap = cv2.VideoCapture(0)

    # Configurar resolución (ajustable según cámara y rendimiento)
    # Sugerimos bajar resolución para reducir carga y latencia (320x240 es suficiente para tracking simple)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

    # Ventana OpenCV para mostrar la máscara
    win_name = "Solo objeto azul (Q para cerrar)"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, 640, 480)
    cv2.moveWindow(win_name, 50, 50)

    while True:
        # Leer frame de forma continua. Si falla, salimos del bucle.
        ret, frame = cap.read()
        if not ret:
            break
        # Flip horizontal para interacción espejo (conveniencia del usuario)
        frame = cv2.flip(frame, 1)
        # Obtener centro X y frame enmascarado
        cx, masked = get_blue_mask(frame)
        # Actualizar variable compartida para el loop principal
        blue_x_shared = cx

        # Mostrar ventana con la máscara
        cv2.imshow(win_name, masked)
        # Permitir cerrar la ventana de OpenCV con 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Liberar recursos de cámara y cerrar ventana al terminar
    cap.release()
    cv2.destroyAllWindows()

# --- INICIAR HILO DE CÁMARA ---
# Hilo daemon para que se cierre automáticamente al salir del programa principal
threading.Thread(target=cam_thread, daemon=True).start()

# --- FUNCIONES DEL JUEGO ---
def create_board():
    """
    Crea la matriz de bloques para el tablero.
    - rows: número de filas aleatorio entre 4 y 8 para variar niveles.
    - Cada celda contiene un entero de 0 a 5; 0 = ausencia de bloque, 1..5 = color del bloque.
    """
    rows = random.randint(4, 8)
    return [[random.randint(1, 5) for _ in range(5)] for _ in range(rows)]

def draw_board(board):
    """
    Dibuja los bloques en pantalla y devuelve una lista de rectángulos para colisiones.
    - Usamos BLOCK_INNER_* para que haya un borde visible alrededor de cada bloque.
    - Devolvemos (rect, i, j) para identificar qué bloque colisionó si ocurre el impacto.
    """
    blocks = []
    for i, row in enumerate(board):
        for j, val in enumerate(row):
            if val > 0:
                # Cálculo de posición en pantalla: j * ancho bloque, i * alto bloque + offset del tablero
                x = j * BLOCK_W
                y = BOARD_TOP + i * BLOCK_H
                # Dibujar rectángulo relleno y borde negro
                rect = pygame.draw.rect(screen, colors[val - 1], [x, y, BLOCK_INNER_W, BLOCK_INNER_H], 0, 5)
                pygame.draw.rect(screen, black, [x, y, BLOCK_INNER_W, BLOCK_INNER_H], 3, 5)
                blocks.append((rect, i, j))
    return blocks

# Inicializar tablero de bloques
board = create_board()

# --- LOOP PRINCIPAL ---
running = True

while running:
    # --- Manejo de eventos de Pygame (entrada del usuario, cierre de ventana) ---
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # --- CONTROL DEL JUGADOR ---
    # Si blue_x_shared tiene un valor válido (detectamos el objeto azul), mapeamos su X a la posición del paddle.
    if blue_x_shared is not None:
        # Mapear coordenada X de la cámara (0-320) a la pantalla (0-WIDTH), centrando el paddle
        # El paddle tiene 120px de ancho, por eso restamos 60 para centrar
        player_x = int((blue_x_shared / 320) * WIDTH) - 60
        # Limitar posición del paddle para que no salga de la pantalla
        player_x = max(0, min(WIDTH - 120, player_x))

    # --- COOLDOWN (inicial y tras perder) ---
    if cooldown_active:
        # Calculamos tiempo restante del cooldown
        remaining = cooldown_time - (time.time() - last_loss_time)
        if remaining <= 0:
            # Se acabó el cooldown: continúa el juego
            cooldown_active = False
            starting_cooldown = False
        else:
            # Durante el cooldown mostramos una pantalla limpia con mensaje centralizado
            screen.fill(gray)
            msg = (
                f"¡Prepárate! Comienza en {int(remaining)}s"
                if starting_cooldown else
                f"Perdiste! Reiniciando en {int(remaining)}s"
            )
            text = font.render(msg, True, white)
            # Dibujamos el texto centrado en la pantalla
            screen.blit(
                text,
                (WIDTH//2 - text.get_width()//2, HEIGHT//2 - text.get_height()//2)
            )
            pygame.display.flip()
            clock.tick(30)
            # Saltamos el resto del loop para no actualizar física ni dibujar tablero
            continue

    # --- FÍSICA DE LA PELOTA ---
    # Actualizar posición según velocidad
    ball_x += ball_dx
    ball_y += ball_dy

    # Colisiones con paredes (invirtiendo dirección horizontal)
    if ball_x <= 10 or ball_x >= WIDTH - 10:
        ball_dx *= -1
    # Colisiones con techo (invertir dirección vertical)
    if ball_y <= 10:
        ball_dy *= -1
    # Si la pelota cae por debajo de la pantalla -> pérdida, reiniciar estado básico
    if ball_y >= HEIGHT:
        cooldown_active = True
        starting_cooldown = False
        last_loss_time = time.time()
        # Reposicionar pelota y resetear velocidad
        ball_x, ball_y = WIDTH // 2, HEIGHT - 30
        ball_dx, ball_dy = 4, -4
        # Reiniciar tablero y puntaje
        board = create_board()
        score = 0
        continue

    # --- DIBUJAR TODO ---
    screen.fill(gray)

    # HUD: barra superior y puntaje (solo en juego)
    pygame.draw.rect(screen, hud_bg, [0, 0, WIDTH, HUD_HEIGHT])
    score_text = font.render(f"Puntaje: {score}", True, white)
    screen.blit(score_text, (20, HUD_HEIGHT//2 - score_text.get_height()//2))

    # Tablero de bloques y entidades (jugador y pelota)
    blocks = draw_board(board)
    player = pygame.draw.rect(screen, black, [player_x, HEIGHT - 20, 120, 15])
    ball = pygame.draw.circle(screen, white, (ball_x, ball_y), 10)

    # --- COLISIONES ---
    # Colisión simple entre centro de la pelota y el rectángulo del paddle (punto dentro del rectangulo)
    if player.collidepoint(ball_x, ball_y + 10):
        # Invertir velocidad vertical al impactar con el paddle
        ball_dy *= -1

    # Colisiones con bloques:
    # Recorremos lista de rectangulos devuelta por draw_board y verificamos si el centro de la pelota está dentro
    # del rect para detectar impacto. Al colisionar, decrementamos la "vida" del bloque y aumentamos el puntaje.
    for rect, i, j in blocks:
        if rect.collidepoint(ball_x, ball_y):
            # Invertir dirección vertical
            ball_dy *= -1
            # Decrementar el valor del bloque (representa "resistencia" del bloque)
            board[i][j] -= 1
            score += 1
            # AUMENTAR VELOCIDAD SEGÚN PUNTAJE
            speed_factor = 1.05
            max_speed = 14
            # Aumentar componente X y Y si aún están por debajo del máximo absoluto
            if abs(ball_dx) < max_speed:
                ball_dx *= speed_factor
            if abs(ball_dy) < max_speed:
                ball_dy *= speed_factor
            # Salir del bucle para evitar múltiples colisiones en un solo frame
            break

    # Actualizar pantalla y controlar FPS
    pygame.display.flip()
    clock.tick(60)

# Cerrar Pygame al salir del loop principal
pygame.quit()