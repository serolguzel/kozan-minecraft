import json
import math
import os
import random

from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from ursina.shaders import unlit_shader

app = Ursina()

WORLD_SIZE = 25
SAVE_FILE = 'world_save.json'
REACH = 6            # bloklara en fazla bu kadar uzaktan dokunabilirsin
DAY_LENGTH = 240     # bir tam gün (gündüz + gece) kaç saniye sürsün
VOID_Y = -15         # oyuncu bunun altına düşerse yeniden doğar

# ---- Blok türleri ----
# Her blok bir id, isim, model ve dokuya sahip. 'color' o dokuyu boyamak için kullanılıyor
# (özel dokumuz olmadığı için white_cube dokusunu renklendirerek toprak/taş/odun/kum yapıyoruz).
BEDROCK = 10
BLOCK_TYPES = {
    1: {'name': 'Beyaz Küp', 'texture': 'white_cube', 'color': color.white},
    2: {'name': 'Çim',       'texture': 'grass',      'color': color.white},
    3: {'name': 'Taş',       'texture': 'white_cube', 'color': color.gray},
    4: {'name': 'Toprak',    'texture': 'white_cube', 'color': color.brown},
    5: {'name': 'Odun',      'texture': 'white_cube', 'color': color.orange},
    6: {'name': 'Kum',       'texture': 'white_cube', 'color': color.yellow},
    7: {'name': 'Yaprak',    'texture': 'white_cube', 'color': color.rgb32(60, 150, 60)},
    8: {'name': 'Cam',       'texture': 'white_cube', 'color': color.rgba32(180, 230, 255, 110)},
    9: {'name': 'Tuğla',     'texture': 'brick',      'color': color.white},
    BEDROCK: {'name': 'Ana Kaya', 'texture': 'white_cube', 'color': color.dark_gray, 'unbreakable': True},
}
HOTBAR_IDS = [i for i in sorted(BLOCK_TYPES) if not BLOCK_TYPES[i].get('unbreakable')]
chosen_block = 1

# ---- Ses efektleri ----
place_sound = Audio('square', autoplay=False, loop=False, volume=.4)
break_sound = Audio('noise', autoplay=False, loop=False, volume=.3)


class Sky(Entity):
    def __init__(self):
        super().__init__(
            parent=scene,
            model='sphere',
            texture='sky_default',
            double_sided=True,
            scale=150,
            shader=unlit_shader,  # gökyüzü sisten etkilenmesin
            position=(WORLD_SIZE / 2, 0, WORLD_SIZE / 2),
        )


class Block(Button):
    def __init__(self, position=(0, 0, 0), block_id=1):
        info = BLOCK_TYPES[block_id]
        super().__init__(
            parent=scene,
            position=position,
            model='cube',
            texture=info['texture'],
            color=info['color'],
            origin_y=.5,
            highlight_color=color.lime,
        )
        self.block_id = block_id


# ---- Dünya (yerleştirilen bloklar konum -> Block eşleşmesi) ----
world = {}


def block_overlaps_player(pos):
    # Blok (origin_y=.5 yüzünden) y-1 ile y arasında duruyor, oyuncu ise ayaklarından ~1.8 yukarıya kadar.
    return (
        abs(pos[0] - player.x) < .8
        and abs(pos[2] - player.z) < .8
        and pos[1] > player.y
        and pos[1] - 1 < player.y + 1.8
    )


def spawn_block(position, block_id, play_sound=False):
    pos = (round(position[0]), round(position[1]), round(position[2]))
    if pos in world:
        return world[pos]
    if play_sound and block_overlaps_player(pos):
        return None  # kendi içine blok koyma
    block = Block(position=pos, block_id=block_id)
    world[pos] = block
    if play_sound:
        place_sound.pitch = random.uniform(.9, 1.1)
        place_sound.play()
        swing_hand()
    return block


def remove_block(block, play_sound=False):
    if play_sound and BLOCK_TYPES[block.block_id].get('unbreakable'):
        show_status('Ana kaya kırılamaz!')
        return
    pos = (round(block.x), round(block.y), round(block.z))
    world.pop(pos, None)
    if play_sound:
        break_particles(block.world_position + Vec3(0, -.5, 0), block.color, block.texture)
        break_sound.pitch = random.uniform(.8, 1.2)
        break_sound.play()
        swing_hand()
    destroy(block)


def clear_world():
    for block in list(world.values()):
        destroy(block)
    world.clear()


def break_particles(center, block_color, block_texture):
    for _ in range(8):
        p = Entity(
            model='cube',
            texture=block_texture,
            color=block_color,
            scale=.15,
            position=center + Vec3(random.uniform(-.3, .3), random.uniform(-.3, .3), random.uniform(-.3, .3)),
        )
        target = p.position + Vec3(random.uniform(-.8, .8), random.uniform(.2, 1), random.uniform(-.8, .8))
        p.animate_position(target, duration=.4, curve=curve.out_quad)
        p.animate_scale(0, duration=.5, curve=curve.in_quad)
        destroy(p, delay=.55)


# ---- Arazi üretimi (basit dalga tabanlı tepe/vadi) ----
def height_at(x, z, seed_x, seed_z):
    h = (
        math.sin((x + seed_x) * .3)
        + math.cos((z + seed_z) * .3)
        + math.sin((x + seed_x) * .13 + (z + seed_z) * .17) * 1.5
    )
    return max(1, round(3 + h))


def place_tree(x, y, z):
    trunk_height = random.randint(3, 5)
    for i in range(trunk_height):
        spawn_block((x, y + i, z), 5)
    top = y + trunk_height
    for dy in range(-2, 2):
        radius = 2 if dy < 0 else 1
        for dx in range(-radius, radius + 1):
            for dz in range(-radius, radius + 1):
                if abs(dx) == radius and abs(dz) == radius and random.random() < .6:
                    continue  # köşeleri yuvarla
                spawn_block((x + dx, top + dy, z + dz), 7)
    spawn_block((x, top + 2, z), 7)


def generate_world():
    seed_x = random.uniform(0, 1000)
    seed_z = random.uniform(0, 1000)
    heights = {}
    for x in range(WORLD_SIZE):
        for z in range(WORLD_SIZE):
            top = height_at(x, z, seed_x, seed_z)
            heights[(x, z)] = top
            for y in range(top + 1):
                if y == 0:
                    block_id = BEDROCK  # en altta kırılmaz ana kaya
                elif y == top:
                    block_id = 6 if top <= 1 else 2  # alçak yerler kumsal, diğerleri çim
                elif y >= top - 2:
                    block_id = 4  # altında birkaç kat toprak
                else:
                    block_id = 3  # en derinde taş
                spawn_block((x, y, z), block_id)

    # Ağaçlar (kenarlardan ve birbirinden biraz uzak)
    trees = []
    for _ in range(WORLD_SIZE // 3):
        x, z = random.randint(3, WORLD_SIZE - 4), random.randint(3, WORLD_SIZE - 4)
        if heights[(x, z)] <= 1 or abs(x - WORLD_SIZE // 2) + abs(z - WORLD_SIZE // 2) < 3:
            continue  # kumsala ve doğma noktasına ağaç dikme
        if any(abs(x - tx) + abs(z - tz) < 5 for tx, tz in trees):
            continue
        trees.append((x, z))
        place_tree(x, heights[(x, z)] + 1, z)


def spawn_point():
    cx = cz = WORLD_SIZE // 2
    column = [y for (x, y, z) in world if x == cx and z == cz]
    top = max(column) if column else 0
    return Vec3(cx, top + 1, cz)


def respawn():
    player.position = spawn_point()
    player.air_time = 0
    player.camera_pivot.rotation_x = 0


# ---- Kaydetme / yükleme ----
def save_world():
    data = {
        'blocks': {f'{x},{y},{z}': block.block_id for (x, y, z), block in world.items()},
        'player': [player.x, player.y, player.z, player.rotation_y],
        'chosen_block': chosen_block,
        'time': day_time,
    }
    with open(SAVE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    show_status('Dünya kaydedildi (F5)')


def load_world():
    global day_time
    if not os.path.exists(SAVE_FILE):
        show_status('Kayıtlı dünya bulunamadı')
        return False
    with open(SAVE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    clear_world()
    # Eski kayıtlarda sadece bloklar vardı, yenilerinde oyuncu bilgisi de var.
    blocks = data['blocks'] if 'blocks' in data else data
    for key, block_id in blocks.items():
        x, y, z = (int(v) for v in key.split(','))
        if block_id in BLOCK_TYPES:
            spawn_block((x, y, z), block_id)
    if 'player' in data:
        x, y, z, rot = data['player']
        player.position = Vec3(x, y, z)
        player.rotation_y = rot
    else:
        respawn()
    if data.get('chosen_block') in HOTBAR_IDS:
        set_chosen_block(data['chosen_block'])
    day_time = data.get('time', day_time)
    show_status('Dünya yüklendi (F9)')
    return True


def new_world():
    clear_world()
    generate_world()
    respawn()
    show_status('Yeni dünya oluşturuldu (F6)')


# ---- Gündüz / gece döngüsü ----
day_time = .3  # 0 = gece yarısı, .25 = sabah, .5 = öğle, .75 = akşam

night_overlay = Entity(parent=camera.ui, model='quad', color=color.rgba(0, 0, 0, 0), scale=(3, 2), z=1)
sun = Entity(model='sphere', color=color.rgb32(255, 230, 120), scale=8, shader=unlit_shader)
moon = Entity(model='sphere', color=color.rgb32(220, 220, 240), scale=5, shader=unlit_shader)

DAY_SKY = color.rgb32(255, 255, 255)
NIGHT_SKY = color.rgb32(25, 30, 60)
DAY_FOG = color.rgb32(190, 215, 255)
NIGHT_FOG = color.rgb32(10, 12, 25)


def update_day_night():
    global day_time
    day_time = (day_time + time.dt / DAY_LENGTH) % 1
    angle = (day_time - .25) * 2 * math.pi  # .25'te güneş doğuyor
    center = Vec3(WORLD_SIZE / 2, 0, WORLD_SIZE / 2)
    sun.position = center + Vec3(math.cos(angle) * 60, math.sin(angle) * 60, 10)
    moon.position = center - Vec3(math.cos(angle) * 60, math.sin(angle) * 60, 10)

    light = clamp(math.sin(angle) * 2 + .5, 0, 1)  # 1 = tam gündüz, 0 = tam gece
    sky.color = lerp(NIGHT_SKY, DAY_SKY, light)
    scene.fog_color = lerp(NIGHT_FOG, DAY_FOG, light)
    night_overlay.color = color.rgba(0, 0, .05, (1 - light) * .55)


def clock_string():
    minutes = int(day_time * 24 * 60)
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


# ---- Arayüz ----
hotbar_slots = {}
slot_size = .07
start_x = -(len(HOTBAR_IDS) - 1) * slot_size / 2

selected_text = Text(text='', position=(0, -.36), origin=(0, 0), scale=1.3, background=True)
status_text = Text(text='', position=(0, .45), origin=(0, 0), scale=1.3, color=color.yellow, background=True)
help_text = Text(
    text='Sol tık: Kır  Sağ tık: Koy  Orta tık: Bloğu seç  1-9/Tekerlek: Blok\n'
         'F: Uçma  Ctrl: Koş  F3: Bilgi  F5: Kaydet  F6: Yeni dünya  F9: Yükle  Esc: Duraklat',
    position=(-.88, -.44),
    scale=.75,
)
debug_text = Text(text='', position=(-.88, .48), scale=.9, background=True, enabled=False)
mode_text = Text(text='', position=(.88, .48), origin=(.5, .5), scale=1.1, color=color.azure)

# Nişangah (crosshair)
Entity(parent=camera.ui, model='quad', color=color.white, scale=(.008, .0015))
Entity(parent=camera.ui, model='quad', color=color.white, scale=(.0015, .008))

for i, block_id in enumerate(HOTBAR_IDS):
    info = BLOCK_TYPES[block_id]
    slot = Entity(
        parent=camera.ui,
        model='quad',
        texture=info['texture'],
        color=info['color'],
        scale=slot_size * .9,
        position=(start_x + i * slot_size, -.47 + slot_size / 2),
    )
    Text(parent=slot, text=str(block_id), scale=8, position=(-.4, -.4, -1), origin=(0, 0))
    hotbar_slots[block_id] = slot

pause_panel = Entity(parent=camera.ui, enabled=False, z=-1)
Entity(parent=pause_panel, model='quad', color=color.rgba(0, 0, 0, .6), scale=(3, 2))
Text(parent=pause_panel, text='DURAKLATILDI', origin=(0, 0), y=.08, scale=3)
Text(parent=pause_panel, text='Esc: Devam et     F5: Kaydet     Q: Kaydet ve çık', origin=(0, 0), y=-.03, scale=1.2)


def show_status(message):
    status_text.text = message
    invoke(setattr, status_text, 'text', '', delay=2)


def set_chosen_block(block_id):
    global chosen_block
    chosen_block = block_id
    info = BLOCK_TYPES[block_id]
    selected_text.text = f'Seçili blok: {info["name"]}'
    for bid, slot in hotbar_slots.items():
        slot.scale = slot_size * (1.15 if bid == block_id else .9)
    hand.texture = info['texture']
    hand.color = info['color']


def target_block():
    """Nişangahın baktığı ve erişim mesafesi içindeki blok."""
    e = mouse.hovered_entity
    if isinstance(e, Block) and distance(e.world_position, camera.world_position) <= REACH + .5:
        return e
    return None


def input(key):
    if key.isdigit() and int(key) in HOTBAR_IDS:
        set_chosen_block(int(key))
    if key == 'scroll up' or key == 'scroll down':
        idx = HOTBAR_IDS.index(chosen_block)
        step = -1 if key == 'scroll up' else 1
        set_chosen_block(HOTBAR_IDS[(idx + step) % len(HOTBAR_IDS)])

    block = target_block()
    if block:
        if key == 'right mouse down':
            spawn_block(block.position + mouse.normal, chosen_block, play_sound=True)
        if key == 'left mouse down':
            remove_block(block, play_sound=True)
        if key == 'middle mouse down' and block.block_id in HOTBAR_IDS:
            set_chosen_block(block.block_id)

    if key == 'f':
        toggle_fly()
    if key == 'f3':
        debug_text.enabled = not debug_text.enabled
    if key == 'f5':
        save_world()
    if key == 'f6':
        new_world()
    if key == 'f9':
        load_world()


def update():
    update_day_night()

    # Koşma / uçma
    sprinting = held_keys['left control'] or held_keys['control']
    player.speed = (10 if flying else 5) * (1.6 if sprinting else 1)
    if flying:
        player.y += (held_keys['space'] - held_keys['left shift']) * 8 * time.dt

    if player.y < VOID_Y:
        respawn()
        show_status('Boşluğa düştün! Yeniden doğdun.')

    # Elin yürürken hafifçe sallanması
    moving = held_keys['w'] or held_keys['a'] or held_keys['s'] or held_keys['d']
    bob = math.sin(time.time() * (14 if sprinting else 9)) * .02 if moving else 0
    hand.y = HAND_REST_POSITION.y + bob

    if debug_text.enabled:
        debug_text.text = (
            f'FPS: {round(1 / max(time.dt, 1e-4))}\n'
            f'X: {player.x:.1f}  Y: {player.y:.1f}  Z: {player.z:.1f}\n'
            f'Blok sayısı: {len(world)}\n'
            f'Saat: {clock_string()}'
        )
    mode_text.text = f'{clock_string()}' + ('   UÇUŞ' if flying else '')


# ---- Duraklatma (oyun durunca da çalışması için ignore_paused) ----
class PauseHandler(Entity):
    def __init__(self):
        super().__init__(ignore_paused=True)

    def input(self, key):
        if key == 'escape':
            application.paused = not application.paused
            pause_panel.enabled = application.paused
            mouse.locked = not application.paused
        elif application.paused and key == 'f5':
            save_world()
        elif application.paused and key == 'q':
            save_world()
            application.quit()


PauseHandler()


# ---- Oyuncu ----
player = FirstPersonController()
player.cursor.enabled = False  # varsayılan küçük pembe/kırmızı işaretçiyi kapat, yerine kendi nişangahımızı ve eli kullanıyoruz
flying = False


def toggle_fly():
    global flying
    flying = not flying
    player.gravity = 0 if flying else 1
    player.air_time = 0
    player.grounded = False
    show_status('Uçma modu AÇIK (Boşluk: yüksel, Shift: alçal)' if flying else 'Uçma modu KAPALI')


# Elde seçili blok duruyor
HAND_REST_ROTATION = Vec3(10, -15, -5)
HAND_REST_POSITION = Vec3(.55, -.45, .8)
hand = Entity(
    parent=camera,
    model='cube',
    scale=(.25, .25, .25),
    position=HAND_REST_POSITION,
    rotation=HAND_REST_ROTATION,
)


def swing_hand():
    hand.animate_rotation(HAND_REST_ROTATION + Vec3(-30, 15, 20), duration=.06, curve=curve.out_quad)
    invoke(hand.animate_rotation, HAND_REST_ROTATION, duration=.15, curve=curve.out_quad, delay=.07)


sky = Sky()
scene.fog_density = (20, 70)  # uzaklar sise karışsın
set_chosen_block(1)

if not (os.path.exists(SAVE_FILE) and load_world()):
    new_world()
    save_world()

app.run()
