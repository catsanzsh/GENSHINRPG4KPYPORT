from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from ursina.shaders import lit_with_shadows_shader
from perlin_noise import PerlinNoise  # Ensure 'perlin-noise' package is installed
import random
import math

# --- App and Window Setup ---
app = Ursina()
window.fps_counter.enabled = True
window.vsync = False
application.target_frame_rate = 144
window.title = 'Ursina Impact'

Sky(color=color.rgb(135, 206, 235))
scene.fog_density = 0.02
scene.fog_color = color.rgb(200, 200, 220)

# --- Game Data ---
CHARACTERS = {
    'Traveler': {'color': color.yellow, 'element': 'Anemo', 'hp': 100, 'atk': 10, 'skill_cd': 5, 'burst_cd': 15},
    'Amber': {'color': color.orange, 'element': 'Pyro', 'hp': 80, 'atk': 12, 'skill_cd': 8, 'burst_cd': 20},
    'Kaeya': {'color': color.azure, 'element': 'Cryo', 'hp': 90, 'atk': 11, 'skill_cd': 6, 'burst_cd': 18},
    'Lisa': {'color': color.violet, 'element': 'Electro', 'hp': 70, 'atk': 15, 'skill_cd': 7, 'burst_cd': 22}
}

ELEMENTAL_REACTIONS = {
    ('Pyro', 'Cryo'): ('Melt', 2.0),
    ('Cryo', 'Pyro'): ('Melt', 1.5),
    ('Pyro', 'Electro'): ('Overloaded', 1.8),
    ('Electro', 'Pyro'): ('Overloaded', 1.8),
    ('Cryo', 'Electro'): ('Superconduct', 1.4),
    ('Electro', 'Cryo'): ('Superconduct', 1.4)
}

# --- Terrain Generation ---
class Terrain(Entity):
    def __init__(self, size=128, height=10):
        super().__init__(model=None, collider=None)
        self.size = size
        self.height = height
        self.terrain_model = self.generate_terrain()
        self.model = self.terrain_model
        self.texture = 'grass'
        self.scale = (self.size, self.height, self.size)
        self.collider = 'mesh'
        self.shader = lit_with_shadows_shader

    def generate_terrain(self):
        noise = PerlinNoise(octaves=4, seed=random.randint(1, 1000))
        subdivision = self.size
        verts = []
        tris = []
        uvs = []

        for x in range(subdivision):
            for z in range(subdivision):
                y = noise([x / subdivision, z / subdivision])
                verts.append(Vec3(x / subdivision - 0.5, y, z / subdivision - 0.5))
                uvs.append((x / subdivision, z / subdivision))

        for x in range(subdivision - 1):
            for z in range(subdivision - 1):
                idx = x * subdivision + z
                tris.extend([idx, idx + 1, idx + subdivision])
                tris.extend([idx + 1, idx + subdivision + 1, idx + subdivision])

        return Mesh(vertices=verts, triangles=tris, uvs=uvs)

# --- Projectile ---
class Bullet(Entity):
    def __init__(self, position, direction, damage, element, reaction_checker):
        super().__init__(
            model='sphere',
            color=CHARACTERS[player.active_char_name]['color'],
            scale=0.3,
            position=position,
            collider='sphere'
        )
        self.direction = direction
        self.damage = damage
        self.element = element
        self.reaction_checker = reaction_checker
        destroy(self, delay=5)

    def update(self):
        speed = 25
        distance_this_frame = speed * time.dt
        hit_info = raycast(self.position, self.direction, distance=distance_this_frame, ignore=(self,))
        if hit_info.hit:
            if hasattr(hit_info.entity, 'is_enemy') and hit_info.entity.is_enemy:
                self.reaction_checker(hit_info.entity, self.damage, self.element)
                destroy(self)
        else:
            self.position += self.direction * distance_this_frame

# --- Character and Player ---
class GenshinCharacter(Entity):
    def __init__(self, char_name):
        self.char_name = char_name
        self.char_data = CHARACTERS[char_name]
        super().__init__(model='cube', color=self.char_data['color'], scale=(0, 0, 0))
        self.hp = self.char_data['hp']
        self.max_hp = self.char_data['hp']
        self.element = self.char_data['element']
        self.atk = self.char_data['atk']
        self.is_fallen = False

    def take_damage(self, amount):
        if self.is_fallen:
            return
        self.hp -= amount
        ui_manager.show_feedback(f"-{int(amount)} HP", color.red, position=Vec2(-0.2, 0.2))
        if self.hp <= 0:
            self.hp = 0
            self.is_fallen = True
            self.visible = False
            ui_manager.show_feedback(f"{self.char_name} has fallen!", color.red, scale=2)
            player.handle_character_fallen()
        ui_manager.update_bars(self)

    def heal(self, amount):
        if self.is_fallen:
            self.is_fallen = False
            player.revive_character(self.char_name)
        self.hp = min(self.max_hp, self.hp + amount)
        ui_manager.update_bars(self)
        ui_manager.show_feedback(f"+{int(amount)} HP", color.green, position=Vec2(-0.2, 0.2))

class Player(FirstPersonController):
    def __init__(self):
        super().__init__(speed=8, jump_height=2.5, position=(0, 15, 0))
        self.cursor.visible = False
        self.gravity = 1
        self.team = {name: GenshinCharacter(name) for name in CHARACTERS.keys()}
        self.active_char_name = 'Traveler'
        self.active_character_entity = None
        self.stamina = 100
        self.max_stamina = 100
        self.cooldowns = {'attack': 0, 'skill': 0, 'burst': 0, 'switch': 0}
        self.switch_character('Traveler')

    @property
    def active_character(self):
        return self.team[self.active_char_name]

    def switch_character(self, char_name):
        if self.cooldowns['switch'] > 0 or char_name == self.active_char_name:
            return
        if self.team[char_name].is_fallen:
            ui_manager.show_feedback("Character has fallen!", color.orange)
            return
        self.active_char_name = char_name
        if self.active_character_entity:
            destroy(self.active_character_entity)
        self.active_character_entity = Entity(
            parent=self,
            model='cube',
            color=self.active_character.char_data['color'],
            scale=(0.8, 1.8, 0.8),
            position=(0, -0.9, 0)
        )
        self.cooldowns['switch'] = 1
        ui_manager.update_character_info(self.active_char_name, self.active_character)
        ui_manager.update_active_character_icon(list(CHARACTERS.keys()).index(char_name))

    def attack(self):
        if self.cooldowns['attack'] > 0:
            return
        start_pos = self.camera_pivot.world_position + self.forward * 1.5
        Bullet(
            position=start_pos,
            direction=self.forward,
            damage=self.active_character.atk,
            element=self.active_character.element,
            reaction_checker=self.check_elemental_reaction
        )
        self.cooldowns['attack'] = 0.5

    def elemental_skill(self):
        if self.cooldowns['skill'] > 0:
            return
        ui_manager.show_feedback(f"{self.active_char_name}'s Skill!", self.active_character.char_data['color'])
        skill_effect = Entity(
            model='sphere',
            color=self.active_character.char_data['color'],
            scale=0.1,
            position=self.position + self.forward * 3,
            collider='sphere'
        )

        def check_skill_hits():
            hit_info = skill_effect.intersects()
            for entity in hit_info.entities:
                if hasattr(entity, 'is_enemy'):
                    self.check_elemental_reaction(entity, self.active_character.atk * 1.5, self.active_character.element)
            destroy(skill_effect)

        skill_effect.animate_scale(5, duration=0.5, curve=curve.out_quad)
        invoke(check_skill_hits, delay=0.5)
        self.cooldowns['skill'] = self.active_character.char_data['skill_cd']

    def elemental_burst(self):
        if self.cooldowns['burst'] > 0:
            return
        ui_manager.show_feedback(f"{self.active_char_name}'s Burst!", self.active_character.char_data['color'], scale=2.5)
        burst_effect = Entity(
            model='sphere',
            color=self.active_character.char_data['color'],
            scale=0.1,
            position=self.position,
            alpha=0.5
        )
        burst_effect.animate_scale(20, duration=1, curve=curve.out_expo)
        for enemy in scene.entities:
            if hasattr(enemy, 'is_enemy') and enemy.is_enemy:
                if distance(enemy.position, self.position) < 10:
                    self.check_elemental_reaction(enemy, self.active_character.atk * 4, self.active_character.element)
        destroy(burst_effect, delay=1)
        self.cooldowns['burst'] = self.active_character.char_data['burst_cd']

    def check_elemental_reaction(self, enemy, base_damage, atk_element):
        damage = base_damage
        reaction_name = None
        if enemy.element_applied:
            reaction_key = (atk_element, enemy.element_applied)
            if reaction_key in ELEMENTAL_REACTIONS:
                reaction_name, multiplier = ELEMENTAL_REACTIONS[reaction_key]
                damage *= multiplier
        enemy.take_damage(damage, atk_element, reaction_name)

    def handle_character_fallen(self):
        available_chars = [name for name, char in self.team.items() if not char.is_fallen]
        if available_chars:
            self.switch_character(available_chars[0])
        else:
            ui_manager.show_game_over()
            self.speed = 0
            self.mouse_sensitivity = Vec2(0, 0)

    def revive_character(self, char_name):
        index = list(self.team.keys()).index(char_name)
        ui_manager.char_icons[index].color = CHARACTERS[char_name]['color']

    def update(self):
        super().update()
        if self.y < -10:
            self.position = (0, 20, 0)
        for key in self.cooldowns:
            if self.cooldowns[key] > 0:
                self.cooldowns[key] -= time.dt
        if held_keys['left shift'] and self.stamina > 0:
            self.speed = 15
            self.stamina -= 20 * time.dt
        else:
            self.speed = 8
            if self.stamina < self.max_stamina:
                self.stamina += 10 * time.dt
        self.stamina = clamp(self.stamina, 0, self.max_stamina)
        ui_manager.update_bars(self.active_character)
        ui_manager.update_cooldown_text(self.cooldowns)
        waypoints = [e for e in scene.entities if isinstance(e, Waypoint)]
        for waypoint in waypoints:
            if distance(self.position, waypoint.position) < 3:
                ui_manager.show_interaction_prompt(True)
                if held_keys['f']:
                    for char in self.team.values():
                        char.heal(char.max_hp)
                    ui_manager.show_feedback("Team fully healed!", color.cyan)
                break
        else:
            ui_manager.show_interaction_prompt(False)

# --- Enemy AI ---
class Enemy(Entity):
    def __init__(self, position, element_type=None):
        super().__init__(
            model='cube',
            color=color.dark_gray,
            scale=(1, 2, 1),
            position=position,
            collider='box',
            shader=lit_with_shadows_shader
        )
        self.is_enemy = True
        self.max_hp = 50
        self.hp = self.max_hp
        self.speed = 3
        self.attack_range = 2.5
        self.attack_cooldown = 0
        self.element_applied = None
        self.element_timer = 0
        self.elemental_indicator = Entity(
            parent=self,
            model='sphere',
            scale=0.3,
            position=(0, 1.2, 0),
            enabled=False
        )
        self.health_bar_bg = Entity(
            parent=self,
            model='quad',
            color=color.black,
            scale=(1.2, 0.12),
            position=(0, 1.5, 0),
            billboard=True
        )
        self.health_bar = Entity(
            parent=self,
            model='quad',
            color=color.red,
            scale=(1.1, 0.1),
            position=(0, 1.5, 0),
            billboard=True
        )

    def take_damage(self, damage, element, reaction=None):
        self.hp -= damage
        self.health_bar.scale_x = (self.hp / self.max_hp) * 1.1
        dmg_text = Text(
            f"{int(damage)}",
            position=self.screen_position,
            origin=(0, 0),
            scale=2,
            color=color.white
        )
        if reaction:
            dmg_text.color = color.orange
            reaction_text = Text(
                reaction,
                position=self.screen_position + Vec3(0, -0.05, 0),
                origin=(0, 0),
                scale=2.5,
                color=color.orange
            )
            reaction_text.animate_scale(1, duration=0.5, curve=curve.out_bounce)
            destroy(reaction_text, delay=1)
        dmg_text.animate_position(dmg_text.position + Vec3(0, 0.1, 0), duration=1, curve=curve.out_quad)
        dmg_text.fade_out(duration=1)
        destroy(dmg_text, delay=1)
        self.element_applied = element
        self.elemental_indicator.enabled = True
        self.elemental_indicator.color = CHARACTERS[next(c for c, d in CHARACTERS.items() if d['element'] == element)]['color']
        self.element_timer = 5
        if self.hp <= 0:
            destroy(self)

    def update(self):
        if not player.active_character or player.active_character.is_fallen:
            return
        if self.element_applied:
            self.element_timer -= time.dt
            if self.element_timer <= 0:
                self.element_applied = None
                self.elemental_indicator.enabled = False
        self.look_at_2d(player.position, 'y')
        dist = distance_xz(self.position, player.position)
        if dist > self.attack_range:
            self.position += self.forward * self.speed * time.dt
        else:
            if self.attack_cooldown <= 0:
                player.active_character.take_damage(10)
                self.attack_cooldown = 2
        if self.attack_cooldown > 0:
            self.attack_cooldown -= time.dt

# --- UI Manager ---
class UIManager:
    def __init__(self):
        self.char_name_text = Text('', position=(-0.85, 0.48), scale=1.8)
        self.hp_bar = Entity(
            parent=camera.ui,
            model='quad',
            color=color.green,
            scale=(0.4, 0.02),
            position=(-0.65, 0.45),
            origin=(-0.5, 0)
        )
        self.stamina_bar = Entity(
            parent=camera.ui,
            model='quad',
            color=color.yellow,
            scale=(0.4, 0.02),
            position=(-0.65, 0.42),
            origin=(-0.5, 0)
        )
        self.char_icons = []
        for i, (name, data) in enumerate(CHARACTERS.items()):
            icon = Button(
                text=str(i + 1),
                color=data['color'],
                scale=0.06,
                position=(-0.85 + i * 0.07, -0.4)
            )
            icon.on_click = Func(player.switch_character, name)
            self.char_icons.append(icon)
        self.update_active_character_icon(0)
        self.skill_text = Text('E: Ready', position=(0.85, -0.35), origin=(1, 0), scale=1.5)
        self.burst_text = Text('Q: Ready', position=(0.85, -0.4), origin=(1, 0), scale=1.5)
        self.interaction_prompt = Text(
            'Press F to interact',
            position=(0, -0.2),
            origin=(0, 0),
            scale=1.5,
            enabled=False
        )

    def update_character_info(self, char_name, character):
        self.char_name_text.text = f"{char_name} <{character.element}>"
        self.char_name_text.color = character.char_data['color']
        self.update_bars(character)

    def update_active_character_icon(self, index):
        for i, icon in enumerate(self.char_icons):
            icon.scale = 0.07 if i == index else 0.06
            icon.z = -1 if i == index else 0

    def update_bars(self, character):
        self.hp_bar.scale_x = 0.4 * (character.hp / character.max_hp) if character.max_hp > 0 else 0
        self.stamina_bar.scale_x = 0.4 * (player.stamina / player.max_stamina) if player.max_stamina > 0 else 0

    def update_cooldown_text(self, cooldowns):
        self.skill_text.text = f'E: {"Ready" if cooldowns["skill"] <= 0 else f"{cooldowns["skill"]:.1f}s"}'
        self.burst_text.text = f'Q: {"Ready" if cooldowns["burst"] <= 0 else f"{cooldowns["burst"]:.1f}s"}'

    def show_feedback(self, text, color, scale=2, duration=2, position=Vec2(0, 0.25)):
        feedback = Text(text, origin=(0, 0), scale=scale, color=color, position=position)
        feedback.fade_out(duration=duration)
        destroy(feedback, delay=duration)

    def show_interaction_prompt(self, show):
        self.interaction_prompt.enabled = show

    def show_game_over(self):
        Panel(z=1, scale=10, model='quad', color=color.black90)
        Text("All characters have fallen.", scale=3, origin=(0, 0), position=(0, 0.1))
        Text("Game Over", scale=5, origin=(0, 0), position=(0, 0))

# --- World Objects ---
class Waypoint(Entity):
    def __init__(self, position):
        super().__init__(
            model='diamond',
            color=color.cyan,
            scale=(1, 3, 1),
            position=position,
            shader=lit_with_shadows_shader
        )
        self.glow = Entity(
            parent=self,
            model='sphere',
            color=color.rgba(0, 255, 255, 100),
            scale=3,
            add_to_scene_entities=False
        )
        self.glow.animate_scale(3.5, duration=2, curve=curve.in_out_sine, loop=True)

class Tree(Entity):
    def __init__(self, position):
        super().__init__(
            model='cube',
            color=color.brown,
            scale=(1, 8, 1),
            position=position,
            collider='box',
            shader=lit_with_shadows_shader
        )
        Entity(
            parent=self,
            model='sphere',
            color=color.green,
            scale=(6, 4, 6),
            position=(0, 2.5, 0),
            shader=lit_with_shadows_shader
        )

# --- Input Handling ---
def input(key):
    if not hasattr(player, 'active_character') or player.active_character.is_fallen:
        return
    if key == 'left mouse down':
        player.attack()
    elif key == 'e':
        player.elemental_skill()
    elif key == 'q':
        player.elemental_burst()
    elif key in '1234':
        index = int(key) - 1
        if index < len(CHARACTERS):
            char_name = list(CHARACTERS.keys())[index]
            player.switch_character(char_name)

# --- Game Initialization ---
terrain = Terrain(size=128)
pivot = Entity()
DirectionalLight(parent=pivot, y=2, z=3, shadows=True, rotation=(45, -45, 0))

player = Player()
ui_manager = UIManager()

for _ in range(20):
    Tree(position=(random.uniform(-60, 60), 0, random.uniform(-60, 60)))
for _ in range(5):
    Waypoint(position=(random.uniform(-50, 50), 0, random.uniform(-50, 50)))
for _ in range(15):
    Enemy(position=(random.uniform(-50, 50), 5, random.uniform(-50, 50)))

app.run()
