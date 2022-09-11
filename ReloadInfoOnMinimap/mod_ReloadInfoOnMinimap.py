__doc__ = """World of tanks modification for showing reload animation
             of ally tank on the minimap after shoot."""

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


# mod
class ReloadInfoMinimap:
    """Modification shows reloading animation on the minimap for tanks in the ally team"""

    def __init__(self):
        self._arenaVehiclesPlugin = None
        self._config = {
            'onShotAnimation': 'reloading_gun'
        }

    def setArenaVehiclesPlugin(self, arenaVehiclesPlugin):
        """Setter for a arena vehicles plugin. Mod wont work until it is not set to proper object"""

        self._arenaVehiclesPlugin = arenaVehiclesPlugin

    def _checkIfAlly(self, shooterId):
        if not self._arenaVehiclesPlugin:
            return False
        isAlly = self._arenaVehiclesPlugin.sessionProvider.getArenaDP().isAlly(shooterId)
        return isAlly

    def onShowTracer(self, shooterId):
        """Show reloading animation if tracer appear"""

        if not self._arenaVehiclesPlugin:
            return

        if not self._checkIfAlly(shooterId):
            return

        if shooterId in self._arenaVehiclesPlugin._entries:
            self._arenaVehiclesPlugin._invoke(
                self._arenaVehiclesPlugin._entries[shooterId].getID(),
                'setAnimation', self._config['onShotAnimation'])



g_reloadInfoMod = ReloadInfoMinimap()

# Game overwritten methods
@Hook(Avatar.PlayerAvatar, 'showTracer')
def reloadInfoshowTracer(*args):
    """Register for a showTracer method."""
    g_reloadInfoMod.onShowTracer(args[1])

@Hook(ArenaVehiclesPlugin, 'start')
def vehPluginStart(*args):
    """Set plugin object."""
    g_reloadInfoMod.setArenaVehiclesPlugin(args[0])
