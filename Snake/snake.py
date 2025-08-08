import cv2
import numpy as np
import pygame
import sys
import random

# Inicializar pygame
pygame.init()

# Dimensiones del juego
WIDTH, HEIGHT = 600, 600
CELL_SIZE = 20
GRID_WIDTH = WIDTH // CELL_SIZE
GRID_HEIGHT = HEIGHT // CELL_SIZE

# Colores
BLACK = (0, 0, 0)
GREEN = (0, 255, 0)
RED   = (255, 0, 0)
WHITE = (255, 255, 255)

# Crear ventana de juego
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()

# Inicializar webcam
cap = cv2.VideoCapture(0)

# Función para generar comida
def random_food():
    return [random.randint(0, GRID_WIDTH-1), random.randint(0, GRID_HEIGHT-1)]

# Inicializar variables del juego
snake = [[5, 5]]
direction = [1, 0]  # Comienza hacia la derecha
food = random_food()

def detect_direction(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # Rango de color rojo en HSV
    lower1 = np.array([0, 100, 100])
    upper1 = np.array([10, 255, 255])
    lower2 = np.array([160, 100, 100])
    upper2 = np.array([179, 255, 255])

    # Máscara para ambos rangos
    mask1 = cv2.inRange(hsv, lower1, upper1)
    mask2 = cv2.inRange(hsv, lower2, upper2)
    mask = cv2.bitwise_or(mask1, mask2)

    # Encontrar contornos
    contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        # Tomar el mayor contorno
        c = max(contours, key=cv2.contourArea)
        M = cv2.moments(c)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])

            # Determinar dirección con respecto al centro
            if abs(cx - 320) > abs(cy - 240):
                return [1, 0] if cx > 320 else [-1, 0]
            else:
                return [0, 1] if cy > 240 else [0, -1]
    return None

# Loop principal
while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame = cv2.flip(frame, 1)  # Espejo para control más natural
    new_dir = detect_direction(frame)
    if new_dir and (new_dir[0] != -direction[0] or new_dir[1] != -direction[1]):
        direction = new_dir

    # Lógica de movimiento
    head = [snake[0][0] + direction[0], snake[0][1] + direction[1]]
    if head in snake or head[0] < 0 or head[0] >= GRID_WIDTH or head[1] < 0 or head[1] >= GRID_HEIGHT:
        print("¡Perdiste!")
        pygame.quit()
        cap.release()
        cv2.destroyAllWindows()
        sys.exit()

    snake.insert(0, head)
    if head == food:
        food = random_food()
    else:
        snake.pop()

    # Dibujar
    screen.fill(BLACK)
    for s in snake:
        pygame.draw.rect(screen, GREEN, (s[0]*CELL_SIZE, s[1]*CELL_SIZE, CELL_SIZE, CELL_SIZE))
    pygame.draw.rect(screen, RED, (food[0]*CELL_SIZE, food[1]*CELL_SIZE, CELL_SIZE, CELL_SIZE))

    pygame.display.flip()
    clock.tick(10)

    # Mostrar frame para que veas la detección
    cv2.imshow("Control", frame)
    if cv2.waitKey(1) == 27:  # ESC para salir
        break
