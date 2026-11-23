"""The map editor's part for zombies' interact points, counters and triggers (see logic.py): the Interact tool, which
places interact points on the map, and the Triggers section, which lists the map's triggers and counters to edit in
the Details pane. LogicEditor is mixed into map_editor.Editor and works through the editor's own pieces (the Details
pane's Fields, begin_edit for undo, the section scrolling and drawing helpers)."""
import math

import pygame

from details import Field
from mapfile import (ACTION_KINDS, ACTION_LABELS, ACTION_WHO, ACTION_WHO_LABELS, BUY_COST_LABELS, BUY_COSTS,
                     CONDITION_KINDS, CONDITION_LABELS, MAX_ACTIONS, MAX_CONDITIONS, MAX_COUNTERS, MAX_INTERACTS,
                     MAX_NAME, MAX_TEXT, MAX_TRIGGERS, Action, Condition, Counter, Interact, Trigger, unique_thing_name)

INTERACT_FILL, INTERACT_EDGE = (170, 90, 220), (240, 210, 255)     # an interact point on the map
FIXED_EVENTS = (("game_start", "the game starts"), ("round_start", "a round starts"))
# What each kind of condition or action names, for its row in the Details pane.
CONDITION_NAMES = {"counter_at_least": "counter", "counter_below": "counter", "player_has": "item",
                   "team_has": "item", "door_open": "door", "door_closed": "door", "round_at_least": None}
ACTION_NAMES = {"open_door": "door", "close_door": "door", "add_counter": "counter", "set_counter": "counter",
                "give_item": "item", "take_item": "item", "effect": "effect", "light": "light",
                "spawn_enemies": "enemy", "event": "event", "give_money": None, "give_score": None,
                "message": None, "win": None}
AMOUNT_ACTIONS = ("add_counter", "set_counter", "give_money", "give_score", "give_item", "take_item",
                  "spawn_enemies")
WHO_ACTIONS = ("give_money", "give_score", "give_item", "take_item", "message")
TEXT_ACTIONS = ("message", "win")


def event_label(event):
    """An event in words: "the game starts", "Generator is used", "Fuse is picked up"..."""
    fixed = dict(FIXED_EVENTS)
    if event in fixed:
        return fixed[event]
    kind, _, name = event.partition(":")
    if name and kind == "used":
        return f"{name} is used"
    if name and kind == "picked":
        return f"{name} is picked up"
    if name and kind == "door":
        return f"{name} opens"
    if name and kind == "counter":
        return f"{name} changes"
    return f'"{event}" is fired'


def condition_text(c):
    if c.kind == "round_at_least":
        return f"round {c.amount:g} or later"
    if c.kind in ("counter_at_least", "counter_below"):
        return f"{c.name or '?'} {'>=' if c.kind == 'counter_at_least' else '<'} {c.amount:g}"
    if c.kind in ("player_has", "team_has"):
        return f"{'the player' if c.kind == 'player_has' else 'the team'} carries {c.amount:g} {c.name or '?'}"
    return f"{c.name or '?'} is {'open' if c.kind == 'door_open' else 'closed'}"


def action_text(a):
    if a.kind in ("open_door", "close_door"):
        return f"{'open' if a.kind == 'open_door' else 'close'} {a.name or '?'}"
    if a.kind == "add_counter":
        return f"{a.name or '?'} {'+' if a.amount >= 0 else '-'}{abs(a.amount):g}"
    if a.kind == "set_counter":
        return f"{a.name or '?'} = {a.amount:g}"
    if a.kind in ("give_money", "give_score"):
        what = f"${a.amount:g}" if a.kind == "give_money" else f"{a.amount:g} score"
        return f"give {what}" + (" to everyone" if a.who == "everyone" else "")
    if a.kind in ("give_item", "take_item"):
        return f"{'give' if a.kind == 'give_item' else 'take'} {a.amount:g} {a.name or '?'}"
    if a.kind == "message":
        return f'say "{a.text}"'
    if a.kind in ("effect", "light"):
        return f"{a.kind} {a.name or '?'}" + (f" at {a.at}" if a.at else "")
    if a.kind == "spawn_enemies":
        return f"send {a.amount:g} {a.name or 'enemies'}"
    if a.kind == "event":
        return f'fire "{a.name}"'
    return f'win ("{a.text}")' if a.text else "win"


class LogicEditor:
    """The Interact tool and the Triggers section (see the module's description)."""

    def init_logic_editor(self):
        self.triggers_mode = False              # the Triggers section is showing instead of the map
        self.triggers_scroll = 0
        self.triggers_selected = None           # ("trigger", index) or ("counter", index) being edited
        self.interact_selected = None           # index in level.interacts of the one being edited (Interact tool)

    # ---------------------------------------------------------------- what is selected

    def selected_trigger(self):
        chosen = self.triggers_selected
        if self.triggers_mode and chosen and chosen[0] == "trigger" and chosen[1] < len(self.level.triggers):
            return self.level.triggers[chosen[1]]
        return None

    def selected_counter(self):
        chosen = self.triggers_selected
        if self.triggers_mode and chosen and chosen[0] == "counter" and chosen[1] < len(self.level.counters):
            return self.level.counters[chosen[1]]
        return None

    def selected_interact(self):
        i = self.interact_selected
        if self.tool == "interact" and not self.section_open() and i is not None and i < len(self.level.interacts):
            return self.level.interacts[i]
        return None

    def logic_chosen(self):
        """What of the Interact tool or the Triggers section the Details pane edits, or None."""
        return self.selected_trigger() or self.selected_counter() or self.selected_interact()

    def logic_fields(self):
        trigger, counter, interact = self.selected_trigger(), self.selected_counter(), self.selected_interact()
        if trigger is not None:
            return self.trigger_fields(trigger)
        if counter is not None:
            return self.counter_fields(counter)
        if interact is not None:
            return self.interact_fields(interact)
        return None

    def logic_text(self):
        """(title, notes) of the Details pane for a trigger, counter or interact point, or None."""
        if self.selected_trigger() is not None:
            return "Trigger", ("When its event happens and every", "condition holds, its actions run in",
                               "order. Once: only the first time in", "a game. Events of things are picked",
                               "from the list; type your own name to", "wait for an \"Fire an event\" action.")
        if self.selected_counter() is not None:
            return "Counter", ("A number kept through a game, that", "triggers add to, set and test. The",
                               "HUD shows it (with its goal) when", "Show is on.")
        if self.selected_interact() is not None:
            return "Interact point", ("Zombies: pressing E beside it, a", "player who has what it asks for uses",
                                      "it, which fires \"<name> is used\" for", "the triggers. Once: it can be used",
                                      "once a game, then is gone. Click an", "atlas tile for its picture.")
        return None

    def delete_logic(self):
        """Delete the selected trigger, counter or interact point (True), or nothing is selected (False)."""
        level = self.level
        if self.selected_trigger() is not None:
            self.begin_edit()
            del level.triggers[self.triggers_selected[1]]
        elif self.selected_counter() is not None:
            self.begin_edit()
            del level.counters[self.triggers_selected[1]]
        elif self.selected_interact() is not None:
            self.begin_edit()
            del level.interacts[self.interact_selected]
            self.interact_selected = None
            return True
        else:
            return False
        self.triggers_selected = None
        return True

    def logic_delete_label(self):
        if self.selected_trigger() is not None:
            return "Delete trigger"
        if self.selected_counter() is not None:
            return "Delete counter"
        if self.selected_interact() is not None:
            return "Delete interact point"
        return None

    # ---------------------------------------------------------------- the Interact tool

    def interact_at(self, cell):
        return next((k for k, i in enumerate(self.level.interacts)
                     if (math.floor(i.x), math.floor(i.y)) == tuple(cell) and i.span == self.floor), None)

    def place_interact(self, cell):
        """Interact tool: an interact point in the middle of an open cell of this floor (selected), or select the one
        there."""
        level = self.level
        if not level.in_bounds(*cell):
            return
        found = self.interact_at(cell)
        if found is not None:
            self.interact_selected = found
            self.field_edit = self.menu_open = None
            return
        if not level.span_present(self.floor, *cell) or level.is_solid(*cell, self.floor):
            self.say("An interact point goes in an open cell")
            return
        if len(level.interacts) >= MAX_INTERACTS:
            self.say(f"A map has at most {MAX_INTERACTS} interact points")
            return
        self.begin_edit()
        name = self.new_logic_name("Button", [i.name for i in level.interacts])
        level.interacts.append(Interact(name, cell[0] + 0.5, cell[1] + 0.5, self.floor))
        self.interact_selected = len(level.interacts) - 1
        self.field_edit = self.menu_open = None
        self.tile_target = "tile"
        self.say(f"{name}: what it costs and needs in the Details pane; triggers say what using it does")

    def remove_interact(self, cell):
        found = self.interact_at(cell)
        if found is not None:
            self.begin_edit()
            del self.level.interacts[found]
            self.interact_selected = None

    def new_logic_name(self, base, taken, skip=None):
        taken = {n for n in taken if n != skip}
        return base if base not in taken else unique_thing_name(base, taken)

    def interact_fields(self, interact):
        def field(name, label, kind, **options):
            return Field(name, label, kind, (lambda n=name: getattr(interact, n)),
                         (lambda v, n=name: self.set_interact(n, v)), **options)

        fields = [field("name", "Name", "text"), field("prompt", "Press E to", "text"),
                  field("cost_kind", "Costs", "enum", choices=BUY_COSTS, labels=BUY_COST_LABELS)]
        if interact.cost_kind != "free":
            fields.append(field("cost", "Price", "num", step=50.0, low=0.0, high=1000000.0))
        fields.append(field("needs", "Needs item (blank: none)", "text"))
        if interact.needs:
            fields += [field("needs_amount", "... how many", "num", step=1.0, low=1.0, high=1000.0),
                       field("consume", "... taken", "enum", choices=(True, False),
                             labels={True: "Yes (handed over)", False: "No (just carried)"})]
        fields += [field("once", "Used", "enum", choices=(False, True),
                         labels={False: "Any number of times", True: "Once a game (then gone)"}),
                   field("tile", "Picture (-1: none)", "tile", low=-1, high=len(self.tiles) - 1),
                   field("size", "Picture size", "num", step=0.05, low=0.1, high=3.0)]
        used = sum(1 for t in self.level.triggers if t.on == f"used:{interact.name}")
        fields.append(Field("interact_triggers", "Triggers on it", "info",
                            (lambda: f"{used} (Triggers section, Y)"), None))
        return fields

    def set_interact(self, name, value):
        interact = self.selected_interact()
        if interact is None:
            return
        if name == "name":
            value = self.new_logic_name(str(value).strip()[:MAX_NAME] or "Button",
                                        [i.name for i in self.level.interacts], skip=interact.name)
        elif name in ("prompt", "needs"):
            value = str(value).strip()[:MAX_TEXT if name == "prompt" else MAX_NAME]
        elif name == "tile":
            value = int(value)
        if getattr(interact, name) == value:
            return
        self.begin_edit()
        if name == "name":
            self.level.rename_reference("interact", interact.name, value)
        setattr(interact, name, value)

    def draw_interacts(self, screen):
        """Interact points on this floor: a purple diamond with the name."""
        z = self.zoom
        origin = self.cell_rect(0, 0)
        radius = max(4, z * 0.32)
        for k, i in enumerate(self.level.interacts):
            if i.span != self.floor:
                continue
            cx, cy = origin.x + i.x * z, origin.y + i.y * z
            points = [(cx, cy - radius), (cx + radius, cy), (cx, cy + radius), (cx - radius, cy)]
            pygame.draw.polygon(screen, INTERACT_FILL, points)
            edge = (255, 205, 60) if k == self.interact_selected and self.tool == "interact" else INTERACT_EDGE
            pygame.draw.polygon(screen, edge, points, 2)
            if z >= 16:
                label = self.small.render(i.name, True, (255, 255, 255))
                screen.blit(label, label.get_rect(midtop=(cx, cy + radius + 1)))

    # ---------------------------------------------------------------- the Triggers section

    def toggle_triggers(self):
        self.triggers_mode = not self.triggers_mode
        self.guns_mode = self.prefabs_mode = self.effects_mode = self.lights_mode = self.settings_mode = False
        self.deselect()
        self.triggers_scroll = 0
        self.say("Triggers: what happens when things happen (zombies); counters keep numbers through a game"
                 if self.triggers_mode else "Back to the map")

    def known_events(self):
        """Every event the map's things can set off, for picking a trigger's event from."""
        level = self.level
        items = {e.item for e in level.entities + level.prefabs if e.effect == "item" and e.item}
        items |= {i.needs for i in level.interacts if i.needs}
        fired = {a.name for t in level.triggers for a in t.actions if a.kind == "event" and a.name}
        return ([e for e, _label in FIXED_EVENTS] + [f"used:{i.name}" for i in level.interacts]
                + [f"picked:{n}" for n in sorted(items)] + [f"door:{d.name}" for d in level.doors]
                + [f"counter:{c.name}" for c in level.counters] + sorted(fired))

    def trigger_summary(self, trigger):
        text = f"When {event_label(trigger.on)}"
        if trigger.conditions:
            text += "   if " + " and ".join(condition_text(c) for c in trigger.conditions)
        text += "   then " + (", ".join(action_text(a) for a in trigger.actions) or "nothing yet")
        return text + ("   (once)" if trigger.once else "")

    def counter_summary(self, counter):
        text = f"starts at {counter.start:g}" + (f", goal {counter.goal:g}" if counter.goal else "")
        return text + ("   on the HUD" + (f' as "{counter.label}"' if counter.label else "") if counter.show
                       else "   not shown")

    def triggers_rows(self):
        """([(rect, index)] of the triggers, Add trigger rect, [(rect, index)] of the counters, Add counter rect)."""
        area = self.map_area()
        width = self.settings_list_width()
        x, y = area.x + 20, area.y + 74 - self.triggers_scroll + 30
        triggers = []
        for i, trigger in enumerate(self.level.triggers):
            triggers.append((pygame.Rect(x, y, width, self.settings_row_height(self.trigger_summary(trigger), width)), i))
            y = triggers[-1][0].bottom + 4
        add_trigger = pygame.Rect(x, y, 220, 34)
        y = add_trigger.bottom + 16 + 30
        counters = []
        for i, counter in enumerate(self.level.counters):
            counters.append((pygame.Rect(x, y, width, self.settings_row_height(self.counter_summary(counter), width)), i))
            y = counters[-1][0].bottom + 4
        return triggers, add_trigger, counters, pygame.Rect(x, y, 220, 34)

    def triggers_content_bottom(self):
        return self.triggers_rows()[3].bottom + self.triggers_scroll + 20

    def triggers_click(self, pos):
        triggers, add_trigger, counters, add_counter = self.triggers_rows()
        if add_trigger.collidepoint(pos):
            self.add_trigger()
            return
        if add_counter.collidepoint(pos):
            self.add_counter()
            return
        for rect, choice in [(r, ("trigger", i)) for r, i in triggers] + [(r, ("counter", i)) for r, i in counters]:
            if rect.collidepoint(pos):
                self.triggers_selected = choice
                self.field_edit = self.menu_open = None
                return

    def draw_triggers(self, screen):
        area = self.map_area()
        screen.set_clip(area)
        pygame.draw.rect(screen, (30, 31, 36), area)
        self.set_scroll("triggers", self.triggers_scroll)
        top = area.y - self.triggers_scroll
        accent, dim = (255, 205, 60), (140, 142, 152)
        screen.blit(self.font.render("Triggers and counters", True, accent), (area.x + 20, top + 14))
        self.blit_fitted(screen, self.small, "Zombies: when something happens (a point used, an item picked up, a door "
                         "opened, a round", dim, (area.x + 20, top + 36), area.right - 14)
        self.blit_fitted(screen, self.small, "starting...) and its conditions hold, a trigger's actions run. "
                         "Counters keep numbers.", dim, (area.x + 20, top + 52), area.right - 14)
        triggers, add_trigger, counters, add_counter = self.triggers_rows()
        screen.blit(self.font.render("Triggers", True, accent), (area.x + 20, top + 80))
        for rect, i in triggers:
            trigger = self.level.triggers[i]
            self.draw_settings_row(screen, rect, trigger.name, self.trigger_summary(trigger),
                                   self.triggers_selected == ("trigger", i))
        self._draw_add_button(screen, add_trigger, "+ Add trigger")
        screen.blit(self.font.render("Counters", True, accent), (add_trigger.x, add_trigger.bottom + 24))
        for rect, i in counters:
            counter = self.level.counters[i]
            self.draw_settings_row(screen, rect, counter.name, self.counter_summary(counter),
                                   self.triggers_selected == ("counter", i))
        self._draw_add_button(screen, add_counter, "+ Add counter")
        self.draw_scrollbar(screen, "triggers")
        screen.set_clip(None)

    def add_trigger(self):
        if len(self.level.triggers) >= MAX_TRIGGERS:
            self.say(f"A map has at most {MAX_TRIGGERS} triggers")
            return
        self.begin_edit()
        name = self.new_logic_name("Trigger", [t.name for t in self.level.triggers])
        self.level.triggers.append(Trigger(name, actions=[Action("message", text="Something happened")]))
        self.triggers_selected = ("trigger", len(self.level.triggers) - 1)
        self.field_edit = self.menu_open = None
        self.say(f"{name}: pick its event, then add conditions and actions in the Details pane")

    def add_counter(self):
        if len(self.level.counters) >= MAX_COUNTERS:
            self.say(f"A map has at most {MAX_COUNTERS} counters")
            return
        self.begin_edit()
        name = self.new_logic_name("Counter", [c.name for c in self.level.counters])
        self.level.counters.append(Counter(name))
        self.triggers_selected = ("counter", len(self.level.counters) - 1)
        self.field_edit = self.menu_open = None

    # ---------------------------------------------------------------- a trigger in the Details pane

    def name_choices(self, what):
        """The names a condition's or action's name can be picked from, for what it is about (None: typed)."""
        level = self.level
        return {"door": [d.name for d in level.doors], "counter": [c.name for c in level.counters],
                "effect": [e.name for e in level.effects], "light": [light.name for light in level.lights],
                "enemy": [""] + [e.name for e in level.enemies]}.get(what)

    def name_field(self, key, label, what, get, set_):
        """A row for the name a condition or action is about: picked from the map's things of that kind, or typed."""
        choices = self.name_choices(what)
        if choices is None:
            return Field(key, label, "text", get, set_)
        current = get()
        choices = tuple(choices) + ((current,) if current not in choices else ())
        labels = {n: n or ("(any)" if what == "enemy" else "(none)") for n in choices}
        if what != "enemy" and "" in labels and "" not in self.name_choices(what):
            labels[""] = "(pick one)"
        return Field(key, label, "enum", get, set_, choices=choices, labels=labels)

    def trigger_fields(self, trigger):
        def field(name, label, kind, **options):
            return Field(name, label, kind, (lambda n=name: getattr(trigger, n)),
                         (lambda v, n=name: self.set_trigger(n, v)), **options)

        events = tuple(self.known_events())
        fields = [field("name", "Name", "text"),
                  Field("on_info", "When", "info", (lambda: event_label(trigger.on)), None),
                  Field("pick_event", "Pick the event", "menu", None, lambda v: self.set_trigger("on", v),
                        choices=events, labels={e: event_label(e) for e in events},
                        text_override="Pick what it waits for"),
                  field("on", "... or type an event", "text"),
                  field("once", "Runs", "enum", choices=(False, True),
                        labels={False: "Every time", True: "Once a game"}),
                  Field("if_header", "If (all of these)", "header", None, None)]
        for j, condition in enumerate(trigger.conditions):
            fields += self.condition_fields(j, condition)
        if len(trigger.conditions) < MAX_CONDITIONS:
            fields.append(Field("add_condition", "Add condition", "button", None, None, action=self.add_condition,
                                text_override="+ Add a condition"))
        fields.append(Field("then_header", "Then", "header", None, None))
        for j, action in enumerate(trigger.actions):
            fields += self.action_fields(j, action)
        if len(trigger.actions) < MAX_ACTIONS:
            fields.append(Field("add_action", "Add action", "button", None, None, action=self.add_action,
                                text_override="+ Add an action"))
        return fields

    def condition_fields(self, j, condition):
        def get(name):
            return lambda: getattr(condition, name)

        def put(name):
            return lambda v: self.set_part("conditions", j, name, v)

        fields = [Field(f"c{j}", f"Condition {j + 1}", "header", None, None,
                        action=lambda: self.remove_part("conditions", j)),
                  Field(f"c{j}_kind", "Is", "enum", get("kind"), put("kind"), choices=CONDITION_KINDS,
                        labels=CONDITION_LABELS)]
        what = CONDITION_NAMES[condition.kind]
        if what is not None:
            fields.append(self.name_field(f"c{j}_name", what.capitalize(), what, get("name"), put("name")))
        label = {"round_at_least": "Round", "player_has": "How many", "team_has": "How many"}.get(condition.kind,
                                                                                                 "Number")
        if condition.kind not in ("door_open", "door_closed"):
            fields.append(Field(f"c{j}_amount", label, "num", get("amount"), put("amount"), step=1.0, low=-1e6,
                                high=1e6))
        return fields

    def action_fields(self, j, action):
        def get(name):
            return lambda: getattr(action, name)

        def put(name):
            return lambda v: self.set_part("actions", j, name, v)

        fields = [Field(f"a{j}", f"Action {j + 1}", "header", None, None, action=lambda: self.remove_part("actions", j)),
                  Field(f"a{j}_kind", "Do", "enum", get("kind"), put("kind"), choices=ACTION_KINDS,
                        labels=ACTION_LABELS)]
        what = ACTION_NAMES[action.kind]
        if what is not None:
            label = {"enemy": "Kind of enemy", "event": "Event name"}.get(what, what.capitalize())
            fields.append(self.name_field(f"a{j}_name", label, what, get("name"), put("name")))
        if action.kind in AMOUNT_ACTIONS:
            fields.append(Field(f"a{j}_amount", "How many" if action.kind != "give_money" else "Money", "num",
                                get("amount"), put("amount"), step=1.0 if action.kind != "give_money" else 50.0,
                                low=-1e6, high=1e6))
        if action.kind in TEXT_ACTIONS:
            fields.append(Field(f"a{j}_text", "Text", "text", get("text"), put("text")))
        if action.kind in WHO_ACTIONS:
            fields.append(Field(f"a{j}_who", "For", "enum", get("who"), put("who"), choices=ACTION_WHO,
                                labels=ACTION_WHO_LABELS))
        if action.kind in ("effect", "light"):
            places = ("",) + tuple(i.name for i in self.level.interacts)
            if action.at not in places:
                places += (action.at,)
            fields.append(Field(f"a{j}_at", "At", "enum", get("at"), put("at"), choices=places,
                                labels={p: p or "the player who set it off" for p in places}))
        return fields

    def set_trigger(self, name, value):
        trigger = self.selected_trigger()
        if trigger is None:
            return
        if name == "name":
            value = self.new_logic_name(str(value).strip()[:MAX_NAME] or "Trigger",
                                        [t.name for t in self.level.triggers], skip=trigger.name)
        elif name == "on":
            value = str(value).strip()[:MAX_TEXT] or "game_start"
        if getattr(trigger, name) == value:
            return
        self.begin_edit()
        setattr(trigger, name, value)

    def set_part(self, which, j, name, value):
        """Change one setting of the selected trigger's condition or action j (one undo step)."""
        trigger = self.selected_trigger()
        parts = getattr(trigger, which) if trigger is not None else []
        if not 0 <= j < len(parts):
            return
        if name in ("name", "text", "at"):
            value = str(value).strip()[:MAX_TEXT if name == "text" else MAX_NAME]
        if getattr(parts[j], name) == value:
            return
        self.begin_edit()
        part = getattr(self.selected_trigger(), which)[j]
        setattr(part, name, value)
        if name == "kind":                              # (what it names belongs to the old kind)
            part.name = ""

    def add_condition(self):
        trigger = self.selected_trigger()
        if trigger is not None and len(trigger.conditions) < MAX_CONDITIONS:
            self.begin_edit()
            name = self.level.counters[0].name if self.level.counters else ""
            self.selected_trigger().conditions.append(Condition("counter_at_least", name, 1.0))

    def add_action(self):
        trigger = self.selected_trigger()
        if trigger is not None and len(trigger.actions) < MAX_ACTIONS:
            self.begin_edit()
            self.selected_trigger().actions.append(Action("message", text="Something happened"))

    def remove_part(self, which, j):
        trigger = self.selected_trigger()
        if trigger is not None and 0 <= j < len(getattr(trigger, which)):
            self.begin_edit()
            del getattr(self.selected_trigger(), which)[j]

    # ---------------------------------------------------------------- a counter in the Details pane

    def counter_fields(self, counter):
        def field(name, label, kind, **options):
            return Field(name, label, kind, (lambda n=name: getattr(counter, n)),
                         (lambda v, n=name: self.set_counter(n, v)), **options)

        return [field("name", "Name", "text"), field("label", "HUD calls it (blank: name)", "text"),
                field("start", "Starts at", "num", step=1.0, low=-1e6, high=1e6),
                field("goal", "Goal (0: none)", "num", step=1.0, low=0.0, high=1e6),
                field("show", "On the HUD", "enum", choices=(True, False), labels={True: "Shown", False: "Hidden"})]

    def set_counter(self, name, value):
        counter = self.selected_counter()
        if counter is None:
            return
        if name == "name":
            value = self.new_logic_name(str(value).strip()[:MAX_NAME] or "Counter",
                                        [c.name for c in self.level.counters], skip=counter.name)
        elif name == "label":
            value = str(value).strip()[:MAX_TEXT]
        if getattr(counter, name) == value:
            return
        self.begin_edit()
        if name == "name":
            self.level.rename_reference("counter", counter.name, value)
        setattr(counter, name, value)
