import sqlite3
import time
import datetime

try:
    import Avatar
    from gui.Scaleform.daapi.view.battle.shared.minimap.plugins import ArenaVehiclesPlugin
    from messenger import MessengerEntry


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
            'loggerPrefix' : 'ArenaSpy',
            'logPython' : True,
            'logInGame' : True,
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
except:
    pass


class BadStateException(Exception):
    pass


class GameStates:
    def on_client_started(self):
        raise NotImplementedError()

    def on_lobby_loaded(self):
        raise NotImplementedError()

    def on_arena_loaded(self):
        raise NotImplementedError()

    def on_veh_destroyed(self):
        raise NotImplementedError()


class Context:
    def set_state(self, state):
        raise NotImplementedError()

    def save_state(self, state):
        raise NotImplementedError()


class GameStateBase(GameStates):
    def __init__(self, context):
        self._start_time = 0
        self._stop_time = 0
        self._context = context

    def __repr__(self):
        return "{}: start={} stop={}".format(self.__class__.__name__, self._start_time, self._stop_time)

    def _start(self):
        if self._start_time > 0:
            return
        self._start_time = int(time.time() * 1000)

    def _stop(self):
        if self._stop_time > 0:
            return
        self._stop_time = int(time.time() * 1000)

    def _bad_state_exception(self, method_name, class_name):
        raise BadStateException("State not allowed, class={}, method={} ".format(str(class_name), str(method_name)))

    def save_to_db(self):
        raise NotImplementedError()

    def save_to_cache(self):
        self._context.save_state(self)

    def transition(self, next_state):
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
        self._stop()
        self.save_to_cache()


class ArenaLoadedState(GameStateBase):
    def __init__(self, context):
        GameStateBase.__init__(self, context)
        self._veh_destroyed_timestamp = 0

    def save_to_db(self):
        pass

    def _stop(self):
        GameStateBase._stop(self)
        self._veh_destroyed_timestamp = self._stop_time

    def on_client_started(self):
        self._bad_state_exception(method_name="on_client_started", class_name="ArenaLoadedState")

    def on_lobby_loaded(self):
        self.transition(LobbyLoadedState(self._context))

    def on_arena_loaded(self):
        self._start()

    def on_veh_destroyed(self):
        if self._veh_destroyed_timestamp > 0:
            return self._veh_destroyed_timestamp
        self._veh_destroyed_timestamp = time.time()


class LobbyLoadedState(GameStateBase):
    def __init__(self, context):
        GameStateBase.__init__(self, context)

    def save_to_db(self):
        pass

    def on_client_started(self):
        self._bad_state_exception(method_name="on_client_started", class_name="LobbyLoadedState")

    def on_lobby_loaded(self):
        self._start()

    def on_arena_loaded(self):
        self.transition(ArenaLoadedState(self._context))

    def on_veh_destroyed(self):
        self._bad_state_exception(method_name="on_veh_destroyed", class_name="LobbyLoadedState")


class ClientLoadingState(GameStateBase):
    def __init__(self, context):
        GameStateBase.__init__(self, context)

    def save_to_db(self):
        pass

    def on_client_started(self):
        self._start()

    def on_lobby_loaded(self):
        self.transition(LobbyLoadedState(self._context))

    def on_arena_loaded(self):
        self._bad_state_exception(method_name="on_arena_loaded", class_name="ClientLoadingState")

    def on_veh_destroyed(self):
        self._bad_state_exception(method_name="on_veh_destroyed", class_name="ClientLoadingState")


class Database:
    class DataRow:
        STATE_LOADING = 'LOADING'
        STATE_LOBBY = 'LOBBY'
        STATE_ARENA = 'ARENA'

        def __init__(self, table_row):
            self.wot_trace_id = table_row[0]
            self.date = str(table_row[1]).encode('utf-8')
            self.duration = table_row[2]
            self.game_state = str(table_row[3]).encode('utf-8')
            self.param1 = table_row[4]
            self.param2 = table_row[5]
            self.param3 = table_row[6]
            self.param4 = table_row[7]

        def __repr__(self):
            return "{}/{}/{}/{}".format(self.wot_trace_id, self.date, self.game_state, self.duration)

        @staticmethod
        def create_query():
            query = """CREATE TABLE {} (
wot_trace_id INTEGER PRIMARY KEY,
date TEXT NOT NULL,
duration REAL NOT NULL,
game_state TEXT NOT NULL,
param1 TEXT,
param2 TEXT,
param3 TEXT,
param4 TEXT
)
""".format(Database.TABLE_NAME)
            return query

    TABLE_NAME = "WOT_GAME_TIME"

    def __init__(self, file_name="database.db"):
        self._file_name = file_name
        self._fresh_database = not self._check_table()

    def _connect(self):
        connection = sqlite3.connect(self._file_name)
        cursor = connection.cursor()
        return cursor, connection

    def _execute_on_db(self, query, callback):
        cursor, connection = self._connect()
        try:
            print("DB: {}".format(query))
            result = cursor.execute(query)
            if callback:
                callback(result)
        except Exception as e:
            print("Database->_check_table(): Failed to fetch data from {}, msg: {}".format(self._file_name, e))
        finally:
            connection.close()

    def _check_table(self):
        is_table_exists = {
            'result': False
        }

        def on_result_ready(result):
            if result.fetchone() is not None:
                is_table_exists['result'] = True

        self._execute_on_db(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='{}';".format(Database.TABLE_NAME),
            on_result_ready
        )
        return is_table_exists['result']

    def _create_wot_table(self):
        query = Database.DataRow.create_query()
        self._execute_on_db(query, None)

    def load_data(self):
        if self._fresh_database:
            self._create_wot_table()
            return []

        query = "SELECT * FROM {}".format(Database.TABLE_NAME)
        data = []

        def data_ready(result):
            fetch = result.fetchall()
            for row in fetch:
                data.append(Database.DataRow(row))
        self._execute_on_db(query, data_ready)
        return data


class HistoricStats:
    def __init__(self, data):
        self._data = data
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
        self._calculate_stats()

    @staticmethod
    def _get_date(row_date):
        date = datetime.datetime.fromtimestamp(int(row_date)/1000)
        return date

    def _calculate_stats(self):
        for row in self._data:
            self.all_time_avg_time_spent += row.duration
            if row.game_state == Database.DataRow.STATE_LOADING:
                self.all_time_avg_game_loading += row.duration
                self.all_time_loading_counter += 1
            if row.game_state == Database.DataRow.STATE_LOBBY:
                self.all_time_avg_game_lobby += row.duration
                self.all_time_lobby_counter += 1
            if row.game_state == Database.DataRow.STATE_ARENA:
                self.all_time_avg_game_arena += row.duration
                self.all_time_arena_counter += 1
            date = HistoricStats._get_date(row.date)
            if date.year == datetime.datetime.now().year and \
               date.month == datetime.datetime.now().month:
                self.curr_month_avg_time_spent += row.duration
                self.curr_month_counter += 1
                if row.game_state == Database.DataRow.STATE_LOADING:
                    self.curr_month_avg_game_loading += row.duration
                    self.curr_month_loading_counter += 1
                if row.game_state == Database.DataRow.STATE_LOBBY:
                    self.curr_month_avg_game_lobby += row.duration
                    self.curr_month_lobby_counter += 1
                if row.game_state == Database.DataRow.STATE_ARENA:
                    self.curr_month_avg_game_arena += row.duration
                    self.curr_month_arena_counter += 1
        if len(self._data) > 0:
            self.all_time_avg_time_spent = self.all_time_avg_time_spent / len(self._data)
            if self.all_time_loading_counter > 0:
                self.all_time_avg_game_loading = self.all_time_avg_game_loading / self.all_time_loading_counter
            if self.all_time_lobby_counter > 0:
                self.all_time_avg_game_lobby = self.all_time_avg_game_lobby / self.all_time_lobby_counter
            if self.all_time_arena_counter > 0:
                self.all_time_avg_game_arena = self.all_time_avg_game_arena / self.all_time_arena_counter
            if self.curr_month_counter > 0:
                self.curr_month_avg_time_spent = self.curr_month_avg_time_spent / self.curr_month_counter
            if self.curr_month_loading_counter > 0:
                self.curr_month_avg_game_loading = self.curr_month_avg_game_loading / self.curr_month_loading_counter
            if self.curr_month_lobby_counter > 0:
                self.curr_month_avg_game_lobby = self.curr_month_avg_game_lobby / self.curr_month_lobby_counter
            if self.curr_month_arena_counter > 0:
                self.curr_month_avg_game_arena = self.curr_month_avg_game_arena / self.curr_month_arena_counter


class InGameTimeSpentMod(GameStates, Context):
    def __init__(self):
        self._config = {

        }
        init_state = ClientLoadingState(self)
        self._state = init_state
        self._state_history_cache = set()
        self._historic_stats = HistoricStats(Database().load_data())

    def dump(self):
        for state in self._state_history_cache:
            print(state)

    def set_state(self, state):
        self._state = state

    def save_state(self, state):
        self._state_history_cache.add(state)

    def on_client_started(self):
        self._state.on_client_started()

    def on_lobby_loaded(self):
        self._state.on_lobby_loaded()

    def on_arena_loaded(self):
        self._state.on_arena_loaded()

    def on_veh_destroyed(self):
        self._state.on_veh_destroyed()

    def on_exit(self):
        self._state.on_exit()


def main():
    ingame_mod = InGameTimeSpentMod()
    ingame_mod.on_client_started()
    ingame_mod.on_lobby_loaded()
    ingame_mod.on_arena_loaded()
    ingame_mod.on_lobby_loaded()
    ingame_mod.on_arena_loaded()
    ingame_mod.on_lobby_loaded()
    ingame_mod.on_exit()
    ingame_mod.dump()

    print(ingame_mod._historic_stats.all_time_avg_time_spent)
    print(ingame_mod._historic_stats.all_time_avg_game_loading)
    print(ingame_mod._historic_stats.all_time_avg_game_lobby)
    print(ingame_mod._historic_stats.all_time_avg_game_arena)
    print(ingame_mod._historic_stats.curr_month_avg_time_spent)
    print(ingame_mod._historic_stats.curr_month_avg_game_loading)
    print(ingame_mod._historic_stats.curr_month_avg_game_lobby)
    print(ingame_mod._historic_stats.curr_month_avg_game_arena)


if __name__ == "__main__":
    main()
