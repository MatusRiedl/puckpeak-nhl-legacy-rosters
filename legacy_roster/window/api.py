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
    def __init__(self, host, update, editor=None, uniforms=None, equipment=None):
        self._host, self._update, self._editor, self._uniforms = host, update, editor, uniforms
        self._equipment = equipment

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
    def open_error_log(self):
        path = datasource.app_dir('logs', 'error.log')
        import os
        if not os.path.exists(path):
            with open(path, 'a', encoding='utf-8'):
                pass
        self._host.open_path(path)

    @_safe
    def tab(self, name):
        if name == 'editor' and self._editor is not None:
            self._editor.opened()

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
    def uniforms_template(self, variant=None):
        self._uniforms.template(variant)

    @_safe
    def uniforms_apply(self):
        self._uniforms.apply()

    @_safe
    def uniforms_undo(self):
        self._uniforms.undo()

    @_safe
    def uniforms_close(self):
        self._uniforms.close()
