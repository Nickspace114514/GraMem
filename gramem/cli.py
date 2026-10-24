import argparse
from pathlib import Path

from .config import Config
from .documents import ingest
from .engine import Engine
from .graph import FalkorGraph
from .migrate import import_exclusions, import_records, load_records
from .model import Model
from .tokens import compact


def main(argv=None):
    parser = argparse.ArgumentParser(description="GraMem standalone memory management")
    parser.add_argument("--home", type=Path, required=True, help="Hermes profile home")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("worker")
    commands.add_parser("knowledge-worker")
    chats = commands.add_parser("chats")
    chats.add_argument("action", choices=["overview", "search", "read", "export", "audio", "bundle", "process", "progress", "retry"])
    chats.add_argument("value", nargs="?", default="")
    chats.add_argument("--platform", default="")
    chats.add_argument("--session", default="")
    chats.add_argument("--after", type=float)
    chats.add_argument("--before", type=float)
    chats.add_argument("--start", type=int, default=0)
    chats.add_argument("--destination", type=Path)
    chats.add_argument("--audio-id", default="")
    network = commands.add_parser("network")
    network.add_argument("query", nargs="?", default="")
    network.add_argument("--hops", type=int, default=2)
    network.add_argument("--historical", action="store_true")
    library = commands.add_parser("knowledge")
    library.add_argument(
        "action", choices=["list", "search", "get", "read", "export", "retry", "backup"]
    )
    library.add_argument("value", nargs="?", default="")
    library.add_argument("--historical", action="store_true")
    library.add_argument("--page", type=int, default=1)
    library.add_argument("--start", type=int, default=0)
    library.add_argument("--destination", type=Path)
    commands.add_parser("maintain")
    commands.add_parser("review")
    recall = commands.add_parser("recall")
    recall.add_argument("query")
    recall.add_argument("--historical", action="store_true")
    remember = commands.add_parser("remember")
    remember.add_argument("content")
    remember.add_argument("--type", default="knowledge")
    remember.add_argument("--slot", default="")
    for name in ("forget", "suppress", "reactivate", "reauthorize"):
        sub = commands.add_parser(name)
        sub.add_argument("slot")
    for name in ("confirm", "reject"):
        sub = commands.add_parser(name)
        sub.add_argument("id")
    document = commands.add_parser("ingest")
    document.add_argument("path", type=Path)
    graph = commands.add_parser("graph")
    graph.add_argument("query", default="", nargs="?")
    graph.add_argument("--hops", type=int, default=1)
    graph.add_argument("--historical", action="store_true")
    backup = commands.add_parser("backup")
    backup.add_argument("destination", type=Path)
    imports = commands.add_parser("import")
    imports.add_argument("path", type=Path)
    imports.add_argument("--activate", action="store_true")
    imports.add_argument("--exclusions", type=Path)
    commands.add_parser("profile")
    commands.add_parser("reflect")
    args = parser.parse_args(argv)
    home = args.home.resolve()
    engine = None
    try:
        config = Config.load(home / "gramem" / "config.json")
        import hashlib

        config.graph_name += "_" + hashlib.sha256(str(home).encode()).hexdigest()[:12]
        p = config.principal("cli", "")
        if p.scope != "owner" and args.command != "status":
            parser.error("CLI owner access requires trusted_cli_owner in this profile config")
        engine = Engine(
            home / "gramem" / "memory.sqlite", config, Model(config), FalkorGraph(config)
        )
        cmd = args.command
        from .knowledge import Knowledge

        kb = Knowledge(engine)
        if cmd == "chats":
            from .chats import Chats

            archive = Chats(engine)
            filters = {k: getattr(args, k) for k in ("platform", "session", "after", "before")}
            if args.action in {'process','progress','retry'}:
                from .chat_backfill import Backfill

                result = getattr(Backfill(engine), {'process':'request','progress':'status','retry':'retry'}[args.action])(p)
            elif args.action == "overview":
                result = archive.overview(p, **filters)
            elif args.action == "search":
                result = archive.search(p, args.value, start=args.start, **filters)
            elif args.action == "read":
                result = archive.read(p, args.value)
            else:
                if not args.destination:
                    raise ValueError("export needs --destination")
                if args.action == 'export':
                    info, data = archive.original(p, args.value)
                else:
                    from .chat_audio import ChatAudio

                    audio = ChatAudio(engine)
                    info, data = audio.bundle(p, args.value) if args.action == 'bundle' else audio.original(p, args.value, args.audio_id)
                with args.destination.open("xb") as out:
                    import os

                    os.chmod(args.destination, 0o600)
                    out.write(data)
                result = {**info, "path": str(args.destination)}
        elif cmd == "network":
            from .network import Network

            result = Network(engine).query(p, args.query, hops=args.hops, historical=args.historical)
        elif cmd == "knowledge":
            if args.action == "list":
                result = kb.list(p, query=args.value, page=args.page, historical=args.historical)
            elif args.action == "search":
                result = kb.search(p, args.value, historical=args.historical)
            elif args.action == "get":
                result = kb.get(p, args.value)
            elif args.action == "read":
                result = kb.read(p, args.value, start=args.start)
            elif args.action == "retry":
                result = kb.retry(p, args.value)
            elif args.action == "backup":
                if not args.destination:
                    raise ValueError("backup needs --destination")
                result = kb.backup(args.destination)
            else:
                if not args.destination:
                    raise ValueError("export needs --destination")
                info, data = kb.original(p, args.value)
                with args.destination.open("xb") as out:
                    import os

                    os.chmod(args.destination, 0o600)
                    out.write(data)
                result = {"path": str(args.destination), "sha256": info["sha256"]}
        elif cmd == "status":
            result = engine.status()
        elif cmd == "recall":
            result = engine.recall(p, args.query, historical=args.historical)
        elif cmd == "remember":
            result = {"id": engine.remember(p, args.content, kind=args.type, slot=args.slot)}
        elif cmd in {"forget", "suppress"}:
            result = engine.exclude(
                p, args.slot, state="deleted" if cmd == "forget" else "suppressed"
            )
        elif cmd in {"reactivate", "reauthorize"}:
            result = engine.reactivate(p, args.slot, reauthorize=cmd == "reauthorize")
        elif cmd in {"confirm", "reject"}:
            engine.confirm(p, args.id, reject=cmd == "reject")
            result = {"success": True}
        elif cmd == "graph":
            result = engine.graph(p, args.query, hops=args.hops, historical=args.historical)
        elif cmd == "reflect":
            from .reflection import reflect

            result = reflect(engine, p)
        elif cmd == "profile":
            result = engine.profile(p)
        elif cmd == "maintain":
            result = {"lifecycle_changes": engine.maintain(), "graph_synced": engine.flush_graph()}
        elif cmd == "review":
            result = {"review_processed": engine.review_one(), "graph_synced": engine.flush_graph()}
        elif cmd == "ingest":
            result = ingest(engine, p, args.path)
        elif cmd == "backup":
            engine.store.backup(args.destination)
            result = {"memory_backup": str(args.destination), "graph_backup_required": True}
        elif cmd == "import":
            if args.exclusions:
                import_exclusions(engine, p, load_records(args.exclusions))
            result = import_records(engine, p, load_records(args.path), review=not args.activate)
        else:
            import time

            last_maintenance = last_weekly = 0
            while True:
                worked = kb.process_one()
                worked = kb.embed_one() or worked
                worked = engine.process_one() or worked
                worked = engine.review_one() or worked
                from .chat_backfill import Backfill
                from .chats import Chats
                from .network import Network

                worked = Backfill(engine).step(home / 'state.db') or worked
                worked = Chats(engine).process_one() or worked
                if not worked:
                    Network(engine).sync_one()
                engine.flush_graph(limit_jobs=10)
                if cmd == "knowledge-worker":
                    if not worked:
                        time.sleep(1)
                    continue
                now = engine.clock()
                if now - last_maintenance > 86400:
                    engine.maintain()
                    last_maintenance = now
                if now - last_weekly > 3600:
                    from .reflection import weekly

                    weekly(engine)
                    last_weekly = now
                if not worked:
                    time.sleep(1)
        print(compact(result))
    except (ValueError, PermissionError, KeyError, OSError, RuntimeError) as exc:
        parser.exit(2, str(exc) + "\n")
    except KeyboardInterrupt:
        pass
    finally:
        if engine:
            engine.close()


if __name__ == "__main__":
    main()
