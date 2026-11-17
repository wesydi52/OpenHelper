from . import info, mail, productivity, system
from .registry import Registry


def build_registry(cfg, store) -> Registry:
    reg = Registry()
    for mod in (info, productivity, mail, system):
        mod.register(reg, cfg, store)
    return reg
