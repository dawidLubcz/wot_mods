__doc__ = """
    World of tanks modification for collecting time spent in the game.
    Time is split into states like:
    * game initialization
    * game lobby
    * battle
    
    Data is stored locally on json file.
"""

import os.path
import shutil
import time
import datetime
import json


is_wot_runtime = True
try:
    import Avatar
    from gui.Scaleform.daapi.view.battle.shared.minimap.plugins import ArenaVehiclesPlugin
    from messenger import MessengerEntry
    from states.StateInBattle import StateInBattle
    from states.StateInGarage import StateInGarage
except ImportError:
    is_wot_runtime = False
    print("Could not import world of tanks modules")


class Hook:
    """Class for injecting function call to specific class method"""

    def __init__(self, classType, method):
        self._classType = classType
        self._method = method
        self._originalMethod = getattr(classType, method)

    def __call__(self, injectedFunction):
        def wrapper(*args, **kwargs):
            injectedFunction(*args)
            # call original method to keep proper code flow
            return self._originalMethod(*args, **kwargs)

        # overwrite original method with wrapper
        setattr(self._classType, self._method, wrapper)
        return wrapper


class Logger:
    """Logger to python.log file and game chat"""

    config = {
        'loggerPrefix': 'ArenaSpy',
        'logPython': True,
        'logInGame': True,
    }

    @staticmethod
    def log(func):
        """Decorator to log method params to the python.log file"""

        def wrapper(*args, **kwargs):
            if Logger.config['logPython'] is True:
                params = []
                for arg in args:
                    params.append(arg)
                print(Logger.config['loggerPrefix'], func.__name__, params)
            return func(*args, **kwargs)

        return wrapper

    @staticmethod
    def logingame(func):
        """Decorator to log method params to the ingame chat"""

        def wrapper(*args, **kwargs):
            if Logger.config['logInGame'] is True:
                params = ""
                for arg in args:
                    params += '_' + str(arg)
                # if there are whitespaces text can be cut by the game chat
                params = params.replace(" ", "")
                params = params.replace("\n", "")
                MessengerEntry.g_instance.gui.addClientMessage(func.__name__ + params)
            return func(*args, **kwargs)

        return wrapper


class BadStateException(Exception):
    """Exception for any unexpected state in state machine."""


class GameStates:
    """Class which describes supported game states"""

    class Names:
        """Game states names"""

        BASE = "STATE_BASE"
        CLIENT_LOADING = "STATE_CLIENT_LOADING"
        LOBBY_LOADED = "STATE_LOBBY_LOADED"
        ARENA_LOADED = "STATE_ARENA_LOADED"

    def on_client_started(self):
        """Initial state, could be called on object creation"""
        raise NotImplementedError()

    def on_lobby_loaded(self):
        """Called when the game lobby is loaded"""
        raise NotImplementedError()

    def on_arena_loaded(self):
        """Called when the game battle is started"""
        raise NotImplementedError()

    def on_veh_destroyed(self):
        """Not supported so far"""
        raise NotImplementedError()


class Context:
    """Interface for calling back context/manager class for changing current state"""

    def set_state(self, state):
        """Update current state"""
        raise NotImplementedError()

    def save_state(self, state):
        """Save state to cache (later cache should be pushed to the database)"""
        raise NotImplementedError()


class StateData:
    """Dataclass for keeping state params together"""

    def __init__(self, start=0, stop=0, name=GameStates.Names.BASE):
        self._start_timestamp = start
        self._stop_timestamp = stop
        self._state_name = name

    @property
    def start_timestamp(self):
        """Timestamp when state was activated (getter)"""
        return self._start_timestamp

    @start_timestamp.setter
    def start_timestamp(self, value):
        """Timestamp when state was activated (setter)"""
        self._start_timestamp = value

    @property
    def stop_timestamp(self):
        """Timestamp when state was deactivated (getter)"""
        return self._stop_timestamp

    @stop_timestamp.setter
    def stop_timestamp(self, value):
        """Timestamp when state was deactivated (setter)"""
        self._stop_timestamp = value

    @property
    def state_name(self):
        """State name (getter)"""
        return self._state_name

    @state_name.setter
    def state_name(self, value):
        """State name (setter)"""
        self.state_name = value


class State:
    """Interface to define state functionality
     from context point of view"""

    def get_state_data(self):
        """
        Get data corresponds to specific state.
        Derived classes should overwrite data (i.e. state_name) in this method.
        """
        raise NotImplementedError()

    def save_to_cache(self):
        """
        Save state object to cache (list).
        Use cache to write to the database once for all items stored in the cache.
        """
        raise NotImplementedError()

    def on_exit(self):
        """
        Has to be called when the object will be destroyed/the game will be closed
        to save current (not finished) state
        """
        raise NotImplementedError()


class GameStateBase(GameStates, State):
    """Game state base class. Class holds common methods used by derived classes"""

    STATE_NAME = GameStates.Names.BASE

    def __init__(self, context):
        self._state_data = StateData(name=self.STATE_NAME)
        self._context = context

    def __repr__(self):
        return "{}: start={} stop={}".format(self.__class__.__name__,
                                             self._state_data.start_timestamp,
                                             self._state_data.stop_timestamp)

    def _start(self):
        if self._state_data.start_timestamp > 0:
            return
        self._state_data.start_timestamp = int(time.time() * 1000)

    def _stop(self):
        if self._state_data.stop_timestamp > 0:
            return
        self._state_data.stop_timestamp = int(time.time() * 1000)

    def _bad_state_exception(self, method_name, class_name):
        raise BadStateException(
            "State not allowed, class={}, method={} ".format(
                str(class_name), str(method_name)))

    def get_state_data(self):
        return self._state_data

    def save_to_cache(self):
        self._context.save_state(self)

    def _transition(self, next_state):
        """
        Called from state classes to update current state in the context
        (modification class) object.
        """
        self._stop()
        self.save_to_cache()
        next_state._start()
        self._context.set_state(next_state)

    def on_client_started(self):
        pass

    def on_lobby_loaded(self):
        pass

    def on_arena_loaded(self):
        pass

    def on_veh_destroyed(self):
        pass

    def on_exit(self):
        """
        Has to be called when the object will be destroyed/the game will be closed
        to save current (not finished) state
        """
        self._stop()
        self.save_to_cache()


class ArenaLoadedState(GameStateBase):
    """WOT battle state"""

    STATE_NAME = GameStates.Names.ARENA_LOADED

    def __init__(self, context):
        GameStateBase.__init__(self, context)
        self._veh_destroyed_timestamp = 0

    def _stop(self):
        GameStateBase._stop(self)
        self._veh_destroyed_timestamp = self._state_data.stop_timestamp

    def on_client_started(self):
        self._bad_state_exception(method_name="on_client_started", class_name="ArenaLoadedState")

    def on_lobby_loaded(self):
        self._transition(LobbyLoadedState(self._context))

    def on_arena_loaded(self):
        self._start()

    def on_veh_destroyed(self):
        if self._veh_destroyed_timestamp > 0:
            return
        self._veh_destroyed_timestamp = time.time()


class LobbyLoadedState(GameStateBase):
    """Game lobby state"""

    STATE_NAME = GameStates.Names.LOBBY_LOADED

    def __init__(self, context):
        GameStateBase.__init__(self, context)

    def on_client_started(self):
        self._bad_state_exception(method_name="on_client_started", class_name="LobbyLoadedState")

    def on_lobby_loaded(self):
        self._start()

    def on_arena_loaded(self):
        self._transition(ArenaLoadedState(self._context))

    def on_veh_destroyed(self):
        self._bad_state_exception(method_name="on_veh_destroyed", class_name="LobbyLoadedState")


class ClientLoadingState(GameStateBase):
    """State between starting the game and loading the lobby"""

    STATE_NAME = GameStates.Names.CLIENT_LOADING

    def __init__(self, context):
        GameStateBase.__init__(self, context)

    def on_client_started(self):
        self._start()

    def on_lobby_loaded(self):
        self._transition(LobbyLoadedState(self._context))

    def on_arena_loaded(self):
        self._bad_state_exception(method_name="on_arena_loaded", class_name="ClientLoadingState")

    def on_veh_destroyed(self):
        self._bad_state_exception(method_name="on_veh_destroyed", class_name="ClientLoadingState")


class Database:
    """Database wrapper interface"""

    def load_data(self):
        """Load stored data"""
        raise NotImplementedError()

    def commit(self, data):
        """Save data do persistent memory"""
        raise NotImplementedError()


class JsonDb:
    """Simple db to store data in a json file"""

    def __init__(self, file_name):
        self._file_name = file_name
        self._backup_file_name = file_name + '.backup'

    def _create_if_not_exist(self):
        if not os.path.isfile(self._file_name):
            with open(self._file_name, 'a', encoding='utf-8') as file_object:
                file_object.write('{}')

    def load(self, table_name):
        """Load data from json file"""

        self._create_if_not_exist()
        with open(self._file_name, 'r', encoding='utf-8') as file_object:
            content = json.load(file_object)
            results = []
            if table_name in content:
                for row in content[table_name]:
                    results.append(
                        SimpleDiscCache.DataRow.from_db_type(row)
                    )
            return results

    def _save_backup(self):
        shutil.copy2(self._file_name, self._backup_file_name)

    def _restore_from_backup(self):
        shutil.copy2(self._backup_file_name, self._file_name)

    def commit(self, table_name, data):
        """Save data to json file"""

        self._create_if_not_exist()
        self._save_backup()
        content = None
        try:
            with open(self._file_name, 'r', encoding='utf-8') as file_object:
                content = json.load(file_object)
                if table_name not in content:
                    content[table_name] = []
                for data_item in data:
                    print("JsonDb: commit item: {}".format(data_item))
                    data_row = SimpleDiscCache.DataRow.from_state(data_item)
                    content[table_name].append(
                        SimpleDiscCache.DataRow.to_db_type(data_row)
                    )
            if content:
                with open(self._file_name, 'w', encoding='utf-8') as file_object:
                    json.dump(content, file_object, indent=4)
                    self._save_backup()
        except:
            self._restore_from_backup()
        return True


class SimpleDiscCache(Database):
    """Wrapper for json database"""

    TABLE_NAME = "WOT_GAME_TIME"

    class DataRow:
        """Class for defining database table row"""

        STATE_LOADING = 'LOADING'
        STATE_LOBBY = 'LOBBY'
        STATE_ARENA = 'ARENA'

        def __init__(self):
            self.date = ""
            self.duration = 0
            self.game_state = ""

        @staticmethod
        def from_db_type(db_type):
            """Create DataRow object from database type"""
            data_row = SimpleDiscCache.DataRow()
            data_row.date = db_type["date"]
            data_row.duration = db_type["duration"]
            data_row.game_state = db_type["game_state"]
            return data_row

        @staticmethod
        def from_state(state):
            """Create DataRow object from state type"""
            data_row = SimpleDiscCache.DataRow()
            state_data = state.get_state_data()
            data_row.date = state_data.start_timestamp
            data_row.duration = state_data.stop_timestamp - state_data.start_timestamp
            data_row.game_state = state_data.state_name
            return data_row

        @staticmethod
        def to_db_type(data_row):
            """Save database type object based on DataRow"""
            return {
                "date": data_row.date,
                "duration": data_row.duration,
                "game_state": data_row.game_state
            }

    def __init__(self, file_name="mod_ingametimespent_database.json"):
        self._db = JsonDb(file_name)

    def load_data(self):
        """Load data from db"""
        return self._db.load(SimpleDiscCache.TABLE_NAME)

    def commit(self, data):
        """Save data to db"""
        return self._db.commit(SimpleDiscCache.TABLE_NAME, data)


class HistoricStats:
    """Class for calculating stats based on data
    fetched from the database"""

    def __init__(self):
        self._data = []
        self.all_time_avg_time_spent = 0

        self.all_time_avg_game_loading = 0
        self.all_time_loading_counter = 0

        self.all_time_avg_game_lobby = 0
        self.all_time_lobby_counter = 0

        self.all_time_avg_game_arena = 0
        self.all_time_arena_counter = 0

        self.curr_month_avg_time_spent = 0
        self.curr_month_counter = 0

        self.curr_month_avg_game_loading = 0
        self.curr_month_loading_counter = 0

        self.curr_month_avg_game_lobby = 0
        self.curr_month_lobby_counter = 0

        self.curr_month_avg_game_arena = 0
        self.curr_month_arena_counter = 0

    def set_data(self, data):
        """Set loaded items"""
        self._data = data

    @staticmethod
    def _get_date(row_date):
        date = datetime.datetime.fromtimestamp(int(row_date) / 1000)
        return date

    def calculate_stats(self):
        """Calculate parameters"""

        for row in self._data:
            self.all_time_avg_time_spent += row.duration
            if row.game_state == SimpleDiscCache.DataRow.STATE_LOADING:
                self.all_time_avg_game_loading += row.duration
                self.all_time_loading_counter += 1
            if row.game_state == SimpleDiscCache.DataRow.STATE_LOBBY:
                self.all_time_avg_game_lobby += row.duration
                self.all_time_lobby_counter += 1
            if row.game_state == SimpleDiscCache.DataRow.STATE_ARENA:
                self.all_time_avg_game_arena += row.duration
                self.all_time_arena_counter += 1
            date = HistoricStats._get_date(row.date)
            if date.year == datetime.datetime.now().year and \
                    date.month == datetime.datetime.now().month:
                self.curr_month_avg_time_spent += row.duration
                self.curr_month_counter += 1
                if row.game_state == SimpleDiscCache.DataRow.STATE_LOADING:
                    self.curr_month_avg_game_loading += row.duration
                    self.curr_month_loading_counter += 1
                if row.game_state == SimpleDiscCache.DataRow.STATE_LOBBY:
                    self.curr_month_avg_game_lobby += row.duration
                    self.curr_month_lobby_counter += 1
                if row.game_state == SimpleDiscCache.DataRow.STATE_ARENA:
                    self.curr_month_avg_game_arena += row.duration
                    self.curr_month_arena_counter += 1
        if len(self._data) > 0:
            self.all_time_avg_time_spent = self.all_time_avg_time_spent / len(self._data)
            if self.all_time_loading_counter > 0:
                self.all_time_avg_game_loading = \
                    self.all_time_avg_game_loading / self.all_time_loading_counter
            if self.all_time_lobby_counter > 0:
                self.all_time_avg_game_lobby = \
                    self.all_time_avg_game_lobby / self.all_time_lobby_counter
            if self.all_time_arena_counter > 0:
                self.all_time_avg_game_arena = \
                    self.all_time_avg_game_arena / self.all_time_arena_counter
            if self.curr_month_counter > 0:
                self.curr_month_avg_time_spent = \
                    self.curr_month_avg_time_spent / self.curr_month_counter
            if self.curr_month_loading_counter > 0:
                self.curr_month_avg_game_loading = \
                    self.curr_month_avg_game_loading / self.curr_month_loading_counter
            if self.curr_month_lobby_counter > 0:
                self.curr_month_avg_game_lobby = \
                    self.curr_month_avg_game_lobby / self.curr_month_lobby_counter
            if self.curr_month_arena_counter > 0:
                self.curr_month_avg_game_arena = \
                    self.curr_month_avg_game_arena / self.curr_month_arena_counter


class InGameTimeSpentMod(GameStates, Context):
    """Main mod class / context"""

    def __init__(self):
        self._config = {}
        init_state = ClientLoadingState(self)
        self._state = init_state
        self._state_history_cache = []
        self._database = SimpleDiscCache()
        self._historic_stats = HistoricStats()

    def dump(self):
        """Print states stored in the cache"""

        print("+====== dump start =====+")
        for state in self._state_history_cache:
            print("\t" + str(state))
        print("+====== dump end =====+")
        return self._state_history_cache

    def commit(self):
        """Save cache to the database"""

        if not self._database.commit(self._state_history_cache):
            print("ERROR: Failed to commit!")
            return
        print("Clear cache")
        self._state_history_cache = []

    def set_state(self, state):
        """Update current state"""
        self._state = state

    def save_state(self, state):
        """Save state to cache"""
        self._state_history_cache.append(state)

    def on_client_started(self):
        self._state.on_client_started()

    def on_lobby_loaded(self):
        self._state.on_lobby_loaded()

    def on_arena_loaded(self):
        self._state.on_arena_loaded()

    def on_veh_destroyed(self):
        self._state.on_veh_destroyed()

    def _load_data(self):
        self._historic_stats.set_data(self._database.load_data())

    def get_historic_stats(self):
        """Get historic stats"""
        self._load_data()
        self._historic_stats.calculate_stats()
        return self._historic_stats

    def on_exit(self):
        """Should be called on the game exit to save current state"""
        self._state.on_exit()
        self.commit()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.on_exit()


g_mod = InGameTimeSpentMod()

if is_wot_runtime:
# Game overwritten methods
    @Hook(StateInGarage, 'activate')
    def state_in_garage_activated(*args):
        """Register for a showTracer method."""
        g_mod.on_lobby_loaded()

    @Hook(StateInBattle, 'activate')
    def state_in_battle_activated(*args):
        """Register for a showTracer method."""
        g_mod.on_arena_loaded()


def test_mod_context_init_obj():
    """Mod initial state test"""
    ingame_mod = InGameTimeSpentMod()
    assert ingame_mod._state.STATE_NAME == GameStates.Names.CLIENT_LOADING
    ingame_mod.on_exit()
    cache = ingame_mod.dump()
    assert len(cache) == 0


def test_mod_context_states_lobby_loaded_state():
    """Lobby loaded state test"""
    ingame_mod = InGameTimeSpentMod()
    ingame_mod.on_lobby_loaded()

    cache = ingame_mod.dump()
    assert cache[0].STATE_NAME == GameStates.Names.CLIENT_LOADING
    assert ingame_mod._state.STATE_NAME == GameStates.Names.LOBBY_LOADED
    ingame_mod.on_exit()

    cache = ingame_mod.dump()
    assert len(cache) == 0


def test_mod_context_states_arena_state():
    """Arena loaded state test"""
    ingame_mod = InGameTimeSpentMod()
    ingame_mod.on_lobby_loaded()
    ingame_mod.on_arena_loaded()
    cache = ingame_mod.dump()
    assert cache[0].STATE_NAME == GameStates.Names.CLIENT_LOADING
    assert cache[1].STATE_NAME == GameStates.Names.LOBBY_LOADED
    assert ingame_mod._state.STATE_NAME == GameStates.Names.ARENA_LOADED
    ingame_mod.on_exit()


def test_mod_context_states_arena_lobby():
    """Transition arena -> lobby test"""
    ingame_mod = InGameTimeSpentMod()
    ingame_mod.on_lobby_loaded()
    ingame_mod.on_arena_loaded()
    ingame_mod.on_lobby_loaded()
    cache = ingame_mod.dump()
    assert cache[0].STATE_NAME == GameStates.Names.CLIENT_LOADING
    assert cache[1].STATE_NAME == GameStates.Names.LOBBY_LOADED
    assert cache[2].STATE_NAME == GameStates.Names.ARENA_LOADED
    assert ingame_mod._state.STATE_NAME == GameStates.Names.LOBBY_LOADED
    ingame_mod.on_exit()


def test_mod_context_init_bad_state():
    """Not allowed transitions test"""

    ingame_mod = InGameTimeSpentMod()
    exc_count = 0

    ingame_mod.on_client_started()

    try:
        ingame_mod.on_arena_loaded()
    except BadStateException:
        exc_count += 1

    ingame_mod.on_lobby_loaded()

    try:
        ingame_mod.on_client_started()
    except BadStateException:
        exc_count += 1

    ingame_mod.on_arena_loaded()

    try:
        ingame_mod.on_client_started()
    except BadStateException:
        exc_count += 1

    assert exc_count == 3


class DatabaseMock:
    """Test class for database operations"""

    def __init__(self, file_name="database.db"):
        self.data = []

    def load_data(self):
        """Load prepared data"""
        return self.data

    def commit(self, data_list):
        """Save given list of items to the fake database."""
        for item in data_list:
            self.data.append(item)
        return True


def test_mod_context_on_exit_database_push():
    """Check if data will be pushed to the database"""
    ingame_mod = InGameTimeSpentMod()
    database_mock = DatabaseMock()
    ingame_mod._database = database_mock
    ingame_mod.on_exit()

    assert len(database_mock.data) == 1
    assert database_mock.data[0].STATE_NAME == GameStates.Names.CLIENT_LOADING


def test_mod_context_on_exit_database_load():
    """Check if data will be loaded from the database"""
    ingame_mod = InGameTimeSpentMod()
    database_mock = DatabaseMock()
    timestamp = int(time.time() * 1000)

    item_dict = {
        "date": timestamp,
        "duration": 1000,
        "game_state": GameStates.Names.LOBBY_LOADED
    }
    test_item = SimpleDiscCache.DataRow.from_db_type(item_dict)
    database_mock.data.append(test_item)
    ingame_mod._database = database_mock
    stats = ingame_mod.get_historic_stats()
    ingame_mod.on_exit()

    assert len(database_mock.data) == 2
    assert stats.all_time_avg_time_spent == 1000.0


def testall():
    """Run test functions"""

    import inspect
    import sys

    test_functions = [obj for name, obj in inspect.getmembers(sys.modules[__name__])
                      if (inspect.isfunction(obj) and
                          name.startswith('test') and name != 'testall')]

    for i, test_function in enumerate(test_functions):
        print("{}/{}. Run test function: {}".format(i + 1, len(test_functions), str(test_function)))
        test_function()


def main():
    """Entry function for running the script standalone"""
    testall()


if __name__ == "__main__":
    main()
