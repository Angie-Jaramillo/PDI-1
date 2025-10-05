import pygame
import cv2
import numpy as np
import random
import threading
import time
import platform  # <-- agregado para detectar Windows

# --- CONFIGURACIÓN PYGAME ---
pygame.init()
WIDTH, HEIGHT = 500, 900
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Breakout - Control por objeto azul")
clock = pygame.time.Clock()

# --- COLORES ---
white = (255, 255, 255)
black = (0, 0, 0)
gray = (128, 128, 128)
colors = [(255, 0, 0), (255, 128, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255)]

# --- VARIABLES DE JUEGO ---
player_x = 190
ball_x, ball_y = WIDTH // 2, HEIGHT - 30
ball_dx, ball_dy = 4, -4
player_speed = 8
font = pygame.font.Font(None, 36)
score = 0
cooldown_active = False
cooldown_time = 3  # segundos

# --- VARIABLE COMPARTIDA ENTRE HILOS ---
blue_x_shared = None

# --- FUNCIÓN DE DETECCIÓN DE COLOR AZUL ---
def get_blue_mask(frame):
    """Devuelve el centro del objeto azul más grande y el frame enmascarado."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # RANGO DE AZUL EN HSV
    lower_blue = np.array([100, 120, 70])
    upper_blue = np.array([130, 255, 255])
    mask = cv2.inRange(hsv, lower_blue, upper_blue)

    # aplicar desenfoque suave y filtro morfológico
    mask = cv2.GaussianBlur(mask, (7, 7), 0)
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)

    # encontrar contornos
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cx = None
    if contours:
        # Filtrar contornos por tamaño mínimo
        min_area = 800  # puedes ajustar este valor según tu cámara/iluminación
        large_contours = [c for c in contours if cv2.contourArea(c) > min_area]

        if large_contours:
            # tomar el contorno más grande
            c = max(large_contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(c)
            cx = x + w // 2
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

    # crear versión enmascarada (solo lo azul visible)
    masked = cv2.bitwise_and(frame, frame, mask=mask)
    return cx, masked


# --- HILO DE CÁMARA ---
def cam_thread():
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

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

    # Crear y preparar la ventana (Windows a veces lo exige)
    win_name = "Solo objeto azul (Q para cerrar)"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, 640, 480)
    cv2.moveWindow(win_name, 50, 50)

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.flip(frame, 1)
        cx, masked = get_blue_mask(frame)
        blue_x_shared = cx

        # mostrar solo el enmascarado (objeto azul visible)
        cv2.imshow(win_name, masked)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

# --- INICIAR HILO DE CÁMARA ---
threading.Thread(target=cam_thread, daemon=True).start()

# --- FUNCIONES DEL JUEGO ---
def create_board():
    rows = random.randint(4, 8)
    return [[random.randint(1, 5) for _ in range(5)] for _ in range(rows)]

def draw_board(board):
    blocks = []
    for i, row in enumerate(board):
        for j, val in enumerate(row):
            if val > 0:
                rect = pygame.draw.rect(screen, colors[val - 1], [j * 100, i * 40, 98, 38], 0, 5)
                pygame.draw.rect(screen, black, [j * 100, i * 40, 98, 38], 3, 5)
                blocks.append((rect, i, j))
    return blocks

board = create_board()

# --- LOOP PRINCIPAL ---
running = True
last_loss_time = 0

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # --- CONTROL DEL JUGADOR ---
    if blue_x_shared is not None:
        player_x = int((blue_x_shared / 320) * WIDTH) - 60
        player_x = max(0, min(WIDTH - 120, player_x))

    # --- LOGICA DE COOLDOWN ---
    if cooldown_active:
        remaining = cooldown_time - (time.time() - last_loss_time)
        if remaining <= 0:
            cooldown_active = False
        else:
            screen.fill(gray)
            text = font.render(f"Perdiste! Reiniciando en {remaining:.1f}s", True, white)
            screen.blit(text, (80, HEIGHT // 2))
            pygame.display.flip()
            clock.tick(30)
            continue

    # --- FÍSICA DE LA PELOTA ---
    ball_x += ball_dx
    ball_y += ball_dy

    if ball_x <= 10 or ball_x >= WIDTH - 10:
        ball_dx *= -1
    if ball_y <= 10:
        ball_dy *= -1
    if ball_y >= HEIGHT:
        # activa cooldown antes de reiniciar
        cooldown_active = True
        last_loss_time = time.time()
        ball_x, ball_y = WIDTH // 2, HEIGHT - 30
        ball_dx, ball_dy = 4, -4
        board = create_board()
        score = 0
        continue

    # --- DIBUJAR TODO ---
    screen.fill(gray)
    blocks = draw_board(board)
    player = pygame.draw.rect(screen, black, [player_x, HEIGHT - 20, 120, 15])
    ball = pygame.draw.circle(screen, white, (ball_x, ball_y), 10)

    # --- COLISIONES ---
    if player.collidepoint(ball_x, ball_y + 10):
        ball_dy *= -1

    for rect, i, j in blocks:
        if rect.collidepoint(ball_x, ball_y):
            ball_dy *= -1
            board[i][j] -= 1
            score += 1
            # AUMENTAR VELOCIDAD SEGÚN PUNTAJE
            speed_factor = 1.05  # cuánto se incrementa cada vez
            max_speed = 14       # límite superior de velocidad
            if abs(ball_dx) < max_speed:
                ball_dx *= speed_factor
            if abs(ball_dy) < max_speed:
                ball_dy *= speed_factor
            break

    # --- PUNTAJE ---
    text = font.render(f"Puntaje: {score}", True, white)
    screen.blit(text, (10, 10))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
