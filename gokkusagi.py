from turtle import *
shape('circle')
yaricap = 2
adim = 1

renklistesi = ['red', 'orange', 'yellow', 'green', 'blue', 'purple', 'violet']
renk = 0

penup()
for i in range(30):
    if renk > 6:
        renk = 0
    color(renklistesi[renk])
    renk = renk + 1
    turtlesize(adim)
    adim = adim + 0.12
    forward(yaricap)
    left(24)
    yaricap = yaricap + 3
    stamp()
hideturtle()
color('black')