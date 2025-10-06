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
white = (255, 255, 255)
black = (0, 0, 0)
gray = (128, 128, 128)
hud_bg = (30, 30, 30)
colors = [(255, 0, 0), (255, 128, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255)]

# --- LAYOUT / HUD ---
BLOCK_W, BLOCK_H = 100, 40
BLOCK_INNER_W, BLOCK_INNER_H = 98, 38
HUD_HEIGHT = BLOCK_H            # una “fila” para el puntaje
BOARD_TOP = HUD_HEIGHT          # el tablero empieza debajo del HUD

# --- VARIABLES DE JUEGO ---
player_x = 190
ball_x, ball_y = WIDTH // 2, HEIGHT - 30
ball_dx, ball_dy = 4, -4
player_speed = 8
font = pygame.font.Font(None, 36)
score = 0
cooldown_time = 3  # segundos

# Cooldown compartido para inicio y para cuando se pierde
cooldown_active = True          # empieza con cooldown inicial
starting_cooldown = True
last_loss_time = time.time()

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

    # suavizado y morfología
    mask = cv2.GaussianBlur(mask, (7, 7), 0)
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)

    # contornos -> quedarse con el mayor, filtrando ruido por área
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cx = None
    if contours:
        min_area = 800  # ajustable
        large = [c for c in contours if cv2.contourArea(c) > min_area]
        if large:
            c = max(large, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(c)
            cx = x + w // 2
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

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

    # Ventana OpenCV
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
                x = j * BLOCK_W
                y = BOARD_TOP + i * BLOCK_H
                rect = pygame.draw.rect(screen, colors[val - 1], [x, y, BLOCK_INNER_W, BLOCK_INNER_H], 0, 5)
                pygame.draw.rect(screen, black, [x, y, BLOCK_INNER_W, BLOCK_INNER_H], 3, 5)
                blocks.append((rect, i, j))
    return blocks

board = create_board()

# --- LOOP PRINCIPAL ---
running = True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # --- CONTROL DEL JUGADOR ---
    if blue_x_shared is not None:
        player_x = int((blue_x_shared / 320) * WIDTH) - 60
        player_x = max(0, min(WIDTH - 120, player_x))

    # --- COOLDOWN (inicial y tras perder) ---
    if cooldown_active:
        remaining = cooldown_time - (time.time() - last_loss_time)
        if remaining <= 0:
            cooldown_active = False
            starting_cooldown = False
        else:
            # Pantalla limpia sin HUD; mensaje centrado
            screen.fill(gray)
            msg = (
                f"¡Prepárate! Comienza en {int(remaining)}s"
                if starting_cooldown else
                f"Perdiste! Reiniciando en {int(remaining)}s"
            )
            text = font.render(msg, True, white)
            # centrar texto
            screen.blit(
                text,
                (WIDTH//2 - text.get_width()//2, HEIGHT//2 - text.get_height()//2)
            )
            pygame.display.flip()
            clock.tick(30)
            continue  # no se dibuja HUD ni tablero durante cooldown

    # --- FÍSICA DE LA PELOTA ---
    ball_x += ball_dx
    ball_y += ball_dy

    if ball_x <= 10 or ball_x >= WIDTH - 10:
        ball_dx *= -1
    if ball_y <= 10:
        ball_dy *= -1
    if ball_y >= HEIGHT:
        cooldown_active = True
        starting_cooldown = False
        last_loss_time = time.time()
        ball_x, ball_y = WIDTH // 2, HEIGHT - 30
        ball_dx, ball_dy = 4, -4
        board = create_board()
        score = 0
        continue

    # --- DIBUJAR TODO ---
    screen.fill(gray)

    # HUD: barra superior y puntaje (solo en juego)
    pygame.draw.rect(screen, hud_bg, [0, 0, WIDTH, HUD_HEIGHT])
    score_text = font.render(f"Puntaje: {score}", True, white)
    screen.blit(score_text, (20, HUD_HEIGHT//2 - score_text.get_height()//2))

    # Tablero y entidades
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
            speed_factor = 1.05
            max_speed = 14
            if abs(ball_dx) < max_speed:
                ball_dx *= speed_factor
            if abs(ball_dy) < max_speed:
                ball_dy *= speed_factor
            break

    pygame.display.flip()
    clock.tick(60)

pygame.quit()