"""Hermes directory-plugin entry point, preserving native memory discovery."""


def register(ctx):
    from gramem.hermes import GraMemProvider, register_guards
    from gramem.knowledge_gateway import archive_inbound

    ctx.register_memory_provider(GraMemProvider())
    register_guards(ctx)
    ctx.register_hook("pre_gateway_dispatch", archive_inbound)
