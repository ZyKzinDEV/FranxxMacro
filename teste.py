import keyboard
import time

print("A começar em 3 segundos... clica no Bloco de Notas!")
time.sleep(3)

for i in range(10):
    keyboard.press_and_release('f')
    print(f"Enviou F #{i+1}")
    time.sleep(0.2)

print("Feito!")