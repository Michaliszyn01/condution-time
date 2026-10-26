from desktop.single_instance import ERROR_ALREADY_EXISTS, SingleInstance
from desktop import startup_manager
from desktop.app_state import DesktopAppState


class FakeKernel32:
    def __init__(self, last_error=0):
        self.last_error = last_error
        self.closed = []
        self.released = []

    def CreateMutexW(self, *_args):
        return 42

    def GetLastError(self):
        return self.last_error

    def CloseHandle(self, handle):
        self.closed.append(handle)

    def ReleaseMutex(self, handle):
        self.released.append(handle)


def test_single_instance_acquires_and_releases_mutex():
    kernel = FakeKernel32()
    instance = SingleInstance(kernel32=kernel)
    assert instance.acquire() is True
    instance.release()
    assert kernel.released == [42]
    assert kernel.closed == [42]


def test_single_instance_detects_existing_mutex():
    kernel = FakeKernel32(ERROR_ALREADY_EXISTS)
    instance = SingleInstance(kernel32=kernel)
    assert instance.acquire() is False
    assert kernel.closed == [42]
    assert instance.handle is None


class RegistryKey:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class FakeRegistry:
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 1
    KEY_READ = 2
    REG_SZ = 3

    def __init__(self):
        self.values = {}

    def OpenKey(self, *_args):
        return RegistryKey()

    def SetValueEx(self, _key, name, _reserved, _kind, value):
        self.values[name] = value

    def DeleteValue(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError
        del self.values[name]

    def QueryValueEx(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError
        return self.values[name], self.REG_SZ


def test_startup_registry_enable_disable_cycle():
    registry = FakeRegistry()
    startup_manager.enable_startup(registry=registry)
    assert startup_manager.is_startup_enabled(registry=registry) is True
    assert "--background" in registry.values["CondutionTime"]
    startup_manager.disable_startup(registry=registry)
    assert startup_manager.is_startup_enabled(registry=registry) is False


def test_shutdown_state_is_idempotent():
    state = DesktopAppState()
    assert state.begin_shutdown() is True
    assert state.begin_shutdown() is False
    assert state.snapshot()["shutting_down"] is True
