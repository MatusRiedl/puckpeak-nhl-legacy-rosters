"""What the page can call (pywebview's js_api). Every method only hands over to a controller; an
unexpected error is written to the error log and told to the page, it never takes the window down.
pywebview runs each call in a thread of its own; the controllers lock their state. Attributes start
with an underscore so pywebview does not offer (or walk into) them."""
import functools

from .. import __version__, datasource
from ..app import jobs, texts as X


def _safe(method):
    @functools.wraps(method)
    def call(self, *args):
        try:
            return method(self, *args)
        except Exception as err:            # the details go to the error log, the page goes on
            return {'error': jobs.log_unexpected(err)}
    return call


class Api:
    def __init__(self, host, update, editor=None, uniforms=None, equipment=None, lines=None, strategy=None,
                 calendar=None, office=None, prospects=None, career=None):
        self._host, self._update, self._editor, self._uniforms = host, update, editor, uniforms
        self._equipment, self._lines, self._strategy = equipment, lines, strategy
        self._calendar, self._office, self._prospects = calendar, office, prospects
        self._career = career

    # --- the page -------------------------------------------------------------------------------
    @_safe
    def ready(self):
        """The page has loaded: everything it shows, then changes as they come."""
        message = self._host.first()
        message['meta'] = {'version': __version__, 'tagline': X.TAGLINE, 'site_label': X.SITE_LABEL}
        self._host.start_pushing()
        return message

    @_safe
    def open_site(self):
        self._host.open_url(X.SITE)

    @_safe
    def open_discord(self):
        self._host.open_url(X.DISCORD)

    @_safe
    def open_error_log(self):
        path = datasource.app_dir('logs', 'error.log')
        import os
        if not os.path.exists(path):
            with open(path, 'a', encoding='utf-8'):
                pass
        self._host.open_path(path)

    @_safe
    def tab(self, name):
        """The page shows tab `name` (setup, update, patch, roster, lines, strategy, jerseys, calendar, office,
        prospects)."""
        if self._editor is not None:
            self._editor.show_tab('roster' if name == 'editor' else str(name))

    # --- the team list (left of the team tabs) ---------------------------------------------------------
    @_safe
    def rail_league(self, league):
        self._editor.set_league(league)

    @_safe
    def rail_team(self, team):
        self._editor.pick_team(team)

    @_safe
    def rail_step(self, step):
        self._editor.rail_step(int(step))

    # --- the Update tab -------------------------------------------------------------------------
    @_safe
    def pick_rpcs3(self):
        self._update.pick_rpcs3()

    @_safe
    def pick_game(self, folder=False):
        self._update.pick_game(bool(folder))

    @_safe
    def set_check_updates(self, on):
        self._update.set_check_updates(bool(on))

    @_safe
    def check_updates_now(self):
        self._update.check_for_update(force=True)

    @_safe
    def set_export_only(self, on):
        self._update.set_export_only(bool(on))

    @_safe
    def pick_export_file(self):
        self._update.pick_export_file()

    @_safe
    def select_roster(self, folder):
        self._update.select(folder)

    @_safe
    def open_roster_folder(self, folder):
        self._update.open_roster_folder(folder)

    @_safe
    def ask_delete(self, folder):
        self._update.ask_delete(folder)

    @_safe
    def set_step(self, key, on):
        self._update.set_step(key, bool(on))

    @_safe
    def toggle_restore(self, key):
        self._update.toggle_restore(key)

    @_safe
    def restore_default(self):
        self._update.restore_default()

    @_safe
    def remove_photos(self):
        self._update.remove_photos()

    @_safe
    def patch(self):
        self._update.patch()

    @_safe
    def unpatch(self):
        self._update.unpatch()

    @_safe
    def set_patch_switch(self, key, on):
        self._update.set_patch_switch(key, bool(on))

    @_safe
    def set_save_mode(self, mode):
        self._update.set_save_mode(mode)

    @_safe
    def set_save_for(self, value):
        self._update.set_save_for(value)

    @_safe
    def set_name(self, text):
        self._update.set_name(text)

    @_safe
    def start(self):
        self._update.start()

    @_safe
    def result_action(self, action):
        self._update.result_action(action)

    @_safe
    def answer(self, ident, answer):
        self._update.answer(ident, answer)

    # --- the Roster editor ------------------------------------------------------------------------
    @_safe
    def editor_league(self, league):
        self._editor.set_league(league)

    @_safe
    def editor_team(self, team):
        self._editor.pick_team(team)

    @_safe
    def editor_search(self, text):
        self._editor.search(text)

    @_safe
    def editor_player(self, ident, card=None):
        self._editor.pick_player(str(ident), card or None)

    @_safe
    def editor_new_player(self):
        self._editor.new_player()

    @_safe
    def editor_apply(self, card):
        self._editor.apply(card or {})

    @_safe
    def editor_undo(self):
        self._editor.undo()

    @_safe
    def editor_photo(self):
        self._editor.choose_photo()

    @_safe
    def editor_save_mode(self, mode):
        self._editor.set_save_mode(mode)

    @_safe
    def editor_name(self, text):
        self._editor.set_name(text)

    @_safe
    def editor_save(self, card=None):
        self._editor.save(card or None)

    @_safe
    def team_open(self):
        self._editor.team_open()

    @_safe
    def team_logo(self):
        self._editor.team_choose_logo()

    @_safe
    def team_apply(self, values):
        self._editor.team_apply(values or {})

    @_safe
    def team_undo(self):
        self._editor.team_undo()

    @_safe
    def edits_open(self):
        self._editor.edits_open()

    @_safe
    def edits_remove(self, kind, key):
        self._editor.edits_remove(kind, str(key))

    @_safe
    def modal_close(self):
        self._editor.close_modal()

    @_safe
    def face_open(self):
        self._editor.face_open()

    @_safe
    def face_search(self, text):
        self._editor.face_search(str(text or ''))

    @_safe
    def face_pick_player(self, who):
        self._editor.face_pick_player(str(who))

    @_safe
    def face_pick_generic(self, head):
        self._editor.face_pick_generic(head)

    # --- a created look -----------------------------------------------------------------------------
    @_safe
    def look_open(self, look=None):
        self._editor.look_open(look if isinstance(look, dict) else None)

    @_safe
    def look_set(self, part, value):
        self._editor.look_set(str(part), value)

    @_safe
    def look_random(self):
        self._editor.look_random()

    @_safe
    def look_done(self):
        self._editor.look_done()

    # --- Equipment ----------------------------------------------------------------------------------
    @_safe
    def equipment_open(self):
        self._equipment.open()

    @_safe
    def equipment_pick(self, choice, value):
        self._equipment.pick(choice, value)

    @_safe
    def equipment_apply(self, whole_team=False):
        (self._equipment.apply_team if whole_team else self._equipment.apply_player)()

    @_safe
    def equipment_undo(self):
        self._equipment.undo()

    @_safe
    def equipment_close(self):
        self._equipment.close()

    @_safe
    def equipment_mask_picture(self):
        self._equipment.choose_mask_picture()

    @_safe
    def equipment_mask_clear(self):
        self._equipment.clear_mask_picture()

    @_safe
    def equipment_mask_template(self):
        self._equipment.mask_template()

    # --- Lines ----------------------------------------------------------------------------------------
    @_safe
    def lines_open(self):
        self._lines.open()

    @_safe
    def lines_tab(self, tab):
        self._lines.set_tab(tab)

    @_safe
    def lines_slot(self, slot):
        self._lines.pick_slot(slot)

    @_safe
    def lines_place(self, who):
        self._lines.place(who)

    @_safe
    def lines_letter(self, who, letter=None):
        self._lines.set_letter(who, letter)

    @_safe
    def lines_apply(self):
        self._lines.apply()

    @_safe
    def lines_undo(self):
        self._lines.undo()

    @_safe
    def lines_close(self):
        self._lines.close()

    # --- Strategies -----------------------------------------------------------------------------------
    @_safe
    def strategy_open(self):
        self._strategy.open()

    @_safe
    def strategy_set(self, field, value):
        self._strategy.set(field, value)

    @_safe
    def strategy_reset(self, field=None):
        self._strategy.reset(field)

    @_safe
    def strategy_apply(self):
        self._strategy.apply()

    @_safe
    def strategy_undo(self):
        self._strategy.undo()

    @_safe
    def strategy_close(self):
        self._strategy.close()

    # --- Jerseys and ice ----------------------------------------------------------------------------
    @_safe
    def uniforms_open(self):
        self._editor.uniforms_open()

    @_safe
    def uniforms_colour(self, part, text):
        self._uniforms.set_colour(part, text)

    @_safe
    def uniforms_crest(self, mine=True):
        if mine:
            self._uniforms.choose_crest()
        else:
            self._uniforms.clear_crest()

    @_safe
    def uniforms_pick(self, variant, value):
        self._uniforms.pick(variant, value)

    @_safe
    def uniforms_ice(self, value):
        self._uniforms.pick_ice(value)

    @_safe
    def uniforms_arena(self, text):
        self._uniforms.set_arena(text)

    @_safe
    def uniforms_template(self, variant=None, which='game'):
        self._uniforms.template(variant, which)

    @_safe
    def uniforms_kit(self, action, first=None, second=None, third=None):
        args = [a for a in (first, second, third) if a is not None]
        self._uniforms.kit(action, *args)

    @_safe
    def uniforms_kit_picture(self):
        self._uniforms.kit_picture()

    @_safe
    def uniforms_apply(self):
        self._uniforms.apply()

    @_safe
    def uniforms_undo(self):
        self._uniforms.undo()

    @_safe
    def uniforms_close(self):
        self._uniforms.close()

    # --- Calendar -------------------------------------------------------------------------------------
    @_safe
    def calendar_month(self, step):
        self._calendar.month(int(step))

    @_safe
    def calendar_day(self, date=None):
        self._calendar.day(date or None)

    @_safe
    def calendar_today(self):
        self._calendar.today()

    @_safe
    def calendar_mode(self, mode):
        self._calendar.mode(str(mode))

    @_safe
    def calendar_season(self, on):
        self._calendar.season(bool(on))

    # --- Front office -----------------------------------------------------------------------------------
    @_safe
    def office_sort(self, key):
        self._office.sort(str(key))

    @_safe
    def office_group(self, group):
        self._office.group(group)

    @_safe
    def contract_open(self, key):
        self._editor.contract_open(str(key))

    @_safe
    def contract_change(self, field, value):
        self._office.contract_change(str(field), value)

    @_safe
    def contract_close(self):
        self._office.contract_close()

    @_safe
    def contract_apply(self):
        self._office.contract_apply()

    @_safe
    def contract_reset(self):
        self._office.contract_reset()

    # --- Draft & Pro -------------------------------------------------------------------------------------
    @_safe
    def prospects_show(self, view):
        self._prospects.show(view)

    @_safe
    def prospects_step(self, step):
        self._prospects.step(int(step))

    @_safe
    def prospects_pick(self, key, typed=None):
        self._prospects.pick(str(key), typed)

    @_safe
    def prospects_add(self):
        self._prospects.add()

    @_safe
    def prospects_set(self, field, value):
        self._prospects.set(str(field), value)

    @_safe
    def prospects_remove(self, key):
        self._prospects.remove(str(key))

    @_safe
    def prospects_make_open(self):
        self._prospects.make_open()

    @_safe
    def prospects_make_set(self, field, value):
        self._prospects.make_set(str(field), value)

    @_safe
    def prospects_make(self):
        self._prospects.make()

    @_safe
    def prospects_close(self):
        self._prospects.close()

    @_safe
    def prospects_import(self):
        self._prospects.import_class()

    @_safe
    def prospects_export(self):
        self._prospects.export_class()

    # --- Be a Pro careers (Draft & Pro) ------------------------------------------------------------------------------
    @_safe
    def career_look(self):
        self._career.look(fresh=True)

    @_safe
    def career_open(self, folder):
        self._career.open(str(folder))

    @_safe
    def career_set(self, field, value):
        self._career.set(str(field), value)

    @_safe
    def career_undo(self):
        self._career.undo()

    @_safe
    def career_save(self):
        self._career.save()
